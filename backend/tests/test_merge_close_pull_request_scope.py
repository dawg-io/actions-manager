"""merge/close-pull-request must prove the caller, and prove the target (#2071).

Both endpoints took ``repo_name`` and ``pr_number`` straight from the request
and checked neither against the project: the only validation was that the repo
string contained a "/". They also resolved the caller with
``_find_project_by_name``, which never reads ``ProjectMembership.project_role``,
so a project_viewer could merge a campaign's pull requests.

The caller's own GitHub token bounds the blast radius — GitHub still refuses a
repository the caller cannot write to — but ActionsManager's own role model was
bypassed, and ``_handle_merged_pull_request`` runs its "no open PRs left"
transitions even when the merged PR has no record here, so an unrelated merge
could move project and workflow state.
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
    ProjectPullRequest,
    ProjectRepo,
    Repo,
    WorkspaceMember,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_merge_close_pull_request_scope.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

OWNER = "owner-user"
MEMBER = "member-user"
PROJECT = "caller-project"
REPO = "owner-user/service"
OUTSIDE_REPO = "owner-user/not-in-project"
RECORDED_PR = 7


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


def _seed(project_role):
    """A project owned by OWNER with one recorded open PR, and MEMBER holding
    *project_role* on it as a full workspace member."""
    db = TestingSessionLocal()
    try:
        owner = Account(github_user=OWNER, github_email="owner@example.com", account_type="pro")
        member = Account(github_user=MEMBER, github_email="member@example.com", account_type="pro")
        db.add_all([owner, member])
        db.flush()
        db.add(WorkspaceMember(user_id=member.user_id, workspace_role="member"))

        project = Project(
            project_name=PROJECT, project_code="CALL", user_id=owner.user_id,
            project_type="standard", pr_state="open",
        )
        db.add(project)
        db.flush()
        db.add(ProjectMembership(
            user_id=member.user_id, project_id=project.project_id, project_role=project_role,
        ))

        repo = Repo(repo_name=REPO)
        db.add(repo)
        db.flush()
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))

        db.add(ProjectPullRequest(
            project_id=project.project_id, repo_name=REPO, pr_number=RECORDED_PR,
            pr_url=f"https://github.com/{REPO}/pull/{RECORDED_PR}", pr_state="open",
            branch_name=f"actions-manager/campaign-{RECORDED_PR}", target_branch="main",
        ))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def member_client(authenticate_client):
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


def _merge(client, repo_name=REPO, pr_number=RECORDED_PR):
    return client.put("/api/merge-pull-request", json={
        "github_user": MEMBER, "project_name": PROJECT,
        "repo_name": repo_name, "pr_number": pr_number,
    })


def _close(client, repo_name=REPO, pr_number=RECORDED_PR):
    return client.patch("/api/close-pull-request", json={
        "github_user": MEMBER, "project_name": PROJECT,
        "repo_name": repo_name, "pr_number": pr_number,
    })


@mock.patch("workflows._merge_pull_request_with_fallback")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_viewer_cannot_merge(mock_tokens, mock_merge, member_client):
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    response = _merge(member_client)

    assert response.status_code == 403, response.text
    assert "project_editor" in response.json()["detail"]
    mock_merge.assert_not_called()


@mock.patch("workflows.github_patch")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_project_viewer_cannot_close(mock_tokens, mock_patch, member_client):
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    response = _close(member_client)

    assert response.status_code == 403, response.text
    assert "project_editor" in response.json()["detail"]
    mock_patch.assert_not_called()


@mock.patch("workflows._merge_pull_request_with_fallback")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_a_repository_outside_the_project_is_refused(mock_tokens, mock_merge, member_client):
    """The merge target was caller-chosen: any owner/repo string was accepted."""
    _seed("project_editor")
    mock_tokens[MEMBER] = "fake_token"

    response = _merge(member_client, repo_name=OUTSIDE_REPO)

    assert response.status_code == 404, response.text
    assert "No pull request" in response.json()["detail"]
    mock_merge.assert_not_called()


@mock.patch("workflows._merge_pull_request_with_fallback")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_a_pr_number_this_project_never_opened_is_refused(mock_tokens, mock_merge, member_client):
    """A repo in the project is not enough — the PR number was free too."""
    _seed("project_editor")
    mock_tokens[MEMBER] = "fake_token"

    response = _merge(member_client, pr_number=4242)

    assert response.status_code == 404, response.text
    assert "No pull request" in response.json()["detail"]
    mock_merge.assert_not_called()


@mock.patch("workflows.github_patch")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_close_refuses_an_unrecorded_pull_request(mock_tokens, mock_patch, member_client):
    _seed("project_editor")
    mock_tokens[MEMBER] = "fake_token"

    response = _close(member_client, pr_number=4242)

    assert response.status_code == 404, response.text
    assert "No pull request" in response.json()["detail"]
    mock_patch.assert_not_called()


@mock.patch("workflows._merge_pull_request_with_fallback")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_an_editor_merging_a_recorded_pr_reaches_github(mock_tokens, mock_merge, member_client):
    """Both new checks must let the real case through.

    The merge is mocked as refused by GitHub (405), so this asserts the call was
    attempted rather than exercising the whole post-merge bookkeeping.
    """
    _seed("project_editor")
    mock_tokens[MEMBER] = "fake_token"
    mock_merge.return_value = (
        mock.MagicMock(status_code=405), "merge", "Pull request is not mergeable",
    )

    response = _merge(member_client)

    assert response.status_code == 400, response.text
    mock_merge.assert_called_once()
