"""
Tests for deterministic drift detection behavior:
- Hash mismatch does NOT automatically mean drift
- Content mismatch means drift
- When content matches but hash differs, hash should auto-update
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
from workflows import get_db as real_get_db, _normalize_yaml_for_comparison  # noqa: E402
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
    """Fresh schema + sample project per test."""
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
        )
        db.add(project); db.commit(); db.refresh(project)

        repo = Repo(repo_name="alice/repo1")
        db.add(repo); db.commit(); db.refresh(repo)
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id)); db.commit()

        # Workflow with old hash but content matches GitHub
        wf = Workflow(
            workflow_name="ci",
            workflow_yaml="name: AM_P001_ci\non: push\n",  # Normalized: single trailing newline
            workflow_git_hash="sha-old-123",
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
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        if prev_override:
            app.dependency_overrides[real_get_db] = prev_override
        else:
            app.dependency_overrides.pop(real_get_db, None)
        user_tokens.clear()


def test_normalize_yaml_for_comparison():
    """Test YAML normalization function."""
    # Test line ending normalization
    assert _normalize_yaml_for_comparison("line1\r\nline2\r\n") == "line1\nline2\n"
    assert _normalize_yaml_for_comparison("line1\rline2\r") == "line1\nline2\n"

    # Test trailing whitespace removal
    assert _normalize_yaml_for_comparison("line1  \nline2\t\n") == "line1\nline2\n"

    # Test single trailing newline
    assert _normalize_yaml_for_comparison("content\n\n\n") == "content\n"
    assert _normalize_yaml_for_comparison("content") == "content\n"

    # Test empty content
    assert _normalize_yaml_for_comparison("") == ""
    assert _normalize_yaml_for_comparison("   \n   \n") == ""  # All whitespace becomes empty


@pytest.fixture
def mock_sha_mismatch_content_match(db_state):
    """Mock GitHub API: SHA differs from local, but content matches after normalization."""
    def mock_get_all_shas(owner, repo, branch, token):
        return {"AM_P001_ci.yml": "sha-new-456"}  # Different SHA

    def mock_get_workflow(owner, repo, filename, token):
        # Same content as local but with different whitespace (should still match after normalization)
        return {
            "content": "name: AM_P001_ci\non: push  \n",  # Trailing spaces
            "sha": "sha-new-456"
        }

    def mock_default_branch(owner, repo, headers, user=None, db=None):
        return "main"

    with patch("workflows.get_all_workflow_shas", side_effect=mock_get_all_shas), \
         patch("workflows.get_workflow_from_github", side_effect=mock_get_workflow), \
         patch("workflows.get_default_branch", side_effect=mock_default_branch):
        yield


def test_sha_mismatch_content_match_no_drift(mock_sha_mismatch_content_match, db_state):
    """When SHA differs but content matches (after normalization), no drift should be reported."""
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"}
    )
    assert resp.status_code == 200
    data = resp.json()

    # No drift should be detected
    assert data["drift_count"] == 0
    assert len(data["drifted_workflows"]) == 0


@pytest.fixture
def mock_sha_mismatch_content_differs(db_state):
    """Mock GitHub API: SHA differs and content also differs."""
    def mock_get_all_shas(owner, repo, branch, token):
        return {"AM_P001_ci.yml": "sha-new-789"}

    def mock_get_workflow(owner, repo, filename, token):
        return {
            "content": "name: AM_P001_ci\non: [push, pull_request]\n",  # Different content
            "sha": "sha-new-789"
        }

    def mock_default_branch(owner, repo, headers, user=None, db=None):
        return "main"

    with patch("workflows.get_all_workflow_shas", side_effect=mock_get_all_shas), \
         patch("workflows.get_workflow_from_github", side_effect=mock_get_workflow), \
         patch("workflows.get_default_branch", side_effect=mock_default_branch):
        yield


def test_sha_mismatch_content_differs_drift_detected(mock_sha_mismatch_content_differs, db_state):
    """When SHA differs and content also differs, drift should be detected."""
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"}
    )
    assert resp.status_code == 200
    data = resp.json()

    # Drift should be detected
    assert data["drift_count"] == 1
    assert len(data["drifted_workflows"]) == 1
    assert data["drifted_workflows"][0]["workflow_id"] == db_state["workflow_id"]
    assert data["drifted_workflows"][0]["has_drift"] is True


def test_auto_hash_update_when_content_matches(mock_sha_mismatch_content_match, db_state):
    """When content matches but SHA differs, the stored hash should auto-update."""
    db = TestingSessionLocal()
    try:
        # Get workflow before drift check
        wf_before = db.query(Workflow).filter_by(workflow_id=db_state["workflow_id"]).first()
        assert wf_before.workflow_git_hash == "sha-old-123"

        # Run drift detection
        resp = client.get(
            f"/api/projects/{db_state['project_id']}/drift",
            params={"github_user": "alice"}
        )
        assert resp.status_code == 200

        # Get workflow after drift check
        db.expire_all()  # Refresh from database
        wf_after = db.query(Workflow).filter_by(workflow_id=db_state["workflow_id"]).first()

        # Hash should have been auto-updated to GitHub's SHA
        assert wf_after.workflow_git_hash == "sha-new-456"
    finally:
        db.close()


@pytest.fixture
def mock_sha_match():
    """Mock GitHub API: SHA matches local (optimization path)."""
    def mock_get_all_shas(owner, repo, branch, token):
        return {"AM_P001_ci.yml": "sha-old-123"}  # Same as local

    def mock_default_branch(owner, repo, headers, user=None, db=None):
        return "main"

    # When SHAs match, get_workflow_from_github should NOT be called
    with patch("workflows.get_all_workflow_shas", side_effect=mock_get_all_shas), \
         patch("workflows.get_default_branch", side_effect=mock_default_branch):
        yield


def test_sha_match_no_content_fetch(mock_sha_match, db_state):
    """When SHA matches, content should not be fetched (optimization)."""
    with patch("workflows.get_workflow_from_github") as mock_get:
        resp = client.get(
            f"/api/projects/{db_state['project_id']}/drift",
            params={"github_user": "alice"}
        )
        assert resp.status_code == 200
        data = resp.json()

        # No drift
        assert data["drift_count"] == 0

        # get_workflow_from_github should NOT have been called (SHA optimization)
        mock_get.assert_not_called()


@pytest.fixture
def mock_locally_committed_workflow():
    """Test workflow with local commit hash (never pushed to GitHub)."""
    db = TestingSessionLocal()
    try:
        # Create workflow with local-only hash (all zeros)
        wf = db.query(Workflow).first()
        wf.workflow_git_hash = "0000000000000000000000000000000000000000"  # Local commit marker
        wf.workflow_status = "committed_locally"
        db.commit()
        yield
    finally:
        db.close()


@pytest.fixture
def mock_no_workflows_on_github():
    """Mock GitHub API: No workflows exist on GitHub yet."""
    def mock_get_all_shas(owner, repo, branch, token):
        return {}  # No workflows found

    def mock_default_branch(owner, repo, headers, user=None, db=None):
        return "main"

    with patch("workflows.get_all_workflow_shas", side_effect=mock_get_all_shas), \
         patch("workflows.get_default_branch", side_effect=mock_default_branch):
        yield


def test_locally_committed_workflow_no_drift(mock_locally_committed_workflow, mock_no_workflows_on_github, db_state):
    """Locally committed workflows (hash=0000...) should NOT show drift when missing from GitHub."""
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"}
    )
    assert resp.status_code == 200
    data = resp.json()

    # CRITICAL: No drift should be detected for locally committed workflows
    # These workflows have never been pushed to GitHub, so they can't be "drifted"
    assert data["drift_count"] == 0
    assert len(data["drifted_workflows"]) == 0


@pytest.fixture
def mock_workflow_with_open_pr():
    """Test workflow with open PR (never merged to target branch)."""
    db = TestingSessionLocal()
    try:
        # Get first workflow and project
        wf = db.query(Workflow).first()
        project_workflow = db.query(ProjectWorkflow).filter_by(workflow_id=wf.workflow_id).first()

        # Set workflow as locally committed (never synced to target branch)
        wf.workflow_git_hash = "0000000000000000000000000000000000000000"
        wf.workflow_status = "under_review"

        # Create an open PR for this workflow
        from models import ProjectPullRequest
        pr = ProjectPullRequest(
            project_id=project_workflow.project_id,
            repo_name="owner/repo",
            pr_number=123,
            pr_url="https://github.com/owner/repo/pull/123",
            pr_state="open",
            branch_name="am-test-branch",
            target_branch="main",
            workflow_names=wf.workflow_name,
            title="Add new workflow"
        )
        db.add(pr)
        db.commit()
        yield {"workflow": wf, "pr": pr}
    finally:
        db.close()


def test_new_workflow_with_open_pr_no_drift(mock_workflow_with_open_pr, mock_no_workflows_on_github, db_state):
    """New workflows with open PRs should NOT show drift when missing from target branch."""
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"}
    )
    assert resp.status_code == 200
    data = resp.json()

    # CRITICAL: No drift should be detected for new workflows with open PRs
    # The workflow exists in a PR branch but not on the target branch yet
    # This is expected until the PR is merged
    assert data["drift_count"] == 0
    assert len(data["drifted_workflows"]) == 0


@pytest.fixture
def mock_workflow_with_open_pr_multi_names():
    """Workflow with open PR whose workflow_names is a comma+space joined list (matches production).

    Simulates the real production scenario: after a PR is created, the
    workflow_git_hash is updated to the PR branch SHA (a real, non-zero hash),
    but the workflow file is NOT yet on the target branch. This must NOT be
    flagged as drift (it's pending merge).
    """
    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).first()
        project_workflow = db.query(ProjectWorkflow).filter_by(workflow_id=wf.workflow_id).first()

        # Real, non-zero SHA from PR branch (NOT "0000...") — production assigns
        # the PR-branch SHA after the workflow is uploaded for the PR.
        wf.workflow_git_hash = "pr-branch-sha-abc123"
        wf.workflow_status = "under_review"

        from models import ProjectPullRequest
        # Production stores as ", ".join(...) — ensure check tolerates whitespace
        # and matches a workflow that's NOT the first in the list.
        pr = ProjectPullRequest(
            project_id=project_workflow.project_id,
            repo_name="alice/repo1",
            pr_number=124,
            pr_url="https://github.com/alice/repo1/pull/124",
            pr_state="open",
            branch_name="am-test-branch",
            target_branch="main",
            workflow_names=f"some-other-wf, {wf.workflow_name}",
            title="Add new workflows"
        )
        db.add(pr)
        db.commit()
        yield {"workflow": wf, "pr": pr}
    finally:
        db.close()


@pytest.fixture
def mock_locally_modified_previously_synced_workflow():
    """Workflow that was previously synced to GitHub, then edited locally via 'Commit Locally'.

    Simulates the production flow:
    1. PR was merged, so workflow_yaml matched GitHub target branch and status was synced.
    2. User edited workflow in ActionsManager and clicked 'Commit Locally'.
    3. _save_workflow_to_db reset workflow_git_hash to all zeros and set
       workflow_status='committed_locally'. workflow_yaml now differs from
       the target branch but the workflow file still exists on the target branch.

    This MUST NOT be flagged as drift — drift means GitHub changed outside
    ActionsManager. A local AM edit is a pending sync, not drift.
    """
    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).first()
        # Simulate "Commit Locally" on previously-synced workflow
        wf.workflow_yaml = "name: AM_P001_ci\non: [push, pull_request, workflow_dispatch]\n"
        wf.workflow_git_hash = "0000000000000000000000000000000000000000"
        wf.workflow_status = "committed_locally"
        db.commit()
        yield {"workflow": wf}
    finally:
        db.close()


def test_locally_modified_previously_synced_workflow_no_drift(
    mock_locally_modified_previously_synced_workflow, mock_sha_mismatch_content_differs, db_state
):
    """Locally modified previously-synced workflows must NOT show drift.

    Workflow exists on target branch but local YAML differs because user clicked
    'Commit Locally'. Status='committed_locally' and hash=0000... indicate the
    local edit is intentional and pending sync, not GitHub drift.
    """
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"}
    )
    assert resp.status_code == 200
    data = resp.json()

    # CRITICAL: A local AM edit is NOT drift
    assert data["drift_count"] == 0
    assert len(data["drifted_workflows"]) == 0


def test_open_pr_workflow_names_with_whitespace_no_drift(mock_workflow_with_open_pr_multi_names, mock_no_workflows_on_github, db_state):
    """Workflow with PR-branch SHA but missing from target branch must NOT be drift when an open PR exists.

    Also verifies workflow_names with ', ' separator is matched correctly (whitespace-tolerant).
    """
    resp = client.get(
        f"/api/projects/{db_state['project_id']}/drift",
        params={"github_user": "alice"}
    )
    assert resp.status_code == 200
    data = resp.json()
    # Workflow has a real SHA (PR branch) but is in an open PR — must NOT be drift
    assert data["drift_count"] == 0
    assert len(data["drifted_workflows"]) == 0
