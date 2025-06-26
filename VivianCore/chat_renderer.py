import sys
import time
import shutil
import threading
import re
import json
import os
from datetime import datetime

class ChatRenderer:
    """
    Ultra-advanced, extensible chat renderer for terminal, web, and plugin-based AGI/LLM agents.
    Features:
    - Typing simulation, color, markdown, emoji, hyperlinks, timestamps, code blocks, spinners, history, theming, plugin hooks, sound, export/import, search, accessibility, notifications, LLM streaming, per-user customization, auto mode switching, web GUI, collaborative chat, DB support, analytics, screen reader, curses UI, macros, dynamic plugins, and more.
    - Multi-backend: CLI, Web, Remote, and extensible via hooks/plugins.
    """

    DEFAULT_COLORS = {
        "Vivian": "magenta",
        "User": "cyan",
        "System": "yellow",
        "Error": "red",
        "AI": "green"
    }

    THEMES = {
        "dark": {
            "background": "\033[40m",
            "reset": "\033[0m",
        },
        "light": {
            "background": "\033[107m",
            "reset": "\033[0m",
        },
        "solarized": {
            "background": "\033[48;5;235m",
            "reset": "\033[0m"
        }
    }

    def __init__(
        self,
        typing_speed=0.002,
        enable_typing=True,
        use_colors=True,
        history_log=None,
        show_timestamps=True,
        spinner_style=None,
        enable_markdown=True,
        speaker_colors=None,
        plugin_hooks=None,
        theme="dark",
        enable_sound=False,
        enable_websocket=False,
        websocket_url=None,
        per_user_config=None,
        enable_notifications=False,
        accessibility_mode=False,
        llm_stream_callback=None,
        mode=None,
        db_path=None,
        enable_analytics=False,
        screen_reader_mode=False,
        macro_hooks=None,
        dynamic_plugin_dirs=None,
        curses_ui=False,
        web_gui_callback=None,
        collaborative_chat_server=None
    ):
        self.terminal_width = shutil.get_terminal_size((80, 20)).columns
        self.lock = threading.Lock()
        self.history = []
        self.history_log = history_log
        self.typing_speed = typing_speed
        self.enable_typing = enable_typing
        self.use_colors = use_colors
        self.show_timestamps = show_timestamps
        self.spinner_style = spinner_style or ['|', '/', '-', '\\']
        self.enable_markdown = enable_markdown
        self.theme = theme if theme in self.THEMES else "dark"
        self.speaker_colors = {**ChatRenderer.DEFAULT_COLORS, **(speaker_colors or {})}
        self.plugin_hooks = plugin_hooks or []
        self.web_clients = set()
        self.enable_sound = enable_sound
        self.enable_websocket = enable_websocket
        self.websocket_url = websocket_url
        self.enable_notifications = enable_notifications
        self.per_user_config = per_user_config or {}
        self.accessibility_mode = accessibility_mode
        self.llm_stream_callback = llm_stream_callback
        self.mode = mode or self.detect_mode()
        self.db_path = db_path
        self.enable_analytics = enable_analytics
        self.screen_reader_mode = screen_reader_mode
        self.macro_hooks = macro_hooks or []
        self.dynamic_plugin_dirs = dynamic_plugin_dirs or []
        self.curses_ui = curses_ui
        self.web_gui_callback = web_gui_callback
        self.collaborative_chat_server = collaborative_chat_server
        if self.enable_websocket and self.websocket_url:
            self._init_websocket()
        if self.dynamic_plugin_dirs:
            self.load_dynamic_plugins()

    def detect_mode(self):
        if "jupyter" in sys.modules:
            return "jupyter"
        if os.environ.get("TERM", "").startswith("xterm"):
            return "cli"
        if os.environ.get("VIVIAN_WEB_MODE", False):
            return "web"
        return "cli"

    def _init_websocket(self):
        try:
            import websocket
            ws = websocket.WebSocket()
            ws.connect(self.websocket_url)
            self.web_clients.add(ws)
        except Exception as e:
            print(f"[ChatRenderer] WebSocket init failed: {e}")

    def load_dynamic_plugins(self):
        for plugin_dir in self.dynamic_plugin_dirs:
            if not os.path.isdir(plugin_dir):
                continue
            for fname in os.listdir(plugin_dir):
                if fname.endswith(".py"):
                    path = os.path.join(plugin_dir, fname)
                    try:
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(fname[:-3], path)
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "register_plugin"):
                            mod.register_plugin(self)
                    except Exception as e:
                        print(f"Failed to load plugin {fname}: {e}")

    def type_out(self, text, typing_speed=None):
        speed = typing_speed if typing_speed is not None else self.typing_speed
        if not self.enable_typing or self.screen_reader_mode or self.accessibility_mode:
            print(text)
            return
        for char in text:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(speed)
        print()

    def format_message(self, speaker, message, color=None, timestamp=None, user=None):
        cfg = self.per_user_config.get(user or speaker, {})
        header = f"{speaker}:"
        indent = ' ' * (len(header) + 1)
        msg = self.render_markdown(message, speaker=speaker) if self.enable_markdown or cfg.get("enable_markdown", False) else message
        wrapped = self.wrap_text(msg, indent=indent)
        if color is None and speaker in self.speaker_colors:
            color = cfg.get("color", self.speaker_colors[speaker])
        if color and self.use_colors:
            header = self.color_text(header, color)
        ts = f" [{timestamp}]" if (timestamp and self.show_timestamps) else ""
        return f"{header} {wrapped}{ts}"

    def wrap_text(self, text, indent=''):
        lines = []
        current_line = ''
        for word in text.split():
            clean_word = re.sub(r"\033\[[0-9;]*m", "", word)
            if len(current_line) + len(clean_word) + 1 > self.terminal_width:
                lines.append(current_line)
                current_line = indent + word
            else:
                if current_line:
                    current_line += ' ' + word
                else:
                    current_line = word
        if current_line:
            lines.append(current_line)
        return '\n'.join(lines)

    def color_text(self, text, color):
        color_codes = {
            'red': '\033[91m',
            'green': '\033[92m',
            'yellow': '\033[93m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'cyan': '\033[96m',
            'white': '\033[97m',
            'grey': '\033[90m',
            'reset': '\033[0m'
        }
        return f"{color_codes.get(color, '')}{text}{color_codes['reset']}"

    def print_message(self, speaker, message, color=None, typing_speed=None, timestamp=None, sound=None, user=None):
        formatted = self.format_message(
            speaker, message, color, timestamp or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), user=user
        )
        with self.lock:
            self.type_out(formatted, typing_speed=typing_speed)
        for hook in self.plugin_hooks:
            try:
                hook(speaker, message, color, timestamp, user)
            except Exception as e:
                print(self.color_text(f"[Renderer Plugin Error] {e}", "red"))
        for macro in self.macro_hooks:
            try:
                macro(speaker, message, color, timestamp, user)
            except Exception as e:
                print(self.color_text(f"[Renderer Macro Error] {e}", "red"))
        if self.enable_sound and (sound or speaker == "Vivian"):
            self.play_sound(sound or "default")
        if self.enable_websocket:
            self.send_websocket({"speaker": speaker, "message": message, "color": color, "timestamp": timestamp})
        if self.enable_notifications and speaker != "User":
            self.send_notification(f"New message from {speaker}", message)
        if self.web_gui_callback:
            self.web_gui_callback(speaker, message, color, timestamp, user)
        if self.collaborative_chat_server:
            self.collaborative_chat_server.broadcast(speaker, message, color, timestamp, user)
        record = {
            "speaker": speaker,
            "message": message,
            "color": color,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "user": user
        }
        self.history.append(record)
        if self.history_log:
            with open(self.history_log, "a") as f:
                f.write(json.dumps(record) + "\n")
        if self.db_path and self.enable_analytics:
            self.save_to_db(record)

    def render_markdown(self, text, speaker=None):
        text = re.sub(r"```(.*?)```", lambda m: "\n"+self.color_text(m.group(1), "green")+"\n", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", lambda m: self.color_text(m.group(1), "green"), text)
        text = re.sub(r"\*\*(.*?)\*\*", lambda m: self.color_text(m.group(1), "yellow"), text)
        text = re.sub(r"\*(.*?)\*", lambda m: self.color_text(m.group(1), "cyan"), text)
        text = re.sub(r"(https?://\S+)", lambda m: self.hyperlink(m.group(1)), text)
        text = text.replace(":robot:", "🤖").replace(":user:", "🧑").replace(":warning:", "⚠️")
        text = re.sub(r"\$(.*?)\$", lambda m: self.color_text(m.group(1), "blue"), text)
        if "|" in text and "---" in text:
            text = self.render_table(text)
        text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", lambda m: "[Image: "+m.group(1)+"] "+m.group(2), text)
        return text

    def render_table(self, text):
        rows = [row.strip() for row in text.strip().split('\n') if "|" in row]
        if not rows:
            return text
        output = []
        for row in rows:
            cols = [col.strip() for col in row.split("|")]
            output.append(" | ".join(cols))
        return "\n".join(output)

    def print_code_block(self, code, language=""):
        border = self.color_text("─" * (self.terminal_width - 2), "grey")
        print(self.color_text("┌" + border + "┐", "grey"))
        for line in code.split('\n'):
            print(self.color_text("│ ", "grey") + self.color_text(line, "green"))
        print(self.color_text("└" + border + "┘", "grey"))

    def show_spinner(self, msg="Thinking...", delay=0.1, duration=2):
        spinner = self.spinner_style
        end_time = time.time() + duration
        i = 0
        while time.time() < end_time:
            sys.stdout.write(f"\r{msg} {spinner[i % len(spinner)]}")
            sys.stdout.flush()
            time.sleep(delay)
            i += 1
        sys.stdout.write("\r" + " " * (len(msg) + 4) + "\r")

    def get_history(self, n=20):
        return self.history[-n:]

    def clear_history(self):
        self.history = []
        if self.history_log and os.path.exists(self.history_log):
            os.remove(self.history_log)

    def search_history(self, pattern, case_sensitive=False):
        regex = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        return [msg for msg in self.history if regex.search(msg["message"])]

    def export_history(self, path="chat_history.json"):
        with open(path, "w") as f:
            json.dump(self.history, f, indent=2)

    def import_history(self, path="chat_history.json"):
        if os.path.exists(path):
            with open(path, "r") as f:
                self.history = json.load(f)

    def print_conversation(self, messages):
        for msg in messages:
            self.print_message(
                msg.get("speaker"),
                msg.get("message"),
                msg.get("color"),
                timestamp=msg.get("timestamp"),
                user=msg.get("user")
            )

    def replay_history(self):
        self.print_conversation(self.history)

    def add_plugin_hook(self, hook):
        self.plugin_hooks.append(hook)

    def add_macro_hook(self, macro):
        self.macro_hooks.append(macro)

    def print_hyperlink(self, url, label=None):
        print(self.hyperlink(url, label))

    def hyperlink(self, url, label=None):
        label = label or url
        if self.mode == "web" and self.web_gui_callback:
            return f'<a href="{url}" target="_blank">{label}</a>'
        if os.environ.get("TERM", "").startswith("xterm"):
            return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"
        return self.color_text(label, "blue")

    def send_notification(self, title, message):
        try:
            if sys.platform == "darwin":
                os.system(f"""osascript -e 'display notification "{message}" with title "{title}"' """)
            elif "linux" in sys.platform:
                os.system(f'notify-send "{title}" "{message}"')
            elif sys.platform == "win32":
                import winsound
                winsound.MessageBeep()
        except Exception:
            pass

    def print_system_error(self, message):
        self.print_message("Error", message, color="red")

    def print_system(self, message):
        self.print_message("System", message, color="yellow")

    def play_sound(self, sound_type="default"):
        try:
            if sys.platform == "win32":
                import winsound
                freq = 750 if sound_type == "default" else 440
                winsound.Beep(freq, 100)
            else:
                sys.stdout.write('\a')
                sys.stdout.flush()
        except Exception:
            pass

    def send_websocket(self, message):
        try:
            for ws in self.web_clients:
                ws.send(json.dumps(message))
        except Exception:
            pass

    def print_llm_stream(self, token_stream, speaker="Vivian", color=None, user=None):
        output = []
        with self.lock:
            for token in token_stream:
                sys.stdout.write(self.color_text(token, color or self.speaker_colors.get(speaker, "magenta")))
                sys.stdout.flush()
                output.append(token)
                if self.llm_stream_callback:
                    self.llm_stream_callback(token)
            print()
        self.history.append({
            "speaker": speaker,
            "message": "".join(output),
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "user": user
        })

    def theme_background(self):
        return self.THEMES[self.theme]["background"] if self.theme in self.THEMES else ""

    def theme_reset(self):
        return self.THEMES[self.theme]["reset"] if self.theme in self.THEMES else ""

    def set_theme(self, theme_name):
        if theme_name in self.THEMES:
            self.theme = theme_name

    def set_user_config(self, user, config):
        self.per_user_config[user] = config

    def print_accessibility_message(self, speaker, message):
        if self.accessibility_mode or self.screen_reader_mode:
            print("===")
            self.print_message(speaker, message, color="white")
            print("===")

    def auto_mode_switch(self, preferred=None):
        self.mode = preferred or self.detect_mode()

    def print_conversation_map(self):
        print(self.color_text("[Conversation Map/Tree rendering not implemented]", "grey"))

    # --- Save to DB (stub, for analytics) ---
    def save_to_db(self, record):
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                speaker TEXT, message TEXT, color TEXT, timestamp TEXT, user TEXT
            )''')
            c.execute('''INSERT INTO chat_history (speaker, message, color, timestamp, user)
                         VALUES (?, ?, ?, ?, ?)''',
                         (record["speaker"], record["message"], record["color"], record["timestamp"], record.get("user")))
            conn.commit()
            conn.close()
        except Exception as e:
            print(self.color_text(f"[DB Error] {e}", "red"))