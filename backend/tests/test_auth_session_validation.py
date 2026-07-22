"""
Tests for session-based authentication validation.

Verifies that the X-GitHub-User header alone is not sufficient for
authentication — the user must also have an active session (OAuth token
or saved PAT) in the credential store.

This prevents spoofing attacks where an attacker sends X-GitHub-User: victim.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from database import Base
from models import Account, WorkspaceMember
from authorization import _get_db as auth_get_db
from workspace_members import get_db as ws_get_db
from auth import INVALID_SAVED_TOKEN_SENTINEL, create_auth_session, get_db as auth_router_get_db, user_tokens

# Create shared test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Create tables before each test and clean up after."""
    original_ws_override = app.dependency_overrides.get(ws_get_db)
    original_auth_override = app.dependency_overrides.get(auth_get_db)
    original_auth_router_override = app.dependency_overrides.get(auth_router_get_db)
    app.dependency_overrides[ws_get_db] = override_get_db
    app.dependency_overrides[auth_get_db] = override_get_db
    app.dependency_overrides[auth_router_get_db] = override_get_db
    original_factory = app.state.middleware_db_factory
    app.state.middleware_db_factory = TestingSessionLocal
    Base.metadata.create_all(bind=engine)
    yield
    db = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            try:
                db.execute(table.delete())
            except Exception:
                pass
        db.commit()
    finally:
        db.close()
    app.state.middleware_db_factory = original_factory
    for dependency, original in (
        (ws_get_db, original_ws_override),
        (auth_get_db, original_auth_override),
        (auth_router_get_db, original_auth_router_override),
    ):
        if original is None:
            app.dependency_overrides.pop(dependency, None)
        else:
            app.dependency_overrides[dependency] = original
    client.cookies.clear()
    user_tokens.clear()
    user_tokens._pat_cache.clear()


@pytest.fixture
def test_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def victim_user(test_db):
    """Create a user account that has NO active session (simulates a victim)."""
    user = Account(
        github_user="victim-user",
        github_email="victim@example.com",
        account_type="enterprise",
        github_account_type="User",
        avatar_url="https://example.com/victim.jpg",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    member = WorkspaceMember(user_id=user.user_id, workspace_role="admin")
    test_db.add(member)
    test_db.commit()
    # NOTE: No token registered — simulates a user who is not logged in
    return user


@pytest.fixture
def legitimate_user(test_db):
    """Create a user account that has an active session."""
    user = Account(
        github_user="legit-user",
        github_email="legit@example.com",
        account_type="enterprise",
        github_account_type="User",
        avatar_url="https://example.com/legit.jpg",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    member = WorkspaceMember(user_id=user.user_id, workspace_role="admin")
    test_db.add(member)
    test_db.commit()
    # Register active session
    user_tokens["legit-user"] = "ghp_test_legit_token"
    user.session_token = create_auth_session("legit-user", test_db)
    return user


@pytest.fixture
def second_logged_in_user(test_db):
    """Create another logged-in user to prove sessions cannot impersonate users."""
    user = Account(
        github_user="second-user",
        github_email="second@example.com",
        account_type="enterprise",
        github_account_type="User",
        avatar_url="https://example.com/second.jpg",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    member = WorkspaceMember(user_id=user.user_id, workspace_role="admin")
    test_db.add(member)
    test_db.commit()
    user_tokens["second-user"] = "ghp_test_second_token"
    user.session_token = create_auth_session("second-user", test_db)
    return user


client = TestClient(app)


def auth_headers(user, extra_headers=None):
    headers = {"Authorization": "Bearer " + user.session_token}
    if extra_headers:
        headers.update(extra_headers)
    return headers


class TestSessionSpoofingPrevention:
    """Tests that X-GitHub-User header spoofing is blocked."""

    def test_spoofed_header_without_session_rejected_on_read(self, victim_user):
        """
        An attacker sending X-GitHub-User for a user without an active session
        is rejected with 401 on GET endpoints that use get_current_user.
        """
        resp = client.get(
            "/api/workspace/members",
            headers={"X-GitHub-User": "victim-user"},
        )
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()

    def test_spoofed_header_without_session_rejected_on_write(self, victim_user):
        """
        An attacker sending X-GitHub-User for a user without an active session
        is rejected with 401 on write endpoints via middleware.
        """
        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"X-GitHub-User": "victim-user"},
        )
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()

    def test_nonexistent_user_header_rejected(self, legitimate_user):
        """
        A header with a username that has no account AND no session is rejected.
        """
        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"X-GitHub-User": "attacker-fake-user"},
        )
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()

    def test_legitimate_user_with_session_allowed(self, legitimate_user):
        """
        A user with both an account and an active session passes auth checks.
        """
        resp = client.get(
            "/api/workspace/members",
            headers=auth_headers(legitimate_user),
        )
        assert resp.status_code == 200

    def test_account_exists_but_no_session_rejected(self, victim_user, legitimate_user):
        """
        Even if the account exists in the database, without an active session
        the request is rejected. This is the core spoofing protection.
        """
        # victim-user has an account + workspace membership but no session token
        resp = client.get(
            "/api/workspace/members",
            headers={"X-GitHub-User": "victim-user"},
        )
        assert resp.status_code == 401

        # legit-user has both account and session — should succeed
        resp = client.get(
            "/api/workspace/members",
            headers=auth_headers(legitimate_user),
        )
        assert resp.status_code == 200

    def test_session_required_for_write_middleware(self, victim_user, legitimate_user):
        """
        WriteProtectionMiddleware rejects spoofed users on mutating requests.
        """
        # victim-user: account exists, no session
        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"X-GitHub-User": "victim-user"},
        )
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()

    def test_invalid_saved_token_sentinel_rejected_on_read(self, victim_user):
        """Invalid/decryption-failed saved PATs must not count as active sessions."""
        user_tokens._pat_cache["victim-user"] = (INVALID_SAVED_TOKEN_SENTINEL, float("inf"))
        resp = client.get(
            "/api/workspace/members",
            headers={"X-GitHub-User": "victim-user"},
        )
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()

    def test_invalid_saved_token_sentinel_rejected_on_write(self, victim_user):
        """Middleware must reject invalid/decryption-failed saved PAT sentinels."""
        user_tokens._pat_cache["victim-user"] = (INVALID_SAVED_TOKEN_SENTINEL, float("inf"))
        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"X-GitHub-User": "victim-user"},
        )
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()

    def test_missing_header_still_rejected(self, legitimate_user):
        """Requests without the header still get 401."""
        resp = client.get("/api/workspace/members")
        assert resp.status_code == 401

    def test_logged_in_user_cannot_impersonate_other_logged_in_user_with_header(self, legitimate_user, second_logged_in_user):
        """A valid session for User A cannot be combined with X-GitHub-User: User B."""
        resp = client.get(
            "/api/workspace/members",
            headers=auth_headers(legitimate_user, {"X-GitHub-User": "second-user"}),
        )
        assert resp.status_code == 403
        assert "does not match" in resp.json()["detail"].lower()

    def test_logout_revokes_session(self, legitimate_user):
        """Logout revokes the server-side session token."""
        headers = auth_headers(legitimate_user)
        resp = client.post("/auth/logout", headers=headers)
        assert resp.status_code == 200

        resp = client.get("/api/workspace/members", headers=headers)
        assert resp.status_code == 401
        assert "invalid or expired" in resp.json()["detail"].lower()
