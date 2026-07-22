"""
Tests for the unlink reusable workflow endpoint.

Verifies that DELETE /api/projects/{project_name}/linked-reusable-workflows/{workflow_id}
removes only the LinkedReusableWorkflow association row without deleting the
source Workflow, ProjectWorkflow, or RWX project.

Endpoint under test:
    DELETE /api/projects/{project_name}/linked-reusable-workflows/{workflow_id}
"""
import os
import sys

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (  # noqa: E402
    Base,
    Account,
    Project,
    Workflow,
    ProjectWorkflow,
    LinkedReusableWorkflow,
    WorkspaceMember,
    ProjectMembership,
)
from main import app  # noqa: E402
from projects import get_db as projects_get_db  # noqa: E402


SQLALCHEMY_DATABASE_URL = "sqlite:///./test_unlink_rwx_workflow.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
def client():
    app.dependency_overrides[projects_get_db] = override_get_db
    with patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.pop(projects_get_db, None)


def _seed(db, *, owner="alice"):
    """Create owner + standard project + RWX project + one linked reusable workflow."""
    user = Account(github_user=owner, github_email=f"{owner}@example.com",
                   account_type="pro")
    db.add(user)
    db.flush()

    rwx = Project(
        project_name="SharedRWX",
        project_code="RWX1",
        user_id=user.user_id,
        project_type="rwx",
        use_prefix=True,
    )
    std = Project(
        project_name="CallerProject",
        project_code="STD1",
        user_id=user.user_id,
        project_type="standard",
        use_prefix=False,
    )
    db.add_all([rwx, std])
    db.flush()

    wf = Workflow(
        workflow_name="shared-deploy",
        workflow_yaml="name: Deploy\non:\n  workflow_call: {}\n",
        reusable_workflow=True,
        workflow_status="synced",
        workflow_git_hash="a" * 40,
    )
    db.add(wf)
    db.flush()
    db.add(ProjectWorkflow(project_id=rwx.project_id, workflow_id=wf.workflow_id))
    db.add(LinkedReusableWorkflow(
        standard_project_id=std.project_id,
        rwx_project_id=rwx.project_id,
        workflow_id=wf.workflow_id,
    ))
    db.commit()
    db.refresh(wf)
    db.refresh(std)
    db.refresh(rwx)
    return user, std, rwx, wf


def test_unlink_removes_association_only(client):
    """Unlinking removes the LinkedReusableWorkflow row but keeps the Workflow and ProjectWorkflow."""
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)
        workflow_id = wf.workflow_id
    finally:
        db.close()

    resp = client.delete(
        f"/api/projects/{std.project_name}/linked-reusable-workflows/{workflow_id}",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "unlinked" in data["message"].lower() or "✅" in data["message"]

    # Verify the link is gone
    db = TestingSessionLocal()
    try:
        link = db.query(LinkedReusableWorkflow).filter(
            LinkedReusableWorkflow.standard_project_id == std.project_id,
            LinkedReusableWorkflow.workflow_id == workflow_id,
        ).first()
        assert link is None, "LinkedReusableWorkflow row should be deleted"

        # Verify the source workflow still exists
        source_wf = db.query(Workflow).filter(Workflow.workflow_id == workflow_id).first()
        assert source_wf is not None, "Source Workflow must not be deleted"
        assert source_wf.workflow_name == "shared-deploy"
        assert source_wf.workflow_status == "synced"

        # Verify the ProjectWorkflow association in the RWX project still exists
        pw = db.query(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == rwx.project_id,
            ProjectWorkflow.workflow_id == workflow_id,
        ).first()
        assert pw is not None, "ProjectWorkflow in RWX project must not be deleted"
    finally:
        db.close()


def test_unlink_nonexistent_link_returns_404(client):
    """Attempting to unlink a workflow that is not linked returns 404."""
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)
    finally:
        db.close()

    # Use a workflow_id that doesn't exist
    resp = client.delete(
        f"/api/projects/{std.project_name}/linked-reusable-workflows/99999",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 404


def test_unlink_nonexistent_project_returns_404(client):
    """Attempting to unlink from a non-existent project returns 404."""
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)
        workflow_id = wf.workflow_id
    finally:
        db.close()

    resp = client.delete(
        f"/api/projects/NonExistentProject/linked-reusable-workflows/{workflow_id}",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 404


def test_unlink_unauthorized_user_cannot_unlink(client):
    """A user without access to the project cannot unlink workflows."""
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)
        workflow_id = wf.workflow_id
        project_name = std.project_name

        # Create another user with no project access
        other = Account(github_user="bob", github_email="bob@example.com",
                        account_type="pro")
        db.add(other)
        db.commit()
    finally:
        db.close()

    resp = client.delete(
        f"/api/projects/{project_name}/linked-reusable-workflows/{workflow_id}",
        params={"github_user": "bob"},
    )
    assert resp.status_code == 404, "User without access should get 404 (project not found)"


def test_unlink_does_not_affect_other_projects_link(client):
    """Unlinking from one project does not affect the same workflow linked in another project."""
    db = TestingSessionLocal()
    try:
        user, std, rwx, wf = _seed(db)
        workflow_id = wf.workflow_id
        std_name = std.project_name

        # Create a second standard project that also links the same workflow
        std2 = Project(
            project_name="SecondCaller",
            project_code="STD2",
            user_id=user.user_id,
            project_type="standard",
            use_prefix=False,
        )
        db.add(std2)
        db.flush()
        db.add(LinkedReusableWorkflow(
            standard_project_id=std2.project_id,
            rwx_project_id=rwx.project_id,
            workflow_id=wf.workflow_id,
        ))
        db.commit()
        std2_id = std2.project_id
    finally:
        db.close()

    # Unlink from the first project
    resp = client.delete(
        f"/api/projects/{std_name}/linked-reusable-workflows/{workflow_id}",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 200

    # Verify the link in the second project is still intact
    db = TestingSessionLocal()
    try:
        link = db.query(LinkedReusableWorkflow).filter(
            LinkedReusableWorkflow.standard_project_id == std2_id,
            LinkedReusableWorkflow.workflow_id == workflow_id,
        ).first()
        assert link is not None, "Link in second project should remain"
    finally:
        db.close()
