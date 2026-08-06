"""pages routes extracted from run_test_v2."""
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

bp = Blueprint('pages', __name__)


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



@bp.route('/analytics')
@jwt_required()
def analytics():
    """Analytics page - shows performance metrics"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)

        from bot.analytics_db import analytics_db
        from app.core.config import AppConfig

        dashboard = analytics_db.get_dashboard_data(int(user_id))
        top_groups = dashboard.get('top_groups', [])
        recent_posts = dashboard.get('recent_posts', [])
        recommended_groups = [g for g in top_groups if (g.get('recommendation_score') or 0) >= 0.8]
        avoid_groups = [g for g in top_groups if (g.get('post_success_rate') or 0) * 100 < 50]
        worker_mode = 'rq' if AppConfig.USE_RQ_WORKERS else 'in-process'

        return render_template(
            'analytics.html',
            total_posts=dashboard.get('total_posts', 0),
            scraped_posts=dashboard.get('scraped_posts', 0),
            avg_engagement_rate=dashboard.get('avg_engagement_rate', 0),
            active_groups=dashboard.get('active_groups', 0),
            success_rate=dashboard.get('success_rate', 0),
            pending_checks=dashboard.get('pending_checks', 0),
            completed_checks=dashboard.get('completed_checks', 0),
            failed_checks=dashboard.get('failed_checks', 0),
            top_groups=top_groups,
            performance_dates=dashboard.get('performance_dates', []),
            performance_data=dashboard.get('performance_data', []),
            engagement_breakdown=dashboard.get('engagement_breakdown', [0, 0, 0]),
            recent_posts=recent_posts,
            recommended_groups=recommended_groups,
            avoid_groups=avoid_groups,
            worker_mode=worker_mode,
            current_user=current_user,
        )

    except Exception as e:
        logger.error(f"Analytics page error: {e}")
        return render_template(
            'analytics.html',
            error_message=f"Error loading analytics: {str(e)}",
            total_posts=0,
            scraped_posts=0,
            avg_engagement_rate=0,
            active_groups=0,
            success_rate=0,
            pending_checks=0,
            completed_checks=0,
            failed_checks=0,
            top_groups=[],
            recommended_groups=[],
            avoid_groups=[],
            performance_dates=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            performance_data=[0, 0, 0, 0, 0, 0, 0],
            engagement_breakdown=[1, 1, 1],
            recent_posts=[],
            worker_mode='in-process',
        )

@bp.route('/dashboard')
@jwt_required()
def dashboard():
    """Dashboard page"""
    try:
        user_id = get_jwt_identity()
        print(f"Dashboard: Got user_id: {user_id}")
        
        current_user = User.query.get(user_id)
        print(f"Dashboard: Got user: {current_user}")
        
        if not current_user:
            print("Dashboard: User not found")
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)
        
        # Get dashboard data (safe without Campaign model)
        try:
            campaigns = Campaign.query.filter_by(user_id=user_id).all()
            total_campaigns = len(campaigns)
            active_campaigns = len([c for c in campaigns if c.status == 'running'])
        except Exception as campaign_error:
            print(f"Dashboard: Campaign error: {campaign_error}")
            # Use mock data if Campaign model not available
            campaigns = []
            total_campaigns = 0
            active_campaigns = 0
        
        # Get Telegram status
        telegram_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        telegram_connected = telegram_settings and telegram_settings.is_active
        
        # Derive real totals for groups and messages
        total_groups = 0
        try:
            # 1) Try fetched groups file (per user)
            groups_full = get_fetched_groups(user_id)
            total_groups = len(groups_full or [])
        except Exception:
            total_groups = 0

        # Analytics-based aggregates (per user)
        posts_total = 0
        groups_posted_unique = 0
        try:
            # 2) If analytics has more groups, use unique count and totals
            import sqlite3
            from bot.analytics_db import analytics_db
            with sqlite3.connect(analytics_db.db_path) as conn:
                cur = conn.cursor()
                if current_user.is_admin():
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE is_legacy = 0')
                else:
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE user_id = ? AND is_legacy = 0', (user_id,))
                row = cur.fetchone()
                analytics_groups = (row[0] or 0) if row else 0
                total_groups = max(total_groups, analytics_groups)

                if current_user.is_admin():
                    cur.execute('SELECT COUNT(*) FROM post_analytics WHERE is_legacy = 0')
                    posts_total = (cur.fetchone()[0] or 0)
                else:
                    cur.execute('SELECT COUNT(*) FROM post_analytics WHERE user_id = ? AND is_legacy = 0', (user_id,))
                    posts_total = (cur.fetchone()[0] or 0)

                if current_user.is_admin():
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE is_legacy = 0')
                    groups_posted_unique = (cur.fetchone()[0] or 0)
                else:
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE user_id = ? AND is_legacy = 0', (user_id,))
                    groups_posted_unique = (cur.fetchone()[0] or 0)
        except Exception:
            pass

        # Create stats object for template
        stats = {
            'total_campaigns': total_campaigns,
            'active_campaigns': active_campaigns,
            'total_groups': total_groups,
            'messages_sent': current_user.messages_sent_this_month,
            'posts_total': posts_total,
            'groups_posted_unique': groups_posted_unique,
            'success_rate': '95%',  # simple placeholder, analytics page shows real
            'telegram_connected': telegram_connected
        }
        
        print(f"Dashboard: Rendering template...")
        return render_template('dashboard.html', 
                             current_user=current_user,
                             total_campaigns=total_campaigns,
                             active_campaigns=active_campaigns,
                             stats=stats,
                             dashboard_stats=stats)
    except Exception as e:
        print(f"Dashboard error: {e}")
        logger.error(f"Dashboard error: {e}")
        # Instead of redirect, return error for debugging
        return jsonify({'error': f'Dashboard error: {str(e)}'}), 500

@bp.route('/group-search')
@jwt_required()
def group_search_page():
    """Dedicated page for fetching/searching Facebook groups."""
    try:
        user_id = int(get_jwt_identity())
        current_user = User.query.get(user_id)
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)

        groups_full = get_fetched_groups(user_id) or []
        try:
            from bot.language_classifier import LanguageClassifier
            groups_full = LanguageClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass
        try:
            from bot.geo_classifier import GeoClassifier
            groups_full = GeoClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass

        latest_fetch_task = runtime_store.get_latest_task(user_id, 'fetch')
        has_saved_credentials = bool(current_user.facebook_username and current_user.facebook_password)

        return render_template(
            'group_search.html',
            current_user=current_user,
            total_groups=len(groups_full),
            preview_groups=groups_full[:50],
            last_fetched_at=_groups_file_mtime(user_id),
            has_saved_credentials=has_saved_credentials,
            saved_username=current_user.facebook_username or '',
            latest_fetch_task=latest_fetch_task,
        )
    except Exception as e:
        logger.error(f"Group search page error: {e}")
        return render_template(
            'group_search.html',
            current_user=None,
            total_groups=0,
            preview_groups=[],
            last_fetched_at=None,
            has_saved_credentials=False,
            saved_username='',
            latest_fetch_task=None,
            error_message=str(e),
        )

@bp.route('/groups')
@jwt_required()
def groups_page():
    """Groups page"""
    try:
        user_id = get_jwt_identity()
        print(f"Groups page - user_id: {user_id}")
        logger.info(f"Groups page - user_id: {user_id}")
        
        current_user = User.query.get(user_id)
        print(f"Groups page - current_user: {current_user}")
        logger.info(f"Groups page - current_user: {current_user}")
        
        if not current_user:
            print("Groups page - User not found")
            logger.error("Groups page - User not found")
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)
        
        # Load groups from fetcher output (per user)
        try:
            groups_full = get_fetched_groups(user_id)
        except Exception:
            groups_full = []
        workspace_map = runtime_store.get_group_workspace_map(int(user_id))
        saved_filters = runtime_store.list_filters(int(user_id))
        
        # Classify languages
        try:
            from bot.language_classifier import LanguageClassifier
            groups_full = LanguageClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass
        try:
            from bot.geo_classifier import GeoClassifier
            groups_full = GeoClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass
        
        # Query params
        from flask import request
        search = request.args.get('search', '').strip()
        per_page = int(request.args.get('per_page', 12))
        page = int(request.args.get('page', 1))
        selected_languages = request.args.getlist('languages')
        selected_countries = request.args.getlist('countries')
        segment = request.args.get('segment', '').strip().lower()

        for g in groups_full:
            meta = workspace_map.get(g.get('url', '')) or {}
            g['workspace'] = meta
            g['is_blacklisted'] = bool(meta.get('is_blacklisted'))
            g['is_whitelisted'] = bool(meta.get('is_whitelisted'))
            g['last_posted_at'] = meta.get('last_posted_at')
            g['last_post_status'] = meta.get('last_post_status')
            g['last_campaign_name'] = meta.get('last_campaign_name')
        
        # Filter by search
        if search:
            groups_filtered = [g for g in groups_full if search.lower() in (g.get('name','').lower())]
        else:
            groups_filtered = groups_full
        
        # Filter by languages
        if selected_languages:
            groups_filtered = [g for g in groups_filtered if g.get('language_tag','unknown') in selected_languages]
        if selected_countries:
            groups_filtered = [g for g in groups_filtered if g.get('country_tag','unknown') in selected_countries]

        if segment == 'failed':
            groups_filtered = [g for g in groups_filtered if g.get('last_post_status') == 'failed']
        elif segment == 'recently_posted':
            groups_filtered = [g for g in groups_filtered if g.get('last_posted_at')]
        elif segment == 'blacklist':
            groups_filtered = [g for g in groups_filtered if g.get('is_blacklisted')]
        elif segment == 'whitelist':
            groups_filtered = [g for g in groups_filtered if g.get('is_whitelisted')]
        elif segment == 'new':
            groups_filtered = [g for g in groups_filtered if not g.get('last_posted_at')]
        elif segment == 'german':
            groups_filtered = [g for g in groups_filtered if (g.get('language_tag') or '').lower() == 'german']
        
        total = len(groups_filtered)
        start = (page - 1) * per_page
        end = start + per_page
        groups_page_items = groups_filtered[start:end]
        
        # Build language statistics
        try:
            from bot.language_classifier import LanguageClassifier as _LC
            language_stats = {}
            for g in groups_full:
                lang = g.get('language_tag','unknown')
                language_stats[lang] = language_stats.get(lang, 0) + 1
            language_classifier = _LC
        except Exception:
            language_stats = {}
            language_classifier = None
        try:
            country_stats = {}
            for g in groups_full:
                country = g.get('country_tag', 'unknown')
                country_stats[country] = country_stats.get(country, 0) + 1
        except Exception:
            country_stats = {}
        
        class MockPagination:
            def __init__(self, total, page, per_page):
                self.total = total
                self.page = page
                self.per_page = per_page
                self.pages = max(1, (total + per_page - 1) // per_page)
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        pagination = MockPagination(total, page, per_page)
        
        return render_template('groups.html', 
                             current_user=current_user,
                             pagination=pagination,
                             groups=groups_page_items,
                             search=search,
                             segment=segment,
                             selected_languages=selected_languages,
                             selected_countries=selected_countries,
                             language_stats=language_stats,
                             language_classifier=language_classifier,
                             country_stats=country_stats,
                             saved_filters=saved_filters)
    except Exception as e:
        logger.error(f"Groups page error: {e}")
        return redirect(url_for('home'))

@bp.route('/poster')
@jwt_required()
def poster_page():
    """Poster page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)
        
        # Load groups for selection on the poster page (per user)
        try:
            groups_full = get_fetched_groups(user_id)
        except Exception:
            groups_full = []
        
        # Add language tags for filters
        try:
            from bot.language_classifier import LanguageClassifier
            groups_full = LanguageClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass
        try:
            from bot.geo_classifier import GeoClassifier
            groups_full = GeoClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass

        language_stats = {}
        country_stats = {}
        for group in groups_full:
            lang = group.get('language_tag', 'unknown') or 'unknown'
            language_stats[lang] = language_stats.get(lang, 0) + 1
            country = group.get('country_tag', 'unknown') or 'unknown'
            country_stats[country] = country_stats.get(country, 0) + 1

        return render_template(
            'poster.html',
            current_user=current_user,
            groups=groups_full,
            language_stats=language_stats,
            country_stats=country_stats
        )
    except Exception as e:
        logger.error(f"Poster page error: {e}")
        return redirect(url_for('home'))

@bp.route('/scheduler')
@jwt_required()
def scheduler_page():
    """Scheduler page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get scheduled jobs for the user
        try:
            scheduled_jobs = ScheduledJob.query.filter_by(user_id=user_id).all()
        except Exception as job_error:
            logger.error(f"Error fetching scheduled jobs: {job_error}")
            scheduled_jobs = []
        
        return render_template('scheduler.html', 
                             current_user=current_user,
                             scheduled_jobs=scheduled_jobs)
    except Exception as e:
        logger.error(f"Scheduler page error: {e}")
        return redirect(url_for('home'))

@bp.route('/templates')
@jwt_required()
def template_manager():
    """Template manager page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        return render_template('template_manager.html', current_user=current_user)
    except Exception as e:
        logger.error(f"Template manager error: {e}")
        return redirect(url_for('home'))

@bp.route('/telegram')
@jwt_required()
def telegram_page():
    """Telegram bot configuration page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        return render_template('telegram.html', current_user=current_user)
        
    except Exception as e:
        logger.error(f"Telegram page error: {e}")
        return redirect(url_for('pages.dashboard'))

@bp.route('/guide')
@jwt_required()
def guide_page():
    """How It Works guide page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        return render_template('guide.html', current_user=current_user)
        
    except Exception as e:
        logger.error(f"Guide page error: {e}")
        return redirect(url_for('pages.dashboard'))

@bp.route('/plans')
@jwt_required()
def plans_page():
    """Plans page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Plans data as dictionary (expected by template)
        plans = {
            'FREE': {
                'name': 'FREE',
                'price': '$0',
                'price_period': 'forever',
                'limits': 'Perfect for testing',
                'color': 'secondary',
                'is_current': current_user.current_plan == 'FREE',
                'button_text': 'Current Plan' if current_user.current_plan == 'FREE' else 'Downgrade',
                'features': [
                    '✅ Up to 5 groups per campaign',
                    '✅ Basic analytics',
                    '✅ Standard support',
                    '❌ Manual posting only'
                ]
            },
            'PLUS': {
                'name': 'PLUS',
                'price': '$29',
                'price_period': 'per month',
                'limits': 'For growing businesses',
                'color': 'primary',
                'is_current': current_user.current_plan == 'PLUS',
                'button_text': 'Current Plan' if current_user.current_plan == 'PLUS' else 'Upgrade to Plus',
                'features': [
                    '✅ Up to 50 groups per campaign',
                    '✅ Advanced analytics',
                    '✅ Priority support',
                    '✅ Scheduled posting',
                    '✅ Custom templates'
                ]
            },
            'PREMIUM': {
                'name': 'PREMIUM',
                'price': '$99',
                'price_period': 'per month',
                'limits': 'For power users',
                'color': 'success',
                'is_current': current_user.current_plan == 'PREMIUM',
                'button_text': 'Current Plan' if current_user.current_plan == 'PREMIUM' else 'Upgrade to Premium',
                'features': [
                    '✅ Unlimited groups',
                    '✅ Full analytics suite',
                    '✅ VIP support',
                    '✅ Advanced automation',
                    '✅ API access',
                    '✅ White-label options'
                ]
            }
        }
        
        return render_template('plans.html', 
                             current_user=current_user,
                             plans=plans)
    except Exception as e:
        logger.error(f"Plans page error: {e}")
        return redirect(url_for('home'))

@bp.route('/admin')
@jwt_required()
@admin_required
def admin_panel():
    """Admin panel - requires admin role"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if user is admin
        if not current_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        return render_template('admin.html', current_user=current_user)
    except Exception as e:
        logger.error(f"Admin panel error: {e}")
        return redirect(url_for('home'))

