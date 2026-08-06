"""Central configuration loaded from environment variables."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppConfig:
    PROJECT_ROOT = PROJECT_ROOT
    DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() in ("1", "true", "yes")
    USE_RQ_WORKERS = os.environ.get("USE_RQ_WORKERS", "false").lower() in ("1", "true", "yes")
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RUNTIME_DB_PATH = os.environ.get(
        "RUNTIME_DB_PATH",
        str(PROJECT_ROOT / "platform_runtime.db"),
    )
    # When set (postgres://...), RuntimeStore uses Postgres for multi-host web/worker.
    # Falls back to DATABASE_URL if RUNTIME_USE_APP_DB=true; otherwise SQLite file.
    RUNTIME_DATABASE_URL = (os.environ.get("RUNTIME_DATABASE_URL") or "").strip()
    RUNTIME_USE_APP_DB = os.environ.get("RUNTIME_USE_APP_DB", "true").lower() in ("1", "true", "yes")
    APP_SQLITE_PATH = os.environ.get("APP_SQLITE_PATH", str(PROJECT_ROOT / "test_app.db"))
    DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
    CONFIG_INI_PATH = os.environ.get("CONFIG_INI_PATH", str(PROJECT_ROOT / "config.ini"))

    DEFAULT_HOURLY_POST_LIMIT = int(os.environ.get("DEFAULT_HOURLY_POST_LIMIT", "5"))
    DEFAULT_DAILY_POST_LIMIT = int(os.environ.get("DEFAULT_DAILY_POST_LIMIT", "25"))
    # Absolute caps — UI/API cannot exceed these (anti-ban guardrail).
    HARD_MAX_HOURLY_POST_LIMIT = int(os.environ.get("HARD_MAX_HOURLY_POST_LIMIT", "20"))
    HARD_MAX_DAILY_POST_LIMIT = int(os.environ.get("HARD_MAX_DAILY_POST_LIMIT", "80"))
    ACCOUNT_COOLDOWN_MINUTES = int(os.environ.get("ACCOUNT_COOLDOWN_MINUTES", "60"))
    MAX_CONSECUTIVE_FAILURES = int(os.environ.get("MAX_CONSECUTIVE_FAILURES", "2"))
    # Warm-up: first N days after account creation use stricter caps.
    ACCOUNT_WARMUP_DAYS = int(os.environ.get("ACCOUNT_WARMUP_DAYS", "7"))
    WARMUP_HOURLY_POST_LIMIT = int(os.environ.get("WARMUP_HOURLY_POST_LIMIT", "3"))
    WARMUP_DAILY_POST_LIMIT = int(os.environ.get("WARMUP_DAILY_POST_LIMIT", "12"))
    # On checkpoint/2FA: hard-stop the posting task (do not keep queue going).
    AUTO_STOP_ON_VERIFICATION = os.environ.get("AUTO_STOP_ON_VERIFICATION", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    TELEGRAM_BOT_POLLING = os.environ.get("TELEGRAM_BOT_POLLING", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    @classmethod
    def sqlalchemy_database_uri(cls) -> str:
        """Postgres when DATABASE_URL is set; otherwise local SQLite."""
        if cls.DATABASE_URL:
            return cls.DATABASE_URL
        return "sqlite:///" + cls.APP_SQLITE_PATH

    @classmethod
    def runtime_database_url(cls) -> str:
        """Postgres URL for RuntimeStore, or empty string to use SQLite RUNTIME_DB_PATH."""
        if cls.RUNTIME_DATABASE_URL:
            return cls.RUNTIME_DATABASE_URL
        if cls.RUNTIME_USE_APP_DB and cls.DATABASE_URL and cls.DATABASE_URL.startswith("postgres"):
            return cls.DATABASE_URL
        return ""

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
