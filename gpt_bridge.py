import openai
import time
import logging
from config import get_config

# Optional: Import tiktoken for token counting if installed
try:
    import tiktoken
except ImportError:
    tiktoken = None

# Provider stubs for future integration
class AnthropicProvider:
    def chat(self, messages, **kwargs):
        raise NotImplementedError("Anthropic Claude provider integration not implemented yet.")

class GeminiProvider:
    def chat(self, messages, **kwargs):
        raise NotImplementedError("Google Gemini provider integration not implemented yet.")

# Vector store memory (stub, pluggable)
class VectorMemory:
    def __init__(self):
        self.memory = []

    def store(self, prompt, response):
        self.memory.append((prompt, response))

    def retrieve(self, prompt):
        # Very basic: return last 3, real would use vectors
        return self.memory[-3:] if self.memory else []

# Advanced prompt injection detection (expand patterns as needed)
def detect_prompt_injection(prompt):
    patterns = [
        "ignore previous", "disregard above", "forget instructions",
        "override system", "pretend", "you are not", "repeat after me",
        "as an ai", "as a language model", "simulate"
    ]
    for pat in patterns:
        if pat in prompt.lower():
            return True
    return False

def estimate_cost(model, usage):
    model_prices = {
        "gpt-3.5-turbo": (0.0005, 0.0015),
        "gpt-4": (0.03, 0.06),
        "gpt-4-turbo": (0.01, 0.03),
    }
    input_cost, output_cost = model_prices.get(model, (0.001, 0.002))
    prompt_toks = usage.get("prompt_tokens", 0)
    completion_toks = usage.get("completion_tokens", 0)
    return {
        "input_tokens": prompt_toks,
        "output_tokens": completion_toks,
        "input_cost": round(input_cost * prompt_toks / 1000, 6),
        "output_cost": round(output_cost * completion_toks / 1000, 6),
        "total_cost": round(input_cost * prompt_toks / 1000 + output_cost * completion_toks / 1000, 6),
    }

def default_safety_callback(text):
    banned = ["hate", "kill", "bomb"]
    for word in banned:
        if word in text.lower():
            return False
    return True

def default_pre_hook(prompt, history):
    import datetime
    now = datetime.datetime.utcnow().isoformat()
    intro = f"[{now}] User prompt: {prompt}"
    if not history:
        return intro, None
    return intro, history

def default_post_hook(response):
    if hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content
        response.choices[0].message.content = content.strip() + "\n\n[Response processed by post_hook]"
    return response

def add_chain_of_thought(prompt):
    return "Let's think step by step.\n" + prompt

def format_output(answer, output_format):
    if output_format == "json":
        import json
        return json.dumps({"answer": answer}, ensure_ascii=False, indent=2)
    if output_format == "markdown":
        return f"```\n{answer}\n```"
    if output_format == "table":
        return f"| Answer |\n|---|\n| {answer} |"
    return answer

def decompose_prompt(prompt):
    # Example: use LLM for decomposition in production
    if " and " in prompt:
        return [p.strip() for p in prompt.split(" and ")]
    return [prompt]

def aggregate_subtask_results(results):
    return "\n".join(str(r) for r in results)

def self_evaluate_answer(answer):
    # Ideally, use an LLM or scoring function
    return f"Confidence: 8/10. This answer is likely accurate."

def debate_agents(agent_outputs):
    debate = "Agent Debate:\n"
    for agent in agent_outputs:
        debate += f"{agent['agent']}: {agent['answer']}\n"
    debate += "End of Debate."
    return debate

def augment_prompt_with_memory(prompt, related_context):
    if not related_context:
        return prompt
    context_snippets = "\n".join(f"Past: {p} => {r}" for p, r in related_context)
    return f"{context_snippets}\n\nCurrent: {prompt}"

def search_and_retrieve(prompt):
    # Placeholder: Use Bing, Google, or other APIs in production
    return ["Fact 1 about topic.", "Fact 2 about topic."]

def inject_facts(prompt, facts):
    return f"{' '.join(facts)}\n\n{prompt}"

def detect_user_intent(prompt):
    ambiguous = "?" not in prompt and len(prompt.split()) < 5
    return "general", ambiguous

def generate_clarifying_question(prompt, intent):
    return f"Can you clarify what you mean by: '{prompt}'? (Intent: {intent})"

def filter_pii(text):
    import re
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", text or "")
    text = re.sub(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b", "[REDACTED_PHONE]", text)
    return text

def ask_gpt_ultimate(
    prompt,
    history=None,
    model=None,
    temperature=0.7,
    max_tokens=1024,
    top_p=1.0,
    n=1,
    stop=None,
    presence_penalty=0.0,
    frequency_penalty=0.0,
    logprobs=None,
    user=None,
    system_prompt=None,
    retries=3,
    timeout=60,
    stream=False,
    functions=None,
    function_call=None,
    return_full=False,
    log_calls=False,
    redact_sensitive=False,
    async_mode=False,
    context_trim=True,
    token_trim_margin=128,
    show_usage=False,
    on_chunk=None,
    multi_provider=None,
    censorship_filter=False,
    analytics_callback=None,
    pre_hook=default_pre_hook,
    post_hook=default_post_hook,
    persistent_session=None,
    safety_callback=None,
    cost_estimate=True,
    session_id=None,
    tool_messages=None,
    role_map=None,
    rich_roles=False,
    conversation_summary=False,
    prompt_injection_detection=True,
    metadata=None,
    multi_agent=False,
    agents=None,
    audit_trail=False,
    audit_callback=None,
    pii_filtering=False,
    auto_personalize=False,
    auto_feedback=False,
    auto_self_improve=False,
    persona_profile=None,
    output_format="markdown",
    chain_of_thought=False,
    memory_db=None,
    search_fallback=False,
    detect_intent=False,
    clarify_if_ambiguous=False,
    auto_decompose=False,
    self_evaluate=False,
    log_trace=False,
    # Multimodal and tool-calling stubs:
    multimodal_input=None,
    voice_input=None,
    file_input=None,
    vision_model=None,
    tool_use=None,
    schedule_time=None,
    **kwargs
):
    trace = []
    cfg = get_config()
    provider = (multi_provider or "openai").lower()

    def track_analytics(event, data):
        if analytics_callback:
            try:
                analytics_callback(event, data)
            except Exception:
                pass

    def redact(text):
        if not redact_sensitive or not text:
            return text
        return text.replace(cfg.get("openai_api_key", ""), "[REDACTED_API_KEY]")

    def log_event(event_type, detail):
        if log_calls:
            logging.info(f"[ask_gpt_ultimate:{event_type}] {redact(str(detail))}")

    def audit(event, detail):
        if audit_trail and audit_callback:
            try:
                audit_callback(event, detail)
            except Exception:
                pass

    # Intent detection & clarification
    if detect_intent:
        intent, ambiguous = detect_user_intent(prompt)
        if ambiguous and clarify_if_ambiguous:
            clarifying_q = generate_clarifying_question(prompt, intent)
            trace.append({"clarify": clarifying_q})
            if log_trace: log_event("clarify", clarifying_q)
            return {"clarify": clarifying_q, "trace": trace}

    # Auto decomposition for complex tasks
    if auto_decompose and " and " in prompt:
        subtasks = decompose_prompt(prompt)
        results = []
        for sub in subtasks:
            result = ask_gpt_ultimate(sub, **kwargs)
            results.append(result["answer"] if isinstance(result, dict) and "answer" in result else result)
        combined = aggregate_subtask_results(results)
        trace.append({"subtasks": subtasks, "results": results})
        if log_trace: log_event("decomposition", {"subtasks": subtasks, "results": results})
        return {"answer": combined, "trace": trace}

    # Multi-agent collaboration/debate
    if multi_agent and agents:
        agent_outputs = []
        for agent in agents:
            agent_answer = ask_gpt_ultimate(prompt, model=agent.get("model", model), persona_profile=agent.get("persona"), **agent.get("kwargs", {}))
            agent_outputs.append({"agent": agent.get("name", "agent"), "answer": agent_answer["answer"] if isinstance(agent_answer, dict) else agent_answer})
        debate = debate_agents(agent_outputs)
        trace.append({"agents": agent_outputs, "debate": debate})
        if log_trace: log_event("multi_agent", {"agents": agent_outputs, "debate": debate})
        return {"answer": debate, "trace": trace}

    # External search/fact retrieval
    if search_fallback:
        facts = search_and_retrieve(prompt)
        prompt = inject_facts(prompt, facts)
        trace.append({"facts": facts, "new_prompt": prompt})
        if log_trace: log_event("search_fallback", {"facts": facts, "new_prompt": prompt})

    # Memory vector store retrieval
    if memory_db is not None:
        related_context = memory_db.retrieve(prompt)
        prompt = augment_prompt_with_memory(prompt, related_context)
        trace.append({"memory": related_context})
        if log_trace: log_event("memory", {"related_context": related_context})

    # Chain-of-thought reasoning
    if chain_of_thought:
        prompt = add_chain_of_thought(prompt)
        trace.append({"chain_of_thought": prompt})

    # Prompt injection detection
    if prompt_injection_detection and detect_prompt_injection(prompt):
        log_event("prompt_injection_detected", prompt)
        audit("prompt_injection", prompt)
        raise ValueError("Prompt injection detected! Aborting call.")

    # Multimodal support (stub)
    if multimodal_input or voice_input or file_input:
        prompt = f"[Multimodal: {multimodal_input or ''} {voice_input or ''} {file_input or ''}]\n{prompt}"

    # Tool use scheduling (stub)
    if schedule_time:
        trace.append({"scheduled": schedule_time})
        if log_trace: log_event("scheduled", schedule_time)
        # In real code, this would queue/schedule the LLM call for later

    # Pre-processing hook
    if pre_hook:
        prompt, history = pre_hook(prompt, history)

    # Persistent session/context
    if persistent_session and hasattr(persistent_session, "get_history"):
        history = persistent_session.get_history(session_id=session_id) or history

    # Build messages
    messages = []
    if history is not None:
        messages = list(history)
    else:
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

    if system_prompt and (not messages or messages[0].get("role") != "system"):
        messages = [{"role": "system", "content": system_prompt}] + messages

    if persona_profile:
        messages = [{"role": "system", "content": f"Persona: {persona_profile}"}] + messages

    if tool_messages:
        messages += tool_messages

    if role_map:
        for m in messages:
            if m.get("role") in role_map:
                m["role"] = role_map[m["role"]]

    if metadata:
        for m in messages:
            m.update(metadata)

    _model = model or cfg.get("model", "gpt-3.5-turbo")

    # Context/history trimming
    if context_trim and tiktoken:
        try:
            enc = tiktoken.encoding_for_model(_model)
            total_tokens = sum(len(enc.encode(m.get("content", ""))) for m in messages)
            model_context = 4096 if "3.5" in _model else 8192
            if total_tokens + max_tokens > model_context - token_trim_margin:
                while messages and total_tokens + max_tokens > model_context - token_trim_margin:
                    if len(messages) > 1 and messages[1]['role'] != "system":
                        removed = messages.pop(1)
                        total_tokens -= len(enc.encode(removed.get("content", "")))
                    else:
                        break
                log_event("context_trimmed", messages)
        except Exception:
            pass

    # Censorship/safety filter
    def safe_content(text):
        if censorship_filter and text:
            if not safety_callback:
                safe = default_safety_callback(text)
            else:
                safe = safety_callback(text)
            if not safe:
                return "[REDACTED UNSAFE CONTENT]"
        return text

    # Conversation summarization for long chats (optional)
    if conversation_summary and len(messages) > 6 and tiktoken:
        try:
            summary_prompt = "Summarize the following conversation in 100 words or less:"
            convo_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
            summary_resp = openai.ChatCompletion.create(
                model=_model,
                messages=[
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": convo_text}
                ],
                max_tokens=128,
                temperature=0.2,
            )
            summary = summary_resp.choices[0].message.content
            messages = [{"role": "system", "content": f"Conversation summary: {summary}"}] + messages[-4:]
            log_event("convo_summary", summary)
        except Exception:
            pass

    # PII filtering on prompt/messages
    if pii_filtering:
        prompt = filter_pii(prompt)
        for m in messages:
            m["content"] = filter_pii(m.get("content", ""))

    # Auto-personalize (stub)
    if auto_personalize and user:
        messages = [{"role": "system", "content": f"User: {user}"}] + messages

    # Auto-feedback/self-improve (stub)
    if auto_feedback or auto_self_improve:
        pass  # Extend as needed

    # Main LLM call (with multi-provider support)
    def call_provider(api_args):
        if provider == "openai":
            return openai.ChatCompletion.create(**api_args)
        elif provider == "anthropic":
            return AnthropicProvider().chat(messages, **api_args)
        elif provider == "gemini":
            return GeminiProvider().chat(messages, **api_args)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    api_args = {
        "model": _model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "n": n,
        "presence_penalty": presence_penalty,
        "frequency_penalty": frequency_penalty,
        "timeout": timeout,
    }
    if stop is not None: api_args["stop"] = stop
    if logprobs is not None: api_args["logprobs"] = logprobs
    if user is not None: api_args["user"] = user
    if functions is not None: api_args["functions"] = functions
    if function_call is not None: api_args["function_call"] = function_call
    api_args.update(kwargs)

    # Streaming and async support
    if async_mode:
        import asyncio
        async def _async_call():
            for attempt in range(retries + 1):
                try:
                    res = await openai.ChatCompletion.acreate(**api_args)
                    log_event("response", res)
                    track_analytics("call_end", res)
                    audit("response", res)
                    if post_hook:
                        res = post_hook(res)
                    if return_full:
                        return res
                    out = res.choices[0].message.content.strip()
                    out = safe_content(out)
                    result = out
                    if show_usage and hasattr(res, "usage"):
                        usage = dict(res.usage)
                        if cost_estimate:
                            cost = estimate_cost(_model, usage)
                            result = (out, usage, cost)
                        else:
                            result = (out, usage)
                    if persistent_session and hasattr(persistent_session, "save_history"):
                        persistent_session.save_history(session_id=session_id, history=messages + [{"role": "assistant", "content": out}])
                    return result
                except openai.error.RateLimitError as e:
                    log_event("rate_limit", e)
                    track_analytics("error", {"type": "rate_limit", "error": str(e)})
                    audit("rate_limit", str(e))
                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return f"[Rate limit error contacting GPT]: {e}"
                except openai.error.Timeout as e:
                    log_event("timeout", e)
                    track_analytics("error", {"type": "timeout", "error": str(e)})
                    audit("timeout", str(e))
                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return f"[Timeout contacting GPT]: {e}"
                except Exception as e:
                    log_event("exception", e)
                    track_analytics("error", {"type": "exception", "error": str(e)})
                    audit("exception", str(e))
                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    return f"[Error contacting GPT]: {e}"
        return _async_call()

    if stream:
        def _streamer():
            for attempt in range(retries + 1):
                try:
                    resp = call_provider(dict(api_args, stream=True))
                    full = ""
                    for chunk in resp:
                        if "choices" in chunk and chunk.choices:
                            delta = chunk.choices[0].delta
                            if "content" in delta:
                                text_piece = delta.content
                                full += text_piece
                                if on_chunk:
                                    on_chunk(text_piece)
                                yield text_piece
                    if on_chunk:
                        on_chunk(None)
                    if show_usage and hasattr(resp, "usage"):
                        yield dict(resp.usage)
                    if cost_estimate and hasattr(resp, "usage"):
                        yield estimate_cost(_model, dict(resp.usage))
                    break
                except openai.error.RateLimitError as e:
                    log_event("rate_limit", e)
                    track_analytics("error", {"type": "rate_limit", "error": str(e)})
                    audit("rate_limit", str(e))
                    if attempt < retries:
                        time.sleep(2 ** attempt)
                        continue
                    yield f"[Rate limit error contacting GPT]: {e}"
                    break
                except openai.error.Timeout as e:
                    log_event("timeout", e)
                    track_analytics("error", {"type": "timeout", "error": str(e)})
                    audit("timeout", str(e))
                    if attempt < retries:
                        time.sleep(2 ** attempt)
                        continue
                    yield f"[Timeout contacting GPT]: {e}"
                    break
                except Exception as e:
                    log_event("exception", e)
                    track_analytics("error", {"type": "exception", "error": str(e)})
                    audit("exception", str(e))
                    if attempt < retries:
                        time.sleep(2 ** attempt)
                        continue
                    yield f"[Error contacting GPT]: {e}"
                    break
        return _streamer()

    # Synchronous, non-streaming
    for attempt in range(retries + 1):
        try:
            log_event("prompt", api_args)
            track_analytics("call_start", {"provider": provider, "api_args": api_args})
            audit("prompt", api_args)
            res = call_provider(api_args)
            log_event("response", res)
            track_analytics("call_end", res)
            audit("response", res)
            if post_hook:
                res = post_hook(res)
            if return_full:
                return res
            out = res.choices[0].message.content.strip()
            out = safe_content(out)
            result = out
            if show_usage and hasattr(res, "usage"):
                usage = dict(res.usage)
                if cost_estimate:
                    cost = estimate_cost(_model, usage)
                    result = (out, usage, cost)
                else:
                    result = (out, usage)
            if persistent_session and hasattr(persistent_session, "save_history"):
                persistent_session.save_history(session_id=session_id, history=messages + [{"role": "assistant", "content": out}])
            # Self-evaluation (if enabled)
            if self_evaluate:
                score = self_evaluate_answer(out)
                trace.append({"self_eval": score})
                if log_trace: log_event("self_eval", score)
                result = f"{out}\n\n{score}"
            # Output formatting
            answer = format_output(result, output_format)
            trace.append({"formatted": answer})
            if log_trace: log_event("output_formatted", answer)
            return {"answer": answer, "trace": trace} if log_trace else answer
        except openai.error.RateLimitError as e:
            log_event("rate_limit", e)
            track_analytics("error", {"type": "rate_limit", "error": str(e)})
            audit("rate_limit", str(e))
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return f"[Rate limit error contacting GPT]: {e}"
        except openai.error.Timeout as e:
            log_event("timeout", e)
            track_analytics("error", {"type": "timeout", "error": str(e)})
            audit("timeout", str(e))
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return f"[Timeout contacting GPT]: {e}"
        except Exception as e:
            log_event("exception", e)
            track_analytics("error", {"type": "exception", "error": str(e)})
            audit("exception", str(e))
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            return f"[Error contacting GPT]: {e}"

# Example usage:
if __name__ == "__main__":
    memory = VectorMemory()
    response = ask_gpt_ultimate(
        "Summarize the history of AI and its future challenges.",
        system_prompt="You are a masterful AI assistant.",
        temperature=0.5,
        stream=False,
        show_usage=True,
        cost_estimate=True,
        log_calls=True,
        censorship_filter=True,
        conversation_summary=True,
        prompt_injection_detection=True,
        metadata={'user_id': 'gregmish'},
        multi_provider="openai",
        multi_agent=True,
        agents=[
            {"name": "Debater", "persona": "debate both sides", "model": "gpt-3.5-turbo"},
            {"name": "FactChecker", "persona": "fact-check and cite sources", "model": "gpt-4-turbo"},
        ],
        audit_trail=True,
        audit_callback=lambda event, detail: print(f"AUDIT: {event} -> {detail}"),
        pii_filtering=True,
        auto_personalize=True,
        auto_feedback=True,
        auto_self_improve=True,
        persona_profile="You are Vivian, an AI assistant who is always helpful.",
        output_format="markdown",
        chain_of_thought=True,
        memory_db=memory,
        search_fallback=True,
        detect_intent=True,
        clarify_if_ambiguous=True,
        auto_decompose=True,
        self_evaluate=True,
        log_trace=True,
        multimodal_input="A picture of a robot",
        voice_input="audio.wav",
        file_input="file.pdf",
        schedule_time=None,
    )
    print(response)