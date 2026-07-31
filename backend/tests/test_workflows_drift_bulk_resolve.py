"""
Tests for the bulk drift-resolution endpoint:

  * POST /api/projects/{project_id}/drift/bulk-resolve

Feature: bulk-fix workflow drift. This endpoint resolves multiple
(workflow_id, repo, branch) drift items in one request, applying one
resolution/delivery_mode uniformly across the batch. It reuses the same
per-item helpers as the existing single-workflow resolve-drift endpoint
(``_apply_use_github_resolution``, ``_direct_push_workflow_to_branch``) and
the same multi-workflow-single-PR grouping used elsewhere
(``create_pull_requests`` / ``_process_regular_workflows_update``).

These tests follow the same conventions as
test_workflows_drift_v2_endpoints.py: FastAPI TestClient, in-memory SQLite
via StaticPool, a db_state fixture, and mocking at the
_process_regular_workflows_update boundary for PR-mode assertions.
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app  # noqa: E402
from workflows import get_db as real_get_db  # noqa: E402
from projects import get_db as projects_get_db  # noqa: E402
from models import (  # noqa: E402
    Base, Account, Project, Repo, ProjectRepo, Workflow, ProjectWorkflow,
)
from auth import user_tokens  # noqa: E402


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


@pytest.fixture(autouse=True)
def db_state():
    """Project with 2 repos and 2 workflows, so bulk items can target
    different (workflow, repo) combinations."""
    prev_override = app.dependency_overrides.get(real_get_db)
    prev_projects_override = app.dependency_overrides.get(projects_get_db)
    app.dependency_overrides[real_get_db] = override_get_db
    app.dependency_overrides[projects_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        user = Account(github_user="alice", github_email="a@example.com", account_type="free")
        db.add(user); db.commit(); db.refresh(user)

        project = Project(
            project_name="proj1", project_code="P001",
            user_id=user.user_id, branch_option="default", use_prefix=True,
        )
        db.add(project); db.commit(); db.refresh(project)

        other_user = Account(github_user="bob", github_email="b@example.com", account_type="free")
        db.add(other_user); db.commit(); db.refresh(other_user)
        other_project = Project(
            project_name="proj2", project_code="P002",
            user_id=other_user.user_id, branch_option="default", use_prefix=True,
        )
        db.add(other_project); db.commit(); db.refresh(other_project)

        repo1 = Repo(repo_name="alice/repo1")
        repo2 = Repo(repo_name="alice/repo2")
        db.add_all([repo1, repo2]); db.commit()
        db.refresh(repo1); db.refresh(repo2)
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo1.repo_id))
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo2.repo_id))
        db.commit()

        # workflow_status starts at "committed_locally" (the realistic
        # pre-fix state a normal edit/save cycle leaves behind) so tests can
        # prove drift-resolution actually advances it, rather than it just
        # happening to already be "synced_with_github" before the call.
        wf_ci = Workflow(
            workflow_name="ci",
            workflow_yaml="name: AM_P001_ci\non: push",
            workflow_git_hash="sha-old-ci",
            reusable_workflow=False,
            workflow_status="committed_locally",
        )
        wf_deploy = Workflow(
            workflow_name="deploy",
            workflow_yaml="name: AM_P001_deploy\non: push",
            workflow_git_hash="sha-old-deploy",
            reusable_workflow=False,
            workflow_status="committed_locally",
        )
        db.add_all([wf_ci, wf_deploy]); db.commit()
        db.refresh(wf_ci); db.refresh(wf_deploy)
        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf_ci.workflow_id))
        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf_deploy.workflow_id))
        db.commit()

        # A workflow belonging to the OTHER project, to test cross-project rejection.
        wf_foreign = Workflow(
            workflow_name="foreign",
            workflow_yaml="name: foreign\non: push",
            workflow_git_hash="sha-foreign",
            reusable_workflow=False,
            workflow_status="synced_with_github",
        )
        db.add(wf_foreign); db.commit(); db.refresh(wf_foreign)
        db.add(ProjectWorkflow(project_id=other_project.project_id, workflow_id=wf_foreign.workflow_id))
        db.commit()

        user_tokens["alice"] = "test-token"

        yield {
            "project_id": project.project_id,
            "ci_id": wf_ci.workflow_id,
            "deploy_id": wf_deploy.workflow_id,
            "foreign_id": wf_foreign.workflow_id,
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        user_tokens.pop("alice", None)
        if prev_override is None:
            app.dependency_overrides.pop(real_get_db, None)
        else:
            app.dependency_overrides[real_get_db] = prev_override
        if prev_projects_override is None:
            app.dependency_overrides.pop(projects_get_db, None)
        else:
            app.dependency_overrides[projects_get_db] = prev_projects_override


def _bulk_resolve(project_id, items, resolution, delivery_mode=None, github_user="alice"):
    body = {"github_user": github_user, "items": items, "resolution": resolution}
    if delivery_mode is not None:
        body["delivery_mode"] = delivery_mode
    return client.post(f"/api/projects/{project_id}/drift/bulk-resolve", json=body)


# ----------------------------------------------------------------------------
# use_github
# ----------------------------------------------------------------------------

def test_bulk_use_github_across_two_workflows_and_repos(db_state):
    def fake_github_fetch(owner, repo, filename, token, default_branch=None):
        if "ci" in filename:
            return {"content": "name: AM_P001_ci\non: pull_request", "sha": "new-sha-ci"}
        return {"content": "name: AM_P001_deploy\non: pull_request", "sha": "new-sha-deploy"}

    with patch("workflows.get_workflow_from_github", side_effect=fake_github_fetch), \
         patch("workflows.get_default_branch", return_value="main"):
        resp = _bulk_resolve(
            db_state["project_id"],
            [
                {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
                {"workflow_id": db_state["deploy_id"], "repo": "alice/repo2", "branch": "main"},
            ],
            resolution="use_github",
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert len(body["results"]) == 2
    assert all(r["success"] for r in body["results"])

    db = TestingSessionLocal()
    try:
        ci = db.query(Workflow).filter_by(workflow_id=db_state["ci_id"]).first()
        deploy = db.query(Workflow).filter_by(workflow_id=db_state["deploy_id"]).first()
        assert ci.workflow_git_hash == "new-sha-ci"
        assert deploy.workflow_git_hash == "new-sha-deploy"
        assert "pull_request" in ci.workflow_yaml
        assert "pull_request" in deploy.workflow_yaml
        # Regression: drift resolution must advance workflow_status forward,
        # not leave it at whatever it was pre-resolution.
        assert ci.workflow_status == "synced_with_github"
        assert deploy.workflow_status == "synced_with_github"
    finally:
        db.close()


def test_bulk_use_github_partial_failure_reports_per_item(db_state):
    """One item's workflow is missing on GitHub - it fails, the other still succeeds."""
    def fake_github_fetch(owner, repo, filename, token, default_branch=None):
        if "ci" in filename:
            return {"content": "name: AM_P001_ci\non: pull_request", "sha": "new-sha-ci"}
        return None  # deploy not found on GitHub

    with patch("workflows.get_workflow_from_github", side_effect=fake_github_fetch), \
         patch("workflows.get_default_branch", return_value="main"):
        resp = _bulk_resolve(
            db_state["project_id"],
            [
                {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
                {"workflow_id": db_state["deploy_id"], "repo": "alice/repo2", "branch": "main"},
            ],
            resolution="use_github",
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    results_by_id = {r["workflow_id"]: r for r in body["results"]}
    assert results_by_id[db_state["ci_id"]]["success"] is True
    assert results_by_id[db_state["deploy_id"]]["success"] is False

    db = TestingSessionLocal()
    try:
        ci = db.query(Workflow).filter_by(workflow_id=db_state["ci_id"]).first()
        deploy = db.query(Workflow).filter_by(workflow_id=db_state["deploy_id"]).first()
        assert ci.workflow_git_hash == "new-sha-ci"  # succeeded item still applied
        assert deploy.workflow_git_hash == "sha-old-deploy"  # failed item untouched
    finally:
        db.close()


def test_bulk_use_github_one_item_exception_does_not_abort_the_batch(db_state):
    """Regression: an unexpected exception fetching one item (e.g. a GitHub
    API error) must be isolated to that item's result, not propagate out and
    500 the whole request - discarding results already collected for other
    items would contradict the endpoint's own partial-failure guarantee."""
    def fake_github_fetch(owner, repo, filename, token, default_branch=None):
        if "ci" in filename:
            return {"content": "name: AM_P001_ci\non: pull_request", "sha": "new-sha-ci"}
        raise Exception("GitHub API error: 403")  # e.g. rate-limited

    with patch("workflows.get_workflow_from_github", side_effect=fake_github_fetch), \
         patch("workflows.get_default_branch", return_value="main"):
        resp = _bulk_resolve(
            db_state["project_id"],
            [
                {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
                {"workflow_id": db_state["deploy_id"], "repo": "alice/repo2", "branch": "main"},
            ],
            resolution="use_github",
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    results_by_id = {r["workflow_id"]: r for r in body["results"]}
    assert results_by_id[db_state["ci_id"]]["success"] is True
    assert results_by_id[db_state["deploy_id"]]["success"] is False
    assert "403" in results_by_id[db_state["deploy_id"]]["message"]


def test_bulk_use_github_caches_default_branch_per_repo(db_state):
    """Regression: two items in the same repo should resolve the repo's
    default branch once, not once per item."""
    def fake_github_fetch(owner, repo, filename, token, default_branch=None):
        assert default_branch == "main"  # the cached value was actually forwarded
        return {"content": f"name: {filename}\non: pull_request", "sha": f"sha-{filename}"}

    with patch("workflows.get_workflow_from_github", side_effect=fake_github_fetch), \
         patch("workflows.get_default_branch", return_value="main") as mock_default_branch:
        resp = _bulk_resolve(
            db_state["project_id"],
            [
                {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
                {"workflow_id": db_state["deploy_id"], "repo": "alice/repo1", "branch": "main"},
            ],
            resolution="use_github",
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True
    assert mock_default_branch.call_count == 1


# ----------------------------------------------------------------------------
# restore_actionsmanager + direct
# ----------------------------------------------------------------------------

@patch('workflows._check_existing_workflow_content', return_value=("existing-sha", False))
@patch('workflows.github_put')
def test_bulk_restore_direct_pushes_both_workflows(mock_put, _check, db_state):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"content": {"sha": "fresh-sha"}}
    mock_put.return_value = mock_resp

    resp = _bulk_resolve(
        db_state["project_id"],
        [
            {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
            {"workflow_id": db_state["deploy_id"], "repo": "alice/repo2", "branch": "main"},
        ],
        resolution="restore_actionsmanager",
        delivery_mode="direct",
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert len(body["results"]) == 2
    assert all(r["success"] for r in body["results"])
    assert mock_put.call_count == 2

    db = TestingSessionLocal()
    try:
        ci = db.query(Workflow).filter_by(workflow_id=db_state["ci_id"]).first()
        deploy = db.query(Workflow).filter_by(workflow_id=db_state["deploy_id"]).first()
        assert ci.workflow_git_hash == "fresh-sha"
        assert deploy.workflow_git_hash == "fresh-sha"
        # Regression: a direct push means the repo now matches our managed
        # version - workflow_status and project.pr_state must reflect that.
        assert ci.workflow_status == "synced_with_github"
        assert deploy.workflow_status == "synced_with_github"
        project = db.query(Project).filter_by(project_id=db_state["project_id"]).first()
        assert project.pr_state == "synced"
    finally:
        db.close()


@patch('workflows._check_existing_workflow_content', return_value=("existing-sha", False))
@patch('workflows.github_put')
def test_bulk_restore_direct_partial_failure_sets_project_pr_state_draft(mock_put, _check, db_state):
    """One push succeeds, one fails - the failed workflow's status is left
    untouched, the succeeded one is synced, and the project is left "draft"
    (not "synced") since the batch didn't fully complete."""
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {"content": {"sha": "fresh-sha"}}
    fail_resp = MagicMock()
    fail_resp.status_code = 502
    fail_resp.text = "GitHub is down"
    mock_put.side_effect = [ok_resp, fail_resp]

    resp = _bulk_resolve(
        db_state["project_id"],
        [
            {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
            {"workflow_id": db_state["deploy_id"], "repo": "alice/repo2", "branch": "main"},
        ],
        resolution="restore_actionsmanager",
        delivery_mode="direct",
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    results_by_id = {r["workflow_id"]: r for r in body["results"]}
    assert results_by_id[db_state["ci_id"]]["success"] is True
    assert results_by_id[db_state["deploy_id"]]["success"] is False

    db = TestingSessionLocal()
    try:
        ci = db.query(Workflow).filter_by(workflow_id=db_state["ci_id"]).first()
        deploy = db.query(Workflow).filter_by(workflow_id=db_state["deploy_id"]).first()
        assert ci.workflow_status == "synced_with_github"  # succeeded item advanced
        assert deploy.workflow_status == "committed_locally"  # failed item untouched (fixture default)
        project = db.query(Project).filter_by(project_id=db_state["project_id"]).first()
        assert project.pr_state == "draft"
    finally:
        db.close()


# ----------------------------------------------------------------------------
# restore_actionsmanager + pr
# ----------------------------------------------------------------------------

@patch('workflows._process_reusable_workflows_update', return_value={})
@patch('workflows._process_regular_workflows_update')
def test_bulk_restore_pr_same_repo_creates_single_pr(mock_regular, _mock_reusable, db_state):
    """Two workflows restored to the SAME repo must land in exactly one PR call."""
    mock_regular.return_value = {
        "alice/repo1 on main": {
            "status": "pr_created",
            "pr_number": 42,
            "pr_url": "https://github.com/alice/repo1/pull/42",
            "branch_name": "actions-manager/p001/alice-repo1/abc-main",
            "workflows_committed": ["AM_P001_ci.yml", "AM_P001_deploy.yml"],
        }
    }

    resp = _bulk_resolve(
        db_state["project_id"],
        [
            {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
            {"workflow_id": db_state["deploy_id"], "repo": "alice/repo1", "branch": "main"},
        ],
        resolution="restore_actionsmanager",
        delivery_mode="pr",
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert len(body["results"]) == 2
    assert all(r["success"] for r in body["results"])
    assert all(r["pr_url"] == "https://github.com/alice/repo1/pull/42" for r in body["results"])

    # Exactly one create_pull_requests -> _process_regular_workflows_update call,
    # scoped to the one repo, with both workflow names included.
    assert mock_regular.call_count == 1
    assert mock_regular.call_args.kwargs["repo_names"] == ["alice/repo1"]
    workflow_names = {w["name"] for w in mock_regular.call_args.kwargs["workflows"]}
    assert workflow_names == {"ci", "deploy"}


@patch('workflows._process_reusable_workflows_update', return_value={})
@patch('workflows._process_regular_workflows_update')
def test_bulk_restore_pr_different_repos_creates_separate_prs(mock_regular, _mock_reusable, db_state):
    """Two workflows restored to DIFFERENT repos must produce two separate PR groupings."""
    def fake_regular(repo_names, workflows, **kwargs):
        repo = repo_names[0]
        return {
            f"{repo} on main": {
                "status": "pr_created",
                "pr_number": 1 if repo == "alice/repo1" else 2,
                "pr_url": f"https://github.com/{repo}/pull/{1 if repo == 'alice/repo1' else 2}",
                "branch_name": f"actions-manager/p001/{repo.split('/')[-1]}/abc-main",
                "workflows_committed": [w["name"] for w in workflows],
            }
        }
    mock_regular.side_effect = fake_regular

    resp = _bulk_resolve(
        db_state["project_id"],
        [
            {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
            {"workflow_id": db_state["deploy_id"], "repo": "alice/repo2", "branch": "main"},
        ],
        resolution="restore_actionsmanager",
        delivery_mode="pr",
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    results_by_repo = {r["repo"]: r for r in body["results"]}
    assert results_by_repo["alice/repo1"]["pr_url"] == "https://github.com/alice/repo1/pull/1"
    assert results_by_repo["alice/repo2"]["pr_url"] == "https://github.com/alice/repo2/pull/2"

    assert mock_regular.call_count == 2
    called_repo_names = sorted(c.kwargs["repo_names"][0] for c in mock_regular.call_args_list)
    assert called_repo_names == ["alice/repo1", "alice/repo2"]


@patch('workflows._process_reusable_workflows_update', return_value={})
@patch('workflows._process_regular_workflows_update')
def test_bulk_restore_pr_reports_per_repo_error_status_as_failure(mock_regular, _mock_reusable, db_state):
    """Regression: a per-repo/branch "error" status from
    _process_regular_workflows_update must be reported as a failed item, not
    silently swallowed as success (the endpoint must not claim a PR was
    opened when it wasn't)."""
    mock_regular.return_value = {
        "alice/repo1 on main": {
            "status": "error",
            "error": "Branch protection blocked the push",
        }
    }

    resp = _bulk_resolve(
        db_state["project_id"],
        [
            {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
            {"workflow_id": db_state["deploy_id"], "repo": "alice/repo1", "branch": "main"},
        ],
        resolution="restore_actionsmanager",
        delivery_mode="pr",
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert len(body["results"]) == 2
    for r in body["results"]:
        assert r["success"] is False
        assert "Branch protection blocked the push" in r["message"]
        assert r["pr_url"] is None


@patch('workflows._process_reusable_workflows_update', return_value={})
@patch('workflows._process_regular_workflows_update')
def test_bulk_restore_pr_reports_top_level_error_as_failure(mock_regular, _mock_reusable, db_state):
    """Regression: when _process_regular_workflows_update fails before any
    per-repo processing (e.g. bad branch pattern), it returns a bare
    {"error": ..., "status": 400} dict instead of a per-repo-keyed one - this
    must also be reported as a failure, not misread as an empty-but-successful
    per-repo lookup."""
    mock_regular.return_value = {"error": "Invalid branch regex", "status": 400}

    resp = _bulk_resolve(
        db_state["project_id"],
        [{"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"}],
        resolution="restore_actionsmanager",
        delivery_mode="pr",
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["results"][0]["success"] is False
    assert "Invalid branch regex" in body["results"][0]["message"]


# ----------------------------------------------------------------------------
# Validation / authorization / edge cases
# ----------------------------------------------------------------------------

def test_bulk_resolve_empty_items_returns_400(db_state):
    resp = _bulk_resolve(db_state["project_id"], [], resolution="use_github")
    assert resp.status_code == 400


def test_bulk_resolve_invalid_resolution_returns_400(db_state):
    resp = _bulk_resolve(
        db_state["project_id"],
        [{"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"}],
        resolution="not_a_real_resolution",
    )
    assert resp.status_code == 400


def test_bulk_resolve_unauthenticated_returns_401(db_state):
    user_tokens.pop("alice", None)
    resp = _bulk_resolve(
        db_state["project_id"],
        [{"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"}],
        resolution="use_github",
    )
    assert resp.status_code == 401


def test_bulk_resolve_unknown_project_returns_404(db_state):
    resp = _bulk_resolve(
        999999,
        [{"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"}],
        resolution="use_github",
    )
    assert resp.status_code == 404


def test_bulk_resolve_item_from_other_project_returns_403(db_state):
    """An item naming a workflow that belongs to a DIFFERENT project is rejected
    before any writes happen - the whole batch fails closed."""
    resp = _bulk_resolve(
        db_state["project_id"],
        [
            {"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"},
            {"workflow_id": db_state["foreign_id"], "repo": "alice/repo1", "branch": "main"},
        ],
        resolution="use_github",
    )
    assert resp.status_code == 403

    # Nothing was written - fail-closed before any per-item processing.
    db = TestingSessionLocal()
    try:
        ci = db.query(Workflow).filter_by(workflow_id=db_state["ci_id"]).first()
        assert ci.workflow_git_hash == "sha-old-ci"
    finally:
        db.close()


def test_bulk_resolve_wrong_user_returns_403(db_state):
    user_tokens["mallory"] = "mallory-token"
    try:
        resp = _bulk_resolve(
            db_state["project_id"],
            [{"workflow_id": db_state["ci_id"], "repo": "alice/repo1", "branch": "main"}],
            resolution="use_github",
            github_user="mallory",
        )
        assert resp.status_code == 403
    finally:
        user_tokens.pop("mallory", None)
