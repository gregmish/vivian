import logging
from flask import Flask, request, jsonify, send_file
from threading import Thread
from flask_cors import CORS
import os
import datetime
from typing import Optional, Callable, Dict, Any

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins

# Global references to system components, set by run_server()
memory: Optional[Any] = None
config: Dict[str, Any] = {}
command_handler: Optional[Callable[[str, Any, Dict[str, Any]], str]] = None
event_bus: Optional[Any] = None
plugins: Optional[Dict[str, Callable]] = None
voiceio: Optional[Any] = None

# Optional API token for simple authentication (env var: VIVIAN_API_TOKEN)
API_TOKEN = os.environ.get("VIVIAN_API_TOKEN")

def require_auth():
    """Check for API token in Authorization header if API_TOKEN is set."""
    if API_TOKEN:
        token = request.headers.get("Authorization")
        if not token or token != f"Bearer {API_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
    return None

def get_uptime() -> str:
    """Return server uptime as string."""
    if not hasattr(get_uptime, "start"):
        get_uptime.start = datetime.datetime.now()
    delta = datetime.datetime.now() - get_uptime.start
    return str(delta)

@app.route("/")
def index():
    return (
        f"<h1>{config.get('name', 'Vivian')} Web Interface</h1>"
        f"<p>Use <code>/api/chat</code> to interact.<br>"
        f"See <a href='/api/docs'>/api/docs</a> for API documentation.</p>"
    )

@app.route("/api/chat", methods=["POST"])
def api_chat():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp

    data = request.get_json()
    if not data or "input" not in data:
        return jsonify({"error": "Missing input"}), 400

    user_input = data["input"]
    session_id = data.get("session_id", "default")
    user = data.get("user", "web")

    try:
        if command_handler:
            reply = command_handler(user_input, memory, config)
        else:
            from main import handle_user_input
            reply = handle_user_input(user_input, memory, config)

        if event_bus:
            event_bus.publish(
                "web_chat",
                data={"input": user_input, "reply": reply, "session_id": session_id, "user": user},
                context={"source": "api_chat"},
            )
        return jsonify({"reply": reply, "session_id": session_id})
    except Exception as e:
        logging.error(f"[API] Error handling input: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/memory", methods=["GET"])
def api_memory():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    try:
        q = request.args.get("q")
        user = request.args.get("user")
        limit = int(request.args.get("limit", 20))
        if hasattr(memory, "search") and q:
            results = memory.search(keyword=q, author=user, limit=limit)
            return jsonify(results)
        elif hasattr(memory, "session"):
            return jsonify(memory.session)
        return jsonify({"error": "Memory not available"}), 404
    except Exception as e:
        logging.error(f"[API] Error accessing memory: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/memory/<entry_id>", methods=["GET"])
def api_memory_entry(entry_id: str):
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    try:
        if hasattr(memory, "get_by_id"):
            result = memory.get_by_id(entry_id)
            if result:
                return jsonify(result)
            return jsonify({"error": "Not found"}), 404
        return jsonify({"error": "Not available"}), 404
    except Exception as e:
        logging.error(f"[API] Error fetching memory entry: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/memory/export", methods=["GET"])
def api_memory_export():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    try:
        if hasattr(memory, "export_memories"):
            path = memory.export_memories()
            return send_file(path, as_attachment=True)
        return jsonify({"error": "Export not available"}), 404
    except Exception as e:
        logging.error(f"[API] Error exporting memory: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/memory/import", methods=["POST"])
def api_memory_import():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400
    try:
        tmp_path = f"/tmp/vivian_import_{datetime.datetime.now().timestamp()}.jsonl"
        file.save(tmp_path)
        if hasattr(memory, "import_memories"):
            count = memory.import_memories(tmp_path)
            os.remove(tmp_path)
            return jsonify({"imported": count})
        os.remove(tmp_path)
        return jsonify({"error": "Import not available"}), 404
    except Exception as e:
        logging.error(f"[API] Error importing memory: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/status", methods=["GET"])
def api_status():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    return jsonify({
        "status": "online",
        "name": config.get("name", "Vivian"),
        "voice": config.get("voice_enabled", False),
        "server_port": config.get("server_port", 8000),
        "uptime": get_uptime(),
    })

# --- Voice endpoints ---

@app.route("/api/voice/speak", methods=["POST"])
def api_voice_speak():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    if not voiceio or not getattr(voiceio, "voice_enabled", False):
        return jsonify({"error": "VoiceIO not available"}), 404
    data = request.get_json()
    text = data.get("text")
    if not text:
        return jsonify({"error": "Missing text"}), 400
    try:
        voiceio.speak(text, background=True)
        if event_bus:
            event_bus.publish("voice_speak_api", data={"text": text}, context={"source": "api_voice_speak"})
        return jsonify({"status": "spoken"})
    except Exception as e:
        logging.error(f"[API] Voice speak error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/voice/listen", methods=["POST"])
def api_voice_listen():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    if not voiceio or not getattr(voiceio, "listen_enabled", False):
        return jsonify({"error": "VoiceIO not available"}), 404
    try:
        result = {}
        def cb(text):
            result["text"] = text
            if event_bus:
                event_bus.publish("api_voice_recognized", data={"text": text})
        voiceio.listen(background=True, result_callback=cb)
        return jsonify({"status": "listening"})
    except Exception as e:
        logging.error(f"[API] Voice listen error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/voice/voices", methods=["GET"])
def api_voice_voices():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    if not voiceio or not getattr(voiceio, "voice_enabled", False):
        return jsonify({"error": "VoiceIO not available"}), 404
    try:
        voices = voiceio.get_available_voices()
        return jsonify({"voices": voices})
    except Exception as e:
        logging.error(f"[API] Voice voices error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/voice/set_voice", methods=["POST"])
def api_voice_set_voice():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    if not voiceio or not getattr(voiceio, "voice_enabled", False):
        return jsonify({"error": "VoiceIO not available"}), 404
    data = request.get_json()
    voice_id = data.get("voice_id")
    if not voice_id:
        return jsonify({"error": "Missing voice_id"}), 400
    try:
        voiceio.set_voice(voice_id)
        if event_bus:
            event_bus.publish("voice_set_api", data={"voice_id": voice_id}, context={"source": "api_voice_set_voice"})
        return jsonify({"status": "voice set"})
    except Exception as e:
        logging.error(f"[API] Voice set voice error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/voice/list_microphones", methods=["GET"])
def api_voice_list_microphones():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    if not voiceio or not getattr(voiceio, "listen_enabled", False):
        return jsonify({"error": "VoiceIO not available"}), 404
    try:
        mics = voiceio.list_microphones()
        return jsonify({"microphones": mics})
    except Exception as e:
        logging.error(f"[API] Voice list microphones error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/voice/set_microphone", methods=["POST"])
def api_voice_set_microphone():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    if not voiceio or not getattr(voiceio, "listen_enabled", False):
        return jsonify({"error": "VoiceIO not available"}), 404
    data = request.get_json()
    mic_index = data.get("mic_index")
    if mic_index is None:
        return jsonify({"error": "Missing mic_index"}), 400
    try:
        voiceio.set_microphone(int(mic_index))
        if event_bus:
            event_bus.publish("voice_mic_set_api", data={"mic_index": mic_index}, context={"source": "api_voice_set_microphone"})
        return jsonify({"status": "microphone set"})
    except Exception as e:
        logging.error(f"[API] Voice set microphone error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/plugin/<plugin>", methods=["POST"])
def api_plugin(plugin: str):
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    if not plugins or plugin not in plugins:
        return jsonify({"error": "Plugin not available"}), 404
    data = request.get_json() or {}
    try:
        result = plugins[plugin](**data)
        if event_bus:
            event_bus.publish("plugin_api_call", data={"plugin": plugin, "args": data, "result": result}, context={"source": "api_plugin"})
        return jsonify({"result": result})
    except Exception as e:
        logging.error(f"[API] Plugin '{plugin}' error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/events", methods=["GET"])
def api_events():
    auth_resp = require_auth()
    if auth_resp:
        return auth_resp
    if hasattr(event_bus, "list_event_log"):
        log = event_bus.list_event_log(limit=30)
        return jsonify([str(e) for e in log])
    return jsonify({"error": "Event log unavailable"}), 404

@app.route("/api/docs", methods=["GET"])
def api_docs():
    return jsonify({
        "endpoints": [
            {"path": "/api/chat", "method": "POST", "desc": "Chat with Vivian."},
            {"path": "/api/memory", "method": "GET", "desc": "Get/search memory."},
            {"path": "/api/memory/<entry_id>", "method": "GET", "desc": "Get memory entry by ID."},
            {"path": "/api/memory/export", "method": "GET", "desc": "Export all memory to file."},
            {"path": "/api/memory/import", "method": "POST", "desc": "Import memories from file."},
            {"path": "/api/status", "method": "GET", "desc": "Vivian system status."},
            {"path": "/api/voice/speak", "method": "POST", "desc": "Speak text via Vivian's voice."},
            {"path": "/api/voice/listen", "method": "POST", "desc": "Listen for voice input."},
            {"path": "/api/voice/voices", "method": "GET", "desc": "List available voices."},
            {"path": "/api/voice/set_voice", "method": "POST", "desc": "Set TTS voice."},
            {"path": "/api/voice/list_microphones", "method": "GET", "desc": "List microphones."},
            {"path": "/api/voice/set_microphone", "method": "POST", "desc": "Set microphone index."},
            {"path": "/api/plugin/<plugin>", "method": "POST", "desc": "Call a registered plugin."},
            {"path": "/api/events", "method": "GET", "desc": "Get recent Vivian events."},
            {"path": "/api/shutdown", "method": "POST", "desc": "Shutdown the server (localhost only)."}
        ]
    })

@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify({"error": "Unauthorized"}), 403
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()
    if event_bus:
        event_bus.publish("system_shutdown", data={"source": "webapi"})
    return jsonify({"status": "shutting down"})

def server_supported() -> bool:
    """Check if Flask and flask_cors are installed and importable."""
    try:
        import flask  # noqa: F401
        import flask_cors  # noqa: F401
        return True
    except ImportError:
        return False

def run_server(
    mem: Any,
    conf: Dict[str, Any],
    handler: Optional[Callable[[str, Any, Dict[str, Any]], str]] = None,
    eb: Optional[Any] = None,
    vio: Optional[Any] = None,
    plgs: Optional[Dict[str, Callable]] = None,
):
    """Initialize global variables and start Flask server in a background thread."""
    global memory, config, command_handler, event_bus, voiceio, plugins

    memory = mem
    config = conf
    command_handler = handler
    event_bus = eb
    voiceio = vio
    plugins = plgs

    port = config.get("server_port", 8000)

    def start():
        logging.info(f"[Vivian] Web server running at http://0.0.0.0:{port}")
        app.run(host="0.0.0.0", port=port, threaded=True)

    thread = Thread(target=start, daemon=True)
    thread.start()