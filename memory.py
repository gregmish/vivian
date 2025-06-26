import os
import json
import datetime
import threading
import hashlib

try:
    import cv2  # For future multimodal (image/video) support
except ImportError:
    cv2 = None

def current_time():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

class MemoryManager:
    """
    Vivian-compatible memory/session/event manager.
    Features: interaction/event log, context window, knowledge base, stats, export/backup, multimodal/media, distributed/federated stubs.
    """
    def __init__(self, config, event_bus=None, user_manager=None):
        self.config = config
        self.event_bus = event_bus
        self.user_manager = user_manager

        self.memory_dir = config.get("memory_dir", "memory")
        self.log_file = config.get("log_file", "history.jsonl")
        self.context_window = config.get("context_window", 5)
        self.long_term_memory_enabled = config.get("long_term_memory_enabled", True)
        self.knowledge_base_enabled = config.get("knowledge_base_enabled", True)
        self.knowledge_base_dir = config.get("knowledge_base_dir", "knowledge")
        self.encrypt_memory = config.get("security", {}).get("encrypt_memory", False)
        self.data_retention_days = config.get("security", {}).get("data_retention_days", 90)
        self.mood_tracking_enabled = config.get("mood_tracking_enabled", True)
        self.sentiment_analysis_enabled = config.get("sentiment_analysis_enabled", True)
        self.explainable_ai_enabled = config.get("explainable_ai_enabled", True)
        self.content_moderation_enabled = config.get("content_moderation_enabled", True)
        self.multimodal_enabled = config.get("multimodal_enabled", False)
        self.sandbox_code_execution = config.get("sandbox_code_execution", True)
        self.language = config.get("language", "en")
        self.localization_enabled = config.get("localization_enabled", True)
        self.backup_enabled = config.get("backup_enabled", True)
        self.backup_dir = config.get("backup_dir", "backups")
        self.federated_knowledge_sharing = config.get("federated_knowledge_sharing", False)
        self.distributed_sync_enabled = config.get("distributed_sync_enabled", False)

        self.session = []
        self._event_log = []
        self.lock = threading.Lock()

        os.makedirs(self.memory_dir, exist_ok=True)
        self.log_path = os.path.join(self.memory_dir, self.log_file)

        if self.knowledge_base_enabled:
            os.makedirs(self.knowledge_base_dir, exist_ok=True)
        if self.backup_enabled:
            os.makedirs(self.backup_dir, exist_ok=True)

        self._load_session()
        self._load_event_log()
        self.cleanup_old_entries()

    def _load_session(self):
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    self.session = [json.loads(line) for line in f if line.strip()]
            except Exception as e:
                print(f"[Memory] Failed to load history: {e}")

    def _load_event_log(self):
        event_log_path = os.path.join(self.memory_dir, "vivian_event_log.jsonl")
        self._event_log = []
        if os.path.exists(event_log_path):
            try:
                with open(event_log_path, "r", encoding="utf-8") as f:
                    self._event_log = [json.loads(line) for line in f if line.strip()]
            except Exception as e:
                print(f"[Memory] Failed to load event log: {e}")

    def _encrypt(self, data):
        if not self.encrypt_memory:
            return data
        key = "vivian_secret"
        return ''.join(chr((ord(char) ^ ord(key[i % len(key)]))) for i, char in enumerate(data))

    def _decrypt(self, data):
        return self._encrypt(data)  # XOR is symmetric

    def log_interaction(self, user_input, vivian_reply, mood=None, tags=None, sentiment=None, explanation=None, moderation_result=None, media=None):
        timestamp = datetime.datetime.now().isoformat()
        entry = {
            "timestamp": timestamp,
            "user": user_input,
            "vivian": vivian_reply,
            "mood": mood,
            "sentiment": sentiment,
            "explanation": explanation,
            "moderation": moderation_result,
            "tags": tags or [],
            "media": media
        }
        with self.lock:
            self.session.append(entry)
            try:
                data = json.dumps(entry)
                if self.encrypt_memory:
                    data = self._encrypt(data)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(data + "\n")
            except Exception as e:
                print(f"[Memory] Failed to write entry: {e}")

    def log_event(self, event_type, data=None):
        """
        VivianBrain-compatible event logging.
        """
        event = {
            "time": current_time(),
            "type": event_type,
            "data": data or {},
        }
        with self.lock:
            self._event_log.append(event)
            try:
                event_log_path = os.path.join(self.memory_dir, "vivian_event_log.jsonl")
                with open(event_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception as e:
                print(f"[Memory] Could not write event log: {e}")

    def get_recent(self, limit=10, user=None, event_type=None):
        """
        Get most recent events, optionally filter by user and event_type.
        """
        with self.lock:
            events = list(self._event_log)
            if user:
                events = [e for e in events if e.get("data", {}).get("user") == user or e.get("user") == user]
            if event_type:
                events = [e for e in events if e.get("type") == event_type or e.get("event_type") == event_type]
            return events[-limit:]

    def get_context(self, new_input=None, persona=None, language=None):
        with self.lock:
            context_entries = self.session[-self.context_window:] if self.context_window > 0 else []
            context = []
            for msg in context_entries:
                user = msg.get("user", "")
                vivian = msg.get("vivian", "")
                mood = f" [Mood: {msg.get('mood', '')}]" if self.mood_tracking_enabled and msg.get("mood") else ""
                sentiment = f" [Sentiment: {msg.get('sentiment', '')}]" if self.sentiment_analysis_enabled and msg.get("sentiment") else ""
                context.append(f"User: {user}{mood}{sentiment}\nVivian: {vivian}")
            if new_input:
                persona_blurb = f" [{persona}]" if persona else ""
                lang_blurb = f" [Language: {language or self.language}]" if self.localization_enabled else ""
                context.append(f"User: {new_input}{persona_blurb}{lang_blurb}\nVivian:")
            return "\n".join(context)

    def clear(self):
        with self.lock:
            self.session = []
            try:
                open(self.log_path, "w").close()
            except Exception as e:
                print(f"[Memory] Failed to clear history: {e}")

    def export(self, filename=None):
        if not filename:
            filename = f"export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(self.memory_dir, filename)
        with self.lock:
            try:
                export_session = self.session
                if self.encrypt_memory:
                    export_session = [json.loads(self._decrypt(json.dumps(e))) for e in self.session]
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(export_session, f, indent=2)
                return f"Session exported to {path}"
            except Exception as e:
                return f"[Memory] Export failed: {e}"

    def backup(self):
        if not self.backup_enabled:
            return "[Memory] Backups are disabled."
        filename = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = os.path.join(self.backup_dir, filename)
        with self.lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.session, f, indent=2)
                return f"Backup created at {path}"
            except Exception as e:
                return f"[Memory] Backup failed: {e}"

    def remember_fact(self, fact_text, tags=None, shared=False):
        if not self.knowledge_base_enabled:
            return "[Memory] Knowledge base is disabled."
        if not fact_text:
            return "[Memory] No fact provided."
        key = hashlib.sha256(fact_text.encode("utf-8")).hexdigest()[:12]
        filename = f"fact_{key}.json"
        path = os.path.join(self.knowledge_base_dir, filename)
        fact = {
            "fact": fact_text,
            "tags": tags or [],
            "timestamp": datetime.datetime.now().isoformat(),
            "shared": shared
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(fact, f, indent=2)
            return f"Fact saved as {filename}"
        except Exception as e:
            return f"[Memory] Failed to save fact: {e}"

    def search_knowledge(self, query, tags=None, shared_only=False):
        if not self.knowledge_base_enabled:
            return []
        matches = []
        try:
            for fname in os.listdir(self.knowledge_base_dir):
                if fname.startswith("fact_") and fname.endswith(".json"):
                    with open(os.path.join(self.knowledge_base_dir, fname), "r", encoding="utf-8") as f:
                        fact = json.load(f)
                        if shared_only and not fact.get("shared", False):
                            continue
                        if query.lower() in fact.get("fact", "").lower() or \
                           any(query.lower() in tag.lower() for tag in fact.get("tags", [])):
                            if tags and not set(tags).intersection(set(fact.get("tags", []))):
                                continue
                            matches.append(fact)
        except Exception as e:
            print(f"[Memory] Knowledge search error: {e}")
        return matches

    def cleanup_old_entries(self):
        if self.data_retention_days is None or self.data_retention_days <= 0:
            return
        cutoff = datetime.datetime.now() - datetime.timedelta(days=self.data_retention_days)
        new_session = []
        try:
            for entry in self.session:
                ts = entry.get("timestamp")
                if ts:
                    try:
                        dt = datetime.datetime.fromisoformat(ts)
                        if dt >= cutoff:
                            new_session.append(entry)
                    except Exception:
                        new_session.append(entry)
            if len(new_session) < len(self.session):
                self.session = new_session
                with open(self.log_path, "w", encoding="utf-8") as f:
                    for entry in self.session:
                        data = json.dumps(entry)
                        if self.encrypt_memory:
                            data = self._encrypt(data)
                        f.write(data + "\n")
        except Exception as e:
            print(f"[Memory] Cleanup failed: {e}")

    def get_stats(self):
        stats = {
            "interaction_count": len(self.session),
            "unique_days": len(set(e['timestamp'][:10] for e in self.session if 'timestamp' in e)),
            "facts_saved": 0,
            "moods_tracked": len([e for e in self.session if e.get("mood")]),
            "sentiments_tracked": len([e for e in self.session if e.get("sentiment")]),
            "media_entries": len([e for e in self.session if e.get("media")])
        }
        if self.knowledge_base_enabled:
            try:
                stats["facts_saved"] = len([f for f in os.listdir(self.knowledge_base_dir) if f.startswith("fact_")])
            except Exception:
                stats["facts_saved"] = 0
        return stats

    def save_media(self, media_type, data, tags=None):
        if not self.multimodal_enabled:
            return "[Memory] Multimodal support not enabled."
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        media_name = f"{media_type}_{timestamp}"
        ext = {"image": "jpg", "audio": "wav", "video": "mp4"}.get(media_type, "bin")
        path = os.path.join(self.memory_dir, f"{media_name}.{ext}")
        try:
            with open(path, "wb") as f:
                f.write(data)
            self.log_interaction(
                user_input=f"[{media_type} uploaded]",
                vivian_reply="[Media received]",
                tags=tags,
                media={"type": media_type, "path": path}
            )
            return f"Media saved at {path}"
        except Exception as e:
            return f"[Memory] Failed to save media: {e}"

    def share_fact(self, fact_id):
        if not self.federated_knowledge_sharing:
            return "[Memory] Federated sharing not enabled."
        return f"Fact {fact_id} marked for sharing (not yet implemented)."

    def sync_distributed(self):
        if not self.distributed_sync_enabled:
            return "[Memory] Distributed sync not enabled."
        return "[Memory] Sync complete (not yet implemented)."