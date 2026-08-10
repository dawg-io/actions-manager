"""
Drift notification event emission (issue #1793, part of #1789).

Hooks into the existing on-demand drift-check endpoint in workflows.py — no
new scheduler. Diffs newly-computed per-workflow drift state against the
last persisted WorkflowDriftState to detect transitions, and writes
deduplicated notification_events for drift.detected / drift.resolved /
drift.check_failed.

Known v1 limitation: since drift is only checked when something calls the
project drift endpoint, a drifted workflow won't generate a notification
until that endpoint is called again — freshness is bounded by existing call
cadence, not a new schedule.
"""

import hashlib
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from models import WorkflowDriftState, Project, Workflow, Repo
from notification_dispatch import emit_notification_event


def _content_hash(detail) -> str:
    raw = f"{detail.has_drift}:{detail.github_sha or ''}:{detail.actionsmanager_sha or ''}:{detail.message}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _get_or_create_state(db: Session, project_id: int, workflow_id: int, repo_id: int,
                         branch: str = "") -> WorkflowDriftState:
    branch = branch or ""
    state = (
        db.query(WorkflowDriftState)
        .filter(
            WorkflowDriftState.workflow_id == workflow_id,
            WorkflowDriftState.repo_id == repo_id,
            WorkflowDriftState.branch == branch,
        )
        .first()
    )
    if state is None:
        state = WorkflowDriftState(project_id=project_id, workflow_id=workflow_id, repo_id=repo_id,
                                   branch=branch, has_drift=False)
        db.add(state)
        db.flush()
    return state


def record_drift_transitions(db: Session, project: Project, details: List) -> None:
    """Diff newly-computed WorkflowDriftDetail rows against persisted state,
    emit drift.detected/drift.resolved events on transitions, and persist
    the new state either way."""
    now = datetime.now(timezone.utc)
    for detail in details:
        if detail.repo_id is None:
            continue  # can't build a stable identity without a repo

        if getattr(detail, "check_failed", False):
            # The check didn't complete, so has_drift is meaningless here.
            # Persisting it would overwrite a real "drifted" with "clean" and
            # emit drift.resolved for a workflow that is still drifted — the
            # previous behaviour whenever GitHub rate-limited or the token
            # expired. Leave the last known state alone.
            continue

        branch = getattr(detail, "branch", "") or ""
        state = _get_or_create_state(db, project.project_id, detail.workflow_id, detail.repo_id, branch)
        content_hash = _content_hash(detail)

        # The branch is part of every dedup key: drift appearing on a second
        # branch is its own event, not a duplicate of the first branch's.
        if detail.has_drift and not state.has_drift:
            state.drift_cycle_count += 1
            dedup_key = (
                f"drift.detected:{project.project_id}:{detail.repo_id}:{detail.workflow_id}:"
                f"{branch}:{content_hash}:{state.drift_cycle_count}"
            )
            emit_notification_event(db, project.project_id, "drift.detected", dedup_key, {
                "project_name": project.project_name,
                "repo": detail.repo,
                "branch": branch,
                "workflow_name": detail.workflow_name,
                "message": detail.message,
            })
        elif not detail.has_drift and state.has_drift:
            dedup_key = (
                f"drift.resolved:{project.project_id}:{detail.repo_id}:{detail.workflow_id}:"
                f"{branch}:{content_hash}:{state.drift_cycle_count}"
            )
            emit_notification_event(db, project.project_id, "drift.resolved", dedup_key, {
                "project_name": project.project_name,
                "repo": detail.repo,
                "branch": branch,
                "workflow_name": detail.workflow_name,
            })

        state.has_drift = detail.has_drift
        state.content_hash = content_hash
        # Kept so the drift panel can render this row without calling GitHub.
        state.github_sha = detail.github_sha
        state.deleted_in_github = bool(getattr(detail, "deleted_in_github", False))
        state.last_checked_at = now

    db.commit()


def recompute_project_drift_summary(db: Session, project: Project) -> None:
    """Refresh the cached projects.drift_* columns from persisted per-workflow state.

    The project list renders its drift badge from these columns while the
    project page renders from WorkflowDriftState, so the two must not diverge.

    ponytail: writes the columns directly rather than reusing workflows.py's
    _cache_project_drift_summary — workflows.py already imports this module, so
    calling back into it would be a circular import.
    """
    drift_count = (
        db.query(WorkflowDriftState)
        .filter(
            WorkflowDriftState.project_id == project.project_id,
            WorkflowDriftState.has_drift.is_(True),
        )
        .count()
    )
    project.drift_status = "drifted" if drift_count else "clean"
    project.drift_count = drift_count
    project.last_drift_check_at = datetime.now(timezone.utc)
    project.drift_error_summary = None
    # This path only runs from a real answer ("drifted" or "clean"), never
    # check_failed, so it must reset the sweep's backoff streak the same way
    # workflows.py's _cache_project_drift_summary does.
    project.drift_check_failure_count = 0
    db.commit()


def clear_workflow_drift(db: Session, project: Project, workflow_id: int,
                         repo_name: Optional[str] = None,
                         branch: Optional[str] = None) -> int:
    """Mark persisted drift resolved for a workflow, optionally scoped to one repo/branch.

    For actions that resolve drift as a side effect (adopting GitHub's version,
    restoring the managed version, merging a fix PR, syncing). Without this the
    caches keep claiming drift until someone re-opens the project and triggers
    a live check, so the banner shows drift that is already fixed.

    Clears from known intent rather than re-checking GitHub, so no extra API
    calls. Returns the number of rows cleared.

    ``branch`` matters as much as ``repo_name``: a resolution writes to one
    branch, so clearing every branch's row would report the workflow clean
    while the branches nobody touched are still drifted.
    """
    states = (
        db.query(WorkflowDriftState)
        .filter(
            WorkflowDriftState.workflow_id == workflow_id,
            WorkflowDriftState.has_drift.is_(True),
        )
    )
    if repo_name:
        repo = db.query(Repo).filter(Repo.repo_name == repo_name.strip()).first()
        if repo is None:
            # Unknown repo name can't match any row; clearing everything for the
            # workflow instead would wrongly resolve drift in its other repos.
            recompute_project_drift_summary(db, project)
            return 0
        states = states.filter(WorkflowDriftState.repo_id == repo.repo_id)
    if branch:
        states = states.filter(WorkflowDriftState.branch == branch)
    states = states.all()

    if not states:
        # Still recompute: a caller may have deleted rows (cascade) rather than
        # flipping them, which changes the project's count.
        recompute_project_drift_summary(db, project)
        return 0

    workflow = db.query(Workflow).filter(Workflow.workflow_id == workflow_id).first()
    workflow_name = workflow.workflow_name if workflow else str(workflow_id)
    now = datetime.now(timezone.utc)

    for state in states:
        repo = db.query(Repo).filter(Repo.repo_id == state.repo_id).first()
        # Same dedup shape as record_drift_transitions so a resolution recorded
        # here can't double-notify with one recorded by a later live check.
        dedup_key = (
            f"drift.resolved:{project.project_id}:{state.repo_id}:{state.workflow_id}:"
            f"{state.branch or ''}:{state.content_hash or ''}:{state.drift_cycle_count}"
        )
        emit_notification_event(db, project.project_id, "drift.resolved", dedup_key, {
            "project_name": project.project_name,
            "repo": repo.repo_name if repo else "",
            "branch": state.branch or "",
            "workflow_name": workflow_name,
        })
        state.has_drift = False
        state.last_checked_at = now

    # Flush before recomputing: the summary re-counts drifted rows with a
    # query, which would not see these pending updates under autoflush=False.
    db.flush()
    recompute_project_drift_summary(db, project)
    return len(states)


def drop_workflow_drift(db: Session, project: Project, workflow_id: int) -> None:
    """Delete persisted drift for a workflow removed from a project.

    Deleting the Workflow row cascades these away, but a workflow still linked
    to other projects is not deleted — its rows for *this* project would
    survive and keep inflating the project's drift count.
    """
    db.query(WorkflowDriftState).filter(
        WorkflowDriftState.project_id == project.project_id,
        WorkflowDriftState.workflow_id == workflow_id,
    ).delete(synchronize_session=False)
    db.commit()
    recompute_project_drift_summary(db, project)


def record_drift_check_failed(db: Session, project: Project, error: str) -> None:
    """Emit a project-scoped drift.check_failed event, deduplicated on the error content
    so repeated identical failures don't spam but a new failure reason still notifies."""
    content_hash = hashlib.sha256((error or "").encode("utf-8")).hexdigest()[:16]
    dedup_key = f"drift.check_failed:{project.project_id}:{content_hash}"
    emit_notification_event(db, project.project_id, "drift.check_failed", dedup_key, {
        "project_name": project.project_name,
        "error": error,
    })
    db.commit()
