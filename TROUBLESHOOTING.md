# Troubleshooting Facebook Group Poster

This document provides solutions to common issues you might encounter when using the Facebook Group Poster application.

## Emoji and Special Character Issues

### Problem: "ChromeDriver only supports characters in the BMP"

This error occurs when trying to post messages containing emoji or other Unicode characters outside the Basic Multilingual Plane (BMP). Characters like emoji flags 🇺🇦🇨🇭, colorful emoji 🔥🚀, and other special symbols cause this error.

**Solution:** We've implemented a fix that uses JavaScript to set the text content instead of using Selenium's send_keys method. This bypasses ChromeDriver's Unicode limitations.

If you're still seeing this error:

1. Update to the latest version of the application
2. Try running one of our test scripts to verify the fix:
   ```
   python test_emoji_post.py
   ```
3. If problems persist, remove emoji and special characters from your posts

## Login and Authentication Issues

### Problem: Login Fails or Shows CAPTCHA

If the bot fails to log in or frequently encounters CAPTCHA challenges:

1. Use the session persistence feature:
   ```
   python manual_fetch_groups.py --no-headless
   ```
   This opens a visible browser where you can complete any CAPTCHA or 2FA challenges manually once

2. After completing the manual login, the session will be saved for future use

3. Ensure you're not trying to post too frequently, which can trigger Facebook's anti-automation measures

## Group Fetching Issues

### Problem: No Groups Found

If the application isn't finding your Facebook groups:

1. Run the manual fetch with visible browser:
   ```
   python manual_fetch_groups.py --no-headless --force-direct
   ```

2. Check the `autofetched_groups.json` file to verify groups were found

3. If Facebook's UI has changed, the selectors might need updating - check the logs for any errors

## Posting Issues

### Problem: Posts Not Being Published

If the bot navigates to groups but fails to publish posts:

1. Check if your account has proper permissions in the groups
2. Verify your post isn't being flagged by Facebook's content filters
3. Try with a simple text-only message first to verify the basic functionality
4. Look for error screenshots in the `screenshots` directory for visual clues

## Dashboard Issues

### Problem: Dashboard Not Showing Fetched Groups

If your dashboard isn't displaying groups from `autofetched_groups.json`:

1. Verify the JSON file exists and contains valid data
2. Restart the Flask application
3. Click the "Refresh Groups" button in the dashboard
4. Check browser console for any JavaScript errors

## Testing Your Setup

We've included two test scripts to verify your setup:

- `test_post.py` - Tests posting a simple text-only message
- `test_emoji_post.py` - Tests posting a message with emoji characters

Run these scripts to troubleshoot and verify that your setup is working correctly.

## Getting Help

If you continue experiencing issues after trying these troubleshooting steps, please:

1. Check the application logs in `poster.log`
2. Look at screenshots in the `screenshots` directory
3. Note the exact error messages you're seeing
4. Contact support with these details for further assistance 