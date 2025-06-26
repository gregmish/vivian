import time
import threading
import logging
import traceback
from typing import Callable, Dict, List, Any, Optional

class Scheduler:
    """
    Vivian's ultimate task scheduler.
    - Timed, interval, delayed, one-off, and recurring jobs
    - Pause/resume/enable/disable/cancel jobs
    - Job arguments, tags/groups, expiry, timeout, and result/error capture
    - Rolling global and per-job history
    - EventBus emits events on job run/complete/fail/timeout
    - Diagnostics, stats, admin commands, persistence hooks
    - Safe exception handling and clean shutdown
    - Ready for API/GUI/plugin integration
    """

    def __init__(self, config: Dict[str, Any], event_bus=None, memory=None, command_engine=None, user_manager=None, persistence_hook: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.config = config
        self.event_bus = event_bus
        self.memory = memory
        self.command_engine = command_engine
        self.user_manager = user_manager
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.running = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.job_history: List[Dict[str, Any]] = []
        self.history_limit = config.get("scheduler_history_limit", 200)
        self.stats = {
            "runs": 0, "fails": 0, "last_run": None, "last_error": None,
            "added": 0, "removed": 0, "last_added": None, "last_removed": None
        }
        self.admin_commands = {}
        self.persistence_hook = persistence_hook  # Optional function to persist jobs

    # --- Job Management ---

    def add_job(
        self,
        name: str,
        func: Callable[..., None],
        interval: Optional[float] = None,
        delay: Optional[float] = None,
        repeat: bool = False,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        expires: Optional[float] = None,
        enabled: bool = True,
        timeout: Optional[float] = None,
        description: str = "",
        user: Optional[str] = None,
        group: Optional[str] = None,
    ):
        """Add a job with all options."""
        with self.lock:
            now = time.time()
            next_run = now + (delay or interval or 0)
            job = {
                "func": func,
                "interval": interval,
                "delay": delay,
                "repeat": repeat,
                "args": args or [],
                "kwargs": kwargs or {},
                "tags": tags or [],
                "enabled": enabled,
                "paused": False,
                "next_run": next_run,
                "last_run": None,
                "last_result": None,
                "error": None,
                "history": [],
                "expires": now + expires if expires else None,
                "timeout": timeout,
                "added_at": now,
                "description": description,
                "user": user,
                "group": group,
            }
            self.jobs[name] = job
            self.stats["added"] += 1
            self.stats["last_added"] = now
            if self.event_bus:
                self.event_bus.publish("scheduler_job_added", data={"name": name, "job": job})
            if self.persistence_hook:
                try:
                    self.persistence_hook(self.serialize_jobs())
                except Exception as e:
                    logging.error(f"[Scheduler] Persistence hook error: {e}")

    def remove_job(self, name: str):
        with self.lock:
            job = self.jobs.pop(name, None)
            self.stats["removed"] += 1
            self.stats["last_removed"] = time.time()
            if self.event_bus:
                self.event_bus.publish("scheduler_job_removed", data={"name": name, "job": job})
            if self.persistence_hook:
                try:
                    self.persistence_hook(self.serialize_jobs())
                except Exception as e:
                    logging.error(f"[Scheduler] Persistence hook error: {e}")

    def pause_job(self, name: str):
        with self.lock:
            if name in self.jobs:
                self.jobs[name]["paused"] = True
                if self.event_bus:
                    self.event_bus.publish("scheduler_job_paused", data={"name": name})

    def resume_job(self, name: str):
        with self.lock:
            if name in self.jobs:
                self.jobs[name]["paused"] = False
                if self.event_bus:
                    self.event_bus.publish("scheduler_job_resumed", data={"name": name})

    def enable_job(self, name: str):
        with self.lock:
            if name in self.jobs:
                self.jobs[name]["enabled"] = True
                if self.event_bus:
                    self.event_bus.publish("scheduler_job_enabled", data={"name": name})

    def disable_job(self, name: str):
        with self.lock:
            if name in self.jobs:
                self.jobs[name]["enabled"] = False
                if self.event_bus:
                    self.event_bus.publish("scheduler_job_disabled", data={"name": name})

    def update_job(self, name: str, **updates):
        with self.lock:
            if name in self.jobs:
                self.jobs[name].update(updates)
                if self.event_bus:
                    self.event_bus.publish("scheduler_job_updated", data={"name": name, "updates": updates})

    def run_now(self, name: str):
        with self.lock:
            if name in self.jobs:
                self._run_job(name, self.jobs[name])

    def cancel_job(self, name: str):
        self.remove_job(name)

    def get_job(self, name: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.jobs.get(name)

    # --- Job Execution ---

    def _run_job(self, name: str, job: Dict[str, Any]):
        result = None
        error = None
        start = time.time()
        try:
            if job["timeout"]:
                # Run with timeout (advanced)
                def target():
                    nonlocal result
                    result = job["func"](*job["args"], **job["kwargs"])
                thread = threading.Thread(target=target)
                thread.start()
                thread.join(job["timeout"])
                if thread.is_alive():
                    error = f"Timeout after {job['timeout']}s"
                    if self.event_bus:
                        self.event_bus.publish("scheduler_job_timeout", data={"name": name})
            else:
                result = job["func"](*job["args"], **job["kwargs"])
            job["last_run"] = start
            job["last_result"] = result
            job["error"] = error
            self.stats["runs"] += 1
            self.stats["last_run"] = start
            if self.event_bus:
                self.event_bus.publish("scheduler_job_run", data={"name": name, "result": result, "error": error})
        except Exception as e:
            error = str(e)
            job["error"] = error
            job["traceback"] = traceback.format_exc()
            self.stats["fails"] += 1
            self.stats["last_error"] = error
            logging.error(f"[Scheduler] Job '{name}' error: {e}\n{job.get('traceback','')}")
            if self.event_bus:
                self.event_bus.publish("scheduler_job_error", data={"name": name, "error": error, "traceback": job.get("traceback")})
        # Record history
        entry = {
            "name": name,
            "time": start,
            "result": result,
            "error": error,
            "traceback": job.get("traceback"),
        }
        job["history"].append(entry)
        self.job_history.append(entry)
        if len(job["history"]) > 10:
            job["history"] = job["history"][-10:]
        if len(self.job_history) > self.history_limit:
            self.job_history = self.job_history[-self.history_limit:]

    def _loop(self):
        while self.running:
            now = time.time()
            with self.lock:
                to_remove = []
                for name, job in list(self.jobs.items()):
                    # Skip paused, disabled, or expired jobs
                    if not job["enabled"] or job["paused"]:
                        continue
                    if job.get("expires") and now > job["expires"]:
                        to_remove.append(name)
                        if self.event_bus:
                            self.event_bus.publish("scheduler_job_expired", data={"name": name})
                        continue
                    if job["next_run"] <= now:
                        self._run_job(name, job)
                        if job["repeat"] and job["interval"]:
                            job["next_run"] = now + job["interval"]
                        else:
                            to_remove.append(name)
                for name in to_remove:
                    self.remove_job(name)
            time.sleep(0.5)

    def start(self):
        if not self.running:
            self.running = True
            if not self.thread.is_alive():
                self.thread = threading.Thread(target=self._loop, daemon=True)
                self.thread.start()
            logging.info("[Scheduler] Started.")

    def stop(self):
        self.running = False

    # --- Query, Introspection, Diagnostics ---

    def list_jobs(self, filter_tags: Optional[List[str]] = None, group: Optional[str] = None, user: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            jobs = [
                {
                    "name": name,
                    "enabled": job["enabled"],
                    "paused": job["paused"],
                    "next_run": job["next_run"],
                    "last_run": job["last_run"],
                    "interval": job["interval"],
                    "repeat": job["repeat"],
                    "tags": job["tags"],
                    "error": job["error"],
                    "expires": job["expires"],
                    "description": job["description"],
                    "user": job["user"],
                    "group": job["group"],
                }
                for name, job in self.jobs.items()
                if (not filter_tags or any(t in job["tags"] for t in filter_tags))
                and (not group or job.get("group") == group)
                and (not user or job.get("user") == user)
            ]
            return jobs

    def get_job_history(self, name: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self.lock:
            if name in self.jobs:
                return self.jobs[name]["history"][-limit:]
            return []

    def get_stats(self):
        with self.lock:
            return self.stats.copy()

    def diagnostics(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "jobs": self.list_jobs(),
                "job_history": self.job_history[-20:],
                "stats": self.stats,
            }

    def serialize_jobs(self) -> Dict[str, Any]:
        """Serialize jobs for persistence (exclude func objects)."""
        with self.lock:
            result = {}
            for name, job in self.jobs.items():
                result[name] = {
                    k: v for k, v in job.items()
                    if k not in ("func", "history", "last_result", "traceback")  # exclude unserializable
                }
            return result

    def restore_jobs(self, job_defs: Dict[str, Any], func_resolver: Callable[[str], Callable]):
        """Restore jobs from serialized state, resolving functions via func_resolver(name:str)->callable."""
        with self.lock:
            for name, jobdef in job_defs.items():
                func = func_resolver(name)
                if func:
                    self.add_job(name, func, **{k: v for k, v in jobdef.items() if k != "func"})

    # --- Admin Commands ---

    def register_admin_command(self, cmd: str, func: Callable[[Dict[str, Any]], Any]):
        self.admin_commands[cmd] = func

    def run_admin_command(self, cmd: str, args: Dict[str, Any]) -> Any:
        if cmd in self.admin_commands:
            try:
                return self.admin_commands[cmd](args)
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": "Unknown command"}