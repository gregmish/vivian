import threading
import logging
from typing import Dict, Any, Optional, Callable

try:
    import tkinter as tk
    from tkinter import scrolledtext, messagebox, simpledialog
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

def gui_supported():
    return GUI_AVAILABLE

class VivianGUI:
    """
    Vivian's advanced Tkinter GUI.
    - Scrollable, stylized conversation history
    - Input box with command and chat support
    - Input history navigation (up/down)
    - Speak/listen buttons (VoiceIO integration)
    - Clear, copy, export, and settings controls
    - Typing/system indicators
    - EventBus integration (show events, memory, voice, etc.)
    - Plugin panel support (for future extensibility)
    - Graceful shutdown and error handling
    """
    def __init__(
        self,
        memory,
        config: Dict[str, Any],
        event_bus=None,
        voiceio=None,
        command_handler: Optional[Callable[[str, Any, Any], str]] = None,
        plugins: Optional[Dict[str, Callable]] = None
    ):
        if not GUI_AVAILABLE:
            logging.warning("[GUI] Tkinter not installed.")
            return
        self.memory = memory
        self.config = config
        self.event_bus = event_bus
        self.voiceio = voiceio
        self.command_handler = command_handler
        self.plugins = plugins or {}
        self.input_history = []
        self.history_idx = -1
        self._last_system_tag = None
        self.session = []

        self.app = tk.Tk()
        self.app.title(config.get("name", "Vivian"))
        self.app.protocol("WM_DELETE_WINDOW", self.shutdown)

        # --- Output area (conversation log) ---
        self.output_area = scrolledtext.ScrolledText(
            self.app, wrap=tk.WORD, width=80, height=26, font=("Consolas", 11), state=tk.NORMAL
        )
        self.output_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # --- Input frame (entry + controls) ---
        input_frame = tk.Frame(self.app)
        input_frame.pack(padx=10, pady=(0, 10), fill=tk.X)
        self.input_box = tk.Entry(input_frame, width=60, font=("Consolas", 11))
        self.input_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.input_box.focus()

        send_btn = tk.Button(input_frame, text="Send", command=self.handle_input)
        send_btn.pack(side=tk.LEFT, padx=5)

        if voiceio:
            if voiceio.voice_enabled:
                speak_btn = tk.Button(input_frame, text="🔊 Speak", command=self.speak_last_reply)
                speak_btn.pack(side=tk.LEFT, padx=2)
            if voiceio.listen_enabled:
                listen_btn = tk.Button(input_frame, text="🎤 Listen", command=self.listen_and_send)
                listen_btn.pack(side=tk.LEFT, padx=2)

        clear_btn = tk.Button(input_frame, text="Clear", command=self.clear_history)
        clear_btn.pack(side=tk.RIGHT, padx=2)

        copy_btn = tk.Button(input_frame, text="Copy", command=self.copy_history)
        copy_btn.pack(side=tk.RIGHT, padx=2)

        export_btn = tk.Button(input_frame, text="Export", command=self.export_history)
        export_btn.pack(side=tk.RIGHT, padx=2)

        settings_btn = tk.Button(input_frame, text="⚙️", command=self.open_settings)
        settings_btn.pack(side=tk.RIGHT, padx=2)

        if self.plugins:
            plugin_btn = tk.Button(input_frame, text="Plugins", command=self.show_plugins)
            plugin_btn.pack(side=tk.RIGHT, padx=2)

        self.input_box.bind("<Return>", lambda e: self.handle_input())
        self.input_box.bind("<Up>", self.history_up)
        self.input_box.bind("<Down>", self.history_down)

        # --- Start GUI main loop in a thread ---
        threading.Thread(target=self.app.mainloop, daemon=True).start()

        # --- Subscribe to events ---
        if event_bus:
            event_bus.subscribe("memory_updated", self.on_event)
            event_bus.subscribe("memory_deleted", self.on_event)
            event_bus.subscribe("memory_expired", self.on_event)
            event_bus.subscribe("memory_cleared", self.on_event)
            event_bus.subscribe("voice_spoken", self.on_event)
            event_bus.subscribe("voice_recognized", self.on_event)
            event_bus.subscribe("voice_error", self.on_event)
            event_bus.subscribe("wake_word_detected", self.on_event)
            event_bus.subscribe("command_executed", self.on_event)
            event_bus.subscribe("system_shutdown", self.on_event)

    # --- Core input handling ---

    def handle_input(self):
        user_input = self.input_box.get().strip()
        if not user_input:
            return
        self.input_history.append(user_input)
        self.history_idx = len(self.input_history)
        self.input_box.delete(0, tk.END)
        self.display("You", user_input)
        self.display_system("Vivian is thinking...", tag="thinking")
        self.app.update()

        # Prefer injected command handler, else fallback to main.py
        try:
            if self.command_handler:
                reply = self.command_handler(user_input, self.memory, self.config)
            else:
                from main import handle_user_input
                reply = handle_user_input(user_input, self.memory, self.config)
            self.session.append({"user": user_input, "vivian": reply})
            self.clear_last_system(tag="thinking")
            self.display(self.config.get('name', 'Vivian'), reply)
        except Exception as e:
            self.clear_last_system(tag="thinking")
            self.display_system(f"Error: {e}")

    def display(self, who: str, msg: str):
        self.output_area.insert(tk.END, f"{who}: {msg}\n")
        self.output_area.see(tk.END)

    def display_system(self, msg: str, tag: Optional[str] = None):
        # Tag allows us to clear specific system messages (like "Vivian is thinking...")
        pos = self.output_area.index(tk.END)
        self.output_area.insert(tk.END, f"[System] {msg}\n")
        if tag:
            self._last_system_tag = (tag, pos)
        self.output_area.see(tk.END)

    def clear_last_system(self, tag: Optional[str] = None):
        if self._last_system_tag and (tag is None or self._last_system_tag[0] == tag):
            pos = self._last_system_tag[1]
            self.output_area.delete(f"{float(pos)-1}.0", pos)
            self._last_system_tag = None

    def clear_history(self):
        self.output_area.delete("1.0", tk.END)
        self.session.clear()

    def copy_history(self):
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(self.output_area.get("1.0", tk.END))
        except Exception as e:
            self.display_system(f"Copy error: {e}")

    def export_history(self):
        try:
            import datetime
            fname = f"vivian_chat_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(self.output_area.get("1.0", tk.END))
            self.display_system(f"Exported history to {fname}")
        except Exception as e:
            self.display_system(f"Export error: {e}")

    def open_settings(self):
        # Simple settings dialog (expand as needed)
        current_lang = self.config.get("voice_language", "en")
        new_lang = simpledialog.askstring("Settings", f"Voice Language (current: {current_lang})")
        if new_lang:
            self.config["voice_language"] = new_lang
            self.display_system(f"Voice language set to {new_lang}")
            if self.voiceio:
                self.voiceio.lang = new_lang

    def show_plugins(self):
        # List and run plugins via a simple popup
        plugin_names = list(self.plugins.keys())
        if not plugin_names:
            messagebox.showinfo("Plugins", "No plugins loaded.")
            return
        plugin = simpledialog.askstring("Plugins", f"Available: {', '.join(plugin_names)}\nEnter plugin to run:")
        if plugin and plugin in self.plugins:
            try:
                result = self.plugins[plugin]()
                self.display_system(f"[Plugin:{plugin}] {result}")
            except Exception as e:
                self.display_system(f"Plugin error: {e}")

    def speak_last_reply(self):
        if self.voiceio:
            last_reply = self._get_last_reply()
            if last_reply:
                self.voiceio.speak(last_reply, background=True)

    def listen_and_send(self):
        if self.voiceio:
            def callback(text):
                self.input_box.insert(0, text)
                self.handle_input()
            self.display_system("Listening for speech...", tag="listening")
            self.voiceio.listen(background=True, result_callback=callback)

    def history_up(self, event):
        if self.input_history and self.history_idx > 0:
            self.history_idx -= 1
            self.input_box.delete(0, tk.END)
            self.input_box.insert(0, self.input_history[self.history_idx])

    def history_down(self, event):
        if self.input_history and self.history_idx < len(self.input_history) - 1:
            self.history_idx += 1
            self.input_box.delete(0, tk.END)
            self.input_box.insert(0, self.input_history[self.history_idx])
        else:
            self.input_box.delete(0, tk.END)

    def _get_last_reply(self) -> str:
        try:
            if self.session:
                return self.session[-1].get("vivian", "[No reply]")
            if hasattr(self.memory, 'session') and self.memory.session:
                return self.memory.session[-1].get("vivian", "[No reply]")
            return "[No reply]"
        except Exception as e:
            return f"[GUI error: {e}]"

    def on_event(self, event):
        # Display system events in GUI
        if hasattr(event, "type") and hasattr(event, "data"):
            color = "blue" if "error" not in event.type else "red"
            msg = f"[Event] {event.type}: {event.data}"
            self.output_area.insert(tk.END, msg + "\n", color)
            self.output_area.see(tk.END)
            self.output_area.tag_config("red", foreground="red")
            self.output_area.tag_config("blue", foreground="blue")

    def shutdown(self):
        if messagebox.askokcancel("Quit", "Close Vivian?"):
            try:
                if self.voiceio:
                    self.voiceio.shutdown()
                if self.event_bus:
                    self.event_bus.publish("system_shutdown", data={"source": "gui"})
            except Exception:
                pass
            self.app.destroy()

def run_gui(memory, config, event_bus=None, voiceio=None, command_handler=None, plugins=None):
    """
    Launch Vivian's enhanced Tkinter GUI.
    """
    VivianGUI(memory, config, event_bus, voiceio, command_handler, plugins)