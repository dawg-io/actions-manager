"""
The sweep is the only thing that checks drift without a human clicking.

Before it, drift state changed on exactly three user-initiated requests, so a
project could show "in sync" indefinitely while GitHub had drifted. These tests
are about *which projects get picked and when* — the drift comparison itself is
covered by the ~170 existing drift tests and is mocked out here.

Two failure modes matter more than the rest, both of which would leave the
sweep silently doing nothing:

  * a project whose owner has no token must not advance its own cursor (that
    would fake a check) *and* must not starve the projects behind it.
  * one project raising must not stop the sweep for everyone else.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project  # noqa: E402
import drift_worker  # noqa: E402
from drift_worker import sweep_projects_for_drift  # noqa: E402

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

STALE = datetime.now(timezone.utc) - timedelta(hours=2)
FRESH = datetime.now(timezone.utc)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _owner(db, name="alice"):
    user = Account(github_user=name, github_email=f"{name}@e.com", account_type="free")
    db.add(user); db.commit(); db.refresh(user)
    return user


def _project(db, owner, code, last_checked=STALE, failure_count=0):
    project = Project(project_name=f"proj-{code}", project_code=code, user_id=owner.user_id,
                      use_prefix=False, branch_option="default",
                      last_drift_check_at=last_checked,
                      drift_check_failure_count=failure_count)
    db.add(project); db.commit(); db.refresh(project)
    return project


def _tokens(mapping):
    """Patch the credential store the worker resolves owners through."""
    return patch("auth.user_tokens.get", side_effect=lambda u, d=None: mapping.get(u, d))


class TestOnlyStaleProjectsAreChecked:
    def test_a_stale_project_is_checked(self, db):
        _project(db, _owner(db), "P1")

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check", return_value=([], [])) as check:
            assert sweep_projects_for_drift(db) == 1

        assert check.call_count == 1

    def test_a_recently_checked_project_is_skipped(self, db):
        _project(db, _owner(db), "P1", last_checked=FRESH)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0

    def test_never_checked_goes_first(self, db):
        owner = _owner(db)
        _project(db, owner, "OLD", last_checked=STALE)
        _project(db, owner, "NEW", last_checked=None)

        seen = []
        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])), \
             patch.dict(os.environ, {"DRIFT_SWEEP_BATCH_SIZE": "1"}):
            sweep_projects_for_drift(db)

        assert seen == ["NEW"]


class TestBatching:
    def test_the_batch_caps_how_many_are_checked(self, db):
        owner = _owner(db)
        for i in range(5):
            _project(db, owner, f"P{i}")

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check", return_value=([], [])) as check, \
             patch.dict(os.environ, {"DRIFT_SWEEP_BATCH_SIZE": "2"}):
            assert sweep_projects_for_drift(db) == 2

        assert check.call_count == 2


class TestAMissingTokenDoesNotBreakTheSweep:
    def test_no_token_means_no_check_and_no_fake_timestamp(self, db):
        """Marking it checked would be the stale-'clean' bug this feature exists
        to prevent."""
        project = _project(db, _owner(db), "P1")

        with _tokens({}), patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0
        db.refresh(project)
        # SQLite drops tzinfo on round-trip, so compare naive to naive.
        assert project.last_drift_check_at.replace(tzinfo=None) == STALE.replace(tzinfo=None)

    def test_the_skip_is_explained_rather_than_silent(self, db):
        """A timestamp that just stops moving reads as a broken feature. The
        reason has to be recorded, without pretending a check happened."""
        project = _project(db, _owner(db), "P1")

        with _tokens({}), patch("workflows.run_project_drift_check"):
            sweep_projects_for_drift(db)

        db.refresh(project)
        assert project.drift_error_summary == drift_worker.NO_CREDENTIAL_REASON
        assert project.last_drift_check_at.replace(tzinfo=None) == STALE.replace(tzinfo=None)

    def test_a_previous_real_result_is_not_overwritten(self, db):
        """A project that genuinely was drifting still is — a skip must not
        downgrade that to 'unknown' and hide a true positive."""
        project = _project(db, _owner(db), "P1")
        project.drift_status = "drifted"
        project.drift_count = 3
        db.commit()

        with _tokens({}), patch("workflows.run_project_drift_check"):
            sweep_projects_for_drift(db)

        db.refresh(project)
        assert project.drift_status == "drifted"
        assert project.drift_count == 3

    def test_the_reason_is_written_once_not_every_tick(self, db):
        _project(db, _owner(db), "P1")

        with _tokens({}), patch("workflows.run_project_drift_check"), \
             patch.object(drift_worker.Session, "commit", autospec=True) as commit:
            sweep_projects_for_drift(db)
            first = commit.call_count
            sweep_projects_for_drift(db)
            assert commit.call_count == first

    def test_a_successful_check_clears_the_reason(self, db):
        """Self-healing: once the owner saves a token the warning must go away
        on its own, not linger and mislead."""
        project = _project(db, _owner(db), "P1")
        project.drift_error_summary = drift_worker.NO_CREDENTIAL_REASON
        db.commit()

        # A real check clears it via _cache_project_drift_summary.
        from workflows import _cache_project_drift_summary
        _cache_project_drift_summary(db, project, "clean", 0, None)

        db.refresh(project)
        assert project.drift_error_summary is None

    def test_a_tokenless_project_does_not_starve_the_others(self, db):
        """It keeps its old cursor, so it stays at the head of the queue. If the
        batch counted skips, the sweep would stop working entirely."""
        broke = _owner(db, "broke")
        fine = _owner(db, "fine")
        # The tokenless project sorts first (oldest cursor).
        _project(db, broke, "STARVER", last_checked=STALE - timedelta(days=1))
        _project(db, fine, "WANTED", last_checked=STALE)

        seen = []
        with _tokens({"fine": "tok"}), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])), \
             patch.dict(os.environ, {"DRIFT_SWEEP_BATCH_SIZE": "1"}):
            assert sweep_projects_for_drift(db) == 1

        assert seen == ["WANTED"]


class TestOneBadProjectDoesNotStopTheRest:
    def test_an_exception_is_contained(self, db):
        owner = _owner(db)
        _project(db, owner, "BAD", last_checked=STALE - timedelta(days=1))
        _project(db, owner, "GOOD", last_checked=STALE)

        def flaky(_db, _user, project):
            if project.project_code == "BAD":
                raise RuntimeError("GitHub exploded")
            return ([], [])

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check", side_effect=flaky):
            assert sweep_projects_for_drift(db) == 1


class TestBackoffMultiplier:
    """Pure function - covering the shape directly is cheaper than round-tripping
    through the DB for every case. notification_worker.py's _backoff_delay uses
    the same 2**(attempt-1) shape; this mirrors it."""

    def test_no_failures_is_1x(self):
        assert drift_worker._backoff_multiplier(0) == 1

    def test_a_single_failure_does_not_yet_back_off(self):
        assert drift_worker._backoff_multiplier(1) == 1

    def test_doubles_from_the_second_failure(self):
        assert drift_worker._backoff_multiplier(2) == 2
        assert drift_worker._backoff_multiplier(3) == 4
        assert drift_worker._backoff_multiplier(4) == 8

    def test_caps_rather_than_growing_unbounded(self):
        assert drift_worker._backoff_multiplier(6) == drift_worker.BACKOFF_MAX_MULTIPLIER
        assert drift_worker._backoff_multiplier(100) == drift_worker.BACKOFF_MAX_MULTIPLIER


class TestBackoffInTheSweep:
    def test_a_single_failure_is_still_checked_at_the_normal_interval(self, db):
        """Matches TestBackoffMultiplier: the first failure doesn't back off yet."""
        _project(db, _owner(db), "P1", last_checked=STALE, failure_count=1)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check", return_value=([], [])) as check:
            assert sweep_projects_for_drift(db) == 1

        assert check.call_count == 1

    def test_a_repeatedly_failing_project_is_skipped_before_its_backoff_window_elapses(self, db):
        """5 failures -> 16x the 15-minute default = 4h. Checked 2h ago (STALE)
        is not due yet, even though it clears the un-backed-off base cutoff."""
        _project(db, _owner(db), "P1", last_checked=STALE, failure_count=5)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0

    def test_a_repeatedly_failing_project_is_checked_once_its_backoff_window_elapses(self, db):
        """5 failures -> 4h backoff window; checked 5h ago clears it."""
        _project(db, _owner(db), "P1", last_checked=STALE - timedelta(hours=3), failure_count=5)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check", return_value=([], [])) as check:
            assert sweep_projects_for_drift(db) == 1

        assert check.call_count == 1

    def test_a_backed_off_project_does_not_starve_the_others(self, db):
        """Same non-starvation guarantee as the tokenless case, for backoff.

        STARVER sorts first (older cursor) but 10 failures caps its backoff at
        8h, and it was only checked 3h ago - not due. WANTED, checked 2h ago
        with no failures, is due at the plain 15-minute interval and must
        still be reached despite sorting behind STARVER.
        """
        owner = _owner(db)
        _project(db, owner, "STARVER", last_checked=STALE - timedelta(hours=1), failure_count=10)
        _project(db, owner, "WANTED", last_checked=STALE)

        seen = []
        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])), \
             patch.dict(os.environ, {"DRIFT_SWEEP_BATCH_SIZE": "1"}):
            assert sweep_projects_for_drift(db) == 1

        assert seen == ["WANTED"]


class TestDriftCheckFailureCountBookkeeping:
    """_cache_project_drift_summary is what backoff is computed from, so its
    increment/reset behavior is covered directly here alongside the sweep
    tests that depend on it."""

    def test_check_failed_increments_the_counter(self, db):
        from workflows import _cache_project_drift_summary
        project = _project(db, _owner(db), "P1", failure_count=2)

        _cache_project_drift_summary(db, project, "check_failed", 0, "boom")

        db.refresh(project)
        assert project.drift_check_failure_count == 3

    def test_clean_resets_the_counter(self, db):
        from workflows import _cache_project_drift_summary
        project = _project(db, _owner(db), "P1", failure_count=4)

        _cache_project_drift_summary(db, project, "clean", 0, None)

        db.refresh(project)
        assert project.drift_check_failure_count == 0

    def test_drifted_resets_the_counter(self, db):
        """Finding real drift is a successful check, not a failure."""
        from workflows import _cache_project_drift_summary
        project = _project(db, _owner(db), "P1", failure_count=4)

        _cache_project_drift_summary(db, project, "drifted", 2, None)

        db.refresh(project)
        assert project.drift_check_failure_count == 0


class TestTheKillSwitch:
    def test_disabled_means_nothing_is_checked(self, db):
        _project(db, _owner(db), "P1")

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check") as check, \
             patch.dict(os.environ, {"DRIFT_SWEEP_ENABLED": "false"}):
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0

    def test_enabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert drift_worker.sweep_enabled() is True
