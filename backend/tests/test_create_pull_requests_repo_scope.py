"""
Scoping a PR campaign to specific repositories.

The UI offers a campaign for the repositories a save has just added to a
project. That works only because /api/create-pull-requests accepts
selected_repos and intersects it with the project's own repos
(_get_filtered_repo_names). Two properties matter and neither was pinned:

- A subset really is a subset: the untargeted repos get no PR.
- A repo the project doesn't own is rejected loudly with 400, not silently
  dropped. This is why the caller must save the repo before offering the
  campaign; if the intersection ever became lossy instead of loud, the prompt
  would appear to succeed while delivering nothing.
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
    ProjectPullRequest,
    Repo,
    ProjectRepo,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_create_pull_requests_repo_scope.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_GITHUB_USER = "testuser"
TEST_PROJECT = "caller-project"
EXISTING_REPO = "testuser/existing"
ADDED_REPO = "testuser/added"


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
def client(authenticate_client):
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    with mock.patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            authenticate_client(c, TEST_GITHUB_USER, TestingSessionLocal)
            yield c
    app.dependency_overrides.pop(projects_get_db, None)
    app.dependency_overrides.pop(workflows_get_db, None)


@pytest.fixture
def project_with_two_repos():
    """A synced project delivering one workflow to two repositories."""
    db = TestingSessionLocal()
    try:
        account = Account(
            github_user=TEST_GITHUB_USER, github_email="t@t.com", account_type="pro"
        )
        db.add(account)
        db.flush()

        project = Project(
            project_name=TEST_PROJECT,
            project_code="CALL",
            user_id=account.user_id,
            project_type="standard",
            pr_state="synced",
        )
        db.add(project)
        db.flush()

        for name in (EXISTING_REPO, ADDED_REPO):
            repo = Repo(repo_name=name)
            db.add(repo)
            db.flush()
            db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))

        wf = Workflow(
            workflow_name="ci.yml",
            workflow_yaml="on: push",
            reusable_workflow=False,
            workflow_status="synced_with_github",
        )
        db.add(wf)
        db.flush()
        db.add(
            ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id)
        )
        db.commit()
        return project.project_id
    finally:
        db.close()


def _post(client, selected_repos):
    return client.post(
        "/api/create-pull-requests",
        json={
            "github_user": TEST_GITHUB_USER,
            "project_name": TEST_PROJECT,
            "selected_repos": selected_repos,
            "selected_workflows": ["ci.yml"],
        },
    )


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_campaign_targets_only_the_selected_repo(
    mock_tokens, mock_process_reg, mock_process_rx, client, project_with_two_repos
):
    """The repo the campaign was not scoped to must receive no PR."""
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {}
    mock_process_reg.return_value = {
        f"{ADDED_REPO} on main": {
            "status": "pr_created",
            "pr_url": f"https://github.com/{ADDED_REPO}/pull/1",
            "pr_number": 1,
            "workflows_committed": ["ci.yml"],
        }
    }

    response = _post(client, [ADDED_REPO])

    assert response.status_code == 200, response.text

    # The delivery layer is only ever handed the repo that was selected.
    assert mock_process_reg.called
    passed_repos = mock_process_reg.call_args.kwargs["repo_names"]
    assert list(passed_repos) == [ADDED_REPO]

    db = TestingSessionLocal()
    try:
        pr_repos = [
            pr.repo_name
            for pr in db.query(ProjectPullRequest)
            .filter(ProjectPullRequest.project_id == project_with_two_repos)
            .all()
        ]
    finally:
        db.close()
    assert pr_repos == [ADDED_REPO]
    assert EXISTING_REPO not in pr_repos


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_repo_not_attached_to_the_project_is_rejected(
    mock_tokens, mock_process_reg, mock_process_rx, client, project_with_two_repos
):
    """Naming an unattached repo must fail loudly, never silently deliver nothing.

    This is the failure the UI avoids by saving the repo before offering the
    campaign. If it ever became a silent no-op, the prompt would report success
    while the new repository stayed empty.
    """
    mock_tokens[TEST_GITHUB_USER] = "fake_token"
    mock_process_rx.return_value = {}
    mock_process_reg.return_value = {}

    response = _post(client, ["testuser/never-attached"])

    assert response.status_code == 400
    assert "No valid repositories selected" in response.json()["detail"]
    mock_process_reg.assert_not_called()
