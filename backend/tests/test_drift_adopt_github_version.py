"""
Tests for the scope-aware drift resolution flow (issue: design-level drift fix).

Covers:

  * Drift detection consults per-repo overrides (via _get_repo_workflow_override).
  * /api/drift/adopt-github-version with the three resolution modes:
      - create_repo_override     – does NOT modify the project workflow.
      - adopt_local_only         – preserves legacy "Keep GitHub Version".
      - adopt_project_and_sync   – updates project + syncs other repos.
  * Drift detail response carries scope-aware metadata
    (is_shared_workflow, has_repo_override, affected_repos, ...).
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
from models import (  # noqa: E402
    Base, Account, Project, Repo, ProjectRepo, Workflow, ProjectWorkflow,
    RepoWorkflowOverride, ProjectPullRequest,
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
    """Two repos sharing a single project workflow."""
    prev_override = app.dependency_overrides.get(real_get_db)
    app.dependency_overrides[real_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        user = Account(github_user="alice", github_email="a@example.com", account_type="free")
        db.add(user); db.commit(); db.refresh(user)

        project = Project(
            project_name="proj1", project_code="P001",
            user_id=user.user_id, branch_option="default", use_prefix=True,
            pr_state="synced",
        )
        db.add(project); db.commit(); db.refresh(project)

        repo1 = Repo(repo_name="whatsupdawg/test1")
        repo2 = Repo(repo_name="whatsupdawg/test2")
        db.add_all([repo1, repo2]); db.commit()
        db.refresh(repo1); db.refresh(repo2)
        db.add_all([
            ProjectRepo(project_id=project.project_id, repo_id=repo1.repo_id),
            ProjectRepo(project_id=project.project_id, repo_id=repo2.repo_id),
        ])
        db.commit()

        wf = Workflow(
            workflow_name="ci",
            workflow_yaml="name: AM_P001_ci\non: push",
            workflow_git_hash="sha-old",
            reusable_workflow=False,
            workflow_status="synced_with_github",
        )
        db.add(wf); db.commit(); db.refresh(wf)
        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
        db.commit()

        user_tokens["alice"] = "test-token"

        yield {
            "user_id": user.user_id,
            "project_id": project.project_id,
            "workflow_id": wf.workflow_id,
            "repo1_id": repo1.repo_id,
            "repo2_id": repo2.repo_id,
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        user_tokens.pop("alice", None)
        if prev_override is None:
            app.dependency_overrides.pop(real_get_db, None)
        else:
            app.dependency_overrides[real_get_db] = prev_override


# ---------------------------------------------------------------------------
# Drift detail metadata
# ---------------------------------------------------------------------------

@patch('workflows.get_default_branch', return_value="main")
@patch('workflows.fetch_workflow_tree', return_value=({"AM_P001_ci.yml": "sha-new"}, None))
@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request", "sha": "sha-new",
})
def test_drift_detail_includes_shared_metadata(_g, _shas, _branch, db_state):
    """Drift response should mark workflow as shared and list affected repos."""
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice", "refresh": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Both repos drift since both compare against the (now stale) project workflow
    assert body["drift_count"] >= 1
    drift = body["drifted_workflows"][0]
    assert drift["is_shared_workflow"] is True
    assert drift["has_repo_override"] is False
    assert drift["override_id"] is None
    # affected_repos excludes the source repo
    assert drift["source_repo_name"] == drift["repo"]
    assert drift["repo"] not in drift["affected_repos"]
    assert drift["affected_repo_count"] == len(drift["affected_repos"])


# ---------------------------------------------------------------------------
# create_repo_override
# ---------------------------------------------------------------------------

@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request",
    "sha": "sha-new",
})
def test_adopt_github_create_repo_override(_g, db_state):
    """create_repo_override stores override and DOES NOT touch the project workflow."""
    resp = client.post(
        "/api/drift/adopt-github-version",
        json={
            "github_user": "alice",
            "project_id": db_state["project_id"],
            "repo_id": db_state["repo1_id"],
            "workflow_id": db_state["workflow_id"],
            "resolution_mode": "create_repo_override",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["resolution_mode"] == "create_repo_override"
    assert body["updated_project_workflow"] is False
    assert body["created_or_updated_override"] is not None
    assert body["created_or_updated_override"]["source_repo_name"] == "whatsupdawg/test1"

    db = TestingSessionLocal()
    try:
        # Project workflow content unchanged
        wf = db.query(Workflow).filter_by(workflow_id=db_state["workflow_id"]).first()
        assert wf.workflow_git_hash == "sha-old"
        assert "pull_request" not in wf.workflow_yaml
        # Override row created
        ov = db.query(RepoWorkflowOverride).filter_by(
            project_id=db_state["project_id"],
            repo_id=db_state["repo1_id"],
            workflow_id=db_state["workflow_id"],
        ).first()
        assert ov is not None
        assert ov.workflow_git_hash == "sha-new"
        assert "pull_request" in ov.workflow_yaml
    finally:
        db.close()


@patch('workflows.get_default_branch', return_value="main")
@patch('workflows.fetch_workflow_tree', return_value=({"AM_P001_ci.yml": "sha-new"}, None))
@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request", "sha": "sha-new",
})
def test_drift_uses_override_when_present(_g, _shas, _branch, db_state):
    """A repo with an override compares against the override, not the project."""
    db = TestingSessionLocal()
    try:
        db.add(RepoWorkflowOverride(
            project_id=db_state["project_id"],
            repo_id=db_state["repo1_id"],
            workflow_id=db_state["workflow_id"],
            workflow_name="ci",
            workflow_yaml="name: AM_P001_ci\non: pull_request",
            workflow_git_hash="sha-new",
            source_repo_name="whatsupdawg/test1",
        ))
        db.commit()
    finally:
        db.close()

    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice", "refresh": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    drifts_for_repo1 = [d for d in body["drifted_workflows"] if d["repo"] == "whatsupdawg/test1"]
    # repo1 should NOT be drifted because override matches GitHub
    assert drifts_for_repo1 == []


# ---------------------------------------------------------------------------
# adopt_local_only
# ---------------------------------------------------------------------------

@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request",
    "sha": "sha-new",
})
def test_adopt_github_local_only_updates_project_only(_g, db_state):
    """adopt_local_only updates the project workflow but does not sync other repos."""
    resp = client.post(
        "/api/drift/adopt-github-version",
        json={
            "github_user": "alice",
            "project_id": db_state["project_id"],
            "repo_id": db_state["repo1_id"],
            "workflow_id": db_state["workflow_id"],
            "resolution_mode": "adopt_local_only",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["resolution_mode"] == "adopt_local_only"
    assert body["updated_project_workflow"] is True
    # Other repo (test2) should be in affected list, signalling a warning
    assert "whatsupdawg/test2" in body["affected_repos"]
    assert body["new_drift_status"] == "drifted_on_other_repos"

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=db_state["workflow_id"]).first()
        assert wf.workflow_git_hash == "sha-new"
        assert "pull_request" in wf.workflow_yaml
        # No overrides created
        assert db.query(RepoWorkflowOverride).count() == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# adopt_project_and_sync (PR delivery)
# ---------------------------------------------------------------------------

@patch('workflows.create_pull_requests', return_value={"created": [], "skipped": []})
@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request",
    "sha": "sha-new",
})
def test_adopt_project_and_sync_pr_mode(_g, mock_create, db_state):
    """adopt_project_and_sync (PR) updates project workflow and triggers PRs for affected repos."""
    resp = client.post(
        "/api/drift/adopt-github-version",
        json={
            "github_user": "alice",
            "project_id": db_state["project_id"],
            "repo_id": db_state["repo1_id"],
            "workflow_id": db_state["workflow_id"],
            "resolution_mode": "adopt_project_and_sync",
            "delivery_mode": "pr",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["resolution_mode"] == "adopt_project_and_sync"
    assert body["updated_project_workflow"] is True
    assert body["affected_repos"] == ["whatsupdawg/test2"]
    assert body["new_drift_status"] == "pr_pending"
    assert mock_create.called
    # PR creation should be scoped to the affected repos (test2 only).
    sent_payload = mock_create.call_args[0][0]
    assert sent_payload.selected_repos == ["whatsupdawg/test2"]
    assert sent_payload.selected_workflows == ["ci"]


@patch('workflows._process_reusable_workflows_update', return_value={})
@patch('workflows._process_regular_workflows_update')
@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request",
    "sha": "sha-new",
})
def test_adopt_project_and_sync_pr_mode_runs_real_pipeline(_g, mock_regular, _mock_reusable, db_state):
    """Regression: adopt_project_and_sync (PR) must not 500. Unlike the mocked
    test above, this exercises the REAL create_pull_requests so the internal
    call-site argument passing (background_tasks/db) is verified end to end,
    and persists a PR only for the affected repo.
    """
    mock_regular.return_value = {
        "whatsupdawg/test2 on main": {
            "status": "pr_created",
            "pr_number": 7,
            "pr_url": "https://github.com/whatsupdawg/test2/pull/7",
            "branch_name": "actions-manager/p001/whatsupdawg-test2/abc-main",
            "workflows_committed": ["AM_P001_ci.yml"],
        }
    }

    resp = client.post(
        "/api/drift/adopt-github-version",
        json={
            "github_user": "alice",
            "project_id": db_state["project_id"],
            "repo_id": db_state["repo1_id"],
            "workflow_id": db_state["workflow_id"],
            "resolution_mode": "adopt_project_and_sync",
            "delivery_mode": "pr",
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["new_drift_status"] == "pr_pending"
    assert mock_regular.call_args.kwargs["repo_names"] == ["whatsupdawg/test2"]

    db = TestingSessionLocal()
    try:
        prs = db.query(ProjectPullRequest).filter_by(
            project_id=db_state["project_id"]
        ).all()
        assert len(prs) == 1
        assert prs[0].repo_name == "whatsupdawg/test2"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# adopt_project_and_sync excludes overridden repos
# ---------------------------------------------------------------------------

@patch('workflows.create_pull_requests', return_value={"created": []})
@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request",
    "sha": "sha-new",
})
def test_project_sync_does_not_overwrite_overrides(_g, mock_create, db_state):
    """A repo with an override is excluded from the default sync target list."""
    db = TestingSessionLocal()
    try:
        db.add(RepoWorkflowOverride(
            project_id=db_state["project_id"],
            repo_id=db_state["repo2_id"],  # test2 has an override
            workflow_id=db_state["workflow_id"],
            workflow_name="ci",
            workflow_yaml="name: custom",
            workflow_git_hash="sha-custom",
            source_repo_name="whatsupdawg/test2",
        ))
        db.commit()
    finally:
        db.close()

    resp = client.post(
        "/api/drift/adopt-github-version",
        json={
            "github_user": "alice",
            "project_id": db_state["project_id"],
            "repo_id": db_state["repo1_id"],
            "workflow_id": db_state["workflow_id"],
            "resolution_mode": "adopt_project_and_sync",
            "delivery_mode": "pr",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # test2 has an override, so it should NOT be in the affected/sync list.
    assert body["affected_repos"] == []
    # No PR should be opened since there is nothing to sync.
    assert mock_create.called is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_adopt_github_invalid_mode(db_state):
    resp = client.post(
        "/api/drift/adopt-github-version",
        json={
            "github_user": "alice",
            "project_id": db_state["project_id"],
            "repo_id": db_state["repo1_id"],
            "workflow_id": db_state["workflow_id"],
            "resolution_mode": "bogus_mode",
        },
    )
    assert resp.status_code == 400


def test_adopt_github_unauthenticated(db_state):
    user_tokens.pop("alice", None)
    resp = client.post(
        "/api/drift/adopt-github-version",
        json={
            "github_user": "alice",
            "project_id": db_state["project_id"],
            "repo_id": db_state["repo1_id"],
            "workflow_id": db_state["workflow_id"],
            "resolution_mode": "create_repo_override",
        },
    )
    assert resp.status_code == 401
