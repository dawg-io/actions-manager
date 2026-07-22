"""
Configuration Module for ActionsManager.xyz

Handles application configuration including installation mode detection.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Valid installation modes
VALID_MODES = {"cloud", "self-hosted"}

# Default installation mode
DEFAULT_MODE = "self-hosted"


def get_installation_mode() -> str:
    """
    Get the installation mode from environment variable.
    
    Returns:
        str: The installation mode ('cloud' or 'self-hosted')
        
    Raises:
        ValueError: If INSTALLATION_MODE is set to an invalid value
    """
    mode = os.getenv("INSTALLATION_MODE", "").strip().lower()
    
    # Use default if not set or empty
    if not mode:
        return DEFAULT_MODE
    
    # Validate the mode
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid INSTALLATION_MODE: '{mode}'. "
            f"Must be one of: {', '.join(sorted(VALID_MODES))}"
        )
    
    return mode


# Initialize installation mode at module load
INSTALLATION_MODE = get_installation_mode()


# License configuration for self-hosted installations
LICENSE_KEY = os.getenv("LICENSE_KEY", "").strip()


def get_cors_allowed_origins() -> list[str]:
    """
    Resolve the list of allowed CORS origins.

    Resolution order:
      1. ``CORS_ALLOWED_ORIGINS`` env var (comma-separated list of origins).
      2. ``VITE_FRONTEND_URL`` env var (Vite-era explicit frontend URL).
      3. ``REACT_APP_FRONTEND_URL`` env var (legacy explicit frontend URL).
      4. ``VITE_APP_URL`` env var (Vite-era simplified self-hosted config).
      5. ``APP_URL`` env var (legacy simplified self-hosted config).
      6. Wildcard ``["*"]`` as a last-resort fallback. Callers should treat
         ``"*"`` as "credentials must not be allowed" — see
         :func:`cors_allow_credentials`.
    """
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if origins:
            return origins

    for env_var in ("VITE_FRONTEND_URL", "REACT_APP_FRONTEND_URL", "APP_URL", "VITE_APP_URL"):
        url = os.getenv(env_var, "").strip().rstrip("/")
        if url:
            return [url]

    print(
        "WARNING: CORS_ALLOWED_ORIGINS is not configured. Defaulting to wildcard ('*'), "
        "which allows cross-origin Bearer-token requests from any site. "
        "Set CORS_ALLOWED_ORIGINS or APP_URL (VITE_FRONTEND_URL) to your frontend origin "
        "for any non-localhost deployment.",
        file=sys.stderr,
    )
    return ["*"]


def cors_allow_credentials(origins: list[str]) -> bool:
    """
    Return whether credentialed CORS requests should be allowed.

    Credentialed requests (cookies / Authorization headers) MUST NOT be
    combined with a wildcard ``"*"`` origin — browsers reject this and it
    is also a misconfiguration that allows any site to make authenticated
    cross-origin requests if a server echoes the request Origin.
    """
    return "*" not in origins


def is_api_docs_disabled() -> bool:
    """
    Determine whether FastAPI interactive docs should be disabled.

    Docs are disabled when:
      - ``DISABLE_API_DOCS=true`` (explicit opt-out), OR
      - ``ENVIRONMENT=production`` (auto-disable in production).

    Docs remain enabled by default for local development
    (``ENVIRONMENT=development`` or unset without explicit disable).
    """
    explicit = os.getenv("DISABLE_API_DOCS", "").strip().lower()
    if explicit == "true":
        return True
    if explicit == "false":
        return False
    # Auto-disable in production environment
    from mode_validation import get_environment
    return get_environment() == "production"


# Resolve once at module load
CORS_ALLOWED_ORIGINS = get_cors_allowed_origins()
CORS_ALLOW_CREDENTIALS = cors_allow_credentials(CORS_ALLOWED_ORIGINS)
API_DOCS_DISABLED = is_api_docs_disabled()
