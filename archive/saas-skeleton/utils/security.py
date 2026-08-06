"""
Security utilities for Facebook SaaS Platform
Implements security headers, CSRF protection, input sanitization
"""

from flask import request, g, current_app
from functools import wraps
import re
import bleach
import secrets
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import hashlib
import hmac

class SecurityHeaders:
    """Security headers configuration"""
    
    @staticmethod
    def add_security_headers(response):
        """Add security headers to all responses"""
        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self' wss: ws:; "
            "frame-ancestors 'none';"
        )
        
        # Set security headers
        response.headers['Content-Security-Policy'] = csp
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'
        
        # HTTPS enforcement (in production)
        if not current_app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response

class CSRFProtection:
    """CSRF protection implementation"""
    
    @staticmethod
    def generate_csrf_token():
        """Generate CSRF token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def validate_csrf_token(token: str, session_token: str) -> bool:
        """Validate CSRF token"""
        if not token or not session_token:
            return False
        return hmac.compare_digest(token, session_token)

class InputSanitizer:
    """Input sanitization utilities"""
    
    # Allowed HTML tags for rich content
    ALLOWED_TAGS = [
        'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote'
    ]
    
    ALLOWED_ATTRIBUTES = {
        '*': ['class'],
        'a': ['href', 'title'],
        'abbr': ['title'],
        'acronym': ['title'],
    }
    
    @staticmethod
    def sanitize_html(text: str) -> str:
        """Sanitize HTML content"""
        if not text:
            return ""
        
        return bleach.clean(
            text,
            tags=InputSanitizer.ALLOWED_TAGS,
            attributes=InputSanitizer.ALLOWED_ATTRIBUTES,
            strip=True
        )
    
    @staticmethod
    def sanitize_string(text: str, max_length: int = 1000) -> str:
        """Sanitize plain text string"""
        if not text:
            return ""
        
        # Remove null bytes and control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # Limit length
        text = text[:max_length]
        
        # Strip whitespace
        return text.strip()
    
    @staticmethod
    def sanitize_email(email: str) -> str:
        """Sanitize email address"""
        if not email:
            return ""
        
        email = email.lower().strip()
        
        # Basic email pattern validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise ValueError("Invalid email format")
        
        return email
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe storage"""
        if not filename:
            return ""
        
        # Remove dangerous characters
        filename = re.sub(r'[^\w\-_\.]', '_', filename)
        
        # Limit length
        filename = filename[:255]
        
        # Ensure it doesn't start with a dot
        if filename.startswith('.'):
            filename = 'file_' + filename
        
        return filename

class RateLimiter:
    """Custom rate limiter for specific use cases"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
    
    def check_rate_limit(self, key: str, limit: int, window: int) -> Dict[str, Any]:
        """
        Check rate limit for a given key
        
        Args:
            key: Unique identifier for the rate limit
            limit: Number of requests allowed
            window: Time window in seconds
            
        Returns:
            Dict with rate limit info
        """
        if not self.redis_client:
            # Fallback to in-memory (not recommended for production)
            return {'allowed': True, 'remaining': limit, 'reset_time': None}
        
        try:
            pipe = self.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window)
            results = pipe.execute()
            
            current_requests = results[0]
            
            if current_requests > limit:
                return {
                    'allowed': False,
                    'remaining': 0,
                    'reset_time': datetime.utcnow() + timedelta(seconds=window),
                    'limit': limit,
                    'window': window
                }
            
            return {
                'allowed': True,
                'remaining': limit - current_requests,
                'reset_time': datetime.utcnow() + timedelta(seconds=window),
                'limit': limit,
                'window': window
            }
            
        except Exception as e:
            current_app.logger.error(f"Rate limiting error: {e}")
            # Allow request if rate limiting fails
            return {'allowed': True, 'remaining': limit, 'reset_time': None}

class SessionSecurity:
    """Session security utilities"""
    
    @staticmethod
    def generate_session_id():
        """Generate secure session ID"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple:
        """Hash password with salt"""
        if not salt:
            salt = secrets.token_hex(32)
        
        # Use PBKDF2 for password hashing
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # 100,000 iterations
        )
        
        return password_hash.hex(), salt
    
    @staticmethod
    def verify_password(password: str, password_hash: str, salt: str) -> bool:
        """Verify password against hash"""
        try:
            computed_hash, _ = SessionSecurity.hash_password(password, salt)
            return hmac.compare_digest(computed_hash, password_hash)
        except Exception:
            return False

class ValidationUtils:
    """Input validation utilities"""
    
    @staticmethod
    def validate_password_strength(password: str) -> Dict[str, Any]:
        """Validate password strength"""
        errors = []
        score = 0
        
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long")
        else:
            score += 1
        
        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        else:
            score += 1
        
        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        else:
            score += 1
        
        if not re.search(r'\d', password):
            errors.append("Password must contain at least one number")
        else:
            score += 1
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")
        else:
            score += 1
        
        # Additional checks for common patterns
        if password.lower() in ['password', '123456', 'qwerty', 'admin']:
            errors.append("Password is too common")
            score = 0
        
        strength_levels = ['Very Weak', 'Weak', 'Fair', 'Good', 'Strong']
        strength = strength_levels[min(score, 4)]
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'strength': strength,
            'score': score
        }
    
    @staticmethod
    def validate_file_upload(file, allowed_extensions: set, max_size: int = 16 * 1024 * 1024):
        """Validate file upload"""
        if not file or not file.filename:
            return False, "No file selected"
        
        # Check file extension
        if '.' not in file.filename:
            return False, "File must have an extension"
        
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_extensions:
            return False, f"File type .{ext} not allowed"
        
        # Check file size (read first to get size)
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if size > max_size:
            return False, f"File too large. Maximum size: {max_size // (1024*1024)}MB"
        
        return True, "File is valid"

class SecurityAudit:
    """Security audit utilities"""
    
    @staticmethod
    def log_security_event(event_type: str, user_id: str = None, ip_address: str = None, 
                          details: Dict[str, Any] = None):
        """Log security-related events"""
        event_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'user_id': user_id,
            'ip_address': ip_address,
            'user_agent': request.headers.get('User-Agent', ''),
            'details': details or {}
        }
        
        # Log to application logger with security tag
        current_app.logger.warning(f"SECURITY_EVENT: {event_type}", extra=event_data)
    
    @staticmethod
    def detect_suspicious_activity(user_id: str, activity_type: str) -> bool:
        """Detect suspicious user activity patterns"""
        # This would typically use Redis or database to track patterns
        # For now, return False (no suspicious activity detected)
        return False

# Initialize security utilities
def init_security(app):
    """Initialize security for Flask app"""
    
    @app.after_request
    def add_security_headers(response):
        return SecurityHeaders.add_security_headers(response)
    
    @app.before_request
    def security_before_request():
        """Security checks before each request"""
        # Add CSRF token to g object for templates
        g.csrf_token = CSRFProtection.generate_csrf_token()
        
        # Log suspicious patterns
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            user_agent = request.headers.get('User-Agent', '')
            if not user_agent or len(user_agent) < 10:
                SecurityAudit.log_security_event(
                    'suspicious_user_agent',
                    ip_address=request.remote_addr,
                    details={'user_agent': user_agent}
                )

# Export utility functions for easy import
def sanitize_input(text: str, html: bool = False) -> str:
    """Convenience function for input sanitization"""
    if html:
        return InputSanitizer.sanitize_html(text)
    return InputSanitizer.sanitize_string(text)

def validate_email(email: str) -> bool:
    """Convenience function for email validation"""
    try:
        InputSanitizer.sanitize_email(email)
        return True
    except ValueError:
        return False 