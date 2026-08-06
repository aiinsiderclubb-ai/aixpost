"""Telegram report builders and send helpers for AIPostX."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from bot.analytics_db import analytics_db

logger = logging.getLogger(__name__)


def _esc(text: Any) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def resolve_bot_token(explicit: Optional[str] = None) -> str:
    if explicit and explicit not in ("YOUR_BOT_TOKEN_HERE", "test_token_for_development"):
        return explicit.strip()
    for key in ("TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN"):
        value = (os.environ.get(key) or "").strip()
        if value and value not in ("YOUR_BOT_TOKEN_HERE", "test_token_for_development"):
            return value
    return ""


def send_telegram_html(chat_id: str, message: str, bot_token: Optional[str] = None) -> bool:
    token = resolve_bot_token(bot_token)
    chat = str(chat_id or "").strip()
    if not token or not chat:
        logger.warning("Telegram send skipped: missing token or chat_id")
        return False
    if token == "test_token_for_development":
        logger.info("TEST MODE Telegram → %s: %s", chat, message[:200])
        return True
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": chat,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=15,
        )
        if response.status_code == 200 and response.json().get("ok"):
            return True
        logger.warning("Telegram API failed: %s %s", response.status_code, response.text[:300])
        return False
    except Exception as exc:
        logger.error("Telegram send error: %s", exc)
        return False


def format_daily_digest(stats: Dict[str, Any], user_label: str = "") -> str:
    day = stats.get("day") or datetime.utcnow().strftime("%Y-%m-%d")
    posts = int(stats.get("posts_today") or 0)
    groups = int(stats.get("groups_today") or 0)
    eng = float(stats.get("avg_engagement_pct") or 0)
    likes = int(stats.get("likes") or 0)
    comments = int(stats.get("comments") or 0)
    shares = int(stats.get("shares") or 0)
    score = float(stats.get("avg_score") or 0)
    success = int(stats.get("lifetime_success") or 0)
    failed = int(stats.get("lifetime_failed") or 0)
    week = int(stats.get("posts_7d") or 0)
    lifetime_total = success + failed
    lifetime_rate = (success / lifetime_total * 100) if lifetime_total else 0.0

    who = f" · {_esc(user_label)}" if user_label else ""
    lines = [
        f"📅 <b>Daily digest{who}</b>",
        f"<i>{_esc(day)} UTC</i>",
        "",
        "<b>Today</b>",
        f"• Posts: <b>{posts}</b> across <b>{groups}</b> groups",
        f"• Avg engagement: <b>{eng:.1f}%</b> · score <b>{score:.0f}</b>",
        f"• Reactions: 👍 {likes} · 💬 {comments} · ↗ {shares}",
        "",
        "<b>Rolling</b>",
        f"• Last 7 days posts: <b>{week}</b>",
        f"• Lifetime group success: <b>{success}</b> / fail <b>{failed}</b> ({lifetime_rate:.0f}%)",
    ]

    top = stats.get("top_groups") or []
    if top:
        lines.append("")
        lines.append("<b>Top groups today</b>")
        for idx, row in enumerate(top[:5], start=1):
            name = _esc((row.get("name") or "Group")[:40])
            lines.append(
                f"{idx}. {name} — {int(row.get('posts') or 0)} posts, "
                f"{float(row.get('engagement_pct') or 0):.1f}% eng"
            )
    elif posts == 0:
        lines.append("")
        lines.append("<i>No posts recorded today. Run a campaign or check account trust.</i>")

    lines.append("")
    lines.append("AIPostX analytics")
    return "\n".join(lines)


def build_daily_digest_for_user(user_id: int, user_label: str = "", day: Optional[str] = None) -> str:
    stats = analytics_db.get_daily_digest(int(user_id), day=day)
    return format_daily_digest(stats, user_label=user_label)


def format_session_report(
    *,
    success: int,
    failed: int,
    total_groups: int,
    elapsed_minutes: int,
    session_restarts: int = 0,
    use_templates: bool = False,
    template_mode: str = "",
    template_count: int = 0,
    failed_samples: Optional[Sequence[Tuple[str, str]]] = None,
    campaign_name: str = "",
    account_label: str = "",
) -> str:
    processed = success + failed
    rate = (success / processed * 100) if processed else 0.0
    if failed == 0 and success > 0:
        emoji, status = "🎉", "Session completed — all posts succeeded"
    elif success > failed:
        emoji, status = "✅", "Session completed — mostly successful"
    elif success == 0 and failed > 0:
        emoji, status = "🛑", "Session failed — no successful posts"
    else:
        emoji, status = "⚠️", "Session completed — high error rate"

    lines = [f"{emoji} <b>{_esc(status)}</b>", ""]
    if campaign_name:
        lines.append(f"📌 Campaign: <b>{_esc(campaign_name)}</b>")
    if account_label:
        lines.append(f"👤 Account: <b>{_esc(account_label)}</b>")
    if campaign_name or account_label:
        lines.append("")

    lines.extend(
        [
            "<b>Results</b>",
            f"✅ Success: <b>{success}</b>",
            f"❌ Failed: <b>{failed}</b>",
            f"📝 Processed: <b>{processed}</b> / {total_groups}",
            f"🎯 Success rate: <b>{rate:.1f}%</b>",
            f"⏱ Duration: <b>{elapsed_minutes} min</b>",
        ]
    )
    if session_restarts:
        lines.append(f"🔄 Browser restarts: <b>{session_restarts}</b>")
    if use_templates:
        lines.append(
            f"🧠 Templates: <b>{template_count}</b> ({_esc(template_mode or 'random')})"
        )

    samples = list(failed_samples or [])[:5]
    if samples:
        lines.append("")
        lines.append("<b>Failed samples</b>")
        for name, reason in samples:
            short_name = _esc((name or "group")[:32])
            short_reason = _esc((reason or "error")[:60])
            lines.append(f"• <code>{short_name}</code> — <i>{short_reason}</i>")

    remaining = max(0, total_groups - processed)
    if remaining:
        lines.append("")
        lines.append(f"⏭ Remaining in queue: <b>{remaining}</b> (resume from Tasks)")

    return "\n".join(lines)


def format_batch_report(
    *,
    batch_num: int,
    batch_success: int,
    batch_failed: int,
    total_processed: int,
    total_groups: int,
    failed_groups: Optional[Sequence[Tuple[str, str]]] = None,
) -> str:
    batch_total = batch_success + batch_failed
    rate = (batch_success / batch_total * 100) if batch_total else 0.0
    overall = (total_processed / total_groups * 100) if total_groups else 0.0
    if batch_failed == 0:
        emoji = "🎉"
    elif batch_success >= batch_failed:
        emoji = "✅"
    else:
        emoji = "⚠️"

    lines = [
        f"{emoji} <b>Batch #{batch_num}</b>",
        "",
        f"✅ {batch_success} · ❌ {batch_failed} · rate <b>{rate:.0f}%</b>",
        f"📈 Progress: <b>{total_processed}/{total_groups}</b> ({overall:.0f}%)",
    ]
    failed = list(failed_groups or [])
    if failed:
        lines.append("")
        lines.append("<b>Failures</b>")
        for name, reason in failed[:5]:
            lines.append(
                f"• <code>{_esc((name or '')[:30])}</code> — <i>{_esc((reason or '')[:50])}</i>"
            )
        if len(failed) > 5:
            lines.append(f"… +{len(failed) - 5} more")
    return "\n".join(lines)


def format_verification_alert(
    *,
    status: str,
    reason: str = "",
    headless: bool = False,
) -> str:
    labels = {
        "need_2fa": ("🔐", "Two-factor authentication required"),
        "checkpoint": ("🛡️", "Facebook checkpoint required"),
        "captcha": ("🧩", "CAPTCHA required"),
        "waiting_manual": ("🖐️", "Manual verification required"),
    }
    emoji, title = labels.get(status, ("⚠️", "Manual verification required"))
    lines = [
        f"{emoji} <b>{_esc(title)}</b>",
        "",
        _esc(reason or "Open the Chrome window and complete the challenge."),
        "",
        "<b>What to do</b>",
        "1. Use a <b>visible</b> Chrome window (headless cannot pass this)",
        "2. Complete 2FA / CAPTCHA / checkpoint in the browser",
        "3. Click <b>Я прошёл CAPTCHA</b> / Resume in the dashboard",
    ]
    if headless:
        lines.append("")
        lines.append("ℹ️ Bot will try to reopen Chrome in visible mode automatically.")
    return "\n".join(lines)


def send_daily_digests(
    recipients: List[Dict[str, Any]],
    bot_token: Optional[str] = None,
) -> Dict[str, int]:
    """
    recipients: list of {user_id, chat_id, label?}
    """
    sent = skipped = failed = 0
    for row in recipients:
        user_id = int(row["user_id"])
        chat_id = row.get("chat_id")
        if not chat_id:
            skipped += 1
            continue
        text = build_daily_digest_for_user(user_id, user_label=row.get("label") or "")
        if send_telegram_html(chat_id, text, bot_token=bot_token):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "skipped": skipped, "failed": failed}
