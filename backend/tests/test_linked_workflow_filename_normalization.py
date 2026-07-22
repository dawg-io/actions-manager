"""
Tests for linked reusable workflow filename normalization.

Verifies that when a standard project fetches its linked reusable workflows,
the returned ``workflow_name`` reflects the **source RWX project's** naming
mode and not the consuming standard project's mode.

Scenarios covered:
1. Prefix-Mode RWX → No-Prefix-Mode consumer: prefix must be preserved.
2. No-Prefix-Mode RWX → Prefix-Mode consumer: no prefix must be added.
3. Prefix-Mode RWX → Prefix-Mode consumer: prefix is still from source.
4. No-Prefix-Mode RWX → No-Prefix-Mode consumer: stays unprefixed.
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

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_linked_wf_filename.db"
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


def _make_project(db, user_id, name, code, project_type="standard", use_prefix=True):
    project = Project(
        project_name=name,
        project_code=code,
        user_id=user_id,
        project_type=project_type,
        branch_option="default",
        use_prefix=use_prefix,
    )
    db.add(project)
    db.flush()
    return project


def _make_reusable_workflow(db, rwx_project_id, stem):
    """Create a reusable workflow stored as a stem (no .yml extension)."""
    wf = Workflow(
        workflow_name=stem,
        workflow_yaml="on:\n  workflow_call: {}",
        reusable_workflow=True,
    )
    db.add(wf)
    db.flush()
    pw = ProjectWorkflow(project_id=rwx_project_id, workflow_id=wf.workflow_id)
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

def test_prefix_mode_rwx_into_no_prefix_consumer_preserves_prefix(client):
    """
    Scenario 1: Prefix-Mode RWX project → No-Prefix-Mode consumer.

    Source RWX project: use_prefix=True, project_code="RWW1", stem="testrwx"
    Expected linked workflow_name: "AM_RWW1_testrwx.yml"
    Must NOT be normalised to "testrwx.yml" by the consumer's No-Prefix mode.
    """
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        rwx = _make_project(db, user.user_id, "RWX Project", "RWW1",
                            project_type="rwx", use_prefix=True)
        std = _make_project(db, user.user_id, "Standard Project", "STD1",
                            project_type="standard", use_prefix=False)
        wf = _make_reusable_workflow(db, rwx.project_id, "testrwx")
        _link(db, std.project_id, rwx.project_id, wf.workflow_id)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/Standard%20Project", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    linked = data.get("linked_reusable_workflows", [])
    assert len(linked) == 1, f"Expected 1 linked workflow, got {len(linked)}"
    assert linked[0]["workflow_name"] == "AM_RWW1_testrwx.yml", (
        f"Prefix must be preserved from source RWX project; "
        f"got {linked[0]['workflow_name']!r}"
    )


def test_no_prefix_rwx_into_prefix_consumer_does_not_add_prefix(client):
    """
    Scenario 2: No-Prefix-Mode RWX project → Prefix-Mode consumer.

    Source RWX project: use_prefix=False, project_code="RWW2", stem="testrwx"
    Expected linked workflow_name: "testrwx.yml"
    Must NOT become "AM_STD2_testrwx.yml" due to consumer's Prefix mode.
    """
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        rwx = _make_project(db, user.user_id, "RWX No Prefix", "RWW2",
                            project_type="rwx", use_prefix=False)
        std = _make_project(db, user.user_id, "Standard Prefix", "STD2",
                            project_type="standard", use_prefix=True)
        wf = _make_reusable_workflow(db, rwx.project_id, "testrwx")
        _link(db, std.project_id, rwx.project_id, wf.workflow_id)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/Standard%20Prefix", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    linked = data.get("linked_reusable_workflows", [])
    assert len(linked) == 1, f"Expected 1 linked workflow, got {len(linked)}"
    assert linked[0]["workflow_name"] == "testrwx.yml", (
        f"Unprefixed source must remain unprefixed; "
        f"got {linked[0]['workflow_name']!r}"
    )


def test_prefix_mode_rwx_into_prefix_mode_consumer_uses_source_prefix(client):
    """
    Scenario 3: Prefix-Mode RWX → Prefix-Mode consumer.

    Both use prefix, but the consumer has a different project code.
    The linked workflow_name must use the *source* RWX code, not the consumer code.
    """
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        rwx = _make_project(db, user.user_id, "RWX Prefix", "RWX3",
                            project_type="rwx", use_prefix=True)
        std = _make_project(db, user.user_id, "Standard Also Prefix", "STD3",
                            project_type="standard", use_prefix=True)
        wf = _make_reusable_workflow(db, rwx.project_id, "myworkflow")
        _link(db, std.project_id, rwx.project_id, wf.workflow_id)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/Standard%20Also%20Prefix", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    linked = data.get("linked_reusable_workflows", [])
    assert len(linked) == 1
    # Source prefix (RWX3), not consumer prefix (STD3)
    assert linked[0]["workflow_name"] == "AM_RWX3_myworkflow.yml", (
        f"Source RWX prefix must be used; got {linked[0]['workflow_name']!r}"
    )
    assert "STD3" not in linked[0]["workflow_name"], (
        "Consumer project code must NOT appear in linked workflow name"
    )


def test_no_prefix_rwx_into_no_prefix_consumer_stays_unprefixed(client):
    """
    Scenario 4: No-Prefix-Mode RWX → No-Prefix-Mode consumer.

    Both without prefix; linked workflow_name stays plain.
    """
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        rwx = _make_project(db, user.user_id, "RWX No Pfx", "RWX4",
                            project_type="rwx", use_prefix=False)
        std = _make_project(db, user.user_id, "Std No Pfx", "STD4",
                            project_type="standard", use_prefix=False)
        wf = _make_reusable_workflow(db, rwx.project_id, "plain-workflow")
        _link(db, std.project_id, rwx.project_id, wf.workflow_id)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/Std%20No%20Pfx", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    linked = data.get("linked_reusable_workflows", [])
    assert len(linked) == 1
    assert linked[0]["workflow_name"] == "plain-workflow.yml", (
        f"Unprefixed source should remain plain; got {linked[0]['workflow_name']!r}"
    )


def test_already_suffixed_stem_does_not_produce_double_extension(client):
    """
    Regression: if a workflow_name was stored with an extension (legacy data),
    format_workflow_name must not produce a double-extension like '...yml.yml'.

    In Prefix-Mode the stem is stripped before formatting, so the result should
    be 'AM_RWX5_testrwx.yml', not 'AM_RWX5_testrwx.yml.yml'.
    """
    db = TestingSessionLocal()
    try:
        user = _make_user(db)
        rwx = _make_project(db, user.user_id, "RWX Suffixed", "RWX5",
                            project_type="rwx", use_prefix=True)
        std = _make_project(db, user.user_id, "Std Suffixed", "STD5",
                            project_type="standard", use_prefix=False)
        # Simulate legacy row that was written with extension already attached
        wf = Workflow(
            workflow_name="testrwx.yml",
            workflow_yaml="on:\n  workflow_call: {}",
            reusable_workflow=True,
        )
        db.add(wf)
        db.flush()
        pw = ProjectWorkflow(project_id=rwx.project_id, workflow_id=wf.workflow_id)
        db.add(pw)
        db.flush()
        _link(db, std.project_id, rwx.project_id, wf.workflow_id)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/projects/Std%20Suffixed", params={"github_user": "testuser"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    linked = data.get("linked_reusable_workflows", [])
    assert len(linked) == 1
    result_name = linked[0]["workflow_name"]
    assert result_name == "AM_RWX5_testrwx.yml", (
        f"Double extension must not occur; got {result_name!r}"
    )
    assert "yml.yml" not in result_name, f"Double extension detected in {result_name!r}"
