"""
License Key Validation Module for ActionsManager.xyz

Provides JWT-based license key validation for self-hosted installations.
Validates license tier and expiration without requiring network calls.
Uses RS256 (asymmetric) signing: the vendor's private key signs licenses,
and the public key embedded here verifies them. Customers cannot forge
licenses even with full access to this source code.
"""

import os
import jwt
from typing import Optional, Tuple
import config


# ============================================================
# LICENSE PUBLIC KEY
# Replace this placeholder with your actual RSA public key.
# Generate a key pair with:
#   openssl genrsa -out private_key.pem 2048
#   openssl rsa -in private_key.pem -pubout -out public_key.pem
# NEVER commit private_key.pem to version control.
# The public key below is safe to include in source code.
# ============================================================
LICENSE_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
REPLACE_THIS_WITH_YOUR_ACTUAL_RSA_PUBLIC_KEY_GENERATED_BY_OPENSSL
-----END PUBLIC KEY-----"""

_PLACEHOLDER_TEXT = "REPLACE_THIS_WITH_YOUR_ACTUAL_RSA_PUBLIC_KEY_GENERATED_BY_OPENSSL"


def _warn_if_placeholder():
    """Emit a warning if the public key has not been replaced."""
    if _PLACEHOLDER_TEXT in LICENSE_PUBLIC_KEY:
        print(
            "⚠️  WARNING: backend/license.py still contains the placeholder public key.\n"
            "   License validation will fail for all keys until you replace it.\n"
            "   Generate a key pair with:\n"
            "     openssl genrsa -out private_key.pem 2048\n"
            "     openssl rsa -in private_key.pem -pubout -out public_key.pem\n"
            "   Then paste the contents of public_key.pem into LICENSE_PUBLIC_KEY."
        )


# Warn at import time so problems are visible in application logs
_warn_if_placeholder()


# Cache for installation tier to avoid repeated validation
_cached_tier: Optional[str] = None
_cache_initialized: bool = False


def validate_license_key(license_key: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate a JWT license key and extract tier and expiration information.

    Verification uses RS256 with the embedded ``LICENSE_PUBLIC_KEY``. The
    matching private key is held exclusively by the vendor and is never
    distributed, so customers cannot forge licenses even with full source
    access.

    Args:
        license_key: The JWT license key to validate

    Returns:
        Tuple of (valid: bool, tier: Optional[str], error_message: Optional[str])
        - valid: True if license is valid and not expired
        - tier: The tier from the license ("free", "professional", "enterprise") if valid
        - error_message: Error message if validation fails
    """
    if not license_key:
        return False, None, "License key not provided"

    try:
        payload = jwt.decode(
            license_key,
            LICENSE_PUBLIC_KEY,
            algorithms=["RS256"]
        )

        # Extract tier from payload
        tier = payload.get("tier")
        if not tier:
            return False, None, "License key missing 'tier' field"

        # Normalize tier name
        normalized_tier = _normalize_tier(tier)

        return True, normalized_tier, None

    except jwt.ExpiredSignatureError:
        return False, None, "License key has expired"
    except jwt.InvalidSignatureError:
        return False, None, "Invalid license key signature"
    except jwt.DecodeError:
        return False, None, "Invalid license key format"
    except Exception as e:
        return False, None, f"License validation error: {str(e)}"


def _normalize_tier(tier: str) -> str:
    """
    Normalize tier name to standard values.

    Args:
        tier: Tier name from license

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


def get_installation_tier() -> str:
    """
    Get the installation tier from license validation.

    This function caches the result on first call to avoid repeated validation.
    The cache persists for the lifetime of the application.

    For self-hosted installations:
    - Validates LICENSE_KEY using the embedded RS256 public key
    - Returns tier from valid license
    - Falls back to "free" tier if license is invalid, expired, or absent

    For cloud installations:
    - Always returns "free" (tier managed through marketplace)

    Returns:
        str: The installation tier ("free", "professional", or "enterprise")
    """
    global _cached_tier, _cache_initialized

    # Return cached result if already initialized
    if _cache_initialized:
        return _cached_tier

    # For cloud mode, always return free (marketplace handles tier)
    if config.INSTALLATION_MODE == "cloud":
        _cached_tier = "free"
        _cache_initialized = True
        return _cached_tier

    # For self-hosted mode, validate license
    license_key = os.getenv("LICENSE_KEY", "").strip()

    # If no license provided, default to free tier
    if not license_key:
        _cached_tier = "free"
        _cache_initialized = True
        return _cached_tier

    # Validate the license using the embedded RS256 public key
    valid, tier, error_msg = validate_license_key(license_key)

    if valid:
        _cached_tier = tier
        _cache_initialized = True
        return _cached_tier
    else:
        # Log the error for debugging
        print(f"⚠️  License validation failed: {error_msg}")
        print(f"⚠️  Falling back to free tier")
        _cached_tier = "free"
        _cache_initialized = True
        return _cached_tier


def reset_cache():
    """
    Reset the cached installation tier.

    This is primarily useful for testing purposes to force re-validation
    of the license key.
    """
    global _cached_tier, _cache_initialized
    _cached_tier = None
    _cache_initialized = False
