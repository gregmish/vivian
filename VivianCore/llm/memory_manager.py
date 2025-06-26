import os
import json
import time
import logging
import threading
from typing import List, Dict, Optional, Any, Callable, Set, Tuple
from collections import defaultdict, Counter

try:
    import networkx as nx
except ImportError:
    nx = None

class SuperMemoryManager:
    """
    Vivian SuperMemoryManager:
    - Hybrid memory: flat, hierarchical, episodic/working/long-term, graph-based, hierarchical (parent/child), multi-modal
    - Tagging, multi-user, multi-session, multi-agent, context, mood, fact-check status, permissioning, privacy, encryption
    - Semantic search, keyword search, embedding, memory chaining, story extraction, clustering, memory abstraction
    - Auto-compression, TTL, summarization, annotation, scoring, fact validation, audit, feedback, event triggers, async hooks
    - Fact validation, self-healing, snapshot/restore, concurrency, real-time hooks, external references, forgetting/redaction
    - Full audit log, event-driven triggers, permissioning, visualization, user/agent subspaces, external data pointers
    - Temporal, spatial, and natural language queries, memory validation, multi-agent shared memory, memory refresh
    """

    def __init__(self, config: Dict):
        self.config = config
        self.memory_dir = config.get("memory_dir", "memory_storage")
        os.makedirs(self.memory_dir, exist_ok=True)
        self.memory_file = os.path.join(self.memory_dir, "vivian_supermemory.jsonl")
        self.snapshot_dir = os.path.join(self.memory_dir, "snapshots")
        os.makedirs(self.snapshot_dir, exist_ok=True)
        self.memory: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.embedding_fn = config.get("embedding_fn")
        self.max_memory = config.get("max_memory", 10000)
        self.ttl_seconds = config.get("ttl_seconds")
        self.encryption_fn = config.get("encryption_fn")
        self.decryption_fn = config.get("decryption_fn")
        self.async_hooks: List[Callable[[Dict[str, Any]], None]] = []
        self.event_hooks: Dict[str, List[Callable[[Dict[str, Any]], None]]] = defaultdict(list)
        self.session_id = config.get("session_id")
        self.agent_id = config.get("agent_id")
        self.graph_enabled = bool(nx)
        self.graph = nx.MultiDiGraph() if nx else None
        self.audit_log: List[Dict[str, Any]] = []
        self.memory_hierarchy: Dict[str, List[str]] = defaultdict(list)  # parent_id: [child_id]
        self.memory_index: Dict[str, Dict[str, Any]] = {}  # id: memory
        self.load_memory()
        self._expire_old()

    # --- Core Storage ---
    def store(self, content: str, *,
              tags: Optional[List[str]] = None,
              user: Optional[str] = None,
              context: Optional[Dict] = None,
              embedding: Optional[List[float]] = None,
              score: Optional[float] = None,
              annotations: Optional[Dict[str, Any]] = None,
              session_id: Optional[str] = None,
              agent_id: Optional[str] = None,
              privacy: str = "normal",
              mood: Optional[str] = None,
              media: Optional[Dict[str, Any]] = None,
              external_refs: Optional[List[str]] = None,
              fact_status: Optional[str] = None,
              location: Optional[str] = None,
              expires: Optional[float] = None,
              parent_id: Optional[str] = None,
              permissions: Optional[Dict[str, Any]] = None,
              abstraction_level: Optional[str] = None,
              auto_cluster: bool = False
              ) -> str:
        ts = self._now()
        session_id = session_id or self.session_id
        agent_id = agent_id or self.agent_id
        idstr = f"{session_id or ''}_{agent_id or ''}_{ts}_{hash(content) % 1_000_000_000}"
        item = {
            "content": content,
            "tags": tags or [],
            "user": user,
            "context": context or {},
            "timestamp": ts,
            "session_id": session_id,
            "agent_id": agent_id,
            "score": score,
            "annotations": annotations or {},
            "privacy": privacy,
            "mood": mood,
            "media": media,
            "external_refs": external_refs or [],
            "fact_status": fact_status,
            "location": location,
            "expires": expires,
            "id": idstr,
            "parent_id": parent_id,
            "permissions": permissions or {},
            "abstraction_level": abstraction_level,
        }
        if embedding is None and self.embedding_fn:
            try:
                item["embedding"] = self.embedding_fn(content)
            except Exception as e:
                logging.warning(f"[SuperMemory] Embedding failed: {e}")
        elif embedding is not None:
            item["embedding"] = embedding

        if self.encryption_fn:
            item = self.encryption_fn(item)
        with self.lock:
            self.memory.append(item)
            self.memory_index[item["id"]] = item
            with open(self.memory_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(item) + "\n")
            if len(self.memory) > self.max_memory:
                self._compress_or_prune()
            self._add_to_graph(item)
            self._add_to_hierarchy(item)
            self._log_audit("store", item)
        self._notify_hooks(item)
        self._trigger_event("memory_stored", item)
        if auto_cluster:
            self.auto_cluster_memories()
        return item["id"]

    def load_memory(self):
        self.memory.clear()
        self.memory_index.clear()
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        item = json.loads(line.strip())
                        if self.decryption_fn:
                            item = self.decryption_fn(item)
                        self.memory.append(item)
                        self.memory_index[item["id"]] = item
                    except Exception:
                        logging.warning("[SuperMemory] Skipped corrupt or undecryptable memory line.")
        if self.graph_enabled:
            self._rebuild_graph()
        self._rebuild_hierarchy()

    def _compress_or_prune(self):
        # Summarize/cluster and compress, then prune oldest if still too large
        prune_count = len(self.memory) - self.max_memory
        if prune_count > 0:
            # TODO: Use clustering/LLM to summarize/compress before pruning
            self.memory = self.memory[prune_count:]
            self.memory_index = {m["id"]: m for m in self.memory}
            with open(self.memory_file, "w", encoding="utf-8") as f:
                for item in self.memory:
                    f.write(json.dumps(item) + "\n")
            logging.info(f"[SuperMemory] Pruned {prune_count} oldest memories.")

    def _expire_old(self):
        if not self.ttl_seconds:
            return
        now = time.time()
        cutoff = now - self.ttl_seconds
        before = len(self.memory)
        self.memory = [m for m in self.memory if self._to_epoch(m["timestamp"]) >= cutoff]
        self.memory_index = {m["id"]: m for m in self.memory}
        after = len(self.memory)
        if after < before:
            logging.info(f"[SuperMemory] Expired {before - after} old memories (TTL).")

    def clear(self):
        open(self.memory_file, "w").close()
        self.memory.clear()
        self.memory_index.clear()
        if self.graph_enabled:
            self.graph.clear()
        self.memory_hierarchy.clear()
        logging.info("[SuperMemory] Memory cleared.")

    # --- Memory Querying and Filtering ---
    def search(self, keyword: str, top_k: int = 5, **filters) -> List[Dict[str, Any]]:
        results = []
        for m in self.memory:
            if keyword.lower() in m.get("content", "").lower():
                if not self._filter_match(m, **filters):
                    continue
                results.append(m)
        return sorted(results, key=lambda m: m["timestamp"])[-top_k:]

    def semantic_search(self, query: str, top_k: int = 5, **filters) -> List[Dict[str, Any]]:
        if not self.embedding_fn:
            logging.warning("[SuperMemory] Semantic search unavailable (no embedding_fn).")
            return []
        try:
            q_emb = self.embedding_fn(query)
            scored = []
            for m in self.memory:
                emb = m.get("embedding")
                if emb and self._filter_match(m, **filters):
                    score = self._cosine_similarity(q_emb, emb)
                    scored.append((score, m))
            scored.sort(reverse=True, key=lambda x: x[0])
            return [m for _, m in scored[:top_k]]
        except Exception as e:
            logging.error(f"[SuperMemory] Semantic search failure: {e}")
            return []

    def nlp_query(self, nl_query: str, top_k: int = 5, **filters) -> List[Dict[str, Any]]:
        """
        Natural language query interface stub.
        A real implementation would use an LLM to parse and run structured queries.
        """
        # For now, use keyword search as fallback
        return self.search(nl_query, top_k, **filters)

    def filter(self, **criteria) -> List[Dict[str, Any]]:
        return [m for m in self.memory if self._filter_match(m, **criteria)]

    def timeline(self, user: Optional[str] = None, as_strings=True) -> List[Any]:
        items = [m for m in self.memory if not user or m.get("user") == user]
        if as_strings:
            return [f"{m['timestamp']} - {m['content']}" for m in items]
        return items

    def story_chains(self, keyword: Optional[str] = None, top_k: int = 5) -> List[List[Dict[str, Any]]]:
        """
        Extracts "chains" of related memories (story arcs). Graph-based if available.
        """
        if not self.graph_enabled or not self.graph or self.graph.number_of_nodes() == 0:
            return []
        chains = []
        nodes = [n for n, data in self.graph.nodes(data=True)
                 if (not keyword or keyword in data.get("content", ""))]
        for n in nodes[:top_k]:
            chain = [self.graph.nodes[n]]
            for succ in self.graph.successors(n):
                chain.append(self.graph.nodes[succ])
            chains.append(chain)
        return chains

    def get_graph(self):
        return self.graph if self.graph_enabled else None

    # --- Graph Memory ---
    def _add_to_graph(self, item: Dict[str, Any]):
        if not self.graph_enabled or not self.graph:
            return
        node_id = item["id"]
        self.graph.add_node(node_id, **item)
        # Sequence edge (session order)
        session_items = [m for m in self.memory if m.get("session_id") == item.get("session_id")]
        if len(session_items) > 1:
            prev = session_items[-2]
            self.graph.add_edge(prev["id"], node_id, type="sequence")
        # Tag and user edges
        for tag in item.get("tags", []):
            tag_node = f"tag::{tag}"
            self.graph.add_node(tag_node, type="tag", tag=tag)
            self.graph.add_edge(node_id, tag_node, type="tagged")
        if item.get("user"):
            u_node = f"user::{item['user']}"
            self.graph.add_node(u_node, type="user", user=item["user"])
            self.graph.add_edge(node_id, u_node, type="user")
        for ref in item.get("external_refs", []):
            ref_node = f"ref::{ref}"
            self.graph.add_node(ref_node, type="reference", ref=ref)
            self.graph.add_edge(node_id, ref_node, type="ref")
        # Parent/child
        if item.get("parent_id"):
            self.graph.add_edge(item["parent_id"], node_id, type="hierarchy")

    def _rebuild_graph(self):
        if not self.graph_enabled or not self.graph:
            return
        self.graph.clear()
        for m in self.memory:
            self._add_to_graph(m)

    # --- Hierarchical Memory ---
    def _add_to_hierarchy(self, item: Dict[str, Any]):
        parent_id = item.get("parent_id")
        if parent_id:
            self.memory_hierarchy[parent_id].append(item["id"])

    def _rebuild_hierarchy(self):
        self.memory_hierarchy.clear()
        for m in self.memory:
            self._add_to_hierarchy(m)

    def get_children(self, memory_id: str) -> List[Dict[str, Any]]:
        return [self.memory_index[cid] for cid in self.memory_hierarchy.get(memory_id, []) if cid in self.memory_index]

    def get_parent(self, memory_id: str) -> Optional[Dict[str, Any]]:
        item = self.memory_index.get(memory_id)
        if item and item.get("parent_id"):
            return self.memory_index.get(item["parent_id"])
        return None

    # --- Memory Validation & Fact Checking ---
    def validate_memory(self, memory_id: str, validator_fn: Callable[[Dict[str, Any]], bool], update_status=True) -> bool:
        m = self.memory_index.get(memory_id)
        if m:
            result = validator_fn(m)
            if update_status:
                m["fact_status"] = "verified" if result else "suspect"
            return result
        return False

    def auto_validate_all(self, validator_fn: Callable[[Dict[str, Any]], bool]):
        for m in self.memory:
            self.validate_memory(m["id"], validator_fn, update_status=True)

    def refresh_embeddings(self):
        if not self.embedding_fn:
            return
        for m in self.memory:
            try:
                m["embedding"] = self.embedding_fn(m["content"])
            except Exception:
                continue

    # --- Feedback, Annotation, Clustering, Analytics, Visualization ---
    def annotate(self, memory_id: str, annotation: Dict[str, Any]):
        m = self.memory_index.get(memory_id)
        if m:
            m["annotations"].update(annotation)
            self._log_audit("annotate", m)

    def accept_feedback(self, memory_id: str, feedback: str, score: Optional[float]=None):
        m = self.memory_index.get(memory_id)
        if m:
            m.setdefault("feedback", []).append({
                "feedback": feedback,
                "score": score,
                "timestamp": self._now()
            })
            self._log_audit("feedback", m)

    def stats(self) -> Dict[str, Any]:
        tag_set = {tag for m in self.memory for tag in m.get("tags", [])}
        users = {m.get("user") for m in self.memory if m.get("user")}
        sessions = {m.get("session_id") for m in self.memory if m.get("session_id")}
        agents = {m.get("agent_id") for m in self.memory if m.get("agent_id")}
        return {
            "count": len(self.memory),
            "users": list(users),
            "tags": list(tag_set),
            "sessions": list(sessions),
            "agents": list(agents),
            "moods": list({m.get("mood") for m in self.memory if m.get("mood")}),
            "locations": list({m.get("location") for m in self.memory if m.get("location")}),
            "audit_count": len(self.audit_log)
        }

    def summarize(self, top_k: int = 10) -> str:
        items = self.memory[-top_k:]
        summary = "\n".join(f"{m['timestamp']}: {m['content'][:60]}" for m in items)
        return summary

    def visualize(self, mode: str = "timeline") -> str:
        if mode == "timeline":
            return "\n".join(self.timeline())
        elif mode == "tags":
            tag_counter = Counter(tag for m in self.memory for tag in m.get("tags", []))
            return "\n".join(f"{tag}: {count}" for tag, count in tag_counter.most_common())
        elif mode == "graph" and self.graph_enabled:
            return f"Graph nodes: {self.graph.number_of_nodes()}, edges: {self.graph.number_of_edges()}"
        elif mode == "hierarchy":
            output = []
            for parent, children in self.memory_hierarchy.items():
                output.append(f"{parent} -> {children}")
            return "\n".join(output)
        return "Unknown visualization mode."

    def auto_cluster_memories(self):
        # Placeholder: In real system, use embeddings/LLM to cluster memories and set abstraction_level
        pass

    # --- Privacy, Permissions, Audit, Forgetting ---
    def forget(self, memory_id: str):
        self.memory = [m for m in self.memory if m["id"] != memory_id]
        self.memory_index.pop(memory_id, None)
        self._rewrite_memory_file()
        self._log_audit("forget", {"id": memory_id})

    def redact(self, memory_id: str, mask: str = "[REDACTED]"):
        m = self.memory_index.get(memory_id)
        if m:
            m["content"] = mask
            self._log_audit("redact", m)
        self._rewrite_memory_file()

    def _log_audit(self, action: str, item: Dict[str, Any]):
        self.audit_log.append({
            "action": action,
            "item_id": item.get("id"),
            "timestamp": self._now(),
            "user": item.get("user"),
            "session": item.get("session_id"),
        })

    def get_audit_log(self, last_n: int = 20) -> List[Dict[str, Any]]:
        return self.audit_log[-last_n:]

    # --- Self-Healing, Snapshot, Restore, Async/Events ---
    def heal_memory(self):
        healthy = []
        fixed = 0
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        item = json.loads(line.strip())
                        if self.decryption_fn:
                            item = self.decryption_fn(item)
                        healthy.append(item)
                    except Exception:
                        fixed += 1
        with open(self.memory_file, "w", encoding="utf-8") as f:
            for item in healthy:
                f.write(json.dumps(item) + "\n")
        self.memory = healthy
        self.memory_index = {m["id"]: m for m in self.memory}
        self._rebuild_graph()
        self._rebuild_hierarchy()
        if fixed > 0:
            logging.info(f"[SuperMemory] Self-healed, removed {fixed} corrupt memories.")
        self._log_audit("heal", {"fixed": fixed})

    def snapshot(self, label: Optional[str] = None) -> str:
        ts = int(time.time())
        path = os.path.join(self.snapshot_dir, f"snapshot_{label or ts}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for m in self.memory:
                f.write(json.dumps(m) + "\n")
        logging.info(f"[SuperMemory] Snapshot saved: {path}")
        self._log_audit("snapshot", {"path": path})
        return path

    def restore(self, path: str):
        if not os.path.exists(path):
            logging.error(f"[SuperMemory] Snapshot not found: {path}")
            return
        with open(path, "r", encoding="utf-8") as f:
            self.memory = [json.loads(line.strip()) for line in f]
        self.memory_index = {m["id"]: m for m in self.memory}
        self._rewrite_memory_file()
        self._rebuild_graph()
        self._rebuild_hierarchy()
        logging.info(f"[SuperMemory] Memory restored from snapshot: {path}")
        self._log_audit("restore", {"path": path})

    def register_async_hook(self, hook: Callable[[Dict[str, Any]], None]):
        self.async_hooks.append(hook)

    def _notify_hooks(self, item: Dict[str, Any]):
        for hook in self.async_hooks:
            try:
                threading.Thread(target=hook, args=(item,), daemon=True).start()
            except Exception as e:
                logging.warning(f"[SuperMemory] Async hook failure: {e}")

    def register_event_hook(self, event: str, hook: Callable[[Dict[str, Any]], None]):
        self.event_hooks[event].append(hook)

    def _trigger_event(self, event: str, item: Dict[str, Any]):
        for hook in self.event_hooks.get(event, []):
            try:
                threading.Thread(target=hook, args=(item,), daemon=True).start()
            except Exception as e:
                logging.warning(f"[SuperMemory] Event hook '{event}' failure: {e}")

    # --- Utility ---
    def _filter_match(self, m: Dict[str, Any], **filters) -> bool:
        for k, v in filters.items():
            if v is None:
                continue
            if k == "tags" and v:
                if not any(tag in m.get("tags", []) for tag in v):
                    return False
            elif k == "user" and m.get("user") != v:
                return False
            elif k == "session_id" and m.get("session_id") != v:
                return False
            elif k == "agent_id" and m.get("agent_id") != v:
                return False
            elif k == "privacy" and m.get("privacy") != v:
                return False
            elif k == "fact_status" and m.get("fact_status") != v:
                return False
            elif k == "location" and m.get("location") != v:
                return False
            elif k == "mood" and m.get("mood") != v:
                return False
            elif k == "after" and m.get("timestamp") < v:
                return False
            elif k == "before" and m.get("timestamp") > v:
                return False
            elif k == "min_score" and (m.get("score") or 0) < v:
                return False
            elif k == "permissions" and v:
                # For permission check, 'v' should be a callable or comparison dict
                perms = m.get("permissions") or {}
                if callable(v):
                    if not v(perms):
                        return False
                elif isinstance(v, dict):
                    for permk, permv in v.items():
                        if perms.get(permk) != permv:
                            return False
        return True

    def _rewrite_memory_file(self):
        with open(self.memory_file, "w", encoding="utf-8") as f:
            for item in self.memory:
                f.write(json.dumps(item) + "\n")

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        import math
        dot = sum(a*b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a*a for a in v1))
        norm2 = math.sqrt(sum(a*a for a in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def _now(self):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    def _to_epoch(self, timestr: str) -> float:
        try:
            return time.mktime(time.strptime(timestr, "%Y-%m-%d %H:%M:%S"))
        except Exception:
            return 0.0