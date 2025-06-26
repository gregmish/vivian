import sys
import platform
import datetime
import psutil
import shutil
import difflib
import json
import os

# --- Command Aliases & Custom Shortcuts ---

ALIASES = {
    '/bye': '/exit',
    '/quit': '/exit',
    '/leave': '/exit',
    '/h': '/help',
    '/ls': '/plugins',
    '/pluginlist': '/plugins',
    '/hist': '/history',
    '/sched': '/scheduled',
}

def add_alias(alias, command):
    """Add a user-defined alias."""
    ALIASES[alias] = command

def get_command_for_alias(alias):
    """Return the command for an alias, or the alias itself if not found."""
    return ALIASES.get(alias, alias)

def print_aliases():
    print("Command Aliases:")
    for k, v in ALIASES.items():
        print(f"  {k} => {v}")

# --- Help System ---

def print_help(extra_commands=None, plugin_help=None, show_shortcuts=True, categories=None, show_aliases=True):
    """
    Print Vivian's help message with commands, optional plugin info, system shortcuts, and categories.
    """
    help_text = """
Available commands:
  /exit, /quit, /bye   - Exit the program
  /help, /h            - Show this help message
  /voice               - List available voices
  /plugins             - List available plugins
  /plugin <name>       - Show details/help for a plugin
  /clear               - Clear memory
  /export              - Export session memory
  /settings            - Open interactive settings
  /history, /hist      - Show recent chat history
  /personas            - List personas
  /persona <name>      - Set persona
  /reload              - Reload plugins
  /stats               - Show system stats
  /files               - List supported file types
  /schedule <task>     - Schedule a task
  /scheduled, /sched   - List scheduled tasks
  /gui                 - Launch GUI if available
  /server              - Launch web server if available
  /about               - Show Vivian info and credits
  /health              - Show system health/diagnostics
  /recent              - Show recent commands/interactions
  /shortcuts           - List keyboard shortcuts
  /aliases             - Show command aliases
  /easteregg           - Show a Vivian fun fact or quote
  /savehelp            - Export this help to a file
  /category <name>     - List commands by category
  /tips                - Show user prompt tips
  /help <command>      - Show detailed help for a command
  !<plugin> [args...]  - Run a plugin by name
  >>filename           - Run file handler on given file
"""
    if extra_commands:
        help_text += "\nExtra commands:\n"
        for cmd in extra_commands:
            help_text += f"  {cmd}\n"
    if plugin_help:
        help_text += "\nPlugins:\n"
        for pl in plugin_help:
            help_text += f"  {pl['name']}: {pl.get('description','')}\n"
    if show_aliases:
        help_text += "\nAliases:\n"
        for a, c in ALIASES.items():
            help_text += f"  {a} => {c}\n"
    if show_shortcuts:
        help_text += """
Keyboard Shortcuts:
  Ctrl+C, Ctrl+D       - Exit
  Up/Down Arrow        - Command history (if supported)
  Tab                  - Autocomplete (if supported)
  Ctrl+L               - Clear screen
Tips:
- Use '/help <command>' for more info on a specific command.
- Use '/plugin <name>' for details on a specific plugin.
"""
    if categories:
        help_text += "\nCommand Categories:\n"
        for cat, cmds in categories.items():
            help_text += f"  {cat}: {', '.join(cmds)}\n"
    print(help_text)

def get_help_text(**kwargs):
    """Get the full help text as a string (for export or API)."""
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = s = StringIO()
    print_help(**kwargs)
    sys.stdout = old_stdout
    return s.getvalue()

def export_help(filepath="vivian_help.txt"):
    """Export help text to a file."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(get_help_text())
    print(f"Help exported to {filepath}")

def print_command_suggestions(partial: str, all_commands: list):
    """Suggest commands if user makes a typo or partial entry."""
    matches = difflib.get_close_matches(partial, all_commands, n=5, cutoff=0.5)
    if matches:
        print("Did you mean:")
        for cmd in matches:
            print(f"  {cmd}")

def print_category(category, categories):
    """Print commands grouped by category."""
    cmds = categories.get(category)
    if not cmds:
        print(f"No commands found in category '{category}'.")
        return
    print(f"Category '{category}': {', '.join(cmds)}")

# --- Contextual Tips, Prompt Tips, Fun ---

def prompt_tips():
    """Show Vivian's user prompt tips for better experience."""
    tips = [
        "You can use '/help' to see all commands.",
        "Use '!plugin_name arguments...' to run plugins directly.",
        "Try '/plugin <name>' for plugin-specific help.",
        "Use '/settings' to customize Vivian's behavior.",
        "Arrow keys and Tab may work for history and autocomplete.",
        "Type '/aliases' to see command aliases.",
        "Use '/category <name>' for grouped commands.",
    ]
    print("Tips:")
    for tip in tips:
        print(f"  - {tip}")

def print_easteregg():
    """Print a random fun fact or quote."""
    import random
    eggs = [
        "Vivian: \"AI is not magic, but I can still make your day better!\"",
        "Vivian: \"Did you know? My codebase supports plugins, just like your favorite editor!\"",
        "Vivian: \"Remember: It's always safe to /export before you experiment!\"",
        "Vivian: \"Fun fact: I never sleep, but I do love /reload-ing my plugins!\"",
        "Vivian: \"If you break me, just /reload. No hard feelings!\"",
    ]
    print(random.choice(eggs))

def print_logo(version: str = None):
    """Print a Vivian ASCII logo with version (optional)."""
    logo = r"""
 _    _ _     _             
| |  | (_)   | |            
| |  | |_ ___| |_ ___  _ __ 
| |/\| | / __| __/ _ \| '__|
\  /\  / \__ \ || (_) | |   
 \/  \/  |___/\__\___/|_|   
"""
    if version:
        print(logo + f"\nVivian AI v{version}\n")
    else:
        print(logo)

def print_about():
    """Print about and credits info."""
    print("""
Vivian AI - Your flexible, extensible assistant!
Developed by the Vivian Project contributors.
https://github.com/gregmish/vivian
License: MIT
""")

# --- Detailed Command Help ---

DETAILED_HELP = {
    "/exit": "Exit the program immediately.",
    "/help": "Show the main help message, or '/help <command>' for details.",
    "/voice": "List available voices for text-to-speech.",
    "/plugins": "List all registered plugins.",
    "/plugin": "Show description and usage for a specific plugin. Usage: /plugin <name>",
    "/clear": "Clear the short-term memory/context.",
    "/export": "Export the current session's history/memory to a file.",
    "/settings": "Open the interactive settings menu.",
    "/history": "Show recent chat/user command history.",
    "/personas": "List available personas for Vivian.",
    "/persona": "Switch to a different persona. Usage: /persona <name>",
    "/reload": "Reload all plugins from disk.",
    "/stats": "Show system and usage stats.",
    "/files": "List supported file types for file handling.",
    "/schedule": "Schedule a task. Usage: /schedule <task>",
    "/scheduled": "List all scheduled tasks.",
    "/gui": "Launch the GUI if supported.",
    "/server": "Launch the web server if supported.",
    "/about": "Show Vivian about and credits.",
    "/health": "Show system health and diagnostics.",
    "/recent": "Show recent commands or interactions.",
    "/shortcuts": "Show keyboard shortcuts.",
    "/aliases": "Print all defined command aliases.",
    "/easteregg": "Show a Vivian fun fact or quote.",
    "/savehelp": "Export this help text to a file.",
    "/category": "List commands in a specific category. Usage: /category <name>",
    "/tips": "Show usage and productivity tips.",
    "!<plugin>": "Run a plugin by name. Usage: !plugin_name [arguments...]",
    ">>filename": "Run file handler on a given file by path.",
}

def command_help(command: str):
    """
    Print detailed help for a specific command (expand as Vivian grows).
    """
    c = command.strip().split()[0].lower()
    found = DETAILED_HELP.get(c)
    if found:
        print(f"{c}: {found}")
    else:
        print(f"No detailed help found for: {command}")

# --- Command Grouping/Categories ---

CATEGORIES = {
    "core": ["/exit", "/help", "/about", "/stats", "/health", "/reload"],
    "memory": ["/clear", "/export", "/history"],
    "personality": ["/personas", "/persona"],
    "plugins": ["/plugins", "/plugin", "/reload"],
    "files": ["/files", ">>filename"],
    "tasks": ["/schedule", "/scheduled"],
    "ui": ["/gui", "/server"],
    "tips": ["/tips", "/easteregg", "/shortcuts"],
    "admin": ["/aliases", "/savehelp", "/category"],
}
def print_categories():
    print("Command Categories:")
    for cat, cmds in CATEGORIES.items():
        print(f"  {cat}: {', '.join(cmds)}")

# --- System/Stats/Health/Diagnostics ---

def print_stats(stats: dict = None, show_sysinfo: bool = True, show_time: bool = True, show_disk: bool = True):
    """
    Print Vivian's system stats, optionally with host/system info, time, and disk.
    """
    if not stats:
        print("No Vivian stats available.")
    else:
        print("Vivian System Stats:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    if show_sysinfo:
        print("\nHost/System Info:")
        print(f"  OS: {platform.system()} {platform.release()} ({platform.version()})")
        print(f"  Python: {platform.python_version()} ({platform.python_implementation()})")
        print(f"  Machine: {platform.node()} ({platform.machine()})")
        try:
            print(f"  CPU: {platform.processor()} / {psutil.cpu_count()} cores, {psutil.cpu_percent()}% usage")
            print(f"  RAM: {round(psutil.virtual_memory().total / (1024**3), 2)} GB total, {psutil.virtual_memory().percent}% used")
        except Exception:
            print("  (psutil not available, skipping detailed system stats)")
    if show_disk:
        try:
            total, used, free = shutil.disk_usage(os.path.abspath(os.sep))
            print(f"  Disk: {round(total/(1024**3),2)} GB total, {round(used/(1024**3),2)} GB used, {round(free/(1024**3),2)} GB free")
        except Exception:
            print("  (disk usage not available)")
    if show_time:
        now = datetime.datetime.now()
        print(f"\nCurrent Time: {now.strftime('%Y-%m-%d %H:%M:%S')} ({datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')})")

def print_health_status(health_info: dict):
    """Prints Vivian's health/diagnostics (uptime, errors, last check, etc)."""
    if not health_info:
        print("No health information available.")
        return
    print("Vivian Health Status:")
    for key, value in health_info.items():
        print(f"  {key}: {value}")

def print_recent_commands(recent: list):
    """Print recent user commands/interactions."""
    print("Recent Commands/Interactions:")
    for r in recent[-10:]:
        print(f"  {r}")

def print_error_log(error_log: list):
    """Print recent system/plugin errors."""
    print("Recent Errors:")
    for e in error_log[-10:]:
        print(f"  {e}")

def print_plugin_usage(plugin_stats: dict):
    """Print plugin usage/failure statistics."""
    print("Plugin Usage Stats:")
    for name, stat in plugin_stats.items():
        print(f"  {name}: {stat['runs']} runs, {stat['fails']} failures")

# --- API/GUI Integration Helpers ---

def help_as_dict():
    """Returns command help as dict (for API/UI)."""
    return DETAILED_HELP

def stats_as_dict(stats, health=None):
    """Return stats and health as a dict."""
    d = {"stats": stats}
    if health:
        d["health"] = health
    return d

def logo_as_text(version=None):
    """Return logo as text string."""
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = s = StringIO()
    print_logo(version=version)
    sys.stdout = old_stdout
    return s.getvalue()

# --- Accessibility & Export ---

def print_accessibility_help():
    print("""
Accessibility:
- Commands and help text can be displayed in high-contrast mode.
- All output is screen-reader friendly and available via API/GUI.
- For large help text, use /savehelp to export to a file.
""")

def save_help_markdown(filepath="vivian_help.md"):
    """Export help text in markdown format."""
    content = "## Vivian AI Help\n\n" + "```\n" + get_help_text() + "```\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Help exported as markdown to {filepath}")

# --- Fun: System Fortune ---

def print_fortune():
    quotes = [
        "The best way to predict the future is to invent it.",
        "Simplicity is the soul of efficiency.",
        "The only mistake is the one from which we learn nothing.",
        "Code never lies, comments sometimes do.",
        "Every great developer you know got there by solving problems they were unqualified to solve until they actually did it. – Patrick McKenzie",
    ]
    import random
    print("Vivian's fortune:\n  " + random.choice(quotes))