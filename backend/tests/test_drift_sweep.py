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

from models import Base, Account, DriftSettings, Project  # noqa: E402
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


def _project(db, owner, code, last_checked=STALE, failure_count=0, interval=None):
    project = Project(project_name=f"proj-{code}", project_code=code, user_id=owner.user_id,
                      use_prefix=False, branch_option="default",
                      last_drift_check_at=last_checked,
                      drift_check_failure_count=failure_count,
                      drift_check_interval_minutes=interval)
    db.add(project); db.commit(); db.refresh(project)
    return project


def _settings(db, **overrides):
    """Save the single global settings row. Config lives in the DB, not the
    environment, so tests set it the same way the GUI does."""
    values = {"sweep_enabled": True, "recheck_interval_minutes": 15,
              "batch_size": 5, "poll_interval_seconds": 60}
    values.update(overrides)
    settings = DriftSettings(**values)
    db.add(settings); db.commit()
    return settings


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
        _settings(db, batch_size=1)

        seen = []
        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])):
            sweep_projects_for_drift(db)

        assert seen == ["NEW"]


class TestBatching:
    def test_the_batch_caps_how_many_are_checked(self, db):
        owner = _owner(db)
        for i in range(5):
            _project(db, owner, f"P{i}")
        _settings(db, batch_size=2)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check", return_value=([], [])) as check:
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
        _settings(db, batch_size=1)

        seen = []
        with _tokens({"fine": "tok"}), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])):
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
        _settings(db, batch_size=1)

        seen = []
        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])):
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
        _settings(db, sweep_enabled=False)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0

    def test_enabled_when_nothing_has_been_saved(self, db):
        """No settings row is the state of every install that has never opened
        the settings page — it must behave exactly as the old defaults did."""
        settings = drift_worker.get_settings(db)

        assert settings.sweep_enabled is True
        assert settings.recheck_interval_minutes == 15
        assert settings.batch_size == 5
        assert settings.poll_interval_seconds == 60


class TestPerProjectInterval:
    """One project off, one on a long interval, one on a short one — the point
    of moving this config into the GUI."""

    def test_a_project_set_to_off_is_never_checked(self, db):
        _project(db, _owner(db), "OFF", interval=drift_worker.INTERVAL_OFF,
                 last_checked=STALE - timedelta(days=7))

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0

    def test_off_does_not_starve_the_projects_behind_it(self, db):
        """An off project sorts to the head of the queue (oldest check first),
        so excluding it must not cost the next project its slot."""
        owner = _owner(db)
        _project(db, owner, "OFF", interval=drift_worker.INTERVAL_OFF,
                 last_checked=STALE - timedelta(days=7))
        _project(db, owner, "WANTED", last_checked=STALE)
        _settings(db, batch_size=1)

        seen = []
        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])):
            assert sweep_projects_for_drift(db) == 1

        assert seen == ["WANTED"]

    def test_a_longer_project_interval_defers_a_check_the_global_would_allow(self, db):
        """Checked 2h ago: due at the 15-minute global default, not due on the
        project's own daily cadence."""
        _project(db, _owner(db), "DAILY", interval=1440, last_checked=STALE)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0

    def test_a_project_past_its_own_longer_interval_is_checked(self, db):
        _project(db, _owner(db), "DAILY", interval=1440,
                 last_checked=datetime.now(timezone.utc) - timedelta(days=2))

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check", return_value=([], [])) as check:
            assert sweep_projects_for_drift(db) == 1

        assert check.call_count == 1

    def test_a_shorter_project_interval_beats_a_long_global_default(self, db):
        """The SQL pre-filter is bounded by the shortest interval in play, so a
        project checking more often than the global default is still reached."""
        _project(db, _owner(db), "FAST", interval=15,
                 last_checked=datetime.now(timezone.utc) - timedelta(minutes=30))
        _settings(db, recheck_interval_minutes=1440)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check", return_value=([], [])) as check:
            assert sweep_projects_for_drift(db) == 1

        assert check.call_count == 1

    def test_no_override_inherits_the_global_default(self, db):
        _project(db, _owner(db), "P1", interval=None, last_checked=STALE)
        _settings(db, recheck_interval_minutes=1440)

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0

    def test_many_not_due_projects_do_not_starve_a_due_one(self, db):
        """The candidate window is capped, so "due" has to be decided in SQL.

        Sixty daily projects checked 2h ago are not due, but they sort ahead of
        a 15-minute project checked 30m ago that is. If they can occupy
        candidate slots, the due project is never reached and the tick does no
        work at all — the same starvation an "off" project would cause.
        """
        owner = _owner(db)
        for i in range(60):
            _project(db, owner, f"D{i}", interval=1440,
                     last_checked=datetime.now(timezone.utc) - timedelta(hours=2))
        _project(db, owner, "DUE", interval=15,
                 last_checked=datetime.now(timezone.utc) - timedelta(minutes=30))
        _settings(db, batch_size=5)

        seen = []
        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])):
            assert sweep_projects_for_drift(db) == 1

        assert seen == ["DUE"]

    def test_backoff_still_applies_on_top_of_a_project_interval(self, db):
        """Two consecutive failures double the wait — on the project's own
        30-minute cadence, not the global default."""
        _project(db, _owner(db), "P1", interval=30, failure_count=2,
                 last_checked=datetime.now(timezone.utc) - timedelta(minutes=45))

        with _tokens({"alice": "tok"}), \
             patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0


class TestAnUndecryptableSavedTokenIsNotACredential:
    """#2050: after a container update every project showed "Needs Attention".

    A saved PAT that will not decrypt (SECRET_KEY changed) resolved to the
    sentinel string, which the store handed out as an ordinary token. Every
    GitHub read then 401'd, every (workflow, repo) pair came back check_failed,
    and every project cached check_failed at once. These tests drive the real
    credential store rather than patching it, because the bug lived there.
    """

    @pytest.fixture
    def sentinel_owner(self, db):
        from auth import INVALID_SAVED_TOKEN_SENTINEL, user_tokens

        owner = _owner(db, "alice")
        user_tokens.clear()
        user_tokens._pat_cache["alice"] = (INVALID_SAVED_TOKEN_SENTINEL, float("inf"))
        try:
            yield owner
        finally:
            user_tokens.clear()
            user_tokens.invalidate_pat("alice")

    def test_the_project_is_skipped_rather_than_checked_with_a_garbage_token(
        self, db, sentinel_owner
    ):
        """Running the check anyway is what produced check_failed everywhere."""
        _project(db, sentinel_owner, "P1")

        with patch("workflows.run_project_drift_check") as check:
            assert sweep_projects_for_drift(db) == 0

        assert check.call_count == 0

    def test_a_clean_project_is_not_flipped_to_check_failed(self, db, sentinel_owner):
        """The reported symptom. Running the check with the sentinel 401s every
        read, so the whole project caches check_failed — which the UI shows as
        "Needs Attention". The mock stands in for that, so the test fails if the
        sweep ever decides to run the check again."""
        project = _project(db, sentinel_owner, "P1")
        project.drift_status = "clean"
        db.commit()

        def every_read_401s(session, _username, proj):
            from workflows import _cache_project_drift_summary
            _cache_project_drift_summary(session, proj, "check_failed", 0, "401")
            return ([], [])

        with patch("workflows.run_project_drift_check", side_effect=every_read_401s):
            sweep_projects_for_drift(db)

        db.refresh(project)
        assert project.drift_status == "clean"

    def test_the_badge_the_bug_left_behind_is_cleared(self, db, sentinel_owner):
        """The fix is worthless on upgrade if it only stops *new* false badges.

        Every affected project is already sitting on a check_failed written by
        the bug, which the UI renders as "Needs Attention". A skip knows no
        check is being attempted, so that non-verdict becomes "unknown"
        ("Not checked") instead of accusing the project indefinitely.
        """
        project = _project(db, sentinel_owner, "P1")
        project.drift_status = "check_failed"
        db.commit()

        with patch("workflows.run_project_drift_check"):
            sweep_projects_for_drift(db)

        db.refresh(project)
        assert project.drift_status == "unknown"

    def test_a_real_verdict_is_still_not_touched(self, db, sentinel_owner):
        """Only the non-verdict is cleared: drift that was really found stands."""
        project = _project(db, sentinel_owner, "P1")
        project.drift_status = "drifted"
        project.drift_count = 3
        db.commit()

        with patch("workflows.run_project_drift_check"):
            sweep_projects_for_drift(db)

        db.refresh(project)
        assert project.drift_status == "drifted"
        assert project.drift_count == 3

    def test_the_inflated_backoff_streak_is_reset(self, db, sentinel_owner):
        """Pre-fix, every doomed check incremented the streak, so it hit the 32x
        cap within ~1.5h. A skip is not a failed check, so carrying that streak
        would keep throttling a project that is not being checked at all — and
        would still be throttling it after the credential is repaired.

        Cursor is set past the inflated 8h window (32 x 15min) on purpose: that
        backoff is applied when candidates are selected, so a project inside it
        is not reached at all and nothing here can reset anything.
        """
        project = _project(db, sentinel_owner, "P1", failure_count=6,
                           last_checked=datetime.now(timezone.utc) - timedelta(hours=9))

        with patch("workflows.run_project_drift_check"):
            sweep_projects_for_drift(db)

        db.refresh(project)
        assert project.drift_check_failure_count == 0

    def test_the_reason_names_the_unreadable_token_not_a_missing_one(
        self, db, sentinel_owner
    ):
        """A token *is* stored, so "no saved GitHub token" sends the owner
        looking for a credential that is sitting right there."""
        project = _project(db, sentinel_owner, "P1")

        with patch("workflows.run_project_drift_check"):
            sweep_projects_for_drift(db)

        db.refresh(project)
        assert project.drift_error_summary == drift_worker.UNREADABLE_CREDENTIAL_REASON
        assert project.drift_error_summary != drift_worker.NO_CREDENTIAL_REASON


class TestARecordedSkipCannotKillTheTick:
    def test_a_failed_skip_does_not_stop_the_other_projects(self, db):
        """_record_skip commits, and a commit can fail (SQLite "database is
        locked"). Outside the per-project guard that took the whole sweep down
        with it, on the first tick after a deploy when every affected project
        writes at once."""
        broke = _owner(db, "broke")
        fine = _owner(db, "fine")
        _project(db, broke, "SKIPPED", last_checked=STALE - timedelta(days=1))
        _project(db, fine, "WANTED", last_checked=STALE)

        seen = []
        with _tokens({"fine": "tok"}), \
             patch.object(drift_worker, "_record_skip", side_effect=RuntimeError("database is locked")), \
             patch("workflows.run_project_drift_check",
                   side_effect=lambda d, u, p: seen.append(p.project_code) or ([], [])):
            assert sweep_projects_for_drift(db) == 1

        assert seen == ["WANTED"]
