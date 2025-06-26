import time
import json
import threading

class CommandPipeline:
    """
    AGI-Grade CommandPipeline:
    - Receives commands from voice, shell, script, or API.
    - Passes them through parsing, validation, permissions, routing, and execution.
    - Records command history, arguments, return values, errors, and audit trail.
    - Supports command help/metadata, macros, scheduling, undo, and dynamic registration.
    """

    def __init__(self, controller, user="system"):
        self.controller = controller
        self.history = []
        self.user = user
        self.audit_log = []
        self.macros = {}
        self.scheduled = []
        self.permissions = {"system": {"*"}}  # user: set of allowed commands, '*' means all
        self.commands = {
            "start": (self.controller.start_all, "Start all subsystems."),
            "stop": (self.controller.stop_all, "Stop all subsystems."),
            "health": (self.controller.health_check, "Return system health status."),
            "explain": (self.controller.explain_all, "Explain system state."),
            "simulate": (self.controller.simulate, "Run a simulation step."),
            "audit": (self.controller.audit_export, "Export audit log."),
            "notify": (lambda *a, **k: self.controller.notify("Manual trigger"), "Send notification."),
            "analytics": (self.controller.analytics, "Get analytics summary."),
            "help": (self.help, "Show help for commands."),
            "history": (self.get_history, "Show recent command history."),
            "macro": (self.run_macro, "Run a macro by name."),
            "schedule": (self.schedule_command, "Schedule a command to run later."),
            "undo": (self.undo, "Undo the last command."),
            "add_macro": (self.add_macro, "Add a macro by name and code."),
            "list_macros": (self.list_macros, "List defined macros."),
        }
        self.undo_stack = []
        self.running = False
        self.scheduler_thread = None

    def run_command(self, cmd, *args, **kwargs):
        """Parse, validate, authorize, and execute a command string."""
        try:
            timestamp = time.time()
            base, *rest = cmd.strip().split(" ")
            args = args or rest
            allowed = self.permissions.get(self.user, set())
            if "*" not in allowed and base not in allowed:
                result = {"error": f"User '{self.user}' not permitted for '{base}'."}
            elif base in self.commands:
                fn, _ = self.commands[base]
                value = fn(*args, **kwargs)
                rec = {"timestamp": timestamp, "user": self.user, "command": cmd, "args": args, "result": value, "ok": True}
                self.history.append(rec)
                self.audit_log.append(rec)
                # Support undo for certain commands (simple demo)
                if base in ("start", "simulate", "notify"):
                    self.undo_stack.append((base, args, kwargs))
                return {"result": value or "OK"}
            else:
                result = {"error": f"Unknown command: {base}"}
                self.history.append({"timestamp": timestamp, "user": self.user, "command": cmd, "error": result["error"], "ok": False})
                self.audit_log.append(self.history[-1])
                return result
        except Exception as e:
            rec = {"timestamp": time.time(), "user": self.user, "command": cmd, "error": str(e), "ok": False}
            self.history.append(rec)
            self.audit_log.append(rec)
            return {"error": str(e)}

    def add_custom_command(self, name, fn, helpstr="(no description)"):
        self.commands[name] = (fn, helpstr)

    def get_history(self, n=10):
        return self.history[-n:]

    def help(self, *args):
        """Return help for all or specific commands."""
        if args:
            base = args[0]
            if base in self.commands:
                return {base: self.commands[base][1]}
            return {base: "Unknown command"}
        return {k: v[1] for k, v in self.commands.items()}

    def add_macro(self, name, code):
        """Add a macro (Python code string) to the macro registry."""
        self.macros[name] = code
        self.audit_log.append({"event":"add_macro","name":name,"timestamp":time.time()})
        return f"Macro '{name}' added."

    def run_macro(self, name, *args, **kwargs):
        """Execute a macro by name."""
        code = self.macros.get(name)
        if not code:
            return f"Macro '{name}' not found."
        try:
            exec(code, {"pipeline": self, "args": args, "kwargs": kwargs, "controller": self.controller})
            self.audit_log.append({"event":"run_macro","name":name,"timestamp":time.time()})
            return f"Macro '{name}' executed."
        except Exception as e:
            self.audit_log.append({"event":"macro_error","name":name,"error":str(e),"timestamp":time.time()})
            return f"Macro '{name}' error: {e}"

    def list_macros(self):
        return list(self.macros.keys())

    def schedule_command(self, cmd, delay_sec=10, *args, **kwargs):
        """Schedule a command to run after delay_sec seconds."""
        def runner():
            time.sleep(delay_sec)
            self.run_command(cmd, *args, **kwargs)
        t = threading.Thread(target=runner, daemon=True)
        t.start()
        self.scheduled.append({"cmd": cmd, "delay_sec": delay_sec, "time": time.time()})
        self.audit_log.append({"event":"schedule_command","cmd":cmd,"delay_sec":delay_sec,"timestamp":time.time()})
        return f"Command '{cmd}' scheduled in {delay_sec}s."

    def start_scheduler(self):
        """Start periodic scheduler for scheduled commands (if needed)."""
        self.running = True
        def loop():
            while self.running:
                now = time.time()
                for item in list(self.scheduled):
                    if item["time"] + item["delay_sec"] <= now:
                        self.run_command(item["cmd"])
                        self.scheduled.remove(item)
                time.sleep(1)
        self.scheduler_thread = threading.Thread(target=loop, daemon=True)
        self.scheduler_thread.start()

    def stop_scheduler(self):
        self.running = False

    def undo(self):
        """Undo the last undoable command."""
        if not self.undo_stack:
            return "Nothing to undo."
        base, args, kwargs = self.undo_stack.pop()
        # Simple demo: just record the undo, real undo logic would be more complex
        self.audit_log.append({"event":"undo","command":base,"timestamp":time.time()})
        return f"Undo of '{base}' recorded."

    def export_history(self, path="command_history.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2)

    def audit_export(self, path="command_audit.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def set_permissions(self, user, allowed):
        """Set allowed commands for a user."""
        self.permissions[user] = set(allowed)
        return f"Permissions for {user} set."

    def explain_last(self):
        if not self.history:
            return "No command run."
        return self.history[-1]

    def shell(self):
        print("CommandPipeline Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print(json.dumps(self.help(), indent=2))
                elif cmd.startswith("run "):
                    print(self.run_command(cmd[4:]))
                elif cmd == "history":
                    print(self.get_history())
                elif cmd.startswith("macro "):
                    parts = cmd.split(" ", 2)
                    if len(parts) == 3:
                        name, code = parts[1], parts[2]
                        print(self.add_macro(name, code))
                elif cmd.startswith("run_macro "):
                    name = cmd.split(" ", 1)[1]
                    print(self.run_macro(name))
                elif cmd == "list_macros":
                    print(self.list_macros())
                elif cmd.startswith("schedule "):
                    parts = cmd.split(" ", 2)
                    if len(parts) >= 3:
                        cmd_to_run, delay = parts[1], int(parts[2])
                        print(self.schedule_command(cmd_to_run, delay))
                elif cmd == "undo":
                    print(self.undo())
                elif cmd == "explain_last":
                    print(self.explain_last())
                else:
                    print(self.run_command(cmd))
            except Exception as e:
                print(f"Error: {e}")

# Demo usage
if __name__ == "__main__":
    class DummyController:
        def start_all(self): print("Started."); return "Started"
        def stop_all(self): print("Stopped."); return "Stopped"
        def health_check(self): return {"status":"ok"}
        def explain_all(self): return {"explain":"test"}
        def simulate(self): print("Simulated."); return "Simulated"
        def audit_export(self): print("Audit exported."); return "Audit exported"
        def notify(self, msg): print(f"Notify: {msg}"); return "Notified"
        def analytics(self): return {"analytics":"ok"}
    pipeline = CommandPipeline(DummyController())
    pipeline.shell()