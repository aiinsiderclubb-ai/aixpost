"""
Validation utilities for Facebook SaaS Platform
Input validation and data sanitization functions
"""

import re
from typing import List, Optional
from urllib.parse import urlparse


def validate_email(email: str) -> bool:
    """
    Validate email address format
    
    Args:
        email: Email address to validate
        
    Returns:
        bool: True if email is valid, False otherwise
    """
    if not email or len(email) > 254:
        return False
    
    # RFC 5322 compliant regex (simplified)
    email_pattern = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    return bool(email_pattern.match(email))


def validate_password(password: str) -> List[str]:
    """
    Validate password strength
    
    Args:
        password: Password to validate
        
    Returns:
        List[str]: List of validation errors (empty if valid)
    """
    errors = []
    
    if not password:
        errors.append("Password is required")
        return errors
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    
    if len(password) > 128:
        errors.append("Password must be less than 128 characters long")
    
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number")
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character")
    
    # Check for common weak patterns
    common_patterns = [
        r'123456',
        r'password',
        r'qwerty',
        r'abc123',
        r'admin'
    ]
    
    password_lower = password.lower()
    for pattern in common_patterns:
        if pattern in password_lower:
            errors.append("Password contains common weak patterns")
            break
    
    return errors


def validate_facebook_url(url: str) -> bool:
    """
    Validate Facebook group URL format
    
    Args:
        url: Facebook URL to validate
        
    Returns:
        bool: True if URL is valid Facebook group URL
    """
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        
        # Check if it's a Facebook URL
        if parsed.netloc.lower() not in ['facebook.com', 'www.facebook.com', 'm.facebook.com']:
            return False
        
        # Check if it's a groups URL
        path = parsed.path.lower()
        if not path.startswith('/groups/'):
            return False
        
        # Extract group ID
        group_id = path.replace('/groups/', '').split('/')[0].split('?')[0]
        
        # Group ID should be non-empty and contain only valid characters
        if not group_id or not re.match(r'^[a-zA-Z0-9._-]+$', group_id):
            return False
        
        return True
        
    except Exception:
        return False


def validate_message_content(content: str, max_length: int = 5000) -> List[str]:
    """
    Validate message content for posting
    
    Args:
        content: Message content to validate
        max_length: Maximum allowed length
        
    Returns:
        List[str]: List of validation errors (empty if valid)
    """
    errors = []
    
    if not content or not content.strip():
        errors.append("Message content cannot be empty")
        return errors
    
    content = content.strip()
    
    if len(content) > max_length:
        errors.append(f"Message content must be less than {max_length} characters")
    
    # Check for suspicious patterns that might indicate spam
    spam_patterns = [
        r'(click here now|act now|limited time|urgent|guaranteed)',
        r'(\$\$\$|\bmoney\b.*\bfast\b|\bget rich\b)',
        r'(viagra|cialis|pharmacy|pills)',
        r'(lottery|winner|congratulations.*won)',
    ]
    
    content_lower = content.lower()
    for pattern in spam_patterns:
        if re.search(pattern, content_lower):
            errors.append("Message content may contain spam-like patterns")
            break
    
    # Check for excessive capitalization
    if len(content) > 20:  # Only check for longer messages
        caps_ratio = sum(1 for c in content if c.isupper()) / len(content)
        if caps_ratio > 0.5:
            errors.append("Message contains excessive capitalization")
    
    # Check for excessive special characters
    special_char_count = len(re.findall(r'[!@#$%^&*()_+=\-\[\]{};:"|<>,.?/~`]', content))
    if special_char_count > len(content) * 0.3:
        errors.append("Message contains excessive special characters")
    
    return errors


def validate_campaign_name(name: str) -> List[str]:
    """
    Validate campaign name
    
    Args:
        name: Campaign name to validate
        
    Returns:
        List[str]: List of validation errors (empty if valid)
    """
    errors = []
    
    if not name or not name.strip():
        errors.append("Campaign name cannot be empty")
        return errors
    
    name = name.strip()
    
    if len(name) < 3:
        errors.append("Campaign name must be at least 3 characters long")
    
    if len(name) > 100:
        errors.append("Campaign name must be less than 100 characters long")
    
    # Check for valid characters (letters, numbers, spaces, hyphens, underscores)
    if not re.match(r'^[a-zA-Z0-9\s\-_]+$', name):
        errors.append("Campaign name can only contain letters, numbers, spaces, hyphens, and underscores")
    
    return errors


def validate_phone_number(phone: str) -> bool:
    """
    Validate international phone number format
    
    Args:
        phone: Phone number to validate
        
    Returns:
        bool: True if phone number is valid
    """
    if not phone:
        return False
    
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Check if it starts with + and has 7-15 digits
    phone_pattern = re.compile(r'^\+\d{7,15}$')
    
    return bool(phone_pattern.match(cleaned))


def sanitize_input(text: str, max_length: Optional[int] = None) -> str:
    """
    Sanitize user input by removing potentially harmful content
    
    Args:
        text: Text to sanitize
        max_length: Maximum allowed length
        
    Returns:
        str: Sanitized text
    """
    if not text:
        return ""
    
    # Remove leading/trailing whitespace
    sanitized = text.strip()
    
    # Remove null bytes and other control characters
    sanitized = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', sanitized)
    
    # Normalize whitespace
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Truncate if max_length is specified
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized


def validate_template_variables(template: str) -> List[str]:
    """
    Validate template variable syntax
    
    Args:
        template: Template string to validate
        
    Returns:
        List[str]: List of validation errors (empty if valid)
    """
    errors = []
    
    if not template:
        return errors
    
    # Find all variable placeholders
    variables = re.findall(r'\{\{([^}]+)\}\}', template)
    
    for var in variables:
        var = var.strip()
        
        # Variable name validation
        if not var:
            errors.append("Empty variable name found")
            continue
        
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', var):
            errors.append(f"Invalid variable name: {var}. Variables must start with a letter or underscore and contain only letters, numbers, and underscores")
    
    # Check for unmatched braces
    open_braces = template.count('{{')
    close_braces = template.count('}}')
    
    if open_braces != close_braces:
        errors.append("Unmatched template variable braces")
    
    return errors


def validate_delay_settings(min_delay: int, max_delay: int) -> List[str]:
    """
    Validate delay settings for posting campaigns
    
    Args:
        min_delay: Minimum delay in seconds
        max_delay: Maximum delay in seconds
        
    Returns:
        List[str]: List of validation errors (empty if valid)
    """
    errors = []
    
    if min_delay < 5:
        errors.append("Minimum delay must be at least 5 seconds")
    
    if min_delay > 3600:  # 1 hour
        errors.append("Minimum delay cannot exceed 1 hour")
    
    if max_delay < 5:
        errors.append("Maximum delay must be at least 5 seconds")
    
    if max_delay > 3600:  # 1 hour
        errors.append("Maximum delay cannot exceed 1 hour")
    
    if min_delay >= max_delay:
        errors.append("Minimum delay must be less than maximum delay")
    
    return errors


def validate_batch_size(batch_size: int, max_groups: int) -> List[str]:
    """
    Validate batch size for notifications
    
    Args:
        batch_size: Number of groups per batch
        max_groups: Maximum number of groups
        
    Returns:
        List[str]: List of validation errors (empty if valid)
    """
    errors = []
    
    if batch_size < 1:
        errors.append("Batch size must be at least 1")
    
    if batch_size > 100:
        errors.append("Batch size cannot exceed 100")
    
    if batch_size > max_groups:
        errors.append("Batch size cannot exceed maximum number of groups")
    
    return errors 