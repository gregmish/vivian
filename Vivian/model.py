import requests
import time
import logging
import json

class ModelError(Exception):
    pass

def count_tokens(text: str, model: str = "mistral") -> int:
    return max(1, len(text) // 4)

def send_to_model(
    context_or_prompt,
    config,
    stream: bool = False,
    persona: str = None,
    system_message: str = None,
    history: list = None,
    retries: int = 2,
    multimodal_input: dict = None,
    postprocess: callable = None,
    on_stream: callable = None,
    debug: bool = False,
):
    model = config.get("model", "mistral:latest")
    api_url = config.get("api_url", "http://localhost:11434/api/chat")
    timeout = config.get("model_timeout", 60)

    sys_msg = system_message or f"You are {config.get('name', 'Vivian')}, persona: {persona or config.get('persona', 'default')}."
    if config.get("language") and config.get("localization_enabled"):
        sys_msg += f" Respond in {config['language']}."

    # Construct chat messages
    messages = [{"role": "system", "content": sys_msg}]
    if history:
        messages += history
    elif isinstance(context_or_prompt, list):
        messages += context_or_prompt
    else:
        messages.append({"role": "user", "content": str(context_or_prompt)})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }

    headers = {"Content-Type": "application/json"}

    attempt = 0
    while attempt <= retries:
        try:
            start_time = time.time()
            response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()
            content = data.get("message", {}).get("content", "[Model] No output.")

            if debug:
                logging.info(f"[Model] Used model: {model}, time: {time.time()-start_time:.2f}s")

            if postprocess:
                content = postprocess(content, config)

            return content

        except Exception as e:
            logging.warning(f"[Model] Error: {e}")
            time.sleep(1)
            attempt += 1

    raise ModelError("[Model] Failed after retries.")