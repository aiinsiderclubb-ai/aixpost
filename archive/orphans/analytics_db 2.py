"""
Analytics Database Module
Handles all database operations for post performance tracking and analytics
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

logger = logging.getLogger(__name__)

class AnalyticsDB:
    """Database manager for analytics and performance tracking"""
    
    def __init__(self, db_path='analytics.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with required tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Posts analytics table
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS post_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id VARCHAR(50),
                    group_id VARCHAR(50),
                    group_name VARCHAR(255),
                    group_url TEXT,
                    message_text TEXT,
                    message_hash VARCHAR(64),
                    template_used INTEGER,
                    posted_at TIMESTAMP,
                    
                    -- Metrics at different intervals
                    likes_1h INTEGER DEFAULT 0,
                    comments_1h INTEGER DEFAULT 0,
                    likes_24h INTEGER DEFAULT 0,
                    comments_24h INTEGER DEFAULT 0,
                    
                    -- Calculated metrics
                    engagement_rate_24h FLOAT DEFAULT 0,
                    performance_score FLOAT DEFAULT 0,
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                # Group performance aggregates
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS group_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id VARCHAR(50) UNIQUE,
                    group_name VARCHAR(255),
                    group_url TEXT,
                    
                    total_posts INTEGER DEFAULT 0,
                    total_successful_posts INTEGER DEFAULT 0,
                    total_failed_posts INTEGER DEFAULT 0,
                    
                    avg_likes FLOAT DEFAULT 0,
                    avg_comments FLOAT DEFAULT 0,
                    avg_engagement_rate FLOAT DEFAULT 0,
                    
                    post_success_rate FLOAT DEFAULT 0,
                    ban_risk_score FLOAT DEFAULT 0,
                    recommendation_score FLOAT DEFAULT 0,
                    
                    consecutive_failures INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                conn.commit()
                logger.info("Analytics database initialized successfully")

                # Backward-compatible schema upgrades
                # 1) Ensure user_id column exists in post_analytics
                try:
                    cursor.execute("PRAGMA table_info(post_analytics)")
                    cols = [r[1] for r in cursor.fetchall()]
                    if 'user_id' not in cols:
                        cursor.execute("ALTER TABLE post_analytics ADD COLUMN user_id INTEGER")
                        conn.commit()
                        logger.info("analytics_db: added user_id to post_analytics")
                    # 2) Ensure is_legacy column exists, default 0
                    if 'is_legacy' not in cols:
                        cursor.execute("ALTER TABLE post_analytics ADD COLUMN is_legacy BOOLEAN DEFAULT 0")
                        conn.commit()
                        logger.info("analytics_db: added is_legacy to post_analytics")
                        # Mark rows with NULL user_id as legacy
                        cursor.execute("UPDATE post_analytics SET is_legacy = 1 WHERE user_id IS NULL")
                        conn.commit()
                except Exception as e:
                    logger.warning(f"analytics_db: user_id add skipped: {e}")
                
        except Exception as e:
            logger.error(f"Error initializing analytics database: {e}")
            raise
    
    def save_post(self, group_id: str, group_name: str, group_url: str, 
                  message_text: str, template_id: Optional[int] = None,
                  user_id: Optional[int] = None) -> int:
        """Save a posted message for analytics tracking"""
        try:
            import hashlib
            message_hash = hashlib.md5(message_text.encode()).hexdigest()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                INSERT INTO post_analytics (
                    group_id, group_name, group_url, message_text, message_hash,
                    template_used, posted_at, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    group_id, group_name, group_url, message_text, message_hash,
                    template_id, datetime.now(), user_id
                ))
                
                post_analytics_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Saved post analytics for group {group_id}")
                return post_analytics_id
                
        except Exception as e:
            logger.error(f"Error saving post analytics: {e}")
            raise
    
    def update_group_stats(self, group_id: str, success: bool):
        """Update group performance statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get or create group performance record
                cursor.execute('''
                INSERT OR IGNORE INTO group_performance (group_id) VALUES (?)
                ''', (group_id,))
                
                if success:
                    cursor.execute('''
                    UPDATE group_performance SET
                        total_posts = total_posts + 1,
                        total_successful_posts = total_successful_posts + 1,
                        consecutive_failures = 0,
                        updated_at = ?
                    WHERE group_id = ?
                    ''', (datetime.now(), group_id))
                else:
                    cursor.execute('''
                    UPDATE group_performance SET
                        total_posts = total_posts + 1,
                        total_failed_posts = total_failed_posts + 1,
                        consecutive_failures = consecutive_failures + 1,
                        updated_at = ?
                    WHERE group_id = ?
                    ''', (datetime.now(), group_id))
                
                # Update success rate
                cursor.execute('''
                UPDATE group_performance SET
                    post_success_rate = CASE 
                        WHEN total_posts > 0 THEN 
                            CAST(total_successful_posts AS FLOAT) / total_posts 
                        ELSE 0 
                    END
                WHERE group_id = ?
                ''', (group_id,))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error updating group stats: {e}")
    
    def get_top_performing_groups(self, limit: int = 10) -> List[Dict]:
        """Get top performing groups by recommendation score"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                SELECT group_id, group_name, post_success_rate, avg_engagement_rate,
                       recommendation_score, total_posts, consecutive_failures
                FROM group_performance
                WHERE total_posts >= 1
                ORDER BY post_success_rate DESC, recommendation_score DESC
                LIMIT ?
                ''', (limit,))
                
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting top performing groups: {e}")
            return []
    
    def get_group_performance(self, group_id: str) -> Optional[Dict]:
        """Get performance metrics for a specific group"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                SELECT * FROM group_performance WHERE group_id = ?
                ''', (group_id,))
                
                row = cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    return dict(zip(columns, row))
                return None
                
        except Exception as e:
            logger.error(f"Error getting group performance: {e}")
            return None
    
    def log_error(self, group_id: str, group_name: str, error_type: str, 
                  error_message: str, context: Optional[Dict] = None):
        """Log posting error for spam analysis"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create spam_indicators table if it doesn't exist
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS spam_indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id VARCHAR(50),
                    group_name VARCHAR(255),
                    error_type VARCHAR(100),
                    error_message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                
                cursor.execute('''
                INSERT INTO spam_indicators (
                    group_id, group_name, error_type, error_message
                ) VALUES (?, ?, ?, ?)
                ''', (group_id, group_name, error_type, error_message))
                
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error logging spam indicator: {e}")
    
    def calculate_recommendation_scores(self):
        """Calculate and update recommendation scores for all groups"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Update recommendation scores based on multiple factors
                cursor.execute('''
                UPDATE group_performance SET
                    recommendation_score = (
                        (post_success_rate * 0.6) +
                        (CASE WHEN consecutive_failures = 0 THEN 0.4 ELSE 
                            CASE WHEN (0.4 - (consecutive_failures * 0.1)) > 0 
                                 THEN (0.4 - (consecutive_failures * 0.1)) 
                                 ELSE 0 END END)
                    ),
                    ban_risk_score = CASE 
                        WHEN consecutive_failures >= 3 THEN 0.8
                        WHEN consecutive_failures >= 2 THEN 0.6  
                        WHEN consecutive_failures >= 1 THEN 0.3
                        ELSE 0.1
                    END
                WHERE total_posts > 0
                ''')
                
                conn.commit()
                logger.info("Updated recommendation scores for all groups")
                
        except Exception as e:
            logger.error(f"Error calculating recommendation scores: {e}")
    
    def get_pending_analytics_checks(self) -> List[Dict]:
        """Get analytics checks that need to be performed (mock for now)"""
        # This is a simplified version for testing
        return []

# Global instance
analytics_db = AnalyticsDB()
