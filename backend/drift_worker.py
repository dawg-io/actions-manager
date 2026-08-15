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

Cadence comes from the database, not the environment: global defaults live in
``drift_settings`` (edited by workspace admins in the GUI) and a project can
override the interval, or opt out entirely, via
``Project.drift_check_interval_minutes``. Everything is re-read per tick, so
changes apply without a restart.
"""

import asyncio
import contextlib
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Callable, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from models import Account, DriftSettings, Project

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
# whatever recheck interval an admin configures.
BACKOFF_MAX_MULTIPLIER = 32

# Per-project override meaning "never sweep this project".
INTERVAL_OFF = 0


def _backoff_multiplier(failure_count: int) -> int:
    """1x for a project with no recent failures, doubling per failure after
    the first, capped at BACKOFF_MAX_MULTIPLIER. Mirrors notification_worker's
    _backoff_delay shape."""
    return min(2 ** max(failure_count - 1, 0), BACKOFF_MAX_MULTIPLIER)


_DEFAULTS = SimpleNamespace(
    sweep_enabled=True,
    recheck_interval_minutes=DEFAULT_RECHECK_INTERVAL_MINUTES,
    batch_size=DEFAULT_BATCH_SIZE,
    poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
)


def get_settings(db: Session):
    """Global drift settings, or the built-in defaults when nobody has saved any.

    Read fresh on every tick rather than cached, so a change made in the GUI
    takes effect on the next sweep instead of at the next restart.
    """
    return db.query(DriftSettings).first() or _DEFAULTS


def _effective_interval(project: Project, default_minutes: int) -> int:
    """Minutes between checks for this project: its own override, else the global default."""
    configured = project.drift_check_interval_minutes
    return default_minutes if configured is None else configured


def _due_in_sql(db: Session, now: datetime, default_minutes: int):
    """Filter matching exactly the projects whose own interval says they are due.

    A single cutoff cannot express this once intervals vary per project. Using
    the shortest one in play looks like a safe superset, but the candidate set
    is capped: enough not-yet-due projects on a long interval sort ahead of a
    due one (oldest checked first) and fill the whole window, so the due project
    is never reached and the tick does no work at all — the same starvation
    INTERVAL_OFF projects are filtered out to avoid.

    So the cutoff is built per interval instead. Every timestamp is computed in
    Python and bound as a parameter, which keeps this identical on SQLite and
    PostgreSQL rather than relying on either one's date arithmetic. Only the
    intervals actually stored are considered, so this is a handful of terms.
    """
    def checked_before(minutes: int):
        return Project.last_drift_check_at <= now - timedelta(minutes=minutes)

    not_switched_off = or_(Project.drift_check_interval_minutes.is_(None),
                           Project.drift_check_interval_minutes != INTERVAL_OFF)

    clauses = [
        # Never checked: due whatever the interval, as long as it isn't "off".
        and_(Project.last_drift_check_at.is_(None), not_switched_off),
        # Inheriting the workspace default.
        and_(Project.drift_check_interval_minutes.is_(None), checked_before(default_minutes)),
    ]

    configured = (
        db.query(Project.drift_check_interval_minutes)
        .filter(Project.drift_check_interval_minutes.isnot(None))
        .filter(Project.drift_check_interval_minutes != INTERVAL_OFF)
        .distinct()
        .all()
    )
    for (minutes,) in configured:
        clauses.append(and_(Project.drift_check_interval_minutes == minutes,
                            checked_before(minutes)))

    return or_(*clauses)


def _stale_projects(db: Session, now: datetime, limit: int, default_minutes: int):
    """Projects due a re-check, never-checked first, then least-recently.

    Interval due-ness is decided in SQL (see _due_in_sql), so every candidate is
    genuinely due and a project on a long interval can never occupy a slot that
    belongs to one on a short interval. Projects set to INTERVAL_OFF are
    excluded there too.

    Only failure backoff is left to Python, because its multiplier is
    exponential in a column. That keeps the SCAN_MULTIPLIER window doing what it
    always did — absorbing candidates that turn out not to be actionable, so a
    project in backoff, like one with no usable token, cannot block the projects
    behind it.
    """
    candidates = (
        db.query(Project)
        .filter(_due_in_sql(db, now, default_minutes))
        .order_by(Project.last_drift_check_at.is_(None).desc(),
                  Project.last_drift_check_at.asc())
        .limit(limit)
        .all()
    )

    def _due(project: Project) -> bool:
        if project.last_drift_check_at is None:
            return True
        interval_minutes = _effective_interval(project, default_minutes)
        multiplier = _backoff_multiplier(project.drift_check_failure_count or 0)
        # SQLite drops tzinfo on round-trip, so last_drift_check_at may come
        # back naive even though `now` is timezone-aware — normalize both to
        # naive before comparing.
        due_cutoff = (now - timedelta(minutes=interval_minutes * multiplier)).replace(tzinfo=None)
        checked_at = project.last_drift_check_at.replace(tzinfo=None) if project.last_drift_check_at.tzinfo else project.last_drift_check_at
        return checked_at <= due_cutoff

    return [project for project in candidates if _due(project)]


# Shown to the user beside the last-checked time. Without it a skipped project
# is indistinguishable from a forgotten one: the timestamp simply stops moving
# and nothing says why.
NO_CREDENTIAL_REASON = (
    "Automatic drift checks are paused: this project's owner has no saved "
    "GitHub token. Sign out and sign back in to store one, or save a personal "
    "access token. Check Now still works."
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
    settings = get_settings(db)
    if not settings.sweep_enabled:
        return 0

    from workflows import run_project_drift_check

    now = now or datetime.now(timezone.utc)
    batch_size = settings.batch_size

    checked = 0
    for project in _stale_projects(db, now, batch_size * SCAN_MULTIPLIER,
                                   settings.recheck_interval_minutes):
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
    loop = asyncio.get_event_loop()
    interval = poll_interval_seconds or DEFAULT_POLL_INTERVAL_SECONDS
    while True:
        await asyncio.sleep(interval)
        try:
            db = session_factory()
            try:
                # The drift check does blocking `requests` I/O; running it
                # directly here would stall every other request sharing this
                # process's event loop.
                await loop.run_in_executor(None, sweep_projects_for_drift, db)
                # Re-read each tick so an admin changing the cadence in the GUI
                # doesn't have to wait for a restart. An explicit argument
                # (tests) still wins over whatever is stored. The first sleep
                # uses the default, because reading it earlier would touch the
                # database before the loop is known to be staying alive.
                if poll_interval_seconds is None:
                    interval = get_settings(db).poll_interval_seconds
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
