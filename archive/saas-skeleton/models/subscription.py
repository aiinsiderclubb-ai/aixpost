"""
Subscription models for Facebook SaaS Platform
Handles subscription plans, payments, and billing
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy import Index, Text

db = SQLAlchemy()


class SubscriptionPlan(db.Model):
    """Model for subscription plans"""
    
    __tablename__ = 'subscription_plans'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Plan details
    code = db.Column(db.String(50), unique=True, nullable=False)  # FREE, PLUS, PREMIUM
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(Text)
    
    # Pricing
    price_monthly = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    price_yearly = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3), default='USD')
    
    # Limits
    max_messages_per_month = db.Column(db.Integer, nullable=False)
    max_groups = db.Column(db.Integer, nullable=False)
    max_campaigns = db.Column(db.Integer, default=10)
    max_templates = db.Column(db.Integer, default=10)
    
    # Features (JSON array)
    features = db.Column(JSON, default=list)
    
    # Stripe integration
    stripe_price_id_monthly = db.Column(db.String(255))
    stripe_price_id_yearly = db.Column(db.String(255))
    stripe_product_id = db.Column(db.String(255))
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    subscriptions = db.relationship('UserSubscription', back_populates='plan', lazy='dynamic')
    
    # Indexes
    __table_args__ = (
        Index('idx_plans_code', 'code'),
        Index('idx_plans_is_active', 'is_active'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to dictionary"""
        return {
            'id': str(self.id),
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'price_monthly': float(self.price_monthly),
            'price_yearly': float(self.price_yearly) if self.price_yearly else None,
            'currency': self.currency,
            'max_messages_per_month': self.max_messages_per_month,
            'max_groups': self.max_groups,
            'max_campaigns': self.max_campaigns,
            'max_templates': self.max_templates,
            'features': self.features,
            'is_active': self.is_active,
            'is_featured': self.is_featured,
            'stripe_price_id_monthly': self.stripe_price_id_monthly,
            'stripe_price_id_yearly': self.stripe_price_id_yearly,
        }
    
    @classmethod
    def get_active_plans(cls) -> List['SubscriptionPlan']:
        """Get all active subscription plans"""
        return cls.query.filter_by(is_active=True).order_by(cls.price_monthly).all()
    
    @classmethod
    def find_by_code(cls, code: str) -> Optional['SubscriptionPlan']:
        """Find plan by code"""
        return cls.query.filter_by(code=code, is_active=True).first()
    
    @classmethod
    def find_by_stripe_price_id(cls, price_id: str) -> Optional['SubscriptionPlan']:
        """Find plan by Stripe price ID"""
        return cls.query.filter(
            (cls.stripe_price_id_monthly == price_id) |
            (cls.stripe_price_id_yearly == price_id)
        ).first()


class UserSubscription(db.Model):
    """Model for user subscriptions"""
    
    __tablename__ = 'user_subscriptions'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User relationship
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    
    # Plan relationship
    plan_id = db.Column(UUID(as_uuid=True), db.ForeignKey('subscription_plans.id'), nullable=False)
    plan = db.relationship('SubscriptionPlan', back_populates='subscriptions')
    
    # Subscription details
    stripe_subscription_id = db.Column(db.String(255), unique=True)
    stripe_customer_id = db.Column(db.String(255))
    
    # Status
    status = db.Column(db.String(50), nullable=False, default='active')
    # active, past_due, canceled, unpaid, trialing, incomplete, incomplete_expired
    
    # Billing cycle
    billing_cycle = db.Column(db.String(20), default='monthly')  # monthly, yearly
    
    # Dates
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    trial_start = db.Column(db.DateTime)
    trial_end = db.Column(db.DateTime)
    canceled_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_subscriptions_user_id', 'user_id'),
        Index('idx_subscriptions_stripe_id', 'stripe_subscription_id'),
        Index('idx_subscriptions_status', 'status'),
        Index('idx_subscriptions_period_end', 'current_period_end'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert subscription to dictionary"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'plan': self.plan.to_dict() if self.plan else None,
            'stripe_subscription_id': self.stripe_subscription_id,
            'status': self.status,
            'billing_cycle': self.billing_cycle,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'current_period_start': self.current_period_start.isoformat() if self.current_period_start else None,
            'current_period_end': self.current_period_end.isoformat() if self.current_period_end else None,
            'trial_start': self.trial_start.isoformat() if self.trial_start else None,
            'trial_end': self.trial_end.isoformat() if self.trial_end else None,
            'canceled_at': self.canceled_at.isoformat() if self.canceled_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'is_active': self.is_active(),
            'days_remaining': self.get_days_remaining(),
        }
    
    def is_active(self) -> bool:
        """Check if subscription is currently active"""
        if self.status not in ['active', 'trialing']:
            return False
        if self.current_period_end and datetime.utcnow() > self.current_period_end:
            return False
        return True
    
    def is_trial(self) -> bool:
        """Check if subscription is in trial period"""
        if self.status != 'trialing':
            return False
        if not self.trial_end:
            return False
        return datetime.utcnow() <= self.trial_end
    
    def get_days_remaining(self) -> Optional[int]:
        """Get days remaining in current period"""
        if not self.current_period_end:
            return None
        remaining = self.current_period_end - datetime.utcnow()
        return max(0, remaining.days)
    
    def cancel(self) -> None:
        """Cancel subscription"""
        self.status = 'canceled'
        self.canceled_at = datetime.utcnow()
        db.session.commit()
    
    def reactivate(self) -> None:
        """Reactivate subscription"""
        self.status = 'active'
        self.canceled_at = None
        db.session.commit()
    
    @classmethod
    def find_by_stripe_id(cls, stripe_subscription_id: str) -> Optional['UserSubscription']:
        """Find subscription by Stripe ID"""
        return cls.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
    
    @classmethod
    def get_user_subscription(cls, user_id: str) -> Optional['UserSubscription']:
        """Get current subscription for user"""
        return cls.query.filter_by(user_id=user_id).order_by(cls.created_at.desc()).first()
    
    @classmethod
    def get_expiring_subscriptions(cls, days: int = 7) -> List['UserSubscription']:
        """Get subscriptions expiring in specified days"""
        expiry_date = datetime.utcnow() + timedelta(days=days)
        return cls.query.filter(
            cls.status == 'active',
            cls.current_period_end <= expiry_date
        ).all()


class PaymentHistory(db.Model):
    """Model for payment history"""
    
    __tablename__ = 'payment_history'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User relationship
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    
    # Subscription relationship (optional for one-time payments)
    subscription_id = db.Column(UUID(as_uuid=True), db.ForeignKey('user_subscriptions.id'))
    
    # Payment details
    stripe_payment_intent_id = db.Column(db.String(255), unique=True)
    stripe_invoice_id = db.Column(db.String(255))
    
    # Amount and currency
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='USD')
    
    # Status
    status = db.Column(db.String(50), nullable=False)
    # succeeded, pending, failed, canceled, refunded
    
    # Payment method
    payment_method = db.Column(db.String(50))  # card, bank_transfer, etc.
    payment_method_details = db.Column(JSON)  # Last 4 digits, brand, etc.
    
    # Description
    description = db.Column(db.String(500))
    
    # Timestamps
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_payments_user_id', 'user_id'),
        Index('idx_payments_stripe_id', 'stripe_payment_intent_id'),
        Index('idx_payments_status', 'status'),
        Index('idx_payments_paid_at', 'paid_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert payment to dictionary"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'subscription_id': str(self.subscription_id) if self.subscription_id else None,
            'stripe_payment_intent_id': self.stripe_payment_intent_id,
            'stripe_invoice_id': self.stripe_invoice_id,
            'amount': float(self.amount),
            'currency': self.currency,
            'status': self.status,
            'payment_method': self.payment_method,
            'payment_method_details': self.payment_method_details,
            'description': self.description,
            'paid_at': self.paid_at.isoformat() if self.paid_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def get_user_payments(cls, user_id: str, limit: int = 20) -> List['PaymentHistory']:
        """Get payment history for user"""
        return cls.query.filter_by(user_id=user_id).order_by(
            cls.paid_at.desc()
        ).limit(limit).all()
    
    @classmethod
    def find_by_stripe_payment_intent(cls, payment_intent_id: str) -> Optional['PaymentHistory']:
        """Find payment by Stripe payment intent ID"""
        return cls.query.filter_by(stripe_payment_intent_id=payment_intent_id).first()


class UsageTracker(db.Model):
    """Model for tracking monthly usage"""
    
    __tablename__ = 'usage_tracker'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User relationship
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'), nullable=False)
    
    # Period
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    
    # Usage metrics
    messages_sent = db.Column(db.Integer, default=0)
    campaigns_created = db.Column(db.Integer, default=0)
    groups_targeted = db.Column(db.Integer, default=0)
    
    # Limits (snapshot of plan limits at the time)
    plan_code = db.Column(db.String(50))
    max_messages = db.Column(db.Integer)
    max_groups = db.Column(db.Integer)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_usage_user_period', 'user_id', 'year', 'month'),
        Index('idx_usage_year_month', 'year', 'month'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert usage to dictionary"""
        return {
            'id': str(self.id),
            'user_id': str(self.user_id),
            'year': self.year,
            'month': self.month,
            'messages_sent': self.messages_sent,
            'campaigns_created': self.campaigns_created,
            'groups_targeted': self.groups_targeted,
            'plan_code': self.plan_code,
            'max_messages': self.max_messages,
            'max_groups': self.max_groups,
            'usage_percentage': self.get_usage_percentage(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def get_usage_percentage(self) -> float:
        """Get usage percentage for messages"""
        if not self.max_messages or self.max_messages == 0:
            return 0.0
        return min(100.0, (self.messages_sent / self.max_messages) * 100)
    
    def increment_messages(self, count: int = 1) -> None:
        """Increment message count"""
        self.messages_sent += count
        db.session.commit()
    
    def increment_campaigns(self, count: int = 1) -> None:
        """Increment campaign count"""
        self.campaigns_created += count
        db.session.commit()
    
    def set_groups_targeted(self, count: int) -> None:
        """Set groups targeted count"""
        self.groups_targeted = max(self.groups_targeted, count)
        db.session.commit()
    
    @classmethod
    def get_or_create_current_usage(cls, user_id: str, plan_code: str = None) -> 'UsageTracker':
        """Get or create current month usage tracker"""
        now = datetime.utcnow()
        
        usage = cls.query.filter_by(
            user_id=user_id,
            year=now.year,
            month=now.month
        ).first()
        
        if not usage:
            from app.models.user import User
            user = User.query.get(user_id)
            plan_limits = user.get_plan_limits() if user else {}
            
            usage = cls(
                user_id=user_id,
                year=now.year,
                month=now.month,
                plan_code=plan_code or (user.current_plan if user else 'FREE'),
                max_messages=plan_limits.get('max_messages', 50),
                max_groups=plan_limits.get('max_groups', 10)
            )
            db.session.add(usage)
            db.session.commit()
        
        return usage
    
    @classmethod
    def get_user_usage_history(cls, user_id: str, months: int = 6) -> List['UsageTracker']:
        """Get usage history for user"""
        return cls.query.filter_by(user_id=user_id).order_by(
            cls.year.desc(), cls.month.desc()
        ).limit(months).all()


class BillingEvent(db.Model):
    """Model for billing events and webhooks"""
    
    __tablename__ = 'billing_events'
    
    # Primary key
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Event details
    stripe_event_id = db.Column(db.String(255), unique=True, nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    
    # Associated objects
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id'))
    subscription_id = db.Column(UUID(as_uuid=True), db.ForeignKey('user_subscriptions.id'))
    
    # Event data
    data = db.Column(JSON)
    
    # Processing status
    processed = db.Column(db.Boolean, default=False)
    processed_at = db.Column(db.DateTime)
    error_message = db.Column(Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_events_stripe_id', 'stripe_event_id'),
        Index('idx_events_type', 'event_type'),
        Index('idx_events_processed', 'processed'),
        Index('idx_events_created_at', 'created_at'),
    )
    
    def mark_processed(self) -> None:
        """Mark event as processed"""
        self.processed = True
        self.processed_at = datetime.utcnow()
        db.session.commit()
    
    def mark_failed(self, error: str) -> None:
        """Mark event processing as failed"""
        self.error_message = error
        db.session.commit()
    
    @classmethod
    def find_by_stripe_id(cls, stripe_event_id: str) -> Optional['BillingEvent']:
        """Find event by Stripe ID"""
        return cls.query.filter_by(stripe_event_id=stripe_event_id).first()
    
    @classmethod
    def get_unprocessed_events(cls) -> List['BillingEvent']:
        """Get unprocessed events"""
        return cls.query.filter_by(processed=False).order_by(cls.created_at).all() 