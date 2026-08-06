"""campaigns routes extracted from run_test_v2."""
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

bp = Blueprint('campaigns', __name__)


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



@bp.route('/api/campaigns', methods=['GET'])
@jwt_required()
def get_campaigns():
    """Get user's campaigns"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        campaigns = Campaign.query.filter_by(user_id=user_id).order_by(Campaign.created_at.desc()).all()
        
        return jsonify({
            'campaigns': [campaign.to_dict() for campaign in campaigns]
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get campaigns',
            'message': str(e),
            'code': 'GET_CAMPAIGNS_ERROR'
        }), 500

@bp.route('/api/campaigns', methods=['POST'])
@jwt_required()
@limiter.limit("100 per 15 minutes")  # Moderate limit for campaign creation
def create_campaign():
    """Create a new campaign"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'message', 'group_urls']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'missing_fields': missing_fields,
                'code': 'MISSING_FIELDS'
            }), 400
        
        # Validate group URLs
        group_urls = data.get('group_urls', [])
        if not group_urls or len(group_urls) == 0:
            return jsonify({
                'error': 'At least one group URL is required',
                'code': 'NO_GROUPS'
            }), 400
        
        # Check user limits
        plan_limits = user.get_plan_limits()
        max_allowed_groups = min(data.get('max_groups', 10), plan_limits['max_groups'])
        
        if len(group_urls) > max_allowed_groups:
            return jsonify({
                'error': f'Too many groups. Your plan allows maximum {max_allowed_groups} groups.',
                'code': 'LIMIT_EXCEEDED'
            }), 400
        
        # Check message limit
        if user.messages_sent_this_month >= plan_limits['max_messages']:
            return jsonify({
                'error': f'Monthly message limit reached. Your plan allows {plan_limits["max_messages"]} messages per month.',
                'code': 'MESSAGE_LIMIT_EXCEEDED'
            }), 400
        
        # Create campaign
        import json
        campaign = Campaign(
            user_id=user_id,
            name=data['name'],
            message=data['message'],
            target_groups=json.dumps(group_urls[:max_allowed_groups]),
            max_groups=max_allowed_groups,
            min_delay=data.get('min_delay', 10),
            max_delay=data.get('max_delay', 60),
            total_groups=len(group_urls[:max_allowed_groups])
        )
        
        db.session.add(campaign)
        db.session.commit()
        
        return jsonify({
            'message': 'Campaign created successfully',
            'campaign': campaign.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to create campaign',
            'message': str(e),
            'code': 'CREATE_CAMPAIGN_ERROR'
        }), 500

@bp.route('/api/campaigns/<int:campaign_id>/start', methods=['POST'])
@jwt_required()
def start_campaign(campaign_id):
    """Start a Facebook posting campaign"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user_id).first()
        
        if not campaign:
            return jsonify({
                'error': 'Campaign not found',
                'code': 'CAMPAIGN_NOT_FOUND'
            }), 404
        
        if campaign.status != 'draft':
            return jsonify({
                'error': 'Campaign is not in draft status',
                'code': 'INVALID_STATUS'
            }), 400
        
        if not user.facebook_username or not user.facebook_password:
            return jsonify({
                'error': 'Facebook credentials not configured. Please update your settings.',
                'code': 'MISSING_CREDENTIALS'
            }), 400
        
        if not FACEBOOK_POSTER_AVAILABLE:
            return jsonify({
                'error': 'AI Posting is not available. Please check the bot integration.',
                'code': 'FACEBOOK_POSTER_NOT_AVAILABLE'
            }), 500

        task = _start_local_posting_thread(
            user_id=int(user_id),
            username=user.facebook_username,
            password=decrypt_password(user.facebook_password),
            message=campaign.message,
            group_urls=json.loads(campaign.target_groups),
            headless=bool(user.use_headless if user.use_headless is not None else True),
            use_templates=(campaign.message or '').strip().upper() == '[TEMPLATE_MODE]',
            template_mode='sequential',
            max_groups=campaign.max_groups,
            campaign_name=campaign.name,
        )
        campaign.status = 'running'
        campaign.started_at = datetime.utcnow()
        db.session.commit()
        return jsonify({
            'message': 'Campaign started successfully',
            'campaign': campaign.to_dict(),
            'task': task,
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to start campaign',
            'message': str(e),
            'code': 'START_CAMPAIGN_ERROR'
        }), 500

@bp.route('/api/campaigns/<int:campaign_id>/stop', methods=['POST'])
@jwt_required()
def stop_campaign(campaign_id):
    """Stop a running Facebook posting campaign"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user_id).first()
        
        if not campaign:
            return jsonify({
                'error': 'Campaign not found',
                'code': 'CAMPAIGN_NOT_FOUND'
            }), 404
        
        if campaign.status != 'running':
            return jsonify({
                'error': 'Campaign is not running',
                'code': 'INVALID_STATUS'
            }), 400
        
        # Prefer durable task control used by the modern posting path.
        stopped = False
        try:
            active = runtime_store.get_latest_task(int(user_id), task_type='posting')
            if active and active.get('status') in {
                'queued', 'running', 'waiting_manual', 'paused', 'stopping'
            }:
                runtime_store.request_stop(int(active['id']), int(user_id))
                stopped = True
        except Exception as stop_err:
            logger.warning("Campaign stop via runtime_store failed: %s", stop_err)
        if not stopped and poster_instance and getattr(poster_instance, 'is_posting', False):
            poster_instance.stop_posting_method()
        
        # Update campaign status
        campaign.status = 'stopped'
        campaign.completed_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Campaign stop requested',
            'campaign': campaign.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to stop campaign',
            'message': str(e),
            'code': 'STOP_CAMPAIGN_ERROR'
        }), 500

@bp.route('/api/campaigns/<int:campaign_id>/status', methods=['GET'])
@jwt_required()
def get_campaign_status(campaign_id):
    """Get real-time status of a campaign"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user_id).first()
        
        if not campaign:
            return jsonify({
                'error': 'Campaign not found',
                'code': 'CAMPAIGN_NOT_FOUND'
            }), 404
        
        return jsonify({
            'campaign': campaign.to_dict(),
            'live_status': _task_snapshot_from_poster(int(user_id), runtime_store.get_latest_task(int(user_id), 'posting'), poster_instance.get_status() if poster_instance else None)
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get campaign status',
            'message': str(e),
            'code': 'GET_STATUS_ERROR'
        }), 500

@bp.route('/api/campaigns/<int:campaign_id>/rerun', methods=['POST'])
@jwt_required()
def rerun_campaign(campaign_id):
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=get_jwt_identity()).first()
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    campaign.status = 'draft'
    db.session.commit()
    return start_campaign(campaign_id)

