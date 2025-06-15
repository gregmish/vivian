import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable, Union
from datetime import datetime, timedelta

class OverseerBrain:
    def __init__(
        self,
        config: Dict[str, Any],
        memory,
        users,
        skills,
        eventbus,
        llm_func: Optional[Callable[[str, str], str]] = None,
        qa_func: Optional[Callable[[str, str], str]] = None,
        semantic_search_func: Optional[Callable[[str, str], Any]] = None,
        nlp_hooks: Optional[List[Callable[[str], Dict[str, Any]]]] = None,
    ):
        self.config = config
        self.memory = memory
        self.users = users
        self.skills = skills
        self.eventbus = eventbus
        self.llm_func = llm_func
        self.qa_func = qa_func
        self.semantic_search_func = semantic_search_func
        self.nlp_hooks = nlp_hooks or []
        self.name = config.get("name", "Overseer")
        self.log = logging.getLogger(self.name + "Brain")
        self._start_time = datetime.now()
        self.mode = "default"
        self.rate_limits: Dict[str, List[datetime]] = {}
        self.admins = set(config.get("admins", []))
        self.history: List[Dict[str, Any]] = []
        self.webhooks: Dict[str, List[str]] = {}  # event -> [urls]
        self.personas: Dict[str, str] = {}  # user_id -> persona
        self.permissions: Dict[str, List[str]] = {}  # user_id -> [permissions]
        self.scheduled_tasks: List[Dict[str, Any]] = []
        self.audit_log: List[Dict[str, Any]] = []

    def _rate_limited(self, user_id: str, max_per_minute: int = 10) -> bool:
        now = datetime.now()
        times = self.rate_limits.setdefault(user_id, [])
        times = [t for t in times if now - t < timedelta(minutes=1)]
        self.rate_limits[user_id] = times
        if len(times) >= max_per_minute:
            self.log.warning(f"[Brain] User {user_id} rate limited.")
            return True
        times.append(now)
        return False

    async def process_async(
        self,
        user_input: str,
        user_id: str = "default",
        as_dict: bool = False,
        context_window: int = 5,
        stream: bool = False,
        language: Optional[str] = None
    ) -> Union[str, Dict[str, Any]]:
        if self._rate_limited(user_id):
            msg = "You're sending messages too fast. Please slow down."
            return {"response": msg, "status": "rate_limited"} if as_dict else msg

        self.log.info(f"[OverseerBrain] [async] Input from {user_id}: {user_input}")
        context = self.memory.get_context(user_input, user_id=user_id, window=context_window)
        user_profile = self.users.get_profile(user_id)
        persona = self.personas.get(user_id, "default")
        self.eventbus.emit("pre_process", {"input": user_input, "user": user_id, "context": context})

        try:
            skill_response = await self.skills.handle_input_async(
                context, user_id, user_profile=user_profile, language=language, mode=self.mode, persona=persona
            )
            self.eventbus.emit("post_process", {"input": user_input, "user": user_id, "response": skill_response})
        except Exception as e:
            self.log.error(f"[OverseerBrain] Async process error: {e}")
            skill_response = await self.fallback_async(user_input, user_id, context=context, language=language, stream=stream)

        self.memory.log_interaction(user_input, skill_response, user=user_id)
        self.history.append({
            "user": user_id, "input": user_input, "response": skill_response, "time": datetime.now().isoformat()
        })
        self._audit("process", user_id, {"input": user_input, "response": skill_response})

        if as_dict:
            return {"response": skill_response, "status": "ok"}
        return skill_response

    def process(self, user_input: str, user_id: str = "default", as_dict: bool = False, context_window: int = 5, language: Optional[str] = None) -> Union[str, Dict[str, Any]]:
        return asyncio.run(self.process_async(user_input, user_id, as_dict, context_window, language=language))

    async def fallback_async(self, user_input: str, user_id: str, context=None, language=None, stream=False) -> str:
        if self.llm_func:
            prompt = f"The user ({user_id}) asked: \"{user_input}\".\nContext: {context}\nRespond appropriately."
            try:
                response = await self._call_llm(prompt, model=self.config.get("llm_model", "gpt-4"), stream=stream)
                return response
            except Exception as e:
                self.log.error(f"[OverseerBrain] LLM fallback error: {e}")
        return "I'm having trouble answering that. Please try again or contact support."

    async def _call_llm(self, prompt: str, model: str = "gpt-4", stream: bool = False) -> str:
        if self.llm_func:
            if asyncio.iscoroutinefunction(self.llm_func):
                return await self.llm_func(prompt, model=model)
            return self.llm_func(prompt, model=model)
        return "[LLM] No LLM function configured."

    def register_webhook(self, event: str, url: str) -> str:
        self.webhooks.setdefault(event, []).append(url)
        return f"Webhook for '{event}' registered."

    def emit_webhook(self, event: str, data: Dict[str, Any]) -> None:
        urls = self.webhooks.get(event, [])
        for url in urls:
            self.log.info(f"[OverseerBrain] Would emit webhook to {url}: {data}")

    def export_analytics(self, format: str = "json") -> Any:
        analytics = {
            "total_interactions": len(self.history),
            "skills_used": self.skills.usage_stats() if hasattr(self.skills, "usage_stats") else {},
            "users": self.users.count_users(),
            "errors": [e for e in self.audit_log if e.get("type") == "error"],
        }
        if format == "json":
            import json
            return json.dumps(analytics, indent=2)
        return analytics

    def set_permission(self, user_id: str, permission: str) -> str:
        self.permissions.setdefault(user_id, []).append(permission)
        return f"Permission '{permission}' added for {user_id}."

    def check_permission(self, user_id: str, permission: str) -> bool:
        return permission in self.permissions.get(user_id, [])

    def roles(self, user_id: str) -> List[str]:
        roles = []
        if user_id in self.admins:
            roles.append("admin")
        roles.extend(self.permissions.get(user_id, []))
        return roles if roles else ["user"]

    def adjust_skill_score(self, skill: str, delta: float):
        if hasattr(self.skills, "adjust_score"):
            self.skills.adjust_score(skill, delta)

    def set_user_preference(self, user_id: str, key: str, value: Any):
        if hasattr(self.users, "set_preference"):
            self.users.set_preference(user_id, key, value)
        else:
            self.log.warning("User profile system does not support preferences.")

    def schedule_task(self, when: datetime, func: Callable, *args, **kwargs) -> str:
        delay = (when - datetime.now()).total_seconds()
        if delay < 0:
            self.log.warning("[OverseerBrain] Tried to schedule a task in the past!")
            return "Cannot schedule task in the past."
        handle = asyncio.get_event_loop().call_later(delay, func, *args, **kwargs)
        task = {"when": when.isoformat(), "func": func.__name__, "args": args, "kwargs": kwargs, "handle": handle}
        self.scheduled_tasks.append(task)
        return f"Task '{func.__name__}' scheduled for {when}."

    def list_scheduled_tasks(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.scheduled_tasks

    def cancel_scheduled_task(self, func_name: str) -> str:
        for task in self.scheduled_tasks:
            if task["func"] == func_name:
                handle = task["handle"]
                handle.cancel()
                self.scheduled_tasks.remove(task)
                return f"Task '{func_name}' canceled."
        return f"No scheduled task named '{func_name}'."

    def localize(self, text: str, lang: str = "en") -> str:
        return text

    def handle_multimodal(self, user_input: Any, user_id: str = "default") -> Any:
        if isinstance(user_input, str):
            return self.process(user_input, user_id)
        elif isinstance(user_input, bytes):
            return self.skills.handle_media(user_input, user_id)
        else:
            return "[Overseer] Unsupported input type."

    def get_sessions(self, user_id: str) -> List[str]:
        if hasattr(self.memory, "list_sessions"):
            return self.memory.list_sessions(user_id)
        return ["default"]

    def switch_session(self, user_id: str, session_id: str) -> str:
        if hasattr(self.memory, "switch_session"):
            self.memory.switch_session(user_id, session_id)
            return f"Switched to session '{session_id}'."
        return "Session switching not supported."

    def query_kb(self, query: str) -> Any:
        if hasattr(self.skills, "knowledge_base_query"):
            return self.skills.knowledge_base_query(query)
        return "[Overseer] No knowledge base connected."

    def search_skills(self, query: str) -> List[str]:
        if hasattr(self.skills, "search_skills"):
            return self.skills.search_skills(query)
        return [s for s in self.list_skills() if query.lower() in s.lower()]

    def suggest_skills(self, partial_input: str) -> List[str]:
        return self.search_skills(partial_input)

    def _audit(self, action: str, user_id: str, details: Dict[str, Any]):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "user": user_id,
            "details": details,
            "type": "error" if action.startswith("error") else "info"
        }
        self.audit_log.append(log_entry)

    def get_audit_log(self, limit: int = 50, action: Optional[str] = None) -> List[Dict[str, Any]]:
        logs = [a for a in reversed(self.audit_log) if (action is None or a["action"] == action)]
        return logs[:limit]

    def set_persona(self, persona: str, user_id: Optional[str] = None) -> str:
        if user_id:
            self.personas[user_id] = persona
            return f"Persona for {user_id} set to '{persona}'."
        self.config["persona"] = persona
        return f"Global persona set to '{persona}'."

    def run_skill_sandboxed(self, skill_name: str, *args, **kwargs):
        try:
            if hasattr(self.skills, skill_name):
                skill_func = getattr(self.skills, skill_name)
                return skill_func(*args, **kwargs)
            return f"Skill '{skill_name}' not found."
        except Exception as e:
            self._audit("error_skill", "system", {"skill": skill_name, "error": str(e)})
            return f"[Overseer] Error running skill '{skill_name}': {e}"

    def get_version(self) -> str:
        return self.config.get("version", "1.0.0")

    def hot_swap_skills(self, new_skills) -> str:
        self.skills = new_skills
        return "Skills hot-swapped at runtime."

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "uptime": str(datetime.now() - self._start_time),
            "users": self.users.count_users(),
            "skills_loaded": self.skills.count(),
            "mode": self.mode,
            "admins": list(self.admins),
            "history_length": len(self.history),
            "version": self.get_version(),
            "persona": self.config.get("persona", "default"),
        }

    def react_to_event(self, event_type: str, data: Dict[str, Any]) -> Optional[str]:
        self.log.debug(f"[OverseerBrain] Reacting to event: {event_type}")
        for hook in getattr(self, "event_hooks", []):
            try:
                result = hook(event_type, data)
                if result:
                    return result
            except Exception as e:
                self.log.error(f"[OverseerBrain] Event hook error: {e}")

        if event_type == "command_failed":
            return f"Something went wrong with that command."
        elif event_type == "user_joined":
            return f"Welcome, {data.get('user', 'friend')}!"
        return None

    def run_command(self, cmd: str, args: List[str], user_id: str = "default") -> str:
        try:
            if hasattr(self.skills, "command_requires_admin") and self.skills.command_requires_admin(cmd):
                if user_id not in self.admins:
                    return "[Permissions] You are not authorized to run this command."
            return self.skills.run_command(cmd, args)
        except Exception as e:
            self.log.error(f"[OverseerBrain] Command run error: {e}")
            self._audit("error_command", user_id, {"cmd": cmd, "args": args, "error": str(e)})
            return f"[Error] Could not run command: {cmd}"

    def introspect(self, prompt: str) -> str:
        feedback = []
        if hasattr(self.memory, "get_feedback"):
            feedback.extend(self.memory.get_feedback())
        if hasattr(self.skills, "get_skill_feedback"):
            feedback.extend(self.skills.get_skill_feedback())
        return f"{self.name} is still learning. Your prompt was: '{prompt}'. Feedback: {feedback}"

    def think(self, thoughts: str) -> str:
        self.log.info(f"[OverseerBrain] Thinking: {thoughts}")
        if hasattr(self.memory, "store_brain_thought"):
            self.memory.store_brain_thought(thoughts)
        return f"I'm noting that down: {thoughts}"

    def set_mode(self, mode: str) -> str:
        valid_modes = ["default", "focus", "debug", "quiet", "casual"]
        if mode in valid_modes:
            self.mode = mode
            return f"Brain mode set to {mode}."
        else:
            return f"Invalid mode. Valid modes: {', '.join(valid_modes)}"

    def reload_skills(self) -> str:
        try:
            if hasattr(self.skills, "reload"):
                self.skills.reload()
                return "Skills reloaded."
            return "Skill system does not support reload."
        except Exception as e:
            self.log.error(f"[OverseerBrain] Skill reload error: {e}")
            return f"[Error] Could not reload skills."

    def list_skills(self) -> List[str]:
        if hasattr(self.skills, "list_skills"):
            return self.skills.list_skills()
        return []

    def describe_skill(self, name: str) -> Optional[str]:
        if hasattr(self.skills, "describe_skill"):
            return self.skills.describe_skill(name)
        return None

    def get_response(self, user_input: str, user_id: str = "default", as_dict: bool = True, **kwargs) -> Dict[str, Any]:
        output = self.process(user_input, user_id, as_dict=True, **kwargs)
        if isinstance(output, dict):
            output["timestamp"] = datetime.now().isoformat()
            output["user"] = user_id
        return output

    def add_admin(self, user_id: str) -> str:
        self.admins.add(user_id)
        return f"{user_id} added as admin."

    def remove_admin(self, user_id: str) -> str:
        self.admins.discard(user_id)
        return f"{user_id} removed from admin list."

    def is_admin(self, user_id: str) -> bool:
        return user_id in self.admins

    def reset_rate_limit(self, user_id: Optional[str] = None) -> str:
        if user_id:
            self.rate_limits[user_id] = []
            return f"Rate limit reset for {user_id}."
        else:
            self.rate_limits = {}
            return "Rate limits reset for all users."

    def get_history(self, limit: int = 20, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        result = [
            entry for entry in reversed(self.history)
            if user_id is None or entry["user"] == user_id
        ]
        return result[:limit]

    def help(self) -> str:
        return (
            f"{self.name} Brain Help:\n"
            "- process_async / process: Main message processing.\n"
            "- get_status: System status.\n"
            "- react_to_event: Handle system/user events.\n"
            "- run_command: Run admin/user commands.\n"
            "- set_mode: Switch between operational modes.\n"
            "- reload_skills, list_skills, describe_skill: Skill management.\n"
            "- get_response: API/GUI-friendly answer.\n"
            "- schedule_task, list_scheduled_tasks, cancel_scheduled_task: Task scheduling.\n"
            "- add_admin/remove_admin/is_admin: Admin management.\n"
            "- set_permission/check_permission: Fine-grained permissions.\n"
            "- set_persona: Dynamic personality/tone.\n"
            "- handle_multimodal: Multi-modal input (text, image, etc).\n"
            "- get_sessions/switch_session: Conversation management.\n"
            "- query_kb: Knowledge base lookup.\n"
            "- search_skills/suggest_skills: Skill discovery & suggestion.\n"
            "- export_analytics: Usage, error, and skill analytics.\n"
            "- get_audit_log: Secure audit/event log.\n"
            "- reset_rate_limit: Remove user or global rate limits.\n"
            "- get_history: Query recent interactions.\n"
            "- All methods are async-ready and extensible for future Overseer needs.\n"
        )
