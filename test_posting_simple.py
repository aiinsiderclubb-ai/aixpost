#!/usr/bin/env python3
"""
Simple test for improved Facebook posting system
"""

import sys
import os
from datetime import datetime

# Add the bot directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from fb_poster import FacebookGroupPoster

def simple_posting_test():
    """Simple test of the posting functionality"""
    
    print("=" * 60)
    print("Simple Facebook Posting Test")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test message
    test_message = """🧪 Тест улучшенной системы публикации

✅ Новые селекторы для русского интерфейса
✅ Система повторных попыток
✅ Улучшенная обработка ошибок

#тест #автоматизация"""

    print(f"Test message: {test_message[:50]}...")
    print()
    
    # Initialize the poster
    print("Initializing Facebook Group Poster...")
    bot = FacebookGroupPoster(headless=False)  # Visible mode for debugging
    
    try:
        # Test with one group
        success = bot.post_to_multiple_groups(
            message=test_message,
            groups_file="autofetched_groups.json" if os.path.exists("autofetched_groups.json") else "groups.txt",
            max_groups=1  # Test with just one group
        )
        
        # Get final stats
        stats = bot.get_status()
        
        print(f"\n" + "=" * 40)
        print("TEST RESULTS")
        print("=" * 40)
        print(f"Success: {success}")
        print(f"Posts completed: {stats.get('posts_completed', 0)}")
        print(f"Posts failed: {stats.get('posts_failed', 0)}")
        print(f"Status: {stats.get('status', 'Unknown')}")
        
        if success and stats.get('posts_completed', 0) > 0:
            print("\n✅ TEST PASSED! Improved posting system works!")
        else:
            print("\n❌ TEST FAILED! Check logs and screenshots.")
            
        return success
        
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        return False

if __name__ == "__main__":
    print("Simple Facebook Posting Test")
    print("This will test the improved posting system with one group")
    print()
    
    try:
        confirm = input("Proceed with test? (y/N): ")
        if confirm.lower() != 'y':
            print("Test cancelled.")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nTest cancelled.")
        sys.exit(0)
    
    result = simple_posting_test()
    sys.exit(0 if result else 1) 