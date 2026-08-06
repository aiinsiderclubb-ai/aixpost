"""infra routes extracted from run_test_v2."""
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

bp = Blueprint('infra', __name__)


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



@bp.route('/api/csrf-token', methods=['GET'])
def api_csrf_token():
    """Expose CSRF token for cookie-authenticated SPA-style fetch calls."""
    return jsonify({'csrf_token': generate_csrf()})

@bp.route('/')
def home():
    return render_template_string(MAIN_PAGE_HTML)

@bp.route('/test_groups_simple')
def test_groups_simple():
    """Debug-only probe route."""
    if not app.debug:
        return jsonify({'error': 'Not found'}), 404
    return "Groups page works!"

@bp.route('/groups_no_jwt')
def groups_no_jwt():
    """Debug-only groups page without JWT."""
    if not app.debug:
        return jsonify({'error': 'Not found'}), 404

    class MockPagination:
        def __init__(self):
            self.pages = 1
            self.page = 1
            self.per_page = 10
            self.total = 0
            self.has_prev = False
            self.has_next = False
            self.prev_num = None
            self.next_num = None

    return render_template('groups.html',
                         current_user={'first_name': 'Test', 'last_name': 'User'},
                         pagination=MockPagination(),
                         groups=[],
                         total_groups=0)

@bp.route('/health')
def health():
    checks = {'database': False, 'runtime_store': False, 'redis': False}
    try:
        User.query.limit(1).all()
        checks['database'] = True
    except Exception as exc:
        logger.warning("Primary database readiness check failed: %s", exc)
    try:
        with runtime_store.connect() as conn:
            conn.execute('SELECT 1').fetchone()
        checks['runtime_store'] = True
    except Exception as exc:
        logger.warning("Runtime database readiness check failed: %s", exc)
    try:
        redis_conn.ping()
        checks['redis'] = True
    except Exception as exc:
        logger.info("Redis unavailable for health check: %s", exc)
    status_code = 200 if checks['database'] and checks['runtime_store'] else 503
    return jsonify({
        'status': 'healthy' if status_code == 200 else 'degraded',
        'checks': checks,
        'rq_enabled': task_dispatcher.use_rq,
        'version': '2.0',
    }), status_code

@bp.route('/test_auth')
def test_auth():
    """Test authentication status (for debugging)"""
    if not app.debug:
        return jsonify({'error': 'Not found'}), 404
    try:
        # Check if user is authenticated
        token = request.headers.get('Authorization') or request.cookies.get('access_token')
        
        if not token:
            return jsonify({
                'authenticated': False,
                'message': 'No token found',
                'cookies': dict(request.cookies),
                'headers': dict(request.headers)
            }), 200
        
        # Clean token
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        # Verify token
        try:
            from flask_jwt_extended import decode_token
            decoded = decode_token(token)
            user_id = decoded['sub']
            
            user = User.query.get(user_id)
            
            return jsonify({
                'authenticated': True,
                'user_id': user_id,
                'user': user.to_dict() if user else None,
                'token_valid': True
            }), 200
            
        except Exception as token_error:
            return jsonify({
                'authenticated': False,
                'message': 'Invalid token',
                'error': str(token_error)
            }), 200
            
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

