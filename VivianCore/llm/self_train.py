import time
import threading
import json
from VivianCore.llm.memory_graph import MemoryGraph

class SelfTrainer:
    """
    Vivian Quantum SelfTrainer:
    - Continuously scans long-term and short-term memory for patterns, contradictions, novelty, forgotten threads, and emerging goals.
    - Injects deep reflection, self-questioning, and action proposals for AGI-grade self-improvement.
    - Supports anomaly, novelty, and drift detection, hooks, plugin bus, scheduled/triggered reflection, explainability, audit, API/shell, observer/subscribe, self-healing, and multi-agent modes.
    """

    def __init__(self, memory: MemoryGraph, log_path="self_trainer_audit.json", config=None):
        self.memory = memory
        self.config = config or {}
        self.running = False
        self.interval = self.config.get("selftrainer.interval", 30)
        self.audit_log = []
        self.hooks = []
        self._loop_thread = None
        self.log_path = log_path
        self.last_insight = None
        self.last_pattern = None
        self.last_error = None
        self.scheduled_reflections = []
        self._scheduler_thread = None
        self._shell_thread = None
        self.max_patterns = self.config.get("selftrainer.max_patterns", 5)
        self.security = {
            "owner": self.config.get("vivian.owner", "system"),
            "allowed_users": set([self.config.get("vivian.owner", "system")])
        }
        self.observers = []
        self._scheduler_started = False
        self._reflection_history = []
        self.max_reflection_history = self.config.get("selftrainer.max_reflection_history", 100)

    def reflect_and_learn(self):
        """Deep self-improvement and anomaly/novelty/drift detection."""
        recent = self.memory.last_n(30)
        if not recent:
            return

        # Pattern and novelty analysis
        themes = {}
        contradictions = []
        forgotten_tags = set()
        timestamps = []
        seen_tags = set()
        for node in recent:
            for tag in node.get("tags", []):
                themes[tag] = themes.get(tag, 0) + 1
                seen_tags.add(tag)
            if "contradiction" in node.get("tags", []):
                contradictions.append(node)
            timestamps.append(node.get("timestamp", 0))

        dominant = max(themes, key=themes.get) if themes else None
        self.last_pattern = dominant

        # Novelty/Drift: tags not seen recently but present in long-term memory
        longterm = self.memory.last_n(200)
        ltags = set()
        for node in longterm:
            for tag in node.get("tags", []):
                ltags.add(tag)
        forgotten_tags = ltags - seen_tags
        forgotten_tags = list(forgotten_tags)[:self.max_patterns]

        # Reflection: dominant theme
        reflection_chunks = []
        if dominant:
            insight = f"Recurring focus: '{dominant}'. Should I pursue this further or change direction?"
            self.memory.add_memory(
                content=insight,
                tags=["insight", "self_reflection", dominant],
                importance=1.7,
                source="SelfTrainer"
            )
            reflection_chunks.append(insight)
        # Reflection: forgotten tags/themes
        if forgotten_tags:
            forgotten_note = f"Topics not recently considered: {', '.join(forgotten_tags)}. Is there value in revisiting them?"
            self.memory.add_memory(
                content=forgotten_note,
                tags=["forgotten", "self_reflection"],
                importance=1.2,
                source="SelfTrainer"
            )
            reflection_chunks.append(forgotten_note)
        # Reflection: contradictions
        if contradictions:
            for c in contradictions:
                contradiction_note = f"Contradiction detected: {str(c.get('content'))[:80]}"
                self.memory.add_memory(
                    content=contradiction_note,
                    tags=["contradiction", "self_reflection"],
                    importance=2.1,
                    source="SelfTrainer"
                )
                reflection_chunks.append(contradiction_note)

        # Reflection: drift detection (change in focus over time)
        if len(timestamps) >= 2:
            drift = (max(timestamps) - min(timestamps)) / max(1, len(timestamps))
            if drift > 3600 * 24:  # more than a day between oldest and newest
                drift_note = "Detected drift in attention: large time gap between memories. Should I review why?"
                self.memory.add_memory(
                    content=drift_note,
                    tags=["drift", "self_reflection"],
                    importance=1.5,
                    source="SelfTrainer"
                )
                reflection_chunks.append(drift_note)

        # Reflection: inject a self-question if no strong themes
        if not dominant and not contradictions and not forgotten_tags:
            question = "No strong patterns found. Should I explore new topics or review old goals?"
            self.memory.add_memory(
                content=question,
                tags=["self_query", "self_reflection"],
                importance=1.0,
                source="SelfTrainer"
            )
            reflection_chunks.append(question)

        # Save reflection history
        if reflection_chunks:
            self._reflection_history.extend(reflection_chunks)
            self._reflection_history = self._reflection_history[-self.max_reflection_history:]
            self.last_insight = reflection_chunks[-1]
            self._audit("reflect_and_learn", {
                "dominant": dominant, "contradictions": len(contradictions),
                "forgotten_tags": forgotten_tags, "reflection": reflection_chunks
            })
            self._fire_hooks("reflection", dominant, contradictions, forgotten_tags)
            self._notify_observers("reflection", dominant, contradictions, forgotten_tags)

    def run(self, interval: int = None, user=None):
        """Start self-training loop in background."""
        if user and not self._is_allowed(user):
            return "[SelfTrainer] Permission denied."
        if self.running:
            return "[SelfTrainer] Already running."
        self.running = True
        if interval:
            self.interval = interval

        def loop():
            while self.running:
                try:
                    self.reflect_and_learn()
                    time.sleep(self.interval)
                except Exception as e:
                    self.last_error = str(e)
                    print(f"[SelfTrainer] Error: {e}")
                    self._audit("error", {"error": str(e)})
                    time.sleep(5)

        self._loop_thread = threading.Thread(target=loop, daemon=True)
        self._loop_thread.start()
        self._start_scheduler()
        return "[SelfTrainer] Started."

    def stop(self, user=None):
        if user and not self._is_allowed(user):
            return "[SelfTrainer] Permission denied."
        self.running = False
        self._audit("stop", {})
        return "[SelfTrainer] Stopped."

    # --- Scheduling ---
    def schedule_reflection(self, when: float, note="", user=None):
        """Schedule a one-time reflection at a unix timestamp."""
        if user and not self._is_allowed(user):
            return "[SelfTrainer] Permission denied."
        self.scheduled_reflections.append({"time": when, "note": note})
        self._audit("schedule_reflection", {"when": when, "note": note})
        self._start_scheduler()
        return f"[SelfTrainer] Scheduled reflection at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(when))}"

    def _start_scheduler(self):
        if self._scheduler_started:
            return
        def scheduler_loop():
            while True:
                now = time.time()
                for r in list(self.scheduled_reflections):
                    if now >= r["time"]:
                        self.reflect_and_learn()
                        if r["note"]:
                            self.memory.add_memory(f"Scheduled reflection: {r['note']}", tags=["scheduled_reflection"], source="SelfTrainer")
                        self.scheduled_reflections.remove(r)
                time.sleep(2)
        self._scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        self._scheduler_started = True

    # --- Hooks/plugins/event bus ---
    def register_hook(self, fn):
        self.hooks.append(fn)
    def _fire_hooks(self, typ, pattern, contradictions, forgotten_tags):
        for fn in self.hooks:
            try:
                fn(typ, pattern, contradictions, forgotten_tags)
            except Exception:
                pass

    def subscribe(self, fn):
        self.observers.append(fn)
    def _notify_observers(self, typ, pattern, contradictions, forgotten_tags):
        for fn in self.observers:
            try:
                fn(typ, pattern, contradictions, forgotten_tags)
            except Exception:
                pass

    # --- Auditing and explainability ---
    def _audit(self, event, details):
        self.audit_log.append({
            "timestamp": time.time(),
            "event": event,
            "details": details
        })

    def audit_export(self, path=None):
        path = path or self.log_path
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def explain(self):
        return {
            "running": self.running,
            "interval": self.interval,
            "last_insight": self.last_insight,
            "last_pattern": self.last_pattern,
            "last_error": self.last_error,
            "scheduled_reflections": self.scheduled_reflections,
            "audit_length": len(self.audit_log),
            "reflection_history": self._reflection_history[-5:]
        }

    # --- Security/access control ---
    def _is_allowed(self, user):
        return (not self.security["allowed_users"]) or (user in self.security["allowed_users"])

    def grant(self, user):
        self.security["allowed_users"].add(user)
    def revoke(self, user):
        self.security["allowed_users"].discard(user)

    # --- Shell & API ---
    def shell(self):
        print("Vivian Quantum SelfTrainer Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("start, stop, reflect, schedule, explain, audit, grant, revoke, subscribe, shell, exit")
                elif cmd == "start":
                    print(self.run())
                elif cmd == "stop":
                    print(self.stop())
                elif cmd == "reflect":
                    self.reflect_and_learn()
                    print("Reflected.")
                elif cmd.startswith("schedule "):
                    _, t, *note = cmd.split(" ", 2)
                    t = float(t)
                    note = note[0] if note else ""
                    print(self.schedule_reflection(t, note))
                elif cmd == "explain":
                    print(self.explain())
                elif cmd == "audit":
                    self.audit_export()
                    print("Audit exported.")
                elif cmd.startswith("grant "):
                    self.grant(cmd[6:])
                    print("Granted.")
                elif cmd.startswith("revoke "):
                    self.revoke(cmd[7:])
                    print("Revoked.")
                elif cmd == "subscribe":
                    print("Subscribed a demo observer to reflections.")
                    self.subscribe(lambda typ, pat, contr, forgot: print(f"[Observer] {typ}: {pat or contr or forgot}"))
                elif cmd == "shell":
                    print("Already in shell.")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self._shell_thread = threading.Thread(target=self.shell, daemon=True)
        self._shell_thread.start()

    def demo(self):
        print("=== Vivian Quantum SelfTrainer Demo ===")
        print(self.run(2))
        time.sleep(3)
        self.reflect_and_learn()
        print(self.schedule_reflection(time.time()+2, "Demo scheduled reflection"))
        time.sleep(5)
        print(self.stop())
        self.audit_export()
        print("Demo complete. Try .run_shell().")

if __name__ == "__main__":
    # Minimal demo with MemoryGraph stub
    class DummyMemory:
        def __init__(self):
            self.mem = []
        def last_n(self, n):
            return self.mem[-n:]
        def add_memory(self, content, tags=None, importance=None, source=None):
            self.mem.append({
                "content": content, "tags": tags or [],
                "importance": importance, "source": source,
                "timestamp": time.time()
            })
    m = DummyMemory()
    m.add_memory("I am learning about AGI.", tags=["agi","learning"])
    m.add_memory("Contradictory info here.", tags=["contradiction"])
    m.add_memory("I haven't thought about robotics in a while.", tags=["robotics"])
    trainer = SelfTrainer(m)
    trainer.demo()