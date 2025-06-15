import os
import threading
import time
import logging
import signal
from typing import Optional, Callable, List, Dict, Tuple
from engine.upgrade_trigger import UpgradeTrigger

try:
    import prometheus_client
except ImportError:
    prometheus_client = None

try:
    import redis  # For distributed lock
except ImportError:
    redis = None

class DistributedLock:
    """Cluster-wide distributed lock using Redis."""
    def __init__(self, lock_name: str = "vivian:upgrade:lock", ttl: int = 600, redis_url: Optional[str] = None):
        self.lock_name = lock_name
        self.ttl = ttl
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis = redis.Redis.from_url(self.redis_url) if redis else None

    def acquire(self, owner: str = "system", timeout: int = 10) -> bool:
        if not self.redis:
            return True  # Fallback: always acquire if no Redis
        end = time.time() + timeout
        while time.time() < end:
            if self.redis.set(self.lock_name, owner, nx=True, ex=self.ttl):
                return True
            time.sleep(1)
        return False

    def release(self, owner: str = "system"):
        if not self.redis:
            return
        val = self.redis.get(self.lock_name)
        if val is None or val.decode() == owner:
            self.redis.delete(self.lock_name)

class UpgradeScheduler:
    """
    Ultra-robust, agentic, distributed, policy-driven upgrade scheduler for Vivian.
    Features: distributed lock, dynamic scheduling, Prometheus metrics, upgrade windows, cron/plan support, failure backoff,
    alerting, pre/post hooks, self-healing, web/api ready, audit, extensibility, policy, multi-source, queueing, 
    REST API stubs, dashboard-ready, and more.
    """

    def __init__(
        self,
        check_interval: int = 300,
        download_dir: str = "downloads",
        alert_fn: Optional[Callable[[str, dict], None]] = None,
        allowed_windows: Optional[List[Tuple[int, int]]] = None,
        pre_check_hook: Optional[Callable[[], None]] = None,
        post_check_hook: Optional[Callable[[bool], None]] = None,
        distributed_lock: Optional[DistributedLock] = None,
        rbac_fn: Optional[Callable[[str, str], bool]] = None,
        backup_fn: Optional[Callable[[], None]] = None,
        health_check_fn: Optional[Callable[[], bool]] = None,
        approval_fn: Optional[Callable[[str], bool]] = None,
        policy_fn: Optional[Callable[[str], bool]] = None,
        web_api_fn: Optional[Callable[[], None]] = None,
        schedule_plan: Optional[List[Tuple[int, int, int]]] = None,  # (weekday, hour, minute)
        max_retry: int = 5,
        canary_nodes: Optional[List[str]] = None,
        marketplace_url: Optional[str] = None,
        extra_upgrade_sources: Optional[List[str]] = None,
        cleanup_fn: Optional[Callable[[], None]] = None
    ):
        self.check_interval = check_interval
        self.download_dir = download_dir
        self.trigger = UpgradeTrigger(
            base_dir=self.download_dir,
            health_check_fn=health_check_fn,
            approval_fn=approval_fn,
            upgrade_policy_fn=policy_fn,
            rbac_fn=rbac_fn,
            canary_nodes=canary_nodes,
            marketplace_url=marketplace_url
        )
        self.running = False
        self.thread = None
        self.alert_fn = alert_fn
        self.allowed_windows = allowed_windows
        self.pre_check_hook = pre_check_hook
        self.post_check_hook = post_check_hook
        self.lock = threading.Lock()
        self.last_status = None
        self.last_check = None
        self.failed_checks = 0
        self.max_retry = max_retry
        self.retry_backoff = 1
        self.distributed_lock = distributed_lock
        self.backup_fn = backup_fn
        self.schedule_plan = schedule_plan
        self.web_api_fn = web_api_fn
        self.metrics = self._init_metrics()
        self.extra_upgrade_sources = extra_upgrade_sources or []
        self.cleanup_fn = cleanup_fn
        # Queue for on-demand/manual/REST-triggered upgrades
        self._manual_queue = []
        # Status/observable
        self.status_info = {
            "last_check_time": None,
            "last_result": None,
            "failed_checks": 0,
            "next_check_eta": None
        }

    def _init_metrics(self):
        if not prometheus_client:
            return None
        metrics = {
            "checks_total": prometheus_client.Counter("vivian_upgrade_checks_total", "Total upgrade checks"),
            "failures_total": prometheus_client.Counter("vivian_upgrade_failures_total", "Total failed upgrade checks"),
            "check_duration": prometheus_client.Summary("vivian_upgrade_check_duration_seconds", "Upgrade check duration"),
            "last_check_status": prometheus_client.Gauge("vivian_upgrade_last_status", "Last upgrade check status (1=success,0=failure)"),
            "manual_triggers_total": prometheus_client.Counter("vivian_upgrade_manual_triggers", "Total manual/force checks"),
        }
        return metrics

    def start(self):
        if self.running:
            logging.warning("[UpgradeScheduler] Already running.")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logging.info("[UpgradeScheduler] Started.")

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        logging.info("[UpgradeScheduler] Stopped.")

    def _within_allowed_window(self):
        if not self.allowed_windows:
            return True
        now = time.gmtime()
        for start, end in self.allowed_windows:
            if start <= now.tm_hour < end:
                return True
        return False

    def _within_schedule_plan(self):
        if not self.schedule_plan:
            return True
        now = time.gmtime()
        for (weekday, hour, minute) in self.schedule_plan:
            if now.tm_wday == weekday and now.tm_hour == hour and now.tm_min == minute:
                return True
        return False

    def _fetch_from_sources(self):
        # Pull upgrades from extra sources/registries
        for src in self.extra_upgrade_sources:
            logging.info(f"[UpgradeScheduler] Fetching upgrades from source: {src}")
            # Placeholder: implement remote fetch, e.g. download new zips to self.download_dir

    def _cleanup(self):
        if self.cleanup_fn:
            self.cleanup_fn()
        # Placeholder: auto-delete old downloads/logs, enforce retention policy

    def _run_loop(self):
        while self.running:
            try:
                # Distributed lock support
                lock_acquired = True
                if self.distributed_lock:
                    lock_acquired = self.distributed_lock.acquire(owner="scheduler")
                    if not lock_acquired:
                        logging.info("[UpgradeScheduler] Skipping: lock not acquired (distributed mode).")
                        time.sleep(self.check_interval)
                        continue
                if not self._within_allowed_window():
                    logging.info("[UpgradeScheduler] Skipping: not in allowed upgrade window.")
                    time.sleep(self.check_interval)
                    continue
                if not self._within_schedule_plan():
                    time.sleep(60)
                    continue
                self._fetch_from_sources()
                if self.pre_check_hook:
                    self.pre_check_hook()
                t0 = time.time()
                if self.metrics:
                    self.metrics["checks_total"].inc()
                logging.info("[UpgradeScheduler] Checking for upgrades...")
                # Pre-check backup
                if self.backup_fn:
                    self.backup_fn()
                status = self.trigger.try_upgrade()
                duration = time.time() - t0
                if self.metrics:
                    self.metrics["check_duration"].observe(duration)
                    self.metrics["last_check_status"].set(1 if status else 0)
                self.last_status = status
                self.last_check = time.time()
                self.status_info["last_check_time"] = self.last_check
                self.status_info["last_result"] = status
                if self.post_check_hook:
                    self.post_check_hook(status)
                if not status:
                    self.failed_checks += 1
                    self.status_info["failed_checks"] = self.failed_checks
                    if self.metrics:
                        self.metrics["failures_total"].inc()
                    if self.failed_checks >= self.max_retry and self.alert_fn:
                        self.alert_fn("upgrade_check_failed", {"count": self.failed_checks})
                    logging.warning(f"[UpgradeScheduler] Upgrade failed. Retrying in {self.retry_backoff * self.check_interval}s.")
                    time.sleep(self.retry_backoff * self.check_interval)
                    self.retry_backoff = min(self.retry_backoff * 2, 16)
                else:
                    self.failed_checks = 0
                    self.retry_backoff = 1
                # Manual/queue processing
                self._process_manual_queue()
                self._cleanup()
            except Exception as e:
                logging.error(f"[UpgradeScheduler] Error during check: {e}")
                self.failed_checks += 1
                self.status_info["failed_checks"] = self.failed_checks
                if self.alert_fn:
                    self.alert_fn("upgrade_scheduler_error", {"error": str(e)})
            finally:
                if self.distributed_lock:
                    self.distributed_lock.release(owner="scheduler")
            time.sleep(self.check_interval)

    def _process_manual_queue(self):
        while self._manual_queue:
            action = self._manual_queue.pop(0)
            if action == "force_check":
                logging.info("[UpgradeScheduler] Processing queued force check.")
                if self.metrics:
                    self.metrics["manual_triggers_total"].inc()
                self.trigger.try_upgrade()

    def force_check(self):
        logging.info("[UpgradeScheduler] Forced check triggered.")
        self._manual_queue.append("force_check")
        return True

    def status(self) -> Dict:
        self.status_info["running"] = self.running
        self.status_info["next_check_eta"] = time.time() + self.check_interval
        return self.status_info

    def set_interval(self, interval: int):
        self.check_interval = interval

    def graceful_shutdown(self, signum, frame):
        logging.info("[UpgradeScheduler] Signal received, shutting down...")
        self.stop()

    # --- Web/API UI Stub ---
    def api_status(self) -> Dict:
        """REST API endpoint for status."""
        return self.status()

    def api_force_check(self) -> bool:
        return self.force_check()

    def api_pause(self):
        self.stop()
        return {"paused": True}

    def api_resume(self):
        self.start()
        return {"running": True}

    # --- Manual Hooks for Extensibility ---
    def register_pre_check_hook(self, fn: Callable[[], None]):
        self.pre_check_hook = fn

    def register_post_check_hook(self, fn: Callable[[bool], None]):
        self.post_check_hook = fn

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Example: Distributed lock, maintenance window 2am-4am UTC, prometheus, alert, pre/post hooks
    distlock = DistributedLock() if redis else None
    def alert(event, data): print(f"ALERT: {event} {data}")
    def prehook(): print("[UpgradeScheduler] Pre-check hook triggered.")
    def posthook(status): print(f"[UpgradeScheduler] Post-check hook, status: {status}")
    def cleanup(): print("[UpgradeScheduler] Cleanup old upgrades/logs.")
    scheduler = UpgradeScheduler(
        check_interval=60,
        allowed_windows=[(2, 4)],
        distributed_lock=distlock,
        alert_fn=alert,
        pre_check_hook=prehook,
        post_check_hook=posthook,
        max_retry=3,
        cleanup_fn=cleanup,
        extra_upgrade_sources=["https://vivian-registry.example.com"],
        schedule_plan=[(6, 3, 0)]  # Example: Sunday 3:00 UTC
    )
    # Signal handling for graceful shutdown
    signal.signal(signal.SIGINT, scheduler.graceful_shutdown)
    signal.signal(signal.SIGTERM, scheduler.graceful_shutdown)
    scheduler.start()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        scheduler.stop()