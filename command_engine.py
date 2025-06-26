import os
import json
import time
import logging
import importlib.util
from typing import Callable, Dict, List, Any, Optional, Union

import argparse
import threading
import glob

# Command registry and metadata
COMMANDS: Dict[str, Callable[[List[str], Dict[str, Any]], str]] = {}
COMMAND_ALIASES: Dict[str, str] = {}
COMMAND_HISTORY: List[Dict[str, Any]] = []
COMMAND_CATEGORIES: Dict[str, str] = {}
COMMAND_SUGGESTIONS: Dict[str, str] = {}
COMMAND_PERMISSIONS: Dict[str, List[str]] = {}
COMMAND_ARGPARSE: Dict[str, Callable[[List[str]], argparse.Namespace]] = {}
COMMAND_I18N: Dict[str, Dict[str, str]] = {}

LOG_FILE = "logs/command_log.jsonl"
PLUGIN_DIR = "commands"
os.makedirs("logs", exist_ok=True)
os.makedirs(PLUGIN_DIR, exist_ok=True)

def register_command(
    name: str,
    func: Callable[[List[str], Dict[str, Any]], str],
    category: str = "General",
    suggestion: str = "",
    aliases: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    argparse_func: Optional[Callable[[List[str]], argparse.Namespace]] = None,
    i18n: Optional[Dict[str, str]] = None
):
    """Registers a command with optional category, suggestion, aliases, permissions, argparse, and i18n help."""
    COMMANDS[name] = func
    COMMAND_CATEGORIES[name] = category
    COMMAND_SUGGESTIONS[name] = suggestion
    if permissions:
        COMMAND_PERMISSIONS[name] = permissions
    if aliases:
        for alias in aliases:
            COMMAND_ALIASES[alias] = name
    if argparse_func:
        COMMAND_ARGPARSE[name] = argparse_func
    if i18n:
        COMMAND_I18N[name] = i18n

def run_command(command_input: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Parses and runs a registered command string with user context."""
    command_input = command_input.strip()
    if not command_input:
        return "[Command] No input."

    # Chaining support (async supported for long-running)
    if ";" in command_input:
        return run_command_chain(command_input, context)

    # Pipe support: use $out as last output
    if "$out" in command_input and COMMAND_HISTORY:
        last_output = COMMAND_HISTORY[-1]["result"] if "result" in COMMAND_HISTORY[-1] else ""
        command_input = command_input.replace("$out", str(last_output))

    parts = command_input.split()
    cmd = parts[0]
    args = parts[1:]

    real_cmd = COMMAND_ALIASES.get(cmd, cmd)

    if real_cmd in COMMANDS:
        user = (context or {}).get("user", "unknown")

        # Permission check
        if not check_command_permission(real_cmd, context):
            log_command(real_cmd, args, user, False, error="Permission denied")
            return "[Command] Permission denied."

        try:
            # If argparse is registered, parse and inject into context
            if real_cmd in COMMAND_ARGPARSE:
                namespace = COMMAND_ARGPARSE[real_cmd](args)
                context = context or {}
                context["argparse"] = namespace
            result = COMMANDS[real_cmd](args, context or {})
            log_command(real_cmd, args, user, True, result=result)
            return result
        except Exception as e:
            log_command(real_cmd, args, user, False, error=str(e))
            return f"[Command Error] {e}"
    else:
        return f"[Command] Unknown command: {cmd}"

def check_command_permission(cmd: str, context: Optional[Dict[str, Any]]) -> bool:
    """Checks if the user in context has permission to run the command."""
    if not context or "user_manager" not in context or "user" not in context:
        return True  # Default allow if no user context
    user_manager = context["user_manager"]
    username = context["user"]
    if cmd not in COMMAND_PERMISSIONS:
        return True
    for perm in COMMAND_PERMISSIONS[cmd]:
        if not user_manager.has_permission(username, perm):
            return False
    return True

def log_command(cmd: str, args: List[str], user: str, success: bool, error: str = "", result: str = ""):
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user": user,
        "command": cmd,
        "args": args,
        "success": success,
        "error": error,
        "result": result
    }
    COMMAND_HISTORY.append(entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def list_commands(category_filter: str = None) -> List[str]:
    return [
        cmd
        for cmd in COMMANDS
        if not category_filter or COMMAND_CATEGORIES.get(cmd) == category_filter
    ]

def get_command_suggestion(cmd: str, lang: str = "en") -> str:
    if lang != "en" and cmd in COMMAND_I18N and lang in COMMAND_I18N[cmd]:
        return COMMAND_I18N[cmd][lang]
    return COMMAND_SUGGESTIONS.get(cmd, "")

def list_categories() -> List[str]:
    return sorted(set(COMMAND_CATEGORIES.values()))

def get_command_aliases(cmd: str) -> List[str]:
    return [alias for alias, name in COMMAND_ALIASES.items() if name == cmd]

def search_command_history(keyword: str = "") -> List[Dict[str, Any]]:
    if not keyword:
        return COMMAND_HISTORY
    return [
        entry
        for entry in COMMAND_HISTORY
        if keyword in entry["command"]
        or any(keyword in str(arg) for arg in entry["args"])
        or keyword in entry.get("result", "")
    ]

def get_command_help(cmd: str, lang: str = "en") -> str:
    if cmd not in COMMANDS:
        return f"[Help] Command '{cmd}' not found."
    help_str = f"[Help] {cmd}: {get_command_suggestion(cmd, lang)}"
    aliases = get_command_aliases(cmd)
    if aliases:
        help_str += f"\nAliases: {', '.join(aliases)}"
    perms = COMMAND_PERMISSIONS.get(cmd)
    if perms:
        help_str += f"\nPermissions required: {', '.join(perms)}"
    if cmd in COMMAND_ARGPARSE:
        help_str += f"\nUsage: {cmd} {COMMAND_ARGPARSE[cmd](['--help']).format_usage().strip()}"
    return help_str

def list_commands_detailed(category_filter: str = None, lang: str = "en") -> List[str]:
    cmds = list_commands(category_filter)
    return [
        f"{cmd} (aliases: {', '.join(get_command_aliases(cmd))}) - {get_command_suggestion(cmd, lang)}"
        for cmd in cmds
    ]

def load_plugins(directory: str = PLUGIN_DIR):
    """Auto-loads command plugins from a directory."""
    for fname in os.listdir(directory):
        if fname.endswith(".py") and not fname.startswith("_"):
            path = os.path.join(directory, fname)
            spec = importlib.util.spec_from_file_location(fname[:-3], path)
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                # Plugins should call register_command when loaded
            except Exception as e:
                logging.error(f"[Command Plugin] Failed to load {fname}: {e}")

def run_command_chain(chain: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Runs multiple commands separated by ';' and pipes output if possible."""
    commands = [c.strip() for c in chain.split(";") if c.strip()]
    last_output = ""
    for command in commands:
        command = command.replace("$out", last_output)
        last_output = run_command(command, context)
    return last_output

def async_run_command(command_input: str, context: Optional[Dict[str, Any]] = None):
    """Run a command asynchronously (background jobs support)."""
    def target():
        run_command(command_input, context)
    t = threading.Thread(target=target)
    t.daemon = True
    t.start()
    return "[Command] Running in background."

# --- Argparse Example ---
def echo_argparse(args: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="echo", description="Echo arguments.")
    parser.add_argument("words", nargs="*", help="Words to echo")
    return parser.parse_args(args)

# --- Example Built-in Commands ---

def echo(args: List[str], context: Dict[str, Any]) -> str:
    if "argparse" in context:
        return " ".join(context["argparse"].words)
    return " ".join(args)

def help_cmd(args: List[str], context: Dict[str, Any]) -> str:
    lang = context.get("lang", "en") if context else "en"
    if args and args[0] in COMMANDS:
        return get_command_help(args[0], lang)
    cmds = list_commands()
    return "[Help] Commands: " + ", ".join(cmds)

def cmds_cmd(args: List[str], context: Dict[str, Any]) -> str:
    lang = context.get("lang", "en") if context else "en"
    return "\n".join(list_commands_detailed(args[0] if args else None, lang))

def history_cmd(args: List[str], context: Dict[str, Any]) -> str:
    keyword = args[0] if args else ""
    entries = search_command_history(keyword)
    return "\n".join(
        f"{e['time']} {e['user']} {e['command']} {' '.join(e['args'])} {'OK' if e['success'] else 'FAIL'}"
        for e in entries[-20:]
    )

def categories_cmd(args: List[str], context: Dict[str, Any]) -> str:
    return "Categories: " + ", ".join(list_categories())

# --- Example: Admin command with permission and alias ---
def shutdown_cmd(args: List[str], context: Dict[str, Any]) -> str:
    return "[System] Shutting down (simulated)."

register_command(
    "echo",
    echo,
    "Utility",
    "Repeats your input",
    aliases=["repeat", "say"],
    argparse_func=echo_argparse,
    i18n={"fr": "Répète votre entrée", "es": "Repite tu entrada"}
)
register_command(
    "help",
    help_cmd,
    "Utility",
    "Shows available commands or help for one",
    aliases=["?"],
    i18n={"fr": "Affiche les commandes ou l'aide", "es": "Muestra los comandos o la ayuda"}
)
register_command(
    "cmds",
    cmds_cmd,
    "Utility",
    "Lists all commands, optionally by category",
    aliases=["commands", "list"],
    i18n={"fr": "Liste toutes les commandes", "es": "Lista todos los comandos"}
)
register_command(
    "history",
    history_cmd,
    "Utility",
    "Shows recent command history, optionally filtered",
    aliases=["cmdhist"],
    permissions=["user"]
)
register_command(
    "categories",
    categories_cmd,
    "Utility",
    "Lists command categories",
    aliases=["cats"]
)
register_command(
    "shutdown",
    shutdown_cmd,
    "Admin",
    "Shuts down the system (admin only)",
    aliases=["poweroff", "halt"],
    permissions=["admin"]
)

# --- Load plugins on import ---
load_plugins()

# --- Plugin loader for dynamic command discovery ---
def reload_plugins():
    """Reload all plugin commands."""
    # Remove all plugin commands (not built-in)
    builtins = {"echo", "help", "cmds", "history", "categories", "shutdown"}
    for k in list(COMMANDS):
        if k not in builtins:
            COMMANDS.pop(k)
            COMMAND_CATEGORIES.pop(k, None)
            COMMAND_SUGGESTIONS.pop(k, None)
            COMMAND_PERMISSIONS.pop(k, None)
            COMMAND_ARGPARSE.pop(k, None)
            COMMAND_I18N.pop(k, None)
    COMMAND_ALIASES.clear()
    load_plugins()

register_command(
    "reload_plugins",
    lambda args, ctx: (reload_plugins() or "[Command] Plugins reloaded."),
    "Admin",
    "Reloads all plugin commands",
    permissions=["admin"]
)

# --- Internationalization Example ---
def set_lang_cmd(args: List[str], context: Dict[str, Any]) -> str:
    if not args:
        return "[Lang] Please specify a language code."
    lang = args[0]
    if context is not None:
        context["lang"] = lang
    return f"[Lang] Language set to {lang}."

register_command(
    "setlang",
    set_lang_cmd,
    "Utility",
    "Sets the command help language",
    aliases=["lang", "language"]
)