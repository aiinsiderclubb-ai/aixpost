"""Account posting rate limits backed by platform_runtime.db."""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from app.core.config import AppConfig

if TYPE_CHECKING:
    from platform_runtime import RuntimeStore


class AccountRateLimiter:
    def __init__(self, store: "RuntimeStore"):
        self.store = store

    def can_post(self, account_id: int | None, hourly_limit: int = 0, daily_limit: int = 0) -> Tuple[bool, str]:
        if not account_id:
            return True, ""
        hourly = hourly_limit or AppConfig.DEFAULT_HOURLY_POST_LIMIT
        daily = daily_limit or AppConfig.DEFAULT_DAILY_POST_LIMIT
        hour_count = self.store.count_account_posts(account_id, hours=1)
        day_count = self.store.count_account_posts(account_id, hours=24)
        if hourly > 0 and hour_count >= hourly:
            return False, f"Hourly limit reached ({hour_count}/{hourly})"
        if daily > 0 and day_count >= daily:
            return False, f"Daily limit reached ({day_count}/{daily})"
        return True, ""

    def record_post(self, account_id: int | None, user_id: int, group_url: str, success: bool) -> None:
        if account_id:
            self.store.record_account_post(account_id, user_id, group_url, success)
