from VivianCore.llm.memory_graph import MemoryGraph
from VivianCore.llm.goal_loop import GoalLoop
from VivianCore.llm.plugin_orchestrator import PluginOrchestrator
import threading
import time
import json

class BrainRouter:
    """
    AGI-Grade BrainRouter:
    - Ties memory, goals, plugins, and orchestrates high-level AGI cognition.
    - Central controller for thought flow, with analytics, explainability, audit, plugins, simulation, shell, and optional HTTP API.
    """

    def __init__(self, memory: MemoryGraph, goal_loop: GoalLoop = None, plugin_orchestrator: PluginOrchestrator = None):
        self.memory = memory
        self.goals = goal_loop if goal_loop else GoalLoop(memory)
        self.plugins = plugin_orchestrator if plugin_orchestrator else PluginOrchestrator(memory, self.goals)
        self.running = False
        self.audit_log = []
        self.shell_thread = None
        self.api_thread = None
        self.last_summary = {}
        self.last_explanation = ""
        self.meta_context = {}

    def add_goal(self, description: str, context=None, tags=None, priority=1.0, **kwargs):
        goal_id = self.goals.add_goal(description, context, tags, priority, **kwargs)
        self.memory.add_memory(f"[BrainRouter] Added goal: {description}", tags=["brainrouter", "goal"])
        self.audit_log.append({"event": "add_goal", "description": description, "goal_id": goal_id, "timestamp": time.time()})
        return goal_id

    def run_once(self):
        self.goals.run_once()
        self.plugins.run_all_plugins()
        self.audit_log.append({"event": "run_once", "timestamp": time.time()})

    def run_forever(self, interval=5.0):
        self.running = True
        while self.running:
            self.run_once()
            time.sleep(interval)

    def start(self, interval=5.0):
        self.shell_thread = threading.Thread(target=self.run_forever, args=(interval,), daemon=True)
        self.shell_thread.start()
        self.memory.add_memory("[BrainRouter] Started main loop.", tags=["brainrouter", "start"])
        self.audit_log.append({"event": "start", "timestamp": time.time()})

    def stop(self):
        self.running = False
        self.memory.add_memory("[BrainRouter] Stopped main loop.", tags=["brainrouter", "stop"])
        self.audit_log.append({"event": "stop", "timestamp": time.time()})

    def summary(self):
        goals_summary = self.goals.analytics() if hasattr(self.goals, "analytics") else {}
        summary = {
            "goals_total": len(self.goals.goals),
            "active_goals": len(self.goals.get_active_goals()),
            "plugins": list(self.plugins.plugins.keys()),
            "memory_nodes": len(self.memory.nodes),
            "goal_status": goals_summary,
        }
        self.last_summary = summary
        return summary

    def explain(self):
        goals_explanation = [self.goals.explain_goal(gid) for gid in list(self.goals.goals.keys())[:5]]
        plugins = list(self.plugins.plugins.keys())
        mem_example = []
        try:
            mem_example = [n for n in list(self.memory.nodes.values())[-5:]]
        except Exception:
            pass
        explanation = {
            "goals_explanation": goals_explanation,
            "plugins": plugins,
            "recent_memory": [n.to_dict() for n in mem_example] if mem_example else [],
        }
        self.last_explanation = explanation
        return explanation

    def audit_export(self, path: str = "brainrouter_audit.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def simulate(self, steps: int = 3):
        for i in range(steps):
            gid = self.add_goal(f"Simulated BrainRouter goal #{i+1}", tags=["sim"], priority=1.0)
            self.memory.add_memory(f"[Simulate] Created goal {gid}", tags=["sim", "goal"])
        self.audit_log.append({"event": "simulate", "steps": steps, "timestamp": time.time()})

    def plugin_register(self, name: str, fn):
        if hasattr(self.plugins, "register_plugin"):
            self.plugins.register_plugin(name, fn)
        elif hasattr(self.plugins, "register"):
            self.plugins.register(name, fn)

    def plugin_call(self, name: str, *args, **kwargs):
        if hasattr(self.plugins, "call_plugin"):
            return self.plugins.call_plugin(name, *args, **kwargs)
        elif hasattr(self.plugins, "call"):
            return self.plugins.call(name, *args, **kwargs)
        raise ValueError(f"No plugin call interface found for: {name}")

    def run_api_server(self, port: int = 8778):
        import http.server
        import socketserver

        router = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body)
                    action = data.get("action")
                    if action == "add_goal":
                        goal_id = router.add_goal(**data.get("goal", {}))
                        self._respond({"goal_id": goal_id})
                    elif action == "summary":
                        self._respond(router.summary())
                    elif action == "explain":
                        self._respond(router.explain())
                    elif action == "simulate":
                        router.simulate(data.get("steps", 3))
                        self._respond({"result": "ok"})
                    elif action == "audit":
                        router.audit_export(data.get("path", "brainrouter_audit.json"))
                        self._respond({"result": "ok"})
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
                print(f"BrainRouter API running on port {port}")
                httpd.serve_forever()
        self.api_thread = threading.Thread(target=serve, daemon=True)
        self.api_thread.start()

    def interactive_shell(self):
        print("BrainRouter Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: add, summary, explain, simulate, plugins, call, audit, start, stop, api, exit")
                elif cmd.startswith("add "):
                    desc = cmd[4:]
                    gid = self.add_goal(desc)
                    print(f"Added goal: {gid}")
                elif cmd == "summary":
                    print(self.summary())
                elif cmd == "explain":
                    print(self.explain())
                elif cmd.startswith("simulate"):
                    self.simulate()
                    print("Simulated.")
                elif cmd == "plugins":
                    print(f"Plugins: {list(self.plugins.plugins.keys())}")
                elif cmd.startswith("call "):
                    _, name, *args = cmd.split(" ")
                    print(self.plugin_call(name, *args))
                elif cmd == "audit":
                    self.audit_export()
                    print("Audit exported.")
                elif cmd == "start":
                    self.start()
                    print("Main loop started.")
                elif cmd == "stop":
                    self.stop()
                    print("Main loop stopped.")
                elif cmd == "api":
                    self.run_api_server()
                    print("API server started on port 8778.")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self.shell_thread = threading.Thread(target=self.interactive_shell, daemon=True)
        self.shell_thread.start()

    def demo(self):
        print("=== BrainRouter AGI Demo ===")
        gid1 = self.add_goal("Route thought to memory graph", tags=["routing"], priority=1.3)
        gid2 = self.add_goal("Trigger plugin", tags=["plugin"], priority=1.1)
        self.simulate(2)
        print("Summary:", self.summary())
        print("Explanation:", self.explain())
        self.audit_export()
        print("Demo complete. You can also start the interactive shell with .run_shell() or API with .run_api_server().")

if __name__ == "__main__":
    # For demonstration, use dummy MemoryGraph, GoalLoop, PluginOrchestrator if not available.
    class DummyMemoryGraph:
        def __init__(self):
            self.nodes = {}
        def add_memory(self, *a, **k): pass
    class DummyGoalLoop:
        def __init__(self, memory): self.goals = {}; self.memory = memory
        def add_goal(self, *a, **k):
            gid = str(uuid.uuid4())
            self.goals[gid] = {"id": gid, "desc": a[0] if a else "goal"}
            return gid
        def run_once(self): pass
        def analytics(self): return {"dummy": True}
        def get_active_goals(self): return []
        def explain_goal(self, goal_id): return {"id": goal_id}
    class DummyPluginOrchestrator:
        def __init__(self, memory, goals): self.plugins = {}
        def run_all_plugins(self): pass
        def register_plugin(self, name, fn): self.plugins[name] = fn
        def call_plugin(self, name, *a, **k): return self.plugins[name](*a, **k)
    memory = DummyMemoryGraph()
    goal_loop = DummyGoalLoop(memory)
    plugins = DummyPluginOrchestrator(memory, goal_loop)
    router = BrainRouter(memory, goal_loop, plugins)
    router.demo()