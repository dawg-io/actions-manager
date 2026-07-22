"""
Tests for API Rate Limiting functionality

This test suite validates that:
1. Rate limits are correctly configured for different account types
2. Rate limit checking works correctly
3. Users are blocked when exceeding limits
4. Warnings are displayed when approaching limits
5. Rate limits reset after 24 hours
"""

import pytest
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Account, Base
from rate_limiter import (
    get_rate_limit_for_account,
    check_rate_limit,
    RATE_LIMITS,
    WARNING_THRESHOLD
)
from github_api_tracker import RateLimitExceeded, github_request
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch


@pytest.fixture
def db_session():
    """Create a fresh database session for testing"""
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    db = SessionLocal()
    
    yield db
    
    # Cleanup
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def free_user(db_session):
    """Create a test user with free account"""
    user = Account(
        github_user='freeuser',
        github_email='freeuser@example.com',
        account_type='free',
        github_account_type='User',
        avatar_url='https://example.com/avatar.png',
        last_login_at=datetime.now(timezone.utc),
        last_login_ip='127.0.0.1',
        github_api_calls=0,
        github_api_calls_today=0,
        api_calls_reset_at=None
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def enterprise_user(db_session):
    """Create a test user with enterprise account"""
    user = Account(
        github_user='enterpriseuser',
        github_email='enterpriseuser@example.com',
        account_type='enterprise',
        github_account_type='Organization',
        avatar_url='https://example.com/avatar.png',
        last_login_at=datetime.now(timezone.utc),
        last_login_ip='127.0.0.1',
        github_api_calls=0,
        github_api_calls_today=0,
        api_calls_reset_at=None
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def professional_user(db_session):
    """Create a test user with professional account"""
    user = Account(
        github_user='professionaluser',
        github_email='professionaluser@example.com',
        account_type='professional',
        github_account_type='User',
        avatar_url='https://example.com/avatar.png',
        last_login_at=datetime.now(timezone.utc),
        last_login_ip='127.0.0.1',
        github_api_calls=0,
        github_api_calls_today=0,
        api_calls_reset_at=None
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_rate_limit_configuration():
    """Test that rate limits are correctly configured"""
    assert get_rate_limit_for_account("free") == 5000
    assert get_rate_limit_for_account("unknown") == 5000
    assert get_rate_limit_for_account("professional") == 5000
    assert get_rate_limit_for_account("enterprise") == 15000


def test_rate_limit_for_unknown_account_type():
    """Test that unknown account types default to free tier"""
    assert get_rate_limit_for_account("invalid_type") == 5000
    assert get_rate_limit_for_account(None) == 5000


def test_check_rate_limit_allows_new_user(db_session, free_user):
    """Test that new users are allowed to make API calls"""
    is_allowed, status = check_rate_limit('freeuser', db_session)
    
    assert is_allowed is True
    assert status['limit'] == 5000
    assert status['used'] == 0
    assert status['remaining'] == 5000
    assert status['should_warn'] is False


def test_check_rate_limit_enterprise_has_higher_limit(db_session, enterprise_user):
    """Test that enterprise users have higher limits"""
    is_allowed, status = check_rate_limit('enterpriseuser', db_session)
    
    assert is_allowed is True
    assert status['limit'] == 15000
    assert status['remaining'] == 15000


def test_check_rate_limit_professional_has_same_limit_as_free(db_session, professional_user):
    """Test that professional users have the same API rate limit as free users"""
    is_allowed, status = check_rate_limit('professionaluser', db_session)
    
    assert is_allowed is True
    assert status['limit'] == 5000
    assert status['remaining'] == 5000
    assert status['account_type'] == 'professional'


def test_check_rate_limit_blocks_when_exceeded(db_session, free_user):
    """Test that users are blocked when exceeding their limit"""
    # Set user at the limit
    free_user.github_api_calls_today = 5000
    free_user.api_calls_reset_at = datetime.now(timezone.utc)
    db_session.commit()
    
    is_allowed, status = check_rate_limit('freeuser', db_session)
    
    assert is_allowed is False
    assert status['used'] == 5000
    assert status['remaining'] == 0


def test_check_rate_limit_shows_warning_below_10_percent(db_session, free_user):
    """Test that warning is shown when below 10% remaining"""
    # Set user at 91% usage (4550 out of 5000)
    free_user.github_api_calls_today = 4550
    free_user.api_calls_reset_at = datetime.now(timezone.utc)
    db_session.commit()
    
    is_allowed, status = check_rate_limit('freeuser', db_session)
    
    assert is_allowed is True
    assert status['should_warn'] is True
    assert status['percentage_used'] == 91.0
    assert status['remaining'] == 450


def test_check_rate_limit_no_warning_above_10_percent(db_session, free_user):
    """Test that no warning is shown when above 10% remaining"""
    # Set user at 50% usage (2500 out of 5000)
    free_user.github_api_calls_today = 2500
    free_user.api_calls_reset_at = datetime.now(timezone.utc)
    db_session.commit()
    
    is_allowed, status = check_rate_limit('freeuser', db_session)
    
    assert is_allowed is True
    assert status['should_warn'] is False
    assert status['percentage_used'] == 50.0
    assert status['remaining'] == 2500


def test_check_rate_limit_resets_after_24_hours(db_session, free_user):
    """Test that rate limit resets after 24 hours"""
    # Set user at limit 25 hours ago
    free_user.github_api_calls_today = 5000
    free_user.api_calls_reset_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()
    
    is_allowed, status = check_rate_limit('freeuser', db_session)
    
    # Should be allowed again after reset
    assert is_allowed is True
    assert status['used'] == 0
    assert status['remaining'] == 5000


def test_check_rate_limit_no_reset_within_24_hours(db_session, free_user):
    """Test that rate limit doesn't reset within 24 hours"""
    # Set user at limit 12 hours ago
    free_user.github_api_calls_today = 5000
    free_user.api_calls_reset_at = datetime.now(timezone.utc) - timedelta(hours=12)
    db_session.commit()
    
    is_allowed, status = check_rate_limit('freeuser', db_session)
    
    # Should still be blocked
    assert is_allowed is False
    assert status['used'] == 5000
    assert status['remaining'] == 0


def test_check_rate_limit_nonexistent_user(db_session):
    """Test that checking rate limit for nonexistent user returns error"""
    is_allowed, status = check_rate_limit('nonexistent', db_session)
    
    assert is_allowed is False
    assert 'error' in status
    assert status['error'] == 'User not found'


def test_get_rate_limit_status(db_session, free_user):
    """Test getting rate limit status"""
    free_user.github_api_calls_today = 3000
    free_user.api_calls_reset_at = datetime.now(timezone.utc)
    db_session.commit()
    
    _, status = check_rate_limit('freeuser', db_session)
    
    assert status['limit'] == 5000
    assert status['used'] == 3000
    assert status['remaining'] == 2000
    assert status['account_type'] == 'free'


@patch('github_api_tracker.requests.request')
def test_github_request_raises_rate_limit_exceeded(mock_request, db_session, free_user):
    """Test that github_request raises RateLimitExceeded when limit is exceeded"""
    # Set user at limit
    free_user.github_api_calls_today = 5000
    free_user.api_calls_reset_at = datetime.now(timezone.utc)
    db_session.commit()
    
    # Try to make a GitHub API request
    with pytest.raises(RateLimitExceeded) as exc_info:
        github_request('GET', 'https://api.github.com/user/repos', 'freeuser', db_session)
    
    # Verify exception details
    assert exc_info.value.limit == 5000
    assert exc_info.value.used == 5000
    assert exc_info.value.reset_at is not None
    
    # Request should not have been made
    assert not mock_request.called


@patch('github_api_tracker.requests.request')
def test_github_request_allows_when_under_limit(mock_request, db_session, free_user):
    """Test that github_request works when under limit"""
    # Set user well under limit
    free_user.github_api_calls_today = 100
    free_user.api_calls_reset_at = datetime.now(timezone.utc)
    db_session.commit()
    
    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_request.return_value = mock_response
    
    # Make a GitHub API request
    response = github_request('GET', 'https://api.github.com/user/repos', 'freeuser', db_session)
    
    # Request should have been made
    assert mock_request.called
    assert response.status_code == 200
    
    # Counter should have incremented
    db_session.refresh(free_user)
    assert free_user.github_api_calls_today == 101


@patch('github_api_tracker.requests.request')
def test_github_request_non_github_url_not_rate_limited(mock_request, db_session, free_user):
    """Test that non-GitHub URLs are not rate limited"""
    # Set user at limit
    free_user.github_api_calls_today = 5000
    free_user.api_calls_reset_at = datetime.now(timezone.utc)
    db_session.commit()
    
    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_request.return_value = mock_response
    
    # Make a non-GitHub API request - should not raise exception
    response = github_request('GET', 'https://example.com/api/data', 'freeuser', db_session)
    
    # Request should have been made
    assert mock_request.called
    assert response.status_code == 200


def test_warning_threshold_is_10_percent():
    """Test that warning threshold is set to 10%"""
    assert WARNING_THRESHOLD == 0.10


def test_enterprise_user_higher_threshold_for_warning(db_session, enterprise_user):
    """Test that enterprise users get warnings at higher usage"""
    # Set enterprise user at 91% usage (13650 out of 15000)
    enterprise_user.github_api_calls_today = 13650
    enterprise_user.api_calls_reset_at = datetime.now(timezone.utc)
    db_session.commit()
    
    is_allowed, status = check_rate_limit('enterpriseuser', db_session)
    
    assert is_allowed is True
    assert status['should_warn'] is True
    assert status['remaining'] == 1350


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
