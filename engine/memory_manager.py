import os
import shutil
import logging
import json
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
import threading

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)
META_FILE_SUFFIX = "_session_meta.json"
SNAPSHOT_DIR = MEMORY_DIR / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)

def get_memory_file(user: str, session: str) -> Path:
    return MEMORY_DIR / f"vivian_memory_{user}_{session}.json"

def current_time() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

def days_ago(iso_time: str) -> int:
    dt = datetime.datetime.fromisoformat(iso_time.rstrip("Z"))
    return (datetime.datetime.utcnow() - dt).days

class NotificationStub:
    def send(self, msg: str):
        logging.info(f"[Notification] {msg}")

class LLMStub:
    def summarize(self, text: str) -> str:
        return f"[LLM Summary]: {text[:100]}..."

class MemoryManager:
    """
    Vivian-compatible advanced memory/session manager.
    Features: usage analytics, event timeline, multi-user, snapshots/versioning, plugin/event hooks, and more.
    """
    def __init__(self, user: str, notifier: Optional[Any] = None, llm: Optional[Any] = None, config: Optional[dict] = None, plugin_event_cb: Optional[Callable] = None):
        self.user = user
        self.session = "default"
        self.memory_file = get_memory_file(self.user, self.session)
        self.memory: Dict[str, Any] = {}
        self.meta_file = MEMORY_DIR / f"{self.user}{META_FILE_SUFFIX}"
        self.session_meta: Dict[str, Any] = {}
        self.deleted_sessions = set()
        self.lock = threading.RLock()
        self.notifier = notifier or NotificationStub()
        self.llm = llm or LLMStub()
        self._plugin_event_cb = plugin_event_cb
        self.config = config or {}
        self._load_session_meta()
        self.load_memory()
        self.record_session_access(self.session)
        self.log_event("manager_init", {"session": self.session, "user": self.user})

    # ------------ Core Event Log for Vivian Plugins -------------
    def log_event(self, event_type: str, data: dict = None):
        """Append an event to the memory event log, and persist."""
        event = {
            "time": current_time(),
            "type": event_type,
            "data": data or {},
        }
        self.memory.setdefault("_event_log", []).append(event)
        self.save_memory()
        self._plugin_event("on_log_event", {"type": event_type, "data": data})

    def get_recent(self, limit: int = 10, user: Optional[str] = None, event_type: Optional[str] = None) -> List[dict]:
        """Fetch recent events, optionally filtered by user and/or event_type."""
        events = self.memory.get("_event_log", [])
        if user:
            events = [e for e in events if e["data"].get("user") == user]
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return events[-limit:] if events else []

    # -------------------- Session File Management --------------------
    def _encrypt(self, data: bytes) -> bytes:
        return data

    def _decrypt(self, data: bytes) -> bytes:
        return data

    def load_memory(self):
        with self.lock:
            if self.memory_file.exists():
                try:
                    with open(self.memory_file, "rb") as f:
                        raw = f.read()
                        if self.config.get("security", {}).get("encrypt_memory"):
                            raw = self._decrypt(raw)
                        text = raw.decode("utf-8")
                        self.memory = json.loads(text)
                    logging.info(f"[Memory] Loaded session '{self.session}'.")
                except Exception as e:
                    logging.error(f"[Memory] Corrupted session '{self.session}', attempting repair: {e}")
                    self.log_event("corrupted_memory", {"session": self.session, "error": str(e)})
                    bak = self.memory_file.with_suffix(".bak")
                    if bak.exists():
                        shutil.copy2(bak, self.memory_file)
                        with open(self.memory_file, "r", encoding="utf-8") as f:
                            self.memory = json.load(f)
                        logging.info(f"[Memory] Restored '{self.session}' from backup.")
                    else:
                        self.memory = {}
            else:
                self.memory = {}
                logging.info(f"[Memory] Created new empty session '{self.session}'.")

    def save_memory(self):
        with self.lock:
            if self.memory_file.exists():
                backup_path = self.memory_file.with_suffix(".bak")
                try:
                    shutil.copy2(self.memory_file, backup_path)
                except Exception as e:
                    logging.warning(f"[Memory] Failed to backup before saving: {e}")

            self.memory["_last_saved"] = current_time()
            self.memory["_session"] = self.session
            self.memory["_user"] = self.user
            try:
                out = json.dumps(self.memory, indent=2)
                data = out.encode("utf-8")
                if self.config.get("security", {}).get("encrypt_memory"):
                    data = self._encrypt(data)
                with open(self.memory_file, "wb") as f:
                    f.write(data)
                logging.info(f"[Memory] Saved session '{self.session}'.")
                self._save_session_snapshot()
            except Exception as e:
                logging.error(f"[Memory] Failed to save session '{self.session}': {e}")

    def _save_session_snapshot(self):
        snap_name = f"{self.user}_{self.session}_{current_time().replace(':', '').replace('-', '')}.json"
        snap_path = SNAPSHOT_DIR / snap_name
        try:
            with open(snap_path, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2)
            logging.info(f"[Memory] Created snapshot for session '{self.session}'.")
        except Exception as e:
            logging.warning(f"[Memory] Failed to create snapshot: {e}")

    def list_snapshots(self, session_name: Optional[str] = None) -> List[str]:
        snaps = [f.name for f in SNAPSHOT_DIR.glob(f"{self.user}_{session_name or '*'}_*.json")]
        return sorted(snaps, reverse=True)

    def restore_snapshot(self, snapshot_name: str) -> bool:
        snap_path = SNAPSHOT_DIR / snapshot_name
        if not snap_path.exists():
            logging.warning(f"[Memory] Snapshot '{snapshot_name}' not found for restore.")
            return False
        session_name = snapshot_name.split("_")[1]
        dst = get_memory_file(self.user, session_name)
        try:
            shutil.copy2(snap_path, dst)
            logging.info(f"[Memory] Restored session '{session_name}' from snapshot '{snapshot_name}'.")
            return True
        except Exception as e:
            logging.error(f"[Memory] Failed to restore snapshot '{snapshot_name}': {e}")
            return False

    # -------------------- Session Meta/Tagging/Timeline --------------------
    def _load_session_meta(self):
        if self.meta_file.exists():
            try:
                with open(self.meta_file, "r", encoding="utf-8") as f:
                    self.session_meta = json.load(f)
            except Exception:
                self.session_meta = {}
        else:
            self.session_meta = {}

    def save_session_meta(self):
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(self.session_meta, f, indent=2)

    def tag_session(self, session_name: str, tags: List[str]):
        meta = self.session_meta.setdefault(session_name, {})
        meta["tags"] = list(set(meta.get("tags", []) + tags))
        self.save_session_meta()
        self.log_event("tag_session", {"session": session_name, "tags": tags})

    def search_by_tag(self, tag: str) -> List[str]:
        return [name for name, meta in self.session_meta.items() if tag in meta.get("tags", [])]

    # -------------------- Usage Analytics & Event Log --------------------
    def session_usage_stats(self) -> Dict[str, int]:
        return dict(sorted(
            {k: v.get("accesses", 0) for k, v in self.session_meta.items()}.items(),
            key=lambda x: -x[1]
        ))

    def record_session_access(self, session_name: str):
        meta = self.session_meta.setdefault(session_name, {})
        meta["accesses"] = meta.get("accesses", 0) + 1
        meta["last_access"] = current_time()
        self.save_session_meta()

    def session_timeline(self, session_name: Optional[str] = None) -> List[dict]:
        events = []
        for fname in MEMORY_DIR.glob(f"vivian_memory_{self.user}_*.json"):
            try:
                with open(fname, "r", encoding="utf-8") as f:
                    mem = json.load(f)
                if session_name is None or mem.get("_session") == session_name:
                    events.extend(mem.get("_event_log", []))
            except Exception:
                continue
        return sorted(events, key=lambda e: e["time"])

    def export_event_log(self, out_path: Path, all_sessions: bool = True):
        all_events = []
        sessions = self.list_sessions() if all_sessions else [{"name": self.session}]
        for session in sessions:
            path = get_memory_file(self.user, session["name"])
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        mem = json.load(f)
                    all_events.extend(mem.get("_event_log", []))
                except Exception:
                    continue
        with open(out_path, "w", encoding="utf-8") as out_f:
            json.dump(all_events, out_f, indent=2)
        logging.info(f"[Memory] Exported event log to {out_path}")

    # -------------------- Session Management & Context/Notes --------------------
    def list_sessions(self, details: bool = False) -> List[Dict[str, Any]]:
        pattern = f"vivian_memory_{self.user}_"
        sessions = []
        for f in MEMORY_DIR.glob(f"{pattern}*.json"):
            if f.name.endswith(".bak") or f.name.startswith(".archive"):
                continue
            session_name = f.name[len(pattern):-5]
            meta = {
                "name": session_name,
                "file": f.name,
            }
            if details:
                stat = f.stat()
                meta.update({
                    "modified": stat.st_mtime,
                    "size": stat.st_size,
                    "last_saved": self._get_last_saved_from_file(f),
                    "tags": self.session_meta.get(session_name, {}).get("tags", []),
                    "accesses": self.session_meta.get(session_name, {}).get("accesses", 0),
                    "last_access": self.session_meta.get(session_name, {}).get("last_access")
                })
            sessions.append(meta)
        return sorted(sessions, key=lambda x: x.get("modified", 0), reverse=True)

    def _get_last_saved_from_file(self, path: Path) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("_last_saved")
        except Exception:
            return None

    def switch_session(self, new_session: str) -> bool:
        self.save_memory()
        self.session = new_session
        self.memory_file = get_memory_file(self.user, new_session)
        self.load_memory()
        self.record_session_access(new_session)
        self.log_event("switch_session", {"to": new_session})
        self._plugin_event("on_switch_session", {"to": new_session})
        return True

    def get_recent_context(self, limit: Optional[int] = None) -> List[dict]:
        ctx = self.memory.get("context", [])
        if limit is None:
            limit = self.config.get("context_window", 20)
        return ctx[-limit:] if ctx else []

    def get_context(self) -> List[dict]:
        return self.memory.get("context", [])

    def add_context(self, entry: dict):
        entry["time"] = current_time()
        self.memory.setdefault("context", []).append(entry)
        self.save_memory()
        self.log_event("add_context", {"entry": entry})
        self._plugin_event("on_add_context", {"entry": entry})

    def get_all_notes(self) -> Dict[str, str]:
        return self.memory.get("notes", {})

    def add_note(self, topic: str, note: str):
        self.memory.setdefault("notes", {})[topic] = note
        self.save_memory()
        self.log_event("add_note", {"topic": topic})
        self._plugin_event("on_add_note", {"topic": topic, "note": note})

    # -------------------- Deletion, Archival, Undelete, Cleanup --------------------
    def delete_session(self, session_name: str, archive: bool = True) -> bool:
        path = get_memory_file(self.user, session_name)
        if not path.exists():
            logging.warning(f"[Memory] Session '{session_name}' not found for deletion.")
            return False
        try:
            if archive:
                archive_path = path.parent / (".archive_" + path.name)
                shutil.move(str(path), str(archive_path))
                logging.info(f"[Memory] Session '{session_name}' archived as '{archive_path.name}'.")
            else:
                os.remove(path)
                logging.info(f"[Memory] Session '{session_name}' deleted.")
            self.deleted_sessions.add(session_name)
            self.log_event("delete_session", {"session": session_name, "archived": archive})
            self.notifier.send(f"Session '{session_name}' archived/deleted by user {self.user}")
            self._plugin_event("on_delete_session", {"session": session_name, "archived": archive})
            return True
        except Exception as e:
            logging.error(f"[Memory] Failed to delete/archive session '{session_name}': {e}")
            return False

    def undelete_session(self, session_name: str) -> bool:
        archive_path = MEMORY_DIR / (".archive_vivian_memory_" + self.user + "_" + session_name + ".json")
        out_path = get_memory_file(self.user, session_name)
        if not archive_path.exists():
            logging.warning(f"[Memory] Archived session '{session_name}' not found for restore.")
            return False
        try:
            shutil.move(str(archive_path), str(out_path))
            logging.info(f"[Memory] Session '{session_name}' restored from archive.")
            self.deleted_sessions.discard(session_name)
            self.log_event("undelete_session", {"session": session_name})
            self._plugin_event("on_undelete_session", {"session": session_name})
            return True
        except Exception as e:
            logging.error(f"[Memory] Failed to restore session '{session_name}': {e}")
            return False

    def session_metadata(self, session_name: str) -> Optional[Dict[str, Any]]:
        path = get_memory_file(self.user, session_name)
        if not path.exists():
            return None
        stat = path.stat()
        last_saved = self._get_last_saved_from_file(path)
        meta = self.session_meta.get(session_name, {})
        return {
            "name": session_name,
            "modified": stat.st_mtime,
            "size": stat.st_size,
            "last_saved": last_saved,
            "tags": meta.get("tags", []),
            "accesses": meta.get("accesses", 0),
            "last_access": meta.get("last_access")
        }

    def search_sessions(self, substring: str) -> List[str]:
        return [
            s["name"] for s in self.list_sessions()
            if substring.lower() in s["name"].lower()
        ]

    def export_session(self, session_name: str, export_path: Path) -> bool:
        src = get_memory_file(self.user, session_name)
        if src.exists():
            try:
                shutil.copy2(src, export_path)
                logging.info(f"[Memory] Exported session '{session_name}' to '{export_path}'.")
                self.log_event("export_session", {"session": session_name, "to": str(export_path)})
                return True
            except Exception as e:
                logging.error(f"[Memory] Failed to export session '{session_name}': {e}")
        return False

    def import_session(self, import_path: Path, new_session_name: str) -> bool:
        dst = get_memory_file(self.user, new_session_name)
        try:
            shutil.copy2(import_path, dst)
            logging.info(f"[Memory] Imported session '{new_session_name}' from '{import_path}'.")
            self.log_event("import_session", {"session": new_session_name, "from": str(import_path)})
            return True
        except Exception as e:
            logging.error(f"[Memory] Failed to import session '{new_session_name}': {e}")
            return False

    def cleanup_archives(self, max_age_days: int = 30):
        now = datetime.datetime.utcnow().timestamp()
        for f in MEMORY_DIR.glob(".archive_*.json"):
            age_days = (now - f.stat().st_mtime) / 86400
            if age_days > max_age_days:
                try:
                    os.remove(f)
                    logging.info(f"[Memory] Cleaned up archived file: {f.name}")
                    self.log_event("cleanup_archive", {"file": f.name})
                except Exception as e:
                    logging.error(f"[Memory] Failed to remove archive '{f.name}': {e}")

    def prune_sessions(self, keep_latest: int = 20):
        all_sessions = sorted(self.list_sessions(details=True), key=lambda x: x.get("modified", 0), reverse=True)
        for meta in all_sessions[keep_latest:]:
            self.delete_session(meta["name"], archive=True)
        self.log_event("prune_sessions", {"kept": keep_latest})

    # -------------------- AI/LLM Features --------------------
    def summarize_session(self, session_name: Optional[str] = None) -> str:
        session_name = session_name or self.session
        path = get_memory_file(self.user, session_name)
        if not path.exists():
            return "[No such session]"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            context = data.get("context", [])
            notes = data.get("notes", {})
            text = json.dumps(context, indent=2) + "\n" + json.dumps(notes, indent=2)
            return self.llm.summarize(text)
        except Exception as e:
            logging.error(f"[Memory] Failed to summarize session '{session_name}': {e}")
            return "[Summary error]"

    def auto_suggest_cleanup(self):
        sessions = self.list_sessions(details=True)
        if len(sessions) > 30:
            msg = f"Auto-suggestion: Prune old sessions (currently {len(sessions)})."
            logging.info(f"[Memory] {msg}")
            self.notifier.send(msg)
            self.log_event("auto_suggest_cleanup", {"action": "prune", "count": len(sessions)})
        old_sessions = [s for s in sessions if s.get("last_saved") and
            days_ago(s["last_saved"]) > 90]
        if old_sessions:
            msg = f"Auto-suggestion: Archive {len(old_sessions)} old sessions."
            logging.info(f"[Memory] {msg}")
            self.notifier.send(msg)
            self.log_event("auto_suggest_cleanup", {"action": "archive", "count": len(old_sessions)})

    # -------------------- Multi-user Support --------------------
    @staticmethod
    def list_all_users() -> List[str]:
        users = set()
        for f in MEMORY_DIR.glob("vivian_memory_*_*.json"):
            parts = f.name.split("_")
            if len(parts) >= 3:
                users.add(parts[2])
        return list(users)

    def switch_user(self, new_user: str):
        self.save_memory()
        self.user = new_user
        self.meta_file = MEMORY_DIR / f"{self.user}{META_FILE_SUFFIX}"
        self.session_meta = {}
        self._load_session_meta()
        self.session = "default"
        self.memory_file = get_memory_file(self.user, self.session)
        self.load_memory()
        self.record_session_access(self.session)
        self.log_event("switch_user", {"to": new_user})
        self._plugin_event("on_switch_user", {"to": new_user})

    # -------------------- Extensibility: Plugin/Event Hooks --------------------
    def _plugin_event(self, event_name: str, data: dict):
        if self._plugin_event_cb:
            try:
                self._plugin_event_cb(event_name, data)
            except Exception as e:
                logging.warning(f"[Memory] Plugin event '{event_name}' failed: {e}")

    def for_each_session(self, func: Callable[[str, Dict[str, Any]], None]):
        for s in self.list_sessions():
            func(s["name"], self.memory)

# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr = MemoryManager("gregmish")
    mgr.add_context({"message": "Test context entry"})
    mgr.add_note("python", "Remember to use type hints!")
    mgr.tag_session("default", ["important", "ai"])
    print("Sessions:", mgr.list_sessions(details=True))
    print("Usage stats:", mgr.session_usage_stats())
    print("Recent context:", mgr.get_recent())
    print("Summary:", mgr.summarize_session())
    mgr.auto_suggest_cleanup()
    print("All users:", MemoryManager.list_all_users())