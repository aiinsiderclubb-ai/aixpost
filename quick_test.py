#!/usr/bin/env python3

import requests
import json
import time

BASE_URL = "http://localhost:8080"

def test_main_functionality():
    """Test main functionality after fixes"""
    
    print("🧪 Quick Test After Password Fix")
    print("=" * 40)
    
    # Test 1: Health check
    print("\n1. Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Server is healthy")
        else:
            print(f"❌ Server health check failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health check error: {e}")
    
    # Test 2: Main page
    print("\n2. Main Page")
    try:
        response = requests.get(BASE_URL)
        if response.status_code == 200:
            print("✅ Main page loads successfully")
            if "Facebook Group Fetcher" in response.text:
                print("✅ Main page contains expected content")
            else:
                print("❌ Main page content not found")
        else:
            print(f"❌ Main page failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Main page error: {e}")
    
    # Test 3: Login with existing admin
    print("\n3. Admin Login")
    try:
        login_data = {
            "email": "admin@test.com",
            "password": "Admin123!"
        }
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
        result = response.json()
        
        if response.status_code == 200:
            print("✅ Admin login successful")
            admin_token = result.get('access_token')
            
            # Test admin panel access
            print("\n4. Admin Panel Access")
            headers = {'Authorization': f'Bearer {admin_token}'}
            response = requests.get(f"{BASE_URL}/admin", headers=headers)
            
            if response.status_code == 200:
                print("✅ Admin panel accessible")
            else:
                print(f"❌ Admin panel access failed: {response.status_code}")
                
        else:
            print(f"❌ Admin login failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Admin login error: {e}")
    
    # Test 4: Registration with valid password (after waiting)
    print("\n5. Registration Test (after delay)")
    time.sleep(65)  # Wait for rate limit to reset
    
    try:
        unique_email = f"testuser{int(time.time())}@test.com"
        register_data = {
            "first_name": "Test",
            "last_name": "User",
            "email": unique_email,
            "password": "Test123"  # Valid password
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/register", json=register_data)
        result = response.json()
        
        if response.status_code == 201:
            print("✅ Registration with valid password successful")
            print(f"   User: {result.get('user', {}).get('full_name', 'N/A')}")
        else:
            print(f"❌ Registration failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Registration error: {e}")
    
    print("\n" + "=" * 40)
    print("🎉 Quick test completed!")

if __name__ == "__main__":
    test_main_functionality() 