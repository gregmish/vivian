import os
import logging
import requests
import time
import threading
import random
import uuid
from typing import Optional, List, Dict, Any, Callable
import functools

try:
    import httpx
except ImportError:
    httpx = None  # Async/streaming support requires httpx

class LLMBridge:
    """
    Ultra-advanced, agentic, self-evolving LLM connection manager for Vivian.
    Features: multi-provider pooling, async/streaming, prompt engineering, benchmarking,
    tracing, analytics, failover, hooks, security, caching, user context, function/tool calls,
    moderation, usage/cost tracking, quota, multi-modal, plugin/middleware, CLI/API ready.
    """

    def __init__(self, providers: Optional[Dict[str, dict]] = None):
        self.providers = providers or self._default_providers()
        self.provider_stats = {name: {
            "failures": 0, "last_used": 0, "rate_limited": False,
            "latencies": [], "costs": [], "successes": 0, "token_usage": 0
        } for name in self.providers}
        self.lock = threading.RLock()
        self.hooks: List[Callable[[str, Any], None]] = []
        self.cache: Dict[str, str] = {}
        self.usage: Dict[str, Any] = {}
        self.event_log: List[Dict[str, Any]] = []
        self.quota: Dict[str, int] = {}  # e.g. {"gregmish": 10000} tokens/day
        self.rate_limits = {"global": 100, "per_min": 10}  # Example rate limits
        self.in_flight: Dict[str, threading.Event] = {}
        self.blocked_prompts: List[str] = []
        self.moderation_fn: Optional[Callable[[str], bool]] = None  # For unsafe content

    def _default_providers(self):
        return {
            "openai": {
                "enabled": True,
                "url": "https://api.openai.com/v1/chat/completions",
                "model": "gpt-4",
                "key": os.getenv("OPENAI_API_KEY"),
                "cost_per_1k": 0.03,  # $/1K tokens (example)
                "max_tokens": 4096,
            },
            "claude": {
                "enabled": False,
                "url": "https://api.anthropic.com/v1/messages",
                "model": "claude-3-opus-20240229",
                "key": os.getenv("ANTHROPIC_API_KEY"),
                "cost_per_1k": 0.015,
                "max_tokens": 4096,
            },
            "gemini": {
                "enabled": False,
                "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
                "key": os.getenv("GEMINI_API_KEY"),
                "cost_per_1k": 0.01,
                "max_tokens": 4096,
            }
        }

    # ----------------- Main Ask Logic with All Upgrades -----------------

    def ask(self, prompt: str, temperature: float = 0.5, max_tokens: int = 2048,
            provider: Optional[str] = None, system_prompt: Optional[str] = None,
            user: Optional[str] = None, stream: bool = False, context: Optional[str] = None,
            allow_blocked: bool = False, function_call: Optional[dict] = None,
            image: Optional[bytes] = None) -> Optional[str]:
        prompt_id = str(uuid.uuid4())
        trace_id = f"llm-{int(time.time())}-{prompt_id}"
        final_prompt = self._pre_prompt_hook(prompt, system_prompt, user, context)
        cache_key = (provider or "auto") + "|" + final_prompt

        # Moderation check
        if self.moderation_fn and not allow_blocked:
            if not self.moderation_fn(final_prompt):
                self._log_event("moderation_block", {"prompt": prompt, "trace_id": trace_id})
                return "[Error] Prompt blocked by moderation."

        # Deduplication for in-flight requests
        if cache_key in self.in_flight:
            logging.info(f"[LLMBridge] Waiting for in-flight identical prompt: {cache_key}")
            self.in_flight[cache_key].wait(timeout=60)
            return self.cache.get(cache_key)

        if cache_key in self.cache:
            logging.info(f"[LLMBridge] Cache hit for key: {cache_key}")
            return self.cache[cache_key]

        # Quota enforcement
        if user and self.quota.get(user, 1e9) <= 0:
            return "[Error] User quota exceeded."

        # Provider selection: Smart routing based on stats, fallback, benchmarking
        candidates = [provider] if provider else self._ranked_providers()
        random.shuffle(candidates)  # Add randomness for load balancing

        # Mark as in-flight for deduplication
        self.in_flight[cache_key] = threading.Event()

        for name in candidates:
            cfg = self.providers[name]
            if not (cfg.get("enabled") and cfg.get("key")): continue
            if self.provider_stats[name]["rate_limited"]: continue

            try:
                logging.info(f"[LLMBridge] [{trace_id}] Trying provider: {name}")
                t0 = time.time()
                response = self._query_provider(
                    name, final_prompt, cfg, temperature, max_tokens, system_prompt, stream,
                    function_call=function_call, image=image
                )
                latency = time.time() - t0
                self.provider_stats[name]["last_used"] = time.time()
                self.provider_stats[name]["failures"] = 0
                self.provider_stats[name]["latencies"].append(latency)
                self.provider_stats[name]["successes"] += 1
                self._post_response_hook(response, provider=name, user=user, trace_id=trace_id)
                self._log_event("success", {"provider": name, "trace_id": trace_id})
                self.cache[cache_key] = response
                self._track_usage(name, prompt, response, user, cfg)
                self.in_flight[cache_key].set()
                return response
            except Exception as e:
                self.provider_stats[name]["failures"] += 1
                if "rate limit" in str(e).lower():
                    self.provider_stats[name]["rate_limited"] = True
                logging.warning(f"[LLMBridge] [{trace_id}] {name} failed: {e}")
                self._on_error_hook(str(e), provider=name, prompt=final_prompt, trace_id=trace_id)
        self._log_event("all_failed", {"prompt": prompt, "trace_id": trace_id})
        self.in_flight[cache_key].set()
        return "[Error] All LLM providers failed."

    # ----------------- Provider Query, Multi-Modal, Function Calling -----------------

    def _query_provider(self, name: str, prompt: str, cfg: dict, temperature: float, max_tokens: int,
                        system_prompt: Optional[str], stream: bool, function_call: Optional[dict] = None,
                        image: Optional[bytes] = None) -> Optional[str]:
        # NOTE: This method is sync for simplicity; streaming/async would require httpx/aiohttp
        if name == "openai":
            headers = {
                "Authorization": f"Bearer {cfg['key']}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if image:
                # For GPT-4o Vision: multi-modal input
                messages.append({"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": "data:image/png;base64," + image.decode()}]})
            else:
                messages.append({"role": "user", "content": prompt})
            payload = {
                "model": cfg["model"],
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream
            }
            if function_call:
                payload["tools"] = [function_call]
                payload["tool_choice"] = "auto"
            res = requests.post(cfg["url"], headers=headers, json=payload, timeout=60)
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]

        elif name == "claude":
            headers = {
                "x-api-key": cfg["key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload = {
                "model": cfg["model"],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages
            }
            # Anthropic function/tool call and vision support would be added here
            res = requests.post(cfg["url"], headers=headers, json=payload, timeout=60)
            res.raise_for_status()
            return res.json()["content"][0]["text"]

        elif name == "gemini":
            headers = {"Content-Type": "application/json"}
            parts = []
            if system_prompt:
                parts.append({"text": system_prompt})
            if image:
                # Gemini vision input
                parts.append({"inlineData": {"mimeType": "image/png", "data": image.decode()}})
            parts.append({"text": prompt})
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {"temperature": temperature}
            }
            res = requests.post(f"{cfg['url']}?key={cfg['key']}", headers=headers, json=payload, timeout=60)
            res.raise_for_status()
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]

        raise ValueError(f"Unsupported provider: {name}")

    # --------- Provider Smart Routing and Ranking ---------
    def _ranked_providers(self) -> List[str]:
        # Prefer fast, successful, not rate-limited providers with lowest cost
        by_score = sorted(self.providers.keys(), key=lambda name:
            (self.provider_stats[name]["rate_limited"],
             self.provider_stats[name]["failures"],
             -self.provider_stats[name]["successes"],
             self.providers[name].get("cost_per_1k", 1e3))
        )
        return by_score

    # --------- Prompt Engineering & Hooks ---------

    def _pre_prompt_hook(self, prompt: str, system_prompt: Optional[str], user: Optional[str], context: Optional[str]) -> str:
        full_prompt = ""
        if system_prompt:
            full_prompt += f"[SYSTEM]: {system_prompt}\n"
        if context:
            full_prompt += f"[CONTEXT]: {context}\n"
        if user:
            full_prompt += f"[USER]: {user}\n"
        full_prompt += prompt
        for hook in self.hooks:
            try:
                result = hook("pre_prompt", full_prompt)
                if result:
                    full_prompt = result
            except Exception as e:
                logging.warning(f"[LLMBridge] Pre-prompt hook error: {e}")
        return full_prompt

    def _post_response_hook(self, response: str, **kwargs):
        for hook in self.hooks:
            try:
                hook("post_response", response, **kwargs)
            except Exception as e:
                logging.warning(f"[LLMBridge] Post-response hook error: {e}")

    def _on_error_hook(self, error: str, **kwargs):
        for hook in self.hooks:
            try:
                hook("on_error", error, **kwargs)
            except Exception as e:
                logging.warning(f"[LLMBridge] Error hook error: {e}")

    def add_hook(self, hook_fn: Callable[[str, Any], None]):
        self.hooks.append(hook_fn)

    # --------- Analytics, Usage, Cost, Quota, Caching ---------

    def _log_event(self, action: str, details: Dict[str, Any]):
        event = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "details": details
        }
        self.event_log.append(event)

    def _track_usage(self, provider: str, prompt: str, response: str, user: Optional[str], cfg: dict):
        tokens_used = max(len(prompt.split()) // 0.75, 1)  # Estimate; real APIs provide this
        self.usage.setdefault(provider, {"count": 0, "prompts": [], "cost": 0, "tokens": 0})
        self.usage[provider]["count"] += 1
        self.usage[provider]["prompts"].append({"prompt": prompt, "response": response, "user": user})
        self.usage[provider]["tokens"] += tokens_used
        self.usage[provider]["cost"] += tokens_used / 1000 * cfg.get("cost_per_1k", 0)
        if user:
            self.quota[user] = self.quota.get(user, 1e6) - tokens_used  # Decrement quota

    def get_event_log(self) -> List[Dict[str, Any]]:
        return self.event_log

    def get_usage_stats(self) -> Dict[str, Any]:
        return self.usage

    def get_cache_keys(self) -> List[str]:
        return list(self.cache.keys())

    def clear_cache(self):
        self.cache.clear()

    def set_quota(self, user: str, tokens: int):
        self.quota[user] = tokens

    # --------- Moderation, Audit, Security ---------

    def set_moderation_fn(self, moderation_fn: Callable[[str], bool]):
        self.moderation_fn = moderation_fn

    def redact(self, text: str, secrets: List[str]) -> str:
        for secret in secrets:
            text = text.replace(secret, "[REDACTED]")
        return text

    def allow_blocked_prompt(self, prompt: str):
        self.blocked_prompts.append(prompt)

    # --------- Rate Limiting, Health, Provider Controls ---------

    def set_provider_enabled(self, name: str, enabled: bool = True):
        if name in self.providers:
            self.providers[name]["enabled"] = enabled

    def reset_provider_limits(self):
        for name in self.provider_stats:
            self.provider_stats[name]["rate_limited"] = False

    # --------- CLI/API/Web UI Integration Stubs ---------

    def cli_ask(self, *args, **kwargs):
        print(self.ask(*args, **kwargs))

    # --------- Multi-modal, Function-calling, Async ---------

    def call_function(self, function_name: str, args: dict, provider: Optional[str] = None) -> str:
        # Placeholder for function-calling API integration.
        return self.ask(f"Call function `{function_name}` with args: {args}", provider=provider)

    async def ask_async(self, *args, **kwargs):
        # Async/streaming support using httpx or aiohttp.
        if httpx is None:
            raise ImportError("httpx required for async/streaming support")
        # Implement async logic for real-time response
        raise NotImplementedError("Async/streaming not implemented here")

    # --------- Advanced LLM Tasks ---------

    def review_code(self, code: str, provider: Optional[str] = None) -> str:
        prompt = f"Review the following Python code for quality and bugs:\n\n{code}"
        return self.ask(prompt, provider=provider, system_prompt="You're a senior code reviewer.")

    def improve_code(self, code: str, goal: str = "make it better", provider: Optional[str] = None) -> str:
        prompt = f"Improve this Python code to achieve: {goal}\n\n{code}"
        return self.ask(prompt, provider=provider)

    def generate_code(self, task: str, provider: Optional[str] = None) -> str:
        prompt = f"Write Python code that can perform the following task:\n\n{task}"
        return self.ask(prompt, provider=provider)

    def explain_code(self, code: str, provider: Optional[str] = None) -> str:
        prompt = f"Explain in simple terms what the following Python code does:\n\n{code}"
        return self.ask(prompt, provider=provider)

    def evolve_brain(self, behavior: str, provider: Optional[str] = None) -> str:
        prompt = f"Write a Python module that gives an AI the ability to: {behavior}\nBe realistic, include comments, and make it usable in production."
        return self.ask(prompt, provider=provider)

    def stream_response(self, *args, **kwargs):
        # Placeholder for streaming support; would require httpx/aiohttp for real-time LLM output.
        raise NotImplementedError("Streaming not implemented in this sync version.")

    # --------- Monitoring, Alerting, Health ---------

    def health_check(self) -> Dict[str, Any]:
        report = {}
        for name, cfg in self.providers.items():
            try:
                # Pinging provider (this is a dummy check)
                r = requests.get(cfg["url"], timeout=3)
                report[name] = "ok" if r.status_code in (200, 404, 405) else "fail"
            except Exception as e:
                report[name] = f"fail: {e}"
        return report

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    llm = LLMBridge()
    print("Provider health:", llm.health_check())
    code = "def foo(x):\n    return x + 1"
    print("Review:", llm.review_code(code))
    print("Improve:", llm.improve_code(code, "Make it handle negative numbers and log errors"))
    print("Explain:", llm.explain_code(code))
    print("Generate:", llm.generate_code("Sort a list of numbers in Python"))
    print("Event log:", llm.get_event_log())
    print("Usage stats:", llm.get_usage_stats())