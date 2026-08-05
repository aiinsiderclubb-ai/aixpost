#!/usr/bin/env python3
"""
Comprehensive test script for Admin Real-time Workflow
Tests all new admin functions including:
- User plan management
- Usage reset
- User details viewing
- Real-time WebSocket updates
- Audit logging
"""

import asyncio
import json
import time
import requests
import socketio
from typing import Dict, Any

class AdminRealtimeTest:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.admin_token = None
        self.user_token = None
        self.admin_id = None
        self.user_id = None
        self.sio = socketio.AsyncClient()
        self.test_results = {}
        
    async def setup(self):
        """Setup test environment"""
        print("🔧 Setting up test environment...")
        
        # Register admin
        admin_data = {
            "email": "admin_test@test.com",
            "password": "Admin123!",
            "first_name": "Admin",
            "last_name": "Test"
        }
        
        try:
            response = requests.post(f"{self.base_url}/api/auth/register", json=admin_data)
            if response.status_code == 201:
                admin_result = response.json()
                self.admin_token = admin_result['access_token']
                self.admin_id = admin_result['user']['id']
                print(f"✅ Admin created: ID {self.admin_id}")
            elif response.status_code == 409:
                # User exists, login
                login_response = requests.post(f"{self.base_url}/api/auth/login", json={
                    "email": admin_data["email"],
                    "password": admin_data["password"]
                })
                if login_response.status_code == 200:
                    admin_result = login_response.json()
                    self.admin_token = admin_result['access_token']
                    self.admin_id = admin_result['user']['id']
                    print(f"✅ Admin logged in: ID {self.admin_id}")
        except Exception as e:
            print(f"❌ Failed to setup admin: {e}")
            return False
            
        # Set admin role in database
        import sqlite3
        conn = sqlite3.connect('test_app.db')
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (self.admin_id,))
        conn.commit()
        conn.close()
        print("✅ Admin role set")
        
        # Register regular user
        user_data = {
            "email": "user_test@test.com",
            "password": "User123!",
            "first_name": "User",
            "last_name": "Test"
        }
        
        try:
            response = requests.post(f"{self.base_url}/api/auth/register", json=user_data)
            if response.status_code == 201:
                user_result = response.json()
                self.user_token = user_result['access_token']
                self.user_id = user_result['user']['id']
                print(f"✅ User created: ID {self.user_id}")
            elif response.status_code == 409:
                # User exists, login
                login_response = requests.post(f"{self.base_url}/api/auth/login", json={
                    "email": user_data["email"],
                    "password": user_data["password"]
                })
                if login_response.status_code == 200:
                    user_result = login_response.json()
                    self.user_token = user_result['access_token']
                    self.user_id = user_result['user']['id']
                    print(f"✅ User logged in: ID {self.user_id}")
        except Exception as e:
            print(f"❌ Failed to setup user: {e}")
            return False
            
        print("✅ Test environment setup complete\n")
        return True
        
    def test_admin_get_users(self) -> bool:
        """Test admin users listing endpoint"""
        print("🧪 Testing admin get users endpoint...")
        
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{self.base_url}/api/v1/admin/users", headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                users = data.get('users', [])
                print(f"✅ Retrieved {len(users)} users")
                print(f"   Pagination: {data.get('pagination', {})}")
                self.test_results['admin_get_users'] = True
                return True
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
                self.test_results['admin_get_users'] = False
                return False
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            self.test_results['admin_get_users'] = False
            return False
            
    def test_admin_update_plan(self) -> bool:
        """Test admin plan update endpoint"""
        print("🧪 Testing admin plan update endpoint...")
        
        try:
            headers = {
                "Authorization": f"Bearer {self.admin_token}",
                "Content-Type": "application/json"
            }
            data = {"plan": "PREMIUM"}
            
            response = requests.post(
                f"{self.base_url}/api/admin/users/{self.user_id}/plan",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Plan updated: {result['old_plan']} → {result['new_plan']}")
                self.test_results['admin_update_plan'] = True
                return True
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
                self.test_results['admin_update_plan'] = False
                return False
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            self.test_results['admin_update_plan'] = False
            return False
            
    def test_admin_reset_usage(self) -> bool:
        """Test admin usage reset endpoint"""
        print("🧪 Testing admin usage reset endpoint...")
        
        try:
            # First set some usage
            import sqlite3
            conn = sqlite3.connect('test_app.db')
            conn.execute("UPDATE users SET messages_used = 50 WHERE id = ?", (self.user_id,))
            conn.commit()
            conn.close()
            print("   Set usage to 50 messages")
            
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.post(
                f"{self.base_url}/api/admin/users/{self.user_id}/reset_usage",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Usage reset: {result['old_usage']} → {result['new_usage']}")
                self.test_results['admin_reset_usage'] = True
                return True
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
                self.test_results['admin_reset_usage'] = False
                return False
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            self.test_results['admin_reset_usage'] = False
            return False
            
    def test_admin_user_details(self) -> bool:
        """Test admin user details endpoint"""
        print("🧪 Testing admin user details endpoint...")
        
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(
                f"{self.base_url}/api/admin/users/{self.user_id}/details",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                user = result.get('user', {})
                audits = result.get('recent_audits', [])
                print(f"✅ User details retrieved")
                print(f"   User: {user.get('first_name')} {user.get('last_name')} ({user.get('email')})")
                print(f"   Plan: {user.get('current_plan')}")
                print(f"   Recent audits: {len(audits)}")
                self.test_results['admin_user_details'] = True
                return True
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
                self.test_results['admin_user_details'] = False
                return False
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            self.test_results['admin_user_details'] = False
            return False
            
    def test_audit_logs(self) -> bool:
        """Test audit logs endpoint"""
        print("🧪 Testing audit logs endpoint...")
        
        try:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response = requests.get(f"{self.base_url}/api/admin/audit_logs", headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                logs = result.get('audit_logs', [])
                print(f"✅ Audit logs retrieved: {len(logs)} entries")
                
                for log in logs[:3]:  # Show first 3 logs
                    print(f"   {log['action']} by {log['admin_email']} on {log['user_email']}")
                    
                self.test_results['audit_logs'] = True
                return True
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
                self.test_results['audit_logs'] = False
                return False
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            self.test_results['audit_logs'] = False
            return False
            
    def test_user_dashboard_update(self) -> bool:
        """Test user dashboard update after admin changes"""
        print("🧪 Testing user dashboard data...")
        
        try:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = requests.get(f"{self.base_url}/api/auth/me", headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                user = result.get('user', {})
                usage_stats = user.get('usage_stats', {})
                
                print(f"✅ User data retrieved")
                print(f"   Plan: {user.get('current_plan')}")
                print(f"   Messages: {usage_stats.get('messages_sent')}/{usage_stats.get('messages_limit')}")
                
                self.test_results['user_dashboard_update'] = True
                return True
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
                self.test_results['user_dashboard_update'] = False
                return False
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            self.test_results['user_dashboard_update'] = False
            return False
            
    async def test_websocket_connection(self) -> bool:
        """Test WebSocket connection and events"""
        print("🧪 Testing WebSocket connection...")
        
        try:
            # Connect to WebSocket
            await self.sio.connect(f'{self.base_url.replace("http", "ws")}/socket.io')
            print("✅ WebSocket connected")
            
            # Test event emission
            await self.sio.emit('join_user_room', {'user_id': self.user_id})
            await asyncio.sleep(1)
            
            self.test_results['websocket_connection'] = True
            return True
            
        except Exception as e:
            print(f"❌ WebSocket failed: {e}")
            self.test_results['websocket_connection'] = False
            return False
            
    def test_security(self) -> bool:
        """Test security - non-admin access"""
        print("🧪 Testing security (non-admin access)...")
        
        try:
            # Try to access admin endpoint with user token
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response = requests.get(f"{self.base_url}/api/v1/admin/users", headers=headers)
            
            if response.status_code == 403:
                print("✅ Non-admin correctly denied access")
                self.test_results['security'] = True
                return True
            else:
                print(f"❌ Security issue: {response.status_code} - should be 403")
                self.test_results['security'] = False
                return False
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            self.test_results['security'] = False
            return False
            
    async def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting Admin Real-time Workflow Tests\n")
        
        # Setup
        if not await self.setup():
            print("❌ Setup failed, aborting tests")
            return
            
        # Run tests
        tests = [
            ('Admin Get Users', self.test_admin_get_users),
            ('Admin Update Plan', self.test_admin_update_plan),
            ('Admin Reset Usage', self.test_admin_reset_usage),
            ('Admin User Details', self.test_admin_user_details),
            ('Audit Logs', self.test_audit_logs),
            ('User Dashboard Update', self.test_user_dashboard_update),
            ('Security Test', self.test_security),
        ]
        
        success_count = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n{'='*50}")
            print(f"TEST: {test_name}")
            print('='*50)
            
            if test_func():
                success_count += 1
                
            time.sleep(1)  # Brief pause between tests
            
        # WebSocket test (async)
        print(f"\n{'='*50}")
        print("TEST: WebSocket Connection")
        print('='*50)
        
        if await self.test_websocket_connection():
            success_count += 1
        total_tests += 1
            
        # Results summary
        print(f"\n{'='*60}")
        print("🎯 TEST RESULTS SUMMARY")
        print('='*60)
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:<30} {status}")
            
        print(f"\n📊 Overall Success Rate: {success_count}/{total_tests} ({(success_count/total_tests)*100:.1f}%)")
        
        if success_count == total_tests:
            print("🎉 All tests passed! Admin real-time workflow is working correctly.")
        else:
            print(f"⚠️  {total_tests - success_count} test(s) failed. Review the output above.")
            
        # Cleanup
        if self.sio.connected:
            await self.sio.disconnect()
            
        return success_count == total_tests

async def main():
    """Main test runner"""
    tester = AdminRealtimeTest()
    success = await tester.run_all_tests()
    return success

if __name__ == "__main__":
    import sys
    result = asyncio.run(main())
    sys.exit(0 if result else 1) 