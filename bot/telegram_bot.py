"""Inbound Telegram bot: schedule posting via chat commands.

Commands (chat must match a saved TelegramSettings.chat_id):
  /help
  /status
  /limits
  /schedule HH:MM | message text
  /schedule HH:MM max=N | message text
  /jobs
  /cancel <job_id>
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from bot.telegram_reports import resolve_bot_token, send_telegram_html

logger = logging.getLogger(__name__)

_HELP = """<b>AIPostX bot</b>

<code>/schedule HH:MM | your post text</code>
Daily post at that time (UTC) to whitelist groups.

Optional: <code>/schedule 09:30 max=5 | Hello</code>

<code>/jobs</code> — list scheduled jobs
<code>/cancel ID</code> — cancel a job
<code>/status</code> — accounts / cooldown
<code>/limits</code> — effective caps + warm-up
<code>/help</code> — this message

Connect Chat ID on the Telegram page in the dashboard first."""

_UPDATE_OFFSET = None
_POLL_THREAD: Optional[threading.Thread] = None
_STOP = threading.Event()


def _resolve_user_by_chat(chat_id: str) -> Optional[int]:
    from run_test_v2 import TelegramSettings, app

    chat = str(chat_id or "").strip()
    if not chat:
        return None
    with app.app_context():
        row = TelegramSettings.query.filter_by(chat_id=chat, is_active=True).first()
        if not row:
            # Also match string/int variants
            for settings in TelegramSettings.query.filter_by(is_active=True).all():
                if str(settings.chat_id).strip() == chat:
                    return int(settings.user_id)
            return None
        return int(row.user_id)


def _whitelist_group_urls(user_id: int, max_groups: int = 10) -> List[str]:
    from run_test_v2 import runtime_store

    workspace = runtime_store.get_group_workspace_map(int(user_id)) or {}
    urls: List[str] = []
    for url, meta in workspace.items():
        if not url:
            continue
        if meta and meta.get("is_whitelisted"):
            urls.append(url)
        if len(urls) >= max_groups:
            break
    if urls:
        return urls[:max_groups]

    # Fallback: recent autofetch file for the user
    try:
        from run_test_v2 import _user_groups_path

        path = _user_groups_path(user_id)
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        groups = data if isinstance(data, list) else data.get("groups") or []
        for item in groups:
            url = item.get("url") if isinstance(item, dict) else str(item)
            if url:
                urls.append(url)
            if len(urls) >= max_groups:
                break
    except Exception:
        pass
    return urls[:max_groups]


def _parse_schedule(text: str) -> Tuple[Optional[str], Optional[str], int, str]:
    """Return (cron, hhmm, max_groups, message) or error in message with cron None."""
    body = (text or "").strip()
    body = re.sub(r"^/schedule(@\w+)?\s*", "", body, flags=re.I).strip()
    if not body:
        return None, None, 10, "Usage: /schedule HH:MM | message"

    max_groups = 10
    max_m = re.search(r"\bmax\s*=\s*(\d+)\b", body, flags=re.I)
    if max_m:
        max_groups = max(1, min(50, int(max_m.group(1))))
        body = (body[: max_m.start()] + body[max_m.end() :]).strip()

    if "|" in body:
        left, message = body.split("|", 1)
        left = left.strip()
        message = message.strip()
    else:
        parts = body.split(None, 1)
        left = parts[0] if parts else ""
        message = parts[1].strip() if len(parts) > 1 else ""

    time_m = re.match(r"^(\d{1,2}):(\d{2})$", left.strip())
    if not time_m:
        return None, None, max_groups, "Time must be HH:MM (UTC), e.g. 09:30"
    hour, minute = int(time_m.group(1)), int(time_m.group(2))
    if hour > 23 or minute > 59:
        return None, None, max_groups, "Invalid time"
    if not message:
        return None, None, max_groups, "Message text is required after |"

    cron = f"{minute} {hour} * * *"
    return cron, f"{hour:02d}:{minute:02d}", max_groups, message


def _create_job(user_id: int, cron: str, message: str, groups: List[str], name: str) -> Tuple[bool, str, Optional[dict]]:
    from run_test_v2 import ScheduledJob, app, db, job_scheduler

    if not groups:
        return False, "No groups found. Whitelist groups in the dashboard first.", None
    if job_scheduler is None:
        return False, "Job scheduler is not running on this process.", None

    with app.app_context():
        campaign = {
            "message": message,
            "target_groups": groups,
            "max_groups": len(groups),
            "use_templates": False,
            "template_mode": "random",
        }
        job = ScheduledJob(
            user_id=user_id,
            name=name[:250],
            cron_expression=cron,
            campaign_data=json.dumps(campaign),
            status="active",
        )
        db.session.add(job)
        db.session.commit()
        job_data = {
            "name": job.name,
            "cron_expression": cron,
            "message": message,
            "target_groups": groups,
            "max_groups": len(groups),
            "use_templates": False,
            "template_mode": "random",
        }
        ok = job_scheduler.schedule_job(job.id, user_id, job_data)
        if not ok:
            db.session.delete(job)
            db.session.commit()
            return False, "Failed to register cron job", None
        return True, "Scheduled", job.to_dict()


def _list_jobs(user_id: int) -> List[dict]:
    from run_test_v2 import ScheduledJob, app

    with app.app_context():
        rows = (
            ScheduledJob.query.filter_by(user_id=user_id)
            .order_by(ScheduledJob.created_at.desc())
            .limit(20)
            .all()
        )
        return [j.to_dict() for j in rows]


def _cancel_job(user_id: int, job_id: int) -> Tuple[bool, str]:
    from run_test_v2 import ScheduledJob, app, db, job_scheduler

    with app.app_context():
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        if not job:
            return False, "Job not found"
        if job_scheduler:
            try:
                job_scheduler.delete_job(job_id)
            except Exception:
                pass
        job.status = "cancelled"
        db.session.commit()
        return True, f"Cancelled job #{job_id}"


def _status_text(user_id: int) -> str:
    from app.services.account_orchestrator import AccountOrchestrator
    from run_test_v2 import runtime_store

    orch = AccountOrchestrator(runtime_store)
    rows = orch.list_account_trust(user_id)
    if not rows:
        return "No accounts yet. Add one on /accounts."
    lines = ["<b>Accounts</b>"]
    for a in rows:
        warm = " · warm-up" if a.get("warmup") else ""
        cool = f" · cooldown until {a.get('cooldown_until')}" if a.get("cooldown_until") else ""
        lines.append(
            f"#{a.get('id')} {_esc(a.get('label') or a.get('login_email'))}: "
            f"{_esc(a.get('trust'))} · "
            f"{a.get('posts_last_hour') or 0}/{a.get('effective_hourly_limit')}/h · "
            f"{a.get('posts_last_day') or 0}/{a.get('effective_daily_limit')}/d"
            f"{warm}{cool}"
        )
    return "\n".join(lines)


def _limits_text(user_id: int) -> str:
    from app.core.config import AppConfig
    from app.services.account_orchestrator import AccountOrchestrator
    from run_test_v2 import runtime_store

    orch = AccountOrchestrator(runtime_store)
    rows = orch.list_account_trust(user_id)
    lines = [
        "<b>Safety limits</b>",
        f"Hard max: {AppConfig.HARD_MAX_HOURLY_POST_LIMIT}/h · {AppConfig.HARD_MAX_DAILY_POST_LIMIT}/d",
        f"Warm-up: first {AppConfig.ACCOUNT_WARMUP_DAYS}d → "
        f"{AppConfig.WARMUP_HOURLY_POST_LIMIT}/h · {AppConfig.WARMUP_DAILY_POST_LIMIT}/d",
        f"Cooldown: {AppConfig.ACCOUNT_COOLDOWN_MINUTES}m · "
        f"Auto-stop on 2FA: {'on' if AppConfig.AUTO_STOP_ON_VERIFICATION else 'off'}",
        "",
    ]
    for a in rows:
        lines.append(
            f"#{a.get('id')}: effective {a.get('effective_hourly_limit')}/h · "
            f"{a.get('effective_daily_limit')}/d"
            f" ({a.get('limit_source')}"
            f"{', ' + str(a.get('warmup_days_left')) + 'd left' if a.get('warmup') else ''})"
        )
    return "\n".join(lines)


def _esc(text: Any) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def handle_message(chat_id: str, text: str) -> str:
    user_id = _resolve_user_by_chat(chat_id)
    if not user_id:
        return (
            "Chat not linked. Open dashboard → Telegram, save your Chat ID, then retry."
        )

    cmd = (text or "").strip()
    lower = cmd.lower()

    if lower.startswith("/start") or lower.startswith("/help"):
        return _HELP

    if lower.startswith("/status"):
        return _status_text(user_id)

    if lower.startswith("/limits"):
        return _limits_text(user_id)

    if lower.startswith("/jobs"):
        jobs = _list_jobs(user_id)
        if not jobs:
            return "No scheduled jobs."
        lines = ["<b>Jobs</b>"]
        for j in jobs:
            next_run = j.get("next_run") or "—"
            lines.append(
                f"#{j['id']} {_esc(j.get('name'))} · <code>{_esc(j.get('cron_expression'))}</code> · "
                f"{_esc(j.get('status'))} · next { _esc(next_run) }"
            )
        return "\n".join(lines)

    if lower.startswith("/cancel"):
        parts = cmd.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return "Usage: /cancel JOB_ID"
        ok, msg = _cancel_job(user_id, int(parts[1]))
        return msg if ok else f"Error: {msg}"

    if lower.startswith("/schedule"):
        cron, hhmm, max_groups, message = _parse_schedule(cmd)
        if not cron:
            return message
        groups = _whitelist_group_urls(user_id, max_groups=max_groups)
        name = f"TG {hhmm} {datetime.utcnow().strftime('%m-%d %H:%M')}"
        ok, msg, job = _create_job(user_id, cron, message, groups, name)
        if not ok:
            return f"❌ {msg}"
        return (
            f"✅ Scheduled daily at <b>{_esc(hhmm)} UTC</b>\n"
            f"Job #{job['id']} · {len(groups)} group(s)\n"
            f"Preview: {_esc(message[:120])}"
        )

    return "Unknown command. Send /help"


def _api_get(token: str, method: str, params: Optional[dict] = None) -> dict:
    response = requests.get(
        f"https://api.telegram.org/bot{token}/{method}",
        params=params or {},
        timeout=35,
    )
    response.raise_for_status()
    return response.json()


def poll_loop(token: str) -> None:
    global _UPDATE_OFFSET
    logger.info("Telegram inbound bot polling started")
    while not _STOP.is_set():
        try:
            params: Dict[str, Any] = {"timeout": 25}
            if _UPDATE_OFFSET is not None:
                params["offset"] = _UPDATE_OFFSET
            data = _api_get(token, "getUpdates", params)
            if not data.get("ok"):
                time.sleep(3)
                continue
            for update in data.get("result") or []:
                _UPDATE_OFFSET = int(update["update_id"]) + 1
                message = update.get("message") or update.get("edited_message") or {}
                chat = message.get("chat") or {}
                chat_id = str(chat.get("id") or "")
                text = message.get("text") or ""
                if not chat_id or not text:
                    continue
                try:
                    reply = handle_message(chat_id, text)
                    send_telegram_html(chat_id, reply, bot_token=token)
                except Exception as exc:
                    logger.exception("Telegram command failed: %s", exc)
                    try:
                        send_telegram_html(chat_id, f"Error: {exc}", bot_token=token)
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("Telegram poll error: %s", exc)
            time.sleep(5)
    logger.info("Telegram inbound bot polling stopped")


def start_telegram_bot_polling() -> bool:
    """Start long-poll thread if TELEGRAM_BOT_POLLING and token are set."""
    global _POLL_THREAD
    from app.core.config import AppConfig

    if not AppConfig.TELEGRAM_BOT_POLLING:
        return False
    token = resolve_bot_token()
    if not token or token == "test_token_for_development":
        logger.info("Telegram bot polling skipped: no token")
        return False
    if _POLL_THREAD and _POLL_THREAD.is_alive():
        return True
    _STOP.clear()
    _POLL_THREAD = threading.Thread(
        target=poll_loop,
        args=(token,),
        name="telegram-bot-poll",
        daemon=True,
    )
    _POLL_THREAD.start()
    return True


def stop_telegram_bot_polling() -> None:
    _STOP.set()
