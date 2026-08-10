"""
Drift checks must never report a state they could not verify.

Three false states are covered:

  * A GitHub listing failure (revoked token, rate limit, 5xx) used to collapse
    to an empty result, which is indistinguishable from "this repo has no
    workflow files" — so every workflow in the repo was reported as deleted.
  * A failed check returned has_drift=False, which the persistence layer
    recorded as clean and notified as drift.resolved, silently clearing genuine
    drift.
  * Closing a fix PR without merging reverts the workflow to
    "committed_locally", which was treated as an intentional local edit and
    suppressed drift indefinitely while GitHub still differed.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, Repo, Workflow  # noqa: E402
from workflows import (  # noqa: E402
    DriftCheckUnavailable,
    _check_regular_workflow_in_repo,
    _drift_for_content_mismatch,
    _prefetch_workflow_shas_per_repo,
    get_all_workflow_shas,
)
from drift_notifications import record_drift_transitions  # noqa: E402
from models import WorkflowDriftState, NotificationEvent  # noqa: E402


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _workflow(db, *, git_hash="abc123", status="synced_with_github"):
    wf = Workflow(
        workflow_name="ci",
        workflow_yaml="name: CI\non: push\n",
        workflow_git_hash=git_hash,
        reusable_workflow=False,
        workflow_status=status,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


class TestListingFailureIsNotAbsence:
    @pytest.mark.parametrize("status_code", [401, 403, 429, 500, 502, 503])
    def test_api_failure_raises_instead_of_reporting_no_workflows(self, status_code):
        # These used to return {} — the same value as "repo has no workflows" —
        # which made every workflow in the repo look deleted from GitHub.
        with patch("workflows.requests.get") as get:
            get.return_value = MagicMock(status_code=status_code)
            with pytest.raises(DriftCheckUnavailable):
                get_all_workflow_shas("acme", "widgets", "main", "token")

    def test_genuine_404_still_means_no_workflows(self):
        # A missing .github/workflows directory is a real, knowable answer.
        with patch("workflows.requests.get") as get:
            get.return_value = MagicMock(status_code=404)
            assert get_all_workflow_shas("acme", "widgets", "main", "token") == {}

    def test_prefetch_reports_unknown_rather_than_empty(self):
        with patch("workflows.get_default_branch", return_value="main"), \
             patch("workflows.get_all_workflow_shas",
                   side_effect=DriftCheckUnavailable("rate limited")):
            cache = _prefetch_workflow_shas_per_repo(["acme/widgets"], "token")

        # None, not {} — the distinction the whole fix rests on.
        # Keyed by (repo, branch): drift is checked per target branch.
        assert cache[("acme/widgets", "main")] is None

    def test_branch_resolution_failure_is_unknown_not_empty(self):
        """If we can't even work out which branch to check, that's unknown too —
        not a silent fallback to whatever branch happens to be the default."""
        with patch("workflows.get_default_branch",
                   side_effect=DriftCheckUnavailable("token revoked")):
            cache = _prefetch_workflow_shas_per_repo(["acme/widgets"], "token")

        assert list(cache.values()) == [None]

    def test_unknown_listing_yields_check_failed_not_deleted(self, db_session):
        wf = _workflow(db_session)

        status = _check_regular_workflow_in_repo(
            db_session, wf, "acme/widgets", "acme", "widgets", "ci.yml",
            None, "P001", "token", project_id=None,
        )

        assert status.check_failed is True
        assert status.has_drift is False
        assert "deleted" not in status.message.lower()


class TestUnknownStateIsNeverPersisted:
    def _detail(self, *, has_drift, check_failed, workflow_id=1, repo_id=1, branch="main"):
        detail = MagicMock()
        detail.repo_id = repo_id
        detail.workflow_id = workflow_id
        detail.has_drift = has_drift
        detail.check_failed = check_failed
        detail.repo = "acme/widgets"
        # Explicit: drift state is keyed by branch, and a bare MagicMock would
        # hand SQLAlchemy a Mock instead of the string the real detail carries.
        detail.branch = branch
        detail.workflow_name = "ci"
        detail.message = "msg"
        detail.github_sha = "sha-b"
        detail.actionsmanager_sha = "sha-a"
        return detail

    def _project(self, db):
        """Project plus the workflow/repo rows the drift state references.

        Foreign keys are enforced now, so the referenced rows must actually
        exist rather than being invented ids.
        """
        acct = Account(github_user="u", github_email="u@x.com", account_type="free")
        db.add(acct); db.commit(); db.refresh(acct)
        project = Project(project_name="p", project_code="P001", user_id=acct.user_id)
        db.add(project); db.commit(); db.refresh(project)
        wf = _workflow(db)
        repo = Repo(repo_name="acme/widgets")
        db.add(repo); db.commit(); db.refresh(repo)
        self._ids = (wf.workflow_id, repo.repo_id)
        return project

    def test_failed_check_does_not_clear_known_drift(self, db_session):
        project = self._project(db_session)

        # A real check finds drift...
        record_drift_transitions(db_session, project, [self._detail(has_drift=True, check_failed=False, workflow_id=self._ids[0], repo_id=self._ids[1])])
        assert db_session.query(WorkflowDriftState).one().has_drift is True

        # ...then the next check fails. The drift must survive.
        record_drift_transitions(db_session, project, [self._detail(has_drift=False, check_failed=True, workflow_id=self._ids[0], repo_id=self._ids[1])])

        assert db_session.query(WorkflowDriftState).one().has_drift is True

    def test_failed_check_does_not_emit_drift_resolved(self, db_session):
        project = self._project(db_session)
        record_drift_transitions(db_session, project, [self._detail(has_drift=True, check_failed=False, workflow_id=self._ids[0], repo_id=self._ids[1])])
        before = [e.event_type for e in db_session.query(NotificationEvent).all()]

        record_drift_transitions(db_session, project, [self._detail(has_drift=False, check_failed=True, workflow_id=self._ids[0], repo_id=self._ids[1])])

        after = [e.event_type for e in db_session.query(NotificationEvent).all()]
        assert after == before
        assert "drift.resolved" not in after

    def test_a_real_clean_check_still_resolves(self, db_session):
        # The guard must not block genuine resolution.
        project = self._project(db_session)
        record_drift_transitions(db_session, project, [self._detail(has_drift=True, check_failed=False, workflow_id=self._ids[0], repo_id=self._ids[1])])

        record_drift_transitions(db_session, project, [self._detail(has_drift=False, check_failed=False, workflow_id=self._ids[0], repo_id=self._ids[1])])

        assert db_session.query(WorkflowDriftState).one().has_drift is False
        assert "drift.resolved" in [e.event_type for e in db_session.query(NotificationEvent).all()]


class TestClosedPullRequestDoesNotSuppressDrift:
    def test_rejected_fix_pr_still_reports_drift(self, db_session):
        # Closing a fix PR reverts workflow_status to committed_locally but
        # leaves the real GitHub SHA — GitHub still differs, so this is drift.
        wf = _workflow(db_session, git_hash="real-sha", status="committed_locally")

        status = _drift_for_content_mismatch(
            wf, "name: CI\n# edited in github\n", "sha-b", "acme/widgets", "workflow",
            db_session, None, "name: ci\n", "name: ci\n# edited in github\n",
        )

        assert status.has_drift is True
        assert "modified locally" not in status.message

    def test_genuine_local_edit_is_still_not_drift(self, db_session):
        # A real "Commit Locally" zeroes the hash; that must stay suppressed.
        wf = _workflow(db_session, git_hash="0" * 40, status="committed_locally")

        status = _drift_for_content_mismatch(
            wf, "name: CI\n# github\n", "sha-b", "acme/widgets", "workflow",
            db_session, None, "name: ci\n", "name: ci\n# github\n",
        )

        assert status.has_drift is False
        assert "modified locally" in status.message


class TestDeletedInGithubIsTyped:
    """"Deleted" used to be signalled only by free text in the message, so
    consumers could not tell it from an empty file — the UI rendered a blank
    diff pane and offered to adopt content that does not exist."""

    def test_missing_file_is_flagged_as_deleted(self, db_session):
        from workflows import _drift_for_missing_workflow

        wf = _workflow(db_session, git_hash="real-sha")
        status = _drift_for_missing_workflow(wf, "acme/widgets", "workflow", db_session, None)

        assert status.has_drift is True
        assert status.deleted_in_github is True
        assert status.github_content is None

    def test_a_normal_drift_is_not_flagged_as_deleted(self, db_session):
        from workflows import _drift_for_content_mismatch

        wf = _workflow(db_session, git_hash="real-sha")
        status = _drift_for_content_mismatch(
            wf, "name: CI\n# edited\n", "sha-b", "acme/widgets", "workflow",
            db_session, None, "name: ci\n", "name: ci\n# edited\n",
        )

        assert status.has_drift is True
        assert status.deleted_in_github is False

    def test_an_unchecked_repo_is_not_reported_as_deleted(self, db_session):
        # The failure mode from the previous PR, re-asserted against the new
        # field: unknown must never masquerade as deleted.
        wf = _workflow(db_session)
        status = _check_regular_workflow_in_repo(
            db_session, wf, "acme/widgets", "acme", "widgets", "ci.yml",
            None, "P001", "token", project_id=None,
        )

        assert status.check_failed is True
        assert status.deleted_in_github is False
