import datetime
import os
import random
import json
import platform
import threading
import time

GREETINGS_LOG = "logs/hello_plugin.log"
JOKES = [
    "Why did the computer show up at work late? It had a hard drive!",
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "Why did Vivian cross the road? To help you on the other side!",
    "Why do Java developers wear glasses? Because they can't C#!",
    "Why was the AI cold? Because it left its Windows open.",
    "Debugging: Being the detective in a crime movie where you are also the murderer."
]
FACTS = [
    "The first computer bug was an actual bug: a moth stuck in a relay.",
    "Vivian can be extended with plugins in Python.",
    "Python is named after Monty Python, not the snake.",
    "The first computer virus was created in 1971 and was called Creeper.",
    "The QWERTY keyboard was designed to slow down typing speed.",
    "The original name for Windows was 'Interface Manager'."
]
QUOTES = [
    "The best way to predict the future is to invent it. – Alan Kay",
    "Any sufficiently advanced technology is indistinguishable from magic. – Arthur C. Clarke",
    "It's not a bug – it's an undocumented feature.",
    "First, solve the problem. Then, write the code. – John Johnson"
]
LANGS = {
    "en": "Hello",
    "es": "¡Hola",
    "fr": "Bonjour",
    "de": "Hallo",
    "it": "Ciao",
    "ru": "Привет",
    "ja": "こんにちは",
    "zh": "你好",
}

def main(
    user=None,
    mood=None,
    joke=False,
    fact=False,
    quote=False,
    show_info=False,
    healthcheck=False,
    lang="en",
    timezone=None,
    admin_only=False,
    privacy=False,
    interactive=False,
    gdpr_export=False,
    gdpr_delete=False,
    schedule_greeting=None,
    add_joke=None,
    add_fact=None,
    add_quote=None,
    voice_output=False,
    analytics=False,
    weather=False,
    news=False,
    calendar_event=None,
    **kwargs
):
    """
    Vivian Quantum Hello Plugin:
    - Personalized, time/mood-aware, multi-lingual greeting.
    - Can tell a joke, fact, or quote. Shows plugin/system info, checks health, logs usage/history.
    - Supports privacy, admin-only, interactive, language/timezone, and scheduled greetings.
    - GDPR export/delete for logs. Users can add their own jokes/facts/quotes.
    - Voice output, analytics, external content, calendar event awareness.
    """
    now = datetime.datetime.now()
    hour = now.hour
    username = user or os.environ.get("USER", "Vivian User")
    admins = kwargs.get("admins", ["gregmish"])

    # Admin mode
    if admin_only and username not in admins:
        return "Permission denied: admin-only greeting."

    # GDPR Export/Delete
    if gdpr_export:
        return gdpr_history_export(username)
    if gdpr_delete:
        return gdpr_history_delete(username)

    # Privacy mode
    if privacy:
        username = "Anonymous"

    # Time zone support
    try:
        if timezone:
            import pytz
            tz = pytz.timezone(timezone)
            now = now.astimezone(tz)
    except Exception:
        pass

    # Add user joke/fact/quote
    if add_joke:
        _add_to_list(GREETINGS_LOG, "joke", add_joke)
        JOKES.append(add_joke)
    if add_fact:
        _add_to_list(GREETINGS_LOG, "fact", add_fact)
        FACTS.append(add_fact)
    if add_quote:
        _add_to_list(GREETINGS_LOG, "quote", add_quote)
        QUOTES.append(add_quote)

    # Localized greeting
    greet_word = LANGS.get(lang, LANGS["en"])
    # Smart greeting based on time of day and mood
    if mood:
        day_greet = f"{greet_word} ({mood.title()} mood)"
    elif 5 <= hour < 12:
        day_greet = f"{greet_word} Good morning"
    elif 12 <= hour < 18:
        day_greet = f"{greet_word} Good afternoon"
    elif 18 <= hour < 22:
        day_greet = f"{greet_word} Good evening"
    else:
        day_greet = f"{greet_word}"

    greeting = f"{day_greet}, {username}! Vivian's plugin system is working.\n"
    greeting += f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"

    # Calendar event awareness
    if calendar_event:
        greeting += f"Upcoming event: {calendar_event}\n"

    # Weather stub (can be replaced with real API)
    if weather:
        greeting += f"Weather: It's always sunny in Vivian World! (API integration ready)\n"

    # News stub (can be replaced with real API)
    if news:
        greeting += f"News: Vivian is now the most extensible AI! (API integration ready)\n"

    # Add joke
    if joke:
        greeting += f"Here's a joke: {random.choice(JOKES)}\n"

    # Add fact
    if fact:
        greeting += f"Did you know? {random.choice(FACTS)}\n"

    # Add quote
    if quote:
        greeting += f"Inspiration: {random.choice(QUOTES)}\n"

    # System/Plugin Info
    if show_info:
        greeting += (
            f"Plugin: hello.py | Version: 5.0\n"
            f"System: {platform.system()} {platform.release()} | Python: {platform.python_version()}\n"
            f"Working dir: {os.getcwd()}\n"
            f"Available languages: {', '.join(LANGS.keys())}\n"
        )

    # Healthcheck
    if healthcheck:
        try:
            writable = os.access(os.getcwd(), os.W_OK)
            greeting += f"Plugin health: OK, Writable: {writable}\n"
        except Exception as e:
            greeting += f"Plugin health: ERROR: {e}\n"

    # Logging usage
    log_entry = {
        "user": username,
        "time": now.isoformat(),
        "mood": mood,
        "joke": joke,
        "fact": fact,
        "quote": quote,
        "lang": lang,
        "privacy": privacy,
        "weather": weather,
        "news": news,
        "calendar_event": calendar_event
    }
    try:
        os.makedirs(os.path.dirname(GREETINGS_LOG), exist_ok=True)
        with open(GREETINGS_LOG, "a") as logf:
            logf.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass

    # Analytics
    if analytics:
        greeting += f"Analytics: {get_analytics()}\n"

    # Schedule greeting
    if schedule_greeting:
        _schedule_greeting(schedule_greeting, log_entry)

    # Voice output stub
    if voice_output:
        greeting += "[Voice output would play this greeting here (TTS integration ready)]\n"

    # Interactive mode
    if interactive:
        greeting += (
            "What would you like next?\n"
            "Type: 'joke', 'fact', 'quote', 'info', 'health', 'history', 'add_joke', 'add_fact', 'add_quote', 'gdpr_export', 'gdpr_delete', 'analytics', 'weather', 'news', 'exit'.\n"
        )

    return greeting

def _add_to_list(log_path, typ, content):
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as logf:
            logf.write(json.dumps({typ: content, "added_by": os.environ.get("USER", "Vivian User"), "time": datetime.datetime.now().isoformat()}) + "\n")
    except Exception:
        pass

def _schedule_greeting(seconds, log_entry):
    def delayed_greeting():
        time.sleep(seconds)
        print(main(**log_entry))
    threading.Thread(target=delayed_greeting, daemon=True).start()

def plugin_info():
    """Returns plugin metadata for discovery or introspection."""
    return {
        "name": "hello",
        "author": "Vivian AI Core",
        "version": "5.0",
        "tags": [
            "test", "hello", "greeting", "joke", "fact", "system", "interactive", "privacy",
            "logging", "localization", "admin", "history", "quote", "gdpr", "scheduler",
            "analytics", "voice", "weather", "news", "calendar"
        ],
        "description": (
            "Quantum greeter for Vivian: personalized, time/mood/language-aware. "
            "Can tell joke/fact/quote, log usage, check health, admin/privacy modes, schedule, GDPR, interactive, analytics, voice, weather/news/calendar (API-ready)."
        ),
        "usage": (
            "Call with options: user, mood, joke=True, fact=True, quote=True, show_info=True, healthcheck=True, "
            "lang='en', timezone, admin_only=True, privacy=True, interactive=True, gdpr_export=True, gdpr_delete=True, "
            "schedule_greeting=<seconds>, add_joke='...', add_fact='...', add_quote='...', voice_output=True, "
            "analytics=True, weather=True, news=True, calendar_event='Meeting at noon'."
        ),
        "features": [
            "Personalized, time-aware, and multi-lingual greetings",
            "Mood-based and privacy/admin mode support",
            "Random joke/fact/quote feature",
            "System info and plugin health check",
            "Usage logging and greeting history",
            "Interactive mode for CLI",
            "User-added jokes/facts/quotes",
            "Schedule greeting in the future",
            "GDPR export/delete for greeting history",
            "Voice output (TTS-ready)",
            "Analytics/statistics",
            "Weather/news/calendar event awareness (API-ready)",
            "Extensible with new features"
        ]
    }

def get_history(n=3, username=None):
    """Returns the last n greetings (optionally for a user) from the log."""
    history = []
    try:
        with open(GREETINGS_LOG, "r") as logf:
            lines = logf.readlines()
            lines = reversed(lines)
            count = 0
            for line in lines:
                try:
                    entry = json.loads(line.strip())
                    if username and entry.get("user") != username:
                        continue
                    history.append(entry)
                    count += 1
                    if count >= n:
                        break
                except Exception:
                    continue
    except Exception:
        pass
    return history

def gdpr_history_export(username):
    """Exports all greeting log entries for a user."""
    export = []
    try:
        with open(GREETINGS_LOG, "r") as logf:
            for line in logf:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("user") == username:
                        export.append(entry)
                except Exception:
                    continue
    except Exception:
        pass
    return json.dumps(export, indent=2) if export else "No data found for this user."

def gdpr_history_delete(username):
    """Deletes all greeting log entries for a user."""
    try:
        if not os.path.exists(GREETINGS_LOG):
            return "No data to delete."
        with open(GREETINGS_LOG, "r") as logf:
            lines = logf.readlines()
        with open(GREETINGS_LOG, "w") as logf:
            for line in lines:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("user") != username:
                        logf.write(json.dumps(entry) + "\n")
                except Exception:
                    continue
        return f"All greeting data for user '{username}' deleted."
    except Exception as e:
        return f"Error: {e}"

def get_analytics():
    """Returns simple analytics: most active user, total greetings, most popular feature."""
    users = {}
    jokes = facts = quotes = 0
    total = 0
    try:
        with open(GREETINGS_LOG, "r") as logf:
            for line in logf:
                try:
                    entry = json.loads(line.strip())
                    u = entry.get("user") or "Unknown"
                    users[u] = users.get(u, 0) + 1
                    if entry.get("joke"): jokes += 1
                    if entry.get("fact"): facts += 1
                    if entry.get("quote"): quotes += 1
                    total += 1
                except Exception:
                    continue
    except Exception:
        pass
    most_user = max(users, key=users.get) if users else None
    most_feat = max(
        [("joke", jokes), ("fact", facts), ("quote", quotes)],
        key=lambda x: x[1]
    )[0] if total else "none"
    return f"Total: {total} | Most active: {most_user} | Most popular: {most_feat}"

def interactive_cli():
    """A minimal interactive CLI for demo/testing purposes."""
    print(main(interactive=True))
    while True:
        cmd = input("hello> ").strip().lower()
        if cmd == "exit":
            print("Goodbye!")
            break
        elif cmd == "joke":
            print(main(joke=True))
        elif cmd == "fact":
            print(main(fact=True))
        elif cmd == "quote":
            print(main(quote=True))
        elif cmd == "info":
            print(main(show_info=True))
        elif cmd == "health":
            print(main(healthcheck=True))
        elif cmd == "history":
            hist = get_history()
            print("Last greetings:")
            for h in hist:
                print(f"- {h.get('time', '?')} :: {h.get('user', '?')} :: mood: {h.get('mood', '?')}, joke: {h.get('joke', False)}, fact: {h.get('fact', False)}, quote: {h.get('quote', False)}")
        elif cmd == "add_joke":
            j = input("Enter your joke: ").strip()
            _add_to_list(GREETINGS_LOG, "joke", j)
            JOKES.append(j)
            print("Joke added!")
        elif cmd == "add_fact":
            f = input("Enter your fact: ").strip()
            _add_to_list(GREETINGS_LOG, "fact", f)
            FACTS.append(f)
            print("Fact added!")
        elif cmd == "add_quote":
            q = input("Enter your quote: ").strip()
            _add_to_list(GREETINGS_LOG, "quote", q)
            QUOTES.append(q)
            print("Quote added!")
        elif cmd == "gdpr_export":
            username = input("Enter user for export: ").strip()
            print(gdpr_history_export(username))
        elif cmd == "gdpr_delete":
            username = input("Enter user for deletion: ").strip()
            print(gdpr_history_delete(username))
        elif cmd == "analytics":
            print(get_analytics())
        elif cmd == "weather":
            print(main(weather=True))
        elif cmd == "news":
            print(main(news=True))
        elif cmd.startswith("schedule "):
            try:
                seconds = int(cmd.split(" ", 1)[1])
                print(f"Greeting will be printed in {seconds} seconds.")
                _schedule_greeting(seconds, {})
            except Exception:
                print("Usage: schedule <seconds>")
        else:
            print(main())

# Minimal plugin registration
def register(register_plugin):
    register_plugin(
        name="hello",
        func=main,
        description=plugin_info()["description"],
        author=plugin_info()["author"],
        version=plugin_info()["version"],
        tags=plugin_info()["tags"],
        usage=plugin_info()["usage"],
        info_func=plugin_info,
        commands={
            "history": get_history,
            "interactive": interactive_cli,
            "gdpr_export": gdpr_history_export,
            "gdpr_delete": gdpr_history_delete,
            "add_joke": lambda j: _add_to_list(GREETINGS_LOG, "joke", j),
            "add_fact": lambda f: _add_to_list(GREETINGS_LOG, "fact", f),
            "add_quote": lambda q: _add_to_list(GREETINGS_LOG, "quote", q),
            "schedule": _schedule_greeting,
            "analytics": get_analytics,
        }
    )