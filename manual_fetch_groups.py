#!/usr/bin/env python
"""
Premium Facebook Group Fetcher
This standalone script reliably fetches your Facebook groups and saves them to autofetched_groups.json
Run this script separately from the main application when you need to update your groups.
"""

import os
import sys
import time
import logging
import getpass
import argparse
import configparser
from pathlib import Path
from bot.group_fetcher import FacebookGroupFetcher
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('manual_fetch.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_credentials():
    """Load Facebook credentials from config.ini or prompt the user"""
    config_file = 'config.ini'
    username = None
    password = None
    
    # Try to load from config file first
    if os.path.exists(config_file):
        try:
            config = configparser.ConfigParser()
            config.read(config_file)
            if 'Credentials' in config:
                username = config.get('Credentials', 'username', fallback=None)
                password = config.get('Credentials', 'password', fallback=None)
                
                if username and password:
                    logger.info(f"Loaded credentials for user: {username}")
                    return username, password
    except Exception as e:
            logger.error(f"Error loading credentials from config: {str(e)}")
    
    # Prompt for credentials if not found in config
    print("\n=== Facebook Group Fetcher ===")
    print("Please enter your Facebook credentials:")
    username = input("Email/Phone: ").strip()
    password = getpass.getpass("Password: ").strip()
    
    # Save to config if user agrees
    save_to_config = input("Save credentials to config file? (y/n): ").strip().lower()
    if save_to_config == 'y':
        try:
            config = configparser.ConfigParser()
            if os.path.exists(config_file):
                config.read(config_file)
            
            if 'Credentials' not in config:
                config['Credentials'] = {}
                
            config['Credentials']['username'] = username
            config['Credentials']['password'] = password
            
            with open(config_file, 'w') as f:
                config.write(f)
                
            logger.info("Credentials saved to config.ini")
            print("Credentials saved to config.ini")
        except Exception as e:
            logger.error(f"Failed to save credentials: {str(e)}")
            print(f"Failed to save credentials: {str(e)}")
    
    return username, password

def create_screenshots_dir():
    """Create screenshots directory if it doesn't exist"""
    os.makedirs("screenshots", exist_ok=True)
    logger.info("Created screenshots directory")
    print("Created screenshots directory")

def check_session_exists():
    """Check if a saved session exists"""
    profile_exists = os.path.exists("chrome_profile") and os.path.isdir("chrome_profile")
    cookies_exist = os.path.exists("facebook_cookies.json")
    return profile_exists, cookies_exist

def main():
    """Main entry point for the script"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Facebook Group Fetcher')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no browser UI)')
    parser.add_argument('--no-headless', action='store_false', dest='headless', help='Run with visible browser UI (for handling CAPTCHA/2FA)')
    parser.add_argument('--output', type=str, default='autofetched_groups.json', 
                        help='Output file path for fetched groups')
    parser.add_argument('--use-session', action='store_true', default=True,
                       help='Use saved session if available (default: True)')
    parser.add_argument('--no-session', action='store_true',
                       help='Do not use saved session, but still save new session')
    parser.add_argument('--reset-session', action='store_true',
                       help='Reset existing session and force new login')
    parser.add_argument('--profile-dir', type=str, default='chrome_profile',
                       help='Chrome profile directory for session persistence')
    parser.add_argument('--cookies-file', type=str, default='facebook_cookies.json',
                       help='Cookies file for session persistence')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with more verbose output')
    parser.add_argument('--verbose', action='store_true', help='Print more detailed extraction info')
    parser.add_argument('--force-direct', action='store_true', 
                        help='Force direct navigation to groups list URL')
    parser.add_argument('--extract-timeout', type=int, default=300,
                        help='Maximum time in seconds to attempt group extraction (default: 300)')
    parser.add_argument('--language', type=str, default='en',
                        help='Force Facebook UI language (en, ru, uk) - helps with selectors')
    args = parser.parse_args()
    
    # Handle conflicts in arguments
    if args.no_session:
        args.use_session = False
    
    # Set up more detailed logging if debug mode
    if args.debug:
        logging.getLogger('fb_group_fetcher').setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)
        print("Debug mode enabled - verbose logging active")
    
    # Additional options info
    if args.force_direct:
        print("⚠️ Using direct navigation to groups list (bypass UI navigation)")
    if args.verbose:
        print("🔍 Verbose mode enabled - will show detailed extraction info")
    
    print("\n========================================")
    print("  🔍 Premium Facebook Group Fetcher 🔍  ")
    print("========================================")
    print("This tool will extract all groups you've joined on Facebook\n")
    
    # Check for existing sessions
    profile_exists, cookies_exist = check_session_exists()
    session_exists = profile_exists or cookies_exist
    
    # Session status message
    if args.reset_session:
        print("🔄 Session reset requested - will force new login")
        if session_exists:
            print("   Existing session will be cleared")
    elif not args.use_session:
        print("⚠️ Session usage disabled - will perform fresh login")
        print("   A new session will still be saved for future use")
    elif session_exists:
        print("✅ Existing session found - will attempt to reuse")
        if profile_exists:
            print(f"   Chrome profile directory: {os.path.abspath(args.profile_dir)}")
        if cookies_exist:
            print(f"   Cookies file: {args.cookies_file}")
    else:
        print("ℹ️ No existing session found - will perform fresh login")
        print("   A new session will be saved for future use")
    
    # Warn about headless mode for first login
    if args.headless and (args.reset_session or not session_exists):
        print("\n⚠️ WARNING: Headless mode enabled for first-time login!")
        print("   This may fail if Facebook requires CAPTCHA or 2FA verification.")
        print("   For first login, it's recommended to run without --headless")
        print("   Continue anyway? (y/n)")
        response = input().strip().lower()
        if response != 'y':
            print("Exiting. Please restart without --headless option for first login.")
            return False
    
    # Ensure screenshots directory exists
    create_screenshots_dir()
    
    # Load or prompt for credentials
    username, password = load_credentials()
    if not username or not password:
        print("❌ Error: Valid credentials are required to fetch groups.")
        logger.error("Failed to get valid credentials")
        return False
    
    print("\n📋 Configuration:")
    print(f"  • Username: {username}")
    print(f"  • Output file: {args.output}")
    print(f"  • Headless mode: {'✅ Enabled' if args.headless else '❌ Disabled'}")
    print(f"  • Session usage: {'✅ Enabled' if args.use_session else '❌ Disabled'}")
    print("\n🚀 Starting group fetch process...")
    print("  This may take a minute or two...\n")
    
    try:
        # Initialize the group fetcher
        fetcher = FacebookGroupFetcher(
            username=username,
            password=password,
            output_file=args.output,
            headless=args.headless,
            use_session=args.use_session,
            reset_session=args.reset_session,
            profile_dir=args.profile_dir,
            cookies_file=args.cookies_file
        )
        
        # Override direct navigation if requested
        if args.force_direct:
            fetcher.force_direct_navigation = True
        
        # Configure verbose mode
        if args.verbose:
            logging.getLogger('fb_group_fetcher').setLevel(logging.DEBUG)
        
        # Start timer
        start_time = time.time()
        extraction_timeout = args.extract_timeout
        
        # Progress indicator
        fetching_thread = threading.Thread(target=lambda: fetcher.fetch_groups())
        fetching_thread.daemon = True
        fetching_thread.start()
        
        # Show a spinner while fetching
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        i = 0
        print("Starting fetch process...")
        
        # Monitor thread with timeout
        elapsed = 0
        while fetching_thread.is_alive() and elapsed < extraction_timeout:
            if fetcher.error:
                status_text = f"⚠️ Error: {fetcher.error}"
            else:
                status_text = f"{spinner[i]} Fetching groups... Current step: {fetcher.step}"
            
            # Add special messages for certain steps
            if fetcher.step == "login":
                if fetcher.session_loaded:
                    status_text = f"{spinner[i]} Using existing session... skipping login"
                else:
                    status_text = f"{spinner[i]} Logging in to Facebook..."
            elif fetcher.step == "navigate_to_groups":
                status_text = f"{spinner[i]} Navigating to groups page..."
            elif fetcher.step == "find_see_all":
                status_text = f"{spinner[i]} Looking for groups listing..."
            elif fetcher.step == "extract_groups":
                status_text = f"{spinner[i]} Extracting your groups... Found {len(fetcher.groups)} so far"
                
                # Add scroll info in verbose mode
                if args.verbose and hasattr(fetcher, 'current_scroll'):
                    status_text += f" (Scroll {fetcher.current_scroll})"
            
            print(status_text, end='\r')
            time.sleep(0.1)
            i = (i + 1) % len(spinner)
            elapsed = time.time() - start_time
            
            # Every 15 seconds, print a newline to show progress over time
            if int(elapsed) % 15 == 0 and int(elapsed) > 0 and int(elapsed - 0.1) % 15 != 0:
                if fetcher.step == "extract_groups":
                    print(f"\n⏱️  {int(elapsed)}s elapsed - {len(fetcher.groups)} groups found so far...")
        
        # Handle timeout
        if elapsed >= extraction_timeout:
            print(f"\n⚠️ Extraction timed out after {extraction_timeout} seconds.")
            print(f"   Found {len(fetcher.groups)} groups before timeout.")
            
            # If we found some groups, consider it a partial success
            if len(fetcher.groups) > 0:
                print(f"   Saving the {len(fetcher.groups)} groups that were found.")
                if fetcher.step == "extract_groups":
                    fetcher._save_groups()
        
        print(" " * 100, end='\r')  # Clear the line
        
        groups = fetcher.groups
        elapsed_time = time.time() - start_time
        
        if groups is None or len(groups) == 0:
            print(f"\n❌ Error: {fetcher.error or 'No groups were found'}")
            print(f"  Current step: {fetcher.step}")
            print("\n📷 Screenshots have been saved to the 'screenshots' directory")
            print("    Check these images to see what went wrong")
            
            if fetcher.step == "login":
                print("\n💡 Login troubleshooting:")
                print("  • Check if your credentials are correct")
                if not args.use_session and session_exists:
                    print("  • Try using existing session with --use-session flag (default)")
                elif args.reset_session:
                    print("  • Try without --reset-session to use existing session")
                print("  • Facebook may be requiring 2FA or CAPTCHA verification")
                print("  • First login must be done with visible browser (without --headless)")
                print("  • Complete any CAPTCHA or 2FA challenges manually when prompted")
                print("  • After successful login, the session will be saved for future use")
            elif fetcher.step == "find_see_all":
                print("\n💡 Navigation troubleshooting:")
                print("  • Facebook UI may have changed")
                print("  • Try using --force-direct to bypass UI navigation")
                print("  • Try manually navigating to your groups in browser")
            elif fetcher.step == "extract_groups":
                print("\n💡 Group extraction troubleshooting:")
                print("  • Facebook may have changed their groups page layout")
                print("  • Try the --verbose flag for more detailed logging")
                print("  • Try --force-direct to go directly to the groups list")
                
            logger.error(f"Group fetch failed: {fetcher.error or 'No groups found'}")
            return False
        
        print(f"\n✅ Success! Found {len(groups)} groups in {elapsed_time:.1f} seconds.")
        print(f"  Groups have been saved to: {args.output}")
        
        # Session reuse message
        if fetcher.session_loaded:
            print(f"\n🔐 Used existing session successfully!")
        else:
            print(f"\n🔐 Saved new session for future use")
            print(f"  • Next time, the tool can log in instantly without credentials")
        
        print("\n📊 Group fetch statistics:")
        print(f"  • Total groups found: {len(groups)}")
        
        # Show first 5 groups as a preview
        if groups:
            print("\n📋 Sample of fetched groups:")
            for i, group in enumerate(groups[:5]):
                print(f"  {i+1}. {group['name']}")
            
            if len(groups) > 5:
                print(f"  ... and {len(groups)-5} more")
        
        logger.info(f"Successfully fetched {len(groups)} groups")
        return True
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Process interrupted by user.")
        logger.warning("Process interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Error: Unexpected error occurred: {str(e)}")
        logger.exception("Unexpected error occurred")
        return False
    finally:
        print("\n💡 Tips:")
        print("  • After fetching groups, restart the main Flask application to use them")
        print("  • Use --use-session flag to reuse existing session (faster, avoids CAPTCHA)")
        print("  • Use --reset-session to force a new login if session becomes invalid")
        print("  • First login must be done with visible browser to handle CAPTCHA/2FA")
        print("  • For best results, use Chrome as your regular browser for Facebook too")

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 