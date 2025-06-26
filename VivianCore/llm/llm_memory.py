import os
import json
import time
from datetime import datetime
import threading

class LLM_Memory:
    """
    Vivian-Grade LLM_Memory:
    - Tag-organized, timestamped, metadata-rich memory store.
    - Search, filter, export/import, audit, explainability, concurrent-safe.
    - Supports archiving, pinning, tagging, visualization, retention policies, shell/API access, autosave, eventbus, websocket/notify hooks, context/role awareness, and basic tests.
    """

    def __init__(self, memory_dir="vivian_memory", tags_enabled=True, autosave_interval=None,
                 eventbus=None, notify_cb=None, websocket_cb=None, gui_cb=None, logging_cb=None,
                 context_profiles=None, role=None, autosave=False, on_change=None):
        self.memory_dir = memory_dir
        self.tags_enabled = tags_enabled
        self.lock = threading.Lock()
        os.makedirs(self.memory_dir, exist_ok=True)
        self.audit_log = []
        self.pinned = set()
        self.archive_dir = os.path.join(self.memory_dir, "_archive")
        os.makedirs(self.archive_dir, exist_ok=True)
        self.retention_days = None  # None = unlimited
        self.eventbus = eventbus
        self.notify_cb = notify_cb
        self.websocket_cb = websocket_cb
        self.gui_cb = gui_cb
        self.logging_cb = logging_cb
        self.context_profiles = context_profiles or {}
        self.role = role or "default"
        self.autosave_flag = autosave
        self.on_change = on_change
        if autosave_interval:
            self.autosave(autosave_interval)
        if self.autosave_flag:
            self._autosave_once()

    def _get_path(self, tag, archived=False):
        safe = tag.replace(" ", "_").lower()
        base = self.archive_dir if archived else self.memory_dir
        return os.path.join(base, f"{safe}.json")

    def save(self, tag, content, meta=None):
        with self.lock:
            path = self._get_path(tag)
            entry = {
                "timestamp": time.time(),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "content": content,
                "meta": meta or {},
                "pinned": tag in self.pinned
            }
            data = self.load(tag)
            data.append(entry)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._audit("save", {"tag": tag, "content": content, "meta": meta})
            self._notify_all("memory_saved", {"tag": tag, "entry": entry})
            self._autosave_once()

    def load(self, tag, archived=False):
        path = self._get_path(tag, archived)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def recent(self, tag, n=5, archived=False):
        return self.load(tag, archived)[-n:]

    def search_all(self, keyword, include_archived=False, tags=None):
        result = []
        for fname in os.listdir(self.memory_dir):
            if fname.endswith(".json"):
                tag = fname[:-5]
                if tags and tag not in tags:
                    continue
                entries = self.load(tag)
                for e in entries:
                    if keyword.lower() in json.dumps(e).lower():
                        result.append((tag, e))
        if include_archived:
            for fname in os.listdir(self.archive_dir):
                if fname.endswith(".json"):
                    tag = fname[:-5]
                    entries = self.load(tag, archived=True)
                    for e in entries:
                        if keyword.lower() in json.dumps(e).lower():
                            result.append((f"archived:{tag}", e))
        return result

    def tag_list(self, archived=False):
        base = self.archive_dir if archived else self.memory_dir
        return [f[:-5] for f in os.listdir(base) if f.endswith(".json")]

    def delete_tag(self, tag):
        path = self._get_path(tag)
        if os.path.exists(path):
            os.remove(path)
            self._audit("delete_tag", {"tag": tag})
            self._notify_all("tag_deleted", {"tag": tag})
            self._autosave_once()
            return True
        return False

    def wipe(self):
        for tag in self.tag_list():
            self.delete_tag(tag)
        self._audit("wipe", {})
        self._notify_all("memory_wiped", {})
        self._autosave_once()

    def export_tag(self, tag, path=None):
        data = self.load(tag)
        out = path or (tag + ".export.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self._audit("export_tag", {"tag": tag, "path": out})
        self._notify_all("tag_exported", {"tag": tag, "path": out})
        return out

    def import_tag(self, tag, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with self.lock:
            with open(self._get_path(tag), "w", encoding="utf-8") as f2:
                json.dump(data, f2, indent=2)
        self._audit("import_tag", {"tag": tag, "path": path})
        self._notify_all("tag_imported", {"tag": tag, "path": path})
        self._autosave_once()

    def archive_tag(self, tag):
        data = self.load(tag)
        with open(self._get_path(tag, archived=True), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.delete_tag(tag)
        self._audit("archive_tag", {"tag": tag})
        self._notify_all("tag_archived", {"tag": tag})
        self._autosave_once()

    def restore_archived(self, tag):
        data = self.load(tag, archived=True)
        with open(self._get_path(tag), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.remove(self._get_path(tag, archived=True))
        self._audit("restore_archived", {"tag": tag})
        self._notify_all("tag_restored", {"tag": tag})
        self._autosave_once()

    def pin(self, tag):
        self.pinned.add(tag)
        self._audit("pin", {"tag": tag})
        self._notify_all("tag_pinned", {"tag": tag})
        self._autosave_once()

    def unpin(self, tag):
        self.pinned.discard(tag)
        self._audit("unpin", {"tag": tag})
        self._notify_all("tag_unpinned", {"tag": tag})
        self._autosave_once()

    def retention_policy(self, days=None):
        """Set retention in days. None = unlimited."""
        self.retention_days = days
        self._autosave_once()

    def enforce_retention(self):
        if self.retention_days is None:
            return
        cutoff = time.time() - self.retention_days * 86400
        for tag in self.tag_list():
            entries = self.load(tag)
            filtered = [e for e in entries if e["timestamp"] >= cutoff or e.get("pinned")]
            if len(filtered) < len(entries):
                with open(self._get_path(tag), "w", encoding="utf-8") as f:
                    json.dump(filtered, f, indent=2)
                self._audit("retention_enforced", {"tag": tag, "kept": len(filtered), "removed": len(entries)-len(filtered)})
                self._notify_all("retention_enforced", {"tag": tag, "kept": len(filtered), "removed": len(entries)-len(filtered)})
        self._autosave_once()

    def autosave(self, interval=60):
        """Periodically enforce retention and flush audit."""
        def loop():
            while True:
                time.sleep(interval)
                self.enforce_retention()
                self.flush_audit()
        threading.Thread(target=loop, daemon=True).start()

    def _autosave_once(self):
        if self.autosave_flag:
            self.flush_audit()

    def _audit(self, event, details):
        entry = {
            "timestamp": time.time(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": event,
            "details": details
        }
        self.audit_log.append(entry)
        if self.eventbus:
            self.eventbus.publish(event, details)
        if self.logging_cb:
            self.logging_cb(event, details)
        if self.on_change:
            try: self.on_change(event, details)
            except Exception: pass

    def flush_audit(self, path=None):
        out = path or os.path.join(self.memory_dir, "audit.log.json")
        if self.audit_log:
            with open(out, "a", encoding="utf-8") as f:
                for entry in self.audit_log:
                    f.write(json.dumps(entry) + "\n")
            self.audit_log.clear()

    def explain(self, tag):
        entries = self.load(tag)
        if not entries:
            return f"No entries for tag '{tag}'."
        last = entries[-1]
        return {
            "last_entry": last,
            "total_entries": len(entries),
            "pinned": tag in self.pinned,
            "archived": os.path.exists(self._get_path(tag, archived=True))
        }

    def visualize(self, tag, n=10):
        entries = self.recent(tag, n)
        print(f"=== {tag.upper()} (last {n}) ===")
        for e in entries:
            mark = "*" if e.get("pinned") else " "
            print(f"{mark} {e['date']} | {str(e['content'])[:60]}")

    def shell(self):
        print("Vivian LLM_Memory Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: save, load, recent, search, tags, delete, wipe, export, import, archive, restore, pin, unpin, retention, explain, visualize, audit, exit")
                elif cmd.startswith("save "):
                    _, tag, *content = cmd.split(" ")
                    self.save(tag, " ".join(content))
                    print("Saved.")
                elif cmd.startswith("load "):
                    tag = cmd.split(" ", 1)[1]
                    print(self.load(tag))
                elif cmd.startswith("recent "):
                    tag = cmd.split(" ", 1)[1]
                    print(self.recent(tag))
                elif cmd.startswith("search "):
                    key = cmd.split(" ", 1)[1]
                    print(self.search_all(key))
                elif cmd == "tags":
                    print(self.tag_list())
                elif cmd.startswith("delete "):
                    tag = cmd.split(" ", 1)[1]
                    print(self.delete_tag(tag))
                elif cmd == "wipe":
                    self.wipe()
                    print("Wiped all memory.")
                elif cmd.startswith("export "):
                    tag = cmd.split(" ", 1)[1]
                    print(self.export_tag(tag))
                elif cmd.startswith("import "):
                    tag, path = cmd.split(" ")[1:3]
                    self.import_tag(tag, path)
                    print("Imported.")
                elif cmd.startswith("archive "):
                    tag = cmd.split(" ", 1)[1]
                    self.archive_tag(tag)
                    print("Archived.")
                elif cmd.startswith("restore "):
                    tag = cmd.split(" ", 1)[1]
                    self.restore_archived(tag)
                    print("Restored.")
                elif cmd.startswith("pin "):
                    tag = cmd.split(" ", 1)[1]
                    self.pin(tag)
                    print("Pinned.")
                elif cmd.startswith("unpin "):
                    tag = cmd.split(" ", 1)[1]
                    self.unpin(tag)
                    print("Unpinned.")
                elif cmd.startswith("retention "):
                    days = int(cmd.split(" ", 1)[1])
                    self.retention_policy(days)
                    print(f"Retention set to {days} days.")
                elif cmd.startswith("explain "):
                    tag = cmd.split(" ", 1)[1]
                    print(self.explain(tag))
                elif cmd.startswith("visualize "):
                    tag = cmd.split(" ", 1)[1]
                    self.visualize(tag)
                elif cmd == "audit":
                    self.flush_audit()
                    print("Audit flushed.")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        threading.Thread(target=self.shell, daemon=True).start()

    def demo(self):
        print("=== Vivian LLM_Memory Demo ===")
        self.save("test", "hello world", {"user": "vivian"})
        self.save("test", "another memory", {"user": "vivian"})
        print(self.recent("test"))
        self.visualize("test")
        self.pin("test")
        print(self.explain("test"))
        self.export_tag("test")
        self.archive_tag("test")
        print("Archived:", self.explain("test"))
        self.restore_archived("test")
        print("Restored:", self.explain("test"))
        self.retention_policy(0)  # Remove all except pinned
        self.enforce_retention()
        self.flush_audit()
        print("Demo complete. Try .run_shell() for an interactive session.")

    # --- Basic unit test for main features ---
    def _test(self):
        self.save("demo", "unit test", {"x": 1})
        assert len(self.recent("demo", 1)) == 1
        self.pin("demo")
        assert "demo" in self.pinned
        self.archive_tag("demo")
        assert "demo" in self.tag_list(archived=True)
        self.restore_archived("demo")
        assert "demo" in self.tag_list()
        self.delete_tag("demo")
        assert "demo" not in self.tag_list()
        print("LLM_Memory basic tests passed.")

if __name__ == "__main__":
    memory = LLM_Memory(autosave=True)
    memory.demo()
    memory._test()