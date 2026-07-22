"""
Tests for the strict startup mode validator (`backend/mode_validation.py`).

These tests cover the rules from the "Harden Cloud and Self-Hosted Release
Targets" issue:

* Cloud refuses to start when LICENSE_KEY / tier-override env
  vars are set, when mock or stubbed marketplace responses are enabled, when
  DEBUG_MODE=true, when GITHUB_WEBHOOK_SECRET is missing, when PostgreSQL is
  not configured, or when default admin credentials are used.
* Self-hosted allows missing LICENSE_KEY (resolves to Free), missing
  GITHUB_WEBHOOK_SECRET, and SQLite.
* Tier overrides via env vars are rejected in both modes so the JWT license
  remains the only upgrade path on self-hosted.
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mode_validation import _CLOUD_PRELAUNCH_RELAXED  # noqa: E402

# When ``_CLOUD_PRELAUNCH_RELAXED`` is True the cloud build is not yet
# publicly released and the operational hardening checks (mocks/stubs/debug,
# ENVIRONMENT=development, GITHUB_WEBHOOK_SECRET, Postgres requirement,
# default admin credentials) are intentionally suppressed. The corresponding
# tests are skipped while the flag is on so they automatically come back to
# life when it flips to False at Marketplace launch.
skip_if_cloud_prelaunch_relaxed = pytest.mark.skipif(
    _CLOUD_PRELAUNCH_RELAXED,
    reason="cloud operational hardening is relaxed pre-Marketplace launch",
)


# A baseline cloud env that satisfies every rule. Tests mutate one variable
# at a time to assert that each rule is enforced independently.
CLOUD_VALID_ENV = {
    "INSTALLATION_MODE": "cloud",
    "GITHUB_WEBHOOK_SECRET": "wh-secret-32bytes",
    "DATABASE_URL": "postgresql://user:pw@db:5432/actions_manager",
    "ADMIN_USERNAME": "ops-team",
    "ADMIN_PASSWORD": "Sup3rStr0ng!Passw0rd",
    "USE_MOCK_RESPONSES": "false",
    "USE_STUBBED_MARKETPLACE_API": "false",
    "DEBUG_MODE": "false",
}


# Env vars that should NEVER appear in a clean test run; clear them so the
# host environment cannot influence the result.
_DANGEROUS_VARS = (
    "LICENSE_KEY",
    "ACCOUNT_TYPE",
    "TIER",
    "PLAN",
    "FORCE_TIER",
    "OVERRIDE_TIER",
    "USE_MOCK_RESPONSES",
    "USE_STUBBED_MARKETPLACE_API",
    "DEBUG_MODE",
    "GITHUB_WEBHOOK_SECRET",
    "DATABASE_URL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
    "ENVIRONMENT",
)


def _apply_env(monkeypatch, env: dict, mode: str = "cloud"):
    """Reset dangerous env vars then apply the test scenario."""
    # Set to empty (not delete) so config.py's load_dotenv() — which only
    # fills *unset* vars — cannot resurrect values from a local .env file
    # when we reload the config module below.
    for var in _DANGEROUS_VARS:
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("INSTALLATION_MODE", mode)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Reload config so config.INSTALLATION_MODE is up-to-date.
    import config
    importlib.reload(config)
    import mode_validation
    importlib.reload(mode_validation)
    return mode_validation


# --------------------------------------------------------------------------- #
# Cloud mode: rules that must FAIL closed
# --------------------------------------------------------------------------- #


class TestCloudFailClosedRules:
    def test_cloud_with_baseline_valid_env_passes(self, monkeypatch):
        mv = _apply_env(monkeypatch, CLOUD_VALID_ENV)
        # Should not raise
        mv.validate_startup_configuration()

    def test_cloud_refuses_license_key(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV, LICENSE_KEY="some.jwt.token")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("LICENSE_KEY" in v for v in exc.value.violations)

    @pytest.mark.parametrize(
        "var", ("ACCOUNT_TYPE", "TIER", "PLAN", "FORCE_TIER", "OVERRIDE_TIER")
    )
    def test_cloud_refuses_tier_override_env_vars(self, monkeypatch, var):
        env = dict(CLOUD_VALID_ENV)
        env[var] = "enterprise"
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any(var in v for v in exc.value.violations)

    @skip_if_cloud_prelaunch_relaxed
    def test_cloud_refuses_use_mock_responses(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV, USE_MOCK_RESPONSES="true")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("USE_MOCK_RESPONSES" in v for v in exc.value.violations)

    @skip_if_cloud_prelaunch_relaxed
    def test_cloud_refuses_stubbed_marketplace_api(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV, USE_STUBBED_MARKETPLACE_API="true")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("USE_STUBBED_MARKETPLACE_API" in v for v in exc.value.violations)

    @skip_if_cloud_prelaunch_relaxed
    def test_cloud_refuses_debug_mode(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV, DEBUG_MODE="true")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("DEBUG_MODE" in v for v in exc.value.violations)

    @skip_if_cloud_prelaunch_relaxed
    def test_cloud_requires_github_webhook_secret(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV)
        env.pop("GITHUB_WEBHOOK_SECRET")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("GITHUB_WEBHOOK_SECRET" in v for v in exc.value.violations)

    @skip_if_cloud_prelaunch_relaxed
    def test_cloud_requires_postgres(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV)
        env.pop("DATABASE_URL")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("PostgreSQL" in v for v in exc.value.violations)

    def test_cloud_accepts_postgres_via_postgres_vars(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV)
        env.pop("DATABASE_URL")
        env.update(
            {
                "POSTGRES_USER": "u",
                "POSTGRES_PASSWORD": "p",
                "POSTGRES_DB": "d",
                "POSTGRES_HOST": "h",
            }
        )
        mv = _apply_env(monkeypatch, env)
        mv.validate_startup_configuration()  # no raise

    @skip_if_cloud_prelaunch_relaxed
    def test_cloud_rejects_sqlite_database_url(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV, DATABASE_URL="sqlite:///./app.db")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError):
            mv.validate_startup_configuration()

    @skip_if_cloud_prelaunch_relaxed
    @pytest.mark.parametrize(
        "username", ("admin", "replace_with_unique_admin_username")
    )
    def test_cloud_refuses_default_admin_username(self, monkeypatch, username):
        env = dict(CLOUD_VALID_ENV, ADMIN_USERNAME=username)
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("ADMIN_USERNAME" in v for v in exc.value.violations)

    @skip_if_cloud_prelaunch_relaxed
    @pytest.mark.parametrize(
        "pw",
        (
            "change_this_password",
            "change_this_secure_password",
            "replace_with_strong_random_password",
            "admin",
            "admin123",
            "",
        ),
    )
    def test_cloud_refuses_default_admin_password(self, monkeypatch, pw):
        env = dict(CLOUD_VALID_ENV, ADMIN_PASSWORD=pw)
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("ADMIN_PASSWORD" in v for v in exc.value.violations)


# --------------------------------------------------------------------------- #
# Self-hosted mode: permissive defaults
# --------------------------------------------------------------------------- #


class TestSelfHostedPermissiveRules:
    def test_self_hosted_minimal_env_passes(self, monkeypatch):
        # Empty env beyond INSTALLATION_MODE — SQLite, no license, no webhook.
        mv = _apply_env(monkeypatch, {}, mode="self-hosted")
        mv.validate_startup_configuration()

    def test_self_hosted_allows_license_key(self, monkeypatch):
        mv = _apply_env(
            monkeypatch, {"LICENSE_KEY": "any.jwt.token"}, mode="self-hosted"
        )
        mv.validate_startup_configuration()

    def test_self_hosted_does_not_require_github_webhook_secret(self, monkeypatch):
        mv = _apply_env(monkeypatch, {}, mode="self-hosted")
        mv.validate_startup_configuration()

    def test_self_hosted_allows_sqlite(self, monkeypatch):
        # No DATABASE_URL set — SQLite is the documented default.
        mv = _apply_env(monkeypatch, {}, mode="self-hosted")
        mv.validate_startup_configuration()

    def test_self_hosted_allows_default_admin_credentials(self, monkeypatch):
        # Self-hosted operators control their own host; we don't fail-closed
        # on default admin credentials in development. The cloud rule and the
        # self-hosted-production rule are the security-critical ones.
        mv = _apply_env(
            monkeypatch,
            {
                "ENVIRONMENT": "development",
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "change_this_password",
            },
            mode="self-hosted",
        )
        mv.validate_startup_configuration()

    @pytest.mark.parametrize(
        "var", ("ACCOUNT_TYPE", "TIER", "PLAN", "FORCE_TIER", "OVERRIDE_TIER")
    )
    def test_self_hosted_refuses_tier_override_env_vars(self, monkeypatch, var):
        # The JWT license is the ONLY upgrade path on self-hosted; env-var
        # tier overrides must be rejected too.
        mv = _apply_env(monkeypatch, {var: "enterprise"}, mode="self-hosted")
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any(var in v for v in exc.value.violations)


# --------------------------------------------------------------------------- #
# Helpers / public API surface
# --------------------------------------------------------------------------- #


class TestModeHelpers:
    def test_marketplace_billing_enabled_in_cloud_only(self, monkeypatch):
        mv = _apply_env(monkeypatch, CLOUD_VALID_ENV)
        assert mv.is_marketplace_billing_enabled() is True
        assert mv.is_license_based_tier_enabled() is False

    def test_license_based_tier_enabled_in_self_hosted_only(self, monkeypatch):
        mv = _apply_env(monkeypatch, {}, mode="self-hosted")
        assert mv.is_license_based_tier_enabled() is True
        assert mv.is_marketplace_billing_enabled() is False

    def test_get_violations_returns_list_for_explicit_mode(self, monkeypatch):
        # Active mode is self-hosted but we explicitly query cloud violations.
        # Set a forbidden value (LICENSE_KEY) so the assertion stays meaningful
        # both pre-launch (relaxed) and post-launch (strict).
        mv = _apply_env(
            monkeypatch, {"LICENSE_KEY": "some.jwt.token"}, mode="self-hosted"
        )
        violations = mv.get_violations("cloud")
        assert violations
        assert any("LICENSE_KEY" in v for v in violations)


# --------------------------------------------------------------------------- #
# ENVIRONMENT axis: production vs development strictness
# --------------------------------------------------------------------------- #


class TestEnvironmentAxis:
    """
    The ENVIRONMENT env var is orthogonal to INSTALLATION_MODE:

      * cloud + production    → today's strict cloud rules (default)
      * cloud + development   → REFUSED (no relaxed cloud build)
      * self-hosted + production → strict ops checks (no mocks/debug/default creds)
      * self-hosted + development → permissive (intended for local iteration)

    Tier-override env vars are rejected in every cell.
    """

    # ---- cloud × ENVIRONMENT --------------------------------------------- #

    def test_cloud_defaults_to_production(self, monkeypatch):
        # No ENVIRONMENT set ⇒ implicit production ⇒ baseline valid env passes.
        mv = _apply_env(monkeypatch, CLOUD_VALID_ENV)
        assert mv.get_environment() == "production"
        mv.validate_startup_configuration()

    def test_cloud_explicit_production_passes(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV, ENVIRONMENT="production")
        mv = _apply_env(monkeypatch, env)
        mv.validate_startup_configuration()

    @skip_if_cloud_prelaunch_relaxed
    def test_cloud_refuses_development_environment(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV, ENVIRONMENT="development")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("ENVIRONMENT" in v and "cloud" in v for v in exc.value.violations)

    def test_cloud_refuses_unknown_environment_value(self, monkeypatch):
        env = dict(CLOUD_VALID_ENV, ENVIRONMENT="staging")
        mv = _apply_env(monkeypatch, env)
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any(
            "Unknown ENVIRONMENT" in v or "ENVIRONMENT='staging'" in v
            for v in exc.value.violations
        )

    # ---- self-hosted × production --------------------------------------- #

    def test_self_hosted_production_minimal_env_passes(self, monkeypatch):
        # SQLite + no admin creds + no webhook is fine in self-hosted prod.
        mv = _apply_env(monkeypatch, {"ENVIRONMENT": "production"}, mode="self-hosted")
        mv.validate_startup_configuration()

    def test_self_hosted_production_refuses_use_mock_responses(self, monkeypatch):
        mv = _apply_env(
            monkeypatch,
            {"ENVIRONMENT": "production", "USE_MOCK_RESPONSES": "true"},
            mode="self-hosted",
        )
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("USE_MOCK_RESPONSES" in v for v in exc.value.violations)

    def test_self_hosted_production_refuses_stubbed_marketplace(self, monkeypatch):
        mv = _apply_env(
            monkeypatch,
            {"ENVIRONMENT": "production", "USE_STUBBED_MARKETPLACE_API": "true"},
            mode="self-hosted",
        )
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("USE_STUBBED_MARKETPLACE_API" in v for v in exc.value.violations)

    def test_self_hosted_production_refuses_debug_mode(self, monkeypatch):
        mv = _apply_env(
            monkeypatch,
            {"ENVIRONMENT": "production", "DEBUG_MODE": "true"},
            mode="self-hosted",
        )
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("DEBUG_MODE" in v for v in exc.value.violations)

    @pytest.mark.parametrize(
        "username", ("admin", "replace_with_unique_admin_username")
    )
    def test_self_hosted_production_refuses_default_admin_username_when_set(
        self, monkeypatch, username
    ):
        mv = _apply_env(
            monkeypatch,
            {"ENVIRONMENT": "production", "ADMIN_USERNAME": username},
            mode="self-hosted",
        )
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("ADMIN_USERNAME" in v for v in exc.value.violations)

    @pytest.mark.parametrize(
        "password",
        (
            "change_this_password",
            "replace_with_strong_random_password",
            "admin123",
        ),
    )
    def test_self_hosted_production_refuses_default_admin_password_when_set(
        self, monkeypatch, password
    ):
        mv = _apply_env(
            monkeypatch,
            {"ENVIRONMENT": "production", "ADMIN_PASSWORD": password},
            mode="self-hosted",
        )
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("ADMIN_PASSWORD" in v for v in exc.value.violations)

    def test_self_hosted_production_does_not_require_postgres(self, monkeypatch):
        # Self-hosted prod legitimately runs on SQLite for small deployments.
        mv = _apply_env(monkeypatch, {"ENVIRONMENT": "production"}, mode="self-hosted")
        mv.validate_startup_configuration()

    def test_self_hosted_production_does_not_require_github_webhook_secret(
        self, monkeypatch
    ):
        # Marketplace doesn't apply to self-hosted; webhook secret is optional.
        mv = _apply_env(monkeypatch, {"ENVIRONMENT": "production"}, mode="self-hosted")
        mv.validate_startup_configuration()

    @pytest.mark.parametrize(
        "var", ("ACCOUNT_TYPE", "TIER", "PLAN", "FORCE_TIER", "OVERRIDE_TIER")
    )
    def test_self_hosted_production_refuses_tier_override_env_vars(
        self, monkeypatch, var
    ):
        mv = _apply_env(
            monkeypatch,
            {"ENVIRONMENT": "production", var: "enterprise"},
            mode="self-hosted",
        )
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any(var in v for v in exc.value.violations)

    # ---- self-hosted × development -------------------------------------- #

    def test_self_hosted_development_allows_mocks_debug_and_default_admin(
        self, monkeypatch
    ):
        mv = _apply_env(
            monkeypatch,
            {
                "ENVIRONMENT": "development",
                "USE_MOCK_RESPONSES": "true",
                "USE_STUBBED_MARKETPLACE_API": "true",
                "DEBUG_MODE": "true",
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "change_this_password",
            },
            mode="self-hosted",
        )
        mv.validate_startup_configuration()

    @pytest.mark.parametrize(
        "var", ("ACCOUNT_TYPE", "TIER", "PLAN", "FORCE_TIER", "OVERRIDE_TIER")
    )
    def test_self_hosted_development_still_refuses_tier_overrides(
        self, monkeypatch, var
    ):
        # The one invariant across every cell: env-var tier overrides are
        # always rejected, no exceptions.
        mv = _apply_env(
            monkeypatch,
            {"ENVIRONMENT": "development", var: "enterprise"},
            mode="self-hosted",
        )
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any(var in v for v in exc.value.violations)

    def test_self_hosted_unknown_environment_emits_violation(self, monkeypatch):
        mv = _apply_env(
            monkeypatch, {"ENVIRONMENT": "qa"}, mode="self-hosted"
        )
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("Unknown ENVIRONMENT" in v for v in exc.value.violations)

    def test_self_hosted_unknown_environment_falls_back_to_production_strictness(
        self, monkeypatch
    ):
        # Unknown values default to production semantics so misconfiguration
        # fails closed. DEBUG_MODE=true should still be rejected even when
        # the operator typo'd the ENVIRONMENT value.
        mv = _apply_env(
            monkeypatch,
            {"ENVIRONMENT": "qa", "DEBUG_MODE": "true"},
            mode="self-hosted",
        )
        violations = mv.get_violations()
        assert any("Unknown ENVIRONMENT" in v for v in violations)
        assert any("DEBUG_MODE" in v for v in violations)

    # ---- get_environment helper ----------------------------------------- #

    def test_get_environment_defaults_to_production(self, monkeypatch):
        mv = _apply_env(monkeypatch, {}, mode="self-hosted")
        assert mv.get_environment() == "production"

    def test_get_environment_accepts_development(self, monkeypatch):
        mv = _apply_env(
            monkeypatch, {"ENVIRONMENT": "development"}, mode="self-hosted"
        )
        assert mv.get_environment() == "development"

    def test_get_environment_is_case_insensitive(self, monkeypatch):
        mv = _apply_env(
            monkeypatch, {"ENVIRONMENT": "Development"}, mode="self-hosted"
        )
        assert mv.get_environment() == "development"

    def test_get_environment_falls_back_to_production_for_unknown_value(
        self, monkeypatch
    ):
        # Helper itself never raises; fail-closed by returning production.
        mv = _apply_env(
            monkeypatch, {"ENVIRONMENT": "qa"}, mode="self-hosted"
        )
        assert mv.get_environment() == "production"
