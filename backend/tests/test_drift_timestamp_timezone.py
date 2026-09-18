"""
A drift timestamp must say which timezone it is in.

The columns store naive UTC, so ``.isoformat()`` produced "2026-09-15T22:46:10"
with no designator and the browser's ``new Date()`` read that as *local* time.
The live-check response built its timestamp from an aware ``datetime.now``, so
clicking "Check Now" showed the right time and reloading the page showed the
same instant shifted by the viewer's UTC offset — which reads as the previous
automatic sweep's check rather than the manual one just triggered.

The check itself was always persisted correctly; only the serialization lost
the offset, so these assert the wire format rather than the stored value.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from workflows import get_db as real_get_db  # noqa: E402
from projects import get_db as projects_get_db  # noqa: E402
from models import (  # noqa: E402
    Base, Account, Project, Repo, ProjectRepo, Workflow, ProjectWorkflow,
    WorkflowDriftState,
)
from auth import user_tokens  # noqa: E402

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture
def state(authenticate_client):
    prev = app.dependency_overrides.get(real_get_db)
    prev_projects = app.dependency_overrides.get(projects_get_db)
    app.dependency_overrides[real_get_db] = _override_get_db
    app.dependency_overrides[projects_get_db] = _override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        user = Account(github_user="alice", github_email="a@e.com", account_type="free")
        db.add(user); db.commit(); db.refresh(user)
        project = Project(project_name="proj", project_code="P001", user_id=user.user_id,
                          use_prefix=False, branch_option="default")
        db.add(project); db.commit(); db.refresh(project)
        repo = Repo(repo_name="acme/api")
        db.add(repo); db.commit(); db.refresh(repo)
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id)); db.commit()
        wf = Workflow(workflow_name="ci", workflow_yaml="name: ci\non: push\n",
                      workflow_git_hash="sha-local", reusable_workflow=False,
                      workflow_status="synced_with_github")
        db.add(wf); db.commit(); db.refresh(wf)
        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id)); db.commit()
        user_tokens["alice"] = "tok"
        authenticate_client(client, "alice", TestingSessionLocal)
        yield {"project_id": project.project_id, "workflow_id": wf.workflow_id,
               "repo_id": repo.repo_id, "db": db}
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        user_tokens.clear()
        for dep, previous in ((real_get_db, prev), (projects_get_db, prev_projects)):
            if previous is None:
                app.dependency_overrides.pop(dep, None)
            else:
                app.dependency_overrides[dep] = previous


def _stored_check_time(state) -> datetime:
    db = state["db"]
    db.expire_all()
    return db.query(Project).filter_by(project_id=state["project_id"]).first().last_drift_check_at


def _parsed(value: str) -> datetime:
    """Parse the way a browser does: an absolute instant, or fail the test."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, f"{value!r} has no timezone — a browser reads it as local time"
    return parsed


@patch("workflows.get_default_branch", return_value="main")
@patch("workflows.fetch_workflow_tree", return_value=({"ci.yml": "sha-local"}, None))
def test_reloading_after_a_manual_check_shows_that_check(_tree, _branch, state):
    """The reported bug: run a check, reload, and read the banner's timestamp."""
    live = client.get(f"/api/projects/{state['project_id']}/drift",
                      params={"github_user": "alice", "refresh": True})
    assert live.status_code == 200, live.text

    reloaded = client.get(f"/api/projects/{state['project_id']}/drift",
                          params={"github_user": "alice"})
    assert reloaded.status_code == 200, reloaded.text

    shown = _parsed(reloaded.json()["last_checked"])
    assert shown == _stored_check_time(state).replace(tzinfo=timezone.utc)
    # The instant the banner renders must be the manual check, not an offset
    # away from it — under the bug these differed by the viewer's UTC offset.
    assert abs((shown - _parsed(live.json()["last_checked"])).total_seconds()) < 5


def test_stored_drift_row_timestamp_carries_utc(state):
    checked_at = datetime(2026, 9, 15, 22, 46, 10, tzinfo=timezone.utc)
    db = state["db"]
    db.add(WorkflowDriftState(
        project_id=state["project_id"], workflow_id=state["workflow_id"],
        repo_id=state["repo_id"], branch="main", has_drift=True,
        content_hash="h", drift_cycle_count=1, github_sha="sha-remote",
        last_checked_at=checked_at,
    ))
    db.commit()

    resp = client.get(f"/api/projects/{state['project_id']}/drift",
                      params={"github_user": "alice"})
    assert resp.status_code == 200, resp.text
    assert _parsed(resp.json()["drifted_workflows"][0]["last_checked"]) == checked_at


@patch("workflows.get_default_branch", return_value="main")
@patch("workflows.fetch_workflow_tree", return_value=({"ci.yml": "sha-local"}, None))
def test_project_list_drift_timestamp_carries_utc(_tree, _branch, state):
    """The list card's "Drift checked …" reads the same column as the banner."""
    client.get(f"/api/projects/{state['project_id']}/drift",
               params={"github_user": "alice", "refresh": True})

    resp = client.get("/api/projects/", params={"github_user": "alice"})
    assert resp.status_code == 200, resp.text
    listed = next(p for p in resp.json() if p["project_id"] == state["project_id"])
    assert _parsed(listed["last_drift_check_at"]) == _stored_check_time(state).replace(tzinfo=timezone.utc)
