"""user routes extracted from run_test_v2."""
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

bp = Blueprint('user', __name__)


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



@bp.route('/api/user/settings', methods=['GET'])
@jwt_required()
def get_user_settings():
    """Get user settings"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        return jsonify({
            'settings': {
                'facebook_username': user.facebook_username or '',
                'facebook_password_set': bool(user.facebook_password),  # Don't return actual password
                'use_headless': user.use_headless if user.use_headless is not None else True
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get settings',
            'message': str(e),
            'code': 'GET_SETTINGS_ERROR'
        }), 500

@bp.route('/api/user/settings', methods=['POST'])
@jwt_required()
def update_user_settings():
    """Update user settings"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        data = request.get_json()
        
        # Update Facebook credentials
        if 'facebook_username' in data:
            user.facebook_username = data['facebook_username']
        
        if 'facebook_password' in data and data['facebook_password']:
            user.facebook_password = encrypt_password(data['facebook_password'])
        
        if 'use_headless' in data:
            user.use_headless = data['use_headless']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Settings updated successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to update settings',
            'message': str(e),
            'code': 'UPDATE_SETTINGS_ERROR'
        }), 500

@bp.route('/api/user/plan', methods=['POST'])
@admin_required
def update_user_plan():
    """Admin-only plan change (self-service upgrades disabled)."""
    try:
        admin_id = get_jwt_identity()
        admin_user = User.query.get(admin_id)
        data = request.get_json() or {}
        target_user_id = data.get('user_id') or admin_id
        current_user = User.query.get(target_user_id)

        if not current_user:
            return jsonify({'error': 'User not found'}), 404

        new_plan = (data.get('plan') or '').upper()
        valid_plans = ['FREE', 'PLUS', 'PREMIUM']
        if new_plan not in valid_plans:
            return jsonify({
                'error': 'Invalid plan',
                'valid_plans': valid_plans
            }), 400

        previous = current_user.current_plan
        current_user.current_plan = new_plan
        if hasattr(current_user, 'update_plan_limits'):
            current_user.update_plan_limits()
        current_user.updated_at = datetime.utcnow()
        try:
            AuditLog.log_action(
                admin_id=int(admin_id),
                user_id=current_user.id,
                action='plan_changed',
                old_value=previous,
                new_value=new_plan,
                request_obj=request,
            )
        except Exception as audit_err:
            logger.warning("Plan change audit skipped: %s", audit_err)
        db.session.commit()

        return jsonify({
            'message': f'Plan updated to {new_plan}',
            'current_plan': new_plan,
            'user': current_user.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Plan update error: {e}")
        return jsonify({
            'error': 'Failed to update plan',
            'message': str(e)
        }), 500

