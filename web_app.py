"""
Modern Web Dashboard for Facebook Group Fetcher
Real-time progress tracking, group visualization, and export functionality
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

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import schedule

from bot.group_fetcher_fixed import FacebookGroupFetcher, get_fetched_groups
from bot.fb_poster import FacebookGroupPoster

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import analytics (graceful fallback if not available)
try:
    from bot.analytics_db import analytics_db
    analytics_available = True
    logger.info("✅ Analytics database available")
except ImportError as e:
    analytics_available = False
    analytics_db = None
    logger.warning(f"Analytics not available: {e}")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'facebook-group-fetcher-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
# Обеспечиваем корректную работу с UTF-8 и эмодзи
app.config['JSON_AS_ASCII'] = False

# Initialize SocketIO for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*")

# Global variables for tracking state
fetcher_instance = None
poster_instance = None
posting_thread = None
scheduled_jobs = []
job_history = []

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('exports', exist_ok=True)

# Encryption for credentials
CREDENTIALS_FILE = 'saved_credentials.enc'
ENCRYPTION_KEY_FILE = 'encryption.key'

def get_encryption_key():
    """Get or create encryption key for credentials"""
    if os.path.exists(ENCRYPTION_KEY_FILE):
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, 'wb') as f:
            f.write(key)
        return key

def encrypt_credentials(username, password):
    """Encrypt and save user credentials"""
    try:
        key = get_encryption_key()
        fernet = Fernet(key)
        
        data = {
            'username': username,
            'password': password,
            'saved_at': datetime.now().isoformat()
        }
        
        encrypted_data = fernet.encrypt(json.dumps(data).encode())
        
        with open(CREDENTIALS_FILE, 'wb') as f:
            f.write(encrypted_data)
            
        logger.info("Credentials saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving credentials: {e}")
        return False

def decrypt_credentials():
    """Decrypt and load saved credentials"""
    try:
        if not os.path.exists(CREDENTIALS_FILE):
            return None
            
        key = get_encryption_key()
        fernet = Fernet(key)
        
        with open(CREDENTIALS_FILE, 'rb') as f:
            encrypted_data = f.read()
            
        decrypted_data = fernet.decrypt(encrypted_data)
        data = json.loads(decrypted_data.decode())
        
        return {
            'username': data['username'],
            'password': data['password'],
            'saved_at': data.get('saved_at')
        }
    except Exception as e:
        logger.error(f"Error loading credentials: {e}")
        return None

def delete_saved_credentials():
    """Delete saved credentials"""
    try:
        if os.path.exists(CREDENTIALS_FILE):
            os.remove(CREDENTIALS_FILE)
        if os.path.exists(ENCRYPTION_KEY_FILE):
            os.remove(ENCRYPTION_KEY_FILE)
        logger.info("Saved credentials deleted")
        return True
    except Exception as e:
        logger.error(f"Error deleting credentials: {e}")
        return False

class ProgressTracker:
    """Track fetching progress and emit real-time updates"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.status = "idle"
        self.step = ""
        self.progress = 0
        self.total_groups = 0
        self.current_scroll = 0
        self.max_scroll = 10
        self.error = None
        self.start_time = None
        self.end_time = None
        
    def update(self, status=None, step=None, progress=None, total_groups=None, 
               current_scroll=None, error=None):
        if status:
            self.status = status
        if step:
            self.step = step
        if progress is not None:
            self.progress = progress
        if total_groups is not None:
            self.total_groups = total_groups
        if current_scroll is not None:
            self.current_scroll = current_scroll
        if error:
            self.error = error
            
        # Emit update via WebSocket
        socketio.emit('progress_update', {
            'status': self.status,
            'step': self.step,
            'progress': self.progress,
            'total_groups': self.total_groups,
            'current_scroll': self.current_scroll,
            'max_scroll': self.max_scroll,
            'error': self.error,
            'elapsed_time': self.get_elapsed_time()
        })
    
    def start(self):
        self.start_time = datetime.now()
        self.status = "running"
        
    def finish(self, success=True):
        self.end_time = datetime.now()
        self.status = "completed" if success else "failed"
        
    def get_elapsed_time(self):
        if not self.start_time:
            return 0
        end = self.end_time or datetime.now()
        return int((end - self.start_time).total_seconds())

# Global progress tracker
progress_tracker = ProgressTracker()


@app.route('/')
def dashboard():
    """Main dashboard page"""
    groups = get_fetched_groups()
    stats = {
        'total_groups': len(groups),
        'last_fetch': get_last_fetch_time(),
        'scheduled_jobs': len(scheduled_jobs),
        'job_history': len(job_history)
    }
    return render_template('dashboard.html', stats=stats)


@app.route('/groups')
def groups_page():
    """Groups listing and management page"""
    groups = get_fetched_groups()
    
    # Apply filters
    search = request.args.get('search', '')
    language_filters = request.args.getlist('languages')
    
    if search:
        groups = [g for g in groups if search.lower() in g['name'].lower()]
    
    if language_filters:
        groups = [g for g in groups if g.get('language_tag', 'unknown') in language_filters]
    
    # Pagination
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 12))
    start = (page - 1) * per_page
    end = start + per_page
    
    total_groups = len(groups)
    groups_page = groups[start:end]
    
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_groups,
        'pages': (total_groups + per_page - 1) // per_page,
        'has_prev': page > 1,
        'has_next': page * per_page < total_groups
    }
    
    # Get language statistics for filters
    from bot.language_classifier import LanguageClassifier
    all_groups = get_fetched_groups()  # Get all groups for stats
    language_stats = {}
    for group in all_groups:
        lang = group.get('language_tag', 'unknown')
        language_stats[lang] = language_stats.get(lang, 0) + 1
    
    return render_template('groups.html', 
                         groups=groups_page, 
                         pagination=pagination,
                         search=search,
                         selected_languages=language_filters,
                         language_stats=language_stats,
                         language_classifier=LanguageClassifier)


@app.route('/scheduler')
def scheduler_page():
    """Scheduling management page"""
    return render_template('scheduler.html', 
                         scheduled_jobs=scheduled_jobs,
                         job_history=job_history[-20:])  # Last 20 jobs


@app.route('/poster')
def poster_page():
    """Facebook posting page"""
    groups = get_fetched_groups()
    return render_template('poster.html', groups=groups)


@app.route('/api/start_fetch', methods=['POST'])
def start_fetch():
    """Start fetching groups"""
    global fetcher_instance
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    headless = data.get('headless', True)
    use_session = data.get('use_session', True)
    save_credentials = data.get('save_credentials', False)
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    if fetcher_instance and fetcher_instance.is_fetching:
        return jsonify({'error': 'Fetching already in progress'}), 400
    
    # Save credentials if requested
    if save_credentials:
        if encrypt_credentials(username, password):
            logger.info("User credentials saved for future use")
        else:
            logger.warning("Failed to save user credentials")
    
    # Start fetching in background thread
    def fetch_groups():
        global fetcher_instance
        progress_tracker.reset()
        progress_tracker.start()
        
        try:
            fetcher_instance = FacebookGroupFetcher(
                username=username,
                password=password,
                headless=headless,
                use_session=use_session
            )
            
            # Monkey patch to track progress
            original_extract = fetcher_instance.extract_joined_groups
            
            def tracked_extract(max_scroll_attempts=10):
                progress_tracker.max_scroll = max_scroll_attempts
                progress_tracker.update(status="running", step="extracting_groups")
                
                # Override the extraction method to track scroll progress
                original_groups = fetcher_instance.groups
                
                for i in range(max_scroll_attempts):
                    progress_tracker.update(
                        current_scroll=i+1,
                        total_groups=len(fetcher_instance.groups),
                        progress=int((i+1) / max_scroll_attempts * 100)
                    )
                    time.sleep(1)  # Simulate work
                
                return original_extract(max_scroll_attempts)
            
            fetcher_instance.extract_joined_groups = tracked_extract
            
            # Track different steps
            progress_tracker.update(step="initializing")
            groups = fetcher_instance.fetch_groups()
            
            if groups:
                progress_tracker.update(
                    total_groups=len(groups),
                    progress=100
                )
                progress_tracker.finish(success=True)
                
                # Add to job history
                job_history.append({
                    'id': len(job_history) + 1,
                    'type': 'manual',
                    'status': 'completed',
                    'groups_found': len(groups),
                    'started_at': progress_tracker.start_time.isoformat(),
                    'completed_at': progress_tracker.end_time.isoformat(),
                    'duration': progress_tracker.get_elapsed_time()
                })
            else:
                progress_tracker.update(error=fetcher_instance.error or "Unknown error")
                progress_tracker.finish(success=False)
                
        except Exception as e:
            progress_tracker.update(error=str(e))
            progress_tracker.finish(success=False)
            logger.error(f"Error during fetching: {str(e)}")
    
    thread = threading.Thread(target=fetch_groups)
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Fetching started'})


@app.route('/api/progress')
def get_progress():
    """Get current fetching progress"""
    return jsonify({
        'status': progress_tracker.status,
        'step': progress_tracker.step,
        'progress': progress_tracker.progress,
        'total_groups': progress_tracker.total_groups,
        'current_scroll': progress_tracker.current_scroll,
        'max_scroll': progress_tracker.max_scroll,
        'error': progress_tracker.error,
        'elapsed_time': progress_tracker.get_elapsed_time()
    })


@app.route('/api/groups')
def get_groups_api():
    """Get groups data as JSON"""
    groups = get_fetched_groups()
    
    # Apply search filter
    search = request.args.get('search', '')
    if search:
        groups = [g for g in groups if search.lower() in g['name'].lower()]
    
    # Apply language filters
    language_filters = request.args.getlist('languages')  # Get list of selected languages
    if language_filters:
        groups = [g for g in groups if g.get('language_tag', 'unknown') in language_filters]
    
    return jsonify({
        'groups': groups,
        'total': len(groups)
    })


@app.route('/api/languages')
def get_languages_api():
    """Get language statistics and supported languages"""
    from bot.language_classifier import LanguageClassifier
    
    groups = get_fetched_groups()
    
    # Calculate language statistics
    language_stats = {}
    for group in groups:
        lang = group.get('language_tag', 'unknown')
        language_stats[lang] = language_stats.get(lang, 0) + 1
    
    # Get all supported languages with info
    supported_languages = LanguageClassifier.get_all_languages()
    
    # Add unknown language info
    supported_languages.append({
        'code': 'unknown',
        'name': 'Unknown',
        'flag': '❓'
    })
    
    return jsonify({
        'statistics': language_stats,
        'supported_languages': supported_languages
    })


@app.route('/api/export/<format>')
def export_groups(format):
    """Export groups in various formats"""
    groups = get_fetched_groups()
    
    if not groups:
        return jsonify({'error': 'No groups to export'}), 400
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if format == 'json':
        output = BytesIO()
        output.write(json.dumps(groups, indent=2).encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f'facebook_groups_{timestamp}.json',
            mimetype='application/json'
        )
    
    elif format == 'csv':
        output = BytesIO()
        df = pd.DataFrame(groups)
        df.to_csv(output, index=False, encoding='utf-8')
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f'facebook_groups_{timestamp}.csv',
            mimetype='text/csv'
        )
    
    elif format == 'excel':
        output = BytesIO()
        df = pd.DataFrame(groups)
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Facebook Groups', index=False)
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f'facebook_groups_{timestamp}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    elif format == 'all':
        # Create zip with all formats
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # JSON
            zip_file.writestr(f'facebook_groups_{timestamp}.json', 
                            json.dumps(groups, indent=2))
            
            # CSV
            df = pd.DataFrame(groups)
            csv_buffer = BytesIO()
            df.to_csv(csv_buffer, index=False, encoding='utf-8')
            zip_file.writestr(f'facebook_groups_{timestamp}.csv', 
                            csv_buffer.getvalue())
            
            # Excel
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Facebook Groups', index=False)
            zip_file.writestr(f'facebook_groups_{timestamp}.xlsx', 
                            excel_buffer.getvalue())
        
        zip_buffer.seek(0)
        
        return send_file(
            zip_buffer,
            as_attachment=True,
            download_name=f'facebook_groups_export_{timestamp}.zip',
            mimetype='application/zip'
        )
    
    else:
        return jsonify({'error': 'Invalid format'}), 400


@app.route('/api/schedule', methods=['POST'])
def schedule_job():
    """Schedule automatic fetching"""
    data = request.get_json()
    
    schedule_type = data.get('type')  # 'daily', 'weekly', 'monthly'
    time_str = data.get('time', '09:00')  # HH:MM format
    username = data.get('username')
    password = data.get('password')
    
    if not all([schedule_type, username, password]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    job_id = len(scheduled_jobs) + 1
    
    def scheduled_fetch():
        # This would trigger the same fetch process
        pass
    
    # Add to scheduled jobs
    scheduled_jobs.append({
        'id': job_id,
        'type': schedule_type,
        'time': time_str,
        'username': username,
        'created_at': datetime.now().isoformat(),
        'active': True
    })
    
    return jsonify({'message': 'Job scheduled successfully', 'job_id': job_id})


@app.route('/api/schedule/<int:job_id>', methods=['DELETE'])
def delete_scheduled_job(job_id):
    """Delete scheduled job"""
    global scheduled_jobs
    scheduled_jobs = [job for job in scheduled_jobs if job['id'] != job_id]
    return jsonify({'message': 'Job deleted successfully'})


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    emit('connected', {'message': 'Connected to real-time updates'})


@socketio.on('request_progress')
def handle_progress_request():
    """Send current progress when requested"""
    emit('progress_update', {
        'status': progress_tracker.status,
        'step': progress_tracker.step,
        'progress': progress_tracker.progress,
        'total_groups': progress_tracker.total_groups,
        'current_scroll': progress_tracker.current_scroll,
        'max_scroll': progress_tracker.max_scroll,
        'error': progress_tracker.error,
        'elapsed_time': progress_tracker.get_elapsed_time()
    })


def get_last_fetch_time():
    """Get timestamp of last fetch"""
    try:
        if os.path.exists('autofetched_groups.json'):
            stat = os.path.stat('autofetched_groups.json')
            return datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    except:
        pass
    return 'Never'


@app.route('/api/credentials', methods=['GET'])
def get_saved_credentials():
    """Get saved credentials (username only for security)"""
    credentials = decrypt_credentials()
    if credentials:
        return jsonify({
            'has_saved_credentials': True,
            'username': credentials['username'],
            'saved_at': credentials.get('saved_at'),
            'password_length': len(credentials['password'])  # For verification only
        })
    else:
        return jsonify({'has_saved_credentials': False})


@app.route('/api/credentials', methods=['POST'])
def save_credentials():
    """Save user credentials"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    if encrypt_credentials(username, password):
        return jsonify({'message': 'Credentials saved successfully'})
    else:
        return jsonify({'error': 'Failed to save credentials'}), 500


@app.route('/api/credentials', methods=['DELETE'])
def delete_credentials():
    """Delete saved credentials"""
    if delete_saved_credentials():
        return jsonify({'message': 'Credentials deleted successfully'})
    else:
        return jsonify({'error': 'Failed to delete credentials'}), 500


@app.route('/api/credentials/load', methods=['POST'])
def load_saved_credentials():
    """Load saved credentials for auto-fill"""
    credentials = decrypt_credentials()
    if credentials:
        return jsonify({
            'username': credentials['username'],
            'password': credentials['password']
        })
    else:
        return jsonify({'error': 'No saved credentials found'}), 404


@app.route('/api/reset_session', methods=['POST'])
def reset_facebook_session():
    """Reset Facebook session and clear profile data"""
    try:
        import shutil
        
        # Paths to clean up
        profile_dir = 'chrome_profile'
        cookies_file = 'facebook_cookies.json'
        screenshots_dir = 'screenshots'
        
        # Remove Chrome profile directory
        if os.path.exists(profile_dir):
            shutil.rmtree(profile_dir)
            logger.info("Chrome profile directory removed")
        
        # Remove cookies file
        if os.path.exists(cookies_file):
            os.remove(cookies_file)
            logger.info("Facebook cookies file removed")
        
        # Clear old screenshots (keep last 5)
        if os.path.exists(screenshots_dir):
            screenshots = sorted([f for f in os.listdir(screenshots_dir) if f.endswith('.png')])
            if len(screenshots) > 5:
                for screenshot in screenshots[:-5]:
                    os.remove(os.path.join(screenshots_dir, screenshot))
                logger.info(f"Cleaned up old screenshots, kept last 5")
        
        return jsonify({'message': 'Facebook session reset successfully'})
        
    except Exception as e:
        logger.error(f"Error resetting session: {e}")
        return jsonify({'error': f'Failed to reset session: {str(e)}'}), 500


@app.route('/api/post_to_groups', methods=['POST'])
def post_to_groups():
    """Start posting message to Facebook groups"""
    global poster_instance, posting_thread
    
    data = request.get_json()
    message = data.get('message', '').strip()
    username = data.get('username')
    password = data.get('password')
    group_urls = data.get('group_urls', [])
    headless = data.get('headless', True)
    max_groups = data.get('max_groups', 20)
    use_templates = data.get('use_templates', False)
    template_mode = data.get('template_mode', 'random')
    
    # Validation
    if not use_templates and not message:
        return jsonify({'error': 'Message content is required when not using templates'}), 400
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
        
    if not group_urls:
        return jsonify({'error': 'At least one group URL is required'}), 400
    
    # Check if posting is already in progress
    if poster_instance and poster_instance.is_posting:
        return jsonify({'error': 'Posting already in progress'}), 400
    
    def posting_task():
        global poster_instance
        
        try:
            # Initialize poster instance
            poster_instance = FacebookGroupPoster(headless=headless)
            poster_instance.username = username
            poster_instance.password = password
            
            # Enable analytics if available
            if analytics_available:
                try:
                    poster_instance.analytics_db = analytics_db
                    poster_instance.analytics_enabled = True
                    logger.info("✅ Analytics enabled for posting")
                except Exception as e:
                    logger.warning(f"Failed to enable analytics: {e}")
            
            # Create temporary groups file
            temp_groups_file = 'temp_groups.txt'
            with open(temp_groups_file, 'w') as f:
                for url in group_urls[:max_groups]:
                    f.write(url + '\n')
            
            # Start posting
            success = poster_instance.post_to_multiple_groups(
                message=message,
                groups_file=temp_groups_file,
                max_groups=max_groups,
                use_templates=use_templates,
                template_mode=template_mode
            )
            
            # Clean up temp file
            if os.path.exists(temp_groups_file):
                os.remove(temp_groups_file)
            
            # Emit completion event
            socketio.emit('posting_completed', {
                'success': success,
                'stats': poster_instance.get_status()
            })
            
        except Exception as e:
            logger.error(f"Error in posting task: {e}")
            socketio.emit('posting_error', {'error': str(e)})
    
    # Start posting in background thread
    posting_thread = threading.Thread(target=posting_task)
    posting_thread.daemon = True
    posting_thread.start()
    
    return jsonify({'message': 'Posting started successfully'})


@app.route('/api/stop_posting', methods=['POST'])
def stop_posting():
    """Stop current posting process"""
    global poster_instance
    
    if poster_instance and poster_instance.is_posting:
        poster_instance.stop_posting_method()
        return jsonify({'message': 'Posting stop requested'})
    else:
        return jsonify({'error': 'No posting in progress'}), 400


@app.route('/api/posting_status')
def get_posting_status():
    """Get current posting status"""
    global poster_instance
    
    if poster_instance:
        status = poster_instance.get_status()
        return jsonify(status)
    else:
        return jsonify({
            'is_posting': False,
            'status': 'Idle',
            'posts_completed': 0,
            'posts_failed': 0,
            'groups_total': 0,
            'elapsed_time': '00:00:00'
        })


@app.route('/api/validate_message', methods=['POST'])
def validate_message():
    """Validate message content for Facebook posting with emoji support"""
    data = request.get_json()
    message = data.get('message', '')
    
    if not message.strip():
        return jsonify({'valid': False, 'error': 'Message cannot be empty'})
    
    # Check for common issues
    warnings = []
    positive_features = []
    
    # Check for very long message
    if len(message) > 8000:
        warnings.append('Message is very long (>8000 chars), might be truncated by Facebook')
    
    # Check for excessive links
    link_count = message.count('http://') + message.count('https://')
    if link_count > 3:
        warnings.append(f'Message contains {link_count} links, Facebook might flag as spam')
    
    # Enhanced emoji detection and support
    emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002702-\U000027B0]')
    emoji_count = len(emoji_pattern.findall(message))
    
    if emoji_count > 0:
        if emoji_count <= 15:
            positive_features.append(f'✅ Содержит {emoji_count} эмодзи - отлично для привлечения внимания!')
        else:
            warnings.append(f'Message contains {emoji_count} emojis, consider reducing for better readability')
    
    # Check UTF-8 encoding
    try:
        message.encode('utf-8')
        positive_features.append('✅ UTF-8 кодировка корректна - поддерживаются все символы')
    except UnicodeEncodeError:
        warnings.append('⚠️ Message contains characters that may not display correctly')
    
    # Check for newlines and formatting
    if '\n' in message:
        positive_features.append('✅ Использует переносы строк для лучшего форматирования')
    
    return jsonify({
        'valid': True,
        'warnings': warnings,
        'positive_features': positive_features,
        'stats': {
            'length': len(message),
            'words': len(message.split()),
            'lines': len(message.split('\n')),
            'links': link_count,
            'emojis': emoji_count,
            'utf8_safe': True
        }
    })


# ===============================
# TEMPLATE SYSTEM API ENDPOINTS
# ===============================

@app.route('/api/templates/stats')
def get_template_stats():
    """Get template system statistics"""
    try:
        from bot.message_templates import get_template_manager
        manager = get_template_manager()
        stats = manager.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting template stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/variables')
def get_template_variables():
    """Get available template variables"""
    try:
        from bot.message_templates import get_template_manager
        manager = get_template_manager()
        return jsonify(manager.default_variables)
    except Exception as e:
        logger.error(f"Error getting template variables: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/add', methods=['POST'])
def add_template():
    """Add a new message template"""
    try:
        from bot.message_templates import get_template_manager
        data = request.get_json()
        template = data.get('template', '').strip()
        
        if not template:
            return jsonify({'error': 'Template content is required'}), 400
        
        manager = get_template_manager()
        
        # Validate template
        is_valid, warnings = manager.validate_template(template)
        if not is_valid:
            return jsonify({'error': f'Invalid template: {"; ".join(warnings)}'}), 400
        
        # Add template
        success = manager.add_template(template)
        if success:
            return jsonify({'success': True, 'warnings': warnings})
        else:
            return jsonify({'error': 'Failed to add template'}), 500
            
    except Exception as e:
        logger.error(f"Error adding template: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/preview')
def preview_templates():
    """Get preview of template variations"""
    try:
        from bot.message_templates import get_template_manager
        manager = get_template_manager()
        count = request.args.get('count', 3, type=int)
        previews = manager.preview_templates(count)
        return jsonify({'previews': previews})
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/settings')
def get_template_settings():
    """Get template system settings from config"""
    try:
        import configparser
        config = configparser.ConfigParser()
        config.read('config.ini')
        
        settings = {}
        if config.has_section('Templates'):
            settings['use_templates'] = config.getboolean('Templates', 'use_templates', fallback=False)
            settings['template_mode'] = config.get('Templates', 'template_mode', fallback='random')
            settings['log_template_usage'] = config.getboolean('Templates', 'log_template_usage', fallback=True)
        else:
            settings = {
                'use_templates': False,
                'template_mode': 'random',
                'log_template_usage': True
            }
        
        return jsonify(settings)
    except Exception as e:
        logger.error(f"Error getting template settings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/generate')
def generate_template_message():
    """Generate a message from templates"""
    try:
        from bot.message_templates import get_template_manager
        manager = get_template_manager()
        
        template_index = request.args.get('template_index', type=int)
        message, used_index, variables = manager.generate_message(template_index)
        
        return jsonify({
            'message': message,
            'template_index': used_index,
            'variables_used': variables,
            'original_template': manager.templates[used_index] if used_index < len(manager.templates) else None
        })
    except Exception as e:
        logger.error(f"Error generating template message: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/templates/list')
def list_templates():
    """Get list of all templates"""
    try:
        from bot.message_templates import get_template_manager
        manager = get_template_manager()
        
        return jsonify({
            'success': True,
            'templates': manager.templates,
            'count': len(manager.templates)
        })
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/templates/delete', methods=['POST'])
def delete_template():
    """Delete a specific template"""
    try:
        from bot.message_templates import get_template_manager
        manager = get_template_manager()
        
        data = request.get_json()
        template_index = data.get('template_index')
        
        if template_index is None or template_index < 0 or template_index >= len(manager.templates):
            return jsonify({'success': False, 'error': 'Invalid template index'}), 400
        
        # Remove template
        deleted_template = manager.templates.pop(template_index)
        manager.save_templates()
        
        logger.info(f"Deleted template #{template_index}: {deleted_template[:50]}...")
        
        return jsonify({
            'success': True,
            'deleted_template': deleted_template,
            'remaining_count': len(manager.templates)
        })
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/templates/delete_multiple', methods=['POST'])
def delete_multiple_templates():
    """Delete multiple templates"""
    try:
        from bot.message_templates import get_template_manager
        manager = get_template_manager()
        
        data = request.get_json()
        template_indices = data.get('template_indices', [])
        
        if not template_indices:
            return jsonify({'success': False, 'error': 'No template indices provided'}), 400
        
        # Sort indices in descending order to avoid index shifting issues
        sorted_indices = sorted(set(template_indices), reverse=True)
        
        deleted_templates = []
        for index in sorted_indices:
            if 0 <= index < len(manager.templates):
                deleted_template = manager.templates.pop(index)
                deleted_templates.append(deleted_template)
        
        manager.save_templates()
        
        logger.info(f"Deleted {len(deleted_templates)} templates")
        
        return jsonify({
            'success': True,
            'deleted_count': len(deleted_templates),
            'remaining_count': len(manager.templates)
        })
    except Exception as e:
        logger.error(f"Error deleting multiple templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Template Manager Page Route
@app.route('/templates')
def template_manager():
    """Template manager page"""
    return render_template('template_manager.html')


@app.route('/analytics')
def analytics():
    """Analytics dashboard page"""
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
                             recent_posts=[])
    
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
        
        # Mock data for charts (you can replace with real data later)
        performance_dates = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        performance_data = [2.1, 3.5, 2.8, 4.2, 3.9, 5.1, 4.7]
        engagement_breakdown = [150, 45, 12]  # likes, comments, shares
        
        # Mock recent posts (you can get from database later)
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
                             recent_posts=recent_posts)
                             
    except Exception as e:
        logger.error(f"Error loading analytics: {e}")
        # Return basic template with error message
        return render_template('analytics.html',
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
                             error_message=str(e))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, debug=True) 