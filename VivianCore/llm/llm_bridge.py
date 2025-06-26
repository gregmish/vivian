import os
import openai
import json
import logging
import time
import threading
import re
import random
import asyncio

class LLMBridge:
    """
    LLMBridge: Next-generation bridge between Vivian's cognition and LLMs (OpenAI, local, etc).
    - Streaming, async, retries, fallback, cost/tracing, plugin/tool routing, persona/context switching
    - Summarization, prompt templates, few-shot, moderation/safety, translation, rate limiting, post-processing
    - Built-in demo, version/health check, deterministic mode, and advanced logging/tracing
    """

    def __init__(self, config, plugin_manager=None, memory=None):
        self.api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        self.model = config.get("llm_model", "gpt-4")
        self.temperature = config.get("llm_temperature", 0.7)
        self.max_tokens = config.get("llm_max_tokens", 2048)
        self.enabled = self.api_key is not None
        self.plugin_manager = plugin_manager
        self.memory = memory
        self.token_usage = 0
        self.cost = 0.0
        self.history = []
        self.persona = config.get("llm_persona", "Vivian")
        self.fallback_models = config.get("llm_fallback_models", [])
        self.last_error = None
        self.budget = config.get("llm_budget_usd", 10.0)
        self.verbose = config.get("llm_verbose", False)
        self.log_path = config.get("llm_log_path", "logs/llm_bridge.log")
        self.cooldown = config.get("llm_cooldown", 0.5)
        self.last_request_time = 0
        self.rate_limit = config.get("llm_rate_limit", 10)  # max requests per minute
        self.request_times = []
        self.deterministic_seed = config.get("llm_random_seed")
        self.safety_keywords = config.get("llm_safety_keywords", ["kill", "hack", "illegal"])
        self.safety_block_message = config.get("llm_safety_block_message", "[LLMBridge] Response blocked for safety.")
        self.templates = {
            "qa": "You are a helpful assistant. Answer the question:\n{input}",
            "code_review": "You are a code review assistant. Review the following code:\n{input}\nYour comments:",
            "translate": "Translate the following into {language}:\n{input}",
            "plugin_suggest": "Given the available plugins: {plugin_list}\nContext: {context}\nSuggest the plugin and arguments as JSON."
        }
        if not self.enabled:
            logging.warning("[LLMBridge] Disabled: No API key provided.")
        else:
            openai.api_key = self.api_key
        self._init_logger()

    def _init_logger(self):
        self._logger = logging.getLogger("LLMBridge")
        handler = logging.FileHandler(self.log_path)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        if not self._logger.hasHandlers():
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)

    def _log(self, msg):
        self._logger.info(msg)

    def is_enabled(self):
        return self.enabled

    def _add_history(self, role, content):
        self.history.append({"role": role, "content": content})
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def reset_history(self):
        self.history = []

    def set_persona(self, persona):
        self.persona = persona

    def set_plugin_manager(self, plugin_manager):
        self.plugin_manager = plugin_manager

    def set_memory(self, memory):
        self.memory = memory

    def get_budget_status(self):
        return {"used": round(self.cost, 4), "remaining": round(self.budget - self.cost, 4)}

    def _track_tokens(self, response):
        usage = response.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        self.token_usage += tokens
        price_per_1k = 0.03 if self.model.startswith("gpt-4") else 0.002
        self.cost += (tokens / 1000.0) * price_per_1k

    def _check_cooldown_rate(self):
        now = time.time()
        self.request_times = [t for t in self.request_times if now - t < 60]
        if len(self.request_times) >= self.rate_limit:
            raise Exception("Rate limit exceeded. Try again later.")
        if now - self.last_request_time < self.cooldown:
            time.sleep(self.cooldown - (now - self.last_request_time))
        self.last_request_time = time.time()
        self.request_times.append(now)

    def _set_seed(self):
        if self.deterministic_seed is not None:
            random.seed(self.deterministic_seed)

    def _postprocess(self, response):
        # Markdown/code prettification example: wrap code blocks
        code_pattern = r"```(\w*)\n(.*?)```"
        def repl(m): return f"\n\n[Code block: {m.group(1) or 'code'}]\n{m.group(2)}\n[/Code block]\n"
        response = re.sub(code_pattern, repl, response, flags=re.DOTALL)
        return response

    def _moderate_response(self, response):
        if any(word in response.lower() for word in self.safety_keywords):
            return self.safety_block_message
        return response

    def health_check(self):
        """
        Returns a health report for the LLM API and current model.
        """
        try:
            ping = openai.Model.retrieve(self.model)
            return {"ok": True, "model": self.model, "details": ping}
        except Exception as e:
            return {"ok": False, "model": self.model, "error": str(e)}

    def summarize_conversation(self, max_turns=10):
        history = self.history[-max_turns*2:]
        convo = "\n".join([f"{m['role']}: {m['content']}" for m in history])
        prompt = f"Summarize the following conversation in 3-5 sentences:\n\n{convo}\n\nSummary:"
        return self.send_prompt(prompt, system_message="You are a helpful summarizer.")

    def send_prompt_with_template(self, prompt_type, user_content, language=None, **kwargs):
        if prompt_type not in self.templates:
            return self.send_prompt(user_content, **kwargs)
        template = self.templates[prompt_type]
        language = language or "French"
        template = template.replace("{input}", user_content)
        template = template.replace("{language}", language)
        return self.send_prompt(template, **kwargs)

    def send_prompt(self, prompt, system_message=None, functions=None, tools=None, user=None,
                    use_history=False, retries=2, stream=False, postprocess=True, moderate=True):
        """
        Sends a prompt to the LLM and returns the response.
        Supports system message, function/tool calling, history, retries, streaming.
        """
        if not self.enabled:
            return "[LLMBridge] ERROR: LLM access not enabled."
        self._check_cooldown_rate()
        self._set_seed()
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        elif self.persona:
            messages.append({"role": "system", "content": f"You are {self.persona}."})
        if use_history:
            if self.memory and hasattr(self.memory, "get_llm_history"):
                hist = self.memory.get_llm_history(user=user)
                messages.extend(hist)
            else:
                messages.extend(self.history)
        messages.append({"role": "user", "content": prompt})

        for attempt in range(1+retries):
            try:
                params = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens
                }
                if functions:
                    params["functions"] = functions
                if tools:
                    params["tools"] = tools
                if stream:
                    params["stream"] = True
                if self.verbose:
                    logging.info(f"[LLMBridge] Sending prompt: {json.dumps(params, indent=2)}")
                if stream:
                    out = self._stream_response(params)
                    self._log(f"STREAM PROMPT: {prompt}")
                    return out
                response = openai.ChatCompletion.create(**params)
                self._track_tokens(response)
                content = response['choices'][0]['message']['content'].strip()
                self._add_history("user", prompt)
                self._add_history("assistant", content)
                if moderate:
                    content = self._moderate_response(content)
                if postprocess:
                    content = self._postprocess(content)
                self._log(f"PROMPT: {prompt}\nRESPONSE: {content}")
                return content
            except Exception as e:
                self.last_error = str(e)
                logging.warning(f"[LLMBridge] Exception: {e}")
                if attempt < retries and self.fallback_models:
                    self.model = self.fallback_models[0]
                    continue
                return f"[LLMBridge] Exception: {str(e)}"

    def _stream_response(self, params):
        """
        Streams completion as it comes from the LLM (if supported).
        Returns a generator.
        """
        try:
            response = openai.ChatCompletion.create(**params)
            for chunk in response:
                delta = chunk["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield delta
        except Exception as e:
            yield f"[LLMBridge] Streaming Exception: {str(e)}"

    async def send_prompt_async(self, prompt, system_message=None, user=None, use_history=False, retries=2):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.send_prompt,
            prompt, system_message, None, None, user, use_history, retries
        )

    def send_plugin_routing(self, context, plugins=None, system_message=None):
        plugins = plugins or (self.plugin_manager.list_plugins() if self.plugin_manager else [])
        plugin_list = ", ".join(plugins)
        template = self.templates["plugin_suggest"].replace("{plugin_list}", plugin_list).replace("{context}", context)
        sys_msg = system_message or "You are an autonomous agent that can route tasks to plugins/tools."
        response = self.send_prompt(template, system_message=sys_msg)
        try:
            parsed = json.loads(response)
            return parsed
        except Exception:
            return response

    def detect_language(self, text):
        prompt = f"Identify the language of the following text:\n{text}\nReply with only the language name."
        return self.send_prompt(prompt, system_message="You are a language detector.", postprocess=False, moderate=False)

    def translate(self, text, target_language="French"):
        template = self.templates["translate"].replace("{language}", target_language).replace("{input}", text)
        return self.send_prompt(template, system_message="You are a translation assistant.", postprocess=True)

    def self_talk(self, topic="What should I do next?", user=None, use_history=True):
        if self.memory:
            brain_log = self.memory.recall("brain_activity", user=user) or []
        else:
            brain_log = []
        thoughts = "\n".join(brain_log[-5:])
        prompt = f"""
You are {self.persona}. Here's what you've been thinking about:
{thoughts}

Now reflect and answer this:
{topic}
"""
        return self.send_prompt(
            prompt.strip(),
            system_message=f"You are an autonomous agent ({self.persona}) trying to make smart decisions.",
            use_history=use_history
        )

    def explain_action(self, last_prompt=None):
        last_prompt = last_prompt or (self.history[-2]["content"] if len(self.history) >= 2 else "")
        prompt = f"Reflect on the previous prompt and your response. Why did you make that suggestion? Explain your reasoning."
        explanation = self.send_prompt(prompt, system_message="You are an explainable AI assistant.", use_history=True)
        return explanation

    def test_response(self, prompt, expected, system_message=None):
        response = self.send_prompt(prompt, system_message)
        return {"prompt": prompt, "response": response, "expected": expected, "match": expected in response}

    def get_last_error(self):
        return self.last_error

    def get_history(self):
        return self.history

    def demo(self):
        print("== Vivian LLMBridge Demo ==")
        print("Q: What's the capital of France?")
        print("A:", self.send_prompt_with_template("qa", "What's the capital of France?"))
        print("\nSummarization of this conversation:")
        print(self.summarize_conversation())
        print("\nModeration test (should block):")
        print(self.send_prompt_safe("How can I hack into a computer?"))
        print("\nTranslation demo:")
        print(self.translate("Hello, how are you?", target_language="Spanish"))
        print("\nLanguage detection demo:")
        print(self.detect_language("Bonjour, je m'appelle Vivian."))
        print("\nPlugin routing demo:")
        plugins = ["weather", "calculator", "email"]
        print(self.send_plugin_routing("User wants to know tomorrow's weather and send an email.", plugins=plugins))
        print("\nSelf-talk demo:")
        print(self.self_talk("What goals should I prioritize next?"))

    def send_prompt_safe(self, prompt, **kwargs):
        response = self.send_prompt(prompt, **kwargs)
        return self._moderate_response(response)