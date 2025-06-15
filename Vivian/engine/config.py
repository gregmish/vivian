import json
import os
from pathlib import Path
import copy
import logging
from typing import Dict, Any, Optional

CONFIG_DIR = Path("config")
CONFIG_FILE = CONFIG_DIR / "vivian_config.json"
BACKUP_DIR = CONFIG_DIR / "backups"

DEFAULT_CONFIG = {
    "name": "Vivian",
    "greeting": "Hello! I'm ready when you are.",
    "voice_enabled": False,
    "voice_params": {
        "rate": 1.0,
        "voice": "default"
    },
    "context_window": 10,
    "persona": "default",
    "model": "gpt-4",
    "api_url": "http://localhost:5000/api",
    "version": "1.0.0",
    "allow_plugins": True,
    "plugin_system_enabled": True,
    "plugin_dir": "plugins",
    "debug_mode": False,
    "auto_reload_plugins": True,
    "profiles": {},
    "secrets_file": str(CONFIG_DIR / "secrets.json"),
    "log_config_events": True,
    "memory_dir": "memory",
    "log_file": "history.jsonl",
    "long_term_memory_enabled": True,
    "knowledge_base_enabled": True,
    "knowledge_base_dir": "knowledge",
    "backup_enabled": True,
    "backup_dir": "backups",
    "data_retention_days": 90,
    "mood_tracking_enabled": True,
    "sentiment_analysis_enabled": True,
    "explainable_ai_enabled": True,
    "content_moderation_enabled": True,
    "multimodal_enabled": False,
    "sandbox_code_execution": True,
    "websearch_enabled": True,
    "websearch_engine": "duckduckgo",
    "scheduler_enabled": True,
    "calendar_enabled": True,
    "calendar_provider": "",
    "file_handling_enabled": True,
    "supported_file_types": ["txt", "pdf", "docx", "md", "jpg", "png"],
    "analytics_enabled": True,
    "usage_stats_enabled": True,
    "security": {
        "encrypt_memory": False,
        "user_authentication": False,
        "access_control": [],
        "data_retention_days": 90,
        "two_factor_auth": False,
        "audit_trail_enabled": True
    },
    "privacy": {
        "log_user_consent": True,
        "share_knowledge": False,
        "gdpr_compliance": False,
        "data_purging_enabled": True
    },
    "auto_update_enabled": True,
    "update_channel": "stable",
    "localization_enabled": True,
    "language": "en",
    "timezone": "UTC",
    "federated_knowledge_sharing": False,
    "distributed_sync_enabled": False,
    "personas": {
        "default": "You are Vivian, an intelligent, agentic assistant. Be helpful, sharp, and real.",
        "friendly": "You are Vivian, a warm, friendly assistant who always encourages users.",
        "dark": "You are Vivian, brutally honest and sarcastic. You say it like it is.",
        "coder": "You are Vivian, an expert software engineer. Be technical, concise, and practical."
    },
    "goals": {
        "default": "",
        "productivity": "Help the user stay focused, organized, and get things done.",
        "learning": "Assist the user in learning new skills, concepts, or languages.",
        "wellness": "Promote good habits, positivity, and self-care."
    },
    "few_shot_examples": "",
    "system_prompt": "You are Vivian, an intelligent, agentic assistant. Be direct, helpful, and sharp.",
    "last_loaded": None,
    # --- ADVANCED/EXPERIMENTAL/OPTIONAL FEATURES ---
    "macros_enabled": False,
    "macro_directory": "macros",
    "reminders_enabled": False,
    "notification_channels": [],  # ["email", "discord", "sms"]
    "notification_email": "",
    "notification_discord_webhook": "",
    "notification_sms_number": "",
    "auto_persona_switching": False,
    "auto_mode_switching": False,
    "plugin_marketplace_enabled": False,
    "plugin_marketplace_url": "",
    "plugin_auto_update": False,
    "ocr_enabled": False,
    "audio_transcription_enabled": False,
    "pdf_summarization_enabled": False,
    "ui_theme": "auto",  # dark, light, high-contrast, auto
    "user_themes": {},
    "voice_command_enabled": False,
    "wake_word": "",
    "web_browsing_enabled": False,
    "browser_sandbox_enabled": True,
    "knowledge_graph_enabled": False,
    "self_diagnostics_enabled": True,
    "auto_repair_enabled": False,
    "user_reputation_enabled": False,
    "gamification_enabled": False,
    "badges": {},
    "leaderboards_enabled": False,
    "data_export_formats": ["json", "md", "csv", "html"],
    "multi_language_enabled": True,
    "supported_languages": ["en"],
    "translation_provider": "",
    "api_integrations": {
        "google_calendar": "",
        "trello": "",
        "slack": "",
        "jira": "",
        "notion": "",
        "github": ""
    },
    "multi_workspace_enabled": False,
    "workspace_directory": "workspaces",
    "sentiment_driven_persona": False,
    "enhanced_security": True,
    "fun_features_enabled": False,
    "fun_games": ["joke", "riddle", "chess", "haiku"],
    "api_enabled": True,
    "api_port": 8888,
    "api_auth_required": True,
    "sdk_enabled": False,
    "event_hooks_enabled": True,
    "scheduled_actions_enabled": False,
    "schedule_storage": "schedules",
    "auto_macro_suggestions": False,
    "contextual_help_enabled": True,
    "self_check_enabled": True,
    "diagnose_enabled": True,
    # Any other future feature toggles can be added here
}

def merge_defaults(defaults: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively fill in missing keys from defaults (deep merge)."""
    for k, v in defaults.items():
        if k not in config:
            config[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(config[k], dict):
            merge_defaults(v, config[k])
    return config

def fix_config_types(config: dict):
    """Defensively ensure personas/goals are always dicts (never lists)."""
    # Personas - if accidentally a list, convert to dict
    personas = config.get("personas")
    if isinstance(personas, list):
        config["personas"] = {p: f"You are Vivian with the {p} persona." for p in personas}
    elif not isinstance(personas, dict) or personas is None:
        config["personas"] = copy.deepcopy(DEFAULT_CONFIG["personas"])

    # Goals - if accidentally a list, convert to dict
    goals = config.get("goals")
    if isinstance(goals, list):
        config["goals"] = {g: "" for g in goals}
    elif not isinstance(goals, dict) or goals is None:
        config["goals"] = copy.deepcopy(DEFAULT_CONFIG["goals"])

    # Supported file types
    if not isinstance(config.get("supported_file_types"), list):
        config["supported_file_types"] = list(DEFAULT_CONFIG["supported_file_types"])

    # Security block
    if not isinstance(config.get("security"), dict):
        config["security"] = copy.deepcopy(DEFAULT_CONFIG["security"])
    # Privacy block
    if not isinstance(config.get("privacy"), dict):
        config["privacy"] = copy.deepcopy(DEFAULT_CONFIG["privacy"])

    # plugin_dir
    if not config.get("plugin_dir"):
        config["plugin_dir"] = "plugins"

    return config

def load_secrets(secrets_file: Optional[str] = None) -> dict:
    secrets_path = Path(secrets_file) if secrets_file else (CONFIG_DIR / "secrets.json")
    if secrets_path.exists():
        try:
            with secrets_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"[Config] Failed to load secrets: {e}")
    return {}

def apply_env_overrides(config: dict) -> dict:
    """Override config values with environment variables if present."""
    for key in config:
        env_key = f"VIVIAN_{key.upper()}"
        if env_key in os.environ:
            val = os.environ[env_key]
            orig = config[key]
            if isinstance(orig, bool):
                config[key] = val.lower() in ("1", "true", "yes")
            elif isinstance(orig, int):
                try:
                    config[key] = int(val)
                except Exception:
                    pass
            elif isinstance(orig, float):
                try:
                    config[key] = float(val)
                except Exception:
                    pass
            elif isinstance(orig, dict):
                try:
                    config[key] = json.loads(val)
                except Exception:
                    pass
            else:
                config[key] = val
    return config

def backup_config(config_path: Path):
    """Save a versioned backup of the existing config."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        version = 1
        backup_base = BACKUP_DIR / f"{config_path.stem}.bak"
        backup_path = backup_base.with_suffix(f".v{version}.json")
        while backup_path.exists():
            version += 1
            backup_path = backup_base.with_suffix(f".v{version}.json")
        try:
            with config_path.open("r", encoding="utf-8") as f_in, backup_path.open("w", encoding="utf-8") as f_out:
                f_out.write(f_in.read())
            logging.info(f"[Config] Config backed up at {backup_path}")
        except Exception as e:
            logging.error(f"[Config] Failed to backup config: {e}")

def validate_config(config: dict) -> bool:
    """Simple schema validation. Extend for stricter checks."""
    required_keys = list(DEFAULT_CONFIG.keys())
    for key in required_keys:
        if key not in config:
            logging.error(f"[Config] Missing required config key: {key}")
            return False
    # Add more validation if needed
    return True

def load_profile(profile_name: Optional[str], config: dict) -> dict:
    """Load a named profile and merge it with the current config."""
    profiles = config.get("profiles", {})
    if profile_name and profile_name in profiles:
        profile = copy.deepcopy(profiles[profile_name])
        merge_defaults(DEFAULT_CONFIG, profile)
        config.update(profile)
    return config

def load_config(profile: Optional[str] = None) -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {}
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                config = json.load(f)
            config = merge_defaults(DEFAULT_CONFIG, config)
            config = apply_env_overrides(config)
            config = load_profile(profile, config)
            config["last_loaded"] = str(Path(CONFIG_FILE).stat().st_mtime)
            config = fix_config_types(config)
            if not validate_config(config):
                logging.error("[Config] Invalid config structure, using defaults.")
                config = copy.deepcopy(DEFAULT_CONFIG)
        except Exception as e:
            logging.error(f"[Config] Error loading config: {e}")
            config = copy.deepcopy(DEFAULT_CONFIG)
    else:
        save_config(DEFAULT_CONFIG)
        config = copy.deepcopy(DEFAULT_CONFIG)
    # Optionally load secrets
    secrets = load_secrets(config.get("secrets_file"))
    if secrets:
        config["secrets"] = secrets
    return config

def save_config(config: dict):
    try:
        backup_config(CONFIG_FILE)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        if config.get("log_config_events"):
            logging.info("[Config] Config saved successfully.")
    except Exception as e:
        logging.error(f"[Config] Failed to save config: {e}")

def import_config(path: str):
    """Import config from a given file (overwriting existing config)."""
    src_path = Path(path)
    if not src_path.exists():
        print(f"[Config] Import source does not exist: {path}")
        return
    try:
        with src_path.open("r", encoding="utf-8") as f:
            imported = json.load(f)
        save_config(imported)
        print(f"[Config] Config imported from {path}")
    except Exception as e:
        print(f"[Config] Failed to import config: {e}")

def export_config(path: str):
    """Export current config to a chosen path."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f_in, open(path, "w", encoding="utf-8") as f_out:
            f_out.write(f_in.read())
        print(f"[Config] Config exported to {path}")
    except Exception as e:
        print(f"[Config] Failed to export config: {e}")

def list_profiles() -> list:
    config = load_config()
    return list(config.get("profiles", {}).keys())

def set_profile(profile_name: str):
    config = load_config(profile=profile_name)
    save_config(config)
    print(f"[Config] Profile '{profile_name}' set and config reloaded.")

def reset_config():
    save_config(DEFAULT_CONFIG)
    print("[Config] Config reset to defaults.")

def print_config():
    config = load_config()
    print(json.dumps(config, indent=4))

# For CLI usage
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vivian Config Manager")
    parser.add_argument("--show", action="store_true", help="Print current config")
    parser.add_argument("--import", dest="import_path", help="Import config from file")
    parser.add_argument("--export", dest="export_path", help="Export config to file")
    parser.add_argument("--reset", action="store_true", help="Reset config to defaults")
    parser.add_argument("--profile", help="Set active profile")
    parser.add_argument("--list-profiles", action="store_true", help="List available profiles")
    args = parser.parse_args()
    if args.show:
        print_config()
    elif args.import_path:
        import_config(args.import_path)
    elif args.export_path:
        export_config(args.export_path)
    elif args.reset:
        reset_config()
    elif args.profile:
        set_profile(args.profile)
    elif args.list_profiles:
        print("Available profiles:", ", ".join(list_profiles()))
    else:
        parser.print_help()