#!/usr/bin/env python3
"""
Test script to verify Facebook posting with simple text
"""

import os
import sys
import time
from bot.fb_poster import FacebookGroupPoster

def main():
    """Main function to test posting to a single group"""
    # Create a simple message without emojis or special Unicode characters
    test_message = """
    This is a test message for Facebook Group Poster.
    Testing our fixed Unicode handling.
    
    Simple text only, no special characters or emojis.
    """
    
    # Initialize the bot
    bot = FacebookGroupPoster()
    
    # Check if credentials are configured
    if not bot.username or not bot.password:
        print("ERROR: Facebook credentials not configured. Please configure them first.")
        sys.exit(1)
        
    print(f"Using account: {bot.username}")
    print("Starting test post to one group...")
    
    # Get the first group from autofetched_groups.json
    if os.path.exists("autofetched_groups.json"):
        try:
            groups = bot.load_groups("autofetched_groups.json")
            if groups and len(groups) > 0:
                test_group = groups[0]
                print(f"Using group: {test_group}")
                
                # Post to the group
                if bot.setup_driver():
                    print("Driver initialized, logging in...")
                    if bot.login():
                        print("Successfully logged in, posting message...")
                        success = bot.post_to_group(test_group, test_message)
                        if success:
                            print("SUCCESS: Test message posted successfully!")
                        else:
                            print("ERROR: Failed to post test message.")
                    else:
                        print("ERROR: Failed to login to Facebook.")
                    bot.cleanup()
                else:
                    print("ERROR: Failed to initialize WebDriver.")
            else:
                print("ERROR: No groups found in autofetched_groups.json")
        except Exception as e:
            print(f"ERROR: {str(e)}")
    else:
        print("ERROR: autofetched_groups.json file not found. Run manual_fetch_groups.py first.")

if __name__ == "__main__":
    main() 