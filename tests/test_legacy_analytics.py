import os
import sqlite3


def test_legacy_flag_on_missing_user_id(tmp_path):
    from bot.analytics_db import AnalyticsDB
    db_path = tmp_path / 'analytics.db'
    adb = AnalyticsDB(str(db_path))
    # Insert legacy row (no user_id)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO post_analytics (group_id, group_name, group_url, message_text) VALUES (?,?,?,?)",
                     ('1', 'Test', 'url', 'msg'))
        conn.commit()
    # Re-init should add is_legacy and backfill
    adb.init_database()
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM post_analytics WHERE is_legacy = 1")
        assert cur.fetchone()[0] >= 1



