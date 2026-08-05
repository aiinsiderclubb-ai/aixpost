"""
Facebook Group Poster - Post Analytics Logger
Provides structured logging for post attempts with support for analytics and reporting
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# Configure module logger
logger = logging.getLogger(__name__)

# Constants
LOG_DIR = "logs"
LOG_FILE = "posting_log.json"
LOG_PATH = os.path.join(LOG_DIR, LOG_FILE)

# Status constants
STATUS_SUCCESS = "SUCCESS"
STATUS_ERROR = "ERROR"
STATUS_BLOCKED = "BLOCKED"


def ensure_log_directory() -> None:
    """Ensure the logs directory exists"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create log directory: {str(e)}")
        raise


def read_log_file() -> List[Dict[str, Any]]:
    """
    Read and parse the log file
    
    Returns:
        List of log entries or empty list if file doesn't exist
    """
    if not os.path.exists(LOG_PATH):
        return []
    
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # If the file is empty or corrupted, return an empty list
        logger.warning(f"Log file {LOG_PATH} is empty or corrupted. Starting fresh.")
        return []
    except Exception as e:
        logger.error(f"Error reading log file: {str(e)}")
        return []


def write_log_file(logs: List[Dict[str, Any]]) -> bool:
    """
    Write logs to the log file
    
    Args:
        logs: List of log entries
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        ensure_log_directory()
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to write to log file: {str(e)}")
        return False


def log_post_result(
    group_name: str, 
    group_url: str, 
    status: str, 
    account: str, 
    message: str = ""
) -> bool:
    """
    Log a post attempt result to the structured log file
    
    Args:
        group_name: Name of the Facebook group
        group_url: URL of the Facebook group
        status: Result status (SUCCESS, ERROR, BLOCKED)
        account: Facebook account used for posting
        message: Optional details (e.g., error message)
        
    Returns:
        bool: True if logging was successful
    """
    # Validate status
    if status not in (STATUS_SUCCESS, STATUS_ERROR, STATUS_BLOCKED):
        logger.warning(f"Invalid status '{status}', defaulting to ERROR")
        status = STATUS_ERROR
    
    # Create log entry
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "group_name": group_name,
        "group_url": group_url,
        "status": status,
        "message": message,
        "account": account
    }
    
    # Read existing logs
    try:
        logs = read_log_file()
        
        # Add new entry
        logs.append(log_entry)
        
        # Write updated logs
        return write_log_file(logs)
    except Exception as e:
        logger.error(f"Failed to log post result: {str(e)}")
        
        # Attempt to write directly to a fallback log if reading fails
        try:
            fallback_path = os.path.join(LOG_DIR, "fallback_log.json")
            ensure_log_directory()
            with open(fallback_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            return True
        except Exception as fallback_error:
            logger.error(f"Fallback logging also failed: {str(fallback_error)}")
            return False


def filter_logs(
    status: Optional[str] = None, 
    account: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filter logs by various criteria
    
    Args:
        status: Filter by status (SUCCESS, ERROR, BLOCKED)
        account: Filter by account name
        start_date: Filter by start date (ISO format)
        end_date: Filter by end date (ISO format)
        
    Returns:
        List of filtered log entries
    """
    logs = read_log_file()
    filtered_logs = logs.copy()
    
    if status:
        filtered_logs = [log for log in filtered_logs if log.get("status") == status]
    
    if account:
        filtered_logs = [log for log in filtered_logs if log.get("account") == account]
    
    if start_date:
        filtered_logs = [log for log in filtered_logs if log.get("timestamp", "") >= start_date]
    
    if end_date:
        filtered_logs = [log for log in filtered_logs if log.get("timestamp", "") <= end_date]
    
    return filtered_logs


def get_statistics() -> Dict[str, Any]:
    """
    Get posting statistics
    
    Returns:
        Dictionary with success rate, counts, etc.
    """
    logs = read_log_file()
    
    if not logs:
        return {
            "total": 0,
            "success": 0,
            "error": 0,
            "blocked": 0,
            "success_rate": 0.0
        }
    
    success_count = sum(1 for log in logs if log.get("status") == STATUS_SUCCESS)
    error_count = sum(1 for log in logs if log.get("status") == STATUS_ERROR)
    blocked_count = sum(1 for log in logs if log.get("status") == STATUS_BLOCKED)
    total = len(logs)
    
    return {
        "total": total,
        "success": success_count,
        "error": error_count,
        "blocked": blocked_count,
        "success_rate": (success_count / total) * 100 if total > 0 else 0.0
    } 