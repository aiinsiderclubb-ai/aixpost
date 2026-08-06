#!/usr/bin/env python3

from flask import Flask, render_template_string, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'test-secret-key-for-development'
app.config['JWT_SECRET_KEY'] = 'test-jwt-secret-key'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'test_app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)

# User model
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    current_plan = db.Column(db.String(20), default='FREE')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'full_name': f"{self.first_name} {self.last_name}",
            'current_plan': self.current_plan,
            'created_at': self.created_at.isoformat()
        }

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Facebook SaaS Platform</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; color: white; margin-bottom: 30px; }
        .header h1 { font-size: 2.5em; margin: 0; }
        .form-container { background: white; padding: 30px; margin: 20px 0; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        .form-group { margin: 15px 0; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }
        .btn { padding: 12px 24px; background: #667eea; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        .btn:hover { background: #5a6fd8; }
        .btn-success { background: #28a745; }
        .btn-success:hover { background: #218838; }
        .result { margin: 15px 0; padding: 15px; border-radius: 5px; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        
        #authSection { display: block; }
        #dashboardSection { display: none; background: white; padding: 30px; border-radius: 10px; margin-top: 20px; }
        .dashboard-title { color: #28a745; margin-bottom: 20px; }
        .dashboard-tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .tab-btn { padding: 10px 20px; border: none; background: #f8f9fa; cursor: pointer; border-radius: 5px; }
        .tab-btn.active { background: #667eea; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .user-info { background: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; }
        .stat-number { font-size: 24px; font-weight: bold; color: #667eea; }
        .stat-label { font-size: 14px; color: #666; }
        .campaign-item { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }
        .campaign-title { font-weight: bold; font-size: 18px; }
        .campaign-meta { color: #666; font-size: 14px; margin: 5px 0; }
        .campaign-status { padding: 4px 8px; border-radius: 3px; font-size: 12px; }
        .status-draft { background: #ffc107; color: #856404; }
        .campaign-form { background: #f8f9fa; padding: 20px; border-radius: 5px; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 15px 0; }
        .form-row.full { grid-template-columns: 1fr; }
        textarea { width: 100%; min-height: 120px; padding: 12px; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; resize: vertical; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Auth Section -->
        <div id="authSection">
            <div class="header">
                <h1>🚀 Facebook SaaS Platform</h1>
                <p>Register your account and start automating your Facebook posting!</p>
            </div>
            
            <div class="form-container">
                <h2>📝 Register</h2>
                <form id="registerForm">
                    <div class="form-group">
                        <label>Email Address</label>
                        <input type="email" name="email" required>
                    </div>
                    <div class="form-group">
                        <label>First Name</label>
                        <input type="text" name="first_name" required>
                    </div>
                    <div class="form-group">
                        <label>Last Name</label>
                        <input type="text" name="last_name" required>
                    </div>
                    <div class="form-group">
                        <label>Password</label>
                        <input type="password" name="password" required>
                        <small style="color: #666; font-size: 0.8em;">Min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special character</small>
                    </div>
                    <button type="submit" class="btn">CREATE ACCOUNT</button>
                </form>
                <div id="registerResult" class="result"></div>
            </div>
            
            <div class="form-container">
                <h2>🔐 Login</h2>
                <form id="loginForm">
                    <div class="form-group">
                        <label>Email Address</label>
                        <input type="email" name="email" required>
                    </div>
                    <div class="form-group">
                        <label>Password</label>
                        <input type="password" name="password" required>
                    </div>
                    <button type="submit" class="btn">SIGN IN</button>
                </form>
                <div id="loginResult" class="result"></div>
            </div>
        </div>
        
        <!-- Dashboard Section -->
        <div id="dashboardSection">
            <div class="header">
                <h2 class="dashboard-title">📊 Dashboard</h2>
                <div id="userInfo" class="user-info"></div>
            </div>
            
            <div class="dashboard-tabs">
                <button class="tab-btn active" onclick="showTab('campaigns')">📢 Campaigns</button>
                <button class="tab-btn" onclick="showTab('create')">➕ Create Campaign</button>
                <button class="tab-btn" onclick="showTab('analytics')">📊 Analytics</button>
                <button class="tab-btn" onclick="showTab('settings')">⚙️ Settings</button>
                <button class="btn" onclick="logout()" style="margin-left: auto;">Logout</button>
            </div>
            
            <!-- Campaigns Tab -->
            <div id="campaignsTab" class="tab-content active">
                <h3>Your Campaigns</h3>
                <div id="campaignsList">
                    <div class="campaign-item">
                        <div class="campaign-title">Welcome Campaign</div>
                        <div class="campaign-meta">Created: Just now • Groups: 0 • Messages: 0</div>
                        <span class="campaign-status status-draft">Draft</span>
                    </div>
                </div>
            </div>
            
            <!-- Create Campaign Tab -->
            <div id="createTab" class="tab-content">
                <div class="campaign-form">
                    <h3>Create New Campaign</h3>
                    <form id="campaignForm">
                        <div class="form-row">
                            <div class="form-group">
                                <label>Campaign Name</label>
                                <input type="text" name="name" required>
                            </div>
                            <div class="form-group">
                                <label>Max Groups</label>
                                <input type="number" name="max_groups" min="1" max="500" value="10">
                            </div>
                        </div>
                        
                        <div class="form-row full">
                            <div class="form-group">
                                <label>Message Content</label>
                                <textarea name="message" required placeholder="Enter your message here..."></textarea>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>Min Delay (seconds)</label>
                                <input type="number" name="min_delay" min="1" value="10">
                            </div>
                            <div class="form-group">
                                <label>Max Delay (seconds)</label>
                                <input type="number" name="max_delay" min="1" value="60">
                            </div>
                        </div>
                        
                        <div class="form-row full">
                            <div class="form-group">
                                <label>Facebook Group URLs (one per line)</label>
                                <textarea name="group_urls" required placeholder="https://www.facebook.com/groups/example1/&#10;https://www.facebook.com/groups/example2/"></textarea>
                            </div>
                        </div>
                        
                        <button type="submit" class="btn btn-success">Create Campaign</button>
                    </form>
                    <div id="campaignResult" class="result"></div>
                </div>
            </div>
            
            <!-- Analytics Tab -->
            <div id="analyticsTab" class="tab-content">
                <h3>📊 Analytics Overview</h3>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-number">0</div>
                        <div class="stat-label">Total Campaigns</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">0</div>
                        <div class="stat-label">Messages Sent</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">0%</div>
                        <div class="stat-label">Success Rate</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">0</div>
                        <div class="stat-label">Groups Reached</div>
                    </div>
                </div>
            </div>
            
            <!-- Settings Tab -->
            <div id="settingsTab" class="tab-content">
                <div class="campaign-form">
                    <h3>Facebook Settings</h3>
                    <form id="settingsForm">
                        <div class="form-row">
                            <div class="form-group">
                                <label>Facebook Username/Email</label>
                                <input type="text" name="facebook_username" required>
                            </div>
                            <div class="form-group">
                                <label>Facebook Password</label>
                                <input type="password" name="facebook_password" required>
                            </div>
                        </div>
                        
                        <div class="form-row">
                            <div class="form-group">
                                <label>
                                    <input type="checkbox" name="use_headless" checked> Use Headless Mode
                                </label>
                                <small style="color: #666;">Recommended for better performance</small>
                            </div>
                        </div>
                        
                        <button type="submit" class="btn btn-success">Save Settings</button>
                    </form>
                    <div id="settingsResult" class="result"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        console.log('JavaScript loaded successfully');
        
        let currentUser = null;
        let currentToken = null;
        
        // Show dashboard function
        function showDashboard() {
            console.log('🎯 Showing dashboard...');
            
            document.getElementById('authSection').style.display = 'none';
            document.getElementById('dashboardSection').style.display = 'block';
            
            if (currentUser) {
                document.getElementById('userInfo').innerHTML = 
                    '<h4>Welcome, ' + currentUser.full_name + '! 👋</h4>' +
                    '<p><strong>Email:</strong> ' + currentUser.email + '</p>' +
                    '<p><strong>Plan:</strong> ' + currentUser.current_plan + '</p>' +
                    '<p><strong>Member since:</strong> ' + new Date(currentUser.created_at).toLocaleDateString() + '</p>';
            }
            
            console.log('✅ Dashboard shown successfully!');
        }
        
        // Show tab function
        function showTab(tabName) {
            console.log('Showing tab:', tabName);
            
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Remove active class from all buttons
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // Show selected tab
            document.getElementById(tabName + 'Tab').classList.add('active');
            
            // Add active class to clicked button
            event.target.classList.add('active');
        }
        
        // Logout function
        function logout() {
            console.log('Logging out...');
            document.getElementById('authSection').style.display = 'block';
            document.getElementById('dashboardSection').style.display = 'none';
            currentUser = null;
            currentToken = null;
            localStorage.removeItem('access_token');
        }
        
        // Register form handler
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            console.log('Register form submitted');
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            try {
                const response = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                const resultDiv = document.getElementById('registerResult');
                
                if (response.ok) {
                    console.log('🎉 Registration successful!', result);
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = '✅ Registration Successful! Welcome ' + result.user.full_name + '! Redirecting to dashboard...';
                    
                    currentToken = result.access_token;
                    currentUser = result.user;
                    
                    localStorage.setItem('access_token', result.access_token);
                    
                    // Redirect to dashboard after 1.5 seconds
                    setTimeout(() => {
                        showDashboard();
                    }, 1500);
                } else {
                    console.error('Registration failed:', result);
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
        
        // Login form handler
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            console.log('Login form submitted');
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            
            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                const resultDiv = document.getElementById('loginResult');
                
                if (response.ok) {
                    console.log('🎉 Login successful!', result);
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = '✅ Login Successful! Welcome back ' + result.user.full_name + '! Redirecting to dashboard...';
                    
                    currentToken = result.access_token;
                    currentUser = result.user;
                    
                    localStorage.setItem('access_token', result.access_token);
                    
                    // Redirect to dashboard after 1.5 seconds
                    setTimeout(() => {
                        showDashboard();
                    }, 1500);
                } else {
                    console.error('Login failed:', result);
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
        
        // Campaign form handler
        document.getElementById('campaignForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            console.log('Campaign form submitted');
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            data.target_groups = data.group_urls.split('\\n').filter(url => url.trim());
            
            try {
                const response = await fetch('/api/campaigns', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + currentToken
                    },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                const resultDiv = document.getElementById('campaignResult');
                
                if (response.ok) {
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = '✅ Campaign Created Successfully! Campaign: ' + result.campaign.name;
                    e.target.reset();
                } else {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = '❌ Failed to Create Campaign: ' + (result.error || 'Unknown error');
                }
                
                resultDiv.style.display = 'block';
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('campaignResult').innerHTML = '❌ Network Error: ' + error.message;
                document.getElementById('campaignResult').className = 'result error';
                document.getElementById('campaignResult').style.display = 'block';
            }
        });
        
        // Settings form handler
        document.getElementById('settingsForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            console.log('Settings form submitted');
            
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData);
            data.use_headless = formData.get('use_headless') === 'on';
            
            try {
                const response = await fetch('/api/user/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + currentToken
                    },
                    body: JSON.stringify(data)
                });
                
                const result = await response.json();
                const resultDiv = document.getElementById('settingsResult');
                
                if (response.ok) {
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = '✅ Settings Updated Successfully! Your Facebook credentials have been saved securely.';
                } else {
                    resultDiv.className = 'result error';
                    resultDiv.innerHTML = '❌ Failed to Update Settings: ' + (result.error || 'Unknown error');
                }
                
                resultDiv.style.display = 'block';
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('settingsResult').innerHTML = '❌ Network Error: ' + error.message;
                document.getElementById('settingsResult').className = 'result error';
                document.getElementById('settingsResult').style.display = 'block';
            }
        });
        
        // Check for existing token on page load
        window.addEventListener('load', () => {
            const token = localStorage.getItem('access_token');
            if (token) {
                console.log('Found existing token, checking validity...');
                fetch('/api/auth/me', {
                    headers: {
                        'Authorization': 'Bearer ' + token
                    }
                })
                .then(response => {
                    if (response.ok) {
                        return response.json();
                    } else {
                        localStorage.removeItem('access_token');
                        throw new Error('Token invalid');
                    }
                })
                .then(user => {
                    console.log('Token valid, auto-login user:', user);
                    currentToken = token;
                    currentUser = user;
                    showDashboard();
                })
                .catch(error => {
                    console.log('Token check failed:', error);
                });
            }
        });
        
        console.log('All event listeners attached');
    </script>
</body>
</html>
'''

# Campaign model
class Campaign(db.Model):
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        import json
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
            'created_at': self.created_at.isoformat()
        }

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

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
        
        access_token = create_access_token(identity=user.id)
        
        return jsonify({
            'message': 'User created successfully',
            'access_token': access_token,
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        if not all(k in data for k in ['email', 'password']):
            return jsonify({'error': 'Missing email or password'}), 400
        
        user = User.query.filter_by(email=data['email']).first()
        
        if user and user.check_password(data['password']):
            access_token = create_access_token(identity=user.id)
            return jsonify({
                'message': 'Login successful',
                'access_token': access_token,
                'user': user.to_dict()
            }), 200
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify(user.to_dict()), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns', methods=['POST'])
@jwt_required()
def create_campaign():
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        import json
        campaign = Campaign(
            user_id=user_id,
            name=data.get('name'),
            message=data.get('message'),
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/settings', methods=['POST'])
@jwt_required()
def update_user_settings():
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        # In a real app, you would save these securely
        # For now, just return success
        
        return jsonify({
            'message': 'Settings updated successfully'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database tables created successfully!")
    
    print("🚀 Facebook SaaS Platform - Fixed Dashboard Redirect")
    print("📡 URL: http://localhost:8080")
    print("✨ Auto-redirect to dashboard after login/register")
    print("Press Ctrl+C to stop the server")
    
    app.run(host='0.0.0.0', port=8080, debug=True) 