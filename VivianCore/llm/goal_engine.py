import time
import json
import threading
import queue
from typing import Dict, List, Optional, Callable, Any

class Goal:
    """
    AGI-Grade Goal Object:
    - Tracks description, priority, deadline, status, dependencies, context, progress, feedback, audit history.
    - Supports subgoals, dynamic priority, contextual adaptation, learning, serialization, rewards, explainability,
      risk, uncertainty, resource assignment, cancellation, audit/compliance, notification, owner, and graph/network features.
    """
    def __init__(
        self,
        description: str,
        priority: float = 1.0,
        deadline: Optional[float] = None,
        context: Optional[Dict] = None,
        dependencies: Optional[List[str]] = None,
        reward: float = 0.0,
        risk: float = 0.0,
        uncertainty: float = 0.0,
        resources: Optional[List[str]] = None,
        owner: Optional[str] = None
    ):
        self.description = description
        self.priority = priority
        self.created_at = time.time()
        self.completed = False
        self.deadline = deadline
        self.history: List[Dict] = []
        self.context = context or {}
        self.dependencies = dependencies or []
        self.reward = reward
        self.subgoals: List[str] = []
        self.progress: float = 0.0
        self.feedback: List[Dict] = []
        self.last_action: Optional[str] = None
        self.risk = risk
        self.uncertainty = uncertainty
        self.resources = resources or []
        self.cancelled = False
        self.audit_log: List[Dict] = []
        self.owner = owner
        self.notifications: List[str] = []
        self.simulation_data: List[Dict] = []

    def mark_completed(self, feedback: Optional[str] = None):
        self.completed = True
        self.progress = 1.0
        entry = {"timestamp": time.time(), "status": "completed"}
        if feedback:
            entry["feedback"] = feedback
        self.history.append(entry)
        self.audit_log.append({"timestamp": time.time(), "event": "completed", "feedback": feedback})

    def mark_cancelled(self, reason: Optional[str] = None):
        self.cancelled = True
        entry = {"timestamp": time.time(), "status": "cancelled"}
        if reason:
            entry["reason"] = reason
        self.history.append(entry)
        self.audit_log.append({"timestamp": time.time(), "event": "cancelled", "reason": reason})

    def log_action(self, action: str, details: Optional[Dict] = None):
        entry = {"timestamp": time.time(), "action": action}
        if details:
            entry["details"] = details
        self.last_action = action
        self.history.append(entry)
        self.audit_log.append({"timestamp": time.time(), "event": "action", "action": action, "details": details})

    def add_subgoal(self, subgoal_desc: str):
        self.subgoals.append(subgoal_desc)
        self.history.append({"timestamp": time.time(), "subgoal_added": subgoal_desc})
        self.audit_log.append({"timestamp": time.time(), "event": "subgoal_added", "subgoal": subgoal_desc})

    def add_dependency(self, dependency_desc: str):
        if dependency_desc not in self.dependencies:
            self.dependencies.append(dependency_desc)
            self.history.append({"timestamp": time.time(), "dependency_added": dependency_desc})
            self.audit_log.append({"timestamp": time.time(), "event": "dependency_added", "dependency": dependency_desc})

    def give_feedback(self, feedback: str, reward: float = 0.0):
        self.feedback.append({"timestamp": time.time(), "feedback": feedback, "reward": reward})
        self.reward += reward
        self.audit_log.append({"timestamp": time.time(), "event": "feedback", "feedback": feedback, "reward": reward})

    def set_progress(self, progress: float):
        self.progress = min(max(progress, 0.0), 1.0)
        self.history.append({"timestamp": time.time(), "progress": self.progress})
        self.audit_log.append({"timestamp": time.time(), "event": "progress", "progress": self.progress})

    def assign_resource(self, resource: str):
        if resource not in self.resources:
            self.resources.append(resource)
            self.history.append({"timestamp": time.time(), "resource_assigned": resource})
            self.audit_log.append({"timestamp": time.time(), "event": "resource_assigned", "resource": resource})

    def set_context(self, context: Dict):
        self.context.update(context)
        self.history.append({"timestamp": time.time(), "context_updated": context})
        self.audit_log.append({"timestamp": time.time(), "event": "context_updated", "context": context})

    def set_risk(self, risk: float):
        self.risk = risk
        self.history.append({"timestamp": time.time(), "risk_updated": risk})
        self.audit_log.append({"timestamp": time.time(), "event": "risk_updated", "risk": risk})

    def set_uncertainty(self, uncertainty: float):
        self.uncertainty = uncertainty
        self.history.append({"timestamp": time.time(), "uncertainty_updated": uncertainty})
        self.audit_log.append({"timestamp": time.time(), "event": "uncertainty_updated", "uncertainty": uncertainty})

    def notify(self, message: str):
        self.notifications.append(message)
        self.audit_log.append({"timestamp": time.time(), "event": "notification", "message": message})

    def simulate(self, steps: int = 5):
        # Simple simulation stub (progress increments, risk/uncertainty randomization)
        import random
        prog = self.progress
        for _ in range(steps):
            delta = random.uniform(0.05, 0.2)
            prog = min(prog + delta, 1.0)
            sim_risk = max(0.0, min(1.0, self.risk + random.uniform(-0.1, 0.1)))
            sim_unc = max(0.0, min(1.0, self.uncertainty + random.uniform(-0.1, 0.1)))
            self.simulation_data.append({
                "progress": prog,
                "risk": sim_risk,
                "uncertainty": sim_unc,
                "timestamp": time.time()
            })

    def rollback_last(self):
        if not self.history:
            return
        last = self.history.pop()
        self.audit_log.append({"timestamp": time.time(), "event": "rollback", "data": last})

    def to_dict(self) -> Dict:
        return {
            "description": self.description,
            "priority": self.priority,
            "created_at": self.created_at,
            "completed": self.completed,
            "deadline": self.deadline,
            "history": self.history,
            "context": self.context,
            "dependencies": self.dependencies,
            "reward": self.reward,
            "subgoals": self.subgoals,
            "progress": self.progress,
            "feedback": self.feedback,
            "last_action": self.last_action,
            "risk": self.risk,
            "uncertainty": self.uncertainty,
            "resources": self.resources,
            "cancelled": self.cancelled,
            "audit_log": self.audit_log,
            "owner": self.owner,
            "notifications": self.notifications,
            "simulation_data": self.simulation_data
        }

    @staticmethod
    def from_dict(d: Dict):
        goal = Goal(
            description=d["description"],
            priority=d.get("priority", 1.0),
            deadline=d.get("deadline"),
            context=d.get("context", {}),
            dependencies=d.get("dependencies", []),
            reward=d.get("reward", 0.0),
            risk=d.get("risk", 0.0),
            uncertainty=d.get("uncertainty", 0.0),
            resources=d.get("resources", []),
            owner=d.get("owner")
        )
        goal.created_at = d.get("created_at", time.time())
        goal.completed = d.get("completed", False)
        goal.history = d.get("history", [])
        goal.subgoals = d.get("subgoals", [])
        goal.progress = d.get("progress", 0.0)
        goal.feedback = d.get("feedback", [])
        goal.last_action = d.get("last_action")
        goal.cancelled = d.get("cancelled", False)
        goal.audit_log = d.get("audit_log", [])
        goal.notifications = d.get("notifications", [])
        goal.simulation_data = d.get("simulation_data", [])
        return goal

class GoalEngine:
    """
    AGI-Grade Goal Engine (maximal features, single file):
    - Goal decomposition, NL intake, dependency graph/network, audit/compliance, risk/uncertainty, notification,
      distributed sync, resource/capacity model, analytics, simulation, undo/rollback, plugin registry, shell, API.
    """
    def __init__(
        self,
        adaptive_priority: bool = False,
        feedback_fn: Optional[Callable[[Goal], float]] = None,
        human_confirm: Optional[Callable[[Goal], bool]] = None,
        resource_limit: Optional[int] = None,
        distributed_sync_fn: Optional[Callable[[Dict], None]] = None,
        auto_decompose_fn: Optional[Callable[[str], List[str]]] = None,
        goal_nl_intake_fn: Optional[Callable[[str], Dict]] = None,
        notify_fn: Optional[Callable[[str, str], None]] = None,
        escalation_thresholds: Optional[Dict[str, float]] = None,
        plugins: Optional[Dict[str, Callable]] = None
    ):
        self.goals: Dict[str, Goal] = {}
        self.adaptive_priority = adaptive_priority
        self.feedback_fn = feedback_fn
        self.human_confirm = human_confirm
        self.log: List[Dict] = []
        self.resource_limit = resource_limit
        self.distributed_sync_fn = distributed_sync_fn
        self.global_context: Dict = {}
        self.auto_decompose_fn = auto_decompose_fn
        self.goal_nl_intake_fn = goal_nl_intake_fn
        self.notify_fn = notify_fn
        self.escalation_thresholds = escalation_thresholds or {"risk": 0.7, "uncertainty": 0.7}
        self.plugins = plugins or {}
        self.command_queue = queue.Queue()
        self.shell_thread: Optional[threading.Thread] = None  # for REPL/Shell
        self.api_enabled = False

    def add_plugin(self, name: str, fn: Callable):
        self.plugins[name] = fn

    def call_plugin(self, name: str, *args, **kwargs):
        if name in self.plugins:
            return self.plugins[name](*args, **kwargs)
        else:
            raise ValueError(f"Plugin '{name}' not found")

    def add_goal(
        self,
        description: str,
        priority: float = 1.0,
        deadline: Optional[float] = None,
        context: Optional[Dict] = None,
        dependencies: Optional[List[str]] = None,
        risk: float = 0.0,
        uncertainty: float = 0.0,
        resources: Optional[List[str]] = None,
        owner: Optional[str] = None,
        auto_decompose: bool = True
    ):
        if self.goal_nl_intake_fn:
            params = self.goal_nl_intake_fn(description)
            description = params.get("description", description)
            priority = params.get("priority", priority)
            deadline = params.get("deadline", deadline)
            context = params.get("context", context)
            dependencies = params.get("dependencies", dependencies)
            risk = params.get("risk", risk)
            uncertainty = params.get("uncertainty", uncertainty)
            resources = params.get("resources", resources)
            owner = params.get("owner", owner)
        if description not in self.goals:
            goal = Goal(description, priority, deadline, context, dependencies, risk=risk, uncertainty=uncertainty, resources=resources, owner=owner)
            self.goals[description] = goal
            self.log.append({"timestamp": time.time(), "event": "goal_added", "goal": description})
            if self.auto_decompose_fn and auto_decompose:
                subgoals = self.auto_decompose_fn(description)
                for sub in subgoals:
                    self.add_subgoal(description, sub)
            if self.distributed_sync_fn:
                self.distributed_sync_fn(goal.to_dict())
            self.check_and_notify(goal)

    def complete_goal(self, description: str, feedback: Optional[str] = None):
        goal = self.goals.get(description)
        if goal and not goal.completed:
            if self.human_confirm and not self.human_confirm(goal):
                self.log.append({"timestamp": time.time(), "event": "completion_blocked", "goal": description})
                return False
            goal.mark_completed(feedback)
            self.log.append({"timestamp": time.time(), "event": "goal_completed", "goal": description})
            if self.feedback_fn:
                reward = self.feedback_fn(goal)
                goal.give_feedback(feedback or "auto", reward)
            if self.adaptive_priority:
                self.update_priorities()
            if self.distributed_sync_fn:
                self.distributed_sync_fn(goal.to_dict())
            return True
        return False

    def cancel_goal(self, description: str, reason: Optional[str] = None):
        goal = self.goals.get(description)
        if goal and not goal.completed and not goal.cancelled:
            goal.mark_cancelled(reason)
            self.log.append({"timestamp": time.time(), "event": "goal_cancelled", "goal": description, "reason": reason})
            if self.distributed_sync_fn:
                self.distributed_sync_fn(goal.to_dict())
            return True
        return False

    def log_goal_action(self, description: str, action: str, details: Optional[Dict] = None):
        goal = self.goals.get(description)
        if goal:
            goal.log_action(action, details)
            self.log.append({"timestamp": time.time(), "event": "goal_action", "goal": description, "action": action})

    def add_subgoal(self, parent_desc: str, subgoal_desc: str):
        if parent_desc in self.goals:
            self.goals[parent_desc].add_subgoal(subgoal_desc)
            self.add_goal(subgoal_desc)
            self.goals[subgoal_desc].add_dependency(parent_desc)
            self.log.append({"timestamp": time.time(), "event": "subgoal_added", "parent": parent_desc, "subgoal": subgoal_desc})

    def give_feedback(self, description: str, feedback: str, reward: float = 0.0):
        goal = self.goals.get(description)
        if goal:
            goal.give_feedback(feedback, reward)
            self.log.append({"timestamp": time.time(), "event": "goal_feedback", "goal": description, "feedback": feedback, "reward": reward})

    def set_progress(self, description: str, progress: float):
        goal = self.goals.get(description)
        if goal:
            goal.set_progress(progress)
            self.log.append({"timestamp": time.time(), "event": "goal_progress", "goal": description, "progress": progress})

    def assign_resource(self, description: str, resource: str):
        goal = self.goals.get(description)
        if goal:
            if self.resource_limit and len(goal.resources) >= self.resource_limit:
                self.log.append({"timestamp": time.time(), "event": "resource_limit_reached", "goal": description, "resource": resource})
                return False
            goal.assign_resource(resource)
            self.log.append({"timestamp": time.time(), "event": "resource_assigned", "goal": description, "resource": resource})
            return True
        return False

    def set_goal_context(self, description: str, context: Dict):
        goal = self.goals.get(description)
        if goal:
            goal.set_context(context)
            self.log.append({"timestamp": time.time(), "event": "goal_context_updated", "goal": description, "context": context})

    def set_goal_risk(self, description: str, risk: float):
        goal = self.goals.get(description)
        if goal:
            goal.set_risk(risk)
            self.log.append({"timestamp": time.time(), "event": "goal_risk_updated", "goal": description, "risk": risk})

    def set_goal_uncertainty(self, description: str, uncertainty: float):
        goal = self.goals.get(description)
        if goal:
            goal.set_uncertainty(uncertainty)
            self.log.append({"timestamp": time.time(), "event": "goal_uncertainty_updated", "goal": description, "uncertainty": uncertainty})

    def active_goals(self):
        return {
            desc: g for desc, g in self.goals.items()
            if not g.completed and not g.cancelled and all(self.goals.get(dep, Goal(dep)).completed for dep in g.dependencies)
        }

    def sorted_goals(self):
        if self.adaptive_priority:
            self.update_priorities()
        return sorted(
            self.active_goals().values(),
            key=lambda g: (
                -g.priority,
                g.deadline or float("inf"),
                g.progress,
                g.risk,
                g.uncertainty
            )
        )

    def update_priorities(self):
        now = time.time()
        for g in self.goals.values():
            if g.completed or g.cancelled:
                continue
            if g.deadline and now > g.deadline - 3600:
                g.priority += 0.2
            if g.feedback:
                avg_reward = sum(f["reward"] for f in g.feedback) / len(g.feedback)
                g.priority += 0.1 * avg_reward

    def get_goal_status(self, description: str):
        goal = self.goals.get(description)
        return goal.to_dict() if goal else None

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {desc: goal.to_dict() for desc, goal in self.goals.items()},
                f, indent=2
            )

    def load(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for desc, props in data.items():
                    self.goals[desc] = Goal.from_dict(props)
        except Exception:
            pass

    def batch_complete_goals(self, descriptions: List[str]):
        results = []
        for desc in descriptions:
            result = self.complete_goal(desc)
            results.append((desc, result))
        return results

    def analytical_stats(self):
        total = len(self.goals)
        completed = sum(1 for g in self.goals.values() if g.completed)
        cancelled = sum(1 for g in self.goals.values() if g.cancelled)
        avg_priority = sum(g.priority for g in self.goals.values()) / max(1, total)
        avg_reward = sum(g.reward for g in self.goals.values()) / max(1, total)
        avg_risk = sum(g.risk for g in self.goals.values()) / max(1, total)
        avg_uncertainty = sum(g.uncertainty for g in self.goals.values()) / max(1, total)
        return {
            "total_goals": total,
            "completed": completed,
            "active": total - completed - cancelled,
            "cancelled": cancelled,
            "avg_priority": avg_priority,
            "avg_reward": avg_reward,
            "avg_risk": avg_risk,
            "avg_uncertainty": avg_uncertainty,
        }

    def visualize(self):
        print("Goal Progress Visualization:")
        for desc, goal in self.goals.items():
            bar = "█" * int(goal.progress * 20)
            print(f"{desc[:30]:<30} [{bar:<20}] {goal.progress*100:.1f}% {'✔' if goal.completed else ''}{'✖' if goal.cancelled else ''}")

    def explain_goal(self, description: str):
        goal = self.goals.get(description)
        if not goal:
            return None
        timeline = []
        for entry in goal.history:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["timestamp"]))
            if "action" in entry:
                timeline.append(f"{ts}: Action - {entry['action']}")
            if "status" in entry:
                timeline.append(f"{ts}: Status - {entry['status']}")
            if "progress" in entry:
                timeline.append(f"{ts}: Progress - {entry['progress']*100:.1f}%")
            if "subgoal_added" in entry:
                timeline.append(f"{ts}: Subgoal - {entry['subgoal_added']}")
            if "dependency_added" in entry:
                timeline.append(f"{ts}: Dependency - {entry['dependency_added']}")
            if "resource_assigned" in entry:
                timeline.append(f"{ts}: Resource - {entry['resource_assigned']}")
            if "context_updated" in entry:
                timeline.append(f"{ts}: Context - {entry['context_updated']}")
            if "risk_updated" in entry:
                timeline.append(f"{ts}: Risk - {entry['risk_updated']}")
            if "uncertainty_updated" in entry:
                timeline.append(f"{ts}: Uncertainty - {entry['uncertainty_updated']}")
            if "cancelled" in entry:
                timeline.append(f"{ts}: Cancelled")
        return {
            "description": goal.description,
            "priority": goal.priority,
            "deadline": goal.deadline,
            "completed": goal.completed,
            "progress": goal.progress,
            "reward": goal.reward,
            "risk": goal.risk,
            "uncertainty": goal.uncertainty,
            "resources": goal.resources,
            "timeline": timeline,
            "audit_log": goal.audit_log
        }

    def distributed_sync(self, sync_fn: Callable[[Dict], None]):
        self.distributed_sync_fn = sync_fn

    def set_global_context(self, context: Dict):
        self.global_context = context

    def get_goal_graph(self):
        graph = {}
        for desc, goal in self.goals.items():
            graph[desc] = {
                "dependencies": goal.dependencies,
                "subgoals": goal.subgoals,
                "completed": goal.completed,
                "cancelled": goal.cancelled,
                "progress": goal.progress,
            }
        return graph

    def forecast_completion(self):
        forecast = []
        now = time.time()
        for g in self.sorted_goals():
            if g.completed or g.cancelled:
                continue
            time_left = (g.deadline - now) if g.deadline else float("inf")
            risk_penalty = g.risk * 10
            uncertainty_penalty = g.uncertainty * 10
            score = (1.0 - g.progress) * time_left + risk_penalty + uncertainty_penalty
            forecast.append((g.description, score))
        return sorted(forecast, key=lambda x: x[1])

    def audit_export(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.log + [
                {"goal": desc, "audit_log": goal.audit_log}
                for desc, goal in self.goals.items()
            ], f, indent=2)

    def check_and_notify(self, goal: Goal):
        if (goal.risk >= self.escalation_thresholds.get("risk", 0.7) or
            goal.uncertainty >= self.escalation_thresholds.get("uncertainty", 0.7)):
            msg = f"Escalation: Goal '{goal.description}' has high risk/uncertainty."
            goal.notify(msg)
            if self.notify_fn and goal.owner:
                self.notify_fn(goal.owner, msg)

    def simulate(self, steps: int = 5):
        for goal in self.goals.values():
            goal.simulate(steps)

    def rollback_goal(self, description: str):
        goal = self.goals.get(description)
        if goal:
            goal.rollback_last()
            self.log.append({"timestamp": time.time(), "event": "goal_rollback", "goal": description})

    def repl(self):
        print("GoalEngine Interactive Shell. Enter 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: add, complete, cancel, status, list, visualize, rollback, simulate, save, load, audit, graph, explain, forecast, plugins, call, exit")
                elif cmd.startswith("add"):
                    desc = cmd[4:].strip()
                    self.add_goal(desc)
                    print(f"Added goal: {desc}")
                elif cmd.startswith("complete"):
                    desc = cmd[9:].strip()
                    self.complete_goal(desc)
                    print(f"Completed: {desc}")
                elif cmd.startswith("cancel"):
                    desc = cmd[7:].strip()
                    self.cancel_goal(desc)
                    print(f"Cancelled: {desc}")
                elif cmd.startswith("status"):
                    desc = cmd[7:].strip()
                    print(self.get_goal_status(desc))
                elif cmd == "list":
                    print(list(self.goals.keys()))
                elif cmd == "visualize":
                    self.visualize()
                elif cmd.startswith("rollback"):
                    desc = cmd[9:].strip()
                    self.rollback_goal(desc)
                    print(f"Rolled back last action for: {desc}")
                elif cmd == "simulate":
                    self.simulate()
                    print("Simulated progress for all goals.")
                elif cmd.startswith("save"):
                    _, path = cmd.split(" ", 1)
                    self.save(path.strip())
                    print(f"Saved to {path.strip()}")
                elif cmd.startswith("load"):
                    _, path = cmd.split(" ", 1)
                    self.load(path.strip())
                    print(f"Loaded from {path.strip()}")
                elif cmd == "audit":
                    self.audit_export("audit_log.json")
                    print("Exported audit log to audit_log.json")
                elif cmd == "graph":
                    print(self.get_goal_graph())
                elif cmd.startswith("explain"):
                    desc = cmd[8:].strip()
                    print(self.explain_goal(desc))
                elif cmd == "forecast":
                    print(self.forecast_completion())
                elif cmd == "plugins":
                    print(f"Plugins: {list(self.plugins.keys())}")
                elif cmd.startswith("call"):
                    _, name, *args = cmd.split(" ")
                    print(self.call_plugin(name, *args))
                else:
                    print("Unknown command. Type 'help' for help.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self.shell_thread = threading.Thread(target=self.repl)
        self.shell_thread.start()

    def demo(self):
        print("=== GoalEngine AGI Demo ===")
        self.add_goal("Write report", priority=1.0, deadline=time.time() + 3600, risk=0.2, owner="gregmish")
        self.add_goal("Send email", priority=0.9, risk=0.1, owner="gregmish")
        self.add_goal("Book meeting", priority=0.7, dependencies=["Send email"], risk=0.8, owner="gregmish", uncertainty=0.8)
        self.log_goal_action("Write report", "Started outline")
        self.set_progress("Write report", 0.2)
        self.give_feedback("Write report", "Good start", reward=0.1)
        self.complete_goal("Send email")
        self.add_subgoal("Write report", "Research topic")
        self.set_progress("Research topic", 0.5)
        self.assign_resource("Write report", "VivianAgent-1")
        self.set_goal_context("Write report", {"user": "gregmish"})
        self.set_goal_risk("Book meeting", 0.8)
        self.set_goal_uncertainty("Book meeting", 0.8)
        self.cancel_goal("Book meeting", reason="User requested cancellation")
        self.simulate(steps=3)
        print("Active goals sorted:", [g.description for g in self.sorted_goals()])
        self.visualize()
        print("Analytical stats:", self.analytical_stats())
        print("Explain goal 'Write report':", self.explain_goal("Write report"))
        print("Goal graph/network:", self.get_goal_graph())
        print("Forecasted completions:", self.forecast_completion())
        self.audit_export("audit_log.json")
        print("Demo complete. You can also start the interactive shell with .run_shell()")

if __name__ == "__main__":
    engine = GoalEngine(adaptive_priority=True)
    engine.demo()