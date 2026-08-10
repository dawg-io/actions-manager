"""
Drift reconciliation sweep.

Drift state only ever changed when a human clicked: "Check now", opening a
workflow's drift detail, or resolving a drift. Nothing ran on its own, so a
project could show "in sync" indefinitely while GitHub had drifted. This is the
automatic trigger that was missing.

An in-process asyncio polling loop — no Celery/APScheduler/Redis — started at
FastAPI startup, matching notification_worker.py. Same single-instance
assumption: this app has no multi-replica deployment today, so no row locking.
Two instances would duplicate checks, which wastes rate limit but cannot
corrupt state.

Affordable only because of the conditional-fetch work: an unchanged branch
answers 304, which does not count against the rate limit, and branch recency is
cached by head SHA. Sweeping a quiet project costs roughly one conditional call
per repo, which is why polling every project on a timer is now reasonable when
it would not have been before.
"""

import asyncio
import contextlib
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import Account, Project

DEFAULT_POLL_INTERVAL_SECONDS = 60
DEFAULT_RECHECK_INTERVAL_MINUTES = 15
DEFAULT_BATCH_SIZE = 5

# How many candidates to look at to fill one batch. Projects whose owner has no
# usable token are skipped without advancing their cursor, so they stay at the
# head of the queue forever; without scanning past them they would starve every
# project behind them and the sweep would silently stop working.
SCAN_MULTIPLIER = 10

# A project stuck returning check_failed is retried less and less often as
# failures accumulate, instead of at the full recheck interval forever. The
# cap is a multiplier rather than an absolute number so it scales with
# whatever DRIFT_RECHECK_INTERVAL_MINUTES an operator configures.
BACKOFF_MAX_MULTIPLIER = 32


def _backoff_multiplier(failure_count: int) -> int:
    """1x for a project with no recent failures, doubling per failure after
    the first, capped at BACKOFF_MAX_MULTIPLIER. Mirrors notification_worker's
    _backoff_delay shape."""
    return min(2 ** max(failure_count - 1, 0), BACKOFF_MAX_MULTIPLIER)


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def sweep_enabled() -> bool:
    return os.getenv("DRIFT_SWEEP_ENABLED", "true").strip().lower() not in ("false", "0", "no")


def _stale_projects(db: Session, now: datetime, limit: int):
    """Projects due a re-check, never-checked first, then least-recently.

    The SQL filter uses the un-backed-off cutoff, which is always a superset
    of what backoff would allow — a project failing that cutoff can never pass
    a longer, backed-off one either. The stricter, per-project backoff check
    runs after, in Python, over this already-bounded candidate set (bounded by
    SCAN_MULTIPLIER for the same reason a token-less project doesn't starve
    the queue: a project in backoff must not block the ones behind it).
    """
    interval_minutes = _env_int("DRIFT_RECHECK_INTERVAL_MINUTES", DEFAULT_RECHECK_INTERVAL_MINUTES)
    cutoff = now - timedelta(minutes=interval_minutes)
    candidates = (
        db.query(Project)
        .filter(or_(Project.last_drift_check_at.is_(None),
                    Project.last_drift_check_at <= cutoff))
        .order_by(Project.last_drift_check_at.is_(None).desc(),
                  Project.last_drift_check_at.asc())
        .limit(limit)
        .all()
    )

    def _due(project: Project) -> bool:
        if project.last_drift_check_at is None:
            return True
        multiplier = _backoff_multiplier(project.drift_check_failure_count or 0)
        if multiplier <= 1:
            return True  # already satisfied by the SQL cutoff above
        # SQLite drops tzinfo on round-trip, so last_drift_check_at may come
        # back naive even though `now` is timezone-aware — normalize both to
        # naive before comparing.
        backoff_cutoff = (now - timedelta(minutes=interval_minutes * multiplier)).replace(tzinfo=None)
        checked_at = project.last_drift_check_at.replace(tzinfo=None) if project.last_drift_check_at.tzinfo else project.last_drift_check_at
        return checked_at <= backoff_cutoff

    return [project for project in candidates if _due(project)]


# Shown to the user beside the last-checked time. Without it a skipped project
# is indistinguishable from a forgotten one: the timestamp simply stops moving
# and nothing says why.
NO_CREDENTIAL_REASON = (
    "Automatic drift checks are paused: this project's owner has no saved "
    "GitHub token. Save a personal access token, or use Check Now."
)


def _checkable_owner(db: Session, project: Project) -> Optional[str]:
    """The project owner's username, or None if they have no usable credential.

    Resolved through the normal credential store, which prefers a saved PAT and
    falls back to an in-memory OAuth session token. A worker has no request
    context, so the store's per-request identity guard does not apply here. The
    token itself is discarded — the drift check resolves it again by username;
    this only answers "is this project checkable at all".
    """
    from auth import user_tokens

    owner = db.query(Account).filter(Account.user_id == project.user_id).first()
    if not owner or not owner.github_user:
        return None
    return owner.github_user if user_tokens.get(owner.github_user) else None


def _record_skip(db: Session, project: Project) -> None:
    """Say why a project was passed over, without pretending it was checked.

    ``last_drift_check_at`` and ``drift_status`` are both left alone on purpose.
    Advancing the timestamp would make an unchecked project read as freshly
    verified, and overwriting the status would throw away a real previous
    answer — a project that genuinely was drifting still is.
    """
    if project.drift_error_summary == NO_CREDENTIAL_REASON:
        return  # already recorded; don't write on every tick
    project.drift_error_summary = NO_CREDENTIAL_REASON
    db.commit()


def sweep_projects_for_drift(db: Session, now: Optional[datetime] = None) -> int:
    """Re-check up to one batch of stale projects. Returns how many were checked."""
    if not sweep_enabled():
        return 0

    from workflows import run_project_drift_check

    now = now or datetime.now(timezone.utc)
    batch_size = _env_int("DRIFT_SWEEP_BATCH_SIZE", DEFAULT_BATCH_SIZE)

    checked = 0
    for project in _stale_projects(db, now, batch_size * SCAN_MULTIPLIER):
        if checked >= batch_size:
            break

        username = _checkable_owner(db, project)
        if username is None:
            # Deliberately leaves last_drift_check_at alone: claiming a check
            # happened when none did is exactly the stale-"clean" problem this
            # feature exists to prevent. Record the reason so the staleness is
            # explained rather than silent.
            _record_skip(db, project)
            continue

        try:
            run_project_drift_check(db, username, project)
            checked += 1
        except Exception as exc:  # noqa: BLE001 - one bad project must not stop the sweep
            print(f"⚠️ Drift sweep failed for project {project.project_id}: {exc}",
                  file=sys.stderr, flush=True)
            db.rollback()

    return checked


async def drift_worker_loop(
    session_factory: Callable[[], Session],
    poll_interval_seconds: Optional[int] = None,
) -> None:
    """Sleep-then-poll loop. Sleeps first so a task cancelled shortly after
    startup (e.g. a short-lived test lifespan) never touches the database."""
    interval = poll_interval_seconds or _env_int("DRIFT_SWEEP_POLL_SECONDS",
                                                 DEFAULT_POLL_INTERVAL_SECONDS)
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(interval)
        try:
            db = session_factory()
            try:
                # The drift check does blocking `requests` I/O; running it
                # directly here would stall every other request sharing this
                # process's event loop.
                await loop.run_in_executor(None, sweep_projects_for_drift, db)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 - a bad iteration must never kill the worker
            print(f"⚠️ Drift sweep iteration failed: {exc}", file=sys.stderr, flush=True)


def start_drift_worker(session_factory: Callable[[], Session]) -> asyncio.Task:
    return asyncio.create_task(drift_worker_loop(session_factory))


async def stop_drift_worker(task: asyncio.Task) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
