import os
import sqlite3
from datetime import datetime


def test_legacy_flag_on_missing_user_id(tmp_path):
    from bot.analytics_db import AnalyticsDB
    db_path = tmp_path / 'analytics.db'
    adb = AnalyticsDB(str(db_path))
    # Insert legacy row (no user_id)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO post_analytics (group_id, group_name, group_url, message_text, posted_at, user_id) VALUES (?,?,?,?,?,?)",
            ('1', 'Test', 'url', 'msg', datetime.utcnow().isoformat(), 0),
        )
        conn.commit()
    # Re-init should mark user_id=0 rows as legacy
    adb.init_database()
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM post_analytics WHERE is_legacy = 1")
        assert cur.fetchone()[0] >= 1
