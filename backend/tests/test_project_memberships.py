"""
Tests for project-level memberships (Phase 2 RBAC).

Tests cover:
- ProjectMembership model creation
- Project membership CRUD API (list, add, update, remove)
- Project list filtering by access
- Single project access enforcement
- Admin bypass (implicit full access)
- Authorization helpers
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
from models import Account, WorkspaceMember, Project, ProjectMembership
from authorization import _get_db as auth_get_db
from workspace_members import get_db as ws_get_db
from project_memberships import get_db as pm_get_db
from projects import get_db as proj_get_db
from workflows import get_db as wf_get_db
from auth import user_tokens, create_auth_session

# Create shared test database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

client = TestClient(app)


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
    app.dependency_overrides[ws_get_db] = override_get_db
    app.dependency_overrides[auth_get_db] = override_get_db
    app.dependency_overrides[pm_get_db] = override_get_db
    app.dependency_overrides[proj_get_db] = override_get_db
    app.dependency_overrides[wf_get_db] = override_get_db
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
    app.dependency_overrides.pop(ws_get_db, None)
    app.dependency_overrides.pop(auth_get_db, None)
    app.dependency_overrides.pop(pm_get_db, None)
    app.dependency_overrides.pop(proj_get_db, None)
    app.dependency_overrides.pop(wf_get_db, None)
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
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    member = WorkspaceMember(user_id=user.user_id, workspace_role="admin")
    test_db.add(member)
    test_db.commit()
    test_db.refresh(member)
    # Create a real auth session so session-based auth checks pass
    user.session_token = create_auth_session("admin-user", test_db)
    return user


@pytest.fixture
def second_admin_user(test_db):
    """Create a second admin user with workspace membership."""
    user = Account(
        github_user="second-admin-user",
        github_email="second-admin@example.com",
        account_type="enterprise",
        github_account_type="User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    member = WorkspaceMember(user_id=user.user_id, workspace_role="admin")
    test_db.add(member)
    test_db.commit()
    test_db.refresh(member)
    # Create a real auth session so session-based auth checks pass
    user.session_token = create_auth_session("second-admin-user", test_db)
    return user


@pytest.fixture
def readonly_user(test_db):
    """Create a read_only user with workspace membership."""
    user = Account(
        github_user="readonly-user",
        github_email="readonly@example.com",
        account_type="free",
        github_account_type="User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    member = WorkspaceMember(user_id=user.user_id, workspace_role="read_only")
    test_db.add(member)
    test_db.commit()
    test_db.refresh(member)
    # Create a real auth session so session-based auth checks pass
    user.session_token = create_auth_session("readonly-user", test_db)
    return user


@pytest.fixture
def member_user(test_db):
    """Create a member user with workspace membership."""
    user = Account(
        github_user="member-user",
        github_email="member@example.com",
        account_type="free",
        github_account_type="User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    member = WorkspaceMember(user_id=user.user_id, workspace_role="member")
    test_db.add(member)
    test_db.commit()
    test_db.refresh(member)
    # Create a real auth session so session-based auth checks pass
    user.session_token = create_auth_session("member-user", test_db)
    return user


@pytest.fixture
def sample_project(test_db, admin_user):
    """Create a sample project owned by the admin user."""
    project = Project(
        project_name="Test Project",
        user_id=admin_user.user_id,
        project_code="TST1",
    )
    test_db.add(project)
    test_db.commit()
    test_db.refresh(project)
    return project


@pytest.fixture
def second_project(test_db, admin_user):
    """Create a second project owned by the admin user."""
    project = Project(
        project_name="Secret Project",
        user_id=admin_user.user_id,
        project_code="SEC1",
    )
    test_db.add(project)
    test_db.commit()
    test_db.refresh(project)
    return project


# ──────────────────────────────────────────────
# Tests: Project Membership CRUD API
# ──────────────────────────────────────────────


class TestListProjectMembers:
    """Tests for GET /api/projects/{project_id}/members"""

    def test_admin_can_list_members(self, admin_user, sample_project):
        resp = client.get(
            f"/api/projects/{sample_project.project_id}/members",
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) == 0  # No members assigned yet

    def test_second_admin_can_list_members(self, admin_user, second_admin_user, sample_project):
        resp = client.get(
            f"/api/projects/{sample_project.project_id}/members",
            headers={"Authorization": "Bearer " + second_admin_user.session_token},
        )
        assert resp.status_code == 200

    def test_readonly_cannot_list_members(self, admin_user, readonly_user, sample_project):
        resp = client.get(
            f"/api/projects/{sample_project.project_id}/members",
            headers={"Authorization": "Bearer " + readonly_user.session_token},
        )
        assert resp.status_code == 403

    def test_list_nonexistent_project(self, admin_user):
        resp = client.get(
            "/api/projects/99999/members",
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 404


class TestAddProjectMember:
    """Tests for POST /api/projects/{project_id}/members"""

    def test_admin_can_add_member_as_viewer(self, admin_user, readonly_user, sample_project):
        resp = client.post(
            f"/api/projects/{sample_project.project_id}/members",
            json={"user_id": readonly_user.user_id, "project_role": "project_viewer"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == readonly_user.user_id
        assert data["project_role"] == "project_viewer"
        assert data["github_user"] == "readonly-user"

    def test_admin_can_add_member_as_editor(self, admin_user, readonly_user, sample_project):
        resp = client.post(
            f"/api/projects/{sample_project.project_id}/members",
            json={"user_id": readonly_user.user_id, "project_role": "project_editor"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 201
        assert resp.json()["project_role"] == "project_editor"

    def test_second_admin_can_add_member(self, admin_user, second_admin_user, readonly_user, sample_project):
        resp = client.post(
            f"/api/projects/{sample_project.project_id}/members",
            json={"user_id": readonly_user.user_id, "project_role": "project_viewer"},
            headers={"Authorization": "Bearer " + second_admin_user.session_token},
        )
        assert resp.status_code == 201

    def test_readonly_cannot_add_member(self, admin_user, readonly_user, sample_project):
        resp = client.post(
            f"/api/projects/{sample_project.project_id}/members",
            json={"user_id": readonly_user.user_id, "project_role": "project_viewer"},
            headers={"Authorization": "Bearer " + readonly_user.session_token},
        )
        assert resp.status_code == 403

    def test_duplicate_membership_rejected(self, admin_user, readonly_user, sample_project, test_db):
        # Create first membership
        pm = ProjectMembership(
            user_id=readonly_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_viewer",
        )
        test_db.add(pm)
        test_db.commit()

        # Attempt duplicate
        resp = client.post(
            f"/api/projects/{sample_project.project_id}/members",
            json={"user_id": readonly_user.user_id, "project_role": "project_editor"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 409

    def test_invalid_role_rejected(self, admin_user, readonly_user, sample_project):
        resp = client.post(
            f"/api/projects/{sample_project.project_id}/members",
            json={"user_id": readonly_user.user_id, "project_role": "superadmin"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 422

    def test_nonexistent_user_rejected(self, admin_user, sample_project):
        resp = client.post(
            f"/api/projects/{sample_project.project_id}/members",
            json={"user_id": 99999, "project_role": "project_viewer"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 404

    def test_nonexistent_project_rejected(self, admin_user, readonly_user):
        resp = client.post(
            "/api/projects/99999/members",
            json={"user_id": readonly_user.user_id, "project_role": "project_viewer"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 404


class TestUpdateProjectMember:
    """Tests for PATCH /api/projects/{project_id}/members/{user_id}"""

    def test_admin_can_update_role(self, admin_user, readonly_user, sample_project, test_db):
        pm = ProjectMembership(
            user_id=readonly_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_viewer",
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.patch(
            f"/api/projects/{sample_project.project_id}/members/{readonly_user.user_id}",
            json={"project_role": "project_editor"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200
        assert resp.json()["project_role"] == "project_editor"

    def test_update_nonexistent_membership(self, admin_user, readonly_user, sample_project):
        resp = client.patch(
            f"/api/projects/{sample_project.project_id}/members/{readonly_user.user_id}",
            json={"project_role": "project_editor"},
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 404


class TestRemoveProjectMember:
    """Tests for DELETE /api/projects/{project_id}/members/{user_id}"""

    def test_admin_can_remove_member(self, admin_user, readonly_user, sample_project, test_db):
        pm = ProjectMembership(
            user_id=readonly_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_viewer",
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.delete(
            f"/api/projects/{sample_project.project_id}/members/{readonly_user.user_id}",
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 204

    def test_remove_nonexistent_membership(self, admin_user, readonly_user, sample_project):
        resp = client.delete(
            f"/api/projects/{sample_project.project_id}/members/{readonly_user.user_id}",
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 404


# ──────────────────────────────────────────────
# Tests: Project Access Filtering (GET /api/projects/)
# ──────────────────────────────────────────────


class TestProjectAccessFiltering:
    """Tests for project list filtering based on membership."""

    def test_admin_sees_all_projects(self, admin_user, sample_project, second_project):
        resp = client.get(
            f"/api/projects/?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "admin-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_second_admin_sees_all_projects(self, admin_user, second_admin_user, sample_project, second_project):
        resp = client.get(
            f"/api/projects/?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "second-admin-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_readonly_sees_only_assigned_projects(self, admin_user, readonly_user, sample_project, second_project, test_db):
        # Assign readonly_user to sample_project only
        pm = ProjectMembership(
            user_id=readonly_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_viewer",
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.get(
            f"/api/projects/?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "readonly-user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_name"] == "Test Project"

    def test_readonly_with_no_assignments_sees_nothing(self, admin_user, readonly_user, sample_project, second_project):
        resp = client.get(
            f"/api/projects/?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "readonly-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_no_header_sees_all_projects(self, admin_user, sample_project, second_project):
        """Without X-GitHub-User header, no filtering is applied (backward compat)."""
        resp = client.get(
            f"/api/projects/?github_user={admin_user.github_user}",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_readonly_own_url_sees_assigned_projects(self, admin_user, readonly_user, sample_project, second_project, test_db):
        """Read-only user calling with their own username sees assigned projects (real-world flow)."""
        pm = ProjectMembership(
            user_id=readonly_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_viewer",
        )
        test_db.add(pm)
        test_db.commit()

        # The real-world call: github_user is the read_only user's own name (from their URL)
        resp = client.get(
            f"/api/projects/?github_user={readonly_user.github_user}",
            headers={"X-GitHub-User": "readonly-user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_name"] == "Test Project"

    def test_readonly_own_url_no_assignments_sees_nothing(self, admin_user, readonly_user, sample_project, test_db):
        """Read-only user with no assignments sees empty list using their own URL."""
        resp = client.get(
            f"/api/projects/?github_user={readonly_user.github_user}",
            headers={"X-GitHub-User": "readonly-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0


# ──────────────────────────────────────────────
# Tests: Single Project Access Enforcement
# ──────────────────────────────────────────────


class TestSingleProjectAccess:
    """Tests for GET /api/projects/{project_name} access enforcement."""

    def test_admin_can_access_any_project(self, admin_user, sample_project):
        resp = client.get(
            f"/api/projects/{sample_project.project_name}?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "admin-user"},
        )
        assert resp.status_code == 200
        assert resp.json()["caller_project_role"] == "project_admin"

    def test_readonly_with_assignment_can_access(self, admin_user, readonly_user, sample_project, test_db):
        pm = ProjectMembership(
            user_id=readonly_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        )
        test_db.add(pm)
        test_db.commit()

        resp = client.get(
            f"/api/projects/{sample_project.project_name}?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "readonly-user"},
        )
        assert resp.status_code == 200
        assert resp.json()["caller_project_role"] == "project_editor"

    def test_readonly_without_assignment_denied(self, admin_user, readonly_user, sample_project):
        resp = client.get(
            f"/api/projects/{sample_project.project_name}?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "readonly-user"},
        )
        assert resp.status_code == 403

    def test_readonly_own_url_with_assignment_can_access(self, admin_user, readonly_user, sample_project, test_db):
        """Read-only user can load a project via their own URL when they have membership."""
        pm = ProjectMembership(
            user_id=readonly_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        )
        test_db.add(pm)
        test_db.commit()

        # The real-world call: github_user is the read_only user's own name
        resp = client.get(
            f"/api/projects/{sample_project.project_name}?github_user={readonly_user.github_user}",
            headers={"X-GitHub-User": "readonly-user"},
        )
        assert resp.status_code == 200
        assert resp.json()["caller_project_role"] == "project_editor"
        assert resp.json()["project_name"] == "Test Project"

    def test_readonly_own_url_without_assignment_not_found(self, admin_user, readonly_user, sample_project):
        """Read-only user without membership gets 404 (project not revealed)."""
        resp = client.get(
            f"/api/projects/{sample_project.project_name}?github_user={readonly_user.github_user}",
            headers={"X-GitHub-User": "readonly-user"},
        )
        assert resp.status_code == 404


# ──────────────────────────────────────────────
# Tests: Authorization Helpers
# ──────────────────────────────────────────────


class TestAuthorizationHelpers:
    """Tests for project authorization helper functions."""

    def test_is_project_admin_for_admin(self, admin_user, test_db):
        from authorization import is_project_admin
        member = test_db.query(WorkspaceMember).filter(WorkspaceMember.user_id == admin_user.user_id).first()
        assert is_project_admin(member) is True

    def test_is_project_admin_for_second_admin(self, second_admin_user, test_db):
        from authorization import is_project_admin
        member = test_db.query(WorkspaceMember).filter(WorkspaceMember.user_id == second_admin_user.user_id).first()
        assert is_project_admin(member) is True

    def test_is_project_admin_for_readonly(self, readonly_user, test_db):
        from authorization import is_project_admin
        member = test_db.query(WorkspaceMember).filter(WorkspaceMember.user_id == readonly_user.user_id).first()
        assert is_project_admin(member) is False

    def test_check_project_access_admin(self, admin_user, sample_project, test_db):
        from authorization import check_project_access
        member = test_db.query(WorkspaceMember).filter(WorkspaceMember.user_id == admin_user.user_id).first()
        result = check_project_access(test_db, member, sample_project.project_id)
        assert result == "project_admin"

    def test_check_project_access_readonly_no_membership(self, readonly_user, sample_project, test_db):
        from authorization import check_project_access
        member = test_db.query(WorkspaceMember).filter(WorkspaceMember.user_id == readonly_user.user_id).first()
        result = check_project_access(test_db, member, sample_project.project_id)
        assert result is None

    def test_check_project_access_readonly_with_membership(self, readonly_user, sample_project, test_db):
        from authorization import check_project_access
        pm = ProjectMembership(
            user_id=readonly_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        )
        test_db.add(pm)
        test_db.commit()

        member = test_db.query(WorkspaceMember).filter(WorkspaceMember.user_id == readonly_user.user_id).first()
        result = check_project_access(test_db, member, sample_project.project_id)
        assert result == "project_editor"

    def test_is_project_admin_for_member(self, member_user, test_db):
        """Member role should NOT have implicit project admin access (requires explicit membership)."""
        from authorization import is_project_admin
        member = test_db.query(WorkspaceMember).filter(WorkspaceMember.user_id == member_user.user_id).first()
        assert is_project_admin(member) is False

    def test_check_project_access_member(self, member_user, sample_project, test_db):
        """Member role without explicit membership returns None (no access)."""
        from authorization import check_project_access
        member = test_db.query(WorkspaceMember).filter(WorkspaceMember.user_id == member_user.user_id).first()
        result = check_project_access(test_db, member, sample_project.project_id)
        assert result is None


# ──────────────────────────────────────────────
# Tests: Member Workspace Role
# ──────────────────────────────────────────────


class TestMemberRole:
    """Tests for the member workspace role behavior.

    After Phase 3 RBAC refinement, members need explicit ProjectMembership
    to access projects (no implicit full access).
    """

    def test_member_sees_assigned_projects(self, admin_user, member_user, sample_project, second_project, test_db):
        """Member should only see projects they are explicitly assigned to."""
        # Assign member to sample_project only
        test_db.add(ProjectMembership(
            user_id=member_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "member-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["project_name"] == "Test Project"

    def test_member_without_membership_sees_no_projects(self, admin_user, member_user, sample_project, second_project):
        """Member without any ProjectMembership should see no projects."""
        resp = client.get(
            f"/api/projects/?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "member-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_member_own_url_sees_assigned_projects(self, admin_user, member_user, sample_project, second_project, test_db):
        """Member navigating with their own username sees assigned projects."""
        # Assign member to both projects
        test_db.add(ProjectMembership(
            user_id=member_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        ))
        test_db.add(ProjectMembership(
            user_id=member_user.user_id,
            project_id=second_project.project_id,
            project_role="project_viewer",
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/?github_user={member_user.github_user}",
            headers={"X-GitHub-User": "member-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_member_can_access_single_project_with_membership(self, admin_user, member_user, sample_project, test_db):
        """Member with explicit membership can load a specific project."""
        test_db.add(ProjectMembership(
            user_id=member_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        ))
        test_db.commit()

        resp = client.get(
            f"/api/projects/{sample_project.project_name}?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "member-user"},
        )
        assert resp.status_code == 200

    def test_member_cannot_access_project_without_membership(self, admin_user, member_user, sample_project):
        """Member without membership cannot load a specific project."""
        resp = client.get(
            f"/api/projects/{sample_project.project_name}?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "member-user"},
        )
        assert resp.status_code == 403


# ──────────────────────────────────────────────
# Tests: Admin Own-URL Visibility
# ──────────────────────────────────────────────


class TestPrivilegedUserOwnUrl:
    """Tests that admin users see projects even when navigating with their own URL."""

    def test_admin_own_url_sees_all_projects(self, admin_user, second_admin_user, sample_project, second_project):
        """Admin navigating with their own URL still sees all projects."""
        resp = client.get(
            f"/api/projects/?github_user={admin_user.github_user}",
            headers={"X-GitHub-User": "admin-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_second_admin_own_url_sees_all_projects(self, admin_user, second_admin_user, sample_project, second_project):
        """Second admin navigating with their own username still sees all projects."""
        resp = client.get(
            f"/api/projects/?github_user={second_admin_user.github_user}",
            headers={"X-GitHub-User": "second-admin-user"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_second_admin_own_url_can_access_single_project(self, admin_user, second_admin_user, sample_project):
        """Second admin can load a project even when github_user doesn't match project owner."""
        resp = client.get(
            f"/api/projects/{sample_project.project_name}?github_user={second_admin_user.github_user}",
            headers={"X-GitHub-User": "second-admin-user"},
        )
        assert resp.status_code == 200
        assert resp.json()["project_name"] == "Test Project"
        assert resp.json()["caller_project_role"] == "project_admin"


# ──────────────────────────────────────────────
# Tests: Member Role in ROLE_HIERARCHY
# ──────────────────────────────────────────────


class TestMemberRoleHierarchy:
    """Tests that member role is properly positioned in the role hierarchy."""

    def test_member_in_valid_roles(self):
        from authorization import VALID_ROLES
        assert "member" in VALID_ROLES

    def test_member_above_readonly(self):
        from authorization import _role_level
        assert _role_level("member") > _role_level("read_only")

    def test_member_below_admin(self):
        from authorization import _role_level
        assert _role_level("member") < _role_level("admin")


# ──────────────────────────────────────────────
# Tests: Project Write Operations (PUT/DELETE) for Non-Owner Callers
# ──────────────────────────────────────────────


class TestProjectWriteAccessForNonOwners:
    """Tests that PUT /api/projects/{id}/ works for privileged users who are
    NOT the project owner.  The project is owned by admin-user; the caller
    is a different privileged user (admin or member) whose github_user
    differs from the owner.
    """

    def _put_project(self, project_id, caller_github_user, session_token, project_name="Test Project"):
        """Helper: send a minimal PUT request for the project."""
        return client.put(
            f"/api/projects/{project_id}/",
            json={
                "project_name": project_name,
                "selected_repos": [],
                "workflows": [],
                "rxworkflows": [],
                "github_user": caller_github_user,  # this is the URL user param
                "branch_regex": "",
                "branch_option": "default",
                "branch_max_age_days": 30,
                "reusable_workflows_enabled": False,
                "use_prefix": True,
                "project_type": "standard",
            },
            headers={"Authorization": "Bearer " + session_token},
        )

    def test_second_admin_can_update_admin_project(self, admin_user, second_admin_user, sample_project):
        """second admin calling PUT on a project owned by admin should succeed."""
        resp = self._put_project(sample_project.project_id, "second-admin-user", second_admin_user.session_token)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["project_id"] == sample_project.project_id

    def test_member_can_update_admin_project(self, admin_user, member_user, sample_project, test_db):
        """member with project_editor membership can update admin-owned project."""
        test_db.add(ProjectMembership(
            user_id=member_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        ))
        test_db.commit()
        resp = self._put_project(sample_project.project_id, "member-user", member_user.session_token)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["project_id"] == sample_project.project_id

    def test_admin_can_still_update_own_project(self, admin_user, sample_project):
        """admin (owner) calling PUT should still work as before."""
        resp = self._put_project(sample_project.project_id, "admin-user", admin_user.session_token)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_put_nonexistent_project_returns_404(self, admin_user, second_admin_user):
        """PUT on a non-existent project_id should return 404."""
        resp = self._put_project(99999, "second-admin-user", second_admin_user.session_token)
        assert resp.status_code == 404


class TestProjectDeleteAccessForNonOwners:
    """Tests that DELETE /api/projects/{name} works for privileged non-owner users."""

    def test_second_admin_can_delete_admin_project(self, admin_user, second_admin_user, sample_project):
        resp = client.delete(
            f"/api/projects/{sample_project.project_name}",
            params={"github_user": "second-admin-user"},
            headers={"Authorization": "Bearer " + second_admin_user.session_token},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_member_can_delete_admin_project(self, admin_user, member_user, sample_project, test_db):
        """member with project_editor membership can delete admin-owned project."""
        test_db.add(ProjectMembership(
            user_id=member_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        ))
        test_db.commit()
        resp = client.delete(
            f"/api/projects/{sample_project.project_name}",
            params={"github_user": "member-user"},
            headers={"Authorization": "Bearer " + member_user.session_token},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


# ──────────────────────────────────────────────
# Tests: Workflow Save for Non-Owner Privileged Users
# ──────────────────────────────────────────────


class TestWorkflowSaveForNonOwners:
    """Tests that POST /api/save-workflows works for privileged users who
    do NOT own the project.  The project is owned by admin-user; the caller
    is a different privileged user (admin or member).
    """

    def _save_workflow_payload(self, caller_github_user, project_name):
        return {
            "github_user": caller_github_user,
            "project_name": project_name,
            "workflows": [{"name": "test-wf", "content": "name: Test"}],
            "rxworkflows": [],
        }

    def test_second_admin_can_save_workflow_on_admin_project(self, admin_user, second_admin_user, sample_project):
        """second admin calling save-workflows on admin-owned project should succeed."""
        resp = client.post(
            "/api/save-workflows",
            json=self._save_workflow_payload("second-admin-user", sample_project.project_name),
            headers={"Authorization": "Bearer " + second_admin_user.session_token},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_member_can_save_workflow_on_admin_project(self, admin_user, member_user, sample_project, test_db):
        """member with project_editor membership can save workflows on admin-owned project."""
        test_db.add(ProjectMembership(
            user_id=member_user.user_id,
            project_id=sample_project.project_id,
            project_role="project_editor",
        ))
        test_db.commit()
        resp = client.post(
            "/api/save-workflows",
            json=self._save_workflow_payload("member-user", sample_project.project_name),
            headers={"Authorization": "Bearer " + member_user.session_token},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_admin_can_still_save_workflow_on_own_project(self, admin_user, sample_project):
        """admin (owner) calling save-workflows should still work as before."""
        resp = client.post(
            "/api/save-workflows",
            json=self._save_workflow_payload("admin-user", sample_project.project_name),
            headers={"Authorization": "Bearer " + admin_user.session_token},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_save_workflow_nonexistent_project_returns_404(self, admin_user, second_admin_user):
        """save-workflows on a non-existent project should return 404."""
        resp = client.post(
            "/api/save-workflows",
            json=self._save_workflow_payload("second-admin-user", "nonexistent-project"),
            headers={"Authorization": "Bearer " + second_admin_user.session_token},
        )
        assert resp.status_code == 404
