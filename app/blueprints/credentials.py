"""credentials routes extracted from run_test_v2."""
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

bp = Blueprint('credentials', __name__)


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



@bp.route('/api/credentials', methods=['GET'])
@jwt_required()
def api_credentials_status():
    """Check whether Facebook credentials are saved for the current user."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        has_saved = bool(user.facebook_username and user.facebook_password)
        return jsonify({
            'has_saved_credentials': has_saved,
            'username': user.facebook_username if has_saved else None,
        }), 200
    except Exception as exc:
        logger.error("credentials status error: %s", exc)
        return jsonify({'error': str(exc)}), 500

@bp.route('/api/credentials/load', methods=['POST'])
@jwt_required()
def api_credentials_load():
    """Return saved-credential state without ever exposing a password."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user.facebook_username or not user.facebook_password:
            return jsonify({'error': 'No saved credentials'}), 404
        return jsonify({
            'username': user.facebook_username,
            'has_saved_credentials': True,
        }), 200
    except Exception as exc:
        logger.error("credentials load error: %s", exc)
        return jsonify({'error': str(exc)}), 500

