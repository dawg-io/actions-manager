"""Where a reusable workflow is delivered is decided by who owns it.

A workflow a project owns lives in that project's repositories, whether or not
it carries the reusable label — so a PR campaign delivers it there, with the
rest of the files that project changed. Only a workflow LINKED from a Reusable
Workflow Project belongs in that project's repository instead.

`_get_reusable_workflow_repo` handled two cases — an RWX project (its own repo)
and a standard project with a link (the linked project's repo) — and a standard
project that owns its reusable workflows is neither. It fell through both to
`f"{user}/am-reuseable-workflow"`, so the workflow was delivered to a repository
with nothing to do with the project and never appeared in the campaign.
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
    LinkedReusableWorkflow,
    Project,
    ProjectRepo,
    ProjectWorkflow,
    Repo,
    Workflow,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_owned_reusable_workflow_delivery.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

USER = "testuser"
CALLER_REPO = "testuser/caller-repo"
RWX_REPO = "testuser/rwx-repo"


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
def client(authenticate_client):
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    with mock.patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            authenticate_client(c, USER, TestingSessionLocal)
            yield c
    app.dependency_overrides.pop(projects_get_db, None)
    app.dependency_overrides.pop(workflows_get_db, None)


def _project(db, account, name, code, project_type):
    project = Project(
        project_name=name, project_code=code, user_id=account.user_id,
        project_type=project_type, branch_option="default", use_prefix=True,
        pr_state="draft", reusable_workflows_enabled=(project_type == "rwx"),
    )
    db.add(project)
    db.flush()
    return project


def _repo(db, project, repo_name):
    repo = Repo(repo_name=repo_name)
    db.add(repo)
    db.flush()
    db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
    return repo


def _workflow(db, project, name, reusable):
    workflow = Workflow(
        workflow_name=name, workflow_yaml="on: push",
        reusable_workflow=reusable, workflow_status="new",
    )
    db.add(workflow)
    db.flush()
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=workflow.workflow_id))
    return workflow


def _campaign(client, project_name, repos, regular=None, reusable=None):
    body = {"github_user": USER, "project_name": project_name, "selected_repos": repos}
    if regular is not None:
        body["selected_workflows"] = regular
    if reusable is not None:
        body["selected_reusable_workflows"] = reusable
    return client.post("/api/create-pull-requests", json=body)


@pytest.fixture
def caller_project_owning_a_reusable_workflow():
    """A Caller Workflow Project whose reusable workflow sits in its own repo."""
    db = TestingSessionLocal()
    try:
        account = Account(github_user=USER, github_email="t@t.com", account_type="pro")
        db.add(account)
        db.flush()
        project = _project(db, account, "CallerProject", "CALL", "standard")
        _repo(db, project, CALLER_REPO)
        _workflow(db, project, "build-stuff", False)
        _workflow(db, project, "shared-workflow", True)
        db.commit()
    finally:
        db.close()


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_owned_reusable_workflow_goes_to_the_projects_own_repo(
    mock_tokens, mock_regular, mock_reusable, client,
    caller_project_owning_a_reusable_workflow,
):
    mock_tokens[USER] = "fake_token"
    mock_regular.return_value = {}
    mock_reusable.return_value = {}

    response = _campaign(
        client, "CallerProject", [CALLER_REPO],
        regular=["build-stuff"], reusable=["shared-workflow"],
    )

    assert response.status_code in (200, 400), response.text
    assert mock_regular.called
    kwargs = mock_regular.call_args.kwargs
    assert list(kwargs["repo_names"]) == [CALLER_REPO]
    assert sorted(w["name"] for w in kwargs["workflows"]) == ["build-stuff", "shared-workflow"]

    # Never to {user}/am-reuseable-workflow, which is not this project's repo.
    assert not mock_reusable.called


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_an_owned_reusable_workflow_alone_still_targets_the_projects_repos(
    mock_tokens, mock_regular, mock_reusable, client,
    caller_project_owning_a_reusable_workflow,
):
    """Selecting only the reusable workflow must not make the run target nothing."""
    mock_tokens[USER] = "fake_token"
    mock_regular.return_value = {}
    mock_reusable.return_value = {}

    response = _campaign(client, "CallerProject", [CALLER_REPO], reusable=["shared-workflow"])

    assert response.status_code in (200, 400), response.text
    assert mock_regular.called
    kwargs = mock_regular.call_args.kwargs
    assert list(kwargs["repo_names"]) == [CALLER_REPO]
    assert [w["name"] for w in kwargs["workflows"]] == ["shared-workflow"]
    assert not mock_reusable.called


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_a_linked_reusable_workflow_still_goes_to_the_rwx_repo(
    mock_tokens, mock_regular, mock_reusable, client,
):
    """The case the single-repo path exists for, and which must not change."""
    db = TestingSessionLocal()
    try:
        account = Account(github_user=USER, github_email="t@t.com", account_type="pro")
        db.add(account)
        db.flush()
        rwx = _project(db, account, "SharedWorkflows", "RWX1", "rwx")
        _repo(db, rwx, RWX_REPO)
        shared = _workflow(db, rwx, "linked-shared", True)
        caller = _project(db, account, "CallerLinked", "CLNK", "standard")
        _repo(db, caller, CALLER_REPO)
        db.add(LinkedReusableWorkflow(
            standard_project_id=caller.project_id,
            rwx_project_id=rwx.project_id,
            workflow_id=shared.workflow_id,
        ))
        db.commit()
    finally:
        db.close()

    mock_tokens[USER] = "fake_token"
    mock_regular.return_value = {}
    mock_reusable.return_value = {}

    response = _campaign(client, "CallerLinked", [CALLER_REPO], reusable=["linked-shared"])

    assert response.status_code in (200, 400), response.text
    assert mock_reusable.called, "a linked reusable workflow must still reach the RWX repo"
    assert mock_reusable.call_args.kwargs["reusable_repo"] == RWX_REPO
    assert [w["name"] for w in mock_reusable.call_args.kwargs["rxworkflows"]] == ["linked-shared"]


@mock.patch("workflows._process_reusable_workflows_update")
@mock.patch("workflows._process_regular_workflows_update")
@mock.patch("workflows.user_tokens", new_callable=dict)
def test_an_rwx_project_delivers_its_own_workflows_unchanged(
    mock_tokens, mock_regular, mock_reusable, client,
):
    db = TestingSessionLocal()
    try:
        account = Account(github_user=USER, github_email="t@t.com", account_type="pro")
        db.add(account)
        db.flush()
        rwx = _project(db, account, "SharedWorkflows", "RWX1", "rwx")
        _repo(db, rwx, RWX_REPO)
        _workflow(db, rwx, "rwx-own", True)
        db.commit()
    finally:
        db.close()

    mock_tokens[USER] = "fake_token"
    mock_regular.return_value = {}
    mock_reusable.return_value = {}

    response = _campaign(client, "SharedWorkflows", [RWX_REPO], reusable=["rwx-own"])

    assert response.status_code in (200, 400), response.text
    assert mock_reusable.called
    assert mock_reusable.call_args.kwargs["reusable_repo"] == RWX_REPO
    assert [w["name"] for w in mock_reusable.call_args.kwargs["rxworkflows"]] == ["rwx-own"]
