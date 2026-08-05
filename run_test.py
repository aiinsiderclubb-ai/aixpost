#!/usr/bin/env python3
"""
Facebook SaaS Platform - Quick Test Runner
Simple launcher for testing with SQLite
"""

import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from config_test import TestConfig

# Create Flask app
app = Flask(__name__)
app.config.from_object(TestConfig)

# Initialize extensions
db = SQLAlchemy(app)
jwt = JWTManager(app)
mail = Mail(app)
cors = CORS(app)
bcrypt = Bcrypt(app)

# Import simplified models
from models_simple import (
    User, PostingCampaign, FacebookGroup, MessageTemplate, 
    SubscriptionPlan, UserSubscription, PaymentHistory
)

# Create tables
with app.app_context():
    db.create_all()
    print("Database tables created successfully!")

# Basic routes for testing
@app.route('/')
def home():
    return '''
    <h1>Facebook SaaS Platform - Test Mode</h1>
    <p>Server is running successfully!</p>
    <p>Available endpoints:</p>
    <ul>
        <li><a href="/api/auth/register">POST /api/auth/register</a> - Register new user</li>
        <li><a href="/api/auth/login">POST /api/auth/login</a> - Login user</li>
        <li><a href="/api/auth/me">GET /api/auth/me</a> - Get current user (requires JWT)</li>
    </ul>
    <p>Database: SQLite (test_app.db)</p>
    <p>Port: 8080</p>
    '''

@app.route('/health')
def health():
    return {'status': 'healthy', 'database': 'sqlite', 'mode': 'test'}

# Register simplified API blueprints
from auth_test import auth_bp
app.register_blueprint(auth_bp, url_prefix='/api/auth')

if __name__ == '__main__':
    print("Starting Facebook SaaS Platform in test mode...")
    print("URL: http://localhost:8080")
    print("Database: SQLite (test_app.db)")
    print("Press Ctrl+C to stop the server")
    
    app.run(host='0.0.0.0', port=8080, debug=True) 