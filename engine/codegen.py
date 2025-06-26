import os
import datetime
import logging
import time
from typing import Optional, Callable, Dict, Any

class CodeGenerator:
    """
    Vivian-grade, observable, auditable code generation and management engine.

    Features:
      - Audit log for all script generations and deletions
      - Alert/metrics hooks for completion/failure (Slack/email/webhook/Prometheus-ready)
      - Pre/post hooks for validation, notification, or review
      - Explainability/reporting hooks
      - RBAC-ready for user/role-based restrictions
      - Integrated with file watcher or hot-reload if needed
      - REST API ready (can be integrated)
    """

    def __init__(
        self,
        base_path: str = "generated_code",
        audit_log_path: str = "code_generator_audit.jsonl",
        pre_generate_hook: Optional[Callable[[str, str], None]] = None,
        post_generate_hook: Optional[Callable[[str, str, bool], None]] = None,
        pre_delete_hook: Optional[Callable[[str], None]] = None,
        post_delete_hook: Optional[Callable[[str, bool], None]] = None,
        alert_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        metrics_cb: Optional[Callable[[str, float], None]] = None,
        explainability_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        rbac_cb: Optional[Callable[[str, str], bool]] = None,
        current_user: Optional[str] = None
    ):
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        self.audit_log_path = audit_log_path
        self.pre_generate_hook = pre_generate_hook
        self.post_generate_hook = post_generate_hook
        self.pre_delete_hook = pre_delete_hook
        self.post_delete_hook = post_delete_hook
        self.alert_cb = alert_cb
        self.metrics_cb = metrics_cb
        self.explainability_cb = explainability_cb
        self.rbac_cb = rbac_cb
        self.current_user = current_user or os.environ.get("USER", "unknown")
        self._log = logging.getLogger("CodeGenerator")

    def _audit(self, action: str, data: dict):
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "user": self.current_user,
            "data": data
        }
        try:
            with open(self.audit_log_path, "a") as f:
                import json; f.write(json.dumps(entry) + "\n")
        except Exception as e:
            self._log.error(f"[CodeGenerator] Audit log failed: {e}")

    def _alert(self, event: str, data: dict):
        if self.alert_cb:
            try:
                self.alert_cb(event, data)
            except Exception as e:
                self._log.error(f"[CodeGenerator] Alert callback failed: {e}")

    def _metrics(self, metric: str, value: float):
        if self.metrics_cb:
            self.metrics_cb(metric, value)

    def _explain(self, info: Dict[str, Any]):
        if self.explainability_cb:
            self.explainability_cb(info)

    def generate_script(self, filename: str, content: str) -> str:
        """
        Generates a code script with hooks, audit, alerting, and RBAC.
        Returns the full path of the generated script.
        """
        if self.rbac_cb and not self.rbac_cb(self.current_user, "generate"):
            self._log.warning(f"[CodeGenerator] RBAC denied for user {self.current_user} to generate.")
            self._alert("rbac_denied", {"user": self.current_user, "action": "generate"})
            return ""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"{filename}_{timestamp}.py"
        full_path = os.path.join(self.base_path, safe_name)
        if self.pre_generate_hook:
            self.pre_generate_hook(filename, content)
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            self._log.info(f"[CodeGenerator] Generated script: {full_path}")
            self._audit("generated", {"filename": safe_name, "full_path": full_path})
            if self.post_generate_hook:
                self.post_generate_hook(full_path, content, True)
            self._metrics("codegen_generate_success", time.time())
            self._explain({"action": "generate", "filename": filename, "full_path": full_path})
            return full_path
        except Exception as e:
            self._log.error(f"[CodeGenerator] Generation error: {e}")
            self._audit("generate_failed", {"filename": filename, "error": str(e)})
            self._alert("generate_failed", {"filename": filename, "error": str(e)})
            if self.post_generate_hook:
                self.post_generate_hook(full_path, content, False)
            return ""

    def list_generated_files(self):
        """
        Lists all generated files in the base path.
        """
        try:
            files = os.listdir(self.base_path)
            self._audit("list_files", {"files": files})
            return files
        except Exception as e:
            self._log.error(f"[CodeGenerator] List files error: {e}")
            return []

    def delete_generated_file(self, filename: str) -> bool:
        """
        Deletes a generated file with audit, alerting, hooks, and RBAC.
        """
        if self.rbac_cb and not self.rbac_cb(self.current_user, "delete"):
            self._log.warning(f"[CodeGenerator] RBAC denied for user {self.current_user} to delete.")
            self._alert("rbac_denied", {"user": self.current_user, "action": "delete"})
            return False
        path = os.path.join(self.base_path, filename)
        if self.pre_delete_hook:
            self.pre_delete_hook(filename)
        if not os.path.exists(path):
            self._log.warning(f"[CodeGenerator] File not found: {filename}")
            self._audit("delete_failed", {"filename": filename, "reason": "not_found"})
            if self.post_delete_hook:
                self.post_delete_hook(filename, False)
            return False
        try:
            os.remove(path)
            self._log.info(f"[CodeGenerator] Deleted script: {filename}")
            self._audit("deleted", {"filename": filename})
            if self.post_delete_hook:
                self.post_delete_hook(filename, True)
            self._metrics("codegen_delete_success", time.time())
            self._explain({"action": "delete", "filename": filename})
            return True
        except Exception as e:
            self._log.error(f"[CodeGenerator] Deletion error: {e}")
            self._audit("delete_failed", {"filename": filename, "error": str(e)})
            self._alert("delete_failed", {"filename": filename, "error": str(e)})
            if self.post_delete_hook:
                self.post_delete_hook(filename, False)
            return False