import json
import os
import time
import threading
from typing import List, Dict, Optional, Callable, Any

class MemoryEntry:
    """
    AGI-Grade MemoryEntry:
    - Stores timestamp, content, tags, importance, context, source, and optional semantic vector.
    - Supports explainability and advanced metadata.
    """
    def __init__(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        importance: float = 1.0,
        context: Optional[Dict] = None,
        source: Optional[str] = None,
        vector: Optional[List[float]] = None
    ):
        self.timestamp = time.time()
        self.content = content
        self.tags = tags or []
        self.importance = importance
        self.context = context or {}
        self.source = source
        self.vector = vector  # For semantic/embedding search, if available
        self.audit: List[Dict] = []

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "content": self.content,
            "tags": self.tags,
            "importance": self.importance,
            "context": self.context,
            "source": self.source,
            "vector": self.vector,
            "audit": self.audit,
        }

    @staticmethod
    def from_dict(d: Dict):
        entry = MemoryEntry(
            content=d.get("content", ""),
            tags=d.get("tags", []),
            importance=d.get("importance", 1.0),
            context=d.get("context", {}),
            source=d.get("source"),
            vector=d.get("vector")
        )
        entry.timestamp = d.get("timestamp", time.time())
        entry.audit = d.get("audit", [])
        return entry

    def add_audit(self, event: str, details: Optional[Dict] = None):
        self.audit.append({
            "timestamp": time.time(),
            "event": event,
            "details": details or {}
        })

class MemoryStream:
    """
    AGI-Grade MemoryStream:
    - Persistent, concurrent, extensible memory log.
    - Supports tagging, advanced search, importance, context, sources, semantic search, plugins, and full audit.
    - Includes analytics, simulation, undo, export, and interactive shell.
    """
    def __init__(
        self,
        path: str = "vivian_memory.jsonl",
        autosave: bool = True,
        plugin_hooks: Optional[Dict[str, Callable]] = None
    ):
        self.path = path
        self.entries: List[MemoryEntry] = []
        self.lock = threading.Lock()
        self.autosave = autosave
        self.plugin_hooks = plugin_hooks or {}
        self.load()

    def log(self, content: str, tags: Optional[List[str]] = None, importance: float = 1.0, context: Optional[Dict] = None, source: Optional[str] = None, vector: Optional[List[float]] = None):
        entry = MemoryEntry(content, tags, importance, context, source, vector)
        entry.add_audit("created")
        with self.lock:
            self.entries.append(entry)
            if self.autosave:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict()) + "\n")
        # Call plugins/hook if present (e.g., for notifications, external sync)
        if "on_log" in self.plugin_hooks:
            self.plugin_hooks["on_log"](entry)

    def recent(self, count: int = 10) -> List[Dict]:
        with self.lock:
            return [e.to_dict() for e in self.entries[-count:]]

    def search(self, keyword: str, tags: Optional[List[str]] = None, min_importance: float = 0.0, context_require: Optional[Dict] = None) -> List[Dict]:
        with self.lock:
            res = []
            for e in self.entries:
                if keyword.lower() not in e.content.lower():
                    continue
                if tags and not set(tags).issubset(set(e.tags)):
                    continue
                if e.importance < min_importance:
                    continue
                if context_require:
                    # All required keys/values must be present in entry.context
                    if not all(e.context.get(k) == v for k, v in context_require.items()):
                        continue
                res.append(e.to_dict())
            return res

    def semantic_search(self, vector: List[float], top_k: int = 5, similarity_fn: Optional[Callable[[List[float], List[float]], float]] = None) -> List[Dict]:
        """
        Simple semantic search using cosine similarity (default) or custom function.
        """
        if not similarity_fn:
            similarity_fn = MemoryStream._cosine_similarity
        scored = []
        with self.lock:
            for e in self.entries:
                if e.vector:
                    score = similarity_fn(vector, e.vector)
                    scored.append((score, e))
            scored.sort(reverse=True, key=lambda x: x[0])
            return [e.to_dict() for score, e in scored[:top_k]]

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        import math
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x*y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x*x for x in a))
        norm_b = math.sqrt(sum(y*y for y in b))
        return dot / (norm_a * norm_b + 1e-8)

    def load(self):
        if not os.path.exists(self.path):
            return
        with self.lock:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        entry = MemoryEntry.from_dict(data)
                        self.entries.append(entry)
                    except Exception:
                        continue

    def export(self, path: str, filter_fn: Optional[Callable[[MemoryEntry], bool]] = None):
        with self.lock:
            with open(path, "w", encoding="utf-8") as f:
                for e in self.entries:
                    if not filter_fn or filter_fn(e):
                        f.write(json.dumps(e.to_dict()) + "\n")

    def undo_last(self):
        with self.lock:
            if self.entries:
                entry = self.entries.pop()
                entry.add_audit("undone")
                # Optionally, rewrite file
                if self.autosave:
                    with open(self.path, "w", encoding="utf-8") as f:
                        for e in self.entries:
                            f.write(json.dumps(e.to_dict()) + "\n")
                return entry.to_dict()
        return None

    def analytics(self):
        with self.lock:
            return {
                "total": len(self.entries),
                "by_tag": {tag: sum(1 for e in self.entries if tag in e.tags) for e in set(t for e in self.entries for t in e.tags)},
                "avg_importance": sum(e.importance for e in self.entries) / max(1, len(self.entries)),
                "recent_sources": list({e.source for e in self.entries[-20:] if e.source}),
            }

    def simulate(self, steps: int = 5):
        """
        Simulate future memory growth (stub).
        """
        import random
        for i in range(steps):
            self.log(content=f"Simulated memory entry #{len(self.entries)+1}", tags=["sim"], importance=random.uniform(0.5, 1.5))

    def register_plugin(self, name: str, fn: Callable):
        self.plugin_hooks[name] = fn

    def call_plugin(self, name: str, *args, **kwargs):
        if name in self.plugin_hooks:
            return self.plugin_hooks[name](*args, **kwargs)
        else:
            raise ValueError(f"Plugin '{name}' not found")

    def explain_entry(self, idx: int) -> Dict:
        with self.lock:
            if 0 <= idx < len(self.entries):
                e = self.entries[idx]
                return {
                    "content": e.content,
                    "tags": e.tags,
                    "importance": e.importance,
                    "context": e.context,
                    "source": e.source,
                    "audit": e.audit,
                }
        return {}

    def interactive_shell(self):
        print("MemoryStream Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: log, recent, search, undo, analytics, export, simulate, explain, plugins, call, exit")
                elif cmd.startswith("log "):
                    content = cmd[4:]
                    self.log(content)
                    print("Logged.")
                elif cmd == "recent":
                    for e in self.recent():
                        print(e)
                elif cmd.startswith("search "):
                    kw = cmd.split(" ", 1)[1]
                    for e in self.search(kw):
                        print(e)
                elif cmd == "undo":
                    print(self.undo_last())
                elif cmd == "analytics":
                    print(self.analytics())
                elif cmd.startswith("export "):
                    _, path = cmd.split(" ", 1)
                    self.export(path.strip())
                    print(f"Exported to {path.strip()}")
                elif cmd.startswith("simulate"):
                    self.simulate()
                    print("Simulated.")
                elif cmd.startswith("explain "):
                    idx = int(cmd.split(" ", 1)[1])
                    print(self.explain_entry(idx))
                elif cmd == "plugins":
                    print(f"Plugins: {list(self.plugin_hooks.keys())}")
                elif cmd.startswith("call "):
                    _, name, *args = cmd.split(" ")
                    print(self.call_plugin(name, *args))
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        threading.Thread(target=self.interactive_shell, daemon=True).start()

if __name__ == "__main__":
    mem = MemoryStream()
    mem.log("Vivian system started.", tags=["system", "startup"], importance=2.0)
    mem.simulate(steps=3)
    print("Recent entries:", mem.recent())
    print("Analytics:", mem.analytics())
    mem.run_shell()