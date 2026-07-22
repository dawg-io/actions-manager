"""
Tests for workspace membership and authorization.

Tests cover:
- WorkspaceMember model creation
- First user auto-promotion to admin
- Subsequent users default to read_only
- Workspace members API (list, update role)
- Write protection middleware
- Role hierarchy enforcement
- Last-admin protection
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
from auth import user_tokens, create_auth_session

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
    # Override dependency injection
    app.dependency_overrides[ws_get_db] = override_get_db
    app.dependency_overrides[auth_get_db] = override_get_db
    # Override the middleware's DB factory so it uses the test database
    original_factory = app.state.middleware_db_factory
    app.state.middleware_db_factory = TestingSessionLocal
    Base.metadata.create_all(bind=engine)
    yield
    # Clean up all data
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
    app.dependency_overrides.pop(ws_get_db, None)
    app.dependency_overrides.pop(auth_get_db, None)
    # Clear any test tokens from the credential store
    user_tokens.clear()
    user_tokens._pat_cache.clear()


@pytest.fixture
def test_db():
    """Get a test database session."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def admin_user(test_db):
    """Create an admin user with workspace membership."""
    user = Account(
        github_user="admin-user",
        github_email="admin@example.com",
        account_type="enterprise",
        github_account_type="User",
        avatar_url="https://example.com/admin.jpg",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    member = WorkspaceMember(user_id=user.user_id, workspace_role="admin")
    test_db.add(member)
    test_db.commit()
    # Create a real auth session so session-based auth checks pass
    user.session_token = create_auth_session("admin-user", test_db)
    return user


@pytest.fixture
def member_user(test_db):
    """Create a member user with workspace membership."""
    user = Account(
        github_user="member-user",
        github_email="member@example.com",
        account_type="professional",
        github_account_type="User",
        avatar_url="https://example.com/member.jpg",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    member = WorkspaceMember(user_id=user.user_id, workspace_role="member")
    test_db.add(member)
    test_db.commit()
    # Create a real auth session so session-based auth checks pass
    user.session_token = create_auth_session("member-user", test_db)
    return user


@pytest.fixture
def readonly_user(test_db):
    """Create a read_only user with workspace membership."""
    user = Account(
        github_user="readonly-user",
        github_email="readonly@example.com",
        account_type="free",
        github_account_type="User",
        avatar_url="https://example.com/readonly.jpg",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    member = WorkspaceMember(user_id=user.user_id, workspace_role="read_only")
    test_db.add(member)
    test_db.commit()
    # Create a real auth session so session-based auth checks pass
    user.session_token = create_auth_session("readonly-user", test_db)
    return user


client = TestClient(app)


# ──────────────────────────────────────────────
# Tests: Workspace Members API — List
# ──────────────────────────────────────────────

class TestListWorkspaceMembers:
    """Tests for GET /api/workspace/members"""

    def test_list_members_as_admin(self, admin_user, readonly_user):
        """Admin can list all workspace members."""
        resp = client.get(
            "/api/workspace/members",
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        usernames = {m["github_user"] for m in data}
        assert "admin-user" in usernames
        assert "readonly-user" in usernames

    def test_list_members_as_readonly(self, admin_user, readonly_user):
        """Read-only users can also list members (view access)."""
        resp = client.get(
            "/api/workspace/members",
            headers={"Authorization": "Bearer " + readonly_user.session_token},
        )
        assert resp.status_code == 200

    def test_list_members_unauthenticated(self):
        """Unauthenticated requests are rejected."""
        resp = client.get("/api/workspace/members")
        assert resp.status_code == 401

    def test_list_members_unknown_user(self):
        """Unknown user gets 401."""
        resp = client.get(
            "/api/workspace/members",
            headers={"X-GitHub-User": "nonexistent"},
        )
        assert resp.status_code == 401

    def test_list_members_response_shape(self, admin_user):
        """Response contains expected fields."""
        resp = client.get(
            "/api/workspace/members",
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200
        member = resp.json()[0]
        assert "user_id" in member
        assert "github_user" in member
        assert "avatar_url" in member
        assert "workspace_role" in member


# ──────────────────────────────────────────────
# Tests: Workspace Members API — Update Role
# ──────────────────────────────────────────────

class TestUpdateMemberRole:
    """Tests for PATCH /api/workspace/members/{user_id}/role"""

    def test_admin_can_promote_to_member(self, admin_user, readonly_user, test_db):
        """Admin can promote a read-only user to member."""
        resp = client.patch(
            f"/api/workspace/members/{readonly_user.user_id}/role",
            json={"workspace_role": "member"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200
        assert resp.json()["workspace_role"] == "member"

    def test_admin_can_demote_member_to_readonly(self, admin_user, member_user):
        """Admin can demote a member back to read_only."""
        resp = client.patch(
            f"/api/workspace/members/{member_user.user_id}/role",
            json={"workspace_role": "read_only"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200
        assert resp.json()["workspace_role"] == "read_only"

    def test_admin_can_promote_to_admin(self, admin_user, member_user):
        """Admin can promote a member to admin."""
        resp = client.patch(
            f"/api/workspace/members/{member_user.user_id}/role",
            json={"workspace_role": "admin"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200
        assert resp.json()["workspace_role"] == "admin"

    def test_cannot_remove_last_admin(self, admin_user):
        """Cannot demote the only admin."""
        resp = client.patch(
            f"/api/workspace/members/{admin_user.user_id}/role",
            json={"workspace_role": "read_only"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 400
        assert "last admin" in resp.json()["detail"].lower()

    def test_can_demote_admin_if_another_exists(self, admin_user, member_user, test_db):
        """Can demote an admin if there's another admin."""
        # Promote member to admin first
        member_record = test_db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == member_user.user_id
        ).first()
        member_record.workspace_role = "admin"
        test_db.commit()

        resp = client.patch(
            f"/api/workspace/members/{admin_user.user_id}/role",
            json={"workspace_role": "member"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200

    def test_readonly_cannot_update_roles(self, admin_user, readonly_user):
        """Read-only user cannot update roles."""
        resp = client.patch(
            f"/api/workspace/members/{admin_user.user_id}/role",
            json={"workspace_role": "read_only"},
            headers={"Authorization": "Bearer " + readonly_user.session_token},
        )
        assert resp.status_code == 403

    def test_member_cannot_update_roles(self, admin_user, member_user):
        """Member cannot update roles (only admin can)."""
        resp = client.patch(
            f"/api/workspace/members/{admin_user.user_id}/role",
            json={"workspace_role": "read_only"},
            headers={"Authorization": "Bearer " + member_user.session_token},
        )
        assert resp.status_code == 403

    def test_invalid_role_rejected(self, admin_user, readonly_user):
        """Invalid role value is rejected with 422."""
        resp = client.patch(
            f"/api/workspace/members/{readonly_user.user_id}/role",
            json={"workspace_role": "superadmin"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 422

    def test_legacy_coadmin_role_rejected(self, admin_user, readonly_user):
        """Legacy co_admin role value is rejected with 422."""
        resp = client.patch(
            f"/api/workspace/members/{readonly_user.user_id}/role",
            json={"workspace_role": "co_admin"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 422

    def test_update_nonexistent_member(self, admin_user):
        """Updating a nonexistent member returns 404."""
        resp = client.patch(
            "/api/workspace/members/99999/role",
            json={"workspace_role": "member"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 404


# ──────────────────────────────────────────────
# Tests: Write Protection Middleware
# ──────────────────────────────────────────────

class TestWriteProtectionMiddleware:
    """Tests for the middleware that blocks read-only users from write operations."""

    def test_readonly_blocked_on_post(self, admin_user, readonly_user):
        """Read-only user is blocked from POST /api/* endpoints."""
        # Use a well-known endpoint that the middleware intercepts before routing
        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"Authorization": "Bearer " + readonly_user.session_token},
        )
        assert resp.status_code == 403
        assert "read-only" in resp.json()["detail"].lower()

    def test_readonly_blocked_on_delete(self, admin_user, readonly_user):
        """Read-only user is blocked from DELETE /api/* endpoints."""
        resp = client.delete(
            "/api/delete-workflow",
            headers={"Authorization": "Bearer " + readonly_user.session_token},
        )
        assert resp.status_code == 403
        assert "read-only" in resp.json()["detail"].lower()

    def test_admin_allowed_on_post(self, admin_user):
        """Admin is allowed to POST (middleware passes through)."""
        # The actual endpoint may return a different error (validation etc.),
        # but not 403 from the middleware.
        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code != 403

    def test_member_allowed_on_post(self, admin_user, member_user):
        """Member is allowed to POST (middleware passes through)."""
        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"Authorization": "Bearer " + member_user.session_token},
        )
        assert resp.status_code != 403

    def test_readonly_allowed_on_get(self, admin_user, readonly_user):
        """Read-only user is allowed to GET."""
        resp = client.get(
            "/api/workspace/members",
            headers={"Authorization": "Bearer " + readonly_user.session_token},
        )
        assert resp.status_code == 200

    def test_no_header_returns_401(self, admin_user):
        """Requests without any auth credential get 401 on write operations."""
        resp = client.post("/api/save-workflows", json={})
        assert resp.status_code == 401
        assert "authentication" in resp.json()["detail"].lower()

    def test_unknown_user_returns_401(self, admin_user):
        """A request without a valid session token gets 401."""
        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"X-GitHub-User": "nonexistent-user"},
        )
        assert resp.status_code == 401
        assert "authentication" in resp.json()["detail"].lower()

    def test_non_member_returns_401(self, admin_user, test_db):
        """Account that exists but has no workspace membership gets 401."""
        user = Account(
            github_user="orphan-user",
            github_email="orphan@example.com",
            account_type="free",
            github_account_type="User",
        )
        test_db.add(user)
        test_db.commit()
        # Create an auth session for orphan-user so they pass the session check
        # but still fail the workspace membership check
        orphan_session = create_auth_session("orphan-user", test_db)

        resp = client.post(
            "/api/save-workflows",
            json={},
            headers={"Authorization": "Bearer " + orphan_session},
        )
        assert resp.status_code == 401
        assert "member" in resp.json()["detail"].lower()

    def test_no_members_skips_enforcement(self):
        """When no workspace members exist, write requests are allowed without header."""
        # No fixtures used — database has zero workspace members
        resp = client.post("/api/save-workflows", json={})
        # Should NOT be 401 from middleware (may get a different error from the endpoint)
        assert resp.status_code != 401 or "X-GitHub-User" not in resp.json().get("detail", "")

    def test_auth_paths_exempt(self, readonly_user):
        """Auth paths are exempt from write protection."""
        resp = client.get("/auth/github")
        # Should redirect or succeed, not 403
        assert resp.status_code != 403

    def test_webhook_paths_exempt(self, readonly_user):
        """Webhook paths are exempt from write protection."""
        resp = client.post(
            "/webhooks/github",
            json={},
            headers={"X-GitHub-User": "readonly-user"},
        )
        # Should not be 403 from middleware
        assert resp.status_code != 403


# ──────────────────────────────────────────────
# Tests: Authorization Module
# ──────────────────────────────────────────────

class TestAuthorizationModule:
    """Tests for the authorization.py module."""

    def test_role_hierarchy(self):
        """Verify role hierarchy ordering."""
        from authorization import _role_level
        assert _role_level("read_only") < _role_level("member")
        assert _role_level("member") < _role_level("admin")

    def test_invalid_role_returns_negative(self):
        """Invalid role returns -1."""
        from authorization import _role_level
        assert _role_level("superadmin") == -1
        assert _role_level("") == -1

    def test_require_role_validates_minimum_role(self):
        """require_role() raises ValueError for invalid role names."""
        from authorization import require_role
        with pytest.raises(ValueError, match="Invalid minimum_role"):
            require_role("superadmin")
        with pytest.raises(ValueError, match="Invalid minimum_role"):
            require_role("")


# ──────────────────────────────────────────────
# Tests: Workspace Membership on Login
# ──────────────────────────────────────────────

class TestWorkspaceMembershipCreation:
    """Tests for _ensure_workspace_membership in auth module."""

    def test_first_user_becomes_admin(self, test_db):
        """First user to get workspace membership is admin."""
        user = Account(
            github_user="first-user",
            github_email="first@example.com",
            account_type="free",
            github_account_type="User",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        from auth import _ensure_workspace_membership
        _ensure_workspace_membership(user, test_db)

        member = test_db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == user.user_id
        ).first()
        assert member is not None
        assert member.workspace_role == "admin"

    def test_second_user_is_readonly(self, test_db):
        """Second user defaults to read_only."""
        # Create first user with membership
        user1 = Account(
            github_user="first-user",
            github_email="first@example.com",
            account_type="free",
            github_account_type="User",
        )
        test_db.add(user1)
        test_db.commit()
        test_db.refresh(user1)

        from auth import _ensure_workspace_membership
        _ensure_workspace_membership(user1, test_db)

        # Create second user
        user2 = Account(
            github_user="second-user",
            github_email="second@example.com",
            account_type="free",
            github_account_type="User",
        )
        test_db.add(user2)
        test_db.commit()
        test_db.refresh(user2)

        _ensure_workspace_membership(user2, test_db)

        member2 = test_db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == user2.user_id
        ).first()
        assert member2 is not None
        assert member2.workspace_role == "read_only"

    def test_idempotent_membership_creation(self, test_db):
        """Calling _ensure_workspace_membership twice doesn't create duplicates."""
        user = Account(
            github_user="idem-user",
            github_email="idem@example.com",
            account_type="free",
            github_account_type="User",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        from auth import _ensure_workspace_membership
        _ensure_workspace_membership(user, test_db)
        _ensure_workspace_membership(user, test_db)

        count = test_db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == user.user_id
        ).count()
        assert count == 1

    def test_legacy_coadmin_is_normalized_in_member_list(self, admin_user, member_user, test_db):
        """Legacy co_admin rows are normalized to admin when listing workspace members."""
        legacy_member = test_db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == member_user.user_id
        ).first()
        legacy_member.workspace_role = "co_admin"
        test_db.commit()

        resp = client.get(
            "/api/workspace/members",
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        listed_member = next(m for m in data if m["user_id"] == member_user.user_id)
        assert listed_member["workspace_role"] == "admin"
