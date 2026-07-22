# Professional Account Tier Implementation

## Overview

This document describes the implementation of the Professional account tier for Actions Manager. The Professional tier sits between the Free and Enterprise tiers, offering more features than Free but at a lower cost than Enterprise.

## Account Tier Comparison

| Feature | Free | Professional | Enterprise |
|---------|------|--------------|------------|
| **Max Projects** | 3 | 10 | Unlimited |
| **Private Repositories** | ❌ No | ✅ Yes | ✅ Yes |
| **Public Repositories** | ✅ Yes (5 per project) | ✅ Yes | ✅ Yes |
| **Secrets per Project** | 2 | 10 | Unlimited |
| **API Rate Limit** | 5,000/hour | 5,000/hour | 15,000/hour |
| **Reusable Workflows** | ❌ No | ✅ Yes | ✅ Yes |
| **Support** | Community | Email | Priority |

## Implementation Details

### Backend Changes

#### 1. Rate Limiter (`backend/rate_limiter.py`)

Updated the `RATE_LIMITS` dictionary to include Professional tier:

```python
RATE_LIMITS = {
    "free": 5000,
    "unknown": 5000,
    "pro": 5000,  # Legacy alias for professional
    "professional": 5000,
    "enterprise": 15000
}
```

- Professional tier has the same API rate limit as Free (5,000 calls/hour)
- Enterprise tier maintains higher limit (15,000 calls/hour)
- "pro" is kept as a legacy alias for backward compatibility

#### 2. Project Limits (`backend/projects.py`)

Enhanced project creation to enforce tier-specific limits:

**Free Tier:**
- Maximum 3 projects
- Maximum 5 public repositories per project
- No private repository access

**Professional Tier:**
- Maximum 10 projects
- Private repository access enabled
- No public repository limit per project

**Enterprise Tier:**
- Unlimited projects
- Full access to all features

Error messages include helpful upgrade prompts directing users to the appropriate next tier.

#### 3. Secrets Management (`backend/github_secrets.py`)

Updated `_validate_account_limits()` function to enforce secrets limits:

**Free Tier:**
- Maximum 2 secrets per project

**Professional Tier:**
- Maximum 10 secrets per project

**Enterprise Tier:**
- Unlimited secrets per project

The function dynamically determines the limit based on account type and provides contextual error messages with upgrade suggestions.

#### 4. Admin Panel (`backend/admin.py`)

The admin panel already supported "professional" as a valid account type through the `AccountTypeUpdate` Pydantic model validator:

```python
@field_validator('account_type')
@classmethod
def validate_account_type(cls, v: str) -> str:
    allowed_types = ['free', 'professional', 'enterprise']
    if v not in allowed_types:
        raise ValueError(f'account_type must be one of: {", ".join(allowed_types)}')
    return v
```

No changes were needed to the admin panel.

### Migration Script

Created `backend/migrate_normalize_professional_tier.py` to:
- Update any accounts with `account_type='pro'` to `account_type='professional'`
- Maintain backward compatibility with "pro" alias in code
- Provide statistics on account type distribution

Usage:
```bash
cd backend
python migrate_normalize_professional_tier.py
```

### Test Coverage

#### Project Limits Tests (`backend/tests/test_project_limits.py`)

Added/updated tests:
1. ✅ `test_pro_user_project_limit` - Verifies 10 project limit for Professional
2. ✅ `test_enterprise_user_not_limited` - Verifies Enterprise has no limits
3. ✅ `test_free_user_cannot_use_private_repos` - Verifies Free cannot use private repos
4. ✅ `test_professional_user_can_use_private_repos` - Verifies Professional can use private repos

**Results:** 8/8 tests passing

#### Secrets Limits Tests (`backend/tests/test_secrets_limits.py`)

Added tests:
1. ✅ `test_free_user_secrets_limit` - Verifies 2 secrets limit for Free
2. ✅ `test_professional_user_secrets_limit` - Verifies 10 secrets limit for Professional
3. ✅ `test_professional_user_under_limit` - Verifies Professional can add secrets under limit
4. ✅ `test_enterprise_user_no_limit` - Verifies Enterprise has no limits

**Results:** 8/8 tests passing

#### Rate Limiter Tests (`backend/tests/test_rate_limiter.py`)

Added test:
1. ✅ `test_check_rate_limit_professional_has_same_limit_as_free` - Verifies Professional has 5,000/hour limit

Updated test:
1. ✅ `test_rate_limit_configuration` - Added Professional tier verification

**Results:** 17/17 tests passing

#### Admin Tests (`backend/tests/test_admin.py`)

Existing tests already validated "professional" as a valid account type:
1. ✅ `test_update_account_type_success` - Tests updating to Professional
2. ✅ `test_update_account_type_all_valid_types` - Validates all tier types

**Results:** 6/6 tests passing

**Total Test Coverage:** 39/39 tests passing ✅

### Documentation Updates

#### 1. README.md

Added comprehensive account tier comparison table showing:
- Feature availability across all tiers
- Clear visual indicators (✅/❌) for feature availability
- Upgrade guidance for users

#### 2. RATE_LIMITING_IMPLEMENTATION.md

Updated to reflect Professional tier:
- Added Professional to rate limits configuration
- Updated documentation to mention all three tiers
- Maintained "pro" as legacy alias with explanation

## Usage Examples

### Creating Projects

**Free User:**
```python
# Can create up to 3 projects with public repos only
# Attempting 4th project: Error 403
# "Free accounts can only create up to 3 projects. Upgrade to Professional for up to 10 projects."
```

**Professional User:**
```python
# Can create up to 10 projects with private repos
# Attempting 11th project: Error 403
# "Professional accounts can create up to 10 projects. Upgrade to Enterprise for unlimited projects."
```

**Enterprise User:**
```python
# Unlimited projects with all features
```

### Managing Secrets

**Free User:**
```python
# Can create up to 2 secrets per project
# Attempting to exceed: Error 403
# "Free accounts can create up to 2 secrets per project. 
#  You currently have 2 and are trying to add 1 new secrets. 
#  Upgrade to Professional for up to 10 secrets per project."
```

**Professional User:**
```python
# Can create up to 10 secrets per project
# Attempting to exceed: Error 403
# "Professional accounts can create up to 10 secrets per project. 
#  You currently have 10 and are trying to add 1 new secrets. 
#  Upgrade to Enterprise for unlimited secrets."
```

### Account Upgrades

Administrators can upgrade user accounts through the admin panel at `/admin/users`:

1. Click the ⚙️ icon next to a user
2. Select "Professional" from the dropdown
3. Click "Save Changes"
4. User immediately gains Professional tier benefits

## Backward Compatibility

- **Legacy "pro" alias**: Code still accepts "pro" as account_type for backward compatibility
- **Migration script**: Normalizes "pro" to "professional" in the database
- **No breaking changes**: Existing functionality remains unchanged

## Error Messages

All error messages include:
- Current usage information
- Specific limit that was exceeded
- Upgrade suggestion with next appropriate tier
- Clear, user-friendly language

Example:
```
"Professional accounts can create up to 10 projects. Upgrade to Enterprise for unlimited projects."
```

## Security Considerations

- ✅ All limits enforced server-side (cannot be bypassed from frontend)
- ✅ Validation at API endpoint level
- ✅ Proper error handling and status codes
- ✅ CodeQL security scan: 0 issues found
- ✅ Code review: 0 issues found

## Testing Strategy

### Manual Testing Checklist

1. **Project Creation**
   - [ ] Free user can create 3 projects
   - [ ] Free user blocked at 4th project
   - [ ] Free user cannot use private repos
   - [ ] Professional user can create 10 projects
   - [ ] Professional user blocked at 11th project
   - [ ] Professional user can use private repos
   - [ ] Enterprise user has no limits

2. **Secrets Management**
   - [ ] Free user can create 2 secrets per project
   - [ ] Free user blocked at 3rd secret
   - [ ] Professional user can create 10 secrets per project
   - [ ] Professional user blocked at 11th secret
   - [ ] Enterprise user has no secrets limit

3. **API Rate Limiting**
   - [ ] Professional user has 5,000/hour limit
   - [ ] Warning displayed at 90% usage
   - [ ] Blocked at 100% usage
   - [ ] Resets after 24 hours

4. **Admin Panel**
   - [ ] Can upgrade Free to Professional
   - [ ] Can upgrade Professional to Enterprise
   - [ ] Can downgrade Enterprise to Professional
   - [ ] Changes take effect immediately

### Automated Test Results

- **Project Limits:** 8/8 passing ✅
- **Secrets Limits:** 8/8 passing ✅
- **Rate Limiter:** 17/17 passing ✅
- **Admin Panel:** 6/6 passing ✅
- **Total:** 39/39 tests passing ✅

## Deployment

### Prerequisites

1. Backend Python dependencies installed
2. Database accessible (PostgreSQL recommended for production)

### Deployment Steps

1. **Deploy code changes:**
   ```bash
   git pull origin main
   source venv/bin/activate
   pip install -r backend/requirements.txt
   ```

2. **Run migration script:**
   ```bash
   cd backend
   python migrate_normalize_professional_tier.py
   ```

3. **Restart backend service:**
   ```bash
   # Method depends on your deployment (systemd, docker, etc.)
   systemctl restart actions-manager-backend
   ```

4. **Verify deployment:**
   ```bash
   # Check backend health
   curl http://localhost:8000/docs
   
   # Run tests
   PYTHONPATH=./backend python -m pytest backend/tests/test_project_limits.py
   PYTHONPATH=./backend python -m pytest backend/tests/test_secrets_limits.py
   PYTHONPATH=./backend python -m pytest backend/tests/test_rate_limiter.py
   ```

### Rollback Plan

If issues occur:

1. **Revert code:**
   ```bash
   git revert <commit-hash>
   git push origin main
   ```

2. **Rollback database (if needed):**
   ```sql
   -- Revert professional to pro if needed
   UPDATE accounts SET account_type = 'pro' WHERE account_type = 'professional';
   ```

## Support and Troubleshooting

### Common Issues

**Issue:** User cannot create project despite being under limit
- **Check:** Verify account_type is set correctly in database
- **Fix:** Update account_type in admin panel or directly in database

**Issue:** Migration script fails
- **Check:** Database connectivity and permissions
- **Fix:** Ensure database is accessible and user has UPDATE privileges

**Issue:** Tests failing
- **Check:** Python environment and dependencies
- **Fix:** Recreate virtual environment and reinstall dependencies

## Future Enhancements

Potential improvements for future releases:

1. **Self-service upgrades:** Allow users to upgrade their own accounts
2. **Usage dashboards:** Show users their current usage vs. limits
3. **Grace periods:** Allow brief overages with warnings
4. **Custom limits:** Admin-configurable limits per user
5. **Usage analytics:** Track feature adoption by tier
6. **Automated downgrade:** Downgrade inactive paid accounts

## Conclusion

The Professional account tier implementation provides a balanced middle option between Free and Enterprise, meeting the needs of:

- **Individual developers** needing private repo access
- **Small teams** requiring more projects than Free allows
- **Organizations** not requiring Enterprise-level API limits

All changes maintain backward compatibility, include comprehensive test coverage, and follow established patterns in the codebase.
