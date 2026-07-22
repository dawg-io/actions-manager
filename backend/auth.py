import base64
import contextvars
import hashlib
import hmac as _hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import requests
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import config
import license
from database import SessionLocal, get_db
from github_permissions import (
    CredentialSource,
    GitHubPermissionValidator,
    PermissionStatus,
    TokenType,
    format_permission_issues_for_user,
)
from models import Account, AuthSession, WorkspaceMember  # ✅ Import the Account and WorkspaceMember models

router = APIRouter()

# ✅ GitHub OAuth credentials
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "").strip()
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "").strip()

# URL configuration — priority order (highest wins):
#   1. VITE_BACKEND_URL / VITE_FRONTEND_URL (explicit per-service override)
#   2. REACT_APP_BACKEND_URL / REACT_APP_FRONTEND_URL (legacy override)
#   3. APP_URL (primary simplified self-hosted config)
#   4. VITE_APP_URL (deprecated alias for APP_URL, still honored)
# Empty string means the frontend auto-detects via window.location.
APP_URL = os.getenv("APP_URL", "").strip().rstrip("/")
_VITE_APP_URL = os.getenv("VITE_APP_URL", "").strip().rstrip("/")
_app_url_fallback = APP_URL or _VITE_APP_URL
BACKEND_URL = (
    os.getenv("VITE_BACKEND_URL", "").strip()
    or os.getenv("REACT_APP_BACKEND_URL", "").strip()
    or _app_url_fallback
).rstrip("/")
FRONTEND_URL = (
    os.getenv("VITE_FRONTEND_URL", "").strip()
    or os.getenv("REACT_APP_FRONTEND_URL", "").strip()
    or _app_url_fallback
).rstrip("/")

# ✅ Mock toggle for development
USE_MOCK_RESPONSES = os.getenv("USE_MOCK_RESPONSES", "false").lower() == "true"

# ✅ Debugging toggle - Defaults to false for production safety
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
INVALID_SAVED_TOKEN_SENTINEL = "ghp_invalid_saved_token"
GITHUB_TOKEN_PATTERN = re.compile(r"^(gh[opus]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)$")
AUTHORIZATION_PATTERN = re.compile(r"(authorization\s*[:=]\s*)(token\s+)?[^\s,]+", re.IGNORECASE)
SESSION_COOKIE_NAME = "actions_manager_session"
SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(7 * 24 * 60 * 60)))
USER_NOT_FOUND_ERROR = "User not found"
_request_github_user: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "actions_manager_request_github_user",
    default=None,
)

# Security: Allow insecure HTTP for PAT login only when explicitly enabled
ALLOW_INSECURE_HTTP = os.getenv("ALLOW_INSECURE_HTTP", "false").lower() == "true"


def _is_localhost(host: str) -> bool:
    """
    Check if a host is localhost or a local IP address.
    
    Args:
        host: The hostname or IP address to check
        
    Returns:
        True if the host is local, False otherwise
    """
    if not host:
        return False
    
    # Remove port if present
    if host.startswith("[") and "]" in host:
        # IPv6 with port (e.g., "[::1]:8080")
        host = host[1:host.index("]")]
    elif ":" in host and host.count(":") == 1:
        # IPv4 with port (e.g., "127.0.0.1:8080")
        # Only split if there's exactly one colon (IPv4:port, not IPv6)
        host = host.split(":")[0]
    # If multiple colons and no brackets, it's probably IPv6 without port
    
    # Check for localhost names and loopback IPs
    localhost_names = {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "::",  # IPv6 any address
    }
    
    return host.lower() in localhost_names


def _validate_secure_connection(request: Request) -> None:
    """
    Validate that the request is secure (HTTPS) or from localhost.
    
    Raises HTTPException if the connection is insecure and not explicitly allowed.
    
    Args:
        request: The FastAPI request object
        
    Raises:
        HTTPException: If the connection is insecure and ALLOW_INSECURE_HTTP is not set
    """
    if ALLOW_INSECURE_HTTP:
        return
    
    # Check if connection is using HTTPS
    # X-Forwarded-Proto is set by reverse proxies
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()
    is_https = (
        forwarded_proto == "https" 
        or request.url.scheme == "https"
    )
    
    if is_https:
        return
    
    # Check if the actual client connection is from localhost (not the client-supplied Host header)
    client_ip = request.client.host if request.client else ""
    if client_ip in {"127.0.0.1", "::1", "localhost"}:
        return
    
    # Connection is insecure and not from localhost
    raise HTTPException(
        status_code=400,
        detail=(
            "PAT login over non-local HTTP is disabled for security. "
            "Use HTTPS or set ALLOW_INSECURE_HTTP=true to override. "
            "See documentation for HTTPS setup with reverse proxies."
        ),
    )


_PAT_KDF_ITERATIONS = 600_000


def _get_token_cipher() -> Optional[Fernet]:
    if not SECRET_KEY:
        return None
    # Derive a deployment-unique salt from SECRET_KEY so the salt is not a
    # hardcoded constant (satisfies S2053) while remaining deterministic across
    # restarts (required for decryption to work without storing the salt separately).
    salt = _hmac.new(SECRET_KEY.encode("utf-8"), b"actionsmanager-pat-kdf-salt-v1", "sha256").digest()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PAT_KDF_ITERATIONS,
    )
    derived_key = base64.urlsafe_b64encode(kdf.derive(SECRET_KEY.encode("utf-8")))
    return Fernet(derived_key)


def _get_legacy_cipher() -> Optional[Fernet]:
    """SHA-256 cipher used before the PBKDF2HMAC upgrade — decrypt-only for existing PATs."""
    if not SECRET_KEY:
        return None
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode("utf-8")).digest())
    return Fernet(derived_key)


def _encrypt_saved_token(raw_token: str) -> str:
    cipher = _get_token_cipher()
    if cipher is None:
        raise HTTPException(
            status_code=503,
            detail="SECRET_KEY must be configured before storing a personal access token.",
        )
    return cipher.encrypt(raw_token.encode("utf-8")).decode("utf-8")


def _decrypt_saved_token(encrypted_token: str) -> str:
    cipher = _get_token_cipher()
    if cipher is None:
        raise ValueError("SECRET_KEY is not configured")
    try:
        return cipher.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        pass
    # Fall back to the legacy SHA-256 cipher for PATs encrypted before the KDF upgrade.
    legacy = _get_legacy_cipher()
    if legacy:
        try:
            return legacy.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            pass
    raise ValueError("Stored personal access token could not be decrypted")


def _normalize_saved_token_type(token_type: Optional[str]) -> Optional[str]:
    if not token_type:
        return None
    if isinstance(token_type, TokenType):
        return token_type.value
    return str(token_type)


def _user_pat_status_payload(user: Account) -> dict:
    configured = bool(user.github_pat_token_encrypted)
    status = user.github_pat_status or ("configured" if configured else "not_configured")
    if not configured:
        message = "No personal access token configured."
    elif status == PermissionStatus.TOKEN_INVALID:
        message = "Stored token is invalid or expired."
    elif status in {PermissionStatus.MISSING_SCOPES, PermissionStatus.INSUFFICIENT_REPO_PERMISSIONS}:
        message = "Stored token is missing required permissions for one or more Actions Manager features."
    elif status == PermissionStatus.MISSING_REPO_ACCESS:
        message = "Stored token cannot access any repositories."
    elif status == PermissionStatus.MISSING_ORG_APPROVAL:
        message = "Organization policies are blocking this stored token."
    else:
        message = "Token configured."
    return {
        "configured": configured,
        "status": status,
        "message": message,
        "token_type": _normalize_saved_token_type(user.github_pat_token_type),
        "checked_at": user.github_pat_checked_at.isoformat() if user.github_pat_checked_at else None,
        "updated_at": user.github_pat_updated_at.isoformat() if user.github_pat_updated_at else None,
    }


def _load_saved_personal_access_token(username: str) -> Optional[str]:
    db = SessionLocal()
    try:
        try:
            user = db.query(Account).filter(Account.github_user == username).first()
        except Exception:
            return None
        if not user or not getattr(user, "github_pat_token_encrypted", None):
            return None
        try:
            return _decrypt_saved_token(user.github_pat_token_encrypted)
        except ValueError:
            return INVALID_SAVED_TOKEN_SENTINEL
    finally:
        db.close()


_PAT_CACHE_TTL = 300  # seconds; cached PAT stays valid for 5 minutes


class GitHubCredentialStore:
    """OAuth session tokens with database-backed PAT fallback/preference."""

    def __init__(self) -> None:
        self._oauth_tokens: dict[str, str] = {}
        # Cache: username -> (token_or_None, monotonic_expiry)
        self._pat_cache: dict[str, tuple[Optional[str], float]] = {}

    def _cached_pat(self, username: str) -> Optional[str]:
        """Return a PAT from the in-memory cache, refreshing from DB on miss/expiry."""
        now = time.monotonic()
        if username in self._pat_cache:
            token, expires_at = self._pat_cache[username]
            if now < expires_at:
                return token
        token = _load_saved_personal_access_token(username)
        self._pat_cache[username] = (token, now + _PAT_CACHE_TTL)
        return token

    def invalidate_pat(self, username: str) -> None:
        """Evict a username's PAT cache entry (call after save or remove)."""
        self._pat_cache.pop(username, None)

    def _allowed_for_request(self, username: str) -> bool:
        current_user = get_request_user()
        return current_user is None or current_user.lower() == username.lower()

    def __contains__(self, username: object) -> bool:
        if not isinstance(username, str):
            return False
        if not self._allowed_for_request(username):
            return False
        if username in self._oauth_tokens:
            return True
        return self._cached_pat(username) is not None

    def __getitem__(self, username: str) -> str:
        if not self._allowed_for_request(username):
            raise KeyError(username)
        saved_token = self._cached_pat(username)
        if saved_token is not None:
            return saved_token
        return self._oauth_tokens[username]

    def get(self, username: str, default=None):
        try:
            return self[username]
        except KeyError:
            return default

    def __setitem__(self, username: str, token: str) -> None:
        self._oauth_tokens[username] = token

    def __delitem__(self, username: str) -> None:
        del self._oauth_tokens[username]

    def pop(self, username: str, default=None):
        return self._oauth_tokens.pop(username, default)

    def clear(self) -> None:
        self._oauth_tokens.clear()

    def copy(self) -> dict[str, str]:
        return self._oauth_tokens.copy()

    def update(self, values) -> None:
        self._oauth_tokens.update(values)

    def keys(self):
        return self._oauth_tokens.keys()


# ✅ Store authenticated users' tokens (temporary memory storage + persisted PAT lookup)
user_tokens = GitHubCredentialStore()


class OAuthStateStore:
    """
    Temporary storage for OAuth state parameters with TTL for CSRF protection.
    
    Each state is stored with a creation timestamp and automatically expires after
    STATE_TTL seconds. States are single-use: they are deleted after validation.
    """
    STATE_TTL = 600  # 10 minutes in seconds
    
    def __init__(self) -> None:
        self._states: dict[str, float] = {}  # state -> creation_timestamp
    
    def create(self) -> str:
        """Generate a new cryptographically secure state parameter and store it."""
        state = secrets.token_urlsafe(32)
        self._states[state] = time.monotonic()
        self._cleanup_expired()
        return state
    
    def validate_and_consume(self, state: str) -> bool:
        """
        Validate a state parameter and consume it (single-use).
        
        Returns True if the state is valid and not expired.
        Returns False if the state is missing, expired, or invalid.
        """
        self._cleanup_expired()
        
        if state not in self._states:
            return False
        
        created_at = self._states.pop(state)  # Single-use: delete immediately
        age = time.monotonic() - created_at
        
        return age <= self.STATE_TTL
    
    def _cleanup_expired(self) -> None:
        """Remove expired state entries."""
        now = time.monotonic()
        expired = [
            state for state, created_at in self._states.items()
            if (now - created_at) > self.STATE_TTL
        ]
        for state in expired:
            del self._states[state]


# ✅ Store OAuth state parameters for CSRF protection
oauth_states = OAuthStateStore()

# ✅ Utility function to get the correct API endpoints based on account type
def get_github_api_endpoints(username, db_session=None):
    """
    Get the correct GitHub API endpoints based on whether the account is a User or Organization.
    
    Args:
        username: GitHub username
        db_session: Database session to lookup account type (optional)
    
    Returns:
        dict: Dictionary containing the correct API endpoints for the account type
    """
    # constants.py (or at the top of your module)
    GITHUB_API_BASE = "https://api.github.com"
    MARKETPLACE_PURCHASES_ENDPOINT = f"{GITHUB_API_BASE}/user/marketplace_purchases"

    # usage
    endpoints = {
        "repos_list": f"{GITHUB_API_BASE}/user/repos",
        "repos_create": f"{GITHUB_API_BASE}/user/repos",
        "marketplace": MARKETPLACE_PURCHASES_ENDPOINT,
        "account_type": "User"
    }

    # Try to get account type from database if session provided
    if db_session:
        try:
            from models import Account
            user = db_session.query(Account).filter(Account.github_user == username).first()
            if user and user.github_account_type == "Organization":
                endpoints = {
                    "repos_list": f"{GITHUB_API_BASE}/orgs/{username}/repos",
                    "repos_create": f"{GITHUB_API_BASE}/orgs/{username}/repos",
                    "marketplace": MARKETPLACE_PURCHASES_ENDPOINT,  # Use user endpoint for organizations too
                    "account_type": "Organization"
                }
        except Exception as e:
            debug_log(f"⚠️ Warning: Could not determine account type for {username}: {e}")
    
    return endpoints

# ✅ Database dependency


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def extract_session_token(request: Request) -> Optional[str]:
    """Read the opaque app session token from Authorization or the HttpOnly cookie."""
    bearer_token = _extract_bearer_token(request.headers.get("Authorization"))
    if bearer_token:
        return bearer_token
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    return cookie_token.strip() if cookie_token else None


def create_auth_session(username: str, db: Session) -> str:
    """Create a new opaque login session and store only its hash server-side."""
    raw_token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_hash_session_token(raw_token),
            github_user=username,
            expires_at=_now_utc() + timedelta(seconds=SESSION_TTL_SECONDS),
        )
    )
    db.commit()
    return raw_token


def _cookie_secure(request: Request) -> bool:
    return (
        request.headers.get("X-Forwarded-Proto", "").lower() == "https"
        or request.url.scheme == "https"
    )


def set_session_cookie(response: Response, request: Request, session_token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def set_request_user(username: str):
    return _request_github_user.set(username)


def reset_request_user(token) -> None:
    _request_github_user.reset(token)


def get_request_user() -> Optional[str]:
    return _request_github_user.get()


def resolve_authenticated_user(request: Request, db: Session) -> Account:
    """
    Resolve the authenticated user from the server-issued session token.

    X-GitHub-User is accepted only as an optional consistency check and is never
    used as the source of identity.
    """
    session_token = extract_session_token(request)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == _hash_session_token(session_token))
        .first()
    )
    if not session or session.revoked_at is not None or _as_utc(session.expires_at) <= _now_utc():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired",
        )

    claimed_user = request.headers.get("X-GitHub-User", "").strip()
    if claimed_user and claimed_user.lower() != session.github_user.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated session does not match X-GitHub-User",
        )

    user = db.query(Account).filter(Account.github_user == session.github_user).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=USER_NOT_FOUND_ERROR)

    request.state.github_user = user.github_user
    return user


def revoke_current_session(request: Request, db: Session) -> Optional[str]:
    session_token = extract_session_token(request)
    if not session_token:
        return None

    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == _hash_session_token(session_token))
        .first()
    )
    if not session:
        return None

    session.revoked_at = _now_utc()
    db.commit()
    return session.github_user

# ✅ Debugging helper function
def _redact_sensitive_text(message_text: str) -> str:
    redacted = AUTHORIZATION_PATTERN.sub(r"\1[REDACTED]", message_text)
    redacted = GITHUB_TOKEN_PATTERN.sub("[REDACTED_TOKEN]", redacted)
    return redacted


def debug_log(message):
    if DEBUG_MODE:
        message_text = str(message)
        sensitive_markers = ("token", "authorization", "client_secret", "access_token")
        if any(marker in message_text.lower() for marker in sensitive_markers):
            print("🔒 Debug message redacted")
        else:
            print(f"ℹ️ {_redact_sensitive_text(message_text)}")


class GitHubTokenRequest(BaseModel):
    token: str


def _validate_github_token_format(token: str) -> str:
    cleaned_token = token.strip()
    if not cleaned_token:
        raise HTTPException(status_code=400, detail="GitHub token is required.")
    if not GITHUB_TOKEN_PATTERN.match(cleaned_token):
        raise HTTPException(
            status_code=400,
            detail=(
                "Token format looks invalid. Use a GitHub OAuth token, "
                "classic PAT, or fine-grained PAT."
            ),
        )
    return cleaned_token


def _validate_github_token(token: str) -> dict:
    validator = GitHubPermissionValidator(token)
    validation_result = validator.validate_all_permissions()
    validation_result["message"] = format_permission_issues_for_user(validation_result)
    return validation_result


def _public_validation_result(validation_result: dict) -> dict:
    public_result = dict(validation_result)
    if public_result.get("status") == PermissionStatus.UNKNOWN_ERROR:
        public_result["issues"] = ["GitHub token validation could not be completed."]
        public_result["warnings"] = []
        public_result["recommendations"] = ["Please try again. If the issue persists, contact support."]
        public_result["message"] = "⚠️ GitHub token validation could not be completed."
    return public_result


def _persist_pat_validation(user: Account, validation_result: dict) -> None:
    status = validation_result.get("status") or PermissionStatus.UNKNOWN_ERROR
    if isinstance(status, PermissionStatus):
        status = status.value
    public_validation = _public_validation_result(validation_result)
    user.github_pat_token_type = _normalize_saved_token_type(validation_result.get("details", {}).get("token_type"))
    user.github_pat_status = str(status)
    user.github_pat_last_error = public_validation.get("message")
    user.github_pat_checked_at = datetime.now(timezone.utc)


def _ensure_request_user(request: Request, username: str, db: Session) -> Account:
    request_user = resolve_authenticated_user(request, db)
    set_request_user(request_user.github_user)
    if request_user.github_user.lower() != username.lower():
        raise HTTPException(status_code=403, detail="You may only manage your own saved GitHub token.")
    return request_user

# ✅ Mock responses for testing
def get_mock_marketplace_purchases(username):
    """Simulate different plans for testing purposes."""
    mock_responses = {
        "free": [],
        "professional": [
            {
                "plan": {
                    "name": "professional",
                    "price": 4000
                },
                "unit_count": 1,
                "on_free_trial": False,
                "next_billing_date": "2025-06-01T00:00:00Z"
            }
        ],
        "enterprise": [
            {
                "plan": {
                    "name": "enterprise",
                    "price": 20000
                },
                "unit_count": 1,
                "on_free_trial": False,
                "next_billing_date": "2025-06-01T00:00:00Z"
            }
        ]
    }
    # Default to "free" if no specific mock plan is set
    return mock_responses.get(username, mock_responses["enterprise"])

def _exchange_code_for_token(code: str):
    """Exchange OAuth code for GitHub access token."""
    token_url = "https://github.com/login/oauth/access_token"
    response = requests.post(token_url, data={
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code
    }, headers={"Accept": "application/json"})

    token_data = response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        debug_log("❌ Error: Failed to retrieve access token")
        raise ValueError("GitHub authentication failed")

    debug_log("✅ Access token retrieved")
    return access_token

def _fetch_user_info(access_token: str):
    """Fetch user information from GitHub API."""
    user_response = requests.get("https://api.github.com/user", headers={
        "Authorization": f"token {access_token}"
    })
    
    if user_response.status_code != 200:
        debug_log(f"❌ Error: Failed to fetch user info, status: {user_response.status_code}")
        raise ValueError("Failed to fetch user information from GitHub")
        
    user_data = user_response.json()
    username = user_data.get("login")
    email = user_data.get("email") or f"{username}@users.noreply.github.com"
    avatar_url = user_data.get("avatar_url")
    github_account_type = _normalize_github_account_type(user_data.get("type"))

    if not username:
        debug_log("❌ Error: GitHub user not found in response")
        raise ValueError("GitHub user not found")

    debug_log(f"📌 Debug: GitHub user info received for {username} (GitHub account type: {github_account_type})")
    return username, email, avatar_url, github_account_type

def _fetch_marketplace_data(username: str, github_account_type: Optional[str], access_token: str):
    """Fetch marketplace data to determine user's billing plan."""
    if USE_MOCK_RESPONSES:
        debug_log("📌 Using mock marketplace purchases")
        return get_mock_marketplace_purchases(username)

    # Fetch marketplace data for both users and organizations
    billing_data = []
    try:
        billing_response = requests.get("https://api.github.com/user/marketplace_purchases", headers={
            "Authorization": f"token {access_token}"
        })
        if billing_response.status_code == 200:
            billing_data = billing_response.json()
            debug_log(f"📌 Debug: Marketplace data retrieved for {github_account_type} {username}: {len(billing_data)} purchase(s)")
        else:
            debug_log(f"📌 Warning: Marketplace API returned {billing_response.status_code} for {github_account_type}")
            billing_data = []
    except Exception as e:
        debug_log(f"📌 Warning: Failed to fetch marketplace data for {github_account_type} {username}: {e}")
        billing_data = []
    
    debug_log(f"📌 Debug: Final billing purchase count: {len(billing_data)}")
    return billing_data


def _extract_account_from_payload(payload: dict) -> tuple[Optional[str], Optional[str]]:
    """
    Extract a normalized GitHub account login/type pair from a GitHub payload.

    Returns:
        (account_login, account_type) when login exists; account_type is None when unknown.
        Returns (None, None) when extraction fails.
    """
    account = payload.get("account") if isinstance(payload, dict) else None
    if not isinstance(account, dict):
        return None, None

    account_login = account.get("login")
    account_type = _normalize_github_account_type(account.get("type"))
    if account_login:
        return account_login, account_type
    return None, None


def _fetch_installation_account(access_token: str) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch the GitHub App installation account available to the signed-in user.

    Returns:
        (account_login, account_type) or (None, None) if no installation is found or on error.
    """
    try:
        response = requests.get("https://api.github.com/user/installations", headers={
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github+json",
        })

        if response.status_code != 200:
            debug_log(f"📌 Warning: GitHub installations API returned {response.status_code}")
            return None, None

        installations = response.json().get("installations", [])
        if not installations:
            return None, None

        account_login, account_type = _extract_account_from_payload(installations[0])
        if account_login:
            debug_log(f"📌 Debug: GitHub App installation account resolved: {account_login} ({account_type})")
            return account_login, account_type
    except Exception as e:
        debug_log(f"📌 Warning: Failed to fetch GitHub App installation account: {e}")

    return None, None


def _resolve_connected_github_account(
    username: str,
    github_account_type: Optional[str],
    billing_data: list,
    access_token: str
) -> tuple[str, Optional[str]]:
    """
    Resolve the connected GitHub account, preferring GitHub App installation account data.

    Returns:
        (account_login, account_type), falling back to the signed-in username and normalized OAuth account type.
    """
    for purchase in billing_data:
        account_login, account_type = _extract_account_from_payload(purchase)
        if account_login:
            return account_login, account_type

    if USE_MOCK_RESPONSES:
        return username, _normalize_github_account_type(github_account_type)

    account_login, account_type = _fetch_installation_account(access_token)
    if account_login:
        return account_login, account_type

    return username, _normalize_github_account_type(github_account_type)

def _normalize_account_type(account_type: Optional[str]) -> str:
    """Normalize account type to lowercase, defaulting to 'unknown'."""
    return account_type.lower() if account_type else "unknown"


def _normalize_github_account_type(github_account_type: Optional[str]) -> Optional[str]:
    """Normalize GitHub account type to the supported API values."""
    if not github_account_type:
        return None

    normalized_type = github_account_type.strip().lower()
    if normalized_type == "user":
        return "User"
    if normalized_type == "organization":
        return "Organization"
    return None


def _update_user_fields(
    user: "Account",
    normalized_account_type: str,
    github_account_type: Optional[str],
    avatar_url: str,
    client_ip: Optional[str],
    connected_github_account: Optional[str] = None,
    connected_github_account_type: Optional[str] = None
) -> None:
    """Update mutable fields on an existing user record."""
    if user.account_type != normalized_account_type:
        user.account_type = normalized_account_type
    normalized_github_account_type = _normalize_github_account_type(github_account_type)
    if user.github_account_type != normalized_github_account_type:
        user.github_account_type = normalized_github_account_type
    normalized_connected_account_type = _normalize_github_account_type(connected_github_account_type)
    if user.connected_github_account != connected_github_account:
        user.connected_github_account = connected_github_account
    if user.connected_github_account_type != normalized_connected_account_type:
        user.connected_github_account_type = normalized_connected_account_type
    if user.avatar_url != avatar_url:
        user.avatar_url = avatar_url
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = client_ip


def _manage_user_in_database(
    username: str,
    email: str,
    github_account_type: Optional[str],
    avatar_url: str,
    billing_data: list,
    db: Session,
    client_ip: str = None,
    connected_github_account: Optional[str] = None,
    connected_github_account_type: Optional[str] = None
):
    """Create or update user in database."""
    # Determine account type based on installation mode
    if config.INSTALLATION_MODE == "self-hosted":
        # Self-hosted mode: use license tier for all users
        account_type = license.get_installation_tier()
        debug_log(f"📌 Debug: Self-hosted mode - using license tier: {account_type}")
    else:
        # Cloud mode: use billing data from marketplace
        account_type = "unknown"
        if billing_data:
            account_type = billing_data[0].get("plan", {}).get("name", "unknown")
        debug_log(f"📌 Debug: Cloud mode - account type from billing: {account_type}")

    # Find or create user
    user = db.query(Account).filter(Account.github_user == username).first()
    
    if not user:
        user = Account(
            github_user=username,
            github_email=email,
            account_type=_normalize_account_type(account_type),
            github_account_type=_normalize_github_account_type(github_account_type),
            connected_github_account=connected_github_account,
            connected_github_account_type=_normalize_github_account_type(connected_github_account_type),
            avatar_url=avatar_url,
            last_login_at=datetime.now(timezone.utc),
            last_login_ip=client_ip
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        debug_log(f"✅ New user created in database: {username} (Account Type: {account_type}, GitHub Type: {github_account_type}, Avatar URL: {avatar_url})")
    else:
        # Update user if necessary
        normalized_account_type = _normalize_account_type(account_type)
        _update_user_fields(
            user,
            normalized_account_type,
            github_account_type,
            avatar_url,
            client_ip,
            connected_github_account,
            connected_github_account_type
        )
        db.commit()
        debug_log(f"✅ Updated user in database: {username} (Account Type: {account_type}, GitHub Type: {github_account_type}, Avatar URL: {avatar_url})")

    # Ensure workspace membership exists
    _ensure_workspace_membership(user, db)
    
    return user


def _ensure_workspace_membership(user: Account, db: Session) -> None:
    """
    Ensure the user has a workspace membership record.

    - If no membership exists, create one.
    - The very first user in the system is auto-promoted to admin.
    - All subsequent users default to read_only.
    """
    existing = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user.user_id).first()
    if existing:
        return

    # Serialize the count+insert on PostgreSQL with a transaction-level advisory
    # lock so two concurrent first-time logins can't both see member_count==0 and
    # both receive the admin role. SQLite serializes writes natively so the call
    # is a no-op there (caught and ignored).
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(1465)"))
    except Exception:
        pass

    member_count = db.query(WorkspaceMember).count()
    role = "admin" if member_count == 0 else "read_only"

    membership = WorkspaceMember(
        user_id=user.user_id,
        workspace_role=role,
    )
    db.add(membership)
    db.commit()
    debug_log(f"✅ Created workspace membership for {user.github_user} with role: {role}")

@router.get("/auth/github")
def github_auth():
    """Redirects user to GitHub OAuth for authentication with CSRF protection."""
    redirect_uri = f"{BACKEND_URL}/auth/callback"
    state = oauth_states.create()
    return RedirectResponse(
        f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}&redirect_uri={redirect_uri}&scope=repo,workflow,read:org,user:email&state={state}"
    )

@router.get("/auth/callback")
def github_callback(code: str, state: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Handles GitHub OAuth callback with CSRF protection via state validation."""
    
    # Security: Validate state parameter before processing
    if not state or not oauth_states.validate_and_consume(state):
        debug_log("❌ OAuth callback rejected: invalid or expired state parameter")
        return {"error": "Invalid or expired authentication request. Please try logging in again."}
    
    try:
        # Get client IP address
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        if "," in client_ip:  # X-Forwarded-For can contain multiple IPs
            client_ip = client_ip.split(",")[0].strip()
        
        # Step 1: Exchange code for access token
        access_token = _exchange_code_for_token(code)
        
        # Step 2: Fetch user info from GitHub
        username, email, avatar_url, github_account_type = _fetch_user_info(access_token)
        
        # Step 3: Fetch marketplace data for billing plan
        billing_data = _fetch_marketplace_data(username, github_account_type, access_token)

        # Step 4: Resolve connected GitHub account from App installation/marketplace data
        connected_github_account, connected_github_account_type = _resolve_connected_github_account(
            username,
            github_account_type,
            billing_data,
            access_token
        )
        
        # Step 5: Store the GitHub credential and issue an app session
        user_tokens[username] = access_token
        
        # Step 6: Manage user in database with login tracking
        _manage_user_in_database(
            username,
            email,
            github_account_type,
            avatar_url,
            billing_data,
            db,
            client_ip,
            connected_github_account,
            connected_github_account_type
        )

        session_token = create_auth_session(username, db)
        response = RedirectResponse(f"{FRONTEND_URL}?user={username}")
        set_session_cookie(response, request, session_token)
        return response
        
    except ValueError as e:
        # Handle known validation errors
        debug_log(f"❌ Validation error in GitHub callback: {e}")
        return {"error": str(e)}
    except Exception as e:
        debug_log(f"❌ Error in GitHub callback: {e}")
        import traceback
        traceback.print_exc()
        return {"error": "Authentication failed"}


@router.post("/auth/token")
def github_token_login(payload: GitHubTokenRequest, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]):
    """Authenticate directly with a GitHub token and persist it as the preferred credential."""
    # Security: Validate secure connection for PAT login
    _validate_secure_connection(request)
    
    token = _validate_github_token_format(payload.token)
    validation_result = _validate_github_token(token)
    public_validation_result = _public_validation_result(validation_result)
    if validation_result.get("status") == PermissionStatus.TOKEN_INVALID:
        raise HTTPException(status_code=401, detail="GitHub token is invalid or expired.")

    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    username, email, avatar_url, github_account_type = _fetch_user_info(token)
    billing_data = _fetch_marketplace_data(username, github_account_type, token)
    connected_github_account, connected_github_account_type = _resolve_connected_github_account(
        username,
        github_account_type,
        billing_data,
        token,
    )

    user = _manage_user_in_database(
        username,
        email,
        github_account_type,
        avatar_url,
        billing_data,
        db,
        client_ip,
        connected_github_account,
        connected_github_account_type,
    )

    user.github_pat_token_encrypted = _encrypt_saved_token(token)
    user.github_pat_updated_at = datetime.now(timezone.utc)
    _persist_pat_validation(user, validation_result)
    db.commit()
    user_tokens.invalidate_pat(username)
    session_token = create_auth_session(username, db)
    set_session_cookie(response, request, session_token)

    return {
        "user": username,
    }


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Annotated[Session, Depends(get_db)]):
    """Invalidate the current app session and clear the session cookie."""
    revoke_current_session(request, db)
    clear_session_cookie(response, request)
    return {"logged_out": True}

@router.get("/api/user/{username}")
def get_user_details(username: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Fetch user details including avatar URL and rate limit status from the database."""
    user = _ensure_request_user(request, username, db)

    if not user:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_ERROR)

    # Get effective tier based on installation mode and tier service
    from tier_service import get_effective_tier
    effective_tier = get_effective_tier(user)

    # Get rate limit status
    from rate_limiter import check_rate_limit
    _, rate_limit_status = check_rate_limit(username, db)

    # Get workspace role
    membership = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user.user_id).first()
    workspace_role = membership.workspace_role if membership else "read_only"
    connected_github_account = user.connected_github_account or user.github_user
    connected_github_account_type = (
        _normalize_github_account_type(user.connected_github_account_type)
        or _normalize_github_account_type(user.github_account_type)
    )

    return {
        "github_user": user.github_user,
        "github_email": user.github_email,
        "account_type": effective_tier,  # Return effective tier instead of raw account_type
        "installation_mode": config.get_installation_mode(),
        "github_account_type": _normalize_github_account_type(user.github_account_type),
        "connected_github_account": connected_github_account,
        "connected_github_account_type": connected_github_account_type,
        "avatar_url": user.avatar_url,
        "rate_limit": rate_limit_status,
        "workspace_role": workspace_role,
        "github_token": _user_pat_status_payload(user),
    }


@router.get("/api/user/{username}/github-token")
def get_saved_github_token_status(username: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Return masked PAT/OAuth-token configuration state for the user."""
    user = _ensure_request_user(request, username, db)
    return _user_pat_status_payload(user)


@router.post("/api/user/{username}/github-token/test")
def test_github_token(username: str, payload: GitHubTokenRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Validate a one-time GitHub token without persisting it."""
    _ensure_request_user(request, username, db)
    # Security: Validate secure connection for PAT operations
    _validate_secure_connection(request)
    user = db.query(Account).filter(Account.github_user == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_ERROR)

    token = _validate_github_token_format(payload.token)
    validation_result = _validate_github_token(token)
    return _public_validation_result(validation_result)


@router.put("/api/user/{username}/github-token")
def save_github_token(username: str, payload: GitHubTokenRequest, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Validate and persist a GitHub PAT/OAuth token for server-side resolution."""
    _ensure_request_user(request, username, db)
    # Security: Validate secure connection for PAT operations
    _validate_secure_connection(request)
    user = db.query(Account).filter(Account.github_user == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_ERROR)

    token = _validate_github_token_format(payload.token)
    validation_result = _validate_github_token(token)
    public_validation_result = _public_validation_result(validation_result)

    if validation_result.get("status") == PermissionStatus.TOKEN_INVALID:
        raise HTTPException(status_code=401, detail="GitHub token is invalid or expired.")

    user.github_pat_token_encrypted = _encrypt_saved_token(token)
    user.github_pat_updated_at = datetime.now(timezone.utc)
    _persist_pat_validation(user, validation_result)
    db.commit()
    user_tokens.invalidate_pat(username)

    return {"saved": True}


@router.delete("/api/user/{username}/github-token")
def remove_github_token(username: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Remove a stored GitHub PAT/OAuth token."""
    _ensure_request_user(request, username, db)
    user = db.query(Account).filter(Account.github_user == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_ERROR)

    user.github_pat_token_encrypted = None
    user.github_pat_token_type = None
    user.github_pat_status = None
    user.github_pat_last_error = None
    user.github_pat_checked_at = None
    user.github_pat_updated_at = None
    db.commit()
    user_tokens.invalidate_pat(username)

    return {
        "removed": True,
        "token": _user_pat_status_payload(user),
    }

@router.get("/api/user/{username}/permissions")
def check_github_permissions(username: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    """
    Check GitHub OAuth permissions for a user.

    Validates that the user's GitHub token has all required scopes and access levels
    needed for Actions Manager to function correctly.

    Returns:
        - status: One of 'valid', 'missing_scopes', 'missing_repo_access', etc.
        - valid: Boolean indicating if all permissions are present
        - missing_scopes: List of missing OAuth scopes
        - issues: List of human-readable problems
        - warnings: List of non-critical warnings
        - recommendations: List of actionable steps to fix issues
        - message: Formatted user-friendly message
    """
    user = _ensure_request_user(request, username, db)

    # Check if we have a token for this user
    if username not in user_tokens:
        return {
            "status": "token_invalid",
            "valid": False,
            "missing_scopes": [],
            "granted_scopes": [],
            "issues": ["No active GitHub session found"],
            "warnings": [],
            "recommendations": ["Please sign out and sign in again to re-authenticate with GitHub"],
            "message": "⚠️ No active GitHub session. Please sign in again.",
            "details": {}
        }

    # Get the user's access token
    access_token = user_tokens[username]

    # Validate permissions
    try:
        validator = GitHubPermissionValidator(access_token)
        validation_result = validator.validate_all_permissions()

        # Add formatted message for frontend display
        validation_result["message"] = format_permission_issues_for_user(validation_result)

        # Store permission status in user record
        user.github_permission_status = validation_result["status"]
        user.github_permission_checked_at = datetime.now(timezone.utc)
        if user.github_pat_token_encrypted:
            _persist_pat_validation(user, validation_result)
        db.commit()

        debug_log(f"📌 Permission check for {username}: {validation_result['status']}")

        return validation_result

    except Exception as e:
        debug_log(f"❌ Error checking permissions for {username}: {e}")
        import traceback
        traceback.print_exc()

        return {
            "status": "unknown_error",
            "valid": False,
            "missing_scopes": [],
            "granted_scopes": [],
            "issues": [f"Error checking permissions: {str(e)}"],
            "warnings": [],
            "recommendations": ["Please try signing in again. If the problem persists, contact support."],
            "message": f"⚠️ Error checking GitHub permissions: {str(e)}",
            "details": {}
        }
