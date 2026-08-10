"""
Tests for GET /api/projects/{name}'s drifted_workflow_names field (code review
follow-up, part of #1789).

Root cause: the project page showed every workflow as "Synced" on load, then
flipped drifted ones to "Drift Detected" a moment later once the client-side
live drift check (DriftDetection component, GET /api/projects/{id}/drift)
resolved. WorkflowDriftState (issue #1793) already persists per-workflow
drift state on every check, but nothing surfaced it in the initial
project-load response, so the frontend always started from "nothing is
drifted". This field is the read-side fix: on first paint the badge can now
reflect the last known state instead of a hardcoded default.
"""

import sys
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, Workflow, ProjectWorkflow, Repo, WorkflowDriftState
from main import app
from projects import get_db as projects_get_db

TEST_PROJECT_NAME = "drift_badge_project"
TEST_GITHUB_USER = "driftbadgeuser"

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_get_project_drifted_workflow_names.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(projects_get_db, None)


def _make_project(db):
    account = Account(github_user=TEST_GITHUB_USER, github_email="driftbadge@example.com", account_type="free")
    db.add(account)
    db.flush()
    project = Project(project_name=TEST_PROJECT_NAME, project_code="DBP", user_id=account.user_id)
    db.add(project)
    db.flush()
    return account, project


def _add_workflow(db, project, name):
    wf = Workflow(workflow_name=name, workflow_yaml="on: push", workflow_status="synced_with_github")
    db.add(wf)
    db.flush()
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
    db.flush()
    return wf


def test_drifted_workflow_included_in_initial_load(client):
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db)
        drifted_wf = _add_workflow(db, project, "deploy.yml")
        clean_wf = _add_workflow(db, project, "ci.yml")
        repo = Repo(repo_name="driftbadgeuser/widgets")
        db.add(repo)
        db.flush()
        db.add(WorkflowDriftState(
            project_id=project.project_id, workflow_id=drifted_wf.workflow_id, repo_id=repo.repo_id, has_drift=True,
        ))
        db.add(WorkflowDriftState(
            project_id=project.project_id, workflow_id=clean_wf.workflow_id, repo_id=repo.repo_id, has_drift=False,
        ))
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["drifted_workflow_names"] == ["deploy.yml"]


def test_no_drift_state_yet_returns_empty_list(client):
    """A project that has never had a drift check run should not show anything as drifted."""
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db)
        _add_workflow(db, project, "ci.yml")
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    assert resp.json()["drifted_workflow_names"] == []


def test_resolved_drift_no_longer_listed(client):
    """A workflow that was drifted but has since resolved (has_drift flipped
    back to False by a later check) must not show as drifted."""
    db = TestingSessionLocal()
    try:
        account, project = _make_project(db)
        wf = _add_workflow(db, project, "deploy.yml")
        repo = Repo(repo_name="driftbadgeuser/widgets")
        db.add(repo)
        db.flush()
        db.add(WorkflowDriftState(
            project_id=project.project_id, workflow_id=wf.workflow_id, repo_id=repo.repo_id, has_drift=False,
        ))
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/projects/{TEST_PROJECT_NAME}", params={"github_user": TEST_GITHUB_USER})
    assert resp.status_code == 200, resp.text
    assert resp.json()["drifted_workflow_names"] == []
