import sys
import threading
import signal
import logging
import time
import re
import os
import json
from collections import OrderedDict

from config import load_config
from memory import MemoryManager
from plugins import run_plugin, available_plugins, reload_plugins
from utils import *
from gui import run_gui, gui_supported
from web.server import run_server, server_supported

from input_handler import handle_user_input

# Advanced core modules
from engine.auto_upgrader import AutoUpgrader
from engine.task_listener import TaskListener
from engine.self_trigger import SelfTrigger
from engine.remote_dropper import RemoteDropper

from user_manager import UserManager
from event_bus import EventBus
from voice import VoiceIO
from model import send_to_model

# AGENT DESCRIPTIONS/LOGS/ENDPOINTS as before...
AGENT_DESCRIPTIONS = {
    "upgrader": "AutoUpgrader: Handles system upgrades (code, config, skills).",
    "task_listener": "TaskListener: Real-time task/event queue and router.",
    "self_trigger": "SelfTrigger: Agentic Vivian self-evolution engine.",
    "dropper": "RemoteDropper: Handles remote code/data drops and fetches.",
}
AGENT_ENDPOINTS = {
    "upgrader": "http://localhost:7796/api/autoupgrader/health",
    "task_listener": "http://localhost:7797/api/tasklistener/health",
    "self_trigger": "http://localhost:7798/api/selftrigger/health",
    "dropper": "http://localhost:7799/api/remotedropper/health",
}
AGENT_LOG_PATHS = {
    "upgrader": "auto_upgrader_audit.jsonl",
    "task_listener": "task_listener_audit.jsonl",
    "self_trigger": "self_trigger_audit.jsonl",
    "dropper": "remote_dropper_audit.jsonl",
}

# --- RBAC/Session via UserManager (no more USER_ROLES dict) ---
user_manager = None  # will be initialized in main()

def current_user():
    # For now, try to get from env; in future, use session
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

# Cluster/HA/Distributed (unchanged for now)
CLUSTER_NODES = ["localhost"]
LEADER_NODE = "localhost"
def is_leader():
    return LEADER_NODE == "localhost"

# --- Notification queue (with event bus integration) ---
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

# --- Agent/Plugin/Agent Control (unchanged except event bus hooks) ---
@require_admin
def agent_restart(name, agents, config, memory, event_bus=None):
    stop_agents({name: agents.get(name)})
    time.sleep(0.5)
    if name == "upgrader":
        agents[name] = AutoUpgrader()
        agents[name].start_rest_api()
    elif name == "task_listener":
        agents[name] = TaskListener()
        agents[name].start()
        agents[name].start_rest_api()
    elif name == "self_trigger":
        agents[name] = SelfTrigger()
        agents[name].start()
        agents[name].start_rest_api()
    elif name == "dropper":
        agents[name] = RemoteDropper()
        agents[name].start()
        agents[name].start_rest_api()
    else:
        return f"Restart not supported for {name}."
    if event_bus:
        event_bus.publish("agent_restarted", {"agent": name, "user": current_user()})
    return f"Restarted {name}."

def start_agents(config, memory, event_bus=None):
    agents = OrderedDict()
    def alert_cb(event, data):
        add_notification({"agent_alert": event, "data": data})
        print(f"[ALERT][Vivian] {event}: {data}")
        if event_bus:
            event_bus.publish("agent_alert", {"event": event, "data": data})
    def metrics_cb(metric, value):
        print(f"[METRICS][Vivian] {metric}: {value}")
        if event_bus:
            event_bus.publish("agent_metric", {"metric": metric, "value": value})
    upgrader = AutoUpgrader(
        alert_cb=alert_cb,
        metrics_cb=metrics_cb,
        approval_cb=lambda zip_path: config.get("auto_upgrade", True),
        health_check_cb=lambda: True,
    )
    upgrader.start_rest_api()
    agents["upgrader"] = upgrader

    task_listener = TaskListener(
        alert_cb=alert_cb,
        metrics_cb=metrics_cb,
    )
    task_listener.start()
    task_listener.start_rest_api()
    agents["task_listener"] = task_listener

    self_trigger = SelfTrigger(
        metrics_cb=metrics_cb,
        alert_cb=alert_cb,
    )
    self_trigger.start()
    self_trigger.start_rest_api()
    agents["self_trigger"] = self_trigger

    dropper = RemoteDropper()
    dropper.start()
    dropper.start_rest_api()
    agents["dropper"] = dropper
    return agents

def stop_agents(agents):
    for agent in ["task_listener", "self_trigger", "dropper"]:
        if agent in agents and hasattr(agents[agent], "stop"):
            agents[agent].stop()

def agent_status_table(agents):
    import requests
    table = []
    header = f"{'Agent':<16} {'Status':<10} {'Health':<8} {'Endpoint':<40} {'Threads':<8} {'Node':<10}"
    table.append(header)
    table.append("-" * len(header))
    for name, agent in agents.items():
        endpoint = AGENT_ENDPOINTS.get(name, "")
        try:
            resp = requests.get(endpoint, timeout=2)
            health = resp.json().get("status", "ERR")
        except Exception:
            health = "ERR"
        running = getattr(agent, "running", True) or getattr(agent, "_running", True)
        threads = getattr(agent, "_thread", None)
        threads = 1 if threads else "?"
        status = "RUNNING" if running else "STOPPED"
        node = "leader" if is_leader() else "follower"
        suggestion = ""
        if health != "OK":
            suggestion = f" [Suggestion: try /agent restart {name}]"
        table.append(f"{name:<16} {status:<10} {health:<8} {endpoint:<40} {threads:<8} {node:<10}{suggestion}")
    return "\n".join(table)

def agent_describe(name, agents):
    if name not in agents:
        return "No such agent."
    desc = AGENT_DESCRIPTIONS.get(name, "No description.")
    agent = agents[name]
    doc = getattr(agent, "__doc__", "").strip().split("\n")[0]
    extra = getattr(agent, "health_status", lambda: {})()
    return f"{name}: {desc}\nDoc: {doc}\nHealth: {extra}"

def agent_logs(name, n=10):
    path = AGENT_LOG_PATHS.get(name, "")
    if not os.path.exists(path):
        return f"No logs for {name}"
    with open(path) as f:
        lines = f.readlines()[-n:]
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except Exception:
            continue
    return "\n".join([str(x) for x in out])

def agent_reload(name, agents):
    agent = agents.get(name)
    if not agent or not hasattr(agent, "reload"):
        return f"Hot-reload not supported for {name}."
    try:
        agent.reload()
        add_notification({"agent_reload": name})
        return f"Reloaded {name}."
    except Exception as e:
        return f"Failed to reload {name}: {e}"

def agent_control_command(cmd, agents, config, memory, event_bus=None):
    if cmd == "/agents":
        print(agent_status_table(agents))
        return
    match = re.match(r"/agent\s+(\w+)(?:\s+(\w+))?", cmd)
    if not match:
        print("Usage: /agent [start|stop|restart|describe|logs|reload] [name]")
        return
    action, name = match.groups()
    if not name or name not in agents:
        print("Available agents:", ", ".join(agents.keys()))
        return
    if action == "describe":
        print(agent_describe(name, agents))
    elif action == "logs":
        print(agent_logs(name))
    elif action == "reload":
        print(agent_reload(name, agents))
    elif action == "restart":
        print(agent_restart(name, agents, config, memory, event_bus))
    elif action == "stop":
        if hasattr(agents[name], "stop"):
            agents[name].stop()
            print(f"Stopped {name}")
            add_notification({"agent_stop": name})
            if event_bus:
                event_bus.publish("agent_stopped", {"agent": name, "user": current_user()})
        else:
            print(f"Stop not supported for {name}")
    elif action == "start":
        if hasattr(agents[name], "start"):
            agents[name].start()
            print(f"Started {name}")
            add_notification({"agent_start": name})
            if event_bus:
                event_bus.publish("agent_started", {"agent": name, "user": current_user()})
        else:
            print(f"Start not supported for {name}")
    else:
        print("Unknown agent action.")

def interpret_natural_agent_command(user_input, agents, config, memory, event_bus=None):
    tokens = user_input.lower().split()
    for name in agents:
        if name in user_input.lower():
            if "restart" in tokens:
                print(agent_restart(name, agents, config, memory, event_bus))
                return True
            elif "stop" in tokens:
                if hasattr(agents[name], "stop"):
                    agents[name].stop()
                    print(f"Stopped {name}")
                    add_notification({"agent_stop": name})
                    if event_bus:
                        event_bus.publish("agent_stopped", {"agent": name, "user": current_user()})
                    return True
            elif "start" in tokens:
                if hasattr(agents[name], "start"):
                    agents[name].start()
                    print(f"Started {name}")
                    add_notification({"agent_start": name})
                    if event_bus:
                        event_bus.publish("agent_started", {"agent": name, "user": current_user()})
                    return True
            elif "describe" in tokens or "info" in tokens:
                print(agent_describe(name, agents))
                return True
            elif "logs" in tokens:
                print(agent_logs(name))
                return True
            elif "reload" in tokens:
                print(agent_reload(name, agents))
                return True
            elif "health" in tokens or "status" in tokens:
                print(agent_status_table(agents))
                return True
    if "agent" in tokens and ("status" in tokens or "health" in tokens):
        print(agent_status_table(agents))
        return True
    return False

def prometheus_metrics_server(port=9300):
    from flask import Flask, Response
    app = Flask("VivianPrometheus")
    @app.route("/metrics")
    def metrics():
        lines = [
            'vivian_agent_status{agent="upgrader"} 1',
            'vivian_agent_status{agent="task_listener"} 1',
            'vivian_agent_status{agent="self_trigger"} 1',
            'vivian_agent_status{agent="dropper"} 1',
            f'vivian_agent_uptime_seconds {int(time.time()) % 10000}'
        ]
        return Response("\n".join(lines), mimetype="text/plain")
    threading.Thread(target=app.run, kwargs={"port": port, "host": "0.0.0.0"}, daemon=True).start()

def websocket_server(port=9310):
    try:
        import asyncio
        import websockets
        async def handler(websocket, path):
            websocket_clients.add(websocket)
            try:
                while True:
                    await asyncio.sleep(10)
            finally:
                websocket_clients.remove(websocket)
        loop = asyncio.get_event_loop()
        ws_server = websockets.serve(handler, "0.0.0.0", port)
        loop.create_task(ws_server)
        threading.Thread(target=loop.run_forever, daemon=True).start()
    except ImportError:
        print("websockets module not installed, skipping websocket server.")

def print_agent_audit_logs():
    print("---- Agent Audit Logs ----")
    for name, path in AGENT_LOG_PATHS.items():
        print(f"== {name} ==")
        print(agent_logs(name, n=5))

def web_dashboard(agents, port=7800):
    try:
        from flask import Flask, render_template_string, request, jsonify
    except ImportError:
        print("Flask not installed: web dashboard unavailable.")
        return
    # unchanged dashboard code...

def cli_tab_completion(agents):
    try:
        import readline
        AGENT_NAMES = list(agents.keys())
        COMMANDS = [
            "/agents", "/agent start", "/agent stop", "/agent restart", "/agent reload",
            "/agent logs", "/agent describe"
        ]
        def completer(text, state):
            options = [c for c in COMMANDS + [f"/agent {a}" for a in AGENT_NAMES] if c.startswith(text)]
            if state < len(options):
                return options[state]
            return None
        readline.parse_and_bind("tab: complete")
        readline.set_completer(completer)
    except ImportError:
        pass

def main():
    global user_manager
    logging.basicConfig(level=logging.INFO)
    config = load_config()

    # 1. --- Initialize EventBus ---
    event_bus = EventBus(persistent_log="logs/event_log.jsonl", enable_async_loop=True)
    logging.info("[Vivian] EventBus initialized.")

    # 2. --- Initialize UserManager (with event bus) ---
    user_manager = UserManager(config, event_bus=event_bus)
    logging.info("[Vivian] UserManager initialized.")

    # 3. --- Initialize MemoryManager (with event bus, user_manager injection) ---
    memory = MemoryManager(config, event_bus=event_bus, user_manager=user_manager)
    logging.info("[Vivian] MemoryManager initialized.")

    # 4. --- Initialize Plugins (with event bus, memory, user_manager) ---
    reload_plugins("plugins", event_bus=event_bus, memory_manager=memory, user_manager=user_manager)
    logging.info("[Vivian] Plugins loaded and event bus integrated.")

    # 5. --- Initialize voice (if enabled) ---
    voice = VoiceIO(config) if config.get("voice_enabled", False) else None

    print_logo(version=config.get("version"))
    print(f"\n[{config['name']}] is online. {config['greeting']}\nType '/help' for commands.\n")

    # 6. --- Initialize VivianBrain (if present, pass all resources) ---
    vivian = None
    try:
        from engine.vivian_brain import VivianBrain
        vivian = VivianBrain(
            config=config,
            memory=memory,
            users=user_manager,
            plugins=available_plugins(),
            eventbus=event_bus
        )
    except ImportError:
        print("[Vivian] Brain module not found. Running without AI core.")

    # 7. --- Start agents (with event bus) ---
    agents = start_agents(config, memory, event_bus=event_bus)
    prometheus_metrics_server()
    websocket_server()
    web_dashboard(agents)
    cli_tab_completion(agents)

    # --- Graceful shutdown hook for all subsystems ---
    def handle_exit(signum, frame):
        print(f"\n{config['name']}: Shutting down agents, draining events, and exiting.")
        stop_agents(agents)
        if event_bus:
            event_bus.drain()
            event_bus.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # --- Optional: voice input loop ---
    if voice and getattr(voice, "listen_enabled", False):
        start_voice_input(memory, config, voice, vivian)

    # --- Main CLI loop ---
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            handle_exit(None, None)

        # RBAC/admin CLI (now using user_manager)
        if user_input.startswith("/agents") or user_input.startswith("/agent"):
            agent_control_command(user_input, agents, config, memory, event_bus=event_bus)
            continue
        if interpret_natural_agent_command(user_input, agents, config, memory, event_bus=event_bus):
            continue
        if user_input.strip().startswith("/audit agents"):
            print_agent_audit_logs()
            continue
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
        if user_input.startswith("/ashell"):
            print("Vivian Agent Shell. Type /exit to exit.")
            while True:
                cmd = input("AgentShell> ").strip()
                if cmd == "/exit":
                    break
                agent_control_command(cmd, agents, config, memory, event_bus=event_bus)
            continue

        # --- User/session/admin commands ---
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
        if user_input.startswith("/audit user "):
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

        # --- Normal input dispatch ---
        handle_user_input(user_input, memory, config, voice, vivian)

if __name__ == "__main__":
    main()