"""
Strict runtime mode validation for ActionsManager.xyz.

This module is the single source of truth for deployment-mode-specific
configuration rules. It is invoked at application startup and **fails closed**
when a Cloud/SaaS deployment is configured in a way that could allow billing
or tier enforcement to be bypassed.

There are two orthogonal axes:

* ``INSTALLATION_MODE`` — *entitlement source*. Either ``cloud`` (tier comes
  from GitHub Marketplace) or ``self-hosted`` (tier comes from a signed JWT
  ``LICENSE_KEY``).
* ``ENVIRONMENT`` — *operational strictness*. Either ``production`` (default,
  fail-closed on unsafe ops settings) or ``development`` (permissive, intended
  for local iteration).

Cloud (``INSTALLATION_MODE=cloud``) rules — refuse to start when:

* ``LICENSE_KEY`` is set (cloud licensing is via Marketplace, never license keys).
* Tier-override env vars are set (``ACCOUNT_TYPE``, ``TIER``, ``PLAN``,
  ``FORCE_TIER``, ``OVERRIDE_TIER``).

Post-launch cloud rules — additionally refuse to start when
``_CLOUD_PRELAUNCH_RELAXED`` is False and any of the following hold:

* ``ENVIRONMENT=development`` is set (cloud cannot run in development mode).
* ``USE_MOCK_RESPONSES=true``.
* ``USE_STUBBED_MARKETPLACE_API=true``.
* ``DEBUG_MODE=true`` (production builds must not run with debug logging).
* ``GITHUB_WEBHOOK_SECRET`` is missing or empty.
* Neither ``DATABASE_URL`` nor a complete PostgreSQL configuration is set.
* ``ADMIN_USERNAME`` / ``ADMIN_PASSWORD`` are missing or use the documented
  default placeholder values.

Self-hosted production (``INSTALLATION_MODE=self-hosted``,
``ENVIRONMENT=production``) rules — refuse to start when:

* ``USE_MOCK_RESPONSES=true`` or ``USE_STUBBED_MARKETPLACE_API=true``.
* ``DEBUG_MODE=true``.
* ``ADMIN_USERNAME`` / ``ADMIN_PASSWORD`` use the documented default
  placeholder values (only checked when explicitly set; an unset admin user
  is allowed because self-hosted operators may rely on OAuth).
* Tier-override env vars are set.

Self-hosted production deliberately does *not* require PostgreSQL or the
GitHub webhook secret: small single-tenant deployments may legitimately use
SQLite and have no Marketplace integration.

Self-hosted development (``INSTALLATION_MODE=self-hosted``,
``ENVIRONMENT=development``) rules — permissive:

* ``LICENSE_KEY`` is allowed.
* ``GITHUB_WEBHOOK_SECRET`` is *not* required.
* SQLite is allowed (no ``DATABASE_URL`` required).
* Marketplace configuration is *not* required.
* Mocks, stubs, debug mode, and default admin credentials are tolerated.
* Tier-override env vars are still rejected — the JWT license is the only
  way to upgrade a self-hosted installation, never an env var.

Use :func:`validate_startup_configuration` from ``main.py``. The function
raises :class:`ModeValidationError` on failure, listing every violation so
operators can fix the deployment in one pass.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional
from urllib.parse import urlsplit

import config


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Env vars that must NEVER set the effective tier directly. Cloud refuses to
# start if any are present; self-hosted also refuses, because the JWT license
# is the only valid upgrade path.
TIER_OVERRIDE_ENV_VARS = (
    "ACCOUNT_TYPE",
    "TIER",
    "PLAN",
    "FORCE_TIER",
    "OVERRIDE_TIER",
)

# Default placeholder admin credentials shipped in env templates. A production
# cloud deployment must never run with these values.
DEFAULT_ADMIN_USERNAMES = {
    "admin",
    "administrator",
    "root",
    "",
    "replace_with_unique_admin_username",
}
DEFAULT_ADMIN_PASSWORDS = {
    "",
    "admin",
    "admin123",
    "password",
    "replace_with_strong_random_password",
    "change_this_password",
    "change_this_secure_password",
    "changeme",
}

# Operational strictness axis. Production is fail-closed; development is
# permissive. Cloud is always production — see ``_validate_cloud``.
VALID_ENVIRONMENTS = {"production", "development"}
DEFAULT_ENVIRONMENT = "production"


# --------------------------------------------------------------------------- #
# Cloud operational hardening toggle
# --------------------------------------------------------------------------- #
#
# Set to ``False`` to enable the full strict cloud ruleset. When ``False``,
# cloud deployments must supply a real PostgreSQL database, a non-default
# GITHUB_WEBHOOK_SECRET, non-placeholder ADMIN_USERNAME/ADMIN_PASSWORD, and
# must not enable ENVIRONMENT=development, USE_STUBBED_MARKETPLACE_API=true,
# USE_MOCK_RESPONSES=true, or DEBUG_MODE=true.
#
# The tier-bypass guards (LICENSE_KEY, LICENSE_SECRET, ACCOUNT_TYPE/TIER/...
# env vars) are always enforced regardless of this flag.
#
# Stays True until cloud actually launches publicly. Today the only
# INSTALLATION_MODE=cloud deployment is an internal dev/staging cluster used
# to develop the cloud code path — it legitimately needs stubbed Marketplace
# calls and mock responses, the same as any other pre-launch environment.
# Flip to False as a deliberate step at real cloud launch, not before —
# flipping it early with no real production cloud traffic just breaks the
# dev cluster's ability to test safely without hitting live GitHub APIs.
_CLOUD_PRELAUNCH_RELAXED = True


def get_environment() -> str:
    """
    Resolve the operational environment from the ``ENVIRONMENT`` env var.

    Defaults to ``production`` when unset, empty, or set to an unknown value
    so that misconfiguration always fails closed. The validators emit a
    separate violation describing the unknown value via
    :func:`_collect_environment_violations`.
    """
    raw = os.environ.get("ENVIRONMENT", "").strip().lower()
    if raw in VALID_ENVIRONMENTS:
        return raw
    return DEFAULT_ENVIRONMENT


def _collect_environment_violations() -> Iterable[str]:
    """Yield a violation when ``ENVIRONMENT`` is set to an unknown value."""
    raw = os.environ.get("ENVIRONMENT", "").strip().lower()
    if raw and raw not in VALID_ENVIRONMENTS:
        yield (
            f"Unknown ENVIRONMENT={raw!r}. "
            f"Must be one of: {', '.join(sorted(VALID_ENVIRONMENTS))}."
        )


class ModeValidationError(RuntimeError):
    """Raised when startup configuration violates the active mode's rules."""

    def __init__(self, mode: str, violations: List[str]):
        self.mode = mode
        self.violations = list(violations)
        bullets = "\n".join(f"  - {v}" for v in self.violations)
        super().__init__(
            f"Refusing to start: INSTALLATION_MODE={mode!r} configuration "
            f"violations:\n{bullets}"
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _env(name: str) -> str:
    """Return a stripped environment variable, never ``None``."""
    return os.environ.get(name, "").strip()


def _is_truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def _has_postgres_config() -> bool:
    """
    Return True when the deployment has either a DATABASE_URL pointing at
    PostgreSQL or a full set of POSTGRES_* connection variables.
    """
    db_url = _env("DATABASE_URL")
    if db_url and (
        db_url.startswith("postgres://")
        or db_url.startswith("postgresql://")
        or db_url.startswith("postgresql+")  # SQLAlchemy driver-qualified URL
    ):
        return True

    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST")
    return all(_env(k) for k in required)


def _collect_tier_override_violations() -> Iterable[str]:
    for var in TIER_OVERRIDE_ENV_VARS:
        if _env(var):
            yield (
                f"{var} is set. Tier overrides via environment variables are "
                f"not allowed in any mode. Cloud uses Marketplace; self-hosted "
                f"uses signed LICENSE_KEY."
            )


# --------------------------------------------------------------------------- #
# APP_URL resolution and validation
# --------------------------------------------------------------------------- #

_LOCALHOST_NAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"}


def resolve_app_url() -> str:
    """
    Return the effective APP_URL after the priority chain.

    Priority: APP_URL > VITE_APP_URL > default ``http://localhost:8080``.
    Trailing slashes are stripped.
    """
    url = _env("APP_URL") or _env("VITE_APP_URL")
    if not url:
        return "http://localhost:8080"
    return url.rstrip("/")


def _host_is_loopback(hostname: str) -> bool:
    """Return True when *hostname* refers to the local machine."""
    if not hostname:
        return False
    # Strip brackets from IPv6 (e.g. "[::1]")
    bare = hostname.strip("[]").lower()
    return bare in _LOCALHOST_NAMES


def _collect_app_url_violations() -> Iterable[str]:
    """
    Validate the resolved APP_URL scheme and HTTP-security policy.

    Yields violations (never raises directly) so that all problems can be
    collected in a single startup pass.
    """
    url = resolve_app_url()
    parsed = urlsplit(url)

    if parsed.scheme not in ("http", "https"):
        yield (
            f"APP_URL={url!r} uses unsupported scheme {parsed.scheme!r}. "
            f"Only http:// and https:// are allowed."
        )
        return

    if parsed.scheme == "https":
        return

    # scheme == "http" — allowed for loopback without opt-in
    hostname = parsed.hostname or ""
    if _host_is_loopback(hostname):
        return

    # Non-loopback HTTP — require ALLOW_INSECURE_HTTP=true
    if not _is_truthy(_env("ALLOW_INSECURE_HTTP")):
        yield (
            f"APP_URL={url!r} is non-local plain HTTP. This is insecure — "
            f"tokens and credentials would be transmitted in cleartext. "
            f"Either switch to https:// or set ALLOW_INSECURE_HTTP=true "
            f"to allow it."
        )


def _validate_cloud() -> List[str]:
    """Return the list of cloud-mode violations (empty when valid)."""
    violations: List[str] = []

    # Always-on tier-bypass guards. These prevent silent drift in the
    # tier-resolution code path regardless of whether the cloud build is
    # publicly released.
    if _env("LICENSE_KEY"):
        violations.append(
            "LICENSE_KEY must not be set in cloud mode. Cloud tier is "
            "controlled exclusively by the GitHub Marketplace subscription."
        )
    if _env("LICENSE_SECRET"):
        violations.append(
            "LICENSE_SECRET must not be set in cloud mode. Cloud tier is "
            "controlled exclusively by the GitHub Marketplace subscription."
        )
    violations.extend(_collect_tier_override_violations())

    # Surface a violation when ENVIRONMENT is set to a value we do not
    # recognise, regardless of the relaxation flag — that's a typo, not
    # a deliberate operational choice.
    env_value = os.environ.get("ENVIRONMENT", "").strip().lower()
    if env_value and env_value not in VALID_ENVIRONMENTS:
        violations.extend(_collect_environment_violations())

    if _CLOUD_PRELAUNCH_RELAXED:
        # Operational hardening is disabled; return only the always-on
        # tier-bypass violations collected above.
        return violations

    # ----- Cloud operational hardening ----------------------------------- #

    # Cloud is always production. Refuse the relaxed combination outright so
    # there is no env-var path to a development-strictness cloud deployment.
    if env_value == "development":
        violations.append(
            "ENVIRONMENT='development' is not permitted in cloud mode. "
            "Cloud always runs as production; use INSTALLATION_MODE=self-hosted "
            "with ENVIRONMENT=development for local iteration."
        )

    # Production-only safety checks.
    if _is_truthy(_env("USE_MOCK_RESPONSES")):
        violations.append(
            "USE_MOCK_RESPONSES=true is not permitted in cloud mode."
        )
    if _is_truthy(_env("USE_STUBBED_MARKETPLACE_API")):
        violations.append(
            "USE_STUBBED_MARKETPLACE_API=true is not permitted in cloud mode."
        )
    if _is_truthy(_env("DEBUG_MODE")):
        violations.append(
            "DEBUG_MODE=true is not permitted in cloud mode. Set DEBUG_MODE=false."
        )

    # Marketplace billing requires a webhook secret.
    if not _env("GITHUB_WEBHOOK_SECRET"):
        violations.append(
            "GITHUB_WEBHOOK_SECRET is required in cloud mode for verifying "
            "GitHub Marketplace webhooks."
        )

    # Cloud must use PostgreSQL.
    if not _has_postgres_config():
        violations.append(
            "Cloud mode requires PostgreSQL. Set DATABASE_URL=postgresql://... "
            "or all of POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB/POSTGRES_HOST."
        )

    # Refuse default admin credentials.
    admin_user = _env("ADMIN_USERNAME").lower()
    admin_pass = _env("ADMIN_PASSWORD")
    if not admin_user:
        violations.append("ADMIN_USERNAME must be set to a non-default value.")
    elif admin_user in DEFAULT_ADMIN_USERNAMES:
        violations.append(
            f"ADMIN_USERNAME={admin_user!r} is a default value. "
            "Choose a unique administrator username."
        )
    if not admin_pass or admin_pass in DEFAULT_ADMIN_PASSWORDS:
        violations.append(
            "ADMIN_PASSWORD is missing or uses a default placeholder value. "
            "Set a strong, unique password."
        )

    return violations


def _validate_self_hosted() -> List[str]:
    """Return the list of self-hosted-mode violations (empty when valid)."""
    violations: List[str] = []
    # Tier-overrides are forbidden in every environment because the JWT
    # license is the only valid upgrade path on self-hosted.
    violations.extend(_collect_tier_override_violations())
    # Surface a clear violation when ENVIRONMENT is set to an unknown value.
    violations.extend(_collect_environment_violations())

    # APP_URL scheme / insecure-HTTP validation applies in every environment.
    violations.extend(_collect_app_url_violations())

    # Operational strictness: production self-hosted gets the same hardening
    # cloud already gets, minus the Marketplace- and Postgres-specific rules
    # that don't apply to single-tenant deployments.
    environment = get_environment()
    if environment == "production":
        if _is_truthy(_env("USE_MOCK_RESPONSES")):
            violations.append(
                "USE_MOCK_RESPONSES=true is not permitted with "
                "ENVIRONMENT=production. Set ENVIRONMENT=development for local "
                "iteration."
            )
        if _is_truthy(_env("USE_STUBBED_MARKETPLACE_API")):
            violations.append(
                "USE_STUBBED_MARKETPLACE_API=true is not permitted with "
                "ENVIRONMENT=production. Set ENVIRONMENT=development for local "
                "iteration."
            )
        if _is_truthy(_env("DEBUG_MODE")):
            violations.append(
                "DEBUG_MODE=true is not permitted with ENVIRONMENT=production. "
                "Set DEBUG_MODE=false or ENVIRONMENT=development."
            )
        # Only check admin credentials when explicitly set — self-hosted
        # operators may rely on OAuth and never configure a local admin user.
        admin_user = _env("ADMIN_USERNAME").lower()
        admin_pass = _env("ADMIN_PASSWORD")
        if admin_user and admin_user in DEFAULT_ADMIN_USERNAMES:
            violations.append(
                f"ADMIN_USERNAME={admin_user!r} is a default value. "
                "Choose a unique administrator username or unset it."
            )
        if admin_pass and admin_pass in DEFAULT_ADMIN_PASSWORDS:
            violations.append(
                "ADMIN_PASSWORD uses a default placeholder value. "
                "Set a strong, unique password or unset it."
            )

    return violations


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def get_violations(mode: Optional[str] = None) -> List[str]:
    """
    Return the list of configuration violations for the given mode (defaults
    to the active installation mode read from the environment). Empty list
    means valid.
    """
    if mode is None:
        # Re-read from the environment rather than relying on the cached
        # ``config.INSTALLATION_MODE`` module constant. This keeps the
        # validator robust against test pollution and against module-load
        # order issues at startup.
        active_mode = config.get_installation_mode()
    else:
        active_mode = mode.lower()
    if active_mode == "cloud":
        return _validate_cloud()
    if active_mode == "self-hosted":
        return _validate_self_hosted()
    # Unknown modes are caught by ``config.get_installation_mode``; treat as
    # invalid here too.
    return [f"Unknown INSTALLATION_MODE: {active_mode!r}"]


def validate_startup_configuration(mode: Optional[str] = None) -> None:
    """
    Validate the active deployment mode's configuration.

    Raises :class:`ModeValidationError` listing every violation when the
    configuration is invalid. Returns silently when valid.
    """
    if mode is None:
        active_mode = config.get_installation_mode()
    else:
        active_mode = mode.lower()
    violations = get_violations(active_mode)
    if violations:
        raise ModeValidationError(active_mode, violations)


def is_marketplace_billing_enabled() -> bool:
    """
    Single source of truth for whether Marketplace billing is the source of
    truth for tier resolution. Should be used in place of ad-hoc
    ``INSTALLATION_MODE == "cloud"`` checks scattered through the codebase.
    """
    return config.get_installation_mode() == "cloud"


def is_license_based_tier_enabled() -> bool:
    """
    Single source of truth for whether JWT license keys may grant tier
    upgrades. Always False in cloud mode.
    """
    return config.get_installation_mode() == "self-hosted"
