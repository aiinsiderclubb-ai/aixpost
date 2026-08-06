"""
Helper utilities for Facebook SaaS Platform
Common utility functions used across the application
"""

import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from flask import current_app
from flask_mail import Message
from werkzeug.utils import secure_filename

from app import mail


def send_email(to: str, subject: str, html_body: str, text_body: str = None) -> bool:
    """
    Send email using Flask-Mail
    
    Args:
        to: Recipient email address
        subject: Email subject
        html_body: HTML email body
        text_body: Plain text email body (optional)
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        msg = Message(
            subject=subject,
            recipients=[to],
            html=html_body,
            body=text_body,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        
        mail.send(msg)
        current_app.logger.info(f"Email sent successfully to {to}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"Failed to send email to {to}: {str(e)}")
        return False


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token
    
    Args:
        length: Token length
        
    Returns:
        str: Secure random token
    """
    return secrets.token_urlsafe(length)


def generate_hash(data: str, salt: str = None) -> str:
    """
    Generate SHA-256 hash of data with optional salt
    
    Args:
        data: Data to hash
        salt: Optional salt for hashing
        
    Returns:
        str: Hexadecimal hash string
    """
    if salt:
        data = data + salt
    
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def allowed_file(filename: str, allowed_extensions: set = None) -> bool:
    """
    Check if uploaded file has allowed extension
    
    Args:
        filename: Name of uploaded file
        allowed_extensions: Set of allowed extensions
        
    Returns:
        bool: True if file extension is allowed
    """
    if allowed_extensions is None:
        allowed_extensions = {'txt', 'csv', 'json', 'xlsx'}
    
    return ('.' in filename and 
            filename.rsplit('.', 1)[1].lower() in allowed_extensions)


def secure_upload_path(filename: str, upload_folder: str = None) -> str:
    """
    Generate secure path for uploaded file
    
    Args:
        filename: Original filename
        upload_folder: Upload directory
        
    Returns:
        str: Secure file path
    """
    if upload_folder is None:
        upload_folder = current_app.config['UPLOAD_FOLDER']
    
    # Secure the filename
    secure_name = secure_filename(filename)
    
    # Add timestamp and UUID to prevent conflicts
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    
    name, ext = os.path.splitext(secure_name)
    final_name = f"{name}_{timestamp}_{unique_id}{ext}"
    
    return os.path.join(upload_folder, final_name)


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format
    
    Args:
        size_bytes: File size in bytes
        
    Returns:
        str: Formatted file size (e.g., "1.5 MB")
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


def format_duration(seconds: int) -> str:
    """
    Format duration in human readable format
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        str: Formatted duration (e.g., "2h 30m")
    """
    if seconds < 60:
        return f"{seconds}s"
    
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if hours < 24:
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"
    
    days = hours // 24
    remaining_hours = hours % 24
    
    if remaining_hours > 0:
        return f"{days}d {remaining_hours}h"
    return f"{days}d"


def extract_facebook_group_id(url: str) -> Optional[str]:
    """
    Extract Facebook group ID from URL
    
    Args:
        url: Facebook group URL
        
    Returns:
        Optional[str]: Group ID if found, None otherwise
    """
    try:
        # Handle different Facebook URL formats
        if '/groups/' in url:
            # Extract ID from path
            parts = url.split('/groups/')
            if len(parts) > 1:
                group_id = parts[1].split('/')[0].split('?')[0]
                return group_id if group_id else None
    except Exception:
        pass
    
    return None


def clean_facebook_url(url: str) -> str:
    """
    Clean and normalize Facebook group URL
    
    Args:
        url: Raw Facebook URL
        
    Returns:
        str: Cleaned URL
    """
    if not url:
        return ""
    
    # Remove whitespace
    url = url.strip()
    
    # Ensure URL has protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Normalize domain
    url = url.replace('m.facebook.com', 'www.facebook.com')
    url = url.replace('facebook.com', 'www.facebook.com')
    
    # Remove unnecessary parameters
    if '?' in url:
        base_url = url.split('?')[0]
        # Keep only essential parameters
        return base_url
    
    return url


def paginate_results(query, page: int, per_page: int = 20):
    """
    Helper for SQLAlchemy pagination
    
    Args:
        query: SQLAlchemy query object
        page: Page number (1-indexed)
        per_page: Number of items per page
        
    Returns:
        tuple: (items, pagination_info)
    """
    paginated = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    pagination_info = {
        'page': page,
        'per_page': per_page,
        'total': paginated.total,
        'pages': paginated.pages,
        'has_prev': paginated.has_prev,
        'has_next': paginated.has_next,
        'prev_num': paginated.prev_num,
        'next_num': paginated.next_num
    }
    
    return paginated.items, pagination_info


def mask_sensitive_data(data: str, mask_char: str = '*', visible_chars: int = 4) -> str:
    """
    Mask sensitive data for logging/display
    
    Args:
        data: Sensitive data to mask
        mask_char: Character to use for masking
        visible_chars: Number of characters to leave visible
        
    Returns:
        str: Masked data
    """
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else ""
    
    if len(data) <= visible_chars * 2:
        # Show first few characters only
        return data[:visible_chars] + mask_char * (len(data) - visible_chars)
    
    # Show first and last few characters
    return (data[:visible_chars] + 
            mask_char * (len(data) - visible_chars * 2) + 
            data[-visible_chars:])


def calculate_success_rate(successful: int, total: int) -> float:
    """
    Calculate success rate percentage
    
    Args:
        successful: Number of successful operations
        total: Total number of operations
        
    Returns:
        float: Success rate as percentage (0.0 to 100.0)
    """
    if total == 0:
        return 0.0
    
    return round((successful / total) * 100, 2)


def estimate_completion_time(completed: int, total: int, start_time: datetime) -> Optional[datetime]:
    """
    Estimate completion time based on current progress
    
    Args:
        completed: Number of completed items
        total: Total number of items
        start_time: When the operation started
        
    Returns:
        Optional[datetime]: Estimated completion time
    """
    if completed == 0 or total == 0:
        return None
    
    elapsed = datetime.utcnow() - start_time
    rate = completed / elapsed.total_seconds()  # items per second
    
    remaining = total - completed
    remaining_seconds = remaining / rate
    
    return datetime.utcnow() + timedelta(seconds=remaining_seconds)


def validate_json_structure(data: Dict[str, Any], required_fields: List[str]) -> List[str]:
    """
    Validate JSON data structure
    
    Args:
        data: JSON data to validate
        required_fields: List of required field names
        
    Returns:
        List[str]: List of validation errors
    """
    errors = []
    
    if not isinstance(data, dict):
        errors.append("Data must be a JSON object")
        return errors
    
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")
        elif data[field] is None:
            errors.append(f"Field '{field}' cannot be null")
    
    return errors


def rate_limit_key(user_id: str, endpoint: str) -> str:
    """
    Generate rate limiting key for Redis
    
    Args:
        user_id: User identifier
        endpoint: API endpoint name
        
    Returns:
        str: Rate limiting key
    """
    return f"rate_limit:{user_id}:{endpoint}"


def cache_key(prefix: str, *args) -> str:
    """
    Generate cache key for Redis
    
    Args:
        prefix: Cache key prefix
        *args: Additional arguments to include in key
        
    Returns:
        str: Cache key
    """
    key_parts = [prefix] + [str(arg) for arg in args]
    return ":".join(key_parts)


def parse_user_agent(user_agent: str) -> Dict[str, str]:
    """
    Parse user agent string to extract browser and OS info
    
    Args:
        user_agent: User agent string
        
    Returns:
        Dict[str, str]: Parsed user agent info
    """
    # Simplified user agent parsing
    info = {
        'browser': 'Unknown',
        'os': 'Unknown',
        'device': 'Desktop'
    }
    
    if not user_agent:
        return info
    
    user_agent = user_agent.lower()
    
    # Browser detection
    if 'chrome' in user_agent:
        info['browser'] = 'Chrome'
    elif 'firefox' in user_agent:
        info['browser'] = 'Firefox'
    elif 'safari' in user_agent:
        info['browser'] = 'Safari'
    elif 'edge' in user_agent:
        info['browser'] = 'Edge'
    
    # OS detection
    if 'windows' in user_agent:
        info['os'] = 'Windows'
    elif 'mac' in user_agent:
        info['os'] = 'macOS'
    elif 'linux' in user_agent:
        info['os'] = 'Linux'
    elif 'android' in user_agent:
        info['os'] = 'Android'
        info['device'] = 'Mobile'
    elif 'ios' in user_agent:
        info['os'] = 'iOS'
        info['device'] = 'Mobile'
    
    return info


def get_client_ip(request) -> str:
    """
    Get client IP address from request
    
    Args:
        request: Flask request object
        
    Returns:
        str: Client IP address
    """
    # Check for forwarded headers (behind proxy/load balancer)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    
    return request.remote_addr or '127.0.0.1' 