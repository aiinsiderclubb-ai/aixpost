"""guide routes extracted from run_test_v2."""
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

bp = Blueprint('guide', __name__)


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



@bp.route('/api/guide', methods=['GET'])
@jwt_required()
def get_guide_content():
    """Get guide markdown content"""
    try:
        # Read the markdown file
        guide_path = os.path.join(os.path.dirname(__file__), 'docs', 'guide.md')
        
        if not os.path.exists(guide_path):
            return jsonify({
                'success': False,
                'error': 'Guide content not found'
            }), 404
        
        with open(guide_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            'success': True,
            'content': content,
            'last_updated': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Get guide content error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to load guide content'
        }), 500

