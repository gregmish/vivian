import traceback
import threading
import time
import json

class PluginOrchestrator:
    """
    AGI-Grade PluginOrchestrator:
    - Handles plugin registration, execution, coordination with memory and goals.
    - Semantic tagging, failure logging, audit, scheduling, dynamic enable/disable, plugin metadata, plugin analytics, plugin shell, HTTP API.
    - Thread-safe, extensible, reliable AGI plugin system.
    """

    def __init__(self, memory, goal_loop=None):
        self.memory = memory
        self.goal_loop = goal_loop
        self.plugins = {}
        self.audit_log = []
        self.plugin_meta = {}
        self.failed_plugins = set()
        self.lock = threading.Lock()
        self.scheduled_plugins = {}  # name -> (interval, last_run)
        self.running = False
        self.shell_thread = None
        self.api_thread = None

    def register_plugin(self, name, fn, description=None, tags=None, schedule_interval=None):
        with self.lock:
            self.plugins[name] = fn
            self.plugin_meta[name] = {
                "description": description or "",
                "tags": tags or [],
                "enabled": True,
                "registered": time.time(),
                "schedule_interval": schedule_interval,
                "last_run": None,
                "calls": 0,
                "failures": 0
            }
            if schedule_interval:
                self.scheduled_plugins[name] = (schedule_interval, time.time())
        self.memory.add_memory(f"[PluginOrchestrator] Registered plugin: {name}", tags=["plugin", "register"])
        self.audit_log.append({"event": "register_plugin", "name": name, "timestamp": time.time()})

    def unregister_plugin(self, name):
        with self.lock:
            self.plugins.pop(name, None)
            self.plugin_meta.pop(name, None)
            self.scheduled_plugins.pop(name, None)
        self.memory.add_memory(f"[PluginOrchestrator] Unregistered plugin: {name}", tags=["plugin", "unregister"])
        self.audit_log.append({"event": "unregister_plugin", "name": name, "timestamp": time.time()})

    def enable_plugin(self, name):
        with self.lock:
            if name in self.plugin_meta:
                self.plugin_meta[name]["enabled"] = True
        self.memory.add_memory(f"[PluginOrchestrator] Enabled plugin: {name}", tags=["plugin", "enable"])

    def disable_plugin(self, name):
        with self.lock:
            if name in self.plugin_meta:
                self.plugin_meta[name]["enabled"] = False
        self.memory.add_memory(f"[PluginOrchestrator] Disabled plugin: {name}", tags=["plugin", "disable"])

    def call_plugin(self, name, *args, **kwargs):
        with self.lock:
            if name not in self.plugins or not self.plugin_meta.get(name, {}).get("enabled", True):
                self.memory.add_memory(f"[PluginOrchestrator] Plugin '{name}' not found or disabled.", tags=["plugin", "error"])
                raise ValueError(f"Plugin '{name}' not registered or is disabled.")
            fn = self.plugins[name]
        try:
            result = fn(*args, **kwargs)
            with self.lock:
                self.plugin_meta[name]["calls"] += 1
                self.plugin_meta[name]["last_run"] = time.time()
            self.memory.add_memory(f"[PluginOrchestrator] Called plugin: {name}", context={"result": str(result)}, tags=["plugin", "call"])
            self.audit_log.append({"event": "call_plugin", "name": name, "timestamp": time.time(), "result": str(result)})
            return result
        except Exception as e:
            err = traceback.format_exc()
            with self.lock:
                self.plugin_meta[name]["failures"] += 1
                self.failed_plugins.add(name)
            self.memory.add_memory(f"[PluginOrchestrator] Error in plugin '{name}': {e}", context={"trace": err}, tags=["plugin", "error"])
            self.audit_log.append({"event": "plugin_error", "name": name, "timestamp": time.time(), "error": str(e), "trace": err})
            return None

    def run_all_plugins(self):
        with self.lock:
            plugins_to_run = [(name, fn) for name, fn in self.plugins.items() if self.plugin_meta.get(name, {}).get("enabled", True)]
        for name, fn in plugins_to_run:
            try:
                result = fn()
                with self.lock:
                    self.plugin_meta[name]["calls"] += 1
                    self.plugin_meta[name]["last_run"] = time.time()
                self.memory.add_memory(f"[PluginOrchestrator] Ran plugin: {name}", context={"result": str(result)}, tags=["plugin", "auto"])
                self.audit_log.append({"event": "run_plugin", "name": name, "timestamp": time.time(), "result": str(result)})
            except Exception as e:
                err = traceback.format_exc()
                with self.lock:
                    self.plugin_meta[name]["failures"] += 1
                    self.failed_plugins.add(name)
                self.memory.add_memory(f"[PluginOrchestrator] Failed plugin: {name} with {e}", context={"trace": err}, tags=["plugin", "fail"])
                self.audit_log.append({"event": "plugin_fail", "name": name, "timestamp": time.time(), "error": str(e), "trace": err})

    def run_scheduled_plugins(self):
        now = time.time()
        with self.lock:
            scheduled = [(name, interval, self.plugins[name]) for name, (interval, last_run) in self.scheduled_plugins.items()
                         if self.plugin_meta.get(name, {}).get("enabled", True) and now - last_run >= interval]
        for name, interval, fn in scheduled:
            try:
                result = fn()
                with self.lock:
                    self.plugin_meta[name]["calls"] += 1
                    self.plugin_meta[name]["last_run"] = time.time()
                    self.scheduled_plugins[name] = (interval, time.time())
                self.memory.add_memory(f"[PluginOrchestrator] Ran scheduled plugin: {name}", context={"result": str(result)}, tags=["plugin", "scheduled"])
                self.audit_log.append({"event": "run_scheduled_plugin", "name": name, "timestamp": time.time(), "result": str(result)})
            except Exception as e:
                err = traceback.format_exc()
                with self.lock:
                    self.plugin_meta[name]["failures"] += 1
                    self.failed_plugins.add(name)
                self.memory.add_memory(f"[PluginOrchestrator] Failed scheduled plugin: {name} with {e}", context={"trace": err}, tags=["plugin", "fail"])
                self.audit_log.append({"event": "scheduled_plugin_fail", "name": name, "timestamp": time.time(), "error": str(e), "trace": err})

    def run_forever(self, interval=5.0):
        self.running = True
        while self.running:
            self.run_all_plugins()
            self.run_scheduled_plugins()
            time.sleep(interval)

    def start(self, interval=5.0):
        self.shell_thread = threading.Thread(target=self.run_forever, args=(interval,), daemon=True)
        self.shell_thread.start()
        self.memory.add_memory("[PluginOrchestrator] Started background plugin loop.", tags=["plugin", "start"])
        self.audit_log.append({"event": "start", "timestamp": time.time()})

    def stop(self):
        self.running = False
        self.memory.add_memory("[PluginOrchestrator] Stopped background plugin loop.", tags=["plugin", "stop"])
        self.audit_log.append({"event": "stop", "timestamp": time.time()})

    def audit_export(self, path: str = "plugin_orchestrator_audit.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def plugin_analytics(self):
        with self.lock:
            return {
                name: {
                    "calls": meta["calls"],
                    "failures": meta["failures"],
                    "last_run": meta["last_run"],
                    "enabled": meta["enabled"],
                    "scheduled": name in self.scheduled_plugins,
                    "tags": meta.get("tags", []),
                }
                for name, meta in self.plugin_meta.items()
            }

    def explain_plugin(self, name):
        with self.lock:
            meta = self.plugin_meta.get(name, {})
            return {
                "name": name,
                "description": meta.get("description", ""),
                "tags": meta.get("tags", []),
                "calls": meta.get("calls", 0),
                "failures": meta.get("failures", 0),
                "last_run": meta.get("last_run", None),
                "enabled": meta.get("enabled", False),
                "scheduled": name in self.scheduled_plugins,
            }

    def interactive_shell(self):
        print("PluginOrchestrator Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: plugins, enable, disable, call, analytics, explain, audit, start, stop, exit")
                elif cmd == "plugins":
                    print(list(self.plugins.keys()))
                elif cmd.startswith("enable "):
                    name = cmd[7:]
                    self.enable_plugin(name)
                    print(f"Enabled: {name}")
                elif cmd.startswith("disable "):
                    name = cmd[8:]
                    self.disable_plugin(name)
                    print(f"Disabled: {name}")
                elif cmd.startswith("call "):
                    _, name, *args = cmd.split(" ")
                    print(self.call_plugin(name, *args))
                elif cmd == "analytics":
                    print(self.plugin_analytics())
                elif cmd.startswith("explain "):
                    name = cmd.split(" ", 1)[1]
                    print(self.explain_plugin(name))
                elif cmd == "audit":
                    self.audit_export()
                    print("Audit exported.")
                elif cmd == "start":
                    self.start()
                    print("Background loop started.")
                elif cmd == "stop":
                    self.stop()
                    print("Background loop stopped.")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self.shell_thread = threading.Thread(target=self.interactive_shell, daemon=True)
        self.shell_thread.start()

    def run_api_server(self, port: int = 8779):
        import http.server
        import socketserver

        orchestrator = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body)
                    action = data.get("action")
                    if action == "call":
                        result = orchestrator.call_plugin(data.get("name"), *data.get("args", []), **data.get("kwargs", {}))
                        self._respond({"result": result})
                    elif action == "analytics":
                        self._respond(orchestrator.plugin_analytics())
                    elif action == "audit":
                        orchestrator.audit_export(data.get("path", "plugin_orchestrator_audit.json"))
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
                print(f"PluginOrchestrator API running on port {port}")
                httpd.serve_forever()
        self.api_thread = threading.Thread(target=serve, daemon=True)
        self.api_thread.start()

    def demo(self):
        print("=== PluginOrchestrator Demo ===")

        def test_plugin():
            print("Test plugin executed!")
            return "ok"

        self.register_plugin("test", test_plugin, description="A test plugin.", tags=["test"])
        self.call_plugin("test")
        self.run_all_plugins()
        print("Analytics:", self.plugin_analytics())
        print("Explain:", self.explain_plugin("test"))
        self.audit_export()
        print("Demo complete. You can also start the interactive shell with .run_shell() or API with .run_api_server().")

if __name__ == "__main__":
    class DummyMemory:
        def add_memory(self, *a, **k): pass
    po = PluginOrchestrator(DummyMemory())
    po.demo()