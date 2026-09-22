"""Secrets, environment variables, environments and rulesets refuse a viewer.

These modules had no project-role check between them — fourteen write routes,
zero calls to check_project_access or _require_project_editor. So hiding the
controls in the UI stopped a viewer clicking them and nothing more: the same
request made outside the interface was accepted.

They also take the caller's own name as a client-supplied field and use it to
select whose GitHub token is sent, which is #2087. Both are closed here by
require_project_write_access, which proves the name against the session before
it proves the role.
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
    Base, Account, Project, ProjectMembership, ProjectRepo, Repo, WorkspaceMember,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_config_write_gates.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

OWNER = "owner-user"
MEMBER = "member-user"
PROJECT = "GatedConfigProject"
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


def _seed(project_role):
    db = TestingSessionLocal()
    try:
        owner = Account(github_user=OWNER, github_email="o@e.com", account_type="pro")
        member = Account(github_user=MEMBER, github_email="m@e.com", account_type="pro")
        db.add_all([owner, member])
        db.flush()
        db.add(WorkspaceMember(user_id=member.user_id, workspace_role="member"))

        project = Project(
            project_name=PROJECT, project_code="GCFG", user_id=owner.user_id,
            project_type="standard",
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
        db.commit()
    finally:
        db.close()


@pytest.fixture
def viewer(authenticate_client):
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    original = app.state.middleware_db_factory
    app.state.middleware_db_factory = TestingSessionLocal
    with mock.patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as client:
            authenticate_client(client, MEMBER, TestingSessionLocal)
            yield client
    app.state.middleware_db_factory = original
    app.dependency_overrides.pop(projects_get_db, None)
    app.dependency_overrides.pop(workflows_get_db, None)


# --- environment variables and environments --------------------------------

@mock.patch("github_env_vars.user_tokens", new_callable=dict)
def test_viewer_cannot_update_env_vars(mock_tokens, viewer):
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    resp = viewer.post("/api/update-env-vars", json={
        "user": MEMBER, "project_name": PROJECT,
        "repo_names": [REPO], "env": [{"key": "K", "value": "V"}],
    })

    assert resp.status_code == 403, resp.text


@mock.patch("github_env_vars.user_tokens", new_callable=dict)
def test_viewer_cannot_delete_env_vars(mock_tokens, viewer):
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    resp = viewer.request("DELETE", "/api/delete-env-vars", json={
        "user": MEMBER, "project_name": PROJECT, "repo_names": [REPO], "env": [],
    })

    assert resp.status_code == 403, resp.text


@mock.patch("github_env_vars.user_tokens", new_callable=dict)
def test_viewer_cannot_create_an_environment(mock_tokens, viewer):
    """Repo-scoped: this route carries no project, so the gate resolves one."""
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    resp = viewer.post("/api/create-environment", json={
        "user": MEMBER, "repo_name": REPO, "environment_name": "production",
    })

    assert resp.status_code == 403, resp.text


# --- secrets ---------------------------------------------------------------

@mock.patch("github_secrets.user_tokens", new_callable=dict)
def test_viewer_cannot_create_secrets(mock_tokens, viewer):
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    resp = viewer.post("/api/create-secrets", json={
        "user": MEMBER, "project_name": PROJECT,
        "repo_names": [REPO], "secrets": [{"secret_key": "K", "secret_value": "V"}],
    })

    assert resp.status_code == 403, resp.text


@mock.patch("github_secrets.user_tokens", new_callable=dict)
def test_viewer_cannot_delete_secrets(mock_tokens, viewer):
    _seed("project_viewer")
    mock_tokens[MEMBER] = "fake_token"

    resp = viewer.request("DELETE", "/api/delete-secrets", json={
        "user": MEMBER, "project_name": PROJECT,
        "repo_names": [REPO], "secret_name": "K",
    })

    assert resp.status_code == 403, resp.text


# --- an editor is unaffected ----------------------------------------------

@mock.patch("github_secrets.user_tokens", new_callable=dict)
def test_an_editor_passes_the_gate(mock_tokens, viewer):
    """The gate must not lock out the role that is meant to configure these.

    Asserts only that the request is not refused: what happens after depends on
    GitHub, which is not reachable here.
    """
    _seed("project_editor")
    mock_tokens[MEMBER] = "fake_token"

    resp = viewer.post("/api/create-secrets", json={
        "user": MEMBER, "project_name": PROJECT,
        "repo_names": [REPO], "secrets": [{"secret_key": "K", "secret_value": "V"}],
    })

    assert resp.status_code != 403, resp.text


@mock.patch("github_secrets.user_tokens", new_callable=dict)
def test_naming_another_user_is_refused(mock_tokens, viewer):
    """#2087: the name selects whose GitHub token is used, so it is proven."""
    _seed("project_editor")
    mock_tokens[MEMBER] = "fake_token"
    mock_tokens[OWNER] = "owner_token"

    resp = viewer.post("/api/create-secrets", json={
        "user": OWNER, "project_name": PROJECT,
        "repo_names": [REPO], "secrets": [{"secret_key": "K", "secret_value": "V"}],
    })

    assert resp.status_code == 403, resp.text
