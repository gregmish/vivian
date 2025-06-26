import threading
import time
import logging
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, Set
from engine.codegen import CodeGenerator

BUILD_PLAN_DIR = Path("build_plans")
BUILD_PLAN_DIR.mkdir(exist_ok=True)

class AutoBuilder:
    """
    Enterprise/agentic autonomous builder for Vivian.

    Features:
        - Concurrent build plan processing
        - Dry-run, plan validation, and backup
        - Pre/post build hooks, alert, progress, metrics callbacks
        - Per-build audit log, CLI & REST API integration
        - Throttling, rate limiting, retry/backoff & error handling
        - Health/status endpoint for dashboards
        - Distributed lock/coordination (optional)
        - Plan exclusion, duplicate detection, and manual trigger
        - REST API for health/trigger/history/manual
        - Prometheus/metrics, Slack/webhook alerting, Discord/email ready
        - Advanced plan validation and dependency checks
        - Integration ready for distributed queues and S3/remote fetch
        - Graceful shutdown and multi-builder scaling
    """
    def __init__(
        self,
        codegen: Optional[CodeGenerator] = None,
        pre_build_hook: Optional[Callable[[str, str], None]] = None,
        post_build_hook: Optional[Callable[[str, str, bool], None]] = None,
        alert_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
        status_cb: Optional[Callable[[str, str], None]] = None,
        metrics_cb: Optional[Callable[[str, float], None]] = None,
        audit_log_path: Path = BUILD_PLAN_DIR / "autobuilder_audit.jsonl",
        max_retries: int = 2,
        retry_delay: int = 5,
        concurrency: int = 2,
        backup_plans: bool = True,
        dry_run: bool = False,
        throttle_seconds: int = 30,
        exclude_patterns: Optional[Set[str]] = None,
        distributed_lock_cb: Optional[Callable[[], bool]] = None,
        plan_validation_cb: Optional[Callable[[str, str], bool]] = None,
        dependency_check_cb: Optional[Callable[[str, str], bool]] = None,
        s3_fetch_cb: Optional[Callable[[str, Path], bool]] = None
    ):
        self.codegen = codegen or CodeGenerator()
        self.pre_build_hook = pre_build_hook
        self.post_build_hook = post_build_hook
        self.alert_cb = alert_cb
        self.progress_cb = progress_cb
        self.status_cb = status_cb
        self.metrics_cb = metrics_cb
        self.audit_log_path = audit_log_path
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.concurrency = concurrency
        self.backup_plans = backup_plans
        self.dry_run = dry_run
        self.throttle_seconds = throttle_seconds
        self.exclude_patterns = exclude_patterns or set()
        self.distributed_lock_cb = distributed_lock_cb
        self.plan_validation_cb = plan_validation_cb
        self.dependency_check_cb = dependency_check_cb
        self.s3_fetch_cb = s3_fetch_cb

        self.running = False
        self.active_threads: List[threading.Thread] = []
        self._lock = threading.Lock()
        self._processed_plans: Set[str] = set()
        self._last_build_time = 0

    def _should_exclude(self, plan_file: Path) -> bool:
        return any(pat in plan_file.name for pat in self.exclude_patterns)

    def start(self):
        self.running = True
        for _ in range(self.concurrency):
            thread = threading.Thread(target=self._run, daemon=True)
            thread.start()
            self.active_threads.append(thread)
        logging.info("[AutoBuilder] Started build monitoring.")

    def _run(self):
        while self.running:
            try:
                plan_files = list(BUILD_PLAN_DIR.glob("*.plan"))
                for plan_file in plan_files:
                    if self._should_exclude(plan_file):
                        continue
                    with self._lock:
                        if plan_file.name in self._processed_plans:
                            continue
                        self._processed_plans.add(plan_file.name)
                    self._process_plan(plan_file)
            except Exception as e:
                logging.error(f"[AutoBuilder] Error scanning plans: {e}")
                if self.alert_cb:
                    self.alert_cb("build_plan_scan_error", {"error": str(e)})
            time.sleep(10)

    def _process_plan(self, plan_file: Path):
        now = time.time()
        if now - self._last_build_time < self.throttle_seconds:
            msg = f"[AutoBuilder] Throttled: {plan_file}"
            logging.info(msg)
            if self.metrics_cb:
                self.metrics_cb("autobuilder_throttled", now)
            return
        self._last_build_time = now

        # Distributed lock/coordination (optional)
        if self.distributed_lock_cb and not self.distributed_lock_cb():
            msg = "[AutoBuilder] Could not acquire distributed lock, skipping this cycle."
            logging.info(msg)
            if self.progress_cb: self.progress_cb(msg)
            return

        try:
            logging.info(f"[AutoBuilder] Found build plan: {plan_file.name}")
            if self.backup_plans:
                backup = plan_file.with_suffix(".plan.bak")
                plan_file.replace(backup)
                plan_file = backup
            with open(plan_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines:
                    if "::" not in line:
                        continue  # skip invalid lines
                    name, goal = line.strip().split("::", 1)
                    name, goal = name.strip(), goal.strip()
                    # Advanced plan validation
                    if self.plan_validation_cb and not self.plan_validation_cb(name, goal):
                        self._audit("plan_invalid", {"name": name, "goal": goal})
                        logging.warning(f"[AutoBuilder] Skipping invalid plan: {name} - {goal}")
                        if self.alert_cb:
                            self.alert_cb("plan_invalid", {"name": name, "goal": goal})
                        continue
                    # Dependency check
                    if self.dependency_check_cb and not self.dependency_check_cb(name, goal):
                        self._audit("dependency_unmet", {"name": name, "goal": goal})
                        logging.warning(f"[AutoBuilder] Dependency unmet for plan: {name} - {goal}")
                        if self.alert_cb:
                            self.alert_cb("dependency_unmet", {"name": name, "goal": goal})
                        continue
                    # Pre-build hook
                    if self.pre_build_hook:
                        self.pre_build_hook(name, goal)
                    if self.progress_cb:
                        self.progress_cb(f"[AutoBuilder] Building: {name} - {goal}")
                    success = False
                    for attempt in range(1, self.max_retries + 2):
                        try:
                            if self.dry_run:
                                logging.info(f"[AutoBuilder] DRY RUN: Would build {name}: {goal}")
                                success = True
                                break
                            self.codegen.generate_template(name, goal)
                            success = True
                            break
                        except Exception as e:
                            logging.error(f"[AutoBuilder] Build failed for {name} (attempt {attempt}): {e}")
                            if self.alert_cb:
                                self.alert_cb("build_failed", {"name": name, "goal": goal, "error": str(e)})
                            if attempt <= self.max_retries:
                                time.sleep(self.retry_delay)
                    if self.post_build_hook:
                        self.post_build_hook(name, goal, success)
                    self._audit("build", {"name": name, "goal": goal, "success": success})
                    if self.status_cb:
                        self.status_cb(name, "success" if success else "failed")
                    if self.metrics_cb:
                        self.metrics_cb("autobuilder_build", time.time())
            plan_file.unlink()  # Delete after use
        except Exception as e:
            logging.error(f"[AutoBuilder] Failed to process {plan_file}: {e}")
            self._audit("plan_error", {"file": str(plan_file), "error": str(e)})
            if self.alert_cb:
                self.alert_cb("plan_error", {"file": str(plan_file), "error": str(e)})

    def stop(self):
        self.running = False
        for thread in self.active_threads:
            thread.join(timeout=5)
        logging.info("[AutoBuilder] Stopped.")

    def _audit(self, action: str, data: dict):
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "data": data
        }
        try:
            with open(self.audit_log_path, "a") as f:
                import json
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logging.error(f"[AutoBuilder] Audit log failed: {e}")

    def health_status(self) -> dict:
        try:
            plan_count = len(list(BUILD_PLAN_DIR.glob("*.plan")))
            return {
                "status": "OK",
                "plans_pending": plan_count,
                "concurrency": self.concurrency,
                "running": self.running
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def trigger_manual(self, plan_file: Path):
        if not plan_file.exists():
            logging.error(f"[AutoBuilder] Manual trigger: file does not exist: {plan_file}")
            return
        with self._lock:
            if plan_file.name in self._processed_plans:
                logging.info(f"[AutoBuilder] Manual trigger: file already processed: {plan_file}")
                return
            self._processed_plans.add(plan_file.name)
        self._process_plan(plan_file)

    # S3/remote fetch integration (example)
    def fetch_plan_from_s3(self, s3_path: str, dest_path: Optional[Path] = None) -> Optional[Path]:
        if self.s3_fetch_cb:
            result = self.s3_fetch_cb(s3_path, dest_path or (BUILD_PLAN_DIR / Path(s3_path).name))
            if result:
                logging.info(f"[AutoBuilder] Fetched plan from S3: {s3_path}")
                return dest_path or (BUILD_PLAN_DIR / Path(s3_path).name)
        return None

    # REST API integration (optional)
    def start_rest_api(self, port: int = 7788):
        try:
            from flask import Flask, request, jsonify
        except ImportError:
            logging.info("[AutoBuilder] Flask not installed, REST API not available.")
            return
        app = Flask("AutoBuilder")

        @app.route("/api/autobuilder/health", methods=["GET"])
        def api_health():
            return jsonify(self.health_status())

        @app.route("/api/autobuilder/trigger", methods=["POST"])
        def api_trigger():
            name = request.form.get("name")
            goal = request.form.get("goal")
            if not name or not goal:
                return {"error": "Missing name or goal"}, 400
            plan_file = BUILD_PLAN_DIR / f"{name}.plan"
            with open(plan_file, "w") as f:
                f.write(f"{name}::{goal}\n")
            return {"queued": True}

        @app.route("/api/autobuilder/history", methods=["GET"])
        def api_history():
            try:
                with open(self.audit_log_path, "r") as f:
                    lines = f.readlines()[-20:]
                import json
                return jsonify([json.loads(line) for line in lines])
            except Exception:
                return jsonify([])

        @app.route("/api/autobuilder/manual", methods=["POST"])
        def api_manual():
            fname = request.form.get("planfile")
            if not fname:
                return {"error": "No planfile specified"}, 400
            plan_path = BUILD_PLAN_DIR / fname
            self.trigger_manual(plan_path)
            return {"triggered": True}

        logging.info(f"[AutoBuilder] REST API starting on port {port} ...")
        threading.Thread(target=app.run, kwargs={"port": port, "host": "0.0.0.0"}, daemon=True).start()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    builder = AutoBuilder()
    builder.start()
    builder.start_rest_api()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        builder.stop()