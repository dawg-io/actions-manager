"""
Tests for GET /api/projects/ project list pr_state for RWX projects.

When a linked standard (caller) project has an open PR campaign that targets
workflows owned by a Reusable Workflow Project (rwx), the project list must
show the RWX project with pr_state="open" (displayed as "Under Review") rather
than the stored pr_state (e.g. "synced").
"""
import sys
import os
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
# Test database (in-memory for isolation)
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_GITHUB_USER = "testuser"


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
    with patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.pop(projects_get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_linked_scenario(db, *, std_pr_state="open", rwx_pr_state="synced"):
    """
    Creates:
      - A standard (caller) project with a PR in the given state
      - An RWX project owning a reusable workflow
      - A LinkedReusableWorkflow linking them
    """
    account = Account(
        github_user=TEST_GITHUB_USER,
        github_email="test@example.com",
        account_type="free",
    )
    db.add(account)
    db.flush()

    std_project = Project(
        project_name="caller-project",
        project_code="CP1",
        user_id=account.user_id,
        pr_state="open" if std_pr_state == "open" else "synced",
        project_type="standard",
    )
    db.add(std_project)
    db.flush()

    rwx_project = Project(
        project_name="rwx-project",
        project_code="RWX1",
        user_id=account.user_id,
        pr_state=rwx_pr_state,
        project_type="rwx",
    )
    db.add(rwx_project)
    db.flush()

    wf = Workflow(
        workflow_name="shared.yml",
        workflow_yaml="on: workflow_call",
        reusable_workflow=True,
        workflow_status="under_review",
    )
    db.add(wf)
    db.flush()

    db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf.workflow_id))
    db.flush()

    db.add(LinkedReusableWorkflow(
        standard_project_id=std_project.project_id,
        rwx_project_id=rwx_project.project_id,
        workflow_id=wf.workflow_id,
    ))
    db.flush()

    pr = ProjectPullRequest(
        project_id=std_project.project_id,
        repo_name="testuser/rwx-repo",
        pr_number=10,
        pr_url="https://github.com/testuser/rwx-repo/pull/10",
        branch_name="am/update",
        target_branch="main",
        pr_state=std_pr_state,
    )
    db.add(pr)
    db.commit()
    return std_project, rwx_project


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_rwx_project_shows_open_when_linked_standard_has_open_pr(client):
    """
    RWX project list entry must show pr_state='open' when a linked standard
    project has an open PR campaign targeting its workflows.
    """
    db = TestingSessionLocal()
    try:
        _seed_linked_scenario(db, std_pr_state="open", rwx_pr_state="synced")
    finally:
        db.close()

    resp = client.get("/api/projects/", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    projects = resp.json()

    rwx_entry = next(p for p in projects if p["project_type"] == "rwx")
    assert rwx_entry["pr_state"] == "open", (
        f"Expected 'open' but got {rwx_entry['pr_state']!r}"
    )


def test_rwx_project_shows_synced_when_linked_pr_is_merged(client):
    """
    Once the linked PR is merged, the RWX project list entry should show its
    stored pr_state (synced) — no override.
    """
    db = TestingSessionLocal()
    try:
        _seed_linked_scenario(db, std_pr_state="merged", rwx_pr_state="synced")
    finally:
        db.close()

    resp = client.get("/api/projects/", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    projects = resp.json()

    rwx_entry = next(p for p in projects if p["project_type"] == "rwx")
    assert rwx_entry["pr_state"] == "synced", (
        f"Expected 'synced' but got {rwx_entry['pr_state']!r}"
    )


def test_rwx_project_already_open_stays_open(client):
    """
    If the RWX project itself already has pr_state='open' (its own PR campaign),
    the result should still be 'open'.
    """
    db = TestingSessionLocal()
    try:
        _seed_linked_scenario(db, std_pr_state="open", rwx_pr_state="open")
    finally:
        db.close()

    resp = client.get("/api/projects/", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    projects = resp.json()

    rwx_entry = next(p for p in projects if p["project_type"] == "rwx")
    assert rwx_entry["pr_state"] == "open"


def test_standard_project_not_affected_by_rwx_logic(client):
    """
    The standard (caller) project should report its own pr_state unchanged.
    """
    db = TestingSessionLocal()
    try:
        _seed_linked_scenario(db, std_pr_state="open", rwx_pr_state="synced")
    finally:
        db.close()

    resp = client.get("/api/projects/", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    projects = resp.json()

    std_entry = next(p for p in projects if p["project_type"] == "standard")
    assert std_entry["pr_state"] == "open"


# ---------------------------------------------------------------------------
# Tests: RWX project shows Draft when owned workflow is committed_locally
# ---------------------------------------------------------------------------

def test_rwx_project_shows_draft_when_owned_workflow_committed_locally(client):
    """
    RWX project list entry must show pr_state='draft' when an owned workflow
    has workflow_status='committed_locally' (local edits not yet pushed).
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
            project_name="rwx-project",
            project_code="RWX1",
            user_id=account.user_id,
            pr_state="synced",
            project_type="rwx",
        )
        db.add(rwx_project)
        db.flush()

        wf = Workflow(
            workflow_name="shared.yml",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="committed_locally",
        )
        db.add(wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf.workflow_id))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    projects = resp.json()

    rwx_entry = next(p for p in projects if p["project_type"] == "rwx")
    assert rwx_entry["pr_state"] == "draft", (
        f"Expected 'draft' but got {rwx_entry['pr_state']!r}"
    )


def test_rwx_project_open_pr_takes_priority_over_draft_workflow(client):
    """
    When an RWX project has both a linked open PR and a draft workflow,
    the 'open' state (Under Review) should take priority over 'draft'.
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

        std_project = Project(
            project_name="caller-project",
            project_code="CP1",
            user_id=account.user_id,
            pr_state="open",
            project_type="standard",
        )
        db.add(std_project)
        db.flush()

        rwx_project = Project(
            project_name="rwx-project",
            project_code="RWX1",
            user_id=account.user_id,
            pr_state="synced",
            project_type="rwx",
        )
        db.add(rwx_project)
        db.flush()

        # One workflow is committed_locally (draft)
        wf = Workflow(
            workflow_name="shared.yml",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="committed_locally",
        )
        db.add(wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf.workflow_id))
        db.flush()

        # It's also linked with an open PR from the standard project
        db.add(LinkedReusableWorkflow(
            standard_project_id=std_project.project_id,
            rwx_project_id=rwx_project.project_id,
            workflow_id=wf.workflow_id,
        ))
        db.flush()

        pr = ProjectPullRequest(
            project_id=std_project.project_id,
            repo_name="testuser/rwx-repo",
            pr_number=10,
            pr_url="https://github.com/testuser/rwx-repo/pull/10",
            branch_name="am/update",
            target_branch="main",
            pr_state="open",
        )
        db.add(pr)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    projects = resp.json()

    rwx_entry = next(p for p in projects if p["project_type"] == "rwx")
    assert rwx_entry["pr_state"] == "open", (
        f"Expected 'open' (Under Review takes priority) but got {rwx_entry['pr_state']!r}"
    )


def test_rwx_project_synced_when_all_workflows_synced(client):
    """
    RWX project stays 'synced' when all owned workflows are synced_with_github.
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
            project_name="rwx-project",
            project_code="RWX1",
            user_id=account.user_id,
            pr_state="synced",
            project_type="rwx",
        )
        db.add(rwx_project)
        db.flush()

        wf = Workflow(
            workflow_name="shared.yml",
            workflow_yaml="on: workflow_call",
            reusable_workflow=True,
            workflow_status="synced_with_github",
        )
        db.add(wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf.workflow_id))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    projects = resp.json()

    rwx_entry = next(p for p in projects if p["project_type"] == "rwx")
    assert rwx_entry["pr_state"] == "synced", (
        f"Expected 'synced' but got {rwx_entry['pr_state']!r}"
    )
