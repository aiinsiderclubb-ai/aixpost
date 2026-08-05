"""
Posting models for Facebook SaaS Platform
Handles posting campaigns, Facebook groups, and message templates
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
import json
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID, JSON, ARRAY
from sqlalchemy import Index, Text

db = SQLAlchemy()


class PostingCampaign(db.Model):
    """Model for posting campaigns"""
    
    __tablename__ = 'posting_campaigns'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User relationship
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', back_populates='posting_campaigns')
    
    # Campaign details
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(Text)
    
    # Message content
    message_content = db.Column(Text, nullable=False)
    use_templates = db.Column(db.Boolean, default=False)
    template_mode = db.Column(db.String(20), default='random')  # random, sequence
    
    # Target groups
    target_groups = db.Column(JSON)  # List of group IDs or URLs
    max_groups = db.Column(db.Integer, default=50)
    
    # Campaign settings
    min_delay_seconds = db.Column(db.Integer, default=10)
    max_delay_seconds = db.Column(db.Integer, default=60)
    batch_size = db.Column(db.Integer, default=10)
    
    # Status and scheduling
    status = db.Column(db.String(20), default='draft')  # draft, scheduled, running, completed, failed, canceled
    scheduled_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Results tracking
    total_groups = db.Column(db.Integer, default=0)
    successful_posts = db.Column(db.Integer, default=0)
    failed_posts = db.Column(db.Integer, default=0)
    
    # Error handling
    error_message = db.Column(Text)
    last_error_at = db.Column(db.DateTime)
    
    # Facebook session settings
    facebook_username = db.Column(db.String(255))
    use_headless = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    post_results = db.relationship('PostResult', back_populates='campaign', lazy='dynamic')
    
    # Indexes
    __table_args__ = (
        Index('idx_campaigns_user_id', 'user_id'),
        Index('idx_campaigns_status', 'status'),
        Index('idx_campaigns_scheduled_at', 'scheduled_at'),
        Index('idx_campaigns_created_at', 'created_at'),
    )
    
    def to_dict(self, include_results: bool = False) -> Dict[str, Any]:
        """Convert campaign to dictionary"""
        campaign_dict = {
            'id': str(self.id),
            'name': self.name,
            'description': self.description,
            'message_content': self.message_content,
            'use_templates': self.use_templates,
            'template_mode': self.template_mode,
            'target_groups': self.target_groups,
            'max_groups': self.max_groups,
            'min_delay_seconds': self.min_delay_seconds,
            'max_delay_seconds': self.max_delay_seconds,
            'batch_size': self.batch_size,
            'status': self.status,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'total_groups': self.total_groups,
            'successful_posts': self.successful_posts,
            'failed_posts': self.failed_posts,
            'error_message': self.error_message,
            'facebook_username': self.facebook_username,
            'use_headless': self.use_headless,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_results:
            campaign_dict['post_results'] = [
                result.to_dict() for result in self.post_results.all()
            ]
        
        return campaign_dict
    
    def get_success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_groups == 0:
            return 0.0
        return (self.successful_posts / self.total_groups) * 100
    
    def can_be_started(self) -> bool:
        """Check if campaign can be started"""
        return self.status in ['draft', 'scheduled', 'failed']
    
    def can_be_canceled(self) -> bool:
        """Check if campaign can be canceled"""
        return self.status in ['scheduled', 'running']
    
    def start(self) -> None:
        """Mark campaign as started"""
        self.status = 'running'
        self.started_at = datetime.utcnow()
        db.session.commit()
    
    def complete(self, successful: int, failed: int) -> None:
        """Mark campaign as completed"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.successful_posts = successful
        self.failed_posts = failed
        self.total_groups = successful + failed
        db.session.commit()
    
    def fail(self, error_message: str) -> None:
        """Mark campaign as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.last_error_at = datetime.utcnow()
        db.session.commit()
    
    def cancel(self) -> None:
        """Cancel campaign"""
        self.status = 'canceled'
        db.session.commit()
    
    @classmethod
    def get_user_campaigns(cls, user_id: str, status: str = None) -> List['PostingCampaign']:
        """Get campaigns for a user"""
        query = cls.query.filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status)
        return query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_scheduled_campaigns(cls) -> List['PostingCampaign']:
        """Get campaigns scheduled to run"""
        return cls.query.filter(
            cls.status == 'scheduled',
            cls.scheduled_at <= datetime.utcnow()
        ).all()


class FacebookGroup(db.Model):
    """Model for Facebook groups"""
    
    __tablename__ = 'facebook_groups'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User relationship
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', back_populates='facebook_groups')
    
    # Group information
    facebook_group_id = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(1000), nullable=False)
    description = db.Column(Text)
    member_count = db.Column(db.Integer)
    
    # Classification
    language = db.Column(db.String(10))
    category = db.Column(db.String(100))
    tags = db.Column(ARRAY(db.String))
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_blocked = db.Column(db.Boolean, default=False)
    last_posted = db.Column(db.DateTime)
    
    # Performance metrics
    total_posts = db.Column(db.Integer, default=0)
    successful_posts = db.Column(db.Integer, default=0)
    failed_posts = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_fetched = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    post_results = db.relationship('PostResult', back_populates='group', lazy='dynamic')
    
    # Indexes
    __table_args__ = (
        Index('idx_groups_user_id', 'user_id'),
        Index('idx_groups_facebook_id', 'facebook_group_id'),
        Index('idx_groups_language', 'language'),
        Index('idx_groups_is_active', 'is_active'),
        Index('idx_groups_last_posted', 'last_posted'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert group to dictionary"""
        return {
            'id': str(self.id),
            'facebook_group_id': self.facebook_group_id,
            'name': self.name,
            'url': self.url,
            'description': self.description,
            'member_count': self.member_count,
            'language': self.language,
            'category': self.category,
            'tags': self.tags,
            'is_active': self.is_active,
            'is_blocked': self.is_blocked,
            'last_posted': self.last_posted.isoformat() if self.last_posted else None,
            'total_posts': self.total_posts,
            'successful_posts': self.successful_posts,
            'failed_posts': self.failed_posts,
            'success_rate': self.get_success_rate(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_fetched': self.last_fetched.isoformat() if self.last_fetched else None,
        }
    
    def get_success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_posts == 0:
            return 0.0
        return (self.successful_posts / self.total_posts) * 100
    
    def record_post_attempt(self, success: bool) -> None:
        """Record a posting attempt"""
        self.total_posts += 1
        if success:
            self.successful_posts += 1
            self.last_posted = datetime.utcnow()
        else:
            self.failed_posts += 1
        db.session.commit()
    
    def block(self) -> None:
        """Block group from posting"""
        self.is_blocked = True
        self.is_active = False
        db.session.commit()
    
    def unblock(self) -> None:
        """Unblock group for posting"""
        self.is_blocked = False
        self.is_active = True
        db.session.commit()
    
    @classmethod
    def get_user_groups(cls, user_id: str, active_only: bool = True) -> List['FacebookGroup']:
        """Get groups for a user"""
        query = cls.query.filter_by(user_id=user_id)
        if active_only:
            query = query.filter_by(is_active=True, is_blocked=False)
        return query.order_by(cls.name).all()
    
    @classmethod
    def find_by_facebook_id(cls, user_id: str, facebook_group_id: str) -> Optional['FacebookGroup']:
        """Find group by Facebook ID and user"""
        return cls.query.filter_by(
            user_id=user_id,
            facebook_group_id=facebook_group_id
        ).first()


class PostResult(db.Model):
    """Model for individual post results"""
    
    __tablename__ = 'post_results'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Relationships
    campaign_id = db.Column(UUID(as_uuid=True), db.ForeignKey('posting_campaigns.id'), nullable=False)
    campaign = db.relationship('PostingCampaign', back_populates='post_results')
    
    group_id = db.Column(UUID(as_uuid=True), db.ForeignKey('facebook_groups.id'), nullable=False)
    group = db.relationship('FacebookGroup', back_populates='post_results')
    
    # Post details
    message_sent = db.Column(Text, nullable=False)
    template_used = db.Column(db.String(255))
    
    # Result
    success = db.Column(db.Boolean, nullable=False)
    error_message = db.Column(Text)
    screenshot_path = db.Column(db.String(500))
    
    # Timing
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow)
    duration_seconds = db.Column(db.Float)
    
    # Indexes
    __table_args__ = (
        Index('idx_results_campaign_id', 'campaign_id'),
        Index('idx_results_group_id', 'group_id'),
        Index('idx_results_success', 'success'),
        Index('idx_results_attempted_at', 'attempted_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            'id': str(self.id),
            'campaign_id': str(self.campaign_id),
            'group_id': str(self.group_id),
            'group_name': self.group.name if self.group else None,
            'message_sent': self.message_sent,
            'template_used': self.template_used,
            'success': self.success,
            'error_message': self.error_message,
            'screenshot_path': self.screenshot_path,
            'attempted_at': self.attempted_at.isoformat() if self.attempted_at else None,
            'duration_seconds': self.duration_seconds,
        }
    
    @classmethod
    def get_campaign_results(cls, campaign_id: str) -> List['PostResult']:
        """Get all results for a campaign"""
        return cls.query.filter_by(campaign_id=campaign_id).order_by(cls.attempted_at).all()
    
    @classmethod
    def get_group_results(cls, group_id: str, limit: int = 10) -> List['PostResult']:
        """Get recent results for a group"""
        return cls.query.filter_by(group_id=group_id).order_by(
            cls.attempted_at.desc()
        ).limit(limit).all()


class MessageTemplate(db.Model):
    """Model for message templates"""
    
    __tablename__ = 'message_templates'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User relationship
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    
    # Template details
    name = db.Column(db.String(255), nullable=False)
    content = db.Column(Text, nullable=False)
    variables = db.Column(JSON)  # Available variables and their options
    category = db.Column(db.String(100))
    
    # Usage statistics
    usage_count = db.Column(db.Integer, default=0)
    last_used = db.Column(db.DateTime)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_templates_user_id', 'user_id'),
        Index('idx_templates_category', 'category'),
        Index('idx_templates_is_active', 'is_active'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary"""
        return {
            'id': str(self.id),
            'name': self.name,
            'content': self.content,
            'variables': self.variables,
            'category': self.category,
            'usage_count': self.usage_count,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def increment_usage(self) -> None:
        """Increment usage counter"""
        self.usage_count += 1
        self.last_used = datetime.utcnow()
        db.session.commit()
    
    @classmethod
    def get_user_templates(cls, user_id: str, active_only: bool = True) -> List['MessageTemplate']:
        """Get templates for a user"""
        query = cls.query.filter_by(user_id=user_id)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(cls.name).all() 