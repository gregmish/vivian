import time
import logging
import threading
import traceback
from typing import Dict, Any, Optional, Callable, List

class HealthMonitor:
    """
    Vivian's ultimate health checker and watchdog.
    - Tracks uptime, error counts, subsystem/component status
    - Publishes health events to EventBus
    - Auto-restart/recovery hooks, notification hooks (email/webhook/log)
    - API/GUI/Prometheus metrics integration
    - Watchdog timer for freeze/crash detection
    - Severity levels, escalation, and alert rate-limiting
    - Manual/forced checks, rolling logs, detailed subsystem history
    - Supports external monitoring, admin commands, and diagnostics dumps
    """

    def __init__(
        self,
        config: Dict[str, Any],
        event_bus=None,
        notification_hook: Optional[Callable[[str, str], None]] = None,
        diagnostics_hook: Optional[Callable[[], Dict[str, Any]]] = None
    ):
        self.config = config
        self.event_bus = event_bus
        self.notification_hook = notification_hook  # function(msg, severity)
        self.diagnostics_hook = diagnostics_hook
        self.running = False
        self.status = {
            "started_at": time.time(),
            "uptime": 0,
            "errors": 0,
            "last_error": None,
            "last_check": 0,
            "ok": True,
            "checks": 0,
            "last_success": None,
            "subsystems": {},
            "subsystem_history": {},
            "error_log": [],
            "alert_log": [],
            "watchdog_last_tick": time.time(),
            "watchdog_triggered": False,
            "diagnostics": {},
        }
        self.check_callbacks = {}  # name -> function returning dict with at least an "ok" bool
        self.recovery_callback = None
        self.watchdog_callback = None
        self.failed_checks = 0
        self.max_failed_checks = config.get("health_max_failed", 3)
        self.error_log_limit = config.get("health_error_log_limit", 50)
        self.alert_log_limit = config.get("health_alert_log_limit", 50)
        self.subsystem_history_limit = config.get("health_subsystem_history_limit", 20)
        self.alert_cooldown = config.get("health_alert_cooldown", 300)
        self.last_alert_times = {}
        self._lock = threading.Lock()
        self.watchdog_interval = config.get("health_watchdog_interval", 180)
        self.watchdog_enabled = config.get("health_watchdog_enabled", True)
        self.prometheus_labels = config.get("health_prometheus_labels", {})
        self.admin_commands = {}

    # --- Registration ---

    def register_check(self, name: str, func: Callable[[], Dict[str, Any]]):
        """Register a subsystem/component health check callback."""
        self.check_callbacks[name] = func

    def set_recovery(self, func: Callable[[], None]):
        """Set a callback for auto-restart/recovery."""
        self.recovery_callback = func

    def set_watchdog(self, func: Callable[[], None]):
        """Set a callback for watchdog crash/freeze recovery."""
        self.watchdog_callback = func

    def register_admin_command(self, cmd: str, func: Callable[[Dict[str, Any]], Any]):
        """Register an admin command callable (API/GUI)."""
        self.admin_commands[cmd] = func

    # --- Main Health Loop ---

    def tick(self):
        """Update the watchdog timer (the main loop should call this regularly)."""
        with self._lock:
            self.status["watchdog_last_tick"] = time.time()
            if self.status.get("watchdog_triggered"):
                self.status["watchdog_triggered"] = False

    def run(self):
        """Start the health monitor and watchdog in threads."""
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
        if self.watchdog_enabled:
            threading.Thread(target=self._watchdog_loop, daemon=True).start()

    def _loop(self):
        interval = self.config.get("health_check_interval", 60)
        while self.running:
            self.check_now()
            time.sleep(interval)

    def _watchdog_loop(self):
        while self.running and self.watchdog_enabled:
            time.sleep(self.watchdog_interval)
            with self._lock:
                since_tick = time.time() - self.status.get("watchdog_last_tick", 0)
                if since_tick > self.watchdog_interval:
                    self.status["watchdog_triggered"] = True
                    msg = f"Watchdog timer expired! No tick for {since_tick:.1f}s"
                    self._alert(msg, severity="critical")
                    if self.watchdog_callback:
                        self.watchdog_callback()
                    if self.event_bus:
                        self.event_bus.publish(
                            "health_watchdog_expired",
                            data={"message": msg, "since_tick": since_tick},
                            context={"source": "health_monitor"}
                        )
                    if self.notification_hook:
                        self.notification_hook(msg, "critical")

    def check_now(self):
        with self._lock:
            self.status["last_check"] = time.time()
            self.status["checks"] += 1
            all_ok = True
            subsystems = {}
            for name, func in self.check_callbacks.items():
                try:
                    result = func()
                    subsystems[name] = result
                    self._save_subsystem_history(name, result)
                    if not result.get("ok", True):
                        all_ok = False
                        self._alert(
                            f"Subsystem '{name}' health check failed: {result}",
                            severity=result.get("severity", "warning")
                        )
                except Exception as e:
                    tb = traceback.format_exc()
                    subsystems[name] = {"ok": False, "error": str(e), "traceback": tb, "severity": "critical"}
                    self._save_subsystem_history(name, subsystems[name])
                    all_ok = False
                    self._alert(f"Exception in '{name}' health check: {e}", severity="critical")
            self.status["subsystems"] = subsystems
            self.status["uptime"] = int(time.time() - self.status["started_at"])
            self.status["ok"] = all_ok

            if all_ok:
                self.status["last_success"] = self.status["last_check"]
                self.failed_checks = 0
            else:
                self.failed_checks += 1
                msg = f"Health check failed: {subsystems}"
                self.status["errors"] += 1
                self.status["last_error"] = msg
                self.status["error_log"].append({"time": time.time(), "msg": msg})
                if len(self.status["error_log"]) > self.error_log_limit:
                    self.status["error_log"] = self.status["error_log"][-self.error_log_limit:]
                if self.failed_checks >= self.max_failed_checks and self.recovery_callback:
                    logging.critical("[Health] Auto-recovery triggered.")
                    self.recovery_callback()
                    self.failed_checks = 0
                    if self.notification_hook:
                        self.notification_hook("Auto-recovery triggered after repeated health check failures.", "critical")

            # Collect diagnostics if available
            if self.diagnostics_hook:
                try:
                    self.status["diagnostics"] = self.diagnostics_hook()
                except Exception as e:
                    self.status["diagnostics"] = {"error": str(e)}

            if self.event_bus:
                self.event_bus.publish("health_check", data=self.status.copy(), context={"source": "health_monitor"})

    def stop(self):
        self.running = False

    # --- Status, Logs, Metrics, Admin ---

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return self.status.copy()

    def get_error_log(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return self.status["error_log"][-limit:]

    def get_alert_log(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return self.status["alert_log"][-limit:]

    def get_subsystem_history(self, name: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return self.status["subsystem_history"].get(name, [])[-limit:]

    def force_check(self):
        """Force a health check immediately (for admin/API/GUI use)."""
        self.check_now()

    def as_check(self) -> Callable[[], Dict[str, Any]]:
        """Return a health check function for Vivian core itself."""
        def check():
            return {"ok": self.status.get("ok", False), "errors": self.status.get("errors", 0)}
        return check

    def run_admin_command(self, cmd: str, args: Dict[str, Any]) -> Any:
        """Run a registered admin command."""
        if cmd in self.admin_commands:
            try:
                return self.admin_commands[cmd](args)
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Unknown command"}

    # --- Alerting, Notification, Rate-limiting ---

    def _alert(self, msg: str, severity: str = "warning"):
        now = time.time()
        last_time = self.last_alert_times.get(msg)
        if last_time and now - last_time < self.alert_cooldown:
            # Rate-limit repeated alerts for the same message
            return
        self.last_alert_times[msg] = now
        entry = {"time": now, "message": msg, "severity": severity}
        self.status["alert_log"].append(entry)
        if len(self.status["alert_log"]) > self.alert_log_limit:
            self.status["alert_log"] = self.status["alert_log"][-self.alert_log_limit:]
        if severity == "critical":
            logging.critical(f"[Health] {msg}")
        else:
            logging.warning(f"[Health] {msg}")
        if self.event_bus:
            event_type = "health_critical" if severity == "critical" else "health_warning"
            self.event_bus.publish(event_type, data={"message": msg, "severity": severity}, context={"source": "health_monitor"})
        if self.notification_hook:
            try:
                self.notification_hook(msg, severity)
            except Exception as notify_error:
                logging.error(f"[Health] Notification hook error: {notify_error}")

    # --- Prometheus/metrics integration (optional) ---
    def get_metrics(self) -> str:
        with self._lock:
            label_str = ",".join([f'{k}="{v}"' for k, v in self.prometheus_labels.items()])
            if label_str:
                label_str = "{" + label_str + "}"
            lines = [
                f'vivian_health_ok{label_str} {1 if self.status["ok"] else 0}',
                f'vivian_health_failed_checks{label_str} {self.failed_checks}',
                f'vivian_health_total_checks{label_str} {self.status["checks"]}',
                f'vivian_health_uptime_seconds{label_str} {self.status["uptime"]}',
                f'vivian_health_errors{label_str} {self.status["errors"]}',
            ]
            for name, data in self.status.get("subsystems", {}).items():
                ok = 1 if data.get("ok", False) else 0
                lines.append(f'vivian_subsystem_ok{{name="{name}"{"," if label_str else ""}{label_str.strip("{}")}}} {ok}')
            return "\n".join(lines)

    # --- Diagnostics Dump ---
    def get_diagnostics(self) -> Dict[str, Any]:
        """Return the latest diagnostics dump (if available)."""
        with self._lock:
            return self.status.get("diagnostics", {})

    # --- Internal: Subsystem History ---
    def _save_subsystem_history(self, name: str, result: Dict[str, Any]):
        history = self.status["subsystem_history"].setdefault(name, [])
        entry = {"time": time.time(), "result": result}
        history.append(entry)
        if len(history) > self.subsystem_history_limit:
            history[:] = history[-self.subsystem_history_limit:]
