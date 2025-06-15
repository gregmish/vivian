import logging
import json
import datetime
from typing import List, Dict, Any, Optional, Callable, Union
import threading
from pathlib import Path

PLANNER_DIR = Path("task_plans")
PLANNER_DIR.mkdir(exist_ok=True)

def current_time() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

class NotificationStub:
    def send(self, msg: str):
        logging.info(f"[Notification] {msg}")

class LLMStub:
    def refine_steps(self, steps: List[str], instruction: str) -> List[str]:
        # Placeholder: integrate with an LLM for advanced decomposition/suggestions
        return steps

    def suggest_improvements(self, plan: List[Dict[str, Any]], feedback: str) -> List[str]:
        # Placeholder: use LLM to suggest alternate or improved plan steps
        return []

    def summarize_plan(self, plan: List[Dict[str, Any]]) -> str:
        # Placeholder: LLM summary of the plan
        return f"Plan with {len(plan)} steps."

    def auto_classify(self, steps: List[str]) -> List[str]:
        # Placeholder: LLM classification of topics/categories
        return ["general" for _ in steps]

    def auto_merge(self, plan1: List[Dict[str, Any]], plan2: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Placeholder: LLM auto-merge of two plans
        return plan1 + plan2

class TaskPlanner:
    """
    Ultra-advanced, self-evolving task planner.
    Features:
    - Advanced step splitting (LLM-ready), event log, persistence, tagging, analytics, self-improvement, notifications, versioning.
    - Snapshots, timeline, feedback, auto-improvement, LLM classification, auto-merge, reminders, search, bulk update, export/import, plugin hooks.
    """
    def __init__(self, user: str = "default", notifier: Optional[Any] = None, llm: Optional[Any] = None):
        self.user = user
        self.plan: List[Dict[str, Any]] = []
        self.plan_meta: Dict[str, Any] = {}
        self.plan_file = PLANNER_DIR / f"plan_{self.user}.json"
        self.history_file = PLANNER_DIR / f"plan_history_{self.user}.json"
        self.event_log: List[Dict[str, Any]] = []
        self.snapshots_dir = PLANNER_DIR / "snapshots"
        self.snapshots_dir.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.notifier = notifier or NotificationStub()
        self.llm = llm or LLMStub()
        self.plugins: List[Callable[[str, Dict[str, Any]], None]] = []
        self.load_plan()
        self.load_history()

    # ---------- Plan Generation & Refinement ----------

    def generate_plan(self, instruction: str, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        logging.info(f"[Planner] Generating plan for instruction: {instruction}")
        with self.lock:
            self.plan = []
            raw_steps = self._advanced_split(instruction)
            categories = self.llm.auto_classify(raw_steps)
            steps = self.llm.refine_steps(raw_steps, instruction)
            for idx, (step, category) in enumerate(zip(steps, categories)):
                self.plan.append({
                    "id": idx + 1,
                    "action": step,
                    "status": "pending",
                    "created": current_time(),
                    "tags": tags or [],
                    "category": category,
                    "history": []
                })
            self.plan_meta = {
                "instruction": instruction,
                "created": current_time(),
                "tags": tags or [],
                "version": 1,
                "feedback": [],
                "last_modified": current_time(),
                "completed": False,
                "reminders": [],
                "auto_classified": list(set(categories))
            }
            self._log_event("generate_plan", {"instruction": instruction, "steps": steps, "categories": categories})
            self.save_plan()
            self._notify_plugins("plan_generated", {"plan": self.plan, "meta": self.plan_meta})
            return self.plan

    def _advanced_split(self, text: str) -> List[str]:
        delimiters = [".", ";", " and then ", " then ", " next ", "\n", "•", "-", "→"]
        steps = [text]
        for delim in delimiters:
            temp = []
            for s in steps:
                temp.extend(s.split(delim))
            steps = temp
        steps = [s.strip(" .;-→") for s in steps if s.strip(" .;-→")]
        return steps

    # ---------- Plan Management ----------

    def update_step_status(self, step_id: int, status: str):
        with self.lock:
            for step in self.plan:
                if step["id"] == step_id:
                    step["status"] = status
                    step["history"].append({"status": status, "time": current_time()})
                    self.plan_meta["last_modified"] = current_time()
                    self._log_event("update_step_status", {"step_id": step_id, "status": status})
                    self.save_plan()
                    if status == "completed":
                        self._check_plan_completion()
                    self._notify_plugins("step_status_updated", {"step": step})
                    break

    def _check_plan_completion(self):
        if all(step["status"] == "completed" for step in self.plan):
            self.plan_meta["completed"] = True
            self._log_event("plan_completed", {})
            self.notifier.send(f"Plan for user {self.user} completed!")
            self.save_plan()
            self._notify_plugins("plan_completed", {"plan": self.plan})

    def add_tag(self, tag: str):
        with self.lock:
            self.plan_meta.setdefault("tags", []).append(tag)
            for step in self.plan:
                step.setdefault("tags", []).append(tag)
            self.plan_meta["last_modified"] = current_time()
            self._log_event("add_tag", {"tag": tag})
            self.save_plan()
            self._notify_plugins("tag_added", {"tag": tag})

    def add_feedback(self, feedback: str):
        with self.lock:
            self.plan_meta.setdefault("feedback", []).append({"text": feedback, "time": current_time()})
            self._log_event("feedback", {"feedback": feedback})
            self.save_plan()
            improvements = self.llm.suggest_improvements(self.plan, feedback)
            if improvements:
                self.notifier.send(f"Improvement suggestions: {improvements}")
                self._notify_plugins("improvement_suggested", {"improvements": improvements})

    def get_plan(self) -> List[Dict[str, Any]]:
        return self.plan

    def get_plan_meta(self) -> Dict[str, Any]:
        return self.plan_meta

    # ---------- Persistence, Versioning, Snapshots ----------

    def save_plan(self):
        with self.lock:
            with open(self.plan_file, "w", encoding="utf-8") as f:
                json.dump({"plan": self.plan, "meta": self.plan_meta}, f, indent=2)
            self._save_snapshot()

    def load_plan(self):
        if self.plan_file.exists():
            try:
                with open(self.plan_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.plan = data.get("plan", [])
                    self.plan_meta = data.get("meta", {})
            except Exception as e:
                logging.error(f"[Planner] Failed to load plan: {e}")
                self.plan = []
                self.plan_meta = {}

    def _save_snapshot(self):
        snap_name = f"{self.user}_plan_{current_time().replace(':', '').replace('-', '')}.json"
        snap_path = self.snapshots_dir / snap_name
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump({"plan": self.plan, "meta": self.plan_meta}, f, indent=2)

    def list_snapshots(self) -> List[str]:
        return sorted([f.name for f in self.snapshots_dir.glob(f"{self.user}_plan_*.json")], reverse=True)

    def restore_snapshot(self, snapshot_name: str):
        snap_path = self.snapshots_dir / snapshot_name
        if snap_path.exists():
            with open(snap_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.plan = data.get("plan", [])
                self.plan_meta = data.get("meta", {})
            self.save_plan()

    # ---------- Event Log & History ----------

    def _log_event(self, action: str, details: Dict[str, Any]):
        event = {
            "time": current_time(),
            "action": action,
            "details": details
        }
        self.event_log.append(event)
        self.save_history()

    def save_history(self):
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.event_log, f, indent=2)

    def load_history(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.event_log = json.load(f)
            except Exception as e:
                logging.error(f"[Planner] Failed to load event history: {e}")
                self.event_log = []

    def plan_timeline(self) -> List[Dict[str, Any]]:
        return sorted(self.event_log, key=lambda e: e["time"])

    # ---------- Analytics & Self-Evolution ----------

    def step_stats(self) -> Dict[str, int]:
        stats = {"pending": 0, "in_progress": 0, "completed": 0}
        for step in self.plan:
            stats[step["status"]] = stats.get(step["status"], 0) + 1
        return stats

    def auto_suggest_improvements(self):
        """Suggest improvements if plan is stuck or feedback is negative."""
        if self.step_stats()["pending"] > 5:
            msg = "Many steps still pending—consider breaking down further or re-prioritizing."
            self.notifier.send(msg)
            self._log_event("auto_suggest", {"suggestion": msg})
            self._notify_plugins("auto_suggest", {"suggestion": msg})

    def summarize_plan(self) -> str:
        return self.llm.summarize_plan(self.plan)

    # ---------- Search/Tag/Export ----------

    def search_steps(self, keyword: str) -> List[Dict[str, Any]]:
        return [step for step in self.plan if keyword.lower() in step["action"].lower()]

    def search_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        return [step for step in self.plan if tag in step.get("tags", [])]

    def export_plan(self, export_path: Path) -> bool:
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump({"plan": self.plan, "meta": self.plan_meta}, f, indent=2)
            self._log_event("export_plan", {"to": str(export_path)})
            self._notify_plugins("exported", {"path": str(export_path)})
            return True
        except Exception as e:
            logging.error(f"[Planner] Failed to export plan: {e}")
            return False

    def import_plan(self, import_path: Path) -> bool:
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.plan = data.get("plan", [])
                self.plan_meta = data.get("meta", {})
            self.save_plan()
            self._log_event("import_plan", {"from": str(import_path)})
            self._notify_plugins("imported", {"path": str(import_path)})
            return True
        except Exception as e:
            logging.error(f"[Planner] Failed to import plan: {e}")
            return False

    # ---------- Bulk Status Updates ----------

    def bulk_update(self, status: str, filter_func: Optional[Callable[[Dict[str, Any]], bool]] = None):
        count = 0
        with self.lock:
            for step in self.plan:
                if filter_func is None or filter_func(step):
                    step["status"] = status
                    step["history"].append({"status": status, "time": current_time()})
                    count += 1
            if count:
                self.plan_meta["last_modified"] = current_time()
                self._log_event("bulk_update", {"status": status, "count": count})
                self.save_plan()
                self._notify_plugins("bulk_update", {"status": status, "count": count})

    # ---------- Reminders & Notifications ----------

    def add_reminder(self, message: str, when: str):
        self.plan_meta.setdefault("reminders", []).append({"message": message, "when": when})
        self._log_event("reminder_added", {"message": message, "when": when})
        self.save_plan()
        self._notify_plugins("reminder_added", {"message": message, "when": when})

    def check_reminders(self):
        now = current_time()
        reminders = self.plan_meta.get("reminders", [])
        due = [r for r in reminders if r["when"] <= now]
        for rem in due:
            self.notifier.send(f"Reminder: {rem['message']}")
            self._notify_plugins("reminder_due", rem)
        # Remove delivered reminders
        self.plan_meta["reminders"] = [r for r in reminders if r["when"] > now]
        if due:
            self.save_plan()

    # ---------- Merge/Import/Plugin/Extensibility ----------

    def merge_plan(self, other_plan_file: Path):
        if not other_plan_file.exists():
            logging.warning(f"[Planner] Cannot merge; file does not exist: {other_plan_file}")
            return
        with open(other_plan_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            other_plan = data.get("plan", [])
            merged = self.llm.auto_merge(self.plan, other_plan)
            self.plan = merged
            self.plan_meta["last_modified"] = current_time()
            self._log_event("merge_plan", {"from": str(other_plan_file)})
            self.save_plan()
            self._notify_plugins("plan_merged", {"from": str(other_plan_file)})

    def register_plugin(self, callback: Callable[[str, Dict[str, Any]], None]):
        self.plugins.append(callback)

    def _notify_plugins(self, event: str, data: Dict[str, Any]):
        for cb in self.plugins:
            try:
                cb(event, data)
            except Exception as e:
                logging.error(f"[Planner] Plugin error: {e}")

    # ---------- Self-Healing ----------

    def self_heal(self):
        """Attempt to heal/correct plan if corruption or error is detected."""
        try:
            self.load_plan()
            assert isinstance(self.plan, list)
            assert isinstance(self.plan_meta, dict)
        except Exception as e:
            logging.error(f"[Planner] Self-healing triggered: {e}")
            # Optionally, restore from snapshot
            snaps = self.list_snapshots()
            if snaps:
                self.restore_snapshot(snaps[0])
                self._log_event("self_healed", {"source": snaps[0]})

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    planner = TaskPlanner("vivian")
    plan = planner.generate_plan(
        "Write a blog post and then upload it to my website. Next, share on Twitter; then email my list."
    )
    for p in plan:
        print(f"[{p['status'].upper()}] Step {p['id']}: {p['action']}")
    print("Plan meta:", planner.get_plan_meta())
    print("Timeline:", planner.plan_timeline())
    print("Step stats:", planner.step_stats())
    print("Summary:", planner.summarize_plan())
    planner.auto_suggest_improvements()
    planner.add_feedback("This plan is too vague.")
    planner.add_tag("content")
    planner.bulk_update("in_progress", lambda step: "upload" in step["action"])
    planner.add_reminder("Check if blog post is live", (datetime.datetime.utcnow() + datetime.timedelta(minutes=1)).isoformat() + "Z")
    planner.check_reminders()