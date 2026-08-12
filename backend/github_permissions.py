"""
GitHub Permission Management Module for ActionsManager

This module defines and validates GitHub OAuth scopes and permissions required
for the application to function correctly. It provides:

1. A single source of truth for required GitHub permissions
2. Permission validation logic to check if a GitHub token has required scopes
3. Detailed permission status reporting for frontend consumption
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import requests

GITHUB_USER_API_URL = "https://api.github.com/user"


class PermissionStatus(str, Enum):
    """Permission validation status codes"""
    VALID = "valid"
    MISSING_SCOPES = "missing_scopes"
    MISSING_REPO_ACCESS = "missing_repo_access"
    MISSING_ORG_APPROVAL = "missing_org_approval"
    INSUFFICIENT_REPO_PERMISSIONS = "insufficient_repo_permissions"
    TOKEN_INVALID = "token_invalid"
    UNKNOWN_ERROR = "unknown_error"


class CredentialSource(str, Enum):
    OAUTH = "oauth"
    PERSONAL_ACCESS_TOKEN = "personal_access_token"
    GITHUB_APP = "github_app"


class TokenType(str, Enum):
    OAUTH_TOKEN = "oauth_token"
    CLASSIC_PAT = "classic_pat"
    FINE_GRAINED_PAT = "fine_grained_pat"
    GITHUB_APP_USER = "github_app_user"
    GITHUB_APP_INSTALLATION = "github_app_installation"
    UNKNOWN = "unknown"


@dataclass
class PermissionRequirement:
    """Defines a required GitHub permission with metadata"""
    scope: str
    description: str
    required_for: List[str]
    critical: bool = True  # If False, app can function with degraded capabilities


# Single source of truth for all required GitHub permissions
REQUIRED_GITHUB_PERMISSIONS = {
    "repo": PermissionRequirement(
        scope="repo",
        description="Full control of private repositories",
        required_for=[
            "Reading repository information",
            "Reading and writing workflow files",
            "Creating and managing branches",
            "Creating and managing pull requests",
            "Reading and writing repository contents",
            "Managing deployment environments",
            "Managing repository secrets",
            "Managing repository variables",
            "Managing repository rulesets",
            "Accessing private repositories"
        ],
        critical=True
    ),
    "workflow": PermissionRequirement(
        scope="workflow",
        description="Update GitHub Action workflows",
        required_for=[
            "Creating workflow files",
            "Updating workflow files",
            "Managing workflow configurations",
            "Triggering workflows"
        ],
        critical=True
    ),
    "read:org": PermissionRequirement(
        scope="read:org",
        description="Read org and team membership, read org projects",
        required_for=[
            "Accessing organization repositories",
            "Reading organization information",
            "Listing organization repositories",
            "Checking organization membership"
        ],
        critical=False  # Users without orgs can still use the app
    ),
    "user:email": PermissionRequirement(
        scope="user:email",
        description="Access user email addresses (read-only)",
        required_for=[
            "Reading user email for account creation",
            "User identification"
        ],
        critical=True
    ),
}


# Fine-grained repository permissions needed (for GitHub Apps in future)
REQUIRED_REPO_PERMISSIONS = {
    "contents": "write",  # Read/write repository contents
    "workflows": "write",  # Read/write workflows
    "pull_requests": "write",  # Create and manage PRs
    "metadata": "read",  # Read repository metadata
    "environments": "write",  # Manage deployment environments
    "secrets": "write",  # Manage repository secrets
    "variables": "write",  # Manage repository variables
    "administration": "write",  # Manage repository rulesets (admin permission)
}


class GitHubPermissionValidator:
    """Validates GitHub token permissions and access levels"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        self.is_github_app = None  # Will be determined during validation
        self.token_type = TokenType.UNKNOWN

    def _detect_token_prefix_type(self) -> TokenType:
        if self.access_token.startswith("github_pat_"):
            return TokenType.FINE_GRAINED_PAT
        if self.access_token.startswith("ghp_"):
            return TokenType.CLASSIC_PAT
        if self.access_token.startswith("gho_"):
            return TokenType.OAUTH_TOKEN
        if self.access_token.startswith("ghu_"):
            return TokenType.GITHUB_APP_USER
        if self.access_token.startswith("ghs_"):
            return TokenType.GITHUB_APP_INSTALLATION
        return TokenType.UNKNOWN

    def _detect_token_type(self) -> Dict:
        """
        Detect if the token is from a traditional OAuth App or a GitHub App.

        GitHub token prefixes (most reliable detection):
        - ghu_ = GitHub App user access token (user-to-server OAuth)
        - ghs_ = GitHub App installation token (server-to-server)
        - gho_ = Traditional OAuth App user access token
        - ghp_ = Personal access token (classic)
        - github_pat_ = Fine-grained personal access token

        GitHub App user tokens (ghu_) DO have X-OAuth-Scopes but with minimal/empty
        user-level permissions — NOT traditional scopes like repo or workflow.
        These must not be validated against OAuth scope requirements.

        Returns dict with:
        - is_github_app: boolean
        - token_valid: boolean
        - user_data: dict (if token valid)
        """
        # Determine GitHub App status from token prefix before making any API call
        # This is the most reliable method since it doesn't depend on response headers
        detected_type = self._detect_token_prefix_type()
        self.token_type = detected_type

        prefix_is_github_app: Optional[bool] = None
        if detected_type in {TokenType.GITHUB_APP_USER, TokenType.GITHUB_APP_INSTALLATION}:
            prefix_is_github_app = True
        elif detected_type in {TokenType.OAUTH_TOKEN, TokenType.CLASSIC_PAT, TokenType.FINE_GRAINED_PAT}:
            prefix_is_github_app = False

        try:
            response = requests.get(
                GITHUB_USER_API_URL,
                headers=self.headers,
                timeout=10
            )

            if response.status_code != 200:
                return {"is_github_app": False, "token_valid": False}

            user_data = response.json()

            if prefix_is_github_app is not None:
                # Prefix-based detection is definitive — use it directly
                return {
                    "is_github_app": prefix_is_github_app,
                    "token_valid": True,
                    "user_data": user_data,
                    "token_type": self.token_type,
                }

            # Fallback for older/classic tokens without a modern prefix:
            # Check the X-OAuth-Scopes header.
            # - Absent header → GitHub App installation token
            # - Header present but lacks traditional scopes (repo/workflow) → GitHub App user token
            # - Header present with repo/workflow scopes → traditional OAuth App token
            oauth_scopes_header = response.headers.get("X-OAuth-Scopes")

            if oauth_scopes_header is None:
                is_github_app = True
            else:
                granted_scopes = {s.strip() for s in oauth_scopes_header.split(",") if s.strip()}
                # Traditional OAuth Apps always request 'repo' and/or 'workflow'.
                # GitHub App user tokens only have user-level permissions (e.g. user:email).
                has_traditional_scopes = bool(granted_scopes & {"repo", "public_repo", "workflow"})
                is_github_app = not has_traditional_scopes

            return {
                "is_github_app": is_github_app,
                "token_valid": True,
                "user_data": user_data,
                "token_type": self.token_type,
            }
        except Exception as e:
            return {
                "is_github_app": False,
                "token_valid": False,
                "error": str(e),
                "token_type": self.token_type,
            }

    def _apply_token_type_check(self, result: Dict) -> bool:
        """Step 1: detect token type, validate the token, populate auth_type details. Returns False if the token is invalid (result is already terminal)."""
        token_type_check = self._detect_token_type()
        if not token_type_check["token_valid"]:
            result["status"] = PermissionStatus.TOKEN_INVALID
            result["valid"] = False
            result["issues"].append("GitHub access token is invalid or expired")
            result["recommendations"].append("Please sign out and sign in again to re-authenticate with GitHub")
            return False

        self.is_github_app = token_type_check["is_github_app"]
        self.token_type = token_type_check.get("token_type", self.token_type)
        if self.is_github_app:
            result["details"]["auth_type"] = CredentialSource.GITHUB_APP
        elif self.token_type in {TokenType.CLASSIC_PAT, TokenType.FINE_GRAINED_PAT}:
            result["details"]["auth_type"] = CredentialSource.PERSONAL_ACCESS_TOKEN
        else:
            result["details"]["auth_type"] = CredentialSource.OAUTH
        result["details"]["token_type"] = self.token_type
        return True

    def _apply_oauth_scope_check(self, result: Dict) -> None:
        scope_check = self._check_oauth_scopes()
        result["granted_scopes"] = scope_check["granted_scopes"]
        result["missing_scopes"] = scope_check["missing_scopes"]
        result["details"]["scopes"] = scope_check

        if not scope_check["missing_scopes"]:
            return

        # Categorize missing scopes — only hard-fail for critical ones
        critical_missing = [
            scope for scope in scope_check["missing_scopes"]
            if REQUIRED_GITHUB_PERMISSIONS.get(scope, PermissionRequirement(scope="", description="", required_for=[], critical=True)).critical
        ]
        optional_missing = [s for s in scope_check["missing_scopes"] if s not in critical_missing]

        if critical_missing:
            result["status"] = PermissionStatus.MISSING_SCOPES
            result["valid"] = False
            result["issues"].append(
                f"Missing critical GitHub permissions: {', '.join(critical_missing)}"
            )
            result["recommendations"].append(
                "Sign out and sign in again. When GitHub asks for permissions, make sure to authorize all requested scopes."
            )

        if optional_missing:
            result["warnings"].append(
                f"Missing optional GitHub permissions: {', '.join(optional_missing)}"
            )
            result["recommendations"].append(
                "Some features may be limited. For full functionality, re-authorize the application with all scopes."
            )

    def _apply_github_app_permission_check(self, result: Dict) -> None:
        app_permissions_check = self._check_github_app_permissions()
        result["details"]["app_permissions"] = app_permissions_check

        if not app_permissions_check.get("has_required_permissions", True):
            result["status"] = PermissionStatus.MISSING_SCOPES
            result["valid"] = False

            missing_perms = app_permissions_check.get("missing_permissions", [])
            if missing_perms:
                result["issues"].append(
                    f"GitHub App installation is missing required permissions: {', '.join(missing_perms)}"
                )
            else:
                result["issues"].append("GitHub App installation is missing required permissions")

            result["recommendations"].append(
                "The GitHub App needs to be configured with additional permissions. Contact your administrator to update the app installation."
            )

        optional_missing = app_permissions_check.get("optional_missing", [])
        if optional_missing:
            result["warnings"].append(
                f"GitHub App is missing optional permissions: {', '.join(optional_missing[:3])}"
            )
            result["recommendations"].append(
                "For full functionality, consider granting the app additional optional permissions."
            )

    def _apply_scope_check(self, result: Dict) -> None:
        """Step 2: OAuth scopes, fine-grained PAT, or GitHub App installation permissions — branched by token type.

        GitHub App tokens don't use OAuth scopes, they use installation permissions.
        """
        if not self.is_github_app and self.token_type != TokenType.FINE_GRAINED_PAT:
            self._apply_oauth_scope_check(result)
        elif self.token_type == TokenType.FINE_GRAINED_PAT:
            result["details"]["scopes"] = {
                "granted_scopes": [],
                "missing_scopes": [],
                "has_all_required": True,
                "note": "Fine-grained personal access tokens use repository permissions instead of OAuth scopes.",
            }
            result["recommendations"].append(
                "Fine-grained personal access tokens should include Metadata: read plus Contents and Actions: read/write. Add Pull requests, Secrets, Variables, or Administration only for features you use."
            )
        else:
            self._apply_github_app_permission_check(result)

    def _apply_repository_access_check(self, result: Dict) -> None:
        """Step 3: repository access.

        GitHub App repo access is managed by the installation, not the user token.
        A GitHub App user token (ghu_) does not carry the 'repo' OAuth scope, so
        /user/repos will return an empty list even when the app has full repo access.
        Showing "Cannot access repos" in this case is a false positive — skip it.
        """
        if self.is_github_app:
            result["details"]["repository_access"] = {
                "has_repo_access": True,
                "note": "Repository access is managed by the GitHub App installation"
            }
            return

        repo_check = self._check_repository_access()
        result["details"]["repository_access"] = repo_check

        if not repo_check["has_repo_access"]:
            result["valid"] = False
            if result["status"] == PermissionStatus.VALID:
                result["status"] = PermissionStatus.MISSING_REPO_ACCESS
            repo_error = repo_check.get("error", "")
            if "organization access is blocked" in repo_error.lower():
                result["status"] = PermissionStatus.MISSING_ORG_APPROVAL
                result["issues"].append("Organization policies are blocking this token from accessing repositories")
                result["recommendations"].append(
                    "Ask an organization administrator to allow this token or create a token that is approved for the target organization."
                )
            else:
                result["issues"].append("Cannot access any repositories")
                result["recommendations"].append(
                    "Ensure you have at least one repository that Actions Manager can access"
                )
        elif repo_check.get("has_write_restrictions"):
            if result["status"] == PermissionStatus.VALID:
                result["status"] = PermissionStatus.INSUFFICIENT_REPO_PERMISSIONS
                result["valid"] = False
            result["issues"].append(
                f"Limited write access to some repositories: {', '.join(repo_check['limited_repos'][:5])}"
            )
            result["recommendations"].append(
                "Write access is required for full repository management features. Grant write permissions to the affected repositories."
            )

    def _apply_organization_access_check(self, result: Dict) -> None:
        """Step 4: organization access (skip for GitHub App tokens - they handle this differently)."""
        if self.is_github_app:
            return

        org_check = self._check_organization_access()
        result["details"]["organization_access"] = org_check

        if org_check["has_org_restrictions"]:
            if result["status"] == PermissionStatus.VALID:
                result["status"] = PermissionStatus.MISSING_ORG_APPROVAL
                result["valid"] = False
            result["issues"].append(
                f"Organization access restricted for: {', '.join(org_check['restricted_orgs'][:3])}"
            )
            result["recommendations"].append(
                "Some organization repositories may be restricted. Contact your organization admin to approve Actions Manager as a third-party OAuth app."
            )

    def validate_all_permissions(self) -> Dict:
        """
        Comprehensive permission validation.

        Returns a dictionary with:
        - status: PermissionStatus enum value
        - valid: boolean
        - missing_scopes: list of missing OAuth scopes
        - granted_scopes: list of granted OAuth scopes
        - issues: list of human-readable issue descriptions
        - warnings: list of non-critical warnings
        - recommendations: list of actionable recommendations for the user
        """
        result = {
            "status": PermissionStatus.VALID,
            "valid": True,
            "missing_scopes": [],
            "granted_scopes": [],
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "details": {}
        }

        if not self._apply_token_type_check(result):
            return result

        self._apply_scope_check(result)
        self._apply_repository_access_check(result)
        self._apply_organization_access_check(result)

        return result

    def _check_token_validity(self) -> Dict:
        """Check if the GitHub token is valid"""
        try:
            response = requests.get(
                GITHUB_USER_API_URL,
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                user_data = response.json()
                return {
                    "valid": True,
                    "username": user_data.get("login"),
                    "account_type": user_data.get("type", "User")
                }
            elif response.status_code == 401:
                return {"valid": False, "error": "Token is invalid or expired"}
            else:
                return {"valid": False, "error": f"Unexpected status code: {response.status_code}"}
        except Exception as e:
            return {"valid": False, "error": f"Error checking token: {str(e)}"}

    def _check_oauth_scopes(self) -> Dict:
        """
        Check which OAuth scopes are granted to the token.

        GitHub returns granted scopes in the X-OAuth-Scopes response header.
        """
        try:
            response = requests.get(
                GITHUB_USER_API_URL,
                headers=self.headers,
                timeout=10
            )

            # GitHub returns granted scopes in X-OAuth-Scopes header
            granted_scopes_header = response.headers.get("X-OAuth-Scopes", "")
            granted_scopes = [s.strip() for s in granted_scopes_header.split(",") if s.strip()]

            # Check which required scopes are missing
            required_scope_names = set(REQUIRED_GITHUB_PERMISSIONS.keys())
            granted_scope_set = set(granted_scopes)

            # Handle scope hierarchies (repo includes repo:status, public_repo, etc.)
            # If 'repo' is granted, it includes all repo:* scopes
            if "repo" in granted_scope_set:
                granted_scope_set.update(["public_repo", "repo:status", "repo_deployment"])



            missing_scopes = list(required_scope_names - granted_scope_set)

            return {
                "granted_scopes": granted_scopes,
                "missing_scopes": missing_scopes,
                "has_all_required": len(missing_scopes) == 0
            }
        except Exception as e:
            return {
                "granted_scopes": [],
                "missing_scopes": list(REQUIRED_GITHUB_PERMISSIONS.keys()),
                "has_all_required": False,
                "error": str(e)
            }

    def _check_repository_access(self) -> Dict:
        """
        Check repository access levels.

        Attempts to:
        1. List accessible repositories
        2. Check write permissions on a sample of repositories
        """
        try:
            # Try to list repositories (limited to first 30 for performance)
            response = requests.get(
                "https://api.github.com/user/repos",
                headers=self.headers,
                params={"per_page": 30, "affiliation": "owner,collaborator,organization_member"},
                timeout=10
            )

            if response.status_code == 403:
                message = ""
                try:
                    message = (response.json() or {}).get("message", "")
                except Exception:
                    message = ""
                if "organization" in message.lower() and "access" in message.lower():
                    return {
                        "has_repo_access": False,
                        "accessible_repos": [],
                        "error": "Organization access is blocked for this token"
                    }
            if response.status_code != 200:
                return {
                    "has_repo_access": False,
                    "accessible_repos": [],
                    "error": f"Cannot list repositories: {response.status_code}"
                }

            repos = response.json()

            if not repos:
                return {
                    "has_repo_access": False,
                    "accessible_repos": [],
                    "total_repos": 0
                }

            # Check write permissions
            limited_repos = []
            for repo in repos[:10]:  # Check first 10 repos for performance
                if not repo.get("permissions", {}).get("push", False):
                    limited_repos.append(repo["full_name"])

            return {
                "has_repo_access": True,
                "total_repos": len(repos),
                "accessible_repos": [r["full_name"] for r in repos[:5]],
                "has_write_restrictions": len(limited_repos) > 0,
                "limited_repos": limited_repos
            }
        except Exception as e:
            return {
                "has_repo_access": False,
                "accessible_repos": [],
                "error": str(e)
            }

    def _check_github_app_permissions(self) -> Dict:
        """
        Check GitHub App installation permissions.

        GitHub App tokens use installation permissions (not OAuth scopes).
        For GitHub App tokens, we take a permissive approach - if the token works
        to access the /user endpoint (already verified), we assume permissions are OK.

        This is because GitHub App tokens are pre-configured with specific permissions
        at installation time, and if the user can authenticate, the app admin has
        already granted the necessary permissions.

        Returns dict with:
        - has_required_permissions: boolean
        - installation_id: int or None
        - permissions: dict of permission levels
        - missing_permissions: list of missing permissions
        """
        try:
            # For GitHub App tokens, we use a permissive validation approach
            # If the token authenticated successfully (which we already verified in _detect_token_type),
            # then we assume the GitHub App has been configured with appropriate permissions.

            # The reason: GitHub App permissions are managed at the organization/installation level
            # by administrators, not by individual users. If a user can authenticate via the app,
            # the app has been installed with specific permissions already.

            # Try to verify we can access repositories as a sanity check
            repos_response = requests.get(
                "https://api.github.com/user/repos",
                headers=self.headers,
                params={"per_page": 1, "affiliation": "owner,collaborator,organization_member"},
                timeout=10
            )

            # If we can access repos, we're good
            if repos_response.status_code == 200:
                repos_data = repos_response.json()
                repo_count = len(repos_data) if isinstance(repos_data, list) else 0

                return {
                    "has_required_permissions": True,
                    "installation_id": None,
                    "permissions": {
                        "status": "verified_via_authentication",
                        "repos_accessible": repo_count
                    },
                    "missing_permissions": [],
                    "optional_missing": [],
                    "app_name": "github_app",
                    "target_type": "installation"
                }

            # Even if we can't list repos, if the token authenticated, assume it's OK
            # This handles cases where the app might not have repo list permission
            # but has other necessary permissions
            return {
                "has_required_permissions": True,
                "installation_id": None,
                "permissions": {
                    "status": "verified_via_authentication",
                    "note": "Token authenticated successfully, assuming permissions are configured correctly"
                },
                "missing_permissions": [],
                "optional_missing": [],
                "app_name": "github_app",
                "target_type": "installation"
            }

        except Exception:
            # Even on exception, be permissive for GitHub App tokens
            # The app admin controls permissions, not individual users
            return {
                "has_required_permissions": True,
                "installation_id": None,
                "permissions": {
                    "status": "assumed_valid",
                    "note": "GitHub App permissions are managed by installation admin"
                },
                "missing_permissions": [],
                "optional_missing": [],
                "app_name": "github_app",
                "target_type": "installation"
            }

    def _check_organization_access(self) -> Dict:
        """
        Check access to organization repositories.

        Detects if there are organization repositories with restricted access
        due to OAuth app restrictions.
        """
        try:
            # List user's organizations
            response = requests.get(
                "https://api.github.com/user/orgs",
                headers=self.headers,
                timeout=10
            )

            if response.status_code != 200:
                return {
                    "has_orgs": False,
                    "organizations": [],
                    "has_org_restrictions": False
                }

            orgs = response.json()

            if not orgs:
                return {
                    "has_orgs": False,
                    "organizations": [],
                    "has_org_restrictions": False
                }

            # For each org, check if we can list their repos
            restricted_orgs = []
            accessible_orgs = []

            for org in orgs[:5]:  # Check first 5 orgs for performance
                org_login = org["login"]
                org_repos_response = requests.get(
                    f"https://api.github.com/orgs/{org_login}/repos",
                    headers=self.headers,
                    params={"per_page": 1},
                    timeout=10
                )

                if org_repos_response.status_code == 200:
                    accessible_orgs.append(org_login)
                elif org_repos_response.status_code == 403:
                    # 403 may indicate OAuth app restrictions
                    restricted_orgs.append(org_login)

            return {
                "has_orgs": True,
                "organizations": [o["login"] for o in orgs],
                "accessible_orgs": accessible_orgs,
                "restricted_orgs": restricted_orgs,
                "has_org_restrictions": len(restricted_orgs) > 0
            }
        except Exception as e:
            return {
                "has_orgs": False,
                "organizations": [],
                "has_org_restrictions": False,
                "error": str(e)
            }


def get_required_scopes() -> List[str]:
    """Get list of required OAuth scope strings"""
    return list(REQUIRED_GITHUB_PERMISSIONS.keys())


def get_required_scopes_description() -> Dict[str, Dict]:
    """Get detailed descriptions of all required scopes"""
    return {
        scope: {
            "description": perm.description,
            "required_for": perm.required_for,
            "critical": perm.critical
        }
        for scope, perm in REQUIRED_GITHUB_PERMISSIONS.items()
    }


def _valid_permission_message(auth_type: Optional[str], token_type: Optional[str]) -> str:
    if auth_type == CredentialSource.PERSONAL_ACCESS_TOKEN:
        if token_type == TokenType.FINE_GRAINED_PAT:
            return "✅ Fine-grained personal access token validated successfully."
        return "✅ Personal access token validated successfully."
    return "✅ All GitHub permissions are correctly configured."


def _append_issues_section(messages: List[str], validation_result: Dict) -> None:
    if not validation_result["issues"]:
        return
    messages.append("**Issues Found:**")
    for issue in validation_result["issues"]:
        messages.append(f"• {issue}")
    messages.append("")


def _append_warnings_section(messages: List[str], validation_result: Dict) -> None:
    if not validation_result["warnings"]:
        return
    messages.append("**Warnings:**")
    for warning in validation_result["warnings"]:
        messages.append(f"• {warning}")
    messages.append("")


def _append_affected_functionality_section(messages: List[str], validation_result: Dict) -> None:
    if not validation_result["missing_scopes"]:
        return
    messages.append("**Affected Functionality:**")
    for scope in validation_result["missing_scopes"]:
        perm = REQUIRED_GITHUB_PERMISSIONS.get(scope)
        if perm:
            messages.append(f"• **{scope}**: {', '.join(perm.required_for[:3])}")
    messages.append("")


def _append_recommendations_section(messages: List[str], validation_result: Dict) -> None:
    if not validation_result["recommendations"]:
        return
    messages.append("**How to Fix:**")
    for i, rec in enumerate(validation_result["recommendations"], 1):
        messages.append(f"{i}. {rec}")


def format_permission_issues_for_user(validation_result: Dict) -> str:
    """
    Format permission validation results into user-friendly message.

    Returns a formatted string explaining permission issues and how to fix them.
    """
    details = validation_result.get("details", {})

    if validation_result["valid"]:
        return _valid_permission_message(details.get("auth_type"), details.get("token_type"))

    messages: List[str] = []
    _append_issues_section(messages, validation_result)
    _append_warnings_section(messages, validation_result)
    _append_affected_functionality_section(messages, validation_result)
    _append_recommendations_section(messages, validation_result)

    return "\n".join(messages)
