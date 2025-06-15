import os
import json
import logging
import datetime
import threading
from typing import Dict, Any, Optional, List, Callable
from functools import wraps

# --- Optional dependencies for advanced features ---
try:
    from cryptography.fernet import Fernet, InvalidToken
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False

# ---------- Utility Decorators ----------

def synchronized(method):
    """Decorator to lock methods for thread safety."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper

# ---------- Cloud & Plugin Stubs ----------

class EvolverPlugin:
    """Base class for plugins."""
    def on_event(self, event: str, data: Dict[str, Any]): pass

class EvolverCloudBackend:
    """Stub for cloud storage backend."""
    def backup(self, local_path: str, remote_path: str): pass
    def restore(self, remote_path: str, local_path: str): pass

class EvolverNotifier:
    """Stub for notifications (webhook, email, etc)."""
    def notify(self, event: str, data: Dict[str, Any]): pass

# ---------- Main Evolver Class ----------

class Evolver:
    SCHEMA_VERSION = "2.0.0"

    def __init__(self, config: Optional[Dict[str, Any]] = None, encryption_password: Optional[str] = None):
        self.config = config or {}
        self.user = self.config.get("user", "unknown")
        self.session_id = self.config.get("session_id") or f"{self.user}-{self._now()}"
        self.base_dir = self.config.get("evolver_dir", "evolver")
        self._set_paths()
        os.makedirs(self.base_dir, exist_ok=True)
        self.lock = threading.RLock()
        self.plugins: List[EvolverPlugin] = []
        self.notifier = self.config.get("notifier", EvolverNotifier())
        self.cloud = self.config.get("cloud", EvolverCloudBackend())
        self.encryption_enabled = bool(encryption_password and ENCRYPTION_AVAILABLE)
        self.fernet = Fernet(self._derive_key(encryption_password)) if self.encryption_enabled else None
        # Quota/retention defaults
        self.max_history_per_session = self.config.get("max_history_per_session", 2000)
        self.max_sessions = self.config.get("max_sessions", 200)
        self.max_audit = self.config.get("max_audit", 5000)
        self.max_suggestions = self.config.get("max_suggestions", 1000)
        self.max_comments_per_suggestion = self.config.get("max_comments_per_suggestion", 100)
        self.retention_days = self.config.get("retention_days", 365)
        # Data
        self.suggestions: Dict[str, Any] = self._load_json(self.suggestions_file, default={})
        self.history: Dict[str, Any] = self._load_json(self.history_file, default={})
        self.audit: List[Dict[str, Any]] = self._load_json(self.audit_file, default=[])
        self._prune_all()
        self._migrate_schema()

    # ---------- File & Encryption Helpers ----------
    def _set_paths(self):
        self.suggestions_file = os.path.join(self.base_dir, self.config.get("suggestions_file", "suggestions.json"))
        self.history_file = os.path.join(self.base_dir, self.config.get("history_file", "history.json"))
        self.audit_file = os.path.join(self.base_dir, self.config.get("audit_file", "audit.json"))
        self.backup_dir = os.path.join(self.base_dir, "backup")

    def _now(self):
        return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def _derive_key(self, password: str) -> bytes:
        # For demo: use SHA256 of password as key. Use PBKDF2 in production!
        import hashlib, base64
        return base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())

    @synchronized
    def _atomic_save_json(self, path: str, data: Any):
        tmp_path = f"{path}.tmp"
        try:
            self._backup_file(path)
            raw = json.dumps(data, indent=4).encode("utf-8")
            if self.encryption_enabled:
                raw = self.fernet.encrypt(raw)
            with open(tmp_path, "wb") as f:
                f.write(raw)
            os.replace(tmp_path, path)
        except Exception as e:
            logging.error(f"[Evolver] Failed to save {path}: {e}")

    @synchronized
    def _load_json(self, path: str, default: Any) -> Any:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                    if self.encryption_enabled:
                        try:
                            raw = self.fernet.decrypt(raw)
                        except InvalidToken:
                            logging.error(f"[Evolver] Decryption failed for {path}")
                            return default
                    return json.loads(raw.decode("utf-8"))
            except Exception as e:
                logging.error(f"[Evolver] Failed to load {path}: {e}")
        return default

    def _backup_file(self, path: str):
        if os.path.exists(path):
            os.makedirs(self.backup_dir, exist_ok=True)
            timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            fname = os.path.basename(path)
            bname = f"{fname}.{timestamp}.bak"
            backup_path = os.path.join(self.backup_dir, bname)
            try:
                with open(path, "rb") as src, open(backup_path, "wb") as dst:
                    dst.write(src.read())
            except Exception as e:
                logging.warning(f"[Evolver] Backup failed for {path}: {e}")

    # ---------- Schema Versioning & Migration ----------
    @synchronized
    def _migrate_schema(self):
        # Example: Add schema_version to all files, migrate fields, etc.
        for data, path in [(self.suggestions, self.suggestions_file), (self.history, self.history_file), (self.audit, self.audit_file)]:
            if isinstance(data, dict) and data.get("_schema_version") != self.SCHEMA_VERSION:
                data["_schema_version"] = self.SCHEMA_VERSION
                self._atomic_save_json(path, data)
            if isinstance(data, list) and (not data or data[0].get("_schema_version") != self.SCHEMA_VERSION):
                if data:
                    data[0]["_schema_version"] = self.SCHEMA_VERSION
                self._atomic_save_json(path, data)

    # ---------- Plugin System ----------
    def load_plugin(self, plugin: EvolverPlugin):
        self.plugins.append(plugin)

    def _emit_event(self, event: str, data: Dict[str, Any]):
        for plugin in self.plugins:
            try:
                plugin.on_event(event, data)
            except Exception as e:
                logging.error(f"[Evolver] Plugin error: {e}")
        try:
            self.notifier.notify(event, data)
        except Exception as e:
            logging.warning(f"[Evolver] Notifier error: {e}")

    # ---------- History, Suggestions, Audit, Voting, Compliance, etc. ----------
    @synchronized
    def record_usage(self, feature: str, details: Optional[Dict[str, Any]] = None, user: Optional[str] = None):
        now = self._now()
        entry = {
            "time": now,
            "feature": feature,
            "details": details or {},
            "user": user or self.user,
            "session_id": self.session_id
        }
        sess = self.session_id
        self.history.setdefault(sess, []).append(entry)
        if len(self.history[sess]) > self.max_history_per_session:
            self.history[sess] = self.history[sess][-self.max_history_per_session:]
        self._prune_history()
        self._atomic_save_json(self.history_file, self.history)
        self._add_audit("usage", entry)
        self._emit_event("usage", entry)

    @synchronized
    def suggest_upgrade(self, area: str, reason: str, recommended_code: Optional[str] = None, user: Optional[str] = None,
                        feedback: str = "", status: str = "pending", version: Optional[str] = None,
                        tags: Optional[List[str]] = None, reviewers: Optional[List[str]] = None):
        now = self._now()
        suggestion_id = f"{area}:{now}"
        audit_entry = {
            "id": suggestion_id,
            "time": now,
            "reason": reason,
            "code": recommended_code or "Pending",
            "applied": False,
            "user": user or self.user,
            "status": status,
            "feedback": feedback,
            "version": version or "1.0.0",
            "tags": tags or [],
            "comments": [],
            "votes": {},
            "required_approvals": self.config.get("required_approvals", 2),
            "reviewers": reviewers or [],
            "consent": {},
            "gdpr_erased": False
        }
        if area not in self.suggestions:
            self.suggestions[area] = {"history": [audit_entry]}
        else:
            self.suggestions[area]["history"].append(audit_entry)
        self.suggestions[area].update(audit_entry)
        self._prune_suggestions()
        self._atomic_save_json(self.suggestions_file, self.suggestions)
        self._add_audit("suggest_upgrade", {"area": area, **audit_entry})
        self._emit_event("suggestion", audit_entry)
        logging.info(f"[Evolver] Suggested upgrade: {area} – {reason}")

    @synchronized
    def vote_suggestion(self, area: str, user: str, vote: str):
        if area in self.suggestions:
            self.suggestions[area].setdefault("votes", {})
            self.suggestions[area]["votes"][user] = vote
            self._atomic_save_json(self.suggestions_file, self.suggestions)
            self._add_audit("vote", {"area": area, "user": user, "vote": vote})
            self._emit_event("vote", {"area": area, "user": user, "vote": vote})
            self._check_approvals(area)

    @synchronized
    def _check_approvals(self, area: str):
        suggestion = self.suggestions.get(area, {})
        votes = suggestion.get("votes", {})
        approvals = sum(1 for v in votes.values() if v == "approve")
        if approvals >= suggestion.get("required_approvals", 2):
            self.mark_applied(area, user="system", feedback="Auto-applied by consensus")

    @synchronized
    def comment_on_suggestion(self, area: str, comment: str, user: Optional[str] = None):
        now = self._now()
        if area in self.suggestions:
            self.suggestions[area].setdefault("comments", [])
            self.suggestions[area]["comments"].append({
                "user": user or self.user,
                "time": now,
                "comment": comment
            })
            if len(self.suggestions[area]["comments"]) > self.max_comments_per_suggestion:
                self.suggestions[area]["comments"] = self.suggestions[area]["comments"][-self.max_comments_per_suggestion:]
            self._atomic_save_json(self.suggestions_file, self.suggestions)
            self._add_audit("comment", {"area": area, "user": user or self.user, "comment": comment})
            self._emit_event("comment", {"area": area, "user": user or self.user, "comment": comment})

    @synchronized
    def consent(self, area: str, user: str, accepted: bool):
        if area in self.suggestions:
            self.suggestions[area].setdefault("consent", {})
            self.suggestions[area]["consent"][user] = {"accepted": accepted, "at": self._now()}
            self._atomic_save_json(self.suggestions_file, self.suggestions)
            self._add_audit("consent", {"area": area, "user": user, "accepted": accepted})

    @synchronized
    def gdpr_delete(self, user: str):
        # Erase user data from suggestions, history, audit
        for area, data in self.suggestions.items():
            for h in data.get("history", []):
                if h.get("user") == user:
                    h["gdpr_erased"] = True
                    h["user"] = "erased"
                    h["reason"] = ""
                    h["code"] = ""
            if data.get("user") == user:
                data["gdpr_erased"] = True
                data["user"] = "erased"
        for sess, entries in self.history.items():
            for entry in entries:
                if entry.get("user") == user:
                    entry["user"] = "erased"
        for entry in self.audit:
            if entry.get("details", {}).get("user") == user:
                entry["details"]["user"] = "erased"
        self._atomic_save_json(self.suggestions_file, self.suggestions)
        self._atomic_save_json(self.history_file, self.history)
        self._atomic_save_json(self.audit_file, self.audit)
        self._add_audit("gdpr_delete", {"user": user})

    # ---------- Retention, Pruning, Export/Import, Cloud ----------
    @synchronized
    def _prune_history(self):
        if len(self.history) > self.max_sessions:
            sorted_sessions = sorted(self.history.items(), key=lambda x: x[1][0]["time"])
            for sid, _ in sorted_sessions[:-self.max_sessions]:
                del self.history[sid]
            self._atomic_save_json(self.history_file, self.history)
            self._add_audit("prune_history", {"max_sessions": self.max_sessions})

    @synchronized
    def _prune_all(self):
        self._prune_history()
        self._prune_audit()
        self._prune_suggestions()

    @synchronized
    def _prune_audit(self):
        if len(self.audit) > self.max_audit:
            self.audit = self.audit[-self.max_audit:]
            self._atomic_save_json(self.audit_file, self.audit)

    @synchronized
    def _prune_suggestions(self):
        if len(self.suggestions) > self.max_suggestions:
            # Remove oldest suggestions
            sorted_suggestions = sorted(self.suggestions.items(), key=lambda x: x[1].get("time", self._now()))
            for area, _ in sorted_suggestions[:-self.max_suggestions]:
                del self.suggestions[area]
            self._atomic_save_json(self.suggestions_file, self.suggestions)
            self._add_audit("prune_suggestions", {"max_suggestions": self.max_suggestions})

    @synchronized
    def export_data(self, path: str):
        data = {
            "suggestions": self.suggestions,
            "history": self.history,
            "audit": self.audit,
            "schema_version": self.SCHEMA_VERSION
        }
        try:
            raw = json.dumps(data, indent=4).encode("utf-8")
            if self.encryption_enabled:
                raw = self.fernet.encrypt(raw)
            with open(path, "wb") as f:
                f.write(raw)
            self._add_audit("export_data", {"path": path})
            self._emit_event("export", {"path": path})
            logging.info(f"[Evolver] Exported data to {path}")
        except Exception as e:
            logging.error(f"[Evolver] Failed to export data: {e}")

    @synchronized
    def import_data(self, path: str):
        try:
            with open(path, "rb") as f:
                raw = f.read()
                if self.encryption_enabled:
                    raw = self.fernet.decrypt(raw)
                data = json.loads(raw.decode("utf-8"))
            self.suggestions = data.get("suggestions", {})
            self.history = data.get("history", {})
            self.audit = data.get("audit", [])
            self._atomic_save_json(self.suggestions_file, self.suggestions)
            self._atomic_save_json(self.history_file, self.history)
            self._atomic_save_json(self.audit_file, self.audit)
            self._add_audit("import_data", {"path": path})
            self._emit_event("import", {"path": path})
            logging.info(f"[Evolver] Imported data from {path}")
        except Exception as e:
            logging.error(f"[Evolver] Failed to import data: {e}")

    # ---------- Cloud/Remote ----------
    def backup_to_cloud(self, remote_path: str):
        for file in [self.suggestions_file, self.history_file, self.audit_file]:
            self.cloud.backup(file, os.path.join(remote_path, os.path.basename(file)))
        self._add_audit("cloud_backup", {"remote_path": remote_path})

    def restore_from_cloud(self, remote_path: str):
        for file in [self.suggestions_file, self.history_file, self.audit_file]:
            self.cloud.restore(os.path.join(remote_path, os.path.basename(file)), file)
        self._add_audit("cloud_restore", {"remote_path": remote_path})

    # ---------- API/CLI/Extensibility Hooks ----------
    def for_each_suggestion(self, func: Callable[[str, Dict[str, Any]], None]):
        for area, data in self.suggestions.items():
            func(area, data)

    def for_each_history_entry(self, func: Callable[[str, Dict[str, Any]], None]):
        for sess, entries in self.history.items():
            for entry in entries:
                func(sess, entry)

    def for_each_audit(self, func: Callable[[Dict[str, Any]], None]):
        for entry in self.audit:
            func(entry)

if __name__ == "__main__":
    # Example usage with encryption password (if cryptography installed)
    password = os.environ.get("EVOLVER_PASS")
    evolver = Evolver({"user": "gregmish"}, encryption_password=password)
    evolver.record_usage("feature_x", {"param": 1}, user="gregmish")
    evolver.suggest_upgrade(
        "db_layer", "Improve caching", "def new_cache(): ...", user="gregmish",
        tags=["db", "performance"], version="1.1.0", reviewers=["alice", "bob"]
    )
    evolver.comment_on_suggestion("db_layer", "This looks good, but needs more tests.", user="alice")
    evolver.vote_suggestion("db_layer", "alice", "approve")
    evolver.vote_suggestion("db_layer", "bob", "approve")
    print("Suggestions:", evolver.get_suggestions())
    evolver.export_data("evolver_export.json")
    evolver.backup_to_cloud("remote_evolver_backup/")
    print("Usage stats:", evolver.usage_stats())
    print("Audit Trail:", evolver.audit)
    evolver.gdpr_delete("alice")