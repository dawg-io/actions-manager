# Marketplace Subscription + Tier System Integration

This document describes the integration between GitHub Marketplace subscriptions and the ActionsManager.xyz tier system.

## Overview

The tier system now fully integrates with GitHub Marketplace subscriptions, providing:
- Automatic tier determination based on marketplace status
- Admin override capability for manual tier management
- Data retention policies for downgrades
- Free trial and pending change support

## Architecture

### Tier Service (`tier_service.py`)

The tier service provides centralized tier enforcement logic that considers multiple factors:

1. **Admin Overrides** (highest priority)
   - Manual tier assignments by administrators
   - Can be indefinite or time-limited
   - Prevents marketplace webhooks from changing tier

2. **Marketplace Subscriptions**
   - Active subscriptions determine tier
   - Free trials grant access to purchased tier
   - Expired subscriptions fall back to account_type

3. **Account Type** (fallback)
   - Direct account_type field
   - Used when no marketplace subscription exists

### Priority Order

```
Admin Override (active) → Marketplace Subscription (active) → Account Type Field
```

## Key Functions

### `get_effective_tier(account: Account) -> str`

Determines the effective tier for an account, returning one of:
- `"free"` - Free tier (3 projects, 10 repos, 2 secrets, includes private repos & reusable workflows)
- `"professional"` - Professional tier (10 projects, 50 repos, 10 secrets)
- `"enterprise"` - Enterprise tier (unlimited projects/repos/secrets)

### Tier Limit Checks

- `check_project_limit(account, current_count)` - Validate project creation
- `check_private_repo_access(account)` - Retained for backwards compatibility; private repos are part of the core product on every tier
- `check_repo_limit(account, repo_count)` - Validate repo count per project
- `check_secrets_limit(account, secret_count)` - Validate secrets per project

### Admin Override Management

- `set_admin_override(account, tier, duration_days)` - Set manual tier override
- `clear_admin_override(account)` - Remove override, allow marketplace control

## Database Schema

### New Columns in `accounts` Table

```sql
-- Admin override for tier management
admin_override BOOLEAN DEFAULT FALSE NOT NULL
admin_override_until TIMESTAMP NULL
```

## Tier Limits

| Feature | Free | Professional | Enterprise |
|---------|------|--------------|------------|
| Projects | 3 | 10 | Unlimited |
| Repos per Project | 10 | 50 | Unlimited |
| Secrets per Project | 2 | 10 | Unlimited |
| Private Repos | ✅ | ✅ | ✅ |
| Reusable Workflows | ✅ | ✅ | ✅ |

## Usage Examples

### Check Project Limit

```python
from tier_service import check_project_limit

user = db.query(Account).filter(Account.github_user == "username").first()
user_projects_count = db.query(Project).filter(Project.user_id == user.user_id).count()

allowed, error_msg = check_project_limit(user, user_projects_count)
if not allowed:
    raise HTTPException(status_code=403, detail=error_msg)
```

### Check Private Repo Access

```python
from tier_service import check_private_repo_access

# Retained for backwards compatibility. Private repositories are part of the
# core product and are available on every tier (including Free), so this
# always returns (True, None).
allowed, error_msg = check_private_repo_access(user)
```

### Set Admin Override

```python
from tier_service import set_admin_override

# Set indefinite override to enterprise
set_admin_override(user, "enterprise", duration_days=None)

# Set 30-day override to professional
set_admin_override(user, "professional", duration_days=30)

db.commit()
```

### Clear Admin Override

```python
from tier_service import clear_admin_override

clear_admin_override(user)
db.commit()
```

## Integration with Marketplace Webhooks

### Webhook Processing Flow

1. Webhook received from GitHub Marketplace
2. Webhook stored in database for auditing
3. Check if user has active admin override
4. If admin override active:
   - Update marketplace metadata only
   - Do NOT change account_type
5. If no admin override:
   - Update marketplace metadata
   - Update account_type based on webhook action

### Webhook Actions

| Action | Admin Override Active | Admin Override Inactive |
|--------|----------------------|------------------------|
| `purchased` | Update metadata only | Update metadata + account_type |
| `changed` | Update metadata only | Update metadata + account_type |
| `cancelled` | Update metadata only | Update metadata + set to free |
| `pending_change` | Update metadata only | Update metadata only |

### Example: Purchase Webhook with Admin Override

```python
# User has admin override set to professional
user.account_type = "professional"
user.admin_override = True
user.admin_override_until = None

# Webhook for enterprise purchase arrives
# Result: marketplace_plan = "enterprise", but account_type stays "professional"
```

## Data Retention Policy

When a user downgrades or cancels their subscription:

- **Within 30 days**: Full data retention
- **After 30 days**: Data may be subject to cleanup

Check retention status:

```python
from tier_service import should_retain_data_on_downgrade

if should_retain_data_on_downgrade(user):
    # Keep all data
    pass
else:
    # Data cleanup allowed
    pass
```

## Free Trial Support

Free trials are fully supported:

```python
# User on free trial
user.marketplace_plan = "professional"
user.marketplace_on_free_trial = True
user.marketplace_next_billing_date = future_date

# Effective tier: professional (trial grants full access)
tier = get_effective_tier(user)
assert tier == "professional"
```

## Pending Changes

Pending plan changes are tracked but don't affect current tier:

```python
# Webhook: pending_change to enterprise
# effective_date: 2025-12-01

# Current tier remains unchanged until change is effective
# Webhook with action="changed" will arrive on effective date
```

## Admin Override Use Cases

### Temporary Trial Extension

Give a user extra time to evaluate a higher tier:

```python
# Extend professional access for 14 days
set_admin_override(user, "professional", duration_days=14)
```

### Permanent Special Access

Give specific users custom access:

```python
# Give beta testers enterprise access
set_admin_override(user, "enterprise", duration_days=None)
```

### Override Marketplace Issues

If marketplace billing has issues, manually maintain tier:

```python
# Keep professional access during billing issue
set_admin_override(user, "professional", duration_days=None)
```

## Migration

To add admin override support to existing database:

```bash
cd backend
python migrate_add_admin_override.py
```

The migration:
- Checks if accounts table exists
- Checks if columns already exist
- Adds `admin_override` and `admin_override_until` columns
- Handles both SQLite and PostgreSQL

## Testing

### Run Integration Tests

```bash
cd backend
source ../venv/bin/activate
PYTHONPATH=. pytest tests/test_marketplace_tier_integration.py -v
```

### Test Coverage

The integration test suite includes:

**Marketplace Tier Integration (3 tests)**
- Marketplace subscription determines tier
- Free trial grants access
- Expired subscription falls back to account_type

**Admin Overrides (3 tests)**
- Admin override prevents webhook updates
- Expired override allows webhook updates
- Set/clear admin override functions

**Retention Policy (2 tests)**
- Data retained within retention period
- Data cleanup allowed after retention period

**Webhook Upgrades/Downgrades (2 tests)**
- Upgrade from free to professional
- Downgrade from professional to free

**Pending Changes (1 test)**
- Pending change doesn't update tier

**Tier Enforcement Consistency (1 test)**
- Free trial enforcement across all features

**Total: 12 comprehensive integration tests**

## Monitoring and Debugging

### Check Effective Tier

```python
from tier_service import get_effective_tier

tier = get_effective_tier(user)
print(f"Effective tier: {tier}")
print(f"Account type: {user.account_type}")
print(f"Marketplace plan: {user.marketplace_plan}")
print(f"Admin override: {user.admin_override}")
```

### Audit Admin Overrides

```sql
SELECT 
    github_user,
    account_type,
    marketplace_plan,
    admin_override,
    admin_override_until
FROM accounts
WHERE admin_override = true;
```

### Audit Marketplace Updates

```sql
SELECT 
    github_user,
    marketplace_plan,
    marketplace_updated_at,
    account_type
FROM accounts
WHERE marketplace_updated_at IS NOT NULL
ORDER BY marketplace_updated_at DESC;
```

## Best Practices

1. **Use Tier Service Functions**
   - Always use tier service functions for enforcement
   - Don't check account_type directly
   - Ensures consistent behavior

2. **Document Admin Overrides**
   - Record why overrides are set
   - Set appropriate expiration dates
   - Review overrides periodically

3. **Monitor Retention Period**
   - Track users approaching retention deadline
   - Notify users before data cleanup
   - Implement cleanup automation carefully

4. **Test Marketplace Integration**
   - Use GitHub's stubbed marketplace API for testing
   - Test all webhook scenarios
   - Verify admin overrides work correctly

## Troubleshooting

### Issue: Admin Override Not Working

Check if override is expired:
```python
if user.admin_override_until and user.admin_override_until < datetime.now(timezone.utc):
    print("Override expired")
```

### Issue: Tier Incorrect

Debug tier determination:
```python
from tier_service import get_effective_tier

print(f"Admin override: {user.admin_override}")
print(f"Admin override until: {user.admin_override_until}")
print(f"Marketplace plan: {user.marketplace_plan}")
print(f"Marketplace billing date: {user.marketplace_next_billing_date}")
print(f"On free trial: {user.marketplace_on_free_trial}")
print(f"Effective tier: {get_effective_tier(user)}")
```

### Issue: Webhook Not Updating Tier

Check admin override status:
```sql
SELECT github_user, admin_override, admin_override_until
FROM accounts
WHERE github_user = 'username';
```

## Security Considerations

1. **Admin Override Access**
   - Requires HTTP Basic Auth
   - Limited to admin users
   - All changes logged

2. **Webhook Verification**
   - All webhooks verified with HMAC signature
   - Invalid signatures rejected
   - Audit trail maintained

3. **Tier Enforcement**
   - Enforced at API level
   - Cannot be bypassed
   - Consistent across all features

## Future Enhancements

Potential improvements:
- Automatic admin override expiration notifications
- Self-service trial extensions
- Detailed tier usage analytics
- Automated retention policy enforcement
- Tier migration tools
