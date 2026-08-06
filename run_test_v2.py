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
from flask_wtf.csrf import CSRFProtect, generate_csrf
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
    # Flask-WTF CSRF covers cookie-authenticated mutating requests.
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_ACCESS_COOKIE_NAME = 'access_token'
    JWT_REFRESH_COOKIE_NAME = 'refresh_token'
    JWT_COOKIE_HTTPONLY = True
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_HEADERS = ['X-CSRFToken', 'X-CSRF-Token']
    WTF_CSRF_CHECK_DEFAULT = True
    # Fetcher storage (per-user directory)
    GROUPS_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'user_data', 'groups')
    FETCHED_GROUPS_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'autofetched_groups.json')  # legacy fallback
    
    # Database configuration (SQLite by default; Postgres via DATABASE_URL)
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = AppConfig.sqlalchemy_database_uri()
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

progress_tracker = ProgressTracker()  # legacy alias; prefer get_progress_tracker(user_id)
_progress_trackers = {}
_progress_lock = threading.RLock()


def get_progress_tracker(user_id: int) -> ProgressTracker:
    """Return an isolated progress tracker for a dashboard user."""
    with _progress_lock:
        tracker = _progress_trackers.get(user_id)
        if tracker is None:
            tracker = ProgressTracker()
            _progress_trackers[user_id] = tracker
        return tracker


def reset_progress_tracker(user_id: int) -> ProgressTracker:
    tracker = get_progress_tracker(user_id)
    tracker.reset()
    return tracker


# Initialize Flask app
app = Flask(__name__)
app.config.from_object(TestConfig)

# Extensions are bound by create_app(), after test configuration is applied.
db = SQLAlchemy()
jwt = JWTManager()
bcrypt = Bcrypt()
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')
csrf = CSRFProtect()
cors = CORS()

# Local persistent runtime store for release features.
RUNTIME_DB_PATH = AppConfig.RUNTIME_DB_PATH
runtime_store = None
task_manager = None

# RQ setup
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
redis_conn = None
job_queue = None
browser_queue = None
analytics_queue = None
task_dispatcher = None

# --- Security middleware (production hardening) ---
@app.after_request
def apply_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.socket.io; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss: https://*.onrender.com; "
        "frame-src 'self' https://*.onrender.com; "
        "frame-ancestors 'none'"
    )
    return response


# Initialize rate limiter (Redis when available; memory fallback for local/dev)
def _limiter_storage_uri() -> str:
    redis_url = os.environ.get('REDIS_URL', '').strip()
    if redis_url:
        return redis_url
    logger.warning("REDIS_URL unset — Flask-Limiter using in-memory storage")
    return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per minute"],
    storage_uri=_limiter_storage_uri(),
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

# CSRF helpers
def get_csrf_token():
    """Return a real Flask-WTF CSRF token for templates / JSON clients."""
    return generate_csrf()


@app.context_processor
def inject_csrf_token_context():
    return {'csrf_token': generate_csrf}


# route moved to app.blueprints — was lines 435-438


# Admin required decorator
def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    @jwt_required()
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
        """Execute a scheduled job via the same TaskDispatcher path as the UI."""
        try:
            logger.info(f"Executing scheduled job {job_id} for user {user_id}")
            with app.app_context():
                user = User.query.get(user_id)
                if not user:
                    raise RuntimeError(f"User {user_id} not found for scheduled job {job_id}")
                groups = job_data.get('target_groups') or []
                if isinstance(groups, str):
                    try:
                        groups = json.loads(groups)
                    except Exception:
                        groups = [g.strip() for g in groups.splitlines() if g.strip()]
                message = job_data.get('message', '')
                account_id = None
                username = user.facebook_username or ''
                password = decrypt_password(user.facebook_password or '') if user.facebook_password else ''
                try:
                    from app.services.account_orchestrator import AccountOrchestrator
                    orch = AccountOrchestrator(runtime_store)
                    selected, _reason = orch.pick_account(user_id, require_trusted=True)
                    if selected:
                        account_id = int(selected['id'])
                        username, password = _account_credentials(selected, user)
                except Exception as pick_err:
                    logger.warning("Scheduled job account pick skipped: %s", pick_err)

                task = _start_local_posting_thread(
                    user_id=user_id,
                    username=username,
                    password=password,
                    message=message,
                    group_urls=list(groups),
                    headless=bool(user.use_headless),
                    use_templates=bool(job_data.get('use_templates')),
                    template_mode=job_data.get('template_mode') or 'random',
                    account_id=account_id,
                    campaign_name=job_data.get('name') or f'Scheduled Job {job_id}',
                )
                job = ScheduledJob.query.get(job_id)
                if job:
                    job.last_run = datetime.utcnow()
                    job.run_count = (job.run_count or 0) + 1
                    job.status = 'active'
                    db.session.commit()
                logger.info(
                    "Scheduled job %s dispatched as task %s",
                    job_id,
                    (task or {}).get('id'),
                )
        except Exception as e:
            logger.error(f"Error executing scheduled job {job_id}: {e}")
            with app.app_context():
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
    """DEPRECATED: legacy in-process campaign runner.

    Prefer TaskDispatcher + _start_local_posting_thread (HTTP and cron).
    Kept only for backward-compatible Socket.IO campaign_* helpers.
    """
    
    def __init__(self):
        self.active_campaigns = {}
        self.poster_instances = {}
    
    def start_campaign(self, campaign_id: int, user_id: int, campaign_data: dict):
        """Start a Facebook posting campaign (legacy — prefer TaskDispatcher)."""
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
                    setTimeout(() => { window.location.replace('/dashboard'); }, 1200);
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
                if (response.ok && result.user) {
                    const name = (result.user && result.user.full_name) ? result.user.full_name : 'User';
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = 'Welcome back, ' + name + '! Redirecting...';
                    resultDiv.style.display = 'block';
                    setTimeout(() => { window.location.replace('/dashboard'); }, 400);
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
            fetch('/api/auth/me', { credentials: 'include' })
            .then(response => {
                if (response.ok) {
                    const d = document.getElementById('autoLoginMessage');
                    d.style.display = 'block';
                    d.innerHTML = '<div class="alert alert-info"><i class="bi bi-info-circle me-2"></i><strong>Welcome back!</strong> Already logged in. <span class="spinner-border spinner-border-sm ms-2"></span> Redirecting...</div>';
                    setTimeout(() => { window.location.replace('/dashboard'); }, 1200);
                }
            })
            .catch(() => {});
        });
    </script>
</body>
</html>
'''

# Routes
# route moved to app.blueprints — was lines 1216-1218

# JWT error handlers - DISABLED FOR DEBUGGING
# @app.errorhandler(Exception)
# def handle_jwt_error(error):
#     """Handle JWT errors"""
#     logger.error(f"JWT Error: {error}")
#     print(f"JWT Error: {error}")
#     return redirect(url_for('home'))

# route moved to app.blueprints — was lines 1228-1233

# route moved to app.blueprints — was lines 1235-1256

# route moved to app.blueprints — was lines 1258-1283

# route moved to app.blueprints — was lines 1285-1331

# route moved to app.blueprints — was lines 1333-1397

# route moved to app.blueprints — was lines 1399-1496

# route moved to app.blueprints — was lines 1498-1546

# route moved to app.blueprints — was lines 1548-1681

# route moved to app.blueprints — was lines 1683-1730

# route moved to app.blueprints — was lines 1732-1755

# route moved to app.blueprints — was lines 1757-1771

# route moved to app.blueprints — was lines 1773-1788

# route moved to app.blueprints — was lines 1790-1805

# route moved to app.blueprints — was lines 1807-1875

# Admin Panel Route
# route moved to app.blueprints — was lines 1878-1897

# Admin API Routes (for AJAX calls from admin panel)
# route moved to app.blueprints — was lines 1900-1975

# route moved to app.blueprints — was lines 1977-2039

# Admin User Management API Endpoints
# route moved to app.blueprints — was lines 2042-2112

# route moved to app.blueprints — was lines 2114-2171

# route moved to app.blueprints — was lines 2173-2211

# route moved to app.blueprints — was lines 2213-2248

# route moved to app.blueprints — was lines 2250-2321

# route moved to app.blueprints — was lines 2323-2416

# route moved to app.blueprints — was lines 2418-2478

# route moved to app.blueprints — was lines 2480-2503

# route moved to app.blueprints — was lines 2505-2521

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
    bot_token = db.Column(db.String(512), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    last_test_sent = db.Column(db.DateTime)
    test_successful = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        token = (self.bot_token or '').strip()
        masked = ''
        if token:
            masked = (token[:6] + '…' + token[-4:]) if len(token) > 12 else '••••'
        return {
            'id': self.id,
            'user_id': self.user_id,
            'chat_id': self.chat_id,
            'bot_token_set': bool(token),
            'bot_token_masked': masked,
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

# route moved to app.blueprints — was lines 2673-2698

# route moved to app.blueprints — was lines 2700-2780

# route moved to app.blueprints — was lines 2782-2849


# route moved to app.blueprints — was lines 2852-2910


# route moved to app.blueprints — was lines 2913-2945


# route moved to app.blueprints — was lines 2948-2956

# Scheduler API endpoints
# route moved to app.blueprints — was lines 2959-2984

# route moved to app.blueprints — was lines 2986-3079

# route moved to app.blueprints — was lines 3081-3150

# route moved to app.blueprints — was lines 3152-3192

# route moved to app.blueprints — was lines 3194-3241

# route moved to app.blueprints — was lines 3243-3290

# route moved to app.blueprints — was lines 3292-3319

# route moved to app.blueprints — was lines 3321-3359

# route moved to app.blueprints — was lines 3361-3413

# Telegram Bot API endpoints
# route moved to app.blueprints — was lines 3416-3437

# route moved to app.blueprints — was lines 3439-3480

# route moved to app.blueprints — was lines 3482-3526


# route moved to app.blueprints — was lines 3529-3549

# route moved to app.blueprints — was lines 3551-3579

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

# route moved to app.blueprints — was lines 3704-3785

# route moved to app.blueprints — was lines 3787-3803


# route moved to app.blueprints — was lines 3806-3823


# route moved to app.blueprints — was lines 3826-3967

# route moved to app.blueprints — was lines 3969-3998

# route moved to app.blueprints — was lines 4000-4024


# route moved to app.blueprints — was lines 4027-4050


# route moved to app.blueprints — was lines 4053-4066


# route moved to app.blueprints — was lines 4069-4141


# route moved to app.blueprints — was lines 4144-4155


# route moved to app.blueprints — was lines 4158-4173


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


# route moved to app.blueprints — was lines 4199-4207


# route moved to app.blueprints — was lines 4210-4297


# route moved to app.blueprints — was lines 4300-4327


# route moved to app.blueprints — was lines 4330-4381


# route moved to app.blueprints — was lines 4384-4402

# route moved to app.blueprints — was lines 4404-4436

# route moved to app.blueprints — was lines 4438-4456

# route moved to app.blueprints — was lines 4458-4487

# route moved to app.blueprints — was lines 4489-4511

# route moved to app.blueprints — was lines 4513-4540

# route moved to app.blueprints — was lines 4542-4562


# route moved to app.blueprints — was lines 4565-4585


# route moved to app.blueprints — was lines 4588-4644

# route moved to app.blueprints — was lines 4646-4706

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
# route moved to app.blueprints — was lines 4805-4890

# route moved to app.blueprints — was lines 4892-4900

# route moved to app.blueprints — was lines 4902-4915


# route moved to app.blueprints — was lines 4918-4927


# route moved to app.blueprints — was lines 4930-4939


# route moved to app.blueprints — was lines 4942-4948


# route moved to app.blueprints — was lines 4951-4957


# route moved to app.blueprints — was lines 4960-4969


# route moved to app.blueprints — was lines 4972-4986


# route moved to app.blueprints — was lines 4989-5030


# route moved to app.blueprints — was lines 5033-5059

# route moved to app.blueprints — was lines 5061-5073

# ---------- Analytics trend API ----------
# route moved to app.blueprints — was lines 5076-5126


# route moved to app.blueprints — was lines 5129-5139


# route moved to app.blueprints — was lines 5142-5160

# Application construction is intentionally separate from production bootstrap.
_app_initialized = False
_background_started = False


def create_app(test_config=None):
    """Bind extensions and runtime storage without starting background work."""
    global _app_initialized, runtime_store, task_manager
    global redis_conn, job_queue, browser_queue, analytics_queue, task_dispatcher, RUNTIME_DB_PATH
    if _app_initialized:
        if test_config:
            raise RuntimeError('create_app(test_config) must be the first initialization')
        return app
    if test_config:
        app.config.update(test_config)
    if app.config.get('TESTING'):
        app.config.setdefault('SECRET_KEY', 'test-secret-key')
        app.config.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-key')
        # TestConfig enables CSRF by default; disable unless a test opts in.
        if not test_config or 'WTF_CSRF_ENABLED' not in test_config:
            app.config['WTF_CSRF_ENABLED'] = False
    if not app.config.get('SECRET_KEY') or not app.config.get('JWT_SECRET_KEY'):
        raise RuntimeError(
            'FLASK_SECRET_KEY (or SECRET_KEY) and JWT_SECRET_KEY are required when debug is disabled'
        )
    db_url = os.environ.get('DATABASE_URL', '').strip()
    if db_url and not app.config.get('TESTING'):
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    socketio.init_app(app)
    csrf.init_app(app)
    cors.init_app(app, origins=["http://localhost:3000", "http://localhost:8080"])
    limiter.init_app(app)
    RUNTIME_DB_PATH = app.config.get('RUNTIME_DB_PATH', AppConfig.RUNTIME_DB_PATH)
    if app.config.get('TESTING'):
        runtime_url = ''
    else:
        runtime_url = app.config.get('RUNTIME_DATABASE_URL') or AppConfig.runtime_database_url()
    runtime_store = RuntimeStore(RUNTIME_DB_PATH, database_url=runtime_url)
    task_manager = LocalTaskManager(runtime_store)
    if app.config.get('TESTING'):
        redis_conn = job_queue = browser_queue = analytics_queue = None
    else:
        redis_url = app.config.get('REDIS_URL', REDIS_URL)
        try:
            redis_kwargs = {}
            if str(redis_url).startswith("rediss://"):
                redis_kwargs["ssl_cert_reqs"] = None
            redis_conn = redis.from_url(redis_url, socket_connect_timeout=5, **redis_kwargs)
            redis_conn.ping()
            job_queue = Queue('default', connection=redis_conn)
            browser_queue = Queue('browser', connection=redis_conn)
            analytics_queue = Queue('analytics', connection=redis_conn)
            logger.info("Redis connected for RQ queues")
        except Exception as redis_err:
            logger.warning("Redis unavailable (%s) — falling back to local task threads", redis_err)
            redis_conn = job_queue = browser_queue = analytics_queue = None
    task_dispatcher = TaskDispatcher(
        runtime_store, task_manager, job_queue=job_queue,
        use_rq=False if app.config.get('TESTING') or job_queue is None else None,
    )
    from app.blueprints import register_blueprints, blueprint_view, rebind_all
    register_blueprints(app)
    # Exempt unauthenticated / health endpoints from CSRF.
    csrf.exempt(blueprint_view('infra', 'health'))
    csrf.exempt(blueprint_view('auth', 'register'))
    csrf.exempt(blueprint_view('auth', 'login'))
    csrf.exempt(blueprint_view('auth', 'logout'))
    csrf.exempt(blueprint_view('infra', 'api_csrf_token'))
    csrf.exempt(blueprint_view('telegram', 'telegram_webhook'))
    if not app.config.get('TESTING'):
        @app.before_request
        def _lazy_bootstrap_background():
            if not _background_started:
                try:
                    bootstrap_background_services()
                except Exception as boot_err:
                    logger.warning("Background bootstrap deferred/failed: %s", boot_err)
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
        try:
            from sqlalchemy import inspect, text
            insp = inspect(db.engine)
            cols = {c["name"] for c in insp.get_columns("telegram_settings")}
            if "bot_token" not in cols:
                db.session.execute(text("ALTER TABLE telegram_settings ADD COLUMN bot_token VARCHAR(512)"))
                db.session.commit()
                print("✅ Added telegram_settings.bot_token column")
        except Exception as migrate_err:
            db.session.rollback()
            print(f"⚠️  telegram_settings.bot_token migrate skipped: {migrate_err}")
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
        from app.services.event_bridge import start_user_event_listener
        start_user_event_listener(redis_conn, broadcast_to_user)
        print("✅ Redis user-event bridge started")
    except Exception as bridge_err:
        print(f"⚠️  User-event bridge skipped: {bridge_err}")
    try:
        from bot.analytics_scheduler import analytics_scheduler
        analytics_scheduler.set_job_queue(analytics_queue)

        def _digest_recipients():
            rows = []
            try:
                with app.app_context():
                    for settings in TelegramSettings.query.filter_by(is_active=True).all():
                        user = User.query.get(settings.user_id)
                        label = ""
                        if user:
                            label = getattr(user, "full_name", None) or user.email or f"user {user.id}"
                        rows.append({
                            "user_id": settings.user_id,
                            "chat_id": settings.chat_id,
                            "label": label,
                        })
            except Exception as recip_err:
                logger.warning("Digest recipients lookup failed: %s", recip_err)
            return rows

        analytics_scheduler.set_digest_recipients_provider(_digest_recipients)
        analytics_scheduler.start()
        print("✅ Analytics scheduler started (metrics + daily Telegram digests)")
    except Exception as analytics_boot_error:
        print(f"⚠️  Analytics scheduler skipped: {analytics_boot_error}")
    print("✅ Campaign manager initialized (deprecated path retained)")
    print("✅ Job scheduler initialized")
    print("✅ Database tables created successfully!")
    try:
        from bot.telegram_bot import activate_inbound_bot

        result = activate_inbound_bot()
        if result.get("ok"):
            print(f"✅ Telegram inbound bot active ({result.get('mode')})")
        else:
            print(f"ℹ️  Telegram inbound bot skipped: {result.get('error') or result}")
    except Exception as tg_bot_err:
        print(f"⚠️  Telegram inbound bot skipped: {tg_bot_err}")
    try:
        from app.blueprints import rebind_all
        rebind_all()
    except Exception:
        pass
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
    try:
        from bot.telegram_bot import stop_telegram_bot_polling
        stop_telegram_bot_polling()
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
