import os
import json

CONFIG_FILE = "vivian_config.json"

DEFAULT_CONFIG = {
    "name": "Vivian",
    "persona": "default",
    "personas": ["default", "storyteller", "mentor", "therapist", "coder"],
    "voice_enabled": False,
    "voice_input_enabled": False,
    "wake_word": "Hey Vivian",
    "voice_params": {
        "voice": "en-US",
        "rate": 1.0,
        "volume": 1.0
    },
    "context_window": 5,
    "long_term_memory_enabled": True,
    "memory_dir": "memory",
    "log_file": "history.jsonl",
    "knowledge_base_enabled": True,
    "knowledge_base_dir": "knowledge",
    "model": "mistral:latest",
    "api_url": "http://localhost:11434/api/generate",
    "greeting": "Hello! I'm ready when you are.",
    "gui_enabled": True,
    "server_enabled": True,
    "server_port": 8000,
    "plugin_system_enabled": True,
    "plugin_dir": "plugins",
    "hot_reload_plugins": True,
    "websearch_enabled": True,
    "websearch_engine": "duckduckgo",
    "scheduler_enabled": True,
    "file_handling_enabled": True,
    "supported_file_types": ["txt", "pdf", "docx", "md", "jpg", "png"],
    "external_integrations": [
        # Example: {"service": "email", "enabled": False, "provider": "gmail"}
    ],
    "calendar_enabled": True,
    "calendar_provider": "",
    "home_automation_enabled": False,
    "analytics_enabled": True,
    "usage_stats_enabled": True,
    "security": {
        "encrypt_memory": False,
        "user_authentication": False,
        "access_control": [],
        "data_retention_days": 90
    },
    "privacy": {
        "log_user_consent": True,
        "share_knowledge": False
    },
    "cloud_sync_enabled": False,
    "cloud_sync_provider": "",
    "backup_enabled": True,
    "backup_dir": "backups",
    "localization_enabled": True,
    "language": "en",
    "timezone": "UTC",
    "sentiment_analysis_enabled": True,
    "mood_tracking_enabled": True,
    "explainable_ai_enabled": True,
    "content_moderation_enabled": True,
    "sandbox_code_execution": True,
    "api_webhook_enabled": True,
    "custom_automation_enabled": True,
    "accessibility": {
        "high_contrast_mode": False,
        "dyslexic_font": False,
        "screen_reader_support": True
    },
    "mobile_app_enabled": False,
    "mobile_app_port": 9000,
    "auto_update_enabled": True,
    "update_channel": "stable",
    "federated_knowledge_sharing": False,
    "distributed_sync_enabled": False
}

def deep_update(d, u):
    """Recursively update dict d with values from u (used for nested configs)."""
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            deep_update(d[k], v)
        else:
            d[k] = v

def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                deep_update(config, user_config)
        except Exception as e:
            print(f"[Vivian] Error loading config, using defaults. Error: {e}")
    return config