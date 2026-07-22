"""
Mock tests for GET /api/projects/{name} workflow status auto-correction.

The root cause of "workflow stuck on Under Review after PR merged on GitHub":
  - GET /api/projects/{name} returned raw workflow_status from DB without checking
    whether tracked PRs (in ProjectPullRequest) were already resolved.
  - This caused the badge to show "Under Review" even when all PRs were merged,
    because the stale Workflow.workflow_status was never corrected.

These tests verify the auto-correction in get_project (projects.py) works correctly
across all scenarios a real user would encounter after merging a PR on GitHub.
"""
import sys
import os
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    Base,
    Account,
    Project,
    Workflow,
    ProjectWorkflow,
    ProjectPullRequest,
    LinkedReusableWorkflow,
)
from main import app
from projects import get_db as projects_get_db

# ---------------------------------------------------------------------------
# Test database
# ---------------------------------------------------------------------------

TEST_PROJECT_NAME = "myproject"
TEST_GITHUB_USER = "testuser"

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_get_project_autocorrect.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """TestClient with the test DB wired in for both projects and workflows routers."""
    app.dependency_overrides[projects_get_db] = override_get_db
    with patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.pop(projects_get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(db, *, pr_state="open"):
    account = Account(
        github_user=TEST_GITHUB_USER,
        github_email="test@example.com",
        account_type="free",
    )
    db.add(account)
    db.flush()

    project = Project(
        project_name=TEST_PROJECT_NAME,
        project_code="MP1",
        user_id=account.user_id,
        pr_state=pr_state,
    )
    db.add(project)
    db.flush()
    return account, project


def _add_workflow(db, project, *, status="under_review", reusable=False):
    wf = Workflow(
        workflow_name="ci.yml",
        workflow_yaml="on: push",
        reusable_workflow=reusable,
        workflow_status=status,
    )
    db.add(wf)
    db.flush()
    pw = ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id)
    db.add(pw)
    db.flush()
    return wf


def _add_pr(db, project, *, pr_state="open"):
    pr = ProjectPullRequest(
        project_id=project.project_id,
        repo_name="testuser/myrepo",
        pr_number=42,
        pr_url="https://github.com/testuser/myrepo/pull/42",
        branch_name="feature",
        target_branch="main",
        pr_state=pr_state,
    )
    db.add(pr)
    db.flush()
    return pr


# ---------------------------------------------------------------------------
# Test 1: The critical bug — workflow "under_review", PR already "merged" in DB
# ---------------------------------------------------------------------------

def test_workflow_under_review_corrected_to_synced_when_pr_merged_in_db(client):
    """
    SCENARIO: User merged PR on GitHub. A previous page-load already updated
    ProjectPullRequest.pr_state to "merged" in the DB, but Workflow.workflow_status
    is still "under_review" (the old stale state).

    EXPECTED: GET /api/projects/{name} must auto-correct and return
    workflowStatus="synced_with_github" so the badge shows correctly on first render.
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="open")
        _add_workflow(db, project, status="under_review")
        _add_pr(db, project, pr_state="merged")   # ← already merged in DB
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Badge must show synced
    assert len(data["workflows"]) == 1
    assert data["workflows"][0]["workflowStatus"] == "synced_with_github", (
        f"Expected synced_with_github but got {data['workflows'][0]['workflowStatus']!r}"
    )
    # Project state must also be corrected
    assert data["pr_state"] == "synced"


# ---------------------------------------------------------------------------
# Test 2: PR still "open" in DB — no correction should happen (needs GitHub API)
# ---------------------------------------------------------------------------

def test_workflow_under_review_unchanged_when_pr_still_open_in_db(client):
    """
    SCENARIO: PR hasn't been synced from GitHub yet — ProjectPullRequest.pr_state
    is still "open". Correction must NOT fire (could be a genuinely open PR).
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="open")
        _add_workflow(db, project, status="under_review")
        _add_pr(db, project, pr_state="open")   # still open in DB
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Badge must stay under_review since PR is still open
    assert data["workflows"][0]["workflowStatus"] == "under_review"
    assert data["pr_state"] == "open"


# ---------------------------------------------------------------------------
# Test 3: All PRs closed without merge → revert to committed_locally
# ---------------------------------------------------------------------------

def test_workflow_under_review_reverted_when_all_prs_closed_without_merge(client):
    """
    SCENARIO: PR was closed without merging on GitHub. DB reflects pr_state="closed".
    The workflow should revert from "under_review" to "committed_locally".
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="open")
        _add_workflow(db, project, status="under_review")
        _add_pr(db, project, pr_state="closed")   # closed without merge
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["workflows"][0]["workflowStatus"] == "committed_locally"
    assert data["pr_state"] == "draft"


# ---------------------------------------------------------------------------
# Test 4: Multiple PRs — one merged, one still open → no correction yet
# ---------------------------------------------------------------------------

def test_no_correction_when_one_pr_still_open(client):
    """
    SCENARIO: Project has two PRs. One merged, one still open. No correction
    should fire because open_pr_count > 0.
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="open")
        _add_workflow(db, project, status="under_review")

        pr1 = ProjectPullRequest(
            project_id=project.project_id,
            repo_name="testuser/repo1",
            pr_number=1,
            pr_url="https://github.com/testuser/repo1/pull/1",
            branch_name="feat",
            target_branch="main",
            pr_state="merged",
        )
        pr2 = ProjectPullRequest(
            project_id=project.project_id,
            repo_name="testuser/repo2",
            pr_number=2,
            pr_url="https://github.com/testuser/repo2/pull/2",
            branch_name="feat",
            target_branch="main",
            pr_state="open",   # still open
        )
        db.add_all([pr1, pr2])
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Badge must stay under_review
    assert data["workflows"][0]["workflowStatus"] == "under_review"
    assert data["pr_state"] == "open"


# ---------------------------------------------------------------------------
# Test 5: No tracked PRs — no correction
# ---------------------------------------------------------------------------

def test_no_correction_when_no_tracked_prs(client):
    """
    SCENARIO: Project has a workflow but no tracked PRs. No correction should fire.
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="open")
        _add_workflow(db, project, status="under_review")
        # No PRs added
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["workflows"][0]["workflowStatus"] == "under_review"


# ---------------------------------------------------------------------------
# Test 6: Workflow already "synced_with_github" — no change needed
# ---------------------------------------------------------------------------

def test_no_change_when_workflow_already_synced(client):
    """
    SCENARIO: Workflow is already synced. No DB write should occur (idempotent).
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="synced")
        _add_workflow(db, project, status="synced_with_github")
        _add_pr(db, project, pr_state="merged")
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["workflows"][0]["workflowStatus"] == "synced_with_github"
    assert data["pr_state"] == "synced"


# ---------------------------------------------------------------------------
# Test 7: Reusable workflow IS now auto-corrected (RWX project support)
# ---------------------------------------------------------------------------

def test_reusable_workflow_auto_corrected_when_pr_merged(client):
    """
    SCENARIO: RWX project has a reusable workflow under_review, and the only
    tracked PR is merged.  Auto-correction must now cover reusable workflows
    (rxworkflows) as well so that RWX projects reflect the same lock/badge
    behaviour as standard projects.
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="open")
        _add_workflow(db, project, status="under_review", reusable=True)   # reusable
        _add_pr(db, project, pr_state="merged")
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Reusable workflows go into rxworkflows list; they are now auto-corrected
    assert data["rxworkflows"][0]["workflowStatus"] == "synced_with_github", (
        f"Expected synced_with_github but got {data['rxworkflows'][0]['workflowStatus']!r}"
    )
    # Project pr_state must also be corrected
    assert data["pr_state"] == "synced"


def test_reusable_workflow_unchanged_when_pr_still_open(client):
    """
    SCENARIO: Reusable workflow is under_review, PR still open → no correction.
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="open")
        _add_workflow(db, project, status="under_review", reusable=True)
        _add_pr(db, project, pr_state="open")
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["rxworkflows"][0]["workflowStatus"] == "under_review"
    assert data["pr_state"] == "open"


def test_reusable_workflow_reverted_when_pr_closed_without_merge(client):
    """
    SCENARIO: Reusable workflow is under_review, PR closed without merge →
    revert to committed_locally.
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db, pr_state="open")
        _add_workflow(db, project, status="under_review", reusable=True)
        _add_pr(db, project, pr_state="closed")
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["rxworkflows"][0]["workflowStatus"] == "committed_locally"
    assert data["pr_state"] == "draft"


# ---------------------------------------------------------------------------
# Test 8: branch_option returned correctly (regression for the NameError bug)
# ---------------------------------------------------------------------------

def test_branch_option_returned_correctly(client):
    """
    Regression test: before the bug fix, branch_option was referenced before
    assignment in get_project, causing NameError (500 on every page load).
    Verify the endpoint returns 200 with the correct branch_option value.
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db)
        project.branch_option = "default"
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    assert resp.json()["branch_option"] == "default"


def test_branch_option_legacy_all_migrated(client):
    """
    Legacy "all" branch_option must be migrated to "default".
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db)
        project.branch_option = "all"   # legacy value
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    assert resp.json()["branch_option"] == "default"


def test_branch_option_legacy_regex_migrated(client):
    """
    Legacy "regex" branch_option must be migrated to "pattern".
    """
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db)
        project.branch_option = "regex"   # legacy value
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    assert resp.json()["branch_option"] == "pattern"


# ---------------------------------------------------------------------------
# Test: RWX project workflow remains under_review when linked standard project
# has an open PR campaign targeting it
# ---------------------------------------------------------------------------

def test_rwx_workflow_stays_under_review_when_linked_standard_project_has_open_pr(client):
    """
    SCENARIO: A standard project created a PR campaign that includes a reusable
    workflow from an RWX project. The RWX project's own pr_state is "synced" (no
    PRs of its own), but the reusable workflow's status is "under_review".

    EXPECTED: GET /api/projects/{name} must NOT auto-correct the workflow to
    synced_with_github because the linked standard project still has an open PR.
    The workflow must remain under_review.
    """
    db = TestingSessionLocal()
    try:
        # Create account
        account = Account(
            github_user=TEST_GITHUB_USER,
            github_email="test@example.com",
            account_type="free",
        )
        db.add(account)
        db.flush()

        # Create RWX project (reusable workflow project)
        rwx_project = Project(
            project_name=TEST_PROJECT_NAME,
            project_code="RWX1",
            user_id=account.user_id,
            pr_state="synced",
            project_type="rwx",
        )
        db.add(rwx_project)
        db.flush()

        # Create standard project that links to the RWX project
        std_project = Project(
            project_name="caller-project",
            project_code="CP1",
            user_id=account.user_id,
            pr_state="open",
            project_type="standard",
        )
        db.add(std_project)
        db.flush()

        # Create a reusable workflow owned by the RWX project, status under_review
        rwx_wf = Workflow(
            workflow_name="shared-build.yml",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="under_review",
        )
        db.add(rwx_wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=rwx_wf.workflow_id))
        db.flush()

        # Link the workflow to the standard project
        link = LinkedReusableWorkflow(
            standard_project_id=std_project.project_id,
            rwx_project_id=rwx_project.project_id,
            workflow_id=rwx_wf.workflow_id,
        )
        db.add(link)
        db.flush()

        # The standard project has an open PR
        pr = ProjectPullRequest(
            project_id=std_project.project_id,
            repo_name="testuser/rwx-workflows",
            pr_number=99,
            pr_url="https://github.com/testuser/rwx-workflows/pull/99",
            branch_name="feature-update",
            target_branch="main",
            pr_state="open",
        )
        db.add(pr)
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # The reusable workflow must remain under_review
    assert len(data["rxworkflows"]) == 1
    assert data["rxworkflows"][0]["workflowStatus"] == "under_review", (
        f"Expected under_review but got {data['rxworkflows'][0]['workflowStatus']!r} — "
        "linked standard project still has an open PR"
    )
    # The RWX project's own pr_state should not have changed
    assert data["pr_state"] == "synced"


def test_rwx_workflow_transitions_to_synced_after_linked_pr_merged(client):
    """
    SCENARIO: The linked standard project's PR was merged. The RWX project's
    reusable workflow should now be auto-corrected to synced_with_github.
    """
    db = TestingSessionLocal()
    try:
        account = Account(
            github_user=TEST_GITHUB_USER,
            github_email="test@example.com",
            account_type="free",
        )
        db.add(account)
        db.flush()

        rwx_project = Project(
            project_name=TEST_PROJECT_NAME,
            project_code="RWX1",
            user_id=account.user_id,
            pr_state="synced",
            project_type="rwx",
        )
        db.add(rwx_project)
        db.flush()

        std_project = Project(
            project_name="caller-project",
            project_code="CP1",
            user_id=account.user_id,
            pr_state="synced",
            project_type="standard",
        )
        db.add(std_project)
        db.flush()

        rwx_wf = Workflow(
            workflow_name="shared-build.yml",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="under_review",
        )
        db.add(rwx_wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=rwx_wf.workflow_id))
        db.flush()

        link = LinkedReusableWorkflow(
            standard_project_id=std_project.project_id,
            rwx_project_id=rwx_project.project_id,
            workflow_id=rwx_wf.workflow_id,
        )
        db.add(link)
        db.flush()

        # The standard project's PR has been merged
        pr = ProjectPullRequest(
            project_id=std_project.project_id,
            repo_name="testuser/rwx-workflows",
            pr_number=99,
            pr_url="https://github.com/testuser/rwx-workflows/pull/99",
            branch_name="feature-update",
            target_branch="main",
            pr_state="merged",
        )
        db.add(pr)
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # After all linked PRs are merged, the workflow should be synced
    assert len(data["rxworkflows"]) == 1
    assert data["rxworkflows"][0]["workflowStatus"] == "synced_with_github", (
        f"Expected synced_with_github but got {data['rxworkflows'][0]['workflowStatus']!r}"
    )
