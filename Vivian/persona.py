import difflib
import json
from typing import Dict, Optional, List

# Built-in personas with advanced fields
PERSONAS: Dict[str, Dict[str, str]] = {
    "default": {
        "description": "Default balanced tone.",
        "style": "Direct, helpful, neutral.",
        "prompt_prefix": "",
        "example": ""
    },
    "storyteller": {
        "description": "Narrative and engaging.",
        "style": "Descriptive, imaginative, vivid.",
        "prompt_prefix": "Once upon a time,",
        "example": "Let me tell you a story..."
    },
    "mentor": {
        "description": "Supportive and instructive.",
        "style": "Calm, wise, educational.",
        "prompt_prefix": "Here's some guidance:",
        "example": "Remember, learning is a journey."
    },
    "therapist": {
        "description": "Empathetic and reflective.",
        "style": "Gentle, listening, supportive.",
        "prompt_prefix": "Let's talk about how you feel.",
        "example": "How does that make you feel?"
    },
    "coder": {
        "description": "Technical and focused on programming.",
        "style": "Concise, logic-driven, code-heavy.",
        "prompt_prefix": "Here's a code example:",
        "example": "def hello():\n    print('Hello, world!')"
    }
}

# Custom personas (runtime)
CUSTOM_PERSONAS: Dict[str, Dict[str, str]] = {}

# Persona history for advanced features
PERSONA_HISTORY: List[str] = []

CURRENT_PERSONA: str = "default"

PERSONAS_FILE = "personas.json"

# ========== Core Persona Functions ==========

def list_personas(include_custom: bool = True) -> List[str]:
    """List all persona names."""
    base = list(PERSONAS.keys())
    if include_custom:
        base += list(CUSTOM_PERSONAS.keys())
    return sorted(set(base))

def persona_exists(name: str) -> bool:
    """Check if a persona exists (built-in or custom)."""
    return name in PERSONAS or name in CUSTOM_PERSONAS

def get_persona(name: Optional[str] = None) -> Dict[str, str]:
    """Return full persona info. If name is None, get current."""
    if not name:
        name = CURRENT_PERSONA
    return CUSTOM_PERSONAS.get(name) or PERSONAS.get(name, PERSONAS["default"])

def describe_persona(name: Optional[str] = None) -> str:
    """Describe a persona in detail (for UI, API, or CLI)."""
    pname = name or CURRENT_PERSONA
    persona = get_persona(pname)
    desc = persona.get("description", "")
    style = persona.get("style", "")
    prefix = persona.get("prompt_prefix", "")
    example = persona.get("example", "")
    s = f"{pname.title()}:\n  Description: {desc}\n  Style: {style}"
    if prefix:
        s += f"\n  Prompt prefix: {prefix}"
    if example:
        s += f"\n  Example: {example}"
    return s

def persona_summary_list() -> str:
    """Return a formatted list of all personas with descriptions."""
    out = []
    for name in list_personas():
        p = get_persona(name)
        out.append(f"- {name} :: {p.get('description', '')}")
    return "\n".join(out)

def search_personas(keyword: str) -> List[str]:
    """Search for personas by keyword in name or description."""
    results = []
    for k, v in {**PERSONAS, **CUSTOM_PERSONAS}.items():
        if keyword.lower() in k.lower() or keyword.lower() in v.get("description", "").lower():
            results.append(k)
    return results

# ========== Persona Management ==========

def set_persona(name: str) -> str:
    """Set the current persona, with fuzzy matching, feedback, and history."""
    global CURRENT_PERSONA
    all_personas = list_personas()
    if name in all_personas:
        CURRENT_PERSONA = name
        PERSONA_HISTORY.append(name)
        return f"Persona set to '{name}'."
    matches = difflib.get_close_matches(name, all_personas, n=1)
    if matches:
        return f"Persona '{name}' not found. Did you mean '{matches[0]}'?"
    return f"Persona '{name}' not found. Use list_personas() to see options."

def get_current_persona() -> str:
    """Return the current persona's name."""
    return CURRENT_PERSONA

def persona_history(limit: int = 10) -> List[str]:
    """Return the most recent persona switches."""
    return PERSONA_HISTORY[-limit:]

def add_persona(
    name: str, 
    description: str, 
    style: str, 
    prompt_prefix: str = "", 
    example: str = ""
) -> str:
    """Add a new custom persona (cannot overwrite built-ins)."""
    if name in PERSONAS or name in CUSTOM_PERSONAS:
        return f"Persona '{name}' already exists."
    CUSTOM_PERSONAS[name] = {
        "description": description,
        "style": style,
        "prompt_prefix": prompt_prefix,
        "example": example
    }
    return f"Persona '{name}' added."

def edit_persona(
    name: str, 
    description: Optional[str] = None, 
    style: Optional[str] = None, 
    prompt_prefix: Optional[str] = None, 
    example: Optional[str] = None
) -> str:
    """Edit an existing custom persona."""
    if name in PERSONAS:
        return "Cannot edit built-in personas directly."
    if name not in CUSTOM_PERSONAS:
        return f"Persona '{name}' not found among custom personas."
    p = CUSTOM_PERSONAS[name]
    if description is not None:
        p["description"] = description
    if style is not None:
        p["style"] = style
    if prompt_prefix is not None:
        p["prompt_prefix"] = prompt_prefix
    if example is not None:
        p["example"] = example
    return f"Persona '{name}' updated."

def remove_persona(name: str) -> str:
    """Remove a custom persona."""
    if name in PERSONAS:
        return "Cannot remove built-in personas."
    if name in CUSTOM_PERSONAS:
        del CUSTOM_PERSONAS[name]
        return f"Persona '{name}' removed."
    return f"Persona '{name}' not found among custom personas."

def reset_personas() -> str:
    """Clear all custom personas and reset to built-ins."""
    global CUSTOM_PERSONAS
    CUSTOM_PERSONAS = {}
    return "Custom personas reset."

# ========== Persistence ==========

def save_personas(filepath: str = PERSONAS_FILE) -> str:
    """Save custom personas to a JSON file."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(CUSTOM_PERSONAS, f, indent=2)
        return "Custom personas saved."
    except Exception as e:
        return f"Error saving personas: {e}"

def load_personas(filepath: str = PERSONAS_FILE) -> str:
    """Load custom personas from a JSON file."""
    global CUSTOM_PERSONAS
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            CUSTOM_PERSONAS = json.load(f)
        return "Custom personas loaded."
    except FileNotFoundError:
        CUSTOM_PERSONAS = {}
        return "No custom personas found. Starting fresh."
    except Exception as e:
        return f"Error loading personas: {e}"

# ========== Advanced Field Access ==========

def current_style() -> str:
    """Get the style string for the current persona."""
    return get_persona().get("style", "")

def current_prompt_prefix() -> str:
    """Get prompt prefix for current persona."""
    return get_persona().get("prompt_prefix", "")

def current_example() -> str:
    """Get example for current persona."""
    return get_persona().get("example", "")

def persona_as_dict(name: Optional[str] = None) -> Dict[str, str]:
    """Get a persona as a dict for API/GUI."""
    return get_persona(name)

def all_personas_as_dict() -> Dict[str, Dict[str, str]]:
    """Return all personas as a dict (built-in and custom)."""
    all_ps = {**PERSONAS, **CUSTOM_PERSONAS}
    return all_ps

# ========== CLI/GUI/API Helpers ==========

def persona_command_help():
    print("""
Persona Commands:
/personas                - List all personas
/persona <name>          - Switch to a persona (fuzzy matching supported)
/persona info [<name>]   - Show description of current or specified persona
/persona add <name>      - Add a custom persona interactively
/persona edit <name>     - Edit a custom persona interactively
/persona remove <name>   - Remove a custom persona
/persona search <kw>     - Search personas by keyword
/persona save            - Save custom personas to file
/persona load            - Load custom personas from file
/persona reset           - Reset custom personas to empty
/persona history         - Show recent persona switches
""")

def persona_interactive_add():
    print("Add a new persona:")
    name = input("Name: ").strip()
    desc = input("Description: ").strip()
    style = input("Style: ").strip()
    prefix = input("Prompt prefix (optional): ").strip()
    example = input("Example (optional): ").strip()
    print(add_persona(name, desc, style, prompt_prefix=prefix, example=example))

def persona_interactive_edit():
    name = input("Persona to edit: ").strip()
    if name in PERSONAS:
        print("You cannot edit built-in personas.")
        return
    if name not in CUSTOM_PERSONAS:
        print(f"Custom persona '{name}' not found.")
        return
    print("Leave fields blank to keep current value.")
    p = CUSTOM_PERSONAS[name]
    desc = input(f"Description [{p['description']}]: ").strip() or p["description"]
    style = input(f"Style [{p['style']}]: ").strip() or p["style"]
    prefix = input(f"Prompt prefix [{p.get('prompt_prefix','')}]: ").strip() or p.get("prompt_prefix", "")
    example = input(f"Example [{p.get('example','')}]: ").strip() or p.get("example", "")
    print(edit_persona(name, desc, style, prompt_prefix=prefix, example=example))

def persona_interactive_remove():
    name = input("Persona to remove: ").strip()
    print(remove_persona(name))

def persona_interactive_search():
    kw = input("Search keyword: ").strip()
    matches = search_personas(kw)
    if matches:
        print("Matching personas:", ", ".join(matches))
        for m in matches:
            print(describe_persona(m))
    else:
        print("No matching personas found.")

def persona_interactive():
    persona_command_help()
    while True:
        cmd = input("Persona> ").strip()
        if cmd in ("exit", "back", "quit"):
            break
        elif cmd == "list":
            print(persona_summary_list())
        elif cmd.startswith("info"):
            parts = cmd.split()
            name = parts[1] if len(parts) > 1 else None
            print(describe_persona(name))
        elif cmd.startswith("add"):
            persona_interactive_add()
        elif cmd.startswith("edit"):
            persona_interactive_edit()
        elif cmd.startswith("remove"):
            persona_interactive_remove()
        elif cmd.startswith("search"):
            persona_interactive_search()
        elif cmd == "save":
            print(save_personas())
        elif cmd == "load":
            print(load_personas())
        elif cmd == "reset":
            print(reset_personas())
        elif cmd == "history":
            print("Persona switch history:", ", ".join(persona_history()))
        else:
            persona_command_help()