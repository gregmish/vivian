import threading
import time
import uuid
import json
from typing import Callable, Optional, List, Dict, Any, Set, Tuple

# Replace with your MemoryGraph implementation, or use a dummy for demonstration.
try:
    from VivianCore.llm.memory_graph import MemoryGraph
except ImportError:
    class MemoryGraph:
        def add_memory(self, *a, **k): pass

class Goal:
    """
    AGI-Grade Goal:
    - Rich metadata, subgoals, dependencies, dynamic priority, expiry, owner, resource assignment, audit, explainability.
    """
    def __init__(self, description: str, context: Optional[Dict] = None, tags: Optional[List[str]] = None,
                 priority: float = 1.0, expiry: Optional[float] = None, owner: Optional[str] = None,
                 resources: Optional[List[str]] = None, template: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.description = description
        self.context = context or {}
        self.tags = tags or []
        self.priority = priority
        self.status = "pending"  # pending, active, complete, failed, cancelled, blocked
        self.created = time.time()
        self.updated = self.created
        self.logs: List[str] = []
        self.audit: List[Dict] = []
        self.subgoals: Set[str] = set()
        self.dependencies: Set[str] = set()
        self.blocked_by: Set[str] = set()
        self.links: Set[str] = set()
        self.expiry = expiry
        self.owner = owner
        self.resources = resources or []
        self.template = template
        self.reward: float = 0.0
        self.risk: float = 0.0
        self.last_state_change: float = self.created

    def to_dict(self):
        return {
            "id": self.id,
            "description": self.description,
            "context": self.context,
            "tags": self.tags,
            "priority": self.priority,
            "status": self.status,
            "created": self.created,
            "updated": self.updated,
            "logs": self.logs,
            "audit": self.audit,
            "subgoals": list(self.subgoals),
            "dependencies": list(self.dependencies),
            "blocked_by": list(self.blocked_by),
            "links": list(self.links),
            "expiry": self.expiry,
            "owner": self.owner,
            "resources": self.resources,
            "template": self.template,
            "reward": self.reward,
            "risk": self.risk,
            "last_state_change": self.last_state_change
        }

    @staticmethod
    def from_dict(d: Dict):
        g = Goal(d["description"], d.get("context"), d.get("tags"), d.get("priority", 1.0),
                 d.get("expiry"), d.get("owner"), d.get("resources"), d.get("template"))
        g.id = d.get("id", str(uuid.uuid4()))
        g.status = d.get("status", "pending")
        g.created = d.get("created", time.time())
        g.updated = d.get("updated", g.created)
        g.logs = d.get("logs", [])
        g.audit = d.get("audit", [])
        g.subgoals = set(d.get("subgoals", []))
        g.dependencies = set(d.get("dependencies", []))
        g.blocked_by = set(d.get("blocked_by", []))
        g.links = set(d.get("links", []))
        g.reward = d.get("reward", 0.0)
        g.risk = d.get("risk", 0.0)
        g.last_state_change = d.get("last_state_change", g.created)
        return g

    def add_audit(self, event: str, details: Optional[Dict] = None):
        self.audit.append({
            "timestamp": time.time(),
            "event": event,
            "details": details or {}
        })

    def add_log(self, message: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.logs.append(f"[{ts}] {message}")
        self.add_audit("log", {"msg": message})

    def add_subgoal(self, goal_id: str):
        self.subgoals.add(goal_id)
        self.add_audit("subgoal_added", {"goal_id": goal_id})

    def add_dependency(self, goal_id: str):
        self.dependencies.add(goal_id)
        self.add_audit("dependency_added", {"goal_id": goal_id})

    def link_to(self, goal_id: str):
        self.links.add(goal_id)
        self.add_audit("linked", {"to": goal_id})

    def is_expired(self):
        return self.expiry is not None and time.time() > self.expiry

    def is_blocked(self):
        return bool(self.blocked_by)

    def can_activate(self):
        return not self.is_blocked() and self.status == "pending" and not self.is_expired()

class GoalLoop:
    """
    AGI-Grade GoalLoop:
    - Subgoals, decomposition, dependencies, graph export, resource assignment, reprioritization, audit, plugins, escalation, notifications, analytics, HTTP API, interactive shell, simulation, explainability.
    """
    def __init__(self, memory: MemoryGraph, interval: float = 5.0):
        self.memory = memory
        self.goals: Dict[str, Goal] = {}
        self.lock = threading.Lock()
        self.interval = interval
        self.running = False
        self.plugin_hooks: Dict[str, Callable[[Goal], None]] = {}
        self.audit_log: List[Dict] = []
        self.history: List[str] = []
        self.notifications: List[str] = []
        self.owner_permissions: Dict[str, Set[str]] = {}
        self.decompose_fn: Optional[Callable[[Goal], List[Dict]]] = None
        self.escalation_thresholds = {"risk": 0.7, "priority": 2.0}

    # ------------------ Goal CRUD and Relationships -------------------

    def add_goal(self, description: str, context: Optional[Dict] = None, tags: Optional[List[str]] = None,
                 priority: float = 1.0, expiry: Optional[float] = None, owner: Optional[str] = None,
                 resources: Optional[List[str]] = None, template: Optional[str] = None,
                 depends_on: Optional[List[str]] = None, auto_decompose: bool = True) -> str:
        goal = Goal(description, context, tags, priority, expiry, owner, resources, template)
        with self.lock:
            self.goals[goal.id] = goal
            self.history.append(goal.id)
            if depends_on:
                for dep in depends_on:
                    goal.add_dependency(dep)
                    if dep in self.goals:
                        self.goals[dep].add_subgoal(goal.id)
            if auto_decompose and self.decompose_fn:
                for sub in self.decompose_fn(goal):
                    sub_id = self.add_goal(**sub, auto_decompose=False)
                    goal.add_subgoal(sub_id)
                    self.goals[sub_id].add_dependency(goal.id)
        self.memory.add_memory(f"[Goal Added] {description}", context=context, tags=(tags or []) + ["goal"], importance=priority)
        goal.add_audit("added")
        self.audit_log.append({"event": "add_goal", "id": goal.id, "timestamp": goal.created})
        self._check_escalation(goal)
        return goal.id

    def complete_goal(self, goal_id: str):
        with self.lock:
            if goal_id in self.goals:
                g = self.goals[goal_id]
                g.status = "complete"
                g.updated = time.time()
                g.add_log(f"Completed at {g.updated}")
                g.add_audit("completed")
                self.memory.add_memory(f"[Goal Completed] {g.description}",
                                       context=g.context, tags=g.tags + ["goal", "complete"])
                self.audit_log.append({"event": "complete_goal", "id": goal_id, "timestamp": g.updated})

    def fail_goal(self, goal_id: str, reason: str = ""):
        with self.lock:
            if goal_id in self.goals:
                g = self.goals[goal_id]
                g.status = "failed"
                g.updated = time.time()
                g.add_log(f"Failed: {reason}")
                g.add_audit("failed", {"reason": reason})
                self.memory.add_memory(f"[Goal Failed] {g.description} | Reason: {reason}",
                                       context=g.context, tags=g.tags + ["goal", "failed"])
                self.audit_log.append({"event": "fail_goal", "id": goal_id, "timestamp": g.updated, "reason": reason})

    def cancel_goal(self, goal_id: str, reason: str = ""):
        with self.lock:
            if goal_id in self.goals:
                g = self.goals[goal_id]
                g.status = "cancelled"
                g.updated = time.time()
                g.add_log(f"Cancelled: {reason}")
                g.add_audit("cancelled", {"reason": reason})
                self.memory.add_memory(f"[Goal Cancelled] {g.description} | Reason: {reason}",
                                       context=g.context, tags=g.tags + ["goal", "cancelled"])
                self.audit_log.append({"event": "cancel_goal", "id": goal_id, "timestamp": g.updated, "reason": reason})

    def get_active_goals(self) -> List[Goal]:
        with self.lock:
            return [g for g in self.goals.values() if g.status == "pending" and not g.is_expired() and not g.is_blocked()]

    def get_blocked_goals(self) -> List[Goal]:
        with self.lock:
            return [g for g in self.goals.values() if g.status == "pending" and g.is_blocked()]

    def get_completed_goals(self) -> List[Goal]:
        with self.lock:
            return [g for g in self.goals.values() if g.status == "complete"]

    def get_failed_goals(self) -> List[Goal]:
        with self.lock:
            return [g for g in self.goals.values() if g.status == "failed"]

    def get_cancelled_goals(self) -> List[Goal]:
        with self.lock:
            return [g for g in self.goals.values() if g.status == "cancelled"]

    def find_goal_by_description(self, description: str) -> Optional[Goal]:
        with self.lock:
            for g in self.goals.values():
                if g.description == description:
                    return g
        return None

    # --------------------- Plugins, Hooks, Decomposition ----------------------

    def register_hook(self, name: str, fn: Callable[[Goal], None]):
        self.plugin_hooks[name] = fn

    def set_decompose_fn(self, fn: Callable[[Goal], List[Dict]]):
        self.decompose_fn = fn

    # --------------------- Main Loop and Processing -----------------------

    def run_once(self):
        active_goals = self.get_active_goals()
        for goal in sorted(active_goals, key=lambda g: -g.priority):
            self.memory.add_memory(f"[GoalLoop] Thinking about: {goal.description}", tags=goal.tags + ["goalloop"])
            goal.add_audit("thinking")
            for name, hook in self.plugin_hooks.items():
                try:
                    hook(goal)
                    goal.add_audit("plugin_hook", {"hook": name})
                except Exception as e:
                    self.fail_goal(goal.id, f"{name} failed: {e}")
                    goal.add_audit("plugin_failed", {"hook": name, "error": str(e)})

    def run_forever(self):
        self.running = True
        while self.running:
            self.run_once()
            self._update_blocked_statuses()
            self._decay_expired_goals()
            time.sleep(self.interval)

    def start(self):
        t = threading.Thread(target=self.run_forever, daemon=True)
        t.start()

    def stop(self):
        self.running = False

    # --------------------- Dependency and Blocked Logic --------------------

    def _update_blocked_statuses(self):
        with self.lock:
            for g in self.goals.values():
                g.blocked_by = {dep for dep in g.dependencies if self.goals.get(dep, None) and self.goals[dep].status != "complete"}
                if g.blocked_by and g.status == "pending":
                    g.status = "blocked"
                elif not g.blocked_by and g.status == "blocked":
                    g.status = "pending"

    def _detect_cycles(self) -> List[List[str]]:
        # Returns a list of cycles (each as a list of goal ids)
        def visit(nid, stack, visited, rec_stack, cycles):
            visited.add(nid)
            rec_stack.add(nid)
            for dep in self.goals[nid].dependencies:
                if dep not in self.goals: continue
                if dep not in visited:
                    visit(dep, stack + [dep], visited, rec_stack, cycles)
                elif dep in rec_stack:
                    cycles.append(stack + [dep])
            rec_stack.remove(nid)
        cycles = []
        with self.lock:
            for gid in self.goals:
                visit(gid, [gid], set(), set(), cycles)
        return cycles

    # --------------------- Expiry/Decay, Escalation, Notification -------------------

    def _decay_expired_goals(self):
        with self.lock:
            expired = [g for g in self.goals.values() if g.is_expired() and g.status == "pending"]
            for g in expired:
                self.cancel_goal(g.id, "Expired (auto-decay)")

    def _check_escalation(self, goal: Goal):
        if goal.risk >= self.escalation_thresholds["risk"] or goal.priority >= self.escalation_thresholds["priority"]:
            msg = f"[Escalation] Goal '{goal.description}' exceeds risk/priority threshold."
            self.notifications.append(msg)
            self.memory.add_memory(msg, context=goal.context, tags=goal.tags + ["escalation"])
            goal.add_audit("escalation", {"msg": msg})

    # --------------------- Dynamic Priority and Resource Assignment -----------------

    def reprioritize(self):
        # Example: increase priority for overdue or blocked goals, reduce for completed
        now = time.time()
        with self.lock:
            for g in self.goals.values():
                if g.status in ("pending", "blocked"):
                    if g.expiry and now > g.expiry - 300:
                        g.priority += 0.2
                    if len(g.blocked_by) > 0:
                        g.priority += 0.1 * len(g.blocked_by)
                elif g.status == "complete":
                    g.priority *= 0.95

    def assign_resource(self, goal_id: str, resource: str):
        with self.lock:
            if goal_id in self.goals:
                g = self.goals[goal_id]
                if resource not in g.resources:
                    g.resources.append(resource)
                    g.add_audit("resource_assigned", {"resource": resource})

    # --------------------- Export/Import, Audit, Analytics, Simulation ----------------

    def audit_export(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def export_graph(self) -> Dict:
        with self.lock:
            return {
                "goals": {gid: g.to_dict() for gid, g in self.goals.items()},
                "history": self.history
            }

    def import_graph(self, data: Dict):
        with self.lock:
            self.goals = {gid: Goal.from_dict(g) for gid, g in data.get("goals", {}).items()}
            self.history = data.get("history", [])

    def analytics(self) -> Dict:
        with self.lock:
            total = len(self.goals)
            completed = sum(1 for g in self.goals.values() if g.status == "complete")
            failed = sum(1 for g in self.goals.values() if g.status == "failed")
            cancelled = sum(1 for g in self.goals.values() if g.status == "cancelled")
            pending = sum(1 for g in self.goals.values() if g.status == "pending")
            blocked = sum(1 for g in self.goals.values() if g.status == "blocked")
            avg_priority = sum(g.priority for g in self.goals.values()) / max(1, total)
            avg_risk = sum(g.risk for g in self.goals.values()) / max(1, total)
            avg_time = sum((g.updated - g.created) for g in self.goals.values()) / max(1, total)
            most_blocked = max(self.goals.values(), key=lambda g: len(g.blocked_by), default=None)
            return {
                "total": total, "completed": completed, "failed": failed, "cancelled": cancelled,
                "pending": pending, "blocked": blocked, "avg_priority": avg_priority,
                "avg_risk": avg_risk, "avg_time": avg_time,
                "most_blocked": most_blocked.to_dict() if most_blocked else None
            }

    def simulate(self, n: int = 2):
        for i in range(n):
            gid = self.add_goal(f"Simulated goal #{len(self.goals)+1}", tags=["sim"], priority=1.0)
            self.memory.add_memory(f"[Simulate] Created goal {gid}", tags=["sim", "goal"])

    def undo_last(self):
        with self.lock:
            if self.history:
                last_id = self.history.pop()
                if last_id in self.goals:
                    g = self.goals.pop(last_id)
                    g.add_audit("undone")
                    self.memory.add_memory(f"[GoalLoop] Undone: {g.description}", tags=g.tags + ["undo"])
                    self.audit_log.append({"event": "undo_goal", "id": last_id, "timestamp": time.time()})
                    return g.to_dict()
        return None

    # --------------------- Explainability and Visualization --------------------

    def explain_goal(self, goal_id: str) -> Dict:
        g = self.goals.get(goal_id)
        if not g:
            return {}
        why = []
        if g.is_blocked():
            why.append(f"Blocked by: {list(g.blocked_by)}")
        if g.is_expired():
            why.append(f"Expired at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(g.expiry))}")
        if g.status == "failed":
            why.append("Marked as failed.")
        if g.status == "complete":
            why.append("Marked as complete.")
        return {
            "id": g.id,
            "description": g.description,
            "status": g.status,
            "priority": g.priority,
            "logs": g.logs,
            "audit": g.audit,
            "subgoals": list(g.subgoals),
            "dependencies": list(g.dependencies),
            "blocked_by": list(g.blocked_by),
            "links": list(g.links),
            "expiry": g.expiry,
            "owner": g.owner,
            "resources": g.resources,
            "why": why
        }

    def visualize(self, maxlen: int = 30):
        print("Goal Graph:")
        for gid, g in self.goals.items():
            status = f"{g.status.upper()}{' [EXPIRED]' if g.is_expired() else ''}"
            dep = ",".join(g.dependencies) if g.dependencies else "-"
            sub = ",".join(g.subgoals) if g.subgoals else "-"
            print(f"{gid[:8]}: {g.description[:maxlen]:<{maxlen}} | P={g.priority:.2f} | {status} | Dep: {dep} | Sub: {sub}")

    # --------------------- HTTP API (in-process, optional) -------------------

    def run_api_server(self, port: int = 8777):
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
                    if action == "add":
                        goal_id = loop.add_goal(**data.get("goal", {}))
                        self._respond({"goal_id": goal_id})
                    elif action == "complete":
                        loop.complete_goal(data.get("id"))
                        self._respond({"result": "ok"})
                    elif action == "fail":
                        loop.fail_goal(data.get("id"), data.get("reason", ""))
                        self._respond({"result": "ok"})
                    elif action == "cancel":
                        loop.cancel_goal(data.get("id"), data.get("reason", ""))
                        self._respond({"result": "ok"})
                    elif action == "analytics":
                        self._respond(loop.analytics())
                    elif action == "graph":
                        self._respond(loop.export_graph())
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
                print(f"GoalLoop API running on port {port}")
                httpd.serve_forever()
        threading.Thread(target=serve, daemon=True).start()

    # --------------------- Interactive Shell -------------------

    def interactive_shell(self):
        print("GoalLoop Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: add, complete, fail, cancel, active, blocked, completed, failed, cancelled, explain, simulate, analytics, undo, audit, graph, reprioritize, assign, visualize, plugins, call, api, exit")
                elif cmd.startswith("add "):
                    desc = cmd[4:]
                    gid = self.add_goal(desc)
                    print(f"Added: {gid}")
                elif cmd.startswith("complete "):
                    gid = cmd[9:]
                    self.complete_goal(gid)
                    print(f"Completed: {gid}")
                elif cmd.startswith("fail "):
                    args = cmd[5:].split(" ", 1)
                    gid = args[0]
                    reason = args[1] if len(args) > 1 else ""
                    self.fail_goal(gid, reason)
                    print(f"Failed: {gid}")
                elif cmd.startswith("cancel "):
                    args = cmd[7:].split(" ", 1)
                    gid = args[0]
                    reason = args[1] if len(args) > 1 else ""
                    self.cancel_goal(gid, reason)
                    print(f"Cancelled: {gid}")
                elif cmd == "active":
                    for g in self.get_active_goals():
                        print(g.to_dict())
                elif cmd == "blocked":
                    for g in self.get_blocked_goals():
                        print(g.to_dict())
                elif cmd == "completed":
                    for g in self.get_completed_goals():
                        print(g.to_dict())
                elif cmd == "failed":
                    for g in self.get_failed_goals():
                        print(g.to_dict())
                elif cmd == "cancelled":
                    for g in self.get_cancelled_goals():
                        print(g.to_dict())
                elif cmd.startswith("explain "):
                    gid = cmd[8:]
                    print(self.explain_goal(gid))
                elif cmd.startswith("simulate"):
                    self.simulate()
                    print("Simulated.")
                elif cmd == "analytics":
                    print(self.analytics())
                elif cmd == "undo":
                    print(self.undo_last())
                elif cmd == "audit":
                    self.audit_export("goalloop_audit.json")
                    print("Audit exported to goalloop_audit.json")
                elif cmd == "graph":
                    print(self.export_graph())
                elif cmd == "reprioritize":
                    self.reprioritize()
                    print("Reprioritized.")
                elif cmd.startswith("assign "):
                    args = cmd[7:].split(" ", 1)
                    gid = args[0]
                    resource = args[1] if len(args) > 1 else "unknown"
                    self.assign_resource(gid, resource)
                    print(f"Assigned {resource} to {gid}")
                elif cmd == "visualize":
                    self.visualize()
                elif cmd == "plugins":
                    print(f"Plugins: {list(self.plugin_hooks.keys())}")
                elif cmd.startswith("call "):
                    _, name, *args = cmd.split(" ")
                    print(self.plugin_hooks[name](*args))
                elif cmd.startswith("api"):
                    self.run_api_server()
                    print("API server started on port 8777")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        threading.Thread(target=self.interactive_shell, daemon=True).start()

    def demo(self):
        print("=== GoalLoop AGI Demo ===")
        gid1 = self.add_goal("Write documentation", tags=["writing"], priority=1.2)
        gid2 = self.add_goal("Fix bug #123", tags=["bugfix"], priority=1.5, depends_on=[gid1])
        gid3 = self.add_goal("Test feature", tags=["test"], priority=1.1)
        self.complete_goal(gid1)
        self.fail_goal(gid2, "Could not reproduce")
        self.simulate(2)
        self.visualize()
        print("Analytics:", self.analytics())
        print("Explain gid1:", self.explain_goal(gid1))
        print("Detected cycles:", self._detect_cycles())
        self.audit_export("goalloop_audit.json")
        print("Demo complete. You can also start the interactive shell with .run_shell() or API with .run_api_server().")

if __name__ == "__main__":
    # Replace with an actual MemoryGraph instance as needed.
    class DummyMemoryGraph:
        def add_memory(self, *a, **k): pass
    memory = DummyMemoryGraph()
    loop = GoalLoop(memory)
    loop.demo()