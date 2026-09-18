"""
Deleting a ruleset from ActionsManager and from GitHub (issue #2011).

`DELETE /api/rulesets/{ruleset_id}` used to drop the `Ruleset` row and its
`ProjectRuleset` links and never call GitHub, so the ruleset stayed applied on
every repository it had been pushed to — branch protection enforced by nothing
ActionsManager still tracked. These cover the `scope` choice that fixes it:
`project` keeps that behaviour, `project_and_github` also deletes the GitHub
copy from each repository the ruleset's projects target.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app
from models import Account, Project, ProjectRepo, ProjectRuleset, Repo, Ruleset
from tests.conftest import TestingSessionLocal

OWNER = "scope-ruleset-owner"
RULESET_NAME = "require-reviews"
REPO_A = "scope-org/repo-a"
REPO_B = "scope-org/repo-b"
GITHUB_RULESET_ID = 4242

client = TestClient(app)


@pytest.fixture
def applied_ruleset():
    """A ruleset linked to one project that targets two repositories."""
    db = TestingSessionLocal()
    try:
        owner = Account(
            github_user=OWNER, github_email=f"{OWNER}@example.com", account_type="free"
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)

        ruleset = Ruleset(
            ruleset_name=RULESET_NAME,
            ruleset_json=json.dumps({"name": RULESET_NAME, "target": "branch"}),
            user_id=owner.user_id,
        )
        project = Project(project_name="Scope Project", user_id=owner.user_id)
        repos = [Repo(repo_name=REPO_A), Repo(repo_name=REPO_B)]
        db.add_all([ruleset, project, *repos])
        db.commit()
        db.refresh(ruleset)
        db.refresh(project)

        db.add(ProjectRuleset(project_id=project.project_id, ruleset_id=ruleset.ruleset_id))
        for repo in repos:
            db.refresh(repo)
            db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
        db.commit()
        return ruleset.ruleset_id
    finally:
        db.close()


@pytest.fixture
def unlinked_ruleset():
    """A ruleset owned by OWNER but linked to no project, so it targets nothing."""
    db = TestingSessionLocal()
    try:
        owner = db.query(Account).filter(Account.github_user == OWNER).first()
        if not owner:
            owner = Account(
                github_user=OWNER, github_email=f"{OWNER}@example.com", account_type="free"
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)

        ruleset = Ruleset(
            ruleset_name="orphaned-policy",
            ruleset_json=json.dumps({"name": "orphaned-policy", "target": "branch"}),
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


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        return self._payload


class FakeGitHub:
    """Records the calls a delete makes, answering list/delete like GitHub does."""

    def __init__(self, delete_status=204, listing=None):
        self.delete_status = delete_status
        self.listing = listing if listing is not None else [
            {"id": GITHUB_RULESET_ID, "name": RULESET_NAME}
        ]
        self.gets = []
        self.deletes = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return FakeResponse(200, self.listing)

    async def delete(self, url, **kwargs):
        self.deletes.append((url, kwargs))
        return FakeResponse(self.delete_status, None if self.delete_status == 204 else {"message": "nope"})


@pytest.fixture
def github(monkeypatch):
    """Authenticate the owner's GitHub token and stand in for the API."""
    import rulesets as rulesets_module

    rulesets_module.user_tokens[OWNER] = "gho_test_token"
    fake = FakeGitHub()
    monkeypatch.setattr(rulesets_module.httpx, "AsyncClient", lambda *a, **k: fake)
    yield fake
    rulesets_module.user_tokens.pop(OWNER, None)


class TestDeleteRulesetScope:
    def test_project_scope_leaves_github_alone(self, applied_ruleset, github, authenticate_client):
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "project"},
        )

        assert resp.status_code == 200
        assert not _ruleset_exists(applied_ruleset)
        assert github.deletes == []

    def test_default_scope_leaves_github_alone(self, applied_ruleset, github, authenticate_client):
        """No `scope` keeps the pre-#2011 behaviour, so nothing changes silently."""
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.delete(f"/api/rulesets/{applied_ruleset}", params={"github_user": OWNER})

        assert resp.status_code == 200
        assert github.deletes == []

    def test_github_scope_deletes_from_every_targeted_repo(
        self, applied_ruleset, github, authenticate_client
    ):
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "project_and_github"},
        )

        assert resp.status_code == 200
        deleted_urls = sorted(url for url, _ in github.deletes)
        assert deleted_urls == [
            f"https://api.github.com/repos/{REPO_A}/rulesets/{GITHUB_RULESET_ID}",
            f"https://api.github.com/repos/{REPO_B}/rulesets/{GITHUB_RULESET_ID}",
        ]
        assert not _ruleset_exists(applied_ruleset)

    def test_github_scope_sends_a_timeout_on_every_call(
        self, applied_ruleset, github, authenticate_client
    ):
        """A hung socket would otherwise pin the worker until the process restarts."""
        authenticate_client(client, OWNER, TestingSessionLocal)

        client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "project_and_github"},
        )

        calls = github.gets + github.deletes
        assert calls, "no GitHub calls to check"
        for _, kwargs in calls:
            assert kwargs.get("timeout")

    def test_never_targets_an_inherited_org_ruleset(
        self, applied_ruleset, github, authenticate_client
    ):
        """includes_parents defaults to true, and an org ruleset cannot be
        deleted from a repository path — it 404s, which counts as removed. The
        row would go while the repository's own ruleset stayed enforced."""
        authenticate_client(client, OWNER, TestingSessionLocal)

        client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "project_and_github"},
        )

        assert github.gets, "no listing was fetched"
        for _, kwargs in github.gets:
            assert kwargs.get("params", {}).get("includes_parents") == "false"

    def test_an_empty_target_list_does_not_claim_a_removal(
        self, unlinked_ruleset, github, authenticate_client
    ):
        """No saved repositories resolves no targets, so nothing was removed."""
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.delete(
            f"/api/rulesets/{unlinked_ruleset}",
            params={"github_user": OWNER, "scope": "github"},
        )

        assert resp.status_code == 200
        assert resp.json()["removed_from_repos"] == []
        assert "nothing was removed" in resp.json()["message"]
        assert github.deletes == []

    def test_rejects_an_unknown_scope(self, applied_ruleset, github, authenticate_client):
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "everything"},
        )

        assert resp.status_code == 400
        assert _ruleset_exists(applied_ruleset)

    def test_keeps_the_row_when_a_repo_delete_fails(
        self, applied_ruleset, github, authenticate_client
    ):
        """Dropping the row would leave an enforced ruleset nothing tracks."""
        authenticate_client(client, OWNER, TestingSessionLocal)
        github.delete_status = 403

        resp = client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "project_and_github"},
        )

        assert resp.status_code == 502
        assert _ruleset_exists(applied_ruleset)

    def test_github_scope_lifts_the_policy_but_keeps_the_record(
        self, applied_ruleset, github, authenticate_client
    ):
        """The inverse of 'project': stop enforcing it, keep it to reapply."""
        authenticate_client(client, OWNER, TestingSessionLocal)

        resp = client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "github"},
        )

        assert resp.status_code == 200
        assert sorted(url for url, _ in github.deletes) == [
            f"https://api.github.com/repos/{REPO_A}/rulesets/{GITHUB_RULESET_ID}",
            f"https://api.github.com/repos/{REPO_B}/rulesets/{GITHUB_RULESET_ID}",
        ]
        # The point of the scope: the ruleset survives so it can be applied again.
        assert _ruleset_exists(applied_ruleset)

    def test_github_scope_keeps_the_project_links(
        self, applied_ruleset, github, authenticate_client
    ):
        """Reapplying needs the project links, so they must survive too."""
        authenticate_client(client, OWNER, TestingSessionLocal)

        client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "github"},
        )

        db = TestingSessionLocal()
        try:
            links = db.query(ProjectRuleset).filter(
                ProjectRuleset.ruleset_id == applied_ruleset
            ).count()
        finally:
            db.close()
        assert links == 1

    def test_github_scope_keeps_the_record_when_a_repo_delete_fails(
        self, applied_ruleset, github, authenticate_client
    ):
        authenticate_client(client, OWNER, TestingSessionLocal)
        github.delete_status = 403

        resp = client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "github"},
        )

        assert resp.status_code == 502
        assert _ruleset_exists(applied_ruleset)

    def test_a_repo_without_the_ruleset_is_not_an_error(
        self, applied_ruleset, github, authenticate_client
    ):
        """Never applied, or already removed by hand — nothing to delete, not a failure."""
        authenticate_client(client, OWNER, TestingSessionLocal)
        github.listing = [{"id": 99, "name": "some-other-ruleset"}]

        resp = client.delete(
            f"/api/rulesets/{applied_ruleset}",
            params={"github_user": OWNER, "scope": "project_and_github"},
        )

        assert resp.status_code == 200
        assert github.deletes == []
        assert not _ruleset_exists(applied_ruleset)
