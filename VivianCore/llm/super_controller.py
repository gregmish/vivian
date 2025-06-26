import threading
import time
import json
import csv
import random
import socketserver
import http.server
import os
import traceback
import base64
try:
    import yaml
except ImportError:
    yaml = None
try:
    import sqlite3
except ImportError:
    sqlite3 = None

# Dummy core modules; replace with real implementations as appropriate
class MemoryGraph:
    def __init__(self): self.nodes = {}; self.audit = []
    def add_memory(self, content, **kwargs): self.nodes[str(time.time())] = content
    def export(self): return {"nodes": self.nodes}
    def import_graph(self, data): self.nodes = data.get("nodes", {})
    def save(self, path="memory.json"): json.dump(self.export(), open(path,"w"))
    def load(self, path="memory.json"): self.import_graph(json.load(open(path)))
    def to_csv(self): return [["id", "content"]] + [[k, v] for k, v in self.nodes.items()]
    def to_yaml(self): return yaml.dump(self.export()) if yaml else "# YAML not available"
    def to_sqlite(self, path="memory.sqlite"):
        if not sqlite3: return
        conn = sqlite3.connect(path)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS memory (id TEXT, content TEXT)")
        c.executemany("INSERT INTO memory VALUES (?,?)", self.nodes.items())
        conn.commit(); conn.close()
    def clear(self): self.nodes = {}
    def recent(self, n=5): return list(self.nodes.items())[-n:]

class GoalLoop:
    def __init__(self, memory):
        self.goals = {}
        self.memory = memory
        self.audit = []
    def add_goal(self, desc, **kwargs):
        gid = str(time.time())
        self.goals[gid] = {"id":gid, "desc":desc, "status":"pending"}
        return gid
    def analytics(self): return {"goals": len(self.goals)}
    def summary(self): return self.analytics()
    def export(self): return {"goals": self.goals}
    def import_graph(self, data): self.goals = data.get("goals", {})
    def to_csv(self): return [["id","desc","status"]]+[[g["id"],g["desc"],g["status"]] for g in self.goals.values()]
    def to_yaml(self): return yaml.dump(self.export()) if yaml else "# YAML not available"
    def to_sqlite(self, path="goals.sqlite"):
        if not sqlite3: return
        conn = sqlite3.connect(path)
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS goals (id TEXT, desc TEXT, status TEXT)")
        c.executemany("INSERT INTO goals VALUES (?,?,?)", [(g["id"],g["desc"],g["status"]) for g in self.goals.values()])
        conn.commit(); conn.close()
    def health(self): return {"active": [g for g in self.goals.values() if g["status"]=="pending"]}
    def clear(self): self.goals = {}
    def explain_goal(self, gid): return self.goals.get(gid, {})

class PluginOrchestrator:
    def __init__(self, memory, goal_loop=None):
        self.plugins = {}
        self.memory = memory
        self.audit = []
        self.enabled = set()
    def register_plugin(self, name, fn, **meta): self.plugins[name]=fn; self.enabled.add(name)
    def call_plugin(self, name, *a, **k): return self.plugins[name](*a, **k) if name in self.enabled else None
    def run_all_plugins(self):
        for n in self.enabled:
            try: self.plugins[n]()
            except: pass
    def plugin_analytics(self): return {"plugins": list(self.enabled)}
    def explain_plugin(self, name): return {"enabled": name in self.enabled}
    def enable_plugin(self, name): self.enabled.add(name)
    def disable_plugin(self, name): self.enabled.discard(name)
    def load_plugin_from_code(self, name, code):
        exec(code, globals())
        self.plugins[name] = globals()[name]
        self.enabled.add(name)

class ThinkingLoop:
    def __init__(self, memory, goal_loop=None, plugin_orchestrator=None):
        self.memory = memory
        self.goal_loop = goal_loop
        self.plugin_orchestrator = plugin_orchestrator
        self.running = False
        self.persona = "default"
        self.audit = []
    def set_persona(self, name): self.persona = name
    def think(self): self.memory.add_memory(f"{self.persona} thought!")
    def start(self): self.running=True; threading.Thread(target=self._loop,daemon=True).start()
    def stop(self): self.running=False
    def _loop(self): 
        while self.running: self.think(); time.sleep(5)
    def explain(self): return {"persona": self.persona}

class BrainRouter:
    def __init__(self, memory, goal_loop, plugins):
        self.memory = memory
        self.goals = goal_loop
        self.plugins = plugins
        self.audit = []
        self.running = False
    def add_goal(self, desc, **k): return self.goals.add_goal(desc, **k)
    def run_once(self): self.goals.add_goal("auto-thought"); self.plugins.run_all_plugins()
    def start(self): self.running=True; threading.Thread(target=self._loop,daemon=True).start()
    def stop(self): self.running=False
    def _loop(self): 
        while self.running: self.run_once(); time.sleep(5)
    def summary(self): return {"goals": self.goals.analytics(), "plugins": self.plugins.plugin_analytics()}
    def explain(self): return {"memory": "memory state", "goals": self.goals.analytics()}

class SuperController:
    """
    SuperController:
    - High-level launcher that links all core systems (memory, goals, thinking, plugins, brain).
    - Entry point to build full cognitive runtime, manage lifecycle, security, audit, analytics, simulation, explainability, health check, scripting, triggers, API, shell, docs, and more.
    """

    def __init__(self):
        self.memory = MemoryGraph()
        self.goal_loop = GoalLoop(self.memory)
        self.plugins = PluginOrchestrator(self.memory, self.goal_loop)
        self.thinking = ThinkingLoop(self.memory, self.goal_loop, self.plugins)
        self.brain = BrainRouter(self.memory, self.goal_loop, self.plugins)
        self.running = False
        self.audit_log = []
        self.triggers = []
        self.tokens = {"admin":"secret"}  # user:token
        self.shell_thread = None
        self.api_thread = None
        self.macros = {}
        self.docs = self.build_docs()
        self.health_status = "OK"
        self.last_save = time.time()

    # --- Security and Permissions ---
    def check_token(self, token):
        return token in self.tokens.values()

    # --- Autosave/Restore ---
    def autosave(self, freq=60, path="supercontroller_autosave.json"):
        def save_loop():
            while self.running:
                self.save_all(path)
                self.last_save = time.time()
                time.sleep(freq)
        threading.Thread(target=save_loop, daemon=True).start()

    def save_all(self, path="supercontroller_autosave.json"):
        state = {
            "memory": self.memory.export(),
            "goals": self.goal_loop.export(),
            "plugins": list(self.plugins.plugins.keys())
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        self.audit_log.append({"event":"autosave","timestamp":time.time()})

    def load_all(self, path="supercontroller_autosave.json"):
        if not os.path.exists(path): return
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        self.memory.import_graph(state.get("memory", {}))
        self.goal_loop.import_graph(state.get("goals", {}))
        # Plugins: just names for demo, not code

    # --- Triggers ---
    def add_time_trigger(self, interval_sec, fn):
        def loop():
            while self.running:
                fn()
                time.sleep(interval_sec)
        threading.Thread(target=loop, daemon=True).start()
        self.triggers.append(("time", fn, interval_sec))

    def add_webhook_trigger(self, path, fn):
        # Only works if API server running; demo only
        self.triggers.append(("webhook", path, fn))

    # --- Export/Import ---
    def export_all(self, fmt="json"):
        if fmt=="json": return json.dumps({"memory": self.memory.export(), "goals": self.goal_loop.export()}, indent=2)
        elif fmt=="csv":
            mem = self.memory.to_csv(); goals = self.goal_loop.to_csv()
            return "\n".join([",".join(map(str,row)) for row in mem]) + "\n" + "\n".join([",".join(map(str,row)) for row in goals])
        elif fmt=="yaml" and yaml:
            return yaml.dump({"memory": self.memory.export(), "goals": self.goal_loop.export()})
        elif fmt=="sqlite" and sqlite3:
            self.memory.to_sqlite("memory.sqlite")
            self.goal_loop.to_sqlite("goals.sqlite")
            return "[sqlite files written]"
        else:
            return "# Unsupported format or missing dependency"

    def import_all(self, data, fmt="json"):
        if fmt=="json": 
            d = json.loads(data) if isinstance(data,str) else data
            self.memory.import_graph(d.get("memory", {}))
            self.goal_loop.import_graph(d.get("goals", {}))
        elif fmt=="yaml" and yaml:
            d = yaml.safe_load(data)
            self.memory.import_graph(d.get("memory", {}))
            self.goal_loop.import_graph(d.get("goals", {}))
        # CSV/SQLite not implemented for import

    # --- Visualization ---
    def ascii_graph(self):
        print("=== MEMORY GRAPH ===")
        for k,v in self.memory.nodes.items():
            print(f"* {k}: {str(v)[:40]}")
        print("=== GOALS GRAPH ===")
        for g in self.goal_loop.goals.values():
            print(f"* {g['id']}: {g['desc']} [{g['status']}]")
        print("====================")

    def timeline(self, n=20):
        print("=== TIMELINE ===")
        for k,v in list(self.memory.nodes.items())[-n:]:
            print(f"{k}: {str(v)[:60]}")

    # --- Scripting/Macro ---
    def add_macro(self, name, code):
        self.macros[name] = code

    def run_macro(self, name, *args, **kwargs):
        code = self.macros.get(name)
        if not code: return None
        try:
            exec(code, {"controller": self, "args": args, "kwargs": kwargs})
            self.audit_log.append({"event":"run_macro","name":name,"timestamp":time.time()})
            return "Macro run."
        except Exception as e:
            return str(e)

    # --- Self-Test and Health ---
    def health_check(self):
        status = "OK"
        if not self.memory.nodes: status = "WARN: memory empty"
        if not self.goal_loop.goals: status = "WARN: no goals"
        return {"status": status, "memory_nodes": len(self.memory.nodes), "goals": len(self.goal_loop.goals)}

    def notify(self, msg, level="info"):
        print(f"[{level.upper()}] {msg}")
        self.memory.add_memory(f"[NOTIFY] {msg}")
        self.audit_log.append({"event":"notify","msg":msg,"timestamp":time.time()})

    # --- Dynamic Plugin Loading ---
    def load_plugin(self, name, code):
        self.plugins.load_plugin_from_code(name, code)

    # --- Docs/Help ---
    def build_docs(self):
        return {
            "start_all": "Start all subsystems.",
            "stop_all": "Stop all subsystems.",
            "export_all": "Export all state in chosen format (json, csv, yaml, sqlite).",
            "import_all": "Import all state from data.",
            "ascii_graph": "Print ASCII graph of memory and goals.",
            "timeline": "Print timeline of recent memory.",
            "add_macro": "Add a macro (code string) under a name.",
            "run_macro": "Run a macro by name.",
            "health_check": "Show health check.",
            "notify": "Send notification (simulated).",
            "load_plugin": "Load a plugin from code string.",
            "help": "Show this help.",
            "shell": "Start interactive shell.",
            "api": "Start HTTP API server.",
        }

    # --- Main Lifecycle ---
    def start_all(self):
        self.running = True
        self.thinking.start()
        self.brain.start()
        self.autosave()
        self.memory.add_memory("[SuperController] All core systems started.", tags=["system", "start"])
        self.audit_log.append({"event": "start_all", "timestamp": time.time()})

    def stop_all(self):
        self.running = False
        self.thinking.stop()
        self.brain.stop()
        self.memory.add_memory("[SuperController] All core systems stopped.", tags=["system", "stop"])
        self.audit_log.append({"event": "stop_all", "timestamp": time.time()})

    def explain_all(self):
        return {
            "brain": self.brain.explain(),
            "thinking": self.thinking.explain(),
            "summary": self.brain.summary()
        }

    def analytics(self):
        return {
            "brain": self.brain.summary(),
            "plugin_analytics": self.plugins.plugin_analytics(),
            "goal_analytics": self.goal_loop.analytics(),
        }

    def audit_export(self, path="supercontroller_audit.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def simulate(self, n=3):
        self.brain.add_goal(f"Simulated BrainRouter goal {random.randint(1,999)}")
        self.thinking.think()
        self.audit_log.append({"event": "simulate", "steps": n, "timestamp": time.time()})

    # --- HTTP, Webhook, Shell ---
    def run_api_server(self, port=8781):
        controller = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body)
                    token = data.get("token")
                    if token and not controller.check_token(token):
                        self._respond({"error": "Invalid token"}); return
                    action = data.get("action")
                    if action == "start":
                        controller.start_all(); self._respond({"result": "started"})
                    elif action == "stop":
                        controller.stop_all(); self._respond({"result": "stopped"})
                    elif action == "explain":
                        self._respond(controller.explain_all())
                    elif action == "analytics":
                        self._respond(controller.analytics())
                    elif action == "simulate":
                        controller.simulate(data.get("steps", 3)); self._respond({"result": "ok"})
                    elif action == "audit":
                        controller.audit_export(data.get("path", "supercontroller_audit.json")); self._respond({"result": "ok"})
                    elif action == "export":
                        fmt = data.get("format", "json")
                        self._respond({"data": controller.export_all(fmt)})
                    elif action == "import":
                        fmt = data.get("format", "json")
                        controller.import_all(data.get("data",""), fmt=fmt)
                        self._respond({"result": "imported"})
                    elif action == "macro":
                        if data.get("run"): self._respond({"result": controller.run_macro(data.get("run"))})
                        elif data.get("add"): controller.add_macro(data.get("add"), data.get("code","")); self._respond({"result":"macro added"})
                    elif action == "notify":
                        controller.notify(data.get("msg",""), data.get("level","info"))
                        self._respond({"result":"notified"})
                    elif action == "health":
                        self._respond(controller.health_check())
                    elif action == "help":
                        self._respond(controller.docs)
                    elif action == "load_plugin":
                        controller.load_plugin(data.get("name"), data.get("code"))
                        self._respond({"result":"plugin loaded"})
                    else:
                        self._respond({"error": "Invalid action"})
                except Exception as e:
                    self._respond({"error": str(e), "trace": traceback.format_exc()})
            def do_GET(self):
                if self.path.startswith("/webhook/"):
                    trigger = self.path.split("/webhook/",1)[-1]
                    for typ,path,fn in controller.triggers:
                        if typ=="webhook" and path==trigger: fn()
                    self.send_response(200); self.end_headers(); self.wfile.write(b"Webhook OK")
                else:
                    self.send_response(200); self.end_headers(); self.wfile.write(b"SuperController API")
            def _respond(self, obj):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(obj).encode())
        def serve():
            with socketserver.TCPServer(("", port), Handler) as httpd:
                print(f"SuperController API running on port {port}")
                httpd.serve_forever()
        self.api_thread = threading.Thread(target=serve, daemon=True)
        self.api_thread.start()

    def interactive_shell(self):
        print("SuperController Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"): print("Exiting shell."); break
                elif cmd == "help": print(json.dumps(self.docs, indent=2))
                elif cmd == "start": self.start_all(); print("Started.")
                elif cmd == "stop": self.stop_all(); print("Stopped.")
                elif cmd.startswith("export"): print(self.export_all("json"))
                elif cmd.startswith("import "): self.import_all(cmd[7:]); print("Imported.")
                elif cmd == "ascii_graph": self.ascii_graph()
                elif cmd == "timeline": self.timeline()
                elif cmd.startswith("macro "): _,name,code = cmd.split(" ",2); self.add_macro(name, code); print("Macro added.")
                elif cmd.startswith("run_macro "): name = cmd.split(" ",1)[1]; print(self.run_macro(name))
                elif cmd == "health": print(self.health_check())
                elif cmd.startswith("notify "): self.notify(cmd[7:]); print("Notified.")
                elif cmd.startswith("load_plugin "):
                    _,name,code64 = cmd.split(" ",2)
                    code = base64.b64decode(code64).decode()
                    self.load_plugin(name, code)
                    print("Plugin loaded.")
                elif cmd == "shell": print("Already in shell.")
                elif cmd == "api": self.run_api_server(); print("API started.")
                elif cmd == "simulate": self.simulate(); print("Simulated.")
                elif cmd == "audit": self.audit_export(); print("Audit exported.")
                elif cmd == "explain": print(self.explain_all())
                elif cmd == "analytics": print(self.analytics())
                elif cmd == "summary": print(self.brain.summary())
                elif cmd.startswith("docs"): print(json.dumps(self.docs, indent=2))
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self.shell_thread = threading.Thread(target=self.interactive_shell, daemon=True)
        self.shell_thread.start()

    def demo(self):
        self.start_all()
        self.simulate(2)
        self.ascii_graph()
        self.timeline()
        print("Explain All:", self.explain_all())
        print("Analytics:", self.analytics())
        print("Health:", self.health_check())
        print("Docs:", self.docs)
        self.audit_export()
        print("Demo complete. You can also start the interactive shell with .run_shell() or API with .run_api_server().")

if __name__ == "__main__":
    controller = SuperController()
    controller.demo()