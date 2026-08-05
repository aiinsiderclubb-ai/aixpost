"""
Admin API Blueprint for Facebook SaaS Platform
Provides admin-only endpoints for user management, analytics, and system control
"""

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc, asc
from datetime import datetime, timedelta
from typing import Dict, Any, List
import uuid

from app.models.user import User
from app.models.subscription import UserSubscription, PaymentHistory, UsageTracker
from app.models.posting import PostingCampaign, FacebookGroup, PostResult
from app.utils.decorators import admin_required
from app.utils.helpers import validate_email, sanitize_input
from app import db, limiter

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
@limiter.limit("100 per hour")
def get_all_users():
    """Get all users with pagination and filtering"""
    try:
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
        
        # Order by creation date (newest first)
        query = query.order_by(desc(User.created_at))
        
        # Paginate
        pagination = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        users = []
        for user in pagination.items:
            user_dict = user.to_dict()
            # Add additional admin info
            user_dict['usage_stats'] = user.get_usage_stats()
            user_dict['campaigns_count'] = PostingCampaign.query.filter_by(user_id=user.id).count()
            user_dict['groups_count'] = FacebookGroup.query.filter_by(user_id=user.id).count()
            users.append(user_dict)
        
        return jsonify({
            'users': users,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            },
            'filters': {
                'search': search,
                'plan': plan_filter,
                'status': status_filter
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Admin get users error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve users'}), 500

@admin_bp.route('/users/<user_id>', methods=['GET'])
@jwt_required()
@admin_required
@limiter.limit("200 per hour")
def get_user_details(user_id):
    """Get detailed user information"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get detailed user info
        user_dict = user.to_dict(include_sensitive=True)
        
        # Add campaigns
        campaigns = PostingCampaign.query.filter_by(user_id=user_id).order_by(desc(PostingCampaign.created_at)).limit(10).all()
        user_dict['recent_campaigns'] = [c.to_dict() for c in campaigns]
        
        # Add groups
        groups = FacebookGroup.query.filter_by(user_id=user_id).order_by(desc(FacebookGroup.created_at)).limit(10).all()
        user_dict['recent_groups'] = [g.to_dict() for g in groups]
        
        # Add usage history
        usage_history = UsageTracker.get_user_usage_history(user_id, months=6)
        user_dict['usage_history'] = [u.to_dict() for u in usage_history]
        
        # Add subscription info
        subscription = UserSubscription.get_user_subscription(user_id)
        user_dict['subscription'] = subscription.to_dict() if subscription else None
        
        # Add payment history
        payments = PaymentHistory.get_user_payments(user_id, limit=10)
        user_dict['payment_history'] = [p.to_dict() for p in payments]
        
        return jsonify({'user': user_dict}), 200
        
    except Exception as e:
        current_app.logger.error(f"Admin get user details error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve user details'}), 500

@admin_bp.route('/users/<user_id>', methods=['PUT'])
@jwt_required()
@admin_required
@limiter.limit("50 per hour")
def update_user(user_id):
    """Update user information"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        
        # Validate and update allowed fields
        if 'first_name' in data:
            user.first_name = sanitize_input(data['first_name'])
        if 'last_name' in data:
            user.last_name = sanitize_input(data['last_name'])
        if 'current_plan' in data:
            if data['current_plan'] in ['FREE', 'PLUS', 'PREMIUM']:
                old_plan = user.current_plan
                user.current_plan = data['current_plan']
                current_app.logger.info(f"Admin changed user {user.email} plan from {old_plan} to {data['current_plan']}")
            else:
                return jsonify({'error': 'Invalid plan'}), 400
        if 'is_active' in data:
            user.is_active = bool(data['is_active'])
        if 'role' in data:
            if data['role'] in ['user', 'admin']:
                user.role = data['role']
            else:
                return jsonify({'error': 'Invalid role'}), 400
        if 'subscription_status' in data:
            user.subscription_status = data['subscription_status']
        
        user.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': 'User updated successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Admin update user error: {str(e)}")
        return jsonify({'error': 'Failed to update user'}), 500

@admin_bp.route('/users/<user_id>/reset-usage', methods=['POST'])
@jwt_required()
@admin_required
@limiter.limit("20 per hour")
def reset_user_usage(user_id):
    """Reset user's monthly usage counter"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        old_usage = user.messages_sent_this_month
        user.messages_sent_this_month = 0
        user.last_message_reset = datetime.utcnow()
        db.session.commit()
        
        current_app.logger.info(f"Admin reset usage for user {user.email} (was {old_usage})")
        
        return jsonify({
            'message': 'Usage reset successfully',
            'old_usage': old_usage,
            'new_usage': 0
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Admin reset usage error: {str(e)}")
        return jsonify({'error': 'Failed to reset usage'}), 500

@admin_bp.route('/analytics/overview', methods=['GET'])
@jwt_required()
@admin_required
@limiter.limit("100 per hour")
def get_platform_analytics():
    """Get platform-wide analytics"""
    try:
        # User statistics
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        new_users_this_month = User.query.filter(
            User.created_at >= datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ).count()
        
        # Plan distribution
        plan_stats = db.session.query(
            User.current_plan,
            func.count(User.id).label('count')
        ).group_by(User.current_plan).all()
        
        # Campaign statistics
        total_campaigns = PostingCampaign.query.count()
        active_campaigns = PostingCampaign.query.filter_by(status='running').count()
        completed_campaigns = PostingCampaign.query.filter_by(status='completed').count()
        
        # Usage statistics
        total_messages = db.session.query(func.sum(User.messages_sent_this_month)).scalar() or 0
        total_groups = FacebookGroup.query.count()
        
        # Revenue statistics (if subscriptions exist)
        revenue_stats = db.session.query(
            func.sum(PaymentHistory.amount).label('total_revenue'),
            func.count(PaymentHistory.id).label('total_payments')
        ).filter(PaymentHistory.status == 'succeeded').first()
        
        return jsonify({
            'users': {
                'total': total_users,
                'active': active_users,
                'new_this_month': new_users_this_month,
                'inactive': total_users - active_users
            },
            'plans': {
                'distribution': {plan: count for plan, count in plan_stats}
            },
            'campaigns': {
                'total': total_campaigns,
                'active': active_campaigns,
                'completed': completed_campaigns,
                'failed': PostingCampaign.query.filter_by(status='failed').count()
            },
            'usage': {
                'total_messages': total_messages,
                'total_groups': total_groups,
                'avg_messages_per_user': round(total_messages / max(active_users, 1), 2)
            },
            'revenue': {
                'total': float(revenue_stats.total_revenue) if revenue_stats.total_revenue else 0,
                'transactions': revenue_stats.total_payments if revenue_stats.total_payments else 0
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Admin analytics error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve analytics'}), 500

@admin_bp.route('/system/health', methods=['GET'])
@jwt_required()
@admin_required
@limiter.limit("60 per hour")
def get_system_health():
    """Get system health information"""
    try:
        # Database connection test
        db_healthy = True
        try:
            db.session.execute('SELECT 1')
        except Exception:
            db_healthy = False
        
        # System metrics
        health_data = {
            'database': {
                'healthy': db_healthy,
                'connections': 'active'  # Could be enhanced with real connection pool stats
            },
            'cache': {
                'healthy': True  # Could be enhanced with Redis health check
            },
            'background_tasks': {
                'healthy': True  # Could be enhanced with Celery health check
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(health_data), 200
        
    except Exception as e:
        current_app.logger.error(f"Admin system health error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve system health'}), 500

@admin_bp.route('/logs', methods=['GET'])
@jwt_required()
@admin_required
@limiter.limit("30 per hour")
def get_system_logs():
    """Get system logs (implementation depends on logging setup)"""
    try:
        # This would need to be implemented based on your logging system
        # For now, return recent user activities
        
        recent_users = User.query.filter(
            User.last_login.isnot(None)
        ).order_by(desc(User.last_login)).limit(50).all()
        
        logs = []
        for user in recent_users:
            logs.append({
                'timestamp': user.last_login.isoformat() if user.last_login else None,
                'user': user.email,
                'action': 'login',
                'ip': 'N/A',  # Would need to be tracked
                'user_agent': 'N/A'  # Would need to be tracked
            })
        
        return jsonify({'logs': logs}), 200
        
    except Exception as e:
        current_app.logger.error(f"Admin logs error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve logs'}), 500

@admin_bp.route('/campaigns', methods=['GET'])
@jwt_required()
@admin_required
@limiter.limit("100 per hour")
def get_all_campaigns():
    """Get all campaigns across all users"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status_filter = request.args.get('status', '').strip()
        
        query = PostingCampaign.query
        
        if status_filter:
            query = query.filter(PostingCampaign.status == status_filter)
        
        query = query.order_by(desc(PostingCampaign.created_at))
        
        pagination = query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        campaigns = []
        for campaign in pagination.items:
            campaign_dict = campaign.to_dict()
            # Add user info
            user = User.query.get(campaign.user_id)
            campaign_dict['user'] = {
                'email': user.email,
                'name': f"{user.first_name} {user.last_name}",
                'plan': user.current_plan
            } if user else None
            campaigns.append(campaign_dict)
        
        return jsonify({
            'campaigns': campaigns,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Admin campaigns error: {str(e)}")
        return jsonify({'error': 'Failed to retrieve campaigns'}), 500 