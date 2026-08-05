#!/usr/bin/env python3
"""
Database migration script to add new fields to users table
"""
import sqlite3
import os
import sys
from pathlib import Path

def get_db_path():
    """Get the database path"""
    basedir = Path(__file__).parent
    return basedir / 'test_app.db'

def migrate_database():
    """Migrate the database to add new fields"""
    db_path = get_db_path()
    
    if not db_path.exists():
        print("Database doesn't exist. Creating new database...")
        # Import and create all tables
        from run_test_v2 import app, db
        with app.app_context():
            db.create_all()
            print("✅ New database created successfully")
        return
    
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if new fields exist
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add missing fields
        fields_to_add = [
            ('messages_used', 'INTEGER DEFAULT 0'),
            ('messages_limit', 'INTEGER DEFAULT 100')
        ]
        
        for field_name, field_definition in fields_to_add:
            if field_name not in columns:
                alter_query = f"ALTER TABLE users ADD COLUMN {field_name} {field_definition}"
                print(f"Adding field: {field_name}")
                cursor.execute(alter_query)
                print(f"✅ Added {field_name}")
            else:
                print(f"✅ Field {field_name} already exists")
        
        # Create audit_logs table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action VARCHAR(100) NOT NULL,
                old_value VARCHAR(255),
                new_value VARCHAR(255),
                ip_address VARCHAR(45),
                user_agent VARCHAR(500),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES users(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        print("✅ audit_logs table created/verified")
        
        conn.commit()
        print("✅ Database migration completed successfully")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database() 