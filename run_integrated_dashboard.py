#!/usr/bin/env python3
"""
Integrated Facebook Group Fetcher with Authentication System
Combines SaaS authentication with original dashboard functionality
"""

import os
import json
import csv
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
import logging
import pandas as pd
from io import BytesIO
import zipfile
import base64
import hashlib
from cryptography.fernet import Fernet
import re
import sys
import bcrypt
import jwt
from functools import wraps

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import schedule

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'facebook-group-fetcher-integrated-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['JSON_AS_ASCII'] = False
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///integrated_dashboard.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")
# Require FERNET_KEY for encryption
FERNET_KEY = os.environ.get('FERNET_KEY')
if not FERNET_KEY:
    raise RuntimeError("FERNET_KEY environment variable is required for startup")
cipher = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)

def encrypt_password(raw: str) -> str:
    if not raw:
        return ''
    return cipher.encrypt(raw.encode()).decode()

def decrypt_password(enc: str) -> str:
    if not enc:
        return ''
    try:
        return cipher.decrypt(enc.encode()).decode()
    except Exception:
        return ''

# JWT Configuration
JWT_SECRET_KEY = 'your-secret-key-change-this-in-production'
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)

# Try to import bot modules
try:
    from bot.group_fetcher_fixed import FacebookGroupFetcher, get_fetched_groups
    bot_available = True
    logger.info("✅ Bot modules available")
except ImportError as e:
    bot_available = False
    logger.warning(f"Bot modules not available: {e}")
    
    # Mock functions for testing
    def get_fetched_groups():
        return []
    
    class FacebookGroupFetcher:
        def __init__(self, *args, **kwargs):
            pass

try:
    from bot.fb_poster import FacebookGroupPoster
    poster_available = True
    logger.info("✅ Facebook Poster available")
except ImportError as e:
    poster_available = False
    logger.warning(f"Facebook Poster not available: {e}")
    
    class FacebookGroupPoster:
        def __init__(self, *args, **kwargs):
            pass

try:
    from bot.analytics_db import analytics_db
    analytics_available = True
    logger.info("✅ Analytics database available")
except ImportError as e:
    analytics_available = False
    analytics_db = None
    logger.warning(f"Analytics not available: {e}")

# Global variables for tracking state
fetcher_instance = None
poster_instance = None
posting_thread = None
scheduled_jobs = []
job_history = []

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('exports', exist_ok=True)

# User model
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    facebook_username = db.Column(db.String(255))
    facebook_password = db.Column(db.String(255))
    use_headless = db.Column(db.Boolean, default=True)
    current_plan = db.Column(db.String(20), default='FREE')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': f"{self.first_name} {self.last_name}",
            'facebook_username': self.facebook_username,
            'use_headless': self.use_headless,
            'current_plan': self.current_plan,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'is_active': self.is_active
        }

# JWT Token Management
def create_access_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + JWT_ACCESS_TOKEN_EXPIRES,
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def verify_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Authentication decorator
def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            token = token.split(' ')[1]  # Remove 'Bearer ' prefix
            user_id = verify_token(token)
            if not user_id:
                return jsonify({'error': 'Token is invalid'}), 401
            
            current_user = User.query.get(user_id)
            if not current_user or not current_user.is_active:
                return jsonify({'error': 'User not found or inactive'}), 401
            
            # Store current user in global context
            request.current_user = current_user
            
        except Exception as e:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(*args, **kwargs)
    return decorated

# Login page template
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Facebook Group Fetcher</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            max-width: 400px;
            width: 100%;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .logo {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo h1 {
            color: white;
            font-weight: 700;
            font-size: 2rem;
        }
        .form-floating .form-control {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: white;
        }
        .form-floating .form-control:focus {
            background: rgba(255, 255, 255, 0.2);
            border-color: rgba(255, 255, 255, 0.5);
            box-shadow: 0 0 0 0.25rem rgba(255, 255, 255, 0.15);
        }
        .form-floating label {
            color: rgba(255, 255, 255, 0.8);
        }
        .btn-primary {
            background: linear-gradient(45deg, #667eea, #764ba2);
            border: none;
            border-radius: 10px;
            padding: 12px;
            font-weight: 600;
        }
        .btn-primary:hover {
            background: linear-gradient(45deg, #5a6fd8, #6a4190);
        }
        .result {
            margin-top: 15px;
            padding: 10px;
            border-radius: 8px;
            display: none;
        }
        .result.success {
            background: rgba(25, 135, 84, 0.2);
            border: 1px solid rgba(25, 135, 84, 0.3);
            color: #20c997;
        }
        .result.error {
            background: rgba(220, 53, 69, 0.2);
            border: 1px solid rgba(220, 53, 69, 0.3);
            color: #f8d7da;
        }
        .nav-tabs .nav-link {
            background: rgba(255, 255, 255, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: rgba(255, 255, 255, 0.8);
            margin-right: 5px;
        }
        .nav-tabs .nav-link.active {
            background: rgba(255, 255, 255, 0.2);
            border-bottom-color: transparent;
            color: white;
        }
        .tab-content {
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <!-- Auto Login Message -->
        <div id="autoLoginMessage" style="display: none;"></div>
        
        <div class="logo">
            <h1><i class="bi bi-facebook"></i> GroupFetcher</h1>
            <p class="text-white-50">Advanced Facebook Group Management</p>
        </div>
        
        <ul class="nav nav-tabs" id="authTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="login-tab" data-bs-toggle="tab" data-bs-target="#login" type="button" role="tab">
                    <i class="bi bi-box-arrow-in-right me-2"></i>Login
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="register-tab" data-bs-toggle="tab" data-bs-target="#register" type="button" role="tab">
                    <i class="bi bi-person-plus me-2"></i>Register
                </button>
            </li>
        </ul>
        
        <div class="tab-content" id="authTabsContent">
            <!-- Login Tab -->
            <div class="tab-pane fade show active" id="login" role="tabpanel">
                <form id="loginForm">
                    <div class="form-floating mb-3">
                        <input type="email" class="form-control" id="loginEmail" placeholder="name@example.com" required>
                        <label for="loginEmail">Email address</label>
                    </div>
                    <div class="form-floating mb-3">
                        <input type="password" class="form-control" id="loginPassword" placeholder="Password" required>
                        <label for="loginPassword">Password</label>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="bi bi-box-arrow-in-right me-2"></i>Login
                    </button>
                    <div id="loginResult" class="result"></div>
                </form>
            </div>
            
            <!-- Register Tab -->
            <div class="tab-pane fade" id="register" role="tabpanel">
                <form id="registerForm">
                    <div class="row mb-3">
                        <div class="col-6">
                            <div class="form-floating">
                                <input type="text" class="form-control" id="registerFirstName" placeholder="First Name" required>
                                <label for="registerFirstName">First Name</label>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="form-floating">
                                <input type="text" class="form-control" id="registerLastName" placeholder="Last Name" required>
                                <label for="registerLastName">Last Name</label>
                            </div>
                        </div>
                    </div>
                    <div class="form-floating mb-3">
                        <input type="email" class="form-control" id="registerEmail" placeholder="name@example.com" required>
                        <label for="registerEmail">Email address</label>
                    </div>
                    <div class="form-floating mb-3">
                        <input type="password" class="form-control" id="registerPassword" placeholder="Password" required>
                        <label for="registerPassword">Password</label>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="bi bi-person-plus me-2"></i>Create Account
                    </button>
                    <div id="registerResult" class="result"></div>
                </form>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Handle registration
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const data = {
                first_name: document.getElementById('registerFirstName').value,
                last_name: document.getElementById('registerLastName').value,
                email: document.getElementById('registerEmail').value,
                password: document.getElementById('registerPassword').value
            };
            
            try {
                const response = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                const resultDiv = document.getElementById('registerResult');
                
                if (response.ok) {
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = '✅ Registration Successful! Welcome ' + result.user.full_name + '! Redirecting to dashboard...';
                    
                    localStorage.setItem('access_token', result.access_token);
                    
                    // Also set cookie for server-side access
                    document.cookie = 'access_token=' + result.access_token + '; path=/; max-age=86400';
                    
                    // Redirect to dashboard after 2 seconds
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 2000);
                } else {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = '❌ Registration Failed: ' + (result.error || 'Unknown error');
                }
                
                resultDiv.style.display = 'block';
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('registerResult').innerHTML = '❌ Network Error: ' + error.message;
                document.getElementById('registerResult').className = 'result error';
                document.getElementById('registerResult').style.display = 'block';
            }
        });
        
        // Handle login
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const data = {
                email: document.getElementById('loginEmail').value,
                password: document.getElementById('loginPassword').value
            };
            
            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                const resultDiv = document.getElementById('loginResult');
                
                if (response.ok) {
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = '✅ Login Successful! Welcome back ' + result.user.full_name + '! Redirecting to dashboard...';
                    
                    localStorage.setItem('access_token', result.access_token);
                    
                    // Also set cookie for server-side access
                    document.cookie = 'access_token=' + result.access_token + '; path=/; max-age=86400';
                    
                    // Redirect to dashboard after 2 seconds
                    setTimeout(() => {
                        window.location.href = '/dashboard';
                    }, 2000);
                } else {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = '❌ Login Failed: ' + (result.error || 'Unknown error');
                }
                
                resultDiv.style.display = 'block';
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('loginResult').innerHTML = '❌ Network Error: ' + error.message;
                document.getElementById('loginResult').className = 'result error';
                document.getElementById('loginResult').style.display = 'block';
            }
        });
        
        // Check for existing token
        window.addEventListener('load', () => {
            const token = localStorage.getItem('access_token');
            if (token) {
                // Verify token and redirect to dashboard
                fetch('/api/auth/me', {
                    headers: {
                        'Authorization': 'Bearer ' + token
                    }
                })
                .then(response => {
                    if (response.ok) {
                        // Show auto-login message
                        const autoLoginDiv = document.getElementById('autoLoginMessage');
                        autoLoginDiv.style.display = 'block';
                        autoLoginDiv.innerHTML = `
                            <div class="alert alert-info">
                                <i class="bi bi-info-circle me-2"></i>
                                <strong>Welcome back!</strong> You are already logged in. 
                                <span class="spinner-border spinner-border-sm ms-2" role="status"></span>
                                Redirecting to dashboard...
                            </div>
                        `;
                        
                        // Set cookie for server-side access
                        document.cookie = 'access_token=' + token + '; path=/; max-age=86400';
                        
                        // Redirect with a delay to show the message
                        setTimeout(() => {
                            window.location.href = '/dashboard';
                        }, 1500);
                    } else {
                        localStorage.removeItem('access_token');
                        document.cookie = 'access_token=; path=/; max-age=0'; // Clear cookie
                    }
                })
                .catch(error => {
                    console.log('Token check failed:', error);
                    localStorage.removeItem('access_token');
                    document.cookie = 'access_token=; path=/; max-age=0'; // Clear cookie
                });
            }
        });
    </script>
</body>
</html>
'''

# Progress tracking
class ProgressTracker:
    def __init__(self):
        self.is_running = False
        self.progress = 0
        self.status = "idle"
        self.details = ""
        self.start_time = None
        self.groups_found = 0
        self.current_group = ""
        self.error_message = None
        
    def start(self):
        self.is_running = True
        self.progress = 0
        self.status = "running"
        self.start_time = time.time()
        self.groups_found = 0
        self.error_message = None
        
    def update(self, progress, status, details="", current_group=""):
        self.progress = progress
        self.status = status
        self.details = details
        self.current_group = current_group
        
    def set_error(self, error_msg):
        self.error_message = error_msg
        self.status = "error"
        self.is_running = False
        
    def finish(self):
        self.is_running = False
        self.progress = 100
        self.status = "completed"
        
    def get_dict(self):
        return {
            'is_running': self.is_running,
            'progress': self.progress,
            'status': self.status,
            'details': self.details,
            'start_time': self.start_time,
            'groups_found': self.groups_found,
            'current_group': self.current_group,
            'error_message': self.error_message
        }

# Global progress tracker
progress_tracker = ProgressTracker()

# Utility functions
def get_last_fetch_time():
    try:
        groups = get_fetched_groups()
        if groups:
            return "Recently updated"
        return "Never"
    except:
        return "Unknown"

def get_current_user():
    """Get current user from request context"""
    return getattr(request, 'current_user', None)

# Routes
@app.route('/')
def home():
    """Landing page with login/register"""
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    """Main dashboard page - requires authentication"""
    # Check if user is authenticated
    token = request.headers.get('Authorization') or request.cookies.get('access_token')
    
    if not token:
        return redirect(url_for('home'))
    
    try:
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        user_id = verify_token(token)
        if not user_id:
            return redirect(url_for('home'))
        
        current_user = User.query.get(user_id)
        if not current_user or not current_user.is_active:
            return redirect(url_for('home'))
        
        # Update last login
        current_user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Get dashboard data
        groups = get_fetched_groups()
        stats = {
            'total_groups': len(groups),
            'last_fetch': get_last_fetch_time(),
            'scheduled_jobs': len(scheduled_jobs),
            'job_history': len(job_history)
        }
        
        return render_template('dashboard.html', stats=stats, current_user=current_user)
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return redirect(url_for('home'))

@app.route('/groups')
def groups_page():
    """Groups page - requires authentication"""
    # Check authentication similar to dashboard
    token = request.headers.get('Authorization') or request.cookies.get('access_token')
    
    if not token:
        return redirect(url_for('home'))
    
    try:
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        user_id = verify_token(token)
        if not user_id:
            return redirect(url_for('home'))
        
        current_user = User.query.get(user_id)
        if not current_user or not current_user.is_active:
            return redirect(url_for('home'))
        
        groups = get_fetched_groups()
        return render_template('groups.html', groups=groups, current_user=current_user)
        
    except Exception as e:
        logger.error(f"Groups page error: {e}")
        return redirect(url_for('home'))

@app.route('/poster')
def poster_page():
    """Poster page - requires authentication"""
    # Check authentication similar to dashboard
    token = request.headers.get('Authorization') or request.cookies.get('access_token')
    
    if not token:
        return redirect(url_for('home'))
    
    try:
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        user_id = verify_token(token)
        if not user_id:
            return redirect(url_for('home'))
        
        current_user = User.query.get(user_id)
        if not current_user or not current_user.is_active:
            return redirect(url_for('home'))
        
        groups = get_fetched_groups()
        return render_template('poster.html', groups=groups, current_user=current_user)
        
    except Exception as e:
        logger.error(f"Poster page error: {e}")
        return redirect(url_for('home'))

@app.route('/scheduler')
def scheduler_page():
    """Scheduler page - requires authentication"""
    # Check authentication similar to dashboard
    token = request.headers.get('Authorization') or request.cookies.get('access_token')
    
    if not token:
        return redirect(url_for('home'))
    
    try:
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        user_id = verify_token(token)
        if not user_id:
            return redirect(url_for('home'))
        
        current_user = User.query.get(user_id)
        if not current_user or not current_user.is_active:
            return redirect(url_for('home'))
        
        return render_template('scheduler.html', 
                             scheduled_jobs=scheduled_jobs, 
                             job_history=job_history,
                             current_user=current_user)
        
    except Exception as e:
        logger.error(f"Scheduler page error: {e}")
        return redirect(url_for('home'))

@app.route('/templates')
def template_manager():
    """Template manager - requires authentication"""
    # Check authentication similar to dashboard
    token = request.headers.get('Authorization') or request.cookies.get('access_token')
    
    if not token:
        return redirect(url_for('home'))
    
    try:
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        user_id = verify_token(token)
        if not user_id:
            return redirect(url_for('home'))
        
        current_user = User.query.get(user_id)
        if not current_user or not current_user.is_active:
            return redirect(url_for('home'))
        
        return render_template('templates.html', current_user=current_user)
        
    except Exception as e:
        logger.error(f"Templates page error: {e}")
        return redirect(url_for('home'))

@app.route('/plans')
def plans_page():
    """Plans selection page - requires authentication"""
    # Check authentication similar to dashboard
    token = request.headers.get('Authorization') or request.cookies.get('access_token')
    
    if not token:
        return redirect(url_for('home'))
    
    try:
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        user_id = verify_token(token)
        if not user_id:
            return redirect(url_for('home'))
        
        current_user = User.query.get(user_id)
        if not current_user or not current_user.is_active:
            return redirect(url_for('home'))
        
        # Define plans with their features
        plans = {
            'FREE': {
                'name': 'FREE',
                'price': '$0',
                'price_period': 'forever',
                'features': [
                    '✅ Basic group fetching',
                    '✅ Up to 50 groups discovery',
                    '✅ Manual posting to 5 groups',
                    '✅ Basic analytics',
                    '❌ Auto-scheduling',
                    '❌ Advanced analytics',
                    '❌ Priority support'
                ],
                'limits': 'Limited features',
                'button_text': 'Current Plan' if current_user.current_plan == 'FREE' else 'Downgrade',
                'is_current': current_user.current_plan == 'FREE',
                'color': 'secondary'
            },
            'PLUS': {
                'name': 'PLUS',
                'price': '$29',
                'price_period': 'per month',
                'features': [
                    '✅ Everything in FREE',
                    '✅ Up to 500 groups discovery',
                    '✅ Posting to 50 groups',
                    '✅ Auto-scheduling',
                    '✅ Advanced analytics',
                    '✅ Email support',
                    '❌ Priority support'
                ],
                'limits': 'Perfect for small businesses',
                'button_text': 'Current Plan' if current_user.current_plan == 'PLUS' else 'Upgrade to PLUS',
                'is_current': current_user.current_plan == 'PLUS',
                'color': 'primary'
            },
            'PREMIUM': {
                'name': 'PREMIUM',
                'price': '$99',
                'price_period': 'per month',
                'features': [
                    '✅ Everything in PLUS',
                    '✅ Unlimited groups discovery',
                    '✅ Posting to unlimited groups',
                    '✅ Advanced auto-scheduling',
                    '✅ Premium analytics & insights',
                    '✅ Priority support',
                    '✅ Custom integrations'
                ],
                'limits': 'For agencies and enterprises',
                'button_text': 'Current Plan' if current_user.current_plan == 'PREMIUM' else 'Upgrade to PREMIUM',
                'is_current': current_user.current_plan == 'PREMIUM',
                'color': 'warning'
            }
        }
        
        return render_template('plans.html', plans=plans, current_user=current_user)
        
    except Exception as e:
        logger.error(f"Plans page error: {e}")
        return redirect(url_for('home'))

@app.route('/analytics')
def analytics():
    """Analytics page - requires authentication"""
    # Check authentication similar to dashboard
    token = request.headers.get('Authorization') or request.cookies.get('access_token')
    
    if not token:
        return redirect(url_for('home'))
    
    try:
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        user_id = verify_token(token)
        if not user_id:
            return redirect(url_for('home'))
        
        current_user = User.query.get(user_id)
        if not current_user or not current_user.is_active:
            return redirect(url_for('home'))
        
        # Get analytics data
        if not analytics_available:
            return render_template('analytics.html',
                                 error_message="Analytics system is not available. Please check the analytics_db module.",
                                 total_posts=0,
                                 avg_engagement_rate=0,
                                 active_groups=0,
                                 success_rate=0,
                                 top_groups=[],
                                 recommended_groups=[],
                                 avoid_groups=[],
                                 performance_dates=[],
                                 performance_data=[],
                                 engagement_breakdown=[1,1,1],
                                 recent_posts=[],
                                 current_user=current_user)
        
        try:
            # Get analytics data
            top_groups = analytics_db.get_top_performing_groups(10)
            
            # Calculate summary statistics
            total_posts = sum(group.get('total_posts', 0) for group in top_groups)
            avg_engagement_rate = sum(group.get('avg_engagement_rate', 0) for group in top_groups) / len(top_groups) if top_groups else 0
            active_groups = len(top_groups)
            success_rate = sum(group.get('post_success_rate', 0) for group in top_groups) / len(top_groups) if top_groups else 0
            
            # Get recommended and avoid groups
            recommended_groups = [g for g in top_groups if g.get('recommendation_score', 0) >= 0.8]
            avoid_groups = [g for g in top_groups if g.get('consecutive_failures', 0) >= 2]
            
            # Mock data for charts
            performance_dates = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            performance_data = [2.1, 3.5, 2.8, 4.2, 3.9, 5.1, 4.7]
            engagement_breakdown = [150, 45, 12]
            
            recent_posts = []
            
            return render_template('analytics.html',
                                 total_posts=total_posts,
                                 avg_engagement_rate=avg_engagement_rate,
                                 active_groups=active_groups,
                                 success_rate=success_rate * 100,
                                 top_groups=top_groups,
                                 recommended_groups=recommended_groups,
                                 avoid_groups=avoid_groups,
                                 performance_dates=performance_dates,
                                 performance_data=performance_data,
                                 engagement_breakdown=engagement_breakdown,
                                 recent_posts=recent_posts,
                                 current_user=current_user)
        
        except Exception as e:
            logger.error(f"Analytics data error: {e}")
            return render_template('analytics.html',
                                 error_message=f"Error loading analytics data: {str(e)}",
                                 total_posts=0,
                                 avg_engagement_rate=0,
                                 active_groups=0,
                                 success_rate=0,
                                 top_groups=[],
                                 recommended_groups=[],
                                 avoid_groups=[],
                                 performance_dates=[],
                                 performance_data=[],
                                 engagement_breakdown=[1,1,1],
                                 recent_posts=[],
                                 current_user=current_user)
        
    except Exception as e:
        logger.error(f"Analytics page error: {e}")
        return redirect(url_for('home'))

# Authentication API Routes
@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        if not all(k in data for k in ['email', 'password', 'first_name', 'last_name']):
            return jsonify({'error': 'Missing required fields'}), 400
        
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'User already exists'}), 400
        
        user = User(
            email=data['email'],
            first_name=data['first_name'],
            last_name=data['last_name']
        )
        user.set_password(data['password'])
        
        db.session.add(user)
        db.session.commit()
        
        access_token = create_access_token(user.id)
        
        return jsonify({
            'message': 'User created successfully',
            'user': user.to_dict(),
            'access_token': access_token
        }), 201
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        if not all(k in data for k in ['email', 'password']):
            return jsonify({'error': 'Missing email or password'}), 400
        
        user = User.query.filter_by(email=data['email']).first()
        
        if not user or not user.check_password(data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user.is_active:
            return jsonify({'error': 'Account is disabled'}), 401
        
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        access_token = create_access_token(user.id)
        
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict(),
            'access_token': access_token
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500

@app.route('/api/auth/me', methods=['GET'])
@jwt_required
def get_current_user():
    try:
        user = request.current_user
        return jsonify(user.to_dict()), 200
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        return jsonify({'error': 'Failed to get user info'}), 500

@app.route('/api/auth/logout', methods=['POST'])
@jwt_required
def logout():
    # JWT tokens are stateless, so we just return success
    # In a production app, you might want to implement a token blacklist
    response = jsonify({'message': 'Logout successful'})
    response.set_cookie('access_token', '', expires=0, path='/')  # Clear cookie
    return response, 200

@app.route('/clear-tokens')
def clear_tokens():
    """Clear all tokens for testing purposes"""
    response = redirect(url_for('home'))
    response.set_cookie('access_token', '', expires=0, path='/')
    return response

@app.route('/api/user/plan', methods=['POST'])
@jwt_required
def update_user_plan():
    """Update user's plan (for admin use or testing)"""
    try:
        data = request.get_json()
        new_plan = data.get('plan', '').upper()
        
        if new_plan not in ['FREE', 'PLUS', 'PREMIUM']:
            return jsonify({'error': 'Invalid plan. Must be FREE, PLUS, or PREMIUM'}), 400
        
        current_user = request.current_user
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        old_plan = current_user.current_plan
        current_user.current_plan = new_plan
        db.session.commit()
        
        return jsonify({
            'message': f'Plan updated successfully from {old_plan} to {new_plan}',
            'old_plan': old_plan,
            'new_plan': new_plan,
            'user': current_user.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Plan update error: {e}")
        return jsonify({'error': 'Failed to update plan'}), 500

# API Routes from original dashboard
@app.route('/api/start_fetch', methods=['POST'])
@jwt_required
def start_fetch():
    """Start fetching Facebook groups"""
    global fetcher_instance
    
    try:
        if not bot_available:
            return jsonify({'error': 'Bot modules not available'}), 500
        
        if progress_tracker.is_running:
            return jsonify({'error': 'Fetching already in progress'}), 400
        
        data = request.get_json()
        current_user = request.current_user
        
        # Use user's saved credentials or form data
        username = data.get('username') or current_user.facebook_username
        saved_password = decrypt_password(current_user.facebook_password) if current_user.facebook_password else ''
        password = data.get('password') or saved_password
        headless = data.get('headless', current_user.use_headless)
        
        if not username or not password:
            return jsonify({'error': 'Facebook credentials required'}), 400
        
        # Save credentials if requested
        if data.get('save_credentials'):
            current_user.facebook_username = username
            current_user.facebook_password = encrypt_password(password)
            current_user.use_headless = headless
            db.session.commit()
        
        # Start fetching in background thread
        def fetch_groups():
            try:
                progress_tracker.start()
                
                # Initialize fetcher
                fetcher_instance = FacebookGroupFetcher(
                    username=username,
                    password=password,
                    headless=headless
                )
                
                # Start fetching with progress updates
                def progress_callback(progress, status, details=""):
                    progress_tracker.update(progress, status, details)
                    socketio.emit('fetch_progress', progress_tracker.get_dict())
                
                fetcher_instance.fetch_groups(progress_callback=progress_callback)
                
                progress_tracker.finish()
                socketio.emit('fetch_complete', progress_tracker.get_dict())
                
            except Exception as e:
                logger.error(f"Fetch error: {e}")
                progress_tracker.set_error(str(e))
                socketio.emit('fetch_error', progress_tracker.get_dict())
        
        thread = threading.Thread(target=fetch_groups)
        thread.daemon = True
        thread.start()
        
        return jsonify({'message': 'Fetching started', 'status': 'started'}), 200
        
    except Exception as e:
        logger.error(f"Start fetch error: {e}")
        return jsonify({'error': 'Failed to start fetching'}), 500

@app.route('/api/progress', methods=['GET'])
@jwt_required
def get_progress():
    """Get current fetch progress"""
    return jsonify(progress_tracker.get_dict())

@app.route('/api/groups', methods=['GET'])
@jwt_required
def get_groups_api():
    """Get all fetched groups"""
    try:
        groups = get_fetched_groups()
        return jsonify({'groups': groups, 'total': len(groups)})
    except Exception as e:
        logger.error(f"Get groups error: {e}")
        return jsonify({'error': 'Failed to get groups'}), 500

@app.route('/api/user/settings', methods=['POST'])
@jwt_required
def update_user_settings():
    """Update user Facebook settings"""
    try:
        data = request.get_json()
        user = request.current_user
        
        if 'facebook_username' in data:
            user.facebook_username = data['facebook_username']
        if 'facebook_password' in data and data['facebook_password']:
            user.facebook_password = encrypt_password(data['facebook_password'])
        if 'use_headless' in data:
            user.use_headless = data['use_headless']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Settings updated successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Update settings error: {e}")
        return jsonify({'error': 'Failed to update settings'}), 500

# Export routes
@app.route('/api/export/<format>')
@jwt_required
def export_groups(format):
    """Export groups in specified format"""
    try:
        groups = get_fetched_groups()
        
        if format == 'json':
            return jsonify(groups)
        
        elif format == 'csv':
            # Create CSV
            output = BytesIO()
            writer = csv.writer(output)
            
            # Write header
            if groups:
                writer.writerow(groups[0].keys())
                for group in groups:
                    writer.writerow(group.values())
            
            output.seek(0)
            return send_file(
                output,
                mimetype='text/csv',
                as_attachment=True,
                download_name='facebook_groups.csv'
            )
        
        elif format == 'excel':
            # Create Excel
            output = BytesIO()
            df = pd.DataFrame(groups)
            df.to_excel(output, index=False)
            output.seek(0)
            
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='facebook_groups.xlsx'
            )
        
        elif format == 'all':
            # Create ZIP with all formats
            zip_buffer = BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add JSON
                zip_file.writestr('facebook_groups.json', json.dumps(groups, indent=2))
                
                # Add CSV
                csv_buffer = BytesIO()
                if groups:
                    df = pd.DataFrame(groups)
                    df.to_csv(csv_buffer, index=False)
                    zip_file.writestr('facebook_groups.csv', csv_buffer.getvalue())
                
                # Add Excel
                excel_buffer = BytesIO()
                if groups:
                    df = pd.DataFrame(groups)
                    df.to_excel(excel_buffer, index=False)
                    zip_file.writestr('facebook_groups.xlsx', excel_buffer.getvalue())
            
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name='facebook_groups_export.zip'
            )
        
        else:
            return jsonify({'error': 'Invalid export format'}), 400
            
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'error': 'Export failed'}), 500

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

@socketio.on('get_progress')
def handle_get_progress():
    emit('fetch_progress', progress_tracker.get_dict())

# Health check
@app.route('/health')
def health():
    try:
        user_count = User.query.count()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'users': user_count,
            'bot_available': bot_available,
            'poster_available': poster_available,
            'analytics_available': analytics_available
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

# Initialize database
def init_db():
    try:
        with app.app_context():
            db.create_all()
            logger.info("✅ Database tables created successfully!")
        return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False

if __name__ == '__main__':
    # Initialize database
    if not init_db():
        logger.error("Failed to initialize database")
        sys.exit(1)
    
    logger.info("✅ Facebook Group Fetcher integration enabled")
    logger.info("✅ Database tables created successfully!")
    logger.info("🚀 Facebook Group Fetcher - Integrated Dashboard")
    logger.info("📡 URL: http://localhost:8080")
    logger.info("🗄️  Database: SQLite (integrated_dashboard.db)")
    logger.info("🤖 Bot Integration: ✅ Enabled" if bot_available else "🤖 Bot Integration: ❌ Disabled")
    logger.info("📊 Analytics: ✅ Enabled" if analytics_available else "📊 Analytics: ❌ Disabled")
    logger.info("⚡ Ready for testing!")
    logger.info("Press Ctrl+C to stop the server")
    
    # Run the application
    socketio.run(
        app,
        host='0.0.0.0',
        port=8080,
        debug=True,
        allow_unsafe_werkzeug=True
    ) 