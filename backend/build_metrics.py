"""
Build metrics for a project's GitHub Actions runs (issue #689).

Provides:
- GET /api/projects/{project_id}/build-metrics — success rates, duration and
  queue-time statistics, a daily trend, and a per-workflow breakdown.

Runs are stored locally (``workflow_runs``) and metrics are computed from those
rows, so opening the panel costs no GitHub API calls. A sync happens only when
the stored data is older than ``BUILD_METRICS_SYNC_INTERVAL_MINUTES`` or the
caller passes ``refresh=true``.

Each sync lists runs **per repository** — one call returns every workflow's runs
— rather than per workflow, and the calls go through ``github_get`` so they are
rate-limited and counted like every other GitHub call in the app.

Job-level breakdown is deliberately absent: GitHub's ``/jobs`` and ``/timing``
endpoints cost one call per run, which would make a project with a hundred runs
a hundred calls. Duration and queue time are derived from fields the run listing
already returns.
"""

import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import user_tokens
from database import get_db
from github_api_tracker import RateLimitExceeded, github_get
from models import Account, Project, ProjectRepo, ProjectWorkflow, Repo, Workflow, WorkflowRun
from tier_service import get_run_history_days
from projects import _require_project_access
from workflows import (
    ACCEPT_HEADER,
    GITHUB_API_URL,
    GITHUB_TIMEOUT_SECONDS,
    X_API_VERSION,
    format_workflow_name,
)

router = APIRouter()

DEFAULT_WINDOW_DAYS = 30
# An unlimited tier applies no clamp of its own, so this is what stops a caller
# from asking for a window wide enough to overflow the date arithmetic.
MAX_WINDOW_DAYS = 365
DEFAULT_SYNC_INTERVAL_MINUTES = 15
# Two pages of 100 caps a single sync at 200 runs per repo. A busy repo is
# truncated rather than allowed to fan out into an unbounded page walk; the
# newest runs are the ones metrics care about and GitHub returns those first.
MAX_PAGES = 2
PER_PAGE = 100
# Enough to cover a typical week without turning the summary into a run browser
# — browsing every run belongs to #685.
RECENT_RUN_LIMIT = 20

GITHUB_WEB_URL = "https://github.com"

NOT_AUTHENTICATED_DETAIL = "User not authenticated"
PROJECT_ERROR = "Project not found"
NOT_AUTHORIZED_PROJECT_DETAIL = "Not authorized to access this project"

# Conclusions that mean the build actually passed judgement. Runs still in
# flight (conclusion NULL) are excluded so a queue of pending builds never looks
# like a drop in success rate — and so are cancelled/skipped runs, which say
# nothing about whether the code was good. Counting a cancellation as a failure
# is the most commonly misread number on a build dashboard.
_SUCCESS = "success"
_FAILURE_CONCLUSIONS = ("failure", "timed_out", "startup_failure")
_DECIDED_CONCLUSIONS = (_SUCCESS,) + _FAILURE_CONCLUSIONS


class TrendPoint(BaseModel):
    date: str
    total: int
    success: int
    failure: int


class WorkflowBreakdown(BaseModel):
    workflow_name: str
    # The delivered filename, which is what identifies a run. Pass it back as
    # ``workflow`` to scope the summary to it — display names are not unique
    # enough to key on (two files can carry the same ``name:``).
    workflow_filename: str
    total: int
    success_rate: Optional[float] = None
    avg_duration_seconds: Optional[int] = None
    # This workflow's Actions page on GitHub. A workflow delivered to several
    # repos runs in each of them, so this points at the repo it most recently
    # ran in — null when that repo is no longer part of the project.
    actions_url: Optional[str] = None


class RecentRun(BaseModel):
    """One run, with the link out to it on GitHub."""
    github_run_id: int
    run_number: Optional[int] = None
    workflow_name: str
    repo: Optional[str] = None
    branch: str
    event: Optional[str] = None
    status: Optional[str] = None
    conclusion: Optional[str] = None
    created_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    html_url: Optional[str] = None


class BuildMetricsSummary(BaseModel):
    project_id: int
    project_name: str
    window_days: int
    # None when nothing has ever been synced — the UI must say "no data yet"
    # rather than presenting an empty result as a freshly verified zero.
    last_synced: Optional[str] = None
    total_runs: int
    # Runs that produced a pass/fail verdict — the denominator of success_rate.
    # Cancelled, skipped and in-flight runs are counted in total_runs only.
    decided_runs: int
    conclusion_counts: Dict[str, int]
    success_rate: Optional[float] = None
    avg_duration_seconds: Optional[int] = None
    p50_duration_seconds: Optional[int] = None
    p95_duration_seconds: Optional[int] = None
    avg_queue_seconds: Optional[int] = None
    # The workflow every figure above is scoped to, echoed back so the UI can
    # label the view and recover if it asked for one that no longer exists.
    # Null means the whole project.
    selected_workflow: Optional[str] = None
    trend: List[TrendPoint]
    # Always every workflow in the window, even when scoped — this is the
    # navigation index, so it must not collapse to the current selection.
    workflows: List[WorkflowBreakdown]
    # Newest first, capped at RECENT_RUN_LIMIT. Narrowed by only_failures; every
    # other field above is always computed over the whole window, so filtering
    # the list never moves the success rate.
    recent_runs: List[RecentRun]
    # True when the GitHub sync failed: the numbers below are the last known
    # ones, not a fresh reading.
    sync_failed: bool = False
    sync_message: Optional[str] = None


def _sync_interval_minutes() -> int:
    try:
        value = int(os.getenv("BUILD_METRICS_SYNC_INTERVAL_MINUTES", "").strip())
    except (TypeError, ValueError):
        return DEFAULT_SYNC_INTERVAL_MINUTES
    return value if value > 0 else DEFAULT_SYNC_INTERVAL_MINUTES


def _parse_github_time(value: Optional[str]) -> Optional[datetime]:
    """Parse GitHub's ISO-8601 timestamps into naive UTC, matching stored rows."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _utc_iso(value: Optional[datetime]) -> Optional[str]:
    """Serialize a stored (naive UTC) timestamp with an explicit UTC marker.

    Without the suffix the browser reads the string as *local* time, so a sync
    five hours old renders as "just now" in one timezone and in the future in
    another — silently defeating the staleness signal the timestamp exists for.
    """
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _elapsed_seconds(start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
    if not start or not end:
        return None
    # GitHub's timestamps occasionally skew a second or two the wrong way.
    # Clamping to zero keeps the sample; discarding it would bias the average.
    return max(0, int((end - start).total_seconds()))


def _project_workflow_files(db: Session, project: Project) -> Dict[str, Workflow]:
    """Map each of the project's GitHub workflow filenames to its Workflow row.

    Keys are lowercased for case-insensitive matching. ``ilike`` is avoided
    throughout this module because workflow filenames routinely contain ``_``,
    which is a SQL LIKE wildcard.

    Reusable workflows are excluded. A ``workflow_call`` workflow produces no
    run record of its own — it executes inside the caller's run, which is
    already counted here — so including them cannot add a single row, but it
    does make the map non-empty, which is what decides whether a sync runs at
    all. A Reusable Workflow Project would otherwise spend two GitHub calls per
    repo, every interval, to populate a panel that can never fill.
    """
    workflows = (
        db.query(Workflow)
        .join(ProjectWorkflow, ProjectWorkflow.workflow_id == Workflow.workflow_id)
        .filter(
            ProjectWorkflow.project_id == project.project_id,
            # Nullable on rows created before the column existed.
            or_(Workflow.reusable_workflow.is_(False), Workflow.reusable_workflow.is_(None)),
        )
        .all()
    )
    return {
        format_workflow_name(w.workflow_name, project.project_code or "", project.use_prefix).lower(): w
        for w in workflows
    }


def _fetch_repo_runs(db: Session, github_user: str, repo_name: str, since: datetime) -> List[dict]:
    """List a repository's workflow runs created since ``since``."""
    owner, repo = repo_name.split("/", 1)
    headers = {
        "Authorization": f"token {user_tokens[github_user]}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }
    created_filter = f">={since.strftime('%Y-%m-%d')}"

    runs: List[dict] = []
    for page in range(1, MAX_PAGES + 1):
        # exclude_pull_requests drops a per-run array this module never reads.
        url = (
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/runs"
            f"?per_page={PER_PAGE}&page={page}&created={created_filter}"
            f"&exclude_pull_requests=true"
        )
        response = github_get(url, github_user, db, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
        if response.status_code != 200:
            raise RuntimeError(f"GitHub returned {response.status_code} for {repo_name}")

        batch = response.json().get("workflow_runs", [])
        runs.extend(batch)
        if len(batch) < PER_PAGE:
            break
    return runs


def _run_values(payload: dict, workflow: Workflow, filename: str) -> dict:
    created = _parse_github_time(payload.get("created_at"))
    started = _parse_github_time(payload.get("run_started_at"))
    updated = _parse_github_time(payload.get("updated_at"))
    conclusion = payload.get("conclusion")

    return {
        "workflow_id": workflow.workflow_id,
        "run_number": payload.get("run_number"),
        "run_attempt": payload.get("run_attempt"),
        "workflow_filename": filename,
        "workflow_name": workflow.workflow_name,
        "branch": payload.get("head_branch") or "",
        "event": payload.get("event"),
        "status": payload.get("status"),
        "conclusion": conclusion,
        "run_created_at": created,
        "run_started_at": started,
        "run_updated_at": updated,
        # Only a finished run has a meaningful duration; an in-flight run's
        # updated_at is just "a moment ago" and would understate the real time.
        "duration_seconds": _elapsed_seconds(started, updated) if conclusion else None,
        "queue_seconds": _elapsed_seconds(created, started),
        "html_url": payload.get("html_url"),
        "synced_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }


def _store_repo_runs(db: Session, project: Project, repo: Repo,
                     payloads: List[dict], workflow_files: Dict[str, Workflow]) -> None:
    """Insert or update the runs belonging to this project's workflows."""
    wanted = [payload.get("id") for payload in payloads if payload.get("id") is not None]
    if not wanted:
        return

    # One query for the whole batch rather than one per run, and the map is
    # updated as rows are added below. GitHub's listing shifts as new runs
    # start, so the same run id can appear on two consecutive pages; with
    # autoflush off, re-querying per payload cannot see the pending insert and
    # the duplicate reaches the unique constraint as an IntegrityError.
    known = {
        row.github_run_id: row
        for row in db.query(WorkflowRun).filter(
            WorkflowRun.project_id == project.project_id,
            WorkflowRun.repo_id == repo.repo_id,
            WorkflowRun.github_run_id.in_(wanted),
        ).all()
    }

    for payload in payloads:
        filename = (payload.get("path") or "").rsplit("/", 1)[-1]
        workflow = workflow_files.get(filename.lower())
        github_run_id = payload.get("id")
        if not workflow or github_run_id is None:
            continue

        values = _run_values(payload, workflow, filename)
        existing = known.get(github_run_id)
        if existing:
            # A re-run keeps its run id and gains an attempt, so the row is
            # updated in place rather than duplicated.
            for key, value in values.items():
                setattr(existing, key, value)
            continue

        row = WorkflowRun(
            project_id=project.project_id,
            repo_id=repo.repo_id,
            github_run_id=github_run_id,
            **values,
        )
        db.add(row)
        known[github_run_id] = row


def _purge_expired_runs(db: Session, project: Project, retention_cutoff: Optional[datetime]) -> None:
    """Drop runs past the account's *retention* horizon.

    Deliberately not the requested display window: those are different
    boundaries, and purging by the request would let a narrow view (``?days=1``,
    or just the 30-day default on a 90-day tier) permanently destroy history the
    tier is meant to keep. The GitHub fetch is bounded by the same request, so
    the deleted rows would never come back.

    ``None`` means unlimited retention — nothing is purged.

    Rows with no parseable ``run_created_at`` are swept too. They can never
    match a window query, so they are invisible to every metric; without this
    they would also never match a ``<`` comparison and would accumulate forever.
    """
    if retention_cutoff is None:
        return
    (
        db.query(WorkflowRun)
        .filter(
            WorkflowRun.project_id == project.project_id,
            or_(
                WorkflowRun.run_created_at < retention_cutoff,
                WorkflowRun.run_created_at.is_(None),
            ),
        )
        .delete(synchronize_session=False)
    )


def _sync_project_runs(db: Session, github_user: str, project: Project,
                       since: datetime) -> Optional[str]:
    """Refresh stored runs from GitHub. Returns an error message on failure."""
    workflow_files = _project_workflow_files(db, project)
    if not workflow_files:
        # Nothing to attribute runs to. Still a successful sync, so the cursor
        # advances and an empty project does not re-ask GitHub on every load.
        project.last_run_sync_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        return None

    repos = db.query(Repo).join(ProjectRepo).filter(ProjectRepo.project_id == project.project_id).all()
    try:
        for repo in repos:
            payloads = _fetch_repo_runs(db, github_user, repo.repo_name, since)
            _store_repo_runs(db, project, repo, payloads, workflow_files)
    except RateLimitExceeded as exc:
        db.rollback()
        return f"GitHub API rate limit reached: {exc}"
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        db.rollback()
        # The cursor is deliberately not advanced: claiming a sync happened when
        # it failed would hide stale data behind a fresh-looking timestamp.
        return f"Could not refresh runs from GitHub: {exc}"

    project.last_run_sync_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return None


def _is_stale(project: Project) -> bool:
    if project.last_run_sync_at is None:
        return True
    age = datetime.now(timezone.utc).replace(tzinfo=None) - project.last_run_sync_at
    return age > timedelta(minutes=_sync_interval_minutes())


def _percentile(sorted_values: List[int], fraction: float) -> int:
    """Nearest-rank percentile — no numpy, and exact for the small samples here.

    ``ceil`` rather than ``round``: Python rounds halves to even, which would
    make the p50 of a five-run sample the second value instead of the third.
    """
    rank = max(1, min(len(sorted_values), math.ceil(fraction * len(sorted_values))))
    return sorted_values[rank - 1]


def _duration_stats(runs: List[WorkflowRun]) -> Dict[str, Optional[int]]:
    durations = sorted(r.duration_seconds for r in runs if r.duration_seconds is not None)
    queues = [r.queue_seconds for r in runs if r.queue_seconds is not None]

    return {
        "avg_duration_seconds": round(sum(durations) / len(durations)) if durations else None,
        "p50_duration_seconds": _percentile(durations, 0.5) if durations else None,
        "p95_duration_seconds": _percentile(durations, 0.95) if durations else None,
        "avg_queue_seconds": round(sum(queues) / len(queues)) if queues else None,
    }


def _success_rate(runs: List[WorkflowRun]) -> Tuple[int, Optional[float]]:
    """Count of decided runs and the percentage of them that succeeded.

    ``None`` rather than ``0.0`` when nothing has been decided: "no data" and
    "everything failed" must not render identically.
    """
    decided = [r for r in runs if r.conclusion in _DECIDED_CONCLUSIONS]
    if not decided:
        return 0, None
    successes = sum(1 for r in decided if r.conclusion == _SUCCESS)
    return len(decided), round(successes / len(decided) * 100, 1)


def _trend(runs: List[WorkflowRun], window_days: int) -> List[TrendPoint]:
    """Daily buckets, oldest first, including days with no runs."""
    buckets: Dict[str, Dict[str, int]] = {}
    for run in runs:
        if not run.run_created_at:
            continue
        key = run.run_created_at.strftime("%Y-%m-%d")
        bucket = buckets.setdefault(key, {"total": 0, "success": 0, "failure": 0})
        bucket["total"] += 1
        if run.conclusion == _SUCCESS:
            bucket["success"] += 1
        elif run.conclusion in _FAILURE_CONCLUSIONS:
            bucket["failure"] += 1

    today = datetime.now(timezone.utc).date()
    days = min(window_days, 90)  # A chart wider than a quarter is unreadable.
    points: List[TrendPoint] = []
    for offset in range(days - 1, -1, -1):
        key = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        bucket = buckets.get(key, {"total": 0, "success": 0, "failure": 0})
        points.append(TrendPoint(date=key, **bucket))
    return points


def _actions_url(repo: Optional[str], filename: str) -> Optional[str]:
    """GitHub's Actions page for one workflow file, or None if it can't be built.

    Mirrors the frontend's ``buildGithubWorkflowUrl``: validate the repo shape
    and encode the filename rather than interpolating either one raw.
    """
    if not repo or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        return None
    return f"{GITHUB_WEB_URL}/{repo}/actions/workflows/{quote(filename, safe='')}"


def _newest_first(runs: List[WorkflowRun]) -> List[WorkflowRun]:
    return sorted(runs, key=lambda r: r.run_created_at or datetime.min, reverse=True)


def _repo_names(db: Session, project_id: int) -> Dict[int, str]:
    """repo_id -> "owner/repo" for the project's repositories."""
    repos = db.query(Repo).join(ProjectRepo).filter(ProjectRepo.project_id == project_id).all()
    return {repo.repo_id: repo.repo_name for repo in repos}


def _workflow_breakdown(runs: List[WorkflowRun], repo_names: Dict[int, str]) -> List[WorkflowBreakdown]:
    """One row per workflow file. Grouped by filename rather than display name:
    two different files may declare the same ``name:``, and merging them would
    both misreport their rates and make the row ambiguous to scope by.

    Always computed over the *unscoped* window so it can double as the
    navigation index — scoping it would collapse the list to the workflow
    already selected, leaving no way to switch to another one.
    """
    grouped: Dict[str, List[WorkflowRun]] = {}
    for run in runs:
        grouped.setdefault(run.workflow_filename, []).append(run)

    breakdown = []
    for filename, group in grouped.items():
        _, rate = _success_rate(group)
        stats = _duration_stats(group)
        latest = _newest_first(group)[0]
        repo = repo_names.get(latest.repo_id)
        breakdown.append(WorkflowBreakdown(
            workflow_name=latest.workflow_name or filename,
            workflow_filename=filename,
            total=len(group),
            success_rate=rate,
            avg_duration_seconds=stats["avg_duration_seconds"],
            actions_url=_actions_url(repo, filename),
        ))
    return sorted(breakdown, key=lambda b: b.total, reverse=True)


def _scoped_to_workflow(runs: List[WorkflowRun], workflow: Optional[str]) -> List[WorkflowRun]:
    """Narrow to one workflow file, matched case-insensitively.

    ``lower()`` rather than ``ilike``: this is an in-memory list, and workflow
    filenames routinely contain ``_``, which is a SQL LIKE wildcard.
    """
    if not workflow:
        return runs
    wanted = workflow.strip().lower()
    return [run for run in runs if (run.workflow_filename or "").lower() == wanted]


def _recent_runs(runs: List[WorkflowRun], repo_names: Dict[int, str],
                 only_failures: bool) -> List[RecentRun]:
    """The newest runs, so a user can click through to one on GitHub."""
    candidates = [r for r in runs if r.conclusion in _FAILURE_CONCLUSIONS] if only_failures else runs
    return [
        RecentRun(
            github_run_id=run.github_run_id,
            run_number=run.run_number,
            workflow_name=run.workflow_name or run.workflow_filename,
            repo=repo_names.get(run.repo_id),
            branch=run.branch,
            event=run.event,
            status=run.status,
            conclusion=run.conclusion,
            created_at=_utc_iso(run.run_created_at),
            duration_seconds=run.duration_seconds,
            html_url=run.html_url,
        )
        for run in _newest_first(candidates)[:RECENT_RUN_LIMIT]
    ]


def _retention_days(account: Optional[Account]) -> Optional[int]:
    """How long this project's runs are kept. ``None`` means forever.

    A project whose owning account row is missing falls back to the default
    window rather than crashing the panel — the tier helpers dereference the
    account, and a bare ``.first()`` can return None.
    """
    if account is None:
        return DEFAULT_WINDOW_DAYS
    return get_run_history_days(account)


def _window_days(retention_days: Optional[int], requested: Optional[int]) -> int:
    """Clamp the requested window to what the tier retains, and to a sane max.

    ``MAX_WINDOW_DAYS`` is not cosmetic: an unlimited tier applies no clamp, and
    a large enough ``days`` overflows the ``timedelta`` subtraction that derives
    the cutoff, which surfaces as a 500.
    """
    days = requested if requested and requested > 0 else DEFAULT_WINDOW_DAYS
    if retention_days is not None:
        days = min(days, retention_days)
    return min(days, MAX_WINDOW_DAYS)


@router.get(
    "/api/projects/{project_id}/build-metrics",
    response_model=BuildMetricsSummary,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "No access to this project"},
        404: {"description": "Project not found"},
    },
)
def get_project_build_metrics(
    project_id: int,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    days: Optional[int] = None,
    refresh: bool = False,
    only_failures: bool = False,
    workflow: Optional[str] = None,
):
    """Build metrics for a project, aggregated from stored workflow runs.

    Serves stored rows by default, so opening the panel is free however often it
    is done. A sync runs when the data is stale or ``refresh=true`` is passed;
    when that sync fails the stored numbers are still returned, flagged with
    ``sync_failed`` so the UI does not present them as fresh.

    ``only_failures`` narrows ``recent_runs`` alone. Every aggregate stays
    computed over the whole window — filtering the list to failures must not
    make the success rate read 0%.

    ``workflow`` (a delivered filename) scopes every figure to that one
    workflow, so a project can be read either as a whole or one workflow at a
    time. ``workflows`` is the exception and stays project-wide: it is the list
    the UI switches with, and scoping it would strand the user on whichever
    workflow they picked.
    """
    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    # Resolved by id, not by name: project names are not unique, and the
    # name-based lookup resolves a caller's own project first, so a member of
    # someone else's same-named project would be refused access they have.
    project = _require_project_access(db, project_id, github_user, None)

    account = db.query(Account).filter_by(user_id=project.user_id).first()
    retention_days = _retention_days(account)
    window_days = _window_days(retention_days, days)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=window_days)
    retention_cutoff = now - timedelta(days=retention_days) if retention_days is not None else None

    sync_message = None
    if refresh or _is_stale(project):
        sync_message = _sync_project_runs(db, github_user, project, cutoff)
        if sync_message is None:
            _purge_expired_runs(db, project, retention_cutoff)
            db.commit()

    window_runs = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.project_id == project_id, WorkflowRun.run_created_at >= cutoff)
        .all()
    )
    runs = _scoped_to_workflow(window_runs, workflow)

    repo_names = _repo_names(db, project_id)
    decided_runs, success_rate = _success_rate(runs)
    conclusion_counts: Dict[str, int] = {}
    for run in runs:
        key = run.conclusion or "in_progress"
        conclusion_counts[key] = conclusion_counts.get(key, 0) + 1

    return BuildMetricsSummary(
        project_id=project.project_id,
        project_name=project.project_name,
        window_days=window_days,
        last_synced=_utc_iso(project.last_run_sync_at),
        total_runs=len(runs),
        decided_runs=decided_runs,
        conclusion_counts=conclusion_counts,
        success_rate=success_rate,
        selected_workflow=workflow or None,
        trend=_trend(runs, window_days),
        workflows=_workflow_breakdown(window_runs, repo_names),
        recent_runs=_recent_runs(runs, repo_names, only_failures),
        sync_failed=sync_message is not None,
        sync_message=sync_message,
        **_duration_stats(runs),
    )
