"""
Tests for the v2 drift detection endpoints introduced for the
"Detect GitHub-side workflow changes" issue:

  * GET  /api/projects/{project_id}/drift
  * GET  /api/workflows/{workflow_id}/drift
  * POST /api/workflows/{workflow_id}/resolve-drift

These tests use the FastAPI TestClient and mock GitHub network calls.
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
from workflows import get_db as real_get_db, WorkflowDriftDetail  # noqa: E402
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
    """Fresh schema + sample project per test.

    Saves and restores any pre-existing ``workflows.get_db`` dependency
    override so we don't clobber other test modules that registered their
    own override at import time (e.g. ``test_github_pr_webhook.py``).
    """
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

        repo = Repo(repo_name="alice/repo1")
        db.add(repo); db.commit(); db.refresh(repo)
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id)); db.commit()

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

        # Provide auth token used by the endpoints
        user_tokens["alice"] = "test-token"

        yield {
            "user_id": user.user_id,
            "project_id": project.project_id,
            "workflow_id": wf.workflow_id,
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


# ----------------------------------------------------------------------------
# GET /api/projects/{project_id}/drift
# ----------------------------------------------------------------------------

@patch('workflows.get_default_branch', return_value="main")
@patch('workflows.get_all_workflow_shas', return_value={"AM_P001_ci.yml": "sha-old"})
def test_project_drift_no_drift(_shas, _branch, db_state):
    """Same SHA on both sides ⇒ project drift_count == 0."""
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == db_state["project_id"]
    assert body["drift_count"] == 0
    assert body["drifted_workflows"] == []

    db = TestingSessionLocal()
    try:
        project = db.query(Project).filter_by(project_id=db_state["project_id"]).first()
        assert project.drift_status == "clean"
        assert project.drift_count == 0
        assert project.last_drift_check_at is not None
        assert project.drift_error_summary is None
    finally:
        db.close()


@patch('workflows.get_default_branch', return_value="main")
@patch('workflows.get_all_workflow_shas', return_value={"AM_P001_ci.yml": "sha-new"})
@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request",  # different content
    "sha": "sha-new",
})
def test_project_drift_one_workflow_drifted(_g, _shas, _branch, db_state):
    """SHAs differ + content differs ⇒ exactly one drifted workflow returned."""
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["drift_count"] == 1
    drift = body["drifted_workflows"][0]
    assert drift["workflow_id"] == db_state["workflow_id"]
    assert drift["repo"] == "alice/repo1"
    assert drift["branch"] == "main"
    assert drift["has_drift"] is True
    assert drift["github_yaml"] is not None
    assert drift["actionsmanager_yaml"] is not None

    db = TestingSessionLocal()
    try:
        project = db.query(Project).filter_by(project_id=db_state["project_id"]).first()
        assert project.drift_status == "drifted"
        assert project.drift_count == 1
        assert project.last_drift_check_at is not None
    finally:
        db.close()


@patch('workflows._collect_project_drift_details', side_effect=Exception("github API failed"))
def test_project_drift_check_failure_updates_cached_summary(_collect, db_state):
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 500

    db = TestingSessionLocal()
    try:
        project = db.query(Project).filter_by(project_id=db_state["project_id"]).first()
        assert project.drift_status == "check_failed"
        assert project.drift_count == 0
        assert project.last_drift_check_at is not None
        assert "github API failed" in (project.drift_error_summary or "")
    finally:
        db.close()


def test_project_drift_unauthenticated(db_state):
    """Caller without an entry in user_tokens gets 401."""
    user_tokens.pop("alice", None)
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 401


def test_project_drift_unknown_project(db_state):
    resp = client.get(
        "/api/projects/9999/drift",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 404


def test_projects_list_includes_cached_drift_summary_fields(db_state):
    db = TestingSessionLocal()
    try:
        project = db.query(Project).filter_by(project_id=db_state["project_id"]).first()
        project.drift_status = "drifted"
        project.drift_count = 3
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/", params={"github_user": "alice"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["drift_status"] == "drifted"
    assert rows[0]["drift_count"] == 3
    assert "last_drift_check_at" in rows[0]
    assert "drift_error_summary" in rows[0]


# ----------------------------------------------------------------------------
# GET /api/workflows/{workflow_id}/drift
# ----------------------------------------------------------------------------

@patch('workflows.get_default_branch', return_value="main")
@patch('workflows.get_all_workflow_shas', return_value={"AM_P001_ci.yml": "sha-new"})
@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request",
    "sha": "sha-new",
})
def test_workflow_drift_detail_returns_yaml(_g, _shas, _branch, db_state):
    resp = client.get(
        f"/api/workflows/{db_state['workflow_id']}/drift",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workflow_id"] == db_state["workflow_id"]
    assert body["has_drift"] is True
    assert body["workflow_filename"] == "AM_P001_ci.yml"
    assert len(body["drift_details"]) == 1
    detail = body["drift_details"][0]
    assert "actionsmanager_yaml" in detail
    assert "github_yaml" in detail
    assert detail["repo"] == "alice/repo1"


def test_workflow_drift_unknown_workflow(db_state):
    resp = client.get(
        "/api/workflows/9999/drift",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 404


# ----------------------------------------------------------------------------
# POST /api/workflows/{workflow_id}/resolve-drift
# ----------------------------------------------------------------------------

@patch('workflows.get_workflow_from_github', return_value={
    "content": "name: AM_P001_ci\non: pull_request",
    "sha": "sha-new",
})
def test_resolve_drift_use_github_overwrites_local(_g, db_state):
    """``use_github`` should replace local YAML + refresh stored hash."""
    # The endpoint re-runs drift detection after applying the change to confirm
    # resolution. Stub it out to return a synced detail so the success branch
    # is exercised here (the underlying drift collector hits multiple GitHub
    # APIs that aren't worth wiring up for this assertion).
    synced_detail = WorkflowDriftDetail(
        workflow_id=db_state["workflow_id"],
        workflow_name="ci",
        workflow_filename="AM_P001_ci.yml",
        repo="alice/repo1",
        branch="main",
        has_drift=False,
        github_sha="sha-new",
        last_checked="2024-01-01T00:00:00Z",
        message="synced",
    )
    with patch(
        'workflows._collect_project_drift_details',
        return_value=[synced_detail],
    ):
        resp = client.post(
            f"/api/workflows/{db_state['workflow_id']}/resolve-drift",
            json={
                "github_user": "alice",
                "repo": "alice/repo1",
                "branch": "main",
                "resolution": "use_github",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "use_github"
    assert body["state"] == "synced"
    # The use_github response surfaces the new SHA via ``github_hash``
    # (``github_sha`` is used by the restore_actionsmanager/direct path).
    assert body["github_hash"] == "sha-new"

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=db_state["workflow_id"]).first()
        assert wf.workflow_git_hash == "sha-new"
        assert "pull_request" in wf.workflow_yaml
    finally:
        db.close()


@patch('workflows.get_workflow_from_github', return_value=None)
def test_resolve_drift_use_github_missing_on_github_returns_404(_g, db_state):
    resp = client.post(
        f"/api/workflows/{db_state['workflow_id']}/resolve-drift",
        json={
            "github_user": "alice",
            "repo": "alice/repo1",
            "branch": "main",
            "resolution": "use_github",
        },
    )
    assert resp.status_code == 404


@patch('workflows._check_existing_workflow_content', return_value=("existing-sha", False))
@patch('workflows.github_put')
def test_resolve_drift_restore_actionsmanager_direct_pushes_yaml(mock_put, _check, db_state):
    """``restore_actionsmanager`` + ``direct`` should PUT contents API and persist new SHA."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"content": {"sha": "fresh-sha"}}
    mock_put.return_value = mock_resp

    resp = client.post(
        f"/api/workflows/{db_state['workflow_id']}/resolve-drift",
        json={
            "github_user": "alice",
            "repo": "alice/repo1",
            "branch": "main",
            "resolution": "restore_actionsmanager",
            "delivery_mode": "direct",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivery_mode"] == "direct"
    assert body["github_sha"] == "fresh-sha"
    assert mock_put.called

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=db_state["workflow_id"]).first()
        assert wf.workflow_git_hash == "fresh-sha"
    finally:
        db.close()


def test_resolve_drift_invalid_resolution_returns_400(db_state):
    resp = client.post(
        f"/api/workflows/{db_state['workflow_id']}/resolve-drift",
        json={
            "github_user": "alice",
            "repo": "alice/repo1",
            "branch": "main",
            "resolution": "wat",
        },
    )
    assert resp.status_code == 400


def test_resolve_drift_invalid_repo_format_returns_400(db_state):
    resp = client.post(
        f"/api/workflows/{db_state['workflow_id']}/resolve-drift",
        json={
            "github_user": "alice",
            "repo": "no-slash",
            "branch": "main",
            "resolution": "use_github",
        },
    )
    assert resp.status_code == 400


def test_resolve_drift_unauthenticated_returns_401(db_state):
    user_tokens.pop("alice", None)
    resp = client.post(
        f"/api/workflows/{db_state['workflow_id']}/resolve-drift",
        json={
            "github_user": "alice",
            "repo": "alice/repo1",
            "branch": "main",
            "resolution": "use_github",
        },
    )
    assert resp.status_code == 401
