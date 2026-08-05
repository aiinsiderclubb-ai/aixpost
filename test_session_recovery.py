#!/usr/bin/env python3
"""
Test script for session recovery functionality
Tests the automatic recovery from 'invalid session id' errors
"""

import sys
import os
import time
import logging
from unittest.mock import patch, MagicMock
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException

# Add bot directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

try:
    from fb_poster import FacebookGroupPoster
except ImportError as e:
    print(f"❌ Error importing FacebookGroupPoster: {e}")
    print("Make sure the bot/fb_poster.py file exists and is properly configured")
    sys.exit(1)

def test_session_check():
    """Test the session checking functionality"""
    print("\n🔍 Testing Session Check Functionality")
    print("=" * 50)
    
    # Create poster instance
    poster = FacebookGroupPoster(headless=True)
    
    # Test 1: Check with no driver
    print("1. Testing with no driver...")
    result = poster.check_driver_session()
    print(f"   Result: {result} (should be False)")
    assert result == False, "Should return False when driver is None"
    
    # Test 2: Mock driver with valid session
    print("2. Testing with valid driver session...")
    poster.driver = MagicMock()
    poster.driver.current_url = "https://www.facebook.com/home"
    result = poster.check_driver_session()
    print(f"   Result: {result} (should be True)")
    assert result == True, "Should return True for valid session"
    
    # Test 3: Mock driver with invalid session
    print("3. Testing with invalid driver session...")
    poster.driver = MagicMock()
    # Настраиваем property current_url чтобы он вызывал исключение
    type(poster.driver).current_url = property(lambda self: (_ for _ in ()).throw(InvalidSessionIdException("Session not found")))
    result = poster.check_driver_session()
    print(f"   Result: {result} (should be False)")
    assert result == False, "Should return False for invalid session"
    
    # Test 4: Mock WebDriverException with session error
    print("4. Testing with WebDriverException containing 'invalid session id'...")
    poster.driver = MagicMock()
    type(poster.driver).current_url = property(lambda self: (_ for _ in ()).throw(WebDriverException("invalid session id: some error")))
    result = poster.check_driver_session()
    print(f"   Result: {result} (should be False)")
    assert result == False, "Should return False for WebDriverException with session error"
    
    # Test 5: Mock WebDriverException without session error
    print("5. Testing with WebDriverException not related to session...")
    poster.driver = MagicMock()
    type(poster.driver).current_url = property(lambda self: (_ for _ in ()).throw(WebDriverException("element not found")))
    result = poster.check_driver_session()
    print(f"   Result: {result} (should be True)")
    assert result == True, "Should return True for WebDriverException not related to session"
    
    print("✅ All session check tests passed!")

def test_safe_driver_operation():
    """Test the safe driver operation wrapper"""
    print("\n🛡️ Testing Safe Driver Operation")
    print("=" * 50)
    
    poster = FacebookGroupPoster(headless=True)
    
    # Mock the restart_driver_session method
    poster.restart_driver_session = MagicMock(return_value=True)
    poster.check_driver_session = MagicMock(return_value=True)
    
    # Test 1: Normal operation
    print("1. Testing normal operation...")
    def normal_operation():
        return "success"
    
    result = poster.safe_driver_operation(normal_operation)
    print(f"   Result: {result} (should be 'success')")
    assert result == "success", "Should return operation result for normal operation"
    
    # Test 2: Operation with InvalidSessionIdException on first try
    print("2. Testing operation with session error on first try...")
    call_count = 0
    def failing_operation():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise InvalidSessionIdException("Session expired")
        return "recovered"
    
    call_count = 0
    result = poster.safe_driver_operation(failing_operation)
    print(f"   Result: {result} (should be 'recovered')")
    assert result == "recovered", "Should recover from session error and return result"
    assert poster.restart_driver_session.called, "Should have called restart_driver_session"
    
    # Test 3: Operation that fails session restart
    print("3. Testing operation with failed session restart...")
    poster.restart_driver_session = MagicMock(return_value=False)
    poster.check_driver_session = MagicMock(return_value=False)
    
    def always_failing_operation():
        raise InvalidSessionIdException("Session expired")
    
    result = poster.safe_driver_operation(always_failing_operation)
    print(f"   Result: {result} (should be None)")
    assert result is None, "Should return None when session restart fails"
    
    print("✅ All safe driver operation tests passed!")

def test_session_restart_limits():
    """Test the session restart limits"""
    print("\n🔄 Testing Session Restart Limits")
    print("=" * 50)
    
    poster = FacebookGroupPoster(headless=True)
    
    # Mock setup methods
    poster.setup_driver = MagicMock(return_value=True)
    poster.login = MagicMock(return_value=True)
    poster.send_telegram_notification = MagicMock()
    
    # Test exceeding restart limits
    poster.session_restarts = poster.max_session_restarts + 1
    
    result = poster.restart_driver_session()
    print(f"Result when exceeding restart limits: {result} (should be False)")
    assert result == False, "Should return False when exceeding restart limits"
    
    # Check that error notification was sent
    assert poster.send_telegram_notification.called, "Should send Telegram notification for critical error"
    
    # Check the error message content
    call_args = poster.send_telegram_notification.call_args_list[-1]
    message = call_args[0][0]  # First argument is the message
    print(f"Error message sent: {message[:50]}...")
    assert "❌" in message and "Критическая ошибка" in message, "Should send critical error message"
    
    print("✅ Session restart limits test passed!")

def test_telegram_notifications():
    """Test Telegram notifications for session recovery"""
    print("\n📱 Testing Telegram Notifications")
    print("=" * 50)
    
    poster = FacebookGroupPoster(headless=True)
    poster.send_telegram_notification = MagicMock()
    poster.setup_driver = MagicMock(return_value=True)
    poster.login = MagicMock(return_value=True)
    
    # Test restart notification
    poster.session_restarts = 0
    poster.restart_driver_session()
    
    # Check that notification was sent
    assert poster.send_telegram_notification.called, "Should send Telegram notification on restart"
    
    # Check notification content
    calls = poster.send_telegram_notification.call_args_list
    
    # Should have restart warning and recovery success messages
    restart_call = None
    recovery_call = None
    
    for call in calls:
        message = call[0][0]
        if "⚠️" in message and "перезапущена" in message:
            restart_call = call
        elif "✅" in message and "восстановлена" in message:
            recovery_call = call
    
    assert restart_call is not None, "Should send restart warning notification"
    assert recovery_call is not None, "Should send recovery success notification"
    
    print("✅ Telegram notifications test passed!")

def simulate_posting_with_session_errors():
    """Simulate a posting session with session errors"""
    print("\n🎭 Simulating Posting Session with Session Errors")
    print("=" * 50)
    
    poster = FacebookGroupPoster(headless=True)
    
    # Mock methods
    poster.setup_driver = MagicMock(return_value=True)
    poster.login = MagicMock(return_value=True)
    poster.send_telegram_notification = MagicMock()
    poster.take_screenshot = MagicMock()
    
    # Mock driver that fails periodically
    call_count = 0
    
    def mock_get(url):
        nonlocal call_count
        call_count += 1
        if call_count % 3 == 0:  # Fail every 3rd call
            raise InvalidSessionIdException("Session expired")
        return True
    
    # Create a function that always returns a fresh mock driver
    def create_mock_driver():
        mock_driver = MagicMock()
        mock_driver.get = mock_get
        mock_driver.current_url = "https://www.facebook.com/groups/123"
        return mock_driver
    
    # Override setup_driver to return our mock
    poster.setup_driver = lambda: setattr(poster, 'driver', create_mock_driver()) or True
    poster.driver = create_mock_driver()
    
    # Test safe navigation
    print("Testing navigation with periodic session failures...")
    
    for i in range(5):
        def navigate():
            poster.driver.get(f"https://www.facebook.com/groups/{i}")
            return True
        
        result = poster.safe_driver_operation(navigate)
        print(f"   Navigation {i+1}: {'✅' if result else '❌'}")
    
    print("✅ Session error simulation completed!")

def run_comprehensive_test():
    """Run comprehensive test suite"""
    print("🚀 Starting Comprehensive Session Recovery Tests")
    print("=" * 60)
    
    try:
        test_session_check()
        test_safe_driver_operation()
        test_session_restart_limits()
        test_telegram_notifications()
        simulate_posting_with_session_errors()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED! Session recovery system is working correctly!")
        print("=" * 60)
        
        print("\n📋 Summary of Improvements:")
        print("✅ Session checking before operations")
        print("✅ Automatic session restart on failure")
        print("✅ Safe driver operation wrapper")
        print("✅ Telegram notifications for session events")
        print("✅ Session restart limits to prevent infinite loops")
        print("✅ Graceful handling of invalid session id errors")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    success = run_comprehensive_test()
    sys.exit(0 if success else 1) 