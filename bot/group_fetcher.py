"""
Facebook Group Fetcher - Premium SaaS Version
Module to reliably fetch and extract a user's joined Facebook groups
"""

from __future__ import annotations

import os
import json
import time
import logging
import pickle
from pathlib import Path
from datetime import datetime
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementNotInteractableException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    WebDriverException
)

# Setup logging
logger = logging.getLogger('fb_group_fetcher')

# Constants
SCREENSHOTS_DIR = "screenshots"
OUTPUT_FILE = "autofetched_groups.json"  # legacy; server will move per-user
COOKIES_FILE = "facebook_cookies.json"
PROFILE_DIR = "chrome_profile"  # legacy fallback; will be overridden per-user
MAX_RETRIES = 3
MAX_WAIT = 15  # seconds
SCROLL_PAUSE = 2  # seconds
MANUAL_VERIFICATION_TIMEOUT = int(os.environ.get("FB_MANUAL_VERIFICATION_TIMEOUT", "900"))


class FacebookGroupFetcher:
    """Enhanced class to reliably fetch Facebook groups a user is a member of"""

    def __init__(self, username=None, password=None, output_file=OUTPUT_FILE, headless=False,
                 use_session=True, reset_session=False, profile_dir=PROFILE_DIR, cookies_file=COOKIES_FILE,
                 user_id: int | None = None, progress_callback=None):
        """Initialize the fetcher with login credentials and session options"""
        self.username = username
        self.password = password
        self.output_file = output_file
        self.headless = headless
        self.use_session = use_session
        self.reset_session = reset_session
        # Configure per-user profile directory if user_id provided
        self.profile_dir = profile_dir
        if user_id is not None:
            base_profiles = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'user_data', 'profiles')
            self.profile_dir = os.path.abspath(os.path.join(base_profiles, f"profile_user_{user_id}"))
        # Place cookies file inside profile
        if self.profile_dir:
            self.cookies_file = os.path.join(self.profile_dir, 'facebook_cookies.json')
        else:
            self.cookies_file = cookies_file
        self.driver = None
        self.groups = []
        self.is_fetching = False
        self.error = None
        self.step = "initializing"
        self.session_loaded = False
        self.force_direct_navigation = False
        self.current_scroll = 0
        self.progress_callback = progress_callback
        self.max_scroll_attempts = 0
        self.manual_verification_needed = False

        # Create necessary directories
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        if not reset_session and use_session and self.profile_dir:
            os.makedirs(self.profile_dir, exist_ok=True)

    def _emit_progress(self, **kwargs):
        if callable(self.progress_callback):
            try:
                payload = {
                    "step": self.step,
                    "total_groups": len(self.groups),
                    "current_scroll": self.current_scroll,
                    "max_scroll": self.max_scroll_attempts,
                }
                payload.update(kwargs)
                self.progress_callback(payload)
            except Exception:
                pass

    def _ensure_window_alive(self, context="fetching"):
        if not self.driver:
            self.error = f"Browser session missing while {context}"
            return False
        try:
            _ = self.driver.current_url
            return True
        except WebDriverException as e:
            self.error = f"Browser window was closed while {context}: {str(e)}"
            logger.error(self.error)
            self._emit_progress(status="failed", error=self.error)
            return False

    def setup_driver(self):
        """Set up and configure the Chrome WebDriver with anti-detection measures and session support"""
        logger.info("Setting up Chrome WebDriver")
        self.step = "driver_setup"
        self._emit_progress(step="driver_setup", progress=5, status="running")

        def _build_options(headless_flag: bool):
            chrome_options = Options()
            if headless_flag:
                # Prefer modern headless, fallback will apply below
                chrome_options.add_argument("--headless=new")
            # Add user data directory if using session (avoid profile in headless on macOS — can crash renderer)
            if self.use_session and not self.reset_session and self.profile_dir and not headless_flag:
                profile_path = os.path.abspath(self.profile_dir)
                logger.info(f"Using Chrome profile directory: {profile_path}")
                chrome_options.add_argument(f"--user-data-dir={profile_path}")
                chrome_options.add_argument("--profile-directory=Default")
            # Essential options to avoid detection and improve stability
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            # Stability flags
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--no-zygote")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--use-gl=swiftshader")
            # User experience options
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--start-maximized")
            # Human-like user agent
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
            chrome_options.add_argument("--lang=en-US")
            return chrome_options

        try:
            # First attempt
            try_headless = bool(self.headless)
            for attempt in range(2):
                try:
                    chrome_options = _build_options(try_headless)
                    service_path = "/opt/homebrew/bin/chromedriver"
                    if os.path.exists(service_path):
                        service = Service(service_path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                    else:
                        driver = webdriver.Chrome(options=chrome_options)
                    self.driver = driver
                    break
                except WebDriverException as e:
                    err = str(e).lower()
                    logger.warning(f"Chrome init failed (attempt {attempt+1}): {e}")
                    # Retry once toggling headless mode or with legacy headless
                    if attempt == 0:
                        try_headless = not try_headless
                        continue
                    # Final fallback: legacy headless
                    if "headless=new" in err:
                        chrome_options = _build_options(True)
                        chrome_options.arguments = [arg for arg in chrome_options.arguments if not arg.startswith("--headless")]  # remove new headless
                        chrome_options.add_argument("--headless")
                        service_path = "/opt/homebrew/bin/chromedriver"
                        if os.path.exists(service_path):
                            service = Service(service_path)
                            driver = webdriver.Chrome(service=service, options=chrome_options)
                        else:
                            driver = webdriver.Chrome(options=chrome_options)
                        self.driver = driver
                        break
                    raise

            if not self.driver:
                self.error = "Failed to initialize WebDriver - driver is None"
                logger.error(self.error)
                return False

            # Additional anti-detection measures via CDP
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5].map(() => ({ length:1, item: () => ({}) })) });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en','es'] });
                    window.chrome = { runtime:{}, loadTimes:function(){}, csi:function(){}, app:{} };
                """
            })

            # Start with Facebook login page
            try:
                logger.info("Navigating to Facebook login page")
                self.driver.get("https://www.facebook.com/")
                WebDriverWait(self.driver, MAX_WAIT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                self._handle_cookie_dialogs()
                current_url = self.driver.current_url
                if not current_url.startswith("https://www.facebook.com") and not current_url.startswith("https://facebook.com"):
                    self.error = f"URL verification failed. Current URL: {current_url}"
                    logger.error(self.error)
                    self.take_screenshot("invalid_url")
                    return False
                logger.info(f"Successfully loaded Facebook page: {current_url}")
            except Exception as e:
                self.error = f"Failed to navigate to Facebook: {str(e)}"
                logger.error(self.error)
                self.take_screenshot("navigation_error")
                return False

            # If using session but not through profile, load cookies
            if self.use_session and not self.reset_session and not self.profile_dir and os.path.exists(self.cookies_file):
                if self.load_cookies():
                    self.driver.refresh()
                    time.sleep(3)

            logger.info("Chrome WebDriver initialized successfully")
            self._emit_progress(step="driver_setup", progress=15, status="running")
            return True
        except Exception as e:
            self.error = f"Failed to initialize Chrome WebDriver: {str(e)}"
            logger.error(self.error)
            if hasattr(self, 'driver') and self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
            return False

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
            cookies = self.driver.get_cookies()
            if any(c.get('name') == 'c_user' and c.get('value') for c in cookies):
                logger.info("Detected logged-in state via c_user cookie")
                return True
        except Exception:
            pass

        try:
            # Check for common elements that indicate logged-in state
            indicators = [
                # Navigation menu
                (By.CSS_SELECTOR, "div[role='navigation']"),
                (By.CSS_SELECTOR, "div[role='banner']"),
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
                except Exception:
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

    def _handle_cookie_dialogs(self) -> bool:
        """Dismiss Facebook cookie consent overlays that block the login form."""
        if not self.driver:
            return False
        cookie_selectors = [
            "//button[contains(text(), 'Allow all cookies')]",
            "//span[contains(text(), 'Allow all cookies')]/ancestor::div[@role='button'][1]",
            "//span[contains(text(), 'Allow all cookies')]/ancestor::button[1]",
            "//button[contains(text(), 'Accept essential and optional cookies')]",
            "//button[contains(text(), 'Only allow essential cookies')]",
            "//button[contains(text(), 'Decline optional cookies')]",
            "//button[contains(string(), 'Allow') or contains(string(), 'Accept')]",
            "//button[contains(@data-testid, 'cookie-policy')]",
            "//span[contains(text(), 'Разрешить все cookie')]/ancestor::div[@role='button'][1]",
            "//span[contains(text(), 'Принять все')]/ancestor::div[@role='button'][1]",
            "//span[contains(text(), 'Alle akzeptieren')]/ancestor::div[@role='button'][1]",
        ]
        for selector in cookie_selectors:
            try:
                button = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                try:
                    button.click()
                except (ElementClickInterceptedException, ElementNotInteractableException):
                    self.driver.execute_script("arguments[0].click();", button)
                logger.info("Dismissed cookie dialog via: %s", selector)
                time.sleep(1)
                return True
            except TimeoutException:
                continue
            except Exception as exc:
                logger.debug("Cookie selector failed (%s): %s", selector, exc)
        return False

    def _find_login_field(self, field_type: str):
        """Find email or password input using multiple Facebook login selectors."""
        if field_type == "email":
            selectors = [
                (By.ID, "email"),
                (By.NAME, "email"),
                (By.NAME, "m_login_email"),
                (By.ID, "m_login_email"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[autocomplete='username']"),
                (By.XPATH, "//input[@placeholder='Email or phone number']"),
                (By.XPATH, "//input[@placeholder='Email or mobile number']"),
                (By.XPATH, "//input[contains(@placeholder, 'Email')]"),
                (By.XPATH, "//input[contains(@placeholder, 'phone') or contains(@placeholder, 'Phone')]"),
                (By.XPATH, "//input[@autocomplete='username' or @autocomplete='email']"),
                (By.XPATH, "//input[@data-testid='royal_email']"),
                (By.XPATH, "//form//input[@type='text'][1]"),
            ]
        else:
            selectors = [
                (By.ID, "pass"),
                (By.NAME, "pass"),
                (By.NAME, "m_login_password"),
                (By.ID, "m_login_password"),
                (By.CSS_SELECTOR, "input[name='pass']"),
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
                (By.XPATH, "//input[@placeholder='Password']"),
                (By.XPATH, "//input[contains(@placeholder, 'Password')]"),
                (By.XPATH, "//input[@data-testid='royal_pass']"),
                (By.XPATH, "//form//input[@type='password'][1]"),
            ]
        for selector_type, selector in selectors:
            try:
                field = WebDriverWait(self.driver, 4).until(
                    EC.element_to_be_clickable((selector_type, selector))
                )
                logger.info("Found %s field via %s", field_type, selector)
                return field
            except TimeoutException:
                continue
        return None

    def _fill_login_field(self, field, value: str) -> None:
        try:
            self.driver.execute_script(
                """
                var el = arguments[0];
                el.focus();
                el.value = '';
                el.dispatchEvent(new Event('input', {bubbles: true}));
                """,
                field,
            )
        except Exception:
            pass
        field.clear()
        time.sleep(0.2)
        field.send_keys(Keys.CONTROL + "a")
        field.send_keys(Keys.DELETE)
        time.sleep(0.2)
        field.send_keys(value)

    def _is_manual_verification_required(self) -> bool:
        """Detect CAPTCHA, checkpoint, 2FA or 'not a robot' challenges."""
        if not self.driver:
            return False
        try:
            url = (self.driver.current_url or "").lower()
            if any(
                token in url
                for token in (
                    "checkpoint",
                    "two_step",
                    "two-factor",
                    "approvals",
                    "captcha",
                    "security",
                    "confirm",
                    "login/device-based",
                )
            ):
                return True
        except Exception:
            pass

        page_source = ""
        try:
            page_source = (self.driver.page_source or "").lower()
        except Exception:
            pass

        if any(
            phrase in page_source
            for phrase in (
                "not a robot",
                "i'm not a robot",
                "im not a robot",
                "recaptcha",
                "security check",
                "two-factor",
                "authentication code",
                "enter the code",
            )
        ):
            return True

        xpath_indicators = [
            "//iframe[contains(@src, 'recaptcha')]",
            "//iframe[contains(@src, 'captcha')]",
            "//div[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'not a robot')]",
            "//span[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'not a robot')]",
            "//input[contains(@id, 'approvals_code')]",
            "//input[contains(@id, '2fa')]",
            "//input[contains(@placeholder, 'code')]",
        ]
        for indicator in xpath_indicators:
            try:
                if self.driver.find_elements(By.XPATH, indicator):
                    return True
            except Exception:
                continue
        return False

    def _wait_for_manual_verification(self, reason: str, timeout_seconds: Optional[int] = None) -> bool:
        """Keep browser open and poll until user completes CAPTCHA/2FA/checkpoint."""
        timeout = timeout_seconds or MANUAL_VERIFICATION_TIMEOUT
        self.manual_verification_needed = True

        if self.headless:
            self.error = (
                f"{reason} Откройте браузер (выключите headless), пройдите проверку и запустите снова."
            )
            logger.warning(self.error)
            return False

        self.step = "manual_verification"
        logger.info("Waiting up to %ss for manual verification", timeout)
        self.take_screenshot("manual_verification_required")
        deadline = time.time() + timeout

        while time.time() < deadline:
            if not self._ensure_window_alive("manual verification"):
                return False
            if getattr(self, "manual_resume_requested", False):
                self.manual_resume_requested = False
                time.sleep(2)
            if self.is_logged_in():
                logger.info("Manual verification completed successfully")
                self.manual_verification_needed = False
                self.save_session()
                self._emit_progress(step="login", progress=30, status="running", message="")
                return True

            remaining = max(0, int(deadline - time.time()))
            self._emit_progress(
                step="manual_verification",
                progress=22,
                status="waiting_manual",
                message=f"{reason} Пройдите проверку в Chrome или нажмите «Я прошёл проверку». Осталось ~{remaining // 60} мин.",
            )
            time.sleep(2)

        self.error = f"{reason} Время ожидания истекло ({timeout // 60} мин)."
        logger.error(self.error)
        self.take_screenshot("manual_verification_timeout")
        return False

    def take_screenshot(self, name):
        """Take a screenshot for debugging purposes"""
        if not self.driver:
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{SCREENSHOTS_DIR}/{name}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            logger.info(f"Screenshot saved: {filename}")
        except Exception as e:
            logger.warning(f"Failed to take screenshot: {str(e)}")

    def login(self):
        """Log in to Facebook with error handling and verification"""
        if not self.driver:
            self.error = "WebDriver not initialized"
            logger.error(self.error)
            return False

        self.step = "login"
        self._emit_progress(step="login", progress=20, status="running")

        # Check if already logged in (session reuse)
        if self.is_logged_in():
            logger.info("Already logged in via persistent session, skipping login form")
            self.take_screenshot("existing_session_detected")
            self.session_loaded = True
            self._emit_progress(step="login", progress=28, status="running")
            return True

        logger.info("Not logged in, attempting to log in to Facebook")

        # Reset session if requested
        if self.reset_session:
            try:
                logger.info("Clearing cookies as session reset was requested")
                self.driver.delete_all_cookies()
                self.driver.refresh()
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Error clearing cookies: {str(e)}")

        try:
            login_urls = [
                "https://www.facebook.com/login",
                "https://www.facebook.com/",
            ]
            email_field = None
            password_field = None

            for login_url in login_urls:
                logger.info("Trying login URL: %s", login_url)
                self.driver.get(login_url)
                time.sleep(2)
                self._handle_cookie_dialogs()
                time.sleep(0.5)
                self._handle_cookie_dialogs()
                self.take_screenshot("login_form_before")
                email_field = self._find_login_field("email")
                if email_field:
                    password_field = self._find_login_field("password")
                    if password_field:
                        break

            if not email_field or not password_field:
                self.error = "Timeout waiting for login form elements"
                logger.error(self.error)
                self.take_screenshot("login_form_timeout")
                return False

            self.take_screenshot("login_form_elements_found")
            self._fill_login_field(email_field, self.username)
            time.sleep(0.5)
            self._fill_login_field(password_field, self.password)
            time.sleep(0.5)
            self.take_screenshot("credentials_entered")

            # Multiple strategies to find and click the login button
            login_btn = None
            login_selectors = [
                (By.NAME, "login"),
                (By.ID, "loginbutton"),
                (By.XPATH, "//button[@type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Log In')]"),
                (By.XPATH, "//button[contains(text(), 'Log in')]"),
                (By.XPATH, "//input[@type='submit']"),
                (By.CSS_SELECTOR, "button[data-testid='royal_login_button']"),
            ]

            for selector_type, selector in login_selectors:
                try:
                    login_btn = WebDriverWait(self.driver, 2).until(
                        EC.element_to_be_clickable((selector_type, selector))
                    )
                    if login_btn:
                        break
                except TimeoutException:
                    continue

            if not login_btn:
                logger.info("Login button not found, trying to submit form with Enter key")
                password_field.send_keys(Keys.RETURN)
            else:
                try:
                    login_btn.click()
                except (ElementClickInterceptedException, ElementNotInteractableException):
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", login_btn)
                        time.sleep(0.5)
                        login_btn.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", login_btn)

            self.take_screenshot("after_login_click")
            time.sleep(3)
            self._handle_cookie_dialogs()

            if self._is_manual_verification_required():
                if self._wait_for_manual_verification(
                    "Facebook требует проверку (CAPTCHA / I'm not a robot)."
                ):
                    self._emit_progress(step="login", progress=30, status="running")
                    return True

            current_url = self.driver.current_url
            logger.info(f"Current URL after login attempt: {current_url}")

            if self.is_logged_in():
                logger.info("Login successful")
                self.take_screenshot("login_successful")
                self.save_session()
                self._emit_progress(step="login", progress=30, status="running")
                return True

            failure_patterns = [
                "error=",
                "not-logged-in",
                "login_attempt",
            ]

            for pattern in failure_patterns:
                if pattern in current_url and not self.is_logged_in():
                    try:
                        error_messages = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            "#loginform div.uiContextualLayer, .login_error_box, #error_box, div[data-testid='login_error']",
                        )
                        if error_messages:
                            error_text = error_messages[0].text
                            self.error = f"Login failed: {error_text}"
                        else:
                            self.error = "Login failed: Please check your credentials"
                    except Exception:
                        self.error = "Login failed: Please check your credentials"
                    logger.error(self.error)
                    self.take_screenshot("login_failed")
                    return False

            if self._is_manual_verification_required():
                if self._wait_for_manual_verification(
                    "Facebook требует проверку (CAPTCHA / I'm not a robot)."
                ):
                    return True

            self.error = "Login state could not be verified. Unknown login state."
            logger.warning(self.error)
            self.take_screenshot("login_uncertain")
            return False

        except TimeoutException:
            self.error = "Timeout waiting for login form elements"
            logger.error(self.error)
            self.take_screenshot("login_form_timeout")
            return False

        except Exception as e:
            self.error = f"Login process failed: {str(e)}"
            logger.error(self.error)
            self.take_screenshot("login_exception")
            # One-time recovery for invalid session id
            if "invalid session id" in str(e).lower() or "session deleted" in str(e).lower():
                try:
                    logger.warning("Attempting one-time WebDriver reinit after session error...")
                    if self.driver:
                        try:
                            self.driver.quit()
                        except:
                            pass
                        self.driver = None
                    # toggle headless mode for recovery
                    self.headless = not self.headless
                    if self.setup_driver():
                        return self.login()
                except Exception as _:
                    pass
            return False
    
    def save_session(self):
        """Save the current session for future use"""
        if not self.driver:
            return False
        
        # Save cookies
        self.save_cookies()
        
        # Profile directory is automatically maintained by Chrome
        if self.profile_dir:
            logger.info(f"Chrome profile being maintained at: {os.path.abspath(self.profile_dir)}")
        
        logger.info("Session saved successfully")
        return True

    def navigate_to_groups(self):
        """Navigate to the 'Your groups' page following the most reliable path"""
        if not self.driver:
            self.error = "WebDriver not initialized"
            logger.error(self.error)
            return False
            
        self.step = "navigate_to_groups"
        logger.info("Navigating to groups feed page")
        self._emit_progress(step="navigate_to_groups", progress=35, status="running")
        
        try:
            # Go directly to groups feed
            self.driver.get("https://www.facebook.com/groups/feed/")
            time.sleep(3)
            self.take_screenshot("groups_feed_page")
            
            # Wait for the page to load
            try:
                WebDriverWait(self.driver, MAX_WAIT).until(
                    lambda d: "facebook.com/groups" in d.current_url
                )
                logger.info(f"Successfully navigated to groups page: {self.driver.current_url}")
            except TimeoutException:
                self.error = "Failed to navigate to groups feed page"
                logger.error(self.error)
                self.take_screenshot("groups_navigation_failed")
                return False
                
            # Verify we're on a groups page
            if "facebook.com/groups" not in self.driver.current_url:
                self.error = f"Not on a groups page. Current URL: {self.driver.current_url}"
                logger.error(self.error)
                self.take_screenshot("wrong_groups_page")
                return False
                
            logger.info("Successfully navigated to groups feed page")
            self._emit_progress(step="navigate_to_groups", progress=45, status="running")
            return True
            
        except Exception as e:
            self.error = f"Failed to navigate to groups page: {str(e)}"
            logger.error(self.error)
            self.take_screenshot("groups_navigation_exception")
            return False
    
    def find_see_all_button(self):
        """Find and click the 'See All' button for joined groups"""
        if not self.driver:
            self.error = "WebDriver not initialized"
            logger.error(self.error)
            return False
            
        self.step = "find_see_all"
        self._emit_progress(step="find_see_all", progress=50, status="running")
        
        # If force direct navigation is enabled, bypass UI navigation
        if self.force_direct_navigation:
            logger.info("Force direct navigation enabled, going directly to groups list")
            
            # Try several URLs that could show the groups list
            direct_urls = [
                "https://www.facebook.com/groups/joins/?nav_source=tab",
                "https://www.facebook.com/groups/your_groups",
                "https://www.facebook.com/groups/yours"
            ]
            
            for url in direct_urls:
                try:
                    logger.info(f"Trying direct navigation to: {url}")
                    self.driver.get(url)
                    time.sleep(5)  # Wait for page to load
                    
                    # Take screenshot
                    self.take_screenshot(f"direct_navigation_{url.split('/')[-1]}")
                    
                    # Verify we're on a groups page
                    current_url = self.driver.current_url
                    if "/groups/" in current_url:
                        logger.info(f"Successfully navigated directly to groups list: {current_url}")
                        return True
                except Exception as e:
                    logger.warning(f"Error navigating to {url}: {str(e)}")
            
            # If all direct URLs failed, try one more with ?joined=1 parameter
            try:
                final_url = "https://www.facebook.com/groups/feed/?joined=1"
                logger.info(f"Trying final direct navigation to: {final_url}")
                self.driver.get(final_url)
                time.sleep(5)
                self.take_screenshot("direct_navigation_final")
                return True
            except Exception as e:
                logger.warning(f"Error navigating to final URL: {str(e)}")
                # Continue with normal flow as fallback
        
        logger.info("Searching for 'See All' button")
        self.take_screenshot("before_see_all_search")
        
        # Wait for sidebar to load
        time.sleep(3)
        
        # Multiple selector patterns for "See All" link in different languages
        see_all_selectors = [
            # English
            (By.XPATH, "//span[text()='See All']/ancestor::a"),
            (By.XPATH, "//span[text()='See all']/ancestor::a"),
            (By.XPATH, "//span[text()='Your groups']/ancestor::div/following-sibling::div//span[text()='See All']/ancestor::a"),
            # Russian
            (By.XPATH, "//span[text()='Просмотреть все группы']/ancestor::a"),
            (By.XPATH, "//span[text()='Просмотреть все']/ancestor::a"),
            # Ukrainian
            (By.XPATH, "//span[text()='Переглянути всі групи']/ancestor::a"),
            (By.XPATH, "//span[text()='Переглянути всі']/ancestor::a"),
            # Generic
            (By.XPATH, "//a[contains(@href, '/groups/')]//span[contains(text(), 'See') or contains(text(), 'see') or contains(text(), 'Просмотреть') or contains(text(), 'Переглянути')]"),
            (By.XPATH, "//a[contains(@href, '/groups/your_groups')]"),
            (By.XPATH, "//a[contains(@href, '/groups/feed/')]//span[contains(text(), 'See') or contains(text(), 'see') or contains(text(), 'все') or contains(text(), 'всі')]"),
        ]
        
        see_all_button = None
        
        # Try each selector
        for selector_type, selector in see_all_selectors:
            try:
                elements = self.driver.find_elements(selector_type, selector)
                for element in elements:
                    try:
                        # Verify it's visible and appears to be the right element
                        if element.is_displayed() and element.is_enabled():
                            text = element.text.strip().lower()
                            href = element.get_attribute("href") or ""
                            
                            # Check if this looks like a "See All" button
                            if (
                                "see all" in text or 
                                "see" in text or 
                                "все" in text or 
                                "всі" in text or 
                                "your_groups" in href or
                                ("/groups/" in href and "feed" not in href and "discover" not in href)
                            ):
                                see_all_button = element
                                logger.info(f"Found 'See All' button with text: '{text}' and href: '{href}'")
                                break
                    except StaleElementReferenceException:
                        continue
                        
                if see_all_button:
                    break
            except Exception as e:
                logger.warning(f"Error finding 'See All' with selector {selector}: {str(e)}")
                continue
        
        # If we couldn't find the See All button, try looking for the direct "Your Groups" link
        if not see_all_button:
            logger.info("'See All' button not found, trying to find direct 'Your Groups' link")
            your_groups_selectors = [
                (By.XPATH, "//a[contains(@href, '/groups/your_groups')]"),
                (By.XPATH, "//a[contains(@href, '/groups/') and contains(@href, 'joined')]"),
                (By.XPATH, "//span[text()='Your groups' or text()='Ваши группы' or text()='Ваші групи']/ancestor::a"),
                # Final fallbacks
                (By.XPATH, "//a[contains(@href, '/groups/')]")
            ]
            
            for selector_type, selector in your_groups_selectors:
                try:
                    elements = self.driver.find_elements(selector_type, selector)
                    for element in elements:
                        try:
                            if element.is_displayed():
                                href = element.get_attribute("href") or ""
                                # Avoid known non-group list pages
                                if not any(x in href for x in ["discover", "feed/", "create", "category"]):
                                    see_all_button = element
                                    logger.info(f"Found alternative groups link with href: '{href}'")
                                    break
                        except:
                            continue
                    
                    if see_all_button:
                        break
                except Exception as e:
                    logger.warning(f"Error finding alternative groups link with selector {selector}: {str(e)}")
                    continue
        
        if not see_all_button:
            # Last resort: try to directly navigate to the groups URL
            logger.info("No 'See All' button found, trying direct URL navigation")
            self.take_screenshot("see_all_not_found")
            
            try:
                self.driver.get("https://www.facebook.com/groups/your_groups")
                time.sleep(3)
                self.take_screenshot("direct_your_groups_navigation")
                return True
            except Exception as e:
                self.error = f"Failed to find 'See All' button and direct navigation failed: {str(e)}"
                logger.error(self.error)
                return False
        
        # Click the "See All" button
        logger.info("Clicking 'See All' button")
        self.take_screenshot("before_see_all_click")
        
        try:
            # Try regular click
            see_all_button.click()
        except (ElementClickInterceptedException, ElementNotInteractableException):
            # Try scrolling to element
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", see_all_button)
                time.sleep(0.5)
                see_all_button.click()
            except:
                # Try JavaScript click
                try:
                    self.driver.execute_script("arguments[0].click();", see_all_button)
                except Exception as e:
                    self.error = f"Failed to click 'See All' button: {str(e)}"
                    logger.error(self.error)
                    self.take_screenshot("see_all_click_failed")
                    return False
        
        # Wait for the groups list page to load
        time.sleep(3)
        self.take_screenshot("after_see_all_click")
        
        # Verify we're on a valid groups page
        if "facebook.com/groups/" in self.driver.current_url:
            logger.info(f"Successfully navigated to groups list page: {self.driver.current_url}")
            self._emit_progress(step="find_see_all", progress=55, status="running")
            return True
        else:
            self.error = f"Failed to navigate to groups list page. Current URL: {self.driver.current_url}"
            logger.error(self.error)
            self.take_screenshot("groups_list_navigation_failed")
            return False 

    def extract_joined_groups(self, max_scroll_attempts=10):
        """Extract all joined groups from the current page"""
        if not self.driver:
            self.error = "WebDriver not initialized"
            logger.error(self.error)
            return False
            
        self.step = "extract_groups"
        logger.info("Extracting joined Facebook groups")
        self.take_screenshot("before_group_extraction")
        self.max_scroll_attempts = max_scroll_attempts
        self._emit_progress(step="extract_groups", progress=60, status="running", max_scroll=max_scroll_attempts)
        
        if not isinstance(self.groups, list):
            self.groups = []
        self.current_scroll = 0
        
        # Wait for page to fully load
        time.sleep(5)
        
        # Take a screenshot of the initial page state
        self.take_screenshot("initial_groups_page")
        logger.info(f"Current URL: {self.driver.current_url}")
        
        # Different approaches for different URLs
        if "/groups/joins" in self.driver.current_url:
            logger.info("Using groups/joins extraction approach")
            main_container_selectors = [
                "//div[@role='main']",
                "//div[@role='feed']",
                "//div[contains(@class, 'x1yztbdb')]"
            ]
        else:
            logger.info("Using generic groups page extraction approach")
            main_container_selectors = [
                "//div[@role='main']",
                "//div[@role='feed']",
                "//div[contains(@class, 'x1yztbdb')]",
                "//div[@data-pagelet='GroupsFeed']",
                "//div[contains(@class, 'x78zum5')]"
            ]
        
        # Find the main container
        search_base = self.driver
        for selector in main_container_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                if elements:
                    search_base = elements[0]
                    logger.info(f"Found main container using selector: {selector}")
                    break
            except Exception as e:
                logger.warning(f"Error finding main container with selector {selector}: {str(e)}")
            
        # Execute scrolling to load more groups
        previous_height = 0
        no_new_groups_counter = 0
        no_new_height_counter = 0
        
        for i in range(max_scroll_attempts):
            if not self._ensure_window_alive("extracting groups"):
                return False
            self.current_scroll = i + 1
            logger.info(f"Scroll attempt {self.current_scroll}/{max_scroll_attempts}")
            
            # Get current height
            current_height = self.driver.execute_script("return document.body.scrollHeight")
            logger.info(f"Current page height: {current_height}")
                
            # Extract groups that are currently visible
            previous_count = len(self.groups)
            self._extract_visible_groups(search_base)
            current_count = len(self.groups)
            
            logger.info(f"Groups found: {current_count} (new: {current_count - previous_count})")
            progress = 60 + int(((i + 1) / max_scroll_attempts) * 35)
            self._emit_progress(
                step=f"Extracting groups ({self.current_scroll}/{max_scroll_attempts})",
                progress=min(progress, 95),
                status="running",
                total_groups=current_count,
                current_scroll=self.current_scroll,
                max_scroll=max_scroll_attempts,
            )
                
            # If we haven't found any new groups in 3 consecutive attempts, try alternative selectors
            if current_count == previous_count:
                no_new_groups_counter += 1
                if no_new_groups_counter >= 3:
                    logger.info("No new groups found in 3 attempts, trying alternative selectors")
                    self._extract_groups_deep_search()
                    
                    # If we found new groups, reset counter
                    if len(self.groups) > current_count:
                        no_new_groups_counter = 0
                    else:
                        # If we still haven't found groups after deep search, try direct DOM inspection
                        logger.info("Deep search didn't find new groups, examining page structure")
                        self.take_screenshot(f"page_structure_scroll_{i}")
                        
                        # Try to get all links on the page for debugging
                        try:
                            all_links = self.driver.find_elements(By.TAG_NAME, "a")
                            group_links = [l for l in all_links if l.get_attribute("href") and "/groups/" in l.get_attribute("href")]
                            logger.info(f"Found {len(group_links)} potential group links in total page inspection")
                            
                            # Try processing these links
                            for link in group_links:
                                self._process_group_element(link)
                        except Exception as e:
                            logger.warning(f"Error in total page inspection: {str(e)}")
            else:
                no_new_groups_counter = 0
            
            # Scroll down
            try:
                # Scroll to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)  # Wait for content to load
            
                # Check if scrolling made any difference
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                
                if new_height == current_height:
                    no_new_height_counter += 1
                    
                    # Try alternative scrolling methods if height doesn't change
                    if no_new_height_counter >= 2:
                        logger.info("Page height not changing, trying alternative scroll methods")
            
                        # Method 1: Scroll by fixed amount
                        self.driver.execute_script("window.scrollBy(0, 800);")
                        time.sleep(1)
            
                        # Method 2: Try to find scrollable elements
                        try:
                            scrollable_elements = self.driver.find_elements(By.XPATH, 
                                "//div[contains(@style, 'overflow') or contains(@class, 'scrollable')]")
                            if scrollable_elements:
                                for elem in scrollable_elements[:3]:
                                    self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", elem)
                                    time.sleep(1)
                        except Exception as e:
                            logger.warning(f"Error in scroll element search: {str(e)}")
                        
                        # Method 3: Try pressing Page Down key
                        try:
                            from selenium.webdriver.common.keys import Keys
                            body = self.driver.find_element(By.TAG_NAME, "body")
                            body.send_keys(Keys.PAGE_DOWN)
                        except Exception as e:
                            logger.warning(f"Error sending Page Down key: {str(e)}")
                            
                        # Take a screenshot to help debug
                        self.take_screenshot(f"alternative_scroll_{i}")
                else:
                    no_new_height_counter = 0
                
                previous_height = current_height
                
            except Exception as e:
                logger.warning(f"Error during scrolling: {str(e)}")
                
            # Take a screenshot periodically to track progress
            if i % 2 == 0:
                self.take_screenshot(f"scroll_attempt_{i}")

            # If we repeatedly fail to discover new groups and page height is stable,
            # assume we exhausted the current surface and stop this pass.
            if no_new_groups_counter >= 6 and no_new_height_counter >= 4:
                logger.info("Stopping current extraction pass due to repeated stagnation")
                break
        
        # Final extraction attempt
        self._extract_visible_groups(search_base)
        self._extract_groups_deep_search()
        
        # Post-process the groups to remove duplicates and invalid entries
        if self.groups:
            self.post_process_groups()
            logger.info(f"After post-processing: {len(self.groups)} unique groups")
            
            # Save to file
            self._save_groups()
            self._emit_progress(step="groups_saved", progress=100, status="running", total_groups=len(self.groups))
            
            # Take final screenshot
            self.take_screenshot("groups_extraction_complete")
            
            return True
        else:
            self.error = "No Facebook groups found after multiple extraction attempts"
            logger.error(self.error)
            self.take_screenshot("no_groups_found")
            return False

    def _visit_group_collection_surfaces(self):
        """Visit multiple Facebook group list surfaces to maximize joined-group coverage."""
        if not self.driver:
            return

        urls = [
            self.driver.current_url,
            "https://www.facebook.com/groups/joins/?nav_source=tab",
            "https://www.facebook.com/groups/your_groups",
            "https://www.facebook.com/groups/feed/?joined=1",
            "https://www.facebook.com/bookmarks/groups",
        ]

        seen = set()
        for idx, url in enumerate(urls):
            if not url or url in seen:
                continue
            seen.add(url)
            try:
                logger.info(f"Coverage pass {idx + 1}: visiting {url}")
                self.driver.get(url)
                time.sleep(4)
                self.take_screenshot(f"coverage_surface_{idx + 1}")
                self.extract_joined_groups(max_scroll_attempts=28)
                self.post_process_groups()
                logger.info(f"Coverage pass {idx + 1} complete, total groups: {len(self.groups)}")
            except Exception as e:
                logger.warning(f"Coverage pass failed for {url}: {str(e)}")
    
    def _extract_visible_groups(self, search_base):
        """Extract groups from the current visible portion of the page with enhanced selectors"""
        try:
            # Updated selectors for Facebook's current UI
            group_selectors = [
                # Direct group links with role=link - most reliable
                "a[href*='/groups/'][role='link']",
                
                # Links with group URLs that might be group cards
                "a[href*='/groups/']",
                
                # More specific selectors for group cards
                "div[role='article'] a[href*='/groups/']",
                "div[role='feed'] a[href*='/groups/']",
                
                # Facebook's group card structure often uses these classes
                "div.x1yztbdb a[href*='/groups/']",
                "div.x78zum5 a[href*='/groups/']"
            ]
            
            # XPath selectors for more complex matching
            xpath_selectors = [
                # Group cards with text content
                "//a[contains(@href, '/groups/') and string-length(text()) > 1]",
                
                # Group links with span children (common Facebook pattern)
                "//a[contains(@href, '/groups/') and .//span]",
                
                # Groups listed in feed or list format
                "//div[@role='feed']//a[contains(@href, '/groups/')]",
                
                # Modern Facebook often uses nested span elements
                "//a[contains(@href, '/groups/') and .//span//span]",
                
                # Group links anywhere in the document
                "//a[contains(@href, '/groups/')]"
            ]
                
            # Process each selector
            found_count = 0
            
            # Try CSS selectors first
            for selector in group_selectors:
                try:
                    elements = search_base.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        logger.info(f"Found {len(elements)} potential group links with selector: {selector}")
                        
                        for element in elements:
                            if self._process_group_element(element):
                                found_count += 1
                except Exception as e:
                    logger.warning(f"Error with selector {selector}: {str(e)}")
            
            # Try XPath selectors next
            for selector in xpath_selectors:
                try:
                    elements = search_base.find_elements(By.XPATH, selector)
                    if elements:
                        logger.info(f"Found {len(elements)} potential group links with XPath: {selector}")
                        
                        for element in elements:
                            if self._process_group_element(element):
                                found_count += 1
                except Exception as e:
                    logger.warning(f"Error with XPath {selector}: {str(e)}")
            
            if found_count > 0:
                logger.info(f"Successfully processed {found_count} new group elements")
                
        except Exception as e:
            logger.warning(f"Error during group extraction: {str(e)}")
    
    def _process_group_element(self, element):
        """Process a potential group element and extract info"""
        try:
            group_url = element.get_attribute("href")
                    
            # Skip if no URL or not a group URL
            if not group_url or "/groups/" not in group_url:
                return False
                        
            # Skip the main groups URL - this is "Create new group" or similar
            if group_url == "https://www.facebook.com/groups/" or group_url.endswith("/groups/"):
                return False
                        
            # Skip special Facebook group pages and non-group links
            skip_patterns = [
                "/groups/feed",
                "/groups/discover",
                "/groups/create",
                "/groups/joins",
                "/groups/your_groups",
                "/bookmarks/groups",
                "?create",
                "?ref=group_browse",
                "/categories/",
                "facebook.com/groups/joins",
                "facebook.com/groups/feeds",
                "facebook.com/groups/feed",
                "/groups/groups_browse/",
                "/groups/groups_browse_feed"
            ]
            
            for pattern in skip_patterns:
                if pattern in group_url:
                    return False
                            
            # Clean up the URL - remove query parameters
            if "?" in group_url:
                group_url = group_url.split("?")[0]
                    
            # Make sure we have a valid group path - should end with a group ID or name
            parts = group_url.strip('/').split('/')
            if len(parts) < 2 or len(parts[-1]) < 4:
                return False
            
            # Extract group ID or name from URL
            group_id = parts[-1]
            
            # Initialize group name
            group_name = ""
                    
            # Multiple methods to extract group name
            
            # Method 1: Try direct text in the element
            try:
                direct_text = element.text.strip()
                if direct_text and len(direct_text) > 3 and "view" not in direct_text.lower():
                    group_name = direct_text
                    logger.debug(f"Extracted name via direct text: {group_name}")
            except Exception as e:
                logger.debug(f"Error getting direct text: {str(e)}")
            
            # Method 2: Look for span elements that might contain the name
            if not group_name or len(group_name) < 3:
                try:
                    # Try multiple ways to find spans with text inside the element
                    span_texts = []
                    
                    # Direct child spans
                    spans = element.find_elements(By.XPATH, "./span")
                    span_texts.extend([s.text.strip() for s in spans if s.text.strip()])
                    
                    # Nested spans (Facebook often has multiple levels)
                    nested_spans = element.find_elements(By.XPATH, ".//span")
                    span_texts.extend([s.text.strip() for s in nested_spans if s.text.strip()])
                    
                    # Find the longest span text that's not "View" or similar
                    filtered_spans = [s for s in span_texts if len(s) > 3 and "view" not in s.lower()]
                    if filtered_spans:
                        # Sort by length and take the longest
                        longest_span = sorted(filtered_spans, key=len, reverse=True)[0]
                        group_name = longest_span
                        logger.debug(f"Extracted name via spans: {group_name}")
                except Exception as e:
                    logger.debug(f"Error getting span text: {str(e)}")
            
            # Method 3: Look for parent elements that might contain the name
            if not group_name or len(group_name) < 3:
                try:
                    parent_divs = [
                        element.find_element(By.XPATH, "./.."),  # Direct parent
                        element.find_element(By.XPATH, "./../.."),  # Parent's parent
                        element.find_element(By.XPATH, "./../../..")  # Even higher level
                    ]
                    
                    for div in parent_divs:
                        div_text = div.text.strip()
                        if div_text:
                            # Split by newline and get the first significant line
                            lines = [line.strip() for line in div_text.split('\n') if line.strip()]
                            if lines and len(lines[0]) > 3 and "view" not in lines[0].lower():
                                group_name = lines[0]
                                logger.debug(f"Extracted name via parent div: {group_name}")
                                break
                except Exception as e:
                    logger.debug(f"Error getting parent div text: {str(e)}")
            
            # Method 4: Look for aria-label which sometimes contains the group name
            if not group_name or len(group_name) < 3:
                try:
                    aria_label = element.get_attribute("aria-label")
                    if aria_label and len(aria_label) > 3 and "view" not in aria_label.lower():
                        group_name = aria_label
                        logger.debug(f"Extracted name via aria-label: {group_name}")
                except Exception as e:
                    logger.debug(f"Error getting aria-label: {str(e)}")
            
            # If we still don't have a name, use the URL path as fallback
            if not group_name or len(group_name) < 3 or group_name.lower() == "view group":
                # If it's a numeric ID, create a generic name
                if group_id.isdigit():
                    group_name = f"Facebook Group {group_id}"
                else:
                    # For named groups, format the URL path nicely
                    group_name = " ".join(word.capitalize() for word in group_id.replace('-', ' ').split())
                    
                logger.debug(f"Using fallback name from URL: {group_name}")
            
            # Skip entries with generic or problematic names
            if (not group_name or 
                len(group_name) < 3 or 
                group_name.lower() == "view group" or 
                group_name.lower() == "view" or
                group_name.lower() == "create new group"):
                return False
                
            # Skip entries with indicator words for suggested/invited groups
            skip_keywords = [
                "suggest", "invitation", "invite", 
                "join group", "request", "pending", "join now",
                "explore",  # "Explore groups" link
                "find friends",  # Not a group
                "your feed",  # Not a group
                "recommended"  # Recommended groups, not joined
            ]
            
            for keyword in skip_keywords:
                if keyword.lower() in group_name.lower():
                    return False
                    
            # Truncate very long names
            if len(group_name) > 100:
                group_name = group_name[:97] + "..."
                    
            # Add to groups list
            self.groups.append({
                "name": group_name,
                "url": group_url
            })
                    
            logger.info(f"Extracted group: {group_name} ({group_url})")
            return True
            
        except StaleElementReferenceException:
            # Element is no longer attached to the DOM - just skip
            return False
        except Exception as e:
            logger.warning(f"Error processing group element: {str(e)}")
            return False
            
    def _extract_groups_deep_search(self):
        """Last resort deep search for groups in the DOM when other methods fail"""
        try:
            logger.info("Performing deep DOM search for groups")
            
            # Try direct XPath search for group links anywhere on the page
            deep_selectors = [
                # Content area -> group links
                "//div[@role='main']//a[contains(@href, '/groups/')]",
                
                # All anchors with group in URL and visible text
                "//a[contains(@href, '/groups/') and string-length(normalize-space(.)) > 1]",
                
                # Links with images (likely group cards)
                "//a[contains(@href, '/groups/') and .//img]"
            ]
            
            found_count = 0
            for selector in deep_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        logger.info(f"Deep search found {len(elements)} potential group links")
                        
                        for element in elements:
                            if self._process_group_element(element):
                                found_count += 1
                except Exception as e:
                    logger.warning(f"Error in deep search with {selector}: {str(e)}")
                    
            if found_count > 0:
                logger.info(f"Deep search successfully found {found_count} groups")
                
            # Take a screenshot of current state
            self.take_screenshot("deep_search_results")
            
        except Exception as e:
            logger.warning(f"Error during deep group search: {str(e)}")
    
    def _remove_duplicates(self):
        """Remove duplicate groups based on URL"""
        unique_groups = {}
        for group in self.groups:
            unique_groups[group["url"]] = group
        
        self.groups = list(unique_groups.values())
    
    def _save_groups(self):
        """Save fetched groups to JSON file"""
        try:
            with open(self.output_file, 'w') as f:
                json.dump(self.groups, f, indent=2)
            logger.info(f"Saved {len(self.groups)} groups to {self.output_file}")
        except Exception as e:
            logger.error(f"Error saving groups to file: {str(e)}")

    def fetch_groups(self):
        """Main method to fetch and extract Facebook groups"""
        self.is_fetching = True
        self.error = None
        self.groups = []
        
        for fetch_attempt in range(2):
            try:
                logger.info(f"Starting Facebook group fetching process (attempt {fetch_attempt + 1}/2)")
                self._emit_progress(step=f"starting_attempt_{fetch_attempt + 1}", progress=1, status="running")

                # Step 1: Set up WebDriver with session support
                if not self.setup_driver():
                    self.is_fetching = False
                    return None
                
                # Step 2: Log in to Facebook or use existing session
                if not self.login():
                    if self.headless and self.manual_verification_needed:
                        logger.warning(
                            "Manual verification required but browser is headless — retrying with visible Chrome"
                        )
                        self._emit_progress(
                            step="retry_visible_browser",
                            progress=15,
                            status="running",
                            message="Повтор с видимым браузером для CAPTCHA...",
                        )
                        self.cleanup()
                        self.headless = False
                        time.sleep(2)
                        continue
                    self.cleanup()
                    self.is_fetching = False
                    return None
                
                # Step 3: Navigate to groups feed
                if not self.navigate_to_groups():
                    self.cleanup()
                    self.is_fetching = False
                    return None
                
                # Step 4: Find and click "See All" for joined groups
                if not self.find_see_all_button():
                    self.cleanup()
                    self.is_fetching = False
                    return None
                
                # Step 5: Extract all joined groups
                if not self.extract_joined_groups(max_scroll_attempts=28):
                    if self.error and ("no such window" in self.error.lower() or "web view not found" in self.error.lower()) and fetch_attempt == 0:
                        logger.warning("Fetch failed because browser window disappeared. Retrying with visible browser.")
                        self._emit_progress(step="retry_visible_browser", progress=10, status="running", error=self.error)
                        self.cleanup()
                        self.headless = False
                        time.sleep(2)
                        continue
                    self.cleanup()
                    self.is_fetching = False
                    return None

                # Step 6: Re-scan additional Facebook group surfaces to improve coverage
                self._visit_group_collection_surfaces()
                self.post_process_groups()
                
                # Save session again after successful completion
                if not self.session_loaded:
                    self.save_session()
                
                # Clean up
                self.cleanup()
                self.is_fetching = False
                
                logger.info(f"Group fetching completed successfully, found {len(self.groups)} groups")
                self._emit_progress(step="completed", progress=100, status="completed", total_groups=len(self.groups))
                return self.groups
            except Exception as e:
                self.error = f"Error during group fetching: {str(e)}"
                logger.error(self.error)
                self._emit_progress(step="fetch_exception", progress=0, status="failed", error=self.error)

                if self.driver:
                    self.take_screenshot("fetch_error")
                self.cleanup()
                if ("no such window" in str(e).lower() or "web view not found" in str(e).lower()) and fetch_attempt == 0:
                    self.headless = False
                    time.sleep(2)
                    continue
                self.is_fetching = False
                return None

        self.is_fetching = False
        return None
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def post_process_groups(self):
        """Post-process the groups list to remove duplicates and invalid entries"""
        # Create a set to track unique group IDs/URLs for deduplication
        seen_group_urls = set()
        unique_groups = []
        
        # First pass - filter out user pages, post pages, and duplicates
        for group in self.groups:
            url = group["url"]
            name = group["name"]
            
            # Skip if empty URL or name
            if not url or not name:
                continue
                
            # Extract the base group URL (without user or post info)
            base_group_url = url
            
            # Skip user and post pages
            if "/user/" in url or "/posts/" in url:
                continue
                
            # Skip "Find friends" and other non-group entries
            skip_names = ["find friends", "your feed", "your groups"]
            if name.lower() in skip_names:
                continue
            
            # Skip if we've seen this group URL already
            if base_group_url in seen_group_urls:
                continue
                
            # Add to list of processed groups
            seen_group_urls.add(base_group_url)
            unique_groups.append(group)
        
        # Sort groups by name
        unique_groups.sort(key=lambda x: x["name"])
        
        logger.info(f"Post-processing reduced {len(self.groups)} entries to {len(unique_groups)} unique groups")
        
        # Replace the groups list with the filtered list
        self.groups = unique_groups


def get_fetched_groups(file_path=OUTPUT_FILE):
    """Get previously fetched groups from file"""
    try:
        # If caller passed an integer user_id, build per-user path
        if isinstance(file_path, int):
            base_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'user_data', 'groups')
            base_dir = os.path.abspath(base_dir)
            os.makedirs(base_dir, exist_ok=True)
            file_path = os.path.join(base_dir, f"autofetched_groups_{file_path}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Error reading groups file: {str(e)}")
        return [] 