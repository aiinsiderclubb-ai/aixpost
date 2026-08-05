"""Lightweight analytics store used by the local release runtime."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


class _AnalyticsDB:
    def __init__(self):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.db_path = os.path.join(base_dir, "analytics.db")
        self._ensure_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS post_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER DEFAULT 0,
                    group_id TEXT,
                    group_name TEXT,
                    group_url TEXT,
                    message_text TEXT,
                    template_id TEXT,
                    post_url TEXT,
                    post_id TEXT,
                    likes_1h INTEGER DEFAULT 0,
                    comments_1h INTEGER DEFAULT 0,
                    shares_1h INTEGER DEFAULT 0,
                    likes_24h INTEGER DEFAULT 0,
                    comments_24h INTEGER DEFAULT 0,
                    shares_24h INTEGER DEFAULT 0,
                    likes_7d INTEGER DEFAULT 0,
                    comments_7d INTEGER DEFAULT 0,
                    shares_7d INTEGER DEFAULT 0,
                    engagement_rate_24h REAL DEFAULT 0,
                    performance_score REAL DEFAULT 0,
                    metrics_source TEXT DEFAULT 'estimated',
                    posted_at TEXT NOT NULL,
                    is_legacy INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS analytics_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_analytics_id INTEGER NOT NULL,
                    check_type TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    engagement_rate REAL DEFAULT 0,
                    performance_score REAL DEFAULT 0,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS group_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER DEFAULT 0,
                    group_id TEXT,
                    group_name TEXT,
                    group_url TEXT,
                    total_posts INTEGER DEFAULT 0,
                    success_posts INTEGER DEFAULT 0,
                    failed_posts INTEGER DEFAULT 0,
                    post_success_rate REAL DEFAULT 0,
                    avg_engagement_rate REAL DEFAULT 0,
                    recommendation_score REAL DEFAULT 0,
                    consecutive_failures INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, group_id)
                );

                CREATE TABLE IF NOT EXISTS analytics_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT,
                    group_name TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(post_analytics)").fetchall()}
        migrations = {
            "post_url": "ALTER TABLE post_analytics ADD COLUMN post_url TEXT",
            "post_id": "ALTER TABLE post_analytics ADD COLUMN post_id TEXT",
            "template_id": "ALTER TABLE post_analytics ADD COLUMN template_id TEXT",
            "likes_1h": "ALTER TABLE post_analytics ADD COLUMN likes_1h INTEGER DEFAULT 0",
            "comments_1h": "ALTER TABLE post_analytics ADD COLUMN comments_1h INTEGER DEFAULT 0",
            "shares_1h": "ALTER TABLE post_analytics ADD COLUMN shares_1h INTEGER DEFAULT 0",
            "shares_24h": "ALTER TABLE post_analytics ADD COLUMN shares_24h INTEGER DEFAULT 0",
            "likes_7d": "ALTER TABLE post_analytics ADD COLUMN likes_7d INTEGER DEFAULT 0",
            "comments_7d": "ALTER TABLE post_analytics ADD COLUMN comments_7d INTEGER DEFAULT 0",
            "shares_7d": "ALTER TABLE post_analytics ADD COLUMN shares_7d INTEGER DEFAULT 0",
            "metrics_source": "ALTER TABLE post_analytics ADD COLUMN metrics_source TEXT DEFAULT 'estimated'",
            "user_id": "ALTER TABLE post_analytics ADD COLUMN user_id INTEGER DEFAULT 0",
            "is_legacy": "ALTER TABLE post_analytics ADD COLUMN is_legacy INTEGER DEFAULT 0",
        }
        for column, sql in migrations.items():
            if column not in columns:
                conn.execute(sql)

        gp_columns = {row[1] for row in conn.execute("PRAGMA table_info(group_performance)").fetchall()}
        if "user_id" not in gp_columns:
            conn.execute("ALTER TABLE group_performance ADD COLUMN user_id INTEGER DEFAULT 0")
            try:
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_group_perf_user_group ON group_performance(user_id, group_id)")
            except sqlite3.OperationalError:
                pass
        gp_migrations = {
            "success_posts": "ALTER TABLE group_performance ADD COLUMN success_posts INTEGER DEFAULT 0",
            "failed_posts": "ALTER TABLE group_performance ADD COLUMN failed_posts INTEGER DEFAULT 0",
            "group_name": "ALTER TABLE group_performance ADD COLUMN group_name TEXT",
            "group_url": "ALTER TABLE group_performance ADD COLUMN group_url TEXT",
        }
        for column, sql in gp_migrations.items():
            if column not in gp_columns:
                conn.execute(sql)
                gp_columns.add(column)
        if "total_successful_posts" in gp_columns and "success_posts" in gp_columns:
            conn.execute(
                """
                UPDATE group_performance
                SET success_posts = COALESCE(total_successful_posts, 0)
                WHERE COALESCE(success_posts, 0) = 0 AND COALESCE(total_successful_posts, 0) > 0
                """
            )
        if "total_failed_posts" in gp_columns and "failed_posts" in gp_columns:
            conn.execute(
                """
                UPDATE group_performance
                SET failed_posts = COALESCE(total_failed_posts, 0)
                WHERE COALESCE(failed_posts, 0) = 0 AND COALESCE(total_failed_posts, 0) > 0
                """
            )

    def _group_success_expr(self) -> str:
        with self.connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(group_performance)").fetchall()}
        if "success_posts" in cols:
            return "COALESCE(success_posts, 0)"
        if "total_successful_posts" in cols:
            return "COALESCE(total_successful_posts, 0)"
        return "0"

    def _group_failed_expr(self) -> str:
        with self.connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(group_performance)").fetchall()}
        if "failed_posts" in cols:
            return "COALESCE(failed_posts, 0)"
        if "total_failed_posts" in cols:
            return "COALESCE(total_failed_posts, 0)"
        return "0"

    def get_dashboard_data(self, user_id: int) -> Dict[str, Any]:
        uid = int(user_id or 0)
        with self.connect() as conn:
            total_posts = conn.execute(
                "SELECT COUNT(*) FROM post_analytics WHERE user_id = ? AND is_legacy = 0",
                (uid,),
            ).fetchone()[0] or 0
            scraped_posts = conn.execute(
                "SELECT COUNT(*) FROM post_analytics WHERE user_id = ? AND metrics_source = 'facebook_scraper'",
                (uid,),
            ).fetchone()[0] or 0
            avg_engagement = conn.execute(
                "SELECT AVG(engagement_rate_24h) FROM post_analytics WHERE user_id = ? AND metrics_source = 'facebook_scraper'",
                (uid,),
            ).fetchone()[0]
            if avg_engagement is None:
                avg_engagement = conn.execute(
                    "SELECT AVG(engagement_rate_24h) FROM post_analytics WHERE user_id = ? AND is_legacy = 0",
                    (uid,),
                ).fetchone()[0] or 0
            active_groups = conn.execute(
                "SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE user_id = ? AND is_legacy = 0",
                (uid,),
            ).fetchone()[0] or 0
            pending_checks = conn.execute(
                """
                SELECT COUNT(*)
                FROM analytics_checks c
                JOIN post_analytics p ON p.id = c.post_analytics_id
                WHERE p.user_id = ? AND c.status = 'pending'
                """,
                (uid,),
            ).fetchone()[0] or 0
            completed_checks = conn.execute(
                """
                SELECT COUNT(*)
                FROM analytics_checks c
                JOIN post_analytics p ON p.id = c.post_analytics_id
                WHERE p.user_id = ? AND c.status = 'completed'
                """,
                (uid,),
            ).fetchone()[0] or 0
            failed_checks = conn.execute(
                """
                SELECT COUNT(*)
                FROM analytics_checks c
                JOIN post_analytics p ON p.id = c.post_analytics_id
                WHERE p.user_id = ? AND c.status = 'failed'
                """,
                (uid,),
            ).fetchone()[0] or 0

        success_expr = self._group_success_expr()
        total_expr = "COALESCE(total_posts, 0)"
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT COALESCE(SUM({success_expr}), 0), COALESCE(SUM({total_expr}), 0)
                FROM group_performance
                WHERE user_id = ?
                """,
                (uid,),
            ).fetchone()
            if row:
                success_posts, total_gp_posts = row[0] or 0, row[1] or 0
                success_rate = (success_posts / total_gp_posts * 100) if total_gp_posts else (100.0 if total_posts else 0.0)
            else:
                success_rate = 100.0 if total_posts else 0.0

        return {
            "total_posts": total_posts,
            "scraped_posts": scraped_posts,
            "avg_engagement_rate": float(avg_engagement or 0) * 100,
            "active_groups": active_groups,
            "success_rate": success_rate,
            "pending_checks": pending_checks,
            "completed_checks": completed_checks,
            "failed_checks": failed_checks,
            "top_groups": self.get_top_performing_groups(10, user_id=uid),
            "performance_dates": [row["day"] for row in self.get_performance_data(7, user_id=uid)] or [
                "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
            ],
            "performance_data": [
                round((row["avg_engagement"] or 0) * 100, 2)
                for row in self.get_performance_data(7, user_id=uid)
            ] or [0, 0, 0, 0, 0, 0, 0],
            "engagement_breakdown": self.get_engagement_breakdown(user_id=uid),
            "recent_posts": self.get_recent_posts(15, user_id=uid),
        }

    def save_post(
        self,
        group_id,
        group_name,
        group_url,
        message_text,
        template_id=None,
        user_id=0,
        post_url: Optional[str] = None,
        post_id: Optional[str] = None,
    ) -> int:
        posted_at = datetime.utcnow().isoformat()
        score = min(100.0, max(0.0, float(len(message_text or "")) / 20.0))
        engagement = round(min(1.0, score / 100.0), 4)
        metrics_source = "permalink" if post_url else "estimated"
        columns = self._post_columns()
        values = {
            "user_id": user_id or 0,
            "group_id": group_id,
            "group_name": group_name,
            "group_url": group_url,
            "message_text": message_text,
            "template_id": str(template_id or ""),
            "template_used": int(template_id) if str(template_id or "").isdigit() else 0,
            "post_url": post_url,
            "post_id": post_id,
            "engagement_rate_24h": engagement,
            "performance_score": score,
            "metrics_source": metrics_source,
            "posted_at": posted_at,
            "is_legacy": 0,
        }
        insert_cols = [col for col in values if col in columns]
        placeholders = ", ".join("?" for _ in insert_cols)
        col_sql = ", ".join(insert_cols)
        with self.connect() as conn:
            cur = conn.execute(
                f"INSERT INTO post_analytics ({col_sql}) VALUES ({placeholders})",
                [values[col] for col in insert_cols],
            )
            post_analytics_id = int(cur.lastrowid)
        self.schedule_analytics_checks(post_analytics_id, posted_at)
        return post_analytics_id

    def _post_columns(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute("PRAGMA table_info(post_analytics)").fetchall()
        return {row[1] for row in rows}

    def schedule_analytics_checks(self, post_analytics_id: int, posted_at: Optional[str] = None) -> None:
        base = datetime.fromisoformat(posted_at) if posted_at else datetime.utcnow()
        schedule = {
            "1h": base + timedelta(hours=1),
            "24h": base + timedelta(hours=24),
            "7d": base + timedelta(days=7),
        }
        with self.connect() as conn:
            for check_type, when in schedule.items():
                conn.execute(
                    """
                    INSERT INTO analytics_checks (post_analytics_id, check_type, scheduled_at, status)
                    VALUES (?, ?, ?, 'pending')
                    """,
                    (post_analytics_id, check_type, when.isoformat()),
                )

    def get_post(self, post_analytics_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM post_analytics WHERE id = ?", (post_analytics_id,)).fetchone()
        return dict(row) if row else None

    def get_pending_analytics_checks(self) -> List[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, p.group_url, p.group_name, p.message_text, p.post_url, p.post_id
                FROM analytics_checks c
                JOIN post_analytics p ON p.id = c.post_analytics_id
                WHERE c.status = 'pending' AND c.scheduled_at <= ?
                ORDER BY c.scheduled_at ASC
                LIMIT 25
                """,
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_check_completed(self, check_id: int, metrics: Dict[str, Any]) -> None:
        check = self._get_check(check_id)
        if not check:
            return
        now = datetime.utcnow().isoformat()
        likes = int(metrics.get("likes") or 0)
        comments = int(metrics.get("comments") or 0)
        shares = int(metrics.get("shares") or 0)
        engagement_rate = float(metrics.get("engagement_rate") or 0)
        performance_score = float(metrics.get("performance_score") or 0)
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE analytics_checks
                SET status = 'completed',
                    completed_at = ?,
                    likes = ?,
                    comments = ?,
                    shares = ?,
                    engagement_rate = ?,
                    performance_score = ?
                WHERE id = ?
                """,
                (now, likes, comments, shares, engagement_rate, performance_score, check_id),
            )
        self._apply_metrics_to_post(int(check["post_analytics_id"]), check["check_type"], metrics)

    def mark_check_failed(self, check_id: int, error_message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE analytics_checks
                SET status = 'failed', completed_at = ?, error_message = ?
                WHERE id = ?
                """,
                (datetime.utcnow().isoformat(), error_message, check_id),
            )

    def _get_check(self, check_id: int) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM analytics_checks WHERE id = ?", (check_id,)).fetchone()
        return dict(row) if row else None

    def _apply_metrics_to_post(self, post_analytics_id: int, check_type: str, metrics: Dict[str, Any]) -> None:
        likes = int(metrics.get("likes") or 0)
        comments = int(metrics.get("comments") or 0)
        shares = int(metrics.get("shares") or 0)
        engagement_rate = float(metrics.get("engagement_rate") or 0)
        performance_score = float(metrics.get("performance_score") or 0)
        post_url = metrics.get("post_url")
        post_id = metrics.get("post_id")

        field_map = {
            "1h": ("likes_1h", "comments_1h", "shares_1h"),
            "24h": ("likes_24h", "comments_24h", "shares_24h"),
            "7d": ("likes_7d", "comments_7d", "shares_7d"),
        }
        fields = field_map.get(check_type)
        if not fields:
            return

        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE post_analytics
                SET {fields[0]} = ?, {fields[1]} = ?, {fields[2]} = ?,
                    engagement_rate_24h = CASE WHEN ? = '24h' THEN ? ELSE engagement_rate_24h END,
                    performance_score = ?,
                    metrics_source = 'facebook_scraper',
                    post_url = COALESCE(?, post_url),
                    post_id = COALESCE(?, post_id)
                WHERE id = ?
                """,
                (
                    likes,
                    comments,
                    shares,
                    check_type,
                    engagement_rate,
                    performance_score,
                    post_url,
                    post_id,
                    post_analytics_id,
                ),
            )
            row = conn.execute(
                "SELECT group_id, group_name, group_url, user_id FROM post_analytics WHERE id = ?",
                (post_analytics_id,),
            ).fetchone()
        if row and check_type in ("24h", "7d"):
            self._refresh_group_engagement(
                row["group_id"], row["group_name"], row["group_url"], user_id=row["user_id"] or 0
            )

    def _refresh_group_engagement(self, group_id: str, group_name: str, group_url: str, user_id: int = 0) -> None:
        uid = int(user_id or 0)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT AVG(engagement_rate_24h) AS avg_engagement
                FROM post_analytics
                WHERE group_id = ? AND user_id = ? AND metrics_source = 'facebook_scraper'
                """,
                (group_id, uid),
            ).fetchone()
        avg_engagement = float(row["avg_engagement"] or 0) if row else 0.0
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM group_performance WHERE group_id = ? AND user_id = ?",
                (group_id, uid),
            ).fetchone()
            if not existing:
                return
            recommendation = min(
                1.0,
                max(0.0, (existing["post_success_rate"] or 0) * 0.6 + avg_engagement * 0.4),
            )
            conn.execute(
                """
                UPDATE group_performance
                SET avg_engagement_rate = ?, recommendation_score = ?, updated_at = ?
                WHERE group_id = ? AND user_id = ?
                """,
                (avg_engagement, recommendation, datetime.utcnow().isoformat(), group_id, uid),
            )

    def calculate_recommendation_scores(self) -> None:
        with self.connect() as conn:
            rows = conn.execute("SELECT group_id FROM group_performance").fetchall()
        for row in rows:
            self._refresh_group_engagement(row["group_id"], None, None)

    def update_group_stats(self, group_id, success=True, group_name=None, group_url=None, user_id=0):
        now = datetime.utcnow().isoformat()
        uid = int(user_id or 0)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM group_performance WHERE group_id = ? AND user_id = ?",
                (group_id, uid),
            ).fetchone()
            if not row:
                total_posts = 1
                success_posts = 1 if success else 0
                failed_posts = 0 if success else 1
                consecutive_failures = 0 if success else 1
                post_success_rate = 1.0 if success else 0.0
                recommendation_score = 1.0 if success else 0.0
                conn.execute(
                    """
                    INSERT INTO group_performance (
                        user_id, group_id, group_name, group_url, total_posts, success_posts, failed_posts,
                        post_success_rate, avg_engagement_rate, recommendation_score, consecutive_failures, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        uid,
                        group_id,
                        group_name or group_id,
                        group_url or "",
                        total_posts,
                        success_posts,
                        failed_posts,
                        post_success_rate,
                        recommendation_score,
                        consecutive_failures,
                        now,
                    ),
                )
                return

            total_posts = (row["total_posts"] or 0) + 1
            success_col = "success_posts" if "success_posts" in row.keys() else "total_successful_posts"
            failed_col = "failed_posts" if "failed_posts" in row.keys() else "total_failed_posts"
            success_posts = (row[success_col] or 0) + (1 if success else 0)
            failed_posts = (row[failed_col] or 0) + (0 if success else 1)
            consecutive_failures = 0 if success else (row["consecutive_failures"] or 0) + 1
            post_success_rate = success_posts / max(1, total_posts)
            avg_engagement = row["avg_engagement_rate"] or 0
            recommendation_score = max(
                0.0,
                min(1.0, post_success_rate * 0.6 + float(avg_engagement) * 0.4 - consecutive_failures * 0.1),
            )
            conn.execute(
                """
                UPDATE group_performance
                SET group_name = COALESCE(?, group_name),
                    group_url = COALESCE(?, group_url),
                    total_posts = ?,
                    success_posts = ?,
                    failed_posts = ?,
                    post_success_rate = ?,
                    recommendation_score = ?,
                    consecutive_failures = ?,
                    updated_at = ?
                WHERE group_id = ? AND user_id = ?
                """,
                (
                    group_name,
                    group_url,
                    total_posts,
                    success_posts,
                    failed_posts,
                    post_success_rate,
                    recommendation_score,
                    consecutive_failures,
                    now,
                    group_id,
                    uid,
                ),
            )

    def log_error(self, group_id, group_name, error_type, error_message):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO analytics_errors (group_id, group_name, error_type, error_message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (group_id, group_name, error_type, error_message, datetime.utcnow().isoformat()),
            )

    def log_post(self, *args, **kwargs):
        return self.save_post(*args, **kwargs)

    def get_top_performing_groups(self, n=10, user_id: Optional[int] = None):
        query = "SELECT * FROM group_performance"
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id = ?"
            params.append(int(user_id))
        query += " ORDER BY recommendation_score DESC, post_success_rate DESC, total_posts DESC LIMIT ?"
        params.append(n)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_analytics_summary(self, user_id: Optional[int] = None):
        uid_filter = " WHERE user_id = ?" if user_id is not None else ""
        params = [int(user_id)] if user_id is not None else []
        with self.connect() as conn:
            total_posts = conn.execute(
                f"SELECT COUNT(*) FROM post_analytics{uid_filter}",
                params,
            ).fetchone()[0] or 0
            active_groups = conn.execute(
                f"SELECT COUNT(DISTINCT group_id) FROM post_analytics{uid_filter}",
                params,
            ).fetchone()[0] or 0
            source_filter = uid_filter + (" AND" if uid_filter else " WHERE") + " metrics_source = 'facebook_scraper'"
            avg_engagement = conn.execute(
                f"SELECT AVG(engagement_rate_24h) FROM post_analytics{source_filter}",
                params,
            ).fetchone()[0]
            if avg_engagement is None:
                avg_engagement = conn.execute(
                    f"SELECT AVG(engagement_rate_24h) FROM post_analytics{uid_filter}",
                    params,
                ).fetchone()[0] or 0
        return {
            "total_posts": total_posts,
            "active_groups": active_groups,
            "avg_engagement_rate": (avg_engagement or 0) * 100,
        }

    def get_performance_data(self, days=7, user_id: Optional[int] = None):
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        query = """
            SELECT substr(posted_at, 1, 10) AS day, AVG(engagement_rate_24h) AS avg_engagement
            FROM post_analytics
            WHERE posted_at >= ?
        """
        params: list[Any] = [cutoff]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(int(user_id))
        query += " GROUP BY substr(posted_at, 1, 10) ORDER BY day ASC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_engagement_breakdown(self, user_id: Optional[int] = None):
        query = """
            SELECT
                COALESCE(SUM(CASE WHEN likes_24h > 0 THEN likes_24h ELSE likes_1h END), 0),
                COALESCE(SUM(CASE WHEN comments_24h > 0 THEN comments_24h ELSE comments_1h END), 0),
                COALESCE(SUM(CASE WHEN shares_24h > 0 THEN shares_24h ELSE shares_1h END), 0)
            FROM post_analytics
        """
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id = ?"
            params.append(int(user_id))
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return [row[0] or 0, row[1] or 0, row[2] or 0]

    def get_recent_posts(self, n=20, user_id: Optional[int] = None):
        query = "SELECT * FROM post_analytics"
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id = ? AND is_legacy = 0"
            params.append(int(user_id))
        query += " ORDER BY posted_at DESC LIMIT ?"
        params.append(n)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


analytics_db = _AnalyticsDB()
