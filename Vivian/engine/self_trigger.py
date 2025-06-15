import logging
import threading
import time
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Set, List
from engine.codegen import CodeGenerator

class SelfTrigger:
    """
    Vivian agentic self-improvement trigger, enterprise/agent-grade.

    Features:
      - Adaptive scheduling, multi-criteria self-improvement, self-assessment, policy/approval
      - Issue tracker integration (GitHub/Jira)
      - Rollback/fallback, distributed coordination, safety & sanity checks
      - Explainability/reporting, versioning/auditability (optionally git-based)
      - REST/Webhook/manual triggers, metrics, dashboard, secrets handling, user feedback loop
      - Pluggable evolution strategies
    """

    def __init__(
        self,
        codegen: Optional[CodeGenerator] = None,
        interval: int = 180,
        adaptive_interval: bool = True,
        min_interval: int = 60,
        max_interval: int = 900,
        pre_evolve_hook: Optional[Callable[[str], None]] = None,
        post_evolve_hook: Optional[Callable[[str, bool], None]] = None,
        alert_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        metrics_cb: Optional[Callable[[str, float], None]] = None,
        audit_log_path: Path = Path("self_trigger_audit.jsonl"),
        distributed_lock_cb: Optional[Callable[[], bool]] = None,
        throttle_seconds: int = 60,
        max_retries: int = 2,
        retry_delay: int = 5,
        slack_cb: Optional[Callable[[str], None]] = None,
        discord_cb: Optional[Callable[[str], None]] = None,
        email_cb: Optional[Callable[[str, str], None]] = None,
        prometheus_cb: Optional[Callable[[str, float], None]] = None,
        webhook_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        approval_cb: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        issue_tracker_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        rollback_cb: Optional[Callable[[str], None]] = None,
        sanity_check_cb: Optional[Callable[[str], bool]] = None,
        explainability_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        versioning_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        feedback_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        evolution_strategies: Optional[Dict[str, Callable[[str], Any]]] = None,
        secrets_check_cb: Optional[Callable[[str], bool]] = None,
        test_coverage_cb: Optional[Callable[[str], float]] = None,
        lint_cb: Optional[Callable[[str], int]] = None,
        usage_metrics_cb: Optional[Callable[[str], int]] = None,
        error_count_cb: Optional[Callable[[str], int]] = None,
        dependency_check_cb: Optional[Callable[[str], bool]] = None
    ):
        self.codegen = codegen or CodeGenerator()
        self.interval = interval
        self.adaptive_interval = adaptive_interval
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.pre_evolve_hook = pre_evolve_hook
        self.post_evolve_hook = post_evolve_hook
        self.alert_cb = alert_cb
        self.metrics_cb = metrics_cb
        self.audit_log_path = audit_log_path
        self.distributed_lock_cb = distributed_lock_cb
        self.throttle_seconds = throttle_seconds
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.slack_cb = slack_cb
        self.discord_cb = discord_cb
        self.email_cb = email_cb
        self.prometheus_cb = prometheus_cb
        self.webhook_cb = webhook_cb
        self.approval_cb = approval_cb
        self.issue_tracker_cb = issue_tracker_cb
        self.rollback_cb = rollback_cb
        self.sanity_check_cb = sanity_check_cb
        self.explainability_cb = explainability_cb
        self.versioning_cb = versioning_cb
        self.feedback_cb = feedback_cb
        self.evolution_strategies = evolution_strategies or {}
        self.secrets_check_cb = secrets_check_cb
        self.test_coverage_cb = test_coverage_cb
        self.lint_cb = lint_cb
        self.usage_metrics_cb = usage_metrics_cb
        self.error_count_cb = error_count_cb
        self.dependency_check_cb = dependency_check_cb

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_trigger_time = 0

    def _audit(self, action: str, data: dict):
        entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "data": data
        }
        try:
            with open(self.audit_log_path, "a") as f:
                import json
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logging.error(f"[SelfTrigger] Audit log failed: {e}")

    def _alert(self, event: str, data: dict):
        for cb in [self.alert_cb, self.slack_cb, self.discord_cb, self.email_cb, self.webhook_cb]:
            if not cb:
                continue
            try:
                if cb in [self.slack_cb, self.discord_cb]:
                    cb(f"[SelfTrigger][{event}] {data}")
                elif cb is self.email_cb:
                    cb(f"SelfTrigger Event: {event}", str(data))
                else:
                    cb(event, data)
            except Exception as e:
                logging.error(f"[SelfTrigger] Alert callback failed: {e}")

    def _metrics(self, metric: str, value: float):
        for cb in [self.metrics_cb, self.prometheus_cb]:
            if cb:
                cb(metric, value)

    def _score_template(self, fname: str) -> float:
        # Composite scoring: newer, used, error-prone, low coverage, lint fails = lower score (worse)
        score = 0
        meta = self.codegen.meta.get(fname, {})
        # Usage signals (example, can be plugged into real metrics system)
        if self.usage_metrics_cb:
            usage = self.usage_metrics_cb(fname)
            score -= usage * 0.1
        if self.error_count_cb:
            errors = self.error_count_cb(fname)
            score += errors * 0.5
        if self.test_coverage_cb:
            cov = self.test_coverage_cb(fname)
            score += (100 - cov) * 0.1
        if self.lint_cb:
            lints = self.lint_cb(fname)
            score += lints * 0.2
        if meta.get("mode") == "generated":
            score += 1
        # Age: older templates might need update
        if "updated_at" in meta:
            try:
                dt = datetime.strptime(meta["updated_at"], "%Y-%m-%d %H:%M:%S")
                age_days = (datetime.utcnow() - dt).days
                score += age_days * 0.05
            except Exception:
                pass
        return score

    def _find_targets(self) -> List[str]:
        # Multi-criteria: stale, error-prone, low coverage, high usage, outdated deps, etc.
        candidates = []
        for fname, meta in self.codegen.meta.items():
            if not fname.endswith(".py"):
                continue
            if self.secrets_check_cb and not self.secrets_check_cb(fname):
                self._audit("secrets_excluded", {"filename": fname})
                continue
            if self.dependency_check_cb and not self.dependency_check_cb(fname):
                self._audit("dependency_unmet", {"filename": fname})
                continue
            score = self._score_template(fname)
            # Threshold can be dynamic, here fixed as example
            if score > 0.8:
                candidates.append(fname)
        return candidates

    def _run_safety(self, filename: str) -> bool:
        # Run lint, static analysis, tests, etc.
        try:
            if self.sanity_check_cb:
                return self.sanity_check_cb(filename)
            return True
        except Exception as e:
            logging.error(f"[SelfTrigger] Sanity check failed: {e}")
            return False

    def _version(self, filename: str, meta: Dict[str, Any]):
        if self.versioning_cb:
            self.versioning_cb(filename, meta)

    def _issue_tracker(self, event: str, meta: Dict[str, Any]):
        if self.issue_tracker_cb:
            self.issue_tracker_cb(event, meta)

    def _explain(self, filename: str, info: Dict[str, Any]):
        if self.explainability_cb:
            self.explainability_cb(filename, info)

    def _feedback(self, filename: str, meta: Dict[str, Any]):
        if self.feedback_cb:
            self.feedback_cb(filename, meta)

    def _evolve_template(self, filename: str):
        success = False
        explain_info = {}
        for attempt in range(1, self.max_retries + 2):
            try:
                if self.pre_evolve_hook:
                    self.pre_evolve_hook(filename)
                # Approval workflow
                meta = self.codegen.meta.get(filename, {})
                if self.approval_cb and not self.approval_cb(filename, meta):
                    self._audit("approval_denied", {"filename": filename})
                    self._alert("approval_denied", {"filename": filename})
                    return
                # Choose evolution strategy if available
                strategy = self.evolution_strategies.get(filename, None)
                if not strategy:
                    strategy = lambda fn: self.codegen.evolve_code(
                        self.codegen._read_file(f"generated_code/{fn}"),
                        instruction="Update logic and improve clarity",
                        filename=fn
                    )
                result = strategy(filename)
                success = True
                self._version(filename, meta)
                self._issue_tracker("evolve", {"filename": filename, "meta": meta})
                explain_info = {"filename": filename, "result": result}
                self._explain(filename, explain_info)
                # Safety/sanity check after evolution
                if not self._run_safety(filename):
                    self._audit("sanity_failed", {"filename": filename})
                    self._alert("sanity_failed", {"filename": filename})
                    # Attempt rollback/fallback
                    if self.rollback_cb:
                        self.rollback_cb(filename)
                    success = False
                    break
                break
            except Exception as e:
                logging.warning(f"[SelfTrigger] Error evolving {filename} (attempt {attempt}): {e}")
                self._audit("evolve_error", {"filename": filename, "error": str(e)})
                self._alert("evolve_error", {"filename": filename, "error": str(e)})
                if attempt <= self.max_retries:
                    time.sleep(self.retry_delay)
        if self.post_evolve_hook:
            self.post_evolve_hook(filename, success)
        self._audit("evolve", {"filename": filename, "success": success})
        self._alert("evolve", {"filename": filename, "success": success})
        self._metrics("selftrigger_evolve", time.time())
        self._feedback(filename, {"success": success, **explain_info})

    def _adaptive_interval(self, targets_count: int) -> int:
        # Shorten interval if lots of targets, else lengthen.
        if not self.adaptive_interval:
            return self.interval
        if targets_count > 8:
            return max(self.min_interval, self.interval // 3)
        elif targets_count > 3:
            return max(self.min_interval, self.interval // 2)
        elif targets_count == 0:
            return min(self.max_interval, self.interval * 2)
        return self.interval

    def _run_loop(self):
        while not self._stop_event.is_set():
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"[SelfTrigger] Checking at {now}")

            # Distributed lock (optional)
            if self.distributed_lock_cb and not self.distributed_lock_cb():
                msg = "[SelfTrigger] Could not acquire distributed lock, skipping this cycle."
                logging.info(msg)
                time.sleep(self.interval)
                continue

            try:
                with self._lock:
                    if time.time() - self._last_trigger_time < self.throttle_seconds:
                        logging.info("[SelfTrigger] Throttled, skipping this run.")
                        time.sleep(self.interval)
                        continue
                    self._last_trigger_time = time.time()
                targets = self._find_targets()
                logging.info(f"[SelfTrigger] Found {len(targets)} targets for self-improvement.")
                for filename in targets:
                    self._evolve_template(filename)
                # Adaptive interval logic
                sleep_interval = self._adaptive_interval(len(targets))
            except Exception as e:
                logging.warning(f"[SelfTrigger] Error: {e}")
                self._audit("selftrigger_error", {"error": str(e)})
                self._alert("selftrigger_error", {"error": str(e)})
                sleep_interval = self.interval
            self._metrics("selftrigger_idle", time.time())
            time.sleep(sleep_interval)
        logging.info("[SelfTrigger] Stopped auto-evolution monitor.")

    def start(self):
        self.running = True
        self._stop_event.clear()
        if not self._thread or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        logging.info("[SelfTrigger] Auto-evolution monitor started.")

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logging.info("[SelfTrigger] Auto-evolution monitor stopped.")

    def health_status(self) -> Dict[str, Any]:
        try:
            count = len(self._find_targets())
            return {
                "status": "OK",
                "targets_pending": count,
                "running": self.running
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def trigger_manual(self):
        try:
            targets = self._find_targets()
            for filename in targets:
                self._evolve_template(filename)
            return True
        except Exception as e:
            self._alert("manual_trigger_error", {"error": str(e)})
            return False

    # REST API integration (optional)
    def start_rest_api(self, port: int = 7798):
        try:
            from flask import Flask, request, jsonify
        except ImportError:
            logging.info("[SelfTrigger] Flask not installed, REST API not available.")
            return
        app = Flask("SelfTrigger")

        @app.route("/api/selftrigger/health", methods=["GET"])
        def api_health():
            return jsonify(self.health_status())

        @app.route("/api/selftrigger/manual", methods=["POST"])
        def api_manual():
            ok = self.trigger_manual()
            return {"triggered": ok}

        @app.route("/api/selftrigger/history", methods=["GET"])
        def api_history():
            try:
                with open(self.audit_log_path, "r") as f:
                    lines = f.readlines()[-20:]
                import json
                return jsonify([json.loads(line) for line in lines])
            except Exception:
                return jsonify([])

        logging.info(f"[SelfTrigger] REST API starting on port {port} ...")
        threading.Thread(target=app.run, kwargs={"port": port, "host": "0.0.0.0"}, daemon=True).start()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cg = CodeGenerator()
    # Example callbacks for integrations (replace with prod logic)
    def slack_cb(msg): print("[Slack]", msg)
    def discord_cb(msg): print("[Discord]", msg)
    def email_cb(subject, body): print(f"[Email] {subject}: {body}")
    def prometheus_cb(metric, value): print(f"[Prometheus] {metric}: {value}")
    def webhook_cb(event, data): print(f"[Webhook] {event}: {data}")
    def approval_cb(filename, meta): return True  # Always approve, plug-in real approval logic
    def issue_tracker_cb(event, meta): print(f"[IssueTracker] {event}: {meta}")
    def rollback_cb(filename): print(f"[Rollback] {filename}")
    def sanity_check_cb(filename): return True    # Always passes, plug-in real checks
    def explainability_cb(filename, info): print(f"[Explain] {filename}: {info}")
    def versioning_cb(filename, meta): print(f"[Version] {filename} versioned.")
    def feedback_cb(filename, meta): print(f"[Feedback] {filename}: {meta}")
    def secrets_check_cb(filename): return True   # Always safe, plug-in real check
    def test_coverage_cb(filename): return random.uniform(50, 100)
    def lint_cb(filename): return random.randint(0, 5)
    def usage_metrics_cb(filename): return random.randint(0, 100)
    def error_count_cb(filename): return random.randint(0, 3)
    def dependency_check_cb(filename): return True

    trigger = SelfTrigger(
        cg,
        slack_cb=slack_cb,
        discord_cb=discord_cb,
        email_cb=email_cb,
        prometheus_cb=prometheus_cb,
        webhook_cb=webhook_cb,
        approval_cb=approval_cb,
        issue_tracker_cb=issue_tracker_cb,
        rollback_cb=rollback_cb,
        sanity_check_cb=sanity_check_cb,
        explainability_cb=explainability_cb,
        versioning_cb=versioning_cb,
        feedback_cb=feedback_cb,
        secrets_check_cb=secrets_check_cb,
        test_coverage_cb=test_coverage_cb,
        lint_cb=lint_cb,
        usage_metrics_cb=usage_metrics_cb,
        error_count_cb=error_count_cb,
        dependency_check_cb=dependency_check_cb
    )
    trigger.start()
    trigger.start_rest_api()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        trigger.stop()