#!/usr/bin/env python3
"""
Comprehensive Test Suite for Facebook SaaS Platform
Tests all critical user flows and functionality
"""

import requests
import json
import time
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8080"
TEST_USER_EMAIL = f"test{int(time.time())}@example.com"  # Unique email
TEST_USER_PASSWORD = "TestPassword123!"
TEST_ADMIN_EMAIL = "admin@test.com"
TEST_ADMIN_PASSWORD = "Admin123!"

class SaaSPlatformTester:
    def __init__(self):
        self.session = requests.Session()
        self.user_token = None
        self.admin_token = None
        self.test_campaign_id = None
        self.results = []
        
    def log_test(self, test_name, success, message=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}: {message}")
        self.results.append({
            'test': test_name,
            'success': success,
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
        
    def test_health_check(self):
        """Test health endpoint"""
        try:
            response = self.session.get(f"{BASE_URL}/health")
            success = response.status_code == 200
            data = response.json() if success else {}
            self.log_test(
                "Health Check",
                success,
                f"Status: {response.status_code}, Users: {data.get('users_count', 0)}"
            )
            return success
        except Exception as e:
            self.log_test("Health Check", False, f"Error: {str(e)}")
            return False
            
    def test_user_registration(self):
        """Test user registration flow"""
        try:
            # First, try to register a new user
            test_data = {
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "first_name": "Test",
                "last_name": "User"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/register",
                json=test_data
            )
            
            if response.status_code == 409:
                # User already exists, that's okay
                self.log_test("User Registration", True, "User already exists")
                return True
            elif response.status_code == 201:
                data = response.json()
                self.user_token = data.get('access_token')
                self.log_test("User Registration", True, f"New user created: {data['user']['email']}")
                return True
            else:
                self.log_test("User Registration", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("User Registration", False, f"Error: {str(e)}")
            return False
            
    def test_user_login(self):
        """Test user login flow"""
        try:
            login_data = {
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json=login_data
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get('access_token')
                self.log_test("User Login", True, f"Token received: {self.user_token[:20]}...")
                return True
            else:
                self.log_test("User Login", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("User Login", False, f"Error: {str(e)}")
            return False
            
    def test_admin_login(self):
        """Test admin login flow"""
        try:
            login_data = {
                "email": TEST_ADMIN_EMAIL,
                "password": TEST_ADMIN_PASSWORD
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/login",
                json=login_data
            )
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get('access_token')
                self.log_test("Admin Login", True, f"Admin token received")
                return True
            else:
                self.log_test("Admin Login", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Admin Login", False, f"Error: {str(e)}")
            return False
            
    def test_protected_route(self):
        """Test protected route access"""
        try:
            if not self.user_token:
                self.log_test("Protected Route", False, "No user token available")
                return False
                
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = self.session.get(f"{BASE_URL}/api/auth/me", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                user_email = data['user']['email']
                self.log_test("Protected Route", True, f"User info retrieved: {user_email}")
                return True
            else:
                self.log_test("Protected Route", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Protected Route", False, f"Error: {str(e)}")
            return False
            
    def test_campaign_creation(self):
        """Test campaign creation"""
        try:
            if not self.user_token:
                self.log_test("Campaign Creation", False, "No user token available")
                return False
                
            campaign_data = {
                "name": "Test Campaign",
                "message": "This is a test message for Facebook groups",
                "group_urls": [
                    "https://www.facebook.com/groups/testgroup1/",
                    "https://www.facebook.com/groups/testgroup2/"
                ],
                "max_groups": 5,
                "min_delay": 10,
                "max_delay": 30
            }
            
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = self.session.post(
                f"{BASE_URL}/api/campaigns",
                json=campaign_data,
                headers=headers
            )
            
            if response.status_code == 201:
                data = response.json()
                self.test_campaign_id = data['campaign']['id']
                self.log_test("Campaign Creation", True, f"Campaign created: {data['campaign']['name']}")
                return True
            else:
                self.log_test("Campaign Creation", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Campaign Creation", False, f"Error: {str(e)}")
            return False
            
    def test_campaign_listing(self):
        """Test campaign listing"""
        try:
            if not self.user_token:
                self.log_test("Campaign Listing", False, "No user token available")
                return False
                
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = self.session.get(f"{BASE_URL}/api/campaigns", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                campaign_count = len(data['campaigns'])
                self.log_test("Campaign Listing", True, f"Found {campaign_count} campaigns")
                return True
            else:
                self.log_test("Campaign Listing", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Campaign Listing", False, f"Error: {str(e)}")
            return False
            
    def test_campaign_start(self):
        """Test campaign start"""
        try:
            if not self.user_token or not self.test_campaign_id:
                self.log_test("Campaign Start", False, "No user token or campaign ID available")
                return False
                
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = self.session.post(
                f"{BASE_URL}/api/campaigns/{self.test_campaign_id}/start",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Campaign Start", True, f"Campaign started: {data['campaign']['status']}")
                return True
            else:
                self.log_test("Campaign Start", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Campaign Start", False, f"Error: {str(e)}")
            return False
            
    def test_settings_update(self):
        """Test settings update"""
        try:
            if not self.user_token:
                self.log_test("Settings Update", False, "No user token available")
                return False
                
            settings_data = {
                "facebook_username": "test@facebook.com",
                "facebook_password": "testpass123",
                "use_headless": True
            }
            
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = self.session.post(
                f"{BASE_URL}/api/user/settings",
                json=settings_data,
                headers=headers
            )
            
            if response.status_code == 200:
                self.log_test("Settings Update", True, "Settings updated successfully")
                return True
            else:
                self.log_test("Settings Update", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Settings Update", False, f"Error: {str(e)}")
            return False
            
    def test_unauthorized_access(self):
        """Test unauthorized access prevention"""
        try:
            # Try to access protected route without token
            response = self.session.get(f"{BASE_URL}/api/auth/me")
            
            if response.status_code == 401:
                self.log_test("Unauthorized Access", True, "Properly blocked unauthorized access")
                return True
            else:
                self.log_test("Unauthorized Access", False, f"Should return 401, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Unauthorized Access", False, f"Error: {str(e)}")
            return False
            
    def test_password_validation(self):
        """Test password validation"""
        try:
            weak_password_data = {
                "email": "weak@example.com",
                "password": "123",  # Weak password
                "first_name": "Weak",
                "last_name": "User"
            }
            
            response = self.session.post(
                f"{BASE_URL}/api/auth/register",
                json=weak_password_data
            )
            
            if response.status_code == 400:
                self.log_test("Password Validation", True, "Weak password properly rejected")
                return True
            else:
                self.log_test("Password Validation", False, f"Should reject weak password, got {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Password Validation", False, f"Error: {str(e)}")
            return False
            
    def test_plan_limits(self):
        """Test plan limits enforcement"""
        try:
            if not self.user_token:
                self.log_test("Plan Limits", False, "No user token available")
                return False
                
            # Try to create campaign with too many groups
            large_campaign_data = {
                "name": "Large Campaign",
                "message": "Test message",
                "group_urls": [f"https://www.facebook.com/groups/testgroup{i}/" for i in range(100)],
                "max_groups": 100
            }
            
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = self.session.post(
                f"{BASE_URL}/api/campaigns",
                json=large_campaign_data,
                headers=headers
            )
            
            if response.status_code == 400:
                data = response.json()
                error_msg = data.get('error', '').lower()
                if "limit" in error_msg or "many" in error_msg:
                    self.log_test("Plan Limits", True, "Plan limits properly enforced")
                    return True
                else:
                    self.log_test("Plan Limits", False, f"Got 400 but wrong error: {data.get('error', '')}")
                    return False
                    
            self.log_test("Plan Limits", False, f"Should enforce limits, got {response.status_code}")
            return False
                
        except Exception as e:
            self.log_test("Plan Limits", False, f"Error: {str(e)}")
            return False
            
    def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting Facebook SaaS Platform Tests...")
        print("=" * 60)
        
        # Wait for server to start
        time.sleep(2)
        
        # Run tests in order
        tests = [
            self.test_health_check,
            self.test_user_registration,
            self.test_user_login,
            self.test_admin_login,
            self.test_protected_route,
            self.test_campaign_creation,
            self.test_campaign_listing,
            self.test_campaign_start,
            self.test_settings_update,
            self.test_unauthorized_access,
            self.test_password_validation,
            self.test_plan_limits
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                if test():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"❌ EXCEPTION in {test.__name__}: {str(e)}")
                failed += 1
            
            time.sleep(0.5)  # Small delay between tests
            
        print("=" * 60)
        print(f"📊 TEST RESULTS:")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"📈 Success Rate: {(passed/(passed+failed)*100):.1f}%")
        
        if failed == 0:
            print("🎉 ALL TESTS PASSED! Platform is ready for production!")
        else:
            print("⚠️  Some tests failed. Please review the issues above.")
            
        return failed == 0

def main():
    """Main test runner"""
    tester = SaaSPlatformTester()
    
    try:
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 