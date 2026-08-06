"""Effective per-account posting limits with warm-up and hard caps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.core.config import AppConfig


def _parse_created_at(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def clamp_limits(hourly: int, daily: int) -> Tuple[int, int]:
    hourly = max(0, int(hourly or 0))
    daily = max(0, int(daily or 0))
    if hourly > 0:
        hourly = min(hourly, AppConfig.HARD_MAX_HOURLY_POST_LIMIT)
    if daily > 0:
        daily = min(daily, AppConfig.HARD_MAX_DAILY_POST_LIMIT)
    return hourly, daily


def safe_default_limits() -> Tuple[int, int]:
    return clamp_limits(
        AppConfig.DEFAULT_HOURLY_POST_LIMIT,
        AppConfig.DEFAULT_DAILY_POST_LIMIT,
    )


def account_age_days(account: Dict[str, Any]) -> Optional[int]:
    created = _parse_created_at(account.get("created_at"))
    if not created:
        return None
    now = datetime.now(timezone.utc)
    return max(0, (now - created).days)


def effective_limits(account: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve hourly/daily caps for an account.

    Priority:
    1) Warm-up window (first ACCOUNT_WARMUP_DAYS) → WARMUP_* caps
    2) Explicit account hourly/daily (clamped)
    3) Safe AppConfig defaults
    """
    age = account_age_days(account)
    warmup_days = max(0, int(AppConfig.ACCOUNT_WARMUP_DAYS))
    in_warmup = age is not None and age < warmup_days

    configured_h = int(account.get("hourly_limit") or 0)
    configured_d = int(account.get("daily_limit") or 0)
    configured_h, configured_d = clamp_limits(configured_h, configured_d)

    if in_warmup:
        hourly = min(
            AppConfig.WARMUP_HOURLY_POST_LIMIT,
            configured_h or AppConfig.WARMUP_HOURLY_POST_LIMIT,
        )
        daily = min(
            AppConfig.WARMUP_DAILY_POST_LIMIT,
            configured_d or AppConfig.WARMUP_DAILY_POST_LIMIT,
        )
        hourly, daily = clamp_limits(hourly, daily)
        return {
            "hourly_limit": hourly,
            "daily_limit": daily,
            "configured_hourly": configured_h,
            "configured_daily": configured_d,
            "warmup": True,
            "warmup_days": warmup_days,
            "account_age_days": age,
            "warmup_days_left": max(0, warmup_days - (age or 0)),
            "source": "warmup",
        }

    hourly = configured_h or AppConfig.DEFAULT_HOURLY_POST_LIMIT
    daily = configured_d or AppConfig.DEFAULT_DAILY_POST_LIMIT
    hourly, daily = clamp_limits(hourly, daily)
    return {
        "hourly_limit": hourly,
        "daily_limit": daily,
        "configured_hourly": configured_h,
        "configured_daily": configured_d,
        "warmup": False,
        "warmup_days": warmup_days,
        "account_age_days": age,
        "warmup_days_left": 0,
        "source": "configured" if configured_h or configured_d else "safe_default",
    }
