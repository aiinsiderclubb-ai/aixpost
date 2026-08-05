"""Central configuration loaded from environment variables."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppConfig:
    DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() in ("1", "true", "yes")
    USE_RQ_WORKERS = os.environ.get("USE_RQ_WORKERS", "false").lower() in ("1", "true", "yes")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RUNTIME_DB_PATH = os.environ.get(
        "RUNTIME_DB_PATH",
        str(PROJECT_ROOT / "platform_runtime.db"),
    )
    APP_SQLITE_PATH = os.environ.get("APP_SQLITE_PATH", str(PROJECT_ROOT / "test_app.db"))
    CONFIG_INI_PATH = os.environ.get("CONFIG_INI_PATH", str(PROJECT_ROOT / "config.ini"))

    DEFAULT_HOURLY_POST_LIMIT = int(os.environ.get("DEFAULT_HOURLY_POST_LIMIT", "15"))
    DEFAULT_DAILY_POST_LIMIT = int(os.environ.get("DEFAULT_DAILY_POST_LIMIT", "80"))
    ACCOUNT_COOLDOWN_MINUTES = int(os.environ.get("ACCOUNT_COOLDOWN_MINUTES", "30"))
    MAX_CONSECUTIVE_FAILURES = int(os.environ.get("MAX_CONSECUTIVE_FAILURES", "3"))

    @classmethod
    def get_fernet_key(cls) -> str:
        key = (os.environ.get("FERNET_KEY") or "").strip()
        if key:
            return key
        key_file = PROJECT_ROOT / "encryption.key"
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        raise RuntimeError(
            "FERNET_KEY environment variable or encryption.key file is required for startup"
        )

    @classmethod
    def overlay_bot_secrets_from_env(cls, poster) -> None:
        """Apply env-based secrets over config.ini values (never log secrets)."""
        if os.environ.get("FB_USERNAME"):
            poster.username = os.environ["FB_USERNAME"]
        if os.environ.get("FB_PASSWORD"):
            poster.password = os.environ["FB_PASSWORD"]
        if os.environ.get("TELEGRAM_BOT_TOKEN"):
            poster.telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
        if os.environ.get("TELEGRAM_CHAT_ID"):
            poster.telegram_chat_id = os.environ["TELEGRAM_CHAT_ID"]
