"""
Build metrics must be cheap to look at and honest about what they mean.

Two failure modes drive most of these tests:

  * **Cost.** Metrics are aggregated from stored runs, so opening the panel must
    cost zero GitHub calls, and a refresh must cost one call per *repository* —
    not one per workflow, which is what the older /api/workflow-status path does.
  * **Meaning.** A cancelled build is not a failed build, and "no data" is not
    "everything failed". Both are counted separately and asserted here, because
    a success rate that quietly includes cancellations is wrong in a way nobody
    notices until they act on it.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from workflows import get_db as real_get_db  # noqa: E402
from models import (  # noqa: E402
    Base, Account, Project, Repo, ProjectRepo, Workflow, ProjectWorkflow, WorkflowRun,
    ProjectMembership, WorkspaceMember,
)
from auth import user_tokens  # noqa: E402
from github_api_tracker import RateLimitExceeded  # noqa: E402

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


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
                      reusable_workflow=False, workflow_status="synced_with_github")
        db.add(wf); db.commit(); db.refresh(wf)
        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id)); db.commit()
        user_tokens["alice"] = "tok"
        yield {"db": db, "account": user, "project": project, "repo": repo, "workflow": wf,
               "project_id": project.project_id}
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        user_tokens.clear()
        if prev is None:
            app.dependency_overrides.pop(real_get_db, None)
        else:
            app.dependency_overrides[real_get_db] = prev


def _add_repo(state, name):
    db = state["db"]
    repo = Repo(repo_name=name)
    db.add(repo); db.commit(); db.refresh(repo)
    db.add(ProjectRepo(project_id=state["project_id"], repo_id=repo.repo_id)); db.commit()
    return repo


def _add_workflow(state, name):
    db = state["db"]
    wf = Workflow(workflow_name=name, workflow_yaml="on: push\n", reusable_workflow=False)
    db.add(wf); db.commit(); db.refresh(wf)
    db.add(ProjectWorkflow(project_id=state["project_id"], workflow_id=wf.workflow_id)); db.commit()
    return wf


def _iso(dt):
    return dt.replace(microsecond=0).isoformat() + "Z"


def _payload(run_id, *, conclusion="success", path=".github/workflows/ci.yml",
             created=None, started=None, updated=None, attempt=1, branch="main"):
    created = created or _now() - timedelta(hours=1)
    started = started if started is not None else created + timedelta(seconds=20)
    updated = updated if updated is not None else started + timedelta(seconds=100)
    return {
        "id": run_id,
        "path": path,
        "run_number": run_id,
        "run_attempt": attempt,
        "head_branch": branch,
        "event": "push",
        "status": "completed" if conclusion else "in_progress",
        "conclusion": conclusion,
        "created_at": _iso(created),
        "run_started_at": _iso(started) if started else None,
        "updated_at": _iso(updated),
        "html_url": f"https://github.com/acme/api/actions/runs/{run_id}",
    }


def _github(*payload_batches):
    """Mock github_get returning one batch of runs per call."""
    batches = list(payload_batches)

    def _call(*_args, **_kwargs):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"workflow_runs": batches.pop(0) if batches else []}
        return response

    return MagicMock(side_effect=_call)


def _get(project_id, **params):
    params.setdefault("github_user", "alice")
    return client.get(f"/api/projects/{project_id}/build-metrics", params=params)


def _store(state, **overrides):
    """Insert a run row directly, bypassing the GitHub sync."""
    db = state["db"]
    values = {
        "project_id": state["project_id"],
        "repo_id": state["repo"].repo_id,
        "workflow_id": state["workflow"].workflow_id,
        "github_run_id": overrides.pop("github_run_id", 1),
        "workflow_filename": "ci.yml",
        "workflow_name": "ci",
        "branch": "main",
        "status": "completed",
        "conclusion": "success",
        "run_created_at": _now() - timedelta(hours=1),
        "synced_at": _now(),
    }
    values.update(overrides)
    db.add(WorkflowRun(**values)); db.commit()


def _mark_synced(state, when=None):
    state["project"].last_run_sync_at = when or _now()
    state["db"].commit()


class TestCost:
    def test_opening_the_panel_makes_no_github_calls(self, state):
        """The whole reason runs are stored rather than fetched per view."""
        _store(state)
        _mark_synced(state)

        with patch("build_metrics.github_get") as gh:
            resp = _get(state["project_id"])

        assert resp.status_code == 200, resp.text
        assert gh.call_count == 0

    def test_refresh_costs_one_call_per_repo_not_per_workflow(self, state):
        _add_repo(state, "acme/web")
        _add_workflow(state, "release")
        _add_workflow(state, "nightly")
        _mark_synced(state)

        gh = _github([_payload(1)], [])
        with patch("build_metrics.github_get", gh):
            resp = _get(state["project_id"], refresh="true")

        assert resp.status_code == 200, resp.text
        # 2 repos x 3 workflows: per-workflow polling would be 6+ calls.
        assert gh.call_count == 2

    def test_a_fresh_sync_is_not_repeated_within_the_interval(self, state):
        _mark_synced(state, _now() - timedelta(minutes=1))

        with patch("build_metrics.github_get") as gh:
            _get(state["project_id"])

        assert gh.call_count == 0

    def test_stale_data_triggers_a_sync(self, state):
        _mark_synced(state, _now() - timedelta(hours=5))

        gh = _github([_payload(1)])
        with patch("build_metrics.github_get", gh):
            _get(state["project_id"])

        assert gh.call_count == 1

    def test_a_project_with_no_runs_yet_still_gates_on_the_cursor(self, state):
        """Deriving staleness from stored rows would re-hit GitHub forever here."""
        gh = _github([])
        with patch("build_metrics.github_get", gh):
            _get(state["project_id"])          # never synced -> one sync
            _get(state["project_id"])          # cursor now set -> no second sync

        assert gh.call_count == 1


class TestIngestion:
    def test_runs_are_stored_and_attributed_to_the_workflow(self, state):
        gh = _github([_payload(11)])
        with patch("build_metrics.github_get", gh):
            _get(state["project_id"], refresh="true")

        run = state["db"].query(WorkflowRun).one()
        assert run.github_run_id == 11
        assert run.workflow_id == state["workflow"].workflow_id
        assert run.workflow_filename == "ci.yml"
        assert run.branch == "main"

    def test_runs_for_other_workflows_are_ignored(self, state):
        gh = _github([_payload(11), _payload(12, path=".github/workflows/someone-else.yml")])
        with patch("build_metrics.github_get", gh):
            _get(state["project_id"], refresh="true")

        stored = state["db"].query(WorkflowRun).all()
        assert [r.github_run_id for r in stored] == [11]

    def test_a_rerun_updates_the_row_instead_of_duplicating_it(self, state):
        with patch("build_metrics.github_get", _github([_payload(11, conclusion="failure")])):
            _get(state["project_id"], refresh="true")
        with patch("build_metrics.github_get", _github([_payload(11, conclusion="success", attempt=2)])):
            _get(state["project_id"], refresh="true")

        run = state["db"].query(WorkflowRun).one()
        assert run.conclusion == "success"
        assert run.run_attempt == 2

    def test_duration_and_queue_come_from_the_run_fields(self, state):
        created = _now() - timedelta(hours=2)
        payload = _payload(11, created=created,
                           started=created + timedelta(seconds=30),
                           updated=created + timedelta(seconds=30 + 90))

        with patch("build_metrics.github_get", _github([payload])):
            _get(state["project_id"], refresh="true")

        run = state["db"].query(WorkflowRun).one()
        assert run.queue_seconds == 30
        assert run.duration_seconds == 90

    def test_an_in_flight_run_has_no_duration(self, state):
        payload = _payload(11, conclusion=None)

        with patch("build_metrics.github_get", _github([payload])):
            _get(state["project_id"], refresh="true")

        run = state["db"].query(WorkflowRun).one()
        assert run.duration_seconds is None

    def test_sync_failure_returns_stored_runs_flagged_as_stale(self, state):
        _store(state)
        _mark_synced(state, _now() - timedelta(hours=5))
        previous_cursor = state["project"].last_run_sync_at

        with patch("build_metrics.github_get", side_effect=RateLimitExceeded("limit reached")):
            body = _get(state["project_id"], refresh="true").json()

        assert body["sync_failed"] is True
        assert "rate limit" in body["sync_message"].lower()
        assert body["total_runs"] == 1  # stored data still served
        state["db"].refresh(state["project"])
        # A failed sync must not look like a fresh one.
        assert state["project"].last_run_sync_at == previous_cursor


class TestMeaning:
    def test_success_rate_ignores_cancelled_and_skipped_runs(self, state):
        for i in range(8):
            _store(state, github_run_id=100 + i, conclusion="success")
        for i in range(2):
            _store(state, github_run_id=200 + i, conclusion="failure")
        for i in range(5):
            _store(state, github_run_id=300 + i, conclusion="cancelled")
        _store(state, github_run_id=400, conclusion="skipped")
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert body["total_runs"] == 16
        assert body["decided_runs"] == 10
        assert body["success_rate"] == 80.0

    def test_no_decided_runs_reports_unknown_not_zero(self, state):
        _store(state, github_run_id=1, conclusion="cancelled")
        _store(state, github_run_id=2, conclusion=None)
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert body["success_rate"] is None
        assert body["total_runs"] == 2

    def test_never_synced_reports_no_timestamp(self, state):
        with patch("build_metrics.github_get", side_effect=RateLimitExceeded("nope")):
            body = _get(state["project_id"]).json()

        assert body["last_synced"] is None

    def test_duration_statistics(self, state):
        for i, seconds in enumerate([10, 20, 30, 40, 100]):
            _store(state, github_run_id=i, duration_seconds=seconds, queue_seconds=5)
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert body["avg_duration_seconds"] == 40
        assert body["p50_duration_seconds"] == 30
        assert body["p95_duration_seconds"] == 100
        assert body["avg_queue_seconds"] == 5

    def test_trend_includes_days_with_no_runs(self, state):
        _store(state, github_run_id=1, run_created_at=_now() - timedelta(days=3))
        _mark_synced(state)

        body = _get(state["project_id"], days=7).json()

        assert len(body["trend"]) == 7
        assert sum(point["total"] for point in body["trend"]) == 1
        assert body["trend"][0]["total"] == 0

    def test_workflow_breakdown_is_ordered_by_volume(self, state):
        other = _add_workflow(state, "release")
        for i in range(3):
            _store(state, github_run_id=i, workflow_name="ci")
        _store(state, github_run_id=99, workflow_id=other.workflow_id,
               workflow_name="release", workflow_filename="release.yml")
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert [w["workflow_name"] for w in body["workflows"]] == ["ci", "release"]
        assert body["workflows"][0]["total"] == 3

    def test_deleting_a_workflow_keeps_its_build_history(self, state):
        """Removing a workflow must not retroactively rewrite past success rates."""
        _store(state, github_run_id=1)
        db = state["db"]
        db.query(ProjectWorkflow).filter_by(workflow_id=state["workflow"].workflow_id).delete()
        db.delete(state["workflow"])
        db.commit()
        _mark_synced(state)

        run = db.query(WorkflowRun).one()
        assert run.workflow_id is None
        assert run.workflow_name == "ci"


class TestLinksOut:
    def test_recent_runs_carry_the_github_url_newest_first(self, state):
        _store(state, github_run_id=1, run_created_at=_now() - timedelta(hours=5),
               html_url="https://github.com/acme/api/actions/runs/1")
        _store(state, github_run_id=2, run_created_at=_now() - timedelta(hours=1),
               html_url="https://github.com/acme/api/actions/runs/2")
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert [r["github_run_id"] for r in body["recent_runs"]] == [2, 1]
        assert body["recent_runs"][0]["html_url"] == "https://github.com/acme/api/actions/runs/2"
        assert body["recent_runs"][0]["repo"] == "acme/api"

    def test_recent_runs_are_capped(self, state):
        for i in range(25):
            _store(state, github_run_id=i, run_created_at=_now() - timedelta(minutes=i))
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert body["total_runs"] == 25
        assert len(body["recent_runs"]) == 20

    def test_only_failures_narrows_the_list_but_not_the_numbers(self, state):
        """Filtering the list must never make the success rate read 0%."""
        for i in range(8):
            _store(state, github_run_id=100 + i, conclusion="success")
        _store(state, github_run_id=200, conclusion="failure")
        _store(state, github_run_id=201, conclusion="timed_out")
        _mark_synced(state)

        body = _get(state["project_id"], only_failures="true").json()

        assert sorted(r["github_run_id"] for r in body["recent_runs"]) == [200, 201]
        assert body["success_rate"] == 80.0
        assert body["total_runs"] == 10
        assert body["decided_runs"] == 10

    def test_recent_runs_respect_the_window(self, state):
        _store(state, github_run_id=1, run_created_at=_now() - timedelta(days=200))
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert body["recent_runs"] == []

    def test_workflow_breakdown_links_to_the_actions_page(self, state):
        _store(state, github_run_id=1)
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert body["workflows"][0]["actions_url"] == (
            "https://github.com/acme/api/actions/workflows/ci.yml"
        )

    def test_actions_url_encodes_the_filename(self, state):
        _store(state, github_run_id=1, workflow_filename="build report.yml")
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert body["workflows"][0]["actions_url"].endswith("/build%20report.yml")

    def test_actions_url_is_null_when_the_repo_left_the_project(self, state):
        _store(state, github_run_id=1)
        db = state["db"]
        db.query(ProjectRepo).filter_by(repo_id=state["repo"].repo_id).delete()
        db.commit()
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert body["workflows"][0]["actions_url"] is None
        assert body["recent_runs"][0]["repo"] is None


class TestScopingToOneWorkflow:
    def _two_workflows(self, state):
        release = _add_workflow(state, "release")
        for i in range(4):
            _store(state, github_run_id=i, conclusion="success")
        _store(state, github_run_id=50, workflow_id=release.workflow_id,
               workflow_name="release", workflow_filename="release.yml", conclusion="failure")
        _mark_synced(state)

    def test_scoping_narrows_every_figure(self, state):
        self._two_workflows(state)

        body = _get(state["project_id"], workflow="release.yml").json()

        assert body["selected_workflow"] == "release.yml"
        assert body["total_runs"] == 1
        assert body["decided_runs"] == 1
        assert body["success_rate"] == 0.0
        assert [r["github_run_id"] for r in body["recent_runs"]] == [50]
        assert sum(point["total"] for point in body["trend"]) == 1

    def test_the_workflow_list_stays_project_wide_while_scoped(self, state):
        """Scoping the index would collapse it to the current selection and
        leave the user no way to switch to another workflow."""
        self._two_workflows(state)

        body = _get(state["project_id"], workflow="release.yml").json()

        assert sorted(w["workflow_filename"] for w in body["workflows"]) == ["ci.yml", "release.yml"]
        assert {w["workflow_filename"]: w["total"] for w in body["workflows"]} == {
            "ci.yml": 4, "release.yml": 1,
        }

    def test_unscoped_still_reports_the_whole_project(self, state):
        self._two_workflows(state)

        body = _get(state["project_id"]).json()

        assert body["selected_workflow"] is None
        assert body["total_runs"] == 5
        assert body["success_rate"] == 80.0

    def test_scoping_is_case_insensitive(self, state):
        self._two_workflows(state)

        body = _get(state["project_id"], workflow="RELEASE.YML").json()

        assert body["total_runs"] == 1

    def test_an_unknown_workflow_reports_empty_rather_than_failing(self, state):
        self._two_workflows(state)

        resp = _get(state["project_id"], workflow="deleted.yml")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_runs"] == 0
        assert body["success_rate"] is None
        # The index is still full, so the UI can recover from a stale selection.
        assert len(body["workflows"]) == 2

    def test_scoping_composes_with_the_failures_filter(self, state):
        self._two_workflows(state)

        body = _get(state["project_id"], workflow="ci.yml", only_failures="true").json()

        assert body["recent_runs"] == []
        assert body["success_rate"] == 100.0

    def test_workflows_sharing_a_display_name_stay_separate_rows(self, state):
        """Grouping by display name would merge two files into one ambiguous row."""
        other = _add_workflow(state, "deploy")
        _store(state, github_run_id=1, workflow_name="Build", workflow_filename="build-a.yml")
        _store(state, github_run_id=2, workflow_id=other.workflow_id,
               workflow_name="Build", workflow_filename="build-b.yml")
        _mark_synced(state)

        body = _get(state["project_id"]).json()

        assert sorted(w["workflow_filename"] for w in body["workflows"]) == ["build-a.yml", "build-b.yml"]


class TestTierWindow:
    def test_free_tier_window_is_clamped(self, state):
        _mark_synced(state)

        body = _get(state["project_id"], days=365).json()

        assert body["window_days"] == 30

    def test_enterprise_window_is_unlimited(self, state):
        state["account"].account_type = "enterprise"
        state["db"].commit()
        _mark_synced(state)

        body = _get(state["project_id"], days=365).json()

        assert body["window_days"] == 365

    def test_self_hosted_beta_window_overrides_the_tier(self, state):
        state["account"].account_type = "enterprise"
        state["db"].commit()
        _mark_synced(state)

        with patch("build_metrics.get_run_history_days", return_value=30):
            body = _get(state["project_id"], days=365).json()

        assert body["window_days"] == 30

    def test_runs_outside_the_window_are_excluded_and_purged(self, state):
        _store(state, github_run_id=1, run_created_at=_now() - timedelta(days=200))
        _store(state, github_run_id=2, run_created_at=_now() - timedelta(days=1))
        _mark_synced(state, _now() - timedelta(hours=5))

        with patch("build_metrics.github_get", _github([])):
            body = _get(state["project_id"]).json()

        assert body["total_runs"] == 1
        assert [r.github_run_id for r in state["db"].query(WorkflowRun).all()] == [2]


class TestRetentionIsNotTheRequestWindow:
    def test_a_narrow_view_does_not_destroy_retained_history(self, state):
        """Purging by the requested window let ?days=1 permanently delete
        history the tier is meant to keep, unrecoverably: the GitHub fetch is
        bounded by the same window, so a refresh never brings it back."""
        _store(state, github_run_id=1, run_created_at=_now() - timedelta(days=20))
        _store(state, github_run_id=2, run_created_at=_now() - timedelta(hours=1))
        _mark_synced(state, _now() - timedelta(hours=5))

        with patch("build_metrics.github_get", _github([])):
            body = _get(state["project_id"], days=1).json()

        assert body["total_runs"] == 1                      # the view is narrow
        assert state["db"].query(WorkflowRun).count() == 2  # the history is not

    def test_runs_past_the_tier_horizon_are_still_purged(self, state):
        _store(state, github_run_id=1, run_created_at=_now() - timedelta(days=200))
        _store(state, github_run_id=2, run_created_at=_now() - timedelta(hours=1))
        _mark_synced(state, _now() - timedelta(hours=5))

        with patch("build_metrics.github_get", _github([])):
            _get(state["project_id"])

        assert [r.github_run_id for r in state["db"].query(WorkflowRun).all()] == [2]

    def test_unparseable_timestamps_do_not_accumulate_forever(self, state):
        """A row with no run_created_at matches no window query, so it is
        invisible to every metric — and matched no purge comparison either."""
        _store(state, github_run_id=1, run_created_at=None)
        _mark_synced(state, _now() - timedelta(hours=5))

        with patch("build_metrics.github_get", _github([])):
            _get(state["project_id"])

        assert state["db"].query(WorkflowRun).count() == 0

    def test_an_absurd_window_is_clamped_rather_than_crashing(self, state):
        state["account"].account_type = "enterprise"
        state["db"].commit()
        _mark_synced(state)

        resp = _get(state["project_id"], days=4000000)

        assert resp.status_code == 200
        assert resp.json()["window_days"] == 365

    def test_a_missing_account_row_falls_back_instead_of_crashing(self):
        """The account comes from a bare .first(); the tier helpers dereference
        it, so None reached them as an AttributeError and a 500."""
        from build_metrics import _retention_days, _window_days

        assert _retention_days(None) == 30
        assert _window_days(_retention_days(None), 365) == 30


class TestSyncRobustness:
    def test_a_run_repeated_across_pages_is_stored_once(self, state):
        """GitHub's listing shifts as new runs start, so a run can appear on two
        consecutive pages. With autoflush off, a per-payload lookup cannot see
        the pending insert and the duplicate hits the unique constraint."""
        page_one = [_payload(i) for i in range(1, 101)]
        page_two = [_payload(100), _payload(101)]  # 100 repeats

        with patch("build_metrics.github_get", _github(page_one, page_two)):
            resp = _get(state["project_id"], refresh="true")

        assert resp.status_code == 200
        assert resp.json()["sync_failed"] is False
        assert state["db"].query(WorkflowRun).count() == 101

    def test_two_projects_sharing_a_repo_each_keep_their_own_runs(self, state):
        """Keyed on (repo, run) alone, whichever project synced first owned the
        row and the other project's panel stayed empty forever."""
        db = state["db"]
        other = Project(project_name="second", project_code="P003",
                        user_id=state["account"].user_id, use_prefix=False)
        db.add(other); db.commit(); db.refresh(other)
        db.add(ProjectRepo(project_id=other.project_id, repo_id=state["repo"].repo_id))
        wf = Workflow(workflow_name="ci", workflow_yaml="on: push\n", reusable_workflow=False)
        db.add(wf); db.commit(); db.refresh(wf)
        db.add(ProjectWorkflow(project_id=other.project_id, workflow_id=wf.workflow_id))
        db.commit()

        with patch("build_metrics.github_get", _github([_payload(9001)])):
            _get(state["project_id"], refresh="true")
        with patch("build_metrics.github_get", _github([_payload(9001)])):
            second = _get(other.project_id, refresh="true").json()

        assert second["total_runs"] == 1
        assert _get(state["project_id"]).json()["total_runs"] == 1

    def test_a_reusable_workflow_project_does_not_poll_github(self, state):
        """A workflow_call workflow runs inside its caller and produces no run
        of its own, so syncing one can only ever spend rate limit."""
        db = state["db"]
        state["workflow"].reusable_workflow = True
        db.commit()

        with patch("build_metrics.github_get") as gh:
            resp = _get(state["project_id"], refresh="true")

        assert resp.status_code == 200
        assert gh.call_count == 0


class TestAuthorization:
    def test_unauthenticated_caller_is_rejected(self, state):
        resp = _get(state["project_id"], github_user="mallory")
        assert resp.status_code == 401

    def test_unknown_project_is_404(self, state):
        assert _get(999999).status_code == 404

    def test_another_users_project_is_rejected(self, state):
        """404 rather than 403 — the shared by-id helper does not confirm that a
        project the caller cannot see exists."""
        db = state["db"]
        bob = Account(github_user="bob", github_email="b@e.com", account_type="free")
        db.add(bob); db.commit(); db.refresh(bob)
        theirs = Project(project_name="theirs", project_code="P002", user_id=bob.user_id)
        db.add(theirs); db.commit(); db.refresh(theirs)

        assert _get(theirs.project_id).status_code == 404

    def test_a_same_named_project_the_caller_is_a_member_of_is_reachable(self, state):
        """The name-based lookup resolved the caller's own project first, so a
        member of someone else's same-named project was refused access."""
        db = state["db"]
        bob = Account(github_user="bob", github_email="b@e.com", account_type="free")
        db.add(bob); db.commit(); db.refresh(bob)
        theirs = Project(project_name="proj", project_code="P002", user_id=bob.user_id)
        db.add(theirs); db.commit(); db.refresh(theirs)
        # An explicit project grant is only consulted for a workspace member.
        db.add(WorkspaceMember(user_id=state["account"].user_id, workspace_role="read_only"))
        db.add(ProjectMembership(project_id=theirs.project_id, user_id=state["account"].user_id,
                                 project_role="project_viewer"))
        db.commit()

        assert _get(theirs.project_id).status_code == 200
