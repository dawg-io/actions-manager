"""
Tests for per-user Projects-grid ordering (issue #1804).

The grid used to sort by projects.updated_at, so opening or editing a project
moved its card to the front. Order is now stored per user in
project_display_order, and reordering must never touch projects.updated_at or
leak into another user's view.
"""
import sys
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    Base,
    Account,
    Project,
    ProjectMembership,
    ProjectDisplayOrder,
    WorkspaceMember,
)
from main import app
from projects import get_db as projects_get_db
from auth import create_auth_session, SESSION_COOKIE_NAME

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

ADMIN = "adminuser"


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app.dependency_overrides[projects_get_db] = override_get_db
    with patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.pop(projects_get_db, None)


def _make_user(db, github_user, workspace_role="admin"):
    """Create an account + workspace member.

    Returns a detached-safe namespace: tests close the session before making
    requests, so ORM instances would raise DetachedInstanceError.
    """
    account = Account(
        github_user=github_user,
        github_email=f"{github_user}@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    db.add(WorkspaceMember(user_id=account.user_id, workspace_role=workspace_role))
    db.commit()
    return SimpleNamespace(user_id=account.user_id, github_user=account.github_user)


def _make_projects(db, owner, names):
    """Create projects with explicitly increasing updated_at.

    SQLite's CURRENT_TIMESTAMP only has one-second resolution, so relying on
    wall-clock ordering between rows created in the same second is a coin flip.
    Later names in the list are the more recently updated.
    """
    made = []
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index, name in enumerate(names):
        project = Project(
            project_name=name,
            project_code=name.upper()[:6],
            user_id=owner.user_id,
            updated_at=base + timedelta(minutes=index),
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        made.append(SimpleNamespace(project_id=project.project_id, project_name=project.project_name))
    return made


def _list_order(client, github_user=ADMIN):
    resp = client.get(f"/api/projects/?github_user={github_user}", headers={"X-GitHub-User": github_user})
    assert resp.status_code == 200, resp.text
    return [p["project_name"] for p in resp.json()]


def _put_order(client, project_ids, github_user=ADMIN):
    return client.put(
        "/api/projects/order",
        json={"github_user": github_user, "project_ids": project_ids},
        headers={"X-GitHub-User": github_user},
    )


class TestSaveAndLoadOrder:
    def test_valid_order_saves_and_is_returned_by_the_list(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta, gamma = _make_projects(db, admin, ["alpha", "beta", "gamma"])
        db.close()

        resp = _put_order(client, [gamma.project_id, alpha.project_id, beta.project_id])
        assert resp.status_code == 200, resp.text

        assert _list_order(client) == ["gamma", "alpha", "beta"]

    def test_order_survives_a_second_reorder(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta, gamma = _make_projects(db, admin, ["alpha", "beta", "gamma"])
        db.close()

        _put_order(client, [gamma.project_id, alpha.project_id, beta.project_id])
        _put_order(client, [beta.project_id, gamma.project_id, alpha.project_id])

        assert _list_order(client) == ["beta", "gamma", "alpha"]
        # Full replace, not accumulation.
        db = TestingSessionLocal()
        assert db.query(ProjectDisplayOrder).count() == 3
        db.close()

    def test_initial_order_is_updated_at_descending_and_is_persisted(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        _make_projects(db, admin, ["oldest", "middle", "newest"])
        db.close()

        # Newest-updated first on the very first listing.
        assert _list_order(client) == ["newest", "middle", "oldest"]

        db = TestingSessionLocal()
        rows = db.query(ProjectDisplayOrder).order_by(ProjectDisplayOrder.position).all()
        assert [r.position for r in rows] == [0, 1, 2]
        db.close()

    def test_touching_updated_at_does_not_move_a_card(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta, gamma = _make_projects(db, admin, ["alpha", "beta", "gamma"])
        db.close()

        _put_order(client, [alpha.project_id, beta.project_id, gamma.project_id])

        # Simulate editing the last project — previously this jumped it to first.
        db = TestingSessionLocal()
        edited = db.query(Project).filter(Project.project_id == gamma.project_id).first()
        edited.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.close()

        assert _list_order(client) == ["alpha", "beta", "gamma"]


class TestValidation:
    def test_duplicate_ids_are_rejected(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta = _make_projects(db, admin, ["alpha", "beta"])
        db.close()

        resp = _put_order(client, [alpha.project_id, alpha.project_id, beta.project_id])
        assert resp.status_code == 422

    def test_unknown_project_id_is_rejected(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta = _make_projects(db, admin, ["alpha", "beta"])
        db.close()

        resp = _put_order(client, [alpha.project_id, beta.project_id, 9999])
        assert resp.status_code == 400
        assert "not exist or are not accessible" in resp.json()["detail"]

    def test_partial_list_is_rejected(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, _beta = _make_projects(db, admin, ["alpha", "beta"])
        db.close()

        resp = _put_order(client, [alpha.project_id])
        assert resp.status_code == 400
        assert "every accessible project" in resp.json()["detail"]

    def test_empty_list_is_rejected(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        _make_projects(db, admin, ["alpha"])
        db.close()

        assert _put_order(client, []).status_code == 422

    def test_unauthenticated_request_is_rejected(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, = _make_projects(db, admin, ["alpha"])
        db.close()

        resp = client.put("/api/projects/order", json={"project_ids": [alpha.project_id]})
        assert resp.status_code == 401

    def test_a_failed_save_leaves_the_previous_order_intact(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta, gamma = _make_projects(db, admin, ["alpha", "beta", "gamma"])
        db.close()

        _put_order(client, [gamma.project_id, beta.project_id, alpha.project_id])
        # Rejected because it omits a project the caller can see.
        assert _put_order(client, [alpha.project_id]).status_code == 400

        assert _list_order(client) == ["gamma", "beta", "alpha"]


class TestPerUserIsolation:
    def test_one_users_order_does_not_affect_another(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        other = _make_user(db, "otheradmin")
        alpha, beta, gamma = _make_projects(db, admin, ["alpha", "beta", "gamma"])
        db.close()

        _put_order(client, [gamma.project_id, beta.project_id, alpha.project_id], github_user=ADMIN)
        _put_order(client, [beta.project_id, alpha.project_id, gamma.project_id], github_user=other.github_user)

        assert _list_order(client, ADMIN) == ["gamma", "beta", "alpha"]
        assert _list_order(client, other.github_user) == ["beta", "alpha", "gamma"]

    def test_project_viewer_may_reorder_their_own_grid(self, client):
        # Ordering is a personal display preference, so unlike other writes in
        # projects.py it is not gated on project_editor.
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        viewer = _make_user(db, "vieweruser", workspace_role="read_only")
        alpha, beta = _make_projects(db, admin, ["alpha", "beta"])
        for project in (alpha, beta):
            db.add(ProjectMembership(
                user_id=viewer.user_id, project_id=project.project_id, project_role="project_viewer"
            ))
        db.commit()
        db.close()

        resp = _put_order(client, [beta.project_id, alpha.project_id], github_user="vieweruser")
        assert resp.status_code == 200, resp.text
        assert _list_order(client, "vieweruser") == ["beta", "alpha"]

    def test_non_admin_cannot_order_a_project_they_cannot_see(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        viewer = _make_user(db, "vieweruser", workspace_role="read_only")
        visible, hidden = _make_projects(db, admin, ["visible", "hidden"])
        db.add(ProjectMembership(
            user_id=viewer.user_id, project_id=visible.project_id, project_role="project_viewer"
        ))
        db.commit()
        db.close()

        resp = _put_order(client, [visible.project_id, hidden.project_id], github_user="vieweruser")
        assert resp.status_code == 400
        assert "not exist or are not accessible" in resp.json()["detail"]


class TestNewAndDeletedProjects:
    def test_new_projects_append_to_the_end(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta = _make_projects(db, admin, ["alpha", "beta"])
        db.close()

        _put_order(client, [beta.project_id, alpha.project_id])

        db = TestingSessionLocal()
        owner = db.query(Account).filter(Account.github_user == ADMIN).first()
        _make_projects(db, owner, ["brandnew"])
        db.close()

        # Appended last despite having the newest updated_at.
        assert _list_order(client) == ["beta", "alpha", "brandnew"]

    def test_deleting_a_project_removes_its_ordering_rows(self, client):
        # Removed both by the endpoint's explicit delete and by ON DELETE
        # CASCADE, which actually fires now that SQLite foreign keys are
        # enforced (issue #1811).
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta = _make_projects(db, admin, ["alpha", "beta"])
        db.close()

        _put_order(client, [beta.project_id, alpha.project_id])

        resp = client.delete(
            f"/api/projects/beta?github_user={ADMIN}", headers={"X-GitHub-User": ADMIN}
        )
        assert resp.status_code == 200, resp.text

        db = TestingSessionLocal()
        remaining = db.query(ProjectDisplayOrder).all()
        assert [r.project_id for r in remaining] == [alpha.project_id]
        db.close()


class TestUpdatedAtIsUntouched:
    def test_reordering_does_not_modify_projects_updated_at(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta = _make_projects(db, admin, ["alpha", "beta"])
        db.close()

        # Read after the one-time initialisation so the baseline is stable.
        _list_order(client)
        db = TestingSessionLocal()
        before = {
            p.project_id: p.updated_at
            for p in db.query(Project).all()
        }
        db.close()

        assert _put_order(client, [beta.project_id, alpha.project_id]).status_code == 200

        db = TestingSessionLocal()
        after = {p.project_id: p.updated_at for p in db.query(Project).all()}
        db.close()

        assert after == before


class TestSessionIdentity:
    """The frontend's apiClient sends no X-GitHub-User on GETs — it authenticates
    with the session cookie alone. Ordering must resolve identity from the
    session too, or the saved order silently never applies in the real app.
    """

    def test_saved_order_applies_from_the_session_cookie_alone(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        alpha, beta, gamma = _make_projects(db, admin, ["alpha", "beta", "gamma"])
        token = create_auth_session(ADMIN, db)
        db.close()

        _put_order(client, [gamma.project_id, alpha.project_id, beta.project_id])

        client.cookies.set(SESSION_COOKIE_NAME, token)
        resp = client.get(f"/api/projects/?github_user={ADMIN}")
        assert resp.status_code == 200, resp.text
        assert [p["project_name"] for p in resp.json()] == ["gamma", "alpha", "beta"]

    def test_without_any_identity_the_list_still_returns_projects(self, client):
        db = TestingSessionLocal()
        admin = _make_user(db, ADMIN)
        _make_projects(db, admin, ["alpha", "beta"])
        db.close()

        # No header, no session: must not 500 or 401, just fall back.
        resp = client.get(f"/api/projects/?github_user={ADMIN}")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
