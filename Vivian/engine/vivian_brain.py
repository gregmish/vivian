import datetime
import logging
import time
import os
import json
import asyncio
from typing import Any, Dict, List, Optional, Callable, Union
from model import send_to_model

class VivianBrain:
    """
    VivianBrain: Agentic, auditable, self-improving LLM orchestrator.
    Upgrades: error/debug reporting, user/session stats, hot-reload, async, RBAC, custom prompts, plugin events, and more.
    """

    def __init__(
        self,
        config,
        memory,
        users,
        skills: Optional[Dict[str, Callable]] = None,
        eventbus=None,
        rbac_cb: Optional[Callable[[str, str], bool]] = None,
        alert_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        metrics_cb: Optional[Callable[[str, Any], None]] = None,
        explainability_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        feedback_cb: Optional[Callable[[str, str], None]] = None,
        persona: Optional[str] = None,
        mode: Optional[str] = None
    ):
        self.config = config
        self.memory = memory
        self.users = users
        self.skills = skills or {}
        self.eventbus = eventbus
        self.rbac_cb = rbac_cb
        self.alert_cb = alert_cb
        self.metrics_cb = metrics_cb
        self.explainability_cb = explainability_cb
        self.feedback_cb = feedback_cb
        self.persona = persona or config.get("persona", "default")
        self.mode = mode or config.get("mode", "default")
        self._log = logging.getLogger("VivianBrain")
        self._version = config.get("version", "unknown")
        self._last_error = None
        self._last_user_input = {}
        self._user_stats = {}  # {user: {last_seen, message_count, session_count, context_window}}
        self._custom_sysprompts = {}  # per user
        self._thread_contexts = {}  # thread_id: [messages]
        self._default_context_window = config.get("context_window", 10)
        self._plugin_dir = config.get("plugin_dir", "plugins")
        self._rbac_perms = {}  # {user: set(perms)}

        self._scan_and_register_skills()

    # -------------- User/session stats --------------
    def _update_user_stats(self, user: str):
        stats = self._user_stats.get(user, {
            "last_seen": None,
            "message_count": 0,
            "session_count": 0,
            "context_window": self._default_context_window
        })
        stats["last_seen"] = datetime.datetime.now().isoformat()
        stats["message_count"] += 1
        self._user_stats[user] = stats

    def get_user_stats(self, user: str):
        return self._user_stats.get(user, {})

    # -------------- RBAC/permission helpers --------------
    def list_permissions(self, user: str):
        perms = self._rbac_perms.get(user, set())
        return f"Permissions for {user}: {', '.join(perms) if perms else 'None'}"

    def set_permission(self, user: str, perm: str):
        if user not in self._rbac_perms:
            self._rbac_perms[user] = set()
        self._rbac_perms[user].add(perm)
        return f"Permission '{perm}' granted to {user}."

    def remove_permission(self, user: str, perm: str):
        if user in self._rbac_perms and perm in self._rbac_perms[user]:
            self._rbac_perms[user].remove(perm)
            return f"Permission '{perm}' revoked from {user}."
        return f"{user} does not have permission '{perm}'."

    # -------------- Error/debug reporting --------------
    def debug(self):
        """Return last error and last user input for debugging."""
        return (
            f"Last error: {self._last_error or 'No recent errors.'}\n"
            f"Last user input: {self._last_user_input or 'N/A'}"
        )

    # -------------- Plugin/skill hot-reload and discovery --------------
    def _scan_and_register_skills(self):
        # Scan plugins directory for Python files with callable 'register' and register skills
        self.skills = self.skills or {}
        plugin_dir = self._plugin_dir
        if not os.path.isdir(plugin_dir):
            return
        for fname in os.listdir(plugin_dir):
            if fname.endswith(".py") and not fname.startswith("_"):
                fpath = os.path.join(plugin_dir, fname)
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(fname[:-3], fpath)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "register"):
                        new_skills = mod.register()
                        if isinstance(new_skills, dict):
                            self.skills.update(new_skills)
                except Exception as e:
                    self._log.warning(f"[VivianBrain] Failed to load plugin {fname}: {e}")

    def reload_skills(self):
        self._audit("reload_skills", {})
        self._scan_and_register_skills()
        return "Skills reloaded from plugins directory."

    # -------------- Conversation context/threading --------------
    def _get_context_window(self, user: str) -> int:
        return self._user_stats.get(user, {}).get("context_window", self._default_context_window)

    def _set_context_window(self, user: str, n: int):
        stats = self._user_stats.setdefault(user, {
            "last_seen": None,
            "message_count": 0,
            "session_count": 0,
            "context_window": self._default_context_window
        })
        stats["context_window"] = n
        return f"Context window set to {n} for {user}."

    def _prepare_context(self, prompt: str, user: str, thread_id=None) -> str:
        if thread_id:
            messages = self._thread_contexts.get(thread_id, [])
            context = "\n".join([f"{m['role'].capitalize()}: {m['text']}" for m in messages[-self._get_context_window(user):]])
            return context
        else:
            history = self.memory.get_recent(limit=self._get_context_window(user), user=user)
            context = "\n".join([f"{item.get('type', 'User').capitalize()}: {item.get('data', {}).get('text', '')}" for item in history])
            return context

    # -------------- Skill help system --------------
    def help(self, skill=None):
        if not skill:
            return (
                "Vivian is an agentic, self-improving, skill-powered assistant.\n"
                "You can ask questions, invoke tools, register plugins, provide feedback, and control persona/mode.\n"
                "Special commands: /skills, /skill <name>, /audit, /setmode, /setperm, /explain <prompt>, /reloadskills, /debug, /sysprompt <prompt>, /setcontext <N>, /stats, /userstats <user>.\n"
                "Use '/help <skill>' for specific skill help."
            )
        skill_obj = self.skills.get(skill)
        if skill_obj:
            doc = getattr(skill_obj, "__doc__", "") or "No docstring."
            intents = getattr(skill_obj, "intents", [])
            return f"[{skill}] {doc} Intents: {intents}"
        return f"No such skill '{skill}'."

    def list_skills(self):
        return list(self.skills.keys())

    def describe_skill(self, name: str):
        return self.help(name)

    # -------------- Command handling & main logic --------------
    def handle(self, prompt: str, user: Optional[str] = None, thread_id=None) -> str:
        user = user or self.config.get("user", "unknown")
        timestamp = datetime.datetime.now().isoformat()
        self._last_user_input = {"time": timestamp, "text": prompt, "user": user}
        self._update_user_stats(user)

        prompt_l = prompt.strip().lower()

        # ---------- Command parsing ----------
        if prompt_l in ["/debug", "debug"]:
            return self.debug()

        if prompt_l.startswith("/help"):
            parts = prompt.strip().split()
            if len(parts) == 1:
                return self.help()
            else:
                return self.help(parts[1])

        if prompt_l in ["what's your current mode?", "what is your current mode?", "current mode?", "/mode", "what mode are you in?", "vivian, what is your mode?"]:
            return f"My current mode is '{self.mode}'."

        if prompt_l in ["what's your current persona?", "what is your current persona?", "current persona?", "/persona", "what persona are you in?", "vivian, what is your persona?"]:
            return f"My current persona is '{self.persona}'."

        if prompt_l in ["what's your version?", "what is your version?", "vivian version?", "version?", "/version"]:
            return f"My current version is '{self._version}'."

        if prompt_l.startswith("/sysprompt"):
            new_prompt = prompt.partition(" ")[2]
            if not new_prompt.strip():
                return f"Current system prompt: {self._custom_sysprompts.get(user) or self.config.get('system_prompt', '(none)')}"
            self._custom_sysprompts[user] = new_prompt.strip()
            return f"System prompt set for {user}."

        if prompt_l.startswith("/setcontext"):
            try:
                n = int(prompt.strip().split()[1])
                return self._set_context_window(user, n)
            except Exception:
                return "Usage: /setcontext <N> (N must be an integer)"

        if prompt_l == "/stats":
            stats = self.memory.get_stats()
            return f"Memory stats: {json.dumps(stats, indent=2)}"

        if prompt_l.startswith("/userstats"):
            parts = prompt.strip().split()
            target = parts[1] if len(parts) > 1 else user
            stats = self.get_user_stats(target)
            return f"User stats for {target}: {json.dumps(stats, indent=2)}"

        if prompt_l == "/skills":
            return "Loaded skills: " + ", ".join(self.skills.keys())

        if prompt_l.startswith("/skill "):
            skillname = prompt.strip().split()[1]
            return self.describe_skill(skillname)

        if prompt_l.startswith("/setmode"):
            parts = prompt.strip().split()
            if len(parts) < 2:
                return f"Current mode: {self.mode}"
            return self.set_mode(parts[1])

        if prompt_l.startswith("/setpersona"):
            parts = prompt.strip().split()
            if len(parts) < 2:
                return f"Current persona: {self.persona}"
            return self.set_persona(parts[1])

        if prompt_l.startswith("/setperm "):
            parts = prompt.strip().split()
            if len(parts) < 3:
                return "Usage: /setperm <user> <perm>"
            return self.set_permission(parts[1], parts[2])

        if prompt_l.startswith("/rmperm "):
            parts = prompt.strip().split()
            if len(parts) < 3:
                return "Usage: /rmperm <user> <perm>"
            return self.remove_permission(parts[1], parts[2])

        if prompt_l.startswith("/perms "):
            parts = prompt.strip().split()
            target = parts[1] if len(parts) > 1 else user
            return self.list_permissions(target)

        if prompt_l == "/reloadskills":
            return self.reload_skills()

        if prompt_l == "/audit":
            return json.dumps(self.memory.get_recent(20), indent=2)

        # ---------- End command parsing ----------

        skill = self._find_skill(prompt)
        if skill:
            reply = self._invoke_skill(skill, prompt, user)
            self.memory.log_event("vivian_response", {"time": timestamp, "text": reply, "user": user})
            return reply

        persona = self.persona
        personas = self.config.get("personas", {})
        if not isinstance(personas, dict):
            personas = {}
        persona_prompt = personas.get(persona, "")

        # Use custom system prompt if set, else persona/system prompt from config
        system_prompt = (
            self._custom_sysprompts.get(user) or
            persona_prompt or
            self.config.get("system_prompt",
                "You are Vivian, an intelligent, agentic assistant. Be direct, helpful, and sharp."
            )
        )

        examples = self.config.get("few_shot_examples", "")
        context = self._prepare_context(prompt, user, thread_id=thread_id)
        mode = self.mode
        goals = self.config.get("goals", {}).get(mode, "")
        full_prompt = f"{system_prompt}\n{examples}\n{goals}\n{context}\n\nUser: {prompt}\nVivian:"

        # -------------- Model call (sync or async) --------------
        try:
            # If send_to_model is async, call it via asyncio (else, use sync)
            if asyncio.iscoroutinefunction(send_to_model):
                loop = asyncio.get_event_loop()
                response = loop.run_until_complete(send_to_model(full_prompt))
            else:
                response = send_to_model(full_prompt)
            self.memory.log_event("vivian_response", {"time": timestamp, "text": response, "user": user})
            self._audit("vivian_response", {"time": timestamp, "text": response, "user": user})
            self._metrics("vivian_model_invoked", time.time())
            self._explain({
                "prompt": prompt, "system_prompt": system_prompt, "mode": mode,
                "context": context, "reply": response
            })
            self._last_error = None  # Clear error on success
            return response
        except Exception as e:
            self._last_error = str(e)
            # Auto-save user input for retry
            self._last_user_input = {"time": timestamp, "text": prompt, "user": user}
            self._audit("model_error", {"error": str(e), "prompt": prompt, "user": user})
            self._alert("model_failed", {"error": str(e), "user": user})
            # Self-improvement suggestion if repeated
            if hasattr(self, "_error_count"):
                self._error_count += 1
            else:
                self._error_count = 1
            if self._error_count >= 3:
                suggestion = "Tip: Multiple errors detected. Try /reloadskills or /debug for diagnostics."
            else:
                suggestion = ""
            return "Sorry, I encountered an error while processing your request." + (" " + suggestion if suggestion else "")

    def _audit(self, action, data):
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "action": action,
            "user": self.config.get("user", "unknown"),
            "data": data,
        }
        try:
            self.memory.log_event(action, entry)
        except Exception:
            pass

    def _alert(self, event, data):
        if self.alert_cb:
            self.alert_cb(event, data)

    def _metrics(self, metric, value):
        if self.metrics_cb:
            self.metrics_cb(metric, value)

    def _explain(self, info: Dict[str, Any]):
        if self.explainability_cb:
            self.explainability_cb(info)

    def _check_rbac(self, user, action):
        if self.rbac_cb:
            return self.rbac_cb(user, action)
        return True

    def _find_skill(self, prompt: str) -> Optional[str]:
        if not self.skills:
            return None
        prompt_l = prompt.lower()
        for skill, func in self.skills.items():
            if hasattr(func, "intents"):
                if any(intent in prompt_l for intent in func.intents):
                    return skill
            elif skill in prompt_l:
                return skill
        return None

    def _invoke_skill(self, skill: str, prompt: str, user: str) -> str:
        if not self._check_rbac(user, f"use_{skill}"):
            self._audit("rbac_denied", {"skill": skill, "prompt": prompt, "user": user})
            return f"Sorry, you do not have permission for skill '{skill}'."
        try:
            result = self.skills[skill](prompt, user=user)
            self._audit("skill_invoked", {"skill": skill, "prompt": prompt, "result": result, "user": user})
            self._metrics("vivian_skill_used", skill)
            return f"[Skill:{skill}] {result}"
        except Exception as e:
            self._audit("skill_error", {"skill": skill, "prompt": prompt, "error": str(e), "user": user})
            self._alert("skill_failed", {"skill": skill, "error": str(e)})
            return f"Skill '{skill}' failed: {e}"

    def receive_feedback(self, user: str, original_prompt: str, feedback: str):
        self.memory.log_event("user_feedback", {
            "user": user,
            "prompt": original_prompt,
            "feedback": feedback,
            "time": datetime.datetime.now().isoformat(),
        })
        if self.feedback_cb:
            self.feedback_cb(original_prompt, feedback)

    def register_skill(self, name: str, func: Callable):
        self.skills[name] = func

    def set_persona(self, persona: str):
        self.persona = persona
        self._audit("set_persona", {"persona": persona})

    def set_mode(self, mode: str):
        self.mode = mode
        self._audit("set_mode", {"mode": mode})
        return f"Mode set to {mode}"

    def explain(self, prompt: str, user: Optional[str] = None) -> str:
        skill = self._find_skill(prompt)
        if skill:
            return f"Skill '{skill}' was selected based on keywords/intents."
        return f"System prompt: {self.config.get('system_prompt', '(none)')}\nCurrent mode: {self.mode}\nPersona: {self.persona}"

    def dispatch_event(self, event: str, data: dict):
        if self.eventbus:
            self.eventbus.publish(event, data)
        self._audit("event_dispatch", {"event": event, "data": data})

    def get_version(self):
        return self._version

    def get_audit_log(self, n: int = 20):
        return self.memory.get_recent(n)

    def process(self, prompt: str, as_dict=False, user: Optional[str] = None):
        reply = self.handle(prompt, user=user)
        if as_dict:
            return {"reply": reply, "skills": self.list_skills(), "persona": self.persona, "mode": self.mode}
        return reply

    # -- Web API stubs for future extension --
    def api_mode(self):
        return {"mode": self.mode}

    def api_persona(self):
        return {"persona": self.persona}

    def api_skills(self):
        return {"skills": self.list_skills()}

    def api_stats(self):
        return {
            "user_stats": self._user_stats,
            "memory_stats": self.memory.get_stats(),
        }

    # -- Plugin extensibility: event hooks (stubs) --
    def emit_event(self, event_name, data):
        if self.eventbus:
            self.eventbus.publish(event_name, data)
        # Plugins can hook into these events
        # Example: self.emit_event("on_context_ready", {"prompt": ..., "context": ...})