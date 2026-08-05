"""
Facebook Group Poster - Dashboard Application
Flask-based web interface to control the Facebook group posting bot
"""

import os
import time
import json
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
import configparser

from bot.fb_poster import FacebookGroupPoster
from bot.post_logger import get_statistics, filter_logs, STATUS_SUCCESS, STATUS_ERROR, STATUS_BLOCKED
from bot.group_fetcher import FacebookGroupFetcher, get_fetched_groups

# Setup logging to capture bot output
log_handler = logging.FileHandler('poster.log')
log_handler.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler.setFormatter(log_formatter)

logger = logging.getLogger('fb_poster')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max upload
app.config['SECRET_KEY'] = 'facebook-group-poster-secret-key'
app.config['TEMPLATES_FOLDER'] = 'templates_data'

# Create necessary folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMPLATES_FOLDER'], exist_ok=True)
os.makedirs('logs', exist_ok=True)

# Only add console handler in debug mode
if app.debug:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

# Reduce Flask logging
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Log startup
logger.info("Initializing Facebook Group Poster")

# Initialize bot
fb_bot = FacebookGroupPoster()
posting_thread = None
log_buffer = []
group_fetching_thread = None

# Load credentials from config file if available
if os.path.exists('config.ini'):
    try:
        logger.info("Loading credentials from config.ini")
        config = configparser.ConfigParser()
        config.read('config.ini')
        
        # Set credentials
        fb_bot.username = config.get('Credentials', 'username', fallback='')
        fb_bot.password = config.get('Credentials', 'password', fallback='')
        
        # Set other settings
        if 'Settings' in config:
            fb_bot.min_delay = config.getint('Settings', 'min_delay_seconds', fallback=10)
            fb_bot.max_delay = config.getint('Settings', 'max_delay_seconds', fallback=60)
            fb_bot.headless = config.getboolean('Settings', 'headless_mode', fallback=False)
            fb_bot.max_groups = config.getint('Settings', 'max_groups_per_session', fallback=20)
            
        logger.info(f"Loaded configuration for user: {fb_bot.username}")
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")

# Templates file path
TEMPLATES_FILE = os.path.join(app.config['TEMPLATES_FOLDER'], 'message_templates.json')
GROUPS_FILE = 'autofetched_groups.json'

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analytics')
def analytics():
    """Analytics dashboard page"""
    try:
        # Get analytics data
        from bot.analytics_db import analytics_db
        
        # Get top performing groups
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

@app.route('/start_posting', methods=['POST'])
def start_posting():
    global posting_thread
    
    if posting_thread and posting_thread.is_alive():
        return jsonify({'status': 'error', 'message': 'Posting already in progress'})
    
    # Get messages - either single message or queue
    message = request.form.get('message', '').strip()
    post_queue = request.form.get('post_queue', '').strip()
    
    # Process queue file if uploaded
    queue_file = request.files.get('queue_file')
    messages = []
    
    if queue_file and queue_file.filename:
        try:
            content = queue_file.read().decode('utf-8')
            # Split by --- separator or by newlines
            if '---' in content:
                messages = [msg.strip() for msg in content.split('---') if msg.strip()]
            else:
                messages = [msg.strip() for msg in content.splitlines() if msg.strip()]
        except Exception as e:
            logger.error(f"Error processing queue file: {str(e)}")
            return jsonify({'status': 'error', 'message': f'Error processing queue file: {str(e)}'})
    elif post_queue:
        # Split by --- separator
        messages = [msg.strip() for msg in post_queue.split('---') if msg.strip()]
    elif message:
        messages = [message]
    
    if not messages:
        return jsonify({'status': 'error', 'message': 'No message content provided'})
    
    max_groups = int(request.form.get('max_groups', 20))
    
    # Handle group selection
    selected_groups = request.form.getlist('selected_groups[]')
    
    # Determine which groups to use:
    # 1. If groups_file is uploaded, use that
    # 2. If selected_groups[] is provided, use the selected groups from autofetched_groups.json
    # 3. Otherwise, use the default groups.txt
    groups_file = request.files.get('groups_file')
    groups_filepath = None
    
    if groups_file and groups_file.filename:
        filename = secure_filename(groups_file.filename)
        groups_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        groups_file.save(groups_filepath)
        logger.info(f"Using uploaded groups file: {groups_filepath}")
    elif selected_groups:
        # Create a temporary file with the selected groups
        temp_groups_filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'selected_groups.txt')
        try:
            # Get groups from json file
            all_groups = get_fetched_groups(GROUPS_FILE)
            
            # Filter to selected groups
            selected_group_urls = []
            for group in all_groups:
                if group['url'] in selected_groups:
                    selected_group_urls.append(group['url'])
            
            # Write to temp file
            with open(temp_groups_filepath, 'w') as f:
                for url in selected_group_urls:
                    f.write(f"{url}\n")
            
            groups_filepath = temp_groups_filepath
            logger.info(f"Using {len(selected_group_urls)} selected groups")
        except Exception as e:
            logger.error(f"Error creating selected groups file: {str(e)}")
            return jsonify({'status': 'error', 'message': f'Error with selected groups: {str(e)}'})
    else:
        groups_filepath = 'groups.txt'  # Use default groups file
        logger.info("Using default groups.txt file")
    
    # Start posting in a separate thread
    def post_to_groups_task():
        try:
            fb_bot.login()
            
            # Post each message in queue
            for msg in messages:
                if fb_bot.stop_posting:
                    logger.info("Posting stopped by user")
                    break
                
                fb_bot.post_to_multiple_groups(msg, groups_filepath, max_groups)
                
                # Small delay between different messages
                if len(messages) > 1 and messages[-1] != msg:
                    time.sleep(5)  # 5 second pause between messages
        except Exception as e:
            logger.error(f"Error in posting thread: {str(e)}")
    
    posting_thread = threading.Thread(target=post_to_groups_task)
    posting_thread.daemon = True
    posting_thread.start()
    
    return jsonify({'status': 'success'})

@app.route('/stop_posting', methods=['POST'])
def stop_posting():
    if fb_bot.is_posting:
        fb_bot.stop_posting_method()
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': 'No posting in progress'})

@app.route('/get_status')
def get_status():
    try:
        status = 'running' if fb_bot.is_posting else 'idle'
        if fb_bot.waiting_for_2fa:
            status = 'waiting for 2FA confirmation'
        elif fb_bot.error:
            status = 'error'
        elif fb_bot.stop_posting_flag:
            status = 'stopping'
        
        # Get group statuses with enriched information
        group_statuses = {}
        if hasattr(fb_bot, 'group_statuses'):
            # Clone the group_statuses to avoid modifying the original
            group_statuses = fb_bot.group_statuses.copy()
            
            # Enrich with group names from autofetched_groups.json if available
            group_names = {}
            if os.path.exists('autofetched_groups.json'):
                try:
                    with open('autofetched_groups.json', 'r') as f:
                        groups = json.load(f)
                        for group in groups:
                            if 'url' in group and 'name' in group:
                                # Extract group ID from URL
                                url_parts = group['url'].split('/')
                                group_id = url_parts[-1].split('?')[0]
                                group_names[group_id] = {
                                    'name': group['name'],
                                    'url': group['url']
                                }
                except Exception as e:
                    logger.error(f"Error loading group names: {str(e)}")
            
            # Add message content and group names to status information
            current_message = getattr(fb_bot, 'current_message', '')
            for group_id, status_data in group_statuses.items():
                # Add the message being posted
                status_data['message'] = current_message
                
                # Add group name if available
                if group_id in group_names:
                    status_data['name'] = group_names[group_id]['name']
                    
                # Make sure URL is included
                if 'url' not in status_data and group_id in group_names:
                    status_data['url'] = group_names[group_id]['url']
                
                # Check if we have a screenshot for this group
                screenshots_dir = os.path.join(os.getcwd(), 'screenshots')
                if os.path.exists(screenshots_dir):
                    for filename in os.listdir(screenshots_dir):
                        # Look for screenshots with this group ID in the filename
                        if group_id in filename:
                            status_data['screenshot'] = filename
                            break
        
        return jsonify({
            'status': status,
            'is_posting': fb_bot.is_posting,
            'posts_completed': fb_bot.posts_completed,
            'posts_failed': fb_bot.posts_failed,
            'groups_total': fb_bot.groups_total,
            'group_statuses': group_statuses
        })
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({
            'status': 'error',
            'is_posting': False,
            'posts_completed': 0,
            'posts_failed': 0,
            'groups_total': 0,
            'error_message': str(e)
        }), 200  # Return 200 instead of 500 to prevent excessive error logging

@app.route('/get_logs')
def get_logs():
    logs = []
    try:
        with open('poster.log', 'r') as log_file:
            log_lines = log_file.readlines()
            for line in log_lines:
                parts = line.strip().split(' - ', 2)
                if len(parts) >= 3:
                    timestamp, level, message = parts
                    logs.append({
                        'timestamp': timestamp,
                        'level': level,
                        'message': message
                    })
    except Exception as e:
        print(f"Error reading log file: {str(e)}")
    
    return jsonify({'logs': logs})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Template Management Endpoints
@app.route('/get_templates')
def get_templates():
    try:
        if os.path.exists(TEMPLATES_FILE):
            with open(TEMPLATES_FILE, 'r') as f:
                templates = json.load(f)
        else:
            templates = []
        return jsonify({'status': 'success', 'templates': templates})
    except Exception as e:
        logger.error(f"Error retrieving templates: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/save_template', methods=['POST'])
def save_template():
    try:
        template_name = request.form.get('name', '').strip()
        template_content = request.form.get('content', '').strip()
        
        if not template_name or not template_content:
            return jsonify({'status': 'error', 'message': 'Template name and content are required'})
        
        # Load existing templates
        templates = []
        if os.path.exists(TEMPLATES_FILE):
            with open(TEMPLATES_FILE, 'r') as f:
                templates = json.load(f)
        
        # Check if template already exists
        template_exists = False
        for i, template in enumerate(templates):
            if template['name'] == template_name:
                # Update existing template
                templates[i]['content'] = template_content
                template_exists = True
                break
        
        # Add new template if it doesn't exist
        if not template_exists:
            templates.append({
                'id': str(int(time.time())),
                'name': template_name,
                'content': template_content
            })
        
        # Save templates
        with open(TEMPLATES_FILE, 'w') as f:
            json.dump(templates, f, indent=2)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error saving template: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/delete_template/<template_id>', methods=['DELETE'])
def delete_template(template_id):
    try:
        # Load existing templates
        if os.path.exists(TEMPLATES_FILE):
            with open(TEMPLATES_FILE, 'r') as f:
                templates = json.load(f)
        else:
            return jsonify({'status': 'error', 'message': 'No templates found'})
        
        # Filter out the template to delete
        templates = [t for t in templates if t.get('id') != template_id]
        
        # Save updated templates
        with open(TEMPLATES_FILE, 'w') as f:
            json.dump(templates, f, indent=2)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error deleting template: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

# Facebook Group Fetching Endpoints
@app.route('/get_my_groups')
def get_my_groups():
    """Get groups the user is a member of"""
    try:
        # Check if groups file exists
        if os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, 'r') as f:
                groups = json.load(f)
                return jsonify({
                    'status': 'success',
                    'groups': groups,
                    'fetched': True
                })
        
        # If no file exists, return empty array with instructions
        return jsonify({
            'status': 'success',
            'groups': [],
            'fetched': False,
            'message': 'No groups found. Please run the manual_fetch_groups.py script to fetch your groups.'
        })
    
    except Exception as e:
        logger.error(f"Error retrieving groups: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error retrieving groups: {str(e)}'
        })

@app.route('/fetch_my_groups', methods=['POST'])
def fetch_my_groups():
    """Trigger fetching of Facebook groups"""
    global group_fetching_thread
    
    # Check if already fetching
    if group_fetching_thread and group_fetching_thread.is_alive():
        return jsonify({
            'status': 'running',
            'message': 'Group fetching is already in progress. Please wait for it to complete.'
        })
    
    # Get credentials from config
    username = fb_bot.username
    password = fb_bot.password
    
    if not username or not password:
        return jsonify({
            'status': 'error',
            'message': 'Facebook credentials are not configured. Please provide your credentials in the Settings tab before fetching groups.'
        })
    
    # Check for session parameters
    use_session = request.form.get('use_session', 'true').lower() == 'true'
    reset_session = request.form.get('reset_session', 'false').lower() == 'true'
    headless = fb_bot.headless
    
    # Warn if headless mode is enabled with reset_session (first login)
    session_exists = os.path.exists("chrome_profile") or os.path.exists("facebook_cookies.json")
    if headless and reset_session or (headless and not session_exists):
        logger.warning("First-time login with headless mode enabled may fail if CAPTCHA or 2FA is required")
    
    # Define the group fetching task
    def fetch_groups_task():
        try:
            logger.info(f"Starting group fetch with options: use_session={use_session}, reset_session={reset_session}, headless={headless}")
            
            # Initialize the group fetcher with credentials
            fetcher = FacebookGroupFetcher(
                username=username,
                password=password,
                output_file="autofetched_groups.json",
                headless=headless,
                use_session=use_session,
                reset_session=reset_session
            )
            
            # Attempt to fetch groups
            groups = fetcher.fetch_groups()
            
            if groups is None:
                error_msg = fetcher.error if fetcher.error else "Unknown error"
                logger.error(f"Group fetching failed: {error_msg}")
                logger.error(f"Current step when failed: {fetcher.step}")
                
                # Save additional diagnostics
                with open('group_fetch_error.log', 'w') as f:
                    f.write(f"Error: {error_msg}\n")
                    f.write(f"Step: {fetcher.step}\n")
                    f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Options: use_session={use_session}, reset_session={reset_session}, headless={headless}\n")
                    
                return
            
            # Log success    
            session_msg = "using existing session" if fetcher.session_loaded else "with new login"
            logger.info(f"Successfully fetched {len(groups)} groups {session_msg}")
            
        except Exception as e:
            logger.error(f"Error in group fetching thread: {str(e)}")
    
    # Start the fetching thread
    group_fetching_thread = threading.Thread(target=fetch_groups_task)
    group_fetching_thread.daemon = True
    group_fetching_thread.start()
    
    # Customize message based on session status
    if reset_session:
        message = 'Facebook group fetching has started with a fresh login (session reset). This may take a minute or two. You can check the progress in the Logs tab.'
    elif use_session and session_exists:
        message = 'Facebook group fetching has started using saved session. This should be quick if the session is valid. You can check the progress in the Logs tab.'
    else:
        message = 'Facebook group fetching has started with a new login. This may take a minute or two. You can check the progress in the Logs tab. For more reliable fetching with CAPTCHA or 2FA, you should run manual_fetch_groups.py with visible browser mode.'
    
    # Add warning about headless mode if appropriate
    if headless and (reset_session or not session_exists):
        message += ' WARNING: Headless mode is enabled for first-time login, which may fail if CAPTCHA/2FA appears. Consider using manual_fetch_groups.py instead.'
    
    return jsonify({
        'status': 'started',
        'message': message,
        'using_session': use_session and session_exists,
        'headless_warning': headless and (reset_session or not session_exists)
    })

@app.route('/session_status')
def session_status():
    """Check if a saved session exists"""
    profile_exists = os.path.exists("chrome_profile") and os.path.isdir("chrome_profile")
    cookies_exist = os.path.exists("facebook_cookies.json")
    
    return jsonify({
        'status': 'success',
        'session_exists': profile_exists or cookies_exist,
        'profile_exists': profile_exists,
        'cookies_exist': cookies_exist
    })

@app.route('/clear_session', methods=['POST'])
def clear_session():
    """Clear saved session data"""
    try:
        # Clear Chrome profile
        if os.path.exists("chrome_profile") and os.path.isdir("chrome_profile"):
            import shutil
            try:
                shutil.rmtree("chrome_profile")
                logger.info("Chrome profile directory cleared")
            except Exception as e:
                logger.error(f"Error clearing Chrome profile: {str(e)}")
        
        # Clear cookies file
        if os.path.exists("facebook_cookies.json"):
            try:
                os.remove("facebook_cookies.json")
                logger.info("Cookies file cleared")
            except Exception as e:
                logger.error(f"Error clearing cookies file: {str(e)}")
        
        return jsonify({
            'status': 'success',
            'message': 'Session data cleared successfully'
        })
    except Exception as e:
        logger.error(f"Error clearing session: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error clearing session: {str(e)}'
        })

# Post History Endpoints
@app.route('/get_history')
def get_history():
    try:
        # Get filter parameters
        status = request.args.get('status')
        account = request.args.get('account')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Get filtered logs
        logs = filter_logs(status, account, start_date, end_date)
        
        # Get statistics
        stats = get_statistics()
        
        return jsonify({
            'status': 'success',
            'history': logs,
            'statistics': stats
        })
    except Exception as e:
        logger.error(f"Error retrieving post history: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/save_credentials', methods=['POST'])
def save_credentials():
    """Save user credentials to config file"""
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            return jsonify({
                'status': 'error',
                'message': 'Username and password are required'
            })
            
        config = configparser.ConfigParser()
        
        # Create or read existing config
        if os.path.exists('config.ini'):
            config.read('config.ini')
        
        # Ensure Credentials section exists
        if 'Credentials' not in config:
            config['Credentials'] = {}
            
        # Update credentials
        config['Credentials']['username'] = username
        config['Credentials']['password'] = password
        
        # Save config
        with open('config.ini', 'w') as config_file:
            config.write(config_file)
            
        # Update bot's credentials
        fb_bot.username = username
        fb_bot.password = password
        
        logger.info(f"Credentials updated for user: {username}")
        
        return jsonify({
            'status': 'success',
            'message': 'Credentials saved successfully'
        })
    
    except Exception as e:
        logger.error(f"Error saving credentials: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error saving credentials: {str(e)}'
        })

@app.route('/save_bot_settings', methods=['POST'])
def save_bot_settings():
    """Save bot settings to config file"""
    try:
        min_delay = request.form.get('min_delay', '10').strip()
        max_delay = request.form.get('max_delay', '60').strip()
        headless = request.form.get('headless', 'false').strip().lower() == 'true'
        max_groups = request.form.get('max_groups', '20').strip()
        
        config = configparser.ConfigParser()
        
        # Create or read existing config
        if os.path.exists('config.ini'):
            config.read('config.ini')
        
        # Ensure Settings section exists
        if 'Settings' not in config:
            config['Settings'] = {}
            
        # Update settings
        config['Settings']['min_delay_seconds'] = min_delay
        config['Settings']['max_delay_seconds'] = max_delay
        config['Settings']['headless_mode'] = str(headless)
        config['Settings']['max_groups_per_session'] = max_groups
        
        # Save config
        with open('config.ini', 'w') as config_file:
            config.write(config_file)
            
        # Update bot's settings
        fb_bot.min_delay = int(min_delay)
        fb_bot.max_delay = int(max_delay)
        fb_bot.headless = headless
        fb_bot.max_groups = int(max_groups)
        
        logger.info("Bot settings updated")
        
        return jsonify({
            'status': 'success',
            'message': 'Bot settings saved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error saving bot settings: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error saving bot settings: {str(e)}'
        })

@app.route('/get_settings')
def get_settings():
    """Get current settings without revealing the actual password"""
    try:
        settings = {
            "username": fb_bot.username,
            "has_password": bool(fb_bot.password),  # Just indicate if password exists
            "min_delay": fb_bot.min_delay,
            "max_delay": fb_bot.max_delay,
            "headless_mode": fb_bot.headless,
            "max_groups": fb_bot.max_groups
        }
        
        return jsonify({
            "status": "success",
            "settings": settings
        })
    except Exception as e:
        logger.error(f"Error getting settings: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Failed to get settings: {str(e)}"
        })

@app.route('/autofetched_groups.json')
def serve_groups_json():
    """Serve the autofetched_groups.json file directly"""
    try:
        if os.path.exists(GROUPS_FILE):
            # Read the file content
            with open(GROUPS_FILE, 'r') as f:
                groups_data = json.load(f)
                
            # Return JSON response
            return jsonify(groups_data)
        else:
            # Return empty array if file doesn't exist
            return jsonify([])
    except Exception as e:
        logger.error(f"Error serving groups JSON file: {str(e)}")
        return jsonify([])

# Run the app
if __name__ == '__main__':
    try:
        app.run(debug=True, host='0.0.0.0', port=9005)
    except OSError as e:
        if 'Address already in use' in str(e):
            print("Error: Port 9005 is already in use.")
            print("Please stop any running instance of the app first, or use a different port.")
            print("For example: app.run(debug=True, host='0.0.0.0', port=9006)")
        else:
            print(f"Error starting the app: {e}") 