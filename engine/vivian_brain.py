import datetime
import logging
import time
import os
import json
import asyncio
import traceback
from typing import Any, Dict, List, Optional, Callable, Union
from model import send_to_model

class VivianBrain:
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
        mode: Optional[str] = None,
        enable_autonomy: bool = True,
        autonomy_interval: int = 60,
        plugin_hot_reload: bool = False,
        gui_cb: Optional[Callable] = None,
        web_cb: Optional[Callable] = None,
        voice_cb: Optional[Callable] = None,
        agent_pool: Optional[List[Any]] = None,
        dashboard_cb: Optional[Callable] = None,
        notification_cb: Optional[Callable] = None,
        api_cb: Optional[Callable] = None,
        shell_cb: Optional[Callable] = None,
        session_id: Optional[str] = None,
        explainable_ai: bool = True,
        healthcheck_cb: Optional[Callable] = None,
        history_cb: Optional[Callable] = None,
        analytics_cb: Optional[Callable] = None,
        websocket_cb: Optional[Callable] = None,
        rest_cb: Optional[Callable] = None,
        intent_classifier: Optional[Callable] = None,
        scripting_cb: Optional[Callable] = None,
        data_lake_cb: Optional[Callable] = None,
        context_tree_cb: Optional[Callable] = None,
        self_heal_cb: Optional[Callable] = None,
        logging_cb: Optional[Callable] = None,
        multi_agent_controller: Optional[Callable] = None,
    ):
        self.config = config
        self.memory = memory
        self.users = users
        self.skills = skills if isinstance(skills, dict) else {}
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
        self._user_stats = {}
        self._custom_sysprompts = {}
        self._thread_contexts = {}
        self._default_context_window = config.get("context_window", 10)
        self._plugin_dir = config.get("plugin_dir", "plugins")
        self._rbac_perms = {}
        self._autonomy_enabled = enable_autonomy
        self._autonomy_interval = autonomy_interval
        self._autonomy_task = None
        self._error_count = 0
        self._evolution_cooldown = 0
        self.goal_stack = []
        self.failed_evolution_log = []
        self._plugin_hot_reload = plugin_hot_reload
        self._gui_cb = gui_cb
        self._web_cb = web_cb
        self._voice_cb = voice_cb
        self._dashboard_cb = dashboard_cb
        self._notification_cb = notification_cb
        self._api_cb = api_cb
        self._shell_cb = shell_cb
        self._agent_pool = agent_pool or []
        self.session_id = session_id or f"session-{datetime.datetime.utcnow().isoformat()}"
        self._explainable_ai = explainable_ai
        self._healthcheck_cb = healthcheck_cb
        self.failed_evolution_log = []
        self._history_cb = history_cb
        self._analytics_cb = analytics_cb
        self._websocket_cb = websocket_cb
        self._rest_cb = rest_cb
        self._intent_classifier = intent_classifier
        self._scripting_cb = scripting_cb
        self._data_lake_cb = data_lake_cb
        self._context_tree_cb = context_tree_cb
        self._self_heal_cb = self_heal_cb
        self._logging_cb = logging_cb
        self._multi_agent_controller = multi_agent_controller
        self._scan_and_register_skills()
        if self._autonomy_enabled:
            self._start_autonomy_loop()
        if self._plugin_hot_reload:
            self._start_hot_reload_watcher()

    # --- Plugin Hot Reloading ---
    def _start_hot_reload_watcher(self):
        import threading
        def watch_plugins():
            last_mtime = {}
            while True:
                for fname in os.listdir(self._plugin_dir):
                    if fname.endswith(".py") and not fname.startswith("_"):
                        fpath = os.path.join(self._plugin_dir, fname)
                        mtime = os.path.getmtime(fpath)
                        if fname not in last_mtime or last_mtime[fname] != mtime:
                            self.reload_skills()
                            last_mtime[fname] = mtime
                time.sleep(2)
        threading.Thread(target=watch_plugins, daemon=True).start()
        self._log.info("[VivianBrain] Plugin hot-reload watcher started.")

    # --- Healthcheck (CLI or API) ---
    def healthcheck(self):
        status = {
            "version": self._version,
            "persona": self.persona,
            "mode": self.mode,
            "plugins": list(self.skills.keys()),
            "autonomy": self._autonomy_enabled,
            "goal_stack": len(self.goal_stack),
            "evolution_log": len(self.failed_evolution_log),
            "last_error": self._last_error,
            "timestamp": datetime.datetime.now().isoformat(),
            "session_id": self.session_id,
            "memory_stats": getattr(self.memory, "stats", lambda: "N/A")(),
            "users": len(self.users.list_users()) if hasattr(self.users, "list_users") else "N/A"
        }
        if self._healthcheck_cb:
            status.update(self._healthcheck_cb())
        return status

    # --- GUI/Web/Voice/Dashboard/Notification/Agent Pool Integration ---
    def gui_event(self, event, data):
        if self._gui_cb:
            self._gui_cb(event, data)
    def web_event(self, event, data):
        if self._web_cb:
            self._web_cb(event, data)
    def voice_event(self, event, data):
        if self._voice_cb:
            self._voice_cb(event, data)
    def dashboard_event(self, event, data):
        if self._dashboard_cb:
            self._dashboard_cb(event, data)
    def notify(self, message):
        if self._notification_cb:
            self._notification_cb(message)
    def api_call(self, endpoint, payload):
        if self._api_cb:
            return self._api_cb(endpoint, payload)
    def shell_callback(self, command, context):
        if self._shell_cb:
            return self._shell_cb(command, context)
    def agent_broadcast(self, msg):
        for agent in self._agent_pool:
            try:
                agent.handle(msg)
            except Exception:
                pass

    # --- Data Lake, Analytics, Websocket/REST, Scripting, Context Tree, Multi-Agent ---
    def log_to_datalake(self, data):
        if self._data_lake_cb:
            self._data_lake_cb(data)
    def analytics_event(self, event, data):
        if self._analytics_cb:
            self._analytics_cb(event, data)
    def websocket_event(self, event, data):
        if self._websocket_cb:
            self._websocket_cb(event, data)
    def rest_event(self, endpoint, data):
        if self._rest_cb:
            self._rest_cb(endpoint, data)
    def classify_intent(self, prompt):
        if self._intent_classifier:
            return self._intent_classifier(prompt)
        return None
    def run_script(self, code):
        if self._scripting_cb:
            return self._scripting_cb(code)
        return None
    def context_tree_update(self, update):
        if self._context_tree_cb:
            self._context_tree_cb(update)
    def self_heal(self):
        if self._self_heal_cb:
            self._self_heal_cb()
        else:
            # fallback to original
            try:
                recent = self.memory.get_recent(limit=5, event_type="skill_error")
            except TypeError:
                recent = self.memory.get_recent(limit=5)
            for err in recent:
                plugin = err.get("skill")
                if plugin:
                    print(f"[Vivian] Detected skill error in {plugin}, attempting rollback/reload...")
                    self.reload_skills()
                    self.memory.log_event("vivian_self_heal", {"plugin": plugin, "error": err})
            print("[Vivian] Self-healing complete.")
    def log_event(self, event, data):
        if self._logging_cb:
            self._logging_cb(event, data)

    def multi_agent_orchestrate(self, task):
        if self._multi_agent_controller:
            return self._multi_agent_controller(task)
        return "No multi-agent controller registered."

    # --- Shell with /health and more ---
    def run_shell(self):
        print("Vivian AGI Brain Shell. Type '/exit' to exit.")
        while True:
            cmd = input("VivianShell> ").strip()
            if cmd == "/exit":
                break
            if cmd == "/health":
                print(json.dumps(self.healthcheck(), indent=2))
                continue
            if cmd == "/skills":
                print("Available skills:", ", ".join(list(self.skills.keys())))
                continue
            if cmd == "/goalstack":
                print("Current goal stack:", self.goal_stack)
                continue
            if cmd == "/selfheal":
                self.self_heal()
                continue
            print(self.handle(cmd))

    # --- Explainability ---
    def explain(self):
        state = {
            "persona": self.persona,
            "mode": self.mode,
            "version": self._version,
            "autonomy": self._autonomy_enabled,
            "goal_stack": self.goal_stack,
            "last_error": self._last_error,
            "session_id": self.session_id,
            "last_user": self._last_user_input,
            "plugins": list(self.skills.keys())
        }
        return json.dumps(state, indent=2)

    # --- Main AGI, Evolution, Plugin, and Skill Logic (rest of your code, upgraded with more hooks and comments) ---
    def register_plugin(self, name, func, **meta):
        if not isinstance(self.skills, dict):
            self.skills = {}
        self.skills[name] = func
        self._log.info(f"Skill '{name}' registered with meta: {meta}")
        self.analytics_event("plugin_registered", {"plugin": name, **meta})

    def _start_autonomy_loop(self):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._autonomy_task = loop.create_task(self._supreme_cognitive_loop())
            else:
                import threading
                threading.Thread(target=lambda: asyncio.run(self._supreme_cognitive_loop()), daemon=True).start()
            self._log.info("[VivianBrain] Supreme autonomy loop started.")
        except Exception as e:
            self._log.warning(f"[VivianBrain] Could not start autonomy loop: {e}")

    async def _supreme_cognitive_loop(self):
        while True:
            try:
                await asyncio.sleep(self._autonomy_interval)
                await self._supreme_reflection_and_evolve()
            except Exception as e:
                self._log.warning(f"[VivianBrain] Supreme autonomy loop error: {e}\n{traceback.format_exc()}")

    async def _supreme_reflection_and_evolve(self):
        context = self.aggregate_memories()
        try:
            feedback = self.memory.get_recent(limit=5, event_type="user_feedback")
        except TypeError:
            feedback = self.memory.get_recent(limit=5)
        last_failed = self.failed_evolution_log[-1] if self.failed_evolution_log else None
        goals = self.goal_stack[-3:] if self.goal_stack else []
        system_prompt = (
            self.config.get("system_prompt", "You are Vivian, the supreme agentic AI. Plan, reflect, explain, and always seek user approval.")
        )
        planning_prompt = (
            f"{system_prompt}\n"
            f"Recent activity/context:\n{context}\n"
            f"Latest feedback: {feedback}\n"
            f"Open goals: {goals}\n"
            f"Last failed evolution: {last_failed}\n"
            "Reflect and propose your next self-improvement, skill, or upgrade. "
            "If code or a plan is needed, generate a summary, implementation, and explain why it's safe and beneficial. "
            "If your prior attempt failed, suggest a new approach."
        )
        try:
            if asyncio.iscoroutinefunction(send_to_model):
                plan = await send_to_model(planning_prompt)
            else:
                loop = asyncio.get_event_loop()
                plan = await loop.run_in_executor(None, send_to_model, planning_prompt)
            self.memory.log_event("vivian_plan", {"time": datetime.datetime.now().isoformat(), "plan": plan})
            self._log.info("[VivianBrain] Plan: %s", plan)
        except Exception as e:
            self.memory.log_event("vivian_plan_error", {"error": str(e), "traceback": traceback.format_exc()})
            self._log.warning(f"[VivianBrain] Planning error: {e}")
            return

        alt_prompt = (
            f"Critique the following plan for risks, alternatives, or improvements:\n{plan}\n"
            "If unsafe, suggest a safer or simpler alternative. Then summarize your reasoning."
        )
        try:
            if asyncio.iscoroutinefunction(send_to_model):
                critique = await send_to_model(alt_prompt)
            else:
                loop = asyncio.get_event_loop()
                critique = await loop.run_in_executor(None, send_to_model, alt_prompt)
            self.memory.log_event("vivian_critique", {"time": datetime.datetime.now().isoformat(), "critique": critique})
        except Exception as e:
            critique = "No critique available: " + str(e)

        print("\n[VIVIAN PROPOSAL]")
        print(f"Plan:\n{plan}\n")
        print(f"Critique & Alternatives:\n{critique}\n")
        print("You may Approve (y), Edit (e), or Reject (n).")
        action = self.wait_for_approval()
        if action == "y":
            self.execute_evolution_plan(plan)
        elif action == "e":
            user_edit = input("Enter your edited plan (or press Enter to skip):\n")
            if user_edit.strip():
                self.execute_evolution_plan(user_edit)
            else:
                print("No edit provided, skipping evolution this cycle.")
        else:
            self.memory.log_event("vivian_evolution_rejected", {"plan": plan, "critique": critique})
            print("Vivian logs your rejection and will learn from it.")

    def wait_for_approval(self):
        while True:
            resp = input("Approve (y), Edit (e), or Reject (n): ").strip().lower()
            if resp in ["y", "n", "e"]:
                return resp

    def execute_evolution_plan(self, plan):
        evolver = self.skills.get("evolver") or self.skills.get("auto_upgrader")
        if not evolver:
            self.memory.log_event("vivian_evolution_failed", {"plan": plan, "error": "No evolver skill found"})
            print("No evolver/auto_upgrader skill found.")
            return
        try:
            if hasattr(evolver, "sandbox"):
                result = evolver.sandbox(plan, user="vivian")
            else:
                result = evolver(plan, user="vivian")
            reload_result = self.reload_skills()
            self.memory.log_event("vivian_evolution_success", {"plan": plan, "result": result, "reload_result": reload_result})
            print(f"[Vivian] Evolution result: {result}")
        except Exception as e:
            self.memory.log_event("vivian_evolution_failed", {"plan": plan, "error": str(e), "traceback": traceback.format_exc()})
            self.failed_evolution_log.append({"time": datetime.datetime.now().isoformat(), "plan": plan, "error": str(e)})
            print("[Vivian] Evolution failed and logged. Will avoid repeating this version.")

    def aggregate_memories(self):
        lines = []
        try:
            for item in self.memory.get_recent(limit=10):
                lines.append(str(item))
        except Exception:
            pass
        try:
            if hasattr(self.memory, "vector_search"):
                lines.append("Vector memory: " + str(self.memory.vector_search("recent context")))
        except Exception:
            pass
        if self.goal_stack:
            lines.append("Goals: " + str(self.goal_stack[-3:]))
        return "\n".join(lines)

    def spawn_minion(self, objective, context=None):
        minion_id = f"minion_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self.memory.log_event("minion_spawned", {"id": minion_id, "objective": objective, "context": context})
        print(f"[Vivian] Minion spawned for: {objective}")
        return minion_id

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

    def get_user_stats(self, user: str): return self._user_stats.get(user, {})

    def list_permissions(self, user: str):
        perms = self._rbac_perms.get(user, set())
        return f"Permissions for {user}: {', '.join(perms) if perms else 'None'}"

    def set_permission(self, user: str, perm: str):
        if user not in self._rbac_perms: self._rbac_perms[user] = set()
        self._rbac_perms[user].add(perm)
        return f"Permission '{perm}' granted to {user}."

    def remove_permission(self, user: str, perm: str):
        if user in self._rbac_perms and perm in self._rbac_perms[user]:
            self._rbac_perms[user].remove(perm)
            return f"Permission '{perm}' revoked from {user}."
        return f"{user} does not have permission '{perm}'."

    def debug(self):
        return (f"Last error: {self._last_error or 'No recent errors.'}\n"
                f"Last user input: {self._last_user_input or 'N/A'}")

    def _scan_and_register_skills(self):
        if not isinstance(self.skills, dict):
            self.skills = {}
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
                        mod.register(self.register_plugin)
                except Exception as e:
                    self._log.warning(f"[VivianBrain] Failed to load plugin {fname}: {e}")

    def reload_skills(self):
        self._audit("reload_skills", {})
        self._scan_and_register_skills()
        return "Skills reloaded from plugins directory."

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
            try:
                history = self.memory.get_recent(limit=self._get_context_window(user), user=user)
            except TypeError:
                history = self.memory.get_recent(limit=self._get_context_window(user))
            context = "\n".join([f"{item.get('type', 'User').capitalize()}: {item.get('data', {}).get('text', '')}" for item in history])
            return context

    def help(self, skill=None):
        if not skill:
            return (
                "Vivian is the supreme, self-evolving, skill-powered agentic assistant.\n"
                "Ask questions, invoke tools, register plugins, provide feedback, and control persona/mode.\n"
                "Special commands: /skills, /skill <name>, /audit, /setmode, /setperm, /explain <prompt>, /reloadskills, /debug, /sysprompt <prompt>, /setcontext <N>, /stats, /userstats <user>.\n"
                "Use '/help <skill>' for specific skill help."
            )
        skill_obj = self.skills.get(skill)
        if skill_obj:
            doc = getattr(skill_obj, "__doc__", "") or "No docstring."
            intents = getattr(skill_obj, "intents", [])
            return f"[{skill}] {doc} Intents: {intents}"
        return f"No such skill '{skill}'."

    def list_skills(self): return list(self.skills.keys())
    def describe_skill(self, name: str): return self.help(name)

    def handle(self, prompt: str, user: Optional[str] = None, thread_id=None) -> str:
        user = user or self.config.get("user", "unknown")
        timestamp = datetime.datetime.now().isoformat()
        self._last_user_input = {"time": timestamp, "text": prompt, "user": user}
        self._update_user_stats(user)
        prompt_l = prompt.strip().lower()
        skill = self._find_skill(prompt)
        if skill:
            reply = self._invoke_skill(skill, prompt, user)
            self.memory.log_event("vivian_response", {"time": timestamp, "text": reply, "user": user})
            self.analytics_event("vivian_response", {"time": timestamp, "text": reply, "user": user})
            return reply
        try:
            if self._intent_classifier:
                intent = self._intent_classifier(prompt)
                self.memory.log_event("vivian_intent", {"prompt": prompt, "intent": intent, "user": user})
            full_prompt = self.compose_llm_prompt(prompt, user, thread_id)
            if asyncio.iscoroutinefunction(send_to_model):
                loop = asyncio.get_event_loop()
                response = loop.run_until_complete(send_to_model(full_prompt))
            else:
                response = send_to_model(full_prompt)
            self.memory.log_event("vivian_response", {"time": timestamp, "text": response, "user": user})
            self._audit("vivian_response", {"time": timestamp, "text": response, "user": user})
            self._metrics("vivian_model_invoked", time.time())
            self._explain({
                "prompt": prompt, "system_prompt": self.config.get("system_prompt", ""), "mode": self.mode,
                "context": self._prepare_context(prompt, user, thread_id=thread_id), "reply": response
            })
            self._last_error = None
            self._error_count = 0
            return response
        except Exception as e:
            self._last_error = str(e)
            self._error_count += 1
            self._last_user_input = {"time": timestamp, "text": prompt, "user": user}
            self._audit("model_error", {"error": str(e), "prompt": prompt, "user": user})
            self._alert("model_failed", {"error": str(e), "user": user})
            if self._error_count >= 3:
                suggestion = "Tip: Multiple errors detected. Try /reloadskills or /debug for diagnostics."
            else:
                suggestion = ""
            return "Sorry, I encountered an error while processing your request." + (" " + suggestion if suggestion else "")

    def compose_llm_prompt(self, prompt, user, thread_id):
        persona = self.persona
        personas = self.config.get("personas", {})
        if not isinstance(personas, dict): personas = {}
        persona_prompt = personas.get(persona, "")
        system_prompt = (
            self._custom_sysprompts.get(user) or
            persona_prompt or
            self.config.get("system_prompt", "You are Vivian, an intelligent, agentic assistant. Be direct, helpful, and sharp.")
        )
        examples = self.config.get("few_shot_examples", "")
        context = self._prepare_context(prompt, user, thread_id=thread_id)
        mode = self.mode
        goals = self.config.get("goals", {}).get(mode, "")
        full_prompt = f"{system_prompt}\n{examples}\n{goals}\n{context}\n\nUser: {prompt}\nVivian:"
        return full_prompt

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
        if not self.skills or not isinstance(self.skills, dict):
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

    def multi_agent_debate(self, proposal):
        debate_prompt = (
            f"Simulate 3 agentic Vivians debating the following plan. Each should critique, propose alternatives, and vote. Plan:\n{proposal}\n"
            "Return the consensus or highlight any disagreements."
        )
        try:
            if asyncio.iscoroutinefunction(send_to_model):
                debate = asyncio.get_event_loop().run_until_complete(send_to_model(debate_prompt))
            else:
                debate = send_to_model(debate_prompt)
        except Exception as e:
            debate = f"Debate failed: {e}"
        return debate

    def update_personality_profile(self, user, feedback):
        self.memory.log_event("vivian_personality_update", {"user": user, "feedback": feedback})