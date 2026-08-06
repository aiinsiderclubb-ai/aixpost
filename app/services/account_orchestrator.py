"""Multi-account selection, rotation and auto-pause helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from app.core.config import AppConfig
from bot.account_health import AccountHealthMonitor
from bot.account_safety import clamp_limits, effective_limits, safe_default_limits
from bot.rate_limiter import AccountRateLimiter


TRUSTED_STATUSES = {"trusted", "logged_in"}
NEEDS_VERIFY_STATUSES = {
    "needs_verify",
    "waiting_manual",
    "need_2fa",
    "checkpoint",
    "captcha",
    "invalid",
}


class AccountOrchestrator:
    def __init__(self, runtime_store):
        self.store = runtime_store
        self.health = AccountHealthMonitor(runtime_store)
        self.limiter = AccountRateLimiter(runtime_store)

    def trust_for_account(self, account_id: int) -> dict:
        account = self.store.get_account(account_id) or {}
        session = self.store.get_latest_session(account.get("user_id") or 0, account_id=account_id)
        blocked, block_reason = self.health.is_blocked(account_id)
        if blocked:
            return {
                "trust": "blocked",
                "reason": block_reason,
                "account": account,
                "session": session,
                "can_use": False,
            }
        status = (session or {}).get("status") or account.get("last_status") or "unknown"
        valid = bool((session or {}).get("session_valid"))
        if status in TRUSTED_STATUSES and valid:
            return {
                "trust": "trusted",
                "reason": "Session validated",
                "account": account,
                "session": session,
                "can_use": True,
            }
        if status in NEEDS_VERIFY_STATUSES or (session and session.get("checkpoint_detected")):
            return {
                "trust": "needs_verify",
                "reason": (session or {}).get("reason") or status,
                "account": account,
                "session": session,
                "can_use": False,
            }
        if status in TRUSTED_STATUSES and not valid:
            return {
                "trust": "needs_verify",
                "reason": "Session expired — run Prepare Account",
                "account": account,
                "session": session,
                "can_use": False,
            }
        return {
            "trust": "unknown",
            "reason": "Account not prepared yet",
            "account": account,
            "session": session,
            "can_use": False,
        }

    def list_account_trust(self, user_id: int) -> List[dict]:
        rows = []
        for account in self.store.list_accounts(user_id):
            trust = self.trust_for_account(int(account["id"]))
            item = dict(account)
            item["trust"] = trust["trust"]
            item["trust_reason"] = trust["reason"]
            item["can_use"] = trust["can_use"]
            item["session"] = trust.get("session")
            item["posts_last_hour"] = self.store.count_account_posts(int(account["id"]), hours=1)
            item["posts_last_day"] = self.store.count_account_posts(int(account["id"]), hours=24)
            limits = effective_limits(account)
            item.update(
                {
                    "effective_hourly_limit": limits["hourly_limit"],
                    "effective_daily_limit": limits["daily_limit"],
                    "warmup": limits["warmup"],
                    "warmup_days_left": limits["warmup_days_left"],
                    "account_age_days": limits["account_age_days"],
                    "limit_source": limits["source"],
                }
            )
            allowed, reason = self.limiter.can_post(int(account["id"]))
            item["can_post"] = allowed and trust["can_use"]
            item["rate_limit_reason"] = reason
            rows.append(item)
        return rows

    def pick_account(
        self,
        user_id: int,
        preferred_account_id: Optional[int] = None,
        *,
        require_trusted: bool = True,
        exclude_ids: Optional[set[int]] = None,
    ) -> Tuple[Optional[dict], str]:
        """Pick best account for posting/fetch. Prefers primary + high health + priority."""
        exclude_ids = exclude_ids or set()
        accounts = self.list_account_trust(user_id)
        if preferred_account_id:
            for acc in accounts:
                if int(acc["id"]) == int(preferred_account_id):
                    if int(acc["id"]) in exclude_ids:
                        break
                    if require_trusted and not acc.get("can_use"):
                        return None, acc.get("trust_reason") or "Session not trusted"
                    if not acc.get("can_post") and acc.get("rate_limit_reason"):
                        return None, acc["rate_limit_reason"]
                    return acc, ""
            # preferred not usable — fall through to rotation

        candidates = []
        for acc in accounts:
            aid = int(acc["id"])
            if aid in exclude_ids:
                continue
            if not acc.get("is_active", True):
                continue
            if require_trusted and not acc.get("can_use"):
                continue
            if not acc.get("can_post", True):
                continue
            score = int(acc.get("health_score") or 100)
            priority = int(acc.get("priority") or 0)
            primary_boost = 20 if acc.get("is_primary") else 0
            candidates.append((score + priority + primary_boost, priority, score, acc))

        if not candidates:
            return None, "No trusted/available accounts. Prepare an account first."
        candidates.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        return candidates[0][3], ""

    def mark_needs_verify(self, user_id: int, account_id: int, reason: str, *, checkpoint: bool = False, needs_2fa: bool = False) -> None:
        self.store.record_session(
            user_id=user_id,
            account_id=account_id,
            status="needs_verify",
            reason=reason,
            session_valid=0,
            checkpoint_detected=checkpoint,
            needs_2fa=needs_2fa,
            last_validated_at=datetime.utcnow().isoformat(),
        )
        self.store.update_account_status(account_id, "needs_verify", reason)
        cooldown_minutes = max(1, int(AppConfig.ACCOUNT_COOLDOWN_MINUTES))
        cooldown = datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes)
        account = self.store.get_account(account_id) or {}
        self.store.update_account_health(
            account_id,
            health_score=max(0, int(account.get("health_score") or 100) - 15),
            consecutive_failures=int(account.get("consecutive_failures") or 0) + 1,
            cooldown_until=cooldown.isoformat(),
            last_error=reason,
        )

    def mark_trusted(self, user_id: int, account_id: int, profile_dir: Optional[str] = None) -> None:
        now = datetime.utcnow().isoformat()
        self.store.record_session(
            user_id=user_id,
            account_id=account_id,
            status="trusted",
            reason="Prepared / validated",
            profile_dir=profile_dir,
            session_valid=1,
            checkpoint_detected=0,
            needs_2fa=0,
            last_validated_at=now,
            cookies_last_synced=now,
        )
        self.store.update_account_status(account_id, "trusted", None)
        account = self.store.get_account(account_id) or {}
        self.store.update_account_health(
            account_id,
            health_score=min(100, int(account.get("health_score") or 100) + 5),
            consecutive_failures=0,
            cooldown_until=None,
            last_error=None,
        )

    def clear_cooldown(self, user_id: int, account_id: int) -> Tuple[bool, str]:
        account = self.store.get_account(account_id)
        if not account or int(account.get("user_id") or 0) != int(user_id):
            return False, "Account not found"
        self.store.update_account_health(
            account_id,
            health_score=int(account.get("health_score") or 100),
            consecutive_failures=0,
            cooldown_until=None,
            last_error=None,
        )
        return True, "Cooldown cleared"

    def next_account_after_failure(
        self,
        user_id: int,
        failed_account_id: int,
        reason: str,
        *,
        checkpoint: bool = False,
    ) -> Tuple[Optional[dict], str]:
        self.mark_needs_verify(user_id, failed_account_id, reason, checkpoint=checkpoint)
        return self.pick_account(
            user_id,
            preferred_account_id=None,
            require_trusted=True,
            exclude_ids={int(failed_account_id)},
        )

    @staticmethod
    def normalize_new_account_limits(hourly_limit: int, daily_limit: int, *, is_new: bool) -> Tuple[int, int]:
        hourly, daily = clamp_limits(int(hourly_limit or 0), int(daily_limit or 0))
        if is_new and hourly <= 0 and daily <= 0:
            return safe_default_limits()
        if hourly <= 0:
            hourly = AppConfig.DEFAULT_HOURLY_POST_LIMIT
        if daily <= 0:
            daily = AppConfig.DEFAULT_DAILY_POST_LIMIT
        return clamp_limits(hourly, daily)
