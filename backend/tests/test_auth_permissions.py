"""
Tests for GitHub Permission Validation in Auth Module

Tests the permission check endpoint added to auth.py
"""

import pytest
import auth
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from main import app
from models import Account, WorkspaceMember
from github_permissions import PermissionStatus
from tests.conftest import TestingSessionLocal


client = TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def auth_permissions_isolation():
    original_factory = app.state.middleware_db_factory
    context_token = auth.set_request_user(None)
    app.state.middleware_db_factory = TestingSessionLocal
    auth.user_tokens.clear()
    auth.user_tokens._pat_cache.clear()
    yield
    auth.user_tokens.clear()
    auth.user_tokens._pat_cache.clear()
    app.state.middleware_db_factory = original_factory
    auth.reset_request_user(context_token)


def auth_headers(user, extra_headers=None):
    headers = {"Authorization": "Bearer " + user.session_token}
    if extra_headers:
        headers.update(extra_headers)
    return headers


@pytest.fixture
def test_user(test_db):
    """Create a test user"""
    user = Account(
        github_user="testuser",
        github_email="test@example.com",
        account_type="free",
        github_account_type="User",
        avatar_url="https://example.com/avatar.png"
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    # Create workspace membership
    membership = WorkspaceMember(
        user_id=user.user_id,
        workspace_role="admin"
    )
    test_db.add(membership)
    test_db.commit()

    auth.user_tokens._pat_cache.clear()
    # Add token and app session
    auth.user_tokens["testuser"] = "mock_github_token"
    auth.user_tokens._pat_cache["testuser"] = (None, float("inf"))
    user.session_token = auth.create_auth_session("testuser", test_db)

    yield user

    # Cleanup
    auth.user_tokens.pop("testuser", None)
    auth.user_tokens.invalidate_pat("testuser")


class TestPermissionCheckEndpoint:
    """Test the /api/user/{username}/permissions endpoint"""

    def test_permission_check_user_not_found(self):
        """Test permission check for non-existent user"""
        response = client.get("/api/user/nonexistentuser/permissions")

        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    @patch("auth.GitHubPermissionValidator")
    def test_permission_check_no_token(self, mock_validator_class, test_user, test_db):
        """Test permission check when user has no active token"""
        # Remove token
        auth.user_tokens.pop("testuser", None)
        auth.user_tokens._pat_cache["testuser"] = (None, float("inf"))

        response = client.get("/api/user/testuser/permissions", headers=auth_headers(test_user))

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "token_invalid"
        assert data["valid"] is False
        assert "No active GitHub session" in data["issues"][0]

        # Restore token for cleanup
        auth.user_tokens["testuser"] = "mock_github_token"

    @patch("auth.GitHubPermissionValidator")
    def test_permission_check_valid_permissions(
        self, mock_validator_class, test_user, test_db
    ):
        """Test permission check with valid permissions"""
        # Mock the validator
        mock_validator = Mock()
        mock_validator.validate_all_permissions.return_value = {
            "status": PermissionStatus.VALID,
            "valid": True,
            "missing_scopes": [],
            "granted_scopes": ["repo", "workflow", "read:org", "user:email"],
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "details": {}
        }
        mock_validator_class.return_value = mock_validator

        response = client.get("/api/user/testuser/permissions", headers=auth_headers(test_user))

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == PermissionStatus.VALID
        assert data["valid"] is True
        assert len(data["missing_scopes"]) == 0
        assert "message" in data

        # Verify validator was called with correct token
        mock_validator_class.assert_called_once_with("mock_github_token")

        # Verify permission status was stored in database
        test_db.refresh(test_user)
        assert test_user.github_permission_status == PermissionStatus.VALID
        assert test_user.github_permission_checked_at is not None

    @patch("auth.GitHubPermissionValidator")
    def test_permission_check_missing_scopes(
        self, mock_validator_class, test_user, test_db
    ):
        """Test permission check with missing scopes"""
        mock_validator = Mock()
        mock_validator.validate_all_permissions.return_value = {
            "status": PermissionStatus.MISSING_SCOPES,
            "valid": False,
            "missing_scopes": ["repo", "workflow"],
            "granted_scopes": ["user:email"],
            "issues": ["Missing critical GitHub permissions: repo, workflow"],
            "warnings": [],
            "recommendations": [
                "Sign out and sign in again. When GitHub asks for permissions, make sure to authorize all requested scopes."
            ],
            "details": {
                "scopes": {
                    "granted_scopes": ["user:email"],
                    "missing_scopes": ["repo", "workflow"],
                    "has_all_required": False
                }
            }
        }
        mock_validator_class.return_value = mock_validator

        response = client.get("/api/user/testuser/permissions", headers=auth_headers(test_user))

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == PermissionStatus.MISSING_SCOPES
        assert data["valid"] is False
        assert "repo" in data["missing_scopes"]
        assert "workflow" in data["missing_scopes"]
        assert len(data["issues"]) > 0
        assert len(data["recommendations"]) > 0

        # Verify status stored in database
        test_db.refresh(test_user)
        assert test_user.github_permission_status == PermissionStatus.MISSING_SCOPES

    @patch("auth.GitHubPermissionValidator")
    def test_permission_check_missing_repo_access(
        self, mock_validator_class, test_user, test_db
    ):
        """Test permission check with missing repository access"""
        mock_validator = Mock()
        mock_validator.validate_all_permissions.return_value = {
            "status": PermissionStatus.MISSING_REPO_ACCESS,
            "valid": False,
            "missing_scopes": [],
            "granted_scopes": ["repo", "workflow", "read:org", "user:email"],
            "issues": ["Cannot access any repositories"],
            "warnings": [],
            "recommendations": [
                "Ensure you have at least one repository that Actions Manager can access"
            ],
            "details": {
                "repository_access": {
                    "has_repo_access": False,
                    "total_repos": 0
                }
            }
        }
        mock_validator_class.return_value = mock_validator

        response = client.get("/api/user/testuser/permissions", headers=auth_headers(test_user))

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == PermissionStatus.MISSING_REPO_ACCESS
        assert data["valid"] is False
        assert "Cannot access any repositories" in data["issues"]

    @patch("auth.GitHubPermissionValidator")
    def test_permission_check_org_restrictions(
        self, mock_validator_class, test_user, test_db
    ):
        """Test permission check with organization restrictions"""
        mock_validator = Mock()
        mock_validator.validate_all_permissions.return_value = {
            "status": PermissionStatus.VALID,
            "valid": True,
            "missing_scopes": [],
            "granted_scopes": ["repo", "workflow", "read:org", "user:email"],
            "issues": [],
            "warnings": ["Organization restrictions detected for: myorg"],
            "recommendations": [
                "Some organization repositories may be restricted. Contact your organization admin to approve Actions Manager as a third-party OAuth app."
            ],
            "details": {
                "organization_access": {
                    "has_orgs": True,
                    "organizations": ["myorg"],
                    "accessible_orgs": [],
                    "restricted_orgs": ["myorg"],
                    "has_org_restrictions": True
                }
            }
        }
        mock_validator_class.return_value = mock_validator

        response = client.get("/api/user/testuser/permissions", headers=auth_headers(test_user))

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True  # Still valid despite warnings
        assert len(data["warnings"]) > 0
        assert "Organization restrictions" in data["warnings"][0]

    @patch("auth.GitHubPermissionValidator")
    def test_permission_check_exception_handling(
        self, mock_validator_class, test_user, test_db
    ):
        """Test permission check handles exceptions gracefully"""
        mock_validator = Mock()
        mock_validator.validate_all_permissions.side_effect = Exception("Network error")
        mock_validator_class.return_value = mock_validator

        response = client.get("/api/user/testuser/permissions", headers=auth_headers(test_user))

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unknown_error"
        assert data["valid"] is False
        assert "Error checking permissions" in data["issues"][0]

    def test_permission_check_updates_timestamp(
        self, test_user, test_db
    ):
        """Test that permission check updates the checked_at timestamp"""
        with patch("auth.GitHubPermissionValidator") as mock_validator_class:
            mock_validator = Mock()
            mock_validator.validate_all_permissions.return_value = {
                "status": PermissionStatus.VALID,
                "valid": True,
                "missing_scopes": [],
                "granted_scopes": [],
                "issues": [],
                "warnings": [],
                "recommendations": [],
                "details": {}
            }
            mock_validator_class.return_value = mock_validator

            # Record time before check
            before_check = datetime.now(timezone.utc)

            response = client.get("/api/user/testuser/permissions", headers=auth_headers(test_user))

            assert response.status_code == 200

            # Verify timestamp was updated
            test_db.refresh(test_user)
            assert test_user.github_permission_checked_at is not None
            # SQLite strips timezone info on read; normalize before comparing.
            checked_at = test_user.github_permission_checked_at
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            assert checked_at >= before_check


class TestSavedGitHubTokenEndpoints:
    """Test PAT configuration endpoints and masked status payloads."""

    def test_user_details_masks_saved_token_state(self, test_user, test_db):
        test_user.github_pat_token_encrypted = "encrypted-token"
        test_user.github_pat_status = "valid"
        test_user.github_pat_last_error = "Token configured."
        test_user.github_pat_token_type = "fine_grained_pat"
        test_db.commit()

        response = client.get("/api/user/testuser", headers=auth_headers(test_user))

        assert response.status_code == 200
        data = response.json()
        assert data["github_token"]["configured"] is True
        assert data["github_token"]["status"] == "valid"
        assert data["github_token"]["token_type"] == "fine_grained_pat"
        assert "token" not in str(data["github_token"]).lower() or "configured" in data["github_token"]["message"].lower()

    @patch("auth._encrypt_saved_token", return_value="encrypted-token")
    @patch("auth._validate_github_token")
    def test_save_github_token_validates_and_persists_masked_state(self, mock_validate, mock_encrypt, test_user, test_db):
        mock_validate.return_value = {
            "status": PermissionStatus.VALID,
            "valid": True,
            "missing_scopes": [],
            "granted_scopes": [],
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "message": "✅ Fine-grained personal access token validated successfully.",
            "details": {
                "auth_type": "personal_access_token",
                "token_type": "fine_grained_pat",
            },
        }

        response = client.put(
            "/api/user/testuser/github-token",
            headers=auth_headers(test_user),
            json={"token": "github_pat_1234567890"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["saved"] is True
        assert "github_pat_1234567890" not in str(body)

        test_db.refresh(test_user)
        assert test_user.github_pat_token_encrypted == "encrypted-token"
        assert test_user.github_pat_status == PermissionStatus.VALID

    def test_save_github_token_rejects_other_users(self, test_user):
        response = client.put(
            "/api/user/testuser/github-token",
            headers=auth_headers(test_user, {"X-GitHub-User": "someone-else"}),
            json={"token": "github_pat_1234567890"},
        )

        assert response.status_code == 403
        assert "does not match" in response.json()["detail"]

    def test_remove_github_token_clears_saved_fields(self, test_user, test_db):
        test_user.github_pat_token_encrypted = "encrypted-token"
        test_user.github_pat_status = "valid"
        test_user.github_pat_last_error = "Token configured."
        test_db.commit()

        response = client.delete(
            "/api/user/testuser/github-token",
            headers=auth_headers(test_user),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["removed"] is True
        assert body["token"]["configured"] is False

        test_db.refresh(test_user)
        assert test_user.github_pat_token_encrypted is None
        assert test_user.github_pat_status is None

    @patch("auth._encrypt_saved_token", return_value="encrypted-token")
    @patch("auth._resolve_connected_github_account", return_value=("testuser", "User"))
    @patch("auth._fetch_marketplace_data", return_value=[])
    @patch("auth._fetch_user_info", return_value=("testuser", "test@example.com", "https://example.com/avatar.png", "User"))
    @patch("auth._validate_github_token")
    def test_auth_token_login_creates_user_and_saves_token(
        self,
        mock_validate,
        mock_user_info,
        mock_marketplace,
        mock_connected_account,
        mock_encrypt,
        test_db,
    ):
        mock_validate.return_value = {
            "status": PermissionStatus.VALID,
            "valid": True,
            "missing_scopes": [],
            "granted_scopes": [],
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "message": "✅ Personal access token validated successfully.",
            "details": {
                "auth_type": "personal_access_token",
                "token_type": "classic_pat",
            },
        }

        response = client.post("/auth/token", json={"token": "ghp_1234567890"})

        assert response.status_code == 200
        body = response.json()
        assert body["user"] == "testuser"
        assert "ghp_1234567890" not in str(body)

        user = test_db.query(Account).filter(Account.github_user == "testuser").first()
        assert user is not None
        assert user.github_pat_token_encrypted == "encrypted-token"
