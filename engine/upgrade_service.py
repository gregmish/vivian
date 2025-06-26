import logging
import signal
import threading
import time
from typing import Optional, Callable, List, Dict, Tuple
from engine.upgrade_scheduler import UpgradeScheduler, DistributedLock
from engine.upgrade_trigger import UpgradeTrigger

try:
    import flask
    from flask import Flask, jsonify, request
except ImportError:
    flask = None

try:
    import prometheus_client
    from prometheus_client import make_wsgi_app
except ImportError:
    prometheus_client = None

try:
    import redis
except ImportError:
    redis = None

class UpgradeService:
    """
    Ultra-agentic, production-grade upgrade service for Vivian.
    Features: status/health, notification, RBAC, distributed lock, REST API, dashboard-ready, hooks, audit, graceful shutdown,
    multi-source, policy, windowing, self-healing, Prometheus metrics, and more.
    """
    def __init__(
        self,
        download_dir="downloads",
        check_interval=300,
        alert_fn: Optional[Callable[[str, dict], None]] = None,
        allowed_windows: Optional[List[Tuple[int, int]]] = None,
        distributed_lock: Optional[DistributedLock] = None,
        web_api: bool = True,
        cleanup_fn: Optional[Callable[[], None]] = None,
        approval_fn: Optional[Callable[[str], bool]] = None,
        rbac_fn: Optional[Callable[[str, str], bool]] = None,
        canary_nodes: Optional[List[str]] = None,
        marketplace_url: Optional[str] = None,
        extra_upgrade_sources: Optional[List[str]] = None,
        schedule_plan: Optional[List[Tuple[int, int, int]]] = None
    ):
        self.download_dir = download_dir
        self.check_interval = check_interval
        self.distributed_lock = distributed_lock
        self.alert_fn = alert_fn
        self.allowed_windows = allowed_windows
        self.cleanup_fn = cleanup_fn
        self.approval_fn = approval_fn
        self.rbac_fn = rbac_fn
        self.canary_nodes = canary_nodes
        self.marketplace_url = marketplace_url
        self.extra_upgrade_sources = extra_upgrade_sources or []
        self.schedule_plan = schedule_plan
        self.scheduler = UpgradeScheduler(
            check_interval=self.check_interval,
            download_dir=self.download_dir,
            alert_fn=self.alert_fn,
            allowed_windows=self.allowed_windows,
            distributed_lock=self.distributed_lock,
            approval_fn=self.approval_fn,
            rbac_fn=self.rbac_fn,
            canary_nodes=self.canary_nodes,
            marketplace_url=self.marketplace_url,
            cleanup_fn=self.cleanup_fn,
            extra_upgrade_sources=self.extra_upgrade_sources,
            schedule_plan=self.schedule_plan
        )
        self.trigger = UpgradeTrigger(
            base_dir=self.download_dir,
            approval_fn=self.approval_fn,
            rbac_fn=self.rbac_fn,
            canary_nodes=self.canary_nodes,
            marketplace_url=self.marketplace_url
        )
        self.status_info = {
            "active": False,
            "last_upgrade_time": None,
            "last_status": None,
            "pending_upgrades": [],
        }
        self._shutdown = threading.Event()
        self._web_api_enabled = web_api
        self._flask_app = Flask("VivianUpgradeService") if flask and self._web_api_enabled else None
        if self._flask_app:
            self._register_flask_routes()
            if prometheus_client:
                # Mount the Prometheus metrics endpoint
                from werkzeug.middleware.dispatcher import DispatcherMiddleware
                self._flask_app.wsgi_app = DispatcherMiddleware(
                    self._flask_app.wsgi_app,
                    {"/metrics": make_wsgi_app()}
                )
        self._web_thread = None

    def start(self):
        logging.info("[UpgradeService] Starting upgrade system...")
        self.status_info["active"] = True
        self.scheduler.start()
        self._setup_signal_handlers()
        if self._flask_app:
            self._web_thread = threading.Thread(target=self._flask_app.run, kwargs=dict(host="0.0.0.0", port=8000, use_reloader=False), daemon=True)
            self._web_thread.start()
            logging.info("[UpgradeService] REST API and dashboard available on port 8000.")

    def stop(self):
        logging.info("[UpgradeService] Stopping upgrade system...")
        self.status_info["active"] = False
        self.scheduler.stop()
        self._shutdown.set()
        # Flask will exit on main thread stop

    def force_check(self, user="system"):
        logging.info("[UpgradeService] Manually checking for upgrade...")
        if self.rbac_fn and not self.rbac_fn(user, "force_check"):
            logging.warning(f"[UpgradeService] User {user} is not authorized to force check.")
            return False
        self.scheduler.force_check()
        return True

    def get_status(self):
        st = self.scheduler.status()
        self.status_info.update({
            "last_upgrade_time": st.get("last_check"),
            "last_status": st.get("last_status"),
            "pending_upgrades": self._pending_upgrades(),
            "failed_checks": st.get("failed_checks"),
            "next_check_eta": st.get("next_check_in"),
        })
        return self.status_info

    def _pending_upgrades(self):
        # Example: scan for zip files in the download_dir not yet applied
        import os
        upgrades = []
        upgrades_dir = os.path.join(self.download_dir, "upgrades")
        auto_applied_dir = os.path.join(upgrades_dir, "auto_applied")
        if os.path.isdir(upgrades_dir):
            for fname in os.listdir(upgrades_dir):
                if fname.endswith(".zip") and (
                    not os.path.isdir(auto_applied_dir) or fname not in os.listdir(auto_applied_dir)
                ):
                    upgrades.append(fname)
        return upgrades

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._graceful_shutdown)
        signal.signal(signal.SIGTERM, self._graceful_shutdown)

    def _graceful_shutdown(self, signum, frame):
        logging.info("[UpgradeService] Signal received, shutting down gracefully.")
        self.stop()

    # --- REST API / Dashboard ---
    def _register_flask_routes(self):
        app = self._flask_app

        @app.route("/status", methods=["GET"])
        def status_():
            return jsonify(self.get_status())

        @app.route("/force_check", methods=["POST"])
        def force_check_():
            user = request.json.get("user", "system") if request.is_json else "system"
            ok = self.force_check(user=user)
            return jsonify({"ok": ok})

        @app.route("/start", methods=["POST"])
        def start_():
            self.start()
            return jsonify({"active": self.status_info["active"]})

        @app.route("/stop", methods=["POST"])
        def stop_():
            self.stop()
            return jsonify({"active": self.status_info["active"]})

        @app.route("/pending_upgrades", methods=["GET"])
        def pending_():
            return jsonify({"pending_upgrades": self._pending_upgrades()})

        # Example: Add a simple web dashboard page
        @app.route("/", methods=["GET"])
        def dashboard_():
            st = self.get_status()
            return f"""
            <html>
            <head><title>Vivian Upgrade Service Dashboard</title></head>
            <body>
                <h1>Vivian Upgrade Service Dashboard</h1>
                <pre>{st}</pre>
                <form action="/force_check" method="post"><button type="submit">Force Upgrade Check</button></form>
                <form action="/stop" method="post"><button type="submit">Stop Service</button></form>
            </body>
            </html>
            """

    # --- API/CLI/Web integration stubs ---
    def api_status(self):
        return self.get_status()

    def api_force_check(self, user="system"):
        return self.force_check(user=user)

    def api_start(self):
        self.start()
        return {"active": self.status_info["active"]}

    def api_stop(self):
        self.stop()
        return {"active": self.status_info["active"]}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    distlock = DistributedLock() if redis else None
    def alert(event, data): print(f"ALERT: {event} {data}")
    # Example: use all features (web API, distributed lock, allowed windows, marketplace, hooks)
    service = UpgradeService(
        check_interval=60,
        alert_fn=alert,
        distributed_lock=distlock,
        allowed_windows=[(2, 4)],
        web_api=True,
        extra_upgrade_sources=["https://vivian-registry.example.com"],
        schedule_plan=[(6, 3, 0)]  # Sunday 3:00 UTC
    )
    service.start()
    try:
        while not service._shutdown.is_set():
            time.sleep(10)
    except KeyboardInterrupt:
        service.stop()