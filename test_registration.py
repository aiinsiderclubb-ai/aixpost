#!/usr/bin/env python3

import requests
import json
import time

BASE_URL = "http://localhost:8080"

def test_registration():
    """Test registration with different passwords"""
    
    test_cases = [
        {
            "name": "Valid password (letters + numbers)",
            "password": "Test123",
            "should_pass": True
        },
        {
            "name": "Valid password (simple)",
            "password": "abc123",
            "should_pass": True
        },
        {
            "name": "Too short password",
            "password": "ab1",
            "should_pass": False
        },
        {
            "name": "Only letters",
            "password": "abcdef",
            "should_pass": False
        },
        {
            "name": "Only numbers",
            "password": "123456",
            "should_pass": False
        },
        {
            "name": "Complex password",
            "password": "MyPassword123",
            "should_pass": True
        }
    ]
    
    print("🧪 Testing Registration with Different Passwords")
    print("=" * 50)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['name']}")
        print(f"Password: '{test['password']}'")
        
        # Create unique email for each test
        email = f"test{int(time.time())}_{i}@example.com"
        
        data = {
            "first_name": "Test",
            "last_name": "User",
            "email": email,
            "password": test['password']
        }
        
        try:
            response = requests.post(f"{BASE_URL}/api/auth/register", json=data)
            result = response.json()
            
            if test['should_pass']:
                if response.status_code == 201:
                    print(f"✅ PASS - Registration successful")
                    print(f"   User: {result.get('user', {}).get('full_name', 'N/A')}")
                else:
                    print(f"❌ FAIL - Expected success but got error: {result.get('error', 'Unknown error')}")
            else:
                if response.status_code != 201:
                    print(f"✅ PASS - Registration correctly failed: {result.get('error', 'Unknown error')}")
                else:
                    print(f"❌ FAIL - Expected failure but registration succeeded")
                    
        except Exception as e:
            print(f"❌ ERROR - Network error: {e}")
            
        time.sleep(0.5)  # Small delay between tests

if __name__ == "__main__":
    test_registration() 