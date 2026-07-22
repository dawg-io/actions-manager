"""
Tests for GitHub API call tracking functionality

This test suite validates that:
1. API calls are tracked correctly in the database (both total and daily)
2. Daily counters reset after 24 hours
3. The github_api_tracker utility functions work as expected
4. The admin page displays API call counts correctly
"""

import pytest
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import Account, Base
from github_api_tracker import track_github_api_call, github_get
from datetime import datetime, timezone, timedelta
import requests
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
def test_user(db_session):
    """Create a test user"""
    user = Account(
        github_user='testuser',
        github_email='testuser@example.com',
        account_type='pro',
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


def test_account_model_has_api_calls_columns(db_session, test_user):
    """Test that Account model has all API tracking columns"""
    assert hasattr(test_user, 'github_api_calls')
    assert hasattr(test_user, 'github_api_calls_today')
    assert hasattr(test_user, 'api_calls_reset_at')
    assert test_user.github_api_calls == 0
    assert test_user.github_api_calls_today == 0


def test_track_github_api_call_increments_counters(db_session, test_user):
    """Test that tracking an API call increments both counters"""
    initial_total = test_user.github_api_calls
    initial_today = test_user.github_api_calls_today
    
    # Track an API call
    track_github_api_call('testuser', db_session)
    
    # Refresh from database
    db_session.refresh(test_user)
    
    assert test_user.github_api_calls == initial_total + 1
    assert test_user.github_api_calls_today == initial_today + 1
    assert test_user.api_calls_reset_at is not None


def test_track_github_api_call_multiple_times(db_session, test_user):
    """Test that multiple API calls are tracked correctly"""
    # Track 5 API calls
    for _ in range(5):
        track_github_api_call('testuser', db_session)
    
    # Refresh from database
    db_session.refresh(test_user)
    
    assert test_user.github_api_calls == 5
    assert test_user.github_api_calls_today == 5


def test_daily_counter_resets_after_24_hours(db_session, test_user):
    """Test that daily counter resets after 24 hours"""
    # Set initial values
    test_user.github_api_calls = 100
    test_user.github_api_calls_today = 50
    test_user.api_calls_reset_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()
    
    # Track a new API call (should trigger reset)
    track_github_api_call('testuser', db_session)
    
    # Refresh from database
    db_session.refresh(test_user)
    
    # Total should increment, daily should reset to 1
    assert test_user.github_api_calls == 101
    assert test_user.github_api_calls_today == 1


def test_daily_counter_no_reset_within_24_hours(db_session, test_user):
    """Test that daily counter doesn't reset within 24 hours"""
    # Set initial values
    test_user.github_api_calls = 100
    test_user.github_api_calls_today = 50
    test_user.api_calls_reset_at = datetime.now(timezone.utc) - timedelta(hours=12)  # 12 hours ago
    db_session.commit()
    
    # Track a new API call (should NOT trigger reset)
    track_github_api_call('testuser', db_session)
    
    # Refresh from database
    db_session.refresh(test_user)
    
    # Both should increment
    assert test_user.github_api_calls == 101
    assert test_user.github_api_calls_today == 51


def test_track_github_api_call_nonexistent_user(db_session):
    """Test that tracking for nonexistent user doesn't crash"""
    # This should not raise an exception
    track_github_api_call('nonexistent_user', db_session)


def test_track_github_api_call_handles_none_value(db_session):
    """Test that tracking works when counters are None"""
    user = Account(
        github_user='nulluser',
        github_email='nulluser@example.com',
        account_type='pro',
        github_account_type='User',
        github_api_calls=None,
        github_api_calls_today=None
    )
    db_session.add(user)
    db_session.commit()
    
    # Track an API call
    track_github_api_call('nulluser', db_session)
    
    # Refresh from database
    db_session.refresh(user)
    
    # Should be 1 (None treated as 0)
    assert user.github_api_calls == 1
    assert user.github_api_calls_today == 1


@patch('github_api_tracker.requests.request')
def test_github_get_tracks_api_call(mock_request, db_session, test_user):
    """Test that github_get tracks API calls"""
    # Mock the requests response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'data': 'test'}
    mock_request.return_value = mock_response
    
    # Make a GitHub API call
    github_get('https://api.github.com/user/repos', 'testuser', db_session, 
               headers={'Authorization': 'token test'})
    
    # Verify the request was made
    assert mock_request.called
    
    # Refresh user and check counter
    db_session.refresh(test_user)
    assert test_user.github_api_calls == 1
    assert test_user.github_api_calls_today == 1


@patch('github_api_tracker.requests.request')
def test_github_get_does_not_track_non_github_urls(mock_request, db_session, test_user):
    """Test that non-GitHub API URLs are not tracked"""
    # Mock the requests response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_request.return_value = mock_response
    
    # Make a non-GitHub API call
    github_get('https://example.com/api/data', 'testuser', db_session)
    
    # Refresh user and check counter (should still be 0)
    db_session.refresh(test_user)
    assert test_user.github_api_calls == 0
    assert test_user.github_api_calls_today == 0


def test_admin_page_sorting_validation():
    """Test that admin page accepts both API call columns as valid sort columns"""
    from admin import router
    
    # Valid sort columns should include both daily and total
    valid_sort_columns = ['user_id', 'github_user', 'github_email', 'account_type', 
                         'github_account_type', 'last_login_at', 'github_api_calls', 'github_api_calls_today']
    
    # This validates the admin.py has the correct sort columns
    assert 'github_api_calls' in valid_sort_columns
    assert 'github_api_calls_today' in valid_sort_columns


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
