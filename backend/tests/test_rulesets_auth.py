"""
Authorization tests for the rulesets API.

Three routes take the caller's name from the client: DELETE as a `github_user`
query parameter, apply and sync-status as a body field. In every case the name
selects whose GitHub token is used, so it has to be proven, not trusted.

`DELETE /api/rulesets/{ruleset_id}` takes the caller's name as a `github_user`
query parameter. Scoping the lookup to that account is not access control — the
caller chooses the account — so the route must assert the session owns the name
it was given. Before that assertion existed, any signed-in member could delete
another user's rulesets by naming them.

These use a real server-issued session via `authenticate_client` rather than
patching the resolver, so they exercise the authorization path the app runs.
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from models import Account, Ruleset
from tests.conftest import TestingSessionLocal

OWNER = "ruleset-owner"
OTHER = "someone-else"

client = TestClient(app)


@pytest.fixture
def ruleset_id():
    """One account owning one ruleset, plus a second account to act as the caller."""
    db = TestingSessionLocal()
    try:
        owner = Account(
            github_user=OWNER, github_email=f"{OWNER}@example.com", account_type="free"
        )
        other = Account(
            github_user=OTHER, github_email=f"{OTHER}@example.com", account_type="free"
        )
        db.add_all([owner, other])
        db.commit()
        db.refresh(owner)

        ruleset = Ruleset(
            ruleset_name="require-reviews",
            ruleset_json='{"name": "require-reviews", "target": "branch"}',
            description="Protected branch policy",
            user_id=owner.user_id,
        )
        db.add(ruleset)
        db.commit()
        db.refresh(ruleset)
        return ruleset.ruleset_id
    finally:
        db.close()


def _ruleset_exists(rid: int) -> bool:
    db = TestingSessionLocal()
    try:
        return db.query(Ruleset).filter(Ruleset.ruleset_id == rid).first() is not None
    finally:
        db.close()


class TestDeleteRulesetAuthorization:
    def test_rejects_a_caller_naming_someone_else(self, ruleset_id, authenticate_client):
        """Session belongs to OTHER; the request claims to be OWNER."""
        authenticate_client(client, OTHER, TestingSessionLocal)

        resp = client.delete(f"/api/rulesets/{ruleset_id}", params={"github_user": OWNER})

        assert resp.status_code == 403
        # The point of the test: the ruleset must survive the attempt.
        assert _ruleset_exists(ruleset_id)

    def test_allows_the_owner(self, ruleset_id, authenticate_client):
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.delete(f"/api/rulesets/{ruleset_id}", params={"github_user": OWNER})

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert not _ruleset_exists(ruleset_id)

    def test_missing_ruleset_returns_404_not_500(self, ruleset_id, authenticate_client):
        """The route's catch-all used to swallow its own 404 and report a 500."""
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.delete("/api/rulesets/999999", params={"github_user": OWNER})

        assert resp.status_code == 404


class TestApplyRulesetAuthorization:
    """`github_user` in the body picks whose token creates the ruleset."""

    def test_rejects_a_caller_naming_someone_else(self, ruleset_id, authenticate_client):
        authenticate_client(client, OTHER, TestingSessionLocal)

        resp = client.post(
            f"/api/rulesets/{ruleset_id}/apply",
            json={"repo_names": ["victim-org/prod"], "github_user": OWNER},
        )

        # Without the assertion this reached GitHub with OWNER's token and
        # created the ruleset on a repository OTHER named.
        assert resp.status_code == 403
        assert _ruleset_exists(ruleset_id)

    def test_missing_ruleset_returns_404_not_500(self, ruleset_id, authenticate_client):
        """The route's catch-all used to report its own 404 as a 500."""
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.post(
            "/api/rulesets/999999/apply",
            json={"repo_names": ["acme/api"], "github_user": OWNER},
        )

        assert resp.status_code == 404


class TestSyncStatusAuthorization:
    """Reads another account's rulesets and spends their rate limit."""

    def test_rejects_a_caller_naming_someone_else(self, ruleset_id, authenticate_client):
        authenticate_client(client, OTHER, TestingSessionLocal)

        resp = client.post(
            f"/api/rulesets/{ruleset_id}/sync-status",
            json={"repo_names": ["victim-org/prod"], "github_user": OWNER},
        )

        assert resp.status_code == 403
