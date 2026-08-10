"""
Tests for drift notification event emission (issue #1793, part of #1789).

Unit-tests the diff/emit functions directly: feed old-state -> new-state
pairs and assert which events fire, plus the dedup-key behavior the
acceptance criteria hinge on (repeated unchanged scans don't re-emit).
"""

import sys
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, Workflow, Repo, NotificationEvent, WorkflowDriftState
from workflows import WorkflowDriftDetail
from drift_notifications import record_drift_transitions, record_drift_check_failed


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


def _setup_project(db):
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

    repo = Repo(repo_name="acme/widgets")
    db.add(repo)
    db.commit()
    db.refresh(repo)

    return project, workflow, repo


def _detail(workflow, repo, project, has_drift, message="content differs", github_sha="sha-a", local_sha="sha-b"):
    return WorkflowDriftDetail(
        workflow_id=workflow.workflow_id,
        workflow_name=workflow.workflow_name,
        workflow_filename="AM_DFT_ci.yml",
        repo=repo.repo_name,
        branch="main",
        has_drift=has_drift,
        actionsmanager_sha=local_sha,
        github_sha=github_sha,
        last_checked="2026-01-01T00:00:00Z",
        message=message,
        project_id=project.project_id,
        repo_id=repo.repo_id,
    )


class TestRecordDriftTransitions:
    def test_first_scan_with_drift_emits_detected_event(self, db_session):
        project, workflow, repo = _setup_project(db_session)
        detail = _detail(workflow, repo, project, has_drift=True)

        record_drift_transitions(db_session, project, [detail])

        events = db_session.query(NotificationEvent).all()
        assert len(events) == 1
        assert events[0].event_type == "drift.detected"

        state = db_session.query(WorkflowDriftState).one()
        assert state.has_drift is True

    def test_first_scan_without_drift_emits_nothing(self, db_session):
        project, workflow, repo = _setup_project(db_session)
        detail = _detail(workflow, repo, project, has_drift=False)

        record_drift_transitions(db_session, project, [detail])

        assert db_session.query(NotificationEvent).count() == 0
        state = db_session.query(WorkflowDriftState).one()
        assert state.has_drift is False

    def test_repeated_unchanged_drift_does_not_reemit(self, db_session):
        project, workflow, repo = _setup_project(db_session)
        detail = _detail(workflow, repo, project, has_drift=True)

        record_drift_transitions(db_session, project, [detail])
        record_drift_transitions(db_session, project, [detail])
        record_drift_transitions(db_session, project, [detail])

        assert db_session.query(NotificationEvent).count() == 1

    def test_resolution_after_drift_emits_resolved_event(self, db_session):
        project, workflow, repo = _setup_project(db_session)
        drifted = _detail(workflow, repo, project, has_drift=True)
        resolved = _detail(workflow, repo, project, has_drift=False)

        record_drift_transitions(db_session, project, [drifted])
        record_drift_transitions(db_session, project, [resolved])

        events = db_session.query(NotificationEvent).order_by(NotificationEvent.event_id).all()
        assert [e.event_type for e in events] == ["drift.detected", "drift.resolved"]

    def test_redrift_after_resolution_emits_new_detected_event(self, db_session):
        project, workflow, repo = _setup_project(db_session)
        drifted = _detail(workflow, repo, project, has_drift=True)
        resolved = _detail(workflow, repo, project, has_drift=False)

        record_drift_transitions(db_session, project, [drifted])
        record_drift_transitions(db_session, project, [resolved])
        record_drift_transitions(db_session, project, [drifted])

        events = db_session.query(NotificationEvent).order_by(NotificationEvent.event_id).all()
        assert [e.event_type for e in events] == ["drift.detected", "drift.resolved", "drift.detected"]
        # Different dedup keys (different content_hash context) — not deduped away
        assert events[0].dedup_key != events[2].dedup_key

    def test_details_without_repo_id_are_skipped(self, db_session):
        project, workflow, repo = _setup_project(db_session)
        detail = _detail(workflow, repo, project, has_drift=True)
        detail.repo_id = None

        record_drift_transitions(db_session, project, [detail])

        assert db_session.query(NotificationEvent).count() == 0
        assert db_session.query(WorkflowDriftState).count() == 0


class TestRecordDriftCheckFailed:
    def test_check_failed_emits_event(self, db_session):
        project, _, _ = _setup_project(db_session)

        record_drift_check_failed(db_session, project, "GitHub API rate limit exceeded")

        events = db_session.query(NotificationEvent).all()
        assert len(events) == 1
        assert events[0].event_type == "drift.check_failed"

    def test_repeated_identical_failure_does_not_reemit(self, db_session):
        project, _, _ = _setup_project(db_session)

        record_drift_check_failed(db_session, project, "GitHub API rate limit exceeded")
        record_drift_check_failed(db_session, project, "GitHub API rate limit exceeded")

        assert db_session.query(NotificationEvent).count() == 1

    def test_different_failure_reason_emits_new_event(self, db_session):
        project, _, _ = _setup_project(db_session)

        record_drift_check_failed(db_session, project, "GitHub API rate limit exceeded")
        record_drift_check_failed(db_session, project, "Permission denied")

        assert db_session.query(NotificationEvent).count() == 2
