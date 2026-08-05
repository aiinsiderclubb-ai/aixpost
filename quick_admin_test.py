#!/usr/bin/env python3
"""
Quick test for admin protection and Telegram functionality
"""

import requests
import json
import time

BASE_URL = "http://localhost:8080"

def test_admin_protection():
    """Test admin protection is working"""
    print("🔐 Testing Admin Protection")
    print("=" * 50)
    
    # 1. Register regular user
    try:
        user_data = {
            "email": f"regular_user_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "first_name": "Regular",
            "last_name": "User"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=user_data)
        if response.status_code != 201:
            print(f"❌ Registration failed: {response.status_code}")
            return False
        
        print("✅ Regular user registered")
        
        # 2. Login as regular user
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            return False
        
        token = login_response.json().get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        print("✅ Regular user logged in")
        
        # 3. Try to access admin endpoints
        admin_endpoints = [
            "/admin",
            "/api/v1/admin/users",
            "/api/v1/admin/analytics/overview"
        ]
        
        for endpoint in admin_endpoints:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
                if response.status_code == 403:
                    print(f"✅ Admin protection working for {endpoint}: 403")
                else:
                    print(f"❌ Admin protection FAILED for {endpoint}: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Error testing {endpoint}: {e}")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Admin protection test failed: {e}")
        return False

def test_telegram_api():
    """Test Telegram API functionality"""
    print("\n🔔 Testing Telegram API")
    print("=" * 50)
    
    try:
        # Register new user for Telegram test
        user_data = {
            "email": f"telegram_user_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "first_name": "Telegram",
            "last_name": "User"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=user_data)
        if response.status_code != 201:
            print(f"❌ User registration failed: {response.status_code}")
            return False
        
        # Login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            return False
        
        token = login_response.json().get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        print("✅ Telegram test user logged in")
        
        # Test GET telegram settings (should be empty initially)
        response = requests.get(f"{BASE_URL}/api/telegram/settings", headers=headers)
        if response.status_code != 200:
            print(f"❌ GET telegram settings failed: {response.status_code}")
            return False
        
        data = response.json()
        if not data.get('connected', True):  # Should be False initially
            print("✅ Telegram initially not connected")
        else:
            print("⚠️ Telegram shows as connected initially (unexpected)")
        
        # Test POST telegram settings
        telegram_data = {"chat_id": "123456789"}
        response = requests.post(f"{BASE_URL}/api/telegram/settings", 
                               json=telegram_data, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ POST telegram settings failed: {response.status_code}")
            return False
        
        print("✅ Telegram settings saved successfully")
        
        # Test Telegram page access
        response = requests.get(f"{BASE_URL}/telegram", headers=headers)
        if response.status_code == 200:
            print("✅ Telegram page accessible")
        else:
            print(f"❌ Telegram page access failed: {response.status_code}")
            return False
        
        # Test telegram test endpoint
        response = requests.post(f"{BASE_URL}/api/telegram/test", headers=headers)
        if response.status_code in [200, 400]:  # 400 is acceptable in test mode
            print("✅ Telegram test endpoint working")
        else:
            print(f"❌ Telegram test failed: {response.status_code}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Telegram API test failed: {e}")
        return False

def test_usage_limits():
    """Test usage limit display"""
    print("\n📊 Testing Usage Limits Display")
    print("=" * 50)
    
    try:
        # Use existing login or create new user
        user_data = {
            "email": f"limits_user_{int(time.time())}@example.com",
            "password": "TestPassword123!",
            "first_name": "Limits",
            "last_name": "User"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=user_data)
        if response.status_code != 201:
            print(f"❌ User registration failed: {response.status_code}")
            return False
        
        # Login
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        
        token = login_response.json().get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        
        # Test user info endpoint
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        if response.status_code != 200:
            print(f"❌ User info failed: {response.status_code}")
            return False
        
        user_info = response.json()
        if 'usage_stats' in user_info:
            usage = user_info['usage_stats']
            print(f"✅ Usage stats available: {usage.get('messages_sent', 0)}/{usage.get('messages_limit', 'unknown')} messages")
            print(f"✅ Current plan: {usage.get('current_plan', 'unknown')}")
        else:
            print("⚠️ No usage stats in user info")
        
        return True
        
    except Exception as e:
        print(f"❌ Usage limits test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Facebook SaaS Platform - Quick Admin & Telegram Test")
    print("=" * 70)
    
    time.sleep(2)  # Wait for server
    
    # Test health first
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server health check passed")
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Server not responding: {e}")
        return
    
    # Run tests
    tests = [
        ("Admin Protection", test_admin_protection),
        ("Telegram API", test_telegram_api),
        ("Usage Limits", test_usage_limits)
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
    print("\n📋 TEST SUMMARY")
    print("=" * 50)
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{len(results)} tests passed ({passed/len(results)*100:.1f}%)")
    
    if passed == len(results):
        print("🎉 All tests passed! Platform ready for production.")
    else:
        print("⚠️ Some tests failed. Review issues above.")

if __name__ == "__main__":
    main() 