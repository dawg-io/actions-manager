"""
Campaign notification event emission (issue #1794, part of #1789).

Hooks into the existing campaign-creation and PR-status-refresh code paths
in workflows.py — no new scheduler. Persists a last-known campaign status
snapshot (campaign_status is otherwise computed live on every read) to
detect the one-time open -> terminal transition, and emits
campaign_pr.merged/closed directly from the existing per-PR
GitHub-state-refresh transition check.

Scope note: campaign.updated (repo/workflow/title/merge-behavior edits) and
an explicit campaign.closed action are intentionally NOT implemented here —
this codebase has no campaign-editing or explicit-close endpoint today;
campaigns are immutable creation records and "closed" only happens
implicitly via constituent PR states. Add these event types if/when an
editing feature ships.
"""

from typing import Dict

from sqlalchemy.orm import Session

from models import Project, ProjectPRCampaign, ProjectPullRequest
from notification_dispatch import emit_notification_event


def record_campaign_opened(db: Session, project: Project, campaign: ProjectPRCampaign,
                            results: Dict[str, dict]) -> None:
    """Emit one campaign.opened summary (never one email per repository), plus
    campaign.partially_failed and per-repo campaign_pr.failed when creation
    failures occurred alongside successes. Reads the full per-repo results
    dict, including entries that were never persisted as PR rows."""
    created = [
        key for key, result in results.items()
        if isinstance(result, dict) and result.get("status") in ("pr_created", "pr_updated")
    ]
    failed = {
        key: result for key, result in results.items()
        if isinstance(result, dict) and result.get("status") not in ("pr_created", "pr_updated")
    }

    dedup_key = f"campaign.opened:{project.project_id}:{campaign.campaign_id}"
    emit_notification_event(db, project.project_id, "campaign.opened", dedup_key, {
        "project_name": project.project_name,
        "campaign_id": campaign.campaign_id,
        "created_count": len(created),
        "failed_count": len(failed),
        "total_count": len(created) + len(failed),
    })

    if failed and created:
        dedup_key = f"campaign.partially_failed:{project.project_id}:{campaign.campaign_id}"
        emit_notification_event(db, project.project_id, "campaign.partially_failed", dedup_key, {
            "project_name": project.project_name,
            "campaign_id": campaign.campaign_id,
            "failed_repos": [{"repo_branch": key, "error": result.get("error")} for key, result in failed.items()],
        })

    for repo_branch, result in failed.items():
        dedup_key = f"campaign_pr.failed:{project.project_id}:{campaign.campaign_id}:{repo_branch}"
        emit_notification_event(db, project.project_id, "campaign_pr.failed", dedup_key, {
            "project_name": project.project_name,
            "campaign_id": campaign.campaign_id,
            "repo_branch": repo_branch,
            "error": result.get("error"),
        })

    db.commit()


def record_campaign_pr_transition(db: Session, pr: ProjectPullRequest, previous_state: str, new_state: str) -> None:
    """Emit campaign_pr.merged/closed when an individual PR transitions out of 'open'."""
    if pr.campaign_id is None or previous_state != "open" or new_state not in ("merged", "closed"):
        return
    event_type = "campaign_pr.merged" if new_state == "merged" else "campaign_pr.closed"
    dedup_key = f"{event_type}:{pr.project_id}:{pr.campaign_id}:{pr.pr_id}"
    emit_notification_event(db, pr.project_id, event_type, dedup_key, {
        "campaign_id": pr.campaign_id,
        "repo_name": pr.repo_name,
        "pr_number": pr.pr_number,
        "pr_url": pr.pr_url,
    })
    db.commit()


def record_campaign_status_transition(db: Session, project_id: int, project_name: str,
                                       campaign: ProjectPRCampaign, new_status: str,
                                       open_count: int, merged_count: int, closed_count: int) -> None:
    """Diff a campaign's newly-computed status against its persisted last-known
    status; emit one campaign.completed summary on the first open -> terminal
    transition. PR states are one-way (merged/closed never revert to open), so
    this fires at most once per campaign.

    Flushes (does not commit) — the caller (get_project_pr_campaigns) commits
    once after processing every campaign in the response, rather than once
    per campaign, to avoid mid-loop expire_on_commit re-fetches and to keep
    the notification_events.dedup_key race window as small as possible.
    """
    if campaign.last_known_status not in (None, "open") or new_status == "open":
        campaign.last_known_status = new_status
        return

    dedup_key = f"campaign.completed:{project_id}:{campaign.campaign_id}"
    emit_notification_event(db, project_id, "campaign.completed", dedup_key, {
        "project_name": project_name,
        "campaign_id": campaign.campaign_id,
        "status": new_status,
        "open_count": open_count,
        "merged_count": merged_count,
        "closed_count": closed_count,
    })
    campaign.last_known_status = new_status
    db.flush()
