import os
import json
from selenium.webdriver.common.by import By

class CookieManager:
    def __init__(self, driver, cookies_file):
        self.driver = driver
        self.cookies_file = cookies_file

    def load_cookies(self):
        """Load cookies from file to reuse session"""
        if not self.driver or not os.path.exists(self.cookies_file):
            return False
        
        try:
            logger.info(f"Loading cookies from {self.cookies_file}")
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
            
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.warning(f"Error adding cookie: {str(e)}")
            
            logger.info(f"Successfully loaded {len(cookies)} cookies")
            return True
        except Exception as e:
            logger.error(f"Failed to load cookies: {str(e)}")
            return False

    def save_cookies(self):
        """Save cookies to file for session persistence"""
        if not self.driver:
            return False
        
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            
            logger.info(f"Saved {len(cookies)} cookies to {self.cookies_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save cookies: {str(e)}")
            return False
        
    def is_logged_in(self):
        """Check if already logged in based on page elements"""
        if not self.driver:
            return False
        
        try:
            # Check for common elements that indicate logged-in state
            indicators = [
                # Navigation menu
                (By.CSS_SELECTOR, "div[role='navigation']"),
                # Profile avatar
                (By.XPATH, "//div[@aria-label='Account' or @aria-label='Your profile']"),
                # Search bar
                (By.XPATH, "//input[@type='search' or @placeholder='Search Facebook']"),
                # Create button/icon
                (By.XPATH, "//div[@aria-label='Create' or @aria-label='New post']")
            ]
            
            for selector_type, selector in indicators:
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    if elements and any(el.is_displayed() for el in elements):
                        logger.info(f"Detected logged-in state via selector: {selector}")
                        return True
                except:
                    continue
            
            # Also check URL - if we're not on login page, likely logged in
            current_url = self.driver.current_url
            if ("facebook.com/home" in current_url or 
                "facebook.com/?" in current_url and "login" not in current_url or
                "facebook.com/groups" in current_url):
                logger.info(f"Detected logged-in state via URL: {current_url}")
                return True
            
            return False
        except Exception as e:
            logger.warning(f"Error checking login state: {str(e)}")
            return False 