"""
Tests for the Action Groups feature.

Covers create/list/rename/delete of groups, add/remove membership (including
idempotent add), and that deleting a group cascades to its memberships.
Groups are shared/workspace-wide, same posture as Actions Projects.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("INSTALLATION_MODE", "cloud")

from main import app  # noqa: E402
from action_groups import get_db as ag_get_db  # noqa: E402
from auth import user_tokens, create_auth_session  # noqa: E402
from models import Base, Account, ActionsProject  # noqa: E402

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _setup_account(db, github_user="testuser"):
    account = Account(github_user=github_user, github_email=f"{github_user}@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)
    return account.user_id


def _setup_action(db, user_id, name="Checkout"):
    project = ActionsProject(
        user_id=user_id,
        name=name,
        source_url="https://github.com/actions/checkout",
        owner="actions",
        repo="checkout",
        ref="main",
        yaml_path="action.yml",
        inputs_json="[]",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project.actions_project_id


def _session_headers(db, github_user="testuser") -> dict:
    """A real session for github_user, since routes now verify the caller's
    session actually belongs to the github_user they claim in the request."""
    return {"Authorization": f"Bearer {create_auth_session(github_user, db)}"}


@pytest.fixture(autouse=True)
def db_state():
    _saved = app.dependency_overrides.get(ag_get_db)
    app.dependency_overrides[ag_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    user_tokens["testuser"] = "fake-token"
    yield
    Base.metadata.drop_all(bind=engine)
    user_tokens.pop("testuser", None)
    if _saved is None:
        app.dependency_overrides.pop(ag_get_db, None)
    else:
        app.dependency_overrides[ag_get_db] = _saved


class TestCrud:
    def test_create_then_list_then_get(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        create_resp = client.post(
            "/api/action-groups/",
            json={"github_user": "testuser", "name": "Deployment", "description": "Deploy actions"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["name"] == "Deployment"
        assert created["actions_project_ids"] == []

        list_resp = client.get("/api/action-groups/", params={"github_user": "testuser"}, headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        get_resp = client.get(
            f"/api/action-groups/{created['action_group_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Deployment"

    def test_rename(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        created = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "Deployment"}, headers=headers
        ).json()

        update_resp = client.put(
            f"/api/action-groups/{created['action_group_id']}",
            json={"github_user": "testuser", "name": "Deploy", "description": "Renamed"},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Deploy"
        assert update_resp.json()["description"] == "Renamed"

    def test_delete(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        created = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "Deployment"}, headers=headers
        ).json()

        delete_resp = client.delete(
            f"/api/action-groups/{created['action_group_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert delete_resp.status_code == 204

        get_resp = client.get(
            f"/api/action-groups/{created['action_group_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert get_resp.status_code == 404

    def test_get_unknown_group_404(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        resp = client.get("/api/action-groups/9999", params={"github_user": "testuser"}, headers=headers)
        assert resp.status_code == 404

    def test_create_unauthenticated(self):
        resp = client.post("/api/action-groups/", json={"github_user": "nobody", "name": "Deployment"})
        assert resp.status_code == 401

    def test_cannot_impersonate_another_user_by_claiming_their_username(self):
        """A real session for testuser must not be able to act as otheruser
        just by putting otheruser's name in github_user - github_user is
        client-controlled and GitHub usernames are public, so this is the
        exact impersonation this endpoint must reject."""
        db = TestingSessionLocal()
        _setup_account(db, "testuser")
        _setup_account(db, "otheruser")
        headers = _session_headers(db, "testuser")
        db.close()
        user_tokens["otheruser"] = "other-token"

        try:
            resp = client.post(
                "/api/action-groups/",
                json={"github_user": "otheruser", "name": "Deployment"},
                headers=headers,
            )
            assert resp.status_code == 403
        finally:
            user_tokens.pop("otheruser", None)

    def test_shared_across_users(self):
        """Groups are shared/workspace-wide, matching the Actions catalog itself."""
        db = TestingSessionLocal()
        _setup_account(db, "testuser")
        _setup_account(db, "otheruser")
        headers = _session_headers(db, "testuser")
        other_headers = _session_headers(db, "otheruser")
        db.close()
        user_tokens["otheruser"] = "other-token"

        try:
            created = client.post(
                "/api/action-groups/", json={"github_user": "testuser", "name": "Deployment"}, headers=headers
            ).json()

            other_list = client.get(
                "/api/action-groups/", params={"github_user": "otheruser"}, headers=other_headers
            )
            assert len(other_list.json()) == 1

            other_update = client.put(
                f"/api/action-groups/{created['action_group_id']}",
                json={"github_user": "otheruser", "name": "Renamed by other user"},
                headers=other_headers,
            )
            assert other_update.status_code == 200
        finally:
            user_tokens.pop("otheruser", None)


class TestMembership:
    def test_add_and_remove_action(self):
        db = TestingSessionLocal()
        user_id = _setup_account(db)
        action_id = _setup_action(db, user_id)
        headers = _session_headers(db)
        db.close()

        group = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "Deployment"}, headers=headers
        ).json()

        add_resp = client.post(
            f"/api/action-groups/{group['action_group_id']}/actions/{action_id}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert add_resp.status_code == 200
        assert add_resp.json()["actions_project_ids"] == [action_id]

        remove_resp = client.delete(
            f"/api/action-groups/{group['action_group_id']}/actions/{action_id}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert remove_resp.status_code == 200
        assert remove_resp.json()["actions_project_ids"] == []

    def test_add_is_idempotent(self):
        db = TestingSessionLocal()
        user_id = _setup_account(db)
        action_id = _setup_action(db, user_id)
        headers = _session_headers(db)
        db.close()

        group = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "Deployment"}, headers=headers
        ).json()

        first = client.post(
            f"/api/action-groups/{group['action_group_id']}/actions/{action_id}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        second = client.post(
            f"/api/action-groups/{group['action_group_id']}/actions/{action_id}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["actions_project_ids"] == [action_id]

    def test_action_can_belong_to_multiple_groups(self):
        """The key many-to-many guarantee: one action, multiple groups, never
        duplicated within any single group's membership list."""
        db = TestingSessionLocal()
        user_id = _setup_account(db)
        action_id = _setup_action(db, user_id)
        headers = _session_headers(db)
        db.close()

        group_a = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "GroupA"}, headers=headers
        ).json()
        group_b = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "GroupB"}, headers=headers
        ).json()

        client.post(
            f"/api/action-groups/{group_a['action_group_id']}/actions/{action_id}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        client.post(
            f"/api/action-groups/{group_b['action_group_id']}/actions/{action_id}",
            params={"github_user": "testuser"},
            headers=headers,
        )

        list_resp = client.get(
            "/api/action-groups/", params={"github_user": "testuser"}, headers=headers
        ).json()
        by_name = {g["name"]: g["actions_project_ids"] for g in list_resp}
        assert by_name["GroupA"] == [action_id]
        assert by_name["GroupB"] == [action_id]

    def test_add_to_unknown_group_404(self):
        db = TestingSessionLocal()
        user_id = _setup_account(db)
        action_id = _setup_action(db, user_id)
        headers = _session_headers(db)
        db.close()

        resp = client.post(
            f"/api/action-groups/9999/actions/{action_id}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_add_unknown_action_404(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        group = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "Deployment"}, headers=headers
        ).json()

        resp = client.post(
            f"/api/action-groups/{group['action_group_id']}/actions/9999",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert resp.status_code == 404


class TestCascadeDelete:
    def test_deleting_group_removes_its_memberships(self):
        db = TestingSessionLocal()
        user_id = _setup_account(db)
        action_id = _setup_action(db, user_id)
        headers = _session_headers(db)
        db.close()

        group = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "Deployment"}, headers=headers
        ).json()
        client.post(
            f"/api/action-groups/{group['action_group_id']}/actions/{action_id}",
            params={"github_user": "testuser"},
            headers=headers,
        )

        delete_resp = client.delete(
            f"/api/action-groups/{group['action_group_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert delete_resp.status_code == 204

        # Recreate a group with the same name; the deleted group's membership
        # row must be gone, not silently resurrected via a stale join.
        new_group = client.post(
            "/api/action-groups/", json={"github_user": "testuser", "name": "Deployment"}, headers=headers
        ).json()
        assert new_group["actions_project_ids"] == []
