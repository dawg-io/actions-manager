"""Write access is required before a campaign reaches GitHub (issue #1909).

`/api/create-pull-requests` resolved the caller with `_get_project_and_token`,
which proves only that the caller can *see* the project — `_find_project_by_name`
never reads `ProjectMembership.project_role`. The endpoint then creates branches,
commits workflow files and opens pull requests across every repository in the
project, so a `project_viewer` could run a full campaign.

These tests drive real membership rows rather than patching
`_require_project_editor`, because patching the helper proves the helper raises,
not that the endpoint calls it — which was the whole defect.
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
    ProjectMembership,
    ProjectWorkflow,
    ProjectRepo,
    Repo,
    Workflow,
    WorkspaceMember,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_create_pull_requests_permissions.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

OWNER = "owner-user"
MEMBER = "member-user"
PROJECT = "caller-project"
REPO = "owner-user/service"


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _seed(project_role, workspace_role="member"):
    """A project owned by OWNER, with MEMBER holding *project_role* on it.

    ``workspace_role`` defaults to "member" rather than "read_only" on purpose.
    WriteProtectionMiddleware (backend/main.py:167) already rejects every
    non-safe method from a read_only workspace member, so that combination
    never reaches this endpoint in the first place; the combination actually
    exposed by #1909 is a full workspace member holding a project_viewer row.
    """
    db = TestingSessionLocal()
    try:
        owner = Account(github_user=OWNER, github_email="owner@example.com", account_type="pro")
        member = Account(github_user=MEMBER, github_email="member@example.com", account_type="pro")
        db.add_all([owner, member])
        db.flush()

        db.add(WorkspaceMember(user_id=member.user_id, workspace_role=workspace_role))

        project = Project(
            project_name=PROJECT,
            project_code="CALL",
            user_id=owner.user_id,
            project_type="standard",
            pr_state="synced",
        )
        db.add(project)
        db.flush()

        db.add(ProjectMembership(
            user_id=member.user_id,
            project_id=project.project_id,
            project_role=project_role,
        ))

        repo = Repo(repo_name=REPO)
        db.add(repo)
        db.flush()
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
        project.validation_repo_id = repo.repo_id

        workflow = Workflow(
            workflow_name="ci.yml",
            workflow_yaml="on: push",
            reusable_workflow=False,
            workflow_status="synced_with_github",
        )
        db.add(workflow)
        db.flush()
        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=workflow.workflow_id))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def member_client(authenticate_client):
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    # WriteProtectionMiddleware resolves the caller through its own factory.
    # Left pointing at the real SessionLocal it finds no workspace members and
    # skips enforcement entirely, which would let these tests pass with a role
    # the middleware would have rejected before the endpoint ever ran.
    original_factory = app.state.middleware_db_factory
    app.state.middleware_db_factory = TestingSessionLocal
    with mock.patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as client:
            authenticate_client(client, MEMBER, TestingSessionLocal)
            yield client
    app.state.middleware_db_factory = original_factory
    app.dependency_overrides.pop(projects_get_db, None)
    app.dependency_overrides.pop(workflows_get_db, None)


def _campaign(client, **extra):
    payload = {
        "github_user": MEMBER,
        "project_name": PROJECT,
        "selected_repos": [REPO],
        "selected_workflows": ["ci.yml"],
    }
    payload.update(extra)
    return client.post("/api/create-pull-requests", json=payload)


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_viewer_cannot_open_a_campaign(
    mock_tokens, mock_process_reg, mock_process_rx, member_client
):
    """Seeing the project is not enough to commit to every repository in it.

    Deliberately mocked to succeed, exactly as test_project_editor_is_unaffected
    is: the only difference between the two is the project role, so before the
    fix this returned 200 with a pull request opened.
    """
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"
    mock_process_rx.return_value = {}
    mock_process_reg.return_value = {
        f"{REPO} on main": {
            "status": "pr_created",
            "pr_url": f"https://github.com/{REPO}/pull/1",
            "pr_number": 1,
            "workflows_committed": ["ci.yml"],
        }
    }

    response = _campaign(member_client)

    assert response.status_code == 403, response.text
    assert "project_editor" in response.json()["detail"]
    mock_process_reg.assert_not_called()
    mock_process_rx.assert_not_called()


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_viewer_is_refused_before_the_async_task_is_queued(
    mock_tokens, mock_process_reg, mock_process_rx, member_client
):
    """async_mode must refuse outright, not hand back a task id that fails later.

    The check used to live inside `_run_create_pull_requests_async`, where a 403
    could only ever surface as a background task error the caller has to poll for.
    """
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    response = _campaign(member_client, async_mode=True)

    assert response.status_code == 403, response.text
    assert "task_id" not in response.json()
    mock_process_reg.assert_not_called()


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_editor_is_unaffected(
    mock_tokens, mock_process_reg, mock_process_rx, member_client
):
    """The gate must not lock out the members who are meant to run campaigns."""
    _seed("project_editor")
    mock_tokens[MEMBER] = "fake_token"
    mock_process_rx.return_value = {}
    mock_process_reg.return_value = {
        f"{REPO} on main": {
            "status": "pr_created",
            "pr_url": f"https://github.com/{REPO}/pull/1",
            "pr_number": 1,
            "workflows_committed": ["ci.yml"],
        }
    }

    response = _campaign(member_client)

    assert response.status_code == 200, response.text
    assert mock_process_reg.called


@mock.patch("workflows._check_validation_repo_access")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_viewer_cannot_run_preflight(
    mock_tokens, mock_repo_access, member_client
):
    """Preflight opens a pull request in the validation repository, so it is a
    GitHub write and carries the same gate as the campaign it validates."""
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    response = member_client.post("/api/run-preflight-validation", json={
        "github_user": MEMBER,
        "project_name": PROJECT,
        "selected_workflows": ["ci.yml"],
    })

    assert response.status_code == 403, response.text
    assert "project_editor" in response.json()["detail"]
    mock_repo_access.assert_not_called()


# ---------------------------------------------------------------------------
# The validation PR that approves preflight (#2071)
#
# Merging it sets preflight to approved, and approved preflight is what
# _ensure_preflight_allows_campaign checks before a campaign may run — so
# leaving these two ungated let a project_viewer walk around the gate on
# running preflight.
# ---------------------------------------------------------------------------

VALIDATION_PR_URL = "https://github.com/owner-user/service/pull/7"


def _record_validation_pr():
    """Give the seeded project a validation PR, so the endpoints get past their
    "no validation PR is recorded" check and would otherwise reach GitHub."""
    db = TestingSessionLocal()
    try:
        project = db.query(Project).filter(Project.project_name == PROJECT).first()
        project.last_preflight_pr_url = VALIDATION_PR_URL
        project.last_preflight_status = "pr_created"
        db.commit()
    finally:
        db.close()


@mock.patch("workflows._fetch_validation_pr_or_raise")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_viewer_cannot_merge_the_validation_pr(
    mock_tokens, mock_fetch, member_client
):
    _seed("project_viewer")
    _record_validation_pr()
    mock_tokens[MEMBER] = "fake_token"

    response = member_client.put("/api/merge-preflight-validation-pr", json={
        "github_user": MEMBER, "project_name": PROJECT,
    })

    assert response.status_code == 403, response.text
    assert "project_editor" in response.json()["detail"]
    mock_fetch.assert_not_called()


@mock.patch("workflows._fetch_validation_pr_or_raise")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_viewer_cannot_close_the_validation_pr(
    mock_tokens, mock_fetch, member_client
):
    _seed("project_viewer")
    _record_validation_pr()
    mock_tokens[MEMBER] = "fake_token"

    response = member_client.patch("/api/close-preflight-validation-pr", json={
        "github_user": MEMBER, "project_name": PROJECT,
    })

    assert response.status_code == 403, response.text
    assert "project_editor" in response.json()["detail"]
    mock_fetch.assert_not_called()


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_editor_passes_the_validation_pr_gate(mock_tokens, member_client):
    """An editor gets through to the next check rather than being refused.

    No validation PR is recorded here, so reaching the 400 that says so is
    itself the proof the gate let them past — the gate runs before that check.
    """
    _seed("project_editor")
    mock_tokens[MEMBER] = "fake_token"

    for method, path in (
        (member_client.put, "/api/merge-preflight-validation-pr"),
        (member_client.patch, "/api/close-preflight-validation-pr"),
    ):
        response = method(path, json={"github_user": MEMBER, "project_name": PROJECT})
        assert response.status_code == 400, f"{path}: {response.text}"
        assert "No validation PR is recorded" in response.json()["detail"]
