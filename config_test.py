"""
Test Configuration for Facebook SaaS Platform
Simple configuration with SQLite for quick testing
"""

import os
from datetime import timedelta


class TestConfig:
    """Test configuration with SQLite"""
    
    # Basic Flask configuration
    SECRET_KEY = 'test-secret-key-for-development'
    DEBUG = True
    
    # Database configuration (SQLite)
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'test_app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT configuration
    JWT_SECRET_KEY = 'test-jwt-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # Email configuration (mock)
    MAIL_SERVER = 'localhost'
    MAIL_PORT = 1025
    MAIL_USE_TLS = False
    MAIL_USERNAME = ''
    MAIL_PASSWORD = ''
    MAIL_DEFAULT_SENDER = 'test@facebook-saas.com'
    
    # Rate limiting (disabled for testing)
    RATELIMIT_ENABLED = False
    
    # File storage
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Facebook bot configuration
    FACEBOOK_SESSIONS_DIR = 'facebook_sessions'
    FACEBOOK_SCREENSHOTS_DIR = 'screenshots'
    
    # Subscription plans
    SUBSCRIPTION_PLANS = {
        'FREE': {
            'name': 'Free',
            'price': 0,
            'max_messages': 50,
            'max_groups': 10,
            'features': ['Basic posting', 'Email support']
        },
        'PLUS': {
            'name': 'Plus',
            'price': 49,
            'max_messages': 500,
            'max_groups': 100,
            'features': ['Advanced posting', 'Templates', 'Analytics', 'Priority support']
        },
        'PREMIUM': {
            'name': 'Premium',
            'price': 99,
            'max_messages': 2000,
            'max_groups': 500,
            'features': ['Unlimited posting', 'Advanced templates', 'Full analytics', 'API access', 'VIP support']
        }
    }
    
    # Admin users
    ADMIN_EMAILS = ['admin@test.com']
    
    # Security settings
    BCRYPT_LOG_ROUNDS = 4  # Fast for testing
    PASSWORD_MIN_LENGTH = 8
    
    @staticmethod
    def init_app(app):
        """Initialize application with configuration"""
        pass 