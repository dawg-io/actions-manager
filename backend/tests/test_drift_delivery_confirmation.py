"""A workflow is only "deleted" from a branch a check actually saw it on.

Drift inferred that history from ``workflow_git_hash`` being non-zero. A PR
campaign sets that to the blob SHA on the *PR branch*, so a brand-new workflow
carried a real hash while having never landed — and opening a campaign reported
every repo in the project as "Workflow was deleted from ..." (issue #1981).

``confirmed_present_at`` records the fact directly. These tests pin both
directions: no delivery history means never deleted, and real delivery history
still means deleted.
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app  # noqa: E402
from workflows import get_db as real_get_db  # noqa: E402
from models import (  # noqa: E402
    Base, Account, Project, Repo, ProjectRepo, Workflow, ProjectWorkflow,
    WorkflowDriftState, RepoWorkflowOverride,
)
from auth import user_tokens  # noqa: E402

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

REPOS = ("whatsupdawg/test1", "whatsupdawg/test2")
# What a campaign writes after committing the workflow to its PR branch: real,
# non-zero, and no evidence at all about the target branch.
PR_BRANCH_SHA = "pr-branch-blob-sha-abc123"


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture
def make_project(authenticate_client):
    """Build a project on demand, choosing prefix mode, status and drift history."""
    prev_override = app.dependency_overrides.get(real_get_db)
    app.dependency_overrides[real_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)

    def _make(*, use_prefix=False, workflow_status="under_review",
              git_hash=PR_BRANCH_SHA, confirmed_on=(), prior_deleted=(),
              extra_repos=(), override_on=None):
        db = TestingSessionLocal()
        try:
            user = Account(github_user="alice", github_email="a@example.com",
                           account_type="free")
            db.add(user); db.commit(); db.refresh(user)

            project = Project(
                project_name="proj", project_code="P001", user_id=user.user_id,
                branch_option="default", use_prefix=use_prefix,
            )
            db.add(project); db.commit(); db.refresh(project)

            repo_ids = {}
            for repo_name in REPOS:
                repo = Repo(repo_name=repo_name)
                db.add(repo); db.commit(); db.refresh(repo)
                db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
                repo_ids[repo_name] = repo.repo_id
            # Repos that exist but are NOT attached to this project.
            for repo_name in extra_repos:
                repo = Repo(repo_name=repo_name)
                db.add(repo); db.commit(); db.refresh(repo)
                repo_ids[repo_name] = repo.repo_id
            db.commit()

            workflow = Workflow(
                workflow_name="build-stuff",
                workflow_yaml="name: build-stuff\non:\n  workflow_dispatch:\n",
                workflow_git_hash=git_hash,
                reusable_workflow=False,
                workflow_status=workflow_status,
            )
            db.add(workflow); db.commit(); db.refresh(workflow)
            db.add(ProjectWorkflow(project_id=project.project_id,
                                   workflow_id=workflow.workflow_id))

            seen_at = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
            for repo_name in confirmed_on:
                db.add(WorkflowDriftState(
                    project_id=project.project_id, workflow_id=workflow.workflow_id,
                    repo_id=repo_ids[repo_name], branch="main",
                    has_drift=False, github_sha="sha-seen-on-main",
                    confirmed_present_at=seen_at,
                ))
            for repo_name in prior_deleted:
                db.add(WorkflowDriftState(
                    project_id=project.project_id, workflow_id=workflow.workflow_id,
                    repo_id=repo_ids[repo_name], branch="main",
                    has_drift=True, github_sha=None, deleted_in_github=True,
                    confirmed_present_at=seen_at,
                ))
            if override_on:
                db.add(RepoWorkflowOverride(
                    project_id=project.project_id, workflow_id=workflow.workflow_id,
                    repo_id=repo_ids[override_on],
                    workflow_name="build-stuff",
                    workflow_yaml="name: build-stuff\non:\n  push:\n",
                    workflow_git_hash="override-pr-branch-sha",
                ))
            db.commit()

            user_tokens["alice"] = "test-token"
            authenticate_client(client, "alice", TestingSessionLocal)
            return project.project_id
        finally:
            db.close()

    try:
        yield _make
    finally:
        Base.metadata.drop_all(bind=engine)
        if prev_override:
            app.dependency_overrides[real_get_db] = prev_override
        else:
            app.dependency_overrides.pop(real_get_db, None)
        user_tokens.clear()


@pytest.fixture
def no_files_on_github():
    """Neither repo has any workflow file on the target branch."""
    with patch("workflows.fetch_workflow_tree",
               side_effect=lambda o, r, b, t, etag=None: ({}, None)), \
         patch("workflows.get_default_branch",
               side_effect=lambda o, r, h, user=None, db=None: "main"):
        yield


def _drift(project_id, refresh=True):
    resp = client.get(
        f"/api/projects/{project_id}/drift",
        params={"github_user": "alice", "refresh": refresh},
    )
    assert resp.status_code == 200
    return resp.json()


def _deleted(payload):
    return [w for w in payload.get("drifted_workflows", []) if w.get("deleted_in_github")]


@pytest.mark.parametrize("use_prefix", [False, True], ids=["no-prefix", "prefix"])
def test_open_campaign_is_not_a_deletion(make_project, no_files_on_github, use_prefix):
    """The reported bug: opening a campaign marked every repo deleted.

    Both naming modes, because the PR-branch hash has nothing to do with the
    prefix — the report happened to come from a no-prefix project, and a fix
    that only held for one mode would be a coincidence.
    """
    project_id = make_project(use_prefix=use_prefix)

    data = _drift(project_id)

    assert data["drift_count"] == 0
    assert _deleted(data) == []


def test_not_a_deletion_even_with_no_open_pr(make_project, no_files_on_github):
    """No open PR either — still not a deletion, because it was never there.

    The old check only avoided the false verdict when it could find a matching
    open PR row, so anything that broke that lookup — a campaign row written
    after the hash, a repo name that did not match — turned a pending file into
    a deletion. Delivery history does not depend on that lookup.
    """
    project_id = make_project(workflow_status="new")

    assert _deleted(_drift(project_id)) == []


def test_synced_status_alone_does_not_make_it_a_deletion(make_project, no_files_on_github):
    """Status is per-workflow, so it cannot answer a per-(repo, branch) question.

    A workflow synced to one repo and newly added to another is synced_with_github
    for both. Treating that as delivery history would report the new repo as a
    deletion — the same false positive, reintroduced.
    """
    project_id = make_project(workflow_status="synced_with_github")

    assert _deleted(_drift(project_id)) == []


def test_confirmed_delivery_then_missing_is_a_deletion(make_project, no_files_on_github):
    """The behaviour that must survive: a file we really saw, now gone."""
    project_id = make_project(confirmed_on=[REPOS[0]])

    deleted = _deleted(_drift(project_id))

    assert [w["repo"] for w in deleted] == [REPOS[0]]
    assert deleted[0]["branch"] == "main"


def test_deletion_keeps_reporting_on_later_checks(make_project, no_files_on_github):
    """A deletion must not report once and then heal itself.

    The check that reports it writes github_sha=None; confirmed_present_at is
    never cleared, so the evidence outlives the check.
    """
    project_id = make_project(prior_deleted=[REPOS[0]])

    assert [w["repo"] for w in _deleted(_drift(project_id))] == [REPOS[0]]


def test_repo_outside_the_project_is_left_alone(make_project, no_files_on_github):
    """Where no evidence could have been recorded, absence proves nothing.

    Drift state is only persisted for a project's own repos, so a linked
    reusable workflow's source repo never gets a row. Suppressing there would
    downgrade a real deletion to "not delivered yet".
    """
    project_id = make_project(extra_repos=["someone-else/rwx-source"])
    from workflows import _delivery_confirmed_on_branch

    db = TestingSessionLocal()
    try:
        workflow = db.query(Workflow).first()
        assert _delivery_confirmed_on_branch(
            db, workflow, "someone-else/rwx-source", "main", project_id
        ) is True
        assert _delivery_confirmed_on_branch(
            db, workflow, REPOS[0], "main", project_id
        ) is False
    finally:
        db.close()


def test_a_repo_override_does_not_bypass_the_gate(make_project, no_files_on_github):
    """_WorkflowExpectedView hardcodes workflow_status='synced_with_github'.

    Any gate reading that status is a no-op for every (project, repo) carrying
    an override. This one reads delivery history instead, so the override row is
    judged the same as any other.
    """
    project_id = make_project(override_on=REPOS[0])

    assert _deleted(_drift(project_id)) == []


def test_the_cached_panel_stops_claiming_a_deletion(make_project, no_files_on_github):
    """The reason this returns a non-drift status instead of None.

    The panel renders from persisted state, so a row an earlier check wrote has
    to be taken back. Returning None would leave the detail out of
    record_drift_transitions entirely and strand the row forever — and no test
    caught that, because the refresh=true response is empty either way.
    """
    project_id = make_project(workflow_status="under_review")

    db = TestingSessionLocal()
    try:
        workflow = db.query(Workflow).first()
        repo = db.query(Repo).filter(Repo.repo_name == REPOS[0]).first()
        db.add(WorkflowDriftState(
            project_id=project_id, workflow_id=workflow.workflow_id,
            repo_id=repo.repo_id, branch="main",
            has_drift=True, github_sha=None, deleted_in_github=True,
            confirmed_present_at=None,
        ))
        db.commit()
    finally:
        db.close()

    _drift(project_id, refresh=True)

    cached = _drift(project_id, refresh=False)
    assert cached["drift_count"] == 0
    assert _deleted(cached) == []


def test_a_repo_attached_mid_sweep_is_not_a_deletion(make_project, no_files_on_github):
    """The sweep reuses one Session for a whole batch, so its caches must not.

    _delivery_confirmed_on_branch reads "repo not in this project" as "no
    evidence could ever have been recorded here", so a repo attached after the
    set was cached is reported as a deletion — the false positive the gate
    exists to remove.
    """
    project_id = make_project(confirmed_on=[REPOS[0]])
    from workflows import _delivery_confirmed_on_branch, _reset_drift_lookup_caches

    db = TestingSessionLocal()
    try:
        workflow = db.query(Workflow).first()
        _delivery_confirmed_on_branch(db, workflow, REPOS[0], "main", project_id)

        late_repo = Repo(repo_name="acme/attached-later")
        db.add(late_repo); db.commit(); db.refresh(late_repo)
        db.add(ProjectRepo(project_id=project_id, repo_id=late_repo.repo_id))
        db.commit()

        assert _delivery_confirmed_on_branch(
            db, workflow, late_repo.repo_name, "main", project_id
        ) is True

        _reset_drift_lookup_caches(db, project_id)
        assert _delivery_confirmed_on_branch(
            db, workflow, late_repo.repo_name, "main", project_id
        ) is False
    finally:
        db.close()


def test_finding_the_file_stamps_the_confirmation(make_project):
    """The runtime half: seeing the file on a branch is what records delivery."""
    project_id = make_project(workflow_status="under_review")
    content = "name: build-stuff\non:\n  workflow_dispatch:\n"

    with patch("workflows.fetch_workflow_tree",
               side_effect=lambda o, r, b, t, etag=None: ({"build-stuff.yml": "gh-sha-1"}, None)), \
         patch("workflows.get_default_branch",
               side_effect=lambda o, r, h, user=None, db=None: "main"), \
         patch("workflows.get_workflow_from_github",
               side_effect=lambda o, r, f, t, default_branch=None: {"content": content, "sha": "gh-sha-1"}):
        _drift(project_id)

    db = TestingSessionLocal()
    try:
        stamped = (
            db.query(WorkflowDriftState.confirmed_present_at)
            .filter(WorkflowDriftState.confirmed_present_at.isnot(None))
            .all()
        )
        assert stamped, "a check that found the file should record delivery"
    finally:
        db.close()
