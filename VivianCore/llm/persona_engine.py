import random
import time
import json
import threading

class PersonaEngine:
    """
    Vivian-Grade PersonaEngine:
    - Dynamic creation, editing, and blending of personas.
    - Automatic/contextual persona and mood shifts (by context, emotion, time, or commands).
    - Persona-driven output, memory tagging, and goal biasing.
    - Mood modulates system tone, verbosity, and self-confidence.
    - Tracks persona/mood history & explainability.
    - Plugin/callback hooks for persona/mood changes.
    - Security (who can change persona), export/import, visualization, HTTP API, and interactive shell.
    """

    def __init__(self, owner="system"):
        self.owner = owner
        self.active_persona = "default"
        self.available_personas = {
            "default": {
                "tone": "neutral",
                "curiosity": 0.5,
                "patience": 0.7,
                "humor": 0.3,
                "assertiveness": 0.5,
            },
            "serious": {
                "tone": "formal",
                "curiosity": 0.2,
                "patience": 0.9,
                "humor": 0.0,
                "assertiveness": 0.85,
            },
            "playful": {
                "tone": "casual",
                "curiosity": 0.9,
                "patience": 0.4,
                "humor": 0.8,
                "assertiveness": 0.3,
            },
            "analyst": {
                "tone": "precise",
                "curiosity": 0.8,
                "patience": 0.6,
                "humor": 0.1,
                "assertiveness": 0.6,
            }
        }
        self.mood = {
            "energy": 0.5,
            "focus": 0.6,
            "confidence": 0.7,
            "mood_time": time.time()
        }
        self.history = []
        self.hooks = []  # Callbacks for persona/mood changes
        self.last_emotion = None
        self.security = {"owner": owner, "allowed_users": set([owner])}
        self.running = False
        self.api_thread = None
        self.shell_thread = None

    # --- Persona management ---
    def set_persona(self, name, user=None):
        if user and not self._is_allowed(user):
            return f"Permission denied for changing persona."
        if name in self.available_personas:
            old = self.active_persona
            self.active_persona = name
            self._record("persona_change", {"from": old, "to": name})
            self._fire_hooks("persona", old, name)
            return f"Persona set to '{name}'."
        return f"Persona '{name}' not found."

    def add_persona(self, name, traits, user=None):
        if user and not self._is_allowed(user):
            return f"Permission denied for adding persona."
        self.available_personas[name] = traits
        self._record("persona_add", {"name": name, "traits": traits})
        return f"Persona '{name}' added."

    def edit_persona(self, name, traits, user=None):
        if user and not self._is_allowed(user):
            return f"Permission denied for editing persona."
        if name in self.available_personas:
            self.available_personas[name].update(traits)
            self._record("persona_edit", {"name": name, "traits": traits})
            return f"Persona '{name}' updated."
        return f"Persona '{name}' not found."

    def remove_persona(self, name, user=None):
        if user and not self._is_allowed(user):
            return f"Permission denied for removing persona."
        if name in self.available_personas and name != "default":
            del self.available_personas[name]
            self._record("persona_remove", {"name": name})
            return f"Persona '{name}' removed."
        return f"Persona '{name}' not found or cannot remove default."

    def list_personas(self):
        return list(self.available_personas.keys())

    def get_persona(self, name=None):
        if not name: name = self.active_persona
        return self.available_personas.get(name, {})

    # --- Persona blending ---
    def blend_personas(self, blend, name="blend", user=None):
        """
        blend: {"persona1": 0.7, "persona2": 0.3}
        """
        if user and not self._is_allowed(user):
            return f"Permission denied for blending personas."
        traits = {}
        for p, w in blend.items():
            if p in self.available_personas:
                for k, v in self.available_personas[p].items():
                    traits[k] = traits.get(k, 0) + v * w
        self.available_personas[name] = traits
        self._record("persona_blend", {"blend": blend, "name": name, "traits": traits})
        return f"Blended persona '{name}' created: {traits}"

    # --- Mood management ---
    def mood_tick(self, context=None):
        # Periodically adjust mood slightly, or by context
        for k in ["energy", "focus", "confidence"]:
            delta = random.uniform(-0.05, 0.05)
            self.mood[k] = min(1.0, max(0.0, self.mood[k] + delta))
        self.mood["mood_time"] = time.time()
        self._record("mood_tick", {"mood": dict(self.mood)})
        self._fire_hooks("mood", None, dict(self.mood))

    def set_mood(self, **kwargs):
        for k, v in kwargs.items():
            if k in self.mood and isinstance(v, float):
                self.mood[k] = min(1.0, max(0.0, v))
        self.mood["mood_time"] = time.time()
        self._record("mood_set", {"mood": dict(self.mood)})
        self._fire_hooks("mood", None, dict(self.mood))

    def receive_emotion(self, emotion, user=None):
        # e.g., "happy", "angry", "bored" -- shifts persona/mood
        # Demo: happy -> playful, angry -> serious, bored -> analyst
        mapping = {"happy": "playful", "angry": "serious", "bored": "analyst"}
        if emotion in mapping:
            self.set_persona(mapping[emotion], user=user)
        self.last_emotion = emotion
        self._record("emotion", {"emotion": emotion, "shifted_to": mapping.get(emotion)})
        return f"Emotion '{emotion}' processed."

    # --- Explainability and history ---
    def get_persona_profile(self):
        return {
            "active": self.active_persona,
            "traits": self.available_personas[self.active_persona],
            "mood": self.mood,
            "history": self.history[-5:]
        }

    def explain(self):
        return self.get_persona_profile()

    def persona_history(self, n=10):
        return self.history[-n:]

    def _record(self, event, details):
        self.history.append({
            "timestamp": time.time(),
            "event": event,
            "details": details
        })

    # --- Hooks/plugin notifications ---
    def register_hook(self, fn):
        self.hooks.append(fn)

    def _fire_hooks(self, typ, old, new):
        for fn in self.hooks:
            try:
                fn(typ, old, new)
            except Exception as e:
                pass

    # --- Persona/mood-driven output helpers ---
    def modulate_output(self, text):
        """Modulate output based on persona and mood."""
        persona = self.available_personas[self.active_persona]
        tone = persona.get("tone", "neutral")
        humor = persona.get("humor", 0)
        confidence = self.mood.get("confidence", 0.7)
        # Example: add jokes if playful and humor high
        if humor > 0.6 and random.random() < humor:
            text += " 😄 (Just kidding!)"
        # Add disclaimers if low confidence
        if confidence < 0.4:
            text = "🤔 (Not sure) " + text
        # Change style
        if tone == "formal":
            text = "Dear user, " + text
        elif tone == "casual":
            text = text + " (ya know?)"
        elif tone == "precise":
            text = "[FACTUAL] " + text
        return text

    def tag_memory(self, content):
        "Return persona/mood tags for classifying memory."
        return [self.active_persona, self.available_personas[self.active_persona]["tone"], "energy_%.2f" % self.mood["energy"]]

    # --- Persona-driven goal biasing ---
    def bias_goal_priority(self, base_priority):
        """Adjust goal priority based on persona traits/mood."""
        persona = self.available_personas[self.active_persona]
        curiosity = persona.get("curiosity", 0.5)
        energy = self.mood.get("energy", 0.5)
        # If playful/curious, increase priority for novel/exploratory goals
        return base_priority + curiosity * 0.2 + (energy-0.5)*0.1

    # --- Security/access control ---
    def _is_allowed(self, user):
        return (not self.security["allowed_users"]) or (user in self.security["allowed_users"])

    def grant(self, user):
        self.security["allowed_users"].add(user)
    def revoke(self, user):
        self.security["allowed_users"].discard(user)

    # --- Import/export ---
    def export_personas(self, path="personas.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.available_personas, f, indent=2)
    def import_personas(self, path="personas.json"):
        with open(path, "r", encoding="utf-8") as f:
            self.available_personas = json.load(f)

    # --- Visualization ---
    def visualize(self):
        profile = self.get_persona_profile()
        print(f"ACTIVE: {profile['active']}")
        print("TRAITS:")
        for k,v in profile["traits"].items():
            bars = "#" * int(v*20)
            print(f"  {k:12}: {bars:20} ({v:.2f})")
        print("MOOD:")
        for k,v in profile["mood"].items():
            if k == "mood_time": continue
            bars = "#" * int(v*20)
            print(f"  {k:12}: {bars:20} ({v:.2f})")
        print("HISTORY (last 5):")
        for h in profile["history"]:
            print(f"  [{time.strftime('%H:%M:%S', time.localtime(h['timestamp']))}] {h['event']}: {h['details']}")

    # --- API and interactive shell ---
    def run_api_server(self, port=8790):
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
                    user = data.get("user", engine.owner)
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
                        engine.set_mood(**data.get("mood", {})); self._respond({"result": "mood set"})
                    elif action == "emotion":
                        self._respond({"result": engine.receive_emotion(data.get("emotion","neutral"), user=user)})
                    elif action == "profile":
                        self._respond(engine.get_persona_profile())
                    elif action == "visualize":
                        engine.visualize()
                        self._respond({"result":"visualized"})
                    elif action == "export":
                        engine.export_personas(data.get("path", "personas.json"))
                        self._respond({"result":"exported"})
                    elif action == "import":
                        engine.import_personas(data.get("path", "personas.json"))
                        self._respond({"result":"imported"})
                    elif action == "list":
                        self._respond({"personas": engine.list_personas()})
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

    def interactive_shell(self):
        print("PersonaEngine Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"): print("Exiting shell."); break
                elif cmd == "help":
                    print("Commands: set, add, edit, remove, list, blend, mood, emotion, explain, visualize, export, import, history, grant, revoke, profile, shell, api, exit")
                elif cmd.startswith("set "):
                    print(self.set_persona(cmd[4:]))
                elif cmd.startswith("add "):
                    _, name, *pairs = cmd.split(" ")
                    traits = {}
                    for pair in pairs:
                        k,v = pair.split("=")
                        traits[k]=float(v) if "." in v else v
                    print(self.add_persona(name, traits))
                elif cmd.startswith("edit "):
                    _, name, *pairs = cmd.split(" ")
                    traits = {}
                    for pair in pairs:
                        k,v = pair.split("=")
                        traits[k]=float(v) if "." in v else v
                    print(self.edit_persona(name, traits))
                elif cmd.startswith("remove "):
                    print(self.remove_persona(cmd[7:]))
                elif cmd == "list":
                    print(self.list_personas())
                elif cmd.startswith("blend "):
                    # Example: blend analyst=0.6 playful=0.4 name=custom
                    parts = cmd.split(" ")
                    blend = {}
                    new_name = "blend"
                    for part in parts[1:]:
                        if "=" in part:
                            k,v = part.split("=")
                            if k == "name": new_name = v
                            else: blend[k]=float(v)
                    print(self.blend_personas(blend, new_name))
                elif cmd.startswith("mood "):
                    _, *pairs = cmd.split(" ")
                    mood = {}
                    for pair in pairs:
                        k,v = pair.split("=")
                        mood[k]=float(v)
                    self.set_mood(**mood)
                    print("Mood set.")
                elif cmd.startswith("emotion "):
                    print(self.receive_emotion(cmd[8:]))
                elif cmd == "explain" or cmd == "profile":
                    print(self.explain())
                elif cmd == "visualize":
                    self.visualize()
                elif cmd.startswith("export"):
                    self.export_personas()
                    print("Exported.")
                elif cmd.startswith("import"):
                    self.import_personas()
                    print("Imported.")
                elif cmd == "history":
                    print(self.persona_history())
                elif cmd.startswith("grant "):
                    self.grant(cmd[6:])
                    print("Granted.")
                elif cmd.startswith("revoke "):
                    self.revoke(cmd[7:])
                    print("Revoked.")
                elif cmd == "shell":
                    print("Already in shell.")
                elif cmd == "api":
                    self.run_api_server()
                    print("API started.")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self.shell_thread = threading.Thread(target=self.interactive_shell, daemon=True)
        self.shell_thread.start()

    def demo(self):
        print("=== PersonaEngine Vivian Demo ===")
        self.visualize()
        print(self.set_persona("playful"))
        self.set_mood(energy=0.9, focus=0.4, confidence=0.8)
        print(self.receive_emotion("angry"))
        self.visualize()
        print(self.blend_personas({"serious":0.5, "playful":0.5}, name="seriplay"))
        print(self.set_persona("seriplay"))
        self.visualize()
        self.export_personas()
        print("Demo complete. You can try .run_shell() or .run_api_server().")

if __name__ == "__main__":
    engine = PersonaEngine()
    engine.demo()