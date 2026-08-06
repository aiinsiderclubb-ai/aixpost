"""Account posting rate limits backed by platform_runtime.db."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Tuple

from bot.account_safety import effective_limits

if TYPE_CHECKING:
    from platform_runtime import RuntimeStore


class AccountRateLimiter:
    def __init__(self, store: "RuntimeStore"):
        self.store = store

    def limits_for_account(self, account_id: int | None) -> Dict:
        if not account_id:
            from bot.account_safety import safe_default_limits

            hourly, daily = safe_default_limits()
            return {
                "hourly_limit": hourly,
                "daily_limit": daily,
                "warmup": False,
                "source": "safe_default",
            }
        account = self.store.get_account(int(account_id)) or {"id": account_id}
        return effective_limits(account)

    def can_post(self, account_id: int | None, hourly_limit: int = 0, daily_limit: int = 0) -> Tuple[bool, str]:
        if not account_id:
            return True, ""
        limits = self.limits_for_account(account_id)
        # Explicit args override only when > 0 and caller already resolved; prefer effective.
        hourly = int(limits.get("hourly_limit") or hourly_limit or 0)
        daily = int(limits.get("daily_limit") or daily_limit or 0)
        hour_count = self.store.count_account_posts(account_id, hours=1)
        day_count = self.store.count_account_posts(account_id, hours=24)
        if hourly > 0 and hour_count >= hourly:
            suffix = " (warm-up)" if limits.get("warmup") else ""
            return False, f"Hourly limit reached ({hour_count}/{hourly}){suffix}"
        if daily > 0 and day_count >= daily:
            suffix = " (warm-up)" if limits.get("warmup") else ""
            return False, f"Daily limit reached ({day_count}/{daily}){suffix}"
        return True, ""

    def record_post(self, account_id: int | None, user_id: int, group_url: str, success: bool) -> None:
        if account_id:
            self.store.record_account_post(account_id, user_id, group_url, success)
