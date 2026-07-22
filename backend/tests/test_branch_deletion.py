"""
Tests for ActionsManager branch deletion after PR merge.
Covers:
1. Unique branch name validation (_is_safe_to_delete_am_branch)
2. Successful branch deletion (_delete_actions_manager_branch)
3. Merge succeeds even when branch deletion fails
4. Branch deletion is skipped for non-AM branches, protected branches, etc.
"""
import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from workflows import (
    _is_safe_to_delete_am_branch,
    _delete_actions_manager_branch,
)


class TestIsSafeToDeleteAmBranch:
    """Unit tests for the safety validation helper."""

    def test_new_format_branch_is_safe(self):
        """New unique AM branch format should be safe to delete."""
        is_safe, reason = _is_safe_to_delete_am_branch(
            "actions-manager/rwx1/test1/a1b2c3d4-main", "main"
        )
        assert is_safe is True
        assert reason == ""

    def test_legacy_format_branch_is_safe(self):
        """Legacy AM branch format (actions-manager/<code>-<branch>) should also be safe."""
        is_safe, reason = _is_safe_to_delete_am_branch(
            "actions-manager/myapp-main", "main"
        )
        assert is_safe is True
        assert reason == ""

    def test_non_am_branch_rejected(self):
        """Non-AM branches must not be deleted."""
        is_safe, reason = _is_safe_to_delete_am_branch("feature/my-feature", "main")
        assert is_safe is False
        assert "naming convention" in reason

    def test_main_branch_rejected(self):
        """'main' branch itself must never be deleted."""
        is_safe, reason = _is_safe_to_delete_am_branch("main", "develop")
        assert is_safe is False

    def test_master_branch_rejected(self):
        is_safe, reason = _is_safe_to_delete_am_branch("master", "develop")
        assert is_safe is False

    def test_source_equals_target_rejected(self):
        """Branch must differ from the target it was merged into."""
        is_safe, reason = _is_safe_to_delete_am_branch(
            "actions-manager/proj/repo/abc12345-main", "actions-manager/proj/repo/abc12345-main"
        )
        assert is_safe is False
        assert "same" in reason

    def test_release_prefix_rejected(self):
        """Branches starting with release/ must be protected (plain branch name)."""
        is_safe, reason = _is_safe_to_delete_am_branch("release/1.0", "main")
        assert is_safe is False

    def test_am_prefixed_release_branch_rejected(self):
        """actions-manager/release/1.0 should be blocked by the protected-prefix rule."""
        is_safe, reason = _is_safe_to_delete_am_branch("actions-manager/release/1.0", "main")
        assert is_safe is False
        assert "protected" in reason.lower()

    def test_am_prefixed_hotfix_branch_rejected(self):
        """actions-manager/hotfix/critical should be blocked by the protected-prefix rule."""
        is_safe, reason = _is_safe_to_delete_am_branch("actions-manager/hotfix/critical", "main")
        assert is_safe is False
        assert "protected" in reason.lower()

    def test_develop_branch_rejected(self):
        is_safe, reason = _is_safe_to_delete_am_branch("develop", "main")
        assert is_safe is False

    def test_production_branch_rejected(self):
        is_safe, reason = _is_safe_to_delete_am_branch("production", "main")
        assert is_safe is False

    def test_staging_branch_rejected(self):
        is_safe, reason = _is_safe_to_delete_am_branch("staging", "main")
        assert is_safe is False


class TestDeleteActionsManagerBranch:
    """Integration-style tests for the deletion helper."""

    def test_successful_deletion(self):
        """Branch is deleted (204) — returns (True, None)."""
        mock_response = Mock()
        mock_response.status_code = 204

        mock_user_tokens = {"user1": "token_abc"}

        with patch('workflows.user_tokens', mock_user_tokens), \
             patch('workflows.requests.delete', return_value=mock_response):
            deleted, warning = _delete_actions_manager_branch(
                owner="owner",
                repo="repo",
                branch_name="actions-manager/proj/repo/abc12345-main",
                target_branch="main",
                github_user="user1",
            )

        assert deleted is True
        assert warning is None

    def test_branch_already_gone(self):
        """404 on delete means branch is already gone — treated as success."""
        mock_response = Mock()
        mock_response.status_code = 404

        mock_user_tokens = {"user1": "token_abc"}

        with patch('workflows.user_tokens', mock_user_tokens), \
             patch('workflows.requests.delete', return_value=mock_response):
            deleted, warning = _delete_actions_manager_branch(
                owner="owner",
                repo="repo",
                branch_name="actions-manager/proj/repo/abc12345-main",
                target_branch="main",
                github_user="user1",
            )

        assert deleted is True
        assert warning is None

    def test_protected_branch_deletion_fails_gracefully(self):
        """422 (protected branch) — returns (False, warning) without raising."""
        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.text = "Protected branch"

        mock_user_tokens = {"user1": "token_abc"}

        with patch('workflows.user_tokens', mock_user_tokens), \
             patch('workflows.requests.delete', return_value=mock_response):
            deleted, warning = _delete_actions_manager_branch(
                owner="owner",
                repo="repo",
                branch_name="actions-manager/proj/repo/abc12345-main",
                target_branch="main",
                github_user="user1",
            )

        assert deleted is False
        assert warning is not None

    def test_non_am_branch_skipped(self):
        """Branch that doesn't match AM convention is skipped without API call."""
        mock_user_tokens = {"user1": "token_abc"}

        with patch('workflows.user_tokens', mock_user_tokens), \
             patch('workflows.requests.delete') as mock_delete:
            deleted, warning = _delete_actions_manager_branch(
                owner="owner",
                repo="repo",
                branch_name="feature/my-feature",
                target_branch="main",
                github_user="user1",
            )

        assert deleted is False
        assert warning is not None
        mock_delete.assert_not_called()

    def test_no_token_returns_warning(self):
        """If user has no token, deletion is skipped with a warning."""
        mock_user_tokens = {}  # empty — no token for user1

        with patch('workflows.user_tokens', mock_user_tokens):
            deleted, warning = _delete_actions_manager_branch(
                owner="owner",
                repo="repo",
                branch_name="actions-manager/proj/repo/abc12345-main",
                target_branch="main",
                github_user="user1",
            )

        assert deleted is False
        assert warning is not None
        assert "token" in warning.lower()

    def test_api_exception_handled_gracefully(self):
        """An exception from requests.delete returns (False, warning) without raising."""
        mock_user_tokens = {"user1": "token_abc"}

        with patch('workflows.user_tokens', mock_user_tokens), \
             patch('workflows.requests.delete', side_effect=ConnectionError("Network error")):
            deleted, warning = _delete_actions_manager_branch(
                owner="owner",
                repo="repo",
                branch_name="actions-manager/proj/repo/abc12345-main",
                target_branch="main",
                github_user="user1",
            )

        assert deleted is False
        assert warning is not None

    def test_unique_branches_multi_repo(self):
        """Calling create branch for two different repos produces distinct names."""
        from workflows import _create_or_get_am_branch

        mock_target = Mock()
        mock_target.status_code = 200
        mock_target.json.return_value = {"object": {"sha": "sha1"}}

        mock_created = Mock()
        mock_created.status_code = 201

        headers = {"Authorization": "token x"}

        with patch('workflows.requests.get', return_value=mock_target), \
             patch('workflows.requests.post', return_value=mock_created):
            branch1, _, _ = _create_or_get_am_branch("owner", "repo1", "main", "PROJ", headers)
            branch2, _, _ = _create_or_get_am_branch("owner", "repo2", "main", "PROJ", headers)

        # Different repos → different slugs → distinct branches
        assert branch1 != branch2
        assert "repo1" in branch1
        assert "repo2" in branch2
