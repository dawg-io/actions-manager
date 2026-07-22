"""
Tests for GET /api/projects/{name} linked_standard_projects response field.

Verifies that:
- RWX projects return `linked_standard_projects` listing standard projects that
  link any of their workflows.
- Results are deduplicated when multiple workflows from the same standard project
  are linked.
- Only standard projects belonging to the same user are returned (security scope).
- Standard projects always return an empty `linked_standard_projects` list.
"""
import sys
import os

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, Workflow, ProjectWorkflow, LinkedReusableWorkflow
from main import app
from projects import get_db as projects_get_db

# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_linked_standard_projects.db"
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
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """TestClient with the test DB wired in for the projects router."""
    app.dependency_overrides[projects_get_db] = override_get_db
    with patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.pop(projects_get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, github_user="testuser", email="test@example.com"):
    account = Account(
        github_user=github_user,
        github_email=email,
        account_type="free",
    )
    db.add(account)
    db.flush()
    return account


def _make_project(db, user_id, name, code, project_type="standard"):
    project = Project(
        project_name=name,
        project_code=code,
        user_id=user_id,
        project_type=project_type,
        branch_option="default",
    )
    db.add(project)
    db.flush()
    return project


def _make_workflow(db, project_id, name="reusable.yml"):
    wf = Workflow(
        workflow_name=name,
        workflow_yaml="on: workflow_call",
        reusable_workflow=True,
    )
    db.add(wf)
    db.flush()
    pw = ProjectWorkflow(project_id=project_id, workflow_id=wf.workflow_id)
    db.add(pw)
    db.flush()
    return wf


def _link(db, standard_project_id, rwx_project_id, workflow_id):
    link = LinkedReusableWorkflow(
        standard_project_id=standard_project_id,
        rwx_project_id=rwx_project_id,
        workflow_id=workflow_id,
    )
    db.add(link)
    db.flush()
    return link


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_rwx_project_returns_linked_standard_projects(client):
    """
    An RWX project with one standard project linked should return that project
    in `linked_standard_projects`.
    """
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        rwx = _make_project(db, user.user_id, "My RWX", "RWX1", project_type="rwx")
        std = _make_project(db, user.user_id, "My Standard", "STD1", project_type="standard")
        wf = _make_workflow(db, rwx.project_id)
        _link(db, std.project_id, rwx.project_id, wf.workflow_id)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/My%20RWX", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "linked_standard_projects" in data
    projects = data["linked_standard_projects"]
    assert len(projects) == 1
    assert projects[0]["project_name"] == "My Standard"
    assert projects[0]["project_code"] == "STD1"


def test_rwx_linked_standard_projects_deduplicated_across_multiple_workflows(client):
    """
    When the same standard project links two different workflows from the same RWX
    project, it should appear only once in `linked_standard_projects`.
    """
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        rwx = _make_project(db, user.user_id, "My RWX", "RWX2", project_type="rwx")
        std = _make_project(db, user.user_id, "My Standard", "STD2", project_type="standard")
        wf1 = _make_workflow(db, rwx.project_id, name="reusable-a.yml")
        wf2 = _make_workflow(db, rwx.project_id, name="reusable-b.yml")
        _link(db, std.project_id, rwx.project_id, wf1.workflow_id)
        _link(db, std.project_id, rwx.project_id, wf2.workflow_id)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/My%20RWX", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    projects = data["linked_standard_projects"]
    assert len(projects) == 1, f"Expected 1 (deduplicated), got {len(projects)}"
    assert projects[0]["project_name"] == "My Standard"


def test_rwx_linked_standard_projects_multiple_standard_projects(client):
    """
    Multiple distinct standard projects linking the same RWX project each appear
    once in `linked_standard_projects`.
    """
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        rwx = _make_project(db, user.user_id, "My RWX", "RWX3", project_type="rwx")
        std1 = _make_project(db, user.user_id, "Standard One", "S001", project_type="standard")
        std2 = _make_project(db, user.user_id, "Standard Two", "S002", project_type="standard")
        wf = _make_workflow(db, rwx.project_id)
        _link(db, std1.project_id, rwx.project_id, wf.workflow_id)
        # Need a second workflow to satisfy the unique_standard_workflow constraint
        wf2 = _make_workflow(db, rwx.project_id, name="reusable-b.yml")
        _link(db, std2.project_id, rwx.project_id, wf2.workflow_id)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/My%20RWX", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    projects = data["linked_standard_projects"]
    assert len(projects) == 2
    names = {p["project_name"] for p in projects}
    assert names == {"Standard One", "Standard Two"}


def test_rwx_linked_standard_projects_scoped_to_owner(client):
    """
    Stray links to standard projects belonging to a different user must NOT
    appear in `linked_standard_projects` (security / cross-account isolation).
    """
    db = TestingSessionLocal()
    try:
        owner = _make_user(db, "owner", "owner@example.com")
        other = _make_user(db, "other", "other@example.com")

        rwx = _make_project(db, owner.user_id, "Owner RWX", "ORWX", project_type="rwx")
        # Standard project owned by a different user
        other_std = _make_project(db, other.user_id, "Other Standard", "OSTD", project_type="standard")

        wf = _make_workflow(db, rwx.project_id)
        # Simulate a stray link: other user's standard project links owner's RWX project
        _link(db, other_std.project_id, rwx.project_id, wf.workflow_id)
        db.commit()
    finally:
        db.close()

    # Owner fetches their RWX project
    resp = client.get("/api/projects/Owner%20RWX", params={"github_user": "owner"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    projects = data["linked_standard_projects"]
    assert len(projects) == 0, (
        "Cross-account standard projects must not appear in linked_standard_projects"
    )


def test_rwx_project_empty_linked_standard_projects_when_no_links(client):
    """An RWX project with no linked standard projects returns an empty list."""
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        _make_project(db, user.user_id, "Lonely RWX", "LRW1", project_type="rwx")
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/Lonely%20RWX", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "linked_standard_projects" in data
    assert data["linked_standard_projects"] == []


def test_standard_project_returns_empty_linked_standard_projects(client):
    """Standard projects always return an empty `linked_standard_projects` list."""
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        _make_project(db, user.user_id, "Std Project", "STD9", project_type="standard")
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/Std%20Project", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "linked_standard_projects" in data
    assert data["linked_standard_projects"] == []
