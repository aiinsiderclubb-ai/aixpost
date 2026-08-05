"""
Simplified models for testing Facebook SaaS Platform
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid
import secrets
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin

# Note: db and bcrypt will be imported from run_test
db = None
bcrypt = None

def init_models(database, bcrypt_instance):
    """Initialize models with database and bcrypt instances"""
    global db, bcrypt
    db = database
    bcrypt = bcrypt_instance


class User(UserMixin, db.Model):
    """Simplified User model for testing"""
    
    __tablename__ = 'users'
    
    # Primary key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Authentication fields
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    
    # Profile fields
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    
    # Role and permissions
    role = db.Column(db.String(20), default='user')  # user, admin
    is_active = db.Column(db.Boolean, default=True)
    
    # Subscription fields
    current_plan = db.Column(db.String(20), default='FREE')  # FREE, PLUS, PREMIUM
    subscription_status = db.Column(db.String(20), default='active')
    
    # Usage tracking
    messages_sent_this_month = db.Column(db.Integer, default=0)
    last_message_reset = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Password reset
    reset_token = db.Column(db.String(255), unique=True)
    reset_token_expires = db.Column(db.DateTime)
    
    def __init__(self, **kwargs):
        """Initialize user with default values"""
        super(User, self).__init__(**kwargs)
    
    def set_password(self, password: str) -> None:
        """Set user password with bcrypt hashing"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password: str) -> bool:
        """Check if provided password matches the hash"""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def get_reset_token(self, expires_in: int = 3600) -> str:
        """Generate password reset token"""
        token = secrets.token_urlsafe(32)
        self.reset_token = token
        self.reset_token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
        return token
    
    def verify_reset_token(self, token: str) -> bool:
        """Verify password reset token"""
        if not self.reset_token or not self.reset_token_expires:
            return False
        if datetime.utcnow() > self.reset_token_expires:
            return False
        return self.reset_token == token
    
    def clear_reset_token(self) -> None:
        """Clear password reset token"""
        self.reset_token = None
        self.reset_token_expires = None
    
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
    
    def can_send_messages(self, count: int = 1) -> bool:
        """Check if user can send specified number of messages"""
        limits = self.get_plan_limits()
        return self.messages_sent_this_month + count <= limits['max_messages']
    
    def increment_message_count(self, count: int = 1) -> None:
        """Increment sent messages counter"""
        self.messages_sent_this_month += count
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get user usage statistics"""
        limits = self.get_plan_limits()
        
        return {
            'messages_sent': self.messages_sent_this_month,
            'messages_limit': limits['max_messages'],
            'messages_remaining': limits['max_messages'] - self.messages_sent_this_month,
            'groups_limit': limits['max_groups'],
            'current_plan': self.current_plan,
            'subscription_status': self.subscription_status
        }
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert user to dictionary"""
        user_dict = {
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
        
        return user_dict
    
    def update_last_login(self) -> None:
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
    
    def __repr__(self) -> str:
        return f'<User {self.email}>'


class PostingCampaign(db.Model):
    """Simplified Posting Campaign model"""
    
    __tablename__ = 'posting_campaigns'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f'<PostingCampaign {self.name}>'


class FacebookGroup(db.Model):
    """Simplified Facebook Group model"""
    
    __tablename__ = 'facebook_groups'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    facebook_id = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f'<FacebookGroup {self.name}>'


class MessageTemplate(db.Model):
    """Simplified Message Template model"""
    
    __tablename__ = 'message_templates'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f'<MessageTemplate {self.name}>'


class SubscriptionPlan(db.Model):
    """Simplified Subscription Plan model"""
    
    __tablename__ = 'subscription_plans'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price_monthly = db.Column(db.Numeric(10, 2), default=0)
    max_messages_per_month = db.Column(db.Integer, default=50)
    max_groups = db.Column(db.Integer, default=10)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f'<SubscriptionPlan {self.code}>'


class UserSubscription(db.Model):
    """Simplified User Subscription model"""
    
    __tablename__ = 'user_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    status = db.Column(db.String(20), default='active')
    stripe_subscription_id = db.Column(db.String(255))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f'<UserSubscription {self.user_id}-{self.plan_id}>'


class PaymentHistory(db.Model):
    """Simplified Payment History model"""
    
    __tablename__ = 'payment_history'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='USD')
    status = db.Column(db.String(20), default='completed')
    stripe_payment_id = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f'<PaymentHistory {self.user_id}-{self.amount}>' 