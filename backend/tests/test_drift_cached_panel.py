"""
Opening a project must not cost GitHub API calls.

The drift panel used to run a full live check every time it mounted, so simply
looking at a project repeatedly burned rate limit. The per-(workflow, repo,
branch) state is already persisted, so the list can be served from it and a
live check becomes something the user asks for.

Two things this must not get wrong, both variants of failures already fixed
elsewhere in drift:

  * "never checked" must not render as "verified clean just now" — hence
    last_checked being null rather than the time of the request.
  * a cached row must not claim to have GitHub's content. The diff is fetched
    when opened, because a stored snapshot may no longer match GitHub.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from workflows import get_db as real_get_db  # noqa: E402
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


@pytest.fixture()
def state():
    prev = app.dependency_overrides.get(real_get_db)
    app.dependency_overrides[real_get_db] = _override_get_db
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
        yield {"project_id": project.project_id, "workflow_id": wf.workflow_id,
               "repo_id": repo.repo_id, "db": db, "project": project}
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        user_tokens.clear()
        if prev is None:
            app.dependency_overrides.pop(real_get_db, None)
        else:
            app.dependency_overrides[real_get_db] = prev


def _drifted(state, *, branch="main", github_sha="sha-remote", deleted=False, checked_at=None):
    db = state["db"]
    db.add(WorkflowDriftState(
        project_id=state["project_id"], workflow_id=state["workflow_id"],
        repo_id=state["repo_id"], branch=branch, has_drift=True,
        content_hash="h", drift_cycle_count=1, github_sha=github_sha,
        deleted_in_github=deleted,
        last_checked_at=checked_at or datetime.now(timezone.utc),
    ))
    db.commit()


def _get(project_id, refresh=None):
    params = {"github_user": "alice"}
    if refresh is not None:
        params["refresh"] = refresh
    return client.get(f"/api/projects/{project_id}/drift", params=params)


class TestOpeningAProjectIsFree:
    def test_default_makes_no_github_calls(self, state):
        """The entire point of the change."""
        _drifted(state)

        with patch("workflows.requests.get") as get, \
             patch("workflows.fetch_workflow_tree") as tree:
            resp = _get(state["project_id"])

        assert resp.status_code == 200, resp.text
        assert get.call_count == 0
        assert tree.call_count == 0

    def test_it_still_reports_the_drift(self, state):
        _drifted(state, branch="release/2.1")

        body = _get(state["project_id"]).json()

        assert body["drift_count"] == 1
        row = body["drifted_workflows"][0]
        assert row["repo"] == "acme/api"
        assert row["branch"] == "release/2.1"
        assert row["has_drift"] is True
        assert row["workflow_filename"] == "ci.yml"

    def test_each_branch_is_its_own_row(self, state):
        _drifted(state, branch="release/2.0")
        _drifted(state, branch="release/2.1")

        body = _get(state["project_id"]).json()

        assert body["drift_count"] == 2
        assert {r["branch"] for r in body["drifted_workflows"]} == {"release/2.0", "release/2.1"}

    def test_resolved_rows_are_not_listed(self, state):
        db = state["db"]
        db.add(WorkflowDriftState(
            project_id=state["project_id"], workflow_id=state["workflow_id"],
            repo_id=state["repo_id"], branch="main", has_drift=False,
        ))
        db.commit()

        body = _get(state["project_id"]).json()

        assert body["drift_count"] == 0


class TestFreshnessIsHonest:
    def test_never_checked_reports_null_not_now(self, state):
        """An empty list from a check that never ran must not read as
        'verified clean just now'."""
        body = _get(state["project_id"]).json()

        assert body["drift_count"] == 0
        assert body["last_checked"] is None

    def test_last_checked_is_when_the_state_was_established(self, state):
        earlier = datetime.now(timezone.utc) - timedelta(days=3)
        state["project"].last_drift_check_at = earlier
        state["db"].commit()
        _drifted(state, checked_at=earlier)

        body = _get(state["project_id"]).json()

        # Three days ago, not "now" — that difference is the whole point.
        assert body["last_checked"].startswith(earlier.isoformat()[:16])


class TestCachedRowsDoNotFakeGithubContent:
    def test_github_yaml_is_absent(self, state):
        """A stored snapshot may no longer match GitHub, so the diff is fetched
        when opened rather than replayed."""
        _drifted(state)

        row = _get(state["project_id"]).json()["drifted_workflows"][0]

        assert row["github_yaml"] is None

    def test_the_managed_side_is_present(self, state):
        """It is local, so there is no reason to withhold it."""
        _drifted(state)

        row = _get(state["project_id"]).json()["drifted_workflows"][0]

        assert row["actionsmanager_yaml"] == "name: ci\non: push\n"
        assert row["actionsmanager_sha"] == "sha-local"

    def test_github_sha_survives_for_grouping(self, state):
        _drifted(state, github_sha="sha-remote-1")

        row = _get(state["project_id"]).json()["drifted_workflows"][0]

        assert row["github_sha"] == "sha-remote-1"

    def test_deleted_stays_distinguishable_from_drifted(self, state):
        """Different states, different actions offered — a cached deleted
        workflow must not render as ordinary drift."""
        _drifted(state, deleted=True)

        row = _get(state["project_id"]).json()["drifted_workflows"][0]

        assert row["deleted_in_github"] is True
        assert "deleted" in row["message"].lower()


class TestRefreshStillRunsALiveCheck:
    def test_refresh_true_calls_github(self, state):
        with patch("workflows._collect_project_drift_details", return_value=[]) as collect:
            resp = _get(state["project_id"], refresh="true")

        assert resp.status_code == 200
        assert collect.call_count == 1

    def test_default_does_not_call_the_live_collector(self, state):
        with patch("workflows._collect_project_drift_details", return_value=[]) as collect:
            _get(state["project_id"])

        assert collect.call_count == 0
