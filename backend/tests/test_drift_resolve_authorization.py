"""
Authorization and stale-write protection for drift resolution.

Three hardening fixes are covered here:

  * Resolving drift writes to GitHub ("Restore Directly" force-pushes over the
    default branch), so it requires project_editor. Previously the endpoints
    only proved the caller could *see* the project — _find_project_by_name
    never reads ProjectMembership.project_role — so a project_viewer could
    force-push.
  * The target repo must belong to the project. Previously only the string
    shape was validated, so `repo` was effectively caller-chosen and any repo
    the caller's token could write to would receive a commit.
  * A direct push carries the blob SHA the drift was computed against and is
    refused with 409 if GitHub moved on, so a stale page cannot silently revert
    a colleague's fix.
"""

import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from workflows import get_db as real_get_db  # noqa: E402
from projects import get_db as projects_get_db  # noqa: E402
from models import (  # noqa: E402
    Base, Account, Project, Repo, ProjectRepo, Workflow, ProjectWorkflow,
    WorkspaceMember, ProjectMembership,
)
from auth import user_tokens  # noqa: E402

engine = create_engine(
    "sqlite:///:memory:",
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

OWNER = "alice"
EDITOR = "editor-user"
VIEWER = "viewer-user"


@pytest.fixture(autouse=True)
def db_state():
    app.dependency_overrides[real_get_db] = override_get_db
    app.dependency_overrides[projects_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    state = {}
    try:
        owner = Account(github_user=OWNER, github_email="a@example.com", account_type="free")
        db.add(owner); db.commit(); db.refresh(owner)
        db.add(WorkspaceMember(user_id=owner.user_id, workspace_role="admin"))

        project = Project(project_name="proj1", project_code="P001", user_id=owner.user_id,
                          branch_option="default", use_prefix=True)
        db.add(project); db.commit(); db.refresh(project)

        # A repo in the project, and one that exists but belongs elsewhere —
        # the interesting case for the ownership check.
        repo = Repo(repo_name="alice/repo1")
        foreign_repo = Repo(repo_name="someone-else/private-repo")
        db.add_all([repo, foreign_repo]); db.commit()
        db.refresh(repo); db.refresh(foreign_repo)
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))

        wf = Workflow(workflow_name="ci", workflow_yaml="name: ci\non: push",
                      workflow_git_hash="sha-local", reusable_workflow=False,
                      workflow_status="committed_locally")
        db.add(wf); db.commit(); db.refresh(wf)
        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))

        # Non-owner members: one editor, one viewer.
        for username, role in ((EDITOR, "project_editor"), (VIEWER, "project_viewer")):
            acct = Account(github_user=username, github_email=f"{username}@example.com",
                           account_type="free")
            db.add(acct); db.commit(); db.refresh(acct)
            db.add(WorkspaceMember(user_id=acct.user_id, workspace_role="member"))
            db.add(ProjectMembership(user_id=acct.user_id, project_id=project.project_id,
                                     project_role=role))
        db.commit()

        state.update(project_id=project.project_id, workflow_id=wf.workflow_id)
        for u in (OWNER, EDITOR, VIEWER):
            user_tokens[u] = f"token-{u}"
        yield state
    finally:
        for u in (OWNER, EDITOR, VIEWER):
            user_tokens.pop(u, None)
        db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(real_get_db, None)
        app.dependency_overrides.pop(projects_get_db, None)


def _resolve(state, user, *, repo="alice/repo1", expected_sha=None, mode="direct"):
    body = {
        "github_user": user,
        "repo": repo,
        "branch": "main",
        "resolution": "restore_actionsmanager",
        "delivery_mode": mode,
    }
    if expected_sha is not None:
        body["expected_github_sha"] = expected_sha
    return client.post(
        f"/api/workflows/{state['workflow_id']}/resolve-drift",
        json=body, headers={"X-GitHub-User": user},
    )


def _bulk(state, user, *, repo="alice/repo1"):
    return client.post(
        f"/api/projects/{state['project_id']}/drift/bulk-resolve",
        json={
            "github_user": user,
            "resolution": "restore_actionsmanager",
            "delivery_mode": "direct",
            "items": [{"workflow_id": state["workflow_id"], "repo": repo, "branch": "main"}],
        },
        headers={"X-GitHub-User": user},
    )


class TestEditorRoleRequired:
    def test_project_viewer_cannot_resolve_drift(self, db_state):
        # The headline fix: a read-only member could previously force-push.
        with patch("workflows._direct_push_workflow_to_branch") as push:
            resp = _resolve(db_state, VIEWER)

        assert resp.status_code == 403
        assert "Insufficient project permissions" in resp.json()["detail"]
        push.assert_not_called()

    def test_project_viewer_cannot_bulk_resolve(self, db_state):
        with patch("workflows._direct_push_workflow_to_branch") as push:
            resp = _bulk(db_state, VIEWER)

        assert resp.status_code == 403
        push.assert_not_called()

    def test_project_editor_can_resolve_drift(self, db_state):
        with patch("workflows._direct_push_workflow_to_branch",
                   return_value={"status_code": 200, "sha": "sha-new"}) as push:
            resp = _resolve(db_state, EDITOR)

        assert resp.status_code == 200, resp.text
        push.assert_called_once()

    def test_project_owner_can_resolve_drift(self, db_state):
        # Owners hold no ProjectMembership row, so they must pass on ownership.
        with patch("workflows._direct_push_workflow_to_branch",
                   return_value={"status_code": 200, "sha": "sha-new"}) as push:
            resp = _resolve(db_state, OWNER)

        assert resp.status_code == 200, resp.text
        push.assert_called_once()


class TestTargetRepoMustBelongToProject:
    def test_repo_outside_the_project_is_rejected(self, db_state):
        # Exists in the repos table, but is not one of this project's repos.
        with patch("workflows._direct_push_workflow_to_branch") as push:
            resp = _resolve(db_state, OWNER, repo="someone-else/private-repo")

        assert resp.status_code == 400
        assert "not part of this project" in resp.json()["detail"]
        push.assert_not_called()

    def test_unknown_repo_is_rejected(self, db_state):
        with patch("workflows._direct_push_workflow_to_branch") as push:
            resp = _resolve(db_state, OWNER, repo="attacker/never-seen")

        assert resp.status_code == 400
        push.assert_not_called()

    def test_malformed_repo_is_rejected(self, db_state):
        with patch("workflows._direct_push_workflow_to_branch") as push:
            resp = _resolve(db_state, OWNER, repo="not-a-repo")

        assert resp.status_code == 400
        push.assert_not_called()

    def test_bulk_rejects_repo_outside_the_project(self, db_state):
        with patch("workflows._direct_push_workflow_to_branch") as push:
            resp = _bulk(db_state, OWNER, repo="someone-else/private-repo")

        assert resp.status_code == 400
        push.assert_not_called()


class TestReusableWorkflowRepoIsResolvable:
    """The reusable-workflow repo is surfaced in drift details but is not one of
    the project's own repos — rejecting it would make reusable drift
    unresolvable from the UI."""

    def test_reusable_workflow_repo_is_accepted(self, db_state):
        from workflows import _require_repo_in_project
        from models import Project

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_code="P001").first()
            # The fallback the code uses when no linked RWX project exists.
            with patch("workflows._get_reusable_workflow_repo",
                       return_value=f"{OWNER}/am-reuseable-workflow"):
                # Must not raise, despite not being in project_repos.
                _require_repo_in_project(db, project, f"{OWNER}/am-reuseable-workflow", OWNER)
        finally:
            db.close()

    def test_unrelated_repo_is_still_rejected(self, db_state):
        from fastapi import HTTPException
        from workflows import _require_repo_in_project
        from models import Project

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_code="P001").first()
            with patch("workflows._get_reusable_workflow_repo",
                       return_value=f"{OWNER}/am-reuseable-workflow"):
                with pytest.raises(HTTPException) as exc:
                    _require_repo_in_project(db, project, "someone-else/private-repo", OWNER)
            assert exc.value.status_code == 400
        finally:
            db.close()


class TestUnchangedContentDetection:
    """The no-op short-circuit compares base64: GitHub wraps it at 60 chars with
    a trailing newline, b64encode does not. Comparing verbatim was never equal
    for a realistic file, so the guard silently never fired."""

    def test_wrapped_github_base64_is_recognised_as_unchanged(self, db_state):
        import base64, textwrap
        from workflows import _check_existing_workflow_content

        content = "name: CI\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
        ours = base64.b64encode(content.encode()).decode()
        github_wrapped = "\n".join(textwrap.wrap(ours, 60)) + "\n"
        assert github_wrapped != ours, "fixture must exercise the wrapping"

        with patch("workflows.github_get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {"sha": "sha-A", "content": github_wrapped}
            sha, unchanged = _check_existing_workflow_content("url", ours, {}, OWNER, object())

        assert sha == "sha-A"
        assert unchanged is True

    def test_genuinely_different_content_is_not_unchanged(self, db_state):
        import base64
        from workflows import _check_existing_workflow_content

        ours = base64.b64encode(b"name: CI\n").decode()
        theirs = base64.b64encode(b"name: CI\n# edited\n").decode()

        with patch("workflows.github_get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {"sha": "sha-A", "content": theirs}
            _sha, unchanged = _check_existing_workflow_content("url", ours, {}, OWNER, object())

        assert unchanged is False


class TestAdoptingGithubVersionIsAlsoGuarded:
    """Adopting discards the managed YAML, so a stale view means accepting
    content the user never saw — the mirror image of the overwrite case."""

    def test_stale_use_github_resolve_returns_409(self, db_state):
        with patch("workflows.get_workflow_from_github",
                   return_value={"content": "name: someone-elses-edit\n", "sha": "sha-B"}):
            resp = client.post(
                f"/api/workflows/{db_state['workflow_id']}/resolve-drift",
                json={
                    "github_user": OWNER,
                    "repo": "alice/repo1",
                    "branch": "main",
                    "resolution": "use_github",
                    "expected_github_sha": "sha-A",
                },
                headers={"X-GitHub-User": OWNER},
            )

        assert resp.status_code == 409, resp.text
        assert "changed since drift was checked" in resp.json()["detail"]

    def test_matching_sha_adopts_normally(self, db_state):
        with patch("workflows.get_workflow_from_github",
                   return_value={"content": "name: agreed\n", "sha": "sha-A"}), \
             patch("workflows._collect_project_drift_details", return_value=[]):
            resp = client.post(
                f"/api/workflows/{db_state['workflow_id']}/resolve-drift",
                json={
                    "github_user": OWNER,
                    "repo": "alice/repo1",
                    "branch": "main",
                    "resolution": "use_github",
                    "expected_github_sha": "sha-A",
                },
                headers={"X-GitHub-User": OWNER},
            )

        assert resp.status_code == 200, resp.text


class TestStaleWriteProtection:
    """The data-loss case: drift computed at SHA A, someone pushes a fix (SHA B),
    the user then clicks Restore Directly from the stale page."""

    def _run_push(self, expected_sha, live_sha, content_matches=False):
        """Drive the real _direct_push_workflow_to_branch against a faked GitHub."""
        from workflows import _direct_push_workflow_to_branch

        with patch("workflows._check_existing_workflow_content",
                   return_value=(live_sha, content_matches)), \
             patch("workflows.github_put") as put:
            put.return_value.status_code = 200
            put.return_value.json.return_value = {"content": {"sha": "sha-written"}}
            result = _direct_push_workflow_to_branch(
                "alice", "repo1", "main", ".github/workflows/ci.yml", "name: ci\n",
                "msg", {}, OWNER, None, expected_sha=expected_sha,
            )
        return result, put

    def test_stale_sha_refuses_the_push(self, db_state):
        result, _put = self._run_push(expected_sha="sha-A", live_sha="sha-B")

        assert result["status_code"] == 409
        assert "changed since drift was checked" in result["error"]

    def test_stale_sha_writes_nothing(self, db_state):
        # The point of the guard: no commit is made when the file moved on.
        _result, put = self._run_push(expected_sha="sha-A", live_sha="sha-B")

        put.assert_not_called()

    def test_stale_resolve_surfaces_409_at_the_endpoint(self, db_state):
        # The helper reports the conflict; the endpoint turns it into a 409.
        with patch("workflows._direct_push_workflow_to_branch",
                   return_value={"status_code": 409,
                                 "error": "ci.yml changed since drift was checked."}):
            resp = _resolve(db_state, OWNER, expected_sha="sha-A")

        assert resp.status_code == 409
        assert "changed since drift was checked" in resp.json()["detail"]

    def test_matching_sha_allows_the_push(self, db_state):
        result, put = self._run_push(expected_sha="sha-A", live_sha="sha-A")

        assert result["status_code"] == 200
        put.assert_called_once()

    def test_omitted_expectation_preserves_previous_behaviour(self, db_state):
        # Optional by design, so existing callers keep working.
        result, put = self._run_push(expected_sha=None, live_sha="sha-B")

        assert result["status_code"] == 200
        put.assert_called_once()

    def test_identical_content_is_not_pushed_twice(self, db_state):
        # Double-submit used to create a second empty-diff commit.
        result, put = self._run_push(expected_sha="sha-A", live_sha="sha-A", content_matches=True)

        assert result["status_code"] == 200
        assert result.get("unchanged") is True
        put.assert_not_called()

    def test_stale_item_fails_only_its_own_row_in_bulk(self, db_state):
        with patch("workflows._direct_push_workflow_to_branch",
                   return_value={"status_code": 409,
                                 "error": "ci.yml changed since drift was checked."}):
            resp = client.post(
                f"/api/projects/{db_state['project_id']}/drift/bulk-resolve",
                json={
                    "github_user": OWNER,
                    "resolution": "restore_actionsmanager",
                    "delivery_mode": "direct",
                    "items": [{
                        "workflow_id": db_state["workflow_id"],
                        "repo": "alice/repo1",
                        "branch": "main",
                        "expected_github_sha": "sha-A",
                    }],
                },
                headers={"X-GitHub-User": OWNER},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is False
        assert "changed since drift was checked" in body["results"][0]["message"]
