import os
import importlib
import logging
import sys
import threading
import time
from typing import Optional, Callable, List, Dict
from datetime import datetime, timedelta
from engine.upgrade_installer import UpgradeInstaller

try:
    import redis  # For distributed locks
except ImportError:
    redis = None

class UpgradeTrigger:
    """
    Enterprise-grade, distributed, agentic upgrade trigger for Vivian.
    Features: auto-upgrade, hot module reload, callback, hooks, scheduling, observability, cluster-safety,
    dry-run, approval, health-check, canary/phased rollout, distributed lock, audit, alerts, RBAC, backup, preview/diff, marketplace, dependency graph, and more.
    """

    def __init__(
        self,
        base_dir: str = ".",
        on_upgrade_callback: Optional[Callable[[List[str]], None]] = None,
        reload_modules: Optional[List[str]] = None,
        health_check_fn: Optional[Callable[[], bool]] = None,
        upgrade_policy_fn: Optional[Callable[[str], bool]] = None,
        approval_fn: Optional[Callable[[str], bool]] = None,
        lock_file: str = "vivian_upgrade.lock",
        distributed_lock_url: Optional[str] = None,
        canary_nodes: Optional[List[str]] = None,
        notification_fn: Optional[Callable[[str, Dict], None]] = None,
        backup_fn: Optional[Callable[[], None]] = None,
        rollback_fn: Optional[Callable[[], None]] = None,
        user: str = "system",
        rbac_fn: Optional[Callable[[str, str], bool]] = None,
        schedule_time: Optional[datetime] = None,
        marketplace_url: Optional[str] = None,
        dependency_graph_fn: Optional[Callable[[str], bool]] = None
    ):
        self.installer = UpgradeInstaller(base_dir=base_dir, verbose=True)
        self.callback = on_upgrade_callback
        self.reload_modules = reload_modules or []
        self.health_check_fn = health_check_fn
        self.policy_fn = upgrade_policy_fn
        self.approval_fn = approval_fn
        self.lock_file = os.path.join(base_dir, lock_file)
        self.lock = threading.Lock()
        self.redis_client = redis.Redis.from_url(distributed_lock_url) if distributed_lock_url and redis else None
        self.canary_nodes = canary_nodes or []
        self.notification_fn = notification_fn
        self.backup_fn = backup_fn
        self.rollback_fn = rollback_fn
        self.rbac_fn = rbac_fn
        self.user = user
        self.schedule_time = schedule_time
        self.marketplace_url = marketplace_url
        self.dependency_graph_fn = dependency_graph_fn
        # Pass policy, approval, health, notification to installer if present
        if self.policy_fn:
            self.installer.set_policy_fn(self.policy_fn)
        if self.approval_fn:
            self.installer.set_approval_callback(self.approval_fn)
        if self.health_check_fn:
            self.installer.set_health_check(self.health_check_fn)
        if self.notification_fn:
            self.installer.set_notification_fn(self.notification_fn)

    # ----------------- Distributed/Cluster Lock -----------------
    def _acquire_lock(self, timeout=60) -> bool:
        if self.redis_client:
            lock_key = f"vivian:upgrade:lock"
            end = time.time() + timeout
            while time.time() < end:
                if self.redis_client.setnx(lock_key, self.user):
                    self.redis_client.expire(lock_key, timeout)
                    logging.info("[UpgradeTrigger] Acquired distributed lock.")
                    return True
                time.sleep(1)
            return False
        else:
            # Local lock file fallback
            try:
                if os.path.exists(self.lock_file):
                    return False
                with open(self.lock_file, "w") as f:
                    f.write(str(os.getpid()))
                return True
            except Exception as e:
                logging.error(f"[UpgradeTrigger] Lock error: {e}")
                return False

    def _release_lock(self):
        if self.redis_client:
            try:
                self.redis_client.delete(f"vivian:upgrade:lock")
                logging.info("[UpgradeTrigger] Released distributed lock.")
            except Exception:
                pass
        else:
            try:
                if os.path.exists(self.lock_file):
                    os.remove(self.lock_file)
            except Exception:
                pass

    # ----------------- Scheduling and Queueing -----------------
    def schedule_upgrade(self, when: Optional[datetime] = None):
        if not when:
            logging.warning("[UpgradeTrigger] No schedule time provided.")
            return
        delta = (when - datetime.utcnow()).total_seconds()
        if delta > 0:
            logging.info(f"[UpgradeTrigger] Upgrade scheduled in {delta} seconds.")
            threading.Timer(delta, self.try_upgrade).start()
        else:
            logging.info("[UpgradeTrigger] Scheduled time has passed, running now.")
            self.try_upgrade()

    # ----------------- Canary/Phased Rollout -----------------
    def canary_upgrade(self, node_list: List[str], dry_run: bool = False) -> bool:
        logging.info(f"[UpgradeTrigger] Starting canary upgrade for nodes: {node_list}")
        # Placeholder: In real distributed settings, trigger upgrades on nodes via RPC/SSH/agent.
        # Here, just simulate for local node.
        for node in node_list:
            # Real system: Send upgrade command to node
            logging.info(f"[UpgradeTrigger] (Simulated) Upgrading canary node: {node}")
        # After canary, check health
        if self.health_check_fn and not self.health_check_fn():
            logging.error("[UpgradeTrigger] Canary health check failed! Stopping rollout.")
            if self.rollback_fn:
                self.rollback_fn()
            return False
        logging.info("[UpgradeTrigger] Canary phase passed, proceeding to full rollout.")
        return True

    # ----------------- Main Upgrade Logic -----------------
    def try_upgrade(self, dry_run: bool = False, user: Optional[str] = None) -> bool:
        if user:
            self.user = user
        # RBAC
        if self.rbac_fn and not self.rbac_fn(self.user, "upgrade"):
            logging.warning(f"[UpgradeTrigger] User {self.user} is not authorized for upgrades.")
            return False
        # Dependency checks
        if self.dependency_graph_fn and not self.dependency_graph_fn(self.user):
            logging.warning(f"[UpgradeTrigger] Dependency checks failed for user {self.user}.")
            return False
        if not self._acquire_lock():
            logging.warning("[UpgradeTrigger] Another upgrade is in progress or lock file present.")
            return False
        try:
            # Backup before upgrade
            if self.backup_fn:
                logging.info("[UpgradeTrigger] Running backup before upgrade...")
                self.backup_fn()
            # Canary rollout if specified
            if self.canary_nodes:
                if not self.canary_upgrade(self.canary_nodes, dry_run=dry_run):
                    self._release_lock()
                    return False
            # Marketplace fetch if specified
            if self.marketplace_url:
                self.fetch_marketplace_upgrades()
            logging.info("[UpgradeTrigger] Scanning for upgrades...")
            applied = self.installer.auto_scan_and_apply(dry_run=dry_run, user=self.user)
            if applied:
                logging.info(f"[UpgradeTrigger] Applied upgrades: {applied}")
                # Hot reload modules if specified
                for mod in self.reload_modules:
                    self.reload_module(mod)
                # Optionally, run post-upgrade health check
                if self.health_check_fn and not self.health_check_fn():
                    logging.error("[UpgradeTrigger] Health check failed post-upgrade! Rolling back.")
                    if self.rollback_fn:
                        self.rollback_fn()
                # Run callback
                if self.callback:
                    try:
                        self.callback(applied)
                    except Exception as e:
                        logging.error(f"[UpgradeTrigger] Callback error: {e}")
                # Notify
                if self.notification_fn:
                    self.notification_fn("upgrade_applied", {"applied": applied, "user": self.user})
                return True
            logging.info("[UpgradeTrigger] No upgrades found.")
            return False
        finally:
            self._release_lock()

    # ----------------- Marketplace Integration -----------------
    def fetch_marketplace_upgrades(self):
        logging.info(f"[UpgradeTrigger] Fetching upgrades from marketplace: {self.marketplace_url}")
        # Placeholder: Download and stage new upgrades from remote registry.
        # Integration example: download to UPGRADE_DIR, verify signature/provenance.

    # ----------------- Module Reload, Observability, Audit -----------------
    def reload_module(self, module_name: str):
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
                logging.info(f"[UpgradeTrigger] Reloaded module: {module_name}")
            else:
                imported = importlib.import_module(module_name)
                sys.modules[module_name] = imported
                logging.info(f"[UpgradeTrigger] Imported module: {module_name}")
        except Exception as e:
            logging.error(f"[UpgradeTrigger] Failed to reload module {module_name}: {e}")

    def get_audit_log(self) -> List[Dict]:
        return self.installer.get_event_log()

    def get_upgrade_preview(self) -> Dict[str, Dict]:
        """
        Returns a preview (diff, undo preview, dependency info) for all pending upgrades.
        """
        preview = {}
        for fname in os.listdir(self.installer.UPGRADE_DIR):
            if fname.endswith(".zip") and fname not in os.listdir(self.installer.AUTO_APPLY_DIR):
                path = os.path.join(self.installer.UPGRADE_DIR, fname)
                preview[fname] = {
                    "diff": self.installer.show_diff(path),
                    "undo_preview": self.installer.undo_preview(fname)
                }
        return preview

    # ----------------- API/CLI/Web UI Stubs -----------------
    def api_trigger_upgrade(self, **kwargs) -> bool:
        """
        API endpoint to trigger upgrade.
        """
        return self.try_upgrade(**kwargs)

    # ----------------- Notification Example (Slack, Email, etc.) -----------------
    def notify(self, event: str, data: Dict):
        if self.notification_fn:
            self.notification_fn(event, data)
        logging.info(f"[UpgradeTrigger][Notify] {event}: {data}")

    # ----------------- Multi-step Approval (stub) -----------------
    def multi_step_approval(self, upgrade_path: str, approvers: List[str]) -> bool:
        logging.info(f"[UpgradeTrigger] Multi-step approval for {upgrade_path} by {approvers}")
        # Placeholder: Implement real multi-user approval chain
        return all(self.approval_fn and self.approval_fn(upgrade_path) for _ in approvers)

    # ----------------- Disaster Recovery -----------------
    def disaster_recovery(self):
        # Placeholder for disaster recovery logic
        logging.error("[UpgradeTrigger] Disaster recovery triggered. Rolling back and restoring last backup.")
        if self.rollback_fn:
            self.rollback_fn()

    # ----------------- Metrics/Observability Example (Prometheus) -----------------
    def export_metrics(self):
        # Placeholder: Integrate with prometheus_client, e.g.
        # from prometheus_client import Counter
        # upgrade_counter.inc()
        pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Example instantiation for demo/testing
    def health_check(): return True
    def approve(zip_path): return True
    def notify(event, data): print(f"NOTIFY: {event} {data}")
    uptrigger = UpgradeTrigger(
        health_check_fn=health_check,
        approval_fn=approve,
        notification_fn=notify,
        canary_nodes=["node1", "node2"]
    )
    # Example schedule (upgrade in 5 seconds)
    uptrigger.schedule_upgrade(datetime.utcnow() + timedelta(seconds=5))
    # Direct trigger
    uptrigger.try_upgrade()
    print("Audit log:", uptrigger.get_audit_log()[-3:])
    print("Upgrade preview:", uptrigger.get_upgrade_preview())