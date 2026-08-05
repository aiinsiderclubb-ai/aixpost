#!/usr/bin/env python3
from __future__ import annotations

"""
AIPostX - Integrated Test Version
With automatic dashboard redirect, AI posting integration, and real-time updates
"""

import os
import sys
import logging
import json
import io
import time
import threading
import random
import atexit
import signal
import re
import csv
import zipfile
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from functools import wraps
from flask import Flask, request, render_template, render_template_string, jsonify, redirect, url_for, session, make_response, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, validate_csrf
from werkzeug.exceptions import BadRequest
from flask_cors import CORS
from rq import Queue
import redis
from cryptography.fernet import Fernet
import secrets
import requests
from urllib.parse import unquote
from flask_login import UserMixin
import sqlite3
from platform_runtime import RuntimeStore, LocalTaskManager
from app.core.config import AppConfig
from app.services.task_dispatcher import TaskDispatcher
from app.services.posting_utils import poster_status_to_task_status

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Browser automation is deliberately imported only by explicit work runners.
# Importing it here loads Selenium and may inspect/create browser profiles.
FacebookGroupPoster = None
FacebookGroupFetcher = None
FACEBOOK_POSTER_AVAILABLE = None


def _load_facebook_automation() -> bool:
    global FacebookGroupPoster, FacebookGroupFetcher, FACEBOOK_POSTER_AVAILABLE
    if FACEBOOK_POSTER_AVAILABLE is not None:
        return FACEBOOK_POSTER_AVAILABLE
    try:
        from bot.fb_poster import FacebookGroupPoster as Poster
        from bot.group_fetcher import FacebookGroupFetcher as Fetcher
        FacebookGroupPoster = Poster
        FacebookGroupFetcher = Fetcher
        FACEBOOK_POSTER_AVAILABLE = True
        logger.info("✅ AI Posting integration enabled")
    except ImportError as exc:
        FACEBOOK_POSTER_AVAILABLE = False
        logger.warning("⚠️ AI Posting not available: %s", exc)
    return FACEBOOK_POSTER_AVAILABLE

# Global variables for background processing
poster_instances = {}  # user_id -> FacebookGroupPoster instance
active_campaigns = {}  # campaign_id -> campaign data
campaign_threads = {}  # campaign_id -> thread
# campaign_manager and job_scheduler will be initialized in __main__
campaign_manager = None
job_scheduler = None
fetcher_instance = None
poster_instance = None

# WebSocket broadcast helper
def broadcast_to_user(user_id: int, event: str, data: dict):
    """Broadcast event to specific user via WebSocket"""
    try:
        room = f"user_{user_id}"
        socketio.emit(event, data, room=room)
        logger.info(f"Broadcast {event} to user {user_id}: {data}")
    except Exception as e:
        logger.error(f"Failed to broadcast {event} to user {user_id}: {e}")

def broadcast_to_admins(event: str, data: dict):
    """Broadcast event to all admin users"""
    try:
        socketio.emit(event, data, room="admins")
        logger.info(f"Broadcast {event} to admins: {data}")
    except Exception as e:
        logger.error(f"Failed to broadcast {event} to admins: {e}")

# Configuration
class TestConfig:
    DEBUG = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    _IS_DEVELOPMENT = DEBUG or os.environ.get('FLASK_ENV', '').lower() in ('development', 'dev', 'testing')
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    if not SECRET_KEY and _IS_DEVELOPMENT:
        SECRET_KEY = 'development-only-change-me'
    if not JWT_SECRET_KEY and _IS_DEVELOPMENT:
        JWT_SECRET_KEY = 'development-only-jwt-change-me'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_SECURE = not _IS_DEVELOPMENT
    JWT_COOKIE_CSRF_PROTECT = not _IS_DEVELOPMENT
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_COOKIE_NAME = 'access_token'
    JWT_REFRESH_COOKIE_NAME = 'refresh_token'
    # Fetcher storage (per-user directory)
    GROUPS_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'user_data', 'groups')
    FETCHED_GROUPS_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'autofetched_groups.json')  # legacy fallback
    
    # Database configuration (SQLite)
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + AppConfig.APP_SQLITE_PATH
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Email configuration (mock)
    MAIL_SERVER = 'localhost'
    MAIL_PORT = 1025
    MAIL_USE_TLS = False
    MAIL_USERNAME = ''
    MAIL_PASSWORD = ''
    MAIL_DEFAULT_SENDER = 'test@facebook-saas.com'
    
    # Telegram Bot configuration
    TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', 'your-telegram-bot-token-here')

# Simple progress tracker for fetching
class ProgressTracker:
    def __init__(self) -> None:
        self.status = 'idle'
        self.step = ''
        self.progress = 0
        self.total_groups = 0
        self.current_scroll = 0
        self.max_scroll = 0
        self.error = None
        self.message = ''
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    def reset(self) -> None:
        self.__init__()

    def start(self) -> None:
        self.status = 'running'
        self.start_time = datetime.utcnow()

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def finish(self, success: bool = True) -> None:
        self.status = 'completed' if success else 'failed'
        self.end_time = datetime.utcnow()

    def get_elapsed_time(self) -> int:
        if not self.start_time:
            return 0
        end = self.end_time or datetime.utcnow()
        return int((end - self.start_time).total_seconds())

progress_tracker = ProgressTracker()

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(TestConfig)

# Extensions are bound by create_app(), after test configuration is applied.
db = SQLAlchemy()
jwt = JWTManager()
bcrypt = Bcrypt()
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')
# csrf = CSRFProtect(app)  # Disabled for test mode
cors = CORS()

# Local persistent runtime store for release features.
RUNTIME_DB_PATH = AppConfig.RUNTIME_DB_PATH
runtime_store = None
task_manager = None

# RQ setup
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
redis_conn = None
job_queue = None
analytics_queue = None
task_dispatcher = None

# --- Security middleware (production hardening) ---
@app.after_request
def apply_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Allow only self by default, but permit inline styles/scripts for our templates,
    # and Bootstrap/CDN assets required by existing templates.
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'"
    )
    return response

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per minute"],
    storage_uri="memory://"
)

# Initialize encryption for Facebook credentials
FERNET_KEY = AppConfig.get_fernet_key()

cipher = Fernet(FERNET_KEY.encode() if isinstance(FERNET_KEY, str) else FERNET_KEY)

# Encryption helper functions
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
    except Exception as e:
        logger.error(f"Failed to decrypt password: {e}")
        return ""


def _ensure_release_runtime_user_state(user: "User") -> Optional[int]:
    """Sync primary Facebook account and templates into the local runtime store."""
    if not user:
        return None

    account_id = None
    if user.facebook_username:
        account_id = runtime_store.upsert_account(
            user_id=user.id,
            login_email=user.facebook_username,
            encrypted_password=user.facebook_password or "",
            label="Primary account",
            is_primary=True,
            is_active=True,
            priority=100,
            profile_dir=os.path.join(
                os.path.abspath(os.path.dirname(__file__)),
                'user_data',
                'profiles',
                f'profile_user_{user.id}',
            ),
        )

    try:
        templates_file = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates_data', 'message_templates.json')
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                template_payload = json.load(f)
            runtime_store.sync_templates(user.id, template_payload.get('templates', []))
    except Exception as template_sync_error:
        logger.warning(f"Template metadata sync skipped: {template_sync_error}")

    return account_id


def _record_session_state(user_id: int, account_id: Optional[int], status: str, reason: str = "", **extra) -> None:
    runtime_store.record_session(
        user_id=user_id,
        account_id=account_id,
        status=status,
        reason=reason,
        **extra,
    )
    if account_id:
        runtime_store.update_account_status(account_id, status if status else 'unknown', reason)


def _task_snapshot_from_poster(user_id: int, task: Optional[dict], live_status: Optional[dict]) -> dict:
    task = task or {}
    live_status = live_status or task.get('result') or {}
    result = {
        'task_id': task.get('id'),
        'task_status': task.get('status', live_status.get('status', 'idle')),
        'is_posting': bool(live_status.get('is_posting') or task.get('status') in ('queued', 'running', 'waiting_manual', 'paused')),
        'status': live_status.get('status') or task.get('status', 'Idle'),
        'posts_completed': live_status.get('posts_completed', 0),
        'posts_failed': live_status.get('posts_failed', 0),
        'groups_total': live_status.get('groups_total', 0),
        'elapsed_time': live_status.get('elapsed_time', '00:00:00'),
        'current_group': live_status.get('current_group'),
        'error': live_status.get('error') or task.get('error_message'),
        'group_statuses': [],
        'events': [],
        'session': runtime_store.get_latest_session(user_id),
        'accounts': runtime_store.list_accounts(user_id),
    }

    if task.get('group_statuses'):
        result['group_statuses'] = task['group_statuses']
    if task.get('events'):
        result['events'] = task['events']

    if live_status:
        groups = []
        for group_id, payload in (live_status.get('group_statuses') or {}).items():
            row = {'group_key': group_id}
            row.update(payload)
            groups.append(row)
        if groups:
            result['group_statuses'] = groups
        if live_status.get('recent_events'):
            result['events'] = live_status['recent_events']
    return result


def _template_runtime_user_id() -> int:
    verify_jwt_in_request()
    return int(get_jwt_identity())

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'test_token_for_development')

def send_telegram_message(chat_id: str, message: str) -> bool:
    """Send message via Telegram Bot API"""
    if TELEGRAM_BOT_TOKEN == 'test_token_for_development':
        logger.info(f"TEST MODE: Would send Telegram message to {chat_id}: {message}")
        return True
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get('ok'):
            logger.info(f"✅ Telegram message sent successfully to {chat_id}")
            return True
        else:
            logger.error(f"❌ Telegram API error: {result.get('description', 'Unknown error')}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send Telegram message: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error sending Telegram message: {e}")
        return False

def validate_telegram_chat_id(chat_id: str) -> bool:
    """Validate Telegram chat ID format"""
    if not chat_id:
        return False
    
    # Chat ID can be numeric (positive for users, negative for groups) or string (usernames)
    if chat_id.startswith('@'):
        # Username format
        return len(chat_id) > 1 and chat_id[1:].replace('_', '').isalnum()
    else:
        # Numeric format
        try:
            int(chat_id)
            return True
        except ValueError:
            return False

# CSRF helper functions (disabled for test mode)
def get_csrf_token():
    """Generate a new CSRF token"""
    return "test_token"  # Mock token for test mode

@app.before_request
def inject_csrf_token():
    """Inject CSRF token into all requests"""
    # CSRF protection disabled for test mode
    pass

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

# Database setup will be done after models are defined

# Background task manager
class JobScheduler:
    """Manages scheduled jobs using APScheduler"""
    
    def __init__(self):
        from apscheduler.executors.pool import ThreadPoolExecutor
        from apscheduler.schedulers.background import BackgroundScheduler

        self.scheduler = BackgroundScheduler(
            executors={'default': ThreadPoolExecutor(10)},
            job_defaults={'coalesce': False, 'max_instances': 1}
        )
        self.scheduler.start()
        logger.info("🕐 Job scheduler started")
    
    def schedule_job(self, job_id: int, user_id: int, job_data: dict):
        """Schedule a new job"""
        try:
            from apscheduler.triggers.cron import CronTrigger

            cron_expr = job_data.get('cron_expression', '0 9 * * 1-5')
            trigger = CronTrigger.from_crontab(cron_expr)
            
            self.scheduler.add_job(
                func=self._execute_scheduled_job,
                trigger=trigger,
                id=f"job_{job_id}",
                args=[job_id, user_id, job_data],
                replace_existing=True
            )
            
            # Update next run time in database
            with app.app_context():
                job = ScheduledJob.query.get(job_id)
                if job:
                    job.next_run = self.scheduler.get_job(f"job_{job_id}").next_run_time
                    db.session.commit()
            
            logger.info(f"✅ Job {job_id} scheduled successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to schedule job {job_id}: {e}")
            return False
    
    def _execute_scheduled_job(self, job_id: int, user_id: int, job_data: dict):
        """Execute a scheduled job"""
        try:
            global campaign_manager
            logger.info(f"Executing scheduled job {job_id} for user {user_id}")
            
            # Create campaign data
            campaign_data = {
                'name': job_data.get('name', f'Scheduled Job {job_id}'),
                'message': job_data.get('message', ''),
                'target_groups': job_data.get('target_groups', []),
                'max_groups': job_data.get('max_groups', 10),
                'min_delay': job_data.get('min_delay', 10),
                'max_delay': job_data.get('max_delay', 60)
            }
            
            # Start campaign
            success = campaign_manager.start_campaign(f"scheduled_{job_id}", user_id, campaign_data)
            
            if success:
                logger.info(f"Scheduled job {job_id} executed successfully")
                # Update job statistics
                job = ScheduledJob.query.get(job_id)
                if job:
                    job.last_run = datetime.utcnow()
                    job.run_count += 1
                    db.session.commit()
            else:
                logger.error(f"Failed to execute scheduled job {job_id}")
                # Update job status
                job = ScheduledJob.query.get(job_id)
                if job:
                    job.status = 'error'
                    db.session.commit()
                    
        except Exception as e:
            logger.error(f"Error executing scheduled job {job_id}: {e}")
            # Update job status
            job = ScheduledJob.query.get(job_id)
            if job:
                job.status = 'error'
                db.session.commit()
    
    def pause_job(self, job_id: int):
        """Pause a scheduled job"""
        try:
            self.scheduler.pause_job(f"job_{job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to pause job {job_id}: {e}")
            return False
    
    def resume_job(self, job_id: int):
        """Resume a paused job"""
        try:
            self.scheduler.resume_job(f"job_{job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to resume job {job_id}: {e}")
            return False
    
    def delete_job(self, job_id: int):
        """Delete a scheduled job"""
        try:
            self.scheduler.remove_job(f"job_{job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete job {job_id}: {e}")
            return False
    
    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()
        logger.info("🔌 Job scheduler shutdown")

class CampaignManager:
    """Manages Facebook posting campaigns with real-time updates"""
    
    def __init__(self):
        self.active_campaigns = {}
        self.poster_instances = {}
    
    def start_campaign(self, campaign_id: int, user_id: int, campaign_data: dict):
        """Start a Facebook posting campaign"""
        if not _load_facebook_automation():
            socketio.emit('campaign_error', {
                'campaign_id': campaign_id,
                'error': 'AI Posting not available'
            }, room=f'user_{user_id}')
            return False
        
        try:
            # Get user settings
            user = User.query.get(user_id)
            if not user:
                return False
            
            # Create poster instance with correct parameters
            poster = FacebookGroupPoster(
                headless=campaign_data.get('use_headless', True)
            )
            poster.user_id = user_id
            
            # Set credentials after initialization (decrypt password)
            poster.username = user.facebook_username or ''
            poster.password = decrypt_password(user.facebook_password) if user.facebook_password else ''
            
            # Store instances
            self.poster_instances[campaign_id] = poster
            self.active_campaigns[campaign_id] = {
                'user_id': user_id,
                'status': 'starting',
                'start_time': datetime.utcnow(),
                'total_groups': len(campaign_data.get('target_groups', [])),
                'completed_groups': 0,
                'failed_groups': 0,
                'current_group': None
            }
            
            # Start posting in background thread
            thread = threading.Thread(
                target=self._run_campaign,
                args=(campaign_id, user_id, campaign_data, poster)
            )
            thread.daemon = True
            thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting campaign {campaign_id}: {e}")
            socketio.emit('campaign_error', {
                'campaign_id': campaign_id,
                'error': str(e)
            }, room=f'user_{user_id}')
            return False
    
    def _run_campaign(self, campaign_id: int, user_id: int, campaign_data: dict, poster: FacebookGroupPoster):
        """Run the actual Facebook posting campaign"""
        try:
            # Update status
            self.active_campaigns[campaign_id]['status'] = 'running'
            socketio.emit('campaign_status', {
                'campaign_id': campaign_id,
                'status': 'running',
                'message': 'Campaign started successfully'
            }, room=f'user_{user_id}')
            
            # Login to Facebook
            if not poster.login():
                raise Exception("Failed to login to Facebook")
            
            # Get campaign details
            target_groups = campaign_data.get('target_groups', [])
            message = campaign_data.get('message', '')
            max_groups = min(len(target_groups), campaign_data.get('max_groups', 10))
            
            # Post to each group
            for i, group_url in enumerate(target_groups[:max_groups]):
                if campaign_id not in self.active_campaigns:
                    break  # Campaign was stopped
                
                # Update current group
                self.active_campaigns[campaign_id]['current_group'] = group_url
                socketio.emit('campaign_progress', {
                    'campaign_id': campaign_id,
                    'current_group': group_url,
                    'progress': i + 1,
                    'total': max_groups,
                    'percentage': int(((i + 1) / max_groups) * 100)
                }, room=f'user_{user_id}')
                
                # Post to group
                success = poster.post_to_group(group_url, message)
                
                if success:
                    self.active_campaigns[campaign_id]['completed_groups'] += 1
                    socketio.emit('campaign_success', {
                        'campaign_id': campaign_id,
                        'group_url': group_url,
                        'message': f'Successfully posted to group {i + 1}/{max_groups}'
                    }, room=f'user_{user_id}')
                else:
                    self.active_campaigns[campaign_id]['failed_groups'] += 1
                    socketio.emit('campaign_failure', {
                        'campaign_id': campaign_id,
                        'group_url': group_url,
                        'message': f'Failed to post to group {i + 1}/{max_groups}'
                    }, room=f'user_{user_id}')
                
                # Random delay between posts
                if i < max_groups - 1:
                    delay = random.randint(
                        campaign_data.get('min_delay', 10),
                        campaign_data.get('max_delay', 60)
                    )
                    time.sleep(delay)
            
            # Campaign completed
            self.active_campaigns[campaign_id]['status'] = 'completed'
            socketio.emit('campaign_completed', {
                'campaign_id': campaign_id,
                'completed_groups': self.active_campaigns[campaign_id]['completed_groups'],
                'failed_groups': self.active_campaigns[campaign_id]['failed_groups'],
                'total_groups': self.active_campaigns[campaign_id]['total_groups']
            }, room=f'user_{user_id}')
            
        except Exception as e:
            logger.error(f"Error in campaign {campaign_id}: {e}")
            self.active_campaigns[campaign_id]['status'] = 'error'
            socketio.emit('campaign_error', {
                'campaign_id': campaign_id,
                'error': str(e)
            }, room=f'user_{user_id}')
        
        finally:
            # Cleanup
            if campaign_id in self.poster_instances:
                self.poster_instances[campaign_id].cleanup()
                del self.poster_instances[campaign_id]
    
    def stop_campaign(self, campaign_id: int):
        """Stop a running campaign"""
        if campaign_id in self.active_campaigns:
            self.active_campaigns[campaign_id]['status'] = 'stopped'
            if campaign_id in self.poster_instances:
                self.poster_instances[campaign_id].stop_posting_method()
        
        return True
    
    def get_campaign_status(self, campaign_id: int):
        """Get current status of a campaign"""
        return self.active_campaigns.get(campaign_id, {})

# Define models
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
    reset_token = db.Column(db.String(255), unique=True)
    reset_token_expires = db.Column(db.DateTime)
    
    # Facebook credentials for posting
    facebook_username = db.Column(db.String(255))
    facebook_password = db.Column(db.String(255))  # Should be encrypted in production
    use_headless = db.Column(db.Boolean, default=True)
    
    # Usage tracking fields
    messages_used = db.Column(db.Integer, default=0)
    messages_limit = db.Column(db.Integer, default=100)  # Default FREE plan limit
    
    def set_password(self, password: str) -> None:
        """Set user password with bcrypt hashing"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches the hash"""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def is_admin(self) -> bool:
        """Check if user is admin"""
        return self.role == 'admin'
    
    def get_plan_limits(self) -> Dict[str, Any]:
        """Get current plan limits"""
        plans = {
            'FREE': {'max_messages': 50, 'max_groups': 10},
            'PLUS': {'max_messages': 500, 'max_groups': 100},
            'PREMIUM': {'max_messages': 2000, 'max_groups': 500}
        }
        return plans.get(self.current_plan, plans['FREE'])
    
    def update_plan_limits(self):
        """Update user limits based on current plan"""
        limits = self.get_plan_limits()
        self.messages_limit = limits['max_messages']
        
    def reset_usage(self):
        """Reset user usage counters"""
        self.messages_used = 0
        self.messages_sent_this_month = 0
        self.last_message_reset = datetime.utcnow()
        
    def can_send_message(self) -> bool:
        """Check if user can send another message"""
        return self.messages_used < self.messages_limit
        
    def increment_usage(self, count: int = 1):
        """Increment message usage counter"""
        self.messages_used = min(self.messages_used + count, self.messages_limit)
        self.messages_sent_this_month += count
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get user usage statistics"""
        limits = self.get_plan_limits()
        # Calculate usage in current month from analytics DB
        groups_used_month = 0
        messages_sent_month = self.messages_sent_this_month or 0
        try:
            import sqlite3
            from datetime import datetime
            from bot.analytics_db import analytics_db
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            with sqlite3.connect(analytics_db.db_path) as conn:
                cur = conn.cursor()
                if self.is_admin():
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE posted_at >= ? AND is_legacy = 0', (month_start,))
                    row = cur.fetchone()
                    groups_used_month = (row[0] or 0) if row else 0
                    cur.execute('SELECT COUNT(*) FROM post_analytics WHERE posted_at >= ? AND is_legacy = 0', (month_start,))
                    row2 = cur.fetchone()
                    messages_sent_month = (row2[0] or 0) if row2 else 0
                else:
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE posted_at >= ? AND user_id = ?', (month_start, self.id))
                    row = cur.fetchone()
                    groups_used_month = (row[0] or 0) if row else 0
                    cur.execute('SELECT COUNT(*) FROM post_analytics WHERE posted_at >= ? AND user_id = ?', (month_start, self.id))
                    row2 = cur.fetchone()
                    messages_sent_month = (row2[0] or 0) if row2 else 0
        except Exception as e:
            # If analytics DB not available, keep default 0
            logger.debug(f"groups_used fetch skipped: {e}")

        return {
            'messages_sent': messages_sent_month,
            'messages_limit': limits['max_messages'],
            'messages_remaining': max(0, limits['max_messages'] - messages_sent_month),
            'groups_limit': limits['max_groups'],
            'groups_used': groups_used_month,
            'current_plan': self.current_plan,
            'subscription_status': self.subscription_status
        }
    
    def get_usage_display(self) -> Dict[str, str]:
        """Get usage display strings with used/allowed format"""
        limits = self.get_plan_limits()
        
        # Format messages
        if limits['max_messages'] >= 999999:
            messages_display = f"{self.messages_sent_this_month} / Unlimited"
        else:
            messages_display = f"{self.messages_sent_this_month} / {limits['max_messages']}"
        
        # Format groups (mock data for now)
        groups_used = 0  # This would come from actual usage tracking
        if limits['max_groups'] >= 999999:
            groups_display = f"{groups_used} / Unlimited"
        else:
            groups_display = f"{groups_used} / {limits['max_groups']}"
        
        return {
            'messages': messages_display,
            'groups': groups_display,
            'messages_remaining': max(0, limits['max_messages'] - self.messages_sent_this_month),
            'groups_remaining': max(0, limits['max_groups'] - groups_used),
            'messages_exhausted': self.messages_sent_this_month >= limits['max_messages'],
            'groups_exhausted': groups_used >= limits['max_groups']
        }
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert user to dictionary"""
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': f"{self.first_name} {self.last_name}",
            'email_verified': self.email_verified,
            'role': self.role,
            'is_active': self.is_active,
            'current_plan': self.current_plan,
            'subscription_status': self.subscription_status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'usage_stats': self.get_usage_stats()
        }
    
    def update_last_login(self) -> None:
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
    
    def __repr__(self) -> str:
        return f'<User {self.email}>'

# Helper functions
def validate_email(email):
    """Simple email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Simple password validation - less strict for demo"""
    errors = []
    if len(password) < 6:
        errors.append("Password must be at least 6 characters long")
    if not re.search(r'[A-Za-z]', password):
        errors.append("Password must contain at least one letter")
    if not re.search(r'[0-9]', password):
        errors.append("Password must contain at least one digit")
    return errors

# Modern Login Template
MAIN_PAGE_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIPostX — Login</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap" rel="stylesheet">
    <style>
        *{box-sizing:border-box;margin:0;padding:0}
        body{font-family:'DM Sans',system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;
             background:#060a13;overflow:hidden;-webkit-font-smoothing:antialiased}

        .bg-mesh{position:fixed;inset:0;z-index:0;overflow:hidden}
        .bg-mesh .orb{position:absolute;border-radius:50%;filter:blur(100px);opacity:.35;animation:drift 20s ease-in-out infinite alternate}
        .bg-mesh .orb-1{width:600px;height:600px;background:#6366f1;top:-15%;left:-10%;animation-delay:0s}
        .bg-mesh .orb-2{width:500px;height:500px;background:#a855f7;bottom:-20%;right:-10%;animation-delay:-5s}
        .bg-mesh .orb-3{width:400px;height:400px;background:#06b6d4;top:40%;left:50%;animation-delay:-10s}
        @keyframes drift{0%{transform:translate(0,0) scale(1)}50%{transform:translate(40px,-30px) scale(1.08)}100%{transform:translate(-20px,20px) scale(.95)}}

        .login-wrapper{position:relative;z-index:1;width:100%;max-width:440px;margin:20px}
        .login-card{background:rgba(12,18,32,.75);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
                    border-radius:20px;border:1px solid rgba(99,102,241,.15);padding:44px 38px 38px;
                    box-shadow:0 24px 80px rgba(0,0,0,.4),0 0 60px rgba(99,102,241,.06)}

        .logo{text-align:center;margin-bottom:32px}
        .logo-icon{width:52px;height:52px;background:linear-gradient(135deg,#6366f1,#a855f7);border-radius:14px;
                   display:inline-flex;align-items:center;justify-content:center;font-size:1.4rem;color:#fff;
                   box-shadow:0 8px 24px rgba(99,102,241,.35);margin-bottom:14px}
        .logo h1{font-size:1.7rem;font-weight:700;
                 background:linear-gradient(135deg,#e0e7ff,#c7d2fe);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .logo p{color:rgba(107,122,153,.8);font-size:.85rem;margin-top:4px}

        .tab-btns{display:flex;gap:8px;margin-bottom:28px;background:rgba(255,255,255,.03);border-radius:12px;padding:4px;border:1px solid rgba(255,255,255,.06)}
        .tab-btn{flex:1;padding:10px;border:none;border-radius:9px;background:transparent;color:rgba(255,255,255,.5);
                 font-weight:600;font-size:.85rem;cursor:pointer;transition:all .25s;font-family:inherit}
        .tab-btn.active{background:rgba(99,102,241,.2);color:#818cf8;box-shadow:0 2px 8px rgba(99,102,241,.15)}
        .tab-btn:hover:not(.active){color:rgba(255,255,255,.7)}

        .form-label{color:rgba(255,255,255,.7);font-weight:500;font-size:.82rem;margin-bottom:6px}
        .form-control{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);color:#e8edf5;
                      border-radius:10px;padding:11px 14px;font-size:.875rem;transition:all .2s;font-family:inherit}
        .form-control:focus{background:rgba(255,255,255,.06);border-color:rgba(99,102,241,.5);color:#fff;
                            box-shadow:0 0 0 3px rgba(99,102,241,.12)}
        .form-control::placeholder{color:rgba(255,255,255,.25)}

        .btn-primary{background:linear-gradient(135deg,#6366f1,#8b5cf6);border:none;border-radius:10px;
                     padding:12px;font-weight:600;font-size:.9rem;transition:all .25s;font-family:inherit}
        .btn-primary:hover{background:linear-gradient(135deg,#818cf8,#a78bfa);box-shadow:0 8px 24px rgba(99,102,241,.3);transform:translateY(-1px)}
        .btn-primary:active{transform:translateY(0)}

        .result{margin-top:16px;padding:12px 14px;border-radius:10px;display:none;font-size:.84rem;font-weight:500;
                animation:slideUp .3s ease}
        .result.success{background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.25);color:#34d399}
        .result.error{background:rgba(244,63,94,.12);border:1px solid rgba(244,63,94,.25);color:#fb7185}
        @keyframes slideUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

        .form-text{color:rgba(107,122,153,.6)!important;font-size:.75rem}
        .alert-info{background:rgba(6,182,212,.1);border:1px solid rgba(6,182,212,.2);color:#22d3ee;border-radius:10px;font-size:.84rem}
        .spinner-border-sm{width:14px;height:14px;border-width:2px}

        @media(max-width:480px){.login-card{padding:32px 24px 28px}.login-wrapper{margin:12px}}
    </style>
</head>
<body>
    <div class="bg-mesh">
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
    </div>

    <div class="login-wrapper">
        <div class="login-card">
            <div id="autoLoginMessage" style="display:none"></div>

            <div class="logo">
                <div class="logo-icon"><i class="bi bi-lightning-charge-fill"></i></div>
                <h1>AIPostX</h1>
                <p>AI-Powered Social Media Automation</p>
            </div>

            <div class="tab-btns">
                <button type="button" class="tab-btn active" id="showLoginForm">
                    <i class="bi bi-box-arrow-in-right me-1"></i>Login
                </button>
                <button type="button" class="tab-btn" id="showRegisterForm">
                    <i class="bi bi-person-plus me-1"></i>Register
                </button>
            </div>

            <div id="loginFormContainer">
                <form id="loginForm">
                    <div class="mb-3">
                        <label for="loginEmail" class="form-label">Email address</label>
                        <input type="email" class="form-control" id="loginEmail" placeholder="name@example.com" required>
                    </div>
                    <div class="mb-3">
                        <label for="loginPassword" class="form-label">Password</label>
                        <input type="password" class="form-control" id="loginPassword" placeholder="Password" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="bi bi-box-arrow-in-right me-2"></i>Login
                    </button>
                    <div id="loginResult" class="result"></div>
                </form>
            </div>

            <div id="registerFormContainer" style="display:none">
                <form id="registerForm">
                    <div class="row mb-3 g-2">
                        <div class="col-6">
                            <label for="registerFirstName" class="form-label">First Name</label>
                            <input type="text" class="form-control" id="registerFirstName" placeholder="First Name" required>
                        </div>
                        <div class="col-6">
                            <label for="registerLastName" class="form-label">Last Name</label>
                            <input type="text" class="form-control" id="registerLastName" placeholder="Last Name" required>
                        </div>
                    </div>
                    <div class="mb-3">
                        <label for="registerEmail" class="form-label">Email address</label>
                        <input type="email" class="form-control" id="registerEmail" placeholder="name@example.com" required>
                    </div>
                    <div class="mb-3">
                        <label for="registerPassword" class="form-label">Password</label>
                        <input type="password" class="form-control" id="registerPassword" placeholder="Password" required>
                        <div class="form-text mt-2">
                            <i class="bi bi-info-circle me-1"></i>
                            At least 6 characters, one letter and one number.
                        </div>
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
                    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
                });
                const result = await response.json();
                const resultDiv = document.getElementById('registerResult');
                if (response.ok) {
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = 'Registration successful! Welcome ' + result.user.full_name + '. Redirecting...';
                    localStorage.setItem('access_token', result.access_token);
                    document.cookie = `access_token=${result.access_token}; path=/; max-age=86400; SameSite=Lax`;
                    setTimeout(() => { window.location.replace('/dashboard?token=' + result.access_token); }, 1200);
                } else {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = (result.error || 'Unknown error');
                }
                resultDiv.style.display = 'block';
            } catch (error) {
                const d = document.getElementById('registerResult');
                d.innerHTML = 'Network error: ' + error.message; d.className = 'result error'; d.style.display = 'block';
            }
        });

        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                email: document.getElementById('loginEmail').value.trim(),
                password: document.getElementById('loginPassword').value
            };
            const resultDiv = document.getElementById('loginResult');
            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
                });
                let result = {};
                try { result = await response.json(); } catch (_) { result = {}; }
                if (response.ok && result.access_token) {
                    const name = (result.user && result.user.full_name) ? result.user.full_name : 'User';
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = 'Welcome back, ' + name + '! Redirecting...';
                    resultDiv.style.display = 'block';
                    try { localStorage.setItem('access_token', result.access_token); } catch (_) {}
                    // Cookie may already be set by server (HttpOnly). Browser cookie setter is brittle — never block login on it.
                    try {
                        document.cookie = 'access_token=' + encodeURIComponent(result.access_token) + '; path=/; max-age=86400; samesite=lax';
                    } catch (_) {}
                    setTimeout(() => {
                        window.location.replace('/dashboard?token=' + encodeURIComponent(result.access_token));
                    }, 400);
                } else {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = (result.error || ('Login failed (' + response.status + ')'));
                    resultDiv.style.display = 'block';
                }
            } catch (error) {
                resultDiv.innerHTML = 'Network error: ' + error.message;
                resultDiv.className = 'result error';
                resultDiv.style.display = 'block';
            }
        });

        document.addEventListener('DOMContentLoaded', function() {
            const loginBtn = document.getElementById('showLoginForm');
            const registerBtn = document.getElementById('showRegisterForm');
            const loginForm = document.getElementById('loginFormContainer');
            const registerForm = document.getElementById('registerFormContainer');
            loginBtn.classList.add('active');
            loginBtn.addEventListener('click', function() {
                loginForm.style.display = 'block'; registerForm.style.display = 'none';
                loginBtn.classList.add('active'); registerBtn.classList.remove('active');
            });
            registerBtn.addEventListener('click', function() {
                loginForm.style.display = 'none'; registerForm.style.display = 'block';
                registerBtn.classList.add('active'); loginBtn.classList.remove('active');
            });
        });

        window.addEventListener('load', () => {
            const token = localStorage.getItem('access_token');
            if (token) {
                fetch('/api/auth/me', { headers: { 'Authorization': 'Bearer ' + token } })
                .then(response => {
                    if (response.ok) {
                        const d = document.getElementById('autoLoginMessage');
                        d.style.display = 'block';
                        d.innerHTML = '<div class="alert alert-info"><i class="bi bi-info-circle me-2"></i><strong>Welcome back!</strong> Already logged in. <span class="spinner-border spinner-border-sm ms-2"></span> Redirecting...</div>';
                        document.cookie = `access_token=${token}; path=/; max-age=86400; SameSite=Lax`;
                        setTimeout(() => { window.location.replace('/dashboard?token=' + token); }, 1200);
                    } else {
                        localStorage.removeItem('access_token');
                        document.cookie = 'access_token=; path=/; max-age=0';
                    }
                })
                .catch(() => {
                    localStorage.removeItem('access_token');
                    document.cookie = 'access_token=; path=/; max-age=0';
                });
            }
        });
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def home():
    return render_template_string(MAIN_PAGE_HTML)

# JWT error handlers - DISABLED FOR DEBUGGING
# @app.errorhandler(Exception)
# def handle_jwt_error(error):
#     """Handle JWT errors"""
#     logger.error(f"JWT Error: {error}")
#     print(f"JWT Error: {error}")
#     return redirect(url_for('home'))

@app.route('/test_groups_simple')
def test_groups_simple():
    """Simple test route without JWT"""
    return "Groups page works!"

@app.route('/groups_no_jwt')
def groups_no_jwt():
    """Groups page without JWT for testing"""
    
    class MockPagination:
        def __init__(self):
            self.pages = 1  # Number of pages, not a list
            self.page = 1
            self.per_page = 10
            self.total = 0
            self.has_prev = False
            self.has_next = False
            self.prev_num = None
            self.next_num = None
    
    return render_template('groups.html', 
                         current_user={'first_name': 'Test', 'last_name': 'User'},
                         pagination=MockPagination(),
                         groups=[],
                         total_groups=0)

@app.route('/health')
def health():
    checks = {'database': False, 'runtime_store': False, 'redis': False}
    try:
        User.query.limit(1).all()
        checks['database'] = True
    except Exception as exc:
        logger.warning("Primary database readiness check failed: %s", exc)
    try:
        with runtime_store.connect() as conn:
            conn.execute('SELECT 1').fetchone()
        checks['runtime_store'] = True
    except Exception as exc:
        logger.warning("Runtime database readiness check failed: %s", exc)
    try:
        redis_conn.ping()
        checks['redis'] = True
    except Exception as exc:
        logger.info("Redis unavailable for health check: %s", exc)
    status_code = 200 if checks['database'] and checks['runtime_store'] else 503
    return jsonify({
        'status': 'healthy' if status_code == 200 else 'degraded',
        'checks': checks,
        'rq_enabled': task_dispatcher.use_rq,
        'version': '2.0',
    }), status_code

@app.route('/test_auth')
def test_auth():
    """Test authentication status (for debugging)"""
    if not app.debug:
        return jsonify({'error': 'Not found'}), 404
    try:
        # Check if user is authenticated
        token = request.headers.get('Authorization') or request.cookies.get('access_token')
        
        if not token:
            return jsonify({
                'authenticated': False,
                'message': 'No token found',
                'cookies': dict(request.cookies),
                'headers': dict(request.headers)
            }), 200
        
        # Clean token
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
        
        # Verify token
        try:
            from flask_jwt_extended import decode_token
            decoded = decode_token(token)
            user_id = decoded['sub']
            
            user = User.query.get(user_id)
            
            return jsonify({
                'authenticated': True,
                'user_id': user_id,
                'user': user.to_dict() if user else None,
                'token_valid': True
            }), 200
            
        except Exception as token_error:
            return jsonify({
                'authenticated': False,
                'message': 'Invalid token',
                'error': str(token_error)
            }), 200
            
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/analytics')
@jwt_required()
def analytics():
    """Analytics page - shows performance metrics"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)

        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)

        from bot.analytics_db import analytics_db
        from app.core.config import AppConfig

        dashboard = analytics_db.get_dashboard_data(int(user_id))
        top_groups = dashboard.get('top_groups', [])
        recent_posts = dashboard.get('recent_posts', [])
        recommended_groups = [g for g in top_groups if (g.get('recommendation_score') or 0) >= 0.8]
        avoid_groups = [g for g in top_groups if (g.get('post_success_rate') or 0) * 100 < 50]
        worker_mode = 'rq' if AppConfig.USE_RQ_WORKERS else 'in-process'

        return render_template(
            'analytics.html',
            total_posts=dashboard.get('total_posts', 0),
            scraped_posts=dashboard.get('scraped_posts', 0),
            avg_engagement_rate=dashboard.get('avg_engagement_rate', 0),
            active_groups=dashboard.get('active_groups', 0),
            success_rate=dashboard.get('success_rate', 0),
            pending_checks=dashboard.get('pending_checks', 0),
            completed_checks=dashboard.get('completed_checks', 0),
            failed_checks=dashboard.get('failed_checks', 0),
            top_groups=top_groups,
            performance_dates=dashboard.get('performance_dates', []),
            performance_data=dashboard.get('performance_data', []),
            engagement_breakdown=dashboard.get('engagement_breakdown', [0, 0, 0]),
            recent_posts=recent_posts,
            recommended_groups=recommended_groups,
            avoid_groups=avoid_groups,
            worker_mode=worker_mode,
            current_user=current_user,
        )

    except Exception as e:
        logger.error(f"Analytics page error: {e}")
        return render_template(
            'analytics.html',
            error_message=f"Error loading analytics: {str(e)}",
            total_posts=0,
            scraped_posts=0,
            avg_engagement_rate=0,
            active_groups=0,
            success_rate=0,
            pending_checks=0,
            completed_checks=0,
            failed_checks=0,
            top_groups=[],
            recommended_groups=[],
            avoid_groups=[],
            performance_dates=['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            performance_data=[0, 0, 0, 0, 0, 0, 0],
            engagement_breakdown=[1, 1, 1],
            recent_posts=[],
            worker_mode='in-process',
        )

@app.route('/dashboard')
@jwt_required()
def dashboard():
    """Dashboard page"""
    try:
        user_id = get_jwt_identity()
        print(f"Dashboard: Got user_id: {user_id}")
        
        current_user = User.query.get(user_id)
        print(f"Dashboard: Got user: {current_user}")
        
        if not current_user:
            print("Dashboard: User not found")
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)
        
        # Get dashboard data (safe without Campaign model)
        try:
            campaigns = Campaign.query.filter_by(user_id=user_id).all()
            total_campaigns = len(campaigns)
            active_campaigns = len([c for c in campaigns if c.status == 'running'])
        except Exception as campaign_error:
            print(f"Dashboard: Campaign error: {campaign_error}")
            # Use mock data if Campaign model not available
            campaigns = []
            total_campaigns = 0
            active_campaigns = 0
        
        # Get Telegram status
        telegram_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        telegram_connected = telegram_settings and telegram_settings.is_active
        
        # Derive real totals for groups and messages
        total_groups = 0
        try:
            # 1) Try fetched groups file (per user)
            groups_full = get_fetched_groups(user_id)
            total_groups = len(groups_full or [])
        except Exception:
            total_groups = 0

        # Analytics-based aggregates (per user)
        posts_total = 0
        groups_posted_unique = 0
        try:
            # 2) If analytics has more groups, use unique count and totals
            import sqlite3
            from bot.analytics_db import analytics_db
            with sqlite3.connect(analytics_db.db_path) as conn:
                cur = conn.cursor()
                if current_user.is_admin():
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE is_legacy = 0')
                else:
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE user_id = ? AND is_legacy = 0', (user_id,))
                row = cur.fetchone()
                analytics_groups = (row[0] or 0) if row else 0
                total_groups = max(total_groups, analytics_groups)

                if current_user.is_admin():
                    cur.execute('SELECT COUNT(*) FROM post_analytics WHERE is_legacy = 0')
                    posts_total = (cur.fetchone()[0] or 0)
                else:
                    cur.execute('SELECT COUNT(*) FROM post_analytics WHERE user_id = ? AND is_legacy = 0', (user_id,))
                    posts_total = (cur.fetchone()[0] or 0)

                if current_user.is_admin():
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE is_legacy = 0')
                    groups_posted_unique = (cur.fetchone()[0] or 0)
                else:
                    cur.execute('SELECT COUNT(DISTINCT group_id) FROM post_analytics WHERE user_id = ? AND is_legacy = 0', (user_id,))
                    groups_posted_unique = (cur.fetchone()[0] or 0)
        except Exception:
            pass

        # Create stats object for template
        stats = {
            'total_campaigns': total_campaigns,
            'active_campaigns': active_campaigns,
            'total_groups': total_groups,
            'messages_sent': current_user.messages_sent_this_month,
            'posts_total': posts_total,
            'groups_posted_unique': groups_posted_unique,
            'success_rate': '95%',  # simple placeholder, analytics page shows real
            'telegram_connected': telegram_connected
        }
        
        print(f"Dashboard: Rendering template...")
        return render_template('dashboard.html', 
                             current_user=current_user,
                             total_campaigns=total_campaigns,
                             active_campaigns=active_campaigns,
                             stats=stats,
                             dashboard_stats=stats)
    except Exception as e:
        print(f"Dashboard error: {e}")
        logger.error(f"Dashboard error: {e}")
        # Instead of redirect, return error for debugging
        return jsonify({'error': f'Dashboard error: {str(e)}'}), 500

@app.route('/group-search')
@jwt_required()
def group_search_page():
    """Dedicated page for fetching/searching Facebook groups."""
    try:
        user_id = int(get_jwt_identity())
        current_user = User.query.get(user_id)
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)

        groups_full = get_fetched_groups(user_id) or []
        try:
            from bot.language_classifier import LanguageClassifier
            groups_full = LanguageClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass
        try:
            from bot.geo_classifier import GeoClassifier
            groups_full = GeoClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass

        latest_fetch_task = runtime_store.get_latest_task(user_id, 'fetch')
        has_saved_credentials = bool(current_user.facebook_username and current_user.facebook_password)

        return render_template(
            'group_search.html',
            current_user=current_user,
            total_groups=len(groups_full),
            preview_groups=groups_full[:50],
            last_fetched_at=_groups_file_mtime(user_id),
            has_saved_credentials=has_saved_credentials,
            saved_username=current_user.facebook_username or '',
            latest_fetch_task=latest_fetch_task,
        )
    except Exception as e:
        logger.error(f"Group search page error: {e}")
        return render_template(
            'group_search.html',
            current_user=None,
            total_groups=0,
            preview_groups=[],
            last_fetched_at=None,
            has_saved_credentials=False,
            saved_username='',
            latest_fetch_task=None,
            error_message=str(e),
        )

@app.route('/groups')
@jwt_required()
def groups_page():
    """Groups page"""
    try:
        user_id = get_jwt_identity()
        print(f"Groups page - user_id: {user_id}")
        logger.info(f"Groups page - user_id: {user_id}")
        
        current_user = User.query.get(user_id)
        print(f"Groups page - current_user: {current_user}")
        logger.info(f"Groups page - current_user: {current_user}")
        
        if not current_user:
            print("Groups page - User not found")
            logger.error("Groups page - User not found")
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)
        
        # Load groups from fetcher output (per user)
        try:
            groups_full = get_fetched_groups(user_id)
        except Exception:
            groups_full = []
        workspace_map = runtime_store.get_group_workspace_map(int(user_id))
        saved_filters = runtime_store.list_filters(int(user_id))
        
        # Classify languages
        try:
            from bot.language_classifier import LanguageClassifier
            groups_full = LanguageClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass
        try:
            from bot.geo_classifier import GeoClassifier
            groups_full = GeoClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass
        
        # Query params
        from flask import request
        search = request.args.get('search', '').strip()
        per_page = int(request.args.get('per_page', 12))
        page = int(request.args.get('page', 1))
        selected_languages = request.args.getlist('languages')
        selected_countries = request.args.getlist('countries')
        segment = request.args.get('segment', '').strip().lower()

        for g in groups_full:
            meta = workspace_map.get(g.get('url', '')) or {}
            g['workspace'] = meta
            g['is_blacklisted'] = bool(meta.get('is_blacklisted'))
            g['is_whitelisted'] = bool(meta.get('is_whitelisted'))
            g['last_posted_at'] = meta.get('last_posted_at')
            g['last_post_status'] = meta.get('last_post_status')
            g['last_campaign_name'] = meta.get('last_campaign_name')
        
        # Filter by search
        if search:
            groups_filtered = [g for g in groups_full if search.lower() in (g.get('name','').lower())]
        else:
            groups_filtered = groups_full
        
        # Filter by languages
        if selected_languages:
            groups_filtered = [g for g in groups_filtered if g.get('language_tag','unknown') in selected_languages]
        if selected_countries:
            groups_filtered = [g for g in groups_filtered if g.get('country_tag','unknown') in selected_countries]

        if segment == 'failed':
            groups_filtered = [g for g in groups_filtered if g.get('last_post_status') == 'failed']
        elif segment == 'recently_posted':
            groups_filtered = [g for g in groups_filtered if g.get('last_posted_at')]
        elif segment == 'blacklist':
            groups_filtered = [g for g in groups_filtered if g.get('is_blacklisted')]
        elif segment == 'whitelist':
            groups_filtered = [g for g in groups_filtered if g.get('is_whitelisted')]
        elif segment == 'new':
            groups_filtered = [g for g in groups_filtered if not g.get('last_posted_at')]
        elif segment == 'german':
            groups_filtered = [g for g in groups_filtered if (g.get('language_tag') or '').lower() == 'german']
        
        total = len(groups_filtered)
        start = (page - 1) * per_page
        end = start + per_page
        groups_page_items = groups_filtered[start:end]
        
        # Build language statistics
        try:
            from bot.language_classifier import LanguageClassifier as _LC
            language_stats = {}
            for g in groups_full:
                lang = g.get('language_tag','unknown')
                language_stats[lang] = language_stats.get(lang, 0) + 1
            language_classifier = _LC
        except Exception:
            language_stats = {}
            language_classifier = None
        try:
            country_stats = {}
            for g in groups_full:
                country = g.get('country_tag', 'unknown')
                country_stats[country] = country_stats.get(country, 0) + 1
        except Exception:
            country_stats = {}
        
        class MockPagination:
            def __init__(self, total, page, per_page):
                self.total = total
                self.page = page
                self.per_page = per_page
                self.pages = max(1, (total + per_page - 1) // per_page)
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        pagination = MockPagination(total, page, per_page)
        
        return render_template('groups.html', 
                             current_user=current_user,
                             pagination=pagination,
                             groups=groups_page_items,
                             search=search,
                             segment=segment,
                             selected_languages=selected_languages,
                             selected_countries=selected_countries,
                             language_stats=language_stats,
                             language_classifier=language_classifier,
                             country_stats=country_stats,
                             saved_filters=saved_filters)
    except Exception as e:
        logger.error(f"Groups page error: {e}")
        return redirect(url_for('home'))

@app.route('/poster')
@jwt_required()
def poster_page():
    """Poster page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        _ensure_release_runtime_user_state(current_user)
        
        # Load groups for selection on the poster page (per user)
        try:
            groups_full = get_fetched_groups(user_id)
        except Exception:
            groups_full = []
        
        # Add language tags for filters
        try:
            from bot.language_classifier import LanguageClassifier
            groups_full = LanguageClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass
        try:
            from bot.geo_classifier import GeoClassifier
            groups_full = GeoClassifier.classify_groups_batch(groups_full)
        except Exception:
            pass

        language_stats = {}
        country_stats = {}
        for group in groups_full:
            lang = group.get('language_tag', 'unknown') or 'unknown'
            language_stats[lang] = language_stats.get(lang, 0) + 1
            country = group.get('country_tag', 'unknown') or 'unknown'
            country_stats[country] = country_stats.get(country, 0) + 1

        return render_template(
            'poster.html',
            current_user=current_user,
            groups=groups_full,
            language_stats=language_stats,
            country_stats=country_stats
        )
    except Exception as e:
        logger.error(f"Poster page error: {e}")
        return redirect(url_for('home'))

@app.route('/scheduler')
@jwt_required()
def scheduler_page():
    """Scheduler page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get scheduled jobs for the user
        try:
            scheduled_jobs = ScheduledJob.query.filter_by(user_id=user_id).all()
        except Exception as job_error:
            logger.error(f"Error fetching scheduled jobs: {job_error}")
            scheduled_jobs = []
        
        return render_template('scheduler.html', 
                             current_user=current_user,
                             scheduled_jobs=scheduled_jobs)
    except Exception as e:
        logger.error(f"Scheduler page error: {e}")
        return redirect(url_for('home'))

@app.route('/templates')
@jwt_required()
def template_manager():
    """Template manager page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        return render_template('template_manager.html', current_user=current_user)
    except Exception as e:
        logger.error(f"Template manager error: {e}")
        return redirect(url_for('home'))

@app.route('/telegram')
@jwt_required()
def telegram_page():
    """Telegram bot configuration page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        return render_template('telegram.html', current_user=current_user)
        
    except Exception as e:
        logger.error(f"Telegram page error: {e}")
        return redirect(url_for('dashboard'))

@app.route('/guide')
@jwt_required()
def guide_page():
    """How It Works guide page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        return render_template('guide.html', current_user=current_user)
        
    except Exception as e:
        logger.error(f"Guide page error: {e}")
        return redirect(url_for('dashboard'))

@app.route('/plans')
@jwt_required()
def plans_page():
    """Plans page"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Plans data as dictionary (expected by template)
        plans = {
            'FREE': {
                'name': 'FREE',
                'price': '$0',
                'price_period': 'forever',
                'limits': 'Perfect for testing',
                'color': 'secondary',
                'is_current': current_user.current_plan == 'FREE',
                'button_text': 'Current Plan' if current_user.current_plan == 'FREE' else 'Downgrade',
                'features': [
                    '✅ Up to 5 groups per campaign',
                    '✅ Basic analytics',
                    '✅ Standard support',
                    '❌ Manual posting only'
                ]
            },
            'PLUS': {
                'name': 'PLUS',
                'price': '$29',
                'price_period': 'per month',
                'limits': 'For growing businesses',
                'color': 'primary',
                'is_current': current_user.current_plan == 'PLUS',
                'button_text': 'Current Plan' if current_user.current_plan == 'PLUS' else 'Upgrade to Plus',
                'features': [
                    '✅ Up to 50 groups per campaign',
                    '✅ Advanced analytics',
                    '✅ Priority support',
                    '✅ Scheduled posting',
                    '✅ Custom templates'
                ]
            },
            'PREMIUM': {
                'name': 'PREMIUM',
                'price': '$99',
                'price_period': 'per month',
                'limits': 'For power users',
                'color': 'success',
                'is_current': current_user.current_plan == 'PREMIUM',
                'button_text': 'Current Plan' if current_user.current_plan == 'PREMIUM' else 'Upgrade to Premium',
                'features': [
                    '✅ Unlimited groups',
                    '✅ Full analytics suite',
                    '✅ VIP support',
                    '✅ Advanced automation',
                    '✅ API access',
                    '✅ White-label options'
                ]
            }
        }
        
        return render_template('plans.html', 
                             current_user=current_user,
                             plans=plans)
    except Exception as e:
        logger.error(f"Plans page error: {e}")
        return redirect(url_for('home'))

# Admin Panel Route
@app.route('/admin')
@jwt_required()
@admin_required
def admin_panel():
    """Admin panel - requires admin role"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if user is admin
        if not current_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        return render_template('admin.html', current_user=current_user)
    except Exception as e:
        logger.error(f"Admin panel error: {e}")
        return redirect(url_for('home'))

# Admin API Routes (for AJAX calls from admin panel)
@app.route('/api/v1/admin/users', methods=['GET'])
@jwt_required()
def admin_get_users():
    """Get all users for admin panel"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user or not current_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        search = request.args.get('search', '').strip()
        plan_filter = request.args.get('plan', '').strip().upper()
        status_filter = request.args.get('status', '').strip()
        
        # Build query
        query = User.query
        
        # Apply filters
        if search:
            query = query.filter(
                User.email.ilike(f'%{search}%') |
                User.first_name.ilike(f'%{search}%') |
                User.last_name.ilike(f'%{search}%')
            )
        
        if plan_filter in ['FREE', 'PLUS', 'PREMIUM']:
            query = query.filter(User.current_plan == plan_filter)
        
        if status_filter == 'active':
            query = query.filter(User.is_active == True)
        elif status_filter == 'inactive':
            query = query.filter(User.is_active == False)
        
        # Order and paginate
        query = query.order_by(User.created_at.desc())
        
        # Simple pagination for SQLite
        total = query.count()
        users = query.offset((page - 1) * per_page).limit(per_page).all()
        
        user_list = []
        for user in users:
            user_dict = user.to_dict()
            user_dict['usage_stats'] = user.get_usage_stats()
            user_dict['campaigns_count'] = Campaign.query.filter_by(user_id=user.id).count()
            
            # Add Telegram settings info
            telegram_settings = TelegramSettings.query.filter_by(user_id=user.id).first()
            user_dict['telegram_chat_id'] = telegram_settings.chat_id if telegram_settings else None
            user_dict['telegram_connected'] = telegram_settings is not None and telegram_settings.is_active
            
            user_list.append(user_dict)
        
        return jsonify({
            'users': user_list,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': page * per_page < total,
                'has_prev': page > 1
            },
            'filters': {
                'search': search,
                'plan': plan_filter,
                'status': status_filter
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Admin get users error: {e}")
        return jsonify({'error': 'Failed to retrieve users'}), 500

@app.route('/api/v1/admin/analytics/overview', methods=['GET'])
@jwt_required()
def admin_analytics_overview():
    """Get platform analytics overview"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user or not current_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        # User statistics
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        
        # Plan distribution
        free_users = User.query.filter_by(current_plan='FREE').count()
        plus_users = User.query.filter_by(current_plan='PLUS').count()
        premium_users = User.query.filter_by(current_plan='PREMIUM').count()
        
        # Campaign statistics
        total_campaigns = Campaign.query.count()
        active_campaigns = Campaign.query.filter_by(status='running').count()
        completed_campaigns = Campaign.query.filter_by(status='completed').count()
        failed_campaigns = Campaign.query.filter_by(status='failed').count()
        
        # Usage statistics
        total_messages = db.session.query(db.func.sum(User.messages_sent_this_month)).scalar() or 0
        
        return jsonify({
            'users': {
                'total': total_users,
                'active': active_users,
                'new_this_month': 0,  # Would need date filtering
                'inactive': total_users - active_users
            },
            'plans': {
                'distribution': {
                    'FREE': free_users,
                    'PLUS': plus_users,
                    'PREMIUM': premium_users
                }
            },
            'campaigns': {
                'total': total_campaigns,
                'active': active_campaigns,
                'completed': completed_campaigns,
                'failed': failed_campaigns
            },
            'usage': {
                'total_messages': total_messages,
                'total_groups': 0,  # Would need groups table
                'avg_messages_per_user': round(total_messages / max(active_users, 1), 2)
            },
            'revenue': {
                'total': 0.0,  # Would need payment tracking
                'transactions': 0
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Admin analytics error: {e}")
        return jsonify({'error': 'Failed to retrieve analytics'}), 500

# Admin User Management API Endpoints
@app.route('/api/admin/users/<int:user_id>/plan', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("100 per 15 minutes")  # Prevent abuse
def admin_update_user_plan(user_id):
    """Update user's plan (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
            
        data = request.get_json()
        new_plan = data.get('plan', '').upper()
        
        # Validate plan
        valid_plans = ['FREE', 'PLUS', 'PREMIUM']
        if new_plan not in valid_plans:
            return jsonify({
                'error': 'Invalid plan type',
                'valid_plans': valid_plans
            }), 400
            
        # Get target user
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
            
        # Store old plan for audit
        old_plan = target_user.current_plan
        
        # Update plan
        target_user.current_plan = new_plan
        target_user.update_plan_limits()
        target_user.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log audit action
        AuditLog.log_action(
            admin_id=current_user_id,
            user_id=user_id,
            action='plan_changed',
            old_value=old_plan,
            new_value=new_plan,
            request_obj=request
        )
        
        # Broadcast to user via WebSocket
        broadcast_to_user(user_id, 'plan_changed', {
            'user_id': user_id,
            'old_plan': old_plan,
            'new_plan': new_plan,
            'new_limits': target_user.get_plan_limits(),
            'timestamp': datetime.utcnow().isoformat()
        })
        
        logger.info(f"Admin {current_user_id} changed user {user_id} plan from {old_plan} to {new_plan}")
        
        return jsonify({
            'message': 'Plan updated successfully',
            'user': target_user.to_dict(),
            'old_plan': old_plan,
            'new_plan': new_plan
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin plan update error: {e}")
        return jsonify({'error': 'Failed to update user plan'}), 500

@app.route('/api/admin/users/<int:user_id>/reset_usage', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("50 per 15 minutes")  # Prevent abuse
def admin_reset_user_usage(user_id):
    """Reset user's usage counters (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
            
        # Get target user
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
            
        # Store old usage for audit
        old_usage = target_user.messages_used
        
        # Reset usage
        target_user.reset_usage()
        target_user.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Log audit action
        AuditLog.log_action(
            admin_id=current_user_id,
            user_id=user_id,
            action='usage_reset',
            old_value=str(old_usage),
            new_value='0',
            request_obj=request
        )
        
        # Broadcast to user via WebSocket
        broadcast_to_user(user_id, 'usage_reset', {
            'user_id': user_id,
            'old_usage': old_usage,
            'new_usage': 0,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        logger.info(f"Admin {current_user_id} reset usage for user {user_id} (was {old_usage})")
        
        return jsonify({
            'message': 'Usage reset successfully',
            'user': target_user.to_dict(),
            'old_usage': old_usage,
            'new_usage': 0
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Admin usage reset error: {e}")
        return jsonify({'error': 'Failed to reset user usage'}), 500

@app.route('/api/admin/users/<int:user_id>/details', methods=['GET'])
@jwt_required()
@admin_required
def admin_get_user_details(user_id):
    """Get detailed user information (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
            
        # Get target user
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
            
        # Get user's telegram settings
        telegram_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        
        # Get recent audit logs for this user
        recent_audits = AuditLog.query.filter_by(user_id=user_id)\
            .order_by(AuditLog.timestamp.desc())\
            .limit(10).all()
            
        # Get user's campaign count
        campaign_count = Campaign.query.filter_by(user_id=user_id).count()
        
        return jsonify({
            'user': target_user.to_dict(include_sensitive=False),
            'telegram_settings': telegram_settings.to_dict() if telegram_settings else None,
            'recent_audits': [audit.to_dict() for audit in recent_audits],
            'campaign_count': campaign_count,
            'usage_stats': target_user.get_usage_stats()
        }), 200
        
    except Exception as e:
        logger.error(f"Admin user details error: {e}")
        return jsonify({'error': 'Failed to get user details'}), 500

@app.route('/api/admin/audit_logs', methods=['GET'])
@jwt_required()
@admin_required
def admin_get_audit_logs():
    """Get audit logs (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 50, type=int), 100)  # Max 100 items
        
        # Get audit logs with pagination
        audit_logs = AuditLog.query\
            .order_by(AuditLog.timestamp.desc())\
            .paginate(page=page, per_page=limit, error_out=False)
        
        return jsonify({
            'audit_logs': [log.to_dict() for log in audit_logs.items],
            'pagination': {
                'page': page,
                'pages': audit_logs.pages,
                'per_page': limit,
                'total': audit_logs.total,
                'has_next': audit_logs.has_next,
                'has_prev': audit_logs.has_prev
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Admin audit logs error: {e}")
        return jsonify({'error': 'Failed to get audit logs'}), 500

@app.route('/api/admin/users/<int:user_id>/ping-telegram', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("30 per 15 minutes")  # Rate limit for Telegram pings
def admin_ping_telegram(user_id):
    """Send test Telegram message to user (admin only)"""
    try:
        current_user_id = get_jwt_identity()
        admin_user = User.query.get(current_user_id)
        
        if not admin_user or not admin_user.is_admin():
            return jsonify({'error': 'Admin access required'}), 403
            
        # Get target user
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get Telegram settings
        telegram_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        if not telegram_settings:
            return jsonify({
                'success': False,
                'error': 'User has no Telegram settings configured'
            }), 400
        
        # Send admin ping message
        admin_message = (
            f"🔔 <b>Admin Ping Test</b>\n\n"
            f"Hello {target_user.first_name}!\n\n"
            f"This is a test message sent by admin: {admin_user.first_name} {admin_user.last_name}\n\n"
            f"Your Telegram notifications are working correctly.\n\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            f"📱 AIPostX Admin Panel"
        )
        
        success = send_telegram_message(telegram_settings.chat_id, admin_message)
        
        if success:
            # Log the ping action
            AuditLog.log_action(
                admin_id=current_user_id,
                user_id=user_id,
                action='telegram_ping',
                new_value=f'Admin ping sent to {telegram_settings.chat_id}',
                request_obj=request
            )
            
            # Update test status
            telegram_settings.last_test_sent = datetime.utcnow()
            telegram_settings.test_successful = True
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Test message sent to {target_user.first_name} {target_user.last_name}'
            }), 200
        else:
            telegram_settings.test_successful = False
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': 'Failed to send Telegram message. Check chat ID.'
            }), 400
            
    except Exception as e:
        logger.error(f"Admin ping Telegram error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to send ping message'
        }), 500

@app.route('/api/auth/register', methods=['POST'])
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

@app.route('/api/auth/login', methods=['POST'])
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

@app.route('/api/auth/me', methods=['GET'])
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

@app.route('/api/auth/logout', methods=['POST'])
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

# Campaign model for simple implementation
class Campaign(db.Model):
    """Simple Campaign model for testing"""
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
    
    def to_dict(self):
        import json
        return {
            'id': self.id,
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
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class ScheduledJob(db.Model):
    """Model for scheduled jobs"""
    __tablename__ = 'scheduled_jobs'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    cron_expression = db.Column(db.String(100), nullable=False)  # e.g., "0 9 * * 1-5"
    campaign_data = db.Column(db.Text, nullable=False)  # JSON string with campaign parameters
    status = db.Column(db.String(20), default='active')  # active, paused, completed, error
    next_run = db.Column(db.DateTime)
    last_run = db.Column(db.DateTime)
    run_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'cron_expression': self.cron_expression,
            'campaign_data': json.loads(self.campaign_data) if self.campaign_data else {},
            'status': self.status,
            'next_run': self.next_run.isoformat() if self.next_run else None,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'run_count': self.run_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
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
        return {
            'id': self.id,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'is_active': self.is_active,
            'last_test_sent': self.last_test_sent.isoformat() if self.last_test_sent else None,
            'test_successful': self.test_successful,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class AuditLog(db.Model):
    """Model for audit logging admin actions"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # plan_changed, usage_reset, etc.
    old_value = db.Column(db.String(255))  # Previous value
    new_value = db.Column(db.String(255))  # New value
    ip_address = db.Column(db.String(45))  # IPv4/IPv6 support
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    admin = db.relationship('User', foreign_keys=[admin_id], backref='admin_actions')
    user = db.relationship('User', foreign_keys=[user_id], backref='audit_entries')
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'admin_id': self.admin_id,
            'user_id': self.user_id,
            'action': self.action,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'admin_email': self.admin.email if self.admin else None,
            'user_email': self.user.email if self.user else None
        }
    
    @staticmethod
    def log_action(admin_id: int, user_id: int, action: str, old_value: str = None, new_value: str = None, request_obj=None):
        """Log an admin action"""
        try:
            audit_entry = AuditLog(
                admin_id=admin_id,
                user_id=user_id,
                action=action,
                old_value=old_value,
                new_value=new_value,
                ip_address=request_obj.remote_addr if request_obj else None,
                user_agent=request_obj.headers.get('User-Agent', '')[:500] if request_obj else None
            )
            db.session.add(audit_entry)
            db.session.commit()
            logger.info(f"Audit log: Admin {admin_id} performed {action} on user {user_id}")
            return audit_entry
        except Exception as e:
            logger.error(f"Failed to log audit action: {e}")
            db.session.rollback()
            return None

@app.route('/api/campaigns', methods=['GET'])
@jwt_required()
def get_campaigns():
    """Get user's campaigns"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        campaigns = Campaign.query.filter_by(user_id=user_id).order_by(Campaign.created_at.desc()).all()
        
        return jsonify({
            'campaigns': [campaign.to_dict() for campaign in campaigns]
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get campaigns',
            'message': str(e),
            'code': 'GET_CAMPAIGNS_ERROR'
        }), 500

@app.route('/api/campaigns', methods=['POST'])
@jwt_required()
@limiter.limit("100 per 15 minutes")  # Moderate limit for campaign creation
def create_campaign():
    """Create a new campaign"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'message', 'group_urls']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'missing_fields': missing_fields,
                'code': 'MISSING_FIELDS'
            }), 400
        
        # Validate group URLs
        group_urls = data.get('group_urls', [])
        if not group_urls or len(group_urls) == 0:
            return jsonify({
                'error': 'At least one group URL is required',
                'code': 'NO_GROUPS'
            }), 400
        
        # Check user limits
        plan_limits = user.get_plan_limits()
        max_allowed_groups = min(data.get('max_groups', 10), plan_limits['max_groups'])
        
        if len(group_urls) > max_allowed_groups:
            return jsonify({
                'error': f'Too many groups. Your plan allows maximum {max_allowed_groups} groups.',
                'code': 'LIMIT_EXCEEDED'
            }), 400
        
        # Check message limit
        if user.messages_sent_this_month >= plan_limits['max_messages']:
            return jsonify({
                'error': f'Monthly message limit reached. Your plan allows {plan_limits["max_messages"]} messages per month.',
                'code': 'MESSAGE_LIMIT_EXCEEDED'
            }), 400
        
        # Create campaign
        import json
        campaign = Campaign(
            user_id=user_id,
            name=data['name'],
            message=data['message'],
            target_groups=json.dumps(group_urls[:max_allowed_groups]),
            max_groups=max_allowed_groups,
            min_delay=data.get('min_delay', 10),
            max_delay=data.get('max_delay', 60),
            total_groups=len(group_urls[:max_allowed_groups])
        )
        
        db.session.add(campaign)
        db.session.commit()
        
        return jsonify({
            'message': 'Campaign created successfully',
            'campaign': campaign.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to create campaign',
            'message': str(e),
            'code': 'CREATE_CAMPAIGN_ERROR'
        }), 500

@app.route('/api/campaigns/<int:campaign_id>/start', methods=['POST'])
@jwt_required()
def start_campaign(campaign_id):
    """Start a Facebook posting campaign"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user_id).first()
        
        if not campaign:
            return jsonify({
                'error': 'Campaign not found',
                'code': 'CAMPAIGN_NOT_FOUND'
            }), 404
        
        if campaign.status != 'draft':
            return jsonify({
                'error': 'Campaign is not in draft status',
                'code': 'INVALID_STATUS'
            }), 400
        
        if not user.facebook_username or not user.facebook_password:
            return jsonify({
                'error': 'Facebook credentials not configured. Please update your settings.',
                'code': 'MISSING_CREDENTIALS'
            }), 400
        
        if not FACEBOOK_POSTER_AVAILABLE:
            return jsonify({
                'error': 'AI Posting is not available. Please check the bot integration.',
                'code': 'FACEBOOK_POSTER_NOT_AVAILABLE'
            }), 500

        task = _start_local_posting_thread(
            user_id=int(user_id),
            username=user.facebook_username,
            password=decrypt_password(user.facebook_password),
            message=campaign.message,
            group_urls=json.loads(campaign.target_groups),
            headless=bool(user.use_headless if user.use_headless is not None else True),
            use_templates=(campaign.message or '').strip().upper() == '[TEMPLATE_MODE]',
            template_mode='sequential',
            max_groups=campaign.max_groups,
            campaign_name=campaign.name,
        )
        campaign.status = 'running'
        campaign.started_at = datetime.utcnow()
        db.session.commit()
        return jsonify({
            'message': 'Campaign started successfully',
            'campaign': campaign.to_dict(),
            'task': task,
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to start campaign',
            'message': str(e),
            'code': 'START_CAMPAIGN_ERROR'
        }), 500


@app.route('/api/campaigns/<int:campaign_id>/stop', methods=['POST'])
@jwt_required()
def stop_campaign(campaign_id):
    """Stop a running Facebook posting campaign"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user_id).first()
        
        if not campaign:
            return jsonify({
                'error': 'Campaign not found',
                'code': 'CAMPAIGN_NOT_FOUND'
            }), 404
        
        if campaign.status != 'running':
            return jsonify({
                'error': 'Campaign is not running',
                'code': 'INVALID_STATUS'
            }), 400
        
        if poster_instance and getattr(poster_instance, 'is_posting', False):
            poster_instance.stop_posting_method()
        
        # Update campaign status
        campaign.status = 'stopped'
        campaign.completed_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'Campaign stopped successfully',
            'campaign': campaign.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to stop campaign',
            'message': str(e),
            'code': 'STOP_CAMPAIGN_ERROR'
        }), 500


@app.route('/api/campaigns/<int:campaign_id>/status', methods=['GET'])
@jwt_required()
def get_campaign_status(campaign_id):
    """Get real-time status of a campaign"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        campaign = Campaign.query.filter_by(id=campaign_id, user_id=user_id).first()
        
        if not campaign:
            return jsonify({
                'error': 'Campaign not found',
                'code': 'CAMPAIGN_NOT_FOUND'
            }), 404
        
        return jsonify({
            'campaign': campaign.to_dict(),
            'live_status': _task_snapshot_from_poster(int(user_id), runtime_store.get_latest_task(int(user_id), 'posting'), poster_instance.get_status() if poster_instance else None)
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get campaign status',
            'message': str(e),
            'code': 'GET_STATUS_ERROR'
        }), 500


@app.route('/api/campaigns/<int:campaign_id>/rerun', methods=['POST'])
@jwt_required()
def rerun_campaign(campaign_id):
    campaign = Campaign.query.filter_by(id=campaign_id, user_id=get_jwt_identity()).first()
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    campaign.status = 'draft'
    db.session.commit()
    return start_campaign(campaign_id)

# Scheduler API endpoints
@app.route('/api/scheduler/jobs', methods=['GET'])
@jwt_required()
def get_scheduled_jobs():
    """Get user's scheduled jobs"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        jobs = ScheduledJob.query.filter_by(user_id=user_id).order_by(ScheduledJob.created_at.desc()).all()
        
        return jsonify({
            'jobs': [job.to_dict() for job in jobs]
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get scheduled jobs',
            'message': str(e),
            'code': 'GET_JOBS_ERROR'
        }), 500

@app.route('/api/scheduler/jobs', methods=['POST'])
@jwt_required()
@limiter.limit("50 per 15 minutes")  # Limit job creation
def create_scheduled_job():
    """Create a new scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'cron_expression', 'campaign_data']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'missing_fields': missing_fields,
                'code': 'MISSING_FIELDS'
            }), 400
        
        # Validate cron expression
        try:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(data['cron_expression'])
        except Exception as e:
            return jsonify({
                'error': 'Invalid cron expression',
                'message': str(e),
                'code': 'INVALID_CRON'
            }), 400
        
        # Create scheduled job
        job = ScheduledJob(
            user_id=user_id,
            name=data['name'],
            cron_expression=data['cron_expression'],
            campaign_data=json.dumps(data['campaign_data']),
            status='active'
        )
        
        db.session.add(job)
        db.session.commit()
        
        # Add job to scheduler
        global job_scheduler
        job_data = {
            'name': job.name,
            'message': data['campaign_data'].get('message', ''),
            'target_groups': data['campaign_data'].get('target_groups', []),
            'max_groups': data['campaign_data'].get('max_groups', 10),
            'min_delay': data['campaign_data'].get('min_delay', 10),
            'max_delay': data['campaign_data'].get('max_delay', 60)
        }
        
        success = job_scheduler.schedule_job(job.id, user_id, job_data)
        
        if not success:
            # Delete the job if scheduling failed
            db.session.delete(job)
            db.session.commit()
            return jsonify({
                'error': 'Failed to schedule job',
                'code': 'SCHEDULE_ERROR'
            }), 500
        
        # Notify via WebSocket
        socketio.emit('job_scheduled', {
            'job_id': job.id,
            'user_id': user_id,
            'name': job.name,
            'message': f'Job "{job.name}" scheduled successfully'
        }, room=f'user_{user_id}')
        
        return jsonify({
            'message': 'Job scheduled successfully',
            'job': job.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to create scheduled job',
            'message': str(e),
            'code': 'CREATE_JOB_ERROR'
        }), 500

@app.route('/api/scheduler/jobs/<int:job_id>', methods=['PUT'])
@jwt_required()
def update_scheduled_job(job_id):
    """Update a scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'code': 'JOB_NOT_FOUND'
            }), 404
        
        data = request.get_json()
        
        # Update job fields
        if 'name' in data:
            job.name = data['name']
        if 'cron_expression' in data:
            # Validate cron expression
            try:
                from apscheduler.triggers.cron import CronTrigger

                CronTrigger.from_crontab(data['cron_expression'])
                job.cron_expression = data['cron_expression']
            except Exception as e:
                return jsonify({
                    'error': 'Invalid cron expression',
                    'message': str(e),
                    'code': 'INVALID_CRON'
                }), 400
        if 'campaign_data' in data:
            job.campaign_data = json.dumps(data['campaign_data'])
        if 'status' in data:
            job.status = data['status']
        
        job.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Update job in scheduler
        global job_scheduler
        job_data = {
            'name': job.name,
            'cron_expression': job.cron_expression,
            'campaign_data': json.loads(job.campaign_data)
        }
        
        job_scheduler.schedule_job(job.id, user_id, job_data)
        
        return jsonify({
            'message': 'Job updated successfully',
            'job': job.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to update job',
            'message': str(e),
            'code': 'UPDATE_JOB_ERROR'
        }), 500

@app.route('/api/scheduler/jobs/<int:job_id>', methods=['DELETE'])
@jwt_required()
def delete_scheduled_job(job_id):
    """Delete a scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'code': 'JOB_NOT_FOUND'
            }), 404
        
        # Remove from scheduler
        global job_scheduler
        job_scheduler.delete_job(job.id)
        
        # Delete from database
        db.session.delete(job)
        db.session.commit()
        
        return jsonify({
            'message': 'Job deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to delete job',
            'message': str(e),
            'code': 'DELETE_JOB_ERROR'
        }), 500

@app.route('/api/scheduler/jobs/<int:job_id>/pause', methods=['POST'])
@jwt_required()
def pause_scheduled_job(job_id):
    """Pause a scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'code': 'JOB_NOT_FOUND'
            }), 404
        
        # Pause in scheduler
        global job_scheduler
        success = job_scheduler.pause_job(job.id)
        
        if success:
            job.status = 'paused'
            job.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'message': 'Job paused successfully',
                'job': job.to_dict()
            }), 200
        else:
            return jsonify({
                'error': 'Failed to pause job',
                'code': 'PAUSE_ERROR'
            }), 500
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to pause job',
            'message': str(e),
            'code': 'PAUSE_JOB_ERROR'
        }), 500

@app.route('/api/scheduler/jobs/<int:job_id>/resume', methods=['POST'])
@jwt_required()
def resume_scheduled_job(job_id):
    """Resume a paused scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'code': 'JOB_NOT_FOUND'
            }), 404
        
        # Resume in scheduler
        global job_scheduler
        success = job_scheduler.resume_job(job.id)
        
        if success:
            job.status = 'active'
            job.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'message': 'Job resumed successfully',
                'job': job.to_dict()
            }), 200
        else:
            return jsonify({
                'error': 'Failed to resume job',
                'code': 'RESUME_ERROR'
            }), 500
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to resume job',
            'message': str(e),
            'code': 'RESUME_JOB_ERROR'
        }), 500

@app.route('/api/user/settings', methods=['GET'])
@jwt_required()
def get_user_settings():
    """Get user settings"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        return jsonify({
            'settings': {
                'facebook_username': user.facebook_username or '',
                'facebook_password_set': bool(user.facebook_password),  # Don't return actual password
                'use_headless': user.use_headless if user.use_headless is not None else True
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get settings',
            'message': str(e),
            'code': 'GET_SETTINGS_ERROR'
        }), 500

@app.route('/api/user/settings', methods=['POST'])
@jwt_required()
def update_user_settings():
    """Update user settings"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        data = request.get_json()
        
        # Update Facebook credentials
        if 'facebook_username' in data:
            user.facebook_username = data['facebook_username']
        
        if 'facebook_password' in data and data['facebook_password']:
            user.facebook_password = encrypt_password(data['facebook_password'])
        
        if 'use_headless' in data:
            user.use_headless = data['use_headless']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Settings updated successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to update settings',
            'message': str(e),
            'code': 'UPDATE_SETTINGS_ERROR'
        }), 500

@app.route('/api/user/plan', methods=['POST'])
@jwt_required()
def update_user_plan():
    """Update user's plan"""
    try:
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        new_plan = data.get('plan', '').upper()
        
        # Validate plan
        valid_plans = ['FREE', 'PLUS', 'PREMIUM']
        if new_plan not in valid_plans:
            return jsonify({
                'error': 'Invalid plan',
                'valid_plans': valid_plans
            }), 400
        
        # Update user's plan
        current_user.current_plan = new_plan
        current_user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': f'Plan updated to {new_plan}',
            'current_plan': new_plan,
            'user': current_user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Plan update error: {e}")
        return jsonify({
            'error': 'Failed to update plan',
            'message': str(e)
        }), 500

# Telegram Bot API endpoints
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
        
        logger.info(f"Telegram settings saved for user {user_id}")
        
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
        test_message = (
            f"🔔 <b>Test Message</b>\n\n"
            f"Hello {user.first_name}! Your Telegram bot is working correctly.\n\n"
            f"You will receive notifications about:\n"
            f"• Campaign completions\n"
            f"• Posting results\n"
            f"• System alerts\n\n"
            f"📱 AIPostX SaaS"
        )
        
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
                'message': 'Failed to send test message. Please check your chat ID.'
            }), 400
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Test Telegram connection error: {e}")
        return jsonify({'error': 'Failed to test Telegram connection'}), 500

@app.route('/api/guide', methods=['GET'])
@jwt_required()
def get_guide_content():
    """Get guide markdown content"""
    try:
        # Read the markdown file
        guide_path = os.path.join(os.path.dirname(__file__), 'docs', 'guide.md')
        
        if not os.path.exists(guide_path):
            return jsonify({
                'success': False,
                'error': 'Guide content not found'
            }), 404
        
        with open(guide_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            'success': True,
            'content': content,
            'last_updated': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Get guide content error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to load guide content'
        }), 500

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    try:
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        join_room(f"user_{user_id}")
        logger.info("Authenticated client connected for user %s", user_id)
    except Exception:
        logger.warning("Rejected unauthenticated Socket.IO connection")
        return False

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('join_user_room')
def handle_join_room(data):
    """Join user-specific room for updates"""
    try:
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        join_room(f"user_{user_id}")
        logger.info("User %s joined own room", user_id)
    except Exception:
        return False

@socketio.on('leave_user_room')
def handle_leave_room(data):
    """Leave user-specific room"""
    try:
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        leave_room(f"user_{user_id}")
        logger.info("User %s left own room", user_id)
    except Exception:
        return False

# Note: JWT authentication is handled by @jwt_required() decorators

# ===============================
# TEMPLATE SYSTEM API ENDPOINTS  
# ===============================

# ===============================
# GROUP FETCHER API (for dashboard)
# ===============================

def _user_groups_path(user_id: int) -> str:
    base_dir = app.config.get('GROUPS_DIR') or os.path.join(os.path.abspath(os.path.dirname(__file__)), 'user_data', 'groups')
    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base_dir, f"autofetched_groups_{user_id}.json")

def _read_groups_from_file(user_id: int = None) -> list:
    try:
        path = None
        if user_id:
            path = _user_groups_path(user_id)
        # Strict per-user: do NOT fall back to global file
        if path and os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                import json
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read groups file: {e}")
    return []

def _save_groups_to_file(groups: list, user_id: int = None) -> None:
    try:
        path = _user_groups_path(user_id) if user_id else app.config.get('FETCHED_GROUPS_FILE')
        with open(path, 'w', encoding='utf-8') as f:
            import json
            json.dump(groups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save groups file: {e}")

def get_fetched_groups(user_id: int = None) -> list:
    return _read_groups_from_file(user_id)

def save_fetched_groups(user_id: int, groups: list) -> None:
    _save_groups_to_file(groups, user_id)

def _groups_file_mtime(user_id: int) -> Optional[str]:
    try:
        path = _user_groups_path(user_id)
        if os.path.exists(path):
            ts = datetime.fromtimestamp(os.path.getmtime(path))
            return ts.strftime('%Y-%m-%d %H:%M')
    except Exception:
        pass
    return None

def _prepare_groups_export_rows(groups: list) -> tuple[list, list]:
    """Normalize group dictionaries for tabular export formats."""
    preferred_columns = ['name', 'url', 'members', 'language_tag', 'privacy', 'category', 'description', 'id']
    discovered_columns = []

    for group in groups:
        if isinstance(group, dict):
            for key in group.keys():
                if key not in discovered_columns:
                    discovered_columns.append(key)

    ordered_columns = [col for col in preferred_columns if col in discovered_columns]
    ordered_columns.extend(col for col in discovered_columns if col not in ordered_columns)

    rows = []
    for group in groups:
        if isinstance(group, dict):
            rows.append({column: group.get(column, '') for column in ordered_columns})
        else:
            rows.append({'value': str(group)})

    if not ordered_columns and rows:
        ordered_columns = list(rows[0].keys())

    return ordered_columns, rows

@app.route('/export/groups/<format>')
@jwt_required()
def export_groups(format):
    """Export fetched groups in JSON, CSV, Excel, or ZIP formats."""
    try:
        user_id = int(get_jwt_identity())
        groups = get_fetched_groups(user_id)
        export_format = (format or 'json').lower()

        if not groups:
            return jsonify({'error': 'No groups available to export'}), 404

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        base_name = f"facebook_groups_{user_id}_{timestamp}"

        if export_format == 'json':
            payload = json.dumps(groups, ensure_ascii=False, indent=2).encode('utf-8')
            return send_file(
                io.BytesIO(payload),
                mimetype='application/json',
                as_attachment=True,
                download_name=f'{base_name}.json'
            )

        columns, rows = _prepare_groups_export_rows(groups)

        def build_csv_bytes() -> bytes:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=columns or ['value'])
            writer.writeheader()
            if rows:
                writer.writerows(rows)
            return output.getvalue().encode('utf-8-sig')

        if export_format == 'csv':
            return send_file(
                io.BytesIO(build_csv_bytes()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'{base_name}.csv'
            )

        if export_format == 'excel':
            try:
                import pandas as pd
            except ImportError:
                return jsonify({'error': 'Excel export is unavailable because pandas is not installed'}), 501

            excel_buffer = io.BytesIO()
            pd.DataFrame(rows or [{'value': ''}], columns=columns or ['value']).to_excel(excel_buffer, index=False)
            excel_buffer.seek(0)
            return send_file(
                excel_buffer,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'{base_name}.xlsx'
            )

        if export_format == 'all':
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(f'{base_name}.json', json.dumps(groups, ensure_ascii=False, indent=2))
                archive.writestr(f'{base_name}.csv', build_csv_bytes())
                try:
                    import pandas as pd
                    excel_buffer = io.BytesIO()
                    pd.DataFrame(rows or [{'value': ''}], columns=columns or ['value']).to_excel(excel_buffer, index=False)
                    archive.writestr(f'{base_name}.xlsx', excel_buffer.getvalue())
                except ImportError:
                    pass
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'{base_name}.zip'
            )

        return jsonify({'error': 'Unsupported export format'}), 400
    except Exception as e:
        logger.error(f"Export groups error: {e}")
        return jsonify({'error': f'Failed to export groups: {str(e)}'}), 500

@app.route('/api/credentials', methods=['GET'])
@jwt_required()
def api_credentials_status():
    """Check whether Facebook credentials are saved for the current user."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        has_saved = bool(user.facebook_username and user.facebook_password)
        return jsonify({
            'has_saved_credentials': has_saved,
            'username': user.facebook_username if has_saved else None,
        }), 200
    except Exception as exc:
        logger.error("credentials status error: %s", exc)
        return jsonify({'error': str(exc)}), 500


@app.route('/api/credentials/load', methods=['POST'])
@jwt_required()
def api_credentials_load():
    """Return saved-credential state without ever exposing a password."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not user.facebook_username or not user.facebook_password:
            return jsonify({'error': 'No saved credentials'}), 404
        return jsonify({
            'username': user.facebook_username,
            'has_saved_credentials': True,
        }), 200
    except Exception as exc:
        logger.error("credentials load error: %s", exc)
        return jsonify({'error': str(exc)}), 500


@app.route('/api/start_fetch', methods=['POST'])
@jwt_required()
def start_fetch():
    """Start fetching Facebook groups using Selenium fetcher"""
    global fetcher_instance
    try:
        data = request.get_json() or {}
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Gate on fetch task only — prepare/post use the same progress_tracker
        active_fetch = runtime_store.get_latest_task(user_id, 'fetch')
        if active_fetch and active_fetch.get('status') in ('queued', 'running', 'waiting_manual', 'paused'):
            return jsonify({'error': 'Fetch task already in progress', 'task': active_fetch}), 400

        username = (data.get('username') or user.facebook_username or '').strip()
        password = (data.get('password') or (decrypt_password(user.facebook_password) if user.facebook_password else '')).strip()
        headless = bool(data.get('headless', False))
        use_session = bool(data.get('use_session', True))
        account_id = data.get('account_id')
        auto_rotate = bool(data.get('auto_rotate', True))

        from app.services.account_orchestrator import AccountOrchestrator
        orch = AccountOrchestrator(runtime_store)
        selected_account = None
        has_saved_accounts = bool(runtime_store.list_accounts(user_id))
        if account_id or auto_rotate or has_saved_accounts:
            selected_account, pick_reason = orch.pick_account(
                user_id,
                preferred_account_id=int(account_id) if account_id else None,
                require_trusted=True,
            )
            if not selected_account and (account_id or has_saved_accounts):
                return jsonify({
                    'error': pick_reason or 'Session not trusted. Prepare account first.',
                    'code': 'SESSION_NOT_TRUSTED',
                    'hint': '/accounts',
                }), 403
            if selected_account:
                account_id = int(selected_account['id'])
                username, password = _account_credentials(selected_account, user)

        if not username or not password:
            return jsonify({
                'error': 'Facebook credentials required — re-save password on /accounts',
                'hint': '/accounts',
            }), 400

        # Persist credentials encrypted (never log)
        user.facebook_username = username
        user.facebook_password = encrypt_password(password)
        db.session.commit()
        _ensure_release_runtime_user_state(user)

        def _runner(task_id: int) -> dict:
            global fetcher_instance
            from app.services.task_control import CooperativeTaskControl, DurableControlMonitor, TaskStopped
            if not _load_facebook_automation():
                raise RuntimeError('Facebook group fetcher is unavailable')
            progress_tracker.reset()
            progress_tracker.start()
            runtime_store.append_task_event(task_id, 'Fetch task started', event_type='system')

            def _fetch_progress(payload: dict):
                control.checkpoint(
                    on_stop=lambda: (
                        setattr(fetcher, 'is_fetching', False),
                        fetcher.cleanup(),
                    ),
                    allow_pause=False,
                )
                progress_tracker.update(**payload)
                if payload.get('status') == 'waiting_manual' and account_id:
                    runtime_store.update_task(task_id, status='waiting_manual')
                    orch.mark_needs_verify(
                        user_id, int(account_id),
                        payload.get('message') or 'Manual verification required',
                    )
                runtime_store.append_task_event(
                    task_id,
                    payload.get('step') or 'fetch-progress',
                    event_type='progress',
                    metadata=payload,
                )
                broadcast_to_user(user_id, 'fetch_progress', payload)

            fetcher = FacebookGroupFetcher(
                username=username,
                password=password,
                headless=headless,
                use_session=use_session,
                user_id=user_id,
                progress_callback=_fetch_progress,
            )
            control = CooperativeTaskControl(runtime_store, task_id, user_id)
            if account_id and selected_account and selected_account.get('profile_dir'):
                fetcher.profile_dir = selected_account['profile_dir']
            fetcher_instance = fetcher
            try:
                control.checkpoint(on_stop=fetcher.cleanup, allow_pause=False)
                with DurableControlMonitor(control, fetcher.cleanup):
                    groups = fetcher.fetch_groups()
                state = runtime_store.get_control_state(task_id, user_id)
                if state and state.get('acknowledged_state') == 'stopping':
                    return {'status': 'cancelled', 'error_message': 'Stopped by user'}
            except TaskStopped:
                return {'status': 'cancelled', 'error_message': 'Stopped by user'}
            if groups is None:
                err = fetcher.error or 'Fetch failed'
                if account_id and getattr(fetcher, 'manual_verification_needed', False):
                    orch.mark_needs_verify(user_id, int(account_id), err, checkpoint=True)
                progress_tracker.update(status='failed', error=err)
                progress_tracker.finish(success=False)
                raise RuntimeError(err)

            if account_id:
                orch.mark_trusted(user_id, int(account_id), profile_dir=fetcher.profile_dir)
            save_fetched_groups(user_id, groups)
            progress_tracker.update(status='completed', total_groups=len(groups), progress=100)
            progress_tracker.finish(success=True)
            runtime_store.append_task_event(task_id, f'Fetched {len(groups)} groups', event_type='result')
            return {'status': 'completed', 'groups_found': len(groups), 'account_id': account_id}

        task = task_dispatcher.start_fetch(
            user_id=user_id,
            title='Fetch Facebook groups',
            payload={'headless': headless, 'use_session': use_session, 'account_id': account_id},
            local_runner=_runner,
        )
        return jsonify({
            'message': 'Fetching started',
            'task': task,
            'task_id': task.get('id'),
            'mode': task.get('queue_mode', 'local_persistent'),
            'account_id': account_id,
        }), 202

    except Exception as e:
        logger.error(f"Start fetch error: {e}")
        return jsonify({'error': str(e) or 'Failed to start fetching'}), 500

@app.route('/api/progress', methods=['GET'])
@jwt_required()
def get_progress():
    user_id = int(get_jwt_identity())
    task_id = request.args.get('task_id', type=int)
    task = runtime_store.get_task_for_user(task_id, user_id) if task_id else None
    if task_id and not task:
        return jsonify({'error': 'Task not found'}), 404
    summary = runtime_store.get_user_task_summary(user_id)
    task = task or summary.get('task')
    progress = {}
    if task:
        progress = next(
            ((event.get('metadata') or {}) for event in reversed(task.get('events') or [])
             if event.get('event_type') == 'progress'),
            {},
        )
    return jsonify({
        'task_id': task.get('id') if task else None,
        'status': task.get('status', 'idle') if task else 'idle',
        'step': progress.get('step', ''),
        'progress': progress.get('progress', 0),
        'total_groups': progress.get('total_groups', 0),
        'current_scroll': progress.get('current_scroll', 0),
        'max_scroll': progress.get('max_scroll', 0),
        'error': progress.get('error') or (task.get('error_message') if task else None),
        'message': progress.get('message', ''),
        'elapsed_time': progress.get('elapsed_time', 0),
        'task': task,
    })

@app.route('/api/groups', methods=['GET'])
@jwt_required()
def get_groups_api():
    try:
        user_id = get_jwt_identity()
        groups = get_fetched_groups(user_id)
        try:
            from bot.language_classifier import LanguageClassifier
            groups = LanguageClassifier.classify_groups_batch(groups)
        except Exception:
            pass
        try:
            from bot.geo_classifier import GeoClassifier
            groups = GeoClassifier.classify_groups_batch(groups)
        except Exception:
            pass
        workspace_map = runtime_store.get_group_workspace_map(int(user_id))
        for group in groups:
            meta = workspace_map.get(group.get('url', '')) or {}
            if meta:
                group['workspace'] = meta
        return jsonify({'groups': groups, 'total': len(groups)})
    except Exception as e:
        logger.error(f"Get groups error: {e}")
        return jsonify({'error': 'Failed to get groups'}), 500


@app.route('/api/groups/workspace', methods=['GET', 'POST'])
@jwt_required()
def api_groups_workspace():
    user_id = int(get_jwt_identity())
    if request.method == 'GET':
        return jsonify({'workspace': list(runtime_store.get_group_workspace_map(user_id).values())})

    data = request.get_json() or {}
    group_url = data.get('group_url')
    if not group_url:
        return jsonify({'error': 'group_url is required'}), 400
    runtime_store.upsert_group_workspace(
        user_id,
        group_url,
        group_name=data.get('group_name'),
        is_blacklisted=bool(data.get('is_blacklisted')),
        is_whitelisted=bool(data.get('is_whitelisted')),
        tags=data.get('tags', []),
        notes=data.get('notes'),
        last_posted_at=data.get('last_posted_at'),
        last_post_status=data.get('last_post_status'),
        last_campaign_name=data.get('last_campaign_name'),
    )
    return jsonify({'message': 'Workspace updated'})


@app.route('/api/groups/filters', methods=['GET', 'POST'])
@jwt_required()
def api_group_filters():
    user_id = int(get_jwt_identity())
    if request.method == 'GET':
        return jsonify({'filters': runtime_store.list_filters(user_id)})

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    config = data.get('config') or {}
    if not name:
        return jsonify({'error': 'Filter name is required'}), 400
    filter_id = runtime_store.save_filter(user_id, name, config, is_default=bool(data.get('is_default')))
    return jsonify({'message': 'Filter saved', 'filter_id': filter_id}), 201


@app.route('/api/accounts', methods=['GET', 'POST'])
@jwt_required()
def api_accounts():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'GET':
        _ensure_release_runtime_user_state(user)
        from app.services.account_orchestrator import AccountOrchestrator
        orch = AccountOrchestrator(runtime_store)
        enriched = orch.list_account_trust(user_id)
        for row in enriched:
            row['credentials_ok'] = _credentials_ok(row, user)
            if not row['credentials_ok']:
                row['trust_reason'] = (row.get('trust_reason') or '') + ' — re-save password'
        prepare_summary = runtime_store.get_user_task_summary(user_id, 'prepare_account')
        prepare_task = prepare_summary.get('task')
        prepare_progress = prepare_summary.get('progress') or {}
        return jsonify({
            'accounts': enriched,
            'session': runtime_store.get_latest_session(user_id),
            'prepare_status': {
                'task_id': prepare_task.get('id') if prepare_task else None,
                'status': prepare_task.get('status', 'idle') if prepare_task else 'idle',
                'step': prepare_progress.get('step', ''),
                'message': prepare_progress.get('message', ''),
                'progress': prepare_progress.get('progress', 0),
                'error': prepare_progress.get('error') or (
                    prepare_task.get('error_message') if prepare_task else None
                ),
            },
        })

    data = request.get_json() or {}
    login_email = (data.get('login_email') or '').strip()
    password = (data.get('password') or '').strip()
    if not login_email:
        return jsonify({'error': 'login_email is required'}), 400
    # Preserve existing ciphertext when password field left blank (update metadata only)
    encrypted_password = encrypt_password(password) if password else None
    profile_dir = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        'user_data', 'profiles', f"profile_user_{user_id}_{login_email.split('@')[0]}",
    )
    existing = next(
        (a for a in runtime_store.list_accounts(user_id) if (a.get('login_email') or '').lower() == login_email.lower()),
        None,
    )
    if encrypted_password is None and existing and existing.get('encrypted_password'):
        encrypted_password = existing['encrypted_password']
    elif encrypted_password is None:
        encrypted_password = ''
    account_id = runtime_store.upsert_account(
        user_id=user_id,
        login_email=login_email,
        encrypted_password=encrypted_password,
        label=(data.get('label') or (existing or {}).get('label') or login_email).strip(),
        is_primary=bool(data.get('is_primary')),
        is_active=bool(data.get('is_active', True)),
        priority=int(data.get('priority', 0) or 0),
        hourly_limit=int(data.get('hourly_limit', 0) or 0),
        daily_limit=int(data.get('daily_limit', 0) or 0),
        notes=data.get('notes'),
        profile_dir=data.get('profile_dir') or (existing or {}).get('profile_dir') or profile_dir,
    )
    # Keep primary User credentials in sync when password was provided
    if password:
        user.facebook_username = login_email
        user.facebook_password = encrypted_password
        db.session.commit()
    return jsonify({'message': 'Account saved', 'account_id': account_id}), 201


@app.route('/api/account/status', methods=['GET'])
@jwt_required()
def api_account_status():
    user_id = int(get_jwt_identity())
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)
    return jsonify({
        'accounts': orch.list_account_trust(user_id),
        'session': runtime_store.get_latest_session(user_id),
        'current_task': runtime_store.get_latest_task(user_id, 'posting'),
        'prepare_task': runtime_store.get_latest_task(user_id, 'prepare_account'),
    })


@app.route('/accounts')
@jwt_required()
def accounts_page():
    user_id = int(get_jwt_identity())
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    _ensure_release_runtime_user_state(current_user)
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)
    accounts = orch.list_account_trust(user_id)
    return render_template(
        'accounts.html',
        current_user=current_user,
        accounts=accounts,
    )


def _account_credentials(account: dict, fallback_user) -> tuple[str, str]:
    username = (account.get('login_email') or '').strip()
    password = ''
    if account.get('encrypted_password'):
        try:
            password = decrypt_password(account['encrypted_password'])
        except Exception:
            password = ''
    if not username and fallback_user:
        username = (fallback_user.facebook_username or '').strip()
    if not password and fallback_user and fallback_user.facebook_password:
        try:
            password = decrypt_password(fallback_user.facebook_password)
        except Exception:
            password = ''
    return username, password


def _credentials_ok(account: dict, fallback_user=None) -> bool:
    username, password = _account_credentials(account, fallback_user)
    return bool(username and password)


@app.route('/api/accounts/<int:account_id>/trust', methods=['GET'])
@jwt_required()
def api_account_trust(account_id: int):
    user_id = int(get_jwt_identity())
    account = runtime_store.get_account(account_id)
    if not account or int(account.get('user_id') or 0) != user_id:
        return jsonify({'error': 'Account not found'}), 404
    trust = runtime_store.get_account_trust(account_id)
    return jsonify(trust), 200


@app.route('/api/accounts/<int:account_id>/prepare', methods=['POST'])
@jwt_required()
def api_account_prepare(account_id: int):
    """Start Prepare Account (visible Chrome + CAPTCHA wait)."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    account = runtime_store.get_account(account_id)
    if not account or int(account.get('user_id') or 0) != user_id:
        return jsonify({'error': 'Account not found'}), 404

    active = runtime_store.get_latest_task(user_id, 'prepare_account')
    if active and active.get('status') in ('queued', 'running', 'waiting_manual'):
        return jsonify({'error': 'Prepare already in progress', 'task': active}), 400

    username, password = _account_credentials(account, user)
    if not username or not password:
        return jsonify({
            'error': 'Account credentials missing or undecryptable — re-save password on /accounts',
            'code': 'CREDENTIALS_MISSING',
            'hint': '/accounts',
        }), 400

    from bot.account_preparer import AccountPreparer
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)

    def _runner(task_id: int) -> dict:
        from app.services.task_control import CooperativeTaskControl, DurableControlMonitor, TaskStopped
        progress_tracker.reset()
        progress_tracker.start()
        runtime_store.append_task_event(task_id, 'Prepare account started', event_type='system')

        def _progress(payload: dict):
            control.checkpoint(on_stop=preparer.signal_resume_manual, allow_pause=False)
            progress_tracker.update(**payload)
            status = payload.get('status')
            if status == 'waiting_manual':
                runtime_store.update_task(task_id, status='waiting_manual', heartbeat_at=datetime.utcnow().isoformat())
                orch.mark_needs_verify(user_id, account_id, payload.get('message') or 'Manual verification required')
            runtime_store.append_task_event(
                task_id,
                payload.get('message') or payload.get('step') or 'prepare-progress',
                event_type='progress',
                metadata=payload,
            )
            broadcast_to_user(user_id, 'prepare_progress', {**payload, 'account_id': account_id, 'task_id': task_id})

        preparer = AccountPreparer(
            user_id=user_id,
            account_id=account_id,
            username=username,
            password=password,
            profile_dir=account.get('profile_dir'),
            progress_callback=_progress,
        )
        control = CooperativeTaskControl(runtime_store, task_id, user_id)
        try:
            control.checkpoint(allow_pause=False)
            with DurableControlMonitor(control, preparer.stop):
                result = preparer.prepare()
            state = runtime_store.get_control_state(task_id, user_id)
            if state and state.get('acknowledged_state') == 'stopping':
                return {'status': 'cancelled', 'error_message': 'Stopped by user'}
        except TaskStopped:
            return {'status': 'cancelled', 'error_message': 'Stopped by user'}
        if result.get('trusted'):
            orch.mark_trusted(user_id, account_id, profile_dir=result.get('profile_dir'))
            progress_tracker.update(status='completed', progress=100, message='Trusted')
            progress_tracker.finish(success=True)
            result = {**result, 'status': 'completed'}
        else:
            task_status = 'waiting_manual' if result.get('needs_manual') or result.get('status') == 'needs_verify' else 'failed'
            progress_tracker.update(status=task_status, error=result.get('error'), progress=progress_tracker.progress)
            progress_tracker.finish(success=False)
            result = {**result, 'status': task_status, 'error_message': result.get('error')}
        return result

    task = task_manager.start_task(
        user_id=user_id,
        task_type='prepare_account',
        title=f"Prepare account #{account_id}",
        payload={'account_id': account_id},
        runner=_runner,
        task_key=f'prepare:{user_id}:{account_id}',
    )
    return jsonify({'message': 'Prepare started', 'task': task, 'task_id': task.get('id')}), 202


@app.route('/api/accounts/<int:account_id>/validate', methods=['POST'])
@jwt_required()
def api_account_validate(account_id: int):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    account = runtime_store.get_account(account_id)
    if not account or int(account.get('user_id') or 0) != user_id:
        return jsonify({'error': 'Account not found'}), 404
    username, password = _account_credentials(account, user)
    if not username:
        return jsonify({'error': 'Account login missing'}), 400

    from bot.account_preparer import AccountPreparer
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)
    preparer = AccountPreparer(
        user_id=user_id,
        account_id=account_id,
        username=username,
        password=password or 'x',
        profile_dir=account.get('profile_dir'),
    )
    result = preparer.validate_only()
    if result.get('trusted'):
        orch.mark_trusted(user_id, account_id, profile_dir=result.get('profile_dir'))
    else:
        orch.mark_needs_verify(user_id, account_id, result.get('error') or 'Session invalid')
    return jsonify(result), 200


@app.route('/api/accounts/<int:account_id>/resume-manual', methods=['POST'])
@jwt_required()
def api_account_resume_manual(account_id: int):
    """Signal that user completed CAPTCHA/2FA in the open Chrome window."""
    user_id = int(get_jwt_identity())
    account = runtime_store.get_account(account_id)
    if not account or int(account.get('user_id') or 0) != user_id:
        return jsonify({'error': 'Account not found'}), 404

    from bot.account_preparer import get_active_preparer
    preparer = get_active_preparer(account_id)
    signaled = False
    if preparer:
        signaled = preparer.signal_resume_manual()

    # Also nudge active fetcher/poster if they share the challenge.
    global fetcher_instance, poster_instance
    if fetcher_instance and getattr(fetcher_instance, 'manual_verification_needed', False):
        setattr(fetcher_instance, 'manual_resume_requested', True)
        signaled = True
    if poster_instance and getattr(poster_instance, 'manual_verification_needed', False):
        setattr(poster_instance, 'manual_resume_requested', True)
        signaled = True

    if not signaled:
        # No live browser — validate saved profile as fallback
        user = User.query.get(user_id)
        username, password = _account_credentials(account, user)
        from bot.account_preparer import AccountPreparer
        from app.services.account_orchestrator import AccountOrchestrator
        orch = AccountOrchestrator(runtime_store)
        preparer = AccountPreparer(
            user_id=user_id,
            account_id=account_id,
            username=username or account.get('login_email') or '',
            password=password or 'x',
            profile_dir=account.get('profile_dir'),
        )
        result = preparer.validate_only()
        if result.get('trusted'):
            orch.mark_trusted(user_id, account_id, profile_dir=result.get('profile_dir'))
        else:
            orch.mark_needs_verify(user_id, account_id, result.get('error') or 'Session invalid')
        return jsonify({'message': 'No live browser — validated profile', **result}), 200

    progress_tracker.update(
        status='waiting_manual',
        step='manual_resume',
        message='Проверяем после ручной верификации...',
        progress=25,
    )
    return jsonify({'message': 'Resume signal sent', 'signaled': True}), 200


@app.route('/api/accounts/pick', methods=['POST'])
@jwt_required()
def api_accounts_pick():
    """Pick best trusted account for automation (rotation)."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)
    preferred = data.get('account_id')
    exclude = set(int(x) for x in (data.get('exclude_ids') or []) if str(x).isdigit())
    account, reason = orch.pick_account(
        user_id,
        preferred_account_id=int(preferred) if preferred else None,
        require_trusted=bool(data.get('require_trusted', True)),
        exclude_ids=exclude,
    )
    if not account:
        return jsonify({'error': reason or 'No account available', 'code': 'NO_ACCOUNT'}), 409
    return jsonify({'account': account}), 200

@app.route('/api/templates/stats')
@jwt_required()
def get_template_stats():
    """Get template system statistics"""
    try:
        runtime_user_id = _template_runtime_user_id()
        records = runtime_store.list_templates(runtime_user_id)
        # Initialize default stats
        stats = {
            'total_templates': len(records),
            'total_variables': 0, 
            'possible_combinations': 0
        }
        
        # Variables are shared application configuration; template content is user-scoped.
        templates_file = 'templates_data/message_templates.json'
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                import json
                data = json.load(f)
                variables = data.get('variables', {})
                stats['total_variables'] = len(variables)
                if records and variables:
                    combinations = 1
                    for var_list in variables.values():
                        if var_list:
                            combinations *= len(var_list)
                    stats['possible_combinations'] = combinations * len(records)
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting template stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/list')
@jwt_required()
def list_templates():
    """Get list of all templates"""
    try:
        import os
        runtime_user_id = _template_runtime_user_id()
        records = runtime_store.list_templates(runtime_user_id)
        templates = [record['content'] for record in records]
        
        return jsonify({
            'success': True,
            'templates': templates,
            'records': records,
            'count': len(templates)
        })
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/templates/variables')
@jwt_required()
def get_template_variables():
    """Get available template variables"""
    try:
        import os
        templates_file = 'templates_data/message_templates.json'
        
        # Default variables
        default_variables = {
            'name': ['Alex', 'Maria', 'John', 'Elena', 'Michael'],
            'product': ['amazing product', 'great service', 'unique opportunity'],
            'company': ['our company', 'our team', 'our platform'],
            'benefit': ['save time', 'increase profit', 'grow business']
        }
        
        variables = default_variables.copy()
        
        # Load custom variables if file exists
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                import json
                data = json.load(f)
                saved_variables = data.get('variables', {})
                variables.update(saved_variables)
        
        return jsonify(variables)
    except Exception as e:
        logger.error(f"Error getting template variables: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/add', methods=['POST'])
@jwt_required()
def add_template():
    """Add new template"""
    try:
        import os
        import json
        from datetime import datetime
        
        data = request.get_json()
        template_text = data.get('template', '').strip()
        
        if not template_text:
            return jsonify({'success': False, 'error': 'Template text is required'}), 400
        
        runtime_store.sync_templates(_template_runtime_user_id(), [template_text])
        
        logger.info(f"Template added successfully: {template_text[:50]}...")
        return jsonify({'success': True, 'message': 'Template added successfully'})
        
    except Exception as e:
        logger.error(f"Error adding template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/templates/delete', methods=['POST'])
@jwt_required()
def delete_template():
    """Delete specific template"""
    try:
        import os
        import json
        
        data = request.get_json()
        template_index = data.get('template_index')
        
        if template_index is None:
            return jsonify({'success': False, 'error': 'Template index is required'}), 400
        
        runtime_user_id = _template_runtime_user_id()
        templates = runtime_store.list_templates(runtime_user_id)
        
        if template_index < 0 or template_index >= len(templates):
            return jsonify({'success': False, 'error': 'Invalid template index'}), 400
        deleted_template = templates[template_index]['content']
        runtime_store.delete_template(runtime_user_id, deleted_template)
        
        logger.info(f"Template deleted: {deleted_template[:50]}...")
        return jsonify({'success': True, 'message': 'Template deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/templates/delete_multiple', methods=['POST'])
@jwt_required()
def delete_multiple_templates():
    """Delete multiple templates by indices (sorted descending to keep indices stable)"""
    try:
        import os, json
        data = request.get_json()
        indices = data.get('template_indices', [])
        if not indices:
            return jsonify({'success': False, 'error': 'No indices provided'}), 400

        runtime_user_id = _template_runtime_user_id()
        templates = runtime_store.list_templates(runtime_user_id)
        for i in sorted(set(indices), reverse=True):
            if 0 <= i < len(templates):
                runtime_store.delete_template(runtime_user_id, templates[i]['content'])

        return jsonify({'success': True, 'message': f'Deleted {len(indices)} template(s)'})
    except Exception as e:
        logger.error(f"Error deleting multiple templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates/metadata', methods=['POST'])
@jwt_required()
def update_template_metadata():
    try:
        data = request.get_json() or {}
        content = data.get('content')
        if not content:
            return jsonify({'success': False, 'error': 'Template content is required'}), 400
        runtime_store.update_template_meta(
            _template_runtime_user_id(),
            content,
            title=(data.get('title') or '').strip() or None,
            folder=(data.get('folder') or '').strip() or None,
            tags=data.get('tags', []),
            is_active=1 if data.get('is_active', True) else 0,
            weight=float(data.get('weight', 1.0) or 1.0),
        )
        return jsonify({'success': True, 'message': 'Template metadata updated'})
    except Exception as e:
        logger.error(f"Error updating template metadata: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/templates/generate')
@jwt_required()
def generate_template_message():
    """Generate a message from templates"""
    try:
        import os
        import json
        import random
        
        template_index = request.args.get('template_index', type=int)
        
        templates_file = 'templates_data/message_templates.json'
        templates = [row['content'] for row in runtime_store.list_templates(_template_runtime_user_id())]
        data = {}
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        variables = data.get('variables', {
            'name': ['Alex', 'Maria', 'John'],
            'product': ['amazing product', 'great service'],
            'benefit': ['save time', 'increase profit']
        })
        
        if not templates:
            return jsonify({'error': 'No templates available'}), 404
        
        # Select template
        if template_index is not None and 0 <= template_index < len(templates):
            template = templates[template_index]
            used_index = template_index
        else:
            used_index = random.randint(0, len(templates) - 1)
            template = templates[used_index]
        
        # Generate message with random variables
        message = template
        used_variables = {}
        
        import re
        for var_name, var_values in variables.items():
            patterns = [f'{{{{{var_name}}}}}', f'{{{var_name}}}']
            if any(pattern in message for pattern in patterns) and var_values:
                selected_value = random.choice(var_values)
                for pattern in patterns:
                    message = message.replace(pattern, selected_value)
                used_variables[var_name] = selected_value
        
        return jsonify({
            'message': message,
            'template_index': used_index,
            'variables_used': used_variables,
            'original_template': template
        })
        
    except Exception as e:
        logger.error(f"Error generating template message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/preview')
@jwt_required()
def preview_templates():
    """Preview multiple templates"""
    try:
        import os
        import json
        import random
        
        count = request.args.get('count', default=5, type=int)
        count = min(count, 20)  # Limit to max 20 previews
        
        templates_file = 'templates_data/message_templates.json'
        templates = [row['content'] for row in runtime_store.list_templates(_template_runtime_user_id())]
        data = {}
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        variables = data.get('variables', {
            'name': ['Alex', 'Maria', 'John'],
            'product': ['amazing product', 'great service'],
            'benefit': ['save time', 'increase profit']
        })
        
        if not templates:
            return jsonify({'previews': [], 'count': 0})
        
        previews = []
        
        # Generate previews
        for i in range(min(count, len(templates))):
            template = templates[i] if i < len(templates) else random.choice(templates)
            
            # Generate message with random variables
            message = template
            used_variables = {}
            
            for var_name, var_values in variables.items():
                patterns = [f'{{{{{var_name}}}}}', f'{{{var_name}}}']
                if any(pattern in message for pattern in patterns) and var_values:
                    selected_value = random.choice(var_values)
                    for pattern in patterns:
                        message = message.replace(pattern, selected_value)
                    used_variables[var_name] = selected_value
            
            previews.append({
                'template_index': i,
                'original_template': template,
                'generated_message': message,
                'variables_used': used_variables
            })
        
        return jsonify({
            'previews': previews,
            'count': len(previews),
            'total_templates': len(templates)
        })
        
    except Exception as e:
        logger.error(f"Error previewing templates: {e}")
        return jsonify({'error': str(e)}), 500

def _poster_status_to_task_status(status: str) -> str:
    return poster_status_to_task_status(status)


def _start_local_posting_thread(user_id: int, username: str, password: str, message: str, group_urls: list,
                                headless: bool = True, use_templates: bool = False,
                                template_mode: str = 'random', max_groups: int = 20,
                                account_id: Optional[int] = None, campaign_name: str = "",
                                skip_success_urls: Optional[set[str]] = None,
                                resumed_from_task_id: Optional[int] = None) -> dict:
    """Unified persistent posting runner backed by local threads or RQ workers."""
    global poster_instance

    if not _load_facebook_automation():
        raise RuntimeError("AI posting is not available in this environment")

    urls = [url for url in (group_urls or []) if url][:max_groups]
    if not urls:
        raise RuntimeError("No valid groups selected")

    active_task = runtime_store.get_latest_task(user_id, 'posting')
    if active_task and active_task.get('status') in ('queued', 'running', 'waiting_manual', 'paused'):
        raise RuntimeError("Posting already in progress")

    account_label = None
    accounts = runtime_store.list_accounts(user_id)
    selected_account = next((a for a in accounts if a['id'] == account_id), None) if account_id else None
    if selected_account:
        account_label = selected_account.get('label') or selected_account.get('login_email')
        if selected_account.get('login_email'):
            username = selected_account['login_email']
        if selected_account.get('encrypted_password'):
            password = decrypt_password(selected_account['encrypted_password'])
    primary_account = selected_account or runtime_store.get_primary_account(user_id)
    if primary_account and not account_label:
        account_label = primary_account.get('label') or primary_account.get('login_email')
        account_id = primary_account.get('id')
    account_profile_dir = primary_account.get('profile_dir') if primary_account else None

    task_payload = {
        'message': message,
        'group_urls': urls,
        'headless': headless,
        'use_templates': use_templates,
        'template_mode': template_mode,
        'account_id': account_id,
        'account_label': account_label,
        'campaign_name': campaign_name,
        'profile_dir': account_profile_dir,
        'resumed_from_task_id': resumed_from_task_id,
    }

    def _runner(task_id: int) -> dict:
        global poster_instance
        from app.services.posting_runner import execute_posting_task

        holder: dict = {}
        result = execute_posting_task(
            task_id=task_id,
            user_id=user_id,
            username=username,
            password=password,
            message=message,
            group_urls=urls,
            runtime_store=runtime_store,
            headless=headless,
            use_templates=use_templates,
            template_mode=template_mode,
            account_id=account_id,
            account_label=account_label,
            campaign_name=campaign_name,
            profile_dir=account_profile_dir,
            skip_success_urls=skip_success_urls,
            broadcast_user=lambda event, data: broadcast_to_user(user_id, event, data),
            record_session=_record_session_state,
            poster_instances=poster_instances,
            global_poster_holder=holder,
        )
        poster_instance = holder.get('instance') or poster_instances.get(user_id)
        tg_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        if tg_settings and tg_settings.is_active:
            snapshot = result.get('snapshot') or {}
            summary = f"Posting task #{task_id} finished with status: {snapshot.get('status', result.get('status'))}"
            if snapshot.get('posts_completed') or snapshot.get('posts_failed'):
                summary += f"\nSuccess: {snapshot.get('posts_completed', 0)} | Failed: {snapshot.get('posts_failed', 0)}"
            send_telegram_message(tg_settings.chat_id, summary)
        return result

    return task_dispatcher.start_posting(
        user_id=user_id,
        title=campaign_name or 'Facebook group posting',
        payload=task_payload,
        local_runner=_runner,
        resumed_from_task_id=resumed_from_task_id,
    )

# ===== Poster API for poster.html =====
@app.route('/api/post_to_groups', methods=['POST'])
@jwt_required()
def api_post_to_groups():
    global poster_instance
    try:
        data = request.get_json() or {}
        message = data.get('message', '').strip()
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        username = (data.get('username') or user.facebook_username or '').strip()
        password = (data.get('password') or (decrypt_password(user.facebook_password) if user.facebook_password else '')).strip()
        group_urls = data.get('group_urls', [])
        headless = bool(data.get('headless', True))
        max_groups = int(data.get('max_groups', 20))
        use_templates = bool(data.get('use_templates', False))
        template_mode = data.get('template_mode', 'random')
        account_id = data.get('account_id')
        campaign_name = (data.get('campaign_name') or '').strip()
        auto_rotate = bool(data.get('auto_rotate', True))

        if not use_templates and not message:
            return jsonify({'error': 'Message is required'}), 400
        if not group_urls:
            return jsonify({'error': 'No groups selected'}), 400

        from app.services.account_orchestrator import AccountOrchestrator
        orch = AccountOrchestrator(runtime_store)
        selected_account, pick_reason = orch.pick_account(
            user_id,
            preferred_account_id=int(account_id) if account_id else None,
            require_trusted=True,
        )
        if not selected_account:
            # Allow legacy form credentials only if no saved accounts exist
            if runtime_store.list_accounts(user_id):
                return jsonify({
                    'error': pick_reason or 'No trusted account available. Prepare an account first.',
                    'code': 'SESSION_NOT_TRUSTED',
                    'hint': '/accounts',
                }), 403
        else:
            account_id = int(selected_account['id'])
            username, password = _account_credentials(selected_account, user)

        if not username or not password:
            return jsonify({'error': 'Facebook credentials required'}), 400

        # Persist credentials encrypted (never log)
        user.facebook_username = username
        user.facebook_password = encrypt_password(password)
        db.session.commit()
        _ensure_release_runtime_user_state(user)
        tg_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        if tg_settings and tg_settings.is_active:
            send_telegram_message(
                tg_settings.chat_id,
                f"Campaign started\nGroups: {len(group_urls[:max_groups])}\nMode: {template_mode}\nHeadless: {'yes' if headless else 'no'}\nAccount: {account_id or 'legacy'}",
            )

        task = _start_local_posting_thread(
            user_id=int(user_id),
            username=username,
            password=password,
            message=message,
            group_urls=group_urls,
            headless=headless,
            use_templates=use_templates,
            template_mode=template_mode,
            max_groups=max_groups,
            account_id=int(account_id) if account_id else None,
            campaign_name=campaign_name,
        )
        return jsonify({
            'message': 'Posting started',
            'task': task,
            'task_id': task.get('id'),
            'mode': task.get('queue_mode', 'local_persistent'),
            'account_id': account_id,
            'auto_rotate': auto_rotate,
        }), 202
    except Exception as e:
        logger.error(f"api_post_to_groups error: {e}")
        return jsonify({'error': str(e) or 'Failed to start posting'}), 500

@app.route('/api/posting_status')
@jwt_required()
def api_posting_status():
    user_id = int(get_jwt_identity())
    task_id = request.args.get('task_id', type=int)
    task = runtime_store.get_task_for_user(task_id, user_id) if task_id else runtime_store.get_latest_task(user_id, 'posting')
    if task_id and not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(_task_snapshot_from_poster(user_id, task, None))

@app.route('/api/stop_posting', methods=['POST'])
@jwt_required()
def api_stop_posting():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}
        task_id = data.get('task_id')
        task = runtime_store.get_task_for_user(int(task_id), user_id) if task_id else runtime_store.get_active_task(user_id, 'posting')
        if task and runtime_store.request_stop(task['id'], user_id):
            return jsonify({'message': 'Stop requested', 'status': 'stopping', 'task_id': task['id']}), 202
        return jsonify({'error': 'No posting in progress'}), 400
    except Exception as e:
        logger.error(f"stop_posting error: {e}")
        return jsonify({'error': 'Failed to stop'}), 500


@app.route('/api/pause_posting', methods=['POST'])
@jwt_required()
def api_pause_posting():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    task = runtime_store.get_task_for_user(int(task_id), user_id) if task_id else runtime_store.get_active_task(user_id, 'posting')
    if task and runtime_store.request_pause(task['id'], user_id):
        return jsonify({'message': 'Posting pause requested', 'task_id': task['id']}), 202
    return jsonify({'error': 'No posting in progress'}), 400


@app.route('/api/resume_posting', methods=['POST'])
@jwt_required()
def api_resume_posting():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    task = runtime_store.get_task_for_user(int(task_id), user_id) if task_id else runtime_store.get_active_task(user_id, 'posting')
    if task and task.get('task_type') == 'posting' and runtime_store.request_resume(task['id'], user_id):
        return jsonify({'message': 'Posting resume requested', 'task_id': task['id']}), 202
    return jsonify({'error': 'No paused posting found'}), 400


@app.route('/api/tasks', methods=['GET'])
@jwt_required()
def api_list_tasks():
    user_id = int(get_jwt_identity())
    task_type = request.args.get('task_type')
    limit = min(int(request.args.get('limit', 25) or 25), 100)
    return jsonify({'tasks': runtime_store.list_tasks(user_id, task_type=task_type, limit=limit)})


@app.route('/api/tasks/<int:task_id>', methods=['GET'])
@jwt_required()
def api_get_task(task_id):
    task = runtime_store.get_task_for_user(task_id, int(get_jwt_identity()))
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@app.route('/api/tasks/<int:task_id>/stop', methods=['POST'])
@jwt_required()
def api_stop_task(task_id):
    user_id = int(get_jwt_identity())
    task = runtime_store.get_task_for_user(task_id, user_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    if not runtime_store.request_stop(task_id, user_id):
        return jsonify({'error': 'Task is not active'}), 409
    return jsonify({'message': 'Stop requested', 'task_id': task_id, 'status': 'stopping'}), 202


@app.route('/api/tasks/<int:task_id>/pause', methods=['POST'])
@jwt_required()
def api_pause_task(task_id):
    user_id = int(get_jwt_identity())
    task = runtime_store.get_task_for_user(task_id, user_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    if task.get('task_type') != 'posting':
        return jsonify({
            'error': f"Pause is not supported for {task.get('task_type')} tasks",
            'supported_actions': ['stop'],
        }), 409
    if not runtime_store.request_pause(task_id, user_id):
        return jsonify({'error': 'Task is not active'}), 409
    return jsonify({'message': 'Pause requested', 'task_id': task_id}), 202


@app.route('/api/tasks/<int:task_id>/resume', methods=['POST'])
@jwt_required()
def api_resume_task(task_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    task = runtime_store.get_task_for_user(task_id, user_id)
    if not user or not task:
        return jsonify({'error': 'Task not found'}), 404
    if task.get('task_type') != 'posting':
        return jsonify({
            'error': f"Resume is not supported for {task.get('task_type')} tasks",
            'supported_actions': ['stop'],
        }), 409
    if task.get('status') in ('queued', 'running', 'paused', 'waiting_manual', 'stopping'):
        if runtime_store.request_resume(task_id, user_id):
            return jsonify({'message': 'Resume requested', 'task_id': task_id}), 202
        return jsonify({'error': 'Task is not active'}), 409
    payload = task.get('payload') or {}
    groups = runtime_store.get_resumable_groups(task_id)
    if not groups:
        return jsonify({'error': 'No groups left to resume'}), 400
    password = decrypt_password(user.facebook_password) if user.facebook_password else ''
    if payload.get('account_id'):
        account = runtime_store.get_account(int(payload['account_id']))
        if account and account.get('encrypted_password'):
            password = decrypt_password(account['encrypted_password'])
    resume_task = _start_local_posting_thread(
        user_id=user_id,
        username=user.facebook_username or payload.get('username', ''),
        password=password,
        message=payload.get('message', ''),
        group_urls=groups,
        headless=bool(payload.get('headless', True)),
        use_templates=bool(payload.get('use_templates', False)),
        template_mode=payload.get('template_mode', 'random'),
        max_groups=len(groups),
        account_id=payload.get('account_id'),
        campaign_name=(payload.get('campaign_name') or f'Resume task #{task_id}'),
        skip_success_urls=runtime_store.get_success_group_urls(task_id),
        resumed_from_task_id=task_id,
    )
    return jsonify({'message': 'Resume started', 'task': resume_task, 'groups_remaining': len(groups)}), 202


@app.route('/api/tasks/<int:task_id>/retry_failed', methods=['POST'])
@jwt_required()
def api_retry_failed_task_groups(task_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    task = runtime_store.get_task_for_user(task_id, user_id)
    if not user or not task:
        return jsonify({'error': 'Task not found'}), 404
    failed_groups = runtime_store.get_failed_groups(task_id)
    if not failed_groups:
        return jsonify({'error': 'No failed groups to retry'}), 400
    payload = task.get('payload', {})
    password = decrypt_password(user.facebook_password) if user.facebook_password else ''
    retry_task = _start_local_posting_thread(
        user_id=user_id,
        username=user.facebook_username or payload.get('username', ''),
        password=password,
        message=payload.get('message', ''),
        group_urls=failed_groups,
        headless=bool(payload.get('headless', True)),
        use_templates=bool(payload.get('use_templates', False)),
        template_mode=payload.get('template_mode', 'random'),
        max_groups=len(failed_groups),
        account_id=payload.get('account_id'),
        campaign_name=(payload.get('campaign_name') or 'Retry failed groups'),
    )
    return jsonify({'message': 'Retry started', 'task': retry_task}), 202

@app.route('/api/validate_message', methods=['POST'])
@jwt_required()
def api_validate_message():
    try:
        data = request.get_json() or {}
        msg = data.get('message', '')
        if not msg.strip():
            return jsonify({'valid': False, 'error': 'Message cannot be empty'})
        links = msg.count('http://') + msg.count('https://')
        words = len(msg.split())
        return jsonify({'valid': True, 'stats': {'length': len(msg), 'words': words, 'links': links, 'emojis': 0}})
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)})

# ---------- Analytics trend API ----------
@app.route('/api/analytics/trend')
@jwt_required()
def api_analytics_trend():
    """Return monthly unique groups posted counts for last N months."""
    try:
        import sqlite3
        from bot.analytics_db import analytics_db
        from datetime import datetime

        def add_months(dt: datetime, months_delta: int) -> datetime:
            total_months = dt.year * 12 + dt.month - 1 + months_delta
            year = total_months // 12
            month = total_months % 12 + 1
            # keep at day 1 to avoid month length issues
            return dt.replace(year=year, month=month, day=1)

        months = int(request.args.get('months', 6) or 6)
        months = max(1, min(months, 24))

        start_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        window_start = add_months(start_month, - (months - 1))

        # Query analytics
        with sqlite3.connect(analytics_db.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT strftime('%Y-%m', posted_at) AS ym, COUNT(DISTINCT group_id)
                FROM post_analytics
                WHERE posted_at >= ? AND user_id = ?
                GROUP BY ym
                ORDER BY ym
                """,
                (window_start, int(get_jwt_identity()))
            )
            rows = cur.fetchall()
            ym_to_count = {ym: count or 0 for ym, count in rows}

        # Build labels and values for each month in window
        labels = []
        values = []
        for i in range(months):
            dt = add_months(window_start, i)
            ym = dt.strftime('%Y-%m')
            labels.append(dt.strftime('%b'))  # Jan, Feb, ...
            values.append(int(ym_to_count.get(ym, 0)))

        return jsonify({'labels': labels, 'values': values})
    except Exception as e:
        logger.error(f"analytics_trend error: {e}")
        return jsonify({'labels': ['Jan'], 'values': [0]}), 200


@app.route('/api/analytics/dashboard')
@jwt_required()
def api_analytics_dashboard():
    """JSON dashboard payload for analytics page live refresh."""
    try:
        from bot.analytics_db import analytics_db
        user_id = int(get_jwt_identity())
        return jsonify(analytics_db.get_dashboard_data(user_id)), 200
    except Exception as exc:
        logger.error("analytics dashboard error: %s", exc)
        return jsonify({'error': str(exc)}), 500


@app.route('/api/analytics/refresh', methods=['POST'])
@jwt_required()
def api_refresh_analytics():
    """Force pending facebook-scraper analytics checks to run."""
    try:
        from bot.analytics_db import analytics_db
        from bot.analytics_scheduler import analytics_scheduler
        user_id = int(get_jwt_identity())
        analytics_scheduler.force_analytics_check()
        summary = analytics_db.get_analytics_summary(user_id=user_id)
        dashboard = analytics_db.get_dashboard_data(user_id)
        return jsonify({
            'message': 'Analytics refresh triggered',
            'summary': summary,
            'dashboard': dashboard,
        }), 200
    except Exception as exc:
        logger.error("analytics refresh error: %s", exc)
        return jsonify({'error': str(exc)}), 500

# Application construction is intentionally separate from production bootstrap.
_app_initialized = False
_background_started = False


def create_app(test_config=None):
    """Bind extensions and runtime storage without starting background work."""
    global _app_initialized, runtime_store, task_manager
    global redis_conn, job_queue, analytics_queue, task_dispatcher, RUNTIME_DB_PATH
    if _app_initialized:
        if test_config:
            raise RuntimeError('create_app(test_config) must be the first initialization')
        return app
    if test_config:
        app.config.update(test_config)
    if app.config.get('TESTING'):
        app.config.setdefault('SECRET_KEY', 'test-secret-key')
        app.config.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-key')
    if not app.config.get('SECRET_KEY') or not app.config.get('JWT_SECRET_KEY'):
        raise RuntimeError(
            'FLASK_SECRET_KEY (or SECRET_KEY) and JWT_SECRET_KEY are required when debug is disabled'
        )
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    socketio.init_app(app)
    cors.init_app(app, origins=["http://localhost:3000", "http://localhost:8080"])
    limiter.init_app(app)
    RUNTIME_DB_PATH = app.config.get('RUNTIME_DB_PATH', AppConfig.RUNTIME_DB_PATH)
    runtime_store = RuntimeStore(RUNTIME_DB_PATH)
    task_manager = LocalTaskManager(runtime_store)
    if app.config.get('TESTING'):
        redis_conn = job_queue = analytics_queue = None
    else:
        redis_conn = redis.from_url(app.config.get('REDIS_URL', REDIS_URL))
        job_queue = Queue('default', connection=redis_conn)
        analytics_queue = Queue('analytics', connection=redis_conn)
    task_dispatcher = TaskDispatcher(
        runtime_store, task_manager, job_queue=job_queue,
        use_rq=False if app.config.get('TESTING') else None,
    )
    _app_initialized = True
    return app


def bootstrap_background_services():
    """Perform production mutations and start long-lived schedulers."""
    global campaign_manager, job_scheduler, _background_started
    if _background_started:
        return
    create_app()
    with app.app_context():
        db.create_all()
        runtime_store.mark_stale_tasks()
        runtime_store.cleanup_old_events()
        try:
            # Create admin user if not exists
            admin_password = os.environ.get('INITIAL_ADMIN_PASSWORD')
            if admin_password and not User.query.filter_by(email=os.environ.get('INITIAL_ADMIN_EMAIL', 'admin@test.com')).first():
                admin = User(
                    email=os.environ.get('INITIAL_ADMIN_EMAIL', 'admin@test.com'),
                    first_name='Admin',
                    last_name='User',
                    role='admin',
                    current_plan='PREMIUM',
                    email_verified=True
                )
                admin.set_password(admin_password)
                db.session.add(admin)
                db.session.commit()
                print("✅ Initial admin user created")
        except Exception as e:
            print(f"⚠️  Admin user creation skipped: {e}")
    
    # Initialize campaign manager and scheduler (outside of app context)
    campaign_manager = CampaignManager()
    job_scheduler = JobScheduler()
    try:
        from bot.analytics_scheduler import analytics_scheduler
        analytics_scheduler.set_job_queue(analytics_queue)
        analytics_scheduler.start()
        print("✅ Analytics scheduler started (facebook-scraper)")
    except Exception as analytics_boot_error:
        print(f"⚠️  Analytics scheduler skipped: {analytics_boot_error}")
    print("✅ Campaign manager initialized")
    print("✅ Job scheduler initialized")
    print("✅ Database tables created successfully!")
    _background_started = True


def shutdown_background_services():
    global _background_started
    if job_scheduler:
        job_scheduler.shutdown()
    try:
        from bot.analytics_scheduler import analytics_scheduler
        analytics_scheduler.stop()
    except Exception:
        pass
    _background_started = False


def run_server():
    create_app()
    bootstrap_background_services()

    # Setup graceful shutdown
    def shutdown_handler(signum, frame):
        print("🔄 Graceful shutdown initiated...")
        shutdown_background_services()
        print("✅ Application shut down successfully")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    # Register atexit handler
    atexit.register(shutdown_background_services)
    
    print("\n🚀 AIPostX - Integrated Test Mode")
    print("📡 URL: http://localhost:8080")
    print("🗄️  Database: SQLite (test_app.db)")
    print("🤖 AI Posting:", "✅ Enabled" if _load_facebook_automation() else "❌ Disabled")
    print("⚡ Ready for testing!")
    print("\nPress Ctrl+C to stop the server")
    
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', '8080')),
        debug=app.debug,
        allow_unsafe_werkzeug=app.debug,
        # Avoid Flask's stat reloader creating a second app/SQLAlchemy instance.
        use_reloader=False,
    )


if __name__ == '__main__':
    run_server()
