"""
Tests for linked reusable workflow PR-state propagation.

Covers:
- GET /api/projects/{name} returns workflowStatus on linked_reusable_workflows.
- create_pull_requests sets linked reusable workflow status to "under_review"
  when the standard project creates a PR that includes the linked workflow.
- The linked workflow status is preserved (not reset) for non-linked workflows.
"""
import sys
import os
import unittest.mock as mock

import pytest
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
    LinkedReusableWorkflow,
    ProjectPullRequest,
    Repo,
    ProjectRepo,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

# ---------------------------------------------------------------------------
# Test DB setup
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_linked_workflow_pr_status.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_GITHUB_USER = "testuser"
TEST_STD_PROJECT = "standard-project"
TEST_RWX_PROJECT = "rwx-project"


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    with mock.patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.pop(projects_get_db, None)
    app.dependency_overrides.pop(workflows_get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_account_and_projects(db):
    """Create an account, a standard project, and an RWX project."""
    account = Account(github_user=TEST_GITHUB_USER, github_email="t@t.com", account_type="pro")
    db.add(account)
    db.flush()

    std_project = Project(
        project_name=TEST_STD_PROJECT,
        project_code="STD1",
        user_id=account.user_id,
        project_type="standard",
        pr_state="draft",
    )
    rwx_project = Project(
        project_name=TEST_RWX_PROJECT,
        project_code="RWX1",
        user_id=account.user_id,
        project_type="rwx",
        pr_state="new",
    )
    db.add_all([std_project, rwx_project])
    db.flush()
    return account, std_project, rwx_project


def _add_linked_workflow(db, std_project, rwx_project, *, status="committed_locally"):
    """Create a reusable workflow and link it to the standard project."""
    wf = Workflow(
        workflow_name="deploy.yml",
        workflow_yaml="on: push",
        reusable_workflow=True,
        workflow_status=status,
    )
    db.add(wf)
    db.flush()

    # Associate with the RWX project
    pw = ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf.workflow_id)
    db.add(pw)

    # Link to the standard project
    link = LinkedReusableWorkflow(
        standard_project_id=std_project.project_id,
        rwx_project_id=rwx_project.project_id,
        workflow_id=wf.workflow_id,
    )
    db.add(link)
    db.flush()
    return wf


def _add_regular_workflow(db, project, *, status="committed_locally"):
    wf = Workflow(
        workflow_name="ci.yml",
        workflow_yaml="on: push",
        reusable_workflow=False,
        workflow_status=status,
    )
    db.add(wf)
    db.flush()
    pw = ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id)
    db.add(pw)
    db.flush()
    return wf


def _add_repo(db, project, repo_name="testuser/myrepo"):
    repo = Repo(repo_name=repo_name)
    db.add(repo)
    db.flush()
    pr = ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id)
    db.add(pr)
    db.flush()
    return repo


def _add_caller_project(db, account, name, code):
    """Create an additional standard (caller) project for the given account."""
    project = Project(
        project_name=name,
        project_code=code,
        user_id=account.user_id,
        project_type="standard",
        pr_state="draft",
    )
    db.add(project)
    db.flush()
    return project


def _link_existing_workflow(db, std_project, rwx_project, workflow):
    """Link an already-created reusable workflow into another caller project."""
    link = LinkedReusableWorkflow(
        standard_project_id=std_project.project_id,
        rwx_project_id=rwx_project.project_id,
        workflow_id=workflow.workflow_id,
    )
    db.add(link)
    db.flush()
    return link


# ---------------------------------------------------------------------------
# Tests: GET /api/projects/{name} — workflowStatus on linked_reusable_workflows
# ---------------------------------------------------------------------------

def test_linked_workflow_status_returned_in_project_response(client):
    """
    SCENARIO: A standard project loads with a linked reusable workflow that has
    workflow_status='under_review' in the DB.

    EXPECTED: The GET /api/projects/{name} response includes
    linked_reusable_workflows[0].workflowStatus == 'under_review'.
    """
    db = TestingSessionLocal()
    try:
        _, std_project, rwx_project = _make_account_and_projects(db)
        _add_linked_workflow(db, std_project, rwx_project, status="under_review")
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_STD_PROJECT}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert len(data["linked_reusable_workflows"]) == 1
    linked = data["linked_reusable_workflows"][0]
    assert linked["workflowStatus"] == "under_review", (
        f"Expected under_review but got {linked.get('workflowStatus')!r}"
    )


def test_linked_workflow_committed_locally_status_returned(client):
    """Baseline: committed_locally status is also returned correctly."""
    db = TestingSessionLocal()
    try:
        _, std_project, rwx_project = _make_account_and_projects(db)
        _add_linked_workflow(db, std_project, rwx_project, status="committed_locally")
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_STD_PROJECT}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["linked_reusable_workflows"][0]["workflowStatus"] == "committed_locally"


# ---------------------------------------------------------------------------
# Tests: create_pull_requests sets linked workflow to under_review
# ---------------------------------------------------------------------------

@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_create_pr_sets_linked_workflow_under_review(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    SCENARIO: A standard project creates a PR that includes a linked reusable
    workflow. The backend must set the linked workflow's workflow_status to
    'under_review' even though it lives in a different project's ProjectWorkflow.

    EXPECTED: After calling create_pull_requests, the linked Workflow record
    has workflow_status == 'under_review'.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"

    # Simulate successful PR creation
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/1",
            "pr_number": 1,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    linked_wf_id = None
    try:
        account, std_project, rwx_project = _make_account_and_projects(db)
        repo = _add_repo(db, std_project)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="committed_locally")
        linked_wf_id = linked_wf.workflow_id
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["prs_created"] >= 1

    # Verify linked workflow status was updated
    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        assert wf is not None
        assert wf.workflow_status == "under_review", (
            f"Expected under_review but got {wf.workflow_status!r}. "
            "Linked workflow status was not propagated from standard project PR."
        )
    finally:
        db.close()


@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_create_pr_does_not_set_non_selected_linked_workflow(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    SCENARIO: Two linked workflows exist; only one is selected for the PR.
    Only the selected workflow should become under_review.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/1",
            "pr_number": 1,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    selected_id = None
    unselected_id = None
    try:
        account, std_project, rwx_project = _make_account_and_projects(db)
        repo = _add_repo(db, std_project)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")

        # First linked workflow (will be selected)
        wf1 = Workflow(
            workflow_name="deploy.yml",
            workflow_yaml="on: push",
            reusable_workflow=True,
            workflow_status="committed_locally",
        )
        db.add(wf1)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf1.workflow_id))
        db.add(LinkedReusableWorkflow(
            standard_project_id=std_project.project_id,
            rwx_project_id=rwx_project.project_id,
            workflow_id=wf1.workflow_id,
        ))
        selected_id = wf1.workflow_id

        # Second linked workflow (NOT selected for PR)
        wf2 = Workflow(
            workflow_name="test.yml",
            workflow_yaml="on: push",
            reusable_workflow=True,
            workflow_status="committed_locally",
        )
        db.add(wf2)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf2.workflow_id))
        db.add(LinkedReusableWorkflow(
            standard_project_id=std_project.project_id,
            rwx_project_id=rwx_project.project_id,
            workflow_id=wf2.workflow_id,
        ))
        unselected_id = wf2.workflow_id
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],  # only deploy.yml selected
    })
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        wf1 = db.query(Workflow).filter_by(workflow_id=selected_id).first()
        wf2 = db.query(Workflow).filter_by(workflow_id=unselected_id).first()
        assert wf1.workflow_status == "under_review", (
            f"Selected linked workflow should be under_review, got {wf1.workflow_status!r}"
        )
        assert wf2.workflow_status == "committed_locally", (
            f"Unselected linked workflow should stay committed_locally, got {wf2.workflow_status!r}"
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests: projects.py auto-correction updates linked workflow status
# ---------------------------------------------------------------------------

def test_auto_correction_clears_linked_workflow_on_pr_merge(client):
    """
    SCENARIO: A standard project created a PR that included a linked workflow.
    The PR has since been merged (ProjectPullRequest.pr_state == 'merged').
    On GET /api/projects/{name}, the auto-correction logic should promote the
    linked workflow's status to 'synced_with_github'.
    """
    db = TestingSessionLocal()
    try:
        _, std_project, rwx_project = _make_account_and_projects(db)
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")
        pr = ProjectPullRequest(
            project_id=std_project.project_id,
            repo_name="testuser/am-reuseable-workflow",
            pr_number=10,
            pr_url="https://github.com/testuser/am-reuseable-workflow/pull/10",
            branch_name="AM-STD1-branch",
            target_branch="main",
            pr_state="merged",
        )
        db.add(pr)
        db.commit()
        linked_wf_id = linked_wf.workflow_id
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_STD_PROJECT}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        assert wf.workflow_status == "synced_with_github", (
            f"Expected synced_with_github but got {wf.workflow_status!r}. "
            "Auto-correction should propagate to linked workflows on PR merge."
        )
    finally:
        db.close()


@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_create_pr_matches_linked_workflow_by_display_name(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    REGRESSION (issue: PRs are not created for linked reusable workflow producer repo).

    SCENARIO: A standard project links a reusable workflow whose source RWX
    project uses prefix mode.  The frontend receives the *display-formatted*
    name (e.g. ``AM_RWX1_deploy.yml``) from ``GET /api/projects/{name}`` and
    submits that exact string in ``selected_reusable_workflows`` when the user
    clicks "Create Pull Requests".  The DB stores the raw stem (``deploy``).

    Before the fix, ``_build_reusable_workflow_results`` filtered by exact
    ``Workflow.workflow_name in selected_reusable_workflows`` membership and
    silently dropped every linked reusable workflow because the prefixed
    display name never matched the raw stem — so no PR was opened against
    the producer repo and the linked workflow stayed in ``committed_locally``.

    EXPECTED: The display-formatted selection resolves to the canonical
    workflow row, the producer repo's PR-creation path is invoked, and the
    linked workflow transitions to ``under_review``.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_reg.return_value = {}
    mock_process_rx.return_value = {
        "testuser/rwx-producer-repo on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/rwx-producer-repo/pull/7",
            "pr_number": 7,
            "branch_name": "actions-manager/rwx1/rwx-producer-repo/abc12345-main",
            "workflows_committed": ["deploy"],
        }
    }

    db = TestingSessionLocal()
    linked_wf_id = None
    try:
        account, std_project, rwx_project = _make_account_and_projects(db)
        # Realistic prefix-mode RWX project — display names will be prefixed.
        rwx_project.use_prefix = True
        rwx_project.project_code = "RWX1"
        # Standard project must have at least one repo to satisfy
        # _get_filtered_repo_names; producer-repo PR creation itself is mocked.
        _add_repo(db, std_project, repo_name="testuser/std-repo")
        _add_repo(db, rwx_project, repo_name="testuser/rwx-producer-repo")

        # Canonical reusable workflow row stores the *raw stem*, not the
        # display-formatted name returned by _load_linked_reusable_workflows.
        wf = Workflow(
            workflow_name="deploy",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="committed_locally",
        )
        db.add(wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf.workflow_id))
        db.add(LinkedReusableWorkflow(
            standard_project_id=std_project.project_id,
            rwx_project_id=rwx_project.project_id,
            workflow_id=wf.workflow_id,
        ))
        linked_wf_id = wf.workflow_id
        db.commit()
    finally:
        db.close()

    # Frontend submits the *display-formatted* name as it received from GET.
    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/std-repo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["AM_RWX1_deploy.yml"],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prs_created"] >= 1, (
        "No PR was created for the linked reusable workflow producer repo."
    )
    # Producer-repo PR creation must have been invoked with the canonical
    # raw-stem workflow name.
    assert mock_process_rx.called, "Reusable PR creation pipeline was not invoked"
    call_kwargs = mock_process_rx.call_args.kwargs
    submitted_names = [w["name"] for w in call_kwargs["rxworkflows"]]
    assert submitted_names == ["deploy"], (
        f"Expected canonical raw-stem name 'deploy' to flow into the PR "
        f"pipeline, got {submitted_names!r}"
    )

    # Linked workflow status must transition to under_review.
    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        assert wf.workflow_status == "under_review", (
            f"Linked reusable workflow should be under_review after producer-repo "
            f"PR creation, got {wf.workflow_status!r}"
        )
    finally:
        db.close()


def test_auto_correction_clears_linked_workflow_on_pr_close(client):
    """
    SCENARIO: A standard project PR was closed without merge.
    On GET /api/projects/{name}, the linked workflow should revert to 'committed_locally'.
    """
    db = TestingSessionLocal()
    try:
        _, std_project, rwx_project = _make_account_and_projects(db)
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")
        pr = ProjectPullRequest(
            project_id=std_project.project_id,
            repo_name="testuser/am-reuseable-workflow",
            pr_number=11,
            pr_url="https://github.com/testuser/am-reuseable-workflow/pull/11",
            branch_name="AM-STD1-branch",
            target_branch="main",
            pr_state="closed",
        )
        db.add(pr)
        db.commit()
        linked_wf_id = linked_wf.workflow_id
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_STD_PROJECT}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        assert wf.workflow_status == "committed_locally", (
            f"Expected committed_locally but got {wf.workflow_status!r}. "
            "Auto-correction should revert linked workflow on closed PR."
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests: Cross-project PR visibility
# ---------------------------------------------------------------------------

@mock.patch("workflows.user_tokens", new_callable=dict)
def test_rwx_project_sees_pr_created_by_standard_project(mock_tokens, client):
    """
    SCENARIO: A standard project creates a PR for a linked reusable workflow.
    The PR is stored with project_id = standard_project.project_id.

    EXPECTED: When the RWX project queries its PR status via
    GET /api/project-pr-status?project_name=rwx-project, the PR created by
    the standard project appears in the response. This ensures:
    - RWX project shows the open PR banner
    - RWX project shows the workflow as locked
    - PR appears in the RWX project's Open PRs list
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"

    db = TestingSessionLocal()
    try:
        _, std_project, rwx_project = _make_account_and_projects(db)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")

        # Standard project creates a PR for the linked workflow
        pr = ProjectPullRequest(
            project_id=std_project.project_id,  # PR belongs to standard project
            repo_name="testuser/rwx-repo",
            pr_number=42,
            pr_url="https://github.com/testuser/rwx-repo/pull/42",
            branch_name="actions-manager/std1/rwx-repo/abc12345-main",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy.yml",
        )
        db.add(pr)
        db.commit()
    finally:
        db.close()

    # Query the RWX project's PR status
    resp = client.get("/api/project-pr-status", params={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_RWX_PROJECT,
        "refresh_from_github": False,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # The PR created by the standard project should appear in the RWX project's PR list
    assert data["open_prs"] == 1, (
        f"Expected 1 open PR in RWX project, got {data['open_prs']}. "
        "PRs created by linked standard projects should be visible in the RWX project."
    )
    assert len(data["pull_requests"]) == 1, (
        f"Expected 1 PR in pull_requests list, got {len(data['pull_requests'])}"
    )

    pr_response = data["pull_requests"][0]
    assert pr_response["pr_number"] == 42
    assert pr_response["repo_name"] == "testuser/rwx-repo"
    assert pr_response["pr_state"] == "open"


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_standard_project_still_sees_its_own_pr(mock_tokens, client):
    """
    SCENARIO: A standard project creates a PR for a linked reusable workflow.

    EXPECTED: The standard project can still see its own PR when querying
    GET /api/project-pr-status?project_name=standard-project.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"

    db = TestingSessionLocal()
    try:
        _, std_project, rwx_project = _make_account_and_projects(db)
        _add_repo(db, std_project, repo_name="testuser/std-repo")
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")

        # Standard project creates a PR
        pr = ProjectPullRequest(
            project_id=std_project.project_id,
            repo_name="testuser/rwx-repo",
            pr_number=99,
            pr_url="https://github.com/testuser/rwx-repo/pull/99",
            branch_name="actions-manager/std1/rwx-repo/xyz67890-main",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy.yml",
        )
        db.add(pr)
        db.commit()
    finally:
        db.close()

    # Standard project should see its own PR
    resp = client.get("/api/project-pr-status", params={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "refresh_from_github": False,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["open_prs"] == 1
    assert len(data["pull_requests"]) == 1
    assert data["pull_requests"][0]["pr_number"] == 99


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_pr_source_project_name_label(mock_tokens, client):
    """
    SCENARIO: A standard project creates a PR for a linked reusable workflow.
    The RWX project queries its PR status.

    EXPECTED: The PR response includes source_project_name set to the
    standard project's name, so the UI can label it as coming from that project.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"

    db = TestingSessionLocal()
    try:
        _, std_project, rwx_project = _make_account_and_projects(db)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")

        # Standard project creates a PR for the linked workflow
        pr = ProjectPullRequest(
            project_id=std_project.project_id,  # PR belongs to standard project
            repo_name="testuser/rwx-repo",
            pr_number=42,
            pr_url="https://github.com/testuser/rwx-repo/pull/42",
            branch_name="actions-manager/std1/rwx-repo/abc12345-main",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy.yml",
        )
        db.add(pr)
        db.commit()
    finally:
        db.close()

    # Query the RWX project's PR status
    resp = client.get("/api/project-pr-status", params={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_RWX_PROJECT,
        "refresh_from_github": False,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # The PR should appear with source_project_name set
    assert data["open_prs"] == 1
    assert len(data["pull_requests"]) == 1
    pr_response = data["pull_requests"][0]
    assert pr_response["pr_number"] == 42
    assert pr_response["source_project_name"] == TEST_STD_PROJECT, (
        f"Expected source_project_name to be '{TEST_STD_PROJECT}', "
        f"got {pr_response.get('source_project_name')!r}"
    )


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_standalone_rwx_project_prs_work_normally(mock_tokens, client):
    """
    REGRESSION TEST: Standalone RWX projects (not linked from any standard project)
    must continue to work normally after cross-project PR visibility changes.

    SCENARIO: An RWX project creates a PR for its own reusable workflow.
    No standard projects link to this RWX project.

    EXPECTED: The RWX project sees its own PR without any source_project_name label.
    Native RWX project behavior is not broken by cross-project PR visibility logic.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"

    db = TestingSessionLocal()
    try:
        account, _, _ = _make_account_and_projects(db)

        # Create a standalone RWX project (not linked from any standard project)
        standalone_rwx = Project(
            project_name="standalone-rwx",
            project_code="SRWX",
            user_id=account.user_id,
            project_type="rwx",
            pr_state="new",
        )
        db.add(standalone_rwx)
        db.flush()

        _add_repo(db, standalone_rwx, repo_name="testuser/standalone-rwx-repo")

        # Create a reusable workflow in the standalone RWX project
        wf = Workflow(
            workflow_name="deploy",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="under_review",
        )
        db.add(wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=standalone_rwx.project_id, workflow_id=wf.workflow_id))

        # Standalone RWX project creates its own PR
        pr = ProjectPullRequest(
            project_id=standalone_rwx.project_id,  # PR belongs to the RWX project itself
            repo_name="testuser/standalone-rwx-repo",
            pr_number=123,
            pr_url="https://github.com/testuser/standalone-rwx-repo/pull/123",
            branch_name="actions-manager/srwx/standalone-rwx-repo/abc12345-main",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy",
        )
        db.add(pr)
        db.commit()
    finally:
        db.close()

    # Query the standalone RWX project's PR status
    resp = client.get("/api/project-pr-status", params={
        "github_user": TEST_GITHUB_USER,
        "project_name": "standalone-rwx",
        "refresh_from_github": False,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # The PR should appear normally without any source_project_name label
    assert data["open_prs"] == 1, (
        f"Standalone RWX project should see its own PR, got {data['open_prs']} open PRs"
    )
    assert len(data["pull_requests"]) == 1

    pr_response = data["pull_requests"][0]
    assert pr_response["pr_number"] == 123
    assert pr_response["repo_name"] == "testuser/standalone-rwx-repo"
    assert pr_response["pr_state"] == "open"

    # Native RWX project PRs should NOT have a source_project_name label
    assert pr_response["source_project_name"] is None, (
        f"Native RWX project PRs should not have source_project_name label, "
        f"got {pr_response.get('source_project_name')!r}"
    )


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_standalone_rwx_project_workflow_locking_works(mock_tokens, client):
    """
    REGRESSION TEST: Workflow locking must work correctly for standalone RWX projects.

    SCENARIO: A standalone RWX project has an open PR for a reusable workflow.
    The _has_open_pr_for_workflow function should correctly identify the open PR
    and mark the workflow as locked.

    EXPECTED: Workflow locking works for standalone RWX projects just as it did
    before cross-project PR visibility changes.
    """
    from workflows import _has_open_pr_for_workflow

    mock_tokens[TEST_GITHUB_USER] = "fake_token"

    db = TestingSessionLocal()
    try:
        account, _, _ = _make_account_and_projects(db)

        # Create a standalone RWX project
        standalone_rwx = Project(
            project_name="standalone-rwx",
            project_code="SRWX",
            user_id=account.user_id,
            project_type="rwx",
            pr_state="open",
        )
        db.add(standalone_rwx)
        db.flush()

        _add_repo(db, standalone_rwx, repo_name="testuser/rwx-repo")

        # Create a reusable workflow
        wf = Workflow(
            workflow_name="deploy.yml",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="under_review",
        )
        db.add(wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=standalone_rwx.project_id, workflow_id=wf.workflow_id))

        # Create an open PR for the workflow
        pr = ProjectPullRequest(
            project_id=standalone_rwx.project_id,
            repo_name="testuser/rwx-repo",
            pr_number=100,
            pr_url="https://github.com/testuser/rwx-repo/pull/100",
            branch_name="actions-manager/srwx/rwx-repo/abc12345-main",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy.yml",
        )
        db.add(pr)
        db.commit()

        # Test that _has_open_pr_for_workflow correctly identifies the open PR
        has_open_pr = _has_open_pr_for_workflow(
            db,
            standalone_rwx.project_id,
            "deploy.yml",
            "testuser/rwx-repo"
        )

        assert has_open_pr is True, (
            "Standalone RWX project should correctly identify open PRs for workflow locking"
        )

        # Test that workflow without open PR returns False
        has_open_pr_nonexistent = _has_open_pr_for_workflow(
            db,
            standalone_rwx.project_id,
            "nonexistent.yml",
            "testuser/rwx-repo"
        )

        assert has_open_pr_nonexistent is False, (
            "Should return False for workflows without open PRs"
        )

    finally:
        db.close()


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_rwx_project_respects_use_prefix_false(mock_tokens, client):
    """
    REGRESSION TEST: RWX projects with use_prefix=false should format workflow names
    without the AM_{PROJECT_CODE}_ prefix.

    SCENARIO: Test that format_workflow_name respects use_prefix=False.

    EXPECTED: Workflow names should not have the prefix when use_prefix=False.

    This fixes the bug where reusable workflows were always prefixed regardless
    of the use_prefix setting, causing PR/lock/banner logic to fail matching.
    """
    from workflows import format_workflow_name

    # Test with use_prefix=True (default behavior)
    formatted_with_prefix = format_workflow_name("deploy", "NPR", use_prefix=True)
    assert formatted_with_prefix == "AM_NPR_deploy.yml", f"Expected 'AM_NPR_deploy.yml', got '{formatted_with_prefix}'"

    # Test with use_prefix=False (should not add prefix)
    formatted_without_prefix = format_workflow_name("deploy", "NPR", use_prefix=False)
    assert formatted_without_prefix == "deploy.yml", f"Expected 'deploy.yml', got '{formatted_without_prefix}'"

    # Test that workflow name already with .yml extension doesn't get double extension
    formatted_no_double_ext = format_workflow_name("deploy.yml", "NPR", use_prefix=False)
    assert formatted_no_double_ext == "deploy.yml", f"Expected 'deploy.yml', got '{formatted_no_double_ext}'"


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_rwx_workflow_stays_under_review_after_reload(mock_tokens, client):
    """
    REGRESSION TEST: RWX workflow with open PR must stay "under_review" after project reload.

    SCENARIO: A standard project creates a PR for a linked reusable workflow.
    The RWX project loads and the workflow shows "under_review".
    Then the workflow is re-saved (simulating a reload or refresh operation).

    EXPECTED: The workflow status must remain "under_review", not downgrade to "committed_locally".

    This fixes the bug where create_or_update_workflow unconditionally set status to
    "committed_locally" even when an open PR existed, causing workflows to flicker
    between "under_review" and "committed_locally" on page refresh.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"

    db = TestingSessionLocal()
    try:
        account, std_project, rwx_project = _make_account_and_projects(db)

        # Add repos to both projects
        _add_repo(db, std_project, repo_name="testuser/std-repo")
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")

        # Create a reusable workflow in the RWX project
        wf = Workflow(
            workflow_name="deploy",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="under_review",  # Already under review due to open PR
        )
        db.add(wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf.workflow_id))

        # Link the workflow to the standard project
        db.add(LinkedReusableWorkflow(
            standard_project_id=std_project.project_id,
            rwx_project_id=rwx_project.project_id,
            workflow_id=wf.workflow_id,
        ))

        # Create an open PR from the standard project for this workflow
        pr = ProjectPullRequest(
            project_id=std_project.project_id,  # PR created from standard project
            repo_name="testuser/rwx-repo",
            pr_number=100,
            pr_url="https://github.com/testuser/rwx-repo/pull/100",
            branch_name="actions-manager/std/rwx-repo/abc12345-main",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy",  # This workflow is in the PR
        )
        db.add(pr)
        db.commit()

        # Verify initial state
        db.refresh(wf)
        assert wf.workflow_status == "under_review", "Initial status should be under_review"

        # Simulate a workflow save/reload operation (what happens during project refresh)
        from workflows import create_or_update_workflow
        from pydantic import BaseModel

        class MockWorkflow(BaseModel):
            name: str
            content: str

        mock_wf = MockWorkflow(name="deploy", content="on: workflow_call\njobs: {}")
        create_or_update_workflow(db, mock_wf, rwx_project.project_id, is_reusable=True, last_modified_by=TEST_GITHUB_USER)

        # Verify the status did NOT downgrade to committed_locally
        db.refresh(wf)
        assert wf.workflow_status == "under_review", (
            f"Workflow with open PR must stay under_review after save/reload, "
            f"got {wf.workflow_status!r}"
        )

        print("✅ Test passed: RWX workflow stayed under_review after reload")

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests: global under-review lock across all linked projects + source project
# ---------------------------------------------------------------------------

@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_reusable_workflow_locked_across_all_linked_projects_and_source(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    SCENARIO: One reusable workflow is linked into three caller projects.
    A PR campaign is created from the first caller project.

    EXPECTED: Because the reusable workflow is a single canonical record shared
    by ``workflow_id``, it shows ``under_review`` in every linked caller project
    AND in the source RWX project.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/1",
            "pr_number": 1,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    linked_wf_id = None
    caller2_name = "caller-p2"
    caller3_name = "caller-p3"
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="committed_locally")
        linked_wf_id = linked_wf.workflow_id

        # Two more caller projects linking the same canonical workflow.
        caller2 = _add_caller_project(db, account, caller2_name, "STD2")
        caller3 = _add_caller_project(db, account, caller3_name, "STD3")
        _add_repo(db, caller2, repo_name="testuser/repo2")
        _add_repo(db, caller3, repo_name="testuser/repo3")
        _link_existing_workflow(db, caller2, rwx_project, linked_wf)
        _link_existing_workflow(db, caller3, rwx_project, linked_wf)
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 200, resp.text

    # The canonical Workflow record is under_review.
    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        assert wf.workflow_status == "under_review"
    finally:
        db.close()

    # Every linked caller project surfaces the under_review status.
    for name in (TEST_STD_PROJECT, caller2_name, caller3_name):
        resp = client.get(f"/api/projects/{name}", params={"github_user": TEST_GITHUB_USER})
        assert resp.status_code == 200, resp.text
        linked = resp.json()["linked_reusable_workflows"]
        assert linked, f"Project {name} should expose the linked workflow"
        assert linked[0]["workflowStatus"] == "under_review", (
            f"Project {name} should show linked workflow as under_review, "
            f"got {linked[0]['workflowStatus']!r}"
        )

    # The source RWX project also shows its workflow as under_review.
    resp = client.get(f"/api/projects/{TEST_RWX_PROJECT}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    rwx_data = resp.json()
    rwx_workflows = rwx_data.get("rxworkflows") or rwx_data.get("reusable_workflows") or []
    assert any(w.get("workflowStatus") == "under_review" for w in rwx_workflows), (
        f"Source RWX project should show the workflow as under_review, got {rwx_workflows!r}"
    )


@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_second_pr_campaign_blocked_when_reusable_workflow_under_review(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    SCENARIO: caller-p1 opens a PR campaign for a linked reusable workflow.
    caller-p2 then attempts to open a second campaign for the same workflow.

    EXPECTED: The second campaign is blocked with HTTP 409 and a clear message
    that names the project holding the active review.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/1",
            "pr_number": 7,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    caller2_name = "caller-p2"
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="committed_locally")

        caller2 = _add_caller_project(db, account, caller2_name, "STD2")
        _add_repo(db, caller2, repo_name="testuser/repo2")
        _link_existing_workflow(db, caller2, rwx_project, linked_wf)
        db.commit()
    finally:
        db.close()

    # First campaign from caller-p1 succeeds.
    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 200, resp.text

    # Second campaign from caller-p2 must be blocked.
    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": caller2_name,
        "selected_repos": ["testuser/repo2"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "under review" in detail.lower()
    assert TEST_STD_PROJECT in detail
    assert "#7" in detail


@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_same_project_can_re_run_its_own_campaign(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    SCENARIO: caller-p1 opens a PR campaign, then re-runs create-pull-requests
    for the same workflow (e.g. to update its own existing PR).

    EXPECTED: The owning project is never blocked by its own open PR.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_updated",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/1",
            "pr_number": 1,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        _add_linked_workflow(db, caller1, rwx_project, status="committed_locally")
        db.commit()
    finally:
        db.close()

    payload = {
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    }
    assert client.post("/api/create-pull-requests", json=payload).status_code == 200
    # Re-running from the same project must not be blocked.
    assert client.post("/api/create-pull-requests", json=payload).status_code == 200


@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_lock_clears_after_pr_close_allows_new_campaign(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    SCENARIO: caller-p1 opens a campaign, then the PR is closed (not merged).

    EXPECTED: The global lock clears and caller-p2 may open a new campaign.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/1",
            "pr_number": 11,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    caller2_name = "caller-p2"
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="committed_locally")
        caller2 = _add_caller_project(db, account, caller2_name, "STD2")
        _add_repo(db, caller2, repo_name="testuser/repo2")
        _link_existing_workflow(db, caller2, rwx_project, linked_wf)
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 200, resp.text

    # Simulate the PR being closed without merge.
    db = TestingSessionLocal()
    try:
        pr = db.query(ProjectPullRequest).filter_by(pr_number=11).first()
        assert pr is not None
        pr.pr_state = "closed"
        db.commit()
    finally:
        db.close()

    # caller-p2 may now open a campaign because the lock is cleared.
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/12",
            "pr_number": 12,
            "workflows_committed": ["deploy.yml"],
        }
    }
    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": caller2_name,
        "selected_repos": ["testuser/repo2"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 200, resp.text

@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_sibling_caller_refresh_does_not_unlock_workflow_with_open_campaign(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    REGRESSION (issue: linked reusable workflow not locked everywhere while an
    open PR campaign exists).

    SCENARIO: caller-p1 opens a PR campaign for a shared reusable workflow, so
    the canonical workflow becomes ``under_review``.  A sibling caller project
    (caller-p2) that links the same workflow has its *own* terminal (closed) PR
    from an earlier, unrelated campaign.  A drift/sync refresh (GET) of caller-p2
    used to inspect only caller-p2's and the RWX project's PRs — missing the
    open campaign held by caller-p1 — and wrongly unlocked the workflow.

    EXPECTED: The workflow stays ``under_review`` everywhere while caller-p1's
    PR remains open.  The under_review lock is a workflow-level state.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/21",
            "pr_number": 21,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    caller2_name = "caller-p2"
    linked_wf_id = None
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="committed_locally")
        linked_wf_id = linked_wf.workflow_id
        caller2 = _add_caller_project(db, account, caller2_name, "STD2")
        _add_repo(db, caller2, repo_name="testuser/repo2")
        _link_existing_workflow(db, caller2, rwx_project, linked_wf)
        # caller-p2 has its own *closed* PR from a prior unrelated campaign.
        db.add(ProjectPullRequest(
            project_id=caller2.project_id,
            repo_name="testuser/repo2",
            pr_number=99,
            pr_url="https://github.com/testuser/repo2/pull/99",
            branch_name="AM-STD2-old",
            target_branch="main",
            pr_state="closed",
        ))
        db.commit()
    finally:
        db.close()

    # caller-p1 opens the campaign → canonical workflow becomes under_review.
    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        assert wf.workflow_status == "under_review"
    finally:
        db.close()

    # A drift/sync refresh of the sibling caller must NOT unlock the workflow
    # while caller-p1's PR is still open.
    resp = client.get(f"/api/projects/{caller2_name}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    linked = resp.json()["linked_reusable_workflows"]
    assert linked and linked[0]["workflowStatus"] == "under_review", (
        f"Sibling caller refresh must keep the workflow under_review while an "
        f"open campaign exists, got {linked[0]['workflowStatus'] if linked else None!r}"
    )

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        assert wf.workflow_status == "under_review", (
            f"Canonical workflow must remain under_review, got {wf.workflow_status!r}"
        )
    finally:
        db.close()


@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_newly_linked_project_inherits_under_review_state(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    REGRESSION (issue: newly linked projects should inherit the current
    under_review state immediately).

    SCENARIO: A reusable workflow already has an open PR campaign (opened by
    caller-p1).  The workflow is then linked into a *new* caller project
    (caller-p3) after the campaign exists.

    EXPECTED: caller-p3 immediately shows the workflow as ``under_review`` and a
    drift/sync refresh does not unlock it while the PR remains open.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/31",
            "pr_number": 31,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    caller3_name = "caller-p3"
    linked_wf_id = None
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="committed_locally")
        linked_wf_id = linked_wf.workflow_id
        db.commit()
    finally:
        db.close()

    # caller-p1 opens the campaign.
    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 200, resp.text

    # Now link the workflow into a brand-new caller project, after the campaign.
    db = TestingSessionLocal()
    try:
        account = db.query(Account).filter_by(github_user=TEST_GITHUB_USER).first()
        rwx_project = db.query(Project).filter_by(project_name=TEST_RWX_PROJECT).first()
        linked_wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        caller3 = _add_caller_project(db, account, caller3_name, "STD3")
        _add_repo(db, caller3, repo_name="testuser/repo3")
        _link_existing_workflow(db, caller3, rwx_project, linked_wf)
        db.commit()
    finally:
        db.close()

    # The newly linked project must inherit under_review immediately and a
    # refresh must not unlock it while the PR is open.
    resp = client.get(f"/api/projects/{caller3_name}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    linked = resp.json()["linked_reusable_workflows"]
    assert linked and linked[0]["workflowStatus"] == "under_review", (
        f"Newly linked project should inherit under_review immediately, "
        f"got {linked[0]['workflowStatus'] if linked else None!r}"
    )

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf_id).first()
        assert wf.workflow_status == "under_review"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests: repo-scoped PR matching — false-positive prevention
# ---------------------------------------------------------------------------

def test_blocking_check_ignores_regular_workflow_pr_from_sibling_caller(client):
    """
    REGRESSION: _find_blocking_reusable_workflow_pr must NOT return a PR owned by
    a sibling caller project for a *regular* workflow that happens to share the
    same filename as the reusable workflow.

    SETUP:
    - RWX project owns reusable workflow "deploy.yml", repo "testuser/rwx-repo".
    - caller-p1 links the reusable workflow.
    - caller-p2 also links the reusable workflow but has an open PR for a
      *regular* workflow named "deploy.yml" stored against "testuser/caller2-repo"
      (not the RWX repo).

    EXPECTED: When caller-p1 tries to open a campaign for "deploy.yml", the
    blocking check finds no matching PR (caller-p2's PR is for the wrong repo)
    and does not raise HTTP 409.
    """
    from workflows import _find_blocking_reusable_workflow_pr

    db = TestingSessionLocal()
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="committed_locally")

        caller2 = _add_caller_project(db, account, "caller-p2", "STD2")
        _add_repo(db, caller2, repo_name="testuser/caller2-repo")
        _link_existing_workflow(db, caller2, rwx_project, linked_wf)

        # caller-p2 has an open PR for a *regular* workflow named "deploy.yml"
        # stored against its own caller repo — not the RWX repo.
        db.add(ProjectPullRequest(
            project_id=caller2.project_id,
            repo_name="testuser/caller2-repo",
            pr_number=55,
            pr_url="https://github.com/testuser/caller2-repo/pull/55",
            branch_name="AM-STD2-deploy-branch",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy.yml",
        ))
        db.commit()

        blocking = _find_blocking_reusable_workflow_pr(db, linked_wf, caller1.project_id)
        assert blocking is None, (
            "A caller project's open PR for a same-named regular workflow must not "
            "block a reusable workflow campaign. Got a false-positive block: "
            f"{blocking}"
        )
    finally:
        db.close()


def test_locked_by_open_campaign_ignores_regular_workflow_pr_from_sibling(client):
    """
    REGRESSION: _linked_workflows_locked_by_open_campaign must NOT keep a
    reusable workflow locked because a sibling caller project has an open PR for
    a *regular* workflow that shares the same filename.

    SETUP:
    - RWX project owns reusable workflow "deploy.yml", repo "testuser/rwx-repo".
    - caller-p1 links it; the workflow is "under_review".
    - caller-p2 also links it but has an open PR for a *regular* "deploy.yml"
      against "testuser/caller2-repo" (not the RWX repo).
    - No PR exists against the RWX repo.

    EXPECTED: _linked_workflows_locked_by_open_campaign returns an empty set —
    the workflow is NOT kept locked by the unrelated PR.
    """
    from projects import _linked_workflows_locked_by_open_campaign

    db = TestingSessionLocal()
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="under_review")

        caller2 = _add_caller_project(db, account, "caller-p2", "STD2")
        _add_repo(db, caller2, repo_name="testuser/caller2-repo")
        _link_existing_workflow(db, caller2, rwx_project, linked_wf)

        # caller-p2 has an open PR for a regular "deploy.yml" in its own caller repo.
        db.add(ProjectPullRequest(
            project_id=caller2.project_id,
            repo_name="testuser/caller2-repo",
            pr_number=77,
            pr_url="https://github.com/testuser/caller2-repo/pull/77",
            branch_name="AM-STD2-deploy-branch",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy.yml",
        ))
        db.commit()

        still_locked = _linked_workflows_locked_by_open_campaign(db, [linked_wf.workflow_id])
        assert linked_wf.workflow_id not in still_locked, (
            "A sibling caller's open PR for a same-named regular workflow must not "
            "keep a reusable workflow locked. Got an unexpected lock."
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests: global lock survives every status-downgrade transition path
# ---------------------------------------------------------------------------

def test_status_downgrade_helper_respects_global_lock(client):
    """
    REGRESSION (issue: reusable workflow with an open PR campaign must stay
    locked everywhere).

    ``_update_project_workflows_status(..., only_if_status="under_review")`` is
    the shared downgrade path used by the merge endpoint, the close endpoint,
    the PR webhook, and the page-load PR refresh.  It previously downgraded
    every under_review workflow in the acting project without checking whether
    a *different* project still holds an open PR campaign for a shared
    reusable workflow.

    EXPECTED: while caller-p1's campaign is open the canonical workflow stays
    ``under_review`` even when the RWX project is downgraded; once the PR is
    merged the same call downgrades it normally (no over-locking).
    """
    from workflows import _update_project_workflows_status

    db = TestingSessionLocal()
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="under_review")
        # caller-p1 holds the open campaign; workflow_names carries the
        # display-formatted name to exercise stem normalization.
        pr = ProjectPullRequest(
            project_id=caller1.project_id,
            repo_name="testuser/rwx-repo",
            pr_number=11,
            pr_url="https://github.com/testuser/rwx-repo/pull/11",
            branch_name="AM-STD1-campaign",
            target_branch="main",
            pr_state="open",
            workflow_names="AM_RWX1_deploy.yml",
        )
        db.add(pr)
        db.commit()

        # Downgrade attempt against the RWX project (e.g. its own PR resolved).
        _update_project_workflows_status(
            db, rwx_project.project_id, "synced_with_github",
            only_if_status="under_review",
        )
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).one()
        assert wf.workflow_status == "under_review", (
            f"Open campaign in caller-p1 must keep the workflow locked, "
            f"got {wf.workflow_status!r}"
        )

        # Negative control: once the campaign is merged the lock clears.
        pr = db.query(ProjectPullRequest).filter_by(pr_number=11).one()
        pr.pr_state = "merged"
        db.commit()
        _update_project_workflows_status(
            db, rwx_project.project_id, "synced_with_github",
            only_if_status="under_review",
        )
        wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).one()
        assert wf.workflow_status == "synced_with_github", (
            f"Lock must clear after the campaign is merged, got {wf.workflow_status!r}"
        )
    finally:
        db.close()


def test_rwx_page_load_resolution_keeps_lock_and_pr_state(client):
    """
    REGRESSION (issue: async drift/sync refresh must not unlock the workflow
    while a PR is open).

    ``_apply_all_prs_resolved_transitions`` runs on PR page loads whenever a
    project's *own* PRs are all merged/closed.  For an RWX project whose
    reusable workflow is still under a caller's open campaign it previously
    flipped the workflow to synced_with_github and the project to pr_state
    'synced'.

    EXPECTED: while caller-p1's campaign is open, the RWX page-load resolution
    keeps the workflow ``under_review`` and leaves the RWX pr_state untouched;
    after the campaign is merged the same call completes the transition.
    """
    from workflows import _apply_all_prs_resolved_transitions

    db = TestingSessionLocal()
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        rwx_project.pr_state = "open"
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="under_review")
        # caller-p1 still has the open campaign for the shared workflow.
        db.add(ProjectPullRequest(
            project_id=caller1.project_id,
            repo_name="testuser/rwx-repo",
            pr_number=21,
            pr_url="https://github.com/testuser/rwx-repo/pull/21",
            branch_name="AM-STD1-campaign",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy.yml",
        ))
        # The RWX project's own earlier PR is fully merged → its page load
        # triggers the all-resolved transition.
        db.add(ProjectPullRequest(
            project_id=rwx_project.project_id,
            repo_name="testuser/rwx-repo",
            pr_number=22,
            pr_url="https://github.com/testuser/rwx-repo/pull/22",
            branch_name="AM-RWX1-own",
            target_branch="main",
            pr_state="merged",
            workflow_names="deploy.yml",
        ))
        db.commit()

        rwx = db.query(Project).filter_by(project_id=rwx_project.project_id).one()
        _apply_all_prs_resolved_transitions(db, rwx, total_count=1, merged_count=1)

        wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).one()
        rwx = db.query(Project).filter_by(project_id=rwx_project.project_id).one()
        assert wf.workflow_status == "under_review", (
            f"Page-load resolution must not unlock a workflow with an open "
            f"campaign elsewhere, got {wf.workflow_status!r}"
        )
        assert rwx.pr_state == "open", (
            f"RWX pr_state must stay untouched while its workflow is locked, "
            f"got {rwx.pr_state!r}"
        )

        # Negative control: merge caller-p1's campaign → transition completes.
        pr = db.query(ProjectPullRequest).filter_by(pr_number=21).one()
        pr.pr_state = "merged"
        db.commit()
        rwx = db.query(Project).filter_by(project_id=rwx_project.project_id).one()
        _apply_all_prs_resolved_transitions(db, rwx, total_count=1, merged_count=1)

        wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).one()
        rwx = db.query(Project).filter_by(project_id=rwx_project.project_id).one()
        assert wf.workflow_status == "synced_with_github"
        assert rwx.pr_state == "synced"
    finally:
        db.close()


def test_sibling_caller_merge_sync_keeps_lock_until_campaign_resolves(client):
    """
    REGRESSION (issue: merging one caller's PR must not unlock a workflow that
    another caller's open campaign still references).

    ``_sync_linked_reusable_workflows_after_merge`` runs when a caller project
    merges its last PR.  It previously promoted every linked under_review
    workflow to synced_with_github — including workflows whose open campaign
    belongs to a *different* caller.

    EXPECTED: caller-p2's merge sync keeps the workflow ``under_review`` and
    the RWX pr_state untouched while caller-p1's campaign is open; once that
    campaign is closed the same sync completes the transition.
    """
    from workflows import _sync_linked_reusable_workflows_after_merge

    db = TestingSessionLocal()
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        rwx_project.pr_state = "open"
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="under_review")
        caller2 = _add_caller_project(db, account, "caller-p2", "STD2")
        _add_repo(db, caller2, repo_name="testuser/repo2")
        _link_existing_workflow(db, caller2, rwx_project, linked_wf)
        # caller-p1 holds the open campaign for the shared workflow.
        db.add(ProjectPullRequest(
            project_id=caller1.project_id,
            repo_name="testuser/rwx-repo",
            pr_number=31,
            pr_url="https://github.com/testuser/rwx-repo/pull/31",
            branch_name="AM-STD1-campaign",
            target_branch="main",
            pr_state="open",
            workflow_names="deploy.yml",
        ))
        db.commit()

        # caller-p2 merges its own last PR → merge sync runs for caller-p2.
        _sync_linked_reusable_workflows_after_merge(db, caller2.project_id)

        wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).one()
        rwx = db.query(Project).filter_by(project_id=rwx_project.project_id).one()
        assert wf.workflow_status == "under_review", (
            f"Sibling caller merge sync must not unlock a workflow with an "
            f"open campaign elsewhere, got {wf.workflow_status!r}"
        )
        assert rwx.pr_state == "open", (
            f"RWX pr_state must stay untouched while its workflow is locked, "
            f"got {rwx.pr_state!r}"
        )

        # Negative control: close caller-p1's campaign → sync completes.
        pr = db.query(ProjectPullRequest).filter_by(pr_number=31).one()
        pr.pr_state = "closed"
        db.commit()
        _sync_linked_reusable_workflows_after_merge(db, caller2.project_id)

        wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).one()
        rwx = db.query(Project).filter_by(project_id=rwx_project.project_id).one()
        assert wf.workflow_status == "synced_with_github"
        assert rwx.pr_state == "synced"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests: GET /api/project-pr-status — cross-project lock surfaced to the
# frontend via ``locked_workflow_ids`` so a sibling caller's GitHub status
# refresh cannot speculatively unlock a shared reusable workflow.
# ---------------------------------------------------------------------------

@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_pr_status_exposes_cross_project_lock_for_sibling_caller(
    mock_tokens,
    mock_process_rx,
    mock_process_reg,
    client,
):
    """
    REGRESSION (issue #1370): A sibling caller project's GitHub PR-status
    refresh must surface the canonical workflow IDs that are still locked by
    an open PR campaign in *another* project, so the frontend cannot flip the
    linked reusable workflow badge back to ``committed_locally``/``synced``.

    SCENARIO: caller-p1 opens a PR campaign for a shared reusable workflow.
    caller-p2 also links the same workflow but has only its own old *closed*
    PR.  When caller-p2's UI calls ``/api/project-pr-status?refresh_from_github
    =true``, the response shows ``open_prs == 0`` from caller-p2's local view
    (caller-p1's PR is not visible there).  Without the lock signal, the
    frontend would treat all PRs as resolved and unlock the workflow.

    EXPECTED: The response includes ``locked_workflow_ids`` containing the
    shared canonical workflow ID, telling the frontend to keep that workflow
    under_review regardless of the local PR counts.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {
        "testuser/am-reuseable-workflow on main": {
            "status": "pr_created",
            "pr_url": "https://github.com/testuser/am-reuseable-workflow/pull/77",
            "pr_number": 77,
            "workflows_committed": ["deploy.yml"],
        }
    }
    mock_process_reg.return_value = {}

    db = TestingSessionLocal()
    caller2_name = "caller-p2-lock"
    linked_wf_id = None
    try:
        account, caller1, rwx_project = _make_account_and_projects(db)
        _add_repo(db, caller1)
        _add_repo(db, rwx_project, repo_name="testuser/rwx-repo")
        linked_wf = _add_linked_workflow(db, caller1, rwx_project, status="committed_locally")
        linked_wf_id = linked_wf.workflow_id

        caller2 = _add_caller_project(db, account, caller2_name, "STD2L")
        _add_repo(db, caller2, repo_name="testuser/repo2")
        _link_existing_workflow(db, caller2, rwx_project, linked_wf)
        # caller-p2 has its own *closed* PR (an old, unrelated campaign).  This
        # is exactly the trigger that used to fool the frontend into thinking
        # everything was resolved.
        db.add(ProjectPullRequest(
            project_id=caller2.project_id,
            repo_name="testuser/repo2",
            pr_number=42,
            pr_url="https://github.com/testuser/repo2/pull/42",
            branch_name="AM-STD2L-old",
            target_branch="main",
            pr_state="closed",
        ))
        db.commit()
    finally:
        db.close()

    # caller-p1 opens the campaign → canonical workflow becomes under_review.
    resp = client.post("/api/create-pull-requests", json={
        "github_user": TEST_GITHUB_USER,
        "project_name": TEST_STD_PROJECT,
        "selected_repos": ["testuser/myrepo"],
        "selected_workflows": [],
        "selected_reusable_workflows": ["deploy.yml"],
    })
    assert resp.status_code == 200, resp.text

    # Cached read (no GitHub roundtrip) — used here so the test does not need
    # to mock the per-PR GitHub fetch.  The lock signal must be present
    # regardless of refresh_from_github because the bug is in the response
    # contract, not the GitHub roundtrip.
    resp = client.get(
        "/api/project-pr-status",
        params={"github_user": TEST_GITHUB_USER, "project_name": caller2_name},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # From caller-p2's local view, caller-p1's PR is invisible → open_prs == 0.
    assert body["open_prs"] == 0, (
        f"Sibling caller view should not see caller-p1's open PR, "
        f"got open_prs={body['open_prs']}"
    )
    # The fix: the response surfaces the cross-project lock so the frontend
    # keeps the workflow badge locked.
    assert "locked_workflow_ids" in body, (
        "Response must expose locked_workflow_ids for the frontend to honour "
        "cross-project PR campaign locks"
    )
    assert linked_wf_id in body["locked_workflow_ids"], (
        f"Workflow {linked_wf_id} must be reported as locked while caller-p1's "
        f"PR campaign is open, got locked_workflow_ids={body['locked_workflow_ids']}"
    )


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_pr_status_locked_workflow_ids_empty_without_campaign(
    mock_tokens,
    client,
):
    """No open campaign anywhere → ``locked_workflow_ids`` is empty."""
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    db = TestingSessionLocal()
    try:
        _, std_project, rwx_project = _make_account_and_projects(db)
        _add_repo(db, std_project)
        _add_linked_workflow(db, std_project, rwx_project, status="committed_locally")
        db.commit()
    finally:
        db.close()

    resp = client.get(
        "/api/project-pr-status",
        params={"github_user": TEST_GITHUB_USER, "project_name": TEST_STD_PROJECT},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("locked_workflow_ids", []) == [], (
        f"Expected no locks without an open campaign, got {body.get('locked_workflow_ids')!r}"
    )
