"""
User model for Facebook SaaS Platform
Handles authentication, roles, and user management
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
import secrets
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy import Index

db = SQLAlchemy()
bcrypt = Bcrypt()


class User(UserMixin, db.Model):
    """User model with authentication and subscription management"""
    
    __tablename__ = 'users'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Authentication fields
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(255), unique=True)
    
    # Profile fields
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    timezone = db.Column(db.String(50), default='UTC')
    
    # Role and permissions
    role = db.Column(db.String(20), default='user')  # user, admin
    is_active = db.Column(db.Boolean, default=True)
    
    # Subscription fields
    current_plan = db.Column(db.String(20), default='FREE')  # FREE, PLUS, PREMIUM
    subscription_status = db.Column(db.String(20), default='active')  # active, canceled, expired
    subscription_id = db.Column(db.String(255))  # Stripe subscription ID
    
    # Usage tracking
    messages_sent_this_month = db.Column(db.Integer, default=0)
    last_message_reset = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Facebook credentials (encrypted)
    facebook_credentials = db.Column(JSON)  # Encrypted Facebook login data
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Password reset
    reset_token = db.Column(db.String(255), unique=True)
    reset_token_expires = db.Column(db.DateTime)
    
    # Relationships
    posting_campaigns = db.relationship('PostingCampaign', back_populates='user', lazy='dynamic')
    facebook_groups = db.relationship('FacebookGroup', back_populates='user', lazy='dynamic')
    analytics = db.relationship('PostingAnalytics', back_populates='user', lazy='dynamic')
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_users_email', 'email'),
        Index('idx_users_role', 'role'),
        Index('idx_users_current_plan', 'current_plan'),
        Index('idx_users_created_at', 'created_at'),
    )
    
    def __init__(self, **kwargs):
        """Initialize user with default values"""
        super(User, self).__init__(**kwargs)
        if not self.email_verification_token:
            self.email_verification_token = secrets.token_urlsafe(32)
    
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
    
    def verify_email(self, token: str) -> bool:
        """Verify email with token"""
        if self.email_verification_token == token:
            self.email_verified = True
            self.email_verification_token = None
            return True
        return False
    
    def is_admin(self) -> bool:
        """Check if user is admin"""
        return self.role == 'admin'
    
    def get_plan_limits(self) -> Dict[str, Any]:
        """Get current plan limits"""
        from app.config import Config
        return Config.SUBSCRIPTION_PLANS.get(self.current_plan, Config.SUBSCRIPTION_PLANS['FREE'])
    
    def can_send_messages(self, count: int = 1) -> bool:
        """Check if user can send specified number of messages"""
        # Reset monthly counter if needed
        self.reset_monthly_usage_if_needed()
        
        limits = self.get_plan_limits()
        return self.messages_sent_this_month + count <= limits['max_messages']
    
    def reset_monthly_usage_if_needed(self) -> None:
        """Reset monthly usage counter if new month"""
        now = datetime.utcnow()
        if (not self.last_message_reset or 
            now.month != self.last_message_reset.month or 
            now.year != self.last_message_reset.year):
            self.messages_sent_this_month = 0
            self.last_message_reset = now
    
    def increment_message_count(self, count: int = 1) -> None:
        """Increment sent messages counter"""
        self.reset_monthly_usage_if_needed()
        self.messages_sent_this_month += count
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get user usage statistics"""
        self.reset_monthly_usage_if_needed()
        limits = self.get_plan_limits()
        
        return {
            'messages_sent': self.messages_sent_this_month,
            'messages_limit': limits['max_messages'],
            'messages_remaining': limits['max_messages'] - self.messages_sent_this_month,
            'groups_limit': limits['max_groups'],
            'current_plan': self.current_plan,
            'subscription_status': self.subscription_status,
            'reset_date': self.last_message_reset
        }
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert user to dictionary"""
        user_dict = {
            'id': str(self.id),
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
            'timezone': self.timezone,
            'usage_stats': self.get_usage_stats()
        }
        
        if include_sensitive:
            user_dict.update({
                'subscription_id': self.subscription_id,
                'facebook_credentials': self.facebook_credentials
            })
        
        return user_dict
    
    @classmethod
    def find_by_email(cls, email: str) -> Optional['User']:
        """Find user by email address"""
        return cls.query.filter_by(email=email.lower()).first()
    
    @classmethod
    def find_by_reset_token(cls, token: str) -> Optional['User']:
        """Find user by reset token"""
        return cls.query.filter_by(reset_token=token).first()
    
    @classmethod
    def find_by_verification_token(cls, token: str) -> Optional['User']:
        """Find user by email verification token"""
        return cls.query.filter_by(email_verification_token=token).first()
    
    @classmethod
    def get_admin_users(cls) -> List['User']:
        """Get all admin users"""
        return cls.query.filter_by(role='admin', is_active=True).all()
    
    @classmethod
    def get_users_by_plan(cls, plan: str) -> List['User']:
        """Get users by subscription plan"""
        return cls.query.filter_by(current_plan=plan, is_active=True).all()
    
    @classmethod
    def get_users_with_expired_subscriptions(cls) -> List['User']:
        """Get users with expired subscriptions"""
        return cls.query.filter_by(subscription_status='expired', is_active=True).all()
    
    def update_last_login(self) -> None:
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def deactivate(self) -> None:
        """Deactivate user account"""
        self.is_active = False
        self.subscription_status = 'canceled'
        db.session.commit()
    
    def activate(self) -> None:
        """Activate user account"""
        self.is_active = True
        if self.subscription_status == 'canceled':
            self.subscription_status = 'active'
        db.session.commit()
    
    def upgrade_plan(self, new_plan: str, subscription_id: str = None) -> None:
        """Upgrade user subscription plan"""
        self.current_plan = new_plan
        self.subscription_status = 'active'
        if subscription_id:
            self.subscription_id = subscription_id
        db.session.commit()
    
    def downgrade_to_free(self) -> None:
        """Downgrade user to free plan"""
        self.current_plan = 'FREE'
        self.subscription_status = 'active'
        self.subscription_id = None
        db.session.commit()
    
    def __repr__(self) -> str:
        return f'<User {self.email}>' 