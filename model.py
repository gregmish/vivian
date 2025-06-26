import requests
import time
import logging
import json
import threading
import base64
from typing import Callable, List, Dict, Any, Optional, Union

class ModelError(Exception):
    pass

def default_privacy_cb(obj):
    """Redact common PII fields from dicts/lists before sending to OpenAI."""
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k in {"email", "password", "ssn", "api_key"} else default_privacy_cb(v)) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [default_privacy_cb(x) for x in obj]
    return obj

class SimpleRateLimiter:
    def __init__(self, max_per_minute=60):
        self.max_per_minute = max_per_minute
        self._lock = threading.Lock()
        self._calls = []

    def check(self, user_id, model):
        now = time.time()
        with self._lock:
            self._calls = [t for t in self._calls if now-t < 60]
            if len(self._calls) >= self.max_per_minute:
                return False, "API rate limit exceeded."
            self._calls.append(now)
        return True, None

def default_healthcheck_cb(api_url, api_key):
    """Check if the OpenAI API is reachable and models are listed."""
    try:
        url = "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(url, headers=headers, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False

def default_trace_cb(etype, data):
    logline = {"event": etype, "data": data, "timestamp": time.time()}
    with open("model_trace.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(logline) + "\n")
    return logline.get("trace_id", None)

class DummyQueue:
    def should_queue(self, model): return False
    def enqueue(self, payload): return "dummy_queue_id"

def count_tokens(text: str, model: str = "gpt-4") -> int:
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model(model)
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)

def _fire_hooks(event_type: str, data: dict, *hooks):
    for cb in hooks:
        if cb is not None:
            try:
                cb(event_type, data)
            except Exception as e:
                logging.debug(f"[Model] Hook error: {e}")

def get_best_openai_model(api_key, preferred="gpt-4o"):
    """Auto-detect best available OpenAI model for the API key."""
    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        models = [m["id"] for m in resp.json().get("data", [])]
        for m in [preferred, "gpt-4o", "gpt-4-vision-preview", "gpt-4", "gpt-3.5-turbo"]:
            if m in models:
                return m
        return models[0] if models else preferred
    except Exception:
        return preferred

def openai_embedding(text, api_key, model="text-embedding-3-small"):
    """Get OpenAI embedding for text (for RAG/memory)."""
    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {"model": model, "input": text}
    resp = requests.post(url, headers=headers, json=data, timeout=20)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]

def openai_speech_to_text(audio_file, api_key):
    """Transcribe audio file with OpenAI Whisper."""
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": open(audio_file, "rb")}
    data = {"model": "whisper-1"}
    resp = requests.post(url, headers=headers, files=files, data=data)
    resp.raise_for_status()
    return resp.json()["text"]

def openai_text_to_speech(text, api_key, voice="alloy"):
    """Generate speech from text using OpenAI TTS."""
    url = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {api_key}"}
    json_data = {"model": "tts-1", "input": text, "voice": voice}
    resp = requests.post(url, headers=headers, json=json_data, timeout=30)
    resp.raise_for_status()
    return resp.content  # Returns raw audio bytes

def send_to_openai_brain(
    context_or_prompt: Union[str, List[Dict[str, Any]]],
    config: Dict[str, Any],
    *,
    stream: bool = False,
    persona: Optional[str] = None,
    system_message: Optional[str] = None,
    history: Optional[List[Dict[str, Any]]] = None,
    retries: int = 2,
    multimodal_input: Optional[Dict[str, Any]] = None,
    on_stream: Optional[Callable[[str], None]] = None,
    debug: bool = False,
    usage_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    fallback_models: Optional[List[str]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    stop: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    user_id: Optional[str] = None,
    privacy_cb: Optional[Callable[[Any], Any]] = default_privacy_cb,
    rate_limit_cb: Optional[Callable[[str, str], Any]] = None,
    healthcheck_cb: Optional[Callable[[str, str], bool]] = None,
    trace_cb: Optional[Callable[[str, dict], Any]] = default_trace_cb,
    before_send: Optional[Callable[[dict], dict]] = None,
    after_receive: Optional[Callable[[dict], dict]] = None,
    return_full: bool = False,
    parse_json: bool = False,
    raise_on_fail: bool = False,
    log_prompt: bool = False,
    ab_test_group: Optional[str] = None,
    sandbox: bool = False,
    dry_run: bool = False,
    explain: bool = False,
    vision_image: Optional[str] = None,
    speech_file: Optional[str] = None,
    tts: bool = False,
    explainable: bool = True,
    memory_retrieve_cb: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
    memory_store_cb: Optional[Callable[[str, str], None]] = None,
    agent_reflection: bool = False,
    tool_plugin_cb: Optional[Callable[[str, List[Dict[str, Any]]], str]] = None,
    **kwargs
) -> Union[str, dict]:
    """
    Ultra-Real OpenAI Brain:
    - GPT-4o/GPT-4/3.5, vision, speech, streaming, function calling, memory/RAG, tool plugins, persona, explainability, privacy, rate limit, tracing, audit, agentic reflection.
    """
    api_key = api_key or config.get("api_key")
    if not api_key:
        raise ModelError("No OpenAI API key provided.")

    model = config.get("model")
    if not model:
        model = get_best_openai_model(api_key)
    api_url = config.get("api_url", "https://api.openai.com/v1/chat/completions")
    timeout = config.get("model_timeout", 60)
    if fallback_models is None:
        fallback_models = config.get("fallback_models", [])
    all_models = [model] + [m for m in fallback_models if m != model]

    # Memory/RAG: Retrieve context if callback is set
    if memory_retrieve_cb and isinstance(context_or_prompt, str):
        memory_ctx = memory_retrieve_cb(context_or_prompt)
        if memory_ctx:
            if not history:
                history = []
            history = memory_ctx + (history or [])

    sys_msg = system_message or f"You are {config.get('name', 'Vivian')}, persona: {persona or config.get('persona', 'default')}."
    if config.get("language") and config.get("localization_enabled"):
        sys_msg += f" Respond in {config['language']}."
    if ab_test_group:
        sys_msg += f" [A/B Test Group: {ab_test_group}]"

    # Privacy/PII Redaction
    if privacy_cb:
        context_or_prompt = privacy_cb(context_or_prompt)
        if history:
            history = privacy_cb(history)

    # Rate Limiting
    if rate_limit_cb:
        allowed, msg = rate_limit_cb(user_id, model)
        if not allowed:
            raise ModelError(msg or "Rate limit exceeded.")

    # Health Check
    if healthcheck_cb and not healthcheck_cb(api_url, api_key):
        raise ModelError("Model API health check failed.")

    # Tracing/Audit
    trace_id = None
    if trace_cb:
        trace_id = trace_cb("request", {
            "user_id": user_id,
            "model": model,
            "ab_test_group": ab_test_group,
            "prompt": str(context_or_prompt)[:1000]
        })

    # Dry run/sandbox
    if sandbox or dry_run:
        fake_content = "[DRY RUN] Model call skipped (sandbox mode)."
        return fake_content if not return_full else {"content": fake_content, "sandbox": True}

    # System prompt and context
    messages = [{"role": "system", "content": sys_msg}]
    if history:
        messages += history
    elif isinstance(context_or_prompt, list):
        messages += context_or_prompt
    else:
        messages.append({"role": "user", "content": str(context_or_prompt)})

    # Vision multimodal support
    if (vision_image or multimodal_input) and (model.startswith("gpt-4") or model.startswith("gpt-4o")):
        # OpenAI expects base64 image in a 'image_url'
        if vision_image:
            with open(vision_image, "rb") as imgf:
                img_b64 = base64.b64encode(imgf.read()).decode()
            user_msg = messages[-1]
            if isinstance(user_msg["content"], list):
                user_msg["content"].append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}})
            else:
                user_msg["content"] = [
                    {"type": "text", "text": user_msg["content"]},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                ]
        elif multimodal_input and "image" in multimodal_input:
            img_path = multimodal_input["image"]
            with open(img_path, "rb") as imgf:
                img_b64 = base64.b64encode(imgf.read()).decode()
            user_msg = messages[-1]
            user_msg["content"] = [
                {"type": "text", "text": user_msg["content"]},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    if stop:
        payload["stop"] = stop
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Function calling / tool plugin support (OpenAI tools)
    if tools and tool_plugin_cb:
        # If OpenAI calls a tool, call the plugin/tool callback
        def tool_callback(tool_call_name, params):
            return tool_plugin_cb(tool_call_name, params)
    else:
        tool_callback = None

    # Before-send middleware
    if before_send:
        payload = before_send(payload)

    if log_prompt:
        logging.info(f"[Model] Prompt for {payload['model']}: {json.dumps(payload)[:500]}")

    attempt = 0
    last_error = None

    for m in all_models:
        payload["model"] = m
        attempt = 0
        while attempt <= retries:
            try:
                start_time = time.time()
                if debug:
                    logging.info(f"[Model] Sending to {api_url} (model={m}): {json.dumps(payload)[:200]}...")

                # Whisper speech-to-text (if speech_file provided)
                if speech_file:
                    transcript = openai_speech_to_text(speech_file, api_key)
                    payload["messages"].append({"role": "user", "content": transcript})

                # Streaming support
                if stream and on_stream:
                    with requests.post(api_url, json=payload, headers=headers, timeout=timeout, stream=True) as response:
                        response.raise_for_status()
                        collected = ""
                        for line in response.iter_lines(decode_unicode=True):
                            if line:
                                try:
                                    data = json.loads(line)
                                    chunk = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if chunk:
                                        collected += chunk
                                        on_stream(chunk)
                                except Exception:
                                    pass
                        content = collected
                        full_response = {"content": content}
                else:
                    response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
                    response.raise_for_status()
                    data = response.json()
                    if after_receive:
                        data = after_receive(data)
                    # Function/tool calling handling
                    if tools and "tool_calls" in data.get("choices", [{}])[0]["message"]:
                        tool_calls = data["choices"][0]["message"]["tool_calls"]
                        for tool_call in tool_calls:
                            if tool_callback:
                                tool_result = tool_callback(tool_call["function"]["name"], tool_call["function"].get("arguments", {}))
                                # Add tool result as assistant message and retry
                                payload["messages"].append({
                                    "role": "tool",
                                    "name": tool_call["function"]["name"],
                                    "content": tool_result
                                })
                                # Recurse with updated messages
                                return send_to_openai_brain(context_or_prompt, config, **locals())
                    content = (
                        data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        or "[Model] No output."
                    )
                    full_response = data

                elapsed = time.time() - start_time
                if debug:
                    logging.info(f"[Model] Used model: {m}, time: {elapsed:.2f}s, tokens: {count_tokens(content)}")

                # Store conversation in memory if callback is set
                if memory_store_cb and isinstance(context_or_prompt, str):
                    memory_store_cb(context_or_prompt, content)

                if explain and explainable:
                    content = f"[EXPLAIN]\nPrompt: {json.dumps(payload, indent=2)}\n\nResponse: {content}"

                usage_info = {"content": content, "model": m, "tokens": count_tokens(content), "elapsed": elapsed, "trace_id": trace_id}
                if usage_cb:
                    try: usage_cb(usage_info)
                    except Exception: pass

                if trace_cb:
                    trace_cb("response", {"trace_id": trace_id, "model": m, "content": content, "elapsed": elapsed})

                if tts:
                    audio_bytes = openai_text_to_speech(content, api_key)
                    return audio_bytes if not return_full else {"content": content, "audio": audio_bytes}

                if parse_json:
                    try:
                        content_json = json.loads(content)
                        return content_json if not return_full else {"content": content_json, "raw": full_response}
                    except Exception:
                        if raise_on_fail:
                            raise
                        else:
                            return content if not return_full else full_response

                return content if not return_full else full_response

            except Exception as e:
                last_error = e
                if trace_cb:
                    trace_cb("error", {"trace_id": trace_id, "model": m, "error": str(e)})
                time.sleep(min(2 ** attempt, 10))
                attempt += 1

    if trace_cb:
        trace_cb("fail", {"trace_id": trace_id, "error": str(last_error), "models": all_models})

    if raise_on_fail:
        raise ModelError(f"[Model] All models failed after retries. Last error: {str(last_error)}")

    return f"[Model] ERROR: All models failed after retries. Last error: {str(last_error)}"

def model_usage_report(content: str, model: str):
    return {
        "model": model,
        "tokens": count_tokens(content, model),
        "length": len(content)
    }