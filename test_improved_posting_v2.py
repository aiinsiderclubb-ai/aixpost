#!/usr/bin/env python3
"""
Enhanced Test Script for Facebook Posting with Improved Button Clicking
Test the updated posting logic with better button detection and clicking methods
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.fb_poster import FacebookGroupPoster
import time

def main():
    print("🧪 Enhanced Facebook Posting Test v2")
    print("=" * 50)
    
    # Test message (shorter and cleaner for testing)
    test_message = """Привет! Тестирую улучшенный бот для постинга.

Основные улучшения:
✅ Множественные методы клика по кнопке
✅ Лучшее обнаружение кнопки "Отправить"
✅ JavaScript fallback для надежности
✅ Проверка статуса поста

Тест проводится: """ + time.strftime("%H:%M:%S")
    
    print(f"📝 Test Message Length: {len(test_message)} characters")
    print(f"📝 Test Message Preview: {test_message[:100]}...")
    print()
    
    # Initialize poster with visible browser for debugging
    poster = FacebookGroupPoster(headless=False)
    
    try:
        print("🔧 Setting up WebDriver...")
        if not poster.setup_driver():
            print("❌ WebDriver setup failed!")
            return
        
        print("🔐 Logging in to Facebook...")
        if not poster.login():
            print("❌ Login failed!")
            return
        
        print("✅ Login successful!")
        print()
        
        # Test with one group for focused testing
        test_groups_file = 'temp_groups.txt'
        groups = poster.load_groups(test_groups_file)
        
        if not groups:
            print(f"❌ No groups found in {test_groups_file}")
            return
        
        print(f"📋 Found {len(groups)} groups, testing with first group")
        test_group = groups[0]
        print(f"🎯 Testing group: {test_group}")
        print()
        
        print("🚀 Starting enhanced posting test...")
        print("=" * 30)
        
        # Post to the test group
        success = poster.post_to_group(test_group, test_message)
        
        print()
        print("=" * 30)
        if success:
            print("✅ POSTING TEST COMPLETED SUCCESSFULLY!")
            print("🎉 Enhanced button clicking logic worked!")
        else:
            print("❌ POSTING TEST FAILED")
            print("🔍 Check the logs and screenshots for details")
        
        print()
        print("📊 Test Summary:")
        print(f"   • Group tested: {test_group}")
        print(f"   • Message length: {len(test_message)} chars")
        print(f"   • Result: {'SUCCESS' if success else 'FAILED'}")
        
        # Keep browser open for manual inspection
        print()
        print("🔍 Browser kept open for manual inspection...")
        print("📁 Check screenshots folder for debugging images")
        print("Press Ctrl+C to exit when ready")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Exiting test...")
    
    except Exception as e:
        print(f"❌ Test error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("🧹 Cleaning up...")
        poster.cleanup()

if __name__ == "__main__":
    main() 