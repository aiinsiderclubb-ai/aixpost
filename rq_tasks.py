import os
import json
import sqlite3
from datetime import datetime
from cryptography.fernet import Fernet

from app.core.config import AppConfig
from app.services.posting_runner import execute_posting_task
from app.services.event_bridge import publish_user_event
from platform_runtime import RuntimeStore


def _get_cipher() -> Fernet:
    return Fernet(AppConfig.get_fernet_key().encode())


def _get_db_path() -> str:
    return AppConfig.APP_SQLITE_PATH


def _get_runtime_store() -> RuntimeStore:
    return RuntimeStore(
        AppConfig.RUNTIME_DB_PATH,
        database_url=AppConfig.runtime_database_url(),
    )


def _redis():
    try:
        import redis
        return redis.from_url(AppConfig.REDIS_URL)
    except Exception:
        return None


def _broadcast(user_id: int, event: str, data: dict) -> None:
    publish_user_event(_redis(), user_id, event, data)


def _get_user_facebook_credentials(user_id: int) -> tuple[str, str]:
    db_path = _get_db_path()
    cipher = _get_cipher()
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT facebook_username, facebook_password FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"User {user_id} not found")
        fb_user, fb_pass_enc = row[0] or "", row[1] or ""
        fb_pass = ""
        if fb_pass_enc:
            try:
                fb_pass = cipher.decrypt(fb_pass_enc.encode()).decode()
            except Exception:
                fb_pass = ""
        return fb_user, fb_pass


def run_fetch_task(user_id: int, headless: bool = True, use_session: bool = True) -> dict:
    """Legacy fetch task without runtime integration."""
    username, password = _get_user_facebook_credentials(user_id)
    if not username or not password:
        raise RuntimeError("Facebook credentials missing for user")
    from bot.group_fetcher import FacebookGroupFetcher

    fetcher = FacebookGroupFetcher(
        username=username,
        password=password,
        headless=headless,
        use_session=use_session,
        user_id=user_id,
    )
    groups = fetcher.fetch_groups()
    if groups is None:
        raise RuntimeError(fetcher.error or "Failed to fetch groups")
    base_dir = os.path.join(AppConfig.PROJECT_ROOT, "user_data", "groups")
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"autofetched_groups_{user_id}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(groups or [], handle, ensure_ascii=False, indent=2)
    return {"status": "completed", "groups": len(groups or [])}


def run_fetch_task_v2(task_id: int, user_id: int, headless: bool = True, use_session: bool = True) -> dict:
    from app.services.task_control import CooperativeTaskControl, DurableControlMonitor

    store = _get_runtime_store()
    store.update_task(task_id, status="running", started_at=datetime.utcnow().isoformat())
    store.append_task_event(task_id, "RQ fetch worker started", event_type="system")
    try:
        task = store.get_task_for_user(task_id, user_id) or {}
        payload = task.get("payload") or {}
        headless = bool(payload.get("headless", headless))
        use_session = bool(payload.get("use_session", use_session))
        account_id = payload.get("account_id")
        username, password = _get_user_facebook_credentials(user_id)
        profile_dir = payload.get("profile_dir")
        if account_id:
            account = store.get_account(int(account_id))
            if not account or int(account.get("user_id")) != int(user_id):
                raise RuntimeError("Selected account does not belong to the task user")
            username = account.get("login_email") or username
            if account.get("encrypted_password"):
                password = _get_cipher().decrypt(account["encrypted_password"].encode()).decode()
            profile_dir = account.get("profile_dir") or profile_dir

        from bot.group_fetcher import FacebookGroupFetcher

        def _progress(payload_progress: dict):
            store.append_task_event(
                task_id,
                payload_progress.get("message") or payload_progress.get("step") or "fetch-progress",
                event_type="progress",
                metadata=payload_progress,
            )
            _broadcast(user_id, "fetch_progress", payload_progress)

        fetcher = FacebookGroupFetcher(
            username=username,
            password=password,
            headless=headless,
            use_session=use_session,
            user_id=user_id,
            progress_callback=_progress,
        )
        if profile_dir:
            fetcher.profile_dir = profile_dir
        control = CooperativeTaskControl(store, task_id, user_id)
        control.checkpoint(allow_pause=False)
        with DurableControlMonitor(control, fetcher.cleanup):
            groups = fetcher.fetch_groups()
        if store.get_control_state(task_id, user_id).get("acknowledged_state") == "stopping":
            result = {"status": "cancelled", "error_message": "Stopped by user"}
            store.update_task(
                task_id, status="cancelled", acknowledged_state="cancelled",
                requested_action="none", result_json=result,
                finished_at=datetime.utcnow().isoformat(),
            )
            return result
        if groups is None:
            raise RuntimeError(fetcher.error or "Failed to fetch groups")
        base_dir = os.path.join(AppConfig.PROJECT_ROOT, "user_data", "groups")
        os.makedirs(base_dir, exist_ok=True)
        path = os.path.join(base_dir, f"autofetched_groups_{user_id}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(groups or [], handle, ensure_ascii=False, indent=2)
        result = {"status": "completed", "groups_found": len(groups or []), "account_id": account_id}
        store.update_task(task_id, status="completed", result_json=result, finished_at=datetime.utcnow().isoformat())
        store.append_task_event(task_id, f"Fetched {len(groups or [])} groups", event_type="result")
        _broadcast(user_id, "fetch_progress", {"status": "completed", "total_groups": len(groups or []), "progress": 100})
        return result
    except Exception as exc:
        store.update_task(task_id, status="failed", error_message=str(exc), finished_at=datetime.utcnow().isoformat())
        _broadcast(user_id, "fetch_progress", {"status": "failed", "error": str(exc)})
        raise


def run_post_task(
    user_id: int,
    message: str,
    group_urls: list,
    headless: bool = True,
    use_templates: bool = False,
    template_mode: str = "random",
) -> dict:
    """Legacy posting task without runtime integration."""
    username, password = _get_user_facebook_credentials(user_id)
    from bot.fb_poster import FacebookGroupPoster

    poster = FacebookGroupPoster(headless=headless, user_id=user_id, use_profile=True)
    poster.username = username
    poster.password = password
    AppConfig.overlay_bot_secrets_from_env(poster)
    temp_dir = os.path.join(AppConfig.PROJECT_ROOT, "tmp")
    os.makedirs(temp_dir, exist_ok=True)
    groups_file = os.path.join(temp_dir, f"legacy_post_{user_id}.txt")
    with open(groups_file, "w", encoding="utf-8") as handle:
        for url in group_urls:
            handle.write(url + "\n")
    poster.post_to_multiple_groups(
        message,
        groups_file=groups_file,
        use_templates=use_templates,
        template_mode=template_mode,
    )
    return {"status": "completed"}


def run_post_task_v2(task_id: int, user_id: int) -> dict:
    store = _get_runtime_store()
    try:
        task = store.get_task_for_user(task_id, user_id)
        if not task:
            raise RuntimeError(f"Task {task_id} not found for user")
        payload = task.get("payload") or {}
        username, password = _get_user_facebook_credentials(user_id)
        account_id = payload.get("account_id")
        if account_id:
            account = store.get_account(int(account_id))
            if not account or int(account.get("user_id")) != user_id:
                raise RuntimeError("Selected account does not belong to the task user")
            username = account.get("login_email") or username
            if account.get("encrypted_password"):
                password = _get_cipher().decrypt(account["encrypted_password"].encode()).decode()

        skip_success = set()
        resumed_from = payload.get("resumed_from_task_id")
        if resumed_from:
            skip_success = store.get_success_group_urls(int(resumed_from))

        def _broadcast_user(event: str, data: dict):
            _broadcast(user_id, event, data)

        def _record_session(user_id_arg, account_id_arg, status, reason="", **extra):
            store.record_session(
                user_id=user_id_arg,
                account_id=account_id_arg,
                status=status,
                reason=reason,
                **extra,
            )

        return execute_posting_task(
            task_id=task_id,
            user_id=user_id,
            username=username,
            password=password,
            message=payload.get("message", ""),
            group_urls=payload.get("group_urls", []),
            runtime_store=store,
            headless=bool(payload.get("headless", True)),
            use_templates=bool(payload.get("use_templates", False)),
            template_mode=payload.get("template_mode", "random"),
            account_id=int(account_id) if account_id else None,
            account_label=payload.get("account_label"),
            campaign_name=payload.get("campaign_name", ""),
            profile_dir=payload.get("profile_dir"),
            skip_success_urls=skip_success,
            broadcast_user=_broadcast_user,
            record_session=_record_session,
        )
    except Exception as exc:
        store.append_task_event(task_id, str(exc), level="error", event_type="exception")
        store.update_task(
            task_id,
            status="failed",
            error_message=str(exc),
            finished_at=datetime.utcnow().isoformat(),
        )
        raise


def run_analytics_batch_task(limit: int = 10) -> dict:
    """RQ worker task: scrape pending post metrics via facebook-scraper."""
    from bot.analytics_collector import process_pending_checks

    return process_pending_checks(limit=limit)
