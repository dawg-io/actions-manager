"""
Tier Service for ActionsManager

Provides centralized tier enforcement logic that integrates:
- Installation mode (self-hosted with license keys or cloud with marketplace)
- Account type (free, professional, enterprise)
- Marketplace subscription status (cloud mode)
- License key validation (self-hosted mode)
- Admin overrides
- Free trial status
- Retention policies

This service ensures consistent tier enforcement across the application
in both self-hosted and cloud deployment modes.
"""

from typing import Optional, Tuple
from datetime import datetime, timezone, timedelta
from models import Account
from config import INSTALLATION_MODE
import license


# Tier limits configuration
#
# Pricing model is workflow-first: every tier can use the core product
# (workflow editor, multi-repo rollout, drift detection, reusable workflows,
# and private repositories). Paid tiers exist to unlock SCALE, not core
# functionality. Only project counts, repos-per-project, secrets-per-project and
# build-metrics history depth are gated — every tier can see build metrics,
# higher tiers simply keep more history.
TIER_LIMITS = {
    "free": {
        "projects": 3,
        "repos_per_project": 10,
        "secrets_per_project": 2,
        "private_repos": True,
        "reusable_workflows": True,
        "run_history_days": 30,
    },
    "professional": {
        "projects": 10,
        "repos_per_project": 50,
        "secrets_per_project": 10,
        "private_repos": True,
        "reusable_workflows": True,
        "run_history_days": 90,
    },
    "enterprise": {
        "projects": None,  # Unlimited
        "repos_per_project": None,  # Unlimited
        "secrets_per_project": None,  # Unlimited
        "private_repos": True,
        "reusable_workflows": True,
        "run_history_days": None,  # Unlimited
    }
}

# Self-hosted beta limits — apply when INSTALLATION_MODE == "self-hosted".
# These supersede the free-tier limits for evaluation purposes.
SELF_HOSTED_BETA_LIMITS = {
    "standard_projects": 4,   # Caller Workflow Projects
    "rwx_projects": 2,        # Reusable Workflow Projects
    "secrets_per_project": 6,
    "env_vars_per_project": 6,
    "environments_per_project": 6,
    "run_history_days": 30,
}


def is_self_hosted_beta() -> bool:
    """Return True when running in self-hosted beta mode."""
    return INSTALLATION_MODE == "self-hosted"

# Retention period for downgraded/cancelled accounts (days)
RETENTION_PERIOD_DAYS = 30


def _is_admin_override_active(account: Account) -> bool:
    """
    Check if admin override is currently active for an account.
    
    Args:
        account: Account object
        
    Returns:
        True if admin override is active, False otherwise
    """
    if not account.admin_override:
        return False
    
    # Indefinite override
    if account.admin_override_until is None:
        return True
    
    # Check if temporary override is still valid
    override_until = account.admin_override_until
    if override_until.tzinfo is None:
        override_until = override_until.replace(tzinfo=timezone.utc)
    
    return override_until > datetime.now(timezone.utc)


def _is_marketplace_subscription_active(account: Account) -> bool:
    """
    Check if marketplace subscription is currently active.
    
    Args:
        account: Account object
        
    Returns:
        True if subscription is active, False otherwise
    """
    if not account.marketplace_plan:
        return False
    
    # Free trial gives immediate access
    if account.marketplace_on_free_trial:
        return True
    
    # Check billing date if available
    if account.marketplace_next_billing_date:
        billing_date = account.marketplace_next_billing_date
        if billing_date.tzinfo is None:
            billing_date = billing_date.replace(tzinfo=timezone.utc)
        return billing_date > datetime.now(timezone.utc)
    
    # No billing date set, assume active if marketplace_plan exists
    return True


def get_effective_tier(account: Account) -> str:
    """
    Determine the effective tier for an account, considering installation mode.
    
    Self-hosted mode (license-based):
    - Uses installation-wide tier from license key validation
    - License tier applies to all accounts
    - Admin overrides can still be used for per-account control
    
    Cloud mode (marketplace-based):
    - Marketplace subscription status
    - Admin overrides
    - Free trial status
    - Account type field
    
    Priority order (cloud mode):
    1. Admin override (if set and not expired)
    2. Marketplace plan (if active and not cancelled)
    3. Free trial (if active)
    4. Account type field (fallback)
    
    Priority order (self-hosted mode):
    1. Admin override (if set and not expired)
    2. Installation license tier (from license.get_installation_tier())
    
    Args:
        account: Account object
        
    Returns:
        Effective tier name: "free", "professional", or "enterprise"
    """
    # Check for admin override (applies in both modes)
    if _is_admin_override_active(account):
        return normalize_tier_name(account.account_type)
    
    # Self-hosted mode: use license tier
    if INSTALLATION_MODE == "self-hosted":
        return license.get_installation_tier()
    
    # Cloud mode: use marketplace subscription logic
    # Check marketplace subscription
    if _is_marketplace_subscription_active(account):
        return normalize_tier_name(account.marketplace_plan)
    
    # Fallback to account_type field
    return normalize_tier_name(account.account_type)


def normalize_tier_name(tier: Optional[str]) -> str:
    """
    Normalize tier name to standard values.
    
    Args:
        tier: Tier name (may be null, varied case, or "pro" vs "professional")
        
    Returns:
        Normalized tier: "free", "professional", or "enterprise"
    """
    if not tier:
        return "free"
    
    tier_lower = tier.lower()
    
    # Handle "pro" as alias for "professional"
    if tier_lower in ["pro", "professional"]:
        return "professional"
    
    # Handle enterprise
    if tier_lower == "enterprise":
        return "enterprise"
    
    # Default to free for unknown tiers
    return "free"


def get_tier_limits(tier: str) -> dict:
    """
    Get limits for a given tier.
    
    Args:
        tier: Tier name ("free", "professional", "enterprise")
        
    Returns:
        Dictionary of tier limits
    """
    normalized_tier = normalize_tier_name(tier)
    return TIER_LIMITS.get(normalized_tier, TIER_LIMITS["free"])


def get_run_history_days(account: Account) -> Optional[int]:
    """How many days of workflow-run history this account can see.

    Returns a value instead of the usual ``(allowed, message)`` pair because the
    requested window is clamped rather than rejected: asking for a year of
    history on a tier that keeps a month should show the month, not an error.

    ``None`` means unlimited.
    """
    if is_self_hosted_beta():
        return SELF_HOSTED_BETA_LIMITS["run_history_days"]

    limits = get_tier_limits(get_effective_tier(account))
    return limits["run_history_days"]


def check_project_limit(account: Account, current_count: int) -> Tuple[bool, Optional[str]]:
    """
    Check if account can create another project.

    In self-hosted beta mode this delegates to the total beta project count
    (standard + rwx combined), which is 4 + 2 = 6. For per-type enforcement
    use :func:`check_project_type_limit` instead.

    Args:
        account: Account object
        current_count: Current number of projects (all types combined)

    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    if is_self_hosted_beta():
        beta_total = (
            SELF_HOSTED_BETA_LIMITS["standard_projects"]
            + SELF_HOSTED_BETA_LIMITS["rwx_projects"]
        )
        if current_count >= beta_total:
            return False, (
                f"Self-hosted beta allows up to {SELF_HOSTED_BETA_LIMITS['standard_projects']} "
                f"Caller Workflow Projects and {SELF_HOSTED_BETA_LIMITS['rwx_projects']} "
                f"Reusable Workflow Projects. You have reached the total beta project limit."
            )
        return True, None

    tier = get_effective_tier(account)
    limits = get_tier_limits(tier)
    max_projects = limits["projects"]

    # Unlimited
    if max_projects is None:
        return True, None

    # Check limit
    if current_count >= max_projects:
        if tier == "free":
            return False, f"Free accounts can only create up to {max_projects} projects. Upgrade to Professional for up to 10 projects."
        elif tier == "professional":
            return False, f"Professional accounts can create up to {max_projects} projects. Upgrade to Enterprise for unlimited projects."
        else:
            return False, f"Project limit of {max_projects} reached for your account tier."

    return True, None


def check_project_type_limit(
    current_standard_count: int,
    current_rwx_count: int,
    project_type: str,
) -> Tuple[bool, Optional[str]]:
    """
    Check if a new project of the given type can be created in self-hosted beta.

    This is only meaningful in self-hosted beta mode; in cloud mode this always
    returns ``(True, None)`` because tier enforcement goes through
    :func:`check_project_limit` instead.

    Args:
        current_standard_count: Current number of standard (caller) projects.
        current_rwx_count: Current number of rwx (reusable workflow) projects.
        project_type: ``"standard"`` or ``"rwx"``.

    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    if not is_self_hosted_beta():
        return True, None

    if project_type == "rwx":
        limit = SELF_HOSTED_BETA_LIMITS["rwx_projects"]
        if current_rwx_count >= limit:
            return False, (
                f"Self-hosted beta allows up to {limit} Reusable Workflow Project(s). "
                f"You have reached the beta limit for Reusable Workflow Projects. "
                f"Paid plans are not available during the self-hosted beta."
            )
    else:
        # "standard" and any unrecognised project type
        limit = SELF_HOSTED_BETA_LIMITS["standard_projects"]
        if current_standard_count >= limit:
            return False, (
                f"Self-hosted beta allows up to {limit} Caller Workflow Project(s). "
                f"You have reached the beta limit for Caller Workflow Projects. "
                f"Paid plans are not available during the self-hosted beta."
            )

    return True, None


def check_private_repo_access(account: Account) -> Tuple[bool, Optional[str]]:
    """
    Check if account can access private repositories.

    Private repositories are part of the core product and are available on
    every tier. This function is retained for backwards compatibility but
    always returns ``(True, None)``.

    Args:
        account: Account object

    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    return True, None


def check_private_visibility_scope(account: Account) -> Tuple[bool, Optional[str]]:
    """
    Check if an account can create a project whose
    ``repository_visibility_scope`` is ``"private"``.

    In self-hosted beta, private repositories are always allowed when the
    user's GitHub credentials have access. On cloud, Free tier users may
    only create public-scope projects; Professional and Enterprise users
    may create private-scope projects.

    Args:
        account: Account object

    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    # In self-hosted beta, private repos are allowed regardless of stored tier.
    if is_self_hosted_beta():
        return True, None

    tier = get_effective_tier(account)
    if tier == "free":
        return False, (
            "Free accounts can only create public repository projects. "
            "Upgrade to Professional or Enterprise to create private repository projects."
        )
    return True, None


def check_repo_limit(account: Account, repo_count: int) -> Tuple[bool, Optional[str]]:
    """
    Check if account can add repos to a project.
    
    Args:
        account: Account object
        repo_count: Number of repos being added
        
    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    tier = get_effective_tier(account)
    limits = get_tier_limits(tier)
    max_repos = limits["repos_per_project"]
    
    # Unlimited
    if max_repos is None:
        return True, None
    
    # Check limit
    if repo_count > max_repos:
        if tier == "free":
            professional_max_repos = get_tier_limits("professional")["repos_per_project"]
            return False, f"You've reached the Free tier limit of {max_repos} repositories per project. Upgrade to Professional to manage up to {professional_max_repos} repositories per project."
        elif tier == "professional":
            return False, f"You've reached the Professional tier limit of {max_repos} repositories per project. Upgrade to Enterprise for unlimited repositories."
        else:
            return False, f"Repository limit of {max_repos} per project reached for your account tier."
    
    return True, None


def check_secrets_limit(account: Account, secret_count: int) -> Tuple[bool, Optional[str]]:
    """
    Check if account can add secrets to a project.
    
    Args:
        account: Account object
        secret_count: Number of secrets being added
        
    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    if is_self_hosted_beta():
        max_secrets = SELF_HOSTED_BETA_LIMITS["secrets_per_project"]
        if secret_count > max_secrets:
            return False, (
                f"Self-hosted beta allows up to {max_secrets} secrets per project. "
                f"You have reached the beta limit for secrets. "
                f"Paid plans are not available during the self-hosted beta."
            )
        return True, None

    tier = get_effective_tier(account)
    limits = get_tier_limits(tier)
    max_secrets = limits["secrets_per_project"]
    
    # Unlimited
    if max_secrets is None:
        return True, None
    
    # Check limit
    if secret_count > max_secrets:
        if tier == "free":
            return False, f"Free accounts can only have up to {max_secrets} secrets per project. Upgrade to Professional for up to 10 secrets."
        elif tier == "professional":
            return False, f"Professional accounts can have up to {max_secrets} secrets per project. Upgrade to Enterprise for unlimited secrets."
        else:
            return False, f"Secret limit of {max_secrets} per project reached for your account tier."
    
    return True, None


def check_env_var_limit(current_count: int, new_count: int) -> Tuple[bool, Optional[str]]:
    """
    Check if adding environment variables would exceed the self-hosted beta limit.

    Only enforced in self-hosted beta mode; always returns ``(True, None)`` in
    cloud mode (cloud enforcement is handled separately via account tier).

    Args:
        current_count: Current number of environment variables in the project.
        new_count: Number of new environment variables being added.

    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    if not is_self_hosted_beta():
        return True, None

    limit = SELF_HOSTED_BETA_LIMITS["env_vars_per_project"]
    if current_count + new_count > limit:
        return False, (
            f"Self-hosted beta allows up to {limit} environment variables per project. "
            f"You currently have {current_count} and are trying to add {new_count} new variable(s). "
            f"Paid plans are not available during the self-hosted beta."
        )
    return True, None


def check_environment_limit(current_count: int, new_count: int = 1) -> Tuple[bool, Optional[str]]:
    """
    Check if adding GitHub deployment environments would exceed the self-hosted beta limit.

    Only enforced in self-hosted beta mode; always returns ``(True, None)`` in
    cloud mode.

    Args:
        current_count: Current number of deployment environments in the project.
        new_count: Number of new environments being created (default 1).

    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    if not is_self_hosted_beta():
        return True, None

    limit = SELF_HOSTED_BETA_LIMITS["environments_per_project"]
    if current_count + new_count > limit:
        return False, (
            f"Self-hosted beta allows up to {limit} GitHub environments per project. "
            f"You currently have {current_count} environment(s). "
            f"Paid plans are not available during the self-hosted beta."
        )
    return True, None


def should_retain_data_on_downgrade(account: Account) -> bool:
    """
    Determine if account data should be retained during downgrade.
    
    Retention policy:
    - Keep data for RETENTION_PERIOD_DAYS after downgrade/cancellation
    - After retention period, data may be subject to cleanup
    
    Args:
        account: Account object
        
    Returns:
        bool: True if data should be retained, False if cleanup allowed
    """
    # If marketplace was recently updated to free (cancelled)
    if account.marketplace_updated_at:
        # Ensure both datetimes are timezone-aware
        updated_at = account.marketplace_updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        
        days_since_update = (datetime.now(timezone.utc) - updated_at).days
        
        # Check if within retention period
        if days_since_update < RETENTION_PERIOD_DAYS:
            return True
        else:
            # Past retention period, cleanup allowed
            return False
    
    # Default: retain data (conservative approach - no update time recorded)
    return True


def set_admin_override(account: Account, new_tier: str, duration_days: Optional[int] = None):
    """
    Set an admin override for account tier.
    
    This prevents marketplace webhooks from changing the tier until the override expires.
    
    Args:
        account: Account object
        new_tier: New tier to set
        duration_days: How long the override lasts (None = indefinite)
    """
    account.account_type = normalize_tier_name(new_tier)
    account.admin_override = True
    
    if duration_days:
        account.admin_override_until = datetime.now(timezone.utc) + timedelta(days=duration_days)
    else:
        account.admin_override_until = None


def clear_admin_override(account: Account):
    """
    Clear admin override, allowing marketplace to control tier again.
    
    Args:
        account: Account object
    """
    account.admin_override = False
    account.admin_override_until = None


def sync_tier_with_marketplace(account: Account):
    """
    Sync account tier with marketplace subscription, respecting admin overrides.
    
    This should be called after webhook processing to ensure tier is current.
    
    Args:
        account: Account object
    """
    # Don't override if admin override is active
    if hasattr(account, 'admin_override') and account.admin_override:
        if hasattr(account, 'admin_override_until'):
            if account.admin_override_until is None or account.admin_override_until > datetime.now(timezone.utc):
                # Admin override still active, don't sync
                return
    
    # Sync tier from marketplace
    effective_tier = get_effective_tier(account)
    account.account_type = effective_tier
