"""Tests for account safety limits, warm-up, and Telegram schedule parsing."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from bot.account_safety import clamp_limits, effective_limits, safe_default_limits
from bot.telegram_bot import _parse_schedule


def test_safe_default_limits_respect_hard_caps():
    hourly, daily = safe_default_limits()
    assert 0 < hourly <= 20
    assert 0 < daily <= 80


def test_clamp_limits_caps_high_values():
    with patch("bot.account_safety.AppConfig") as cfg:
        cfg.HARD_MAX_HOURLY_POST_LIMIT = 20
        cfg.HARD_MAX_DAILY_POST_LIMIT = 80
        assert clamp_limits(999, 999) == (20, 80)
        assert clamp_limits(0, 0) == (0, 0)
        assert clamp_limits(5, 25) == (5, 25)


def test_warmup_overrides_configured_limits():
    created = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    account = {
        "hourly_limit": 20,
        "daily_limit": 80,
        "created_at": created,
    }
    with patch("bot.account_safety.AppConfig") as cfg:
        cfg.ACCOUNT_WARMUP_DAYS = 7
        cfg.WARMUP_HOURLY_POST_LIMIT = 3
        cfg.WARMUP_DAILY_POST_LIMIT = 12
        cfg.HARD_MAX_HOURLY_POST_LIMIT = 20
        cfg.HARD_MAX_DAILY_POST_LIMIT = 80
        cfg.DEFAULT_HOURLY_POST_LIMIT = 5
        cfg.DEFAULT_DAILY_POST_LIMIT = 25
        limits = effective_limits(account)
        assert limits["warmup"] is True
        assert limits["hourly_limit"] == 3
        assert limits["daily_limit"] == 12
        assert limits["warmup_days_left"] == 5
        assert limits["source"] == "warmup"


def test_post_warmup_uses_configured_or_defaults():
    created = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    account = {
        "hourly_limit": 8,
        "daily_limit": 40,
        "created_at": created,
    }
    with patch("bot.account_safety.AppConfig") as cfg:
        cfg.ACCOUNT_WARMUP_DAYS = 7
        cfg.WARMUP_HOURLY_POST_LIMIT = 3
        cfg.WARMUP_DAILY_POST_LIMIT = 12
        cfg.HARD_MAX_HOURLY_POST_LIMIT = 20
        cfg.HARD_MAX_DAILY_POST_LIMIT = 80
        cfg.DEFAULT_HOURLY_POST_LIMIT = 5
        cfg.DEFAULT_DAILY_POST_LIMIT = 25
        limits = effective_limits(account)
        assert limits["warmup"] is False
        assert limits["hourly_limit"] == 8
        assert limits["daily_limit"] == 40
        assert limits["source"] == "configured"


def test_parse_schedule_basic():
    cron, hhmm, max_groups, message = _parse_schedule("/schedule 9:30 | Hello world")
    assert cron == "30 9 * * *"
    assert hhmm == "09:30"
    assert max_groups == 10
    assert message == "Hello world"


def test_parse_schedule_with_max():
    cron, hhmm, max_groups, message = _parse_schedule("/schedule 14:05 max=3 | Soft launch")
    assert cron == "5 14 * * *"
    assert hhmm == "14:05"
    assert max_groups == 3
    assert message == "Soft launch"


def test_parse_schedule_rejects_bad_time():
    cron, _, _, err = _parse_schedule("/schedule notime | hi")
    assert cron is None
    assert "HH:MM" in err
