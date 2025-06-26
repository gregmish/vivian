import time
import uuid
import json
import threading
from typing import List, Dict, Optional, Callable, Any

class MemoryNode:
    """
    AGI-Grade MemoryNode:
    - Stores ID, timestamp, content, context, tags, links, importance, source, vector, and audit history.
    - Supports explainability, audit, undo, advanced metadata, and temporal/association semantics.
    """
    def __init__(
        self,
        content: str,
        context: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
        importance: float = 1.0,
        source: Optional[str] = None,
        vector: Optional[List[float]] = None,
        expiry: Optional[float] = None,
    ):
        self.id = str(uuid.uuid4())
        self.timestamp = time.time()
        self.content = content
        self.context = context or {}
        self.tags = tags or []
        self.links: List[str] = []
        self.importance = importance
        self.source = source
        self.vector = vector
        self.expiry = expiry  # When to "forget" this node (optional)
        self.audit: List[Dict] = []

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "content": self.content,
            "context": self.context,
            "tags": self.tags,
            "links": self.links,
            "importance": self.importance,
            "source": self.source,
            "vector": self.vector,
            "expiry": self.expiry,
            "audit": self.audit
        }

    @staticmethod
    def from_dict(d: Dict):
        node = MemoryNode(
            content=d.get("content", ""),
            context=d.get("context", {}),
            tags=d.get("tags", []),
            importance=d.get("importance", 1.0),
            source=d.get("source"),
            vector=d.get("vector"),
            expiry=d.get("expiry")
        )
        node.id = d.get("id", str(uuid.uuid4()))
        node.timestamp = d.get("timestamp", time.time())
        node.links = d.get("links", [])
        node.audit = d.get("audit", [])
        return node

    def add_audit(self, event: str, details: Optional[Dict] = None):
        self.audit.append({
            "timestamp": time.time(),
            "event": event,
            "details": details or {}
        })

class MemoryGraph:
    """
    AGI-Grade MemoryGraph:
    - Persistent, concurrent, extensible memory graph.
    - Supports rich nodes, advanced search, semantic search, analytics, undo, simulation, plugin hooks, audit, decay/expiry, association, and REPL.
    """
    def __init__(
        self,
        path: str = "vivian_graph.json",
        autosave: bool = True,
        plugin_hooks: Optional[Dict[str, Callable]] = None
    ):
        self.path = path
        self.nodes: Dict[str, MemoryNode] = {}
        self.history: List[str] = []
        self.lock = threading.Lock()
        self.autosave = autosave
        self.plugin_hooks = plugin_hooks or {}
        self.audit_log: List[Dict] = []
        self.load()

    def add_memory(self, content: str, context: Optional[Dict] = None, tags: Optional[List[str]] = None,
                   importance: float = 1.0, source: Optional[str] = None, vector: Optional[List[float]] = None,
                   expiry: Optional[float] = None) -> str:
        node = MemoryNode(content, context, tags, importance, source, vector, expiry)
        node.add_audit("created")
        with self.lock:
            self.nodes[node.id] = node
            self.history.append(node.id)
            if len(self.history) > 1:
                last_id = self.history[-2]
                self.nodes[last_id].links.append(node.id)
                node.add_audit("auto_linked", {"from": last_id})
            if self.autosave:
                self.save()
        if "on_add" in self.plugin_hooks:
            self.plugin_hooks["on_add"](node)
        self.audit_log.append({"event": "add_memory", "id": node.id, "timestamp": node.timestamp})
        return node.id

    def get_memory(self, node_id: str) -> Optional[MemoryNode]:
        with self.lock:
            return self.nodes.get(node_id)

    def search(self, keyword: str, tags: Optional[List[str]] = None, min_importance: float = 0.0, context_require: Optional[Dict] = None) -> List[Dict]:
        with self.lock:
            res = []
            for n in self.nodes.values():
                if keyword.lower() not in n.content.lower():
                    continue
                if tags and not set(tags).issubset(set(n.tags)):
                    continue
                if n.importance < min_importance:
                    continue
                if context_require:
                    if not all(n.context.get(k) == v for k, v in context_require.items()):
                        continue
                res.append(n.to_dict())
            return res

    def semantic_search(self, vector: List[float], top_k: int = 5, similarity_fn: Optional[Callable[[List[float], List[float]], float]] = None) -> List[Dict]:
        if not similarity_fn:
            similarity_fn = MemoryGraph._cosine_similarity
        scored = []
        with self.lock:
            for n in self.nodes.values():
                if n.vector:
                    score = similarity_fn(vector, n.vector)
                    scored.append((score, n))
            scored.sort(reverse=True, key=lambda x: x[0])
            return [n.to_dict() for score, n in scored[:top_k]]

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        import math
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x*y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x*x for x in a))
        norm_b = math.sqrt(sum(y*y for y in b))
        return dot / (norm_a * norm_b + 1e-8)

    def last_n(self, count: int = 5) -> List[Dict]:
        with self.lock:
            return [self.nodes[nid].to_dict() for nid in self.history[-count:]]

    def link_nodes(self, from_id: str, to_id: str):
        with self.lock:
            if from_id in self.nodes and to_id in self.nodes:
                self.nodes[from_id].links.append(to_id)
                self.nodes[from_id].add_audit("link", {"to": to_id})
                self.audit_log.append({"event": "link_nodes", "from": from_id, "to": to_id, "timestamp": time.time()})

    def unlink_nodes(self, from_id: str, to_id: str):
        with self.lock:
            if from_id in self.nodes and to_id in self.nodes and to_id in self.nodes[from_id].links:
                self.nodes[from_id].links.remove(to_id)
                self.nodes[from_id].add_audit("unlink", {"to": to_id})
                self.audit_log.append({"event": "unlink_nodes", "from": from_id, "to": to_id, "timestamp": time.time()})

    def decay(self):
        """Remove expired/obsolete nodes based on expiry timestamp."""
        now = time.time()
        to_delete = []
        with self.lock:
            for node in self.nodes.values():
                if node.expiry and now > node.expiry:
                    to_delete.append(node.id)
            for nid in to_delete:
                self.nodes[nid].add_audit("expired")
                self.audit_log.append({"event": "expired", "id": nid, "timestamp": now})
                del self.nodes[nid]
                if nid in self.history:
                    self.history.remove(nid)
            if to_delete and self.autosave:
                self.save()

    def associative_search(self, start_id: str, depth: int = 2) -> List[Dict]:
        """Traverse graph links out to given depth, collecting nodes."""
        visited = set()
        results = []

        def dfs(nid, d):
            if nid not in self.nodes or nid in visited or d < 0:
                return
            visited.add(nid)
            results.append(self.nodes[nid].to_dict())
            for linked in self.nodes[nid].links:
                dfs(linked, d - 1)

        dfs(start_id, depth)
        return results

    def export(self) -> Dict:
        with self.lock:
            return {
                "nodes": [n.to_dict() for n in self.nodes.values()],
                "history": self.history
            }

    def save(self):
        with self.lock:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.export(), f, indent=2)

    def load(self):
        if not self.path or not threading.current_thread() == threading.main_thread():
            return
        if not hasattr(self, "nodes"):
            self.nodes = {}
        if not hasattr(self, "history"):
            self.history = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.nodes = {n["id"]: MemoryNode.from_dict(n) for n in data.get("nodes", [])}
                self.history = data.get("history", [])
        except Exception:
            pass

    def import_graph(self, data: Dict):
        with self.lock:
            self.nodes = {n["id"]: MemoryNode.from_dict(n) for n in data.get("nodes", [])}
            self.history = data.get("history", [])
            self.save()

    def undo_last(self):
        with self.lock:
            if self.history:
                last_id = self.history.pop()
                node = self.nodes.pop(last_id)
                node.add_audit("undone")
                self.audit_log.append({"event": "undo_last", "id": last_id, "timestamp": time.time()})
                self.save()
                return node.to_dict()
        return None

    def analytics(self):
        with self.lock:
            return {
                "total_nodes": len(self.nodes),
                "avg_importance": sum(n.importance for n in self.nodes.values()) / max(1, len(self.nodes)),
                "tags": list({t for n in self.nodes.values() for t in n.tags}),
                "by_tag": {tag: sum(1 for n in self.nodes.values() if tag in n.tags) for tag in set(t for n in self.nodes.values() for t in n.tags)},
                "recent_sources": list({n.source for n in list(self.nodes.values())[-20:] if n.source}),
            }

    def simulate(self, steps: int = 5):
        import random
        for i in range(steps):
            self.add_memory(
                content=f"Simulated memory node #{len(self.nodes)+1}",
                tags=["sim"],
                importance=random.uniform(0.5, 1.5)
            )

    def plugin_register(self, name: str, fn: Callable):
        self.plugin_hooks[name] = fn

    def plugin_call(self, name: str, *args, **kwargs):
        if name in self.plugin_hooks:
            return self.plugin_hooks[name](*args, **kwargs)
        else:
            raise ValueError(f"Plugin '{name}' not found")

    def explain_node(self, node_id: str) -> Dict:
        node = self.get_memory(node_id)
        if node:
            return {
                "id": node.id,
                "content": node.content,
                "tags": node.tags,
                "importance": node.importance,
                "context": node.context,
                "source": node.source,
                "links": node.links,
                "expiry": node.expiry,
                "audit": node.audit,
            }
        return {}

    def audit_export(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def interactive_shell(self):
        print("MemoryGraph Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: add, get, search, last, link, unlink, decay, assoc, export, import, undo, analytics, simulate, explain, audit, plugins, call, exit")
                elif cmd.startswith("add "):
                    content = cmd[4:]
                    node_id = self.add_memory(content)
                    print(f"Added node: {node_id}")
                elif cmd.startswith("get "):
                    node_id = cmd[4:]
                    print(self.get_memory(node_id).to_dict() if self.get_memory(node_id) else "Not found")
                elif cmd.startswith("search "):
                    kw = cmd.split(" ", 1)[1]
                    print(self.search(kw))
                elif cmd.startswith("last"):
                    print(self.last_n())
                elif cmd.startswith("link "):
                    _, from_id, to_id = cmd.split(" ")
                    self.link_nodes(from_id, to_id)
                    print(f"Linked {from_id} -> {to_id}")
                elif cmd.startswith("unlink "):
                    _, from_id, to_id = cmd.split(" ")
                    self.unlink_nodes(from_id, to_id)
                    print(f"Unlinked {from_id} -/> {to_id}")
                elif cmd == "decay":
                    self.decay()
                    print("Expired/obsolete nodes removed.")
                elif cmd.startswith("assoc "):
                    _, node_id, *rest = cmd.split(" ")
                    depth = int(rest[0]) if rest else 2
                    print(self.associative_search(node_id, depth))
                elif cmd == "export":
                    print(self.export())
                elif cmd.startswith("import "):
                    path = cmd[7:]
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.import_graph(data)
                    print("Imported graph.")
                elif cmd == "undo":
                    print(self.undo_last())
                elif cmd == "analytics":
                    print(self.analytics())
                elif cmd.startswith("simulate"):
                    self.simulate()
                    print("Simulated.")
                elif cmd.startswith("explain "):
                    node_id = cmd.split(" ", 1)[1]
                    print(self.explain_node(node_id))
                elif cmd == "audit":
                    self.audit_export("vivian_graph_audit.json")
                    print("Audit exported to vivian_graph_audit.json")
                elif cmd == "plugins":
                    print(f"Plugins: {list(self.plugin_hooks.keys())}")
                elif cmd.startswith("call "):
                    _, name, *args = cmd.split(" ")
                    print(self.plugin_call(name, *args))
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        threading.Thread(target=self.interactive_shell, daemon=True).start()

    def demo(self):
        print("=== MemoryGraph AGI Demo ===")
        id1 = self.add_memory("The sun is shining.", tags=["weather", "observation"], importance=1.3, source="sensor")
        id2 = self.add_memory("It is warm outside.", tags=["weather"], importance=1.0, source="user")
        id3 = self.add_memory("A cold front is coming.", tags=["forecast"], importance=1.2, source="api", expiry=time.time() + 2)
        self.link_nodes(id1, id3)
        print("Last 2 nodes:", self.last_n(2))
        print("Search 'warm':", self.search("warm"))
        print("Analytics:", self.analytics())
        print("Associative search from id1 to depth 2:", self.associative_search(id1, 2))
        print("Explain node:", self.explain_node(id1))
        self.simulate()
        self.decay()
        self.audit_export("vivian_graph_audit.json")
        print("Demo complete. You can also start the interactive shell with .run_shell()")

if __name__ == "__main__":
    graph = MemoryGraph()
    graph.demo()