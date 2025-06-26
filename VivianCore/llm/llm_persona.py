import random
import json
import time
import threading

class PersonaEngine:
    """
    Vivian Ultra Persona Engine:
    - Tracks and modulates mood, tone, traits, and identity for adaptive AI behavior.
    - Supports blending, dynamic creation/editing, deep explainability, plugin/callbacks, and security.
    - Full audit/history, import/export, visualization, shell and HTTP API, self-healing, scheduled persona shifts.
    - NEW: Autosave, event bus, websocket/notify hooks, context/role-aware profiles, cause/explain, logging/callbacks, unit tests.
    """

    def __init__(self, config=None, owner="system", *,
                 autosave=False,
                 eventbus=None,
                 notify_cb=None,
                 websocket_cb=None,
                 gui_cb=None,
                 logging_cb=None,
                 context_profiles=None,
                 on_change=None,
                 role=None):
        self.config = config or {}
        self.personas = self.config.get("vivian.personas", {
            "default": {
                "traits": {
                    "tone": "friendly",
                    "mood": "neutral",
                    "curiosity": 0.6,
                    "patience": 0.5,
                    "humor": 0.4,
                    "assertiveness": 0.5,
                }
            }
        })
        self.active_persona = self.config.get("vivian.default_persona", "default")
        self.state = {
            "mood": "neutral",
            "tone": "friendly",
            "traits": {},
            "energy": 0.6,
            "focus": 0.5,
            "confidence": 0.7,
            "last_update": time.time(),
        }
        self.history = []
        self.hooks = []
        self.security = {"owner": owner, "allowed_users": set([owner])}
        self.lock = threading.Lock()
        self.shell_thread = None
        self.api_thread = None
        self.scheduled_shifts = []
        self.eventbus = eventbus
        self.autosave = autosave
        self.notify_cb = notify_cb
        self.websocket_cb = websocket_cb
        self.gui_cb = gui_cb
        self.logging_cb = logging_cb
        self.on_change = on_change
        self.context_profiles = context_profiles or {}
        self.role = role or "default"
        self._scheduler_started = False
        self._load_active_persona()
        if self.autosave:
            self.save()

    def _load_active_persona(self):
        profile = self.personas.get(self.active_persona, {})
        traits = profile.get("traits", {})
        self.state["traits"] = traits
        self.state["tone"] = traits.get("tone", "friendly")
        self.state["mood"] = traits.get("mood", "neutral")
        self.state["last_update"] = time.time()
        self._record("persona_load", {"active": self.active_persona, "traits": traits})
        self._notify_all("persona_loaded", self.get_persona_profile())

    def get_persona_profile(self, context=None, role=None):
        # Context/role-aware persona
        role = role or self.role
        context_traits = self.context_profiles.get(role, {})
        persona_traits = {**self.state["traits"], **context_traits}
        return {
            "active": self.active_persona,
            "mood": self.state["mood"],
            "tone": self.state["tone"],
            "traits": persona_traits,
            "energy": self.state.get("energy", 0.6),
            "focus": self.state.get("focus", 0.5),
            "confidence": self.state.get("confidence", 0.7),
            "history": self.history[-5:],
            "scheduled_shifts": self.scheduled_shifts,
            "role": role,
        }

    def set_persona(self, name, user=None, explain=True):
        if user and not self._is_allowed(user):
            return f"[Persona] Permission denied."
        if name in self.personas:
            old = self.active_persona
            self.active_persona = name
            self._load_active_persona()
            self._record("persona_switch", {"from": old, "to": name})
            self._fire_hooks("persona", old, name)
            self._notify_all("persona_switched", {"from": old, "to": name})
            self._autosave()
            return f"[Persona] Switched to: {name}" if not explain else self.explain()
        return f"[Persona] Not found: {name}"

    def add_persona(self, name, traits, user=None):
        if user and not self._is_allowed(user):
            return f"[Persona] Permission denied."
        self.personas[name] = {"traits": traits}
        self._record("persona_add", {"name": name, "traits": traits})
        self._notify_all("persona_added", {"name": name, "traits": traits})
        self._autosave()
        return f"[Persona] Added: {name}"

    def edit_persona(self, name, traits, user=None):
        if user and not self._is_allowed(user):
            return f"[Persona] Permission denied."
        if name in self.personas:
            self.personas[name]["traits"].update(traits)
            self._record("persona_edit", {"name": name, "traits": traits})
            if name == self.active_persona:
                self._load_active_persona()
            self._notify_all("persona_edited", {"name": name, "traits": traits})
            self._autosave()
            return f"[Persona] Edited: {name}"
        return f"[Persona] Not found: {name}"

    def remove_persona(self, name, user=None):
        if user and not self._is_allowed(user):
            return f"[Persona] Permission denied."
        if name in self.personas and name != "default":
            del self.personas[name]
            self._record("persona_remove", {"name": name})
            self._notify_all("persona_removed", {"name": name})
            self._autosave()
            return f"[Persona] Removed: {name}"
        return f"[Persona] Not found or cannot remove default."

    def blend_personas(self, blend, new_name="blend", user=None):
        """blend: {"persona1": 0.7, "persona2": 0.3}"""
        if user and not self._is_allowed(user):
            return f"[Persona] Permission denied."
        traits = {}
        for p, w in blend.items():
            if p in self.personas:
                for k, v in self.personas[p]["traits"].items():
                    if isinstance(v, (int, float)):
                        traits[k] = traits.get(k, 0) + v * w
                    else:
                        traits[k] = v if w == max(blend.values()) else traits.get(k, v)
        self.personas[new_name] = {"traits": traits}
        self._record("persona_blend", {"blend": blend, "name": new_name, "traits": traits})
        self._notify_all("persona_blended", {"name": new_name, "traits": traits})
        self._autosave()
        return f"[Persona] Blended persona '{new_name}' created."

    def update_mood(self, interaction_type="neutral", explain=True, cause=None):
        """Shift mood based on interaction (positive, negative, etc)."""
        mood_map = {
            "positive": ["cheerful", "inspired", "playful"],
            "negative": ["irritated", "quiet", "guarded"],
            "neutral": ["focused", "passive", "attentive"]
        }
        if interaction_type in mood_map:
            old = self.state["mood"]
            new_mood = random.choice(mood_map[interaction_type])
            self.state["mood"] = new_mood
            self.state["last_update"] = time.time()
            self._record("mood_update", {"interaction": interaction_type, "old_mood": old, "new_mood": new_mood, "cause": cause})
            self._fire_hooks("mood", old, new_mood)
            self._notify_all("mood_changed", {"old": old, "new": new_mood, "cause": cause})
            self._autosave()
        return self.state["mood"] if not explain else self.explain(cause=cause)

    def set_mood(self, mood, user=None, explain=True, cause=None):
        if user and not self._is_allowed(user):
            return f"[Persona] Permission denied."
        old = self.state["mood"]
        self.state["mood"] = mood
        self.state["last_update"] = time.time()
        self._record("mood_set", {"old_mood": old, "mood": mood, "cause": cause})
        self._fire_hooks("mood", old, mood)
        self._notify_all("mood_set", {"old": old, "new": mood, "cause": cause})
        self._autosave()
        return f"[Persona] Mood set to: {mood}" if not explain else self.explain(cause=cause)

    def modulate_traits(self, **kwargs):
        "Dynamically change numeric traits (e.g., curiosity=0.9)"
        updated = {}
        for k, v in kwargs.items():
            if k in self.state["traits"] and isinstance(self.state["traits"][k], (float, int)):
                self.state["traits"][k] = float(v)
                updated[k] = float(v)
        self._record("traits_modulate", updated)
        self._notify_all("traits_modulated", updated)
        self._autosave()
        return self.state["traits"]

    def inject_traits_into_prompt(self, prompt, include_energy=True, role=None):
        role = role or self.role
        trait_lines = [f"{k}: {v}" for k, v in self.get_persona_profile(role=role)["traits"].items()]
        if include_energy:
            trait_lines.append(f"energy: {self.state.get('energy', 0.6)}")
            trait_lines.append(f"focus: {self.state.get('focus', 0.5)}")
            trait_lines.append(f"confidence: {self.state.get('confidence', 0.7)}")
        traits_text = "\n".join(trait_lines)
        return f"{traits_text}\n\n{prompt}"

    def explain(self, cause=None):
        profile = self.get_persona_profile()
        explanation = {
            "persona": profile["active"],
            "mood": profile["mood"],
            "tone": profile["tone"],
            "traits": profile["traits"],
            "energy": profile["energy"],
            "focus": profile["focus"],
            "confidence": profile["confidence"],
            "last_events": profile["history"],
            "scheduled_shifts": profile["scheduled_shifts"],
            "role": profile.get("role"),
            "cause": cause,
        }
        return explanation

    def _record(self, event, details):
        with self.lock:
            self.history.append({
                "timestamp": time.time(),
                "event": event,
                "details": details
            })
        if self.eventbus:
            self.eventbus.publish(event, details)
        if self.logging_cb:
            self.logging_cb(event, details)
        self._autosave()

    def persona_history(self, n=10):
        return self.history[-n:]

    # --- Plugin/callback hooks ---
    def register_hook(self, fn):
        self.hooks.append(fn)

    def _fire_hooks(self, typ, old, new):
        for fn in self.hooks:
            try:
                fn(typ, old, new)
            except Exception:
                pass

    # --- Notification broadcasting ---
    def _notify_all(self, event, data):
        if self.notify_cb:
            try: self.notify_cb(event, data)
            except Exception: pass
        if self.websocket_cb:
            try: self.websocket_cb(event, data)
            except Exception: pass
        if self.gui_cb:
            try: self.gui_cb(event, data)
            except Exception: pass
        if self.on_change:
            try: self.on_change(event, data)
            except Exception: pass

    # --- Security/access control ---
    def _is_allowed(self, user):
        return (not self.security["allowed_users"]) or (user in self.security["allowed_users"])

    def grant(self, user):
        self.security["allowed_users"].add(user)
        self._record("grant", {"user": user})

    def revoke(self, user):
        self.security["allowed_users"].discard(user)
        self._record("revoke", {"user": user})

    # --- Import/export with autosave ---
    def save(self, path="persona_state.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "active": self.active_persona,
                "state": self.state,
                "personas": self.personas,
                "history": self.history,
                "scheduled_shifts": self.scheduled_shifts,
                "role": self.role,
            }, f, indent=2)

    def load(self, path="persona_state.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.active_persona = data.get("active", self.active_persona)
                self.state = data.get("state", self.state)
                self.personas = data.get("personas", self.personas)
                self.history = data.get("history", self.history)
                self.scheduled_shifts = data.get("scheduled_shifts", self.scheduled_shifts)
                self.role = data.get("role", self.role)
                self._load_active_persona()
        except Exception as e:
            print("PersonaEngine load error:", e)

    def _autosave(self):
        if self.autosave:
            self.save()

    # --- Visualization ---
    def visualize(self):
        profile = self.get_persona_profile()
        print(f"ACTIVE: {profile['active']}")
        print("TRAITS:")
        for k, v in profile["traits"].items():
            bars = "#" * int(float(v) * 20) if isinstance(v, (float, int)) else ""
            print(f"  {k:12}: {bars:20} ({v})")
        print(f"MOOD: {profile['mood']}, TONE: {profile['tone']}")
        print(f"ENERGY: {profile['energy']:.2f}, FOCUS: {profile['focus']:.2f}, CONFIDENCE: {profile['confidence']:.2f}")
        print("ROLE:", profile.get("role"))
        print("SCHEDULED SHIFTS:")
        for shift in profile.get("scheduled_shifts", []):
            print(f"  At {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(shift['time']))}: {shift['persona']}")
        print("HISTORY (last 5):")
        for h in profile["history"]:
            from datetime import datetime
            print(f"  [{datetime.fromtimestamp(h['timestamp']).strftime('%H:%M:%S')}] {h['event']}: {h['details']}")

    # --- Scheduled persona shifts ---
    def schedule_persona(self, name, shift_time):
        """Schedule a persona switch at a specific unix timestamp."""
        self.scheduled_shifts.append({"persona": name, "time": shift_time})
        self._record("schedule_persona", {"persona": name, "time": shift_time})
        self._autosave()
        self._start_scheduler()
        return f"[Persona] Scheduled shift to '{name}' at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(shift_time))}"

    def _start_scheduler(self):
        if self._scheduler_started:
            return
        def loop():
            while True:
                now = time.time()
                for shift in list(self.scheduled_shifts):
                    if now >= shift["time"]:
                        self.set_persona(shift["persona"])
                        self.scheduled_shifts.remove(shift)
                        self._autosave()
                time.sleep(2)
        threading.Thread(target=loop, daemon=True).start()
        self._scheduler_started = True

    # --- Self-healing ---
    def self_heal(self):
        """Restore to default persona if stuck or error detected."""
        if self.active_persona not in self.personas:
            self.active_persona = "default"
            self._load_active_persona()
            self._record("self_heal", {"reset_to": "default"})
            self._notify_all("self_healed", {"reset_to": "default"})
            self._autosave()
            return "[Persona] Self-healed to default."
        return "[Persona] OK."

    # --- Shell & API ---
    def shell(self):
        print("PersonaEngine Ultra Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("set, add, edit, remove, blend, mood, set_mood, traits, explain, visualize, history, save, load, grant, revoke, schedule, heal, exit")
                elif cmd.startswith("set "):
                    print(self.set_persona(cmd[4:]))
                elif cmd.startswith("add "):
                    _, name, *pairs = cmd.split(" ")
                    traits = {}
                    for pair in pairs:
                        k, v = pair.split("=")
                        traits[k] = float(v) if "." in v else v
                    print(self.add_persona(name, traits))
                elif cmd.startswith("edit "):
                    _, name, *pairs = cmd.split(" ")
                    traits = {}
                    for pair in pairs:
                        k, v = pair.split("=")
                        traits[k] = float(v) if "." in v else v
                    print(self.edit_persona(name, traits))
                elif cmd.startswith("remove "):
                    print(self.remove_persona(cmd[7:]))
                elif cmd.startswith("blend "):
                    parts = cmd.split(" ")
                    blend = {}
                    new_name = "blend"
                    for part in parts[1:]:
                        if "=" in part:
                            k, v = part.split("=")
                            if k == "name":
                                new_name = v
                            else:
                                blend[k] = float(v)
                    print(self.blend_personas(blend, new_name))
                elif cmd.startswith("mood "):
                    print(self.update_mood(cmd[5:]))
                elif cmd.startswith("set_mood "):
                    print(self.set_mood(cmd[9:]))
                elif cmd.startswith("traits "):
                    _, *pairs = cmd.split(" ")
                    traits = {}
                    for pair in pairs:
                        k, v = pair.split("=")
                        traits[k] = float(v)
                    print(self.modulate_traits(**traits))
                elif cmd == "explain":
                    print(self.explain())
                elif cmd == "visualize":
                    self.visualize()
                elif cmd == "history":
                    print(self.persona_history())
                elif cmd.startswith("save"):
                    self.save()
                    print("Saved.")
                elif cmd.startswith("load"):
                    self.load()
                    print("Loaded.")
                elif cmd.startswith("grant "):
                    self.grant(cmd[6:])
                    print("Granted.")
                elif cmd.startswith("revoke "):
                    self.revoke(cmd[7:])
                    print("Revoked.")
                elif cmd.startswith("schedule "):
                    _, name, t = cmd.split(" ")
                    t = float(t)
                    print(self.schedule_persona(name, t))
                elif cmd == "heal":
                    print(self.self_heal())
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self.shell_thread = threading.Thread(target=self.shell, daemon=True)
        self.shell_thread.start()

    def run_api_server(self, port=8789):
        import http.server
        import socketserver
        engine = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body)
                    action = data.get("action")
                    user = data.get("user", engine.security["owner"])
                    if action == "set":
                        self._respond({"result": engine.set_persona(data.get("name"), user=user)})
                    elif action == "add":
                        self._respond({"result": engine.add_persona(data.get("name"), data.get("traits", {}), user=user)})
                    elif action == "edit":
                        self._respond({"result": engine.edit_persona(data.get("name"), data.get("traits", {}), user=user)})
                    elif action == "remove":
                        self._respond({"result": engine.remove_persona(data.get("name"), user=user)})
                    elif action == "blend":
                        self._respond({"result": engine.blend_personas(data.get("blend", {}), data.get("new_name","blend"), user=user)})
                    elif action == "mood":
                        self._respond({"result": engine.update_mood(data.get("mood", "neutral"))})
                    elif action == "set_mood":
                        self._respond({"result": engine.set_mood(data.get("mood","neutral"), user=user)})
                    elif action == "traits":
                        self._respond({"result": engine.modulate_traits(**data.get("traits", {}))})
                    elif action == "explain":
                        self._respond(engine.explain())
                    elif action == "visualize":
                        engine.visualize()
                        self._respond({"result":"visualized"})
                    elif action == "save":
                        engine.save(data.get("path","persona_state.json"))
                        self._respond({"result":"saved"})
                    elif action == "load":
                        engine.load(data.get("path","persona_state.json"))
                        self._respond({"result":"loaded"})
                    elif action == "history":
                        self._respond({"history": engine.persona_history()})
                    elif action == "schedule":
                        self._respond({"result": engine.schedule_persona(data.get("name"), float(data.get("time")))})
                    elif action == "heal":
                        self._respond({"result": engine.self_heal()})
                    else:
                        self._respond({"error": "Invalid action"})
                except Exception as e:
                    self._respond({"error": str(e)})
            def _respond(self, obj):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(obj).encode())
        def serve():
            with socketserver.TCPServer(("", port), Handler) as httpd:
                print(f"PersonaEngine API running on port {port}")
                httpd.serve_forever()
        self.api_thread = threading.Thread(target=serve, daemon=True)
        self.api_thread.start()

    def demo(self):
        print("=== Vivian Ultra PersonaEngine Demo ===")
        print(self.set_persona("default"))
        print(self.add_persona("playful", {"tone":"casual","mood":"playful","curiosity":0.9,"humor":0.8,"assertiveness":0.3}))
        print(self.set_persona("playful"))
        print(self.update_mood("positive"))
        print(self.modulate_traits(curiosity=0.95, patience=0.2))
        print(self.schedule_persona("default", time.time() + 3))
        self.visualize()
        self.save()
        print("Demo complete. Try .run_shell() or .run_api_server().")

    # --- Basic unit test for main features ---
    def _test(self):
        assert "default" in self.personas
        assert self.set_persona("default").get("persona") == "default"
        assert self.add_persona("test", {"tone":"testy"}) == "[Persona] Added: test"
        assert self.edit_persona("test", {"humor":0.77}) == "[Persona] Edited: test"
        assert self.remove_persona("test").startswith("[Persona] Removed")
        print("All tests passed.")

if __name__ == "__main__":
    engine = PersonaEngine(autosave=True)
    engine.demo()
    engine._test()