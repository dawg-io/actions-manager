"""Endpoints whose only authorization was resolving the project.

Several mutating routes never called `check_project_access`. Their sole gate
was `_find_project_by_name` returning a row — the 404 doubled as "or access
denied". That conflates two different things: whether the caller can *see* the
project, and whether they may *change* it. A `project_viewer` grant resolves
the project, so a viewer could delete it, deploy CODEOWNERS to its
repositories, rewrite its workflow YAML, or roll a workflow back.

Auditing `check_project_access` call sites could never surface these, because
they are precisely the endpoints that do not call it.
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
    ProjectRepo,
    ProjectWorkflow,
    Repo,
    Workflow,
    WorkspaceMember,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_unguarded_write_endpoints.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

OWNER = "owner-user"
MEMBER = "member-user"
PROJECT = "GatedProject"
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


@pytest.fixture
def seeded():
    """A project owned by OWNER, with MEMBER holding project_viewer on it."""
    db = TestingSessionLocal()
    try:
        owner = Account(github_user=OWNER, github_email="o@example.com", account_type="pro")
        member = Account(github_user=MEMBER, github_email="m@example.com", account_type="pro")
        db.add_all([owner, member])
        db.flush()
        db.add(WorkspaceMember(user_id=member.user_id, workspace_role="member"))

        project = Project(
            project_name=PROJECT, project_code="GATE", user_id=owner.user_id,
            project_type="standard", pr_state="draft",
        )
        db.add(project)
        db.flush()
        db.add(ProjectMembership(
            user_id=member.user_id, project_id=project.project_id,
            project_role="project_viewer",
        ))

        repo = Repo(repo_name=REPO)
        db.add(repo)
        db.flush()
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))

        workflow = Workflow(
            workflow_name="ci", workflow_yaml="on: push",
            reusable_workflow=False, workflow_status="synced_with_github",
        )
        db.add(workflow)
        db.flush()
        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=workflow.workflow_id))
        db.commit()
        return {"project_id": project.project_id, "workflow_id": workflow.workflow_id}
    finally:
        db.close()


@pytest.fixture
def viewer(authenticate_client):
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    original_factory = app.state.middleware_db_factory
    app.state.middleware_db_factory = TestingSessionLocal
    with mock.patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as client:
            authenticate_client(client, MEMBER, TestingSessionLocal)
            yield client
    app.state.middleware_db_factory = original_factory
    app.dependency_overrides.pop(projects_get_db, None)
    app.dependency_overrides.pop(workflows_get_db, None)


def _project_still_exists() -> bool:
    db = TestingSessionLocal()
    try:
        return db.query(Project).filter(Project.project_name == PROJECT).first() is not None
    finally:
        db.close()


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_viewer_cannot_delete_the_project(mock_tokens, viewer, seeded):
    """The most destructive of them, and the one with no role check at all."""
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.delete(f"/api/projects/{PROJECT}?github_user={OWNER}")

    assert response.status_code == 403, response.text
    assert _project_still_exists(), "the project was deleted by a viewer"


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_viewer_cannot_toggle_reusable_workflows(mock_tokens, viewer, seeded):
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.post(
        f"/api/projects/{PROJECT}/toggle-reusable-workflows",
        json={"github_user": OWNER, "project_name": PROJECT, "enabled": True},
    )

    assert response.status_code == 403, response.text


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_viewer_cannot_unlink_a_reusable_workflow(mock_tokens, viewer, seeded):
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.delete(
        f"/api/projects/{PROJECT}/linked-reusable-workflows/{seeded['workflow_id']}"
        f"?github_user={OWNER}"
    )

    assert response.status_code == 403, response.text


@mock.patch("workflows._update_workflow_to_github")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_viewer_cannot_resolve_drift(mock_tokens, mock_push, viewer, seeded):
    """use_github writes caller-supplied content straight into workflow_yaml."""
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.post("/api/resolve-drift", json={
        "github_user": MEMBER, "project_name": PROJECT, "workflow_name": "ci",
        "resolution": "use_github", "github_content": "on: pwned",
    })

    assert response.status_code == 403, response.text
    mock_push.assert_not_called()

    db = TestingSessionLocal()
    try:
        wf = db.query(Workflow).filter(Workflow.workflow_name == "ci").first()
        assert wf.workflow_yaml == "on: push", "a viewer rewrote the workflow"
    finally:
        db.close()


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_viewer_cannot_restore_a_workflow_version(mock_tokens, viewer, seeded):
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.post("/api/workflows/restore-version", json={
        "github_user": MEMBER, "project_name": PROJECT,
        "workflow_name": "ci", "version_id": 1,
    })

    assert response.status_code == 403, response.text


@mock.patch("codeowners.user_tokens", new_callable=dict)
def test_viewer_cannot_save_a_codeowners_draft(mock_tokens, viewer, seeded):
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.post(f"/api/repos/{REPO}/codeowners", json={
        "github_user": MEMBER, "project_name": PROJECT,
        "content": "* @someone", "file_path": ".github/CODEOWNERS",
    })

    assert response.status_code == 403, response.text


@mock.patch("codeowners._create_branch")
@mock.patch("codeowners.user_tokens", new_callable=dict)
def test_viewer_cannot_deploy_codeowners(mock_tokens, mock_branch, viewer, seeded):
    """Deploy commits to the project's repositories."""
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.post(f"/api/repos/{REPO}/codeowners/deploy", json={
        "github_user": MEMBER, "project_name": PROJECT,
        "content": "* @someone", "mode": "direct",
    })

    assert response.status_code == 403, response.text
    mock_branch.assert_not_called()


@mock.patch("workflows.user_tokens", new_callable=dict)
def test_viewer_cannot_link_a_reusable_workflow(mock_tokens, viewer, seeded):
    """Linking writes a LinkedReusableWorkflow row and changes what this
    project's campaigns deliver. Its unlink counterpart was gated and this was
    not — found by the code review of the combined branch."""
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.post(
        f"/api/projects/{PROJECT}/linked-reusable-workflows",
        json={
            "github_user": OWNER,
            "rwx_project_id": 9999,
            "workflow_id": seeded["workflow_id"],
        },
    )

    assert response.status_code == 403, response.text


@mock.patch("custom_files.user_tokens", new_callable=dict)
def test_viewer_cannot_create_a_custom_file(mock_tokens, viewer, seeded):
    """_get_project_for_user was the only gate on three custom-file writes."""
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.post(
        f"/api/projects/{seeded['project_id']}/custom-files",
        json={"github_user": MEMBER, "file_path": "docs/NOTES.md", "content": "x"},
    )

    assert response.status_code == 403, response.text


@mock.patch("custom_files.user_tokens", new_callable=dict)
def test_a_member_can_still_read_custom_files(mock_tokens, viewer, seeded):
    """Widening that helper for reads is the point; it must not 403 a viewer."""
    mock_tokens[MEMBER] = "fake_token"

    response = viewer.get(
        f"/api/projects/{seeded['project_id']}/custom-files",
        params={"github_user": MEMBER},
    )

    assert response.status_code == 200, response.text
