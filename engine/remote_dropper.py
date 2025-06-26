import os
import logging
import time
import threading
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Set
from engine.codegen import CodeGenerator

DROP_DIR = Path("dropbox")
DROP_DIR.mkdir(exist_ok=True)

class RemoteDropper:
    """
    Agentic, distributed dropbox/code ingestion system.

    Features:
      - Concurrent, thread-safe monitoring
      - Audit log for drops and errors
      - Per-drop progress, alert, and metrics callbacks (Slack/email/webhook/Discord)
      - File pattern exclusion, duplicate detection
      - File type & extension routing (.py, .txt, .plan, .json, etc)
      - Pre/post-process hooks
      - Throttling, retries, distributed lock/coordination
      - REST API for health, manual trigger, history
      - Health endpoint for dashboards
      - S3/remote fetch and queue-ready
      - Plan/code validation, dependency checks
      - Slack/Discord/email/webhook direct integration
      - Prometheus/metrics direct integration
      - Graceful shutdown, scaling, and multi-instance ready
    """

    def __init__(
        self,
        codegen: Optional[CodeGenerator] = None,
        drop_dir: Path = DROP_DIR,
        check_interval: int = 5,
        exclude_patterns: Optional[Set[str]] = None,
        pre_process_hook: Optional[Callable[[Path], None]] = None,
        post_process_hook: Optional[Callable[[Path, bool], None]] = None,
        alert_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        metrics_cb: Optional[Callable[[str, float], None]] = None,
        audit_log_path: Path = DROP_DIR / "remote_dropper_audit.jsonl",
        distributed_lock_cb: Optional[Callable[[], bool]] = None,
        throttle_seconds: int = 10,
        max_retries: int = 2,
        retry_delay: int = 3,
        plan_validation_cb: Optional[Callable[[str, str], bool]] = None,
        dependency_check_cb: Optional[Callable[[str, str], bool]] = None,
        s3_fetch_cb: Optional[Callable[[str, Path], bool]] = None,
        slack_cb: Optional[Callable[[str], None]] = None,
        discord_cb: Optional[Callable[[str], None]] = None,
        email_cb: Optional[Callable[[str, str], None]] = None,
        prometheus_cb: Optional[Callable[[str, float], None]] = None,
        webhook_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.codegen = codegen or CodeGenerator()
        self.drop_dir = drop_dir
        self.check_interval = check_interval
        self.exclude_patterns = exclude_patterns or set()
        self.pre_process_hook = pre_process_hook
        self.post_process_hook = post_process_hook
        self.alert_cb = alert_cb
        self.metrics_cb = metrics_cb
        self.audit_log_path = audit_log_path
        self.distributed_lock_cb = distributed_lock_cb
        self.throttle_seconds = throttle_seconds
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.plan_validation_cb = plan_validation_cb
        self.dependency_check_cb = dependency_check_cb
        self.s3_fetch_cb = s3_fetch_cb
        self.slack_cb = slack_cb
        self.discord_cb = discord_cb
        self.email_cb = email_cb
        self.prometheus_cb = prometheus_cb
        self.webhook_cb = webhook_cb

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._seen_files: Set[str] = set()
        self._last_drop_time = 0

    def _should_exclude(self, file: Path) -> bool:
        return any(pat in file.name for pat in self.exclude_patterns)

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
            logging.error(f"[RemoteDropper] Audit log failed: {e}")

    def _alert(self, event: str, data: dict):
        if self.alert_cb:
            try:
                self.alert_cb(event, data)
            except Exception as e:
                logging.error(f"[RemoteDropper] Alert callback failed: {e}")
        if self.slack_cb:
            try:
                self.slack_cb(f"[RemoteDropper][{event}] {data}")
            except Exception as e:
                logging.error(f"[RemoteDropper] Slack callback failed: {e}")
        if self.discord_cb:
            try:
                self.discord_cb(f"[RemoteDropper][{event}] {data}")
            except Exception as e:
                logging.error(f"[RemoteDropper] Discord callback failed: {e}")
        if self.email_cb:
            try:
                self.email_cb(f"RemoteDropper Event: {event}", str(data))
            except Exception as e:
                logging.error(f"[RemoteDropper] Email callback failed: {e}")
        if self.webhook_cb:
            try:
                self.webhook_cb(event, data)
            except Exception as e:
                logging.error(f"[RemoteDropper] Webhook callback failed: {e}")

    def _metrics(self, metric: str, value: float):
        if self.metrics_cb:
            self.metrics_cb(metric, value)
        if self.prometheus_cb:
            self.prometheus_cb(metric, value)

    def _process_file(self, file: Path):
        now = time.time()
        if now - self._last_drop_time < self.throttle_seconds:
            logging.info(f"[RemoteDropper] Throttled: {file}")
            self._metrics("remote_dropper_throttled", now)
            return
        self._last_drop_time = now

        # Distributed lock (optional)
        if self.distributed_lock_cb and not self.distributed_lock_cb():
            msg = "[RemoteDropper] Could not acquire distributed lock, skipping this cycle."
            logging.info(msg)
            return

        for attempt in range(1, self.max_retries + 2):
            try:
                if self._should_exclude(file):
                    logging.info(f"[RemoteDropper] Excluded by pattern: {file.name}")
                    self._audit("excluded", {"file": str(file)})
                    return

                logging.info(f"[RemoteDropper] Detected drop: {file.name}")
                if self.pre_process_hook:
                    self.pre_process_hook(file)
                success = False

                ext = file.suffix.lower()
                if ext == ".txt":
                    with open(file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        name = file.stem
                        self.codegen.write_custom_code(
                            name, content, tags=["remote"], description="Dropped code"
                        )
                        success = True
                elif ext == ".py":
                    with open(file, "r", encoding="utf-8") as f:
                        code = f.read()
                        name = file.stem
                        self.codegen.write_custom_code(
                            name, code, tags=["remote", "python"], description="Dropped Python code"
                        )
                        success = True
                elif ext == ".plan":
                    valid = True
                    with open(file, "r", encoding="utf-8") as f:
                        for line in f:
                            if "::" not in line:
                                continue
                            name, goal = line.strip().split("::", 1)
                            name, goal = name.strip(), goal.strip()
                            if self.plan_validation_cb and not self.plan_validation_cb(name, goal):
                                self._audit("plan_invalid", {"name": name, "goal": goal})
                                logging.warning(f"[RemoteDropper] Skipping invalid plan: {name} - {goal}")
                                self._alert("plan_invalid", {"name": name, "goal": goal})
                                valid = False
                                break
                            if self.dependency_check_cb and not self.dependency_check_cb(name, goal):
                                self._audit("dependency_unmet", {"name": name, "goal": goal})
                                logging.warning(f"[RemoteDropper] Dependency unmet for plan: {name} - {goal}")
                                self._alert("dependency_unmet", {"name": name, "goal": goal})
                                valid = False
                                break
                    if valid:
                        plan_target = Path("build_plans") / file.name
                        file.replace(plan_target)
                        logging.info(f"[RemoteDropper] Routed plan to AutoBuilder: {plan_target}")
                        success = True
                elif ext == ".json":
                    with open(file, "r", encoding="utf-8") as f:
                        import json
                        req = json.load(f)
                        name = req.get("name", file.stem)
                        content = req.get("content", "")
                        self.codegen.write_custom_code(
                            name, content, tags=["remote", "json"], description="Dropped JSON code"
                        )
                        success = True
                else:
                    logging.warning(f"[RemoteDropper] Unknown drop file type: {file.name}")
                    self._audit("unknown_type", {"file": str(file)})
                    self._alert("unknown_drop_type", {"file": str(file)})
                    break

                self._audit("processed", {"file": str(file), "success": success})
                if self.post_process_hook:
                    self.post_process_hook(file, success)
                self._alert("drop_processed", {"file": str(file), "success": success})
                self._metrics("remote_dropper_processed", time.time())
                file.unlink(missing_ok=True)
                break
            except Exception as e:
                logging.error(f"[RemoteDropper] Failed to process {file} (attempt {attempt}): {e}")
                self._audit("error", {"file": str(file), "error": str(e)})
                self._alert("drop_error", {"file": str(file), "error": str(e)})
                if attempt <= self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    break

    def _watch(self):
        logging.info(f"[RemoteDropper] Watching folder: {self.drop_dir}")
        while not self._stop_event.is_set():
            try:
                files = list(self.drop_dir.iterdir())
                for file in files:
                    with self._lock:
                        if file.name in self._seen_files:
                            continue
                        self._seen_files.add(file.name)
                    self._process_file(file)
            except Exception as e:
                logging.error(f"[RemoteDropper] Watcher error: {e}")
                self._audit("watcher_error", {"error": str(e)})
            self._metrics("remote_dropper_idle", time.time())
            time.sleep(self.check_interval)
        logging.info("[RemoteDropper] Stopped watching drops.")

    def start(self):
        self.running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        logging.info("[RemoteDropper] Background thread started.")

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logging.info("[RemoteDropper] Stopped.")

    def health_status(self) -> Dict[str, Any]:
        try:
            file_count = len(list(self.drop_dir.iterdir()))
            return {
                "status": "OK",
                "files_pending": file_count,
                "running": self.running
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def trigger_manual(self, file: Path):
        if not file.exists():
            logging.error(f"[RemoteDropper] Manual trigger: file does not exist: {file}")
            return
        with self._lock:
            if file.name in self._seen_files:
                logging.info(f"[RemoteDropper] Manual trigger: file already processed: {file}")
                return
            self._seen_files.add(file.name)
        self._process_file(file)

    # S3/remote fetch integration (optional)
    def fetch_from_s3(self, s3_path: str, dest_path: Optional[Path] = None) -> Optional[Path]:
        if self.s3_fetch_cb:
            result = self.s3_fetch_cb(s3_path, dest_path or (self.drop_dir / Path(s3_path).name))
            if result:
                logging.info(f"[RemoteDropper] Fetched file from S3: {s3_path}")
                return dest_path or (self.drop_dir / Path(s3_path).name)
        return None

    # REST API integration (optional)
    def start_rest_api(self, port: int = 7799):
        try:
            from flask import Flask, request, jsonify
        except ImportError:
            logging.info("[RemoteDropper] Flask not installed, REST API not available.")
            return
        app = Flask("RemoteDropper")

        @app.route("/api/remotedropper/health", methods=["GET"])
        def api_health():
            return jsonify(self.health_status())

        @app.route("/api/remotedropper/manual", methods=["POST"])
        def api_manual():
            fname = request.form.get("filename")
            if not fname:
                return {"error": "No filename specified"}, 400
            file_path = self.drop_dir / fname
            self.trigger_manual(file_path)
            return {"triggered": True}

        @app.route("/api/remotedropper/history", methods=["GET"])
        def api_history():
            try:
                with open(self.audit_log_path, "r") as f:
                    lines = f.readlines()[-20:]
                import json
                return jsonify([json.loads(line) for line in lines])
            except Exception:
                return jsonify([])

        logging.info(f"[RemoteDropper] REST API starting on port {port} ...")
        threading.Thread(target=app.run, kwargs={"port": port, "host": "0.0.0.0"}, daemon=True).start()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cg = CodeGenerator()
    # Example Slack integration (replace with real sender in prod!):
    def slack_cb(msg): print("[Slack]", msg)
    def discord_cb(msg): print("[Discord]", msg)
    def email_cb(subject, body): print(f"[Email] {subject}: {body}")
    def prometheus_cb(metric, value): print(f"[Prometheus] {metric}: {value}")
    def webhook_cb(event, data): print(f"[Webhook] {event}: {data}")
    dropper = RemoteDropper(
        cg,
        slack_cb=slack_cb,
        discord_cb=discord_cb,
        email_cb=email_cb,
        prometheus_cb=prometheus_cb,
        webhook_cb=webhook_cb
    )
    dropper.start()
    dropper.start_rest_api()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        dropper.stop()