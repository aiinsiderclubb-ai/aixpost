"""admin routes extracted from run_test_v2."""
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

bp = Blueprint('admin', __name__)


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



@bp.route('/api/v1/admin/users', methods=['GET'])
@jwt_required()
def admin_get_users():
    """Get all users for admin panel"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user or not current_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        search = request.args.get('search', '').strip()
        plan_filter = request.args.get('plan', '').strip().upper()
        status_filter = request.args.get('status', '').strip()
        
        # Build query
        query = User.query
        
        # Apply filters
        if search:
            query = query.filter(
                User.email.ilike(f'%{search}%') |
                User.first_name.ilike(f'%{search}%') |
                User.last_name.ilike(f'%{search}%')
            )
        
        if plan_filter in ['FREE', 'PLUS', 'PREMIUM']:
            query = query.filter(User.current_plan == plan_filter)
        
        if status_filter == 'active':
            query = query.filter(User.is_active == True)
        elif status_filter == 'inactive':
            query = query.filter(User.is_active == False)
        
        # Order and paginate
        query = query.order_by(User.created_at.desc())
        
        # Simple pagination for SQLite
        total = query.count()
        users = query.offset((page - 1) * per_page).limit(per_page).all()
        
        user_list = []
        for user in users:
            user_dict = user.to_dict()
            user_dict['usage_stats'] = user.get_usage_stats()
            user_dict['campaigns_count'] = Campaign.query.filter_by(user_id=user.id).count()
            
            # Add Telegram settings info
            telegram_settings = TelegramSettings.query.filter_by(user_id=user.id).first()
            user_dict['telegram_chat_id'] = telegram_settings.chat_id if telegram_settings else None
            user_dict['telegram_connected'] = telegram_settings is not None and telegram_settings.is_active
            
            user_list.append(user_dict)
        
        return jsonify({
            'users': user_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': page * per_page < total,
                'has_prev': page > 1
            },
            'filters': {
                'search': search,
                'plan': plan_filter,
                'status': status_filter
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Admin get users error: {e}")
        return jsonify({'error': 'Failed to retrieve users'}), 500

@bp.route('/api/v1/admin/analytics/overview', methods=['GET'])
@jwt_required()
def admin_analytics_overview():
    """Get platform analytics overview"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user or not current_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        # User statistics
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        
        # Plan distribution
        free_users = User.query.filter_by(current_plan='FREE').count()
        plus_users = User.query.filter_by(current_plan='PLUS').count()
        premium_users = User.query.filter_by(current_plan='PREMIUM').count()
        
        # Campaign statistics
        total_campaigns = Campaign.query.count()
        active_campaigns = Campaign.query.filter_by(status='running').count()
        completed_campaigns = Campaign.query.filter_by(status='completed').count()
        failed_campaigns = Campaign.query.filter_by(status='failed').count()
        
        # Usage statistics
        total_messages = db.session.query(db.func.sum(User.messages_sent_this_month)).scalar() or 0
        
        return jsonify({
            'users': {
                'total': total_users,
                'active': active_users,
                'new_this_month': 0,  # Would need date filtering
                'inactive': total_users - active_users
            },
            'plans': {
                'distribution': {
                    'FREE': free_users,
                    'PLUS': plus_users,
                    'PREMIUM': premium_users
                }
            },
            'campaigns': {
                'total': total_campaigns,
                'active': active_campaigns,
                'completed': completed_campaigns,
                'failed': failed_campaigns
            },
            'usage': {
                'total_messages': total_messages,
                'total_groups': 0,  # Would need groups table
                'avg_messages_per_user': round(total_messages / max(active_users, 1), 2)
            },
            'revenue': {
                'total': 0.0,  # Would need payment tracking
                'transactions': 0
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Admin analytics error: {e}")
        return jsonify({'error': 'Failed to retrieve analytics'}), 500

@bp.route('/api/admin/users/<int:user_id>/plan', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("100 per 15 minutes")  # Prevent abuse
def admin_update_user_plan(user_id):
    """Update user's plan (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
            
        data = request.get_json()
        new_plan = data.get('plan', '').upper()
        
        # Validate plan
        valid_plans = ['FREE', 'PLUS', 'PREMIUM']
        if new_plan not in valid_plans:
            return jsonify({
                'error': 'Invalid plan type',
                'valid_plans': valid_plans
            }), 400
            
        # Get target user
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
            
        # Store old plan for audit
        old_plan = target_user.current_plan
        
        # Update plan
        target_user.current_plan = new_plan
        target_user.update_plan_limits()
        target_user.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log audit action
        AuditLog.log_action(
            admin_id=current_user_id,
            user_id=user_id,
            action='plan_changed',
            old_value=old_plan,
            new_value=new_plan,
            request_obj=request
        )
        
        # Broadcast to user via WebSocket
        broadcast_to_user(user_id, 'plan_changed', {
            'user_id': user_id,
            'old_plan': old_plan,
            'new_plan': new_plan,
            'new_limits': target_user.get_plan_limits(),
            'timestamp': datetime.utcnow().isoformat()
        })
        
        logger.info(f"Admin {current_user_id} changed user {user_id} plan from {old_plan} to {new_plan}")
        
        return jsonify({
            'message': 'Plan updated successfully',
            'user': target_user.to_dict(),
            'old_plan': old_plan,
            'new_plan': new_plan
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin plan update error: {e}")
        return jsonify({'error': 'Failed to update user plan'}), 500

@bp.route('/api/admin/users/<int:user_id>/reset_usage', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("50 per 15 minutes")  # Prevent abuse
def admin_reset_user_usage(user_id):
    """Reset user's usage counters (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
            
        # Get target user
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
            
        # Store old usage for audit
        old_usage = target_user.messages_used
        
        # Reset usage
        target_user.reset_usage()
        target_user.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log audit action
        AuditLog.log_action(
            admin_id=current_user_id,
            user_id=user_id,
            action='usage_reset',
            old_value=str(old_usage),
            new_value='0',
            request_obj=request
        )
        
        # Broadcast to user via WebSocket
        broadcast_to_user(user_id, 'usage_reset', {
            'user_id': user_id,
            'old_usage': old_usage,
            'new_usage': 0,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        logger.info(f"Admin {current_user_id} reset usage for user {user_id} (was {old_usage})")
        
        return jsonify({
            'message': 'Usage reset successfully',
            'user': target_user.to_dict(),
            'old_usage': old_usage,
            'new_usage': 0
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin usage reset error: {e}")
        return jsonify({'error': 'Failed to reset user usage'}), 500

@bp.route('/api/admin/users/<int:user_id>/details', methods=['GET'])
@jwt_required()
@admin_required
def admin_get_user_details(user_id):
    """Get detailed user information (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
            
        # Get target user
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
            
        # Get user's telegram settings
        telegram_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        
        # Get recent audit logs for this user
        recent_audits = AuditLog.query.filter_by(user_id=user_id)\
            .order_by(AuditLog.timestamp.desc())\
            .limit(10).all()
            
        # Get user's campaign count
        campaign_count = Campaign.query.filter_by(user_id=user_id).count()
        
        return jsonify({
            'user': target_user.to_dict(include_sensitive=False),
            'telegram_settings': telegram_settings.to_dict() if telegram_settings else None,
            'recent_audits': [audit.to_dict() for audit in recent_audits],
            'campaign_count': campaign_count,
            'usage_stats': target_user.get_usage_stats()
        }), 200
        
    except Exception as e:
        logger.error(f"Admin user details error: {e}")
        return jsonify({'error': 'Failed to get user details'}), 500

@bp.route('/api/admin/audit_logs', methods=['GET'])
@jwt_required()
@admin_required
def admin_get_audit_logs():
    """Get audit logs (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 50, type=int), 100)  # Max 100 items
        
        # Get audit logs with pagination
        audit_logs = AuditLog.query\
            .order_by(AuditLog.timestamp.desc())\
            .paginate(page=page, per_page=limit, error_out=False)
        
        return jsonify({
            'audit_logs': [log.to_dict() for log in audit_logs.items],
            'pagination': {
                'page': page,
                'pages': audit_logs.pages,
                'per_page': limit,
                'total': audit_logs.total,
                'has_next': audit_logs.has_next,
                'has_prev': audit_logs.has_prev
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Admin audit logs error: {e}")
        return jsonify({'error': 'Failed to get audit logs'}), 500

@bp.route('/api/admin/users/<int:user_id>/ping-telegram', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("30 per 15 minutes")  # Rate limit for Telegram pings
def admin_ping_telegram(user_id):
    """Send test Telegram message to user (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
            
        # Get target user
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get Telegram settings
        telegram_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        if not telegram_settings:
            return jsonify({
                'success': False,
                'error': 'User has no Telegram settings configured'
            }), 400
        
        # Send admin ping message
        admin_message = (
            f"🔔 <b>Admin Ping Test</b>\n\n"
            f"Hello {target_user.first_name}!\n\n"
            f"This is a test message sent by admin: {admin_user.first_name} {admin_user.last_name}\n\n"
            f"Your Telegram notifications are working correctly.\n\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            f"📱 AIPostX Admin Panel"
        )
        
        success = send_telegram_message(telegram_settings.chat_id, admin_message)
        
        if success:
            # Log the ping action
            AuditLog.log_action(
                admin_id=current_user_id,
                user_id=user_id,
                action='telegram_ping',
                new_value=f'Admin ping sent to {telegram_settings.chat_id}',
                request_obj=request
            )
            
            # Update test status
            telegram_settings.last_test_sent = datetime.utcnow()
            telegram_settings.test_successful = True
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Test message sent to {target_user.first_name} {target_user.last_name}'
            }), 200
        else:
            telegram_settings.test_successful = False
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': 'Failed to send Telegram message. Check chat ID.'
            }), 400
            
    except Exception as e:
        logger.error(f"Admin ping Telegram error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to send ping message'
        }), 500

