# GitHub API Call Tracking - Integration Guide

This guide explains how to integrate the GitHub API call tracking functionality into existing code.

## Overview

The `github_api_tracker` module provides wrapper functions around the `requests` library that automatically track GitHub API calls in the database. Each time a GitHub API request is made, the user's `github_api_calls` counter is incremented.

## Basic Usage

### Before (without tracking):
```python
import requests
from auth import user_tokens

def get_repos(user: str):
    token = user_tokens[user]
    response = requests.get("https://api.github.com/user/repos", headers={
        "Authorization": f"token {token}"
    })
    return response.json()
```

### After (with tracking):
```python
from github_api_tracker import github_get
from auth import user_tokens
from database import SessionLocal

def get_repos(user: str):
    db = SessionLocal()
    try:
        token = user_tokens[user]
        response = github_get(
            "https://api.github.com/user/repos", 
            username=user,
            db=db,
            headers={"Authorization": f"token {token}"}
        )
        return response.json()
    finally:
        db.close()
```

## Integration with FastAPI Dependencies

When using FastAPI dependency injection, you already have a database session available:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from github_api_tracker import github_get
from auth import user_tokens

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/api/repos")
def get_repos(user: str, db: Session = Depends(get_db)):
    """Get user's repositories with API call tracking"""
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = user_tokens[user]
    
    # Use github_get instead of requests.get
    response = github_get(
        "https://api.github.com/user/repos",
        username=user,
        db=db,
        headers={"Authorization": f"token {token}"}
    )
    
    return response.json()
```

## Available Functions

The `github_api_tracker` module provides the following functions:

- `github_get(url, username, db, **kwargs)` - GET request
- `github_post(url, username, db, **kwargs)` - POST request  
- `github_put(url, username, db, **kwargs)` - PUT request
- `github_delete(url, username, db, **kwargs)` - DELETE request
- `github_patch(url, username, db, **kwargs)` - PATCH request
- `github_request(method, url, username, db, **kwargs)` - Generic request

All functions accept the same parameters as their `requests` library counterparts, with two additional required parameters:
- `username`: The GitHub username making the request
- `db`: A SQLAlchemy database session

## Smart Filtering

The tracker only counts calls to GitHub API URLs:
- ✅ `https://api.github.com/*` - Tracked
- ✅ `https://github.com/api/*` - Tracked
- ❌ `https://example.com/*` - NOT tracked

This ensures that only actual GitHub API calls affect the counter.

## Example: Complete Integration

Here's a complete example showing how to update an existing endpoint:

### Original Code (repos.py):
```python
@router.get("/api/repos")
def get_repos(user: str, db: Session = Depends(get_db)):
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail="User not authenticated")

    token = user_tokens[user]
    endpoints = get_github_api_endpoints(user, db)
    
    # Original line - not tracked:
    response = requests.get(endpoints["repos_list"], headers={
        "Authorization": f"token {token}"
    })

    return response.json()
```

### Updated Code (with tracking):
```python
from github_api_tracker import github_get  # Add import

@router.get("/api/repos")
def get_repos(user: str, db: Session = Depends(get_db)):
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail="User not authenticated")

    token = user_tokens[user]
    endpoints = get_github_api_endpoints(user, db)
    
    # Updated line - tracked:
    response = github_get(
        endpoints["repos_list"],
        username=user,
        db=db,
        headers={"Authorization": f"token {token}"}
    )

    return response.json()
```

## Migration Checklist

To integrate API tracking across the codebase:

1. ✅ Add `github_api_calls` column to Account model
2. ✅ Create and run database migration
3. ✅ Create `github_api_tracker` module
4. ✅ Update admin page to display API calls
5. ⏳ Replace `requests.get()` calls with `github_get()` in:
   - `backend/repos.py` (3 locations)
   - `backend/workflows.py` (11 locations)
   - `backend/auth.py` (2 locations - during OAuth flow)
   - Other modules making GitHub API calls
6. ⏳ Test each updated endpoint
7. ⏳ Monitor API call counts in production

## Testing

After integrating the tracker, verify it works:

```bash
# Run the test suite
cd backend
PYTHONPATH=. pytest tests/test_api_call_tracking.py -v

# Check a user's API call count
cd backend
sqlite3 test.db "SELECT github_user, github_api_calls FROM accounts WHERE github_user='your_username';"
```

## Performance Considerations

The API tracker adds a database write operation for each GitHub API call. This has minimal performance impact:

- Database writes are committed immediately (non-blocking)
- Counter increment is a simple SQL UPDATE statement
- No additional network calls are made
- Failed tracking doesn't affect the API response

## Future Enhancements

Potential improvements to consider:

1. **Rate Limiting**: Use API call counts to enforce rate limits per account type
2. **Analytics**: Track API calls over time for usage analytics
3. **Alerts**: Notify admins when users exceed thresholds
4. **Batching**: Batch counter updates to reduce database writes (requires Redis or similar)
5. **Endpoint Tracking**: Track which specific API endpoints are called most frequently
