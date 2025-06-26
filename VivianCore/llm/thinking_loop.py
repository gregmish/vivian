import threading
import time
import random
import json

class ThinkingLoop:
    """
    AGI-Grade ThinkingLoop:
    - Runs continuous, persona-driven internal 'thoughts' based on memory context and goals.
    - Feeds ideas, questions, reflections, and suggestions into memory.
    - Can trigger plugins, spawn new goals, perform analytics, simulate reflection, support explainability, and audit.
    - Interactive shell and HTTP API included. Thread-safe.
    """

    def __init__(self, memory, goal_loop=None, plugin_orchestrator=None, interval=20):
        self.memory = memory
        self.goal_loop = goal_loop
        self.plugin_orchestrator = plugin_orchestrator
        self.running = False
        self.interval = interval  # seconds
        self.persona = "default"
        self.audit_log = []
        self.shell_thread = None
        self.api_thread = None
        self.thought_history = []
        self.last_thought = ""
        self.personas = {
            "default": [
                "What have I learned recently?",
                "Is anything being repeated too often?",
                "Are plugins running smoothly?",
                "Can I suggest a new goal?",
                "What's missing from current memory?",
                "How can I improve my own performance?",
            ],
            "curious": [
                "What new pattern can I discover?",
                "What am I not asking?",
                "What can I explore further?",
                "Who else should be involved in this process?",
                "Can I challenge any current assumptions?",
            ],
            "reflective": [
                "How did my last decision impact the system?",
                "Have I missed any important details?",
                "How would a different persona think about this?",
                "What would I do differently next time?",
            ],
            "critical": [
                "What is the weakest link in my logic?",
                "Where are the most likely errors?",
                "What is the cost of failure right now?",
            ]
        }

    def set_persona(self, name):
        if name not in self.personas:
            self.memory.add_memory(f"[ThinkingLoop] Unknown persona: {name}", tags=["thinking", "error"])
            return
        self.persona = name
        self.memory.add_memory(f"[ThinkingLoop] Persona set to: {name}", tags=["thinking", "persona"])
        self.audit_log.append({"event": "set_persona", "persona": name, "timestamp": time.time()})

    def think(self):
        thoughts = self.personas.get(self.persona, self.personas["default"])
        thought = random.choice(thoughts)
        context = {"persona": self.persona}
        self.memory.add_memory(f"[ThinkingLoop] Thought: {thought}", context=context, tags=["thinking", "self"])
        self.thought_history.append({"thought": thought, "persona": self.persona, "timestamp": time.time()})
        self.last_thought = thought
        self.audit_log.append({"event": "think", "thought": thought, "persona": self.persona, "timestamp": time.time()})

        # Optional: spawn a goal from thought
        if self.goal_loop and random.random() < 0.3:
            goal_id = self.goal_loop.add_goal(f"Reflect on: {thought}", context=context, tags=["thinking", "reflection"])
            self.memory.add_memory(f"[ThinkingLoop] Spawned goal {goal_id} from thought.", tags=["thinking", "goal"])
            self.audit_log.append({"event": "spawn_goal", "goal_id": goal_id, "thought": thought, "timestamp": time.time()})

        # Optional: trigger plugin orchestrator
        if self.plugin_orchestrator and random.random() < 0.2:
            try:
                self.plugin_orchestrator.run_all_plugins()
                self.memory.add_memory("[ThinkingLoop] Triggered plugins.", tags=["thinking", "plugins"])
                self.audit_log.append({"event": "trigger_plugins", "timestamp": time.time()})
            except Exception as e:
                self.memory.add_memory(f"[ThinkingLoop] Plugin trigger error: {e}", tags=["thinking", "error"])
                self.audit_log.append({"event": "plugin_error", "error": str(e), "timestamp": time.time()})

    def start(self):
        self.running = True
        def loop():
            while self.running:
                self.think()
                time.sleep(self.interval)
        threading.Thread(target=loop, daemon=True).start()
        self.memory.add_memory("[ThinkingLoop] Started.", tags=["thinking", "start"])
        self.audit_log.append({"event": "start", "timestamp": time.time()})

    def stop(self):
        self.running = False
        self.memory.add_memory("[ThinkingLoop] Stopped.", tags=["thinking", "stop"])
        self.audit_log.append({"event": "stop", "timestamp": time.time()})

    def explain(self):
        return {
            "persona": self.persona,
            "last_thought": self.last_thought,
            "thought_history": self.thought_history[-5:],
            "running": self.running,
            "interval": self.interval
        }

    def audit_export(self, path="thinkingloop_audit.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def simulate(self, n=3):
        for _ in range(n):
            self.think()
        self.audit_log.append({"event": "simulate", "steps": n, "timestamp": time.time()})

    def interactive_shell(self):
        print("ThinkingLoop Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: persona, think, explain, simulate, audit, start, stop, exit")
                elif cmd.startswith("persona "):
                    name = cmd.split(" ", 1)[1]
                    self.set_persona(name)
                    print(f"Persona set to: {name}")
                elif cmd == "think":
                    self.think()
                    print(f"Thought: {self.last_thought}")
                elif cmd == "explain":
                    print(self.explain())
                elif cmd.startswith("simulate"):
                    self.simulate()
                    print("Simulated.")
                elif cmd == "audit":
                    self.audit_export()
                    print("Audit exported.")
                elif cmd == "start":
                    self.start()
                    print("ThinkingLoop started.")
                elif cmd == "stop":
                    self.stop()
                    print("ThinkingLoop stopped.")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self.shell_thread = threading.Thread(target=self.interactive_shell, daemon=True)
        self.shell_thread.start()

    def run_api_server(self, port=8780):
        import http.server
        import socketserver

        loop = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body)
                    action = data.get("action")
                    if action == "think":
                        loop.think()
                        self._respond({"thought": loop.last_thought})
                    elif action == "persona":
                        loop.set_persona(data.get("persona", "default"))
                        self._respond({"persona": loop.persona})
                    elif action == "explain":
                        self._respond(loop.explain())
                    elif action == "simulate":
                        loop.simulate(data.get("steps", 3))
                        self._respond({"result": "ok"})
                    elif action == "audit":
                        loop.audit_export(data.get("path", "thinkingloop_audit.json"))
                        self._respond({"result": "ok"})
                    elif action == "start":
                        loop.start()
                        self._respond({"result": "started"})
                    elif action == "stop":
                        loop.stop()
                        self._respond({"result": "stopped"})
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
                print(f"ThinkingLoop API running on port {port}")
                httpd.serve_forever()
        self.api_thread = threading.Thread(target=serve, daemon=True)
        self.api_thread.start()

    def demo(self):
        print("=== ThinkingLoop AGI Demo ===")
        self.set_persona("curious")
        self.simulate(3)
        print("Explain:", self.explain())
        self.audit_export()
        print("Demo complete. You can also start the interactive shell with .run_shell() or API with .run_api_server().")

if __name__ == "__main__":
    class DummyMemory:
        def add_memory(self, *a, **k): pass
    memory = DummyMemory()
    loop = ThinkingLoop(memory)
    loop.demo()