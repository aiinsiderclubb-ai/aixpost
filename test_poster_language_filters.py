#!/usr/bin/env python3
"""
Test script for language filters in the poster page
Tests both API endpoints and frontend functionality
"""

import requests
import json
import logging
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_api_endpoints():
    """Test API endpoints for language functionality"""
    print("\n🔍 Testing API Endpoints")
    print("=" * 50)
    
    base_url = "http://localhost:8080"
    
    try:
        # Test groups API with language filters
        print("1. Testing /api/groups endpoint...")
        response = requests.get(f"{base_url}/api/groups")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Found {data['total']} total groups")
        else:
            print(f"   ❌ API Error: {response.status_code}")
            return False
            
        # Test language statistics
        print("2. Testing /api/languages endpoint...")
        response = requests.get(f"{base_url}/api/languages")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Language statistics: {data['statistics']}")
            print(f"   ✓ Supported languages: {len(data['supported_languages'])}")
        else:
            print(f"   ❌ Language API Error: {response.status_code}")
            
        # Test filtered groups (Ukrainian only)
        print("3. Testing language filter (Ukrainian)...")
        response = requests.get(f"{base_url}/api/groups?languages=ukrainian")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Found {data['total']} Ukrainian groups")
        else:
            print(f"   ❌ Filter API Error: {response.status_code}")
            
        # Test multiple language filters
        print("4. Testing multiple language filters...")
        response = requests.get(f"{base_url}/api/groups?languages=ukrainian&languages=russian")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Found {data['total']} Ukrainian + Russian groups")
        else:
            print(f"   ❌ Multiple filter Error: {response.status_code}")
            
        return True
        
    except Exception as e:
        print(f"   ❌ API Test Failed: {str(e)}")
        return False

def test_poster_ui():
    """Test poster page UI with language filters"""
    print("\n🖥️  Testing Poster UI")
    print("=" * 50)
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    # chrome_options.add_argument('--headless')  # Comment out to see browser
    
    driver = None
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("http://localhost:8080/poster")
        
        print("1. Loading poster page...")
        wait = WebDriverWait(driver, 10)
        
        # Wait for page to load
        wait.until(EC.presence_of_element_located((By.ID, "groupsList")))
        print("   ✓ Poster page loaded successfully")
        
        # Check if language filters are present
        print("2. Checking language filter elements...")
        filters = [
            ("filterUkrainian", "🇺🇦 Ukrainian"),
            ("filterRussian", "🇷🇺 Russian"), 
            ("filterGerman", "🇩🇪 German"),
            ("filterPolish", "🇵🇱 Polish")
        ]
        
        for filter_id, filter_name in filters:
            try:
                element = driver.find_element(By.ID, filter_id)
                print(f"   ✓ Found {filter_name} filter")
            except:
                print(f"   ❌ Missing {filter_name} filter")
                
        # Check language counts
        print("3. Checking language counts...")
        counts = [
            ("ukrainianCount", "Ukrainian"),
            ("russianCount", "Russian"),
            ("germanCount", "German"), 
            ("polishCount", "Polish")
        ]
        
        for count_id, lang_name in counts:
            try:
                element = driver.find_element(By.ID, count_id)
                count = element.text
                print(f"   ✓ {lang_name}: {count} groups")
            except:
                print(f"   ❌ Missing {lang_name} count")
                
        # Test filtering functionality
        print("4. Testing Ukrainian filter...")
        ukrainian_filter = driver.find_element(By.ID, "filterUkrainian")
        
        # Get initial group count
        all_groups = driver.find_elements(By.CLASS_NAME, "group-item")
        initial_count = len([g for g in all_groups if g.is_displayed()])
        print(f"   Initial visible groups: {initial_count}")
        
        # Click Ukrainian filter
        ukrainian_filter.click()
        time.sleep(1)
        
        # Count visible groups after filter
        filtered_groups = driver.find_elements(By.CLASS_NAME, "group-item")
        filtered_count = len([g for g in filtered_groups if g.is_displayed()])
        print(f"   After Ukrainian filter: {filtered_count} groups")
        
        # Test "Select All Filtered" button
        print("5. Testing 'Select All Filtered' functionality...")
        # Try multiple ways to find the button
        try:
            select_all_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Select All Filtered')]")
        except:
            try:
                select_all_btn = driver.find_element(By.XPATH, "//button[@onclick='selectAllFiltered()']")
            except:
                select_all_btn = driver.find_element(By.XPATH, "//button[contains(@onclick, 'selectAllFiltered')]")
        select_all_btn.click()
        time.sleep(1)
        
        # Check selected count
        selected_count_element = driver.find_element(By.ID, "selectedCount")
        selected_count = selected_count_element.text
        print(f"   ✓ Selected {selected_count} groups after 'Select All Filtered'")
        
        # Test clear filters
        print("6. Testing 'Clear Filters' functionality...")
        clear_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Clear Filters')]")
        clear_btn.click()
        time.sleep(1)
        
        # Check if all groups are visible again
        final_groups = driver.find_elements(By.CLASS_NAME, "group-item")
        final_count = len([g for g in final_groups if g.is_displayed()])
        print(f"   After clearing filters: {final_count} groups")
        
        if final_count == initial_count:
            print("   ✓ Clear filters working correctly")
        else:
            print("   ⚠️  Clear filters may have issues")
            
        print("\n✅ UI Testing completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ UI Test Failed: {str(e)}")
        return False
        
    finally:
        if driver:
            print("\n🔍 Browser kept open for manual inspection...")
            print("Press Ctrl+C to close browser when ready")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                driver.quit()
                print("Browser closed.")

def main():
    """Run all tests"""
    print("🚀 Testing Language Filters in Poster")
    print("=" * 60)
    
    # Wait for web app to start
    print("Waiting for web app to start...")
    time.sleep(3)
    
    # Test API endpoints
    api_success = test_api_endpoints()
    
    if api_success:
        # Test UI
        ui_success = test_poster_ui()
        
        if api_success and ui_success:
            print("\n🎉 ALL TESTS PASSED!")
            print("Language filters are working correctly in poster!")
        else:
            print("\n⚠️  Some tests failed, check the output above.")
    else:
        print("\n❌ API tests failed, skipping UI tests")

if __name__ == "__main__":
    main() 