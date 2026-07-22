"""
GitHub API Request Tracker

This module provides a wrapper around requests to track GitHub API calls per user.
It automatically increments both total and daily API call counters in the database.
The daily counter resets every 24 hours to provide recent usage metrics.
It also enforces rate limits based on account type.
"""

import requests
from sqlalchemy.orm import Session
from models import Account
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Exception raised when API rate limit is exceeded"""
    def __init__(self, message, reset_at=None, limit=None, used=None):
        super().__init__(message)
        self.reset_at = reset_at
        self.limit = limit
        self.used = used


def track_github_api_call(username: str, db: Session):
    """
    Increment the GitHub API call counters for a user.
    Tracks both total calls and calls in the last 24 hours.
    
    Args:
        username: The GitHub username
        db: Database session
    """
    try:
        user = db.query(Account).filter(Account.github_user == username).first()
        if user:
            # Increment total counter
            user.github_api_calls = (user.github_api_calls or 0) + 1
            
            # Check if daily counter needs reset (older than 24 hours)
            now = datetime.now(timezone.utc)
            
            # Ensure api_calls_reset_at is timezone-aware
            reset_time = user.api_calls_reset_at
            if reset_time is not None and reset_time.tzinfo is None:
                # Make it timezone-aware if it's naive
                reset_time = reset_time.replace(tzinfo=timezone.utc)
            
            if reset_time is None or (now - reset_time) > timedelta(hours=24):
                # Reset daily counter
                user.github_api_calls_today = 1
                user.api_calls_reset_at = now
                logger.debug(f"Reset daily API counter for {username}")
            else:
                # Increment daily counter
                user.github_api_calls_today = (user.github_api_calls_today or 0) + 1
            
            db.commit()
            logger.debug(f"Tracked API call for {username}: {user.github_api_calls} total, {user.github_api_calls_today} today")
    except Exception as e:
        logger.error(f"Failed to track API call for {username}: {e}")
        db.rollback()


def github_request(method: str, url: str, username: str, db: Session, **kwargs):
    """
    Make a GitHub API request and track it.
    Enforces rate limits before making the request.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        url: The API URL
        username: The GitHub username making the request
        db: Database session
        **kwargs: Additional arguments to pass to requests
        
    Returns:
        Response object from requests library
        
    Raises:
        RateLimitExceeded: If the user has exceeded their rate limit
    """
    # Only track and enforce limits if it's a GitHub API call
    if 'api.github.com' in url or 'github.com/api' in url:
        # Check rate limit before making the request
        from rate_limiter import check_rate_limit
        
        is_allowed, status_info = check_rate_limit(username, db)
        
        if not is_allowed:
            logger.warning(f"Rate limit exceeded for {username}: {status_info}")
            raise RateLimitExceeded(
                f"API rate limit exceeded. Limit resets at {status_info.get('reset_at')}",
                reset_at=status_info.get('reset_at'),
                limit=status_info.get('limit'),
                used=status_info.get('used')
            )
        
        # Track the API call
        track_github_api_call(username, db)
    
    # Make the actual request
    return requests.request(method, url, **kwargs)


def github_get(url: str, username: str, db: Session, **kwargs):
    """
    Make a GET request to GitHub API and track it.
    
    Args:
        url: The API URL
        username: The GitHub username making the request
        db: Database session
        **kwargs: Additional arguments to pass to requests.get
        
    Returns:
        Response object from requests library
    """
    return github_request('GET', url, username, db, **kwargs)


def github_post(url: str, username: str, db: Session, **kwargs):
    """
    Make a POST request to GitHub API and track it.
    
    Args:
        url: The API URL
        username: The GitHub username making the request
        db: Database session
        **kwargs: Additional arguments to pass to requests.post
        
    Returns:
        Response object from requests library
    """
    return github_request('POST', url, username, db, **kwargs)


def github_put(url: str, username: str, db: Session, **kwargs):
    """
    Make a PUT request to GitHub API and track it.
    
    Args:
        url: The API URL
        username: The GitHub username making the request
        db: Database session
        **kwargs: Additional arguments to pass to requests.put
        
    Returns:
        Response object from requests library
    """
    return github_request('PUT', url, username, db, **kwargs)


def github_delete(url: str, username: str, db: Session, **kwargs):
    """
    Make a DELETE request to GitHub API and track it.
    
    Args:
        url: The API URL
        username: The GitHub username making the request
        db: Database session
        **kwargs: Additional arguments to pass to requests.delete
        
    Returns:
        Response object from requests library
    """
    return github_request('DELETE', url, username, db, **kwargs)


def github_patch(url: str, username: str, db: Session, **kwargs):
    """
    Make a PATCH request to GitHub API and track it.
    
    Args:
        url: The API URL
        username: The GitHub username making the request
        db: Database session
        **kwargs: Additional arguments to pass to requests.patch
        
    Returns:
        Response object from requests library
    """
    return github_request('PATCH', url, username, db, **kwargs)
