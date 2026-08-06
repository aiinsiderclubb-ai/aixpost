#!/usr/bin/env python3
"""
Facebook SaaS Platform - Application Entry Point
Production-ready launcher with proper error handling
"""

import os
import sys
from flask.cli import FlaskGroup
from app import create_app, db, celery
from app.models.user import User
from app.models.posting import PostingCampaign, FacebookGroup, MessageTemplate
from app.models.subscription import SubscriptionPlan, UserSubscription, PaymentHistory
import click


# Create Flask app
app = create_app()
cli = FlaskGroup(app)


@cli.command()
def init_db():
    """Initialize the database with tables and default data"""
    click.echo('Creating database tables...')
    db.create_all()
    
    # Create default subscription plans
    create_default_plans()
    
    click.echo('Database initialized successfully!')


@cli.command()
def create_admin():
    """Create an admin user"""
    email = click.prompt('Admin email')
    password = click.prompt('Admin password', hide_input=True)
    first_name = click.prompt('First name')
    last_name = click.prompt('Last name')
    
    # Check if user already exists
    existing_user = User.find_by_email(email)
    if existing_user:
        click.echo(f'User with email {email} already exists!')
        return
    
    # Create admin user
    admin = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        role='admin',
        email_verified=True,
        current_plan='PREMIUM'
    )
    admin.set_password(password)
    
    db.session.add(admin)
    db.session.commit()
    
    click.echo(f'Admin user {email} created successfully!')


@cli.command()
def reset_db():
    """Reset the database (WARNING: This will delete all data)"""
    if click.confirm('This will delete all data. Are you sure?'):
        click.echo('Dropping all tables...')
        db.drop_all()
        
        click.echo('Creating tables...')
        db.create_all()
        
        # Create default subscription plans
        create_default_plans()
        
        click.echo('Database reset successfully!')


@cli.command()
def seed_data():
    """Seed the database with sample data for development"""
    click.echo('Seeding database with sample data...')
    
    # Create sample users
    create_sample_users()
    
    click.echo('Sample data created successfully!')


def create_default_plans():
    """Create default subscription plans"""
    plans = [
        {
            'code': 'FREE',
            'name': 'Free Plan',
            'description': 'Perfect for getting started with basic posting features',
            'price_monthly': 0,
            'max_messages_per_month': 50,
            'max_groups': 10,
            'max_campaigns': 3,
            'max_templates': 5,
            'features': [
                'Basic posting',
                'Email support',
                'Up to 10 groups',
                '50 messages per month'
            ]
        },
        {
            'code': 'PLUS',
            'name': 'Plus Plan',
            'description': 'Great for small businesses with growing posting needs',
            'price_monthly': 49,
            'price_yearly': 490,
            'max_messages_per_month': 500,
            'max_groups': 100,
            'max_campaigns': 20,
            'max_templates': 50,
            'features': [
                'Advanced posting',
                'Message templates',
                'Basic analytics',
                'Priority support',
                'Up to 100 groups',
                '500 messages per month'
            ],
            'stripe_price_id_monthly': os.environ.get('STRIPE_PLUS_MONTHLY_PRICE_ID'),
            'stripe_price_id_yearly': os.environ.get('STRIPE_PLUS_YEARLY_PRICE_ID')
        },
        {
            'code': 'PREMIUM',
            'name': 'Premium Plan',
            'description': 'For power users and agencies with unlimited posting needs',
            'price_monthly': 99,
            'price_yearly': 990,
            'max_messages_per_month': 2000,
            'max_groups': 500,
            'max_campaigns': 100,
            'max_templates': 200,
            'features': [
                'Unlimited posting',
                'Advanced templates',
                'Full analytics',
                'Campaign scheduling',
                'API access',
                'VIP support',
                'Up to 500 groups',
                '2000 messages per month'
            ],
            'stripe_price_id_monthly': os.environ.get('STRIPE_PREMIUM_MONTHLY_PRICE_ID'),
            'stripe_price_id_yearly': os.environ.get('STRIPE_PREMIUM_YEARLY_PRICE_ID')
        }
    ]
    
    for plan_data in plans:
        existing_plan = SubscriptionPlan.find_by_code(plan_data['code'])
        if not existing_plan:
            plan = SubscriptionPlan(**plan_data)
            db.session.add(plan)
    
    db.session.commit()
    click.echo('Default subscription plans created')


def create_sample_users():
    """Create sample users for development"""
    # Sample regular user
    if not User.find_by_email('user@example.com'):
        user = User(
            email='user@example.com',
            first_name='John',
            last_name='Doe',
            email_verified=True,
            current_plan='FREE'
        )
        user.set_password('password123')
        db.session.add(user)
    
    # Sample premium user
    if not User.find_by_email('premium@example.com'):
        premium_user = User(
            email='premium@example.com',
            first_name='Jane',
            last_name='Smith',
            email_verified=True,
            current_plan='PREMIUM'
        )
        premium_user.set_password('password123')
        db.session.add(premium_user)
    
    # Sample admin user
    if not User.find_by_email('admin@example.com'):
        admin = User(
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            role='admin',
            email_verified=True,
            current_plan='PREMIUM'
        )
        admin.set_password('admin123')
        db.session.add(admin)
    
    db.session.commit()


@cli.command()
def test():
    """Run the test suite"""
    import pytest
    pytest.main(['-v', 'tests/'])


@cli.command()
def worker():
    """Start Celery worker"""
    celery.start(['worker', '--loglevel=info'])


@cli.command()
def beat():
    """Start Celery beat scheduler"""
    celery.start(['beat', '--loglevel=info'])


@cli.command()
def flower():
    """Start Flower monitoring for Celery"""
    celery.start(['flower'])


@cli.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=5000, help='Port to bind to')
@click.option('--debug', is_flag=True, help='Enable debug mode')
def runserver(host, port, debug):
    """Run the development server"""
    app.run(host=host, port=port, debug=debug)


@app.shell_context_processor
def make_shell_context():
    """Make database models available in Flask shell"""
    return {
        'db': db,
        'User': User,
        'PostingCampaign': PostingCampaign,
        'FacebookGroup': FacebookGroup,
        'MessageTemplate': MessageTemplate,
        'SubscriptionPlan': SubscriptionPlan,
        'UserSubscription': UserSubscription,
        'PaymentHistory': PaymentHistory
    }


if __name__ == '__main__':
    # Environment validation
    required_env_vars = [
        'DATABASE_URL',
        'REDIS_URL',
        'SECRET_KEY',
        'MAIL_USERNAME',
        'MAIL_PASSWORD'
    ]
    
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    
    if missing_vars and os.environ.get('FLASK_ENV') == 'production':
        print(f"ERROR: Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file or environment configuration")
        sys.exit(1)
    
    # Default to development if no environment is set
    if not os.environ.get('FLASK_ENV'):
        os.environ['FLASK_ENV'] = 'development'
    
    cli() 