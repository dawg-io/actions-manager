"""
`pending_delivery_repos` on GET /api/projects/{name}.

Drives the reminder that a repository added to a project hasn't received the
project's workflows yet. The rule it has to get right is the same one issue
#1981 turned on: delivery is per (workflow, repo), so it is answered from
`confirmed_present_at` and never from `workflow_status`, which is per-workflow
and would call a brand-new repo delivered the moment any other repo had the
file.
"""
import sys
import os
from datetime import datetime, timezone

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
    WorkflowDriftState,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_pending_delivery_repos.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_GITHUB_USER = "testuser"
TEST_PROJECT = "caller-project"
DELIVERED_REPO = "testuser/payments-service"
NEW_REPO = "testuser/checkout-web"


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


def _build(
    *,
    checked=True,
    workflow_status="synced_with_github",
    confirm_delivered_repo=True,
    reusable_only=False,
    project_type="standard",
):
    """A project with two repos; only DELIVERED_REPO has confirmed delivery."""
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
            project_type=project_type,
            pr_state="synced",
            last_drift_check_at=datetime.now(timezone.utc) if checked else None,
        )
        db.add(project)
        db.flush()

        repos = {}
        for name in (DELIVERED_REPO, NEW_REPO):
            repo = Repo(repo_name=name)
            db.add(repo)
            db.flush()
            db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
            repos[name] = repo

        wf = Workflow(
            workflow_name="ci.yml",
            workflow_yaml="on: push",
            reusable_workflow=reusable_only,
            workflow_status=workflow_status,
        )
        db.add(wf)
        db.flush()
        db.add(
            ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id)
        )

        if confirm_delivered_repo:
            db.add(
                WorkflowDriftState(
                    project_id=project.project_id,
                    workflow_id=wf.workflow_id,
                    repo_id=repos[DELIVERED_REPO].repo_id,
                    branch="main",
                    has_drift=False,
                    confirmed_present_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
        return project.project_id, wf.workflow_id, repos
    finally:
        db.close()


def _pending(client):
    response = client.get(
        f"/api/projects/{TEST_PROJECT}", params={"github_user": TEST_GITHUB_USER}
    )
    assert response.status_code == 200, response.text
    return response.json()["pending_delivery_repos"]


def test_repo_without_confirmed_delivery_is_pending(client):
    _build()
    assert _pending(client) == [NEW_REPO]


def test_workflow_status_alone_does_not_clear_a_repo(client):
    """The bug this must not reintroduce.

    The workflow is synced_with_github because it really is live in the other
    repo. Reading that per-workflow status as delivery would report the new repo
    as already having the file — the same false negative issue #1981 fixed in the
    opposite direction.
    """
    _build(workflow_status="synced_with_github", confirm_delivered_repo=False)
    assert _pending(client) == sorted([DELIVERED_REPO, NEW_REPO])


def test_confirmed_delivery_clears_a_repo(client):
    _build()
    assert DELIVERED_REPO not in _pending(client)


def test_an_open_pull_request_pauses_the_reminder(client):
    """The user has already acted; nagging until merge would be wrong."""
    project_id, _, _ = _build()
    db = TestingSessionLocal()
    try:
        db.add(
            ProjectPullRequest(
                project_id=project_id,
                repo_name=NEW_REPO,
                pr_number=1,
                pr_url=f"https://github.com/{NEW_REPO}/pull/1",
                pr_state="open",
                branch_name="actions-manager/CALL/checkout-web/abc-main",
                target_branch="main",
                workflow_names="ci.yml",
            )
        )
        db.commit()
    finally:
        db.close()

    assert _pending(client) == []


def test_a_merged_pull_request_does_not_pause_the_reminder(client):
    """Only an *open* PR means delivery is in flight.

    A merged one leaves the drift check to confirm the file really landed, and a
    closed one means it never did.
    """
    project_id, _, _ = _build()
    db = TestingSessionLocal()
    try:
        db.add(
            ProjectPullRequest(
                project_id=project_id,
                repo_name=NEW_REPO,
                pr_number=1,
                pr_url=f"https://github.com/{NEW_REPO}/pull/1",
                pr_state="closed",
                branch_name="actions-manager/CALL/checkout-web/abc-main",
                target_branch="main",
                workflow_names="ci.yml",
            )
        )
        db.commit()
    finally:
        db.close()

    assert _pending(client) == [NEW_REPO]


def test_a_project_never_drift_checked_claims_nothing(client):
    """No check has run, so an absent confirmation means "never looked".

    A project delivered by direct commit leaves no PR row and no confirmation
    until a check sees the file; reporting every repo as waiting would be a
    confident wrong answer.
    """
    _build(checked=False)
    assert _pending(client) == []


def test_a_project_with_no_regular_workflows_claims_nothing(client):
    """There is nothing to deliver, so no repo can be waiting for it."""
    _build(reusable_only=True, confirm_delivered_repo=False)
    assert _pending(client) == []


def test_the_save_response_reports_the_new_pending_list(client):
    """PUT returns it too, so the UI never needs a refresh to show the reminder.

    Adding a repository is the moment the reminder becomes true, so a client
    that could only learn it from the next GET would show nothing until the user
    reloaded the page.
    """
    project_id, _, _ = _build()

    response = client.put(
        f"/api/projects/{project_id}/",
        json={
            "github_user": TEST_GITHUB_USER,
            "project_name": TEST_PROJECT,
            "selected_repos": [DELIVERED_REPO, NEW_REPO],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": False,
        },
        headers={"X-GitHub-User": TEST_GITHUB_USER},
    )

    assert response.status_code == 200, response.text
    assert response.json()["pending_delivery_repos"] == [NEW_REPO]


def test_the_save_response_agrees_with_the_next_load(client):
    """The two must not diverge, or the reminder flickers on the next refresh.

    This is why the save recomputes server-side instead of the client guessing
    that a just-added repo is waiting: a repo removed and re-added keeps its
    delivery history, so "just added" does not imply "not delivered".
    """
    project_id, _, _ = _build()

    saved = client.put(
        f"/api/projects/{project_id}/",
        json={
            "github_user": TEST_GITHUB_USER,
            "project_name": TEST_PROJECT,
            "selected_repos": [DELIVERED_REPO, NEW_REPO],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": False,
        },
        headers={"X-GitHub-User": TEST_GITHUB_USER},
    )
    assert saved.status_code == 200, saved.text

    assert saved.json()["pending_delivery_repos"] == _pending(client)


def test_an_open_pr_without_workflows_does_not_pause_the_reminder(client):
    """A CODEOWNERS-only or custom-file-only campaign delivers no workflow.

    It still opens a PR for the repo, so suppressing on the PR alone would hide
    the reminder for the life of a PR that cannot satisfy it.
    """
    project_id, _, _ = _build()
    db = TestingSessionLocal()
    try:
        db.add(
            ProjectPullRequest(
                project_id=project_id,
                repo_name=NEW_REPO,
                pr_number=7,
                pr_url=f"https://github.com/{NEW_REPO}/pull/7",
                pr_state="open",
                branch_name="actions-manager/CALL/checkout-web/abc-main",
                target_branch="main",
                workflow_names="",
            )
        )
        db.commit()
    finally:
        db.close()

    assert _pending(client) == [NEW_REPO]


_SAVE_PAYLOAD = {
    "github_user": TEST_GITHUB_USER,
    "project_name": TEST_PROJECT,
    "selected_repos": [DELIVERED_REPO, NEW_REPO],
    "workflows": [],
    "rxworkflows": [],
    "branch_regex": "",
    "branch_option": "default",
    "branch_max_age_days": 30,
    "reusable_workflows_enabled": False,
    "use_prefix": False,
}


def test_the_save_says_whether_it_could_tell(client):
    """[] is ambiguous on its own, so the save reports which [] it means."""
    project_id, _, _ = _build()
    response = client.put(
        f"/api/projects/{project_id}/",
        json=_SAVE_PAYLOAD,
        headers={"X-GitHub-User": TEST_GITHUB_USER},
    )
    assert response.status_code == 200, response.text
    assert response.json()["pending_delivery_known"] is True


def test_an_unchecked_project_says_it_could_not_tell(client):
    """So the caller does not read [] as "nothing is waiting" and go quiet.

    The delivery prompt falls back to prompting when this is False; treating the
    empty list as fact would silence it for every never-checked project.
    """
    project_id, _, _ = _build(checked=False)
    response = client.put(
        f"/api/projects/{project_id}/",
        json=_SAVE_PAYLOAD,
        headers={"X-GitHub-User": TEST_GITHUB_USER},
    )
    assert response.status_code == 200, response.text
    assert response.json()["pending_delivery_known"] is False
    assert response.json()["pending_delivery_repos"] == []
