# Facebook Group Poster - Session Persistence Guide

## Overview

The Facebook Group Poster now supports **session persistence**, allowing you to bypass CAPTCHA and 2FA challenges after the first successful login. This significantly enhances reliability and speed for automated group fetching.

## How Session Persistence Works

Session persistence works by:

1. **Saving cookies** after a successful login
2. **Maintaining a Chrome profile directory** with session data
3. **Automatically reusing** this information in future runs

## Benefits

- **No repeated logins** needed
- **Bypass CAPTCHA** and 2FA requirements
- **Much faster** group fetching
- **Reduced risk** of Facebook detection
- **More reliable** automation

## First-Time Setup

The first time you use this feature, follow these steps:

1. Run the script without headless mode to handle any security challenges:
   ```bash
   python manual_fetch_groups.py --no-headless
   ```

2. When prompted, enter your Facebook credentials
   
3. If Facebook shows a CAPTCHA or 2FA challenge:
   - Complete it manually in the browser window
   - The script will wait for you to complete this step
   
4. After successful login, your session will be automatically saved

## Subsequent Usage

For all subsequent runs, the script will:

1. Automatically detect and use your saved session
2. Skip the login form entirely
3. Navigate directly to the Facebook groups page
4. Complete the group fetching without requiring credentials

```bash
# Regular usage (uses saved session by default)
python manual_fetch_groups.py
```

## Command Line Options

The `manual_fetch_groups.py` script supports these session-related arguments:

| Argument | Description |
|----------|-------------|
| `--use-session` | Use saved session if available (default) |
| `--no-session` | Don't use saved session, perform fresh login |
| `--reset-session` | Clear existing session and force new login |
| `--profile-dir DIR` | Specify custom Chrome profile directory |
| `--cookies-file FILE` | Specify custom cookies file |

## Web Interface

The web interface has also been enhanced:

1. The "Fetch My Groups" feature will automatically use saved sessions
2. You can check session status in the settings panel
3. Clear saved sessions if needed through the interface

## Troubleshooting

If you encounter issues with session persistence:

1. **Invalid Session**: Use `--reset-session` to force a fresh login
   ```bash
   python manual_fetch_groups.py --reset-session
   ```

2. **Facebook Security Challenges**: First login must be in visible browser mode (without `--headless`)

3. **Session Not Working**: If Facebook frequently challenges your login:
   - Try logging in manually to Facebook in a regular browser
   - Complete any security challenges
   - Then try the automated tool again

4. **Different Account**: If you need to switch accounts:
   - Use `--reset-session` flag
   - Delete or rename the profile directory and cookies file

## File Locations

- **Chrome Profile Directory**: `chrome_profile/` (configurable)
- **Cookies File**: `facebook_cookies.json` (configurable)

## Security Note

The saved session files contain sensitive authentication data. Ensure they are:
- Stored securely
- Not shared or committed to version control
- Accessible only to authorized users 

## Group Fetching Troubleshooting

If you're encountering issues with fetching Facebook groups, the improved group fetcher script provides several options to help resolve common problems:

### Group Extraction Issues

If the script opens Facebook but doesn't find or extract your groups correctly, try these approaches:

1. **Use Direct Navigation Mode**:
   ```
   python manual_fetch_groups.py --no-headless --force-direct
   ```
   This bypasses the UI navigation and goes directly to the groups list URLs.

2. **Provide Detailed Logging**:
   ```
   python manual_fetch_groups.py --no-headless --verbose
   ```
   This will show more detailed information about what the script is finding.

3. **Combine Options for Maximum Reliability**:
   ```
   python manual_fetch_groups.py --no-headless --force-direct --verbose
   ```
   Using all these options together often provides the best results for difficult cases.

### UI Languages

Facebook's interface is available in multiple languages, which can sometimes affect the group extraction. The script is now designed to handle UI in various languages, including:

- English
- Russian (Русский)
- Ukrainian (Українська)

No special configuration is needed for these languages, as the script automatically tries selectors for all supported languages.

### Timeout Settings

By default, the script will attempt to extract groups for up to 300 seconds (5 minutes). If you have a very large number of groups, you can increase this timeout:

```
python manual_fetch_groups.py --extract-timeout 600
```

This sets the timeout to 10 minutes. If extraction completes before the timeout, the script will finish normally. 