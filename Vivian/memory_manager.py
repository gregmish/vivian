import os
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set, Callable, Union
from threading import RLock

# Optional: for real encryption
try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None

# Optional: for semantic search
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
except ImportError:
    chromadb = None
    SentenceTransformer = None

class MemoryEntry:
    """
    A single memory item for Vivian, including:
    - content, metadata, timestamp, parent/child (hierarchy), embedding, score, versioning, edit history.
    """
    def __init__(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
        entry_id: Optional[str] = None,
        parent: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        score: Optional[float] = None,
        version: int = 1,
        history: Optional[List[Dict[str, Any]]] = None,
    ):
        self.content = content
        self.meta = metadata or {}
        self.timestamp = timestamp or time.time()
        self.id = entry_id or self._make_id()
        self.parent = parent
        self.embedding = embedding
        self.score = score
        self.version = version
        self.history = history or []

    def _make_id(self):
        import hashlib
        hash_base = f"{self.content}|{self.timestamp}|{json.dumps(self.meta, sort_keys=True)}"
        return hashlib.sha256(hash_base.encode("utf-8")).hexdigest()

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "content": self.content,
            "meta": self.meta,
            "parent": self.parent,
            "embedding": self.embedding,
            "score": self.score,
            "version": self.version,
            "history": self.history,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]):
        return MemoryEntry(
            content=d.get("content", ""),
            metadata=d.get("meta", {}),
            timestamp=d.get("timestamp"),
            entry_id=d.get("id"),
            parent=d.get("parent"),
            embedding=d.get("embedding"),
            score=d.get("score"),
            version=d.get("version", 1),
            history=d.get("history", []),
        )

class StorageBackend:
    """
    Pluggable storage API: file (jsonl), SQLite, Mongo, S3, etc.
    Only JSONL file implemented here, but interface is ready.
    """
    def __init__(self, config: Dict[str, Any]):
        self.memory_file = os.path.join(config.get("memory_dir", "memory"), "memories.jsonl")
        self.encryption_enabled = config.get("security", {}).get("encrypt_memory", False)
        self.lock = RLock()
        self.fernet = None
        if self.encryption_enabled and Fernet:
            key = config.get("security", {}).get("memory_key")
            if not key:
                key = Fernet.generate_key()
            self.fernet = Fernet(key)
        # Future: switch based on config["backend"] (sqlite, mongo, s3, etc.)

    def load_all(self) -> List[Dict[str, Any]]:
        with self.lock:
            if not os.path.exists(self.memory_file):
                return []
            try:
                with open(self.memory_file, "rb") as f:
                    raw = f.read()
                    if self.encryption_enabled and self.fernet:
                        raw = self.fernet.decrypt(raw)
                    text = raw.decode("utf-8")
                    return [json.loads(line.strip()) for line in text.splitlines() if line.strip()]
            except Exception as e:
                logging.error(f"[Memory][Storage] Failed to load: {e}")
                return []

    def append(self, entry: Dict[str, Any]):
        with self.lock:
            try:
                out = json.dumps(entry) + "\n"
                data = out.encode("utf-8")
                if self.encryption_enabled and self.fernet:
                    data = self.fernet.encrypt(data)
                with open(self.memory_file, "ab") as f:
                    f.write(data)
            except Exception as e:
                logging.error(f"[Memory][Storage] Failed to append: {e}")

    def overwrite(self, entries: List[Dict[str, Any]]):
        with self.lock:
            try:
                lines = [json.dumps(e) + "\n" for e in entries]
                data = "".join(lines).encode("utf-8")
                if self.encryption_enabled and self.fernet:
                    data = self.fernet.encrypt(data)
                with open(self.memory_file, "wb") as f:
                    f.write(data)
            except Exception as e:
                logging.error(f"[Memory][Storage] Failed to overwrite: {e}")

class MemoryManager:
    """
    Vivian's ultra-advanced, extensible, compliant, and distributed-ready memory manager.
    """
    def __init__(
        self,
        config: Dict[str, Any],
        event_bus=None,
        user_manager=None,
        plugin_hooks: Optional[Dict[str, Callable]] = None,
    ):
        self.config = config
        self.memory_dir = config.get("memory_dir", "memory")
        self.enabled = config.get("long_term_memory_enabled", True)
        self.backend = StorageBackend(config)
        self.index: Dict[str, MemoryEntry] = {}
        self.event_bus = event_bus
        self.user_manager = user_manager
        self.expiry_days = config.get("memory_expiry_days", None)
        self.backup_dir = os.path.join(self.memory_dir, "backups")
        self.memory_quota = config.get("memory_quota", None)
        self.plugin_hooks = plugin_hooks or {}
        self.lock = RLock()
        self._init_semantic(config)
        os.makedirs(self.memory_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        self.load_memory()

    def _init_semantic(self, config):
        self.semantic_enabled = config.get("semantic_memory_enabled", False)
        self.semantic_db = None
        self.embedder = None
        if self.semantic_enabled and chromadb and SentenceTransformer:
            self.semantic_db = chromadb.Client().create_collection("vivian_memories")
            model_name = config.get("semantic_model", "all-MiniLM-L6-v2")
            self.embedder = SentenceTransformer(model_name)
        else:
            self.semantic_enabled = False

    # --- Core CRUD ---

    def load_memory(self):
        if not self.enabled:
            return
        self.index.clear()
        entries = self.backend.load_all()
        for entry in entries:
            try:
                me = MemoryEntry.from_dict(entry)
                self.index[me.id] = me
                # If embedding missing and semantic enabled: add
                if self.semantic_enabled and me.embedding is None:
                    self._add_embedding(me)
            except Exception as e:
                continue

    def save_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        author: Optional[str] = None,
        parent: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        score: Optional[float] = None,
    ):
        if not self.enabled:
            return None
        entry_meta = metadata.copy() if metadata else {}
        if author:
            entry_meta["author"] = author
        self._auto_tag(entry_meta, content)
        me = MemoryEntry(
            content, entry_meta, parent=parent, embedding=embedding, score=score
        )
        if self.semantic_enabled and me.embedding is None:
            self._add_embedding(me)
        self.backend.append(me.to_dict())
        self.index[me.id] = me
        self.enforce_quota(author)
        self._publish_event("memory_updated", me.to_dict(), author)
        self._plugin_hook("on_save", me.to_dict())
        return me.id

    def update_memory(self, entry_id: str, **kwargs):
        entry = self.index.get(entry_id)
        if not entry:
            return False
        # Versioning/history:
        old = entry.to_dict().copy()
        entry.history.append(old)
        entry.version += 1
        # Update fields:
        if kwargs.get("new_content"):
            entry.content = kwargs["new_content"]
        if kwargs.get("new_meta"):
            entry.meta.update(kwargs["new_meta"])
        if kwargs.get("parent"):
            entry.parent = kwargs["parent"]
        if kwargs.get("embedding"):
            entry.embedding = kwargs["embedding"]
        if kwargs.get("score"):
            entry.score = kwargs["score"]
        entry.timestamp = time.time()
        self._reindex()
        self.backend.overwrite([e.to_dict() for e in self.index.values()])
        self._publish_event("memory_updated", entry.to_dict(), entry.meta.get("author"))
        self._plugin_hook("on_update", entry.to_dict())
        return True

    def delete_memory(self, entry_id: str, user: Optional[str] = None):
        if entry_id in self.index:
            entry = self.index[entry_id]
            del self.index[entry_id]
            self.backend.overwrite([e.to_dict() for e in self.index.values()])
            self._publish_event("memory_deleted", entry.to_dict(), user)
            self._plugin_hook("on_delete", entry.to_dict())
            return True
        return False

    def clear_memory(self, user: Optional[str] = None):
        self._backup()
        self.index.clear()
        self.backend.overwrite([])
        self._publish_event("memory_cleared", {}, user)
        self._plugin_hook("on_clear", {})

    # --- Hierarchical/tree memory ---

    def get_children(self, parent_id: str) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.index.values() if e.parent == parent_id]

    def get_ancestry(self, entry_id: str) -> List[Dict[str, Any]]:
        ancestry = []
        current = self.index.get(entry_id)
        while current and current.parent:
            current = self.index.get(current.parent)
            if current:
                ancestry.append(current.to_dict())
        return ancestry

    # --- Semantic/vector search ---
    def _add_embedding(self, entry: MemoryEntry):
        if not self.semantic_enabled or not self.embedder:
            return
        emb = self.embedder.encode([entry.content])[0]
        entry.embedding = emb.tolist() if hasattr(emb, "tolist") else list(emb)
        # Add to Chroma
        if self.semantic_db:
            self.semantic_db.add(
                documents=[entry.content], embeddings=[entry.embedding], ids=[entry.id]
            )

    def semantic_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.semantic_enabled or not self.embedder or not self.semantic_db:
            return []
        emb = self.embedder.encode([query])[0]
        results = self.semantic_db.query(query_embeddings=[emb.tolist()], n_results=limit)
        hits = results.get("ids", [[]])[0]
        return [self.index[hid].to_dict() for hid in hits if hid in self.index]

    # --- Distributed/federated memory (stub) ---
    def sync_distributed(self):
        # TODO: Implement with Redis Streams, Kafka, or CRDT
        pass

    # --- Retention, TTL, summarization, auto-archive ---
    def expire_old_memories(self):
        if not self.expiry_days:
            return
        cutoff = time.time() - self.expiry_days * 86400
        expired = [eid for eid, e in self.index.items() if e.timestamp < cutoff]
        for eid in expired:
            entry = self.index[eid]
            del self.index[eid]
            self._publish_event("memory_expired", entry.to_dict())
            self._plugin_hook("on_expire", entry.to_dict())
        if expired:
            self.backend.overwrite([e.to_dict() for e in self.index.values()])
            logging.info(f"[Memory] Expired {len(expired)} old memory entries.")

    def summarize_and_archive_old(self):
        # TODO: Use LLM to summarize and archive/compress old memories
        pass

    # --- Policy/access control (stub) ---
    def check_access(self, user, action, entry: MemoryEntry):
        # TODO: Use config/user_manager/policy for fine-grained control
        return True

    # --- Pluggable storage backend: handled via StorageBackend ---

    # --- REST API (stub) ---
    def rest_api_stub(self):
        # TODO: Use FastAPI/Flask to serve endpoints
        pass

    # --- Web dashboard (stub) ---
    def web_dashboard_stub(self):
        # TODO: Use Flask/FastAPI + React/Vue for UI
        pass

    # --- Health & repair ---
    def health_check(self) -> Dict[str, Any]:
        healthy = True
        issues = []
        seen = set()
        for e in self.index.values():
            if e.id in seen:
                healthy = False
                issues.append(f"Duplicate entry id: {e.id}")
            seen.add(e.id)
            if "author" not in e.meta:
                issues.append(f"Entry {e.id} missing author")
        # TODO: Check for broken parent/child, orphaned, corruption
        return {"healthy": healthy, "issues": issues}

    # --- Real-time notification/event streaming (stub) ---
    def notify(self, msg: str):
        # TODO: Webhook, email, chat, etc.
        pass

    # --- Auto-tagging/classification (stub) ---
    def _auto_tag(self, meta: dict, content: str):
        # TODO: ML/LLM or rule-based auto-tagging
        pass

    # --- Edit/merge/diff/versioning/rollback ---
    def get_history(self, entry_id: str) -> List[Dict[str, Any]]:
        entry = self.index.get(entry_id)
        return entry.history if entry else []

    def rollback(self, entry_id: str, version: int) -> bool:
        entry = self.index.get(entry_id)
        if entry and entry.history and 1 <= version < entry.version:
            # Find target version
            for hist in entry.history:
                if hist.get("version") == version:
                    entry.content = hist["content"]
                    entry.meta = hist["meta"]
                    entry.timestamp = time.time()
                    entry.version = version
                    self._write_full()
                    return True
        return False

    # --- Plugin system ---
    def on_plugin_memory(self, event_type: str, handler: Callable[[Dict[str, Any]], None]):
        if not self.event_bus:
            return
        def wrapper(event):
            handler(event.data)
        self.event_bus.subscribe(event_type, wrapper)

    def _publish_event(self, event_type: str, data: dict, author: Optional[str] = None):
        if self.event_bus:
            self.event_bus.publish(event_type, data=data, context={"author": author})

    def _plugin_hook(self, hook: str, data: dict):
        if hook in self.plugin_hooks:
            try:
                self.plugin_hooks[hook](data)
            except Exception as e:
                logging.error(f"[Memory] Plugin hook '{hook}' failed: {e}")

    # --- Compliance (GDPR, export, delete, purge) ---
    def gdpr_export(self, username: str) -> List[Dict[str, Any]]:
        return self.get_user_memories(username, limit=1000000)

    def gdpr_delete(self, username: str):
        to_del = [e.id for e in self.index.values() if e.meta.get("author") == username]
        for eid in to_del:
            del self.index[eid]
        self.backend.overwrite([e.to_dict() for e in self.index.values()])

    # --- Full-text search (stub) ---
    def fulltext_search(self, phrase: str, limit: int = 10) -> List[Dict[str, Any]]:
        # TODO: Implement with Whoosh, SQLite FTS, Elastic, etc.
        return [e.to_dict() for e in self.index.values() if phrase.lower() in e.content.lower()][:limit]

    # --- Multi-user utility ---
    def list_all_users(self) -> List[str]:
        authors = {e.meta.get("author", "unknown") for e in self.index.values()}
        return sorted(a for a in authors if a and a != "unknown")

    def get_user_memories(self, username: str, limit: int = 10) -> List[Dict[str, Any]]:
        memories = [
            e.to_dict()
            for e in self.index.values()
            if e.meta.get("author") == username
        ]
        memories.sort(key=lambda m: m["timestamp"], reverse=True)
        return memories[:limit]

    def enforce_quota(self, username: Optional[str]):
        if self.memory_quota is None or not username:
            return
        user_entries = [e for e in self.index.values() if e.meta.get("author") == username]
        if len(user_entries) > self.memory_quota:
            user_entries.sort(key=lambda e: e.timestamp)
            for e in user_entries[:-self.memory_quota]:
                del self.index[e.id]
            self.backend.overwrite([e.to_dict() for e in self.index.values()])

    # --- Context window ---
    def get_recent_context(
        self,
        author: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if limit is None:
            limit = 20
        entries = list(self.index.values())
        if author:
            entries = [e for e in entries if e.meta.get("author") == author]
        if tags:
            entries = [e for e in entries if set(e.meta.get("tags", [])) & tags]
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return [e.to_dict() for e in entries[:limit]]

    # --- Audit/event log export ---
    def export_audit_log(self, out_file: Optional[str] = None) -> str:
        out_file = out_file or os.path.join(self.memory_dir, f"audit-log-{int(time.time())}.csv")
        try:
            import csv
            with open(out_file, "w", newline='', encoding="utf-8") as csvfile:
                fieldnames = ["id", "timestamp", "author", "tags", "summary"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for entry in self.index.values():
                    writer.writerow({
                        "id": entry.id,
                        "timestamp": entry.timestamp,
                        "author": entry.meta.get("author", ""),
                        "tags": ";".join(entry.meta.get("tags", [])),
                        "summary": entry.content[:60]
                    })
            return out_file
        except Exception as e:
            logging.error(f"[Memory] Failed to export audit log: {e}")
            return ""
