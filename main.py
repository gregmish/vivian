import sys
import os
import threading
import signal
import logging
import time
import json

# === Ensure All Core Directories Exist ===
REQUIRED_DIRS = ["logs", "backups", "plugins", "memory", "knowledge", "upgrades"]
for d in REQUIRED_DIRS:
    os.makedirs(d, exist_ok=True)

# === Defensive Imports (with feedback and module fallback) ===
def safe_import(module_name, alias=None):
    try:
        module = __import__(module_name, fromlist=[''])
        return module
    except ImportError as e:
        print(f"[Vivian] CRITICAL: Missing required module: {module_name} ({e})")
        return None

# --- Core Config/State ---
from config import load_config
from memory import SuperMemoryManager
from user_manager import UserManager
from event_bus import EventBus
from voice import VoiceIO
from model import send_to_model
from input_handler import handle_user_input
from utils import *

# --- Plugins ---
from VivianCore.llm.super_plugin_manager import SuperPluginManager
from plugins import run_plugin, available_plugins, reload_plugins

# --- Agents & Engine ---
from engine.auto_upgrader import AutoUpgrader
from engine.task_listener import TaskListener
from engine.self_trigger import SelfTrigger
from engine.remote_dropper import RemoteDropper
from engine.vivian_brain import VivianBrain

from vivian_upgrader_pro import VivianUpgraderPro

# --- Ultra/Quantum AGI Modules ---
from VivianCore.llm.llm_persona import PersonaEngine
from VivianCore.llm.llm_memory import LLM_Memory
from VivianCore.llm.vivian_thought_loop import VivianThoughtLoop
from VivianCore.llm.self_trainer import SelfTrainer

# --- Web/GUI/Server ---
gui_mod = safe_import("gui")
run_gui = getattr(gui_mod, "run_gui", None) if gui_mod else None
gui_supported = getattr(gui_mod, "gui_supported", False) if gui_mod else False

web_server_mod = safe_import("web.server")
run_server = getattr(web_server_mod, "run_server", None) if web_server_mod else None
server_supported = getattr(web_server_mod, "server_supported", False) if web_server_mod else False

# --- GPT Client Integration ---
from gpt_client import (
    query_gpt, query_gpt_json, query_gpt_tool, query_gpt_async,
    get_supported_models, gpt_healthcheck, save_conversation, load_conversation,
    summarize_gpt_history, export_gpt_history, import_gpt_history, clear_gpt_history,
    get_conversation, redact_sensitive
)

# --- Global User Manager reference for RBAC ---
user_manager = None

def current_user():
    return os.environ.get("USER", "gregmish")

def require_admin(func):
    def wrapper(*args, **kwargs):
        global user_manager
        user = current_user()
        if not user_manager or not user_manager.has_permission(user, "admin"):
            print("Permission denied: admin access required.")
            return
        return func(*args, **kwargs)
    return wrapper

# --- Notifications ---
websocket_clients = set()
NOTIFICATIONS = []

def add_notification(note):
    NOTIFICATIONS.append(note)
    notify_all_ws({"type": "notification", "data": note})

def notify_all_ws(message):
    for ws in websocket_clients:
        try:
            ws.send(json.dumps(message))
        except Exception:
            pass

# --- Agent Management ---
from agent_utils import (
    AGENT_DESCRIPTIONS, AGENT_ENDPOINTS, AGENT_LOG_PATHS,
    start_agents, stop_agents, agent_restart, agent_status_table,
    agent_describe, agent_logs, agent_reload, agent_control_command,
    interpret_natural_agent_command, print_agent_audit_logs,
    prometheus_metrics_server, websocket_server, web_dashboard, cli_tab_completion
)

# === Vivian Self-Test & Health Command ===
def vivian_selftest():
    print("[Vivian] Running self-test...")
    checks = {
        "Config loaded": os.path.exists("config/config.json"),
        "Memory dir": os.path.isdir("memory"),
        "Plugins dir": os.path.isdir("plugins"),
        "Logs dir": os.path.isdir("logs"),
        "LLM bridge": safe_import("gpt_client") is not None,
        "User manager": os.path.exists("user_manager.py"),
        "Event bus": os.path.exists("event_bus.py"),
        "Plugin manager": os.path.exists("VivianCore/llm/super_plugin_manager.py"),
    }
    for k, v in checks.items():
        print(f"  {k}: {'OK' if v else 'MISSING'}")
    if not all(checks.values()):
        print("[Vivian] Self-test failed! Fix missing systems before continuing.")
    else:
        print("[Vivian] All systems go.")

def startup_banner(config):
    print("-"*60)
    print(f"██╗   ██╗██╗██╗   ██╗██╗ █████╗ ███╗   ██╗")
    print(f"██║   ██║██║██║   ██║██║██╔══██╗████╗  ██║")
    print(f"██║   ██║██║██║   ██║██║███████║██╔██╗ ██║")
    print(f"╚██╗ ██╔╝██║██║   ██║██║██╔══██║██║╚██╗██║")
    print(f" ╚████╔╝ ██║╚██████╔╝██║██║  ██║██║ ╚████║")
    print(f"  ╚═══╝  ╚═╝ ╚═════╝ ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝")
    print(f":: {config.get('name', 'Vivian')} v{config.get('version', 'DEV')} :: {config.get('greeting', '')}")
    print("-"*60)

def main():
    global user_manager
    logging.basicConfig(level=logging.INFO)
    config = load_config()

    # Run Vivian self-test
    vivian_selftest()

    # Print startup banner
    startup_banner(config)

    # --- 1. Initialize EventBus ---
    event_bus = EventBus(persistent_log="logs/event_log.jsonl", enable_async_loop=True)
    logging.info("[Vivian] EventBus initialized.")

    # --- 2. Initialize UserManager (with event bus) ---
    user_manager = UserManager(config, event_bus=event_bus)
    logging.info("[Vivian] UserManager initialized.")

    # --- 3. Initialize MemoryManager (with event bus, user_manager injection) ---
    memory = SuperMemoryManager(config={
        **config,
        "event_bus": event_bus,
        "user_manager": user_manager
    })
    logging.info("[Vivian] SuperMemoryManager initialized.")

    # --- 4. Initialize PluginManager and Plugins ---
    plugin_manager = SuperPluginManager()
    reload_plugins("plugins", event_bus=event_bus, memory_manager=memory, user_manager=user_manager,
                  plugin_manager=plugin_manager)
    logging.info("[Vivian] Plugins loaded and event bus integrated.")

    # --- 5. Initialize Upgrader (VivianUpgraderPro) ---
    upgrader = VivianUpgraderPro(
        upgrade_dir="upgrades",
        log_file="logs/upgrade_log.txt",
        backup_dir="backups",
        webhook_url=config.get("upgrade_webhook")
    )

    # --- 6. Optional: Voice Support ---
    voice = VoiceIO(config) if config.get("voice_enabled", False) else None

    # --- 7. Initialize VivianBrain and AGI Modules ---
    vivian = None
    persona_engine = None
    llm_memory = None
    thought_loop = None
    self_trainer = None
    try:
        persona_engine = PersonaEngine(config)
        llm_memory = LLM_Memory(memory_dir="memory/vivian_llm", tags_enabled=True)
        vivian = VivianBrain(
            config=config,
            memory=memory,
            users=user_manager,
            skills=available_plugins(),
            eventbus=event_bus,
            plugin_manager=plugin_manager,
            persona=persona_engine,
            llm_memory=llm_memory,
            gpt_client=query_gpt
        )
        thought_loop = VivianThoughtLoop(config)
        self_trainer = SelfTrainer(llm_memory)
        thought_loop.start()
        self_trainer.run(interval=60)
    except Exception as e:
        print(f"[Vivian] Brain or AGI modules failed to load: {e}. Running without advanced AGI core.")

    # --- 8. Start agents and servers ---
    agents = start_agents(config, memory, event_bus=event_bus)
    prometheus_metrics_server()
    websocket_server()
    web_dashboard(agents)
    cli_tab_completion(agents)

    # --- 9. Graceful shutdown hook ---
    def handle_exit(signum, frame):
        print(f"\n{config['name']}: Shutting down agents, draining events, and exiting.")
        stop_agents(agents)
        if thought_loop and getattr(thought_loop, "active", False):
            thought_loop.stop()
        if self_trainer and getattr(self_trainer, "running", False):
            self_trainer.stop()
        if event_bus:
            if hasattr(event_bus, "drain"):
                event_bus.drain()
            if hasattr(event_bus, "shutdown"):
                event_bus.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # --- 10. Optional: GUI/Web Server Mode ---
    if "--gui" in sys.argv and run_gui:
        run_gui(config, vivian)
        return
    if "--web" in sys.argv and run_server:
        run_server(config, vivian)
        return

    # --- 11. Optional: voice input loop ---
    if voice and getattr(voice, "listen_enabled", False):
        try:
            from voice import start_voice_input
            start_voice_input(memory, config, voice, vivian)
        except ImportError:
            print("[Vivian] start_voice_input not found in voice module.")

    # --- 12. Main CLI loop ---
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            handle_exit(None, None)

        # --- Health check ---
        if user_input.strip() == "/health":
            vivian_selftest()
            continue

        # --- GPT Client commands ---
        if user_input.startswith("/gpt "):
            gpt_prompt = user_input[5:].strip()
            print("Vivian (GPT):", query_gpt(gpt_prompt))
            continue
        if user_input.startswith("/gpt_json "):
            gpt_prompt = user_input[10:].strip()
            print("Vivian (GPT JSON):", query_gpt_json(gpt_prompt))
            continue
        if user_input.startswith("/gpt_tool "):
            try:
                parts = user_input.split(" ", 2)
                if len(parts) >= 3:
                    tool_json = json.loads(parts[1])
                    gpt_prompt = parts[2]
                    print("Vivian (GPT Tool):", query_gpt_tool(gpt_prompt, tools=tool_json))
                    continue
            except Exception as e:
                print("Invalid /gpt_tool usage or JSON:", e)
                continue
        if user_input.strip() == "/gpt_models":
            print("Vivian (GPT Models):", get_supported_models())
            continue
        if user_input.strip() == "/gpt_health":
            print("Vivian (GPT Health):", gpt_healthcheck())
            continue
        if user_input.startswith("/gpt_saveconv "):
            fname = user_input.split(" ", 1)[1]
            save_conversation(GPT_CONVERSATIONS.get("default", []), fname)
            print(f"Conversation saved to {fname}")
            continue
        if user_input.startswith("/gpt_loadconv "):
            fname = user_input.split(" ", 1)[1]
            conv = load_conversation(fname)
            print(f"Loaded conversation from {fname}:\n", conv)
            continue
        if user_input == "/gpt_history":
            print(summarize_gpt_history())
            continue
        if user_input.startswith("/gpt_export "):
            fname = user_input.split(" ", 1)[1]
            export_gpt_history(fname)
            print(f"Exported GPT history to {fname}")
            continue
        if user_input.startswith("/gpt_import "):
            fname = user_input.split(" ", 1)[1]
            import_gpt_history(fname)
            print(f"Imported GPT history from {fname}")
            continue
        if user_input == "/gpt_clear":
            clear_gpt_history()
            print("Cleared GPT history.")
            continue
        if user_input.startswith("/gpt_conv "):
            conv_id = user_input.split(" ", 1)[1]
            print(get_conversation(conv_id))
            continue

        # --- Agents ---
        if user_input.startswith("/agents") or user_input.startswith("/agent"):
            agent_control_command(user_input, agents, config, memory, event_bus=event_bus)
            continue
        if interpret_natural_agent_command(user_input, agents, config, memory, event_bus=event_bus):
            continue
        if user_input.strip().startswith("/audit agents"):
            print_agent_audit_logs()
            continue

        # --- Config/Notifications ---
        if user_input.strip() == "/reloadconfig":
            new_config = load_config()
            config.update(new_config)
            print("[Vivian] Config hot-reloaded.")
            add_notification({"config_reload": True})
            event_bus.publish("config_reloaded", {"user": current_user()})
            continue
        if user_input.strip() == "/noti":
            print("\n".join([str(n) for n in NOTIFICATIONS[-10:]]))
            continue

        # --- Agent Shell ---
        if user_input.startswith("/ashell"):
            print("Vivian Agent Shell. Type /exit to exit.")
            while True:
                cmd = input("AgentShell> ").strip()
                if cmd == "/exit":
                    break
                agent_control_command(cmd, agents, config, memory, event_bus=event_bus)
            continue

        # --- User/Session/GDPR ---
        if user_input.startswith("/users"):
            print("\n".join(user_manager.list_users()))
            continue
        if user_input.startswith("/user "):
            parts = user_input.split()
            if len(parts) == 2:
                print(user_manager.get_profile(parts[1]))
            continue
        if user_input.startswith("/sessions"):
            print(user_manager.list_active_sessions())
            continue
        if user_input.strip().startswith("/audit user "):
            uname = user_input.split(" ", 2)[-1]
            print(json.dumps(user_manager.get_user_audit_trail(uname), indent=2))
            continue
        if user_input.strip().startswith("/gdpr_export "):
            uname = user_input.split(" ", 1)[1]
            print(json.dumps(user_manager.gdpr_export_user(uname), indent=2))
            continue
        if user_input.strip().startswith("/gdpr_delete "):
            uname = user_input.split(" ", 1)[1]
            print("Deleted:", user_manager.gdpr_delete_user(uname))
            continue

        # --- AGI/Quantum commands ---
        if user_input.strip() == "/agi_explain" and vivian:
            print(vivian.explain())
            continue
        if user_input.strip() == "/persona" and persona_engine:
            print(persona_engine.explain())
            continue
        if user_input.strip() == "/thoughtloop" and thought_loop:
            print(thought_loop.explain())
            continue
        if user_input.strip() == "/selftrainer" and self_trainer:
            print(self_trainer.explain())
            continue
        if user_input.strip() == "/agi_shell" and vivian:
            print("Vivian AGI Shell. Type 'exit' to exit.")
            vivian.run_shell()
            continue
        if user_input.strip() == "/thought_shell" and thought_loop:
            print("Vivian ThoughtLoop Shell. Type 'exit' to exit.")
            thought_loop.run_shell()
            continue
        if user_input.strip() == "/persona_shell" and persona_engine:
            print("Vivian PersonaEngine Shell. Type 'exit' to exit.")
            persona_engine.run_shell()
            continue
        if user_input.strip() == "/selftrainer_shell" and self_trainer:
            print("Vivian SelfTrainer Shell. Type 'exit' to exit.")
            self_trainer.run_shell()
            continue

        # --- Main handler ---
        handle_user_input(user_input, memory, config, voice, vivian)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)