# vivian_gui.py – Ultra Vivian AI Desktop Assistant GUI (PyInstaller-ready, Accessible, Modern, Fully Responsive)

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, font
import threading
import sys
import os
import logging
import platform

try:
    from ttkthemes import ThemedTk
except ImportError:
    ThemedTk = None

try:
    import pystray
    from PIL import Image as PILImage
except ImportError:
    pystray = None
    PILImage = None

try:
    import tkinterdnd2 as tkdnd
except ImportError:
    tkdnd = None

from vivian_chatbox import VivianChatApp
from VivianCore.plugins_loader import load_plugins, reload_plugins

APP_ICON_PATH = os.path.join(os.path.dirname(__file__), "vivian.ico")
DEFAULT_THEME = "arc"
DARK_BG = "#232323"
DARK_FG = "#eeeeee"
LIGHT_BG = "#fdfdfd"
LIGHT_FG = "#1a1a1a"

def set_dpi_awareness():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

def apply_theme(root, theme=DEFAULT_THEME, high_contrast=False):
    if ThemedTk is not None and not isinstance(root, ThemedTk):
        themed_root = ThemedTk(theme=theme)
        themed_root.title(root.title())
        themed_root.geometry(root.geometry())
        themed_root.minsize(800, 500)
        root.destroy()
        root = themed_root
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    if high_contrast:
        root.tk_setPalette(background=DARK_BG, foreground=DARK_FG)
    return root

def show_about():
    messagebox.showinfo(
        "About Vivian AI",
        "Vivian AI Assistant\n\nSupreme self-evolving desktop agent with plugins, multimodal, accessibility, tray & more.\n\n(c) 2025 Greg Mishkin & Contributors"
    )

def show_help():
    help_text = (
        "Vivian AI Desktop GUI Help\n\n"
        "- Type messages and press Enter or Send to chat with Vivian.\n"
        "- Use Preferences for theme, font, context size & accessibility.\n"
        "- Plugin Manager lets you enable, disable, or reload plugins.\n"
        "- Export/Import conversations via the File menu.\n"
        "- Drag & drop files (text, images) onto chat (if supported).\n"
        "- Ctrl+Enter sends message. Ctrl+Plus/Minus scales font.\n"
        "- Use Search to find messages in chat.\n"
        "- Tray icon for quick access (if available).\n"
        "- Accessibility: font, contrast, dyslexic font, TTS, voice input.\n"
        "- Debug pane shows logs and plugin errors.\n"
        "- Avatar animates with Vivian's mood.\n"
        "- Multi-agent, calendar, home automation, federated knowledge & more.\n"
    )
    messagebox.showinfo("Help", help_text)

class PreferencesDialog(simpledialog.Dialog):
    def __init__(self, parent, app):
        self.app = app
        super().__init__(parent, "Vivian Preferences")

    def body(self, master):
        tk.Label(master, text="Context Window:").grid(row=0, column=0, sticky="w")
        self.ctx_entry = tk.Entry(master)
        self.ctx_entry.insert(0, str(getattr(self.app, "context_window", 5)))
        self.ctx_entry.grid(row=0, column=1, sticky="ew")
        tk.Label(master, text="Font Size:").grid(row=1, column=0, sticky="w")
        self.font_entry = tk.Entry(master)
        self.font_entry.insert(0, str(getattr(self.app, "font_size", 12)))
        self.font_entry.grid(row=1, column=1, sticky="ew")
        tk.Label(master, text="Theme:").grid(row=2, column=0, sticky="w")
        self.theme_var = tk.StringVar(value=getattr(self.app, "theme", DEFAULT_THEME))
        self.theme_entry = tk.Entry(master, textvariable=self.theme_var)
        self.theme_entry.grid(row=2, column=1, sticky="ew")
        tk.Label(master, text="High Contrast:").grid(row=3, column=0, sticky="w")
        self.hc_var = tk.BooleanVar(value=getattr(self.app, "high_contrast", False))
        self.hc_check = tk.Checkbutton(master, variable=self.hc_var)
        self.hc_check.grid(row=3, column=1, sticky="w")
        tk.Label(master, text="Dyslexic Font:").grid(row=4, column=0, sticky="w")
        self.dys_var = tk.BooleanVar(value=getattr(self.app, "dyslexic_font", False))
        self.dys_check = tk.Checkbutton(master, variable=self.dys_var)
        self.dys_check.grid(row=4, column=1, sticky="w")
        return self.ctx_entry

    def apply(self):
        try:
            ctx_val = int(self.ctx_entry.get())
            if hasattr(self.app, "set_context_window"):
                self.app.set_context_window(ctx_val)
        except Exception:
            pass
        try:
            font_val = int(self.font_entry.get())
            if hasattr(self.app, "set_font_scale"):
                self.app.set_font_scale(font_val / 12.0)
        except Exception:
            pass
        if hasattr(self.app, "set_high_contrast"):
            self.app.set_high_contrast(self.hc_var.get())
        if hasattr(self.app, "set_font_family"):
            self.app.set_font_family("OpenDyslexic" if self.dys_var.get() else "TkDefaultFont")
        if hasattr(self.app, "set_theme"):
            self.app.set_theme(self.theme_var.get())

class PluginManagerDialog(tk.Toplevel):
    def __init__(self, parent, plugins, main_app):
        super().__init__(parent)
        self.title("Plugin Manager")
        self.geometry("420x380")
        self.plugins = plugins
        self.main_app = main_app
        self.listbox = tk.Listbox(self)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=10)
        for p in plugins:
            self.listbox.insert(tk.END, getattr(p, "name", str(p)))
        btn_frm = tk.Frame(self)
        btn_frm.pack(fill="x")
        tk.Button(btn_frm, text="Reload Plugins", command=self.reload_plugins).pack(side="left", padx=5, pady=5)
        tk.Button(btn_frm, text="Enable Selected", command=self.enable_selected).pack(side="left", padx=5)
        tk.Button(btn_frm, text="Disable Selected", command=self.disable_selected).pack(side="left", padx=5)
        tk.Button(btn_frm, text="Close", command=self.destroy).pack(side="right", padx=5)

    def reload_plugins(self):
        base_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
        plugin_dir = os.path.join(base_dir, "VivianCore", "plugins")
        if not os.path.isdir(plugin_dir):
            os.makedirs(plugin_dir, exist_ok=True)
        new_plugins = reload_plugins(plugin_dir)
        self.main_app.plugins = new_plugins
        self.main_app.update_plugin_buttons()
        self.listbox.delete(0, tk.END)
        for p in new_plugins:
            self.listbox.insert(tk.END, getattr(p, "name", str(p)))
        messagebox.showinfo("Plugin Manager", f"Plugins reloaded from {plugin_dir}.")

    def enable_selected(self):
        idxs = self.listbox.curselection()
        for i in idxs:
            plugin = self.plugins[i]
            if hasattr(plugin, "enable"):
                plugin.enable()
        self.main_app.update_plugin_buttons()
        messagebox.showinfo("Plugin Manager", "Selected plugins enabled.")

    def disable_selected(self):
        idxs = self.listbox.curselection()
        for i in idxs:
            plugin = self.plugins[i]
            if hasattr(plugin, "disable"):
                plugin.disable()
        self.main_app.update_plugin_buttons()
        messagebox.showinfo("Plugin Manager", "Selected plugins disabled.")

class DebugPane(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.title("Vivian Debug/Log")
        self.geometry("700x350")
        self.text = tk.Text(self, font=("Consolas", 10))
        self.text.pack(fill="both", expand=True)
        logs = ""
        if hasattr(app, "get_logs"):
            logs = app.get_logs()
        self.text.insert("end", logs if logs else "No logs yet.")

def save_conversation(app):
    filename = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text Files", "*.txt"), ("Markdown Files", "*.md"), ("All Files", "*.*")]
    )
    if filename:
        try:
            history = app.get_history() if hasattr(app, "get_history") else []
            with open(filename, "w", encoding="utf-8") as f:
                for msg in history:
                    f.write(msg + "\n")
            messagebox.showinfo("Export", f"Conversation saved to {filename}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

def load_conversation(app):
    filename = filedialog.askopenfilename(
        filetypes=[("Text/Markdown Files", "*.txt *.md"), ("All Files", "*.*")]
    )
    if filename:
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = f.read()
            if hasattr(app, "load_history"):
                app.load_history(data)
            else:
                messagebox.showinfo("Import", "Loaded file, but app does not support loading history.")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

def search_history(app):
    q = simpledialog.askstring("Search History", "Enter search term:")
    if q and hasattr(app, "search_history"):
        app.search_history(q)

def set_dark_mode(root):
    root.tk_setPalette(background=DARK_BG, foreground=DARK_FG)
    for widget in root.winfo_children():
        try:
            widget.configure(background=DARK_BG, foreground=DARK_FG)
        except Exception:
            pass

def set_light_mode(root):
    root.tk_setPalette(background=LIGHT_BG, foreground=LIGHT_FG)
    for widget in root.winfo_children():
        try:
            widget.configure(background=LIGHT_BG, foreground=LIGHT_FG)
        except Exception:
            pass

def notify_system_tray(title, msg):
    if pystray and PILImage and os.path.exists(APP_ICON_PATH):
        def _show():
            icon = pystray.Icon("Vivian", PILImage.open(APP_ICON_PATH))
            icon.title = title
            icon.notify(msg)
            icon.stop()
        t = threading.Thread(target=_show)
        t.start()

def minimize_to_tray(root, app):
    if not pystray or not PILImage or not os.path.exists(APP_ICON_PATH):
        root.iconify()
        return

    def on_show(icon, item):
        icon.stop()
        root.after(0, root.deiconify)
    def on_exit(icon, item):
        icon.stop()
        root.after(0, root.quit)

    icon = pystray.Icon(
        "Vivian",
        PILImage.open(APP_ICON_PATH),
        "Vivian AI",
        menu=pystray.Menu(
            pystray.MenuItem("Show Vivian", on_show),
            pystray.MenuItem("Exit", on_exit)
        )
    )
    root.withdraw()
    threading.Thread(target=icon.run, daemon=True).start()

def drag_and_drop_support(app, root):
    if not tkdnd:
        return
    dnd = tkdnd.TkinterDnD.Tk()
    def on_drop(event):
        files = root.tk.splitlist(event.data)
        for file in files:
            if hasattr(app, "handle_file_drop"):
                app.handle_file_drop(file)
    dnd.drop_target_register(tkdnd.DND_FILES)
    dnd.dnd_bind('<<Drop>>', on_drop)

def toggle_theme(root, app):
    if getattr(app, "high_contrast", False):
        set_light_mode(root)
        app.high_contrast = False
    else:
        set_dark_mode(root)
        app.high_contrast = True

def show_avatar(app):
    if hasattr(app, "show_avatar"):
        app.show_avatar()

def run_accessibility_settings(app):
    # Placeholder for future accessibility dialog
    messagebox.showinfo("Accessibility", "Accessibility settings dialog not yet implemented.")

def main():
    set_dpi_awareness()
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    root.title("Vivian AI Assistant")
    root.geometry("1100x700")
    root.minsize(900, 600)
    if os.path.exists(APP_ICON_PATH):
        try:
            root.iconbitmap(default=APP_ICON_PATH)
        except Exception:
            pass

    root = apply_theme(root, theme=DEFAULT_THEME)

    base_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    plugin_dir = os.path.join(base_dir, "VivianCore", "plugins")
    if not os.path.isdir(plugin_dir):
        os.makedirs(plugin_dir, exist_ok=True)
    plugins = load_plugins(plugin_dir)

    app = VivianChatApp(root, plugins)
    app.pack(fill="both", expand=True)

    menubar = tk.Menu(root)
    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(label="Export Conversation...", command=lambda: save_conversation(app))
    file_menu.add_command(label="Import Conversation...", command=lambda: load_conversation(app))
    file_menu.add_separator()
    file_menu.add_command(label="Backup Now", command=lambda: notify_system_tray("Vivian", "Backup started. (Not implemented)"))
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=root.quit)
    menubar.add_cascade(label="File", menu=file_menu)

    plugin_menu = tk.Menu(menubar, tearoff=0)
    plugin_menu.add_command(label="Manage Plugins...", command=lambda: PluginManagerDialog(root, plugins, app))
    menubar.add_cascade(label="Plugins", menu=plugin_menu)

    tools_menu = tk.Menu(menubar, tearoff=0)
    tools_menu.add_command(label="Preferences", command=lambda: PreferencesDialog(root, app))
    tools_menu.add_command(label="Search Chat History...", command=lambda: search_history(app))
    tools_menu.add_command(label="Toggle Theme (Dark/Light)", command=lambda: toggle_theme(root, app))
    tools_menu.add_command(label="Accessibility...", command=lambda: run_accessibility_settings(app))
    tools_menu.add_command(label="Open Debug Pane", command=lambda: DebugPane(root, app))
    tools_menu.add_separator()
    tools_menu.add_command(label="Speech to Text", command=lambda: messagebox.showinfo("Speech-to-Text", "Speech-to-Text not implemented."))
    tools_menu.add_command(label="Read Vivian's Response", command=lambda: messagebox.showinfo("Text-to-Speech", getattr(app, "get_last_response", lambda: "")()))
    tools_menu.add_command(label="Show Avatar", command=lambda: show_avatar(app))
    menubar.add_cascade(label="Tools", menu=tools_menu)

    help_menu = tk.Menu(menubar, tearoff=0)
    help_menu.add_command(label="Help", command=show_help)
    help_menu.add_command(label="About Vivian...", command=show_about)
    menubar.add_cascade(label="Help", menu=help_menu)

    root.config(menu=menubar)

    # Status bar
    status = tk.StringVar()
    status.set("Ready.")
    status_bar = ttk.Label(root, textvariable=status, relief="sunken", anchor="w")
    status_bar.pack(side="bottom", fill="x")
    if hasattr(app, "set_status_var"):
        app.set_status_var(status)

    # Keyboard shortcuts
    def send_on_ctrl_enter(event):
        if hasattr(app, "send_message"):
            app.send_message()
    root.bind('<Control-Return>', send_on_ctrl_enter)
    root.bind('<Control-plus>', lambda e: app.set_font_scale(1.1) if hasattr(app, "set_font_scale") else None)
    root.bind('<Control-minus>', lambda e: app.set_font_scale(0.9) if hasattr(app, "set_font_scale") else None)
    root.bind("<F1>", lambda e: show_help())
    root.bind("<F2>", lambda e: run_accessibility_settings(app))

    # System tray support (optional)
    def on_minimize(event):
        if root.state() == "iconic":
            minimize_to_tray(root, app)
    root.bind("<Unmap>", on_minimize)

    # Drag and drop support (if tkdnd is available)
    drag_and_drop_support(app, root)

    # Accessibility: font scaling, high-contrast, dyslexic font, screen reader
    # Avatar/animation/multimodal handled in VivianChatApp

    # Show a welcome message or tip
    def show_tip():
        tips = [
            "Tip: Press Ctrl+Enter to send a message.",
            "Tip: Use the Plugin Manager for more skills.",
            "Tip: Toggle themes for better readability.",
            "Tip: Use Accessibility menu for better experience.",
            "Tip: Right-click tray icon for quick actions.",
        ]
        messagebox.showinfo("Vivian Pro Tip", tips[threading.current_thread().ident % len(tips)])
    root.after(3000, show_tip)

    root.mainloop()

if __name__ == "__main__":
    main()