"""
Configuration for Facebook SaaS Platform
Production-ready configuration with environment variables
"""

import os
from datetime import timedelta
from typing import Dict, Any


class Config:
    """Base configuration class"""
    
    # Basic Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    # Encryption key is mandatory for any runtime
    FERNET_KEY = os.environ.get('FERNET_KEY')
    if not FERNET_KEY:
        raise RuntimeError("FERNET_KEY environment variable is required for startup")
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://user:password@localhost/facebook_saas'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 20,
        'max_overflow': 30
    }
    
    # Redis configuration
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    REDIS_SESSION_DB = 1
    REDIS_CACHE_DB = 2
    
    # JWT configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # Email configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.sendgrid.net'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@facebook-saas.com'
    
    # Stripe configuration
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # Celery configuration
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or REDIS_URL
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or REDIS_URL
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = 'UTC'
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = REDIS_URL
    RATELIMIT_DEFAULT = "1000 per hour"
    
    # File storage
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Facebook bot configuration
    FACEBOOK_SESSIONS_DIR = os.environ.get('FACEBOOK_SESSIONS_DIR') or 'facebook_sessions'
    FACEBOOK_SCREENSHOTS_DIR = os.environ.get('FACEBOOK_SCREENSHOTS_DIR') or 'screenshots'
    
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
            'features': ['Advanced posting', 'Templates', 'Analytics', 'Priority support'],
            'stripe_price_id': os.environ.get('STRIPE_PLUS_PRICE_ID')
        },
        'PREMIUM': {
            'name': 'Premium',
            'price': 99,
            'max_messages': 2000,
            'max_groups': 500,
            'features': ['Unlimited posting', 'Advanced templates', 'Full analytics', 'API access', 'VIP support'],
            'stripe_price_id': os.environ.get('STRIPE_PREMIUM_PRICE_ID')
        }
    }
    
    # Admin users (by email)
    ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', '').split(',')
    
    # Security settings
    BCRYPT_LOG_ROUNDS = 12
    PASSWORD_MIN_LENGTH = 8
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE')
    
    # External services
    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    
    @staticmethod
    def init_app(app):
        """Initialize application with configuration"""
        pass


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'postgresql://dev_user:dev_password@localhost/facebook_saas_dev'
    
    # Relaxed rate limiting for development
    RATELIMIT_DEFAULT = "10000 per hour"
    
    # Email debugging
    MAIL_DEBUG = True
    MAIL_SUPPRESS_SEND = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    REDIS_URL = 'redis://localhost:6379/15'  # Use different DB for tests
    WTF_CSRF_ENABLED = False
    
    # Disable rate limiting for tests
    RATELIMIT_ENABLED = False
    
    # Fast password hashing for tests
    BCRYPT_LOG_ROUNDS = 4


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    
    # Enhanced security for production
    BCRYPT_LOG_ROUNDS = 15
    
    # Strict rate limiting
    RATELIMIT_DEFAULT = "500 per hour"
    
    # SSL settings
    PREFERRED_URL_SCHEME = 'https'
    
    @classmethod
    def init_app(cls, app):
        """Initialize production app"""
        Config.init_app(app)
        
        # Log to syslog in production
        import logging
        from logging.handlers import SysLogHandler
        syslog_handler = SysLogHandler()
        syslog_handler.setLevel(logging.INFO)
        app.logger.addHandler(syslog_handler)


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 