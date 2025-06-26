import logging
from .core import AdvancedLLMCore
from typing import Dict, Any, Optional, List, Callable, Union

class VivianBrain:
    """
    VivianBrain: AGI orchestrator for LLM, memory, plugins, user modeling, feedback, evolution, 
    collaboration, session management, explainability, multi-modal, and meta-cognition.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm = AdvancedLLMCore(config)
        self.session_context: Dict[str, Any] = {}
        self.plugins: Dict[str, Callable] = {}
        self.memory: List[Dict[str, Any]] = []
        self.active_users: List[str] = []
        self.global_feedback: List[Dict[str, Any]] = []
        self.runtime_flags: Dict[str, Any] = {}
        self.session_id: Optional[str] = None
        self.meta_log: List[str] = []

    # ===== Main Reasoning & Generation =====
    def think(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        mode: Optional[str] = None,
        images: Optional[List[str]] = None,
        stream: bool = False,
        functions: Optional[List[Dict[str, Any]]] = None,
        function_call: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        stop: Optional[List[str]] = None,
        collaboration: bool = False,
        plugin_calls: Optional[List[Dict[str, Any]]] = None,
        persona: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        logging.info(f"[VivianBrain] Thinking: {prompt[:60]}... (User: {user_id})")
        context = self._build_context(user_id)
        # Pre-process: meta-cognition, auto-flag, plugin triggers
        self._meta_cognition(prompt, user_id)
        plugin_response = self._plugin_preprocess(prompt, plugin_calls)
        if plugin_response is not None:
            self._log_meta(f"Plugin handled: {plugin_response}")
            return plugin_response

        # LLM Core Generation
        output = self.llm.generate(
            prompt=prompt,
            persona=persona,
            context=context,
            user_id=user_id,
            mode=mode,
            images=images,
            stream=stream,
            functions=functions,
            function_call=function_call,
            system_prompt=system_prompt,
            stop=stop,
            collaboration=collaboration,
            **kwargs
        )
        # Post-process: feedback, memory, plugin post, meta
        self._store_memory(prompt, output, user_id, context)
        self._plugin_postprocess(output, plugin_calls)
        self._meta_cognition_post(output, user_id)
        return output

    # ===== Memory, Summarization, and Long-term Recall =====
    def _store_memory(self, prompt, output, user_id, context):
        msg = {
            "user_id": user_id,
            "prompt": prompt,
            "output": output,
            "context": context,
            "timestamp": self._now()
        }
        self.memory.append(msg)
        # Limit memory for performance; summarize if too long
        if len(self.memory) > 200:
            self._summarize_memory()

    def _summarize_memory(self):
        # Summarize old memory (stub: can use LLM for real)
        summary = " | ".join(m['prompt'][:20] for m in self.memory[-10:])
        self.memory = self.memory[-50:]  # keep recent
        self.meta_log.append(f"[Memory] Summarized: {summary}")

    # ===== User and Persona Modeling =====
    def set_user_profile(self, user_id: str, profile: Dict[str, Any]):
        self.llm.set_user_profile(user_id, profile)
        logging.info(f"[VivianBrain] Set profile for {user_id}")

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        return self.llm.get_user_profile(user_id)

    def add_active_user(self, user_id: str):
        if user_id not in self.active_users:
            self.active_users.append(user_id)
            self.meta_log.append(f"[Session] Added user {user_id}")

    def remove_active_user(self, user_id: str):
        if user_id in self.active_users:
            self.active_users.remove(user_id)
            self.meta_log.append(f"[Session] Removed user {user_id}")

    # ===== Plugin/Tool Integration and Management =====
    def register_plugin(self, name: str, func: Callable):
        self.plugins[name] = func
        self.llm.register_plugin(name, func)
        logging.info(f"[VivianBrain] Registered plugin: {name}")

    def call_plugin(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name in self.plugins:
            return self.plugins[name](**arguments)
        return self.llm.call_function(name, arguments)

    def _plugin_preprocess(self, prompt: str, plugin_calls: Optional[List[Dict[str, Any]]]):
        if plugin_calls:
            for call in plugin_calls:
                name = call.get("name")
                args = call.get("args", {})
                if name in self.plugins:
                    return self.plugins[name](**args)
        return None

    def _plugin_postprocess(self, output: str, plugin_calls: Optional[List[Dict[str, Any]]]):
        # Hook for post-processing after LLM/gen, e.g., side effects or notifications
        pass

    # ===== Feedback, Evaluation, and Evolution =====
    def feedback(self, message: str, score: int, user_id: Optional[str] = None):
        feedback_entry = {
            "message": message,
            "score": score,
            "user_id": user_id,
            "timestamp": self._now()
        }
        self.global_feedback.append(feedback_entry)
        self.llm.accept_feedback(f"{message} (score: {score})")
        logging.info(f"[VivianBrain] Feedback: {message} ({score}) by {user_id}")

    def evolve(self, instruction: str, user_id: Optional[str] = None, persona: Optional[Dict[str, Any]] = None) -> str:
        logging.info(f"[VivianBrain] Evolution Requested: {instruction} (User: {user_id})")
        return self.llm.generate(
            prompt=f"Modify yourself based on this instruction:\n{instruction}",
            mode="tutor",
            user_id=user_id,
            persona=persona
        )

    # ===== Multi-Modal and Collaboration =====
    def add_collaborator(self, user_id: str):
        self.llm.add_collaborator(user_id)
        self.add_active_user(user_id)

    def remove_collaborator(self, user_id: str):
        self.llm.remove_collaborator(user_id)
        self.remove_active_user(user_id)

    def broadcast_message(self, message: str):
        self.llm.broadcast_message(message)
        for user in self.active_users:
            self.meta_log.append(f"[Broadcast] {message} to {user}")

    def receive_message(self, user_id: str, message: str):
        self.llm.receive_message(user_id, message)
        self._store_memory(f"{user_id}: {message}", "", user_id, {})

    # ===== Session Management, Export, Import, Replay =====
    def export_session(self) -> Dict[str, Any]:
        session = {
            "memory": self.memory,
            "llm_session": self.llm.export_session(),
            "meta_log": self.meta_log,
            "active_users": self.active_users,
            "session_id": self.session_id
        }
        return session

    def import_session(self, session: Dict[str, Any]):
        self.memory = session.get("memory", [])
        self.llm.import_session(session.get("llm_session", {}))
        self.meta_log = session.get("meta_log", [])
        self.active_users = session.get("active_users", [])
        self.session_id = session.get("session_id", None)
        logging.info("[VivianBrain] Session imported.")

    def replay_session(self):
        self.llm.replay_session()
        for m in self.memory:
            print(f"[{m['timestamp']}] {m['user_id']}: {m['prompt']} => {m['output']}")

    # ===== Explainability, Analytics, Meta-Cognition =====
    def explain(self) -> str:
        stats = self.llm.explain()
        meta = "\n".join(self.meta_log[-5:])
        return f"{stats}\nRecent meta:\n{meta}"

    def cost_summary(self) -> str:
        return self.llm.cost_summary()

    def clear_history(self):
        self.llm.clear_history()
        self.memory.clear()
        self.meta_log.append("[Meta] Cleared all history.")

    def get_history(self) -> List[Dict[str, Any]]:
        return self.llm.get_history()

    def get_usage_stats(self) -> List[Dict[str, Any]]:
        return self.llm.get_usage_stats()

    def set_runtime_flag(self, flag: str, value: Any):
        self.runtime_flags[flag] = value
        self.meta_log.append(f"[Flag] {flag} set to {value}")

    def get_runtime_flag(self, flag: str) -> Any:
        return self.runtime_flags.get(flag)

    # ===== Meta-Cognition, Self-Reflection, and Self-Healing =====
    def _meta_cognition(self, prompt: str, user_id: Optional[str]):
        # Self-evaluate before LLM call (stub)
        if "diagnose" in prompt.lower():
            self.meta_log.append(f"[Meta] Detected diagnostic prompt by {user_id}")

    def _meta_cognition_post(self, output: str, user_id: Optional[str]):
        # Self-reflection after LLM call (stub)
        if "error" in output.lower():
            self.meta_log.append(f"[Meta] Detected error in output for {user_id}")

    def _log_meta(self, message: str):
        self.meta_log.append(f"[Meta] {message}")

    def _now(self):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    # ===== Advanced/Expansion Stubs =====
    def embed(self, text: str) -> List[float]:
        return self.llm.embed(text)

    def retrieve_similar(self, text: str, top_k: int = 3) -> List[str]:
        return self.llm.retrieve_similar(text, top_k=top_k)

    def save_prompt_template(self, name: str, template: str):
        self.llm.save_prompt_template(name, template)

    def get_prompt_template(self, name: str) -> Optional[str]:
        return self.llm.get_prompt_template(name)