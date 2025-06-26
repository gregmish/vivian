import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import datetime
import os
import re
import threading

try:
    from tkhtmlview import HTMLLabel  # For markdown/HTML rendering
except ImportError:
    HTMLLabel = None

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

# --- Import your Ultra OpenAI brain with all features ---
try:
    from model_openai_brain import (
        send_to_openai_brain,
        openai_embedding,
        openai_speech_to_text,
        openai_text_to_speech,
    )
except ImportError:
    def send_to_openai_brain(prompt, config, **kwargs):
        return f"[OpenAI module not installed]\nEcho: {prompt}"
    def openai_embedding(text, api_key, model="text-embedding-3-small"):
        return [0.0]
    def openai_speech_to_text(audio_file, api_key):
        return "[STT not available]"
    def openai_text_to_speech(text, api_key, voice="alloy"):
        return b""

class VivianChatApp(tk.Frame):
    def __init__(self, master, plugins=None, user_profile=None, config=None):
        super().__init__(master)
        self.master = master
        self.plugins = plugins or []
        self.config_brain = config or {}
        self.history = []
        self.font_scale = 1.0
        self.context_window = 5
        self.status_var = None
        self.last_response = ""
        self.input_history = []
        self.input_history_index = -1
        self.high_contrast = False
        self.avatar_path = None
        self.markdown_enabled = True
        self.user_profile = user_profile or {"name": "You", "avatar": None}
        self.persona = "Default"
        self.draft_message = ""
        self.bookmarks = []
        self.session_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self._stop_event = threading.Event()
        self.init_ui()

    def init_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # Avatar / Persona/Theme selector
        self.avatar_img = tk.Label(self, text="🙂", width=4, font=("Arial", int(28 * self.font_scale)))
        self.avatar_img.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(5, 0), pady=5)
        avatar_menu = ttk.Menubutton(self, text="Persona", direction="below")
        avatar_menu.menu = tk.Menu(avatar_menu, tearoff=0)
        avatar_menu["menu"] = avatar_menu.menu
        for persona in ["Default", "Developer", "Friendly", "Serious"]:
            avatar_menu.menu.add_command(label=persona, command=lambda p=persona: self.set_persona(p))
        avatar_menu.grid(row=1, column=0, sticky="w", padx=(5,0))

        # Chat area with scrollbar
        self.text_area = ScrolledText(self, wrap=tk.WORD, state="disabled", font=("Arial", int(12 * self.font_scale)), undo=True)
        self.text_area.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

        if self.draft_message:
            self.append_message("System", f"[Draft restored]: {self.draft_message}")

        # Entry frame (input + controls)
        entry_frame = tk.Frame(self)
        entry_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=(0, 5))
        entry_frame.columnconfigure(0, weight=1)

        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(entry_frame, textvariable=self.entry_var, font=("Arial", int(12 * self.font_scale)))
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", self.on_enter)
        self.entry.bind("<Up>", self.prev_input)
        self.entry.bind("<Down>", self.next_input)
        self.entry.bind("<Control-s>", self.save_draft)
        self.entry.focus_set()

        self.send_btn = ttk.Button(entry_frame, text="Send", command=self.send_message)
        self.send_btn.grid(row=0, column=1, padx=(5,0))
        self.clear_btn = ttk.Button(entry_frame, text="Clear", command=self.clear_chat)
        self.clear_btn.grid(row=0, column=2, padx=(5,0))
        self.copy_btn = ttk.Button(entry_frame, text="Copy", command=self.copy_all)
        self.copy_btn.grid(row=0, column=3, padx=(5,0))
        self.file_btn = ttk.Button(entry_frame, text="Attach", command=self.attach_file)
        self.file_btn.grid(row=0, column=4, padx=(5,0))
        self.bookmark_btn = ttk.Button(entry_frame, text="Bookmark", command=self.bookmark_message)
        self.bookmark_btn.grid(row=0, column=5, padx=(5,0))

        # Speech-to-Text (Whisper) and Text-to-Speech (TTS)
        self.speech_btn = ttk.Button(entry_frame, text="🎤", command=self.speech_to_text)
        self.speech_btn.grid(row=0, column=6, padx=(5,0))
        self.tts_btn = ttk.Button(entry_frame, text="🔊", command=self.text_to_speech)
        self.tts_btn.grid(row=0, column=7, padx=(5,0))

        self.contrast_btn = ttk.Button(entry_frame, text="High Contrast", command=self.toggle_contrast)
        self.contrast_btn.grid(row=0, column=8, padx=(5,0))
        self.palette_btn = ttk.Button(entry_frame, text="⚡", command=self.open_command_palette)
        self.palette_btn.grid(row=0, column=9, padx=(5,0))

        self.plugin_btns_frame = tk.Frame(entry_frame)
        self.plugin_btns_frame.grid(row=1, column=0, columnspan=10, sticky="w")
        self.update_plugin_buttons()

        # Search bar
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(entry_frame, textvariable=self.search_var, font=("Arial", int(10 * self.font_scale)))
        self.search_entry.grid(row=2, column=0, sticky="ew", columnspan=2, pady=(3,0))
        self.search_btn = ttk.Button(entry_frame, text="Search", command=self.search_history_btn)
        self.search_btn.grid(row=2, column=2, padx=(3,0))
        self.export_btn = ttk.Button(entry_frame, text="Export", command=self.export_conversation)
        self.export_btn.grid(row=2, column=3, padx=(3,0))
        self.summarize_btn = ttk.Button(entry_frame, text="Summarize", command=self.summarize_conversation)
        self.summarize_btn.grid(row=2, column=4, padx=(3,0))
        self.bookmark_list_btn = ttk.Button(entry_frame, text="Bookmarks", command=self.show_bookmarks)
        self.bookmark_list_btn.grid(row=2, column=5, padx=(3,0))

        self.master.bind('<Control-Return>', lambda e: self.send_message())
        self.master.bind('<Control-plus>', lambda e: self.set_font_scale(self.font_scale * 1.1))
        self.master.bind('<Control-minus>', lambda e: self.set_font_scale(self.font_scale * 0.9))
        self.master.bind('<Control-Shift-p>', lambda e: self.open_command_palette())
        self.master.bind('<Control-f>', lambda e: self.search_entry.focus_set())
        self.text_area.bind('<Button-3>', self.context_menu_popup)

    # Core Messaging and Plugins

    def on_enter(self, event):
        self.send_message()

    def prev_input(self, event):
        if not self.input_history:
            return
        if self.input_history_index == -1:
            self.input_history_index = len(self.input_history) - 1
        else:
            self.input_history_index = max(0, self.input_history_index - 1)
        self.entry_var.set(self.input_history[self.input_history_index])

    def next_input(self, event):
        if not self.input_history:
            return
        if self.input_history_index == -1:
            return
        self.input_history_index = min(len(self.input_history) - 1, self.input_history_index + 1)
        self.entry_var.set(self.input_history[self.input_history_index])

    def send_message(self):
        msg = self.entry_var.get().strip()
        if not msg:
            return
        self.append_message(self.user_profile.get("name", "You"), msg)
        self.entry_var.set("")
        self.history.append(f"You: {msg}")
        self.input_history.append(msg)
        self.input_history_index = -1
        self.draft_message = ""
        self.process_input(msg)

    def process_input(self, text):
        # Plugins first
        response, avatar, meta = self.run_plugins(text)
        if response is not None:
            self.append_message("Vivian", response)
            self.history.append(f"Vivian: {response}")
            self.last_response = response
            if avatar:
                self.update_avatar(avatar)
            if self.status_var:
                self.status_var.set(f"Responded at {datetime.datetime.now().strftime('%H:%M:%S')}")
            if meta.get("bookmark"):
                self.bookmark_message()
            return

        # --- Otherwise, send to brain (OpenAI) ---
        self.append_message("Vivian", "[Thinking...]")
        def run_brain():
            try:
                # Context for memory/RAG (last N messages)
                context = []
                for line in self.history[-self.context_window*2:]:
                    if ": " in line:
                        who, msg = line.split(": ", 1)
                        context.append({"role": "assistant" if who == "Vivian" else "user", "content": msg})
                persona = self.persona
                system_message = f"You are Vivian, an AI assistant. Persona: {persona}."

                # Vision (attach image if last message/file is an image)
                vision_image = None
                if len(self.history) > 0 and os.path.isfile(text) and text.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    vision_image = text

                # Use speech-to-text if last message was audio
                speech_file = None
                if text.lower().endswith(('.wav', '.mp3', '.m4a', '.flac')):
                    speech_file = text

                # Embedding (for RAG/memory): get embedding and optionally show
                embedding = None
                if self.config_brain.get("api_key"):
                    embedding = openai_embedding(text, self.config_brain["api_key"])
                    # Optionally, you can use embedding to retrieve context or store for future

                # Function calling / tool use: add your tools here
                tools = self.get_tools()

                # Streaming function (token-by-token updates)
                def stream_callback(token):
                    self.text_area.configure(state="normal")
                    self.text_area.insert(tk.END, token)
                    self.text_area.see(tk.END)
                    self.text_area.configure(state="disabled")

                # Send to OpenAI brain
                response = send_to_openai_brain(
                    text,
                    self.config_brain,
                    history=context,
                    persona=persona,
                    system_message=system_message,
                    vision_image=vision_image,
                    speech_file=speech_file,
                    tools=tools,
                    on_stream=stream_callback if self.config_brain.get("stream") else None,
                    explain=True,
                )
                # Remove "[Thinking...]" and add response
                self.text_area.configure(state="normal")
                self.text_area.delete("end-2l", "end-1l")
                self.text_area.configure(state="disabled")
                self.append_message("Vivian", response if isinstance(response, str) else str(response))
                self.history.append(f"Vivian: {response}")
                self.last_response = response
                if self.status_var:
                    self.status_var.set(f"Responded at {datetime.datetime.now().strftime('%H:%M:%S')}")
            except Exception as e:
                self.append_message("Vivian", f"[Brain Error] {e}")
        threading.Thread(target=run_brain, daemon=True).start()

    def run_plugins(self, text):
        meta = {}
        if text.startswith("!"):
            parts = text[1:].split()
            cmd = parts[0]
            args = parts[1:]
            for plugin in self.plugins:
                if hasattr(plugin, "name") and plugin.name == cmd:
                    try:
                        result = plugin(*args)
                        avatar = getattr(plugin, "avatar", None)
                        meta = getattr(plugin, "meta", {})
                        return (result, avatar, meta)
                    except Exception as e:
                        return (f"[Error] {e}", None, {})
        return (None, None, {})

    def get_tools(self):
        # Example OpenAI function calling tool format
        tools = []
        for plugin in self.plugins:
            if hasattr(plugin, "openai_tool"):
                tools.append(plugin.openai_tool)
        return tools if tools else None

    # Chat UI and Output (rest unchanged)
    def append_message(self, who, msg):
        self.text_area.configure(state="normal")
        if self.markdown_enabled and ("**" in msg or "[" in msg or "`" in msg):
            msg = self.render_markdown(msg)
        self.text_area.insert(tk.END, f"{who}: {msg}\n")
        self.text_area.configure(state="disabled")
        self.text_area.see(tk.END)

    def append_image(self, filepath):
        if not Image or not ImageTk:
            self.append_message("Vivian", f"[Image support not installed: {filepath}]")
            return
        try:
            img = Image.open(filepath)
            img.thumbnail((120, 120))
            img_tk = ImageTk.PhotoImage(img)
            self.text_area.image_create(tk.END, image=img_tk)
            self.text_area.insert(tk.END, f" [Image: {os.path.basename(filepath)}]\n")
            if not hasattr(self, "_img_refs"):
                self._img_refs = []
            self._img_refs.append(img_tk)
        except Exception as e:
            self.append_message("Vivian", f"[Failed to show image: {e}]")

    def render_markdown(self, text):
        text = re.sub(r"\*\*(.*?)\*\*", lambda m: m.group(1).upper(), text)
        text = re.sub(r"__(.*?)__", lambda m: m.group(1), text)
        text = re.sub(r"`(.*?)`", lambda m: f"[{m.group(1)}]", text)
        text = re.sub(r"\[(.*?)\]\((.*?)\)", lambda m: f"{m.group(1)}({m.group(2)})", text)
        text = re.sub(r"\$(.*?)\$", r"[MATH:\1]", text)
        return text

    def clear_chat(self):
        self.text_area.configure(state="normal")
        self.text_area.delete(1.0, tk.END)
        self.text_area.configure(state="disabled")
        self.history.clear()

    def copy_all(self):
        self.master.clipboard_clear()
        self.master.clipboard_append("\n".join(self.history))
        self.master.update()

    def attach_file(self):
        filename = filedialog.askopenfilename()
        if filename:
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                self.append_image(filename)
            elif filename.lower().endswith(('.wav', '.mp3', '.m4a', '.flac')):
                self.append_message("You", f"[Audio attached: {os.path.basename(filename)}]")
            else:
                self.append_message("You", f"[File attached: {os.path.basename(filename)}]")
            self.history.append(f"You: [File attached: {filename}]")
            self.process_input(filename)

    def speech_to_text(self):
        filename = filedialog.askopenfilename(filetypes=[("Audio Files", "*.wav *.mp3 *.m4a *.flac")])
        if filename and self.config_brain.get("api_key"):
            try:
                transcript = openai_speech_to_text(filename, self.config_brain["api_key"])
                self.append_message("You", f"[STT] {transcript}")
                self.history.append(f"You: [STT] {transcript}")
                self.process_input(transcript)
            except Exception as e:
                self.append_message("Vivian", f"[STT Failed: {e}]")
        else:
            self.append_message("Vivian", "[Speech-to-Text not available (no API key)]")

    def text_to_speech(self):
        if self.last_response and self.config_brain.get("api_key"):
            try:
                audio_bytes = openai_text_to_speech(self.last_response, self.config_brain["api_key"])
                # Save and play audio (as a .mp3 or .wav file)
                tmp_audio = "vivian_tts_output.mp3"
                with open(tmp_audio, "wb") as f:
                    f.write(audio_bytes)
                try:
                    if os.name == 'nt':
                        os.startfile(tmp_audio)
                    else:
                        os.system(f"open '{tmp_audio}'" if sys.platform == "darwin" else f"xdg-open '{tmp_audio}'")
                except Exception:
                    self.append_message("Vivian", "[Could not auto-play audio, but file was saved]")
            except Exception as e:
                self.append_message("Vivian", f"[TTS Failed: {e}]")
        else:
            self.append_message("Vivian", f"[TTS] {self.last_response}")

    def toggle_contrast(self):
        self.high_contrast = not self.high_contrast
        bg = "#000000" if self.high_contrast else "#ffffff"
        fg = "#ffffff" if self.high_contrast else "#000000"
        self.text_area.configure(background=bg, foreground=fg)
        self.entry.configure(background=bg, foreground=fg)

    def save_draft(self, event=None):
        self.draft_message = self.entry_var.get()
        self.append_message("System", "[Draft saved]")

    def get_history(self):
        return self.history

    def load_history(self, text):
        lines = text.splitlines()
        for line in lines:
            if ": " in line:
                who, msg = line.split(": ", 1)
                self.append_message(who, msg)
        self.history = lines

    def search_history_btn(self):
        term = self.search_var.get()
        self.search_history(term)

    def search_history(self, term):
        found = [msg for msg in self.history if term.lower() in msg.lower()]
        if found:
            self.append_message("Search", f"Found {len(found)} result(s):")
            for line in found:
                self.append_message("-", line)
                self._highlight_in_chat(term)
        else:
            self.append_message("Search", "No results found.")

    def _highlight_in_chat(self, term):
        self.text_area.tag_remove("highlight", 1.0, tk.END)
        idx = 1.0
        while True:
            idx = self.text_area.search(term, idx, nocase=1, stopindex=tk.END)
            if not idx:
                break
            lastidx = f"{idx}+{len(term)}c"
            self.text_area.tag_add("highlight", idx, lastidx)
            self.text_area.tag_config("highlight", background="yellow")
            idx = lastidx

    def get_logs(self):
        return "\n".join(self.history)

    def set_font_scale(self, scale):
        self.font_scale = scale
        self.entry.configure(font=("Arial", int(12 * scale)))
        self.text_area.configure(font=("Arial", int(12 * scale)))
        self.avatar_img.configure(font=("Arial", int(28 * scale)))

    def set_context_window(self, val):
        self.context_window = val

    def set_high_contrast(self, val):
        self.high_contrast = val
        self.toggle_contrast()

    def set_status_var(self, var):
        self.status_var = var

    def get_last_response(self):
        return self.last_response

    def handle_file_drop(self, file):
        self.append_message("Dropped File", file)
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
            self.append_image(file)

    def update_avatar(self, avatar_path_or_emoji):
        if avatar_path_or_emoji and Image and ImageTk and os.path.exists(str(avatar_path_or_emoji)):
            try:
                img = Image.open(avatar_path_or_emoji)
                img.thumbnail((48, 48))
                img_tk = ImageTk.PhotoImage(img)
                self.avatar_img.configure(image=img_tk, text="")
                self.avatar_img.image = img_tk
            except Exception:
                self.avatar_img.configure(text="🙂", image="")
        elif avatar_path_or_emoji:
            self.avatar_img.configure(text=str(avatar_path_or_emoji), image="")
        else:
            self.avatar_img.configure(text="🙂", image="")

    def update_plugin_buttons(self):
        for widget in self.plugin_btns_frame.winfo_children():
            widget.destroy()
        for plugin in self.plugins:
            label = getattr(plugin, "button_label", None)
            if label and hasattr(plugin, "__call__"):
                btn = ttk.Button(self.plugin_btns_frame, text=label, command=lambda p=plugin: self._run_plugin_button(p))
                btn.pack(side="left", padx=2)

    def _run_plugin_button(self, plugin):
        try:
            result = plugin()
            avatar = getattr(plugin, "avatar", None)
            self.append_message("Vivian", result)
            if avatar:
                self.update_avatar(avatar)
        except Exception as e:
            self.append_message("Vivian", f"[Plugin Error] {e}")

    def set_persona(self, persona):
        self.persona = persona
        self.append_message("System", f"Persona set to {persona}")

    def open_command_palette(self):
        palette = tk.Toplevel(self)
        palette.title("Command Palette")
        cmds = ["Clear Chat", "Copy All", "Export", "Summarize"] + [getattr(p, "button_label", p.name) for p in self.plugins if hasattr(p, "button_label") or hasattr(p, "name")]
        tk.Label(palette, text="Type or select a command:").pack(pady=3)
        cmd_var = tk.StringVar()
        cmd_box = ttk.Combobox(palette, textvariable=cmd_var, values=cmds)
        cmd_box.pack(fill="x", padx=8, pady=4)
        cmd_box.focus_set()
        def run_cmd(event=None):
            cmd = cmd_var.get()
            if cmd == "Clear Chat":
                self.clear_chat()
            elif cmd == "Copy All":
                self.copy_all()
            elif cmd == "Export":
                self.export_conversation()
            elif cmd == "Summarize":
                self.summarize_conversation()
            else:
                for p in self.plugins:
                    if getattr(p, "button_label", None) == cmd or getattr(p, "name", None) == cmd:
                        self._run_plugin_button(p)
            palette.destroy()
        cmd_box.bind("<Return>", run_cmd)
        ttk.Button(palette, text="Run", command=run_cmd).pack(pady=(3,8))

    def export_conversation(self):
        filename = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt"),("Markdown","*.md"),("HTML","*.html"),("PDF","*.pdf"),("All Files","*.*")])
        if filename:
            ext = os.path.splitext(filename)[-1].lower()
            data = "\n".join(self.history)
            try:
                if ext == ".html":
                    data = "<html><body><pre>" + data + "</pre></body></html>"
                elif ext == ".md":
                    data = "\n".join(["* "+line for line in self.history])
                elif ext == ".pdf":
                    self.append_message("System", "[PDF export not implemented]")
                    return
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(data)
                self.append_message("System", f"[Exported to {filename}]")
            except Exception as e:
                self.append_message("System", f"[Export failed: {e}]")

    def summarize_conversation(self):
        if not self.history:
            self.append_message("Vivian", "[Nothing to summarize]")
            return
        # Use OpenAI brain to summarize
        try:
            summary = send_to_openai_brain(
                "Summarize this conversation:\n" + "\n".join(self.history),
                self.config_brain,
                explain=False,
            )
        except Exception as e:
            summary = f"[Summary Failed: {e}]"
        self.append_message("Vivian", f"Summary: {summary}")

    def bookmark_message(self):
        idx = len(self.history) - 1
        if idx >= 0:
            self.bookmarks.append(idx)
            self.append_message("System", f"[Bookmarked message {idx+1}]")

    def show_bookmarks(self):
        if not self.bookmarks:
            messagebox.showinfo("Bookmarks", "No bookmarks yet.")
            return
        bm_text = ""
        for idx in self.bookmarks:
            if idx < len(self.history):
                bm_text += f"{idx+1}: {self.history[idx]}\n"
        messagebox.showinfo("Bookmarks", bm_text or "No valid bookmarks.")

    def context_menu_popup(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Copy", command=self.copy_all)
        menu.add_command(label="Clear", command=self.clear_chat)
        menu.add_command(label="Bookmark", command=self.bookmark_message)
        menu.add_command(label="Export", command=self.export_conversation)
        menu.tk_popup(event.x_root, event.y_root)

    def start_new_session(self, persona="Default"):
        self.clear_chat()
        self.session_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.set_persona(persona)
        self.append_message("System", f"[Started new session with persona: {persona}]")