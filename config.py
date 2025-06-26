import os
import json
import copy
import hashlib
import datetime
from typing import Dict, Any, Optional, Callable, List

CONFIG_FILE = "vivian_config.json"
BACKUP_CONFIG_FILE = "vivian_config.backup.json"

DEFAULT_CONFIG = {
    "name": "Vivian",
    "persona": "default",
    "personas": ["default", "storyteller", "mentor", "therapist", "coder", "analyst", "visionary", "security", "researcher"],
    "voice_enabled": False,
    "voice_input_enabled": False,
    "wake_word": "Hey Vivian",
    "voice_params": {
        "voice": "en-US",
        "rate": 1.0,
        "volume": 1.0,
        "pitch": 1.0,
        "audio_output_device": "default"
    },
    "context_window": 10,
    "long_term_memory_enabled": True,
    "memory_dir": "memory",
    "log_file": "history.jsonl",
    "log_level": "INFO",
    "log_rotation": True,
    "log_max_size_mb": 50,
    "knowledge_base_enabled": True,
    "knowledge_base_dir": "knowledge",
    "model": "mistral:latest",
    "api_url": "http://localhost:11434/api/generate",
    "greeting": "Hello! I'm ready when you are.",
    "gui_enabled": True,
    "server_enabled": True,
    "server_port": 8000,
    "server_host": "0.0.0.0",
    "plugin_system_enabled": True,
    "plugin_dir": "plugins",
    "hot_reload_plugins": True,
    "websearch_enabled": True,
    "websearch_engine": "duckduckgo",
    "websearch_api_key": "",
    "scheduler_enabled": True,
    "file_handling_enabled": True,
    "supported_file_types": ["txt", "pdf", "docx", "md", "jpg", "png", "csv", "json", "yaml"],
    "external_integrations": [
        # Example: {"service": "email", "enabled": False, "provider": "gmail"}
    ],
    "calendar_enabled": True,
    "calendar_provider": "",
    "home_automation_enabled": False,
    "iot_integrations": [],
    "analytics_enabled": True,
    "usage_stats_enabled": True,
    "security": {
        "encrypt_memory": False,
        "user_authentication": False,
        "access_control": [],
        "data_retention_days": 90,
        "rate_limit_per_minute": 60,
        "max_login_attempts": 5,
        "jwt_secret_hash": "",
        "allowed_ips": [],
        "audit_logging": True
    },
    "privacy": {
        "log_user_consent": True,
        "share_knowledge": False,
        "mask_sensitive_output": True,
        "gdpr_mode": False,
        "anonymize_logs": False
    },
    "cloud_sync_enabled": False,
    "cloud_sync_provider": "",
    "backup_enabled": True,
    "backup_dir": "backups",
    "backup_frequency_hours": 24,
    "auto_restore_on_crash": True,
    "localization_enabled": True,
    "language": "en",
    "timezone": "UTC",
    "sentiment_analysis_enabled": True,
    "mood_tracking_enabled": True,
    "emotion_detection_enabled": True,
    "explainable_ai_enabled": True,
    "content_moderation_enabled": True,
    "sandbox_code_execution": True,
    "api_webhook_enabled": True,
    "webhook_endpoints": [],
    "custom_automation_enabled": True,
    "custom_scripts_dir": "custom_scripts",
    "accessibility": {
        "high_contrast_mode": False,
        "dyslexic_font": False,
        "screen_reader_support": True,
        "large_text": False
    },
    "mobile_app_enabled": False,
    "mobile_app_port": 9000,
    "auto_update_enabled": True,
    "update_channel": "stable",
    "federated_knowledge_sharing": False,
    "distributed_sync_enabled": False,
    "activity_monitoring_enabled": True,
    "session_timeout_minutes": 30,
    "notifications_enabled": True,
    "notification_channels": ["email", "web", "desktop"],
    "default_theme": "light",
    "themes_available": ["light", "dark", "solarized"],
    "profile_avatar_dir": "avatars",
    "max_upload_size_mb": 100,
    "api_rate_limit_per_minute": 120,
    "config_version": 2,
    "config_source": "default",
    "last_loaded": "",
    "last_modified": "",
    "dynamic_overrides": {},
    "readonly": False,
    "import_hooks": [],
    "export_hooks": [],
    "backup_on_change": True,
    "config_audit_log": [],
    "env_prefix": "VIVIAN_",
    "custom_env": {},
    "config_validators": [],
    "profile": "",
    "experimental": {
        "multi_agent": False,
        "conversational_memory": True,
        "autonomous_mode": False,
        "self_heal": True,
        "auto_save": True,
        "agent_collaboration": False,
        "agent_observability": False,
        "self_diagnostics": True,
        "contextual_routing": True
    }
}

def deep_update(d: Dict[Any, Any], u: Dict[Any, Any]):
    """Recursively update dict d with values from u (used for nested configs)."""
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            deep_update(d[k], v)
        else:
            d[k] = v

def _merge_env_overrides(config: Dict[str, Any], prefix: str, custom_env: dict):
    for k in config:
        env_var = prefix + k.upper()
        if env_var in os.environ:
            val = os.environ[env_var]
            try:
                val = json.loads(val)
            except Exception:
                pass
            config[k] = val
    for k, v in custom_env.items():
        config[k] = v

def backup_config(path: str = CONFIG_FILE, backup_path: str = BACKUP_CONFIG_FILE):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            with open(backup_path, "w", encoding="utf-8") as f2:
                f2.write(content)
        except Exception as e:
            print(f"[Vivian] Error backing up config: {e}")

def validate_config(config: Dict[str, Any], validators: Optional[List[Callable[[dict], bool]]] = None):
    errors = []
    for v in validators or []:
        try:
            if not v(config):
                errors.append(f"Validation failed: {v.__name__}")
        except Exception as e:
            errors.append(str(e))
    return errors

def audit_config(event: str, config: Dict[str, Any], audit_log: Optional[List[dict]] = None):
    entry = {
        "event": event,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "config_snapshot": copy.deepcopy(config)
    }
    (audit_log or config.setdefault("config_audit_log", [])).append(entry)

def load_config(
    path: str = CONFIG_FILE,
    backup_on_fail: bool = True,
    env_override: bool = True,
    dynamic_override: Optional[dict] = None,
    validate: bool = True,
    validators: Optional[List[Callable[[dict], bool]]] = None
) -> Dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["last_loaded"] = datetime.datetime.utcnow().isoformat()
    config["config_source"] = "default"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                deep_update(config, user_config)
                config["config_source"] = path
                config["last_modified"] = datetime.datetime.utcfromtimestamp(os.path.getmtime(path)).isoformat()
        except Exception as e:
            print(f"[Vivian] Error loading config, using defaults. Error: {e}")
            if backup_on_fail and os.path.exists(BACKUP_CONFIG_FILE):
                try:
                    with open(BACKUP_CONFIG_FILE, "r", encoding="utf-8") as f2:
                        user_config = json.load(f2)
                        deep_update(config, user_config)
                        config["config_source"] = BACKUP_CONFIG_FILE
                        config["last_modified"] = datetime.datetime.utcfromtimestamp(os.path.getmtime(BACKUP_CONFIG_FILE)).isoformat()
                except Exception as e2:
                    print(f"[Vivian] Error loading backup config, using defaults. Error: {e2}")
    if env_override:
        _merge_env_overrides(config, config.get("env_prefix", "VIVIAN_"), config.get("custom_env", {}))
    if dynamic_override:
        deep_update(config, dynamic_override)
        config["dynamic_overrides"] = dynamic_override
    if validate and config.get("config_validators"):
        errors = validate_config(config, config.get("config_validators"))
        if errors:
            print(f"[Vivian] Config validation errors: {errors}")
    audit_config("load_config", config)
    return config

def save_config(config: Dict[str, Any], path: str = CONFIG_FILE, backup: bool = True):
    if backup and os.path.exists(path):
        backup_config(path)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        audit_config("save_config", config)
        return True
    except Exception as e:
        print(f"[Vivian] Error saving config: {e}")
        return False

def update_config(updates: Dict[str, Any], path: str = CONFIG_FILE, save: bool = True):
    config = load_config(path)
    deep_update(config, updates)
    audit_config("update_config", config)
    if save:
        save_config(config, path)
    return config

def explain_config(config: Dict[str, Any]) -> str:
    summary = []
    summary.append(f"Vivian Config (version {config.get('config_version', 1)}) loaded from {config.get('config_source', 'default')}")
    summary.append(f"Persona: {config.get('persona')} | Model: {config.get('model')}")
    summary.append(f"Voice: {'on' if config.get('voice_enabled') else 'off'} | GUI: {'on' if config.get('gui_enabled') else 'off'} | Server: {'on' if config.get('server_enabled') else 'off'} (host {config.get('server_host')}, port {config.get('server_port')})")
    summary.append(f"Long-term memory: {'on' if config.get('long_term_memory_enabled') else 'off'}, Knowledge base: {'on' if config.get('knowledge_base_enabled') else 'off'}")
    summary.append(f"Localization: {config.get('language')} | Timezone: {config.get('timezone')}")
    summary.append(f"Security: {config.get('security')}")
    summary.append(f"Backup: {'on' if config.get('backup_enabled') else 'off'} at {config.get('backup_dir')} every {config.get('backup_frequency_hours')}h")
    summary.append(f"Experimental: {config.get('experimental')}")
    summary.append(f"Accessibility: {config.get('accessibility')}")
    return "\n".join(summary)

def print_config(config: Dict[str, Any]):
    print(explain_config(config))
    print(json.dumps(config, indent=2))

def config_shell():
    print("Vivian Config Shell. Commands: load, save, update, explain, print, exit")
    config = load_config()
    while True:
        try:
            cmd = input("> ").strip()
            if cmd == "exit":
                print("Exiting config shell.")
                break
            elif cmd == "load":
                config = load_config()
                print("Loaded.")
            elif cmd == "save":
                save_config(config)
                print("Saved.")
            elif cmd.startswith("update "):
                try:
                    updates = json.loads(cmd[7:])
                    update_config(updates)
                    print("Updated.")
                except Exception as e:
                    print(f"Update failed: {e}")
            elif cmd == "explain":
                print(explain_config(config))
            elif cmd == "print":
                print_config(config)
            else:
                print("Unknown command. Commands: load, save, update, explain, print, exit")
        except Exception as e:
            print(f"Error: {e}")

def hash_secret(secret: str) -> str:
    """Hash a secret for storing in config (e.g., JWT, API keys)."""
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()

def set_jwt_secret(config: Dict[str, Any], secret: str):
    config["security"]["jwt_secret_hash"] = hash_secret(secret)
    save_config(config)

if __name__ == "__main__":
    config = load_config()
    print_config(config)
    # config_shell()