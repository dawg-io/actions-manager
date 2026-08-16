"""
Campaign rollback for ActionsManager.

Generates the inverse of a merged PR campaign and delivers it as a new campaign
through the same PR-based path the original went out on:

* POST /api/campaign-rollback-preview  – proposed inverse diff, for review
* POST /api/campaign-rollback          – open the rollback campaign

A campaign stores no patch and no prior content — it delivers whole file contents
read live from the database, and its creation-time snapshot records only SHAs and
hashes. So the inverse is not derived from ActionsManager state at all. It comes
off the merged pull request itself, which is authoritative:

1. ``GET /pulls/{n}``                → ``merge_commit_sha``
2. ``GET /commits/{merge_sha}``      → ``parents[0].sha``, the target branch tip
                                       immediately before the merge
3. ``GET /pulls/{n}/files``          → the exact paths the PR touched
4. per path, the content at ``parents[0].sha`` → restore it, or delete the path
   when it did not exist there

That is ``git revert -m 1`` semantics. It needs no path derivation from workflow
names (``use_prefix`` may have been flipped since), no snapshot (campaigns
predating it roll back too), and no version history for custom files or
CODEOWNERS (there is none), and it is correct for squash merges.

Where an inverse cannot be computed the whole target is flagged non-invertible
with the reason, and no PR is opened for it — never silently skipped or guessed.
"""

import base64
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

import workflows as wf
from campaign_notifications import record_campaign_opened
from database import get_db
from github_api_tracker import RateLimitExceeded, github_get
from models import Project, ProjectPRCampaign, ProjectPullRequest, ProjectWorkflow, Workflow

router = APIRouter()

ROLLBACK_AM_ACTIONS = ("revert", "keep")

# GitHub file statuses whose inverse is unambiguous. "renamed", "copied" and
# "changed" are deliberately excluded — ActionsManager never produces them, and
# guessing at their inverse is exactly what this feature must not do.
_INVERTIBLE_STATUSES = ("added", "modified", "removed")

_WORKFLOWS_DIR = ".github/workflows/"

_PAGE_SIZE = 100
# 3,000 files. A campaign delivers a handful of workflow files per repo; a PR
# past this is not something ActionsManager created.
_MAX_FILE_PAGES = 30

_LEGACY_DETAIL = (
    "This campaign predates campaign tracking and has no campaign record, "
    "so it cannot be rolled back."
)


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class RollbackPreviewRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    # The string form the UI holds ("campaign-12"); a bare integer also works.
    campaign_id: str


class RollbackCreateRequest(RollbackPreviewRequest):
    am_action: str = "keep"
    campaign_name: Optional[str] = Field(default=None, max_length=200)
    campaign_description: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("am_action")
    @classmethod
    def _known_action(cls, value: str) -> str:
        if value not in ROLLBACK_AM_ACTIONS:
            raise ValueError(f"am_action must be one of {', '.join(ROLLBACK_AM_ACTIONS)}")
        return value

    @field_validator("campaign_name", "campaign_description")
    @classmethod
    def _blank_is_unset(cls, value: Optional[str]) -> Optional[str]:
        return (value or "").strip() or None


# --------------------------------------------------------------------------- #
# GitHub reads                                                                #
# --------------------------------------------------------------------------- #


def _gh_headers(token: str) -> dict:
    return {
        "Accept": wf.ACCEPT_HEADER,
        "X-GitHub-Api-Version": wf.X_API_VERSION,
        "Authorization": f"token {token}",
    }


def _get(url: str, user: str, db: Session, headers: dict, **params):
    return github_get(
        url, user, db,
        headers=headers,
        params=params or None,
        timeout=wf.GITHUB_TIMEOUT_SECONDS,
    )


def _repo_url(repo_name: str) -> str:
    return f"{wf.GITHUB_API_URL}/repos/{repo_name}"


def _pre_merge_base_sha(repo_name: str, pr_number: int, user: str, db: Session,
                        headers: dict) -> tuple:
    """(sha, reason) — the target branch's tip immediately before this PR merged.

    The merge commit's first parent, so a squash merge resolves the same way a
    merge commit does.
    """
    resp = _get(f"{_repo_url(repo_name)}/pulls/{pr_number}", user, db, headers)
    if resp.status_code != 200:
        return None, (f"GitHub returned HTTP {resp.status_code} for pull request "
                      f"#{pr_number}, so the pre-campaign state is unknown.")
    pr_data = resp.json() or {}
    if not pr_data.get("merged"):
        return None, f"GitHub reports pull request #{pr_number} as not merged."

    merge_sha = pr_data.get("merge_commit_sha")
    if not merge_sha:
        return None, (f"Pull request #{pr_number} has no merge commit recorded on "
                      "GitHub, so the pre-campaign state is unknown.")

    commit_resp = _get(f"{_repo_url(repo_name)}/commits/{merge_sha}", user, db, headers)
    if commit_resp.status_code != 200:
        return None, (f"The merge commit for pull request #{pr_number} could not be read "
                      f"on GitHub (HTTP {commit_resp.status_code}), so the pre-campaign "
                      "state is unknown.")
    parents = (commit_resp.json() or {}).get("parents") or []
    if not parents or not parents[0].get("sha"):
        return None, (f"The merge commit for pull request #{pr_number} has no parent "
                      "commit, so there is no pre-campaign state to restore.")
    return parents[0]["sha"], None


def _pr_changed_files(repo_name: str, pr_number: int, user: str, db: Session,
                      headers: dict) -> tuple:
    """(files, reason) — every file the PR touched, following pagination."""
    files: List[dict] = []
    for page in range(1, _MAX_FILE_PAGES + 1):
        resp = _get(f"{_repo_url(repo_name)}/pulls/{pr_number}/files", user, db, headers,
                    per_page=_PAGE_SIZE, page=page)
        if resp.status_code != 200:
            return None, (f"The files changed by pull request #{pr_number} could not be "
                          f"read on GitHub (HTTP {resp.status_code}).")
        batch = resp.json() or []
        files.extend(batch)
        if len(batch) < _PAGE_SIZE:
            return files, None
    return None, (f"Pull request #{pr_number} changed more files than a rollback "
                  "can process.")


def _content_at(repo_name: str, path: str, ref: str, user: str, db: Session,
                headers: dict) -> tuple:
    """(blob_sha, text, status) where status is 'ok', 'absent', or a reason string."""
    resp = _get(f"{_repo_url(repo_name)}/contents/{path}", user, db, headers, ref=ref)
    if resp.status_code == 404:
        return None, None, "absent"
    if resp.status_code != 200:
        return None, None, (f"{path} could not be read at {ref[:7]} "
                            f"(HTTP {resp.status_code}).")

    payload = resp.json() or {}
    encoded = payload.get("content")
    if payload.get("encoding") != "base64" or not encoded:
        return None, None, (f"{path} is too large to read through the GitHub contents "
                            "API, so its previous content cannot be restored.")
    try:
        text = base64.b64decode(encoded).decode("utf-8")
    except ValueError:  # covers UnicodeDecodeError and a malformed base64 payload
        return None, None, (f"{path} is not a UTF-8 text file, so its previous content "
                            "cannot be restored through the GitHub contents API.")
    return payload.get("sha"), text, "ok"


# --------------------------------------------------------------------------- #
# Inverse computation                                                         #
# --------------------------------------------------------------------------- #


def _current_state_reason(path: str, entry_status: str, entry_sha: Optional[str],
                          current_sha: Optional[str], current_status: str,
                          branch: str) -> Optional[str]:
    """Why this path can no longer be inverted, or None when it still can.

    The campaign's contribution is only safely reversible while the path still
    holds exactly what the campaign left there. Anything else means somebody
    changed it afterwards, and reverting would discard that change.
    """
    if current_status not in ("ok", "absent"):
        return current_status

    if entry_status == "removed":
        if current_status != "absent":
            return (f"{path} was deleted by this campaign but exists on {branch} "
                    "again — rolling back would discard that change.")
        return None

    if current_status == "absent":
        return (f"{path} was removed from {branch} after this campaign merged — "
                "rolling back would discard that change.")
    if current_sha != entry_sha:
        return (f"{path} changed on {branch} after this campaign merged — "
                "rolling back would discard that change.")
    return None


def _invert_one_file(repo_name: str, entry: dict, branch: str, base_sha: str,
                     user: str, db: Session, headers: dict) -> tuple:
    """(file dict, reason) for a single path the campaign's PR touched."""
    path = entry.get("filename") or ""
    entry_status = entry.get("status") or "changed"
    if entry_status not in _INVERTIBLE_STATUSES:
        return None, (f"{path} was {entry_status} by this campaign; its inverse is "
                      "not computed automatically.")

    current_sha, current_text, current_status = _content_at(
        repo_name, path, branch, user, db, headers
    )
    reason = _current_state_reason(
        path, entry_status, entry.get("sha"), current_sha, current_status, branch
    )
    if reason:
        return None, reason

    _before_sha, previous_text, previous_status = _content_at(
        repo_name, path, base_sha, user, db, headers
    )
    if previous_status == "absent":
        # The campaign created this path, so its inverse is to remove it.
        return {"path": path, "action": "delete",
                "before": current_text or "", "after": ""}, None
    if previous_status != "ok":
        return None, previous_status
    return {"path": path, "action": "restore",
            "before": current_text or "", "after": previous_text}, None


def _invert_one_pr(pr: ProjectPullRequest, user: str, db: Session, headers: dict) -> dict:
    """The proposed inverse of one merged campaign PR, or why there isn't one."""
    target = {
        "repo_name": pr.repo_name,
        "target_branch": pr.target_branch,
        "pr_number": pr.pr_number,
        "pr_url": pr.pr_url,
        "workflow_names": pr.workflow_names,
        "invertible": False,
        "reason": None,
        "files": [],
    }

    base_sha, reason = _pre_merge_base_sha(pr.repo_name, pr.pr_number, user, db, headers)
    if reason:
        target["reason"] = reason
        return target

    changed, reason = _pr_changed_files(pr.repo_name, pr.pr_number, user, db, headers)
    if reason:
        target["reason"] = reason
        return target

    files = []
    for entry in changed:
        inverted, reason = _invert_one_file(
            pr.repo_name, entry, pr.target_branch, base_sha, user, db, headers
        )
        if reason:
            # Flagged per repo: one unrevertable path makes the whole target
            # unsafe, and half-reverting a repo is its own kind of guessing.
            target["reason"] = reason
            return target
        files.append(inverted)

    if not files:
        target["reason"] = "This pull request changed no files, so there is nothing to roll back."
        return target

    target["invertible"] = True
    target["files"] = files
    return target


def compute_inverse(db: Session, campaign_id: int, user: str, token: str) -> List[dict]:
    """One entry per merged PR in the campaign, invertible or flagged.

    PR states are refreshed from GitHub first: a campaign whose PRs merged since
    the last refresh would otherwise present nothing to roll back.
    """
    headers = _gh_headers(token)
    prs = db.query(ProjectPullRequest).filter(
        ProjectPullRequest.campaign_id == campaign_id
    ).order_by(ProjectPullRequest.repo_name, ProjectPullRequest.target_branch).all()

    merged = []
    for pr in prs:
        pr.pr_state = wf._resolve_pr_state(pr, True, user, token, db)
        if pr.pr_state == "merged":
            merged.append(pr)

    return [_invert_one_pr(pr, user, db, headers) for pr in merged]


# --------------------------------------------------------------------------- #
# Delivery                                                                    #
# --------------------------------------------------------------------------- #


def _deliver_one_target(target: dict, project: Project, campaign_meta: dict,
                        user: str, db: Session, headers: dict,
                        stamps: dict) -> tuple:
    """Open one rollback PR. Returns (result_key, result dict)."""
    repo_name, branch = target["repo_name"], target["target_branch"]
    owner, repo = repo_name.split("/", 1)
    result_key = f"{repo_name} on {branch}"

    branch_shas: dict = {}
    am_branch, _created, error = wf._create_or_get_am_branch(
        owner, repo, branch, project.project_code, headers, user, db, base_shas=branch_shas
    )
    stamps["base_commits"][result_key] = branch_shas.get(branch)
    if not am_branch:
        # A missing branch or repo is not "no protection configured", so record
        # nothing rather than asserting something about a target never reached.
        stamps["protection"][result_key] = {"status": "unknown", "error": error}
        return result_key, {"status": "error", "error": error}

    stamps["protection"][result_key] = wf._fetch_branch_protection(
        owner, repo, branch, headers, user, db
    )

    # Workflow YAML, custom files and CODEOWNERS are all just paths here, so the
    # existing custom-file committer covers every one of them. id=None keeps it
    # from stamping a blob SHA onto an unrelated CustomFile row.
    files = [
        {"id": None, "file_path": entry["path"], "file_content": entry["after"],
         "pending_delete": entry["action"] == "delete"}
        for entry in target["files"]
    ]
    committed, errors = wf._commit_custom_files_to_branch(
        files, owner, repo, am_branch, project.project_code, user, db, headers
    )
    if errors:
        # Any failed path fails the whole target — the same rule inversion
        # applies. A PR restoring three of a repo's four files is a half-revert,
        # which is exactly the guessing this feature must not do.
        return result_key, {
            "status": "error",
            "error": "Some files could not be committed, so no rollback PR was opened "
                     "for this repository.",
            "custom_files_committed": committed,
            "custom_file_errors": errors,
        }
    if not committed:
        return result_key, {
            "status": "error",
            "error": wf.NO_WORKFLOWS_COMMITTED,
            "custom_file_errors": errors,
        }

    return result_key, wf._finalize_pr_result(
        owner, repo, am_branch, branch, headers, user, db,
        project.project_code, None, result_key,
        delivery={
            # Carried over from the source PR row so the rollback campaign renders
            # the same workflows, and so apply_rollback_am_action has names to act on.
            "workflows_committed": wf._split_workflow_names(target.get("workflow_names")),
            "workflow_errors": [],
            "custom_files_result": {
                "custom_files_committed": committed,
                "custom_file_errors": errors,
                "codeowners_committed": "",
            },
            "base_sha": branch_shas.get(branch),
            "campaign_meta": campaign_meta,
            "pr_title": f"[Actions Manager] Roll back {project.project_code} workflows",
        },
    )


def _persist_rollback_campaign(db: Session, project: Project, results: dict,
                               repo_names: List[str], campaign_fields: dict) -> tuple:
    """Create the rollback campaign row and attach its PRs. Returns (campaign_id, pr_count).

    ``campaign_fields`` is the ProjectPRCampaign kwargs describing this rollback —
    who opened it, what it is called, and which campaign it reverts.
    """
    actionable = {
        key: result for key, result in results.items()
        if isinstance(result, dict) and result.get("status") in ("pr_created", "pr_updated")
    }
    if not actionable:
        return None, 0

    campaign = ProjectPRCampaign(
        project_id=project.project_id,
        **campaign_fields,
        # No workflow policy is being applied by a rollback, so the policy block
        # is empty by construction — the restored content is GitHub history, not
        # an ActionsManager version.
        **wf._build_campaign_snapshot(db, project, repo_names, results, []),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    pr_count = 0
    for result_key, result in actionable.items():
        if wf._persist_single_pr(result, result_key, project, campaign, db):
            pr_count += 1

    if pr_count == 0:
        db.delete(campaign)
        db.commit()
        return None, 0

    try:
        record_campaign_opened(db, project, campaign, results)
    except Exception as exc:
        print(f"⚠️ Error recording campaign.opened notification for rollback: {exc}")
        db.rollback()
    return campaign.campaign_id, pr_count


def create_rollback_campaign(db: Session, project: Project, source: ProjectPRCampaign,
                             targets: List[dict], payload: RollbackCreateRequest,
                             user: str, token: str) -> dict:
    """Open the inverse campaign for every target that is still invertible."""
    headers = _gh_headers(token)
    name = payload.campaign_name or f"Rollback of {_source_label(source)}"
    description = payload.campaign_description or (
        f"Reverts campaign #{source.campaign_id} by restoring each repository's "
        "workflow files to their contents immediately before that campaign merged."
    )
    campaign_meta = {
        "name": name,
        "description": description,
        "project_name": project.project_name,
        "policy": {},
    }

    results: dict = {}
    stamps = {"base_commits": {}, "protection": {}}
    repo_names: List[str] = []
    skipped = [
        {"repo_name": t["repo_name"], "target_branch": t["target_branch"], "reason": t["reason"]}
        for t in targets if not t["invertible"]
    ]

    # Whatever stopped the loop, every PR already opened on GitHub still has to be
    # persisted below — an untracked revert PR cannot be merged or closed from here.
    aborted = None
    for target in targets:
        if not target["invertible"]:
            continue
        repo_names.append(target["repo_name"])
        try:
            result_key, result = _deliver_one_target(
                target, project, campaign_meta, user, db, headers, stamps
            )
        except Exception as exc:
            aborted = f"{target['repo_name']}: {type(exc).__name__}: {exc}"
            print(f"❌ Rollback delivery stopped at {aborted}")
            break
        results[result_key] = result

    wf._stamp_target_metadata(results, stamps["base_commits"], stamps["protection"])

    campaign_id, pr_count = _persist_rollback_campaign(db, project, results, repo_names, {
        "created_by": user,
        "campaign_name": name,
        "campaign_description": description,
        "rollback_of_campaign_id": source.campaign_id,
        "rollback_am_action": payload.am_action,
    })
    if campaign_id:
        wf._update_project_pr_state(db, project.project_id, "open")

    return {
        "campaign_id": campaign_id,
        "prs_created": pr_count,
        "results": results,
        "skipped": skipped,
        "aborted": aborted,
    }


# --------------------------------------------------------------------------- #
# What happens to ActionsManager's own copy once the rollback merges           #
# --------------------------------------------------------------------------- #


def rollback_action_for_pr(db: Session, pr: ProjectPullRequest) -> Optional[str]:
    """The rollback choice recorded for this PR's campaign, or None for a normal PR."""
    if pr is None or pr.campaign_id is None:
        return None
    campaign = db.query(ProjectPRCampaign).filter(
        ProjectPRCampaign.campaign_id == pr.campaign_id
    ).first()
    return getattr(campaign, "rollback_am_action", None) if campaign else None


def apply_rollback_am_action(db: Session, project: Project, pr: ProjectPullRequest,
                             action: str, user: str, token: str) -> None:
    """Reconcile ActionsManager's stored workflows with a rollback that just merged.

    ``keep``   – the user intends to fix the change and deliver it again, so
                 ActionsManager holds the new version; the workflows go back to
                 committed_locally and drift reports the divergence from GitHub.
    ``revert`` – the change is abandoned, so ActionsManager adopts what is now on
                 GitHub and nothing is reported as drifted.
    """
    if action == "keep":
        # Matched on the stored workflow names, which is what this status update
        # is keyed on — no path is involved.
        names = wf._split_workflow_names(pr.workflow_names)
        if names:
            wf._update_project_workflows_status(
                db, project.project_id, "committed_locally", workflow_names=names
            )
        return

    _adopt_github_after_rollback(db, project, pr, user, token)


def _workflow_name_from_path(path: str, project_code: str) -> Optional[str]:
    """The stored workflow name behind a delivered path — the inverse of
    ``format_workflow_name``.

    Derived from the path rather than the other way round: ``use_prefix`` may
    have been flipped since the campaign shipped, and the path is what actually
    went out. Returns None for anything that is not a workflow file.
    """
    if not path.startswith(_WORKFLOWS_DIR):
        return None
    filename = path[len(_WORKFLOWS_DIR):]
    for suffix in (".yml", ".yaml"):
        if filename.endswith(suffix):
            filename = filename[: -len(suffix)]
            break
    prefix = f"AM_{project_code}_"
    return filename[len(prefix):] if filename.startswith(prefix) else filename


def _adopt_github_after_rollback(db: Session, project: Project, pr: ProjectPullRequest,
                                 user: str, token: str) -> None:
    """Pull each rolled-back workflow's GitHub content back into ActionsManager.

    Paths come off the PR row, which recorded exactly what the rollback committed.
    """
    headers = _gh_headers(token)
    for path in wf._split_workflow_names(pr.file_names):
        name = _workflow_name_from_path(path, project.project_code)
        if not name:
            continue
        workflow = db.query(Workflow).join(
            ProjectWorkflow, ProjectWorkflow.workflow_id == Workflow.workflow_id
        ).filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.workflow_name == name,
        ).first()
        if not workflow:
            continue

        blob_sha, text, status = _content_at(
            pr.repo_name, path, pr.target_branch, user, db, headers
        )
        if status == "absent":
            # The rollback removed the file the campaign had added, so
            # ActionsManager now holds content GitHub does not — calling that
            # synced_with_github would be a lie.
            workflow.workflow_status = "committed_locally"
            continue
        if status != "ok":
            print(f"⚠️ Rollback adopt skipped for '{name}': {status}")
            continue

        workflow.workflow_yaml = text
        workflow.workflow_git_hash = blob_sha
        workflow.workflow_status = "synced_with_github"
        wf.create_workflow_version(
            db, workflow.workflow_id, text,
            metadata={"source": "campaign_rollback", "repo": pr.repo_name,
                      "branch": pr.target_branch, "pr_number": pr.pr_number},
        )
    db.commit()


def handle_rollback_pr_merged(db: Session, pr: ProjectPullRequest, user: Optional[str] = None) -> None:
    """Merge-path hook. A no-op for every PR that is not part of a rollback campaign."""
    action = rollback_action_for_pr(db, pr)
    if action not in ROLLBACK_AM_ACTIONS:
        return
    project = db.query(Project).filter(Project.project_id == pr.project_id).first()
    if not project:
        return
    token = wf.user_tokens.get(user) if user else None
    if action == "revert" and not token:
        # Webhook deliveries carry no user token; without one the GitHub read
        # cannot happen, so fall back to the honest outcome — drift will report it.
        print(f"⚠️ Rollback PR #{pr.pr_number} merged without an available token; "
              "leaving ActionsManager content untouched.")
        action = "keep"
    try:
        apply_rollback_am_action(db, project, pr, action, user, token)
    except Exception as exc:
        print(f"⚠️ Error applying rollback action '{action}' for PR #{pr.pr_number}: {exc}")
        db.rollback()


# --------------------------------------------------------------------------- #
# Endpoints                                                                   #
# --------------------------------------------------------------------------- #


def _source_label(campaign: ProjectPRCampaign) -> str:
    return campaign.campaign_name or f"campaign #{campaign.campaign_id}"


def _parse_campaign_id(raw: str) -> int:
    text = (raw or "").strip()
    if text.startswith("legacy-"):
        raise HTTPException(status_code=400, detail=_LEGACY_DETAIL)
    if text.startswith("campaign-"):
        text = text[len("campaign-"):]
    try:
        return int(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unrecognized campaign id '{raw}'.") from exc


def _resolve(payload: RollbackPreviewRequest, db: Session, github_user: Optional[str]):
    """(user, token, project, campaign) for a rollback request, or the right HTTP error."""
    user = wf._resolve_github_user(github_user, payload.github_user)
    token, project = wf._get_project_and_token(payload, db, github_user=user)
    # A rollback opens PRs across every merged repo in the campaign, so proving
    # the caller can *see* the project is not enough — _get_project_and_token
    # never reads ProjectMembership.project_role. Same reasoning as drift
    # resolution, which writes to GitHub for the same reason.
    wf._require_drift_editor(db, user, project)
    campaign = db.query(ProjectPRCampaign).filter(
        ProjectPRCampaign.campaign_id == _parse_campaign_id(payload.campaign_id),
        ProjectPRCampaign.project_id == project.project_id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found for this project")
    return user, token, project, campaign


def _inverse_or_429(db: Session, campaign_id: int, user: str, token: str) -> List[dict]:
    """Computing an inverse costs a handful of GitHub reads per merged PR, so the
    rate limit is a realistic outcome here rather than an unexpected crash."""
    try:
        return compute_inverse(db, campaign_id, user, token)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"GitHub API rate limit reached while computing the rollback: {exc}",
        ) from exc


@router.post("/api/campaign-rollback-preview", responses=wf._responses(400, 401, 404, 429, 500))
def preview_campaign_rollback(
    payload: RollbackPreviewRequest,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """The proposed inverse diff for a campaign, for review before anything opens."""
    user, token, _project, campaign = _resolve(payload, db, x_github_user)
    targets = _inverse_or_429(db, campaign.campaign_id, user, token)
    return {
        "campaign_id": campaign.campaign_id,
        "campaign_name": _source_label(campaign),
        "targets": targets,
        "invertible_count": sum(1 for target in targets if target["invertible"]),
    }


@router.post("/api/campaign-rollback", responses=wf._responses(400, 401, 404, 429, 500))
def create_campaign_rollback(
    payload: RollbackCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Open the rollback campaign.

    The inverse is recomputed here rather than taken from the request, so no file
    content ever arrives from the client, and a target that stopped being
    invertible since the preview is reported in ``skipped`` instead of clobbered.

    Preflight deliberately does not gate this path: it validates the forward
    policy against a validation repository, which says nothing about a revert.
    The reviewed inverse diff is this action's own gate.
    """
    user, token, project, campaign = _resolve(payload, db, x_github_user)
    targets = _inverse_or_429(db, campaign.campaign_id, user, token)
    if not any(target["invertible"] for target in targets):
        raise HTTPException(
            status_code=400,
            detail="No repository in this campaign can be rolled back automatically.",
        )
    return create_rollback_campaign(db, project, campaign, targets, payload, user, token)
