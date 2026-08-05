#!/usr/bin/env python3
"""
Debug script to test Facebook posting field detection
Focused on Russian interface compatibility
"""

import sys
import os
import time
from datetime import datetime

# Add the bot directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from fb_poster import FacebookGroupPoster

def debug_field_detection():
    """Debug the field detection specifically"""
    
    print("=" * 60)
    print("Facebook Posting - Field Detection Debug")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Simple test message
    test_message = "Тест сообщения для отладки системы публикации"
    
    # Initialize the poster in non-headless mode for visual debugging
    print("Initializing bot in visible mode...")
    bot = FacebookGroupPoster(headless=False)
    
    try:
        # Setup driver
        if not bot.setup_driver():
            print("❌ Failed to setup WebDriver")
            return False
        print("✅ WebDriver setup successful")
        
        # Login
        print("\nAttempting login...")
        if not bot.login():
            print("❌ Failed to login")
            bot.cleanup()
            return False
        print("✅ Login successful")
        
        # Use first group from autofetched_groups.json if available
        groups_file = "autofetched_groups.json"
        if not os.path.exists(groups_file):
            groups_file = "groups.txt"
            
        if not os.path.exists(groups_file):
            print("❌ No groups file found")
            bot.cleanup()
            return False
            
        groups = bot.load_groups(groups_file)
        if not groups:
            print("❌ No groups found")
            bot.cleanup()
            return False
            
        test_group = groups[0]
        print(f"✅ Using test group: {test_group}")
        
        # Navigate to the group
        print(f"\nNavigating to group...")
        bot.driver.get(test_group)
        time.sleep(5)
        print("✅ Group page loaded")
        
        # Take a screenshot before attempting to find elements
        bot.take_screenshot("before_field_search")
        print("✅ Screenshot taken: before_field_search")
        
        # Try to find and interact with the posting field
        print("\nSearching for post creation field...")
        print("(Check the browser window to see what's happening)")
        
        # Wait for user to observe
        input("\nPress Enter when you're ready to start field detection...")
        
        # Try our new improved selectors step by step
        print("\n" + "=" * 40)
        print("TESTING FIELD DETECTION SELECTORS")
        print("=" * 40)
        
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
        
        # Test each selector individually
        selectors_to_test = [
            "//div[@role='button' and contains(@aria-label, 'Напишите что-нибудь')]",
            "//div[contains(@aria-label, 'Напишите что-нибудь')]",
            "//span[contains(text(), 'Напишите что-нибудь')]//ancestor::div[@role='button'][1]",
            "//div[@role='button' and contains(@aria-label, 'Write something')]",
            "//div[contains(@aria-label, 'Write something')]",
            "//div[@contenteditable='true' and @role='textbox']",
            "//div[@role='textbox' and @contenteditable='true']"
        ]
        
        found_element = None
        for i, selector in enumerate(selectors_to_test):
            print(f"\nTesting selector {i+1}: {selector}")
            try:
                element = WebDriverWait(bot.driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
                print(f"✅ FOUND with selector {i+1}")
                
                # Check if element is visible and clickable
                if element.is_displayed() and element.is_enabled():
                    print(f"✅ Element is visible and enabled")
                    found_element = element
                    break
                else:
                    print(f"⚠️ Element found but not visible/enabled")
                    
            except TimeoutException:
                print(f"❌ Not found with selector {i+1}")
            except Exception as e:
                print(f"❌ Error with selector {i+1}: {str(e)}")
        
        if not found_element:
            # Try JavaScript approach
            print(f"\n🔍 Trying JavaScript approach...")
            try:
                js_result = bot.driver.execute_script("""
                    // Look for elements with Russian text
                    let elements = document.querySelectorAll('*');
                    for (let element of elements) {
                        let text = element.textContent || element.getAttribute('aria-label') || '';
                        if (text.includes('Напишите что-нибудь') || text.includes('Write something')) {
                            console.log('Found element with text:', text);
                            element.style.border = '3px solid red';  // Highlight it
                            return {
                                tagName: element.tagName,
                                role: element.getAttribute('role'),
                                ariaLabel: element.getAttribute('aria-label'),
                                text: element.textContent,
                                contentEditable: element.contentEditable
                            };
                        }
                    }
                    return null;
                """)
                
                if js_result:
                    print(f"✅ JavaScript found element:")
                    print(f"   Tag: {js_result.get('tagName')}")
                    print(f"   Role: {js_result.get('role')}")
                    print(f"   Aria-label: {js_result.get('ariaLabel')}")
                    print(f"   Text: {js_result.get('text', '')[:50]}...")
                    print(f"   ContentEditable: {js_result.get('contentEditable')}")
                else:
                    print(f"❌ JavaScript also didn't find the element")
                    
            except Exception as e:
                print(f"❌ JavaScript approach failed: {str(e)}")
        
        # Take a screenshot after search
        bot.take_screenshot("after_field_search")
        print("✅ Screenshot taken: after_field_search")
        
        if found_element:
            print(f"\n🎯 Found posting field! Attempting to click...")
            try:
                # Scroll into view
                bot.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", found_element)
                time.sleep(1)
                
                # Click
                found_element.click()
                print("✅ Successfully clicked the post creation field")
                
                # Wait and take screenshot
                time.sleep(3)
                bot.take_screenshot("after_click")
                print("✅ Screenshot taken: after_click")
                
                print("\n👀 Check the browser - did a composer dialog open?")
                input("Press Enter to continue...")
                
                return True
                
            except Exception as e:
                print(f"❌ Failed to click: {str(e)}")
                return False
        else:
            print(f"\n❌ Could not find the post creation field")
            print("📝 Please check the screenshots and browser window for debugging")
            return False
            
    except Exception as e:
        print(f"❌ Error during debugging: {str(e)}")
        return False
    finally:
        print(f"\n⏹️ Keeping browser open for inspection...")
        input("Press Enter to close browser and exit...")
        bot.cleanup()

if __name__ == "__main__":
    print("Facebook Posting - Field Detection Debugger")
    print("This will help debug the field detection issue with Russian interface")
    print("\nIMPORTANT: This will open a browser window. Watch it during execution!")
    
    try:
        confirm = input("\nProceed with debugging? (y/N): ")
        if confirm.lower() != 'y':
            print("Debug cancelled.")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nDebug cancelled.")
        sys.exit(0)
    
    debug_field_detection() 