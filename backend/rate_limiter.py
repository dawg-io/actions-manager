"""
API Rate Limiter

This module provides rate limiting functionality based on account types.
It checks if users have exceeded their API call limits and provides
warnings when approaching the limit.

Rate limits based on GitHub API standards:
- Free accounts: 5,000 API calls per hour
- Pro accounts: 5,000 API calls per hour (same as free)
- Enterprise accounts: 15,000 API calls per hour
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from models import Account
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# Rate limit configuration (calls per hour)
RATE_LIMITS = {
    "free": 5000,
    "unknown": 5000,  # Default to free tier
    "professional": 5000,
    "enterprise": 15000
}

# Warning threshold percentage
WARNING_THRESHOLD = 0.10  # 10%


def get_rate_limit_for_account(account_type: str) -> int:
    """
    Get the rate limit for a specific account type.
    
    Args:
        account_type: The account type (free, pro, enterprise, unknown)
        
    Returns:
        The hourly rate limit for the account type
    """
    normalized_type = account_type.lower() if account_type else "unknown"
    return RATE_LIMITS.get(normalized_type, RATE_LIMITS["unknown"])


def check_rate_limit(username: str, db: Session) -> Tuple[bool, Dict]:
    """
    Check if a user has exceeded their rate limit.
    
    Args:
        username: The GitHub username
        db: Database session
        
    Returns:
        Tuple of (is_allowed, status_info)
        - is_allowed: True if the user can make more API calls, False otherwise
        - status_info: Dictionary with rate limit status information
    """
    user = db.query(Account).filter(Account.github_user == username).first()
    
    if not user:
        logger.warning(f"User {username} not found for rate limit check")
        return False, {
            "error": "User not found",
            "limit": 0,
            "used": 0,
            "remaining": 0,
            "reset_at": None
        }
    
    # Get rate limit for account type
    limit = get_rate_limit_for_account(user.account_type)
    
    # Get current usage (last 24 hours)
    used = user.github_api_calls_today or 0
    remaining = max(0, limit - used)
    
    # Check if daily counter needs reset (older than 24 hours)
    now = datetime.now(timezone.utc)
    reset_time = user.api_calls_reset_at
    
    # Ensure reset_time is timezone-aware
    if reset_time is not None and reset_time.tzinfo is None:
        reset_time = reset_time.replace(tzinfo=timezone.utc)
    
    # If no reset time or it's been more than 24 hours, the limit has reset
    if reset_time is None:
        # First API call - set reset time to 24 hours from now
        reset_at = now + timedelta(hours=24)
        is_allowed = True
        remaining = limit
        used = 0
    elif (now - reset_time) > timedelta(hours=24):
        # Reset period has passed
        reset_at = now + timedelta(hours=24)
        is_allowed = True
        remaining = limit
        used = 0
    else:
        # Within current period
        reset_at = reset_time + timedelta(hours=24)
        is_allowed = used < limit
    
    # Calculate percentage used
    percentage_used = (used / limit * 100) if limit > 0 else 0
    
    # Determine if warning should be shown
    should_warn = percentage_used >= (100 - (WARNING_THRESHOLD * 100))
    
    status_info = {
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "reset_at": reset_at.isoformat(),
        "percentage_used": round(percentage_used, 2),
        "should_warn": should_warn,
        "account_type": user.account_type
    }
    
    logger.debug(f"Rate limit check for {username}: {status_info}")
    
    return is_allowed, status_info
