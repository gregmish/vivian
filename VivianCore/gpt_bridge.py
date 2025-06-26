import openai
import os
import logging
import time
import json
import uuid
import asyncio
from typing import List, Dict, Optional, Union, Any, Callable

# === GPT Model Config & API Setup ===
DEFAULT_MODEL = os.environ.get("VIVIAN_GPT_MODEL", "gpt-4")
openai.api_key = os.environ.get("OPENAI_API_KEY", "your_openai_api_key_here")
DEFAULT_TIMEOUT = int(os.environ.get("VIVIAN_GPT_TIMEOUT", "120"))
DEFAULT_ORG = os.environ.get("OPENAI_ORGANIZATION", None)
if DEFAULT_ORG:
    openai.organization = DEFAULT_ORG

# === State/Analytics ===
GPT_REQUEST_HISTORY: List[Dict[str, Any]] = []
GPT_ERROR_HISTORY: List[Dict[str, Any]] = []
GPT_CONVERSATIONS: Dict[str, List[Dict[str, Any]]] = {}

class GPTError(Exception):
    """Custom error for GPT client."""
    pass

def _build_messages(
    prompt: Union[str, List[Dict[str, str]]],
    system_prompt: Optional[str] = None,
    user_name: Optional[str] = None
) -> List[Dict[str, str]]:
    if isinstance(prompt, str):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        user_message = {"role": "user", "content": prompt}
        if user_name:
            user_message["name"] = user_name
        messages.append(user_message)
    else:
        messages = prompt.copy()
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages
        if user_name:
            for m in reversed(messages):
                if m["role"] == "user":
                    m["name"] = user_name
                    break
    return messages

def redact_sensitive(text: str) -> str:
    """
    Redacts API keys and secrets from a string before logging or output.
    """
    import re
    text = re.sub(r"(sk-\w{10,})", "[REDACTED_OPENAI_KEY]", text)
    text = re.sub(r"(?i)api[_-]?key\s*=\s*['\"]?\w+['\"]?", "api_key=[REDACTED]", text)
    return text

def query_gpt(
    prompt: Union[str, List[Dict[str, str]]],
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
    system_prompt: Optional[str] = None,
    functions: Optional[List[Dict]] = None,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    stream: bool = False,
    logger: Optional[logging.Logger] = None,
    retries: int = 3,
    timeout: int = DEFAULT_TIMEOUT,
    response_format: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    log_request: bool = False,
    log_response: bool = False,
    on_token: Optional[Callable[[str], None]] = None,
    seed: Optional[int] = None,
    stop: Optional[Union[str, List[str]]] = None,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    logprobs: Optional[bool] = None,
    logit_bias: Optional[Dict[str, float]] = None,
    attach_raw: bool = False,
    conversation_id: Optional[str] = None,
    save_history: bool = True,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    redact_logs: bool = True,
    # === Extra features ===
    enable_async: bool = False,
    async_callback: Optional[Callable[[str], None]] = None,
    fallback_models: Optional[List[str]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    censor_output: Optional[Callable[[str], str]] = None,
    allow_function_response: bool = False,
    backend: Optional[str] = "openai",  # multi-backend: "openai", "anthropic", "gemini", "ollama"
    ollama_url: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    # You can add more provider configuration here
) -> Union[str, Dict[str, Any]]:
    """
    Hyper-advanced multi-backend GPT/LLM client for OpenAI, Anthropic, Gemini, Ollama, etc.
    - Supports all advanced OpenAI features.
    - Multi-provider: set backend="anthropic", "gemini", "ollama" (OpenAI default).
    - Async/future compatibility, fallback models, error/event hooks, output censor, tags/metadata, history, conversation tracking, plugin-based.
    """
    if logger is None:
        logger = logging.getLogger("VivianGPT")
    if not model:
        model = DEFAULT_MODEL

    messages = _build_messages(prompt, system_prompt, user_name)
    conv_id = conversation_id or str(uuid.uuid4())
    provider_used = backend or "openai"
    request_log = {
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
        "conversation_id": conv_id,
        "params": redact_sensitive(json.dumps(messages, default=str)) if redact_logs else messages,
        "tags": tags or [],
        "metadata": metadata or {},
        "backend": provider_used,
    }

    if log_request:
        logger.info(f"[GPT Request][backend={provider_used}] params: {request_log['params']}")
    if save_history:
        GPT_REQUEST_HISTORY.append(request_log)
        if conv_id not in GPT_CONVERSATIONS:
            GPT_CONVERSATIONS[conv_id] = []
        GPT_CONVERSATIONS[conv_id].extend(messages)

    attempt = 0
    last_exception = None
    model_list = [model] + (fallback_models or [])
    while attempt < retries * len(model_list):
        try:
            current_model = model_list[attempt // retries]
            if provider_used == "openai":
                params = {
                    "model": current_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "timeout": timeout,
                }
                if functions:
                    params["functions"] = functions
                if user_id:
                    params["user"] = user_id
                if stream:
                    params["stream"] = True
                if response_format:
                    params["response_format"] = {"type": response_format}
                if tools:
                    params["tools"] = tools
                if tool_choice:
                    params["tool_choice"] = tool_choice
                if seed is not None:
                    params["seed"] = seed
                if stop is not None:
                    params["stop"] = stop
                if presence_penalty is not None:
                    params["presence_penalty"] = presence_penalty
                if frequency_penalty is not None:
                    params["frequency_penalty"] = frequency_penalty
                if logprobs is not None:
                    params["logprobs"] = logprobs
                if logit_bias is not None:
                    params["logit_bias"] = logit_bias

                t0 = time.time()
                if stream:
                    completion = openai.ChatCompletion.create(**params)
                    chunks = []
                    for chunk in completion:
                        # Function/tool response
                        if allow_function_response and hasattr(chunk.choices[0], "message") and chunk.choices[0].message.get("function_call"):
                            func_call = chunk.choices[0].message["function_call"]
                            logger.info(f"Function call: {func_call}")
                            if on_token: on_token(str(func_call))
                            else: print(str(func_call), end="", flush=True)
                            chunks.append(str(func_call))
                        else:
                            delta = chunk.choices[0].delta.get("content", "")
                            if delta:
                                if on_token: on_token(delta)
                                else: print(delta, end="", flush=True)
                                chunks.append(delta)
                    if not on_token: print()
                    duration = time.time() - t0
                    logger.info(f"GPT stream completed in {duration:.2f} seconds.")
                    resp = "".join(chunks)
                    if censor_output: resp = censor_output(resp)
                    response_log = {
                        "id": request_log["id"],
                        "timestamp": time.time(),
                        "conversation_id": conv_id,
                        "response": redact_sensitive(resp) if redact_logs else resp,
                        "duration": duration,
                        "model": current_model,
                        "backend": provider_used,
                    }
                    if log_response:
                        logger.info(f"GPT stream response: {response_log['response'][:2000]} ...")
                    if save_history:
                        GPT_REQUEST_HISTORY[-1]["response"] = response_log["response"]
                    return {"content": resp, "raw": None} if attach_raw else resp
                else:
                    response = openai.ChatCompletion.create(**params)
                    duration = time.time() - t0
                    resp = ""
                    if allow_function_response and hasattr(response.choices[0], "message") and response.choices[0].message.get("function_call"):
                        func_call = response.choices[0].message["function_call"]
                        logger.info(f"Function call: {func_call}")
                        resp = str(func_call)
                    else:
                        resp = response.choices[0].message["content"].strip()
                    if censor_output: resp = censor_output(resp)
                    response_log = {
                        "id": request_log["id"],
                        "timestamp": time.time(),
                        "conversation_id": conv_id,
                        "response": redact_sensitive(resp) if redact_logs else resp,
                        "duration": duration,
                        "model": current_model,
                        "backend": provider_used,
                    }
                    if log_response:
                        logger.info(f"GPT response: {response_log['response'][:2000]} ...")
                    logger.info(f"GPT completed in {duration:.2f} seconds.")
                    if save_history:
                        GPT_REQUEST_HISTORY[-1]["response"] = response_log["response"]
                    if attach_raw:
                        return {"content": resp, "raw": response.to_dict_recursive()}
                    return resp
            elif provider_used == "ollama":
                # --- Ollama backend (local LLMs) ---
                import requests
                assert ollama_url, "Ollama URL not set"
                t0 = time.time()
                payload = {
                    "model": current_model,
                    "prompt": messages[-1]["content"] if messages else "",
                    "stream": stream,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens
                    }
                }
                r = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=timeout)
                r.raise_for_status()
                duration = time.time() - t0
                resp = r.json().get("response", "")
                if censor_output: resp = censor_output(resp)
                logger.info(f"Ollama completed in {duration:.2f} seconds.")
                if attach_raw:
                    return {"content": resp, "raw": r.json()}
                return resp
            elif provider_used == "anthropic":
                # --- Anthropic backend (Claude etc) ---
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_api_key or os.getenv("ANTHROPIC_API_KEY"))
                t0 = time.time()
                resp_obj = client.messages.create(
                    model=current_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                    system=system_prompt
                )
                resp = resp_obj.content[0].text
                duration = time.time() - t0
                if censor_output: resp = censor_output(resp)
                logger.info(f"Anthropic completed in {duration:.2f} seconds.")
                if attach_raw:
                    return {"content": resp, "raw": resp_obj}
                return resp
            elif provider_used == "gemini":
                # --- Google Gemini backend ---
                import google.generativeai as genai
                genai.configure(api_key=gemini_api_key or os.getenv("GEMINI_API_KEY"))
                model_obj = genai.GenerativeModel(current_model)
                t0 = time.time()
                resp_obj = model_obj.generate_content(messages[-1]["content"] if messages else "")
                resp = resp_obj.text
                duration = time.time() - t0
                if censor_output: resp = censor_output(resp)
                logger.info(f"Gemini completed in {duration:.2f} seconds.")
                if attach_raw:
                    return {"content": resp, "raw": resp_obj}
                return resp
            else:
                raise GPTError(f"Unsupported backend: {provider_used}")

        except Exception as e:
            last_exception = e
            err_log = {
                "id": request_log["id"],
                "timestamp": time.time(),
                "conversation_id": conv_id,
                "error": redact_sensitive(str(e)) if redact_logs else str(e),
                "attempt": attempt + 1,
                "model": model_list[attempt // retries] if attempt // retries < len(model_list) else model,
                "backend": provider_used,
            }
            GPT_ERROR_HISTORY.append(err_log)
            logger.error(f"[GPT Error][attempt {attempt+1}/{retries}] ({provider_used}:{err_log['model']}) {err_log['error']}")
            if on_error:
                on_error(e)
            attempt += 1
            if attempt < retries * len(model_list):
                time.sleep(2 ** (attempt % retries))
            else:
                if attach_raw:
                    return {"content": f"[GPT Error] {err_log['error']}", "raw": None}
                return f"[GPT Error] {err_log['error']}"
    if attach_raw:
        return {"content": f"[GPT Error] {last_exception}", "raw": None}
    return f"[GPT Error] {last_exception}"

# === ASYNC SUPPORT (OpenAI only) ===
async def query_gpt_async(
    *args, **kwargs
) -> Union[str, Dict[str, Any]]:
    import openai
    from openai import AsyncOpenAI
    # Only OpenAI backend for now; can extend to others as APIs support async
    backend = kwargs.get("backend", "openai")
    if backend != "openai":
        raise NotImplementedError("Async currently only supports OpenAI backend.")
    model = kwargs.get("model", DEFAULT_MODEL)
    messages = _build_messages(kwargs.get("prompt", ""), kwargs.get("system_prompt"), kwargs.get("user_name"))
    params = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.7),
        "max_tokens": kwargs.get("max_tokens", 512),
        "timeout": kwargs.get("timeout", DEFAULT_TIMEOUT),
    }
    if kwargs.get("functions"): params["functions"] = kwargs["functions"]
    if kwargs.get("user_id"): params["user"] = kwargs["user_id"]
    if kwargs.get("stream"): params["stream"] = True
    if kwargs.get("response_format"): params["response_format"] = {"type": kwargs["response_format"]}
    if kwargs.get("tools"): params["tools"] = kwargs["tools"]
    if kwargs.get("tool_choice"): params["tool_choice"] = kwargs["tool_choice"]
    if kwargs.get("seed") is not None: params["seed"] = kwargs["seed"]
    if kwargs.get("stop") is not None: params["stop"] = kwargs["stop"]
    if kwargs.get("presence_penalty") is not None: params["presence_penalty"] = kwargs["presence_penalty"]
    if kwargs.get("frequency_penalty") is not None: params["frequency_penalty"] = kwargs["frequency_penalty"]
    if kwargs.get("logprobs") is not None: params["logprobs"] = kwargs["logprobs"]
    if kwargs.get("logit_bias") is not None: params["logit_bias"] = kwargs["logit_bias"]
    async_client = AsyncOpenAI(api_key=openai.api_key, organization=openai.organization if openai.organization else None)
    response = await async_client.chat.completions.create(**params)
    return response.choices[0].message.content.strip()

def query_gpt_json(
    prompt: Union[str, List[Dict[str, str]]],
    **kwargs
) -> Any:
    """
    Queries GPT and attempts to parse the response as JSON.
    Returns parsed object or error string.
    """
    resp = query_gpt(prompt, response_format="json_object", **kwargs)
    try:
        if isinstance(resp, dict) and "content" in resp:
            resp = resp["content"]
        return json.loads(resp)
    except Exception:
        return resp

def query_gpt_tool(
    prompt: Union[str, List[Dict[str, str]]],
    tools: List[Dict[str, Any]],
    tool_choice: Optional[str] = None,
    **kwargs
) -> str:
    """
    Calls GPT with tool calling ability (OpenAI v1 tool-calling API).
    """
    return query_gpt(prompt, tools=tools, tool_choice=tool_choice, **kwargs)

def get_usage_stats() -> Dict[str, Any]:
    """
    Returns usage stats from the OpenAI account, if credentials allow.
    """
    try:
        return openai.api_resources.usage.Usage.retrieve()
    except Exception as e:
        return {"error": str(e)}

def get_supported_models(backend: str = "openai", **kwargs) -> List[str]:
    """
    Returns a list of available GPT model IDs for the given backend.
    """
    try:
        if backend == "openai":
            return [m["id"] for m in openai.Model.list()["data"]]
        elif backend == "ollama":
            import requests
            url = kwargs.get("ollama_url")
            if not url:
                url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
            r = requests.get(f"{url}/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models",[])]
        # Add more backends as needed
        else:
            return [f"[Backend {backend} not supported]"]
    except Exception as e:
        return [f"[Model Error] {e}"]

def gpt_healthcheck(logger: Optional[logging.Logger] = None, backend: str = "openai", **kwargs) -> bool:
    """
    Performs a healthcheck by sending a trivial prompt to the model.
    Returns True if healthy, else False.
    """
    try:
        if backend == "openai":
            resp = query_gpt("Say OK.", temperature=0.0, max_tokens=4, logger=logger)
            return "ok" in resp.lower()
        elif backend == "ollama":
            import requests
            url = kwargs.get("ollama_url")
            if not url:
                url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
            r = requests.get(f"{url}/api/tags")
            return r.status_code == 200
        # Add more healthchecks for other backends as needed
        return False
    except Exception:
        return False

def save_conversation(
    messages: List[Dict[str, str]],
    path: str = "vivian_conversation.json"
):
    """
    Saves a conversation (list of messages) to a JSON file.
    """
    with open(path, "w") as f:
        json.dump(messages, f, indent=2)

def load_conversation(
    path: str = "vivian_conversation.json"
) -> List[Dict[str, str]]:
    """
    Loads a conversation (list of messages) from a JSON file.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)

def summarize_gpt_history(n: int = 10) -> List[Dict[str, Any]]:
    """
    Returns the last N GPT queries and responses for analytics or debugging.
    """
    return GPT_REQUEST_HISTORY[-n:]

def export_gpt_history(path: str = "vivian_gpt_history.json"):
    """
    Exports the full GPT request/response history to disk.
    """
    with open(path, "w") as f:
        json.dump(GPT_REQUEST_HISTORY, f, indent=2)
    print(f"[VivianGPT] Exported GPT request/response history to {path}")

def import_gpt_history(path: str = "vivian_gpt_history.json"):
    """
    Imports GPT history from disk (for analytic replay or migration).
    """
    global GPT_REQUEST_HISTORY
    if os.path.exists(path):
        with open(path, "r") as f:
            GPT_REQUEST_HISTORY = json.load(f)

def get_conversation(conv_id: str) -> List[Dict[str, Any]]:
    """
    Returns all messages in a conversation by id, if tracked.
    """
    return GPT_CONVERSATIONS.get(conv_id, [])

def clear_gpt_history():
    """
    Clears all GPT analytics/history in memory.
    """
    global GPT_REQUEST_HISTORY, GPT_ERROR_HISTORY, GPT_CONVERSATIONS
    GPT_REQUEST_HISTORY = []
    GPT_ERROR_HISTORY = []
    GPT_CONVERSATIONS = {}

# === Example usage ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Basic completion
    resp = query_gpt(
        "Explain the difference between AGI and ANI.",
        system_prompt="You are a helpful AI assistant.",
        temperature=0.5,
        log_request=True,
        log_response=True,
        tags=["demo", "comparison"]
    )
    print("Response:", resp)
    # JSON mode
    resp_json = query_gpt_json(
        [{"role": "user", "content": "Return a JSON object describing a cat."}]
    )
    print("JSON response:", resp_json)
    # Streaming
    print("Streaming demo:")
    query_gpt("List four colors.", stream=True, on_token=lambda t: print(t, end="", flush=True))
    print()
    # Supported models
    print("Supported models:", get_supported_models())
    # Healthcheck
    print("Healthcheck:", gpt_healthcheck())
    # Save and load conversation
    conv = [{"role": "system", "content": "You are Vivian."}, {"role": "user", "content": "Say hello!"}]
    save_conversation(conv, "test_conv.json")
    print("Loaded conversation:", load_conversation("test_conv.json"))
    # Export and import history
    export_gpt_history("gpt_hist.json")
    clear_gpt_history()
    import_gpt_history("gpt_hist.json")
    print("Summarized history:", summarize_gpt_history())