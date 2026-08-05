#!/usr/bin/env python3
"""
Test file for new Telegram Alerts and How It Works features in AIPostX v2.1
"""

import unittest
import requests
import json
import time
import os
import sys
from unittest.mock import patch, MagicMock

# Test Configuration
BASE_URL = "http://localhost:8080"
TEST_ADMIN_EMAIL = "admin@test.com"
TEST_ADMIN_PASSWORD = "Admin123!"
TEST_USER_EMAIL = "testuser@example.com"
TEST_USER_PASSWORD = "TestUser123!"

class TestNewFeatures(unittest.TestCase):
    """Test suite for new Telegram and Guide features"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.admin_token = None
        self.user_token = None
        self.test_user_id = None
        
        # Create test user and get tokens
        self._register_test_user()
        self._login_admin()
        
    def _register_test_user(self):
        """Register a test user"""
        try:
            response = requests.post(f"{BASE_URL}/api/auth/register", json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "first_name": "Test",
                "last_name": "User"
            })
            
            if response.status_code == 201:
                data = response.json()
                self.user_token = data.get('access_token')
                self.test_user_id = data.get('user', {}).get('id')
                print(f"✅ Test user registered: {TEST_USER_EMAIL}")
            elif response.status_code == 409:
                # User already exists, try to login
                self._login_user()
            else:
                print(f"❌ Failed to register test user: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error registering test user: {e}")
            
    def _login_user(self):
        """Login test user"""
        try:
            response = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get('access_token')
                self.test_user_id = data.get('user', {}).get('id')
                print(f"✅ Test user logged in: {TEST_USER_EMAIL}")
            else:
                print(f"❌ Failed to login test user: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error logging in test user: {e}")
    
    def _login_admin(self):
        """Login admin user"""
        try:
            response = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get('access_token')
                print(f"✅ Admin logged in: {TEST_ADMIN_EMAIL}")
            else:
                print(f"❌ Failed to login admin: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error logging in admin: {e}")

    def test_1_telegram_page_access(self):
        """Test 1: Verify Telegram page is accessible"""
        print("\n🧪 Test 1: Telegram Page Access")
        
        if not self.user_token:
            self.skipTest("No user token available")
            
        try:
            response = requests.get(f"{BASE_URL}/telegram", 
                                  cookies={'access_token': self.user_token})
            
            self.assertEqual(response.status_code, 200)
            self.assertIn("Telegram", response.text)
            print("✅ Telegram page accessible")
            
        except Exception as e:
            self.fail(f"Failed to access Telegram page: {e}")

    def test_2_guide_page_access(self):
        """Test 2: Verify How It Works page is accessible"""
        print("\n🧪 Test 2: Guide Page Access")
        
        if not self.user_token:
            self.skipTest("No user token available")
            
        try:
            response = requests.get(f"{BASE_URL}/guide", 
                                  cookies={'access_token': self.user_token})
            
            self.assertEqual(response.status_code, 200)
            self.assertIn("How It Works", response.text)
            print("✅ Guide page accessible")
            
        except Exception as e:
            self.fail(f"Failed to access Guide page: {e}")

    def test_3_telegram_settings_api(self):
        """Test 3: Telegram settings API endpoints"""
        print("\n🧪 Test 3: Telegram Settings API")
        
        if not self.user_token:
            self.skipTest("No user token available")
            
        headers = {'Authorization': f'Bearer {self.user_token}'}
        
        try:
            # Test GET settings (should be empty initially)
            response = requests.get(f"{BASE_URL}/api/telegram/settings", headers=headers)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data.get('connected', True))
            print("✅ GET telegram settings works")
            
            # Test POST settings (save chat ID)
            test_chat_id = "123456789"
            response = requests.post(f"{BASE_URL}/api/telegram/settings", 
                                   json={'chat_id': test_chat_id},
                                   headers=headers)
            self.assertEqual(response.status_code, 200)
            print("✅ POST telegram settings works")
            
            # Test GET settings again (should be connected now)
            response = requests.get(f"{BASE_URL}/api/telegram/settings", headers=headers)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data.get('connected', False))
            self.assertEqual(data.get('settings', {}).get('chat_id'), test_chat_id)
            print("✅ Telegram settings persisted correctly")
            
        except Exception as e:
            self.fail(f"Telegram settings API failed: {e}")

    @patch('requests.post')
    def test_4_telegram_test_message(self, mock_post):
        """Test 4: Telegram test message functionality"""
        print("\n🧪 Test 4: Telegram Test Message")
        
        if not self.user_token:
            self.skipTest("No user token available")
            
        # Mock successful Telegram API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response
        
        headers = {'Authorization': f'Bearer {self.user_token}'}
        
        try:
            # First save settings
            test_chat_id = "123456789"
            response = requests.post(f"{BASE_URL}/api/telegram/settings", 
                                   json={'chat_id': test_chat_id},
                                   headers=headers)
            self.assertEqual(response.status_code, 200)
            
            # Test message sending
            response = requests.post(f"{BASE_URL}/api/telegram/test", headers=headers)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data.get('success', False))
            print("✅ Telegram test message works")
            
        except Exception as e:
            self.fail(f"Telegram test message failed: {e}")

    def test_5_guide_content_api(self):
        """Test 5: Guide content API endpoint"""
        print("\n🧪 Test 5: Guide Content API")
        
        if not self.user_token:
            self.skipTest("No user token available")
            
        headers = {'Authorization': f'Bearer {self.user_token}'}
        
        try:
            response = requests.get(f"{BASE_URL}/api/guide", headers=headers)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data.get('success', False))
            self.assertIn('content', data)
            self.assertIn('Fetching Groups', data['content'])
            print("✅ Guide content API works")
            
        except Exception as e:
            self.fail(f"Guide content API failed: {e}")

    def test_6_admin_users_with_telegram(self):
        """Test 6: Admin panel shows Telegram information"""
        print("\n🧪 Test 6: Admin Users with Telegram Info")
        
        if not self.admin_token:
            self.skipTest("No admin token available")
            
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        try:
            response = requests.get(f"{BASE_URL}/api/v1/admin/users", headers=headers)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn('users', data)
            
            # Check if users have telegram fields
            if data['users']:
                user = data['users'][0]
                self.assertIn('telegram_chat_id', user)
                self.assertIn('telegram_connected', user)
                print("✅ Admin users API includes Telegram info")
            else:
                print("⚠️  No users found to test Telegram info")
                
        except Exception as e:
            self.fail(f"Admin users API failed: {e}")

    @patch('requests.post')
    def test_7_admin_ping_telegram(self, mock_post):
        """Test 7: Admin can ping user's Telegram"""
        print("\n🧪 Test 7: Admin Ping Telegram")
        
        if not self.admin_token or not self.test_user_id:
            self.skipTest("No admin token or test user ID available")
            
        # Mock successful Telegram API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response
        
        headers = {'Authorization': f'Bearer {self.admin_token}'}
        
        try:
            # First setup Telegram for test user
            user_headers = {'Authorization': f'Bearer {self.user_token}'}
            requests.post(f"{BASE_URL}/api/telegram/settings", 
                         json={'chat_id': '123456789'},
                         headers=user_headers)
            
            # Test admin ping
            response = requests.post(f"{BASE_URL}/api/admin/users/{self.test_user_id}/ping-telegram", 
                                   headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                self.assertTrue(data.get('success', False))
                print("✅ Admin ping Telegram works")
            else:
                print(f"⚠️  Admin ping failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            self.fail(f"Admin ping Telegram failed: {e}")

    def test_8_sidebar_navigation(self):
        """Test 8: Verify sidebar contains new menu items"""
        print("\n🧪 Test 8: Sidebar Navigation")
        
        if not self.user_token:
            self.skipTest("No user token available")
            
        try:
            response = requests.get(f"{BASE_URL}/dashboard", 
                                  cookies={'access_token': self.user_token})
            
            self.assertEqual(response.status_code, 200)
            html_content = response.text
            
            # Check for Telegram Alerts menu item
            self.assertIn("Telegram Alerts", html_content)
            self.assertIn('href="/telegram"', html_content)
            
            # Check for How It Works menu item
            self.assertIn("How It Works", html_content)
            self.assertIn('href="/guide"', html_content)
            
            print("✅ Sidebar navigation updated correctly")
            
        except Exception as e:
            self.fail(f"Sidebar navigation test failed: {e}")

    def test_9_dashboard_usage_display(self):
        """Test 9: Dashboard shows usage statistics"""
        print("\n🧪 Test 9: Dashboard Usage Display")
        
        if not self.user_token:
            self.skipTest("No user token available")
            
        try:
            response = requests.get(f"{BASE_URL}/dashboard", 
                                  cookies={'access_token': self.user_token})
            
            self.assertEqual(response.status_code, 200)
            html_content = response.text
            
            # Check for usage statistics section
            self.assertIn("Usage Statistics", html_content)
            self.assertIn("Messages Used", html_content)
            self.assertIn("progress-bar", html_content)
            
            print("✅ Dashboard shows usage statistics")
            
        except Exception as e:
            self.fail(f"Dashboard usage display test failed: {e}")

    def test_10_end_to_end_workflow(self):
        """Test 10: Complete end-to-end workflow"""
        print("\n🧪 Test 10: End-to-End Workflow")
        
        if not self.user_token:
            self.skipTest("No user token available")
            
        headers = {'Authorization': f'Bearer {self.user_token}'}
        
        try:
            # 1. Access Telegram page
            response = requests.get(f"{BASE_URL}/telegram", 
                                  cookies={'access_token': self.user_token})
            self.assertEqual(response.status_code, 200)
            
            # 2. Configure Telegram settings
            response = requests.post(f"{BASE_URL}/api/telegram/settings", 
                                   json={'chat_id': '987654321'},
                                   headers=headers)
            self.assertEqual(response.status_code, 200)
            
            # 3. Access guide page
            response = requests.get(f"{BASE_URL}/guide", 
                                  cookies={'access_token': self.user_token})
            self.assertEqual(response.status_code, 200)
            
            # 4. Get guide content via API
            response = requests.get(f"{BASE_URL}/api/guide", headers=headers)
            self.assertEqual(response.status_code, 200)
            
            # 5. Check dashboard shows updated info
            response = requests.get(f"{BASE_URL}/dashboard", 
                                  cookies={'access_token': self.user_token})
            self.assertEqual(response.status_code, 200)
            
            print("✅ End-to-end workflow completed successfully")
            
        except Exception as e:
            self.fail(f"End-to-end workflow failed: {e}")

def run_tests():
    """Run all tests with proper setup"""
    print("🚀 AIPostX v2.1 New Features Test Suite")
    print("=" * 50)
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ Server is not running or not healthy")
            return False
    except Exception:
        print("❌ Cannot connect to server. Please start the server first.")
        return False
    
    print("✅ Server is running and healthy")
    
    # Run tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNewFeatures)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print("\n❌ FAILURES:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split('AssertionError: ')[-1].split('\\n')[0]}")
    
    if result.errors:
        print("\n❌ ERRORS:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback.split('\\n')[-2]}")
    
    if not result.failures and not result.errors:
        print("\n🎉 ALL TESTS PASSED!")
        return True
    else:
        print(f"\n⚠️  {len(result.failures + result.errors)} test(s) failed")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1) 