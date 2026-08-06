"""
Authentication API endpoints for Facebook SaaS Platform
Handles user registration, login, password reset, and JWT management
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt_identity, get_jwt, verify_jwt_in_request
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any

from app import db, limiter, mail
from app.models.user import User
from app.models.subscription import SubscriptionPlan
from app.utils.validators import validate_email, validate_password
from app.utils.helpers import send_email

auth_bp = Blueprint('auth', __name__)

# Rate limiting configuration
REGISTER_RATE_LIMIT = "5 per hour"
LOGIN_RATE_LIMIT = "10 per minute" 
PASSWORD_RESET_RATE_LIMIT = "3 per hour"


@auth_bp.route('/register', methods=['POST'])
@limiter.limit(REGISTER_RATE_LIMIT)
def register():
    """
    Register a new user
    
    Expected JSON payload:
    {
        "email": "user@example.com",
        "password": "securepassword",
        "first_name": "John",
        "last_name": "Doe"
    }
    """
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
        existing_user = User.find_by_email(email)
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
            current_plan='FREE'
        )
        user.set_password(password)
        
        # Set admin role if email is in admin list
        if email in current_app.config.get('ADMIN_EMAILS', []):
            user.role = 'admin'
        
        db.session.add(user)
        db.session.commit()
        
        # Send verification email
        try:
            send_verification_email(user)
        except Exception as e:
            current_app.logger.error(f"Failed to send verification email: {str(e)}")
            # Don't fail registration if email fails
        
        # Create JWT tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        current_app.logger.info(f"New user registered: {email}")
        
        return jsonify({
            'message': 'User registered successfully',
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token,
            'verification_required': not user.email_verified
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Registration error: {str(e)}")
        return jsonify({
            'error': 'Registration failed',
            'message': 'An unexpected error occurred',
            'code': 'REGISTRATION_ERROR'
        }), 500


@auth_bp.route('/login', methods=['POST'])
@limiter.limit(LOGIN_RATE_LIMIT)
def login():
    """
    Authenticate user and return JWT tokens
    
    Expected JSON payload:
    {
        "email": "user@example.com",
        "password": "securepassword"
    }
    """
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
        user = User.find_by_email(email)
        if not user or not user.check_password(password):
            return jsonify({
                'error': 'Invalid email or password',
                'code': 'INVALID_CREDENTIALS'
            }), 401
        
        # Check if user is active
        if not user.is_active:
            return jsonify({
                'error': 'Account is deactivated',
                'code': 'ACCOUNT_DEACTIVATED'
            }), 403
        
        # Update last login
        user.update_last_login()
        
        # Create JWT tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        current_app.logger.info(f"User logged in: {email}")
        
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict(),
            'access_token': access_token,
            'refresh_token': refresh_token
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Login error: {str(e)}")
        return jsonify({
            'error': 'Login failed',
            'message': 'An unexpected error occurred',
            'code': 'LOGIN_ERROR'
        }), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout user (invalidate tokens)
    Note: In a production system, you'd want to implement token blacklisting
    """
    try:
        # TODO: Add token to blacklist in Redis
        # For now, we'll rely on client-side token removal
        
        return jsonify({
            'message': 'Logout successful'
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Logout error: {str(e)}")
        return jsonify({
            'error': 'Logout failed',
            'message': 'An unexpected error occurred',
            'code': 'LOGOUT_ERROR'
        }), 500


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Refresh access token using refresh token
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Verify user still exists and is active
        user = User.query.get(current_user_id)
        if not user or not user.is_active:
            return jsonify({
                'error': 'User not found or inactive',
                'code': 'USER_INACTIVE'
            }), 401
        
        # Create new access token
        access_token = create_access_token(identity=current_user_id)
        
        return jsonify({
            'access_token': access_token
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Token refresh error: {str(e)}")
        return jsonify({
            'error': 'Token refresh failed',
            'message': 'An unexpected error occurred',
            'code': 'REFRESH_ERROR'
        }), 500


@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit(PASSWORD_RESET_RATE_LIMIT)
def forgot_password():
    """
    Send password reset email
    
    Expected JSON payload:
    {
        "email": "user@example.com"
    }
    """
    try:
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        
        if not email:
            return jsonify({
                'error': 'Email is required',
                'code': 'MISSING_EMAIL'
            }), 400
        
        if not validate_email(email):
            return jsonify({
                'error': 'Invalid email format',
                'code': 'INVALID_EMAIL'
            }), 400
        
        user = User.find_by_email(email)
        
        # Always return success to prevent email enumeration
        # Even if user doesn't exist, we pretend we sent an email
        message = 'If an account with this email exists, you will receive a password reset link'
        
        if user and user.is_active:
            # Generate reset token
            reset_token = user.get_reset_token(expires_in=3600)  # 1 hour
            db.session.commit()
            
            # Send reset email
            try:
                send_password_reset_email(user, reset_token)
                current_app.logger.info(f"Password reset email sent to: {email}")
            except Exception as e:
                current_app.logger.error(f"Failed to send password reset email: {str(e)}")
        
        return jsonify({
            'message': message
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Password reset request error: {str(e)}")
        return jsonify({
            'error': 'Password reset request failed',
            'message': 'An unexpected error occurred',
            'code': 'RESET_REQUEST_ERROR'
        }), 500


@auth_bp.route('/reset-password', methods=['POST'])
@limiter.limit(PASSWORD_RESET_RATE_LIMIT)
def reset_password():
    """
    Reset password using reset token
    
    Expected JSON payload:
    {
        "token": "reset_token_here",
        "new_password": "newsecurepassword"
    }
    """
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        new_password = data.get('new_password', '')
        
        if not token or not new_password:
            return jsonify({
                'error': 'Token and new password are required',
                'code': 'MISSING_FIELDS'
            }), 400
        
        # Validate password strength
        password_errors = validate_password(new_password)
        if password_errors:
            return jsonify({
                'error': 'Password does not meet requirements',
                'requirements': password_errors,
                'code': 'WEAK_PASSWORD'
            }), 400
        
        # Find user by reset token
        user = User.find_by_reset_token(token)
        if not user:
            return jsonify({
                'error': 'Invalid or expired reset token',
                'code': 'INVALID_TOKEN'
            }), 400
        
        # Verify token is still valid
        if not user.verify_reset_token(token):
            return jsonify({
                'error': 'Invalid or expired reset token',
                'code': 'EXPIRED_TOKEN'
            }), 400
        
        # Update password
        user.set_password(new_password)
        user.clear_reset_token()
        db.session.commit()
        
        current_app.logger.info(f"Password reset successful for user: {user.email}")
        
        return jsonify({
            'message': 'Password reset successful'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Password reset error: {str(e)}")
        return jsonify({
            'error': 'Password reset failed',
            'message': 'An unexpected error occurred',
            'code': 'RESET_ERROR'
        }), 500


@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """
    Verify email address using verification token
    
    Expected JSON payload:
    {
        "token": "verification_token_here"
    }
    """
    try:
        data = request.get_json()
        token = data.get('token', '').strip()
        
        if not token:
            return jsonify({
                'error': 'Verification token is required',
                'code': 'MISSING_TOKEN'
            }), 400
        
        # Find user by verification token
        user = User.find_by_verification_token(token)
        if not user:
            return jsonify({
                'error': 'Invalid verification token',
                'code': 'INVALID_TOKEN'
            }), 400
        
        # Verify email
        if user.verify_email(token):
            db.session.commit()
            current_app.logger.info(f"Email verified for user: {user.email}")
            
            return jsonify({
                'message': 'Email verified successfully',
                'user': user.to_dict()
            }), 200
        else:
            return jsonify({
                'error': 'Email verification failed',
                'code': 'VERIFICATION_FAILED'
            }), 400
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Email verification error: {str(e)}")
        return jsonify({
            'error': 'Email verification failed',
            'message': 'An unexpected error occurred',
            'code': 'VERIFICATION_ERROR'
        }), 500


@auth_bp.route('/resend-verification', methods=['POST'])
@limiter.limit("3 per hour")
@jwt_required()
def resend_verification():
    """
    Resend email verification
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        if user.email_verified:
            return jsonify({
                'message': 'Email is already verified'
            }), 200
        
        # Generate new verification token if needed
        if not user.email_verification_token:
            user.email_verification_token = secrets.token_urlsafe(32)
            db.session.commit()
        
        # Send verification email
        try:
            send_verification_email(user)
            current_app.logger.info(f"Verification email resent to: {user.email}")
            
            return jsonify({
                'message': 'Verification email sent'
            }), 200
            
        except Exception as e:
            current_app.logger.error(f"Failed to resend verification email: {str(e)}")
            return jsonify({
                'error': 'Failed to send verification email',
                'code': 'EMAIL_SEND_ERROR'
            }), 500
        
    except Exception as e:
        current_app.logger.error(f"Resend verification error: {str(e)}")
        return jsonify({
            'error': 'Failed to resend verification',
            'message': 'An unexpected error occurred',
            'code': 'RESEND_ERROR'
        }), 500


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    Get current user information
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        return jsonify({
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Get current user error: {str(e)}")
        return jsonify({
            'error': 'Failed to get user information',
            'message': 'An unexpected error occurred',
            'code': 'USER_INFO_ERROR'
        }), 500


def send_verification_email(user: User) -> None:
    """Send email verification email"""
    verification_url = f"{current_app.config.get('FRONTEND_URL', 'http://localhost:3000')}/verify-email?token={user.email_verification_token}"
    
    subject = "Verify your email address"
    html_body = f"""
    <html>
    <body>
        <h2>Welcome to Facebook SaaS Platform!</h2>
        <p>Hello {user.first_name},</p>
        <p>Thank you for registering with us. Please click the link below to verify your email address:</p>
        <p><a href="{verification_url}" style="background-color: #4CAF50; color: white; padding: 14px 20px; text-decoration: none; border-radius: 4px;">Verify Email</a></p>
        <p>If the button doesn't work, copy and paste this link into your browser:</p>
        <p>{verification_url}</p>
        <p>This link will expire in 24 hours.</p>
        <p>If you didn't create an account with us, please ignore this email.</p>
        <br>
        <p>Best regards,<br>Facebook SaaS Platform Team</p>
    </body>
    </html>
    """
    
    send_email(
        to=user.email,
        subject=subject,
        html_body=html_body
    )


def send_password_reset_email(user: User, reset_token: str) -> None:
    """Send password reset email"""
    reset_url = f"{current_app.config.get('FRONTEND_URL', 'http://localhost:3000')}/reset-password?token={reset_token}"
    
    subject = "Reset your password"
    html_body = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>Hello {user.first_name},</p>
        <p>We received a request to reset your password. Click the link below to create a new password:</p>
        <p><a href="{reset_url}" style="background-color: #2196F3; color: white; padding: 14px 20px; text-decoration: none; border-radius: 4px;">Reset Password</a></p>
        <p>If the button doesn't work, copy and paste this link into your browser:</p>
        <p>{reset_url}</p>
        <p>This link will expire in 1 hour.</p>
        <p>If you didn't request a password reset, please ignore this email.</p>
        <br>
        <p>Best regards,<br>Facebook SaaS Platform Team</p>
    </body>
    </html>
    """
    
    send_email(
        to=user.email,
        subject=subject,
        html_body=html_body
    ) 