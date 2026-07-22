# GitHub Permission Validation System

This document describes the GitHub permission validation system implemented in Actions Manager.

## Overview

The GitHub permission validation system ensures that users have all required GitHub OAuth scopes and repository access needed for Actions Manager to function correctly. When users sign in, the system automatically checks their GitHub permissions and alerts them if anything is missing.

## Features

### 1. Comprehensive Permission Checking

The system validates:

- **OAuth Scopes**: Checks that the GitHub token has all required scopes (repo, workflow, read:org, user:email)
- **Repository Access**: Verifies the user can access repositories and has write permissions
- **Organization Access**: Detects organization-level restrictions and third-party OAuth app approvals
- **Token Validity**: Confirms the GitHub access token is still valid and not expired

### 2. User-Friendly Alerts

When permission issues are detected, users see:

- Clear explanation of what's missing
- Impact on functionality
- Step-by-step recommendations to fix the issue
- Easy reconnect/reauthorize action

### 3. Persistent Status Tracking

- Permission status is stored in the database
- Last check timestamp is recorded
- Status persists across sessions

## Required GitHub Permissions

Actions Manager requires the following GitHub OAuth scopes:

| Scope | Critical | Purpose |
|-------|----------|---------|
| `repo` | Yes | Full control of private repositories - needed for reading/writing workflow files, creating PRs, managing branches |
| `workflow` | Yes | Update GitHub Action workflows - needed for creating and modifying workflow files |
| `read:org` | No | Read org and team membership - needed for accessing organization repositories |
| `user:email` | Yes | Access user email addresses - needed for user identification and account creation |

## Architecture

### Backend Components

#### 1. `github_permissions.py`

Core permission validation module containing:

- `PermissionStatus` enum: Standardized status codes
- `PermissionRequirement` dataclass: Permission metadata
- `REQUIRED_GITHUB_PERMISSIONS`: Single source of truth for required permissions
- `GitHubPermissionValidator`: Main validation class

**Key Methods:**
- `validate_all_permissions()`: Comprehensive validation returning detailed status
- `_check_token_validity()`: Validates GitHub token is active
- `_check_oauth_scopes()`: Checks granted OAuth scopes against requirements
- `_check_repository_access()`: Verifies repository access and write permissions
- `_check_organization_access()`: Detects organization restrictions

#### 2. `auth.py` - Permission Check Endpoint

**Endpoint:** `GET /api/user/{username}/permissions`

Returns:
```json
{
  "status": "valid|missing_scopes|missing_repo_access|...",
  "valid": true|false,
  "missing_scopes": ["scope1", "scope2"],
  "granted_scopes": ["scope1", "scope2"],
  "issues": ["Human-readable issue descriptions"],
  "warnings": ["Non-critical warnings"],
  "recommendations": ["Actionable steps to fix"],
  "message": "Formatted user-friendly message",
  "details": {
    "scopes": {...},
    "repository_access": {...},
    "organization_access": {...}
  }
}
```

#### 3. Database Model Changes

Added to `Account` model:
```python
github_permission_status = Column(String(50), nullable=True)
github_permission_checked_at = Column(DateTime, nullable=True)
```

### Frontend Components

#### 1. `api/user.ts` - API Client

**Interface:** `PermissionValidationResult`
- TypeScript types for permission validation responses

**Function:** `checkGitHubPermissions(username: string)`
- Fetches permission status from backend

#### 2. `components/PermissionAlert.tsx`

React component that displays permission alerts with:

- Color-coded severity levels (red for critical, orange for warnings, yellow for org issues)
- Detailed breakdown of issues, warnings, and missing scopes
- Actionable recommendations
- "Reconnect GitHub" and "Dismiss" buttons
- Responsive design with Tailwind CSS

#### 3. `App.tsx` Integration

- Automatically checks permissions after user sign-in
- Displays alert at the top of all authenticated routes
- Alert can be dismissed but persists across page refreshes until resolved
- Reconnect button redirects to GitHub OAuth flow

## Usage

### For Developers

#### Running the Migration

After pulling the code, run the database migration to add permission tracking fields:

```bash
cd backend
python add_permission_tracking_fields.py
```

#### Testing

Run backend tests:
```bash
cd backend
pytest tests/test_github_permissions.py -v
pytest tests/test_auth_permissions.py -v
```

Run frontend tests:
```bash
cd frontend
npm test PermissionAlert.test.tsx
```

### For Users

#### Normal Sign-In Flow

1. User clicks "Sign in with GitHub"
2. GitHub OAuth authorization page appears
3. User authorizes requested scopes
4. User is redirected back to Actions Manager
5. **Permission check runs automatically**
6. If permissions are valid: User proceeds normally
7. If permissions are invalid: Alert appears at top of screen

#### Fixing Permission Issues

**Missing Scopes:**
1. User sees alert: "Missing GitHub Permissions"
2. Alert lists missing scopes (e.g., "repo", "workflow")
3. User clicks "Reconnect GitHub"
4. GitHub OAuth page shows with full scope list
5. User authorizes all scopes
6. Permission check runs again and validates

**Repository Access Issues:**
1. User sees alert: "Limited Repository Access"
2. Alert explains which repos have restricted access
3. User ensures they have write access to needed repos
4. Permission check will validate on next sign-in

**Organization Restrictions:**
1. User sees warning: "Organization Access Restricted"
2. Alert explains third-party OAuth app approval needed
3. User contacts organization admin
4. Admin approves Actions Manager in organization settings
5. Permission check will validate on next sign-in

## Permission Status Codes

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| `valid` | All permissions present and valid | None |
| `missing_scopes` | OAuth scopes are missing | Re-authorize GitHub |
| `missing_repo_access` | Cannot access any repositories | Ensure repo access exists |
| `missing_org_approval` | Organization restricts third-party apps | Contact org admin |
| `insufficient_repo_permissions` | Have read but need write access | Request write access |
| `token_invalid` | GitHub token expired or revoked | Sign in again |
| `unknown_error` | Unexpected error during validation | Contact support |

## Edge Cases Handled

1. **Partial Scope Grant**: User grants some but not all requested scopes
   - System identifies specific missing scopes
   - User can still access app with limited functionality

2. **Read-Only Repository Access**: User has read but not write permissions
   - System detects write restrictions
   - Warning shown with affected repos

3. **Organization Third-Party App Restrictions**:
   - System detects 403 errors from org API calls
   - Provides clear instructions to request org admin approval

4. **Token Expiration**:
   - System detects 401 responses
   - Prompts user to re-authenticate

5. **Mixed Access Levels**:
   - User has access to some repos but not others
   - System shows which repos are accessible vs. restricted

## Security Considerations

- Access tokens are never exposed to frontend
- Tokens stored in memory only (not persisted)
- Permission checks use read-only validation (no modifications)
- Sensitive token data excluded from logs
- Database only stores status enum values, not token data

## Future Enhancements

Possible improvements:

1. **Periodic Re-validation**: Automatically recheck permissions every N hours
2. **Granular Feature Gating**: Disable specific features based on missing permissions
3. **Permission History**: Track permission changes over time
4. **Admin Dashboard**: Show permission status for all workspace users
5. **GitHub App Support**: Extend validation for GitHub App installations with fine-grained permissions

## Troubleshooting

### Backend

**Issue**: Permission check returns `unknown_error`

**Solution**: Check backend logs for detailed error messages. Common causes:
- GitHub API rate limiting
- Network connectivity issues
- Invalid token format

### Frontend

**Issue**: Permission alert doesn't dismiss

**Solution**: Check browser console for errors. Verify:
- API endpoint is reachable
- User exists in database
- Token exists in user_tokens dictionary

**Issue**: Alert shows even with valid permissions

**Solution**: Check:
- Backend validation logic for false positives
- OAuth scope header parsing
- Token expiration

## Related Files

- `backend/github_permissions.py` - Core validation logic
- `backend/auth.py` - Permission check endpoint
- `backend/models.py` - Account model with permission fields
- `backend/add_permission_tracking_fields.py` - Database migration
- `backend/tests/test_github_permissions.py` - Unit tests for validator
- `backend/tests/test_auth_permissions.py` - Integration tests for endpoint
- `frontend/src/api/user.ts` - API client functions
- `frontend/src/components/PermissionAlert.tsx` - Alert component
- `frontend/src/components/PermissionAlert.test.tsx` - Component tests
- `frontend/src/App.tsx` - Integration into main app

## Support

For issues or questions about the permission validation system:

1. Check this documentation first
2. Review backend logs for detailed error messages
3. Test with a fresh OAuth authorization
4. Open an issue on GitHub with:
   - Description of the problem
   - Permission status returned by `/api/user/{username}/permissions`
   - Browser console logs
   - Backend server logs
