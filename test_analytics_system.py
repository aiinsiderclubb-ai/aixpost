#!/usr/bin/env python3

"""
Test script for the Analytics System
Tests database, scheduler, and post analyzer functionality
"""

import os
import sys
import logging
from datetime import datetime, timedelta

# Add bot directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

def test_analytics_database():
    """Test analytics database functionality"""
    print("🔍 Testing Analytics Database...")
    
    try:
        from analytics_db import analytics_db
        
        # Test 1: Save a test post
        print("📝 Testing post saving...")
        post_id = analytics_db.save_post(
            group_id="test_group_123",
            group_name="Test Group",
            group_url="https://facebook.com/groups/test_group_123",
            message_text="Test message with emojis 🎉 and special chars",
            template_id=1
        )
        print(f"✅ Post saved with ID: {post_id}")
        
        # Test 2: Update group stats
        print("📊 Testing group stats update...")
        analytics_db.update_group_stats("test_group_123", True)  # Success
        analytics_db.update_group_stats("test_group_123", False)  # Failure
        print("✅ Group stats updated")
        
        # Test 3: Log an error
        print("⚠️ Testing error logging...")
        analytics_db.log_error(
            group_id="test_group_123",
            group_name="Test Group", 
            error_type="Test Error",
            error_message="This is a test error message"
        )
        print("✅ Error logged")
        
        # Test 4: Get group performance
        print("📈 Testing group performance retrieval...")
        performance = analytics_db.get_group_performance("test_group_123")
        if performance:
            print(f"✅ Group performance: {performance['total_posts']} posts, {performance['post_success_rate']:.1f}% success rate")
        else:
            print("❌ No performance data found")
        
        # Test 5: Get top performing groups
        print("🏆 Testing top performing groups...")
        top_groups = analytics_db.get_top_performing_groups(5)
        print(f"✅ Found {len(top_groups)} top performing groups")
        for group in top_groups:
            print(f"  - {group['group_id']}: {group['post_success_rate']:.1f}% success")
        
        return True
        
    except Exception as e:
        print(f"❌ Analytics database test failed: {e}")
        return False

def test_analytics_scheduler():
    """Test analytics scheduler functionality"""
    print("\n🔍 Testing Analytics Scheduler...")
    
    try:
        from analytics_scheduler import AnalyticsScheduler
        
        # Test scheduler creation
        scheduler = AnalyticsScheduler()
        print("✅ Analytics scheduler created")
        
        # Test force analytics check
        print("🔧 Testing force analytics check...")
        scheduler.force_analytics_check('recommendations')
        print("✅ Force analytics check completed")
        
        return True
        
    except Exception as e:
        print(f"❌ Analytics scheduler test failed: {e}")
        return False

def test_post_analyzer():
    """Test post analyzer functionality"""
    print("\n🔍 Testing Post Analyzer...")
    
    try:
        from post_analyzer import PostAnalyzer
        
        # Test analyzer creation
        analyzer = PostAnalyzer()
        print("✅ Post analyzer created")
        
        # Test text extraction methods
        print("📝 Testing text extraction...")
        test_texts = [
            "15 likes",
            "1.2K reactions", 
            "5M views",
            "1,234 comments"
        ]
        
        for text in test_texts:
            number = analyzer._extract_number_from_text(text)
            print(f"  '{text}' -> {number}")
        
        print("✅ Text extraction tests completed")
        
        # Test performance score calculation
        print("🎯 Testing performance score calculation...")
        metrics = {
            'likes': 25,
            'comments': 8,
            'shares': 2
        }
        score = analyzer._calculate_performance_score(metrics)
        print(f"✅ Performance score: {score}")
        
        return True
        
    except Exception as e:
        print(f"❌ Post analyzer test failed: {e}")
        return False

def test_fb_poster_integration():
    """Test integration with fb_poster.py"""
    print("\n🔍 Testing FB Poster Integration...")
    
    try:
        from fb_poster import FacebookGroupPoster
        
        # Test bot creation with analytics
        bot = FacebookGroupPoster(headless=True)
        print("✅ FB Poster created")
        
        # Check analytics integration
        if hasattr(bot, 'analytics_enabled') and bot.analytics_enabled:
            print("✅ Analytics integration enabled")
            if bot.analytics_db:
                print("✅ Analytics database connected")
            else:
                print("⚠️ Analytics database not connected")
        else:
            print("⚠️ Analytics integration not enabled")
        
        return True
        
    except Exception as e:
        print(f"❌ FB Poster integration test failed: {e}")
        return False

def generate_sample_data():
    """Generate sample analytics data for testing"""
    print("\n🔍 Generating Sample Data...")
    
    try:
        from analytics_db import analytics_db
        
        sample_groups = [
            {"id": "group_001", "name": "Tech Entrepreneurs", "url": "https://facebook.com/groups/tech_entrepreneurs"},
            {"id": "group_002", "name": "Marketing Pros", "url": "https://facebook.com/groups/marketing_pros"},
            {"id": "group_003", "name": "Startup Community", "url": "https://facebook.com/groups/startup_community"},
            {"id": "group_004", "name": "Digital Nomads", "url": "https://facebook.com/groups/digital_nomads"},
            {"id": "group_005", "name": "Business Network", "url": "https://facebook.com/groups/business_network"}
        ]
        
        sample_messages = [
            "Check out this amazing new product! 🚀",
            "Looking for feedback on my startup idea 💡",
            "Free webinar this Friday - don't miss it! 📚",
            "Anyone interested in a business partnership? 🤝",
            "Just launched our new service! Thoughts? ⭐"
        ]
        
        print("📝 Creating sample posts...")
        
        for i, group in enumerate(sample_groups):
            # Create multiple posts per group
            for j in range(3):
                post_id = analytics_db.save_post(
                    group_id=group["id"],
                    group_name=group["name"],
                    group_url=group["url"],
                    message_text=sample_messages[j % len(sample_messages)],
                    template_id=(j % 3) + 1
                )
                
                # Simulate different success rates for different groups
                success_rate = 0.8 if i < 2 else 0.6 if i < 4 else 0.4
                success = (j % 10) < (success_rate * 10)
                
                analytics_db.update_group_stats(group["id"], success)
                
                if not success:
                    analytics_db.log_error(
                        group_id=group["id"],
                        group_name=group["name"],
                        error_type="Post failed",
                        error_message="Could not post to group"
                    )
        
        print("✅ Sample data generated")
        
        # Calculate recommendations
        analytics_db.calculate_recommendation_scores()
        print("✅ Recommendation scores calculated")
        
        # Show results
        top_groups = analytics_db.get_top_performing_groups(3)
        print("\n🏆 Top Performing Groups:")
        for i, group in enumerate(top_groups, 1):
            print(f"  {i}. {group['group_id']} - Score: {group.get('recommendation_score', 0):.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Sample data generation failed: {e}")
        return False

def main():
    """Run all analytics tests"""
    print("🎯 FACEBOOK AUTOMATION ANALYTICS SYSTEM TESTS")
    print("=" * 60)
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Run tests
    tests = [
        ("Analytics Database", test_analytics_database),
        ("Analytics Scheduler", test_analytics_scheduler), 
        ("Post Analyzer", test_post_analyzer),
        ("FB Poster Integration", test_fb_poster_integration),
        ("Sample Data Generation", generate_sample_data)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:<25} {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All analytics tests passed! System is ready.")
        return True
    else:
        print("⚠️ Some tests failed. Check the errors above.")
        return False

if __name__ == "__main__":
    main() 