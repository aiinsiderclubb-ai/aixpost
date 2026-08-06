"""analytics routes extracted from run_test_v2."""
from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)

bp = Blueprint('analytics', __name__)


class _LimiterProxy:
    def limit(self, *limit_args, **limit_kwargs):
        def decorator(f):
            @wraps(f)
            def wrapped(*args, **kwargs):
                import run_test_v2 as rt
                return rt.limiter.limit(*limit_args, **limit_kwargs)(f)(*args, **kwargs)
            return wrapped
        return decorator


limiter = _LimiterProxy()


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        import run_test_v2 as rt
        return rt.admin_required(f)(*args, **kwargs)
    return wrapped


def bind_runtime() -> None:
    """Copy shared symbols from run_test_v2 into this module globals."""
    from app.blueprints import bind_module_runtime
    bind_module_runtime(globals())



@bp.route('/api/analytics/trend')
@jwt_required()
def api_analytics_trend():
    """Return monthly unique groups posted counts for last N months."""
    try:
        import sqlite3
        from bot.analytics_db import analytics_db
        from datetime import datetime

        def add_months(dt: datetime, months_delta: int) -> datetime:
            total_months = dt.year * 12 + dt.month - 1 + months_delta
            year = total_months // 12
            month = total_months % 12 + 1
            # keep at day 1 to avoid month length issues
            return dt.replace(year=year, month=month, day=1)

        months = int(request.args.get('months', 6) or 6)
        months = max(1, min(months, 24))

        start_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        window_start = add_months(start_month, - (months - 1))

        # Query analytics
        with sqlite3.connect(analytics_db.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT strftime('%Y-%m', posted_at) AS ym, COUNT(DISTINCT group_id)
                FROM post_analytics
                WHERE posted_at >= ? AND user_id = ?
                GROUP BY ym
                ORDER BY ym
                """,
                (window_start, int(get_jwt_identity()))
            )
            rows = cur.fetchall()
            ym_to_count = {ym: count or 0 for ym, count in rows}

        # Build labels and values for each month in window
        labels = []
        values = []
        for i in range(months):
            dt = add_months(window_start, i)
            ym = dt.strftime('%Y-%m')
            labels.append(dt.strftime('%b'))  # Jan, Feb, ...
            values.append(int(ym_to_count.get(ym, 0)))

        return jsonify({'labels': labels, 'values': values})
    except Exception as e:
        logger.error(f"analytics_trend error: {e}")
        return jsonify({'labels': ['Jan'], 'values': [0]}), 200

@bp.route('/api/analytics/dashboard')
@jwt_required()
def api_analytics_dashboard():
    """JSON dashboard payload for analytics page live refresh."""
    try:
        from bot.analytics_db import analytics_db
        user_id = int(get_jwt_identity())
        return jsonify(analytics_db.get_dashboard_data(user_id)), 200
    except Exception as exc:
        logger.error("analytics dashboard error: %s", exc)
        return jsonify({'error': str(exc)}), 500

@bp.route('/api/analytics/refresh', methods=['POST'])
@jwt_required()
def api_refresh_analytics():
    """Force pending facebook-scraper analytics checks to run."""
    try:
        from bot.analytics_db import analytics_db
        from bot.analytics_scheduler import analytics_scheduler
        user_id = int(get_jwt_identity())
        analytics_scheduler.force_analytics_check()
        summary = analytics_db.get_analytics_summary(user_id=user_id)
        dashboard = analytics_db.get_dashboard_data(user_id)
        return jsonify({
            'message': 'Analytics refresh triggered',
            'summary': summary,
            'dashboard': dashboard,
        }), 200
    except Exception as exc:
        logger.error("analytics refresh error: %s", exc)
        return jsonify({'error': str(exc)}), 500

