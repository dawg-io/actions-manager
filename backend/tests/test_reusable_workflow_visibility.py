import os
import sys

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auth import user_tokens  # noqa: E402
from main import app  # noqa: E402
from models import (  # noqa: E402
    Account,
    Base,
    LinkedReusableWorkflow,
    Project,
    ProjectRepo,
    ProjectWorkflow,
    Repo,
    Workflow,
)
from projects import get_db as projects_get_db  # noqa: E402
from workflows import get_db as workflows_get_db  # noqa: E402


SQLALCHEMY_DATABASE_URL = "sqlite:///./test_reusable_workflow_visibility.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    Base.metadata.create_all(bind=engine)
    original_factory = app.state.middleware_db_factory
    app.state.middleware_db_factory = TestingSessionLocal
    user_tokens.clear()
    yield
    user_tokens.clear()
    app.state.middleware_db_factory = original_factory
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    with patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.pop(projects_get_db, None)
    app.dependency_overrides.pop(workflows_get_db, None)


def _user(db, login="alice"):
    account = Account(github_user=login, github_email=f"{login}@example.com", account_type="pro")
    db.add(account)
    db.flush()
    return account


def _project(db, user_id, name, code, project_type, visibility):
    project = Project(
        project_name=name,
        project_code=code,
        user_id=user_id,
        project_type=project_type,
        repository_visibility_scope=visibility,
    )
    db.add(project)
    db.flush()
    return project


def _repo(db, project, full_name):
    repo = db.query(Repo).filter(Repo.repo_name == full_name).first()
    if not repo:
        repo = Repo(repo_name=full_name)
        db.add(repo)
        db.flush()
    db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
    db.flush()
    return repo


def _workflow(db, rwx_project, name="deploy"):
    workflow = Workflow(
        workflow_name=name,
        workflow_yaml="name: Deploy\non:\n  workflow_call: {}\n",
        reusable_workflow=True,
    )
    db.add(workflow)
    db.flush()
    db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=workflow.workflow_id))
    db.flush()
    return workflow


def _seed_pair(
    db,
    *,
    caller_visibility,
    rwx_visibility,
    caller_repo="alice/app",
    rwx_repo="alice/rwx",
    caller_owner="alice",
):
    account = _user(db, caller_owner)
    standard = _project(db, account.user_id, "Consumer", "STD1", "standard", caller_visibility)
    rwx = _project(db, account.user_id, "RWX", "RWX1", "rwx", rwx_visibility)
    _repo(db, standard, caller_repo)
    _repo(db, rwx, rwx_repo)
    workflow = _workflow(db, rwx)
    db.commit()
    db.refresh(standard)
    db.refresh(rwx)
    db.refresh(workflow)
    return standard, rwx, workflow


def _link(client, standard, rwx, workflow, user="alice"):
    return client.post(
        f"/api/projects/{standard.project_name}/linked-reusable-workflows",
        json={"github_user": user, "workflow_id": workflow.workflow_id, "rwx_project_id": rwx.project_id},
    )


def test_public_caller_cannot_link_private_rwx_from_another_repository(client):
    db = TestingSessionLocal()
    try:
        standard, rwx, workflow = _seed_pair(
            db,
            caller_visibility="public",
            rwx_visibility="private",
            caller_repo="alice/app",
            rwx_repo="alice/rwx",
        )
    finally:
        db.close()

    response = _link(client, standard, rwx, workflow)
    assert response.status_code == 422
    assert "public repositories cannot call reusable workflows from private repositories" in response.json()["detail"]


@pytest.mark.parametrize(
    ("caller_visibility", "rwx_visibility", "caller_repo", "rwx_repo"),
    [
        ("public", "public", "alice/app", "bob/rwx"),
        ("private", "public", "alice/app", "bob/rwx"),
        ("private", "private", "alice/app", "alice/rwx"),
        ("public", "private", "alice/app", "alice/app"),
    ],
)
def test_valid_visibility_matrix_links_are_allowed(
    client, caller_visibility, rwx_visibility, caller_repo, rwx_repo
):
    db = TestingSessionLocal()
    try:
        standard, rwx, workflow = _seed_pair(
            db,
            caller_visibility=caller_visibility,
            rwx_visibility=rwx_visibility,
            caller_repo=caller_repo,
            rwx_repo=rwx_repo,
        )
    finally:
        db.close()

    response = _link(client, standard, rwx, workflow)
    assert response.status_code == 200, response.text


def test_private_caller_cannot_link_private_rwx_from_different_owner(client):
    db = TestingSessionLocal()
    try:
        standard, rwx, workflow = _seed_pair(
            db,
            caller_visibility="private",
            rwx_visibility="private",
            caller_repo="alice/app",
            rwx_repo="bob/rwx",
        )
    finally:
        db.close()

    response = _link(client, standard, rwx, workflow)
    assert response.status_code == 422
    assert "same user or organization" in response.json()["detail"]


def test_unknown_visibility_fails_closed(client):
    db = TestingSessionLocal()
    try:
        standard, rwx, workflow = _seed_pair(
            db,
            caller_visibility="unknown",
            rwx_visibility="public",
            caller_repo="alice/app",
            rwx_repo="bob/rwx",
        )
    finally:
        db.close()

    response = _link(client, standard, rwx, workflow)
    assert response.status_code == 422
    assert "visibility could not be verified" in response.json()["detail"]


def test_multi_repo_caller_blocks_if_any_target_repo_is_incompatible(client):
    db = TestingSessionLocal()
    try:
        standard, rwx, workflow = _seed_pair(
            db,
            caller_visibility="private",
            rwx_visibility="private",
            caller_repo="alice/app",
            rwx_repo="alice/rwx",
        )
        _repo(db, standard, "bob/other-app")
        db.commit()
    finally:
        db.close()

    response = _link(client, standard, rwx, workflow)
    assert response.status_code == 422
    assert "same user or organization" in response.json()["detail"]


def test_invalid_link_is_not_written_to_linked_reusable_workflows(client):
    db = TestingSessionLocal()
    try:
        standard, rwx, workflow = _seed_pair(
            db,
            caller_visibility="public",
            rwx_visibility="private",
            caller_repo="alice/app",
            rwx_repo="alice/rwx",
        )
    finally:
        db.close()

    response = _link(client, standard, rwx, workflow)
    assert response.status_code == 422

    db = TestingSessionLocal()
    try:
        assert db.query(LinkedReusableWorkflow).count() == 0
    finally:
        db.close()


def test_invalid_existing_link_does_not_generate_pr_or_commit(client, monkeypatch):
    db = TestingSessionLocal()
    try:
        standard, rwx, workflow = _seed_pair(
            db,
            caller_visibility="public",
            rwx_visibility="private",
            caller_repo="alice/app",
            rwx_repo="alice/rwx",
        )
        db.add(
            LinkedReusableWorkflow(
                standard_project_id=standard.project_id,
                rwx_project_id=rwx.project_id,
                workflow_id=workflow.workflow_id,
            )
        )
        db.commit()
    finally:
        db.close()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("reusable workflow delivery should not run for invalid links")

    monkeypatch.setattr("workflows._process_reusable_workflows_update", fail_if_called)
    user_tokens["alice"] = "fake-token"

    response = client.post(
        "/api/create-pull-requests",
        json={
            "github_user": "alice",
            "project_name": "Consumer",
            "selected_repos": ["alice/app"],
            "selected_workflows": [],
            "selected_reusable_workflows": ["deploy"],
        },
    )

    assert response.status_code == 400
    assert "public repositories cannot call reusable workflows from private repositories" in response.json()["detail"]
