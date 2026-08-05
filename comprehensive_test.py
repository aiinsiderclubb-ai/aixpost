#!/usr/bin/env python3
"""
Comprehensive Test Suite for Facebook SaaS Platform
Tests all major functionality including admin endpoints, Telegram integration, and limits
"""

import requests
import json
import time
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8080"
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "Admin123!"
TEST_USER_EMAIL = f"test_{int(time.time())}@test.com"
TEST_USER_PASSWORD = "TestPassword123!"

class ComprehensiveTest:
    def __init__(self):
        self.session = requests.Session()
        self.admin_token = None
        self.user_token = None
        self.test_results = []
        
    def log_test(self, test_name, success, message="", data=None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        timestamp = datetime.now().strftime("%H:%M:%S")
        result = f"{timestamp} {status} {test_name}"
        if message:
            result += f" - {message}"
        
        print(result)
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message,
            'data': data,
            'timestamp': timestamp
        })
        
    def test_health_check(self):
        """Test basic health endpoint"""
        try:
            response = self.session.get(f"{BASE_URL}/health", timeout=10)
            success = response.status_code == 200
            data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
            self.log_test("Health Check", success, f"Status: {response.status_code}", data)
            return success
        except Exception as e:
            self.log_test("Health Check", False, f"Exception: {str(e)}")
            return False
    
    def test_admin_login(self):
        """Test admin login functionality"""
        try:
            payload = {
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }
            response = self.session.post(f"{BASE_URL}/api/auth/login", 
                                       json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.admin_token = data.get('access_token')
                success = self.admin_token is not None
                self.log_test("Admin Login", success, 
                            f"Token: {'Found' if self.admin_token else 'Missing'}")
            else:
                self.log_test("Admin Login", False, 
                            f"Status: {response.status_code}, Response: {response.text}")
                success = False
            
            return success
        except Exception as e:
            self.log_test("Admin Login", False, f"Exception: {str(e)}")
            return False
    
    def test_user_registration(self):
        """Test user registration"""
        try:
            payload = {
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "first_name": "Test",
                "last_name": "User"
            }
            response = self.session.post(f"{BASE_URL}/api/auth/register", 
                                       json=payload, timeout=10)
            
            success = response.status_code == 201
            self.log_test("User Registration", success, 
                        f"Status: {response.status_code}")
            return success
        except Exception as e:
            self.log_test("User Registration", False, f"Exception: {str(e)}")
            return False
    
    def test_user_login(self):
        """Test user login"""
        try:
            payload = {
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
            response = self.session.post(f"{BASE_URL}/api/auth/login", 
                                       json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.user_token = data.get('access_token')
                success = self.user_token is not None
                self.log_test("User Login", success, 
                            f"Token: {'Found' if self.user_token else 'Missing'}")
            else:
                self.log_test("User Login", False, 
                            f"Status: {response.status_code}")
                success = False
            
            return success
        except Exception as e:
            self.log_test("User Login", False, f"Exception: {str(e)}")
            return False
    
    def test_admin_endpoints(self):
        """Test admin-only endpoints"""
        if not self.admin_token:
            self.log_test("Admin Endpoints", False, "No admin token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        admin_endpoints = [
            ("/admin", "Admin Panel"),
            ("/api/v1/admin/users", "Admin Users API"),
            ("/api/v1/admin/analytics/overview", "Admin Analytics")
        ]
        
        results = []
        for endpoint, name in admin_endpoints:
            try:
                response = self.session.get(f"{BASE_URL}{endpoint}", 
                                          headers=headers, timeout=10)
                success = response.status_code in [200, 302]  # 302 for redirects
                self.log_test(f"Admin - {name}", success, 
                            f"Status: {response.status_code}")
                results.append(success)
            except Exception as e:
                self.log_test(f"Admin - {name}", False, f"Exception: {str(e)}")
                results.append(False)
        
        return all(results)
    
    def test_user_endpoint_access(self):
        """Test that regular users can't access admin endpoints"""
        if not self.user_token:
            self.log_test("User Access Control", False, "No user token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        admin_endpoints = [
            ("/admin", "Admin Panel"),
            ("/api/v1/admin/users", "Admin Users API")
        ]
        
        results = []
        for endpoint, name in admin_endpoints:
            try:
                response = self.session.get(f"{BASE_URL}{endpoint}", 
                                          headers=headers, timeout=10)
                # Should return 403 (Forbidden) for non-admin users
                success = response.status_code == 403
                self.log_test(f"User Access Control - {name}", success, 
                            f"Status: {response.status_code} (expected 403)")
                results.append(success)
            except Exception as e:
                self.log_test(f"User Access Control - {name}", False, 
                            f"Exception: {str(e)}")
                results.append(False)
        
        return all(results)
    
    def test_telegram_api(self):
        """Test Telegram bot API endpoints"""
        if not self.user_token:
            self.log_test("Telegram API", False, "No user token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        results = []
        
        # Test GET telegram settings
        try:
            response = self.session.get(f"{BASE_URL}/api/telegram/settings", 
                                      headers=headers, timeout=10)
            success = response.status_code == 200
            self.log_test("Telegram - Get Settings", success, 
                        f"Status: {response.status_code}")
            results.append(success)
        except Exception as e:
            self.log_test("Telegram - Get Settings", False, f"Exception: {str(e)}")
            results.append(False)
        
        # Test POST telegram settings
        try:
            payload = {"chat_id": "123456789"}
            response = self.session.post(f"{BASE_URL}/api/telegram/settings", 
                                       json=payload, headers=headers, timeout=10)
            success = response.status_code == 200
            self.log_test("Telegram - Save Settings", success, 
                        f"Status: {response.status_code}")
            results.append(success)
        except Exception as e:
            self.log_test("Telegram - Save Settings", False, f"Exception: {str(e)}")
            results.append(False)
        
        # Test telegram test endpoint
        try:
            response = self.session.post(f"{BASE_URL}/api/telegram/test", 
                                       headers=headers, timeout=10)
            success = response.status_code in [200, 400]  # 400 is acceptable for test mode
            self.log_test("Telegram - Test Connection", success, 
                        f"Status: {response.status_code}")
            results.append(success)
        except Exception as e:
            self.log_test("Telegram - Test Connection", False, f"Exception: {str(e)}")
            results.append(False)
        
        return all(results)
    
    def test_campaign_api(self):
        """Test campaign management API"""
        if not self.user_token:
            self.log_test("Campaign API", False, "No user token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        results = []
        
        # Test GET campaigns
        try:
            response = self.session.get(f"{BASE_URL}/api/campaigns", 
                                      headers=headers, timeout=10)
            success = response.status_code == 200
            self.log_test("Campaigns - List", success, 
                        f"Status: {response.status_code}")
            results.append(success)
        except Exception as e:
            self.log_test("Campaigns - List", False, f"Exception: {str(e)}")
            results.append(False)
        
        # Test CREATE campaign
        try:
            payload = {
                "name": "Test Campaign",
                "message": "Test message",
                "target_groups": ["test_group_1", "test_group_2"],
                "max_groups": 2,
                "min_delay": 5,
                "max_delay": 10
            }
            response = self.session.post(f"{BASE_URL}/api/campaigns", 
                                       json=payload, headers=headers, timeout=10)
            success = response.status_code == 201
            self.log_test("Campaigns - Create", success, 
                        f"Status: {response.status_code}")
            results.append(success)
        except Exception as e:
            self.log_test("Campaigns - Create", False, f"Exception: {str(e)}")
            results.append(False)
        
        return all(results)
    
    def test_main_pages(self):
        """Test main application pages"""
        if not self.user_token:
            self.log_test("Main Pages", False, "No user token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.user_token}"}
        pages = [
            ("/dashboard", "Dashboard"),
            ("/groups", "Groups"),
            ("/poster", "Poster"),
            ("/scheduler", "Scheduler"),
            ("/plans", "Plans"),
            ("/telegram", "Telegram")
        ]
        
        results = []
        for endpoint, name in pages:
            try:
                response = self.session.get(f"{BASE_URL}{endpoint}", 
                                          headers=headers, timeout=10)
                success = response.status_code in [200, 302]
                self.log_test(f"Page - {name}", success, 
                            f"Status: {response.status_code}")
                results.append(success)
            except Exception as e:
                self.log_test(f"Page - {name}", False, f"Exception: {str(e)}")
                results.append(False)
        
        return all(results)
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting Comprehensive Test Suite")
        print("=" * 60)
        
        test_methods = [
            self.test_health_check,
            self.test_admin_login,
            self.test_user_registration,
            self.test_user_login,
            self.test_admin_endpoints,
            self.test_user_endpoint_access,
            self.test_telegram_api,
            self.test_campaign_api,
            self.test_main_pages
        ]
        
        overall_success = True
        
        for test_method in test_methods:
            try:
                result = test_method()
                if not result:
                    overall_success = False
            except Exception as e:
                print(f"❌ CRITICAL ERROR in {test_method.__name__}: {str(e)}")
                overall_success = False
            
            # Small delay between tests
            time.sleep(0.5)
        
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for r in self.test_results if r['success'])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if overall_success:
            print("\n🎉 ALL TESTS PASSED! Platform is ready for production.")
        else:
            print("\n⚠️  Some tests failed. Please review the issues above.")
            failed_tests = [r for r in self.test_results if not r['success']]
            print("\nFailed Tests:")
            for test in failed_tests:
                print(f"  - {test['test']}: {test['message']}")
        
        return overall_success

def main():
    """Main execution function"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Comprehensive Test Suite for Facebook SaaS Platform")
        print("\nUsage: python comprehensive_test.py")
        print("\nMake sure the server is running on http://localhost:8080")
        return
    
    print("Facebook SaaS Platform - Comprehensive Test Suite")
    print("Make sure the server is running on http://localhost:8080")
    print("Press Ctrl+C to abort\n")
    
    try:
        time.sleep(2)  # Give user time to read
        
        tester = ComprehensiveTest()
        success = tester.run_all_tests()
        
        exit_code = 0 if success else 1
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ CRITICAL ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 