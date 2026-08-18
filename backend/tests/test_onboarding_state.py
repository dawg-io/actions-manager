"""
Tests for first-login onboarding state (welcome screen + guided tour).

Covers the read surface on GET /api/user/{username}, the write surface on
PUT /api/user/{username}/onboarding, and the authorization boundary.
"""

import pytest
import auth
from fastapi.testclient import TestClient
from models import Account, WorkspaceMember
from main import app
from tests.conftest import TestingSessionLocal


client = TestClient(app, base_url="https://testserver")


@pytest.fixture(autouse=True)
def onboarding_isolation():
    original_factory = app.state.middleware_db_factory
    context_token = auth.set_request_user(None)
    app.state.middleware_db_factory = TestingSessionLocal
    auth.user_tokens.clear()
    auth.user_tokens._pat_cache.clear()
    yield
    auth.user_tokens.clear()
    auth.user_tokens._pat_cache.clear()
    app.state.middleware_db_factory = original_factory
    auth.reset_request_user(context_token)


def auth_headers(user, extra_headers=None):
    headers = {"Authorization": "Bearer " + user.session_token}
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _make_user(test_db, username, workspace_role="admin"):
    user = Account(
        github_user=username,
        github_email=f"{username}@example.com",
        account_type="free",
        github_account_type="User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    test_db.add(WorkspaceMember(user_id=user.user_id, workspace_role=workspace_role))
    test_db.commit()

    auth.user_tokens[username] = "mock_github_token"
    auth.user_tokens._pat_cache[username] = (None, float("inf"))
    user.session_token = auth.create_auth_session(username, test_db)
    return user


@pytest.fixture
def test_user(test_db):
    yield _make_user(test_db, "testuser")
    auth.user_tokens.pop("testuser", None)
    auth.user_tokens.invalidate_pat("testuser")


class TestOnboardingReadSurface:
    """GET /api/user/{username} exposes onboarding state."""

    def test_new_account_reports_onboarding_not_completed(self, test_user):
        response = client.get("/api/user/testuser", headers=auth_headers(test_user))

        assert response.status_code == 200
        onboarding = response.json()["onboarding"]
        assert onboarding["completed"] is False
        assert onboarding["completed_at"] is None
        assert onboarding["step"] is None

    def test_stored_state_is_returned(self, test_user, test_db):
        client.put(
            "/api/user/testuser/onboarding",
            headers=auth_headers(test_user),
            json={"step": "project-created"},
        )

        response = client.get("/api/user/testuser", headers=auth_headers(test_user))

        assert response.status_code == 200
        assert response.json()["onboarding"]["step"] == "project-created"


class TestOnboardingWriteSurface:
    """PUT /api/user/{username}/onboarding records progress and completion."""

    def test_recording_a_step_does_not_complete_onboarding(self, test_user, test_db):
        response = client.put(
            "/api/user/testuser/onboarding",
            headers=auth_headers(test_user),
            json={"step": "workflow-saved"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "completed": False,
            "completed_at": None,
            "step": "workflow-saved",
        }

        test_db.refresh(test_user)
        assert test_user.onboarding_step == "workflow-saved"
        assert test_user.onboarding_completed_at is None

    def test_completing_sets_the_timestamp(self, test_user, test_db):
        response = client.put(
            "/api/user/testuser/onboarding",
            headers=auth_headers(test_user),
            json={"completed": True},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["completed"] is True
        assert body["completed_at"] is not None

        test_db.refresh(test_user)
        assert test_user.onboarding_completed_at is not None

    def test_clearing_completion_also_clears_the_resume_step(self, test_user, test_db):
        client.put(
            "/api/user/testuser/onboarding",
            headers=auth_headers(test_user),
            json={"step": "campaign-created", "completed": True},
        )

        response = client.put(
            "/api/user/testuser/onboarding",
            headers=auth_headers(test_user),
            json={"completed": False},
        )

        assert response.status_code == 200
        assert response.json() == {"completed": False, "completed_at": None, "step": None}

        test_db.refresh(test_user)
        assert test_user.onboarding_completed_at is None
        assert test_user.onboarding_step is None

    def test_empty_payload_leaves_state_untouched(self, test_user, test_db):
        client.put(
            "/api/user/testuser/onboarding",
            headers=auth_headers(test_user),
            json={"step": "project-created"},
        )

        response = client.put(
            "/api/user/testuser/onboarding",
            headers=auth_headers(test_user),
            json={},
        )

        assert response.status_code == 200
        assert response.json()["step"] == "project-created"

    @pytest.mark.parametrize(
        "bad_step",
        [
            "Project Created",       # spaces and capitals
            "x" * 41,                # longer than the VARCHAR(40) column
            "../../etc/passwd",      # path traversal shape
            "<script>alert(1)</script>",
        ],
    )
    def test_malformed_steps_are_rejected(self, test_user, test_db, bad_step):
        response = client.put(
            "/api/user/testuser/onboarding",
            headers=auth_headers(test_user),
            json={"step": bad_step},
        )

        assert response.status_code == 422

        test_db.refresh(test_user)
        assert test_user.onboarding_step is None


class TestOnboardingAuthorization:
    """A user may only write their own onboarding state."""

    def test_rejects_writing_another_users_state(self, test_user, test_db):
        other = _make_user(test_db, "otheruser")
        try:
            response = client.put(
                "/api/user/otheruser/onboarding",
                headers=auth_headers(test_user),
                json={"completed": True},
            )

            assert response.status_code == 403

            test_db.refresh(other)
            assert other.onboarding_completed_at is None
        finally:
            auth.user_tokens.pop("otheruser", None)
            auth.user_tokens.invalidate_pat("otheruser")

    def test_rejects_unauthenticated_writes(self, test_user):
        response = client.put(
            "/api/user/testuser/onboarding",
            json={"completed": True},
        )

        assert response.status_code == 401

    def test_read_only_members_cannot_write_onboarding_state(self, test_db):
        """
        WriteProtectionMiddleware blocks every /api/* write for read_only users,
        including this one. The welcome screen therefore must not try to persist
        a dismissal for them — it is gated on workspace_role instead.
        """
        viewer = _make_user(test_db, "vieweruser", workspace_role="read_only")
        try:
            response = client.put(
                "/api/user/vieweruser/onboarding",
                headers=auth_headers(viewer),
                json={"completed": True},
            )

            assert response.status_code == 403
        finally:
            auth.user_tokens.pop("vieweruser", None)
            auth.user_tokens.invalidate_pat("vieweruser")
