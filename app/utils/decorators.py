"""
Custom decorators for Facebook SaaS Platform
Includes admin authorization, rate limiting, and security decorators
"""

from functools import wraps
from flask import jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required
from typing import Callable, Any
from datetime import datetime, timedelta
import redis
import hashlib

from app.models.user import User
from app import db

def admin_required(f: Callable) -> Callable:
    """
    Decorator to require admin role for accessing endpoint
    Must be used after @jwt_required()
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Get current user ID from JWT
            user_id = get_jwt_identity()
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401
            
            # Get user from database
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            # Check if user is admin
            if not user.is_admin():
                current_app.logger.warning(f"Non-admin user {user.email} attempted to access admin endpoint")
                return jsonify({'error': 'Admin access required'}), 403
            
            # Check if user is active
            if not user.is_active:
                return jsonify({'error': 'Account is disabled'}), 403
            
            return f(*args, **kwargs)
            
        except Exception as e:
            current_app.logger.error(f"Admin authorization error: {str(e)}")
            return jsonify({'error': 'Authorization failed'}), 500
    
    return decorated_function

def plan_required(required_plan: str):
    """
    Decorator to require minimum plan level
    Usage: @plan_required('PLUS')
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                user_id = get_jwt_identity()
                if not user_id:
                    return jsonify({'error': 'Authentication required'}), 401
                
                user = User.query.get(user_id)
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                
                # Plan hierarchy: FREE < PLUS < PREMIUM
                plan_hierarchy = {'FREE': 0, 'PLUS': 1, 'PREMIUM': 2}
                
                user_plan_level = plan_hierarchy.get(user.current_plan, 0)
                required_plan_level = plan_hierarchy.get(required_plan, 0)
                
                if user_plan_level < required_plan_level:
                    return jsonify({
                        'error': f'{required_plan} plan required',
                        'current_plan': user.current_plan,
                        'required_plan': required_plan,
                        'upgrade_url': '/plans'
                    }), 402  # Payment Required
                
                return f(*args, **kwargs)
                
            except Exception as e:
                current_app.logger.error(f"Plan authorization error: {str(e)}")
                return jsonify({'error': 'Authorization failed'}), 500
        
        return decorated_function
    return decorator

def usage_limit_check(resource_type: str, count: int = 1):
    """
    Decorator to check usage limits before executing endpoint
    Usage: @usage_limit_check('messages', 1)
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                user_id = get_jwt_identity()
                if not user_id:
                    return jsonify({'error': 'Authentication required'}), 401
                
                user = User.query.get(user_id)
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                
                # Check different resource types
                if resource_type == 'messages':
                    if not user.can_send_messages(count):
                        usage_stats = user.get_usage_stats()
                        return jsonify({
                            'error': 'Monthly message limit exceeded',
                            'usage_stats': usage_stats,
                            'upgrade_url': '/plans'
                        }), 429  # Too Many Requests
                
                elif resource_type == 'groups':
                    limits = user.get_plan_limits()
                    # Would need to implement group counting logic
                    pass
                
                return f(*args, **kwargs)
                
            except Exception as e:
                current_app.logger.error(f"Usage limit check error: {str(e)}")
                return jsonify({'error': 'Usage validation failed'}), 500
        
        return decorated_function
    return decorator

def validate_json_request(required_fields: list = None):
    """
    Decorator to validate JSON request body
    Usage: @validate_json_request(['email', 'password'])
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Check if request contains JSON
                if not request.is_json:
                    return jsonify({'error': 'Content-Type must be application/json'}), 400
                
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'JSON body is required'}), 400
                
                # Check required fields
                if required_fields:
                    missing_fields = []
                    for field in required_fields:
                        if field not in data or not data[field]:
                            missing_fields.append(field)
                    
                    if missing_fields:
                        return jsonify({
                            'error': 'Missing required fields',
                            'missing_fields': missing_fields
                        }), 400
                
                return f(*args, **kwargs)
                
            except Exception as e:
                current_app.logger.error(f"JSON validation error: {str(e)}")
                return jsonify({'error': 'Request validation failed'}), 400
        
        return decorated_function
    return decorator

def track_api_usage(endpoint_name: str = None):
    """
    Decorator to track API endpoint usage
    Usage: @track_api_usage('user_login')
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Get tracking info
                user_id = get_jwt_identity() if hasattr(request, 'headers') else None
                ip_address = request.remote_addr
                user_agent = request.headers.get('User-Agent', '')
                endpoint = endpoint_name or f.__name__
                
                # Execute the function
                result = f(*args, **kwargs)
                
                # Log usage (in production, this could go to a separate analytics service)
                current_app.logger.info(f"API Usage: {endpoint} - User: {user_id} - IP: {ip_address}")
                
                return result
                
            except Exception as e:
                current_app.logger.error(f"API usage tracking error: {str(e)}")
                # Don't fail the request if tracking fails
                return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def require_verified_email(f: Callable) -> Callable:
    """
    Decorator to require verified email address
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            user_id = get_jwt_identity()
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401
            
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            if not user.email_verified:
                return jsonify({
                    'error': 'Email verification required',
                    'message': 'Please verify your email address to access this feature',
                    'verification_url': '/api/auth/resend-verification'
                }), 403
            
            return f(*args, **kwargs)
            
        except Exception as e:
            current_app.logger.error(f"Email verification check error: {str(e)}")
            return jsonify({'error': 'Verification check failed'}), 500
    
    return decorated_function

def csrf_protection(f: Callable) -> Callable:
    """
    Custom CSRF protection decorator
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Only check for state-changing operations
            if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
                csrf_token = request.headers.get('X-CSRF-Token')
                if not csrf_token:
                    return jsonify({'error': 'CSRF token required'}), 400
                
                # In production, implement proper CSRF token validation
                # For now, just check that it exists
                if len(csrf_token) < 10:
                    return jsonify({'error': 'Invalid CSRF token'}), 400
            
            return f(*args, **kwargs)
            
        except Exception as e:
            current_app.logger.error(f"CSRF protection error: {str(e)}")
            return jsonify({'error': 'CSRF validation failed'}), 500
    
    return decorated_function

def ip_whitelist(allowed_ips: list):
    """
    Decorator to restrict access to specific IP addresses
    Usage: @ip_whitelist(['192.168.1.100', '10.0.0.1'])
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                client_ip = request.remote_addr
                
                # Check if IP is in allowed list
                if client_ip not in allowed_ips:
                    current_app.logger.warning(f"Unauthorized IP access attempt: {client_ip}")
                    return jsonify({'error': 'Access denied from this IP address'}), 403
                
                return f(*args, **kwargs)
                
            except Exception as e:
                current_app.logger.error(f"IP whitelist check error: {str(e)}")
                return jsonify({'error': 'IP validation failed'}), 500
        
        return decorated_function
    return decorator 