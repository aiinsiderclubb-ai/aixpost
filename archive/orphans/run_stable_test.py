#!/usr/bin/env python3
"""
Facebook SaaS Platform - Stable Test Version
Without SocketIO for stable testing
"""

import os
import sys
import logging
import json
import time
import threading
import random
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from functools import wraps
from flask import Flask, request, render_template, render_template_string, jsonify, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from cryptography.fernet import Fernet
import secrets
import requests
from urllib.parse import unquote
from flask_login import UserMixin

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
class StableTestConfig:
    DEBUG = True
    SECRET_KEY = 'test-secret-key-for-development'
    JWT_SECRET_KEY = 'test-jwt-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ['headers', 'cookies', 'query_string']
    JWT_QUERY_STRING_NAME = 'token'
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_COOKIE_NAME = 'access_token'
    JWT_REFRESH_COOKIE_NAME = 'refresh_token'
    
    # Database configuration (SQLite)
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'stable_test.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(StableTestConfig)

# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)
bcrypt = Bcrypt(app)
cors = CORS(app, origins=["http://localhost:3000", "http://localhost:8080"])

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["100 per minute"],
    storage_uri="memory://"
)

# Initialize encryption
FERNET_KEY = Fernet.generate_key()
cipher = Fernet(FERNET_KEY)

def encrypt_password(password: str) -> str:
    """Encrypt a password for secure storage"""
    if not password:
        return ""
    return cipher.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    """Decrypt a password for use"""
    if not encrypted_password:
        return ""
    try:
        return cipher.decrypt(encrypted_password.encode()).decode()
    except Exception:
        return ""

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = 'test_token_for_development'

def send_telegram_message(chat_id: str, message: str) -> bool:
    """Send message via Telegram Bot API"""
    logger.info(f"TEST MODE: Would send Telegram message to {chat_id}: {message}")
    return True

def validate_telegram_chat_id(chat_id: str) -> bool:
    """Validate Telegram chat ID format"""
    if not chat_id:
        return False
    
    if chat_id.startswith('@'):
        return len(chat_id) > 1 and chat_id[1:].replace('_', '').isalnum()
    else:
        try:
            int(chat_id)
            return True
        except ValueError:
            return False

# Admin required decorator
def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            user_id = get_jwt_identity()
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401
            
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            if not user.is_admin():
                logger.warning(f"Non-admin user {user.email} attempted to access admin endpoint")
                return jsonify({'error': 'Admin access required'}), 403
            
            if not user.is_active:
                return jsonify({'error': 'Account is disabled'}), 403
            
            return f(*args, **kwargs)
            
        except Exception as e:
            logger.error(f"Admin authorization error: {str(e)}")
            return jsonify({'error': 'Authorization failed'}), 500
    
    return decorated_function

# JWT error handlers
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        'error': 'Token has expired',
        'code': 'TOKEN_EXPIRED'
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        'error': 'Invalid token',
        'code': 'INVALID_TOKEN'
    }), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({
        'error': 'Authorization token is required',
        'code': 'MISSING_TOKEN'
    }), 401

# Database Models
class User(UserMixin, db.Model):
    """User model for testing"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='user')
    is_active = db.Column(db.Boolean, default=True)
    current_plan = db.Column(db.String(20), default='FREE')
    subscription_status = db.Column(db.String(20), default='active')
    messages_sent_this_month = db.Column(db.Integer, default=0)
    last_message_reset = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Facebook credentials
    facebook_username = db.Column(db.String(255))
    facebook_password = db.Column(db.String(255))
    use_headless = db.Column(db.Boolean, default=True)

    def set_password(self, password: str) -> None:
        """Set password hash"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Check password against hash"""
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_admin(self) -> bool:
        """Check if user is admin"""
        return self.role == 'admin'

    def get_plan_limits(self) -> Dict[str, Any]:
        """Get plan limits for user"""
        limits = {
            'FREE': {'groups_per_campaign': 5, 'campaigns_per_month': 3, 'posts_per_day': 5},
            'PLUS': {'groups_per_campaign': 50, 'campaigns_per_month': 25, 'posts_per_day': 100},
            'PREMIUM': {'groups_per_campaign': 999999, 'campaigns_per_month': 999999, 'posts_per_day': 999999}
        }
        return limits.get(self.current_plan, limits['FREE'])

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get user usage statistics"""
        return {
            'messages_sent_this_month': self.messages_sent_this_month,
            'campaigns_count': 0,  # Mock data
            'active_campaigns': 0   # Mock data
        }

    def get_usage_display(self) -> Dict[str, str]:
        """Get formatted usage display"""
        limits = self.get_plan_limits()
        stats = self.get_usage_stats()
        
        return {
            'messages': f"{stats['messages_sent_this_month']} / {limits['posts_per_day']}",
            'campaigns': f"{stats['campaigns_count']} / {limits['campaigns_per_month']}",
            'groups': f"0 / {limits['groups_per_campaign']}"
        }

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert user to dictionary"""
        data = {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'role': self.role,
            'is_active': self.is_active,
            'current_plan': self.current_plan,
            'subscription_status': self.subscription_status,
            'email_verified': self.email_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
        
        if include_sensitive:
            data.update({
                'facebook_username': self.facebook_username,
                'use_headless': self.use_headless
            })
        
        return data

    def update_last_login(self) -> None:
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()

    def __repr__(self) -> str:
        return f'<User {self.email}>'

class Campaign(db.Model):
    """Campaign model for testing"""
    __tablename__ = 'campaigns'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    target_groups = db.Column(db.Text)  # JSON string
    max_groups = db.Column(db.Integer, default=10)
    min_delay = db.Column(db.Integer, default=10)
    max_delay = db.Column(db.Integer, default=60)
    status = db.Column(db.String(20), default='draft')
    total_groups = db.Column(db.Integer, default=0)
    successful_posts = db.Column(db.Integer, default=0)
    failed_posts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        """Convert campaign to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'message': self.message,
            'target_groups': json.loads(self.target_groups) if self.target_groups else [],
            'max_groups': self.max_groups,
            'min_delay': self.min_delay,
            'max_delay': self.max_delay,
            'status': self.status,
            'total_groups': self.total_groups,
            'successful_posts': self.successful_posts,
            'failed_posts': self.failed_posts,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

class TelegramSettings(db.Model):
    """Model for Telegram bot settings"""
    __tablename__ = 'telegram_settings'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    chat_id = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_test_sent = db.Column(db.DateTime)
    test_successful = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Convert settings to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'is_active': self.is_active,
            'last_test_sent': self.last_test_sent.isoformat() if self.last_test_sent else None,
            'test_successful': self.test_successful,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# Validation functions
def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    return True, "Password is valid"

# Routes
@app.route('/')
def home():
    """Home page with login form"""
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Facebook SaaS Platform - Test Mode</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { text-align: center; margin-bottom: 30px; color: #333; }
        .status { padding: 15px; border-radius: 5px; margin: 10px 0; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .endpoint { background: #f8f9fa; padding: 10px; margin: 5px 0; border-left: 4px solid #007bff; }
        a { color: #007bff; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Facebook SaaS Platform</h1>
            <h2>Stable Test Version</h2>
        </div>
        
        <div class="status success">
            <strong>✅ Server Status:</strong> Running and Ready for Testing
        </div>
        
        <div class="status info">
            <strong>📋 Test Credentials:</strong><br>
            Admin: admin@test.com / Admin123!<br>
            Regular User: Register via API
        </div>
        
        <h3>🔧 Available Endpoints:</h3>
        
        <h4>Authentication:</h4>
        <div class="endpoint">POST /api/auth/register - User registration</div>
        <div class="endpoint">POST /api/auth/login - User login</div>
        <div class="endpoint">GET /api/auth/me - Get current user</div>
        <div class="endpoint">POST /api/auth/logout - User logout</div>
        
        <h4>Admin (Requires admin token):</h4>
        <div class="endpoint">GET /admin - Admin panel</div>
        <div class="endpoint">GET /api/v1/admin/users - List all users</div>
        <div class="endpoint">GET /api/v1/admin/analytics/overview - Platform analytics</div>
        
        <h4>User Pages (Requires JWT token):</h4>
        <div class="endpoint">GET /dashboard - User dashboard</div>
        <div class="endpoint">GET /groups - Groups management</div>
        <div class="endpoint">GET /poster - Facebook posting</div>
        <div class="endpoint">GET /plans - Subscription plans</div>
        <div class="endpoint">GET /telegram - Telegram bot settings</div>
        
        <h4>Telegram Bot API:</h4>
        <div class="endpoint">GET /api/telegram/settings - Get Telegram settings</div>
        <div class="endpoint">POST /api/telegram/settings - Save Telegram settings</div>
        <div class="endpoint">POST /api/telegram/test - Test Telegram connection</div>
        
        <h4>Campaign Management:</h4>
        <div class="endpoint">GET /api/campaigns - List campaigns</div>
        <div class="endpoint">POST /api/campaigns - Create campaign</div>
        <div class="endpoint">POST /api/campaigns/:id/start - Start campaign</div>
        <div class="endpoint">POST /api/campaigns/:id/stop - Stop campaign</div>
        
        <h4>Health & Testing:</h4>
        <div class="endpoint"><a href="/health">GET /health</a> - Health check</div>
        
        <h3>🧪 Testing:</h3>
        <p>Run comprehensive test suite:</p>
        <code>python comprehensive_test.py</code>
    </div>
</body>
</html>
    ''')

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Check database connection
        user_count = User.query.count()
        campaign_count = Campaign.query.count()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'database': 'connected',
            'stats': {
                'users': user_count,
                'campaigns': campaign_count
            },
            'version': '1.0.0-stable'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

# Authentication Routes
@app.route('/api/auth/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    """User registration"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'password', 'first_name', 'last_name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        email = data['email'].lower().strip()
        password = data['password']
        first_name = data['first_name'].strip()
        last_name = data['last_name'].strip()
        
        # Validate email
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Check if user exists
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 400
        
        # Validate password
        password_valid, password_message = validate_password(password)
        if not password_valid:
            return jsonify({'error': password_message}), 400
        
        # Create user
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            email_verified=True  # Auto-verify for testing
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        logger.info(f"New user registered: {email}")
        
        return jsonify({
            'message': 'User registered successfully',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500

@app.route('/api/auth/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    """User login"""
    try:
        data = request.get_json()
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Find user
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        if not user.is_active:
            return jsonify({'error': 'Account is disabled'}), 401
        
        # Update last login
        user.update_last_login()
        db.session.commit()
        
        # Create tokens
        access_token = create_access_token(identity=str(user.id))
        refresh_token = create_refresh_token(identity=str(user.id))
        
        response = make_response(jsonify({
            'message': 'Login successful',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict()
        }))
        
        # Set cookies
        response.set_cookie('access_token', access_token, httponly=True, secure=False)
        response.set_cookie('refresh_token', refresh_token, httponly=True, secure=False)
        
        logger.info(f"User logged in: {email}")
        
        return response, 200
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user info"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user': user.to_dict(include_sensitive=True),
            'usage': user.get_usage_display(),
            'limits': user.get_plan_limits()
        }), 200
        
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        return jsonify({'error': 'Failed to get user info'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """User logout"""
    response = make_response(jsonify({'message': 'Logged out successfully'}))
    response.set_cookie('access_token', '', expires=0)
    response.set_cookie('refresh_token', '', expires=0)
    return response, 200

# Page Routes
@app.route('/dashboard')
@jwt_required()
def dashboard():
    """Dashboard page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get dashboard data
        campaigns = Campaign.query.filter_by(user_id=user_id).all()
        total_campaigns = len(campaigns)
        active_campaigns = len([c for c in campaigns if c.status == 'running'])
        
        # Get Telegram status
        telegram_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        telegram_connected = telegram_settings and telegram_settings.is_active
        
        stats = {
            'total_campaigns': total_campaigns,
            'active_campaigns': active_campaigns,
            'total_groups': 0,
            'messages_sent': current_user.messages_sent_this_month,
            'success_rate': '95%',
            'telegram_connected': telegram_connected
        }
        
        return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard - Facebook SaaS</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-value { font-size: 2em; font-weight: bold; color: #007bff; }
        .stat-label { color: #666; margin-top: 5px; }
        .nav { margin-bottom: 20px; }
        .nav a { margin-right: 15px; padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
        .nav a:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Dashboard</h1>
            <p>Welcome, {{ current_user.first_name }} {{ current_user.last_name }}</p>
        </div>
        
        <div class="nav">
            <a href="/dashboard">Dashboard</a>
            <a href="/groups">Groups</a>
            <a href="/poster">Poster</a>
            <a href="/plans">Plans</a>
            <a href="/telegram">Telegram</a>
            <a href="/admin">Admin</a>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{{ stats.total_campaigns }}</div>
                <div class="stat-label">Total Campaigns</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.active_campaigns }}</div>
                <div class="stat-label">Active Campaigns</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.messages_sent }}</div>
                <div class="stat-label">Messages Sent</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ '✅' if stats.telegram_connected else '❌' }}</div>
                <div class="stat-label">Telegram Bot</div>
            </div>
        </div>
        
        <div style="background: white; padding: 20px; border-radius: 8px;">
            <h3>Recent Activity</h3>
            <p>No recent activity to show.</p>
        </div>
    </div>
</body>
</html>
        ''', current_user=current_user, stats=stats)
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({'error': f'Dashboard error: {str(e)}'}), 500

@app.route('/groups')
@jwt_required()
def groups_page():
    """Groups page"""
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    
    return render_template_string('''
<!DOCTYPE html>
<html>
<head><title>Groups - Facebook SaaS</title></head>
<body>
    <h1>Groups Management</h1>
    <p>Welcome, {{ current_user.first_name }}!</p>
    <p>Groups management functionality will be implemented here.</p>
    <a href="/dashboard">← Back to Dashboard</a>
</body>
</html>
    ''', current_user=current_user)

@app.route('/poster')
@jwt_required()
def poster_page():
    """Poster page"""
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    
    return render_template_string('''
<!DOCTYPE html>
<html>
<head><title>Poster - Facebook SaaS</title></head>
<body>
    <h1>Facebook Poster</h1>
    <p>Welcome, {{ current_user.first_name }}!</p>
    <p>Facebook posting functionality will be implemented here.</p>
    <a href="/dashboard">← Back to Dashboard</a>
</body>
</html>
    ''', current_user=current_user)

@app.route('/plans')
@jwt_required()
def plans_page():
    """Plans page"""
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    
    plans = [
        {'name': 'FREE', 'price': 0, 'features': ['5 groups', '3 campaigns/month']},
        {'name': 'PLUS', 'price': 29, 'features': ['50 groups', '25 campaigns/month']},
        {'name': 'PREMIUM', 'price': 99, 'features': ['Unlimited', 'Priority support']}
    ]
    
    return render_template_string('''
<!DOCTYPE html>
<html>
<head><title>Plans - Facebook SaaS</title></head>
<body>
    <h1>Subscription Plans</h1>
    <p>Current Plan: {{ current_user.current_plan }}</p>
    {% for plan in plans %}
    <div style="border: 1px solid #ccc; margin: 10px; padding: 15px;">
        <h3>{{ plan.name }} - ${{ plan.price }}/month</h3>
        <ul>
        {% for feature in plan.features %}
            <li>{{ feature }}</li>
        {% endfor %}
        </ul>
    </div>
    {% endfor %}
    <a href="/dashboard">← Back to Dashboard</a>
</body>
</html>
    ''', current_user=current_user, plans=plans)

@app.route('/scheduler')
@jwt_required()
def scheduler_page():
    """Scheduler page"""
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    
    return render_template_string('''
<!DOCTYPE html>
<html>
<head><title>Scheduler - Facebook SaaS</title></head>
<body>
    <h1>Campaign Scheduler</h1>
    <p>Welcome, {{ current_user.first_name }}!</p>
    <p>Schedule your campaigns for automatic posting.</p>
    <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
        <h3>Schedule Options:</h3>
        <ul>
            <li>One-time posting</li>
            <li>Daily recurring</li>
            <li>Weekly recurring</li>
            <li>Custom schedule</li>
        </ul>
    </div>
    <a href="/dashboard">← Back to Dashboard</a>
</body>
</html>
    ''', current_user=current_user)

@app.route('/telegram')
@jwt_required()
def telegram_page():
    """Telegram page"""
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    settings = TelegramSettings.query.filter_by(user_id=user_id).first()
    
    return render_template_string('''
<!DOCTYPE html>
<html>
<head><title>Telegram - Facebook SaaS</title></head>
<body>
    <h1>Telegram Bot Settings</h1>
    <p>Status: {{ 'Connected' if settings and settings.is_active else 'Not Connected' }}</p>
    {% if settings %}
    <p>Chat ID: {{ settings.chat_id }}</p>
    {% endif %}
    <p>Telegram bot configuration will be implemented here.</p>
    <a href="/dashboard">← Back to Dashboard</a>
</body>
</html>
    ''', current_user=current_user, settings=settings)

# Admin Routes
@app.route('/admin')
@jwt_required()
@admin_required
def admin_panel():
    """Admin panel"""
    user_id = get_jwt_identity()
    current_user = User.query.get(user_id)
    
    return render_template_string('''
<!DOCTYPE html>
<html>
<head><title>Admin Panel - Facebook SaaS</title></head>
<body>
    <h1>Admin Panel</h1>
    <p>Welcome, Admin {{ current_user.first_name }}!</p>
    <p>Admin functionality:</p>
    <ul>
        <li><a href="/api/v1/admin/users">View All Users</a></li>
        <li><a href="/api/v1/admin/analytics/overview">Platform Analytics</a></li>
    </ul>
    <a href="/dashboard">← Back to Dashboard</a>
</body>
</html>
    ''', current_user=current_user)

@app.route('/api/v1/admin/users', methods=['GET'])
@jwt_required()
@admin_required
def admin_get_users():
    """Get all users for admin"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        
        users = User.query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        user_list = []
        for user in users.items:
            user_dict = user.to_dict()
            user_dict['usage_stats'] = user.get_usage_stats()
            user_dict['campaigns_count'] = Campaign.query.filter_by(user_id=user.id).count()
            user_list.append(user_dict)
        
        return jsonify({
            'users': user_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': users.total,
                'pages': users.pages,
                'has_next': users.has_next,
                'has_prev': users.has_prev
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Admin get users error: {e}")
        return jsonify({'error': 'Failed to retrieve users'}), 500

@app.route('/api/v1/admin/analytics/overview', methods=['GET'])
@jwt_required()
@admin_required
def admin_analytics_overview():
    """Get platform analytics overview"""
    try:
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        total_campaigns = Campaign.query.count()
        
        # Plan distribution
        plan_stats = {}
        for plan in ['FREE', 'PLUS', 'PREMIUM']:
            count = User.query.filter_by(current_plan=plan).count()
            plan_stats[plan] = count
        
        return jsonify({
            'users': {
                'total': total_users,
                'active': active_users,
                'inactive': total_users - active_users
            },
            'campaigns': {
                'total': total_campaigns
            },
            'plans': plan_stats,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Admin analytics error: {e}")
        return jsonify({'error': 'Failed to get analytics'}), 500

# Telegram API Routes
@app.route('/api/telegram/settings', methods=['GET'])
@jwt_required()
def get_telegram_settings():
    """Get user's Telegram settings"""
    try:
        user_id = get_jwt_identity()
        settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        
        if not settings:
            return jsonify({
                'connected': False,
                'settings': None
            }), 200
        
        return jsonify({
            'connected': True,
            'settings': settings.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Get Telegram settings error: {e}")
        return jsonify({'error': 'Failed to get Telegram settings'}), 500

@app.route('/api/telegram/settings', methods=['POST'])
@jwt_required()
def save_telegram_settings():
    """Save user's Telegram settings"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        chat_id = data.get('chat_id', '').strip()
        if not chat_id:
            return jsonify({'error': 'Chat ID is required'}), 400
        
        if not validate_telegram_chat_id(chat_id):
            return jsonify({'error': 'Invalid chat ID format'}), 400
        
        # Get or create settings
        settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        if settings:
            settings.chat_id = chat_id
            settings.is_active = True
            settings.updated_at = datetime.utcnow()
        else:
            settings = TelegramSettings(
                user_id=user_id,
                chat_id=chat_id,
                is_active=True
            )
            db.session.add(settings)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Telegram settings saved successfully',
            'settings': settings.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Save Telegram settings error: {e}")
        return jsonify({'error': 'Failed to save Telegram settings'}), 500

@app.route('/api/telegram/test', methods=['POST'])
@jwt_required()
def test_telegram_connection():
    """Test Telegram bot connection"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        
        if not settings:
            return jsonify({'error': 'Telegram not configured'}), 400
        
        # Send test message
        test_message = f"🔔 Test Message\n\nHello {user.first_name}! Your Telegram bot is working correctly."
        
        success = send_telegram_message(settings.chat_id, test_message)
        
        # Update settings
        settings.last_test_sent = datetime.utcnow()
        settings.test_successful = success
        db.session.commit()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Test message sent successfully!'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to send test message.'
            }), 400
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Test Telegram connection error: {e}")
        return jsonify({'error': 'Failed to test Telegram connection'}), 500

# Campaign API Routes
@app.route('/api/campaigns', methods=['GET'])
@jwt_required()
def get_campaigns():
    """Get user's campaigns"""
    try:
        user_id = get_jwt_identity()
        campaigns = Campaign.query.filter_by(user_id=user_id).all()
        
        return jsonify({
            'campaigns': [campaign.to_dict() for campaign in campaigns]
        }), 200
        
    except Exception as e:
        logger.error(f"Get campaigns error: {e}")
        return jsonify({'error': 'Failed to get campaigns'}), 500

@app.route('/api/campaigns', methods=['POST'])
@jwt_required()
@limiter.limit("100 per 15 minutes")
def create_campaign():
    """Create a new campaign"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'message']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Create campaign
        campaign = Campaign(
            user_id=user_id,
            name=data['name'],
            message=data['message'],
            target_groups=json.dumps(data.get('target_groups', [])),
            max_groups=data.get('max_groups', 10),
            min_delay=data.get('min_delay', 10),
            max_delay=data.get('max_delay', 60)
        )
        
        db.session.add(campaign)
        db.session.commit()
        
        return jsonify({
            'message': 'Campaign created successfully',
            'campaign': campaign.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Create campaign error: {e}")
        return jsonify({'error': 'Failed to create campaign'}), 500

# Create tables and run app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create admin user if not exists
        try:
            if not User.query.filter_by(email='admin@test.com').first():
                admin = User(
                    email='admin@test.com',
                    first_name='Admin',
                    last_name='User',
                    role='admin',
                    current_plan='PREMIUM',
                    email_verified=True
                )
                admin.set_password('Admin123!')
                db.session.add(admin)
                db.session.commit()
                print("✅ Admin user created: admin@test.com / Admin123!")
        except Exception as e:
            print(f"⚠️  Admin user creation error: {e}")
    
    print("✅ Database tables created successfully!")
    print("\n🚀 Facebook SaaS Platform - Stable Test Mode")
    print("📡 URL: http://localhost:8080")
    print("🗄️  Database: SQLite (stable_test.db)")
    print("⚡ Ready for testing!")
    print("\nPress Ctrl+C to stop the server\n")
    
    # Run with basic Flask server (more stable than SocketIO)
    app.run(host='0.0.0.0', port=8080, debug=True, threaded=True) 