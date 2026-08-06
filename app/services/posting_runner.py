"""Shared posting execution for local threads and RQ workers."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Callable, Optional

from app.core.config import AppConfig
from app.services.posting_utils import poster_status_to_task_status
from app.services.task_control import CooperativeTaskControl, TaskStopped
from bot.account_health import AccountHealthMonitor
from bot.rate_limiter import AccountRateLimiter


def execute_posting_task(
    *,
    task_id: int,
    user_id: int,
    username: str,
    password: str,
    message: str,
    group_urls: list,
    runtime_store,
    headless: bool = True,
    use_templates: bool = False,
    template_mode: str = "random",
    account_id: Optional[int] = None,
    account_label: Optional[str] = None,
    campaign_name: str = "",
    profile_dir: Optional[str] = None,
    skip_success_urls: Optional[set[str]] = None,
    broadcast_user: Optional[Callable[[str, dict], None]] = None,
    record_session: Optional[Callable[..., None]] = None,
    poster_instances: Optional[dict] = None,
    global_poster_holder: Optional[dict] = None,
) -> dict:
    from bot.fb_poster import FacebookGroupPoster

    poster = FacebookGroupPoster(
        headless=headless,
        user_id=user_id,
        use_profile=True,
        profile_dir=profile_dir,
    )
    poster.username = username
    poster.password = password
    AppConfig.overlay_bot_secrets_from_env(poster)

    if account_id:
        account = runtime_store.get_account(account_id)
        if account:
            poster.account_id = account_id
            poster.hourly_limit = int(account.get("hourly_limit") or 0)
            poster.daily_limit = int(account.get("daily_limit") or 0)
            if account.get("profile_dir"):
                poster.profile_dir = account["profile_dir"]

    poster.rate_limiter = AccountRateLimiter(runtime_store)
    poster.health_monitor = AccountHealthMonitor(runtime_store)
    poster.skip_success_urls = skip_success_urls or set()

    if global_poster_holder is not None:
        global_poster_holder["instance"] = poster
    if poster_instances is not None:
        poster_instances[user_id] = poster

    temp_dir = os.path.join(AppConfig.PROJECT_ROOT, "tmp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_groups_path = os.path.join(temp_dir, f"post_groups_{user_id}_{task_id}.txt")
    with open(temp_groups_path, "w", encoding="utf-8") as handle:
        for url in group_urls:
            handle.write(url + "\n")

    def _emit(event: str, data: dict):
        if broadcast_user:
            broadcast_user(event, data)

    def _push_event(message: str, level: str = "info", event_type: str = "log", metadata: Optional[dict] = None):
        runtime_store.append_task_event(task_id, message, level=level, event_type=event_type, metadata=metadata or {})
        _emit("posting_event", {"task_id": task_id, "level": level, "message": message})

    def _sync_status(status: str, error: Optional[str] = None, snapshot: Optional[dict] = None):
        runtime_store.update_task(
            task_id,
            status=poster_status_to_task_status(status),
            heartbeat_at=datetime.utcnow().isoformat(),
            error_message=error,
            result_json=snapshot or {},
        )
        _emit("posting_status", {"task_id": task_id, "status": status, "error": error})

    def _sync_session(status: str, reason: Optional[str] = None, snapshot: Optional[dict] = None):
        if record_session:
            record_session(
                user_id=user_id,
                account_id=account_id,
                status=status,
                reason=reason or "",
                profile_dir=poster.profile_dir,
                session_valid=status in ("logged_in", "trusted"),
                needs_2fa=status == "need_2fa",
                checkpoint_detected=status == "checkpoint",
                last_validated_at=datetime.utcnow().isoformat(),
            )
        # Auto-pause account trust on checkpoint / 2FA / captcha; suggest next account
        if account_id and status in ("checkpoint", "need_2fa", "captcha", "needs_verify", "waiting_manual"):
            try:
                from app.services.account_orchestrator import AccountOrchestrator
                orch = AccountOrchestrator(runtime_store)
                next_acc, _ = orch.next_account_after_failure(
                    user_id,
                    int(account_id),
                    reason or status,
                    checkpoint=status in ("checkpoint", "captcha"),
                )
                meta = {
                    "paused_account_id": int(account_id),
                    "suggested_account_id": int(next_acc["id"]) if next_acc else None,
                    "reason": reason or status,
                    "verification": status,
                }
                runtime_store.update_task(
                    task_id,
                    status="waiting_manual",
                    heartbeat_at=datetime.utcnow().isoformat(),
                    result_json=meta,
                )
                _emit("account_rotation", meta)
                _emit(
                    "verification_required",
                    {
                        "status": status,
                        "reason": reason or status,
                        "message": "Complete CAPTCHA/2FA in visible Chrome, then Resume.",
                    },
                )
            except Exception:
                pass
        if account_id and status in ("logged_in", "trusted"):
            try:
                from app.services.account_orchestrator import AccountOrchestrator
                AccountOrchestrator(runtime_store).mark_trusted(
                    user_id, int(account_id), profile_dir=poster.profile_dir
                )
            except Exception:
                pass
        _emit("session_status", {"status": status, "reason": reason, "snapshot": snapshot or {}})

    def _sync_group(group_id: str, payload: dict):
        runtime_store.upsert_group_status(
            task_id,
            payload.get("url") or group_id,
            payload.get("status", "Pending"),
            group_key=group_id,
            error_reason=payload.get("error"),
            group_name=payload.get("name") or group_id,
            account_label=account_label,
        )
        if payload.get("status") in ("Success", "Failed"):
            runtime_store.upsert_group_workspace(
                user_id,
                payload.get("url") or group_id,
                group_name=payload.get("name") or group_id,
                last_posted_at=datetime.utcnow().isoformat(),
                last_post_status=payload.get("status", "").lower(),
                last_campaign_name=campaign_name or None,
            )

    poster.runtime_event_callback = _push_event
    poster.status_change_callback = _sync_status
    poster.session_state_callback = _sync_session
    poster.group_status_callback = _sync_group
    control = CooperativeTaskControl(runtime_store, task_id, user_id)
    control_callbacks = {
        "on_pause": poster.pause_posting_method,
        "on_resume": poster.resume_posting_method,
        "on_stop": poster.stop_posting_method,
    }
    poster.task_control_callback = lambda: control.wait_while_paused(**control_callbacks)
    poster.task_control_sleep = lambda seconds: control.sleep(seconds, **control_callbacks)

    if record_session:
        record_session(user_id, account_id, "starting", "task_started", profile_dir=poster.profile_dir)
    _push_event("Posting task accepted", event_type="system")
    runtime_store.update_task(task_id, status="running", started_at=datetime.utcnow().isoformat(), resumable=1)

    try:
        control.wait_while_paused(**control_callbacks)
        ok = poster.post_to_multiple_groups(
            message=message,
            groups_file=temp_groups_path,
            max_groups=len(group_urls),
            use_templates=use_templates,
            template_mode=template_mode,
        )
        snapshot = poster.get_status()
        final_status = "completed" if ok else poster_status_to_task_status(snapshot.get("status"))
        runtime_store.update_task(
            task_id,
            status=final_status,
            result_json=snapshot,
            error_message=snapshot.get("error"),
            finished_at=datetime.utcnow().isoformat(),
        )
        return {
            "status": final_status,
            "task_id": task_id,
            "snapshot": snapshot,
            "error_message": snapshot.get("error"),
        }
    except TaskStopped:
        snapshot = poster.get_status()
        runtime_store.update_task(
            task_id,
            status="cancelled",
            result_json=snapshot,
            error_message="Stopped by user",
            finished_at=datetime.utcnow().isoformat(),
            acknowledged_state="cancelled",
            requested_action="none",
        )
        runtime_store.append_task_event(
            task_id, "Posting stopped by user", event_type="control_result",
        )
        return {
            "status": "cancelled",
            "task_id": task_id,
            "snapshot": snapshot,
            "error_message": "Stopped by user",
        }
    finally:
        try:
            if os.path.exists(temp_groups_path):
                os.remove(temp_groups_path)
        except OSError:
            pass
