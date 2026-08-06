from bot.telegram_reports import format_daily_digest, format_session_report, format_batch_report


def test_format_daily_digest_empty_day():
    text = format_daily_digest({
        "day": "2026-08-06",
        "posts_today": 0,
        "groups_today": 0,
        "avg_engagement_pct": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "avg_score": 0,
        "lifetime_success": 10,
        "lifetime_failed": 2,
        "posts_7d": 5,
        "top_groups": [],
    }, user_label="Alice")
    assert "Daily digest" in text
    assert "Alice" in text
    assert "No posts recorded today" in text
    assert "10" in text and "2" in text


def test_format_session_and_batch_reports():
    session = format_session_report(
        success=8,
        failed=2,
        total_groups=12,
        elapsed_minutes=15,
        session_restarts=1,
        use_templates=True,
        template_mode="random",
        template_count=3,
        failed_samples=[("Group A", "checkpoint")],
        campaign_name="Evening",
        account_label="Primary",
    )
    assert "Success rate" in session
    assert "Evening" in session
    assert "checkpoint" in session

    batch = format_batch_report(
        batch_num=2,
        batch_success=7,
        batch_failed=3,
        total_processed=20,
        total_groups=50,
        failed_groups=[("G1", "timeout")],
    )
    assert "Batch #2" in batch
    assert "timeout" in batch
