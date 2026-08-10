"""
Tests for keeping persisted drift current when actions resolve drift.

Before this, GET /api/projects/{id}/drift was the only code path that wrote
either drift cache, so resolving/adopting/merging left both claiming drift
that was already fixed until someone re-opened the project and triggered a
live check. The project page seeds its banner from those caches, so a stale
cache showed a drift alert for drift that no longer existed.
"""

import sys
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    Base, Account, Project, Workflow, Repo, ProjectWorkflow,
    NotificationEvent, WorkflowDriftState, ProjectPullRequest,
)
from workflows import _clear_drift_for_merged_pr
from drift_notifications import (
    clear_workflow_drift,
    recompute_project_drift_summary,
    drop_workflow_drift,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _setup_project(db, repo_names=("acme/widgets",)):
    account = Account(github_user="driftuser", github_email="drift@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(project_name="drift_project", project_code="DFT", user_id=account.user_id)
    db.add(project)
    db.commit()
    db.refresh(project)

    workflow = Workflow(workflow_name="ci.yml", workflow_yaml="name: ci")
    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=workflow.workflow_id))
    db.commit()

    repos = []
    for name in repo_names:
        repo = Repo(repo_name=name)
        db.add(repo)
        db.commit()
        db.refresh(repo)
        repos.append(repo)

    return project, workflow, repos


def _drifted_state(db, project, workflow, repo, has_drift=True, branch="main"):
    state = WorkflowDriftState(
        project_id=project.project_id,
        workflow_id=workflow.workflow_id,
        repo_id=repo.repo_id,
        # Drift state is per (workflow, repo, branch). Defaults to "main" to
        # match _merged_pr's target_branch, which is how production pairs up.
        branch=branch,
        has_drift=has_drift,
        content_hash="hash-1",
        drift_cycle_count=1,
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


class TestClearWorkflowDrift:
    def test_clears_drift_and_emits_resolved_event(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)

        cleared = clear_workflow_drift(db_session, project, workflow.workflow_id, repo.repo_name)

        assert cleared == 1
        assert db_session.query(WorkflowDriftState).one().has_drift is False
        events = db_session.query(NotificationEvent).all()
        assert [e.event_type for e in events] == ["drift.resolved"]

    def test_updates_the_project_level_summary(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)

        clear_workflow_drift(db_session, project, workflow.workflow_id, repo.repo_name)

        db_session.refresh(project)
        assert project.drift_status == "clean"
        assert project.drift_count == 0

    def test_repo_scope_leaves_other_repos_drifted(self, db_session):
        project, workflow, (repo_a, repo_b) = _setup_project(
            db_session, repo_names=("acme/widgets", "acme/gadgets")
        )
        _drifted_state(db_session, project, workflow, repo_a)
        _drifted_state(db_session, project, workflow, repo_b)

        clear_workflow_drift(db_session, project, workflow.workflow_id, repo_a.repo_name)

        by_repo = {s.repo_id: s.has_drift for s in db_session.query(WorkflowDriftState).all()}
        assert by_repo[repo_a.repo_id] is False
        assert by_repo[repo_b.repo_id] is True

        db_session.refresh(project)
        assert project.drift_status == "drifted"
        assert project.drift_count == 1

    def test_unknown_repo_name_clears_nothing(self, db_session):
        # Guards the dangerous failure mode: silently falling back to clearing
        # every repo would wrongly resolve drift the caller never touched.
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)

        cleared = clear_workflow_drift(db_session, project, workflow.workflow_id, "acme/not-a-repo")

        assert cleared == 0
        assert db_session.query(WorkflowDriftState).one().has_drift is True

    def test_is_idempotent(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)

        clear_workflow_drift(db_session, project, workflow.workflow_id, repo.repo_name)
        second = clear_workflow_drift(db_session, project, workflow.workflow_id, repo.repo_name)

        assert second == 0
        # Re-clearing must not emit a duplicate resolved notification.
        assert db_session.query(NotificationEvent).count() == 1

    def test_omitting_repo_clears_every_repo_for_the_workflow(self, db_session):
        project, workflow, (repo_a, repo_b) = _setup_project(
            db_session, repo_names=("acme/widgets", "acme/gadgets")
        )
        _drifted_state(db_session, project, workflow, repo_a)
        _drifted_state(db_session, project, workflow, repo_b)

        cleared = clear_workflow_drift(db_session, project, workflow.workflow_id)

        assert cleared == 2
        assert all(s.has_drift is False for s in db_session.query(WorkflowDriftState).all())


def _merged_pr(db, project, repo_name, workflow_names):
    pr = ProjectPullRequest(
        project_id=project.project_id,
        repo_name=repo_name,
        pr_number=7,
        pr_url="https://github.com/acme/widgets/pull/7",
        pr_state="merged",
        branch_name="actionsmanager/fix",
        target_branch="main",
        workflow_names=workflow_names,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return pr


class TestClearDriftForMergedPR:
    """The webhook merge path has no UI to trigger a live re-check, so without
    this the caches keep reporting drift the merge already fixed."""

    def test_clears_drift_for_the_workflows_the_pr_carried(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)
        pr = _merged_pr(db_session, project, repo.repo_name, "ci.yml")

        _clear_drift_for_merged_pr(db_session, project, pr)

        assert db_session.query(WorkflowDriftState).one().has_drift is False
        db_session.refresh(project)
        assert project.drift_status == "clean"

    def test_leaves_workflows_not_in_the_pr_drifted(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)

        other_wf = Workflow(workflow_name="release.yml", workflow_yaml="name: release")
        db_session.add(other_wf)
        db_session.commit()
        db_session.refresh(other_wf)
        db_session.add(ProjectWorkflow(
            project_id=project.project_id, workflow_id=other_wf.workflow_id
        ))
        db_session.commit()
        _drifted_state(db_session, project, other_wf, repo)

        pr = _merged_pr(db_session, project, repo.repo_name, "ci.yml")
        _clear_drift_for_merged_pr(db_session, project, pr)

        by_wf = {s.workflow_id: s.has_drift for s in db_session.query(WorkflowDriftState).all()}
        assert by_wf[workflow.workflow_id] is False
        assert by_wf[other_wf.workflow_id] is True

    def test_leaves_other_repos_drifted(self, db_session):
        project, workflow, (repo_a, repo_b) = _setup_project(
            db_session, repo_names=("acme/widgets", "acme/gadgets")
        )
        _drifted_state(db_session, project, workflow, repo_a)
        _drifted_state(db_session, project, workflow, repo_b)

        pr = _merged_pr(db_session, project, repo_a.repo_name, "ci.yml")
        _clear_drift_for_merged_pr(db_session, project, pr)

        by_repo = {s.repo_id: s.has_drift for s in db_session.query(WorkflowDriftState).all()}
        assert by_repo[repo_a.repo_id] is False
        assert by_repo[repo_b.repo_id] is True

    def test_pr_without_recorded_workflows_is_a_no_op(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)
        pr = _merged_pr(db_session, project, repo.repo_name, None)

        _clear_drift_for_merged_pr(db_session, project, pr)

        assert db_session.query(WorkflowDriftState).one().has_drift is True


class TestRecomputeProjectDriftSummary:
    def test_reports_drifted_with_a_count(self, db_session):
        project, workflow, (repo_a, repo_b) = _setup_project(
            db_session, repo_names=("acme/widgets", "acme/gadgets")
        )
        _drifted_state(db_session, project, workflow, repo_a)
        _drifted_state(db_session, project, workflow, repo_b)

        recompute_project_drift_summary(db_session, project)

        db_session.refresh(project)
        assert project.drift_status == "drifted"
        assert project.drift_count == 2
        assert project.last_drift_check_at is not None

    def test_reports_clean_when_nothing_is_drifted(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo, has_drift=False)

        recompute_project_drift_summary(db_session, project)

        db_session.refresh(project)
        assert project.drift_status == "clean"
        assert project.drift_count == 0

    def test_ignores_other_projects_drift(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)

        other = Project(project_name="other", project_code="OTH", user_id=project.user_id)
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        recompute_project_drift_summary(db_session, other)

        db_session.refresh(other)
        assert other.drift_status == "clean"
        assert other.drift_count == 0

    def test_resets_the_sweep_backoff_streak(self, db_session):
        # A real answer ("clean" or "drifted"), same as
        # workflows.py's _cache_project_drift_summary — otherwise a project
        # resolved via the UI stays backed off in the sweep despite the
        # dashboard showing it as clean.
        project, workflow, (repo,) = _setup_project(db_session)
        project.drift_check_failure_count = 5
        db_session.commit()
        _drifted_state(db_session, project, workflow, repo, has_drift=False)

        recompute_project_drift_summary(db_session, project)

        db_session.refresh(project)
        assert project.drift_check_failure_count == 0


class TestDropWorkflowDrift:
    def test_removes_rows_and_recomputes(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)

        drop_workflow_drift(db_session, project, workflow.workflow_id)

        assert db_session.query(WorkflowDriftState).count() == 0
        db_session.refresh(project)
        assert project.drift_status == "clean"
        assert project.drift_count == 0

    def test_only_drops_rows_belonging_to_this_project(self, db_session):
        # WorkflowDriftState is unique per (workflow, repo), so a row recorded
        # under another project must survive - removing a workflow from one
        # project says nothing about drift another project tracks.
        project, workflow, (repo_a, repo_b) = _setup_project(
            db_session, repo_names=("acme/widgets", "acme/gadgets")
        )
        _drifted_state(db_session, project, workflow, repo_a)

        other = Project(project_name="other", project_code="OTH", user_id=project.user_id)
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)
        _drifted_state(db_session, other, workflow, repo_b)

        drop_workflow_drift(db_session, project, workflow.workflow_id)

        remaining = db_session.query(WorkflowDriftState).all()
        assert len(remaining) == 1
        assert remaining[0].project_id == other.project_id

    def test_leaves_other_workflows_in_the_same_project_alone(self, db_session):
        project, workflow, (repo,) = _setup_project(db_session)
        _drifted_state(db_session, project, workflow, repo)

        kept = Workflow(workflow_name="release.yml", workflow_yaml="name: release")
        db_session.add(kept)
        db_session.commit()
        db_session.refresh(kept)
        _drifted_state(db_session, project, kept, repo)

        drop_workflow_drift(db_session, project, workflow.workflow_id)

        remaining = db_session.query(WorkflowDriftState).all()
        assert len(remaining) == 1
        assert remaining[0].workflow_id == kept.workflow_id
        db_session.refresh(project)
        assert project.drift_count == 1
