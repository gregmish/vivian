import json
import os
import datetime
from typing import Dict, Any, List, Optional, Callable

_PERSONA_PATH = "personas.json"
_PERSONA_HISTORY_PATH = "persona_history.json"
_PERSONA_MARKETPLACE_URL = "https://example.com/persona_marketplace.json"  # stub URL

personas: Dict[str, Dict[str, Any]] = {
    "default": {
        "name": "Vivian",
        "tone": "friendly",
        "intro": "Hey, I'm Vivian! How can I help you today?",
        "pronouns": "she/her",
        "avatar": "🤖",
        "voice": "Zira",
        "language": "en",
        "summary_style": "brief",
        "system_prompt": "You are Vivian, a helpful, friendly AI assistant.",
        "permissions": [],
        "keywords": ["default", "assistant", "friendly"],
        "hooks": {},
        "skills": [],
        "base": None,
        "context_adapters": {},
        "trust_level": "user",
        "theme": "light",
    },
    "dark": {
        "name": "Vivian",
        "tone": "serious",
        "intro": "Online. What’s the situation?",
        "pronouns": "she/her",
        "avatar": "🦇",
        "voice": "Brian",
        "language": "en",
        "summary_style": "detailed",
        "system_prompt": "You are Vivian, a no-nonsense, serious AI agent.",
        "permissions": [],
        "keywords": ["dark", "serious", "no-nonsense"],
        "hooks": {},
        "skills": ["threat_assessment"],
        "base": None,
        "context_adapters": {},
        "trust_level": "trusted",
        "theme": "dark",
    },
    "fun": {
        "name": "Viv",
        "tone": "cheeky",
        "intro": "Yo! Viv here, ready to cause some chaos 😈",
        "pronouns": "she/they",
        "avatar": "😈",
        "voice": "Emma",
        "language": "en",
        "summary_style": "fun",
        "system_prompt": "You are Viv, a cheeky, playful AI sidekick.",
        "permissions": [],
        "keywords": ["fun", "playful", "cheeky"],
        "hooks": {},
        "skills": ["jokes", "memes"],
        "base": None,
        "context_adapters": {},
        "trust_level": "user",
        "theme": "party",
    }
}

current_persona: str = "default"
recent_personas: List[str] = []
persona_switch_callbacks: List[Callable[[str], None]] = []
persona_feedback: Dict[str, List[Dict[str, Any]]] = {}
persona_memories: Dict[str, List[Dict[str, Any]]] = {}
persona_performance: Dict[str, Dict[str, Any]] = {}
persona_schedule: Dict[str, Dict[str, Any]] = {}
persona_analytics: Dict[str, Any] = {}

def _now():
    return datetime.datetime.utcnow().isoformat()

def list_personas() -> List[str]:
    return list(personas.keys())

def set_persona(name: str, context: Optional[Dict[str, Any]] = None):
    global current_persona
    if name in personas:
        if current_persona != name:
            recent_personas.append(current_persona)
            if "on_deactivate" in personas[current_persona].get("hooks", {}):
                personas[current_persona]["hooks"]["on_deactivate"](current_persona)
        current_persona = name
        if "on_activate" in personas[name].get("hooks", {}):
            personas[name]["hooks"]["on_activate"](name)
        for cb in persona_switch_callbacks:
            cb(name)
        persona_log_switch(name, context)
        _activate_persona_skills(name)
        _apply_persona_theme(name)
        _apply_persona_schedule(name)

def get_persona() -> Dict[str, Any]:
    persona = personas.get(current_persona, personas["default"])
    # Persona inheritance
    base = persona.get("base")
    if base and base in personas:
        p = dict(personas[base])
        p.update(persona)
        return p
    return persona

def create_persona(name: str, fields: Dict[str, Any], base: Optional[str] = None):
    if name in personas:
        raise ValueError("Persona already exists")
    fields["base"] = base
    fields.setdefault("hooks", {})
    personas[name] = fields
    save_personas()

def edit_persona(name: str, fields: Dict[str, Any]):
    if name not in personas:
        raise ValueError("Persona does not exist")
    personas[name].update(fields)
    save_personas()

def remove_persona(name: str):
    if name in personas and name != "default":
        del personas[name]
        save_personas()

def load_personas(path: str = _PERSONA_PATH):
    global personas
    if os.path.exists(path):
        with open(path, "r") as f:
            loaded = json.load(f)
            for k, v in loaded.items():
                if k in personas and "hooks" in personas[k]:
                    v["hooks"] = personas[k]["hooks"]
            personas.update(loaded)

def save_personas(path: str = _PERSONA_PATH):
    to_save = {}
    for k, v in personas.items():
        v2 = dict(v)
        v2.pop("hooks", None)
        to_save[k] = v2
    with open(path, "w") as f:
        json.dump(to_save, f, indent=2)

def export_persona(name: str, path: str):
    if name in personas:
        v2 = dict(personas[name])
        v2.pop("hooks", None)
        with open(path, "w") as f:
            json.dump({name: v2}, f, indent=2)

def import_persona(path: str):
    with open(path) as f:
        persona = json.load(f)
        for k, v in persona.items():
            if k not in personas:
                v["hooks"] = {}
            personas[k] = v
        save_personas()

def get_recent_personas() -> List[str]:
    return recent_personas[-5:] if recent_personas else []

def persona_greeting() -> str:
    persona = get_persona()
    # Context-aware greeting
    adapters = persona.get("context_adapters", {})
    if "greeting" in adapters:
        return adapters["greeting"]()
    return persona.get("intro", "Hello.")

def persona_prompt() -> str:
    return get_persona().get("system_prompt", "")

def persona_avatar() -> str:
    return get_persona().get("avatar", "")

def persona_voice() -> Optional[str]:
    return get_persona().get("voice", None)

def persona_permissions() -> List[str]:
    return get_persona().get("permissions", [])

def persona_keywords() -> List[str]:
    return get_persona().get("keywords", [])

def persona_theme() -> Optional[str]:
    return get_persona().get("theme", None)

def persona_skills() -> List[str]:
    return get_persona().get("skills", [])

def persona_trust_level() -> str:
    return get_persona().get("trust_level", "user")

def persona_switch_shortcut(input_str: str) -> bool:
    tokens = input_str.lower().split()
    for p in list_personas():
        if p in tokens or any(k in tokens for k in personas[p].get("keywords", [])):
            set_persona(p)
            return True
    return False

def add_persona_switch_callback(cb: Callable[[str], None]):
    persona_switch_callbacks.append(cb)

def persona_marketplace_search(query: str) -> List[str]:
    # Stub: In reality, this would fetch persona packs from a remote repo
    try:
        import requests
        resp = requests.get(_PERSONA_MARKETPLACE_URL)
        if resp.status_code == 200:
            all_personas = resp.json()
            return [p["name"] for p in all_personas if query.lower() in (p.get("name", "") + p.get("intro", "")).lower()]
    except Exception:
        pass
    # Fallback to local
    result = []
    for key, v in personas.items():
        if query.lower() in key.lower() or query.lower() in v.get("intro", "").lower() or \
                any(query.lower() in k for k in v.get("keywords", [])):
            result.append(key)
    return result

def fetch_persona_pack(url: str) -> bool:
    # Download persona pack from a remote URL and import it
    try:
        import requests
        resp = requests.get(url)
        if resp.status_code == 200:
            tmp = "imported_persona_pack.json"
            with open(tmp, "w") as f:
                f.write(resp.text)
            import_persona(tmp)
            os.remove(tmp)
            return True
    except Exception:
        pass
    return False

def persona_context_adapter(action: str) -> Optional[str]:
    # Personas may define custom context behaviors (e.g., apology, greeting, summary)
    persona = get_persona()
    adapters = persona.get("context_adapters", {})
    fn = adapters.get(action)
    return fn() if callable(fn) else adapters.get(action)

def persona_set_hook(name: str, hook_type: str, func: Callable):
    if name in personas:
        personas[name].setdefault("hooks", {})[hook_type] = func

def persona_has_permission(command: str) -> bool:
    trust = persona_trust_level()
    if trust == "admin":
        return True
    return command in persona_permissions() or not persona_permissions()

def persona_set_permissions(name: str, permissions: List[str]):
    if name in personas:
        personas[name]["permissions"] = permissions
        save_personas()

def persona_memory_add(event: Dict[str, Any]):
    """Store persona-specific memory entry."""
    pid = current_persona
    persona_memories.setdefault(pid, []).append({"event": event, "time": _now()})

def persona_memory_get(pid: Optional[str] = None) -> List[Dict[str, Any]]:
    pid = pid or current_persona
    return persona_memories.get(pid, [])

def persona_feedback_add(feedback: str, rating: Optional[int] = None):
    """Add feedback for the current persona."""
    pid = current_persona
    entry = {"feedback": feedback, "rating": rating, "time": _now()}
    persona_feedback.setdefault(pid, []).append(entry)
    _update_persona_performance(pid, rating)

def persona_feedback_get(pid: Optional[str] = None) -> List[Dict[str, Any]]:
    pid = pid or current_persona
    return persona_feedback.get(pid, [])

def _update_persona_performance(pid: str, rating: Optional[int] = None):
    perf = persona_performance.setdefault(pid, {"count": 0, "sum": 0, "avg": 0})
    if rating is not None:
        perf["count"] += 1
        perf["sum"] += rating
        perf["avg"] = perf["sum"] / perf["count"]

def persona_performance_report(pid: Optional[str] = None) -> Dict[str, Any]:
    pid = pid or current_persona
    return persona_performance.get(pid, {"count": 0, "avg": 0})

def persona_log_switch(name: str, context: Optional[Dict[str, Any]] = None):
    entry = {
        "timestamp": _now(),
        "persona": name,
        "user": context.get("user") if context else None,
        "reason": context.get("reason") if context else None,
    }
    try:
        history = []
        if os.path.exists(_PERSONA_HISTORY_PATH):
            with open(_PERSONA_HISTORY_PATH, "r") as f:
                history = json.load(f)
        history.append(entry)
        with open(_PERSONA_HISTORY_PATH, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass

def persona_schedule_set(name: str, schedule: Dict[str, Any]):
    persona_schedule[name] = schedule

def _apply_persona_schedule(name: str):
    # Stub: switch persona on schedule (could use cron, time, context, etc)
    pass

def persona_auto_switch(context: Dict[str, Any]):
    # Example: switch persona if after 6pm, or if user is sad, etc.
    # This is a stub for actual context-driven switching logic
    now = datetime.datetime.utcnow().hour
    if now > 17:
        set_persona("fun", context)
    elif context.get("mood") == "serious":
        set_persona("dark", context)
    elif context.get("mood") == "playful":
        set_persona("fun", context)
    else:
        set_persona("default", context)

def _activate_persona_skills(name: str):
    # Enable/disable skills, plugins, or agents based on persona (stub)
    pass

def _apply_persona_theme(name: str):
    # Set app theme/GUI based on persona (stub)
    pass

def persona_reset():
    global current_persona, recent_personas
    current_persona = "default"
    recent_personas = []

def persona_inheritance_chain(name: Optional[str] = None) -> List[str]:
    # Return chain of inheritance for a persona
    name = name or current_persona
    chain = []
    while name and name in personas:
        chain.append(name)
        name = personas[name].get("base")
    return chain

def persona_explain(name: Optional[str] = None) -> str:
    # Explain persona's traits, permissions, skills, and context
    p = personas.get(name or current_persona, {})
    info = [
        f"Name: {p.get('name')}",
        f"Tone: {p.get('tone')}",
        f"Intro: {p.get('intro')}",
        f"Voice: {p.get('voice')}",
        f"Avatar: {p.get('avatar')}",
        f"Summary Style: {p.get('summary_style')}",
        f"System Prompt: {p.get('system_prompt')}",
        f"Trust Level: {p.get('trust_level')}",
        f"Skills: {', '.join(p.get('skills', []))}",
        f"Theme: {p.get('theme')}",
        f"Permissions: {', '.join(p.get('permissions', []))}",
        f"Keywords: {', '.join(p.get('keywords', []))}",
        f"Base: {p.get('base')}"
    ]
    return "\n".join(info)

def persona_set_context_adapter(name: str, action: str, fn: Callable):
    if name in personas:
        personas[name].setdefault("context_adapters", {})[action] = fn

def persona_lifecycle_hook(name: str, event: str, fn: Callable):
    persona_set_hook(name, event, fn)

def persona_get_contextual_field(field: str, context: Dict[str, Any]) -> Any:
    # Allow fields to be context-sensitive (stub for more advanced logic)
    persona = get_persona()
    val = persona.get(field)
    if callable(val):
        return val(context)
    return val

def persona_stats() -> Dict[str, Any]:
    # Usage and analytics
    return {
        "recent": get_recent_personas(),
        "performance": persona_performance,
        "feedback": {k: len(v) for k, v in persona_feedback.items()},
        "memories": {k: len(v) for k, v in persona_memories.items()},
    }

def persona_collaborate(persona_list: List[str], prompt: str) -> Dict[str, str]:
    # Multi-persona debate/collaboration (stub)
    result = {}
    for p in persona_list:
        set_persona(p)
        # Simulate answer per persona (replace with LLM call as needed)
        result[p] = f"[{p} says]: {prompt} (response style: {get_persona().get('tone')})"
    set_persona("default")
    return result

def persona_feedback_learn():
    # Self-learning stub: adjust persona traits based on feedback
    pass

# Load personas from disk at module import
try:
    load_personas()
except Exception:
    pass