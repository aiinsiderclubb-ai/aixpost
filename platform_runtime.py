from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, Optional


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).isoformat()


class _RuntimeConn:
    """Thin DB adapter so call sites keep using conn.execute / lastrowid."""

    def __init__(self, backend: str, raw):
        self.backend = backend
        self.raw = raw
        if backend == "postgres":
            import psycopg2.extras
            self._cur = raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            raw.row_factory = sqlite3.Row
            self._cur = raw

    def _sql(self, sql: str) -> str:
        if self.backend == "postgres":
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql: str, params=None):
        sql = self._sql(sql)
        if self.backend == "postgres":
            if params is None:
                self._cur.execute(sql)
            else:
                self._cur.execute(sql, params)
        else:
            if params is None:
                self._cur = self.raw.execute(sql)
            else:
                self._cur = self.raw.execute(sql, params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def executescript(self, script: str) -> None:
        if self.backend == "postgres":
            for stmt in script.split(";"):
                stmt = stmt.strip()
                if stmt:
                    self._cur.execute(stmt)
        else:
            self.raw.executescript(script)

    def cursor(self):
        return self

    def commit(self) -> None:
        self.raw.commit()

    def close(self) -> None:
        if self.backend == "postgres":
            try:
                self._cur.close()
            except Exception:
                pass
        self.raw.close()

    @property
    def lastrowid(self):
        if self.backend == "postgres":
            self._cur.execute("SELECT LASTVAL() AS id")
            row = self._cur.fetchone()
            return int(row["id"] if isinstance(row, dict) else row[0])
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return getattr(self._cur, "rowcount", 0)


class RuntimeStore:
    def __init__(self, db_path: str, database_url: str | None = None):
        self.db_path = db_path
        self.database_url = (database_url or "").strip()
        self.backend = "postgres" if self.database_url.startswith("postgres") else "sqlite"
        self._lock = threading.RLock()
        if self.backend == "sqlite":
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self.ensure_schema()

    @contextmanager
    def connect(self):
        with self._lock:
            if self.backend == "postgres":
                import psycopg2
                raw = psycopg2.connect(self.database_url)
                conn = _RuntimeConn("postgres", raw)
            else:
                raw = sqlite3.connect(self.db_path, timeout=30)
                conn = _RuntimeConn("sqlite", raw)
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _schema_sql(self) -> str:
        pk = "SERIAL PRIMARY KEY" if self.backend == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        return f"""
                CREATE TABLE IF NOT EXISTS facebook_accounts (
                    id {pk},
                    user_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    login_email TEXT NOT NULL,
                    encrypted_password TEXT,
                    profile_dir TEXT,
                    is_active INTEGER DEFAULT 1,
                    is_primary INTEGER DEFAULT 0,
                    priority INTEGER DEFAULT 0,
                    hourly_limit INTEGER DEFAULT 0,
                    daily_limit INTEGER DEFAULT 0,
                    notes TEXT,
                    last_status TEXT DEFAULT 'unknown',
                    last_error TEXT,
                    last_login_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS facebook_sessions (
                    id {pk},
                    user_id INTEGER NOT NULL,
                    account_id INTEGER,
                    status TEXT NOT NULL,
                    reason TEXT,
                    profile_dir TEXT,
                    checkpoint_detected INTEGER DEFAULT 0,
                    needs_2fa INTEGER DEFAULT 0,
                    session_valid INTEGER DEFAULT 0,
                    session_expires_at TEXT,
                    last_validated_at TEXT,
                    cookies_last_synced TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS background_tasks (
                    id {pk},
                    user_id INTEGER NOT NULL,
                    task_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    queue_mode TEXT NOT NULL DEFAULT 'local_persistent',
                    task_key TEXT,
                    payload_json TEXT,
                    result_json TEXT,
                    error_message TEXT,
                    resumable INTEGER DEFAULT 0,
                    requested_action TEXT NOT NULL DEFAULT 'none',
                    acknowledged_state TEXT NOT NULL DEFAULT 'queued',
                    control_requested_at TEXT,
                    control_acknowledged_at TEXT,
                    heartbeat_at TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_events (
                    id {pk},
                    task_id INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_group_statuses (
                    id {pk},
                    task_id INTEGER NOT NULL,
                    group_key TEXT NOT NULL,
                    group_url TEXT,
                    group_name TEXT,
                    language_tag TEXT,
                    status TEXT NOT NULL,
                    error_reason TEXT,
                    template_label TEXT,
                    account_label TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, group_key)
                );

                CREATE TABLE IF NOT EXISTS group_workspace (
                    id {pk},
                    user_id INTEGER NOT NULL,
                    group_url TEXT NOT NULL,
                    group_name TEXT,
                    is_blacklisted INTEGER DEFAULT 0,
                    is_whitelisted INTEGER DEFAULT 0,
                    tags_json TEXT,
                    notes TEXT,
                    last_posted_at TEXT,
                    last_post_status TEXT,
                    last_campaign_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, group_url)
                );

                CREATE TABLE IF NOT EXISTS saved_group_filters (
                    id {pk},
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    is_default INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS template_records (
                    id {pk},
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    title TEXT,
                    folder TEXT,
                    tags_json TEXT,
                    is_active INTEGER DEFAULT 1,
                    weight REAL DEFAULT 1.0,
                    use_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_used_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, content)
                );

                CREATE TABLE IF NOT EXISTS account_post_log (
                    id {pk},
                    account_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    group_url TEXT,
                    success INTEGER DEFAULT 1,
                    posted_at TEXT NOT NULL
                );
                """

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            if self.backend == "postgres":
                # psycopg2 execute() accepts one statement; split on semicolons.
                for stmt in self._schema_sql().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(stmt)
            else:
                conn.executescript(self._schema_sql())
            self._migrate_schema(conn)

    def _table_columns(self, conn: _RuntimeConn, table: str) -> set[str]:
        if self.backend == "postgres":
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = ?
                """,
                (table,),
            ).fetchall()
            return {(row["column_name"] if isinstance(row, dict) else row[0]).lower() for row in rows}
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}

    def _migrate_schema(self, conn: _RuntimeConn) -> None:
        columns = self._table_columns(conn, "facebook_accounts")
        migrations = {
            "health_score": "ALTER TABLE facebook_accounts ADD COLUMN health_score INTEGER DEFAULT 100",
            "consecutive_failures": "ALTER TABLE facebook_accounts ADD COLUMN consecutive_failures INTEGER DEFAULT 0",
            "cooldown_until": "ALTER TABLE facebook_accounts ADD COLUMN cooldown_until TEXT",
        }
        for column, sql in migrations.items():
            if column not in columns:
                conn.execute(sql)
        task_columns = self._table_columns(conn, "background_tasks")
        task_migrations = {
            "requested_action": "ALTER TABLE background_tasks ADD COLUMN requested_action TEXT NOT NULL DEFAULT 'none'",
            "acknowledged_state": "ALTER TABLE background_tasks ADD COLUMN acknowledged_state TEXT NOT NULL DEFAULT 'queued'",
            "control_requested_at": "ALTER TABLE background_tasks ADD COLUMN control_requested_at TEXT",
            "control_acknowledged_at": "ALTER TABLE background_tasks ADD COLUMN control_acknowledged_at TEXT",
        }
        for column, sql in task_migrations.items():
            if column not in task_columns:
                conn.execute(sql)

    def get_account(self, account_id: int) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM facebook_accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None

    def update_account_health(
        self,
        account_id: int,
        *,
        health_score: int,
        consecutive_failures: int,
        cooldown_until: str | None = None,
        last_error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE facebook_accounts
                SET health_score = ?, consecutive_failures = ?, cooldown_until = ?,
                    last_error = COALESCE(?, last_error), updated_at = ?
                WHERE id = ?
                """,
                (health_score, consecutive_failures, cooldown_until, last_error, _utcnow_str(), account_id),
            )

    def record_account_post(self, account_id: int, user_id: int, group_url: str, success: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO account_post_log (account_id, user_id, group_url, success, posted_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account_id, user_id, group_url, 1 if success else 0, _utcnow_str()),
            )

    def count_account_posts(self, account_id: int, hours: int = 1) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM account_post_log
                WHERE account_id = ? AND success = 1 AND posted_at >= ?
                """,
                (account_id, cutoff),
            ).fetchone()
        return int(row["cnt"] if row else 0)

    def get_resumable_groups(self, task_id: int) -> list[str]:
        """Return group URLs that are not yet successfully posted for a task."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT group_url
                FROM task_group_statuses
                WHERE task_id = ? AND group_url IS NOT NULL
                  AND status NOT IN ('Success', 'Skipped')
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        urls = [row["group_url"] for row in rows if row["group_url"]]
        if urls:
            return urls
        task = self.get_task(task_id)
        if not task:
            return []
        payload = task.get("payload") or {}
        return [url for url in payload.get("group_urls", []) if url]

    def mark_stale_tasks(self, older_than_hours: int = 12) -> None:
        stale_before = (datetime.utcnow() - timedelta(hours=older_than_hours)).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE background_tasks
                SET status = 'failed',
                    error_message = COALESCE(error_message, 'Task interrupted by application restart'),
                    finished_at = COALESCE(finished_at, ?),
                    updated_at = ?
                WHERE status IN ('queued', 'running', 'waiting_manual', 'paused')
                  AND COALESCE(heartbeat_at, created_at) < ?
                """,
                (_utcnow_str(), _utcnow_str(), stale_before),
            )

    def cleanup_old_events(self, days: int = 14) -> None:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        with self.connect() as conn:
            conn.execute("DELETE FROM task_events WHERE created_at < ?", (cutoff,))

    def upsert_account(self, user_id: int, login_email: str, encrypted_password: str = "", **extra) -> int:
        now = _utcnow_str()
        label = extra.get("label") or login_email
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM facebook_accounts WHERE user_id = ? AND login_email = ?",
                (user_id, login_email),
            ).fetchone()
            if existing:
                current = conn.execute(
                    "SELECT encrypted_password, profile_dir FROM facebook_accounts WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
                new_password = encrypted_password if encrypted_password else (current["encrypted_password"] if current else "")
                new_profile = extra.get("profile_dir") or (current["profile_dir"] if current else None)
                conn.execute(
                    """
                    UPDATE facebook_accounts
                    SET label = ?, encrypted_password = ?, profile_dir = ?, is_active = ?,
                        is_primary = ?, priority = ?, hourly_limit = ?, daily_limit = ?,
                        notes = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        label,
                        new_password,
                        new_profile,
                        1 if extra.get("is_active", True) else 0,
                        1 if extra.get("is_primary", False) else 0,
                        int(extra.get("priority", 0)),
                        int(extra.get("hourly_limit", 0)),
                        int(extra.get("daily_limit", 0)),
                        extra.get("notes"),
                        now,
                        existing["id"],
                    ),
                )
                return int(existing["id"])

            cur = conn.execute(
                """
                INSERT INTO facebook_accounts (
                    user_id, label, login_email, encrypted_password, profile_dir, is_active,
                    is_primary, priority, hourly_limit, daily_limit, notes, last_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', ?, ?)
                """,
                (
                    user_id,
                    label,
                    login_email,
                    encrypted_password or "",
                    extra.get("profile_dir"),
                    1 if extra.get("is_active", True) else 0,
                    1 if extra.get("is_primary", False) else 0,
                    int(extra.get("priority", 0)),
                    int(extra.get("hourly_limit", 0)),
                    int(extra.get("daily_limit", 0)),
                    extra.get("notes"),
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def list_accounts(self, user_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM facebook_accounts
                WHERE user_id = ?
                ORDER BY is_primary DESC, priority DESC, created_at ASC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_primary_account(self, user_id: int) -> Optional[dict]:
        accounts = self.list_accounts(user_id)
        return accounts[0] if accounts else None

    def update_account_status(self, account_id: int, status: str, error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE facebook_accounts
                SET last_status = ?, last_error = ?,
                    last_login_at = CASE WHEN ? IN ('logged_in', 'trusted') THEN ? ELSE last_login_at END,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, error, status, _utcnow_str(), _utcnow_str(), account_id),
            )

    def record_session(self, user_id: int, account_id: int | None, status: str, **extra) -> int:
        now = _utcnow_str()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO facebook_sessions (
                    user_id, account_id, status, reason, profile_dir, checkpoint_detected,
                    needs_2fa, session_valid, session_expires_at, last_validated_at,
                    cookies_last_synced, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    account_id,
                    status,
                    extra.get("reason"),
                    extra.get("profile_dir"),
                    1 if extra.get("checkpoint_detected") else 0,
                    1 if extra.get("needs_2fa") else 0,
                    1 if extra.get("session_valid") else 0,
                    extra.get("session_expires_at"),
                    extra.get("last_validated_at") or now,
                    extra.get("cookies_last_synced"),
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def get_latest_session(self, user_id: int, account_id: int | None = None) -> Optional[dict]:
        with self.connect() as conn:
            if account_id is not None:
                row = conn.execute(
                    """
                    SELECT *
                    FROM facebook_sessions
                    WHERE user_id = ? AND account_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id, int(account_id)),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT *
                    FROM facebook_sessions
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
        return dict(row) if row else None

    def get_account_trust(self, account_id: int) -> dict:
        """Return trust snapshot for an account (trusted/needs_verify/blocked/unknown)."""
        from app.services.account_orchestrator import AccountOrchestrator

        account = self.get_account(account_id)
        if not account:
            return {"trust": "unknown", "reason": "Account not found", "can_use": False}
        return AccountOrchestrator(self).trust_for_account(account_id)

    def create_task(self, user_id: int, task_type: str, title: str, payload: dict | None = None,
                    status: str = "queued", task_key: str | None = None,
                    queue_mode: str = "local_persistent", resumable: int = 0) -> int:
        now = _utcnow_str()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO background_tasks (
                    user_id, task_type, title, status, queue_mode, task_key, payload_json,
                    resumable, created_at, updated_at, heartbeat_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    task_type,
                    title,
                    status,
                    queue_mode,
                    task_key,
                    json.dumps(payload or {}, ensure_ascii=False),
                    resumable,
                    now,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    def update_task(self, task_id: int, **fields) -> None:
        if not fields:
            return
        allowed = {
            "status", "result_json", "error_message", "heartbeat_at", "started_at",
            "finished_at", "updated_at", "title", "payload_json", "resumable", "queue_mode",
            "requested_action", "acknowledged_state", "control_requested_at",
            "control_acknowledged_at",
        }
        sets = []
        values = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            sets.append(f"{key} = ?")
            if key.endswith("_json") and isinstance(value, (dict, list)):
                values.append(json.dumps(value, ensure_ascii=False))
            else:
                values.append(value)
        if "updated_at" not in fields:
            sets.append("updated_at = ?")
            values.append(_utcnow_str())
        values.append(task_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE background_tasks SET {', '.join(sets)} WHERE id = ?", values)

    def heartbeat_task(self, task_id: int, status: str | None = None) -> None:
        fields: dict[str, Any] = {"heartbeat_at": _utcnow_str()}
        if status:
            fields["status"] = status
        self.update_task(task_id, **fields)

    def get_task(self, task_id: int) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM background_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task_row_to_dict(row) if row else None

    def get_task_for_user(self, task_id: int, user_id: int) -> Optional[dict]:
        """Return a task only when it belongs to the requesting user."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM background_tasks WHERE id = ? AND user_id = ?",
                (task_id, user_id),
            ).fetchone()
        return self._task_row_to_dict(row) if row else None

    def get_latest_task(self, user_id: int, task_type: str | None = None) -> Optional[dict]:
        query = "SELECT * FROM background_tasks WHERE user_id = ?"
        params: list[Any] = [user_id]
        if task_type:
            query += " AND task_type = ?"
            params.append(task_type)
        query += " ORDER BY created_at DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return self._task_row_to_dict(row) if row else None

    def get_active_task(self, user_id: int, task_type: str | None = None) -> Optional[dict]:
        query = (
            "SELECT * FROM background_tasks WHERE user_id = ? "
            "AND status IN ('queued', 'running', 'waiting_manual', 'paused', 'stopping')"
        )
        params: list[Any] = [user_id]
        if task_type:
            query += " AND task_type = ?"
            params.append(task_type)
        query += " ORDER BY created_at DESC LIMIT 1"
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return self._task_row_to_dict(row) if row else None

    def _request_control(self, task_id: int, user_id: int, action: str) -> Optional[dict]:
        if action not in {"pause", "resume", "stop"}:
            raise ValueError(f"Unsupported control action: {action}")
        now = _utcnow_str()
        allowed_statuses = {
            "pause": ("queued", "running", "waiting_manual"),
            "resume": ("paused",),
            "stop": ("queued", "running", "waiting_manual", "paused", "stopping"),
        }[action]
        placeholders = ", ".join("?" for _ in allowed_statuses)
        with self.connect() as conn:
            cur = conn.execute(
                f"""
                UPDATE background_tasks
                SET requested_action = ?, control_requested_at = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                  AND status IN ({placeholders})
                """,
                (action, now, now, task_id, user_id, *allowed_statuses),
            )
            if not cur.rowcount:
                return None
        self.append_task_event(
            task_id, f"{action.title()} requested", event_type="control_requested",
            metadata={"action": action},
        )
        return self.get_task_for_user(task_id, user_id)

    def request_pause(self, task_id: int, user_id: int) -> Optional[dict]:
        return self._request_control(task_id, user_id, "pause")

    def request_resume(self, task_id: int, user_id: int) -> Optional[dict]:
        return self._request_control(task_id, user_id, "resume")

    def request_stop(self, task_id: int, user_id: int) -> Optional[dict]:
        return self._request_control(task_id, user_id, "stop")

    def get_control_state(self, task_id: int, user_id: int | None = None) -> Optional[dict]:
        query = (
            "SELECT id, user_id, task_type, status, requested_action, acknowledged_state, "
            "control_requested_at, control_acknowledged_at, heartbeat_at "
            "FROM background_tasks WHERE id = ?"
        )
        params: list[Any] = [task_id]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def acknowledge_control(self, task_id: int, state: str, action: str | None = None) -> None:
        now = _utcnow_str()
        fields: dict[str, Any] = {
            "acknowledged_state": state,
            "control_acknowledged_at": now,
            "heartbeat_at": now,
        }
        if state in {"paused", "running", "stopping", "cancelled"}:
            fields["status"] = state
        if action and action != "pause":
            fields["requested_action"] = "none"
        self.update_task(task_id, **fields)
        self.append_task_event(
            task_id, f"Worker acknowledged {state}", event_type="control_acknowledged",
            metadata={"state": state, "action": action},
        )

    def get_user_task_summary(self, user_id: int, task_type: str | None = None) -> dict:
        task = self.get_active_task(user_id, task_type) or self.get_latest_task(user_id, task_type)
        if not task:
            return {"task": None, "status": "idle", "progress": {}}
        events = task.get("events") or []
        progress = next(
            (event.get("metadata") or {} for event in reversed(events)
             if event.get("event_type") == "progress"),
            {},
        )
        return {"task": task, "status": task.get("status", "idle"), "progress": progress}

    def list_tasks(self, user_id: int, task_type: str | None = None, limit: int = 50) -> list[dict]:
        query = "SELECT * FROM background_tasks WHERE user_id = ?"
        params: list[Any] = [user_id]
        if task_type:
            query += " AND task_type = ?"
            params.append(task_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._task_row_to_dict(row) for row in rows]

    def append_task_event(self, task_id: int, message: str, level: str = "info",
                          event_type: str = "log", metadata: dict | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO task_events (task_id, level, event_type, message, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    level,
                    event_type,
                    message,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    _utcnow_str(),
                ),
            )
        self.heartbeat_task(task_id)

    def list_task_events(self, task_id: int, limit: int = 200) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM task_events
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        result = []
        for row in reversed(rows):
            item = dict(row)
            item["metadata"] = self._json_load(item.pop("metadata_json", None), {})
            result.append(item)
        return result

    def upsert_group_status(self, task_id: int, group_url: str, status: str, **extra) -> None:
        group_key = extra.get("group_key") or self._group_key(group_url)
        now = _utcnow_str()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id, attempt_count FROM task_group_statuses WHERE task_id = ? AND group_key = ?",
                (task_id, group_key),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE task_group_statuses
                    SET group_url = ?, group_name = ?, language_tag = ?, status = ?, error_reason = ?,
                        template_label = ?, account_label = ?, attempt_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        group_url,
                        extra.get("group_name"),
                        extra.get("language_tag"),
                        status,
                        extra.get("error_reason"),
                        extra.get("template_label"),
                        extra.get("account_label"),
                        int(extra.get("attempt_count", existing["attempt_count"] or 0)),
                        now,
                        existing["id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO task_group_statuses (
                        task_id, group_key, group_url, group_name, language_tag, status,
                        error_reason, template_label, account_label, attempt_count, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        group_key,
                        group_url,
                        extra.get("group_name"),
                        extra.get("language_tag"),
                        status,
                        extra.get("error_reason"),
                        extra.get("template_label"),
                        extra.get("account_label"),
                        int(extra.get("attempt_count", 0)),
                        now,
                    ),
                )
        self.heartbeat_task(task_id)

    def list_group_statuses(self, task_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM task_group_statuses
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_failed_groups(self, task_id: int) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT group_url FROM task_group_statuses WHERE task_id = ? AND status = 'Failed'",
                (task_id,),
            ).fetchall()
        return [row["group_url"] for row in rows if row["group_url"]]

    def get_success_group_urls(self, task_id: int) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT group_url FROM task_group_statuses WHERE task_id = ? AND status = 'Success'",
                (task_id,),
            ).fetchall()
        return {row["group_url"] for row in rows if row["group_url"]}

    def upsert_group_workspace(self, user_id: int, group_url: str, **extra) -> None:
        now = _utcnow_str()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM group_workspace WHERE user_id = ? AND group_url = ?",
                (user_id, group_url),
            ).fetchone()
            payload = (
                extra.get("group_name"),
                1 if extra.get("is_blacklisted") else 0,
                1 if extra.get("is_whitelisted") else 0,
                json.dumps(extra.get("tags", []), ensure_ascii=False),
                extra.get("notes"),
                extra.get("last_posted_at"),
                extra.get("last_post_status"),
                extra.get("last_campaign_name"),
                now,
            )
            if existing:
                conn.execute(
                    """
                    UPDATE group_workspace
                    SET group_name = ?, is_blacklisted = ?, is_whitelisted = ?, tags_json = ?,
                        notes = ?, last_posted_at = ?, last_post_status = ?, last_campaign_name = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    payload + (existing["id"],),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO group_workspace (
                        user_id, group_url, group_name, is_blacklisted, is_whitelisted, tags_json,
                        notes, last_posted_at, last_post_status, last_campaign_name, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, group_url, extra.get("group_name"),
                        1 if extra.get("is_blacklisted") else 0,
                        1 if extra.get("is_whitelisted") else 0,
                        json.dumps(extra.get("tags", []), ensure_ascii=False),
                        extra.get("notes"),
                        extra.get("last_posted_at"),
                        extra.get("last_post_status"),
                        extra.get("last_campaign_name"),
                        now,
                        now,
                    ),
                )

    def get_group_workspace_map(self, user_id: int) -> dict[str, dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM group_workspace WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        result = {}
        for row in rows:
            item = dict(row)
            item["tags"] = self._json_load(item.pop("tags_json", None), [])
            result[item["group_url"]] = item
        return result

    def save_filter(self, user_id: int, name: str, config: dict, is_default: bool = False) -> int:
        now = _utcnow_str()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO saved_group_filters (user_id, name, config_json, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, name, json.dumps(config, ensure_ascii=False), 1 if is_default else 0, now, now),
            )
            return int(cur.lastrowid)

    def list_filters(self, user_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM saved_group_filters WHERE user_id = ? ORDER BY is_default DESC, created_at DESC",
                (user_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["config"] = self._json_load(item.pop("config_json", None), {})
            result.append(item)
        return result

    def sync_templates(self, user_id: int, templates: Iterable[str]) -> None:
        now = _utcnow_str()
        with self.connect() as conn:
            for content in templates:
                existing = conn.execute(
                    "SELECT id FROM template_records WHERE user_id = ? AND content = ?",
                    (user_id, content),
                ).fetchone()
                if existing:
                    conn.execute("UPDATE template_records SET updated_at = ? WHERE id = ?", (now, existing["id"]))
                else:
                    title = content.strip().splitlines()[0][:80] if content.strip() else "Untitled template"
                    conn.execute(
                        """
                        INSERT INTO template_records (
                            user_id, content, title, folder, tags_json, created_at, updated_at
                        ) VALUES (?, ?, ?, 'Default', '[]', ?, ?)
                        """,
                        (user_id, content, title, now, now),
                    )

    def list_templates(self, user_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM template_records
                WHERE user_id = ?
                ORDER BY folder ASC, created_at ASC
                """,
                (user_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["tags"] = self._json_load(item.pop("tags_json", None), [])
            result.append(item)
        return result

    def update_template_meta(self, user_id: int, content: str, **extra) -> None:
        now = _utcnow_str()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE template_records
                SET title = COALESCE(?, title),
                    folder = COALESCE(?, folder),
                    tags_json = COALESCE(?, tags_json),
                    is_active = COALESCE(?, is_active),
                    weight = COALESCE(?, weight),
                    updated_at = ?
                WHERE user_id = ? AND content = ?
                """,
                (
                    extra.get("title"),
                    extra.get("folder"),
                    json.dumps(extra.get("tags"), ensure_ascii=False) if "tags" in extra else None,
                    extra.get("is_active"),
                    extra.get("weight"),
                    now,
                    user_id,
                    content,
                ),
            )

    def delete_template(self, user_id: int, content: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM template_records WHERE user_id = ? AND content = ?",
                (user_id, content),
            )
        return cur.rowcount > 0

    def record_template_result(self, user_id: int, content: str, success: bool) -> None:
        now = _utcnow_str()
        column = "success_count" if success else "fail_count"
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE template_records
                SET use_count = use_count + 1,
                    {column} = {column} + 1,
                    last_used_at = ?,
                    updated_at = ?
                WHERE user_id = ? AND content = ?
                """,
                (now, now, user_id, content),
            )

    def _task_row_to_dict(self, row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        item = dict(row)
        item["payload"] = self._json_load(item.pop("payload_json", None), {})
        item["result"] = self._json_load(item.pop("result_json", None), {})
        item["events"] = self.list_task_events(item["id"], limit=50)
        item["group_statuses"] = self.list_group_statuses(item["id"])
        return item

    @staticmethod
    def _json_load(value: Any, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except Exception:
            return default

    @staticmethod
    def _group_key(group_url: str) -> str:
        return (group_url or "").strip().rstrip("/")


class LocalTaskManager:
    def __init__(self, store: RuntimeStore):
        self.store = store
        self._threads: dict[int, threading.Thread] = {}
        self._lock = threading.RLock()

    def start_task(
        self,
        user_id: int,
        task_type: str,
        title: str,
        payload: dict,
        runner: Callable[[int], dict | None],
        task_key: str | None = None,
        existing_task_id: int | None = None,
    ) -> dict:
        if existing_task_id is not None:
            task = self.store.get_task_for_user(existing_task_id, user_id)
            if not task:
                raise ValueError("Cannot start a task that does not belong to the user")
            task_id = existing_task_id
            self.store.update_task(task_id, status="queued", queue_mode="local_persistent", error_message=None)
        else:
            resumable = 1 if task_type == 'posting' or payload.get('resumable') else 0
            task_id = self.store.create_task(
                user_id, task_type, title, payload, status="queued", task_key=task_key, resumable=resumable
            )

        def _wrapped():
            self.store.update_task(task_id, status="running", started_at=_utcnow_str(), heartbeat_at=_utcnow_str())
            try:
                result = runner(task_id) or {}
                status = result.get("status", "completed")
                error_message = result.get("error_message")
                self.store.update_task(
                    task_id,
                    status=status,
                    result_json=result,
                    error_message=error_message,
                    finished_at=_utcnow_str(),
                    heartbeat_at=_utcnow_str(),
                )
            except Exception as exc:
                self.store.append_task_event(
                    task_id,
                    traceback.format_exc(limit=10),
                    level="error",
                    event_type="exception",
                    metadata={"error": str(exc)},
                )
                self.store.update_task(
                    task_id,
                    status="failed",
                    error_message=str(exc),
                    finished_at=_utcnow_str(),
                    heartbeat_at=_utcnow_str(),
                )
            finally:
                with self._lock:
                    self._threads.pop(task_id, None)

        thread = threading.Thread(target=_wrapped, name=f"{task_type}-{task_id}", daemon=True)
        with self._lock:
            self._threads[task_id] = thread
        thread.start()
        return self.store.get_task(task_id) or {"id": task_id}

    def is_task_alive(self, task_id: int) -> bool:
        with self._lock:
            thread = self._threads.get(task_id)
        return bool(thread and thread.is_alive())

