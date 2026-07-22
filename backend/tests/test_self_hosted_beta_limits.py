"""
Tests for self-hosted beta enforcement limits.

Validates that:
- Caller Workflow (standard) projects are capped at 4
- Reusable Workflow (rwx) projects are capped at 2
- Secrets per project are capped at 6
- Environment variables per project are capped at 6
- GitHub deployment environments per project are capped at 6
- Error messages identify the specific beta limit reached
- Cloud mode behavior is unchanged
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock, Mock

from tier_service import (
    check_project_limit,
    check_project_type_limit,
    check_secrets_limit,
    check_env_var_limit,
    check_environment_limit,
    SELF_HOSTED_BETA_LIMITS,
)


class MockAccount:
    def __init__(self, **kwargs):
        self.admin_override = kwargs.get("admin_override", False)
        self.admin_override_until = kwargs.get("admin_override_until", None)
        self.marketplace_plan = kwargs.get("marketplace_plan", None)
        self.marketplace_on_free_trial = kwargs.get("marketplace_on_free_trial", False)
        self.marketplace_next_billing_date = kwargs.get("marketplace_next_billing_date", None)
        self.account_type = kwargs.get("account_type", "free")


# ---------------------------------------------------------------------------
# check_project_type_limit
# ---------------------------------------------------------------------------

class TestCheckProjectTypeLimit:
    """Tests for per-type project limits in self-hosted beta mode."""

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_standard_project_within_limit(self):
        """Caller Workflow Project is allowed when below the limit."""
        allowed, msg = check_project_type_limit(
            current_standard_count=3,
            current_rwx_count=0,
            project_type="standard",
        )
        assert allowed is True
        assert msg is None

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_standard_project_at_limit(self):
        """Caller Workflow Project is blocked when at the limit (4)."""
        limit = SELF_HOSTED_BETA_LIMITS["standard_projects"]
        allowed, msg = check_project_type_limit(
            current_standard_count=limit,
            current_rwx_count=0,
            project_type="standard",
        )
        assert allowed is False
        assert "Caller Workflow Project" in msg
        assert str(limit) in msg
        assert "self-hosted beta" in msg.lower()

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_rwx_project_within_limit(self):
        """Reusable Workflow Project is allowed when below the limit."""
        allowed, msg = check_project_type_limit(
            current_standard_count=0,
            current_rwx_count=1,
            project_type="rwx",
        )
        assert allowed is True
        assert msg is None

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_rwx_project_at_limit(self):
        """Reusable Workflow Project is blocked when at the limit (2)."""
        limit = SELF_HOSTED_BETA_LIMITS["rwx_projects"]
        allowed, msg = check_project_type_limit(
            current_standard_count=0,
            current_rwx_count=limit,
            project_type="rwx",
        )
        assert allowed is False
        assert "Reusable Workflow Project" in msg
        assert str(limit) in msg
        assert "self-hosted beta" in msg.lower()

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_independent_type_counts(self):
        """Standard and rwx limits are enforced independently."""
        # Standard at limit, rwx still has room
        allowed_std, _ = check_project_type_limit(
            current_standard_count=SELF_HOSTED_BETA_LIMITS["standard_projects"],
            current_rwx_count=0,
            project_type="standard",
        )
        assert allowed_std is False

        allowed_rwx, _ = check_project_type_limit(
            current_standard_count=SELF_HOSTED_BETA_LIMITS["standard_projects"],
            current_rwx_count=0,
            project_type="rwx",
        )
        assert allowed_rwx is True

    @patch("tier_service.INSTALLATION_MODE", "cloud")
    def test_cloud_mode_always_allowed(self):
        """In cloud mode check_project_type_limit is a no-op."""
        allowed, msg = check_project_type_limit(
            current_standard_count=100,
            current_rwx_count=100,
            project_type="standard",
        )
        assert allowed is True
        assert msg is None


# ---------------------------------------------------------------------------
# check_project_limit (combined beta total)
# ---------------------------------------------------------------------------

class TestCheckProjectLimitBeta:
    """Tests for the combined project total limit in self-hosted beta mode."""

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_below_combined_limit(self):
        account = MockAccount()
        beta_total = (
            SELF_HOSTED_BETA_LIMITS["standard_projects"]
            + SELF_HOSTED_BETA_LIMITS["rwx_projects"]
        )
        allowed, msg = check_project_limit(account, beta_total - 1)
        assert allowed is True
        assert msg is None

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_at_combined_limit(self):
        account = MockAccount()
        beta_total = (
            SELF_HOSTED_BETA_LIMITS["standard_projects"]
            + SELF_HOSTED_BETA_LIMITS["rwx_projects"]
        )
        allowed, msg = check_project_limit(account, beta_total)
        assert allowed is False
        assert "self-hosted beta" in msg.lower()


# ---------------------------------------------------------------------------
# check_secrets_limit
# ---------------------------------------------------------------------------

class TestCheckSecretsLimitBeta:
    """Tests for the self-hosted beta secrets limit (6 per project)."""

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_within_beta_secret_limit(self):
        account = MockAccount()
        limit = SELF_HOSTED_BETA_LIMITS["secrets_per_project"]
        allowed, msg = check_secrets_limit(account, limit)
        assert allowed is True
        assert msg is None

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_exceeds_beta_secret_limit(self):
        account = MockAccount()
        limit = SELF_HOSTED_BETA_LIMITS["secrets_per_project"]
        allowed, msg = check_secrets_limit(account, limit + 1)
        assert allowed is False
        assert str(limit) in msg
        assert "self-hosted beta" in msg.lower()

    @patch("tier_service.INSTALLATION_MODE", "cloud")
    def test_cloud_free_tier_still_uses_old_limit(self):
        """Cloud free tier still uses the old free-tier limit (2)."""
        account = MockAccount(account_type="free")
        with patch("tier_service.license.get_installation_tier", return_value="free"):
            # 2 secrets: at cloud free limit — blocked
            allowed, msg = check_secrets_limit(account, 3)
        assert allowed is False
        assert "2 secrets" in msg or "up to 2" in msg.lower()


# ---------------------------------------------------------------------------
# check_env_var_limit
# ---------------------------------------------------------------------------

class TestCheckEnvVarLimit:
    """Tests for the self-hosted beta env var limit (6 per project)."""

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_within_beta_env_var_limit(self):
        limit = SELF_HOSTED_BETA_LIMITS["env_vars_per_project"]
        allowed, msg = check_env_var_limit(current_count=3, new_count=3)
        assert allowed is True
        assert msg is None

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_at_beta_env_var_limit(self):
        limit = SELF_HOSTED_BETA_LIMITS["env_vars_per_project"]
        allowed, msg = check_env_var_limit(current_count=limit, new_count=0)
        assert allowed is True  # not exceeding — equal to limit

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_exceeds_beta_env_var_limit(self):
        limit = SELF_HOSTED_BETA_LIMITS["env_vars_per_project"]
        allowed, msg = check_env_var_limit(current_count=limit, new_count=1)
        assert allowed is False
        assert str(limit) in msg
        assert "self-hosted beta" in msg.lower()

    @patch("tier_service.INSTALLATION_MODE", "cloud")
    def test_cloud_mode_no_op(self):
        """In cloud mode check_env_var_limit is a no-op."""
        allowed, msg = check_env_var_limit(current_count=100, new_count=100)
        assert allowed is True
        assert msg is None


# ---------------------------------------------------------------------------
# check_environment_limit
# ---------------------------------------------------------------------------

class TestCheckEnvironmentLimit:
    """Tests for the self-hosted beta GitHub environments limit (6 per project)."""

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_within_beta_environment_limit(self):
        limit = SELF_HOSTED_BETA_LIMITS["environments_per_project"]
        allowed, msg = check_environment_limit(current_count=limit - 1, new_count=1)
        assert allowed is True
        assert msg is None

    @patch("tier_service.INSTALLATION_MODE", "self-hosted")
    def test_exceeds_beta_environment_limit(self):
        limit = SELF_HOSTED_BETA_LIMITS["environments_per_project"]
        allowed, msg = check_environment_limit(current_count=limit, new_count=1)
        assert allowed is False
        assert str(limit) in msg
        assert "self-hosted beta" in msg.lower()

    @patch("tier_service.INSTALLATION_MODE", "cloud")
    def test_cloud_mode_no_op(self):
        """In cloud mode check_environment_limit is a no-op."""
        allowed, msg = check_environment_limit(current_count=100, new_count=100)
        assert allowed is True
        assert msg is None
