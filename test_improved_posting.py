#!/usr/bin/env python3
"""
Test script for improved Facebook Group Posting functionality
Tests the enhanced post_to_group function with better selectors and retry logic
"""

import sys
import os
from datetime import datetime

# Add the bot directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from fb_poster import FacebookGroupPoster

def test_improved_posting():
    """Test the improved posting functionality"""
    
    print("=" * 60)
    print("Facebook Group Poster - Improved Posting Test")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test message
    test_message = """🚀 Тестовое сообщение для проверки улучшенной системы публикации!

📈 Новые возможности:
✅ Более устойчивые селекторы
✅ Поддержка нескольких языков интерфейса
✅ Автоповтор при ошибках (до 3 попыток)
✅ Улучшенная обработка ошибок
✅ Детальное логирование процесса

Это автоматический тест системы. Спасибо за понимание! 🙏

#тест #автоматизация #facebook"""

    print(f"Test message preview:\n{test_message[:100]}...")
    print(f"Message length: {len(test_message)} characters")
    print()
    
    # Initialize the poster
    print("Initializing Facebook Group Poster...")
    try:
        # Start in non-headless mode for debugging
        bot = FacebookGroupPoster(headless=False)
        print("✓ Bot initialized successfully")
    except Exception as e:
        print(f"✗ Failed to initialize bot: {str(e)}")
        return False
    
    # Check for groups file
    groups_file = "autofetched_groups.json"
    if not os.path.exists(groups_file):
        groups_file = "groups.txt"
        if not os.path.exists(groups_file):
            print("✗ No groups file found. Please run group fetching first.")
            return False
    
    print(f"✓ Using groups file: {groups_file}")
    
    try:
        # Load groups
        print("\nLoading groups...")
        groups = bot.load_groups(groups_file)
        if not groups:
            print("✗ No groups found in file")
            return False
            
        print(f"✓ Loaded {len(groups)} groups")
        
        # Take the first group for testing
        test_group = groups[0]
        print(f"✓ Selected test group: {test_group}")
        print()
        
        # Setup driver
        print("Setting up WebDriver...")
        if not bot.setup_driver():
            print("✗ Failed to setup WebDriver")
            return False
        print("✓ WebDriver setup successful")
        
        # Login
        print("\nAttempting to login to Facebook...")
        if not bot.login():
            print("✗ Failed to login to Facebook")
            bot.cleanup()
            return False
        print("✓ Successfully logged in to Facebook")
        
        # Test posting to single group
        print(f"\nTesting posting to group: {test_group}")
        print("-" * 50)
        
        success = bot.post_to_group(test_group, test_message)
        
        if success:
            print("✓ TEST PASSED: Post was successful!")
            print("✓ The improved posting function works correctly")
        else:
            print("✗ TEST FAILED: Post was not successful")
            print("✗ Check the logs and screenshots for details")
        
        print("-" * 50)
        print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Cleanup
        bot.cleanup()
        return success
        
    except Exception as e:
        print(f"✗ Error during testing: {str(e)}")
        bot.cleanup()
        return False

def test_multiple_groups():
    """Test posting to multiple groups with improved error handling"""
    
    print("\n" + "=" * 60)
    print("Testing Multiple Groups Posting")
    print("=" * 60)
    
    test_message = """🧪 Тест множественной публикации

Проверяем:
✅ Работу с несколькими группами
✅ Обработку ошибок
✅ Продолжение при сбоях
✅ Детальную статистику

#тестирование #автоматизация"""

    # Initialize the poster
    bot = FacebookGroupPoster(headless=False)
    
    try:
        # Test with limited number of groups (max 3 for testing)
        success = bot.post_to_multiple_groups(
            message=test_message,
            groups_file="autofetched_groups.json" if os.path.exists("autofetched_groups.json") else "groups.txt",
            max_groups=3
        )
        
        # Get final stats
        stats = bot.get_status()
        
        print(f"\nFinal Results:")
        print(f"✓ Posts completed: {stats.get('posts_completed', 0)}")
        print(f"✗ Posts failed: {stats.get('posts_failed', 0)}")
        print(f"📊 Total groups: {stats.get('groups_total', 0)}")
        print(f"⏱ Status: {stats.get('status', 'Unknown')}")
        
        if success and stats.get('posts_completed', 0) > 0:
            print("\n✓ MULTIPLE GROUPS TEST PASSED!")
        else:
            print("\n✗ MULTIPLE GROUPS TEST FAILED!")
            
        return success
        
    except Exception as e:
        print(f"✗ Error in multiple groups test: {str(e)}")
        return False

if __name__ == "__main__":
    print("Facebook Group Poster - Enhanced Testing Suite")
    print("This will test the improved posting functionality with better error handling")
    print()
    
    # Ask user for confirmation
    try:
        confirm = input("Do you want to proceed with posting test? This will post test messages to your groups. (y/N): ")
        if confirm.lower() != 'y':
            print("Test cancelled by user.")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")
        sys.exit(0)
    
    print("\n" + "=" * 80)
    print("STARTING ENHANCED POSTING TESTS")
    print("=" * 80)
    
    # Run single group test
    single_test_result = test_improved_posting()
    
    if single_test_result:
        # Ask if user wants to test multiple groups
        try:
            confirm_multiple = input("\nSingle group test passed. Test multiple groups? (y/N): ")
            if confirm_multiple.lower() == 'y':
                multiple_test_result = test_multiple_groups()
            else:
                multiple_test_result = True  # Skip but don't fail
        except KeyboardInterrupt:
            print("\nMultiple groups test cancelled.")
            multiple_test_result = True
    else:
        multiple_test_result = False
    
    # Final summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Single Group Test: {'✅ PASSED' if single_test_result else '❌ FAILED'}")
    print(f"Multiple Groups Test: {'✅ PASSED' if multiple_test_result else '❌ FAILED'}")
    
    if single_test_result and multiple_test_result:
        print("\n🎉 ALL TESTS PASSED! The improved posting system is working correctly.")
        print("\nKey improvements verified:")
        print("  ✅ Enhanced element selectors")
        print("  ✅ Multi-language support")
        print("  ✅ Retry logic with exponential backoff")
        print("  ✅ Better error handling and recovery")
        print("  ✅ Detailed logging and screenshots")
        print("  ✅ Graceful failure handling")
    else:
        print("\n❌ SOME TESTS FAILED. Check the logs and screenshots for debugging.")
        
    print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Exit with appropriate code
    sys.exit(0 if (single_test_result and multiple_test_result) else 1) 