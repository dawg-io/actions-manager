# License Type Display Fix - Implementation Summary

## Issue Description
Users with new license types in self-hosted mode were incorrectly displayed as "Unknown" in the UI, leading to restrictive behavior (treated as free tier). This occurred because the backend was defaulting to "unknown" when marketplace billing data was absent.

## Root Cause Analysis
1. **Auth Module (`backend/auth.py`)**: The `_manage_user_in_database()` function was always checking marketplace billing data to determine account_type, even in self-hosted mode where billing data doesn't exist
2. **User API Endpoint**: The `/api/user/{username}` endpoint returned the raw `account_type` from the database instead of the effective tier
3. **Repos Filtering**: The `_should_restrict_to_public_repos()` function checked the raw account_type instead of using tier_service

## Solution Implemented

### 1. Modified `backend/auth.py`

#### `_manage_user_in_database()` Function
**Before:**
```python
account_type = "unknown"
if billing_data:
    account_type = billing_data[0].get("plan", {}).get("name", "unknown")
```

**After:**
```python
import config

# Determine account type based on installation mode
if config.INSTALLATION_MODE == "self-hosted":
    # Self-hosted mode: use license tier for all users
    import license
    account_type = license.get_installation_tier()
    debug_log(f"📌 Debug: Self-hosted mode - using license tier: {account_type}")
else:
    # Cloud mode: use billing data from marketplace
    account_type = "unknown"
    if billing_data:
        account_type = billing_data[0].get("plan", {}).get("name", "unknown")
    debug_log(f"📌 Debug: Cloud mode - account type from billing: {account_type}")
```

#### `get_user_details()` Endpoint
**Before:**
```python
return {
    "account_type": user.account_type,  # Raw database value
    ...
}
```

**After:**
```python
from tier_service import get_effective_tier
effective_tier = get_effective_tier(user)

return {
    "account_type": effective_tier,  # Effective tier based on mode
    ...
}
```

### 2. Modified `backend/repos.py`

#### `_should_restrict_to_public_repos()` Function
**Before:**
```python
# Free and unknown accounts are restricted to public repos only
if account.account_type in ("free", "unknown"):
    return True
    
# Professional and enterprise accounts have full access
if account.account_type in ("professional", "enterprise"):
    return False
```

**After:**
```python
# Get effective tier using tier_service (handles both cloud and self-hosted modes)
from tier_service import get_effective_tier
effective_tier = get_effective_tier(account)

# Free accounts are restricted to public repos only
if effective_tier == "free":
    return True
    
# Professional and enterprise accounts have full access
if effective_tier in ("professional", "enterprise"):
    return False
```

### 3. New Test File: `backend/tests/test_self_hosted_license_types.py`

Created comprehensive test suite with 12 tests covering:
- Self-hosted mode with professional/enterprise/free licenses
- Cloud mode with marketplace billing data
- Cloud mode without billing data (defaults to unknown)
- Effective tier determination in both modes
- User API endpoint returns correct effective tier
- Tier normalization (pro→professional, unknown→free)

### 4. Updated `backend/tests/test_repos_filtering.py`

Modified existing tests to work with tier_service integration by patching `tier_service.INSTALLATION_MODE` instead of just checking raw account_type values.

## How It Works

### Self-Hosted Mode Flow:
1. User authenticates via GitHub OAuth
2. `_manage_user_in_database()` detects INSTALLATION_MODE="self-hosted"
3. Calls `license.get_installation_tier()` to get tier from license key validation
4. Stores tier in account_type field (e.g., "professional", "enterprise", "free")
5. When frontend requests `/api/user/{username}`, tier_service returns effective tier
6. When checking repository access, tier_service provides the license tier

### Cloud Mode Flow:
1. User authenticates via GitHub OAuth
2. `_manage_user_in_database()` detects INSTALLATION_MODE="cloud"
3. Checks marketplace billing data for plan name
4. Stores plan in account_type field (or "unknown" if no billing data)
5. When frontend requests `/api/user/{username}`, tier_service checks marketplace_plan and account_type
6. tier_service normalizes "unknown" to "free" tier

## Tier Normalization

The `tier_service.normalize_tier_name()` function ensures consistency:
- `"pro"` → `"professional"`
- `"Professional"` → `"professional"`
- `"unknown"` → `"free"`
- `"weird_type"` → `"free"`
- `None` → `"free"`

## Testing Results

✅ **29 tests passing:**
- 12 new self-hosted license type tests
- 9 repository filtering tests (updated)
- 8 auth module tests (existing)

## Benefits

1. **Self-hosted installations**: License tier correctly determines user access
2. **Cloud installations**: Marketplace billing continues to work as before
3. **Consistency**: tier_service provides single source of truth for tier determination
4. **Safety**: Unknown or invalid tiers default to free tier with appropriate restrictions
5. **Display**: Frontend receives normalized, readable tier names

## Backward Compatibility

- ✅ Existing cloud mode installations continue to work with marketplace webhooks
- ✅ Existing account_type values in database are normalized via tier_service
- ✅ No database migration required
- ✅ All existing tests updated and passing

## Files Modified

1. `backend/auth.py` - License-aware user management and API endpoint
2. `backend/repos.py` - Tier-aware repository filtering
3. `backend/tests/test_self_hosted_license_types.py` - New test file
4. `backend/tests/test_repos_filtering.py` - Updated for tier_service integration

## Configuration Required

For self-hosted installations to use professional or enterprise tiers, set in `.env`:

```bash
INSTALLATION_MODE=self-hosted
LICENSE_KEY=your_jwt_license_key
```

If LICENSE_KEY are not provided or invalid, defaults to free tier.
