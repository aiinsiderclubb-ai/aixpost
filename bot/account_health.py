"""Account health scoring and cooldown management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Tuple

from app.core.config import AppConfig

if TYPE_CHECKING:
    from platform_runtime import RuntimeStore


class AccountHealthMonitor:
    def __init__(self, store: "RuntimeStore"):
        self.store = store

    def is_blocked(self, account_id: int | None) -> Tuple[bool, str]:
        if not account_id:
            return False, ""
        account = self.store.get_account(account_id)
        if not account:
            return False, ""
        cooldown_until = account.get("cooldown_until")
        if cooldown_until:
            try:
                until = datetime.fromisoformat(cooldown_until)
                if until.tzinfo is None:
                    until = until.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) < until:
                    return True, f"Account in cooldown until {cooldown_until}"
            except ValueError:
                pass
        if int(account.get("health_score", 100) or 100) <= 20:
            return True, "Account health is critically low"
        return False, ""

    def record_result(self, account_id: int | None, success: bool, error: str | None = None) -> None:
        if not account_id:
            return
        account = self.store.get_account(account_id) or {}
        failures = int(account.get("consecutive_failures", 0) or 0)
        score = int(account.get("health_score", 100) or 100)
        if success:
            failures = 0
            score = min(100, score + 2)
        else:
            failures += 1
            score = max(0, score - 12)
            if failures >= AppConfig.MAX_CONSECUTIVE_FAILURES:
                cooldown = datetime.now(timezone.utc) + timedelta(minutes=AppConfig.ACCOUNT_COOLDOWN_MINUTES)
                self.store.update_account_health(
                    account_id,
                    health_score=score,
                    consecutive_failures=failures,
                    cooldown_until=cooldown.isoformat(),
                    last_error=error,
                )
                return
        self.store.update_account_health(
            account_id,
            health_score=score,
            consecutive_failures=failures,
            cooldown_until=None,
            last_error=error if not success else None,
        )
