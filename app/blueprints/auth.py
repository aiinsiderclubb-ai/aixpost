"""auth routes extracted from run_test_v2."""
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

bp = Blueprint('auth', __name__)


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



@bp.route('/api/auth/register', methods=['POST'])
@limiter.limit("5 per minute")  # Strict limit for registration
def register():
    """Register a new user"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'password', 'first_name', 'last_name']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'missing_fields': missing_fields,
                'code': 'MISSING_FIELDS'
            }), 400
        
        email = data['email'].lower().strip()
        password = data['password']
        first_name = data['first_name'].strip()
        last_name = data['last_name'].strip()
        
        # Validate email format
        if not validate_email(email):
            return jsonify({
                'error': 'Invalid email format',
                'code': 'INVALID_EMAIL'
            }), 400
        
        # Validate password strength
        password_errors = validate_password(password)
        if password_errors:
            return jsonify({
                'error': 'Password does not meet requirements',
                'requirements': password_errors,
                'code': 'WEAK_PASSWORD'
            }), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({
                'error': 'User with this email already exists',
                'code': 'USER_EXISTS'
            }), 409
        
        # Create new user
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            current_plan='FREE',
            email_verified=True  # Skip email verification for testing
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Create JWT tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        # Create response with tokens
        response = jsonify({
            'message': 'User registered successfully',
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        })
        
        # Set tokens as cookies for web interface
        response.set_cookie('access_token', access_token, 
                          max_age=24*60*60,  # 24 hours
                          secure=bool(app.config.get('JWT_COOKIE_SECURE', False)),
                          httponly=True,
                          samesite='Lax')
        
        response.set_cookie('refresh_token', refresh_token, 
                          max_age=30*24*60*60,  # 30 days
                          secure=bool(app.config.get('JWT_COOKIE_SECURE', False)),
                          httponly=True,
                          samesite='Lax')
        
        return response, 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Registration failed',
            'message': str(e),
            'code': 'REGISTRATION_ERROR'
        }), 500

@bp.route('/api/auth/login', methods=['POST'])
@limiter.limit("10 per minute")  # Strict limit for login attempts
def login():
    """Authenticate user and return JWT tokens"""
    try:
        data = request.get_json()
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({
                'error': 'Email and password are required',
                'code': 'MISSING_CREDENTIALS'
            }), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({
                'error': 'Invalid email or password',
                'code': 'INVALID_CREDENTIALS'
            }), 401
        
        # Update last login
        user.update_last_login()
        db.session.commit()
        
        # Create JWT tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        # Create response with tokens
        response = jsonify({
            'message': 'Login successful',
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        })
        
        # Set tokens as cookies for web interface
        response.set_cookie('access_token', access_token, 
                          max_age=24*60*60,  # 24 hours
                          secure=bool(app.config.get('JWT_COOKIE_SECURE', False)),
                          httponly=True,
                          samesite='Lax')
        
        response.set_cookie('refresh_token', refresh_token, 
                          max_age=30*24*60*60,  # 30 days
                          secure=bool(app.config.get('JWT_COOKIE_SECURE', False)),
                          httponly=True,
                          samesite='Lax')
        
        return response, 200
        
    except Exception as e:
        return jsonify({
            'error': 'Login failed',
            'message': str(e),
            'code': 'LOGIN_ERROR'
        }), 500

@bp.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user information"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        return jsonify({
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get user',
            'message': str(e),
            'code': 'GET_USER_ERROR'
        }), 500

@bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user and clear cookies"""
    try:
        response = jsonify({'message': 'Logout successful'})
        
        # Clear cookies
        response.set_cookie('access_token', '', expires=0)
        response.set_cookie('refresh_token', '', expires=0)
        
        return response, 200
        
    except Exception as e:
        return jsonify({
            'error': 'Logout failed',
            'message': str(e)
        }), 500

