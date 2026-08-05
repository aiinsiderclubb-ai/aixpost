#!/usr/bin/env python3
"""
Database initialization script
Creates tables and default admin user
"""

import os
import sys
from run_test_v2 import app, db, User, bcrypt

def init_database():
    """Initialize database with default admin user"""
    
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Check if admin user exists
        admin_user = User.query.filter_by(email='admin@test.com').first()
        
        if not admin_user:
            # Create default admin user
            admin_user = User(
                email='admin@test.com',
                first_name='Admin',
                last_name='User',
                role='admin',
                current_plan='PREMIUM',
                is_active=True
            )
            admin_user.set_password('Admin123!')
            
            db.session.add(admin_user)
            db.session.commit()
            
            print("✅ Database initialized successfully!")
            print("✅ Default admin user created:")
            print(f"   Email: admin@test.com")
            print(f"   Password: Admin123!")
            print(f"   Role: admin")
        else:
            print("✅ Database already initialized!")
            print("✅ Admin user already exists:")
            print(f"   Email: {admin_user.email}")
            print(f"   Role: {admin_user.role}")
        
        # Create test user
        test_user = User.query.filter_by(email='test@test.com').first()
        
        if not test_user:
            test_user = User(
                email='test@test.com',
                first_name='Test',
                last_name='User',
                role='user',
                current_plan='FREE',
                is_active=True
            )
            test_user.set_password('Test123!')
            
            db.session.add(test_user)
            db.session.commit()
            
            print("✅ Test user created:")
            print(f"   Email: test@test.com")
            print(f"   Password: Test123!")
            print(f"   Role: user")
        else:
            print("✅ Test user already exists!")
            
        print("\n🚀 Database ready for use!")

if __name__ == '__main__':
    init_database() 