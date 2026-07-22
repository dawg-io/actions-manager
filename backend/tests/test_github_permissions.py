"""
Tests for GitHub Permission Validation System

Tests the github_permissions module including:
- Permission requirement definitions
- OAuth scope validation
- Repository access checking
- Organization access checking
- Permission status determination
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from github_permissions import (
    GitHubPermissionValidator,
    PermissionStatus,
    REQUIRED_GITHUB_PERMISSIONS,
    TokenType,
    get_required_scopes,
    get_required_scopes_description,
    format_permission_issues_for_user,
)


class TestPermissionRequirements:
    """Test permission requirement definitions"""

    def test_required_permissions_defined(self):
        """Test that all required permissions are properly defined"""
        assert "repo" in REQUIRED_GITHUB_PERMISSIONS
        assert "workflow" in REQUIRED_GITHUB_PERMISSIONS
        assert "read:org" in REQUIRED_GITHUB_PERMISSIONS
        assert "user:email" in REQUIRED_GITHUB_PERMISSIONS

    def test_required_permissions_have_metadata(self):
        """Test that each permission has complete metadata"""
        for scope, perm in REQUIRED_GITHUB_PERMISSIONS.items():
            assert perm.scope == scope
            assert perm.description
            assert isinstance(perm.required_for, list)
            assert len(perm.required_for) > 0
            assert isinstance(perm.critical, bool)

    def test_critical_permissions_flagged(self):
        """Test that critical permissions are correctly marked"""
        # repo, workflow, user:email should be critical
        assert REQUIRED_GITHUB_PERMISSIONS["repo"].critical is True
        assert REQUIRED_GITHUB_PERMISSIONS["workflow"].critical is True
        assert REQUIRED_GITHUB_PERMISSIONS["user:email"].critical is True

    def test_get_required_scopes(self):
        """Test get_required_scopes returns correct scope list"""
        scopes = get_required_scopes()
        assert "repo" in scopes
        assert "workflow" in scopes
        assert "read:org" in scopes
        assert "user:email" in scopes

    def test_get_required_scopes_description(self):
        """Test get_required_scopes_description returns detailed info"""
        descriptions = get_required_scopes_description()
        assert "repo" in descriptions
        assert "description" in descriptions["repo"]
        assert "required_for" in descriptions["repo"]
        assert "critical" in descriptions["repo"]


class TestGitHubPermissionValidator:
    """Test GitHubPermissionValidator class"""

    @pytest.fixture
    def mock_validator(self):
        """Create a validator with a mock token"""
        return GitHubPermissionValidator("mock_access_token")

    def test_validator_initialization(self, mock_validator):
        """Test validator initializes with correct headers"""
        assert mock_validator.access_token == "mock_access_token"
        assert "Authorization" in mock_validator.headers
        assert mock_validator.headers["Authorization"] == "token mock_access_token"
        assert mock_validator.headers["Accept"] == "application/vnd.github+json"

    def test_detect_token_prefix_type(self):
        assert GitHubPermissionValidator("github_pat_123")._detect_token_prefix_type() == TokenType.FINE_GRAINED_PAT
        assert GitHubPermissionValidator("ghp_123")._detect_token_prefix_type() == TokenType.CLASSIC_PAT
        assert GitHubPermissionValidator("gho_123")._detect_token_prefix_type() == TokenType.OAUTH_TOKEN

    @patch("github_permissions.requests.get")
    def test_check_token_validity_valid(self, mock_get, mock_validator):
        """Test token validity check with valid token"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "login": "testuser",
            "type": "User"
        }
        mock_get.return_value = mock_response

        result = mock_validator._check_token_validity()

        assert result["valid"] is True
        assert result["username"] == "testuser"
        assert result["account_type"] == "User"

    @patch("github_permissions.requests.get")
    def test_check_token_validity_invalid(self, mock_get, mock_validator):
        """Test token validity check with invalid token"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = mock_validator._check_token_validity()

        assert result["valid"] is False
        assert "error" in result

    @patch("github_permissions.requests.get")
    def test_check_oauth_scopes_all_present(self, mock_get, mock_validator):
        """Test OAuth scope check when all required scopes are present"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "X-OAuth-Scopes": "repo, workflow, read:org, user:email, admin:org"
        }
        mock_get.return_value = mock_response

        result = mock_validator._check_oauth_scopes()

        assert result["has_all_required"] is True
        assert len(result["missing_scopes"]) == 0
        assert "repo" in result["granted_scopes"]
        assert "workflow" in result["granted_scopes"]

    @patch("github_permissions.requests.get")
    def test_check_oauth_scopes_missing(self, mock_get, mock_validator):
        """Test OAuth scope check when some required scopes are missing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            "X-OAuth-Scopes": "user:email"  # Missing repo, workflow, read:org
        }
        mock_get.return_value = mock_response

        result = mock_validator._check_oauth_scopes()

        assert result["has_all_required"] is False
        assert len(result["missing_scopes"]) > 0
        assert "repo" in result["missing_scopes"]
        assert "workflow" in result["missing_scopes"]

    @patch("github_permissions.requests.get")
    def test_check_repository_access_has_access(self, mock_get, mock_validator):
        """Test repository access check with accessible repos"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "full_name": "user/repo1",
                "permissions": {"push": True}
            },
            {
                "full_name": "user/repo2",
                "permissions": {"push": True}
            }
        ]
        mock_get.return_value = mock_response

        result = mock_validator._check_repository_access()

        assert result["has_repo_access"] is True
        assert result["total_repos"] == 2
        assert len(result["accessible_repos"]) > 0

    @patch("github_permissions.requests.get")
    def test_check_repository_access_no_access(self, mock_get, mock_validator):
        """Test repository access check with no accessible repos"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        result = mock_validator._check_repository_access()

        assert result["has_repo_access"] is False
        assert result["total_repos"] == 0

    @patch("github_permissions.requests.get")
    def test_check_repository_access_limited_write(self, mock_get, mock_validator):
        """Test repository access check with limited write permissions"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "full_name": "user/repo1",
                "permissions": {"push": True}
            },
            {
                "full_name": "user/repo2",
                "permissions": {"push": False}  # Read-only
            }
        ]
        mock_get.return_value = mock_response

        result = mock_validator._check_repository_access()

        assert result["has_repo_access"] is True
        assert result["has_write_restrictions"] is True
        assert "user/repo2" in result["limited_repos"]

    @patch("github_permissions.requests.get")
    def test_check_organization_access_with_orgs(self, mock_get, mock_validator):
        """Test organization access check with accessible orgs"""
        def mock_get_side_effect(url, *args, **kwargs):
            response = Mock()
            if "/user/orgs" in url:
                response.status_code = 200
                response.json.return_value = [
                    {"login": "org1"},
                    {"login": "org2"}
                ]
            elif "/orgs/org1/repos" in url:
                response.status_code = 200
                response.json.return_value = [{"name": "repo1"}]
            elif "/orgs/org2/repos" in url:
                response.status_code = 403  # Restricted
                response.json.return_value = {}
            return response

        mock_get.side_effect = mock_get_side_effect

        result = mock_validator._check_organization_access()

        assert result["has_orgs"] is True
        assert "org1" in result["accessible_orgs"]
        assert "org2" in result["restricted_orgs"]
        assert result["has_org_restrictions"] is True

    @patch("github_permissions.requests.get")
    def test_check_organization_access_no_orgs(self, mock_get, mock_validator):
        """Test organization access check with no orgs"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        result = mock_validator._check_organization_access()

        assert result["has_orgs"] is False
        assert result["has_org_restrictions"] is False

    @patch.object(GitHubPermissionValidator, "_detect_token_type")
    @patch.object(GitHubPermissionValidator, "_check_oauth_scopes")
    @patch.object(GitHubPermissionValidator, "_check_repository_access")
    @patch.object(GitHubPermissionValidator, "_check_organization_access")
    def test_validate_all_permissions_valid(
        self, mock_org, mock_repo, mock_scopes, mock_token, mock_validator
    ):
        """Test complete validation with all permissions valid"""
        mock_token.return_value = {"is_github_app": False, "token_valid": True, "user_data": {"login": "testuser"}}
        mock_scopes.return_value = {
            "granted_scopes": ["repo", "workflow", "read:org", "user:email"],
            "missing_scopes": [],
            "has_all_required": True
        }
        mock_repo.return_value = {
            "has_repo_access": True,
            "total_repos": 5,
            "has_write_restrictions": False,
            "limited_repos": []
        }
        mock_org.return_value = {
            "has_orgs": True,
            "has_org_restrictions": False,
            "restricted_orgs": []
        }

        result = mock_validator.validate_all_permissions()

        assert result["status"] == PermissionStatus.VALID
        assert result["valid"] is True
        assert len(result["issues"]) == 0

    @patch.object(GitHubPermissionValidator, "_detect_token_type")
    def test_validate_all_permissions_invalid_token(self, mock_token, mock_validator):
        """Test complete validation with invalid token"""
        mock_token.return_value = {"is_github_app": False, "token_valid": False}

        result = mock_validator.validate_all_permissions()

        assert result["status"] == PermissionStatus.TOKEN_INVALID
        assert result["valid"] is False
        assert len(result["issues"]) > 0
        assert len(result["recommendations"]) > 0

    @patch.object(GitHubPermissionValidator, "_detect_token_type")
    @patch.object(GitHubPermissionValidator, "_check_oauth_scopes")
    @patch.object(GitHubPermissionValidator, "_check_repository_access")
    @patch.object(GitHubPermissionValidator, "_check_organization_access")
    def test_validate_all_permissions_missing_scopes(
        self, mock_org, mock_repo, mock_scopes, mock_token, mock_validator
    ):
        """Test complete validation with missing scopes"""
        mock_token.return_value = {"is_github_app": False, "token_valid": True}
        mock_scopes.return_value = {
            "granted_scopes": ["user:email"],
            "missing_scopes": ["repo", "workflow"],
            "has_all_required": False
        }
        mock_repo.return_value = {"has_repo_access": False}
        mock_org.return_value = {"has_orgs": False, "has_org_restrictions": False}

        result = mock_validator.validate_all_permissions()

        assert result["status"] == PermissionStatus.MISSING_SCOPES
        assert result["valid"] is False
        assert "repo" in result["missing_scopes"]
        assert "workflow" in result["missing_scopes"]
        assert len(result["recommendations"]) > 0

    @patch.object(GitHubPermissionValidator, "_detect_token_type")
    @patch.object(GitHubPermissionValidator, "_check_repository_access")
    @patch.object(GitHubPermissionValidator, "_check_organization_access")
    def test_validate_all_permissions_fine_grained_pat(
        self, mock_org, mock_repo, mock_token
    ):
        validator = GitHubPermissionValidator("github_pat_123")
        mock_token.return_value = {
            "is_github_app": False,
            "token_valid": True,
            "token_type": TokenType.FINE_GRAINED_PAT,
        }
        mock_repo.return_value = {
            "has_repo_access": True,
            "total_repos": 2,
            "has_write_restrictions": False,
            "limited_repos": [],
        }
        mock_org.return_value = {"has_orgs": False, "has_org_restrictions": False}

        result = validator.validate_all_permissions()

        assert result["valid"] is True
        assert result["details"]["auth_type"] == "personal_access_token"
        assert result["details"]["token_type"] == TokenType.FINE_GRAINED_PAT
        assert result["details"]["scopes"]["note"].startswith("Fine-grained personal access tokens")

    @patch("github_permissions.requests.get")
    def test_check_repository_access_handles_org_policy_block(self, mock_get, mock_validator):
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "message": "Resource not accessible by personal access token for this organization"
        }
        mock_get.return_value = mock_response

        result = mock_validator._check_repository_access()

        assert result["has_repo_access"] is False
        assert "Organization access is blocked" in result["error"]

    @patch.object(GitHubPermissionValidator, "_detect_token_type")
    @patch.object(GitHubPermissionValidator, "_check_github_app_permissions")
    @patch.object(GitHubPermissionValidator, "_check_repository_access")
    def test_validate_all_permissions_github_app_valid(
        self, mock_repo, mock_app_perms, mock_token, mock_validator
    ):
        """Test complete validation with valid GitHub App token"""
        mock_token.return_value = {"is_github_app": True, "token_valid": True}
        mock_app_perms.return_value = {
            "has_required_permissions": True,
            "installation_id": 12345,
            "permissions": {
                "contents": "write",
                "workflows": "write",
                "pull_requests": "write",
                "metadata": "read"
            },
            "missing_permissions": [],
            "optional_missing": []
        }
        mock_repo.return_value = {
            "has_repo_access": True,
            "total_repos": 5,
            "has_write_restrictions": False,
            "limited_repos": []
        }

        result = mock_validator.validate_all_permissions()

        assert result["status"] == PermissionStatus.VALID
        assert result["valid"] is True
        assert result["details"]["auth_type"] == "github_app"
        assert len(result["issues"]) == 0

    @patch.object(GitHubPermissionValidator, "_detect_token_type")
    @patch.object(GitHubPermissionValidator, "_check_github_app_permissions")
    @patch.object(GitHubPermissionValidator, "_check_repository_access")
    def test_validate_all_permissions_github_app_missing_perms(
        self, mock_repo, mock_app_perms, mock_token, mock_validator
    ):
        """Test complete validation with GitHub App token missing permissions"""
        mock_token.return_value = {"is_github_app": True, "token_valid": True}
        mock_app_perms.return_value = {
            "has_required_permissions": False,
            "installation_id": 12345,
            "permissions": {
                "contents": "read",
                "metadata": "read"
            },
            "missing_permissions": [
                "workflows (needs write or admin, has none)",
                "pull_requests (needs write or admin, has none)"
            ],
            "optional_missing": ["secrets (recommended: write or admin, has none)"]
        }
        mock_repo.return_value = {
            "has_repo_access": True,
            "total_repos": 5,
            "has_write_restrictions": False,
            "limited_repos": []
        }

        result = mock_validator.validate_all_permissions()

        assert result["status"] == PermissionStatus.MISSING_SCOPES
        assert result["valid"] is False
        assert result["details"]["auth_type"] == "github_app"
        assert len(result["issues"]) > 0
        assert "missing required permissions" in result["issues"][0].lower()
        assert len(result["warnings"]) > 0  # Optional permissions warning


class TestFormatPermissionIssues:
    """Test permission issue formatting"""

    def test_format_valid_permissions(self):
        """Test formatting message for valid permissions"""
        validation_result = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "missing_scopes": [],
            "recommendations": []
        }

        message = format_permission_issues_for_user(validation_result)

        assert "✅" in message
        assert "correctly configured" in message.lower()

    def test_format_valid_personal_access_token(self):
        validation_result = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "missing_scopes": [],
            "recommendations": [],
            "details": {
                "auth_type": "personal_access_token",
                "token_type": TokenType.FINE_GRAINED_PAT,
            }
        }

        message = format_permission_issues_for_user(validation_result)

        assert "Fine-grained personal access token" in message

    def test_format_missing_scopes(self):
        """Test formatting message for missing scopes"""
        validation_result = {
            "valid": False,
            "issues": ["Missing critical GitHub permissions: repo, workflow"],
            "warnings": [],
            "missing_scopes": ["repo", "workflow"],
            "recommendations": ["Sign out and sign in again"],
        }

        message = format_permission_issues_for_user(validation_result)

        assert "Issues Found" in message
        assert "repo" in message
        assert "workflow" in message
        assert "How to Fix" in message

    def test_format_with_warnings(self):
        """Test formatting message with warnings"""
        validation_result = {
            "valid": False,
            "issues": [],
            "warnings": ["Organization restrictions detected"],
            "missing_scopes": [],
            "recommendations": ["Contact your organization admin"],
        }

        message = format_permission_issues_for_user(validation_result)

        assert "Warnings" in message
        assert "Organization restrictions" in message

    def test_format_with_affected_functionality(self):
        """Test formatting message shows affected functionality"""
        validation_result = {
            "valid": False,
            "issues": ["Missing permissions"],
            "warnings": [],
            "missing_scopes": ["repo"],
            "recommendations": ["Re-authorize"],
        }

        message = format_permission_issues_for_user(validation_result)

        assert "Affected Functionality" in message
        assert "repo" in message
