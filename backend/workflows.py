from fastapi import APIRouter, HTTPException, Request, Depends, Header, BackgroundTasks

import requests
import httpx
import base64
import json
import numbers
import re
import hmac
import hashlib
import os
import uuid
from datetime import datetime, timezone, timedelta
import ipaddress
from urllib.parse import quote, urlsplit
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from database import SessionLocal, get_db
import auth as auth_module
from auth import user_tokens, get_github_api_endpoints
from models import Project, Workflow, ProjectWorkflow, Account, ProjectPullRequest, ProjectPRCampaign, Repo, ProjectRepo, WorkflowVersion, LinkedReusableWorkflow, WorkspaceMember, ProjectMembership, RepoWorkflowOverride, CustomFile, Codeowners, WorkflowDriftState, WorkflowTreeCache
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional
from authorization import is_project_admin, check_project_access
from mode_validation import resolve_app_url, _host_is_loopback
from reusable_workflow_visibility import validate_reusable_workflow_link
from reusable_workflow_detection import is_reusable_workflow_yaml
from workflow_templates import (
    generate_template_set, 
    generate_standard_workflow_template,
    generate_reusable_workflow_template,
    get_available_template_types
)
from github_api_tracker import github_get, github_put, github_patch
from drift_notifications import (
    record_drift_transitions,
    record_drift_check_failed,
    clear_workflow_drift,
    recompute_project_drift_summary,
    drop_workflow_drift,
)
from campaign_notifications import (
    record_campaign_opened,
    record_campaign_pr_transition,
    record_campaign_status_transition,
)

NOT_AUTHENTICATED_DETAIL = "User not authenticated"
MISSING_WORKFLOW_NAME_DETAIL = "Missing workflow name"

class WorkflowSchema(BaseModel):
    name: str
    content: str
    original_name: Optional[str] = None  # Previous name when renaming a workflow

class SaveProjectWorkflowsRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    workflows: List[WorkflowSchema]
    rxworkflows: List[WorkflowSchema] = []

class CreatePullRequestsRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    selected_repos: Optional[List[str]] = None  # If None, create PRs for all repos in project
    selected_workflows: Optional[List[str]] = None  # If None, include all workflows in the PR
    selected_reusable_workflows: Optional[List[str]] = None  # If None, no reusable workflows included
    selected_custom_file_ids: Optional[List[int]] = None  # None = all changed, [] = none
    selected_codeowners_repos: Optional[List[str]] = None  # Repos to deploy CODEOWNERS via PR
    async_mode: Optional[bool] = False


class RunPreflightRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    selected_workflows: Optional[List[str]] = None

class ClosePreflightValidationRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    cleanup_branch: bool = True

class MergePreflightValidationRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    cleanup_branch: bool = True

class MergePullRequestRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    repo_name: str
    pr_number: int

class ClosePullRequestRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    repo_name: str
    pr_number: int

class PRStatusResponse(BaseModel):
    repo_name: str
    pr_number: int
    pr_url: str
    pr_state: str
    branch_name: str
    target_branch: str
    created_at: str
    updated_at: str
    # Set when the PR originates from a linked project (cross-project visibility)
    source_project_name: Optional[str] = None
    mergeable: Optional[bool] = None
    mergeable_state: Optional[str] = None
    draft: Optional[bool] = None
    can_merge: Optional[bool] = None
    merge_block_reason: Optional[str] = None
    can_close: Optional[bool] = None
    close_block_reason: Optional[str] = None

class ProjectPRStatusResponse(BaseModel):
    project_state: str  # editing, pr_open
    pull_requests: List[PRStatusResponse]
    total_prs: int
    open_prs: int
    merged_prs: int
    closed_prs: int
    # Canonical workflow IDs that must remain ``under_review`` because an open
    # PR campaign still references them in *some* project sharing the workflow
    # (the owning RWX project or any linking caller project). Surfacing this
    # lets the frontend keep linked reusable workflow badges locked even when
    # the local project's PR view contains no open PRs of its own — a sibling
    # caller's campaign is invisible to ``open_prs`` here but must still hold
    # the lock. See ``_reusable_workflow_ids_locked_by_open_campaign``.
    locked_workflow_ids: List[int] = []

class PRHistoryItemResponse(BaseModel):
    """A single historical (merged or closed) pull request record.

    ``source_project_name`` is only set when the PR was created by a *different*
    project that is linked to the queried project via a ``LinkedReusableWorkflow``
    relationship.  When the PR belongs directly to the queried project this field
    is ``None``.
    """
    pr_id: int
    repo_name: str
    pr_number: int
    pr_url: str
    pr_state: str  # "merged" or "closed"
    branch_name: str
    target_branch: str
    title: Optional[str] = None
    author: Optional[str] = None
    body: Optional[str] = None
    workflow_names: Optional[str] = None
    created_at: str
    updated_at: str
    merged_at: Optional[str] = None
    closed_at: Optional[str] = None
    # Set when the PR originates from a linked project (cross-project visibility)
    source_project_name: Optional[str] = None
    mergeable: Optional[bool] = None
    mergeable_state: Optional[str] = None
    draft: Optional[bool] = None
    can_merge: Optional[bool] = None
    merge_block_reason: Optional[str] = None
    can_close: Optional[bool] = None
    close_block_reason: Optional[str] = None

class PRHistoryResponse(BaseModel):
    """Response envelope for the PR history endpoint."""
    pull_requests: List[PRHistoryItemResponse]
    total: int
    merged_count: int
    closed_count: int


class PRCampaignPRResponse(PRHistoryItemResponse):
    """A pull request row included in a derived PR Campaign."""
    actor: Optional[str] = None
    file_names: Optional[str] = None
    is_reusable_workflow_pr: bool = False


class PRCampaignResponse(BaseModel):
    """Derived campaign grouped from existing Actions Manager pull requests."""
    campaign_id: str
    campaign_name: str
    campaign_status: str
    project_name: str
    project_code: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    target_branches: List[str]
    workflow_names: List[str]
    custom_file_paths: List[str] = []
    repositories: List[str]
    open_count: int
    merged_count: int
    closed_count: int
    failed_count: int = 0
    completion_percentage: int
    pull_requests: List[PRCampaignPRResponse]


class PRCampaignsResponse(BaseModel):
    """Response envelope for the PR Campaigns endpoint."""
    campaigns: List[PRCampaignResponse]
    pull_requests: List[PRCampaignPRResponse]
    total_campaigns: int
    active_campaigns: int
    completed_campaigns: int
    open_prs: int
    merged_prs: int
    closed_prs: int
    repositories_affected: int

class NotModified(Exception):
    """GitHub answered 304 — the resource is unchanged since our stored ETag.

    Not an error: it is the cheap path. The caller replays its cached copy.
    Carried as an exception rather than a sentinel return so it cannot be
    mistaken for "no workflow files", the way a bare {} once was.
    """


class DriftCheckUnavailable(Exception):
    """GitHub could not tell us the current state of a repo.

    Distinct from "the file is not there": a revoked token, a rate limit or a
    5xx means the answer is unknown. Treating those as absence made every
    workflow in the repo look deleted, and treating them as "no drift" emitted
    a false drift.resolved for workflows that were still drifted.
    """


class DriftStatus(BaseModel):
    workflow_name: str
    # Which repo and branch this result is about. Carried as data because the
    # repo used to be recovered by substring-matching the repo name out of
    # ``message``, which cannot express a branch and breaks whenever the
    # message wording changes. Empty only for statuses that aren't tied to a
    # repo at all (deployment variables).
    repo: str = ""
    branch: str = ""
    has_drift: bool
    github_content: Optional[str] = None
    local_content: Optional[str] = None
    github_sha: Optional[str] = None
    local_sha: Optional[str] = None
    message: str
    drift_type: str = "workflow"  # workflow, reusable_workflow, deployment_vars
    # True when the check could not be completed. Such a status carries no
    # opinion about drift: it must never be persisted or notified on, because
    # "we don't know" is not "resolved".
    check_failed: bool = False
    # True when the workflow file is absent from GitHub. Previously this was
    # only distinguishable by substring-matching the message, so consumers
    # could not tell "deleted" from "empty file" — the UI rendered a blank
    # diff pane and offered to adopt content that does not exist.
    deleted_in_github: bool = False

class DriftDetectionRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    repo_names: List[str]
    check_deployment_vars: bool = False

class DriftResolutionRequest(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    workflow_name: str
    resolution: str  # "use_github" or "use_local"
    github_content: Optional[str] = None
    github_sha: Optional[str] = None


class WorkflowDriftDetail(BaseModel):
    """Per-(workflow,repo,branch) drift detail."""
    workflow_id: int
    workflow_name: str
    workflow_filename: str
    repo: str
    branch: str
    has_drift: bool
    actionsmanager_yaml: Optional[str] = None
    github_yaml: Optional[str] = None
    actionsmanager_sha: Optional[str] = None
    github_sha: Optional[str] = None
    last_checked: str
    message: str
    # Scope-aware drift resolution metadata (issue: design-level drift fix)
    project_id: Optional[int] = None
    repo_id: Optional[int] = None
    is_shared_workflow: bool = False  # True if the workflow is associated with >1 repo in the project
    has_repo_override: bool = False   # True if a repo-specific override exists for this (project, repo, workflow)
    override_id: Optional[int] = None
    affected_repo_count: int = 0      # Other repos in the project that share this workflow without overrides
    affected_repos: List[str] = Field(default_factory=list)  # Repo names of the affected repos (without the source repo)
    source_repo_name: Optional[str] = None  # Convenience copy of ``repo`` to align with the spec
    # The check could not be completed (revoked token, rate limit, GitHub 5xx).
    # has_drift carries no meaning when this is True — the state is unknown, and
    # it is never persisted or notified on.
    check_failed: bool = False
    # The workflow file is absent from GitHub. github_yaml is None rather than
    # empty, and adopting GitHub's version is impossible — there is nothing to
    # adopt.
    deleted_in_github: bool = False


class AdoptGithubVersionRequest(BaseModel):
    """Body for POST /api/drift/adopt-github-version."""
    github_user: Optional[str] = None
    project_id: int
    repo_id: Optional[int] = None  # Optional if repo_name is supplied
    repo_name: Optional[str] = None
    # The branch whose drift the user is resolving. Without it this adopted
    # content from the repo's default branch, so a project delivering to
    # release/2.1 could import main's version of the file instead.
    branch: Optional[str] = None
    workflow_id: int
    resolution_mode: str  # adopt_project_and_sync | adopt_local_only | create_repo_override
    delivery_mode: Optional[str] = "pr"  # "pr" or "direct" — only used with adopt_project_and_sync
    target_repo_ids: Optional[List[int]] = None  # If None, default to all affected repos


class ProjectDriftSummary(BaseModel):
    """Project-level drift summary returned by GET /api/projects/{project_id}/drift."""
    project_id: int
    project_name: str
    drift_count: int
    drifted_workflows: List[WorkflowDriftDetail]
    # When the reported state was established — null when no check has ever
    # run. Not the time of this request: an empty list from a check that never
    # happened must not read as "verified clean just now".
    last_checked: Optional[str] = None
    # Workflow/repo pairs GitHub could not be queried about. Non-zero means the
    # drift picture is incomplete, so an empty drifted_workflows must not be
    # presented as "everything is in sync".
    unchecked_count: int = 0
    # Why the state above may be older than it looks — e.g. the background
    # sweep cannot check this project because its owner has no saved token.
    # Without this the timestamp just stops moving and nothing explains it.
    stale_reason: Optional[str] = None


class WorkflowDriftResponse(BaseModel):
    """Per-workflow drift detail returned by GET /api/workflows/{workflow_id}/drift."""
    workflow_id: int
    workflow_name: str
    workflow_filename: str
    has_drift: bool
    drift_details: List[WorkflowDriftDetail]
    last_checked: str


class ResolveWorkflowDriftRequest(BaseModel):
    """Body for POST /api/workflows/{workflow_id}/resolve-drift."""
    github_user: Optional[str] = None
    repo: str
    branch: str
    resolution: str  # "use_github" or "restore_actionsmanager"
    delivery_mode: Optional[str] = "pr"  # "pr" or "direct" — only used for restore_actionsmanager
    # The GitHub blob SHA the drift was computed against. When supplied, a
    # direct push is refused with 409 if GitHub has moved on since, so a
    # colleague's fix can't be silently reverted by a stale page. Optional so
    # existing callers keep working; the UI always sends it.
    expected_github_sha: Optional[str] = None


class BulkResolveDriftItem(BaseModel):
    workflow_id: int
    repo: str
    branch: str
    # See ResolveWorkflowDriftRequest.expected_github_sha.
    expected_github_sha: Optional[str] = None


class BulkResolveDriftRequest(BaseModel):
    """Body for POST /api/projects/{project_id}/drift/bulk-resolve.

    resolution/delivery_mode apply uniformly to every item in the batch -
    mixing resolutions per item isn't supported in one request.
    """
    github_user: Optional[str] = None
    items: List[BulkResolveDriftItem]
    resolution: str  # "use_github" or "restore_actionsmanager"
    delivery_mode: Optional[str] = "pr"  # "pr" or "direct" — only used for restore_actionsmanager


class BulkResolveDriftItemResult(BaseModel):
    workflow_id: int
    repo: str
    branch: str
    success: bool
    message: str
    pr_url: Optional[str] = None


class BulkResolveDriftResponse(BaseModel):
    success: bool
    results: List[BulkResolveDriftItemResult]


def _cache_project_drift_summary(
    db: Session,
    project: Project,
    drift_status: str,
    drift_count: int,
    error_summary: Optional[str] = None,
) -> None:
    """Persist the latest project-level drift summary from a manual check."""
    project.drift_status = drift_status
    project.drift_count = max(int(drift_count or 0), 0)
    project.last_drift_check_at = datetime.now(timezone.utc)
    project.drift_error_summary = (error_summary or "").strip()[:500] or None
    # "check_failed" is the only outcome that didn't get a real answer from
    # GitHub; "clean" and "drifted" both mean the check succeeded, even when
    # the answer is "you have drift", so both reset the streak.
    if drift_status == "check_failed":
        project.drift_check_failure_count = (project.drift_check_failure_count or 0) + 1
    else:
        project.drift_check_failure_count = 0
    db.commit()


class WorkflowTemplateRequest(BaseModel):
    user_org: str
    build_type: str = "generic"
    project_code: Optional[str] = None

class TemplateResponse(BaseModel):
    template_type: str
    content: str
    name: str
    description: str

router = APIRouter()

# Error responses these endpoints can return, declared on each route so they
# appear in the OpenAPI schema (and so generated clients know about them).
# Codes raised inside shared helpers count too - the rule tracks the call.
_ERR_DRIFT_STALE = "The file on GitHub changed since drift was checked"

_ERROR_RESPONSES = {
    400: {"description": "Invalid request"},
    401: {"description": "Not authenticated"},
    403: {"description": "Access denied"},
    404: {"description": "Not found"},
    409: {"description": "Conflicts with the current state"},
    500: {"description": "Unexpected server error"},
    502: {"description": "Upstream GitHub request failed"},
}


def _responses(*codes: int) -> dict:
    """Subset of _ERROR_RESPONSES for a route's `responses=` parameter."""
    return {code: _ERROR_RESPONSES[code] for code in codes}


GITHUB_API_URL = "https://api.github.com"
ACCEPT_HEADER = "application/vnd.github+json"
X_API_VERSION = "2022-11-28"
# requests has no default timeout, so a hung GitHub socket blocks the worker
# thread until the process restarts rather than failing the request.
GITHUB_TIMEOUT_SECONDS = int(os.getenv("GITHUB_TIMEOUT_SECONDS", "30"))
PROJECT_ERROR = "Project not found"
ACCOUNT_ERROR = "Account not found"
BRANCH_INFO_NOT_FOUND = "Branch information not found; branch not deleted"
PROGRESS_CREATING_BRANCH = "Creating branch"
PROGRESS_COMMITTING_FILES = "Committing files"
PROGRESS_OPENING_PR = "Opening PR"
PR_CREATION_FAILED = "Failed to create PR"
NO_WORKFLOWS_COMMITTED = "No workflows committed"
_ERR_WORKFLOW_NOT_FOUND = "Workflow not found"
_ERR_STALE_VALIDATION_URL = "Stored validation PR URL is invalid."
_ERR_VALIDATION_PR_MISSING = "Validation PR not found (may have been deleted)."


# GitHub webhook secret for PR event signature verification
GITHUB_PR_WEBHOOK_SECRET = os.getenv("GITHUB_PR_WEBHOOK_SECRET", "").strip()

# ✅ Helper function to format workflow names
def format_workflow_name(workflow_name: str, project_code: str, use_prefix: bool = True) -> str:
    """Format workflow name with or without project prefix"""
    if use_prefix:
        return f"AM_{project_code}_{workflow_name}.yml"
    else:
        # Ensure it has .yml extension
        if not workflow_name.endswith('.yml') and not workflow_name.endswith('.yaml'):
            return f"{workflow_name}.yml"
        return workflow_name


def _validate_workflow_name(workflow_name: Optional[str]) -> str:
    """Trim and validate a workflow name before it is stored or used as a path."""
    trimmed = (workflow_name or "").strip()
    if not trimmed:
        raise HTTPException(status_code=400, detail="Workflow name is required")

    stem = re.sub(r"\.(yml|yaml)$", "", trimmed, flags=re.IGNORECASE)
    if not stem:
        raise HTTPException(status_code=400, detail="Workflow name cannot be empty")
    if "/" in stem or "\\" in stem:
        raise HTTPException(status_code=400, detail="Workflow name cannot contain path separators")
    if ".." in stem:
        raise HTTPException(status_code=400, detail='Workflow name cannot contain ".." sequences')
    if stem.startswith(".") or stem.endswith("."):
        raise HTTPException(status_code=400, detail="Workflow name cannot start or end with a dot")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", stem):
        raise HTTPException(
            status_code=400,
            detail="Workflow name may only contain letters, numbers, dots, underscores, and hyphens",
        )
    if len(stem) > 100:
        raise HTTPException(status_code=400, detail="Workflow name is too long (max 100 characters)")
    return trimmed


def _normalize_reusable_workflow_name(name: Optional[str]) -> str:
    """Normalize a reusable workflow filename for case-insensitive equality.

    Strips a trailing ``.yml`` / ``.yaml`` extension and a single leading
    ``AM_{code}_`` project-prefix segment that ``format_workflow_name`` may
    have added.  Returns the lowercase stem.

    This is the inverse of ``format_workflow_name`` for matching purposes:
    the canonical ``Workflow.workflow_name`` stored in the DB is the raw
    stem, while the display name surfaced to the frontend (and round-tripped
    back as ``selected_reusable_workflows``) is prefixed and ``.yml``-suffixed
    by ``_load_linked_reusable_workflows``.  Normalising both sides allows
    selections of linked reusable workflows to match the underlying DB row.
    """
    normalized = (name or "").strip()
    normalized = re.sub(r"\.(yml|yaml)$", "", normalized, flags=re.IGNORECASE)
    # Strip a single leading AM_<code>_ prefix.  ``code`` is enforced to be
    # alphanumeric in the project schema, so a non-greedy [^_]+ match is safe
    # and will not accidentally consume legitimate name segments after the
    # first underscore-delimited prefix.
    normalized = re.sub(r"^AM_[^_]+_", "", normalized, flags=re.IGNORECASE)
    return normalized.lower()


def _strip_duplicated_project_prefix(db: Session, project_id: int, name: str) -> str:
    """Normalize an inbound workflow name to avoid duplicated project prefixes.

    For projects that use the ``AM_{project_code}_`` prefix mode, callers may
    accidentally submit a name that already carries the project prefix (for
    example, from a legacy client that didn't separate the locked prefix from
    the editable suffix in the rename UI).  This helper strips a single
    matching ``AM_{project_code}_`` prefix (case-insensitive) so that
    ``format_workflow_name`` does not later produce a duplicated
    ``AM_CODE_AM_CODE_name.yml`` filename.

    The trailing ``.yml`` / ``.yaml`` extension (if any) is preserved so that
    existing workflows whose canonical ``workflow_name`` includes the
    extension continue to round-trip unchanged.

    Returns the name with at most one matching project prefix removed. If the
    project cannot be loaded or does not use prefix mode, the input is
    returned unchanged so existing behaviour is preserved on error.
    """
    if not name:
        return name
    stripped = name.strip()
    if not stripped:
        return stripped

    try:
        project = db.query(Project).filter_by(project_id=project_id).first()
    except SQLAlchemyError:
        # On DB errors, preserve the input unchanged so existing behavior is maintained.
        return stripped
    if project is None:
        return stripped

    if not getattr(project, "use_prefix", False):
        return stripped
    project_code = getattr(project, "project_code", None)
    if not project_code:
        return stripped

    expected_prefix = f"AM_{project_code.upper()}_"
    # Case-insensitive single-prefix strip via re.sub (mirrors the pattern used
    # by _normalize_reusable_workflow_name above).  ``count=1`` ensures we never
    # strip more than one prefix even if the input pathologically contains two.
    stripped = re.sub(
        f"^{re.escape(expected_prefix)}",
        "",
        stripped,
        count=1,
        flags=re.IGNORECASE,
    )
    return stripped

# ✅ Database dependency


def _resolve_github_user(x_github_user: Optional[str], payload_github_user: Optional[str]) -> str:
    """Return the authenticated GitHub username from the header (preferred) or
    the legacy body field.  Raises 401 when neither is provided."""
    user = (x_github_user or "").strip() or (payload_github_user or "").strip()
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _find_project_by_name(db: Session, github_user: str, project_name: str):
    """Look up a project by name, bypassing ownership filter for privileged users.

    Privileged workspace members (admin) can access any project
    by name.  To avoid ambiguity when ``project_name`` is not globally
    unique, the lookup first tries the owner-scoped query (using
    *github_user*) and only falls back to a global name match when that
    does not produce a result.

    Members fall through to ProjectMembership-based lookup.
    Other users fall back to the legacy ownership-based lookup
    (``Project.user_id == account.user_id``).

    Returns the ``Project`` or ``None``.
    """
    account = db.query(Account).filter_by(github_user=github_user).first()
    if not account:
        return None

    # Fast-path: exact ownership match (used by most callers, and keeps
    # backwards compatibility with older unit tests that mock `.filter_by`).
    project = db.query(Project).filter_by(
        user_id=account.user_id,
        project_name=project_name.strip()
    ).first()
    if project:
        return project

    # Check if caller is a privileged workspace member
    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == account.user_id)
        .first()
    )
    if member and is_project_admin(member):
        # Privileged users — try caller-owned project first for disambiguation,
        # since project_name is only unique per owner, not globally.
        project = db.query(Project).filter(
            Project.user_id == account.user_id,
            Project.project_name.ilike(project_name.strip()),
        ).first()
        if project:
            return project
        # Fallback: global name match (single-workspace model)
        return db.query(Project).filter(
            Project.project_name.ilike(project_name.strip())
        ).first()

    # Non-admin members (member, read_only): check ProjectMembership for explicit project access
    if member and member.workspace_role in ("member", "read_only"):
        project = db.query(Project).join(
            ProjectMembership, ProjectMembership.project_id == Project.project_id
        ).filter(
            Project.project_name.ilike(project_name.strip()),
            ProjectMembership.user_id == member.user_id,
        ).first()
        if project:
            return project

    # Non-privileged: ownership-based lookup only
    return db.query(Project).filter(
        Project.user_id == account.user_id,
        Project.project_name.ilike(project_name.strip()),
    ).first()

def count_project_workflows(user: str, project_name: str) -> int:
    """Helper function to count regular workflows for a project"""
    db = SessionLocal()
    try:
        if user not in user_tokens:
            return 0
        
        project = _find_project_by_name(db, user, project_name)
        
        if not project:
            return 0
        # Defensive: treat unexpected/mocked objects as "not found"
        # to avoid returning non-integer Mock counts in unit tests.
        if not isinstance(getattr(project, "project_id", None), numbers.Integral):
            return 0
        
        # Count regular workflows (not reusable) for this project
        workflow_count = db.query(Workflow) \
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id) \
            .filter(
                ProjectWorkflow.project_id == project.project_id,
                Workflow.reusable_workflow == False
            ).count()
        
        return workflow_count
    except Exception as e:
        print(f"❌ Error counting workflows: {str(e)}")
        return 0
    finally:
        db.close()

def count_project_reusable_workflows(user: str, project_name: str) -> int:
    """Helper function to count reusable workflows for a project"""
    db = SessionLocal()
    try:
        if user not in user_tokens:
            return 0
        
        project = _find_project_by_name(db, user, project_name)
        
        if not project:
            return 0
        if not isinstance(getattr(project, "project_id", None), numbers.Integral):
            return 0
        
        # Count reusable workflows for this project
        workflow_count = db.query(Workflow) \
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id) \
            .filter(
                ProjectWorkflow.project_id == project.project_id,
                Workflow.reusable_workflow == True
            ).count()
        
        return workflow_count
    except Exception as e:
        print(f"❌ Error counting reusable workflows: {str(e)}")
        return 0
    finally:
        db.close()

def get_workflow_from_github(owner, repo, workflow_filename, token, default_branch=None):
    """Fetch a specific workflow file from GitHub repository.

    ``default_branch``, when supplied, skips the repo-metadata lookup -
    callers resolving the same repo's default branch for multiple files in
    one request (e.g. a bulk operation) should resolve it once via
    ``get_default_branch`` and pass it through here instead of paying for a
    redundant GET per file.
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION
    }

    if not default_branch:
        # Same resolution (and the same failure semantics) as everywhere else,
        # rather than a second inline copy that quietly settled on "main".
        default_branch = get_default_branch(owner, repo, headers)

    # Try to get the workflow file from default branch
    workflow_path = f".github/workflows/{workflow_filename}"
    file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{workflow_path}?ref={quote(default_branch, safe='')}"
    
    response = requests.get(file_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    
    if response.status_code == 200:
        file_data = response.json()
        # Decode base64 content
        content = base64.b64decode(file_data["content"]).decode('utf-8')
        sha = file_data.get("sha")  # Get the Git SHA of the file
        return {"content": content, "sha": sha}
    elif response.status_code == 404:
        return None  # File doesn't exist
    else:
        raise Exception(f"GitHub API error: {response.status_code}")

def fetch_workflow_tree(owner: str, repo: str, branch: str, token: str,
                        etag: Optional[str] = None) -> tuple:
    """
    List a branch's workflow files via the Git Trees API, optionally conditionally.

    Args:
        etag: A previously returned ETag. When supplied the request carries
            ``If-None-Match`` and GitHub answers 304 if nothing changed —
            **304s do not count against the rate limit**, so re-verifying an
            untouched branch is free. Raises NotModified in that case, leaving
            the caller to replay its cached mapping.

    Returns:
        tuple: ({filename: blob_sha}, etag) — the etag to store for next time.

    Raises:
        NotModified: unchanged since ``etag`` was issued.
        DriftCheckUnavailable: GitHub could not tell us what is there.
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION
    }
    if etag:
        headers["If-None-Match"] = etag

    # Use Git Trees API to get all files in .github/workflows directory.
    # The branch is percent-encoded because '#' is legal in a git ref but ends
    # the URL path — GitHub then 404s, which this function reads as "no
    # workflow files here" and every workflow in the repo looks deleted.
    # ('/' needs no encoding: GitHub resolves the tree-ish server-side and
    # accepts it either way. Encoding it is harmless and verified against the
    # live API.)
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/trees/{quote(branch, safe='')}:.github/workflows"
    response = requests.get(url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)

    if response.status_code == 304:
        raise NotModified(f"{owner}/{repo}@{branch} unchanged")

    if response.status_code == 404:
        # The directory genuinely has no workflows — an empty result is the truth.
        return {}, response.headers.get("ETag")

    if response.status_code != 200:
        # Anything else (401 revoked token, 403/429 rate limit, 5xx) means we do
        # not know what is in the repo. Returning {} here used to be
        # indistinguishable from "no workflows", which made every workflow in
        # the repo look deleted from GitHub.
        raise DriftCheckUnavailable(
            f"GitHub returned {response.status_code} listing workflows in "
            f"{owner}/{repo}@{branch}"
        )

    # Extract blob SHAs from the tree response
    tree_data = response.json()
    shas = {
        item["path"]: item["sha"]
        for item in tree_data.get("tree", [])
        if item["type"] == "blob"
    }
    return shas, response.headers.get("ETag")


def get_all_workflow_shas(owner: str, repo: str, branch: str, token: str) -> dict:
    """Unconditional listing of a branch's workflow file SHAs.

    Kept for callers with nowhere to cache an ETag. The drift path uses
    ``fetch_workflow_tree`` directly so it can go conditional.
    """
    shas, _etag = fetch_workflow_tree(owner, repo, branch, token)
    return shas

def get_default_branch(owner, repo, headers, user: str = None, db: Session = None):
    """Get the default branch for a repository.

    Raises DriftCheckUnavailable when GitHub does not tell us. This used to
    return "main" on any failure, which turned a revoked token or a rate limit
    into a *wrong answer* rather than an error: drift was then compared against
    a branch nobody chose, and reported "synchronized" against a file the
    project had never written to. Callers that genuinely want a best-effort
    guess now have to say so at the call site.
    """
    repo_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
    if user and db:
        response = github_get(repo_url, user, db, headers=headers)
    else:
        response = requests.get(repo_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)

    if response.status_code != 200:
        raise DriftCheckUnavailable(
            f"GitHub returned {response.status_code} resolving the default branch of {owner}/{repo}"
        )

    default_branch = response.json().get("default_branch")
    if not default_branch:
        raise DriftCheckUnavailable(f"GitHub did not report a default branch for {owner}/{repo}")
    return default_branch

def verify_workflow_belongs_to_project(workflow_content, project_code, workflow_name):
    """
    Verify that a workflow found in GitHub actually belongs to the current project.
    This prevents custom workflows or workflows from other projects from being flagged as drifted.
    """
    if not workflow_content:
        return False
    
    # Check for project-specific patterns in the content
    # Actions Manager workflows typically contain the project code in various forms
    project_indicators = [
        f"AM_{project_code}",  # Project code appears in the content (most common)
        f"# Generated by Actions Manager for project {project_code}",  # Potential comment
        f"# Project: {project_code}",  # Alternative comment format
        f"AM_{project_code.lower()}",  # Lowercase version
    ]
    
    # Also check for patterns that suggest this is from a different project
    other_project_patterns = [
        "AM_" + code + "_" for code in ["ABCD", "EFGH", "IJKL", "MNOP", "QRST", "UVWX", "YZ12", "3456"] 
        if code != project_code
    ]
    
    # Count how many indicators are found
    indicators_found = 0
    for indicator in project_indicators:
        if indicator in workflow_content:
            indicators_found += 1
    
    # Check if this workflow seems to belong to a different project
    other_project_found = False
    for pattern in other_project_patterns:
        if pattern in workflow_content:
            other_project_found = True
            break
    
    # If we find indicators of a different project, definitely reject
    if other_project_found:
        return False
    
    # If we find project indicators, it's likely this workflow belongs to our project
    if indicators_found > 0:
        return True
    
    # If no clear indicators are found, we'll allow it for backward compatibility
    # but this is where we could be more strict in the future
    return True


def _validate_user_and_get_project(db: Session, user: str, project_name: str):
    """
    Validate user authentication and retrieve project information.
    
    Returns:
        tuple: (token, project, project_code)
    
    Raises:
        HTTPException: If user is not authenticated or project is not found
    """
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
    
    token = user_tokens[user]
    
    project = _find_project_by_name(db, user, project_name)
    
    if not project:
        raise HTTPException(status_code=404, detail=PROJECT_ERROR)
    
    project_code = project.project_code.upper()
    
    return token, project, project_code


def _get_project_workflows(db: Session, project):
    """
    Retrieve all workflows for a project and separate them by type.
    
    Returns:
        tuple: (regular_workflows, reusable_workflows)
    """
    workflows = db.query(Workflow) \
        .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id) \
        .filter(ProjectWorkflow.project_id == project.project_id) \
        .all()
    
    # Separate regular workflows from reusable workflows
    regular_workflows = [w for w in workflows if not w.reusable_workflow]
    reusable_workflows = [w for w in workflows if w.reusable_workflow]
    
    return regular_workflows, reusable_workflows


def _normalize_yaml_for_comparison(yaml_content: str) -> str:
    """Normalize YAML content for drift comparison.

    Normalizes:
    - Line endings (CRLF → LF)
    - Trailing whitespace on each line
    - Ensures single trailing newline

    Does NOT reformat YAML structure or change content semantics.
    """
    if not yaml_content:
        return ""

    # Normalize line endings
    normalized = yaml_content.replace("\r\n", "\n").replace("\r", "\n")

    # Strip trailing whitespace from each line
    lines = normalized.split("\n")
    lines = [line.rstrip() for line in lines]

    # Join back and ensure single trailing newline
    normalized = "\n".join(lines)
    normalized = normalized.strip() + "\n" if normalized.strip() else ""

    return normalized


def _create_drift_status(workflow_name: str, has_drift: bool,
                        github_content: Optional[str], local_content: Optional[str],
                        github_sha: Optional[str], local_sha: Optional[str],
                        message: str, drift_type: str,
                        check_failed: bool = False,
                        deleted_in_github: bool = False,
                        repo: str = "", branch: str = "") -> DriftStatus:
    """Create a DriftStatus object with the given parameters."""
    return DriftStatus(
        workflow_name=workflow_name,
        repo=repo,
        branch=branch,
        has_drift=has_drift,
        github_content=github_content,
        local_content=local_content,
        github_sha=github_sha,
        local_sha=local_sha,
        message=message,
        drift_type=drift_type,
        check_failed=check_failed,
        deleted_in_github=deleted_in_github,
    )


def _has_open_pr_for_workflow(db: Session, project_id: int, workflow_name: str, repo_name: str) -> bool:
    """
    Check if a workflow has an open PR.

    Cross-project check: For linked reusable workflows, checks PRs in both the
    standard project and the RWX project so that workflows are locked everywhere
    when a PR exists.

    Args:
        db: Database session
        project_id: Project ID (may be standard or RWX project)
        workflow_name: Workflow name to check
        repo_name: Repository name

    Returns:
        True if the workflow has an open PR, False otherwise
    """
    try:
        # Collect related project IDs via LinkedReusableWorkflow so that
        # workflows are locked everywhere when a PR exists.
        project_ids: set[int] = {project_id}

        # Determine if this is a standard or RWX project
        project = db.query(Project).filter_by(project_id=project_id).first()
        if project:
            if project.project_type == "standard":
                # Standard project: include PRs from linked RWX projects
                linked_rwx_rows = (
                    db.query(LinkedReusableWorkflow)
                    .filter(LinkedReusableWorkflow.standard_project_id == project_id)
                    .all()
                )
                rwx_project_ids = {row.rwx_project_id for row in linked_rwx_rows}
                project_ids.update(rwx_project_ids)
            else:
                # RWX project: include PRs from Standard projects that link to it
                linked_std_rows = (
                    db.query(LinkedReusableWorkflow)
                    .filter(LinkedReusableWorkflow.rwx_project_id == project_id)
                    .all()
                )
                std_project_ids = {row.standard_project_id for row in linked_std_rows}
                project_ids.update(std_project_ids)

        open_prs = db.query(ProjectPullRequest).filter(
            ProjectPullRequest.project_id.in_(project_ids),
            ProjectPullRequest.repo_name == repo_name,
            ProjectPullRequest.pr_state == "open"
        ).all()

        # Check if any open PR contains this workflow.
        # workflow_names is a comma-separated list that may include surrounding
        # whitespace (it is stored joined by ", "), so strip each entry before
        # comparing to avoid false negatives.
        for pr in open_prs:
            if not pr.workflow_names:
                continue
            pr_workflow_names = {name.strip() for name in pr.workflow_names.split(",") if name.strip()}
            if workflow_name in pr_workflow_names:
                return True
        return False
    except Exception as e:
        print(f"⚠️ Error checking open PRs for workflow {workflow_name}: {e}")
        return False


def _find_blocking_reusable_workflow_pr(db: Session, workflow: "Workflow", current_project_id: int):
    """Find an open PR campaign owned by a *different* project that is already
    reviewing the given reusable workflow.

    Reusable workflows are canonical, shared assets identified by ``workflow_id``.
    Once any caller (or the owning RWX project) opens a PR campaign for the
    workflow, it is globally locked: no other project may open a second campaign
    until that PR is merged or closed.  This prevents conflicting or duplicate
    PR campaigns against the same source-of-truth workflow.

    Args:
        db: Database session
        workflow: The canonical reusable Workflow record being considered.
        current_project_id: The project attempting to open a PR campaign. PRs
            owned by this project are ignored (updating one's own campaign is
            allowed).

    Returns:
        A ``(ProjectPullRequest, Project)`` tuple describing the blocking PR and
        its owning project, or ``None`` when the workflow is free to review.
    """
    # All projects related to this workflow: the owning RWX project(s) plus
    # every standard project that links it.
    related_project_ids: set[int] = set()
    owner_rows = (
        db.query(ProjectWorkflow.project_id)
        .filter(ProjectWorkflow.workflow_id == workflow.workflow_id)
        .all()
    )
    related_project_ids.update(pid for (pid,) in owner_rows)
    link_rows = (
        db.query(LinkedReusableWorkflow.standard_project_id)
        .filter(LinkedReusableWorkflow.workflow_id == workflow.workflow_id)
        .all()
    )
    related_project_ids.update(pid for (pid,) in link_rows)
    related_project_ids.discard(current_project_id)
    if not related_project_ids:
        return None

    open_prs = (
        db.query(ProjectPullRequest)
        .filter(
            ProjectPullRequest.project_id.in_(related_project_ids),
            ProjectPullRequest.pr_state == "open",
        )
        .all()
    )
    # Restrict name matches to PRs against the owning RWX repo(s) to avoid
    # false positives from same-named regular workflows in caller projects.
    owner_project_ids = [pid for (pid,) in owner_rows]
    rwx_repo_names: set[str] = set()
    if owner_project_ids:
        rwx_repo_names.update(
            rname for (rname,) in
            db.query(Repo.repo_name)
            .join(ProjectRepo, Repo.repo_id == ProjectRepo.repo_id)
            .filter(ProjectRepo.project_id.in_(owner_project_ids))
            .all()
        )
    stem = _normalize_reusable_workflow_name(workflow.workflow_name)
    for pr in open_prs:
        if not pr.workflow_names:
            continue
        if not (pr.repo_name.endswith("/am-reuseable-workflow") or pr.repo_name in rwx_repo_names):
            continue
        names = {
            _normalize_reusable_workflow_name(n)
            for n in pr.workflow_names.split(",")
            if n.strip()
        }
        if stem in names:
            owning_project = db.query(Project).filter_by(project_id=pr.project_id).first()
            return pr, owning_project
    return None


def _reusable_workflow_ids_locked_by_open_campaign(db: Session, workflow_ids) -> set:
    """Return the subset of ``workflow_ids`` that must stay ``under_review``.

    Reusable workflows are canonical, shared assets identified by
    ``workflow_id``.  Their ``under_review`` lock is a *workflow-level* state
    that must persist globally until **every** open PR campaign referencing
    the workflow — from the owning RWX project or any linking caller project —
    is merged or closed.

    Status transitions triggered by a single project (merge/close endpoints,
    PR webhooks, page-load PR refreshes, local saves) only inspect that
    project's own PR rows, so an open campaign held by a *different* project
    would otherwise be invisible and the workflow could be wrongly unlocked.
    Callers use this helper to exclude such workflows from any
    ``under_review`` → ``synced_with_github``/``committed_locally`` downgrade.

    PR rows are matched by normalized workflow stem and scoped to the owning
    RWX repo(s) (or the dedicated ``*/am-reuseable-workflow`` repo) so that
    same-named regular workflows in caller repos cannot cause false locks.

    Args:
        db: Database session.
        workflow_ids: Candidate canonical reusable workflow IDs.

    Returns:
        The set of ``workflow_ids`` that still have an open PR campaign
        somewhere and therefore must remain locked.
    """
    if not workflow_ids:
        return set()

    # Canonical stem name for each shared workflow, used to match PR records
    # whose ``workflow_names`` carry the display-formatted (prefixed/.yml) name.
    stem_by_id = {
        wid: _normalize_reusable_workflow_name(name)
        for wid, name in db.query(Workflow.workflow_id, Workflow.workflow_name)
        .filter(Workflow.workflow_id.in_(workflow_ids))
        .all()
    }

    # Every project related to these workflows: the owning RWX project(s) plus
    # every standard project that links them.
    related_project_ids: set[int] = set()
    related_project_ids.update(
        pid for (pid,) in db.query(ProjectWorkflow.project_id)
        .filter(ProjectWorkflow.workflow_id.in_(workflow_ids))
        .all()
    )
    related_project_ids.update(
        pid for (pid,) in db.query(LinkedReusableWorkflow.standard_project_id)
        .filter(LinkedReusableWorkflow.workflow_id.in_(workflow_ids))
        .all()
    )
    if not related_project_ids:
        return set()

    open_prs = (
        db.query(ProjectPullRequest)
        .filter(
            ProjectPullRequest.project_id.in_(related_project_ids),
            ProjectPullRequest.pr_state == "open",
        )
        .all()
    )

    rwx_repos_by_wid = _rwx_repo_names_by_workflow_id(db, workflow_ids)

    locked: set = set()
    for pr in open_prs:
        locked.update(_workflow_ids_locked_by_pr(pr, stem_by_id, rwx_repos_by_wid))
    return locked


def _rwx_repo_names_by_workflow_id(db: Session, workflow_ids) -> dict:
    """Map each canonical reusable ``workflow_id`` to its owning RWX repo names.

    Used to avoid false-positive locks from same-named regular workflows in
    caller projects.
    """
    rwx_repos_by_wid: dict = {}
    for wid, rname in (
        db.query(ProjectWorkflow.workflow_id, Repo.repo_name)
        .join(ProjectRepo, ProjectRepo.project_id == ProjectWorkflow.project_id)
        .join(Repo, Repo.repo_id == ProjectRepo.repo_id)
        .filter(ProjectWorkflow.workflow_id.in_(workflow_ids))
        .all()
    ):
        rwx_repos_by_wid.setdefault(wid, set()).add(rname)
    return rwx_repos_by_wid


def _workflow_ids_locked_by_pr(pr, stem_by_id: dict, rwx_repos_by_wid: dict) -> set:
    """Return the workflow IDs that ``pr`` keeps locked under_review.

    A reusable workflow is considered locked by ``pr`` when the PR's
    ``workflow_names`` contains its canonical stem **and** the PR was filed
    against an owning RWX repo (or the shared ``*/am-reuseable-workflow`` repo).
    """
    if not pr.workflow_names:
        return set()
    pr_stems = {
        _normalize_reusable_workflow_name(n)
        for n in pr.workflow_names.split(",")
        if n.strip()
    }
    is_rwx_pr_repo = pr.repo_name.endswith("/am-reuseable-workflow")
    locked: set = set()
    for wid, stem in stem_by_id.items():
        if not stem or stem not in pr_stems:
            continue
        if is_rwx_pr_repo or pr.repo_name in rwx_repos_by_wid.get(wid, set()):
            locked.add(wid)
    return locked


def _drift_for_missing_workflow(workflow, repo_name: str, drift_type: str, db: Session, project_id: int,
                                branch: str = "") -> Optional[DriftStatus]:
    """Workflow doesn't exist on GitHub. Decide deleted / pending-merge / never-synced.

    Only flag as drift if the workflow has a REAL git hash (was previously synced) —
    excludes workflows with no hash, or a hash of all zeros (locally committed but
    never pushed: "0000..."). When a PR is created, workflow_git_hash is set to the
    PR branch SHA, which won't be present on the target branch until merge — so an
    open PR means "pending merge", not "deleted".
    """
    LOCAL_COMMIT_HASH = "0" * 40  # 40 zeros indicates local-only commit
    has_real_hash = (
        workflow.workflow_git_hash
        and workflow.workflow_git_hash != LOCAL_COMMIT_HASH
    )
    label = 'Reusable w' if drift_type == 'reusable_workflow' else 'W'

    if has_real_hash:
        if db and project_id and _has_open_pr_for_workflow(db, project_id, workflow.workflow_name, repo_name):
            print(f"ℹ️  Workflow '{workflow.workflow_name}' missing from target branch but has open PR — classifying as pending merge (not drifted)")
            return _create_drift_status(
                workflow_name=workflow.workflow_name,
                has_drift=False,
                github_content=None,
                local_content=workflow.workflow_yaml,
                github_sha=None,
                local_sha=workflow.workflow_git_hash,
                message=f"{label}orkflow in open PR - pending merge to {repo_name}",
                drift_type=drift_type,
                repo=repo_name,
                branch=branch,
            )

        return _create_drift_status(
            workflow_name=workflow.workflow_name,
            has_drift=True,
            github_content=None,
            local_content=workflow.workflow_yaml,
            github_sha=None,
            local_sha=workflow.workflow_git_hash,
            message=f"{label}orkflow was deleted from {repo_name}",
            drift_type=drift_type,
            deleted_in_github=True,
            repo=repo_name,
            branch=branch,
        )

    # Workflow has never been synced (no real git hash). An open PR means
    # new_open_pr state (not drift); otherwise it's just never synced yet.
    if db and project_id and _has_open_pr_for_workflow(db, project_id, workflow.workflow_name, repo_name):
        print(f"ℹ️  Workflow '{workflow.workflow_name}' has open PR - classifying as new_open_pr (not drifted)")
        return _create_drift_status(
            workflow_name=workflow.workflow_name,
            has_drift=False,
            github_content=None,
            local_content=workflow.workflow_yaml,
            github_sha=None,
            local_sha=workflow.workflow_git_hash,
            message=f"{label}orkflow in open PR - pending merge to {repo_name}",
            drift_type=drift_type,
            repo=repo_name,
            branch=branch,
        )

    return None


def _drift_for_content_mismatch(workflow, github_content, github_sha, repo_name: str, drift_type: str,
                                 db: Session, project_id: int, local_normalized: str, github_normalized: str,
                                 branch: str = "") -> DriftStatus:
    """Content differs from target branch. Decide local-edit / under-review / true drift.

    If the workflow was modified locally in ActionsManager (Commit Locally), the hash
    is reset to all zeros and status is "committed_locally" — that's an intentional
    local edit pending sync, NOT drift from GitHub. Drift means GitHub changed outside
    ActionsManager; a local AM edit must never be flagged as drift.
    """
    label = 'Reusable w' if drift_type == 'reusable_workflow' else 'W'
    LOCAL_COMMIT_HASH = "0" * 40
    # Only the zeroed hash proves this was an intentional local edit: every path
    # that edits a workflow in ActionsManager sets that sentinel. Status alone is
    # not enough, because closing a fix PR without merging also reverts the
    # workflow to "committed_locally" while leaving a real GitHub SHA behind.
    # Treating that as a local edit suppressed genuine drift indefinitely and
    # emitted drift.resolved while GitHub still differed.
    is_local_modification = workflow.workflow_git_hash == LOCAL_COMMIT_HASH
    if is_local_modification:
        print(f"ℹ️  Workflow '{workflow.workflow_name}' was modified locally (status={workflow.workflow_status}) - classifying as local_modified (not drifted)")
        return _create_drift_status(
            workflow_name=workflow.workflow_name,
            has_drift=False,
            github_content=github_content,
            local_content=workflow.workflow_yaml,
            github_sha=github_sha,
            local_sha=workflow.workflow_git_hash,
            message=f"{label}orkflow modified locally - pending sync to {repo_name}",
            drift_type=drift_type,
            repo=repo_name,
            branch=branch,
        )

    if db and project_id and _has_open_pr_for_workflow(db, project_id, workflow.workflow_name, repo_name):
        # Workflow has open PR and local differs from target branch — expected for
        # workflows under review, classify as under_review, not drift.
        print(f"ℹ️  Workflow '{workflow.workflow_name}' has open PR with changes - classifying as under_review (not drifted)")
        return _create_drift_status(
            workflow_name=workflow.workflow_name,
            has_drift=False,
            github_content=github_content,
            local_content=workflow.workflow_yaml,
            github_sha=github_sha,
            local_sha=workflow.workflow_git_hash,
            message=f"{label}orkflow under review in open PR for {repo_name}",
            drift_type=drift_type,
            repo=repo_name,
            branch=branch,
        )

    print(f"✅ Drift detected for {'reusable ' if drift_type == 'reusable_workflow' else ''}workflow '{workflow.workflow_name}' (content differs)")
    if local_normalized and github_normalized:
        print(f"  First 200 chars of local (normalized): {repr(local_normalized[:200])}")
        print(f"  First 200 chars of GitHub (normalized): {repr(github_normalized[:200])}")

    return _create_drift_status(
        workflow_name=workflow.workflow_name,
        has_drift=True,
        github_content=github_content,
        local_content=workflow.workflow_yaml,
        github_sha=github_sha,
        local_sha=workflow.workflow_git_hash,
        message=f"{label}orkflow content differs between local and {repo_name}",
        drift_type=drift_type,
        repo=repo_name,
        branch=branch,
    )


def _compare_workflow_content(workflow, github_data, repo_name: str, project_code: str, drift_type: str = "workflow",
                               db: Session = None, project_id: int = None, branch: str = "") -> DriftStatus:
    """Compare workflow content between local and GitHub using deterministic drift logic.

    Core drift rule:
    - If workflow doesn't exist on GitHub → drift (if previously synced)
    - If content (normalized) matches → no drift, update hash if needed
    - If content (normalized) differs → drift

    Returns:
        DriftStatus: The drift status for this workflow
    """
    if github_data is None:
        return _drift_for_missing_workflow(workflow, repo_name, drift_type, db, project_id, branch)

    github_content = github_data["content"]
    github_sha = github_data["sha"]

    # Verify that the workflow in GitHub actually belongs to this project
    if not verify_workflow_belongs_to_project(github_content, project_code, workflow.workflow_name):
        # Skip this workflow as it doesn't belong to the current project
        print(f"⚠️ Skipping workflow {workflow.workflow_name} in {repo_name} - doesn't belong to project {project_code}")
        return None

    # Normalize content for comparison
    local_normalized = _normalize_yaml_for_comparison(workflow.workflow_yaml or "")
    github_normalized = _normalize_yaml_for_comparison(github_content or "")

    content_matches = local_normalized == github_normalized

    print(f"🔍 Drift check for {'reusable ' if drift_type == 'reusable_workflow' else ''}workflow '{workflow.workflow_name}' in {repo_name}:")
    print(f"  Local SHA: {workflow.workflow_git_hash}")
    print(f"  GitHub SHA: {github_sha}")
    print(f"  Local content length (normalized): {len(local_normalized)}")
    print(f"  GitHub content length (normalized): {len(github_normalized)}")
    print(f"  Content matches: {content_matches}")

    if content_matches:
        # Content matches - no drift, even if SHAs differ
        print(f"⚪ No drift for {'reusable ' if drift_type == 'reusable_workflow' else ''}workflow '{workflow.workflow_name}' (content matches)")

        return _create_drift_status(
            workflow_name=workflow.workflow_name,
            has_drift=False,
            github_content=github_content,
            local_content=workflow.workflow_yaml,
            github_sha=github_sha,
            local_sha=workflow.workflow_git_hash,
            message=f"{'Reusable w' if drift_type == 'reusable_workflow' else 'W'}orkflow synchronized with {repo_name}",
            drift_type=drift_type,
            repo=repo_name,
            branch=branch,
        )

    return _drift_for_content_mismatch(
        workflow, github_content, github_sha, repo_name, drift_type, db, project_id,
        local_normalized, github_normalized, branch=branch,
    )


class _WorkflowExpectedView:
    """Lightweight duck-typed wrapper used by drift comparison to substitute
    a per-repo override's expected content/hash for the underlying project
    workflow.  Exposes the same attribute surface as ``models.Workflow`` that
    ``_compare_workflow_content`` reads from."""

    def __init__(self, workflow, override=None):
        self.workflow_id = workflow.workflow_id
        self.workflow_name = workflow.workflow_name
        self.reusable_workflow = getattr(workflow, "reusable_workflow", False)
        if override is not None:
            self.workflow_yaml = override.workflow_yaml
            self.workflow_git_hash = override.workflow_git_hash
            self.workflow_status = "synced_with_github"
            self._is_override = True
            self._override = override
        else:
            self.workflow_yaml = workflow.workflow_yaml
            self.workflow_git_hash = workflow.workflow_git_hash
            self.workflow_status = getattr(workflow, "workflow_status", "new")
            self._is_override = False
            self._override = None


def _get_repo_workflow_override(db: Session, project_id: int, repo_name: str, workflow_id: int):
    """Return the ``RepoWorkflowOverride`` row for (project, repo, workflow) or None.

    Drift detection calls this in a (workflow x repo) nested loop, so we cache
    the per-name repo-id map and the project's overrides in ``db.info`` to
    avoid an N+1 pattern. Subsequent calls within the same SQLAlchemy session
    do O(1) dict lookups.
    """
    if not db or project_id is None or workflow_id is None or not repo_name:
        return None

    repo_id_by_name = db.info.get("repo_id_by_name")
    if repo_id_by_name is None:
        repo_id_by_name = {r.repo_name: r.repo_id for r in db.query(Repo).all()}
        db.info["repo_id_by_name"] = repo_id_by_name

    repo_id = repo_id_by_name.get(repo_name)
    if repo_id is None:
        return None

    overrides_by_project = db.info.setdefault("repo_workflow_overrides_by_project", {})
    project_overrides = overrides_by_project.get(project_id)
    if project_overrides is None:
        project_overrides = {
            (o.repo_id, o.workflow_id): o
            for o in db.query(RepoWorkflowOverride).filter_by(project_id=project_id).all()
        }
        overrides_by_project[project_id] = project_overrides

    return project_overrides.get((repo_id, workflow_id))


def _resolve_drift_branches_for_repo(db: Session, project: "Project", repo_name: str,
                                     owner: str, repo: str, headers: dict, user: str) -> List[str]:
    """Which branches drift should check for one repo.

    Deliberately the *same* resolution delivery uses, so drift is measured
    against the branches ActionsManager actually writes to. Previously drift
    always read the repo's GitHub default branch, so a project delivering to
    ``release/*`` was compared against ``main`` and reported "synchronized"
    against a file it had never written.

    Without a project (direct callers that check a bare repo list) there is no
    branch configuration to honour, so this falls back to the repo's default
    branch — the same shape as ``_resolve_effective_target_branches``.
    """
    if project is None or db is None:
        return [get_default_branch(owner, repo, headers, user, db)]

    cfg = resolve_branch_config_for_repo(db, project, repo_name)
    return _resolve_branches_for_repo(
        owner, repo,
        cfg["branch_option"], cfg["branch_regex"], cfg["branch_max_age_days"],
        headers, user, db,
        recency_cache_repo=repo_name,
    )


def _get_tree_cache_row(db: Session, repo_name: str, branch: str):
    """The cached tree listing for one (repo, branch), or None."""
    if db is None:
        return None
    repo = db.query(Repo).filter(Repo.repo_name == repo_name).first()
    if repo is None:
        return None
    return (
        db.query(WorkflowTreeCache)
        .filter(WorkflowTreeCache.repo_id == repo.repo_id,
                WorkflowTreeCache.branch == branch)
        .first()
    )


def _store_tree_cache(db: Session, repo_name: str, branch: str, shas: dict, etag: Optional[str]) -> None:
    """Remember a listing and its ETag so the next check can go conditional."""
    if db is None or not etag:
        return
    repo = db.query(Repo).filter(Repo.repo_name == repo_name).first()
    if repo is None:
        return
    row = _get_tree_cache_row(db, repo_name, branch)
    if row is None:
        row = WorkflowTreeCache(repo_id=repo.repo_id, branch=branch)
        db.add(row)
    row.etag = etag
    row.sha_map_json = json.dumps(shas)
    row.fetched_at = datetime.now(timezone.utc)
    db.commit()


def _fetch_tree_using_cache(db: Session, repo_name: str, owner: str, repo: str,
                            branch: str, token: str) -> dict:
    """Listing for one (repo, branch), conditional on a stored ETag when we have one.

    A 304 means nothing changed, so the cached mapping is replayed and the call
    costs nothing against the rate limit. If a 304 arrives with no usable cached
    mapping the request is retried unconditionally — replaying an empty map
    would report every workflow in the repo as deleted.
    """
    row = _get_tree_cache_row(db, repo_name, branch)
    etag = row.etag if row else None

    try:
        shas, new_etag = fetch_workflow_tree(owner, repo, branch, token, etag=etag)
    except NotModified:
        if row is not None and row.sha_map_json:
            print(f"🟢 {repo_name}@{branch} unchanged (304, no rate-limit cost)")
            return json.loads(row.sha_map_json)
        print(f"⚠️ {repo_name}@{branch} returned 304 with nothing cached — refetching")
        shas, new_etag = fetch_workflow_tree(owner, repo, branch, token)

    _store_tree_cache(db, repo_name, branch, shas, new_etag)
    return shas


def _prefetch_workflow_shas_per_repo(repo_names: List[str], token: str, db: Session = None,
                                     project: "Project" = None, user: str = None) -> dict:
    """Batch-fetch workflow file SHAs via the Git Trees API, keyed by (repo, branch).

    One Trees call per (repo, branch) rather than per workflow, and that call is
    conditional on a stored ETag — an untouched branch answers 304 and costs
    nothing against the rate limit.

    A branch whose listing fails maps to None ("unknown"), never {} ("no
    workflow files") — callers turn None into a check_failed status, whereas {}
    would report every workflow in that repo as deleted from GitHub.
    """
    repo_sha_cache: dict = {}
    for repo_name in repo_names:
        if "/" not in repo_name:
            continue
        owner, repo = repo_name.split("/", 1)
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }
        try:
            branches = _resolve_drift_branches_for_repo(db, project, repo_name, owner, repo, headers, user)
        except Exception as e:
            # Branch resolution itself failed, so we don't know what to compare
            # against. Record one unknown entry so the repo reports check_failed
            # rather than silently falling back to a branch nobody chose.
            print(f"⚠️ Could not resolve branches for {repo_name}: {e}")
            repo_sha_cache[(repo_name, "")] = None
            continue

        for branch in branches:
            try:
                all_workflow_shas = _fetch_tree_using_cache(db, repo_name, owner, repo, branch, token)
                repo_sha_cache[(repo_name, branch)] = all_workflow_shas
                print(f"🔍 {len(all_workflow_shas)} workflow file SHAs for {repo_name}@{branch}")
            except Exception as e:
                print(f"⚠️ Could not list workflows in {repo_name}@{branch}: {e}")
                repo_sha_cache[(repo_name, branch)] = None
    return repo_sha_cache


def _update_workflow_hash_after_content_match(db: Session, workflow, override, expected, github_data, repo_name: str) -> None:
    """Content matched despite the SHA differing — refresh the stored hash (override's if one applies, else the shared workflow's)."""
    new_github_sha = github_data["sha"]
    if expected.workflow_git_hash == new_github_sha:
        return
    if override is not None:
        override.workflow_git_hash = new_github_sha
        db.commit()
        print(f"✅ Updated git hash for repo override '{workflow.workflow_name}' in {repo_name}: {new_github_sha} (content matched despite SHA difference)")
    else:
        workflow.workflow_git_hash = new_github_sha
        db.commit()
        print(f"✅ Updated git hash for workflow '{workflow.workflow_name}' in {repo_name}: {new_github_sha} (content matched despite SHA difference)")


def _check_regular_workflow_in_repo(db: Session, workflow, repo_name: str, owner: str, repo: str,
                                     formatted_workflow_name: str, workflow_shas: dict, project_code: str,
                                     token: str, project_id: int, branch: str = "") -> Optional[DriftStatus]:
    """Drift-check one workflow against one repo, using a prefetched SHA to skip a full content fetch when possible."""
    # Resolve the expected content for this repo: prefer a repo-specific
    # override when one exists, otherwise fall back to the shared project
    # workflow. This is the core of the design-level drift fix: a repo with
    # an override compares against the override, not the project workflow,
    # so it doesn't constantly re-report drift.
    override = _get_repo_workflow_override(db, project_id, repo_name, workflow.workflow_id)
    expected = _WorkflowExpectedView(workflow, override)

    if workflow_shas is None:
        # We could not list this repo's workflows at all, so we do not know
        # whether the file is missing or we simply couldn't see it.
        return _create_drift_status(
            workflow_name=workflow.workflow_name,
            has_drift=False,
            github_content=None,
            local_content=expected.workflow_yaml,
            github_sha=None,
            local_sha=expected.workflow_git_hash,
            message=f"Could not check {repo_name} — GitHub did not return its workflows",
            drift_type="workflow",
            check_failed=True,
            repo=repo_name,
            branch=branch,
        )

    try:
        github_sha = workflow_shas.get(formatted_workflow_name)

        if github_sha is None:
            # Workflow doesn't exist in GitHub
            github_data = None
        elif expected.workflow_git_hash == github_sha:
            # SHAs match - no drift, skip fetching full content
            sha_display = github_sha[:7] if github_sha else 'None'
            print(f"⚪ No drift for workflow '{workflow.workflow_name}' in {repo_name} (SHA match: {sha_display})")
            return _create_drift_status(
                workflow_name=workflow.workflow_name,
                has_drift=False,
                github_content=expected.workflow_yaml,  # Use local as proxy since they match
                local_content=expected.workflow_yaml,
                github_sha=github_sha,
                local_sha=expected.workflow_git_hash,
                message=f"Workflow synchronized with {repo_name}",
                drift_type="workflow",
                repo=repo_name,
                branch=branch,
            )
        else:
            # SHA differs or workflow was never synced - fetch full content
            print(f"🔍 SHA mismatch for workflow '{workflow.workflow_name}' in {repo_name} - fetching full content")
            print(f"  Local SHA: {expected.workflow_git_hash}")
            print(f"  GitHub SHA: {github_sha}")
            github_data = get_workflow_from_github(owner, repo, formatted_workflow_name, token, default_branch=branch)

        # Compare workflow content (against override-aware expected view)
        drift_status = _compare_workflow_content(expected, github_data, repo_name, project_code, "workflow",
                                                 db=db, project_id=project_id, branch=branch)
        if drift_status and not drift_status.has_drift and github_data:
            _update_workflow_hash_after_content_match(db, workflow, override, expected, github_data, repo_name)
        return drift_status
    except Exception as e:
        print(f"⚠️ Error checking workflow {workflow.workflow_name} in {repo_name}: {e}")
        return _create_drift_status(
            workflow_name=workflow.workflow_name,
            # Not has_drift=False: a failed check used to be recorded as clean,
            # which emitted drift.resolved for workflows that were still drifted.
            has_drift=False,
            github_content=None,
            local_content=workflow.workflow_yaml,
            github_sha=None,
            local_sha=workflow.workflow_git_hash,
            message=f"Could not check {repo_name}: {str(e)}",
            drift_type="workflow",
            check_failed=True,
            repo=repo_name,
            branch=branch,
        )


def _process_regular_workflows(db: Session, regular_workflows: List, repo_names: List[str],
                              project_code: str, token: str, use_prefix: bool = True, project_id: int = None,
                              project: "Project" = None, user: str = None) -> List[DriftStatus]:
    """
    Process regular workflows for drift detection across multiple repositories.
    Uses Git Trees API for batch SHA comparison to minimize API calls.

    Yields one status per (workflow, repo, branch): a project can deliver the
    same workflow to several branches, and each is independently drifted or not.

    Returns:
        List[DriftStatus]: List of drift statuses for regular workflows
    """
    drift_results = []

    if not regular_workflows:
        return drift_results

    repo_sha_cache = _prefetch_workflow_shas_per_repo(repo_names, token, db, project, user)

    # Now process each workflow
    for workflow in regular_workflows:
        # Skip workflows with empty or null names
        if not workflow.workflow_name or not workflow.workflow_name.strip():
            print(f"⚠️ Skipping workflow with empty name (ID: {workflow.workflow_id})")
            continue

        formatted_workflow_name = format_workflow_name(workflow.workflow_name, project_code, use_prefix)

        # Check each (repo, branch) this project delivers to
        for (repo_name, branch), workflow_shas in repo_sha_cache.items():
            if "/" not in repo_name or repo_name not in repo_names:
                continue

            owner, repo = repo_name.split("/", 1)

            drift_status = _check_regular_workflow_in_repo(
                db, workflow, repo_name, owner, repo, formatted_workflow_name,
                workflow_shas, project_code, token, project_id, branch
            )
            if drift_status:
                drift_results.append(drift_status)

    return drift_results


def _process_reusable_workflows(db: Session, reusable_workflows: List, user: str,
                               project_code: str, token: str, use_prefix: bool = True,
                               reusable_repo_name: str = None, project_id: int = None) -> List[DriftStatus]:
    """
    Process reusable workflows for drift detection in the dedicated reusable workflow repository.
    Uses Git Trees API for batch SHA comparison to minimize API calls.
    
    Returns:
        List[DriftStatus]: List of drift statuses for reusable workflows
    """
    drift_results = []
    
    if not reusable_workflows:
        return drift_results

    if not reusable_repo_name:
        reusable_repo_name = f"{user}/am-reuseable-workflow"
    if "/" not in reusable_repo_name:
        return drift_results
        
    owner, repo = reusable_repo_name.split("/", 1)

    default_branch = ""
    prefetch_error = None
    try:
        # Get default branch for the reusable workflow repo
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }
        default_branch = get_default_branch(owner, repo, headers)

        # Fetch all workflow SHAs in one API call using Git Trees API
        all_workflow_shas = get_all_workflow_shas(owner, repo, default_branch, token)

        print(f"🔍 Fetched {len(all_workflow_shas)} reusable workflow file SHAs from {reusable_repo_name} using Trees API")

    except Exception as e:
        # None, not {} — same distinction _prefetch_workflow_shas_per_repo makes.
        # An empty mapping means "this repo has no workflow files", which made a
        # rate limit or revoked token report every reusable workflow as deleted
        # from GitHub, and that now drives the Delete Everywhere flow.
        print(f"⚠️ Error fetching workflow SHAs from {reusable_repo_name}: {e}")
        all_workflow_shas = None
        prefetch_error = str(e)

    if all_workflow_shas is None:
        return [
            _create_drift_status(
                workflow_name=w.workflow_name,
                has_drift=False,
                github_content=None,
                local_content=w.workflow_yaml,
                github_sha=None,
                local_sha=w.workflow_git_hash,
                message=f"Could not check {reusable_repo_name}: {prefetch_error}",
                drift_type="reusable_workflow",
                check_failed=True,
                repo=reusable_repo_name,
                branch=default_branch,
            )
            for w in reusable_workflows
            if w.workflow_name and w.workflow_name.strip()
        ]

    for workflow in reusable_workflows:
        # Skip workflows with empty or null names
        if not workflow.workflow_name or not workflow.workflow_name.strip():
            print(f"⚠️ Skipping reusable workflow with empty name (ID: {workflow.workflow_id})")
            continue

        formatted_workflow_name = format_workflow_name(workflow.workflow_name, project_code, use_prefix)

        try:
            # Get the SHA for this workflow from the Trees API result
            github_sha = all_workflow_shas.get(formatted_workflow_name)
            
            # Check if we need to fetch full content
            if github_sha is None:
                # Workflow doesn't exist in GitHub
                github_data = None
            elif workflow.workflow_git_hash == github_sha:
                # SHAs match - no drift, skip fetching full content
                sha_display = github_sha[:7] if github_sha else 'None'
                print(f"⚪ No drift for reusable workflow '{workflow.workflow_name}' in {reusable_repo_name} (SHA match: {sha_display})")
                
                # Create a no-drift status without fetching content
                drift_status = _create_drift_status(
                    workflow_name=workflow.workflow_name,
                    has_drift=False,
                    github_content=workflow.workflow_yaml,  # Use local as proxy since they match
                    local_content=workflow.workflow_yaml,
                    github_sha=github_sha,
                    local_sha=workflow.workflow_git_hash,
                    message=f"Reusable workflow synchronized with {reusable_repo_name}",
                    drift_type="reusable_workflow",
                    repo=reusable_repo_name,
                    branch=default_branch,
                )
                drift_results.append(drift_status)
                continue
            else:
                # SHA differs or workflow was never synced - fetch full content
                print(f"🔍 SHA mismatch for reusable workflow '{workflow.workflow_name}' in {reusable_repo_name} - fetching full content")
                print(f"  Local SHA: {workflow.workflow_git_hash}")
                print(f"  GitHub SHA: {github_sha}")
                github_data = get_workflow_from_github(owner, repo, formatted_workflow_name, token, default_branch=default_branch)

            drift_status = _compare_workflow_content(workflow, github_data, reusable_repo_name, project_code, "reusable_workflow",
                                                     db=db, project_id=project_id, branch=default_branch)
            if drift_status:
                drift_results.append(drift_status)

                # Update git hash if content matches (no drift) even though SHA differed
                if not drift_status.has_drift and github_data:
                    new_github_sha = github_data["sha"]
                    if workflow.workflow_git_hash != new_github_sha:
                        workflow.workflow_git_hash = new_github_sha
                        db.commit()
                        print(f"✅ Updated git hash for reusable workflow '{workflow.workflow_name}': {new_github_sha} (content matched despite SHA difference)")
                        
        except Exception as e:
            print(f"⚠️ Error checking reusable workflow {workflow.workflow_name} in {reusable_repo_name}: {e}")
            drift_results.append(_create_drift_status(
                workflow_name=workflow.workflow_name,
                # Not a clean result: an unchecked workflow used to be recorded
                # as resolved, silently clearing genuine drift.
                has_drift=False,
                github_content=None,
                local_content=workflow.workflow_yaml,
                github_sha=None,
                local_sha=workflow.workflow_git_hash,
                message=f"Could not check {reusable_repo_name}: {str(e)}",
                drift_type="reusable_workflow",
                check_failed=True,
                repo=reusable_repo_name,
                branch=default_branch,
            ))
    
    return drift_results


def _handle_deployment_variables(check_deployment_vars: bool) -> List[DriftStatus]:
    """
    Handle deployment variables drift detection.
    
    Returns:
        List[DriftStatus]: List containing deployment variables drift status if applicable
    """
    if not check_deployment_vars:
        return []
    
    try:
        # For deployment variables, we don't have direct content comparison
        # But if the user has deployment environments configured, we should treat them as changed
        # since they are typically new additions or modifications
        drift_status = _create_drift_status(
            workflow_name="deployment_variables",
            has_drift=True,  # Mark as changed to auto-select in modal
            github_content=None,
            local_content=None,
            github_sha=None,
            local_sha=None,
            message="Deployment variables detected for update",
            drift_type="deployment_vars"
        )
        print(f"✅ Deployment variables marked as changed for auto-selection")
        return [drift_status]
    except Exception as e:
        print(f"⚠️ Error checking deployment variables: {e}")
        return []


def detect_workflow_drift(db: Session, user: str, project_name: str, repo_names: List[str], check_deployment_vars: bool = False) -> List[DriftStatus]:
    """
    Detect drift between workflows stored in database and workflows in GitHub repositories.
    Uses Git SHA comparison for accurate drift detection.
    Only checks workflows that belong to the current project to prevent custom workflows 
    or workflows from other projects from being flagged as drifted.
    
    Returns a list of drift statuses for each workflow.
    """
    # Validate user and get project information
    token, project, project_code = _validate_user_and_get_project(db, user, project_name)
    
    # Get and separate workflows by type
    regular_workflows, reusable_workflows = _get_project_workflows(db, project)
    
    # Get prefix setting from project
    use_prefix = project.use_prefix
    
    # Process all workflow types and collect drift results
    drift_results = []
    drift_results.extend(_process_regular_workflows(
        db, regular_workflows, repo_names, project_code, token, use_prefix,
        project_id=project.project_id, project=project, user=user,
    ))
    drift_results.extend(_process_reusable_workflows(
        db, reusable_workflows, user, project_code, token, use_prefix,
        reusable_repo_name=_get_reusable_workflow_repo(project, user, db),
        project_id=project.project_id
    ))
    drift_results.extend(_handle_deployment_variables(check_deployment_vars))
    
    return drift_results

def create_workflow_version(db: Session, workflow_id: int, content: str, metadata: Optional[dict] = None, commit: bool = True):
    """
    Create a new version entry for a workflow.
    
    Args:
        db: Database session
        workflow_id: ID of the workflow
        content: Workflow YAML content
        metadata: Optional metadata dictionary (author, session info, etc.)
    
    Returns:
        WorkflowVersion: Created version object
    """
    try:
        # Get the current highest version number for this workflow
        max_version = db.query(WorkflowVersion).filter(
            WorkflowVersion.workflow_id == workflow_id
        ).order_by(WorkflowVersion.version_number.desc()).first()
        
        next_version = 1 if not max_version else max_version.version_number + 1
        
        # Create version entry
        version = WorkflowVersion(
            workflow_id=workflow_id,
            version_number=next_version,
            content=content,
            version_metadata=json.dumps(metadata) if metadata else None
        )
        
        db.add(version)
        if commit:
            db.commit()
            db.refresh(version)
        
        print(f"✅ Created workflow version {next_version} for workflow ID {workflow_id}")
        return version
    except Exception as e:
        print(f"❌ Error creating workflow version: {str(e)}")
        if commit:
            db.rollback()
        # Don't fail the entire workflow save if version creation fails
        # This ensures backward compatibility
        return None

def create_or_update_workflow(db, workflow, project_id, is_reusable, last_modified_by=None):
    """
    Create or update a workflow within the scope of a specific project.
    This ensures that each project maintains its own workflows without cross-project interference.
    Automatically creates a version entry on each save.

    When `workflow.original_name` is provided and differs from `workflow.name`, a true rename
    is performed: the existing record is found by `original_name` and its `workflow_name` is
    updated to the new name instead of creating a duplicate entry.
    """
    # Normalize: strip whitespace and convert blank to None
    if last_modified_by:
        last_modified_by = last_modified_by.strip() or None
    new_name = _validate_workflow_name(workflow.name)
    raw_original = getattr(workflow, 'original_name', None)
    # Use isinstance so that non-string values (e.g. None, or MagicMock in tests)
    # are treated as "no original name provided" rather than triggering a rename.
    # WorkflowSchema declares original_name as Optional[str], so at runtime this
    # will always be None or a str when called via the API.
    original_name = _validate_workflow_name(raw_original) if isinstance(raw_original, str) and raw_original.strip() else ''

    # Defense-in-depth: when the project uses the ``AM_{code}_`` prefix, the
    # canonical ``Workflow.workflow_name`` stored in the DB does not include
    # the project prefix (the prefix is re-applied by ``format_workflow_name``
    # on push to GitHub).  If a client accidentally submits a name that
    # already includes the prefix — for example because of a stale frontend
    # that did not split the editable suffix from the locked prefix — strip a
    # single matching prefix here so we never persist a duplicated
    # ``AM_CODE_AM_CODE_name`` segment.
    new_name = _strip_duplicated_project_prefix(db, project_id, new_name)
    new_name = _validate_workflow_name(new_name)
    if original_name:
        original_name = _strip_duplicated_project_prefix(db, project_id, original_name)
        original_name = _validate_workflow_name(original_name)

    is_rename = bool(original_name and original_name.lower() != new_name.lower())

    print(f"✅ Creating/updating workflow '{new_name}' for project {project_id}, reusable: {is_reusable}"
          + (f" (renamed from '{original_name}')" if is_rename else ""))

    existing_workflow = None

    if is_rename:
        # Look up the workflow by its previous name so we perform a true rename
        existing_workflow = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project_id,
            Workflow.workflow_name.ilike(original_name),
            Workflow.reusable_workflow == is_reusable
        ).first()

        if existing_workflow:
            print(f"📌 ✅ Renaming workflow '{original_name}' → '{new_name}' in project {project_id}")
            existing_workflow.workflow_name = new_name

            # Remove any accidental duplicate(s) that may have been created under the new name
            # (can happen if a prior save already ran before this rename path was in place).
            # Fetch ALL duplicates — not just the first — so nothing is left behind.
            duplicates = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == project_id,
                Workflow.workflow_name.ilike(new_name),
                Workflow.reusable_workflow == is_reusable,
                Workflow.workflow_id != existing_workflow.workflow_id
            ).all()
            for dup in duplicates:
                print(f"📌 Removing accidental duplicate workflow '{new_name}' (id={dup.workflow_id})")
                # Before deleting the duplicate, migrate any LinkedReusableWorkflow rows that
                # point to it so we don't silently unlink standard projects.  The duplicate's
                # links are re-targeted to existing_workflow (the canonical renamed record).
                # Use a raw UPDATE so we don't need to load each row individually.
                dup_linked_count = (
                    db.query(LinkedReusableWorkflow)
                    .filter(LinkedReusableWorkflow.workflow_id == dup.workflow_id)
                    .count()
                )
                if dup_linked_count:
                    print(f"  ↳ Migrating {dup_linked_count} LinkedReusableWorkflow row(s) "
                          f"from duplicate id={dup.workflow_id} → id={existing_workflow.workflow_id}")
                    # Delete any links that would create a duplicate (same standard_project_id already
                    # linked to existing_workflow) to avoid a unique-constraint violation on insert.
                    already_linked_project_ids = {
                        r[0] for r in db.query(LinkedReusableWorkflow.standard_project_id)
                        .filter(LinkedReusableWorkflow.workflow_id == existing_workflow.workflow_id)
                        .all()
                    }
                    db.query(LinkedReusableWorkflow).filter(
                        LinkedReusableWorkflow.workflow_id == dup.workflow_id,
                        LinkedReusableWorkflow.standard_project_id.in_(already_linked_project_ids)
                    ).delete(synchronize_session=False)
                    # Re-point the remaining links to the canonical renamed workflow
                    db.query(LinkedReusableWorkflow).filter(
                        LinkedReusableWorkflow.workflow_id == dup.workflow_id
                    ).update({"workflow_id": existing_workflow.workflow_id}, synchronize_session=False)

                # Must delete the ProjectWorkflow association row first because
                # ProjectWorkflow has a FK to Workflow (and SQLite doesn't always
                # enforce FK cascades).  Deleting the association before the
                # Workflow row avoids a constraint violation.
                db.query(ProjectWorkflow).filter_by(
                    project_id=project_id, workflow_id=dup.workflow_id
                ).delete(synchronize_session=False)
                db.delete(dup)
        else:
            print(f"⚠️ Original workflow '{original_name}' not found; treating as new workflow '{new_name}'")

    if existing_workflow is None:
        # Search for an existing workflow within the current project only.
        # Case-insensitive *equality*, not ILIKE: workflow names commonly
        # contain '_', which is a single-character wildcard in SQL LIKE, so
        # saving "ci_build" could match and overwrite an unrelated "ciXbuild".
        # Same reasoning as the reusable duplicate sweep in projects.py.
        existing_workflow = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project_id,
            func.lower(Workflow.workflow_name) == (new_name or "").lower(),
            Workflow.reusable_workflow == is_reusable
        ).first()

    if existing_workflow:
        print(f"📌 ✅ Updating existing workflow in project: {existing_workflow.workflow_name}")
        existing_workflow.workflow_yaml = workflow.content.strip()
        existing_workflow.reusable_workflow = is_reusable
        # Set hash to zeros to indicate local modification (user doesn't use git locally)
        existing_workflow.workflow_git_hash = "0000000000000000000000000000000000000000"

        # Check if this workflow has any open PRs before downgrading status
        has_open_pr = False
        try:
            if is_reusable:
                # Reusable workflows are canonical shared assets: any open PR
                # campaign referencing them — from the owning RWX project or
                # any linking caller, matched by normalized name and scoped to
                # the owning repo(s) — keeps them globally locked.
                has_open_pr = bool(
                    _reusable_workflow_ids_locked_by_open_campaign(
                        db, [existing_workflow.workflow_id]
                    )
                )
            else:
                # Regular workflows: check open PRs against this project's repo.
                # _has_open_pr_for_workflow handles cross-project PR lookups.
                project_repos = db.query(Repo.repo_name).join(ProjectRepo).filter(
                    ProjectRepo.project_id == project_id
                ).limit(1).all()
                if project_repos:
                    repo_name = project_repos[0][0]
                    has_open_pr = _has_open_pr_for_workflow(db, project_id, existing_workflow.workflow_name, repo_name)
        except Exception as e:
            print(f"⚠️ Error checking for open PRs: {e}")
            import traceback
            traceback.print_exc()

        # Update status: if there's an open PR, keep under_review; otherwise set to committed_locally
        if has_open_pr:
            # Preserve under_review status when PR is open
            if existing_workflow.workflow_status != "under_review":
                existing_workflow.workflow_status = "under_review"
            print("✅ Workflow has open PR - preserving status: under_review")
        else:
            # No open PR: editing a "synced" or "under_review" workflow brings it back to committed_locally
            existing_workflow.workflow_status = "committed_locally"
            print(f"✅ Set git hash to zeros (local modification), workflow status: committed_locally")

        # Audit: record who made this change
        if last_modified_by:
            existing_workflow.last_modified_by = last_modified_by
        db.commit()

        # Create version entry for this update
        create_workflow_version(
            db,
            existing_workflow.workflow_id,
            workflow.content.strip(),
            metadata={'action': 'rename' if is_rename else 'update', 'timestamp': datetime.now(timezone.utc).isoformat()}
        )
    else:
        print(f"📌 Creating new workflow for project: {new_name}")
        new_workflow = Workflow(
            workflow_name=new_name,
            workflow_yaml=workflow.content.strip(),
            reusable_workflow=is_reusable,
            # Set hash to zeros for new workflows (not yet pushed to GitHub)
            workflow_git_hash="0000000000000000000000000000000000000000",
            # New workflows start with "new" status
            workflow_status="new",
            # Audit: record who created this workflow
            last_modified_by=last_modified_by
        )
        db.add(new_workflow)
        db.commit()
        db.refresh(new_workflow)
        existing_workflow = new_workflow
        
        # Create project association for new workflow
        db.add(ProjectWorkflow(
            project_id=project_id,
            workflow_id=existing_workflow.workflow_id
        ))
        db.commit()
        print(f"✅ Created project association for workflow {existing_workflow.workflow_id}")
        print(f"✅ Set git hash to zeros (new workflow, not yet pushed), workflow status: new")
        
        # Create initial version entry for this new workflow
        create_workflow_version(
            db, 
            existing_workflow.workflow_id, 
            workflow.content.strip(),
            metadata={'action': 'create', 'timestamp': datetime.now(timezone.utc).isoformat()}
        )


def cleanup_orphaned_workflows(db: Session):
    """
    Remove workflows that are no longer associated with any projects.
    This helps keep the database clean after project deletions.
    """
    try:
        # Find workflows that have no project associations
        orphaned_workflows = db.query(Workflow).outerjoin(ProjectWorkflow).filter(
            ProjectWorkflow.workflow_id.is_(None)
        ).all()
        
        if orphaned_workflows:
            print(f"🧹 Cleaning up {len(orphaned_workflows)} orphaned workflows")
            for workflow in orphaned_workflows:
                print(f"  - Deleting orphaned workflow: {workflow.workflow_name} (ID: {workflow.workflow_id})")
                db.delete(workflow)
            
            db.commit()
            print(f"✅ Cleaned up {len(orphaned_workflows)} orphaned workflows")
        else:
            print("✅ No orphaned workflows found")
            
    except Exception as e:
        print(f"❌ Error cleaning up orphaned workflows: {str(e)}")
        db.rollback()


def _save_pr_to_database(db: Session, project_id: int, repo_name: str,
                        pr_number: int, pr_url: str, branch_name: str,
                        target_branch: str, title: Optional[str] = None,
                        author: Optional[str] = None, body: Optional[str] = None,
                        workflow_names: Optional[str] = None,
                        file_names: Optional[str] = None,
                        campaign_id: Optional[int] = None,
                        is_new_pr: bool = True) -> bool:
    """
    Save or update PR information in the database.

    Args:
        db: Database session
        project_id: Project ID
        repo_name: Full repository name (owner/repo)
        pr_number: GitHub PR number
        pr_url: GitHub PR URL
        branch_name: Actions Manager branch name
        target_branch: Target/base branch name
        title: PR title captured from GitHub (optional)
        author: PR author GitHub login (optional)
        body: PR description/body from GitHub (optional)
        workflow_names: Comma-separated workflow names associated with this PR (optional)
        campaign_id: The PR campaign this row belongs to (optional)
        is_new_pr: True when a brand-new GitHub PR was created in this run.
            When False (commits were added to an existing open PR), the row
            keeps its current campaign instead of moving to the new one.

    Returns:
        True if the PR row was attached to ``campaign_id``, False otherwise.

    Raises:
        Exception: re-raises any database error after rolling back, so callers
            surface the failure instead of silently leaving the PR untracked.
    """
    try:
        # Check if PR entry already exists
        existing_pr = db.query(ProjectPullRequest).filter_by(
            project_id=project_id,
            repo_name=repo_name,
            branch_name=branch_name,
            target_branch=target_branch
        ).first()

        attached_to_campaign = False
        if existing_pr:
            # Update existing PR entry
            existing_pr.pr_number = pr_number
            existing_pr.pr_url = pr_url
            existing_pr.pr_state = "open"
            # A fresh GitHub PR (or a legacy row without a campaign) joins the
            # new campaign; updates to an existing open PR stay in their campaign.
            if campaign_id is not None and (is_new_pr or existing_pr.campaign_id is None):
                existing_pr.campaign_id = campaign_id
                attached_to_campaign = True
            # Overwrite extended fields when provided
            if title is not None:
                existing_pr.title = title
            if author is not None:
                existing_pr.author = author
            if body is not None:
                existing_pr.body = body
            if workflow_names is not None:
                existing_pr.workflow_names = workflow_names
            if file_names is not None:
                existing_pr.file_names = file_names
            print(f"✅ Updated PR entry in database: PR #{pr_number} for {repo_name}")
        else:
            # Create new PR entry
            new_pr = ProjectPullRequest(
                project_id=project_id,
                campaign_id=campaign_id,
                repo_name=repo_name,
                pr_number=pr_number,
                pr_url=pr_url,
                pr_state="open",
                branch_name=branch_name,
                target_branch=target_branch,
                title=title,
                author=author,
                body=body,
                workflow_names=workflow_names,
                file_names=file_names,
            )
            db.add(new_pr)
            attached_to_campaign = campaign_id is not None
            print(f"✅ Saved new PR entry to database: PR #{pr_number} for {repo_name}")

        db.commit()
        return attached_to_campaign

    except Exception as e:
        # Failing to record a PR (e.g. the database schema is missing the
        # campaign migration) must be a loud backend error — silently
        # continuing would leave GitHub PRs untracked or grouped incorrectly.
        print(f"❌ Error saving PR to database: {str(e)}")
        db.rollback()
        raise


def _update_project_pr_state(db: Session, project_id: int, new_state: str) -> None:
    """
    Update the state of a project.
    
    Args:
        db: Database session
        project_id: Project ID
        new_state: New project state (new, draft, open, synced)
    """
    try:
        project = db.query(Project).filter_by(project_id=project_id).first()
        if project:
            project.pr_state = new_state
            db.commit()
            print(f"✅ Updated project state to: {new_state}")
        else:
            print(f"⚠️ Project with ID {project_id} not found")
            
    except Exception as e:
        print(f"❌ Error updating project state: {str(e)}")
        db.rollback()


def _get_linked_workflow_ids_for_project(
    db: Session,
    standard_project_id: int,
    workflow_names: Optional[List[str]] = None,
    only_if_status: Optional[str] = None,
) -> List[int]:
    """Return workflow IDs for linked reusable workflows associated with a standard project.

    Linked workflows live in the RWX project's ProjectWorkflow, so they are not
    reachable via a simple ProjectWorkflow.project_id filter.  This helper
    centralises the LinkedReusableWorkflow join used in several places.

    Args:
        standard_project_id: The owning standard project's ID.
        workflow_names:       If provided, only include workflows whose names are in this list.
        only_if_status:       If provided, only include workflows currently at this status.
    """
    query = (
        db.query(Workflow.workflow_id)
        .join(LinkedReusableWorkflow, LinkedReusableWorkflow.workflow_id == Workflow.workflow_id)
        .filter(LinkedReusableWorkflow.standard_project_id == standard_project_id)
    )
    if only_if_status is not None:
        query = query.filter(Workflow.workflow_status == only_if_status)
    if workflow_names is not None:
        query = query.filter(Workflow.workflow_name.in_(workflow_names))
    return [r[0] for r in query.all()]


def _update_project_workflows_status(db: Session, project_id: int, new_status: str,
                                     only_if_status: Optional[str] = None,
                                     non_reusable_only: bool = False,
                                     workflow_names: Optional[List[str]] = None) -> None:
    """
    Update the workflow_status of all workflows in a project.

    Reusable workflows that are still referenced by an open PR campaign in
    *any* related project (the owning RWX project or any linking caller) are
    never downgraded out of ``under_review`` — the global review lock only
    clears once every campaign is merged or closed.

    Args:
        db: Database session
        project_id: Project ID
        new_status: New workflow status
        only_if_status: If set, only update workflows currently in this status
        non_reusable_only: If True, only update non-reusable (standard) workflows
        workflow_names: If set, only update workflows whose names are in this list
    """
    try:
        query = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project_id
        )
        if only_if_status:
            query = query.filter(Workflow.workflow_status == only_if_status)
        if workflow_names is not None:
            query = query.filter(Workflow.workflow_name.in_(workflow_names))
        if non_reusable_only:
            # isnot(True) matches both False and NULL, so workflows that have
            # reusable_workflow=NULL (older DB records without an explicit value)
            # are correctly treated as non-reusable and will be updated.
            query = query.filter(Workflow.reusable_workflow.isnot(True))
        workflows = query.all()
        if only_if_status == "under_review" and new_status != "under_review":
            # Global lock: a reusable workflow stays under_review while any
            # other project still has an open PR campaign referencing it.
            reusable_ids = [w.workflow_id for w in workflows if w.reusable_workflow]
            locked_ids = _reusable_workflow_ids_locked_by_open_campaign(db, reusable_ids)
            if locked_ids:
                workflows = [w for w in workflows if w.workflow_id not in locked_ids]
                print(
                    f"🔒 Kept {len(locked_ids)} reusable workflow(s) under_review "
                    f"(open PR campaign in another project)"
                )
        for workflow in workflows:
            workflow.workflow_status = new_status
        db.commit()
        print(f"✅ Updated {len(workflows)} workflow(s) status to: {new_status}")
    except Exception as e:
        print(f"❌ Error updating workflow statuses: {str(e)}")
        db.rollback()


def _update_project_custom_files_status(
    db: Session, project_id: int, new_status: str, only_if_status: Optional[str] = None
) -> None:
    """Update file_status for all custom files in a project.

    When transitioning to synced_with_github, rows marked pending_delete are
    hard-deleted because the file has been successfully removed from GitHub.
    """
    try:
        query = db.query(CustomFile).filter(CustomFile.project_id == project_id)
        if only_if_status:
            query = query.filter(CustomFile.file_status == only_if_status)
        files = query.all()
        if new_status == "synced_with_github":
            to_delete = [f for f in files if f.pending_delete]
            to_update = [f for f in files if not f.pending_delete]
            for f in to_delete:
                db.delete(f)
            for f in to_update:
                f.file_status = new_status
        else:
            for f in files:
                f.file_status = new_status
        db.commit()
        print(f"✅ Updated {len(files)} custom file(s) status to: {new_status}")
    except Exception as e:
        print(f"❌ Error updating custom file statuses: {str(e)}")
        db.rollback()


def _update_project_codeowners_status(
    db: Session, project_id: int, new_status: str, only_if_status: Optional[str] = None
) -> None:
    """Update status for all Codeowners records in a project."""
    try:
        query = db.query(Codeowners).filter(Codeowners.project_id == project_id)
        if only_if_status:
            query = query.filter(Codeowners.status == only_if_status)
        records = query.all()
        for r in records:
            r.status = new_status
        db.commit()
        print(f"✅ Updated {len(records)} codeowners record(s) status to: {new_status}")
    except Exception as e:
        print(f"❌ Error updating codeowners statuses: {str(e)}")
        db.rollback()


def _sync_linked_reusable_workflows_after_merge(db: Session, standard_project_id: int) -> None:
    """Reconcile linked reusable workflows after all PRs for a caller project are merged.

    When a caller (standard) project merges its last open PR, linked reusable
    workflows that are still marked 'under_review' need to transition to
    'synced_with_github'.  Their owning RWX project's pr_state should also
    transition to 'synced' when no un-synced workflows remain.
    """
    try:
        linked_wf_ids = _get_linked_workflow_ids_for_project(
            db, standard_project_id, only_if_status="under_review"
        )
        if not linked_wf_ids:
            return

        # Global lock: workflows still referenced by an open PR campaign in
        # any other project (a sibling caller or the owning RWX project) must
        # stay under_review until that campaign is merged or closed.
        locked_ids = _reusable_workflow_ids_locked_by_open_campaign(db, linked_wf_ids)
        if locked_ids:
            print(
                f"🔒 Kept {len(locked_ids)} linked reusable workflow(s) under_review "
                f"(open PR campaign in another project)"
            )
            linked_wf_ids = [wid for wid in linked_wf_ids if wid not in locked_ids]
        if not linked_wf_ids:
            return

        # Transition the linked workflows to synced_with_github
        db.query(Workflow).filter(
            Workflow.workflow_id.in_(linked_wf_ids)
        ).update({"workflow_status": "synced_with_github"}, synchronize_session=False)
        db.commit()
        print(f"✅ Synced {len(linked_wf_ids)} linked reusable workflow(s) → synced_with_github")

        # Determine which RWX projects own these workflows and update their pr_state
        rwx_project_ids = (
            db.query(LinkedReusableWorkflow.rwx_project_id)
            .filter(LinkedReusableWorkflow.workflow_id.in_(linked_wf_ids))
            .distinct()
            .all()
        )
        for (rwx_pid,) in rwx_project_ids:
            # Only transition to "synced" if the RWX project has no remaining
            # under_review workflows (from any caller project or its own PRs).
            remaining = (
                db.query(Workflow)
                .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
                .filter(
                    ProjectWorkflow.project_id == rwx_pid,
                    Workflow.workflow_status == "under_review",
                )
                .count()
            )
            if remaining == 0:
                _update_project_pr_state(db, rwx_pid, "synced")
    except Exception as e:
        print(f"❌ Error syncing linked reusable workflows after merge: {str(e)}")
        db.rollback()


@router.post("/api/save-workflows", responses=_responses(400, 401, 404, 500))
def save_workflows(
    payload: SaveProjectWorkflowsRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    try:
        github_user = _resolve_github_user(x_github_user, payload.github_user)
        project = _find_project_by_name(db, github_user, payload.project_name)

        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)

        # ✅ Save regular workflows
        for workflow in payload.workflows:
            is_reusable = is_reusable_workflow_yaml(workflow.content)
            print(f"✅ ✅ REG: {workflow}")
            create_or_update_workflow(db, workflow, project.project_id, is_reusable=is_reusable, last_modified_by=github_user)

        # ✅ Save reusable workflows
        for workflow in payload.rxworkflows:
            is_reusable = is_reusable_workflow_yaml(workflow.content)
            print(f"✅ ❌ ❌ ❌ RW: {workflow}")
            create_or_update_workflow(db, workflow, project.project_id, is_reusable=is_reusable, last_modified_by=github_user)

        # Update project audit trail and state
        project.last_modified_by = github_user or None
        db.commit()
        old_state = project.pr_state
        if project.pr_state in ["new", "synced"]:
            _update_project_pr_state(db, project.project_id, "draft")
            # Refresh project to get updated state
            db.refresh(project)

        return {
            "message": "Workflows saved successfully",
            "pr_state": project.pr_state,
            "state_changed": old_state != project.pr_state
        }
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"❌ Error in save_workflows endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error saving workflows: {str(e)}")

@router.post("/api/detect-drift", responses=_responses(401, 404, 500))
def detect_drift(
    payload: DriftDetectionRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Detect drift between local workflows and GitHub workflows."""
    try:
        github_user = _resolve_github_user(x_github_user, payload.github_user)
        drift_statuses = detect_workflow_drift(
            db,
            github_user,
            payload.project_name,
            payload.repo_names,
            payload.check_deployment_vars
        )
        
        return {
            "message": "Drift detection completed",
            "drift_results": [status.model_dump() for status in drift_statuses]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/resolve-drift", responses=_responses(400, 401, 404, 500))
def resolve_drift(
    payload: DriftResolutionRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Resolve workflow drift by updating either the database or GitHub."""
    try:
        github_user = _resolve_github_user(x_github_user, payload.github_user)
        if github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
        
        # Get project and workflow
        project = _find_project_by_name(db, github_user, payload.project_name)
        
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)
        
        workflow = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(
                Workflow.workflow_name == payload.workflow_name,
                ProjectWorkflow.project_id == project.project_id,
            )
            .first()
        )
        if not workflow:
            raise HTTPException(status_code=404, detail=_ERR_WORKFLOW_NOT_FOUND)
        
        if payload.resolution == "use_github":
            # Update the database with GitHub content
            if not payload.github_content:
                raise HTTPException(status_code=400, detail="GitHub content required for this resolution")
            
            workflow.workflow_yaml = payload.github_content.strip()
            
            # Store the GitHub SHA if provided
            if payload.github_sha:
                workflow.workflow_git_hash = payload.github_sha
                print(f"✅ Updated git hash for workflow '{payload.workflow_name}': {payload.github_sha}")
            
            db.commit()
            
            return {
                "message": f"✅ Workflow '{payload.workflow_name}' updated in database with GitHub version",
                "action": "database_updated"
            }
            
        elif payload.resolution == "use_local":
            # The local version is already correct, user should push to GitHub
            # This is handled by the existing update-workflow endpoint
            return {
                "message": f"✅ Local version of '{payload.workflow_name}' is correct. Use 'Update GitHub' to sync to repositories.",
                "action": "use_update_github"
            }
            
        else:
            raise HTTPException(status_code=400, detail="Invalid resolution. Use 'use_github' or 'use_local'")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------------
# Drift detection v2 — issue-spec endpoints
# -----------------------------------------------------------------------------

def _drift_status_to_detail(
    workflow,
    drift_status: DriftStatus,
    repo_name: str,
    branch: str,
    project_code: str,
    use_prefix: bool,
    now_iso: str,
    *,
    project_id: Optional[int] = None,
    repo_id: Optional[int] = None,
    is_shared_workflow: bool = False,
    has_repo_override: bool = False,
    override_id: Optional[int] = None,
    affected_repos: Optional[List[str]] = None,
) -> WorkflowDriftDetail:
    """Convert a legacy DriftStatus into the spec WorkflowDriftDetail shape."""
    affected = affected_repos or []
    return WorkflowDriftDetail(
        workflow_id=workflow.workflow_id,
        workflow_name=workflow.workflow_name,
        workflow_filename=format_workflow_name(workflow.workflow_name, project_code, use_prefix),
        repo=repo_name,
        branch=branch,
        has_drift=drift_status.has_drift,
        actionsmanager_yaml=drift_status.local_content,
        github_yaml=drift_status.github_content,
        actionsmanager_sha=drift_status.local_sha,
        github_sha=drift_status.github_sha,
        last_checked=now_iso,
        message=drift_status.message,
        check_failed=drift_status.check_failed,
        deleted_in_github=drift_status.deleted_in_github,
        project_id=project_id,
        repo_id=repo_id,
        is_shared_workflow=is_shared_workflow,
        has_repo_override=has_repo_override,
        override_id=override_id,
        affected_repo_count=len(affected),
        affected_repos=affected,
        source_repo_name=repo_name,
    )


def _match_repo_for_status(status, candidate_repo_names: List[str]) -> Optional[str]:
    """Associate a drift status with a specific repo.

    Producers set ``status.repo`` directly; that is authoritative. The
    message-parsing below is only a fallback for statuses that predate the
    field (or aren't tied to a repo), and cannot express a branch at all —
    which is why the repo/branch pair is carried as data now.
    """
    if getattr(status, "repo", ""):
        return status.repo

    # Longest name first: one repo's name can be a prefix of another's
    # ("acme/api" vs "acme/api-gateway"), and a plain substring scan in
    # arbitrary order would attribute the longer repo's drift to the shorter one.
    for rn in sorted(candidate_repo_names, key=len, reverse=True):
        if rn and rn in (status.message or ""):
            return rn
    if len(candidate_repo_names) == 1:
        return candidate_repo_names[0]
    return None


def _affected_repos_for(workflow_id: int, repo_for_status: str, project_repo_names: List[str],
                         repo_id_by_name: dict, overrides_by_key: dict) -> list:
    """Other repos sharing this workflow with no per-repo override — they'll drift too if the
    project workflow changes without syncing them. Skips repos we couldn't map to a repo_id
    (defensive — should not happen)."""
    affected = []
    for rn in project_repo_names:
        if rn == repo_for_status:
            continue
        other_repo_id = repo_id_by_name.get(rn)
        if other_repo_id is None:
            continue
        if overrides_by_key.get((workflow_id, other_repo_id)):
            continue
        affected.append(rn)
    return affected


def _build_drift_detail_for_status(status, workflows_by_name: dict, only_workflow_id: Optional[int],
                                    candidate_repo_names: List[str], repo_id_by_name: dict,
                                    project_repo_names: List[str], overrides_by_key: dict, project: Project,
                                    now_iso: str) -> Optional[WorkflowDriftDetail]:
    """Turn one legacy DriftStatus into a spec-shaped WorkflowDriftDetail, or None if it should be skipped."""
    wf = workflows_by_name.get(status.workflow_name)
    if not wf:
        return None
    if only_workflow_id is not None and wf.workflow_id != only_workflow_id:
        return None

    repo_for_status = _match_repo_for_status(status, candidate_repo_names)
    if repo_for_status is None:
        # Skip statuses we cannot pin to a repo
        return None

    repo_id = repo_id_by_name.get(repo_for_status)
    is_shared = len(project_repo_names) > 1
    override = overrides_by_key.get((wf.workflow_id, repo_id)) if repo_id else None
    affected = _affected_repos_for(wf.workflow_id, repo_for_status, project_repo_names, repo_id_by_name, overrides_by_key)

    return _drift_status_to_detail(
        wf,
        status,
        repo_for_status,
        # The branch the check actually used. This used to be an independent
        # default-branch lookup, so the branch shown could differ from the one
        # compared against.
        # The branch the check actually used — no second, independent lookup
        # that could disagree with what was compared.
        status.branch,
        project.project_code or "",
        project.use_prefix,
        now_iso,
        project_id=project.project_id,
        repo_id=repo_id,
        is_shared_workflow=is_shared,
        has_repo_override=override is not None,
        override_id=(override.id if override else None),
        affected_repos=affected,
    )


def _collect_project_drift_details(
    db: Session,
    user: str,
    project: Project,
    only_workflow_id: Optional[int] = None,
) -> List[WorkflowDriftDetail]:
    """Run drift detection for a project and return spec-shaped details.

    When ``only_workflow_id`` is provided, the returned list is filtered to
    that single workflow (still per repo/branch).
    """
    repo_names = [
        r.repo_name for r in
        db.query(Repo).join(ProjectRepo).filter(
            ProjectRepo.project_id == project.project_id
        ).all()
    ]

    # Include the reusable workflow repo so reusable drift statuses can be
    # associated to a repo and surfaced via the v2 endpoints.
    reusable_repo = _get_reusable_workflow_repo(project, user, db)
    candidate_repo_names = list(repo_names)
    if reusable_repo and reusable_repo not in candidate_repo_names:
        candidate_repo_names.append(reusable_repo)

    statuses = detect_workflow_drift(
        db, user, project.project_name, repo_names, check_deployment_vars=False
    )

    # Index workflows by name for quick lookup of workflow_id and yaml content
    workflows_by_name = {
        w.workflow_name: w for w in
        db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.project_id
        ).all()
    }

    now_iso = datetime.now(timezone.utc).isoformat()

    # Pre-compute repo metadata used to enrich each drift detail with
    # scope-aware fields (is_shared_workflow / affected_repos / etc).
    project_repo_rows = (
        db.query(Repo).join(ProjectRepo).filter(ProjectRepo.project_id == project.project_id).all()
    )
    repo_id_by_name = {r.repo_name: r.repo_id for r in project_repo_rows}
    project_repo_names = [r.repo_name for r in project_repo_rows]

    # All overrides for this project, indexed by (workflow_id, repo_id)
    override_rows = (
        db.query(RepoWorkflowOverride)
        .filter_by(project_id=project.project_id)
        .all()
    )
    overrides_by_key = {(o.workflow_id, o.repo_id): o for o in override_rows}

    details: List[WorkflowDriftDetail] = []
    for status in statuses:
        detail = _build_drift_detail_for_status(
            status, workflows_by_name, only_workflow_id, candidate_repo_names,
            repo_id_by_name, project_repo_names, overrides_by_key, project,
            now_iso
        )
        if detail:
            details.append(detail)

    return details


NOT_AUTHORIZED_PROJECT_DETAIL = "Not authorized for this project"
DELIVERY_MODE_ERROR_DETAIL = "delivery_mode must be 'pr' or 'direct'"
_ERR_INSUFFICIENT_PROJECT_ROLE = "Insufficient project permissions. Required: project_editor"
_ERR_REPO_NOT_IN_PROJECT = "Repository is not part of this project"


def _require_drift_editor(db: Session, github_user: str, project: Project) -> None:
    """Require at least project_editor to resolve drift.

    Resolving drift writes to GitHub — "Restore Directly" force-pushes over the
    default branch — so read-only access must not be enough. The endpoints
    previously only proved the caller could *see* the project, because
    _find_project_by_name never reads ProjectMembership.project_role.

    Project owners and admin workspace members always pass; everyone else needs
    an explicit project_editor membership.
    """
    account = db.query(Account).filter_by(github_user=github_user).first()
    if not account:
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED_PROJECT_DETAIL)

    # Owning the project is full rights, and owners need no membership row.
    if project.user_id == account.user_id:
        return

    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == account.user_id)
        .first()
    )
    if member and is_project_admin(member):
        return
    if not member:
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED_PROJECT_DETAIL)

    effective_role = check_project_access(db, member, project.project_id)
    if effective_role is None:
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED_PROJECT_DETAIL)
    if effective_role not in ("project_editor", "project_admin"):
        raise HTTPException(status_code=403, detail=_ERR_INSUFFICIENT_PROJECT_ROLE)


def _require_repo_in_project(db: Session, project: Project, repo_name: str, github_user: str) -> None:
    """Require that *repo_name* is a repository this project may write to.

    Without this the resolve endpoints accept any caller-supplied repo and
    commit to it, so the target was effectively attacker-chosen. Mirrors the
    check _resolve_source_repo already performs for adopt-github-version.

    Reusable workflows are the exception: _collect_project_drift_details
    deliberately surfaces drift against the reusable-workflow repo, which for a
    standard project is the *linked RWX project's* repo and so is not in this
    project's project_repos. Rejecting it would make every reusable-workflow
    drift unresolvable from the UI. That repo is derived from the project's own
    links (or the authenticated user), never from the request, so accepting it
    keeps the target out of the caller's control.
    """
    if not repo_name or "/" not in repo_name:
        raise HTTPException(status_code=400, detail="repo must be in 'owner/repo' format")

    normalized = repo_name.strip()

    repo = db.query(Repo).filter(Repo.repo_name == normalized).first()
    if repo:
        in_project = db.query(ProjectRepo).filter_by(
            project_id=project.project_id, repo_id=repo.repo_id
        ).first()
        if in_project:
            return

    if normalized == _get_reusable_workflow_repo(project, github_user, db):
        return

    raise HTTPException(status_code=400, detail=_ERR_REPO_NOT_IN_PROJECT)


def _record_drift_check_failure(db: Session, project: Project, message: str) -> None:
    """Best-effort: persist that this project's drift check could not complete."""
    try:
        _cache_project_drift_summary(db, project, "check_failed", 0, message)
        record_drift_check_failed(db, project, message)
    except Exception:
        db.rollback()


def _determine_drift_summary_status(drifted: List[WorkflowDriftDetail], unchecked: List[WorkflowDriftDetail]) -> str:
    if drifted:
        return "drifted"
    if unchecked:
        # Some repos could not be reached, so "clean" would be a claim we
        # cannot support — the project list must not show a green badge
        # just because GitHub was rate-limiting.
        return "check_failed"
    return "clean"


def _resolve_workflow_owner_project(db: Session, workflow_id: int):
    """Return (workflow, project) or (None, None) for a workflow_id."""
    wf = db.query(Workflow).filter_by(workflow_id=workflow_id).first()
    if not wf:
        return None, None
    pw = db.query(ProjectWorkflow).filter_by(workflow_id=workflow_id).first()
    if not pw:
        return wf, None
    project = db.query(Project).filter_by(project_id=pw.project_id).first()
    return wf, project


def _stored_project_drift_details(db: Session, project: Project) -> List[WorkflowDriftDetail]:
    """Rebuild the drifted-workflow list from persisted state, calling nothing.

    Everything here is either stored on the drift-state row or already local:
    the managed YAML and its hash come from the project's own workflow (or its
    per-repo override), and the rest is what the last check recorded.

    ``github_yaml`` is deliberately left unset. A diff is only meaningful
    against GitHub's *current* content, so the UI fetches it when the user
    opens one rather than replaying a snapshot that may already be stale.
    """
    states = (
        db.query(WorkflowDriftState)
        .filter(
            WorkflowDriftState.project_id == project.project_id,
            WorkflowDriftState.has_drift.is_(True),
        )
        .all()
    )
    if not states:
        return []

    repo_name_by_id = {r.repo_id: r.repo_name for r in db.query(Repo).all()}
    project_repo_rows = (
        db.query(Repo).join(ProjectRepo).filter(ProjectRepo.project_id == project.project_id).all()
    )
    project_repo_names = [r.repo_name for r in project_repo_rows]
    repo_id_by_name = {r.repo_name: r.repo_id for r in project_repo_rows}
    overrides_by_key = {
        (o.workflow_id, o.repo_id): o
        for o in db.query(RepoWorkflowOverride).filter_by(project_id=project.project_id).all()
    }

    details: List[WorkflowDriftDetail] = []
    for state in states:
        workflow = db.query(Workflow).filter_by(workflow_id=state.workflow_id).first()
        repo_name = repo_name_by_id.get(state.repo_id)
        if not workflow or not repo_name:
            continue

        override = overrides_by_key.get((state.workflow_id, state.repo_id))
        expected = _WorkflowExpectedView(workflow, override)
        filename = format_workflow_name(workflow.workflow_name, project.project_code or "", project.use_prefix)
        affected = _affected_repos_for(
            workflow.workflow_id, repo_name, project_repo_names, repo_id_by_name, overrides_by_key
        )

        details.append(WorkflowDriftDetail(
            workflow_id=workflow.workflow_id,
            workflow_name=workflow.workflow_name,
            workflow_filename=filename,
            repo=repo_name,
            branch=state.branch or "",
            has_drift=True,
            actionsmanager_yaml=expected.workflow_yaml,
            github_yaml=None,          # fetched on demand — see docstring
            actionsmanager_sha=expected.workflow_git_hash,
            github_sha=state.github_sha,
            last_checked=(state.last_checked_at.isoformat() if state.last_checked_at else ""),
            message=(
                f"Workflow was deleted from {repo_name}" if state.deleted_in_github
                else f"Workflow content differs between local and {repo_name}"
            ),
            project_id=project.project_id,
            repo_id=state.repo_id,
            is_shared_workflow=len(project_repo_names) > 1,
            has_repo_override=override is not None,
            override_id=(override.id if override else None),
            affected_repos=affected,
            affected_repo_count=len(affected),
            source_repo_name=repo_name,
            deleted_in_github=bool(state.deleted_in_github),
        ))
    return details


def run_project_drift_check(db: Session, user: str, project: Project):
    """Check one project for drift, persist the result, return (drifted, unchecked).

    The single place a live drift check happens. Both "Check now" and the
    background sweep call this, so an automatic check can never diverge from
    the one a user asks for.
    """
    try:
        details = _collect_project_drift_details(db, user, project)
    except HTTPException:
        _record_drift_check_failure(db, project, "Drift detection request failed")
        raise
    except Exception as e:
        _record_drift_check_failure(db, project, str(e))
        raise

    drifted = [d for d in details if d.has_drift and not d.check_failed]
    unchecked = [d for d in details if d.check_failed]
    try:
        _cache_project_drift_summary(
            db,
            project,
            _determine_drift_summary_status(drifted, unchecked),
            len(drifted),
            f"{len(unchecked)} workflow/repo pair(s) could not be checked" if unchecked else None,
        )
        record_drift_transitions(db, project, details)
    except Exception:
        db.rollback()

    return drifted, unchecked


@router.get(
    "/api/projects/{project_id}/drift",
    response_model=ProjectDriftSummary,
    responses={
        401: {"description": NOT_AUTHENTICATED_DETAIL},
        403: {"description": NOT_AUTHORIZED_PROJECT_DETAIL},
        404: {"description": "Project not found"},
        500: {"description": "Unexpected error while computing drift"},
    },
)
def get_project_drift(
    project_id: int,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    refresh: bool = False,
):
    """Project-level drift summary — all drifted workflows/repos/branches.

    Serves the last known state by default, which costs no GitHub API calls, so
    opening a project is free however often it is done. ``refresh=true`` runs a
    live check and updates that state.

    ``last_checked`` is the time the state was actually established, not the
    time of this request — otherwise "clean" would look freshly verified when
    nothing had been checked in days.
    """
    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    project = db.query(Project).filter_by(project_id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=PROJECT_ERROR)

    # Authorization: ensure caller has access to this project via the standard
    # _find_project_by_name() resolution (handles owner / membership / admin).
    accessible = _find_project_by_name(db, github_user, project.project_name)
    if not accessible or accessible.project_id != project_id:
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED_PROJECT_DETAIL)

    if not refresh:
        drifted = _stored_project_drift_details(db, project)
        return ProjectDriftSummary(
            project_id=project.project_id,
            project_name=project.project_name,
            drift_count=len(drifted),
            drifted_workflows=drifted,
            # None when no check has ever run — the UI must say "not checked
            # yet" rather than implying a clean result.
            last_checked=(project.last_drift_check_at.isoformat()
                          if project.last_drift_check_at else None),
            unchecked_count=0,
            stale_reason=project.drift_error_summary,
        )

    try:
        drifted, unchecked = run_project_drift_check(db, github_user, project)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drift detection failed: {e}")

    return ProjectDriftSummary(
        project_id=project.project_id,
        project_name=project.project_name,
        drift_count=len(drifted),
        drifted_workflows=drifted,
        last_checked=datetime.now(timezone.utc).isoformat(),
        unchecked_count=len(unchecked),
    )


@router.get("/api/workflows/{workflow_id}/drift", response_model=WorkflowDriftResponse, responses=_responses(401, 403, 404, 500))
def get_workflow_drift(
    workflow_id: int,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
):
    """Per-workflow drift detail — includes both YAML versions and SHAs per repo/branch."""
    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    wf, project = _resolve_workflow_owner_project(db, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=_ERR_WORKFLOW_NOT_FOUND)
    if not project:
        raise HTTPException(status_code=404, detail="Workflow is not associated with a project")

    accessible = _find_project_by_name(db, github_user, project.project_name)
    if not accessible or accessible.project_id != project.project_id:
        raise HTTPException(status_code=403, detail="Not authorized for this workflow")

    try:
        details = _collect_project_drift_details(db, github_user, project, only_workflow_id=workflow_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drift detection failed: {e}")

    return WorkflowDriftResponse(
        workflow_id=wf.workflow_id,
        workflow_name=wf.workflow_name,
        workflow_filename=format_workflow_name(wf.workflow_name, project.project_code or "", project.use_prefix),
        has_drift=any(d.has_drift for d in details),
        drift_details=details,
        last_checked=datetime.now(timezone.utc).isoformat(),
    )


def _direct_push_workflow_to_branch(
    owner: str,
    repo: str,
    branch: str,
    path: str,
    content_str: str,
    commit_message: str,
    headers: dict,
    user: str,
    db: Session,
    expected_sha: Optional[str] = None,
) -> dict:
    """Push a single workflow file directly to a branch via the Contents API.

    ``expected_sha`` is the blob SHA the caller's decision was based on. When
    given and GitHub has moved on, the push is refused rather than overwriting
    whatever landed in between — otherwise a stale drift view silently reverts
    someone else's fix. Passing None keeps the previous last-write-wins
    behaviour for callers that have no expectation to assert.

    Returns a dict with keys: ``status_code`` (int) and, on success, ``sha`` (str).
    """
    encoded_content = base64.b64encode(content_str.encode()).decode()
    file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    sha, unchanged = _check_existing_workflow_content(file_url, encoded_content, headers, user, db)

    if expected_sha and sha and sha != expected_sha:
        # Reported through the existing {status_code, error} contract rather than
        # raised: this is a low-level push helper, and callers already branch on
        # status_code. Bulk turns it into a per-item failure for free, and the
        # resolve endpoint converts it to a 409 at the HTTP layer where that
        # response is documented.
        return {
            "status_code": 409,
            "error": (
                f"{path} in {owner}/{repo}@{branch} changed since drift was checked. "
                "Re-run the drift check and review the current difference before resolving."
            ),
        }

    if unchanged:
        # Identical content — pushing would create an empty commit, and a
        # double-submit would create two. Report the existing blob as success.
        return {"status_code": 200, "sha": sha, "unchanged": True}

    payload = {
        "message": commit_message,
        "content": encoded_content,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    put_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}"
    resp = github_put(put_url, user, db, json=payload, headers=headers)
    if resp.status_code in (200, 201):
        try:
            new_sha = resp.json().get("content", {}).get("sha")
        except Exception:
            new_sha = None
        return {"status_code": resp.status_code, "sha": new_sha}
    return {"status_code": resp.status_code, "error": resp.text[:500]}


def _apply_use_github_resolution(
    db: Session,
    github_user: str,
    wf: Workflow,
    repo: str,
    formatted_name: str,
    token: str,
    default_branch: Optional[str] = None,
    expected_sha: Optional[str] = None,
) -> dict:
    """Overwrite ``wf``'s local YAML with the current GitHub version for one repo/branch.

    Pure mutation - does not re-check drift afterward. The single-workflow
    endpoint re-checks drift itself for response shaping; a bulk caller
    re-fetches the whole project's drift summary once at the end instead of
    once per item, since a live GitHub diff check per item would be far more
    expensive than the fetch this helper already does.

    ``default_branch``, when supplied, is forwarded to
    ``get_workflow_from_github`` to skip its repo-metadata lookup - pass it
    when resolving several items in the same repo in one request.

    ``expected_sha`` is the blob SHA the user's decision was based on. Adopting
    GitHub's version discards the managed YAML, so if GitHub moved on since the
    drift was shown the user would be accepting content they never saw — the
    mirror image of the stale overwrite the restore path guards against.

    Returns {"success": bool, "github_sha": str|None, "error": str|None,
    "conflict": bool}.
    """
    owner, repo_short = repo.split("/", 1)
    github_data = get_workflow_from_github(owner, repo_short, formatted_name, token, default_branch=default_branch)
    if not github_data:
        return {
            "success": False,
            "github_sha": None,
            "error": f"Workflow '{formatted_name}' not found in {repo}",
        }

    github_content = (github_data.get("content") or "").strip()
    github_sha = github_data.get("sha")

    if expected_sha and github_sha and github_sha != expected_sha:
        return {
            "success": False,
            "conflict": True,
            "github_sha": github_sha,
            "error": (
                f"{formatted_name} in {repo} changed since drift was checked. "
                "Re-run the drift check and review the current difference before resolving."
            ),
        }

    wf.workflow_yaml = github_content
    wf.workflow_git_hash = github_sha
    wf.last_modified_by = github_user
    wf.workflow_status = "synced_with_github"
    db.commit()

    return {"success": True, "github_sha": github_sha, "error": None}


def _resolve_use_github_drift(db: Session, github_user: str, wf, project, payload: ResolveWorkflowDriftRequest,
                               branch: str, workflow_id: int, formatted_name: str, token: str) -> dict:
    """Overwrite local YAML with GitHub's version, then re-check drift to confirm resolution."""
    print(f"🔄 Resolving drift for workflow {workflow_id} (use_github): {payload.repo}@{payload.branch}")
    print(f"  Old local SHA: {wf.workflow_git_hash}")
    print(f"  Old local content length: {len(wf.workflow_yaml or '')}")

    resolution = _apply_use_github_resolution(
        db, github_user, wf, payload.repo, formatted_name, token,
        expected_sha=payload.expected_github_sha,
    )
    if not resolution["success"]:
        if resolution.get("conflict"):
            raise HTTPException(status_code=409, detail=resolution["error"])
        raise HTTPException(status_code=404, detail=resolution["error"])
    github_sha = resolution["github_sha"]

    print(f"  New GitHub SHA: {github_sha}")
    print("  ✅ Database updated and committed")

    # Refresh the workflow from database to ensure we have the latest state
    db.refresh(wf)

    # Re-check drift with the updated workflow to confirm resolution
    print("  🔍 Re-checking drift after resolution...")
    try:
        drift_details = _collect_project_drift_details(
            db, github_user, project, only_workflow_id=workflow_id
        )

        # This re-check is authoritative, so persist it instead of leaving the
        # caches claiming drift that was just resolved. record_drift_transitions
        # only touches the rows it is given, and only_workflow_id scopes those
        # to this workflow.
        record_drift_transitions(db, project, drift_details)
        recompute_project_drift_summary(db, project)

        # Find the specific drift detail for this repo/branch
        matching_drift = None
        for detail in drift_details:
            if detail.repo == payload.repo and detail.branch == branch:
                matching_drift = detail
                break

        if not matching_drift:
            # No drift detail found for this repo/branch after resolution
            print("  ✅ No drift detail found - assuming synced")
            return {
                "message": f"Workflow '{wf.workflow_name}' updated from GitHub version",
                "action": "use_github",
                "workflow_id": wf.workflow_id,
                "repo": payload.repo,
                "branch": branch,
                "state": "synced",
                "stored_hash": wf.workflow_git_hash,
                "github_hash": github_sha,
                "content_matches": True,
            }

        has_drift_after = matching_drift.has_drift
        print(f"  Drift state after resolution: {'drifted' if has_drift_after else 'synced'}")

        if has_drift_after:
            # Drift still exists - something went wrong
            print("  ⚠️ WARNING: Drift was not resolved!")
            print(f"    Local content length: {len(wf.workflow_yaml or '')}")
            print(f"    GitHub content length: {len(matching_drift.github_yaml or '')}")
            print(f"    Message: {matching_drift.message}")

            return {
                "message": f"Drift resolution failed: {matching_drift.message}",
                "action": "use_github",
                "workflow_id": wf.workflow_id,
                "repo": payload.repo,
                "branch": branch,
                "state": "drifted",
                "stored_hash": wf.workflow_git_hash,
                "github_hash": matching_drift.github_sha,
                "content_matches": False,
            }

        print("  ✅ Drift successfully resolved")
        return {
            "message": f"GitHub version kept. Workflow '{wf.workflow_name}' is now synced.",
            "action": "use_github",
            "workflow_id": wf.workflow_id,
            "repo": payload.repo,
            "branch": branch,
            "state": "synced",
            "stored_hash": wf.workflow_git_hash,
            "github_hash": matching_drift.github_sha,
            "content_matches": True,
        }
    except Exception as drift_check_error:
        print(f"  ⚠️ Error re-checking drift: {drift_check_error}")
        # Database was updated, so return success but note drift check failed
        return {
            "message": f"Workflow '{wf.workflow_name}' updated from GitHub version (drift check failed: {str(drift_check_error)})",
            "action": "use_github",
            "workflow_id": wf.workflow_id,
            "repo": payload.repo,
            "branch": branch,
            "state": "unknown",
            "stored_hash": wf.workflow_git_hash,
            "github_hash": github_sha,
        }


def _resolve_restore_actionsmanager_drift(db: Session, github_user: str, wf, project,
                                           payload: ResolveWorkflowDriftRequest, branch: str, workflow_id: int,
                                           owner: str, repo: str, formatted_name: str, headers: dict) -> dict:
    """Push local YAML back to GitHub via direct commit or the PR pipeline."""
    delivery_mode = (payload.delivery_mode or "pr").lower()
    print(f"🔄 Resolving drift for workflow {workflow_id} (restore_actionsmanager, {delivery_mode}): {payload.repo}@{payload.branch}")

    try:
        if delivery_mode == "direct":
            path = f".github/workflows/{formatted_name}"
            commit_msg = (
                f"Restore {formatted_name} from ActionsManager for "
                f"{project.project_code} [skip ci]"
            )
            result = _direct_push_workflow_to_branch(
                owner, repo, branch, path, wf.workflow_yaml or "",
                commit_msg, headers, github_user, db,
                expected_sha=payload.expected_github_sha,
            )
            if result.get("status_code") in (200, 201):
                if result.get("sha"):
                    wf.workflow_git_hash = result["sha"]
                wf.last_modified_by = github_user
                wf.workflow_status = "synced_with_github"
                project.pr_state = "synced"
                db.commit()
                # GitHub now matches the managed version, so any persisted drift
                # for this workflow/repo is stale.
                clear_workflow_drift(db, project, wf.workflow_id, payload.repo, branch)

                print(f"  ✅ Direct push successful, new SHA: {result.get('sha')}")

                return {
                    "message": f"Workflow '{wf.workflow_name}' restored to {payload.repo}@{branch} (direct commit)",
                    "action": "restore_actionsmanager",
                    "delivery_mode": "direct",
                    "workflow_id": wf.workflow_id,
                    "repo": payload.repo,
                    "branch": branch,
                    "state": "synced",
                    "github_sha": result.get("sha"),
                }
            if result.get("status_code") == 409:
                # The file moved on since drift was computed — surface the
                # conflict rather than reporting it as a GitHub push failure.
                raise HTTPException(status_code=409, detail=result.get("error", ""))
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Failed to push workflow to GitHub: {result.get('status_code')} "
                    f"{result.get('error', '')}"
                ),
            )

        if delivery_mode == "pr":
            # Reuse the create-pull-requests pipeline scoped to this one
            # workflow + repo. create_pull_requests is a route function
            # whose signature is (payload, background_tasks, db, ...) - when
            # called directly (not via FastAPI routing) db has no injected
            # default, so background_tasks must be supplied positionally and
            # db passed explicitly. async_mode defaults False, so the
            # BackgroundTasks instance is never used.
            pr_payload = CreatePullRequestsRequest(
                github_user=github_user,
                project_name=project.project_name,
                selected_repos=[payload.repo],
                selected_workflows=[wf.workflow_name],
            )
            pr_result = create_pull_requests(
                pr_payload, BackgroundTasks(), db, github_user=github_user
            )

            print("  ✅ PR created for restoring workflow")

            return {
                "message": f"PR opened to restore '{wf.workflow_name}' in {payload.repo}",
                "action": "restore_actionsmanager",
                "delivery_mode": "pr",
                "workflow_id": wf.workflow_id,
                "repo": payload.repo,
                "branch": branch,
                "state": "pr_pending",
                "pr_result": pr_result,
            }

        raise HTTPException(status_code=400, detail=DELIVERY_MODE_ERROR_DETAIL)
    except HTTPException:
        # Already-shaped errors (GitHub 502, pipeline failures, bad input)
        # carry a useful status + detail - let them through unchanged.
        raise
    except Exception as e:  # noqa: BLE001 - convert unexpected errors to a safe 500
        import traceback
        traceback.print_exc()
        db.rollback()
        # Server-side context for diagnosis - never logs the token/headers.
        print(
            f"❌ Drift restore failed (workflow_id={workflow_id}, "
            f"repo={payload.repo}, branch={branch}, delivery_mode={delivery_mode}): "
            f"{type(e).__name__}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restore workflow via {delivery_mode}: {e}",
        )


@router.post(
    "/api/workflows/{workflow_id}/resolve-drift",
    responses={
        400: {"description": "resolution or delivery_mode is invalid"},
        401: {"description": NOT_AUTHENTICATED_DETAIL},
        403: {"description": "Not authorized for this workflow, or caller lacks project_editor rights"},
        404: {"description": "Workflow, project, or GitHub file not found"},
        409: {"description": _ERR_DRIFT_STALE},
        500: {"description": "Unexpected error during drift restoration"},
        502: {"description": "Upstream GitHub request failed"},
    },
)
def resolve_workflow_drift(
    workflow_id: int,
    payload: ResolveWorkflowDriftRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Resolve drift for a single workflow on a specific repo/branch.

    Resolutions:
      * ``use_github``               – overwrite local YAML with GitHub YAML and refresh hash.
      * ``restore_actionsmanager``   – push local YAML back to GitHub via PR or direct commit.
    """
    github_user = _resolve_github_user(x_github_user, payload.github_user)
    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    wf, project = _resolve_workflow_owner_project(db, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=_ERR_WORKFLOW_NOT_FOUND)
    if not project:
        raise HTTPException(status_code=404, detail="Workflow is not associated with a project")

    accessible = _find_project_by_name(db, github_user, project.project_name)
    if not accessible or accessible.project_id != project.project_id:
        raise HTTPException(status_code=403, detail="Not authorized for this workflow")

    # Resolving drift writes to GitHub, so seeing the project is not enough.
    _require_drift_editor(db, github_user, project)
    # And the target must be one of the project's own repos, not any repo the
    # caller's token happens to be able to write to.
    _require_repo_in_project(db, project, payload.repo, github_user)

    owner, repo = payload.repo.strip().split("/", 1)
    # No silent fallback: this force-pushes over the named branch, and
    # defaulting to "main" because the caller omitted one would overwrite a
    # branch the user never chose.
    branch = (payload.branch or "").strip()
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required to restore a workflow")
    token = user_tokens[github_user]
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }
    formatted_name = format_workflow_name(wf.workflow_name, project.project_code or "", project.use_prefix)

    if payload.resolution == "use_github":
        return _resolve_use_github_drift(db, github_user, wf, project, payload, branch, workflow_id, formatted_name, token)

    if payload.resolution == "restore_actionsmanager":
        return _resolve_restore_actionsmanager_drift(
            db, github_user, wf, project, payload, branch, workflow_id, owner, repo, formatted_name, headers
        )

    raise HTTPException(
        status_code=400,
        detail="resolution must be 'use_github' or 'restore_actionsmanager'",
    )


def _validate_bulk_resolve_items(db: Session, project_id: int, items) -> list:
    """Resolve + validate every item up front.

    Fails the whole batch before any writes if one item doesn't actually
    belong to this project.
    """
    resolved_items = []
    for item in items:
        wf, wf_project = _resolve_workflow_owner_project(db, item.workflow_id)
        if not wf:
            raise HTTPException(status_code=404, detail=f"Workflow {item.workflow_id} not found")
        if not wf_project or wf_project.project_id != project_id:
            raise HTTPException(
                status_code=403,
                detail=f"Workflow {item.workflow_id} is not part of this project",
            )
        if "/" not in item.repo:
            raise HTTPException(status_code=400, detail="repo must be in 'owner/repo' format")
        resolved_items.append((item, wf))
    return resolved_items


def _bulk_resolve_use_github(
    db: Session, github_user: str, project: Project, resolved_items: list, token: str
) -> List[BulkResolveDriftItemResult]:
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }
    # Cache each repo's default branch across items so N drifted workflows in
    # the same repo cost one repo-metadata lookup, not N. Only consulted for
    # items that somehow arrive without a branch — normally the item names the
    # branch the user was looking at, and adopting from any other branch would
    # import a different file than the one they were shown.
    default_branch_cache: dict = {}
    results: List[BulkResolveDriftItemResult] = []
    for item, wf in resolved_items:
        formatted_name = format_workflow_name(wf.workflow_name, project.project_code or "", project.use_prefix)
        try:
            source_branch = item.branch
            if not source_branch:
                if item.repo not in default_branch_cache:
                    owner, repo_short = item.repo.split("/", 1)
                    default_branch_cache[item.repo] = get_default_branch(owner, repo_short, headers, github_user, db)
                source_branch = default_branch_cache[item.repo]

            outcome = _apply_use_github_resolution(
                db, github_user, wf, item.repo, formatted_name, token,
                default_branch=source_branch,
                expected_sha=item.expected_github_sha,
            )
            if outcome["success"]:
                clear_workflow_drift(db, project, wf.workflow_id, item.repo, source_branch)
            results.append(BulkResolveDriftItemResult(
                workflow_id=item.workflow_id,
                repo=item.repo,
                branch=item.branch,
                success=outcome["success"],
                message=outcome["error"] or f"Workflow '{wf.workflow_name}' updated from GitHub version",
            ))
        except Exception as e:  # noqa: BLE001 - convert unexpected errors to a per-item failure
            db.rollback()
            results.append(BulkResolveDriftItemResult(
                workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
                success=False, message=f"Failed to adopt GitHub version: {e}",
            ))
    return results


def _bulk_resolve_restore_direct_push_result(
    item, wf, push_result: dict, project: Project, github_user: str, db: Session, branch: str,
) -> BulkResolveDriftItemResult:
    status_code = push_result.get("status_code")
    if status_code in (200, 201):
        if push_result.get("sha"):
            wf.workflow_git_hash = push_result["sha"]
        wf.last_modified_by = github_user
        wf.workflow_status = "synced_with_github"
        db.commit()
        clear_workflow_drift(db, project, wf.workflow_id, item.repo, branch)
        return BulkResolveDriftItemResult(
            workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
            success=True,
            message=f"Workflow '{wf.workflow_name}' restored to {item.repo}@{branch} (direct commit)",
        )
    if status_code == 409:
        # Stale item: reported on its own row so the rest of the batch
        # still applies, and not dressed up as a push failure.
        return BulkResolveDriftItemResult(
            workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
            success=False, message=push_result.get("error", ""),
        )
    return BulkResolveDriftItemResult(
        workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
        success=False,
        message=(
            f"Failed to push workflow to GitHub: "
            f"{status_code} {push_result.get('error', '')}"
        ),
    )


def _bulk_resolve_restore_direct_item(
    db: Session, github_user: str, project: Project, item, wf, headers: dict,
) -> BulkResolveDriftItemResult:
    owner, repo_short = item.repo.split("/", 1)
    branch = (item.branch or "").strip()
    formatted_name = format_workflow_name(wf.workflow_name, project.project_code or "", project.use_prefix)
    if not branch:
        # Fail this item rather than force-pushing over "main" by default.
        return BulkResolveDriftItemResult(
            workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
            success=False, message="branch is required to restore a workflow",
        )
    path = f".github/workflows/{formatted_name}"
    commit_msg = f"Restore {formatted_name} from ActionsManager for {project.project_code} [skip ci]"
    try:
        push_result = _direct_push_workflow_to_branch(
            owner, repo_short, branch, path, wf.workflow_yaml or "",
            commit_msg, headers, github_user, db,
            expected_sha=item.expected_github_sha,
        )
        return _bulk_resolve_restore_direct_push_result(item, wf, push_result, project, github_user, db, branch)
    except Exception as e:  # noqa: BLE001 - convert unexpected errors to a per-item failure
        db.rollback()
        return BulkResolveDriftItemResult(
            workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
            success=False, message=f"Failed to restore workflow directly: {e}",
        )


def _bulk_resolve_restore_direct(
    db: Session, github_user: str, project: Project, resolved_items: list, token: str
) -> List[BulkResolveDriftItemResult]:
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }
    results: List[BulkResolveDriftItemResult] = [
        _bulk_resolve_restore_direct_item(db, github_user, project, item, wf, headers)
        for item, wf in resolved_items
    ]

    # Mirrors _handle_sync_direct_push's all_ok aggregate pattern for
    # the equivalent "push local content out to GitHub directly"
    # action - results here contains only this branch's items.
    project.pr_state = "synced" if all(r.success for r in results) else "draft"
    db.commit()
    return results


def _build_pr_item_result(item, wf, repo: str, matching: dict, top_level_error) -> BulkResolveDriftItemResult:
    ok = matching.get("status") in ("pr_created", "pr_updated")
    if ok:
        message = f"PR opened to restore '{wf.workflow_name}' in {repo}"
    else:
        message = (
            f"Failed to create PR for '{wf.workflow_name}' in {repo}: "
            f"{matching.get('error') or top_level_error or 'unknown error'}"
        )
    return BulkResolveDriftItemResult(
        workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
        success=ok, message=message,
        pr_url=matching.get("pr_url") if ok else None,
    )


def _bulk_resolve_pr_group(
    db: Session, github_user: str, project: Project, repo: str, group: list,
) -> List[BulkResolveDriftItemResult]:
    """Create one PR covering every workflow in ``group`` (all share ``repo``)."""
    workflow_names = [wf.workflow_name for _item, wf in group]
    try:
        pr_payload = CreatePullRequestsRequest(
            github_user=github_user,
            project_name=project.project_name,
            selected_repos=[repo],
            selected_workflows=workflow_names,
        )
        pr_result = create_pull_requests(
            pr_payload, BackgroundTasks(), db, github_user=github_user
        )
        pr_results_by_key = pr_result.get("results", {}) if isinstance(pr_result, dict) else {}
        top_level_error = pr_results_by_key.get("error") if isinstance(pr_results_by_key, dict) else None
        results = []
        for item, wf in group:
            branch = item.branch or "main"
            matching = pr_results_by_key.get(f"{repo} on {branch}", {})
            matching = matching if isinstance(matching, dict) else {}
            results.append(_build_pr_item_result(item, wf, repo, matching, top_level_error))
        return results
    except HTTPException as e:
        return [
            BulkResolveDriftItemResult(
                workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
                success=False, message=str(e.detail),
            )
            for item, wf in group
        ]
    except Exception as e:  # noqa: BLE001 - convert unexpected errors to a per-item failure
        db.rollback()
        return [
            BulkResolveDriftItemResult(
                workflow_id=item.workflow_id, repo=item.repo, branch=item.branch,
                success=False, message=f"Failed to create PR: {e}",
            )
            for item, wf in group
        ]


def _bulk_resolve_restore_pr(
    db: Session, github_user: str, project: Project, resolved_items: list
) -> List[BulkResolveDriftItemResult]:
    """Group items by repo and call create_pull_requests once per repo.

    Multiple workflows restored to the SAME repo land in one PR -
    _process_regular_workflows_update already commits every workflow in
    selected_workflows to a single Actions Manager branch/PR per repo (branch
    isn't forwarded to create_pull_requests - it resolves target branches
    itself from the project's branch_option, same as the single-item
    endpoint).
    """
    by_repo: dict = {}
    for item, wf in resolved_items:
        by_repo.setdefault(item.repo, []).append((item, wf))

    results: List[BulkResolveDriftItemResult] = []
    for repo, group in by_repo.items():
        results.extend(_bulk_resolve_pr_group(db, github_user, project, repo, group))
    return results


@router.post(
    "/api/projects/{project_id}/drift/bulk-resolve",
    response_model=BulkResolveDriftResponse,
    responses={
        400: {"description": "Invalid resolution, delivery_mode, repo format, or empty items list"},
        401: {"description": NOT_AUTHENTICATED_DETAIL},
        403: {"description": NOT_AUTHORIZED_PROJECT_DETAIL},
        404: {"description": "Project or workflow not found"},
        409: {"description": _ERR_DRIFT_STALE},
        500: {"description": "Unexpected error during drift resolution"},
    },
)
def bulk_resolve_project_drift(
    project_id: int,
    payload: BulkResolveDriftRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Resolve drift for multiple workflows in one request.

    All items must belong to workflows owned by ``project_id``. Partial
    failure is supported - one bad item doesn't block the rest, matching the
    existing per-repo loop-and-collect-results pattern already used by
    ``_handle_sync_direct_push``.
    """
    github_user = _resolve_github_user(x_github_user, payload.github_user)
    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    if payload.resolution not in ("use_github", "restore_actionsmanager"):
        raise HTTPException(
            status_code=400,
            detail="resolution must be 'use_github' or 'restore_actionsmanager'",
        )
    if not payload.items:
        raise HTTPException(status_code=400, detail="items must not be empty")

    project = db.query(Project).filter_by(project_id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=PROJECT_ERROR)

    accessible = _find_project_by_name(db, github_user, project.project_name)
    if not accessible or accessible.project_id != project_id:
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED_PROJECT_DETAIL)

    # Bulk resolve writes to GitHub for every item, so require editor rights.
    _require_drift_editor(db, github_user, project)

    resolved_items = _validate_bulk_resolve_items(db, project_id, payload.items)
    # Validate every target repo up front — the batch is rejected whole rather
    # than pushing to the valid repos and failing partway.
    for item, _wf in resolved_items:
        _require_repo_in_project(db, project, item.repo, github_user)
    token = user_tokens[github_user]

    if payload.resolution == "use_github":
        results = _bulk_resolve_use_github(db, github_user, project, resolved_items, token)
    else:  # restore_actionsmanager
        delivery_mode = (payload.delivery_mode or "pr").lower()
        if delivery_mode not in ("pr", "direct"):
            raise HTTPException(status_code=400, detail=DELIVERY_MODE_ERROR_DETAIL)

        if delivery_mode == "direct":
            results = _bulk_resolve_restore_direct(db, github_user, project, resolved_items, token)
        else:
            results = _bulk_resolve_restore_pr(db, github_user, project, resolved_items)

    return BulkResolveDriftResponse(success=all(r.success for r in results), results=results)


# -----------------------------------------------------------------------------
# Scope-aware drift resolution (issue: design-level drift fix)
# -----------------------------------------------------------------------------

ADOPT_PROJECT_AND_SYNC = "adopt_project_and_sync"
ADOPT_LOCAL_ONLY = "adopt_local_only"
CREATE_REPO_OVERRIDE = "create_repo_override"

_VALID_RESOLUTION_MODES = {ADOPT_PROJECT_AND_SYNC, ADOPT_LOCAL_ONLY, CREATE_REPO_OVERRIDE}


def _validate_adopt_github_request(
    db: Session,
    payload: AdoptGithubVersionRequest,
    github_user: str,
) -> tuple:
    """Validate authentication, authorization, and return validated entities.

    Returns:
        tuple: (project, workflow, source_repo, token, formatted_name, owner, repo)

    Raises:
        HTTPException: On validation failure
    """
    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    if payload.resolution_mode not in _VALID_RESOLUTION_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"resolution_mode must be one of: {sorted(_VALID_RESOLUTION_MODES)}",
        )

    project = db.query(Project).filter_by(project_id=payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail=PROJECT_ERROR)

    accessible = _find_project_by_name(db, github_user, project.project_name)
    if not accessible or accessible.project_id != project.project_id:
        raise HTTPException(status_code=403, detail=NOT_AUTHORIZED_PROJECT_DETAIL)

    # Adopting can push to every project repo, so require editor rights.
    # (_resolve_source_repo below already checks the repo belongs to the project.)
    _require_drift_editor(db, github_user, project)

    workflow = db.query(Workflow).filter_by(workflow_id=payload.workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail=_ERR_WORKFLOW_NOT_FOUND)

    pw = db.query(ProjectWorkflow).filter_by(
        project_id=project.project_id, workflow_id=workflow.workflow_id,
    ).first()
    if not pw:
        raise HTTPException(status_code=404, detail="Workflow is not associated with this project")

    source_repo = _resolve_source_repo(db, payload, project)
    if "/" not in source_repo.repo_name:
        raise HTTPException(status_code=400, detail="Source repo must be in 'owner/repo' format")

    owner, repo = source_repo.repo_name.split("/", 1)
    token = user_tokens[github_user]
    formatted_name = format_workflow_name(
        workflow.workflow_name, project.project_code or "", project.use_prefix,
    )

    return project, workflow, source_repo, token, formatted_name, owner, repo


def _resolve_source_repo(db: Session, payload: AdoptGithubVersionRequest, project: Project) -> Repo:
    """Resolve source repo by id or name and validate it belongs to the project.

    Returns:
        Repo: The resolved source repo

    Raises:
        HTTPException: If repo not found or not part of the project
    """
    source_repo = None
    if payload.repo_id is not None:
        source_repo = db.query(Repo).filter_by(repo_id=payload.repo_id).first()
    if source_repo is None and payload.repo_name:
        source_repo = db.query(Repo).filter_by(repo_name=payload.repo_name).first()
    if source_repo is None:
        raise HTTPException(status_code=404, detail="Source repo not found")

    in_project = db.query(ProjectRepo).filter_by(
        project_id=project.project_id, repo_id=source_repo.repo_id,
    ).first()
    if not in_project:
        raise HTTPException(status_code=400, detail="Source repo is not part of this project")

    return source_repo


def _fetch_github_content_and_affected_repos(
    db: Session,
    project: Project,
    workflow: Workflow,
    source_repo: Repo,
    formatted_name: str,
    owner: str,
    repo: str,
    token: str,
    branch: Optional[str] = None,
) -> tuple:
    """Fetch GitHub workflow content and identify affected repos.

    ``branch`` is the branch whose drift is being resolved. Falling back to the
    repo default would adopt a different file than the one the user was shown.

    Returns:
        tuple: (github_content, github_sha, affected_repos)

    Raises:
        HTTPException: If workflow not found on GitHub
    """
    github_data = get_workflow_from_github(owner, repo, formatted_name, token, default_branch=branch)
    if not github_data:
        where = f"{source_repo.repo_name}@{branch}" if branch else source_repo.repo_name
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{formatted_name}' not found in {where}",
        )
    github_content = (github_data.get("content") or "").strip()
    github_sha = github_data.get("sha")

    project_repos = (
        db.query(Repo).join(ProjectRepo).filter(
            ProjectRepo.project_id == project.project_id,
        ).all()
    )
    overrides_by_repo = {
        o.repo_id: o for o in db.query(RepoWorkflowOverride).filter_by(
            project_id=project.project_id, workflow_id=workflow.workflow_id,
        ).all()
    }
    affected_repos = [
        r for r in project_repos
        if r.repo_id != source_repo.repo_id and r.repo_id not in overrides_by_repo
    ]

    return github_content, github_sha, affected_repos


def _handle_create_repo_override(
    db: Session,
    project: Project,
    workflow: Workflow,
    source_repo: Repo,
    github_content: str,
    github_sha: str,
    github_user: str,
    affected_repos: list,
) -> dict:
    """Handle CREATE_REPO_OVERRIDE resolution mode.

    Creates or updates a per-repo override without modifying the project workflow.

    Returns:
        dict: API response for the override operation
    """
    existing = db.query(RepoWorkflowOverride).filter_by(
        project_id=project.project_id,
        repo_id=source_repo.repo_id,
        workflow_id=workflow.workflow_id,
    ).first()

    if existing:
        existing.workflow_yaml = github_content
        existing.workflow_git_hash = github_sha
        existing.source_repo_name = source_repo.repo_name
        existing.last_modified_by = github_user
        override = existing
        created = False
    else:
        override = RepoWorkflowOverride(
            project_id=project.project_id,
            repo_id=source_repo.repo_id,
            workflow_id=workflow.workflow_id,
            workflow_name=workflow.workflow_name,
            workflow_yaml=github_content,
            workflow_git_hash=github_sha,
            source_repo_name=source_repo.repo_name,
            last_modified_by=github_user,
        )
        db.add(override)
        created = True

    db.commit()
    db.refresh(override)
    # Invalidate cached overrides for this project
    db.info.get("repo_workflow_overrides_by_project", {}).pop(project.project_id, None)

    return {
        "success": True,
        "message": (
            f"Repo override {'created' if created else 'updated'} for "
            f"{source_repo.repo_name}. The shared project workflow was not modified."
        ),
        "resolution_mode": CREATE_REPO_OVERRIDE,
        "updated_project_workflow": False,
        "created_or_updated_override": {
            "override_id": override.id,
            "project_id": override.project_id,
            "repo_id": override.repo_id,
            "workflow_id": override.workflow_id,
            "workflow_name": override.workflow_name,
            "source_repo_name": override.source_repo_name,
            "workflow_git_hash": override.workflow_git_hash,
        },
        "affected_repos": [r.repo_name for r in affected_repos],
        "sync_results": None,
        "new_drift_status": "synced",
    }


def _update_project_workflow(
    db: Session,
    workflow: Workflow,
    github_content: str,
    github_sha: str,
    github_user: str,
) -> None:
    """Update the project workflow content from GitHub version."""
    workflow.workflow_yaml = github_content
    workflow.workflow_git_hash = github_sha
    workflow.last_modified_by = github_user
    workflow.workflow_status = "synced_with_github"
    db.commit()
    db.refresh(workflow)


def _handle_adopt_local_only(
    db: Session,
    project: Project,
    source_repo: Repo,
    affected_repos: list,
) -> dict:
    """Handle ADOPT_LOCAL_ONLY resolution mode.

    Returns:
        dict: API response for the local-only adoption
    """
    if affected_repos and project.pr_state == "synced":
        project.pr_state = "draft"
        db.commit()

    return {
        "success": True,
        "message": (
            f"Project workflow updated from GitHub version in "
            f"{source_repo.repo_name}. Other repositories using this "
            f"shared workflow may now show drift until they are synced."
        ),
        "resolution_mode": ADOPT_LOCAL_ONLY,
        "updated_project_workflow": True,
        "created_or_updated_override": None,
        "affected_repos": [r.repo_name for r in affected_repos],
        "sync_results": None,
        "new_drift_status": "drifted_on_other_repos" if affected_repos else "synced",
    }


def _get_target_repos_for_sync(
    payload: AdoptGithubVersionRequest,
    affected_repos: list,
) -> list:
    """Filter affected repos by caller-supplied target_repo_ids when present.

    Returns:
        list: Target repos to sync
    """
    if payload.target_repo_ids is not None:
        target_set = set(payload.target_repo_ids)
        return [r for r in affected_repos if r.repo_id in target_set]
    return list(affected_repos)


def _handle_sync_direct_push(
    db: Session,
    project: Project,
    workflow: Workflow,
    source_repo: Repo,
    target_repos: list,
    formatted_name: str,
    github_content: str,
    token: str,
    github_user: str,
) -> dict:
    """Handle direct push delivery mode for adopt_project_and_sync.

    Returns:
        dict: API response for the direct push sync
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }
    sync_results: dict = {"delivery_mode": "direct", "repos": []}
    all_ok = True
    path = f".github/workflows/{formatted_name}"
    commit_msg = (
        f"Sync {formatted_name} from ActionsManager for "
        f"{project.project_code} [skip ci]"
    )

    for r in target_repos:
        t_owner, t_repo = r.repo_name.split("/", 1)
        try:
            t_branch = get_default_branch(t_owner, t_repo, headers, github_user, db)
        except Exception as e:
            # Report the failure for this repo instead of pushing to "main" —
            # if we could not read the repo's metadata we do not know that
            # "main" even exists, let alone that it is the right target.
            all_ok = False
            sync_results["repos"].append({
                "repo": r.repo_name,
                "success": False,
                "error": f"Could not resolve target branch: {e}",
            })
            continue

        result = _direct_push_workflow_to_branch(
            t_owner, t_repo, t_branch, path, github_content,
            commit_msg, headers, github_user, db,
        )
        ok = result.get("status_code") in (200, 201)
        sync_results["repos"].append({
            "repo": r.repo_name,
            "branch": t_branch,
            "status": "synced" if ok else "failed",
            "github_sha": result.get("sha"),
            "error": None if ok else result.get("error"),
        })
        if ok:
            clear_workflow_drift(db, project, workflow.workflow_id, r.repo_name, t_branch)
        else:
            all_ok = False

    project.pr_state = "synced" if all_ok else "draft"
    db.commit()

    return {
        "success": all_ok,
        "message": (
            f"Project workflow adopted from {source_repo.repo_name} and "
            f"directly pushed to {len(target_repos)} repo(s)."
            if all_ok else
            f"Project workflow adopted from {source_repo.repo_name}, but "
            f"some repos failed to sync. See sync_results."
        ),
        "resolution_mode": ADOPT_PROJECT_AND_SYNC,
        "updated_project_workflow": True,
        "created_or_updated_override": None,
        "affected_repos": [r.repo_name for r in target_repos],
        "sync_results": sync_results,
        "new_drift_status": "synced" if all_ok else "partial_failure",
    }


def _handle_sync_pr_mode(
    db: Session,
    project: Project,
    workflow: Workflow,
    source_repo: Repo,
    target_repos: list,
    github_user: str,
) -> dict:
    """Handle PR delivery mode for adopt_project_and_sync.

    Returns:
        dict: API response for the PR-based sync
    """
    pr_payload = CreatePullRequestsRequest(
        github_user=github_user,
        project_name=project.project_name,
        selected_repos=[r.repo_name for r in target_repos],
        selected_workflows=[workflow.workflow_name],
    )
    # create_pull_requests is a route function (payload, background_tasks, db,
    # ...); called directly it needs background_tasks supplied and db passed
    # explicitly. async_mode defaults False, so BackgroundTasks() is unused.
    pr_result = create_pull_requests(
        pr_payload, BackgroundTasks(), db, github_user=github_user
    )

    if project.pr_state in ("new", "draft", "synced"):
        project.pr_state = "open"
        db.commit()

    sync_results: dict = {
        "delivery_mode": "pr",
        "repos": [{"repo": r.repo_name, "status": "pr_requested"} for r in target_repos],
        "pr_result": pr_result,
    }

    return {
        "success": True,
        "message": (
            f"Project workflow adopted from {source_repo.repo_name}. PR(s) "
            f"opened to sync {len(target_repos)} repo(s)."
        ),
        "resolution_mode": ADOPT_PROJECT_AND_SYNC,
        "updated_project_workflow": True,
        "created_or_updated_override": None,
        "affected_repos": [r.repo_name for r in target_repos],
        "sync_results": sync_results,
        "new_drift_status": "pr_pending",
    }


def _handle_adopt_project_and_sync(
    db: Session,
    payload: AdoptGithubVersionRequest,
    project: Project,
    workflow: Workflow,
    source_repo: Repo,
    affected_repos: list,
    formatted_name: str,
    github_content: str,
    token: str,
    github_user: str,
) -> dict:
    """Handle ADOPT_PROJECT_AND_SYNC resolution mode.

    Returns:
        dict: API response for the sync operation

    Raises:
        HTTPException: If delivery_mode is invalid
    """
    delivery_mode = (payload.delivery_mode or "pr").lower()
    if delivery_mode not in ("pr", "direct"):
        raise HTTPException(status_code=400, detail=DELIVERY_MODE_ERROR_DETAIL)

    target_repos = _get_target_repos_for_sync(payload, affected_repos)

    if not target_repos:
        return {
            "success": True,
            "message": (
                f"Project workflow adopted from {source_repo.repo_name}. "
                "No other repositories require syncing."
            ),
            "resolution_mode": ADOPT_PROJECT_AND_SYNC,
            "updated_project_workflow": True,
            "created_or_updated_override": None,
            "affected_repos": [],
            "sync_results": {"delivery_mode": delivery_mode, "repos": []},
            "new_drift_status": "synced",
        }

    if delivery_mode == "direct":
        return _handle_sync_direct_push(
            db, project, workflow, source_repo, target_repos, formatted_name,
            github_content, token, github_user,
        )

    return _handle_sync_pr_mode(
        db, project, workflow, source_repo, target_repos, github_user,
    )


@router.post(
    "/api/drift/adopt-github-version",
    responses={
        400: {"description": "Invalid resolution_mode, delivery_mode, or repo format"},
        401: {"description": NOT_AUTHENTICATED_DETAIL},
        403: {"description": NOT_AUTHORIZED_PROJECT_DETAIL},
        404: {"description": "Project or workflow not found"},
        409: {"description": _ERR_DRIFT_STALE},
        500: {"description": "Unexpected error during drift adoption"},
    },
)
def adopt_github_version(
    payload: AdoptGithubVersionRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Scope-aware drift resolution flow.

    Replaces the simple "Keep GitHub Version" action with three explicit modes:

      * ``adopt_project_and_sync`` – Use the GitHub version from the source repo
        as the new project workflow content, then sync the other repos in the
        project (via PR or direct commit) so they don't silently drift.
      * ``adopt_local_only``       – Update only the local project workflow
        (legacy behaviour). The caller must accept that other repos sharing the
        workflow may now show drift.
      * ``create_repo_override``   – Record a per-repo override so the source
        repo can intentionally diverge from the shared project workflow without
        re-triggering drift on every detection cycle.
    """
    github_user = _resolve_github_user(x_github_user, payload.github_user)

    # Validate request and get entities
    project, workflow, source_repo, token, formatted_name, owner, repo = (
        _validate_adopt_github_request(db, payload, github_user)
    )

    # Fetch GitHub content and identify affected repos
    github_content, github_sha, affected_repos = _fetch_github_content_and_affected_repos(
        db, project, workflow, source_repo, formatted_name, owner, repo, token, payload.branch,
    )

    # Handle CREATE_REPO_OVERRIDE mode
    if payload.resolution_mode == CREATE_REPO_OVERRIDE:
        return _handle_create_repo_override(
            db, project, workflow, source_repo, github_content, github_sha,
            github_user, affected_repos,
        )

    # Update project workflow for ADOPT_LOCAL_ONLY and ADOPT_PROJECT_AND_SYNC
    _update_project_workflow(db, workflow, github_content, github_sha, github_user)
    # The managed version now matches GitHub in the source repo, so its
    # persisted drift is resolved. Other repos are left alone — they may
    # legitimately still drift against the newly adopted content.
    clear_workflow_drift(db, project, workflow.workflow_id, source_repo.repo_name, payload.branch)

    # Handle ADOPT_LOCAL_ONLY mode
    if payload.resolution_mode == ADOPT_LOCAL_ONLY:
        return _handle_adopt_local_only(db, project, source_repo, affected_repos)

    # Handle ADOPT_PROJECT_AND_SYNC mode
    return _handle_adopt_project_and_sync(
        db, payload, project, workflow, source_repo, affected_repos,
        formatted_name, github_content, token, github_user,
    )


def _get_project_and_token(payload: "CreatePullRequestsRequest", db: Session, github_user: str = None):
    """Validate authentication and return (token, project).

    ``github_user`` overrides ``payload.github_user`` when provided so that
    callers can pass the header-derived identity instead of trusting the body.
    """
    user = github_user or payload.github_user or ""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
    token = user_tokens[user]
    project = _find_project_by_name(db, user, payload.project_name)
    if not project:
        raise HTTPException(status_code=404, detail=PROJECT_ERROR)
    return token, project


def _get_filtered_repo_names(project: Project, selected_repos, db: Session):
    """Return repo names for the project, filtered by selected_repos when provided."""
    project_repos = db.query(Repo).join(ProjectRepo).filter(
        ProjectRepo.project_id == project.project_id
    ).all()
    if not project_repos:
        raise HTTPException(status_code=404, detail="No repositories found for this project")
    repo_names = [repo.repo_name for repo in project_repos]
    if selected_repos is not None:
        if not selected_repos:
            raise HTTPException(status_code=400, detail="No valid repositories selected")
        repo_names = [r for r in repo_names if r in selected_repos]
    if not repo_names:
        raise HTTPException(status_code=400, detail="No valid repositories selected")
    return repo_names


def _get_validation_repo_name(project: Project, db: Session) -> Optional[str]:
    if not getattr(project, "validation_repo_id", None):
        return None
    repo = db.query(Repo).filter(Repo.repo_id == project.validation_repo_id).first()
    return repo.repo_name if repo else None


def _set_preflight_result(
    project: Project,
    status: str,
    db: Session,
    error: Optional[str] = None,
    pr_url: Optional[str] = None,
) -> None:
    project.last_preflight_status = status
    project.last_preflight_run_at = datetime.now(timezone.utc)
    project.last_preflight_error = (error[:500] if error else None)
    project.last_preflight_pr_url = pr_url
    db.commit()


def _sanitize_preflight_error(value: object) -> str:
    message = str(value or "Preflight validation failed.")
    message = re.sub(r"(token|authorization)\s+[A-Za-z0-9_.\-:]+", r"\1 [redacted]", message, flags=re.IGNORECASE)
    message = re.sub(r"(ghp|github_pat)_[A-Za-z0-9_]+", "[redacted]", message)
    return message[:500]


def _extract_preflight_results(results: dict, validation_repo: str) -> tuple[list, Optional[str]]:
    """Extract failures and PR URL from preflight workflow processing results."""
    failed = []
    pr_url = None
    for result in results.values():
        if not isinstance(result, dict) or result.get("status") not in ["pr_created", "pr_updated"]:
            failed.append(result.get("error") if isinstance(result, dict) else "Preflight failed")
        elif not pr_url:
            try:
                pr_number = int(result.get("pr_number"))
                pr_url = f"https://github.com/{validation_repo}/pull/{pr_number}"
            except (TypeError, ValueError):
                pr_url = None
    return failed, pr_url


def _compute_preflight_content_hash(workflow_dicts: list, validation_repo: str) -> str:
    """Return a stable SHA-256 fingerprint of a set of workflows + validation repo.

    The hash is computed over all regular workflows for the project (sorted by name)
    and the validation repository name so that any content change — editing YAML,
    adding/removing a workflow, renaming one, or changing the validation repository —
    produces a different fingerprint and invalidates a prior approval.
    """
    sorted_wfs = sorted(workflow_dicts, key=lambda w: (w.get("name") or ""))
    fingerprint_data = {
        "validation_repo": validation_repo,
        "workflows": [{"name": w.get("name"), "content": w.get("content")} for w in sorted_wfs],
    }
    return hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()


def _compute_current_project_preflight_hash(project: Project, db: Session) -> Optional[str]:
    """Compute the preflight fingerprint for the project's current workflow state.

    Returns ``None`` when no validation repository is configured or no regular
    workflows exist.
    """
    validation_repo = _get_validation_repo_name(project, db)
    if not validation_repo:
        return None

    all_regular_workflows = (
        db.query(Workflow)
        .join(ProjectWorkflow)
        .filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.reusable_workflow.isnot(True),
        )
        .all()
    )
    workflow_dicts = [
        {"name": w.workflow_name, "content": w.workflow_yaml}
        for w in all_regular_workflows
        if w.workflow_name and w.workflow_yaml
    ]
    if not workflow_dicts:
        return None

    return _compute_preflight_content_hash(workflow_dicts, validation_repo)


def _mark_stale_if_content_changed(project: Project, db: Session) -> bool:
    """If the project's workflow content has changed since the last preflight run,
    downgrade status to ``stale`` and return ``True``.

    Only acts when the stored status is in ``_PREFLIGHT_PASSING_STATUSES`` and a
    stored content hash is present; safe to call on every status read.
    """
    if project.last_preflight_status not in _PREFLIGHT_PASSING_STATUSES:
        return False
    stored_hash = getattr(project, "last_preflight_content_hash", None)
    if not stored_hash:
        return False
    current_hash = _compute_current_project_preflight_hash(project, db)
    if current_hash is None or current_hash == stored_hash:
        return False
    _update_preflight_cached_fields(
        project,
        db,
        status="stale",
        error="Workflow changes were made after the last preflight approval. Re-run preflight to validate the current changes.",
    )
    return True


_PREFLIGHT_PASSING_STATUSES = {"passed"}

_VALIDATION_REPO_PERMISSION_ERROR = (
    "GitHub returned 403 Forbidden when accessing the validation repository. "
    "Ensure the authenticated token has read access to pull requests in the validation repository. "
    "For GitHub Apps, verify the installation grants 'Pull requests: read' permission on the validation repository. "
    "For personal access tokens, the 'repo' scope (classic) or 'Pull requests: read' permission (fine-grained) is required."
)


def _ensure_preflight_allows_campaign(project: Project, *, github_user: str, token: str, db: Session) -> None:
    if not project.validation_repo_id:
        return
    if not bool(getattr(project, "preflight_required", False)):
        return
    # Invalidate a stale approval before refreshing from GitHub.
    _mark_stale_if_content_changed(project, db)
    if project.last_preflight_status not in _PREFLIGHT_PASSING_STATUSES:
        # Avoid requiring a manual Refresh Status click: if a validation PR URL
        # exists, refresh once so merges/closes done in GitHub are recognized.
        _refresh_preflight_status_from_github(project=project, github_user=github_user, token=token, db=db)
    if project.last_preflight_status not in _PREFLIGHT_PASSING_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Preflight validation must pass before creating this PR Campaign.",
        )


def _build_custom_files_for_delivery(project: Project, payload: "CreatePullRequestsRequest", db: Session) -> List[dict]:
    """Return custom files to include in this PR Campaign.

    ``payload.selected_custom_file_ids = None``  → all changed/pending files.
    ``payload.selected_custom_file_ids = []``     → none (user deselected all).
    ``payload.selected_custom_file_ids = [1,2]``  → only those specific files.
    """
    if payload.selected_custom_file_ids == []:
        return []
    query = db.query(CustomFile).filter(
        CustomFile.project_id == project.project_id,
        (CustomFile.pending_delete.is_(True)) | (CustomFile.file_status != "synced_with_github"),
    )
    if payload.selected_custom_file_ids:
        query = query.filter(CustomFile.id.in_(payload.selected_custom_file_ids))
    files = query.all()
    return [
        {
            "id": f.id,
            "file_path": f.file_path,
            "file_content": f.file_content,
            "pending_delete": f.pending_delete,
        }
        for f in files
    ]


def _build_codeowners_for_delivery(project: Project, payload: "CreatePullRequestsRequest", repo_names: List[str], db: Session) -> dict:
    """Return CODEOWNERS content keyed by repo_name, for repos both selected for
    CODEOWNERS deployment and already in scope for this campaign (``repo_names``).

    Repos selected for CODEOWNERS but not in ``repo_names`` (e.g. deselected from
    Caller Repositories) are left for the standalone ``/codeowners/deploy``
    endpoint, which opens its own dedicated branch/PR for them.
    """
    if not payload.selected_codeowners_repos:
        return {}
    target_repos = set(payload.selected_codeowners_repos) & set(repo_names)
    if not target_repos:
        return {}
    rows = db.query(Codeowners, Repo).join(Repo, Codeowners.repo_id == Repo.repo_id).filter(
        Codeowners.project_id == project.project_id,
        Repo.repo_name.in_(target_repos),
    ).all()
    return {
        repo.repo_name: {
            "file_path": co.file_path or ".github/CODEOWNERS",
            "content": co.content,
            "repo_id": repo.repo_id,
            "project_id": project.project_id,
        }
        for co, repo in rows
        if co.content
    }


def _mark_codeowners_committed(db: Session, project_id: int, repo_id: int, new_sha: str) -> None:
    """Mark a repo's CODEOWNERS record as under_review after committing to an AM branch."""
    try:
        record = db.query(Codeowners).filter(
            Codeowners.project_id == project_id, Codeowners.repo_id == repo_id
        ).first()
        if record:
            record.git_hash = new_sha
            record.status = "under_review"
            db.commit()
    except Exception as e:
        print(f"❌ Error updating codeowners record after commit: {str(e)}")
        db.rollback()


def _build_regular_workflow_results(project: Project, payload: "CreatePullRequestsRequest", repo_names: List[str], headers: dict, db: Session, github_user: str = None, progress_callback=None, custom_files: Optional[List[dict]] = None, codeowners_files: Optional[dict] = None):
    """Process regular (non-reusable) workflows and return (results, selected_names).

    Regular workflows are included when the caller explicitly listed
    selected_workflows, or when neither workflow type was requested (backward-
    compatible default).  They are skipped when only reusable workflows were
    requested (selected_reusable_workflows is set but selected_workflows is None).

    ``custom_files`` are committed to the same AM branch as workflows so they
    land in the same PR Campaign PR.
    """
    include_regular = (
        payload.selected_workflows is not None
        or payload.selected_reusable_workflows is None
    )
    custom_files = custom_files or []
    workflow_dicts = []
    selected_names = []
    if include_regular:
        all_regular_workflows = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.reusable_workflow.isnot(True)
        ).all()
        regular_workflows = all_regular_workflows
        if payload.selected_workflows is not None:
            regular_workflows = [w for w in regular_workflows if w.workflow_name in payload.selected_workflows]
        workflow_dicts = [
            {"name": w.workflow_name, "content": w.workflow_yaml}
            for w in regular_workflows if w.workflow_name and w.workflow_yaml
        ]
        selected_names = [w.workflow_name for w in regular_workflows if w.workflow_name]

    if not workflow_dicts and not custom_files and not codeowners_files:
        return {}, []

    user = github_user or (payload.github_user or "")
    results = _process_regular_workflows_update(
        repo_names=repo_names,
        workflows=workflow_dicts,
        project_code=project.project_code,
        branch_option=project.branch_option or "default",
        regex_pattern=project.branch_regex or "",
        branch_max_age_days=project.branch_max_age_days or 30,
        headers=headers,
        db=db,
        user=user,
        use_prefix=project.use_prefix,
        project=project,
        codeowners_files=codeowners_files,
        progress_callback=progress_callback,
        custom_files=custom_files,
    )
    return results, selected_names


def _validate_linked_workflow_selections(project: Project, selected_linked_rows: list, db: Session):
    """Validate that all selected linked reusable workflows are compatible."""
    for _workflow, rwx_project in selected_linked_rows:
        validation = validate_reusable_workflow_link(project, rwx_project, db)
        if not validation.allowed:
            raise HTTPException(
                status_code=400,
                detail=validation.reason or "Unable to validate reusable workflow compatibility. Please contact support.",
            )


def _check_reusable_workflow_locks(db: Session, reusable_workflows: list, project_id):
    """Block PR creation if any reusable workflow is already under review elsewhere."""
    for workflow in reusable_workflows:
        blocking = _find_blocking_reusable_workflow_pr(db, workflow, project_id)
        if blocking is not None:
            blocking_pr, owning_project = blocking
            owner_label = owning_project.project_name if owning_project else "another project"
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Reusable workflow '{workflow.workflow_name}' is already under review "
                    f"by an open PR campaign in project '{owner_label}' (PR #{blocking_pr.pr_number}). "
                    "It is locked until that PR is merged or closed."
                ),
            )


def _log_reusable_workflow_selection(project_name: str, reusable_workflows: list, linked_only: list):
    """Log which linked reusable workflows are included vs skipped."""
    linked_ids_set = {w.workflow_id for w in linked_only}
    included_linked = [
        w.workflow_name for w in reusable_workflows if w.workflow_id in linked_ids_set
    ]
    if included_linked:
        print(
            f"📌 Including {len(included_linked)} linked reusable workflow(s) in PR "
            f"creation for project '{project_name}': {included_linked}"
        )
    skipped_linked = [
        w.workflow_name for w in linked_only if w not in reusable_workflows
    ]
    if skipped_linked:
        print(
            f"ℹ️ Skipping {len(skipped_linked)} linked reusable workflow(s) not "
            f"selected for project '{project_name}': {skipped_linked}"
        )


def _build_reusable_workflow_results(project: Project, payload: "CreatePullRequestsRequest", headers: dict, db: Session, github_user: str = None, progress_callback=None):
    """Process reusable workflows and return (results, selected_names).

    Only runs when the caller explicitly provided selected_reusable_workflows.
    Merges workflows owned directly by the project (RWX) with those linked from
    RWX projects (standard projects), deduplicating by workflow_id.

    Selection matching uses ``_normalize_reusable_workflow_name`` so that
    display-formatted names sent by the frontend for *linked* reusable
    workflows (e.g. ``AM_RWW1_deploy.yml`` produced by
    ``_load_linked_reusable_workflows``) correctly resolve to the canonical
    raw stem stored in ``Workflow.workflow_name`` (e.g. ``deploy``).
    Without this normalisation, linked reusable workflows are silently
    dropped from PR creation and no PR is opened against the producer repo.
    """
    if payload.selected_reusable_workflows is None:
        return {}, []
    # Workflows owned directly by this project (RWX projects)
    owned = db.query(Workflow).join(ProjectWorkflow).filter(
        ProjectWorkflow.project_id == project.project_id,
        Workflow.reusable_workflow == True
    ).all()
    # Workflows linked from RWX projects (standard projects)
    linked_rows = db.query(Workflow, LinkedReusableWorkflow, Project).join(
        LinkedReusableWorkflow, LinkedReusableWorkflow.workflow_id == Workflow.workflow_id
    ).join(
        Project, Project.project_id == LinkedReusableWorkflow.rwx_project_id
    ).filter(
        LinkedReusableWorkflow.standard_project_id == project.project_id
    ).all()
    linked_rx = [workflow for workflow, _link, _rwx_project in linked_rows]
    seen_ids = {w.workflow_id for w in owned}
    linked_only = [w for w in linked_rx if w.workflow_id not in seen_ids]
    all_reusable = list(owned) + linked_only
    # Normalise both sides so display names (with prefix + .yml extension) match
    # the canonical raw stem stored in ``Workflow.workflow_name``.
    selected_norm = {
        _normalize_reusable_workflow_name(n) for n in payload.selected_reusable_workflows
    }
    reusable_workflows = [
        w for w in all_reusable
        if _normalize_reusable_workflow_name(w.workflow_name) in selected_norm
    ]
    reusable_workflow_ids = {workflow.workflow_id for workflow in reusable_workflows}
    selected_linked_rows = [
        (workflow, rwx_project)
        for workflow, _link, rwx_project in linked_rows
        if workflow.workflow_id in reusable_workflow_ids
    ]
    _validate_linked_workflow_selections(project, selected_linked_rows, db)
    _check_reusable_workflow_locks(db, reusable_workflows, project.project_id)
    _log_reusable_workflow_selection(project.project_name, reusable_workflows, linked_only)
    if not reusable_workflows:
        return {}, []
    rxworkflow_dicts = [
        {"name": w.workflow_name, "content": w.workflow_yaml}
        for w in reusable_workflows if w.workflow_name and w.workflow_yaml
    ]
    selected_names = [w.workflow_name for w in reusable_workflows if w.workflow_name]
    user = github_user or (payload.github_user or "")

    # For linked reusable workflows in a standard (caller) project, prefix
    # behaviour must come from the owning RWX project, not the caller project.
    effective_code = project.project_code
    effective_prefix = project.use_prefix
    if project.project_type == "standard" and selected_linked_rows:
        # All linked workflows in this batch go to the same RWX project's repo
        # (see _get_reusable_workflow_repo logic).  Use that RWX project's settings.
        _first_linked_rwx = selected_linked_rows[0][1]
        effective_code = _first_linked_rwx.project_code
        effective_prefix = _first_linked_rwx.use_prefix

    results = _process_reusable_workflows_update(
        rxworkflows=rxworkflow_dicts,
        user=user,
        project_code=effective_code,
        regex_pattern=project.branch_regex or "",
        branch_max_age_days=project.branch_max_age_days or 30,
        headers=headers,
        db=db,
        reusable_repo=_get_reusable_workflow_repo(project, user, db),
        use_prefix=effective_prefix,
        progress_callback=progress_callback
    )
    return results, selected_names


def _parse_repo_branch(repo_branch: str):
    """Extract repo_name and target_branch from a 'repo on branch' key."""
    if " on " in repo_branch:
        parts = repo_branch.split(" on ")
        return parts[0], parts[1]
    return repo_branch, "main"


def _codeowners_merged_repos(results: dict) -> List[str]:
    """Repo names whose CODEOWNERS content was committed onto an existing
    workflow/custom-file PR branch in this run — the caller should skip
    deploying a standalone CODEOWNERS PR for these."""
    return [
        _parse_repo_branch(repo_branch)[0]
        for repo_branch, result in results.items()
        if isinstance(result, dict)
        and result.get("status") in ("pr_created", "pr_updated")
        and result.get("codeowners_committed")
    ]


def _persist_single_pr(result: dict, repo_branch: str, project: Project, campaign, db: Session):
    """Save a single PR record to the database. Returns (attached, repo_name)."""
    repo_name, target_branch = _parse_repo_branch(repo_branch)
    am_branch = result.get("branch_name") or (
        f"actions-manager/{project.project_code.lower()}"
        f"-{target_branch.replace('/', '-').replace('\\', '-')}"
    )
    per_pr_workflows = result.get("workflows_committed") or []
    workflow_names_str = ", ".join(per_pr_workflows) if per_pr_workflows else None
    per_pr_files: List[str] = list(result.get("custom_files_committed") or [])
    codeowners_path = result.get("codeowners_committed") or ""
    if codeowners_path:
        per_pr_files.append(codeowners_path)
    file_names_str = ", ".join(per_pr_files) if per_pr_files else None
    is_new_pr = result.get("status") == "pr_created"
    try:
        attached = _save_pr_to_database(
            db=db,
            project_id=project.project_id,
            repo_name=repo_name,
            pr_number=result.get("pr_number"),
            pr_url=result.get("pr_url"),
            branch_name=am_branch,
            target_branch=target_branch,
            title=result.get("pr_title"),
            author=result.get("pr_author"),
            body=result.get("pr_body"),
            workflow_names=workflow_names_str,
            file_names=file_names_str,
            campaign_id=campaign.campaign_id if campaign else None,
            is_new_pr=is_new_pr,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Pull request #{result.get('pr_number')} for {repo_name} was created on GitHub "
                f"but could not be recorded in the ActionsManager database: {exc}. "
                "The database schema may be out of date — restart the container or run "
                "'python run_migrations.py' from the backend directory, then refresh PR status."
            ),
        ) from exc
    if is_new_pr and not attached:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Pull request #{result.get('pr_number')} for {repo_name} was saved without a "
                "campaign id. The database schema may be missing the PR campaigns migration — "
                "restart the container or run 'python run_migrations.py' from the backend directory."
            ),
        )
    return attached


def _update_linked_workflow_statuses(db: Session, project_id: int, all_selected: List[str]):
    """Mark linked reusable workflows as under_review after PR creation."""
    _update_project_workflows_status(db, project_id, "under_review", workflow_names=all_selected)
    linked_wf_ids = _get_linked_workflow_ids_for_project(db, project_id, workflow_names=all_selected)
    if linked_wf_ids:
        db.query(Workflow).filter(
            Workflow.workflow_id.in_(linked_wf_ids)
        ).update({"workflow_status": "under_review"}, synchronize_session=False)
        db.commit()
        print(f"✅ Set {len(linked_wf_ids)} linked reusable workflow(s) to under_review")


def _save_prs_and_update_status(results: dict, project: Project, selected_workflow_names: List[str], selected_reusable_workflow_names: List[str], db: Session, github_user: Optional[str] = None, custom_file_ids: Optional[List[int]] = None):
    """Persist PR records to the database and update project/workflow statuses.

    Every run that produces PR records creates a NEW unique campaign record so
    newly-created PRs are never appended to a previous campaign. PR rows whose
    existing open PR merely received new commits stay in their original campaign.

    Returns (pr_count, campaign_id) — campaign_id is None when no campaign was created.
    """
    all_selected = selected_workflow_names + selected_reusable_workflow_names

    actionable_results = {
        repo_branch: result
        for repo_branch, result in results.items()
        if isinstance(result, dict) and result.get("status") in ["pr_created", "pr_updated"]
    }

    campaign = None
    campaign_id = None
    campaign_pr_count = 0
    if actionable_results:
        campaign = ProjectPRCampaign(
            project_id=project.project_id,
            created_by=github_user,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        campaign_id = campaign.campaign_id

    pr_count = 0
    for repo_branch, result in actionable_results.items():
        attached = _persist_single_pr(result, repo_branch, project, campaign, db)
        if attached:
            campaign_pr_count += 1
        pr_count += 1

    if campaign and campaign_pr_count == 0:
        db.delete(campaign)
        db.commit()
        campaign_id = None

    if pr_count == 0:
        return 0, None
    if campaign_id:
        try:
            record_campaign_opened(db, project, campaign, results)
        except Exception as exc:
            print(f"⚠️ Error recording campaign.opened notification: {exc}")
            db.rollback()
    _update_project_pr_state(db, project.project_id, "open")
    if all_selected:
        _update_linked_workflow_statuses(db, project.project_id, all_selected)
    if custom_file_ids:
        try:
            db.query(CustomFile).filter(
                CustomFile.id.in_(custom_file_ids),
                CustomFile.file_status != "synced_with_github",
            ).update({"file_status": "under_review"}, synchronize_session=False)
            db.commit()
            print(f"✅ Set {len(custom_file_ids)} custom file(s) to under_review")
        except Exception as e:
            print(f"❌ Error setting custom files to under_review: {str(e)}")
            db.rollback()
    return pr_count, campaign_id


pr_campaign_tasks = {}

def _run_create_pull_requests_async(task_id: str, payload: CreatePullRequestsRequest, github_user: str):
    pr_campaign_tasks[task_id]["status"] = "running"
    
    def progress_callback(repo_name: str, step: str, status: str, error: Optional[str] = None):
        if repo_name not in pr_campaign_tasks[task_id]["repos"]:
            pr_campaign_tasks[task_id]["repos"][repo_name] = {"step": step, "status": status, "error": error}
        else:
            pr_campaign_tasks[task_id]["repos"][repo_name].update({"step": step, "status": status, "error": error})

    try:
        with SessionLocal() as db:
            token, project = _get_project_and_token(payload, db, github_user=github_user)
            _ensure_preflight_allows_campaign(project, github_user=github_user, token=token, db=db)
            repo_names = _get_filtered_repo_names(project, payload.selected_repos, db)
            headers = {
                "Accept": ACCEPT_HEADER,
                "X-GitHub-Api-Version": X_API_VERSION,
                "Authorization": f"token {token}"
            }
            custom_files_for_delivery = _build_custom_files_for_delivery(project, payload, db)
            codeowners_for_delivery = _build_codeowners_for_delivery(project, payload, repo_names, db)
            regular_results, selected_workflow_names = _build_regular_workflow_results(
                project, payload, repo_names, headers, db, github_user=github_user,
                progress_callback=progress_callback, custom_files=custom_files_for_delivery,
                codeowners_files=codeowners_for_delivery,
            )
            reusable_results, selected_reusable_workflow_names = _build_reusable_workflow_results(
                project, payload, headers, db, github_user=github_user, progress_callback=progress_callback
            )
            results = {**regular_results, **reusable_results}
            has_codeowners = bool(payload.selected_codeowners_repos)
            if not results and not has_codeowners:
                pr_campaign_tasks[task_id]["status"] = "error"
                pr_campaign_tasks[task_id]["error"] = "No workflows, custom files, or CODEOWNERS repos were selected"
                return

            custom_file_ids = [cf["id"] for cf in custom_files_for_delivery]
            pr_count, campaign_id = _save_prs_and_update_status(
                results, project, selected_workflow_names, selected_reusable_workflow_names, db,
                github_user=github_user, custom_file_ids=custom_file_ids,
            )

            if has_codeowners and campaign_id is None:
                # CODEOWNERS-only (or all workflow PRs were no-ops): create a campaign
                # so CODEOWNERS PRs have somewhere to attach.
                campaign = ProjectPRCampaign(project_id=project.project_id, created_by=github_user)
                db.add(campaign)
                db.commit()
                db.refresh(campaign)
                campaign_id = campaign.campaign_id
                _update_project_pr_state(db, project.project_id, "open")

            pr_campaign_tasks[task_id]["status"] = "completed"
            pr_campaign_tasks[task_id]["results"] = results
            pr_campaign_tasks[task_id]["prs_created"] = pr_count
            pr_campaign_tasks[task_id]["campaign_id"] = campaign_id
            pr_campaign_tasks[task_id]["codeowners_merged_repos"] = _codeowners_merged_repos(results)
    except Exception as e:
        print(f"❌ Error in async PR creation: {str(e)}")
        import traceback
        traceback.print_exc()
        pr_campaign_tasks[task_id]["status"] = "error"
        pr_campaign_tasks[task_id]["error"] = str(e)


@router.post("/api/create-pull-requests", responses=_responses(400, 401, 404, 409, 500))
def create_pull_requests(
    payload: CreatePullRequestsRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
    github_user: Optional[str] = None,
):
    """
    Create pull requests for workflows in specified repositories.
    This endpoint transitions the project from 'draft' to 'open' state.
    Supports both regular workflows (per-repo PRs) and reusable workflows
    (PR against the dedicated am-reuseable-workflow repository).
    """
    # Allow internal callers to pass github_user directly; otherwise resolve from header/body
    if github_user is None:
        github_user = _resolve_github_user(x_github_user, payload.github_user)

    if payload.async_mode:
        task_id = str(uuid.uuid4())
        pr_campaign_tasks[task_id] = {
            "status": "queued",
            "repos": {},
            "results": {},
            "prs_created": 0
        }
        background_tasks.add_task(_run_create_pull_requests_async, task_id, payload, github_user)
        return {"task_id": task_id, "status": "running"}

    try:
        token, project = _get_project_and_token(payload, db, github_user=github_user)
        _ensure_preflight_allows_campaign(project, github_user=github_user, token=token, db=db)
        repo_names = _get_filtered_repo_names(project, payload.selected_repos, db)
        headers = {
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION,
            "Authorization": f"token {token}"
        }
        custom_files_for_delivery = _build_custom_files_for_delivery(project, payload, db)
        codeowners_for_delivery = _build_codeowners_for_delivery(project, payload, repo_names, db)
        regular_results, selected_workflow_names = _build_regular_workflow_results(
            project, payload, repo_names, headers, db, github_user=github_user,
            custom_files=custom_files_for_delivery, codeowners_files=codeowners_for_delivery,
        )
        reusable_results, selected_reusable_workflow_names = _build_reusable_workflow_results(
            project, payload, headers, db, github_user=github_user
        )
        results = {**regular_results, **reusable_results}
        has_codeowners = bool(payload.selected_codeowners_repos)
        if not results and not has_codeowners:
            raise HTTPException(status_code=400, detail="No workflows, custom files, or CODEOWNERS repos were selected")
        custom_file_ids = [cf["id"] for cf in custom_files_for_delivery]
        pr_count, campaign_id = _save_prs_and_update_status(
            results, project, selected_workflow_names, selected_reusable_workflow_names, db,
            github_user=github_user, custom_file_ids=custom_file_ids,
        )
        if has_codeowners and campaign_id is None:
            campaign = ProjectPRCampaign(project_id=project.project_id, created_by=github_user)
            db.add(campaign)
            db.commit()
            db.refresh(campaign)
            campaign_id = campaign.campaign_id
            _update_project_pr_state(db, project.project_id, "open")
        return {
            "message": "Pull requests created successfully",
            "results": results,
            "prs_created": pr_count,
            "campaign_id": campaign_id,
            "codeowners_merged_repos": _codeowners_merged_repos(results),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating pull requests: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/create-pull-requests/{task_id}", responses=_responses(404))
def get_create_pull_requests_status(task_id: str):
    if task_id not in pr_campaign_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return pr_campaign_tasks[task_id]

@router.post("/api/run-preflight-validation", responses=_responses(400, 401, 403, 404, 500))
def run_preflight_validation(
    payload: RunPreflightRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Run project preflight in the configured validation repository."""
    github_user = _resolve_github_user(x_github_user, payload.github_user)
    try:
        token, project = _get_project_and_token(payload, db, github_user=github_user)
        validation_repo = _get_validation_repo_name(project, db)
        if not validation_repo:
            raise HTTPException(status_code=400, detail="Preflight validation is not configured.")

        headers = {
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION,
            "Authorization": f"token {token}"
        }
        _check_validation_repo_access(project, validation_repo, github_user, db, headers)

        project.last_preflight_status = "running"
        project.last_preflight_error = None
        project.last_preflight_pr_url = None
        db.commit()

        workflow_dicts, all_workflow_dicts = _collect_preflight_workflows(project, payload, db)

        content_hash = _compute_preflight_content_hash(all_workflow_dicts, validation_repo)

        results = _process_regular_workflows_update(
            repo_names=[validation_repo],
            workflows=workflow_dicts,
            project_code=project.project_code,
            branch_option=project.branch_option or "default",
            regex_pattern=project.branch_regex or "",
            branch_max_age_days=project.branch_max_age_days or 30,
            headers=headers,
            db=db,
            user=github_user,
            use_prefix=project.use_prefix,
            project=project,
        )
        failed, pr_url = _extract_preflight_results(results, validation_repo)
        if failed:
            message = _sanitize_preflight_error("; ".join(str(item) for item in failed if item))
            _set_preflight_result(project, "failed", db, message, pr_url)
            raise HTTPException(status_code=400, detail=message)

        # Preflight approval is based on the validation PR lifecycle:
        # - Open PR => waiting for user review
        # - Merged PR => approved/passed
        # - Closed PR (not merged) => rejected/not approved
        _set_preflight_result(project, "validation_pr_open", db, None, pr_url)
        # Record the content fingerprint so future status checks can detect staleness.
        project.last_preflight_content_hash = content_hash
        db.commit()
        return {
            "status": "validation_pr_open",
            "validation_repo": validation_repo,
            "last_preflight_run_at": project.last_preflight_run_at.isoformat() if project.last_preflight_run_at else None,
            "last_preflight_pr_url": project.last_preflight_pr_url,
        }
    except HTTPException:
        raise
    except Exception as e:
        try:
            project = _find_project_by_name(db, github_user, payload.project_name)
            if project:
                _set_preflight_result(project, "failed", db, str(e))
        except Exception:
            db.rollback()
        print(f"❌ Error running preflight validation: {str(e)}")
        raise HTTPException(status_code=500, detail="Preflight validation failed.")


def _check_validation_repo_access(project, validation_repo: str, github_user: str, db, headers: dict):
    """Check that the validation repository is accessible, raising HTTPException on failure."""
    owner, repo = validation_repo.split("/", 1)
    repo_response = github_get(
        f"{GITHUB_API_URL}/repos/{owner}/{repo}",
        github_user,
        db,
        headers=headers,
    )
    if repo_response.status_code == 404:
        _set_preflight_result(
            project,
            "validation_repo_inaccessible",
            db,
            "Validation repository is inaccessible, deleted, or unauthorized.",
        )
        raise HTTPException(status_code=400, detail="Validation repository is inaccessible, deleted, or unauthorized.")
    if repo_response.status_code == 403:
        _set_preflight_result(
            project,
            "failed",
            db,
            _VALIDATION_REPO_PERMISSION_ERROR,
        )
        raise HTTPException(status_code=403, detail=_VALIDATION_REPO_PERMISSION_ERROR)
    if repo_response.status_code >= 400:
        _set_preflight_result(project, "failed", db, "Unable to access validation repository.")
        raise HTTPException(status_code=400, detail="Unable to access validation repository.")


def _collect_preflight_workflows(project, payload, db):
    """Collect and filter workflows for preflight validation. Returns (selected_dicts, all_dicts)."""
    all_regular_workflows = db.query(Workflow).join(ProjectWorkflow).filter(
        ProjectWorkflow.project_id == project.project_id,
        Workflow.reusable_workflow.isnot(True)
    ).all()
    selected_names = set(payload.selected_workflows or [])
    regular_workflows = [
        workflow for workflow in all_regular_workflows
        if not selected_names or workflow.workflow_name in selected_names
    ]
    workflow_dicts = [
        {"name": w.workflow_name, "content": w.workflow_yaml}
        for w in regular_workflows if w.workflow_name and w.workflow_yaml
    ]
    if not workflow_dicts:
        _set_preflight_result(project, "failed", db, "No regular workflows selected for preflight validation.")
        raise HTTPException(status_code=400, detail="No regular workflows selected for preflight validation.")

    all_workflow_dicts = [
        {"name": w.workflow_name, "content": w.workflow_yaml}
        for w in all_regular_workflows if w.workflow_name and w.workflow_yaml
    ]
    return workflow_dicts, all_workflow_dicts


def _parse_github_pr_url(pr_url: str) -> Optional[tuple[str, str, int]]:
    """Parse a GitHub PR URL into (owner, repo, pr_number)."""
    value = (pr_url or "").strip()
    if not value:
        return None

    web_match = re.match(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", value)
    if web_match:
        owner, repo, pr_number = web_match.group(1), web_match.group(2), web_match.group(3)
        try:
            return owner, repo, int(pr_number)
        except ValueError:
            return None

    api_match = re.match(r"^https?://api\.github\.com/repos/([^/]+)/([^/]+)/pulls/(\d+)", value)
    if api_match:
        owner, repo, pr_number = api_match.group(1), api_match.group(2), api_match.group(3)
        try:
            return owner, repo, int(pr_number)
        except ValueError:
            return None

    return None


def _update_preflight_cached_fields(
    project: Project,
    db: Session,
    *,
    status: Optional[str] = None,
    error: Optional[str] = None,
    pr_url: Optional[str] = None,
    update_run_at: bool = False,
) -> None:
    """Update preflight fields, optionally refreshing last_preflight_run_at."""
    if status is not None:
        project.last_preflight_status = status
    if update_run_at:
        project.last_preflight_run_at = datetime.now(timezone.utc)
    if error is not None:
        project.last_preflight_error = (error[:500] if error else None)
    if pr_url is not None:
        project.last_preflight_pr_url = pr_url
    db.commit()


def _github_error_message(response, fallback: str) -> str:
    """Return a concise, actionable GitHub API error message."""
    error_data = _safe_json(response)
    if not isinstance(error_data, dict):
        return fallback

    message = error_data.get("message")
    details = _github_error_detail_strings(error_data.get("errors"))
    if details:
        return f"{message or fallback}: {'; '.join(details)}"
    return message or fallback


def _safe_json(response) -> object:
    """Decode a response body as JSON, returning ``{}`` on any failure."""
    try:
        return response.json() if getattr(response, "text", "") else {}
    except Exception:
        return {}


def _github_error_detail_strings(errors) -> list:
    """Extract up to three human-readable strings from a GitHub ``errors`` list."""
    if not isinstance(errors, list) or not errors:
        return []
    details = []
    for item in errors[:3]:
        if isinstance(item, dict):
            details.append(str(item.get("message") or item.get("code") or item))
        else:
            details.append(str(item))
    return details


def _is_pull_request_merged(pr_data: dict) -> bool:
    """Return True when PR appears merged based on GitHub REST payload fields."""
    if pr_data.get("merged") is True:
        return True
    merged_at = pr_data.get("merged_at")
    return bool(merged_at)


def _derive_pr_action_capabilities(pr_data: dict) -> dict:
    """Summarize whether ActionsManager can offer PR lifecycle actions."""
    pr_state = "merged" if _is_pull_request_merged(pr_data) else pr_data.get("state", "open")
    draft = bool(pr_data.get("draft", False))
    has_mergeability = "mergeable" in pr_data or "mergeable_state" in pr_data
    mergeable = pr_data.get("mergeable")
    mergeable_state = pr_data.get("mergeable_state")

    can_close = pr_state == "open"
    close_block_reason = None if can_close else "Pull request is not open."

    can_merge = False
    merge_block_reason = None
    if pr_state != "open":
        merge_block_reason = "Pull request is not open."
    elif draft:
        merge_block_reason = "Pull request is a draft."
    elif not has_mergeability:
        can_merge = None
    elif mergeable is None or mergeable_state in {None, "unknown"}:
        merge_block_reason = "GitHub is still computing mergeability; refresh status before merging."
    elif mergeable is False or mergeable_state == "dirty":
        merge_block_reason = "Pull request has merge conflicts."
    elif mergeable_state in {"blocked", "behind", "unstable"}:
        merge_block_reason = "Required checks, reviews, branch protection, or base branch updates are blocking merge."
    else:
        can_merge = True

    return {
        "mergeable": mergeable,
        "mergeable_state": mergeable_state,
        "draft": draft,
        "can_merge": can_merge,
        "merge_block_reason": merge_block_reason,
        "can_close": can_close,
        "close_block_reason": close_block_reason,
    }


def _derive_preflight_status_from_github(
    *,
    pr_data: dict,
) -> tuple[str, Optional[str], Optional[str]]:
    """Return (status, error_summary, pr_state) based on validation PR lifecycle state.

    Preflight pass/fail is determined by PR lifecycle state — not by GitHub
    Actions check or workflow run results on the PR head SHA:

    - Merged PR  => ``passed`` (approved)
    - Closed PR (without merge) => ``closed`` (rejected/not approved)
    - Open PR    => ``validation_pr_open`` (waiting for user review/action)
    """
    pr_state = "merged" if _is_pull_request_merged(pr_data) else pr_data.get("state", "open")
    if pr_state == "merged":
        return "passed", None, pr_state
    if pr_state == "closed":
        # Closed without merge => rejected/not approved.
        return "closed", None, pr_state
    if pr_state == "open":
        return "validation_pr_open", None, pr_state

    return "stale", f"Unexpected validation PR state: {pr_state}", pr_state


def _refresh_preflight_status_from_github(
    *,
    project: Project,
    github_user: str,
    token: str,
    db: Session,
) -> tuple[str, Optional[str], Optional[str]]:
    """Best-effort refresh of preflight status from the stored validation PR URL.

    Returns (status, error_summary, pr_state). If the PR URL is missing or the
    GitHub API is unavailable, returns the current cached status.
    """
    current_status = project.last_preflight_status or "not_run"
    pr_url = project.last_preflight_pr_url
    if not pr_url:
        # Normalize legacy check-based states into the PR-state model.
        if current_status == "waiting_for_checks":
            return "validation_pr_open", project.last_preflight_error, None
        return current_status, project.last_preflight_error, None

    parsed = _parse_github_pr_url(pr_url)
    if not parsed:
        _update_preflight_cached_fields(project, db, status="stale", error=_ERR_STALE_VALIDATION_URL)
        return project.last_preflight_status, project.last_preflight_error, None

    owner, repo, pr_number = parsed
    headers = {
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
        "Authorization": f"token {token}",
    }
    pr_api_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
    pr_response = github_get(pr_api_url, github_user, db, headers=headers)
    if pr_response.status_code == 404:
        _update_preflight_cached_fields(project, db, status="stale", error=_ERR_VALIDATION_PR_MISSING)
        return project.last_preflight_status, project.last_preflight_error, None
    if pr_response.status_code == 403:
        _update_preflight_cached_fields(project, db, status="validation_repo_inaccessible", error=_VALIDATION_REPO_PERMISSION_ERROR)
        return project.last_preflight_status, project.last_preflight_error, None
    if pr_response.status_code != 200:
        # Do not clobber the cached status for transient API failures.
        if current_status == "waiting_for_checks":
            return "validation_pr_open", project.last_preflight_error, None
        return current_status, project.last_preflight_error, None

    pr_data = pr_response.json() or {}
    derived_status, derived_error, pr_state = _derive_preflight_status_from_github(
        pr_data=pr_data,
    )
    _update_preflight_cached_fields(project, db, status=derived_status, error=derived_error)
    return project.last_preflight_status or derived_status, project.last_preflight_error, pr_state


@router.get("/api/preflight-validation-status", responses=_responses(401, 404, 500))
def get_preflight_validation_status(
    github_user: str,
    project_name: str,
    db: Annotated[Session, Depends(get_db)],
    refresh_from_github: bool = True,
):
    """Return (and optionally refresh) the project's preflight validation status."""
    try:
        if github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
        token = user_tokens[github_user]

        project = _find_project_by_name(db, github_user, project_name)
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)

        validation_repo = _get_validation_repo_name(project, db)
        if not validation_repo:
            return {
                "status": "not_configured",
                "validation_repo": None,
                "last_preflight_run_at": None,
                "last_preflight_error": None,
                "last_preflight_pr_url": None,
                "pr_state": None,
            }

        current_status = project.last_preflight_status or "not_run"
        if current_status == "waiting_for_checks":
            # Legacy: older versions used checks-based statuses.
            current_status = "validation_pr_open"
        pr_url = project.last_preflight_pr_url

        # Check whether workflow content has changed since the last approval and
        # downgrade to stale so the UI reflects that re-run is needed.
        _mark_stale_if_content_changed(project, db)
        current_status = project.last_preflight_status or current_status

        if not refresh_from_github or not pr_url:
            return {
                "status": current_status,
                "validation_repo": validation_repo,
                "last_preflight_run_at": project.last_preflight_run_at.isoformat() if project.last_preflight_run_at else None,
                "last_preflight_error": project.last_preflight_error,
                "last_preflight_pr_url": pr_url,
                "pr_state": None,
            }

        parsed = _parse_github_pr_url(pr_url)
        if not parsed:
            _update_preflight_cached_fields(project, db, status="stale", error=_ERR_STALE_VALIDATION_URL)
            return {
                "status": project.last_preflight_status,
                "validation_repo": validation_repo,
                "last_preflight_run_at": project.last_preflight_run_at.isoformat() if project.last_preflight_run_at else None,
                "last_preflight_error": project.last_preflight_error,
                "last_preflight_pr_url": project.last_preflight_pr_url,
                "pr_state": None,
            }

        owner, repo, pr_number = parsed
        headers = {
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION,
            "Authorization": f"token {token}",
        }
        pr_api_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        pr_response = github_get(pr_api_url, github_user, db, headers=headers)
        if pr_response.status_code == 404:
            _update_preflight_cached_fields(project, db, status="stale", error=_ERR_VALIDATION_PR_MISSING)
            return {
                "status": project.last_preflight_status,
                "validation_repo": validation_repo,
                "last_preflight_run_at": project.last_preflight_run_at.isoformat() if project.last_preflight_run_at else None,
                "last_preflight_error": project.last_preflight_error,
                "last_preflight_pr_url": project.last_preflight_pr_url,
                "pr_state": None,
            }
        if pr_response.status_code == 403:
            _update_preflight_cached_fields(project, db, status="validation_repo_inaccessible", error=_VALIDATION_REPO_PERMISSION_ERROR)
            return {
                "status": project.last_preflight_status,
                "validation_repo": validation_repo,
                "last_preflight_run_at": project.last_preflight_run_at.isoformat() if project.last_preflight_run_at else None,
                "last_preflight_error": project.last_preflight_error,
                "last_preflight_pr_url": project.last_preflight_pr_url,
                "pr_state": None,
            }
        if pr_response.status_code != 200:
            # Don't clobber the cached status for transient API failures.
            return {
                "status": current_status,
                "validation_repo": validation_repo,
                "last_preflight_run_at": project.last_preflight_run_at.isoformat() if project.last_preflight_run_at else None,
                "last_preflight_error": project.last_preflight_error,
                "last_preflight_pr_url": project.last_preflight_pr_url,
                "pr_state": None,
            }

        pr_data = pr_response.json() or {}
        action_capabilities = _derive_pr_action_capabilities(pr_data)
        derived_status, derived_error, pr_state = _derive_preflight_status_from_github(
            pr_data=pr_data,
        )
        _update_preflight_cached_fields(project, db, status=derived_status, error=derived_error)
        # If the PR was just detected as merged (passed), immediately check whether
        # content has changed since the approval was recorded.
        _mark_stale_if_content_changed(project, db)
        return {
            "status": project.last_preflight_status or derived_status,
            "validation_repo": validation_repo,
            "last_preflight_run_at": project.last_preflight_run_at.isoformat() if project.last_preflight_run_at else None,
            "last_preflight_error": project.last_preflight_error,
            "last_preflight_pr_url": project.last_preflight_pr_url,
            "pr_state": pr_state,
            **action_capabilities,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error refreshing preflight status: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to refresh preflight status.")


def _fetch_validation_pr_or_raise(project, db, pr_api_url, github_user, headers):
    """Fetch a project's validation PR, updating cached state and raising on errors."""
    pr_response = github_get(pr_api_url, github_user, db, headers=headers)
    if pr_response.status_code == 404:
        _update_preflight_cached_fields(project, db, status="stale", error=_ERR_VALIDATION_PR_MISSING)
        raise HTTPException(status_code=404, detail="Validation PR not found.")
    if pr_response.status_code == 403:
        _update_preflight_cached_fields(project, db, status="validation_repo_inaccessible", error=_VALIDATION_REPO_PERMISSION_ERROR)
        raise HTTPException(status_code=403, detail=_VALIDATION_REPO_PERMISSION_ERROR)
    if pr_response.status_code != 200:
        raise HTTPException(status_code=400, detail="Unable to fetch validation PR from GitHub.")
    return pr_response.json() or {}


def _close_validation_pr_or_raise(pr_api_url, github_user, db, headers):
    """Close an open validation PR via the GitHub API, raising on failure."""
    close_response = github_patch(pr_api_url, github_user, db, json={"state": "closed"}, headers=headers)
    if close_response.status_code != 200:
        raise HTTPException(
            status_code=close_response.status_code,
            detail=_github_error_message(
                close_response,
                f"Failed to close validation PR: {close_response.status_code}",
            ),
        )


def _cleanup_validation_pr_branch(pr_data, owner, repo, github_user):
    """Delete the validation PR source branch when head/base refs are available."""
    head_ref = (pr_data.get("head") or {}).get("ref")
    base_ref = (pr_data.get("base") or {}).get("ref")
    if head_ref and base_ref:
        return _delete_actions_manager_branch(
            owner=owner,
            repo=repo,
            branch_name=head_ref,
            target_branch=base_ref,
            github_user=github_user,
        )
    return False, BRANCH_INFO_NOT_FOUND


def _validate_merge_preflight_request(
    github_user: str,
    project,
    db: Session,
) -> tuple:
    """Validate auth/project/PR URL and return (owner, repo, pr_number, headers, token).

    Raises HTTPException on validation failure.
    """
    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
    token = user_tokens[github_user]

    if not project:
        raise HTTPException(status_code=404, detail=PROJECT_ERROR)

    pr_url = project.last_preflight_pr_url
    if not pr_url:
        raise HTTPException(status_code=400, detail="No validation PR is recorded for this project.")

    parsed = _parse_github_pr_url(pr_url)
    if not parsed:
        _update_preflight_cached_fields(project, db, status="stale", error=_ERR_STALE_VALIDATION_URL)
        raise HTTPException(status_code=400, detail=_ERR_STALE_VALIDATION_URL)

    owner, repo, pr_number = parsed
    headers = {
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
        "Authorization": f"token {token}",
    }
    return owner, repo, pr_number, headers, token


def _handle_already_merged_validation_pr(
    project,
    db: Session,
    pr_data: dict,
    owner: str,
    repo: str,
    github_user: str,
    cleanup_branch: bool,
) -> dict:
    """Handle the case where a validation PR is already merged.

    Updates preflight status and optionally cleans up the branch.
    Returns the response dict.
    """
    _update_preflight_cached_fields(project, db, status="passed", error=None)

    branch_deleted = False
    branch_delete_warning = None
    if cleanup_branch:
        branch_deleted, branch_delete_warning = _cleanup_validation_pr_branch(
            pr_data, owner, repo, github_user
        )

    return {
        "message": "Validation PR already merged",
        "status": project.last_preflight_status,
        "last_preflight_pr_url": project.last_preflight_pr_url,
        "branch_deleted": branch_deleted,
        "branch_delete_warning": branch_delete_warning,
    }


def _execute_validation_pr_merge_and_respond(
    owner: str,
    repo: str,
    pr_number: int,
    headers: dict,
    github_user: str,
    db: Session,
    project,
    pr_data: dict,
    cleanup_branch: bool,
) -> dict:
    """Merge the validation PR and return the response dict.

    Raises HTTPException on merge failure.
    """
    merge_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}/merge"
    merge_response, merge_method, merge_error = _merge_pull_request_with_fallback(
        merge_url=merge_url,
        github_user=github_user,
        db=db,
        headers=headers,
        commit_title=f"Merge validation preflight PR #{pr_number}",
    )

    if merge_response.status_code == 405:
        raise HTTPException(
            status_code=400,
            detail=merge_error or _github_error_message(
                merge_response,
                "Validation PR cannot be merged. Check permissions, branch protection, draft status, "
                "conflicts, and required checks.",
            ),
        )
    if merge_response.status_code == 404:
        raise HTTPException(status_code=404, detail="Validation PR not found.")
    if merge_response.status_code != 200:
        raise HTTPException(
            status_code=merge_response.status_code,
            detail=_github_error_message(merge_response, f"Failed to merge validation PR: {merge_response.status_code}"),
        )

    branch_deleted = False
    branch_delete_warning = None
    if cleanup_branch:
        branch_deleted, branch_delete_warning = _cleanup_validation_pr_branch(
            pr_data, owner, repo, github_user
        )

    _update_preflight_cached_fields(project, db, status="passed", error=None)
    return {
        "message": "Validation PR merged",
        "status": project.last_preflight_status,
        "last_preflight_pr_url": project.last_preflight_pr_url,
        "merge_method": merge_method,
        "branch_deleted": branch_deleted,
        "branch_delete_warning": branch_delete_warning,
    }


@router.patch("/api/close-preflight-validation-pr", responses=_responses(400, 401, 403, 404, 500))
def close_preflight_validation_pr(
    payload: ClosePreflightValidationRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Close the project's validation PR and optionally delete the source branch."""
    github_user = _resolve_github_user(x_github_user, payload.github_user)
    try:
        if github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
        token = user_tokens[github_user]

        project = _find_project_by_name(db, github_user, payload.project_name)
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)

        pr_url = project.last_preflight_pr_url
        if not pr_url:
            raise HTTPException(status_code=400, detail="No validation PR is recorded for this project.")

        parsed = _parse_github_pr_url(pr_url)
        if not parsed:
            _update_preflight_cached_fields(project, db, status="stale", error=_ERR_STALE_VALIDATION_URL)
            raise HTTPException(status_code=400, detail=_ERR_STALE_VALIDATION_URL)

        owner, repo, pr_number = parsed
        headers = {
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION,
            "Authorization": f"token {token}",
        }

        pr_api_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        pr_data = _fetch_validation_pr_or_raise(project, db, pr_api_url, github_user, headers)
        pr_is_merged = _is_pull_request_merged(pr_data)
        current_state = pr_data.get("state", "open")

        if not pr_is_merged and current_state != "closed":
            _close_validation_pr_or_raise(pr_api_url, github_user, db, headers)

        branch_deleted = False
        branch_delete_warning = None
        if payload.cleanup_branch:
            branch_deleted, branch_delete_warning = _cleanup_validation_pr_branch(
                pr_data, owner, repo, github_user
            )

        # Closing an open validation PR rejects the preflight; a merged PR stays approved/passed.
        new_status = "passed" if pr_is_merged else "closed"
        _update_preflight_cached_fields(project, db, status=new_status, error=None)

        return {
            "message": "Validation PR closed",
            "status": new_status,
            "last_preflight_pr_url": project.last_preflight_pr_url,
            "branch_deleted": branch_deleted,
            "branch_delete_warning": branch_delete_warning,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error closing validation PR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to close validation PR.")


@router.put("/api/merge-preflight-validation-pr", responses=_responses(400, 401, 403, 404, 500))
def merge_preflight_validation_pr(
    payload: MergePreflightValidationRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Merge the project's validation PR to approve preflight."""
    github_user = _resolve_github_user(x_github_user, payload.github_user)
    try:
        project = _find_project_by_name(db, github_user, payload.project_name)

        owner, repo, pr_number, headers, _ = _validate_merge_preflight_request(
            github_user, project, db
        )

        pr_api_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        pr_data = _fetch_validation_pr_or_raise(project, db, pr_api_url, github_user, headers)

        if _is_pull_request_merged(pr_data):
            return _handle_already_merged_validation_pr(
                project, db, pr_data, owner, repo, github_user, payload.cleanup_branch
            )

        if pr_data.get("state") != "open":
            _update_preflight_cached_fields(project, db, status="closed", error=None)
            raise HTTPException(status_code=400, detail="Validation PR is not open.")

        action_capabilities = _derive_pr_action_capabilities(pr_data)
        if action_capabilities.get("can_merge") is False:
            raise HTTPException(
                status_code=400,
                detail=action_capabilities.get("merge_block_reason") or "Validation PR cannot be merged.",
            )

        return _execute_validation_pr_merge_and_respond(
            owner, repo, pr_number, headers, github_user, db, project, pr_data, payload.cleanup_branch
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error merging validation PR: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Failed to merge validation PR.")


def _fetch_pr_state_from_github(pr, github_user: str, token: str, db: Session) -> str:
    """Fetch the current state of a single PR from GitHub and persist any change to the DB.

    Returns the (possibly updated) PR state string.  Falls back to the cached
    ``pr.pr_state`` if the API call fails or returns a non-200 status.
    """
    headers = {
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
        "Authorization": f"token {token}",
    }
    owner, repo = pr.repo_name.split("/", 1)
    pr_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr.pr_number}"

    try:
        response = github_get(pr_url, github_user, db, headers=headers)
        if response.status_code != 200:
            pr._github_action_capabilities = {
                "can_merge": False,
                "merge_block_reason": f"Unable to refresh PR from GitHub: {response.status_code}",
                "can_close": False,
                "close_block_reason": f"Unable to refresh PR from GitHub: {response.status_code}",
            }
            return pr.pr_state

        pr_data = response.json()
        pr._github_action_capabilities = _derive_pr_action_capabilities(pr_data)
        pr_state = "merged" if _is_pull_request_merged(pr_data) else pr_data.get("state", "open")

        if pr.pr_state != pr_state:
            original_state = pr.pr_state
            pr.pr_state = pr_state
            # Backfill timestamp fields when transitioning from GitHub data
            if pr_state == "merged" and pr.merged_at is None:
                raw_merged_at = pr_data.get("merged_at")
                if raw_merged_at:
                    try:
                        pr.merged_at = datetime.fromisoformat(raw_merged_at.replace("Z", "+00:00"))
                    except Exception:
                        print(f"⚠️ Could not parse merged_at for PR #{pr.pr_number}: {raw_merged_at!r}")
                        # Leave merged_at as None rather than writing a misleading current timestamp
                else:
                    # GitHub did not return a merged_at value; leave the field unset
                    pass
            elif pr_state == "closed" and pr.closed_at is None:
                raw_closed_at = pr_data.get("closed_at")
                if raw_closed_at:
                    try:
                        pr.closed_at = datetime.fromisoformat(raw_closed_at.replace("Z", "+00:00"))
                    except Exception:
                        print(f"⚠️ Could not parse closed_at for PR #{pr.pr_number}: {raw_closed_at!r}")
                        # Leave closed_at as None rather than writing a misleading current timestamp
                else:
                    # GitHub did not return a closed_at value; leave the field unset
                    pass
            # Backfill title/author if not yet stored
            if not pr.title and pr_data.get("title"):
                pr.title = pr_data["title"]
            if not pr.author and pr_data.get("user", {}).get("login"):
                pr.author = pr_data["user"]["login"]
            try:
                db.commit()
                print(f"✅ Updated PR #{pr.pr_number} state to: {pr_state}")
            except Exception as commit_err:
                print(f"⚠️ Error persisting PR #{pr.pr_number} state: {commit_err}")
                db.rollback()
                pr.pr_state = original_state
                return original_state

            # Separate try/except from the commit above: the PR-state write is
            # already durable at this point, so a notification failure here must
            # never be mistaken for (or trigger a rollback of) that commit.
            try:
                record_campaign_pr_transition(db, pr, original_state, pr_state)
            except Exception as notify_err:
                print(f"⚠️ Error recording campaign PR transition notification: {notify_err}")
                db.rollback()

        return pr_state

    except Exception as e:
        print(f"⚠️ Error fetching PR #{pr.pr_number} state: {e}")
        return pr.pr_state


def _resolve_pr_state(pr, refresh_from_github: bool, github_user: str, token: str, db: Session) -> str:
    """Return the current state for a PR, optionally refreshing from GitHub."""
    # merged/closed are terminal — they cannot change, so skip the API call.
    if refresh_from_github and "/" in pr.repo_name and pr.pr_state == "open":
        return _fetch_pr_state_from_github(pr, github_user, token, db)
    return pr.pr_state


def _pr_action_fields(pr) -> dict:
    return getattr(pr, "_github_action_capabilities", {}) or {}


def _apply_all_prs_resolved_transitions(
    db: Session, project, total_count: int, merged_count: int
) -> None:
    """Apply workflow/project state transitions after all PRs have been resolved.

    When every PR was merged the workflows move to *synced_with_github*; when at
    least one PR was closed without a merge they revert to *committed_locally*.

    This function also handles the matching updates for any linked reusable
    workflows so the caller does not need to repeat that pattern.
    """
    if total_count == 0:
        return
    all_merged = merged_count == total_count

    new_wf_status = "synced_with_github" if all_merged else "committed_locally"
    new_pr_state = "synced" if all_merged else "draft"

    _update_project_workflows_status(
        db, project.project_id, new_wf_status, only_if_status="under_review"
    )
    _update_project_custom_files_status(db, project.project_id, new_wf_status, only_if_status="under_review")
    _update_project_codeowners_status(db, project.project_id, new_wf_status, only_if_status="under_review")

    linked_wf_ids = _get_linked_workflow_ids_for_project(
        db, project.project_id, only_if_status="under_review"
    )
    if linked_wf_ids:
        # Global lock: linked reusable workflows still referenced by an open
        # PR campaign in another project must stay under_review.
        locked_ids = _reusable_workflow_ids_locked_by_open_campaign(db, linked_wf_ids)
        if locked_ids:
            print(
                f"🔒 Page-load sync: kept {len(locked_ids)} linked workflow(s) "
                f"under_review (open PR campaign in another project)"
            )
            linked_wf_ids = [wid for wid in linked_wf_ids if wid not in locked_ids]
    if linked_wf_ids:
        try:
            db.query(Workflow).filter(
                Workflow.workflow_id.in_(linked_wf_ids)
            ).update({"workflow_status": new_wf_status}, synchronize_session=False)
            db.commit()
            print(f"✅ Page-load sync: {len(linked_wf_ids)} linked workflow(s) → {new_wf_status}")
            if all_merged:
                # Update pr_state for owning RWX projects whose remaining
                # under_review workflow count drops to zero.
                rwx_pids = (
                    db.query(LinkedReusableWorkflow.rwx_project_id)
                    .filter(LinkedReusableWorkflow.workflow_id.in_(linked_wf_ids))
                    .distinct()
                    .all()
                )
                for (rwx_pid,) in rwx_pids:
                    remaining = (
                        db.query(Workflow)
                        .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
                        .filter(
                            ProjectWorkflow.project_id == rwx_pid,
                            Workflow.workflow_status == "under_review",
                        )
                        .count()
                    )
                    if remaining == 0:
                        _update_project_pr_state(db, rwx_pid, "synced")
        except Exception as e:
            print(f"❌ Error updating linked workflow statuses: {str(e)}")
            db.rollback()

    # Mirror _sync_linked_reusable_workflows_after_merge: a project is only
    # marked resolved (synced/draft) when none of its own workflows remain
    # under_review — e.g. an RWX project whose workflow is still locked by a
    # caller's open PR campaign keeps its current pr_state.
    remaining_under_review = (
        db.query(Workflow)
        .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
        .filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.workflow_status == "under_review",
        )
        .count()
    )
    if remaining_under_review:
        print(
            f"🔒 Page-load sync: kept pr_state for project {project.project_id} — "
            f"{remaining_under_review} workflow(s) still under_review"
        )
        return

    _update_project_pr_state(db, project.project_id, new_pr_state)

    if all_merged:
        print("✅ Page-load sync: all PRs merged, workflows set to synced_with_github")
    else:
        print("✅ Page-load sync: at least one PR closed without merge, workflows reverted to committed_locally")


def _get_pr_visibility_project_map(db: Session, project: Project) -> dict[int, str]:
    """Return project IDs whose PRs are visible from the queried project."""
    project_id_map: dict[int, str] = {project.project_id: project.project_name}

    if project.project_type == "standard":
        linked_rwx_rows = (
            db.query(LinkedReusableWorkflow)
            .filter(LinkedReusableWorkflow.standard_project_id == project.project_id)
            .all()
        )
        rwx_project_ids = {row.rwx_project_id for row in linked_rwx_rows}
        if rwx_project_ids:
            rwx_projects = db.query(Project).filter(
                Project.project_id.in_(rwx_project_ids)
            ).all()
            for rwx_proj in rwx_projects:
                project_id_map[rwx_proj.project_id] = rwx_proj.project_name
    else:
        linked_std_rows = (
            db.query(LinkedReusableWorkflow)
            .filter(LinkedReusableWorkflow.rwx_project_id == project.project_id)
            .all()
        )
        std_project_ids = {row.standard_project_id for row in linked_std_rows}
        if std_project_ids:
            std_projects = db.query(Project).filter(
                Project.project_id.in_(std_project_ids)
            ).all()
            for std_proj in std_projects:
                project_id_map[std_proj.project_id] = std_proj.project_name

    return project_id_map


def _split_workflow_names(workflow_names: Optional[str]) -> List[str]:
    if not workflow_names:
        return []
    return [name.strip() for name in workflow_names.split(",") if name.strip()]


def _derive_campaign_name(prs: List[ProjectPullRequest]) -> str:
    workflows: List[str] = []
    for pr in prs:
        for workflow in _split_workflow_names(pr.workflow_names):
            if workflow not in workflows:
                workflows.append(workflow)
    if len(workflows) == 1:
        return f"Update {workflows[0]}"
    if len(workflows) > 1:
        return f"Update {workflows[0]} + {len(workflows) - 1} more"
    title = next((pr.title for pr in prs if pr.title), None)
    return title or "File rollout"


def _campaign_status_from_counts(open_count: int, merged_count: int, closed_count: int) -> str:
    if open_count > 0:
        return "open"
    if merged_count > 0 and closed_count == 0:
        return "completed"
    if merged_count > 0 and closed_count > 0:
        return "partially_completed"
    if closed_count > 0:
        return "cancelled"
    return "open"


def _campaign_group_key(pr: ProjectPullRequest) -> tuple:
    """Best-effort campaign key using existing PR fields without new schema."""
    workflow_key = ",".join(sorted(_split_workflow_names(pr.workflow_names)))
    created_day = pr.created_at.date().isoformat() if pr.created_at else ""
    return (pr.project_id, workflow_key, pr.target_branch, created_day)


def _campaign_pr_response(
    pr: ProjectPullRequest,
    project_id_map: dict[int, str],
    queried_project_id: int,
    reusable_workflow_names: set[str],
) -> PRCampaignPRResponse:
    source_project_name = (
        project_id_map.get(pr.project_id)
        if pr.project_id != queried_project_id
        else None
    )
    is_reusable_workflow_pr = any(
        _normalize_reusable_workflow_name(name) in reusable_workflow_names
        for name in _split_workflow_names(pr.workflow_names)
    )
    return PRCampaignPRResponse(
        pr_id=pr.pr_id,
        repo_name=pr.repo_name,
        pr_number=pr.pr_number,
        pr_url=pr.pr_url,
        pr_state=pr.pr_state,
        branch_name=pr.branch_name,
        target_branch=pr.target_branch,
        title=pr.title,
        author=pr.author,
        body=pr.body,
        workflow_names=pr.workflow_names,
        file_names=pr.file_names,
        created_at=pr.created_at.isoformat() if pr.created_at else "",
        updated_at=pr.updated_at.isoformat() if pr.updated_at else "",
        merged_at=pr.merged_at.isoformat() if pr.merged_at else None,
        closed_at=pr.closed_at.isoformat() if pr.closed_at else None,
        source_project_name=source_project_name,
        actor=pr.author,
        is_reusable_workflow_pr=is_reusable_workflow_pr,
        **_pr_action_fields(pr),
    )


@router.get("/api/project-pr-status", responses=_responses(401, 404, 500))
def get_project_pr_status(
    github_user: str,
    project_name: str,
    db: Annotated[Session, Depends(get_db)],
    refresh_from_github: bool = False
):
    """
    Get the PR status for a project, including list of all PRs and their current states.

    Cross-project visibility
    ------------------------
    Pull requests are surfaced across linked Standard ↔ Reusable-Workflow (RWX)
    project pairs so that users see the full picture from either side:

    * Standard Project queried → also includes PRs created by linked
      RWX projects for workflows owned by those RWX projects.
    * RWX Project queried → also includes PRs created by each Standard Project
      that links to it (for reusable workflows in the RWX repo).

    This ensures that when a Standard project creates a PR for a linked reusable
    workflow, the RWX project shows:
    - Open PR banner
    - Locked workflow state
    - PR in Open PRs list

    Args:
        github_user: GitHub username
        project_name: Project name
        db: Database session
        refresh_from_github: If True, fetches current state from GitHub API and updates database.
                           If False (default), returns cached state from database for fast loading.

    Returns cached database state by default for fast loading. Only fetches from GitHub
    when explicitly requested via refresh_from_github=true.
    """
    try:
        if github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

        token = user_tokens[github_user]

        project = _find_project_by_name(db, github_user, project_name)
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)

        # ------------------------------------------------------------------
        # Collect related project IDs via LinkedReusableWorkflow so that PR
        # status is shared across linked Standard ↔ RWX project pairs.
        # ------------------------------------------------------------------
        # project_id_map: {project_id -> project_name} for every project whose
        # PRs should appear in this view (current + linked projects).
        project_id_map: dict[int, str] = {project.project_id: project.project_name}

        if project.project_type == "standard":
            # Standard project: include PRs from each linked RWX project.
            linked_rwx_rows = (
                db.query(LinkedReusableWorkflow)
                .filter(LinkedReusableWorkflow.standard_project_id == project.project_id)
                .all()
            )
            rwx_project_ids = {row.rwx_project_id for row in linked_rwx_rows}
            if rwx_project_ids:
                rwx_projects = db.query(Project).filter(
                    Project.project_id.in_(rwx_project_ids)
                ).all()
                for rwx_proj in rwx_projects:
                    project_id_map[rwx_proj.project_id] = rwx_proj.project_name
        else:
            # RWX project: include PRs from each Standard project that links to it.
            linked_std_rows = (
                db.query(LinkedReusableWorkflow)
                .filter(LinkedReusableWorkflow.rwx_project_id == project.project_id)
                .all()
            )
            std_project_ids = {row.standard_project_id for row in linked_std_rows}
            if std_project_ids:
                std_projects = db.query(Project).filter(
                    Project.project_id.in_(std_project_ids)
                ).all()
                for std_proj in std_projects:
                    project_id_map[std_proj.project_id] = std_proj.project_name

        prs = db.query(ProjectPullRequest).filter(
            ProjectPullRequest.project_id.in_(project_id_map.keys())
        ).all()

        pr_responses = []
        open_count = 0
        merged_count = 0
        closed_count = 0

        for pr in prs:
            pr_state = _resolve_pr_state(pr, refresh_from_github, github_user, token, db)

            if pr_state == "open":
                open_count += 1
            elif pr_state == "merged":
                merged_count += 1
            elif pr_state == "closed":
                closed_count += 1

            # This server-side filter applies only to the returned
            # `pull_requests` list so resolved PRs do not appear in the
            # open PR drawer or expose open-PR actions. Summary counts are
            # still accumulated across all PR states above, and the
            # "Pull Requests Open" banner visibility is determined
            # separately by `project.pr_state`, not by this filter.
            # Merged and closed PRs remain available via the
            # /api/project-pr-history endpoint backing the PR History view.
            if pr_state != "open":
                continue

            # Determine if this PR belongs to the queried project or a linked project
            source_project_name = None
            if pr.project_id != project.project_id:
                # PR belongs to a linked project — label it with the source project name
                source_project_name = project_id_map.get(pr.project_id)

            pr_responses.append(PRStatusResponse(
                repo_name=pr.repo_name,
                pr_number=pr.pr_number,
                pr_url=pr.pr_url,
                pr_state=pr_state,
                branch_name=pr.branch_name,
                target_branch=pr.target_branch,
                created_at=pr.created_at.isoformat() if pr.created_at else "",
                updated_at=pr.updated_at.isoformat() if pr.updated_at else "",
                source_project_name=source_project_name,
                **_pr_action_fields(pr),
            ))

        # After refreshing from GitHub, apply workflow/project state transitions
        # whenever all PRs are now resolved (no remaining open ones).
        # We intentionally do NOT gate on initial_project_pr_state == "open" here.
        # The frontend already controls when refresh_from_github=true is sent (only
        # when pr_state=="open" OR workflows are stuck at "under_review"), so by the
        # time we reach this code the project genuinely has PRs whose resolved state
        # needs to be reflected. Using an overly narrow had_open_state guard caused
        # silent skips when project.pr_state held an unexpected value (e.g. due to
        # a previous partial transition), leaving the UI permanently stuck.
        # Use the in-memory counts from the loop above (already accurate from the
        # GitHub API responses) rather than re-querying the DB, which can return
        # stale results due to SQLAlchemy session caching between per-PR commits.
        if refresh_from_github and len(prs) > 0 and open_count == 0:
            _apply_all_prs_resolved_transitions(db, project, len(prs), merged_count)
            db.refresh(project)

        # Compute the cross-project lock set so the frontend can avoid flipping
        # linked reusable workflow badges that are still held under_review by an
        # open PR campaign in *another* project (a sibling caller or the owning
        # RWX project) — that campaign is not necessarily visible in this
        # project's ``open_prs`` count and would otherwise look "resolved".
        candidate_wf_ids: set[int] = set()
        # Linked reusable workflows for a standard project.
        candidate_wf_ids.update(
            wid for (wid,) in
            db.query(Workflow.workflow_id)
            .join(LinkedReusableWorkflow, LinkedReusableWorkflow.workflow_id == Workflow.workflow_id)
            .filter(LinkedReusableWorkflow.standard_project_id == project.project_id)
            .all()
        )
        # Reusable workflows owned by the project (the RWX-project view).
        candidate_wf_ids.update(
            wid for (wid,) in
            db.query(Workflow.workflow_id)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(
                ProjectWorkflow.project_id == project.project_id,
                Workflow.reusable_workflow.is_(True),
            )
            .all()
        )
        locked_workflow_ids = sorted(
            _reusable_workflow_ids_locked_by_open_campaign(db, list(candidate_wf_ids))
        ) if candidate_wf_ids else []

        return ProjectPRStatusResponse(
            project_state=project.pr_state or "new",
            pull_requests=pr_responses,
            total_prs=len(prs),
            open_prs=open_count,
            merged_prs=merged_count,
            closed_prs=closed_count,
            locked_workflow_ids=locked_workflow_ids,
        )

    except Exception as e:
        print(f"❌ Error getting project PR status: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# Protected branch names that must never be deleted by ActionsManager.
_PROTECTED_BRANCH_NAMES = frozenset({
    "main", "master", "develop", "development", "staging", "production", "prod",
})
_PROTECTED_BRANCH_PREFIXES = ("release/", "release-", "hotfix/", "hotfix-")

# Regex that matches the *new* unique ActionsManager branch naming convention:
#   actions-manager/<project_code>/<repo_slug>/<short_id>-<base_branch>
# Also matches the *legacy* format:
#   actions-manager/<project_code>-<base_branch>
# Both start with "actions-manager/" so a single prefix check is sufficient for
# the first safety gate; the full regex is used for belt-and-braces validation.
_AM_BRANCH_RE = re.compile(r'^actions-manager/')


def _is_safe_to_delete_am_branch(branch_name: str, target_branch: str) -> tuple:
    """
    Validate that *branch_name* is safe to delete under ActionsManager rules.

    Rules:
    - Branch must start with 'actions-manager/'
    - Branch must not equal target_branch
    - Branch must not be a well-known protected branch name
    - Branch must not start with a protected prefix

    Returns:
        (is_safe: bool, reason: str)  – reason is non-empty when is_safe is False.
    """
    if not _AM_BRANCH_RE.match(branch_name):
        return False, f"Branch '{branch_name}' does not follow ActionsManager naming convention"

    if branch_name == target_branch:
        return False, "Source branch and target branch are the same — refusing to delete"

    # Protect well-known stable branches by checking the full branch_name and the
    # last path segment (base). Because branch_name always starts with
    # "actions-manager/", we also check the path *after* that prefix to catch
    # patterns like "actions-manager/release/1.0" or "actions-manager/develop".
    base = branch_name.split("/")[-1] if "/" in branch_name else branch_name
    # Strip the leading "actions-manager/" so prefix rules apply to the rest of the path
    am_stripped = branch_name[len("actions-manager/"):]

    if base in _PROTECTED_BRANCH_NAMES or branch_name in _PROTECTED_BRANCH_NAMES:
        return False, f"Branch '{branch_name}' is a protected branch — refusing to delete"

    for prefix in _PROTECTED_BRANCH_PREFIXES:
        if am_stripped.startswith(prefix) or base.startswith(prefix):
            return False, f"Branch '{branch_name}' matches protected prefix '{prefix}'"

    return True, ""


def _delete_actions_manager_branch(
    owner: str,
    repo: str,
    branch_name: str,
    target_branch: str,
    github_user: str,
) -> tuple:
    """
    Attempt to delete an ActionsManager-created source branch after a successful merge.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch_name: The ActionsManager source branch to delete.
        target_branch: The base branch the PR was merged into (used for safety check).
        github_user: Authenticated GitHub user.
        db: Database session.

    Returns:
        (deleted: bool, warning: str or None)
    """
    is_safe, reason = _is_safe_to_delete_am_branch(branch_name, target_branch)
    if not is_safe:
        print(f"⚠️ Skipping branch deletion: {reason}")
        return False, reason

    delete_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs/heads/{branch_name}"
    try:
        # Use requests directly with the authenticated token
        token = user_tokens.get(github_user)
        if not token:
            msg = "Cannot delete branch: user token not available"
            print(f"⚠️ {msg}")
            return False, msg

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"token {token}",
        }
        del_response = requests.delete(delete_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)

        if del_response.status_code == 204:
            print(f"✅ Deleted ActionsManager branch '{branch_name}' in {owner}/{repo}")
            return True, None
        elif del_response.status_code == 422:
            msg = f"Branch '{branch_name}' is protected or cannot be deleted: {del_response.text[:200]}"
            print(f"⚠️ {msg}")
            return False, msg
        elif del_response.status_code == 404:
            # Branch was already deleted (e.g. GitHub auto-delete on merge)
            print(f"📌 Branch '{branch_name}' already gone (404) — treating as deleted")
            return True, None
        else:
            msg = f"GitHub API returned {del_response.status_code} deleting '{branch_name}': {del_response.text[:200]}"
            print(f"⚠️ {msg}")
            return False, msg
    except Exception as exc:
        print(f"❌ Exception while deleting branch '{branch_name}': {exc}")
        msg = "Branch deletion failed due to an unexpected error. Check server logs for details."
        return False, msg


def _merge_pull_request_with_fallback(
    *,
    merge_url: str,
    github_user: str,
    db: Session,
    headers: dict,
    commit_title: str,
):
    """Try supported GitHub merge methods so repos that disable merge commits still work."""
    last_response = None
    attempted_messages = []
    for merge_method in ("merge", "squash", "rebase"):
        merge_payload = {
            "commit_title": commit_title,
            "merge_method": merge_method,
        }
        response = github_put(merge_url, github_user, db, json=merge_payload, headers=headers)
        if response.status_code == 200:
            return response, merge_method, None

        last_response = response
        if response.status_code != 405:
            return response, merge_method, None

        message = _github_error_message(response, f"Pull request cannot be merged with {merge_method}.")
        attempted_messages.append(f"{merge_method}: {message}")

    return last_response, "rebase", "GitHub rejected all merge methods. " + " | ".join(attempted_messages)


def _create_pr_merged_version_entries(db, project, pr_number, repo_name):
    """Create a 'pr_merged' version entry for each non-reusable workflow in the project."""
    try:
        nr_workflows = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.reusable_workflow == False
        ).all()
        for wf in nr_workflows:
            create_workflow_version(
                db,
                wf.workflow_id,
                wf.workflow_yaml,
                metadata={
                    'action': 'pr_merged',
                    'pr_number': pr_number,
                    'repo_name': repo_name,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                },
                commit=False
            )
        db.commit()
        print(f"✅ Created pr_merged version entries for {len(nr_workflows)} workflow(s)")
    except Exception as e:
        print(f"❌ Error creating pr_merged version entries: {str(e)}")
        db.rollback()


def _clear_drift_for_merged_pr(db, project, pr_record) -> None:
    """Clear persisted drift for the workflows a merged PR restored.

    Scoped to the PR's own workflows and repo: a merge only proves those files
    now match GitHub, so clearing project-wide would hide real drift elsewhere.
    """
    if not pr_record or not pr_record.workflow_names:
        return
    names = [n.strip() for n in pr_record.workflow_names.split(",") if n.strip()]
    if not names:
        return
    workflows = db.query(Workflow).join(ProjectWorkflow).filter(
        ProjectWorkflow.project_id == project.project_id,
        Workflow.workflow_name.in_(names),
    ).all()
    for wf in workflows:
        clear_workflow_drift(db, project, wf.workflow_id, pr_record.repo_name,
                             pr_record.target_branch)


def _handle_merged_pull_request(*, response, project, repo_name, pr_number, owner, repo, github_user, db, merge_method):
    """Persist database state and clean up after a successful PR merge; returns the response dict."""
    merge_data = response.json()
    print(f"✅ Successfully merged PR #{pr_number} in {repo_name}")

    # Update PR state in database
    pr_record = db.query(ProjectPullRequest).filter_by(
        project_id=project.project_id,
        repo_name=repo_name,
        pr_number=pr_number
    ).first()

    if pr_record:
        pr_record.pr_state = "merged"
        pr_record.merged_at = datetime.now(timezone.utc)
        db.commit()
        print(f"✅ Updated PR #{pr_number} state to merged in database")
        _clear_drift_for_merged_pr(db, project, pr_record)

    # Only mark project/workflows as synced when no PRs remain open.
    # Use pr_state='open' (not != 'merged') so a mix of merged + closed PRs
    # also triggers the transition instead of leaving status stuck under_review.
    open_prs = db.query(ProjectPullRequest).filter(
        ProjectPullRequest.project_id == project.project_id,
        ProjectPullRequest.pr_state == "open"
    ).count()

    if open_prs == 0:
        total_count = db.query(ProjectPullRequest).filter_by(project_id=project.project_id).count()
        merged_count = db.query(ProjectPullRequest).filter_by(
            project_id=project.project_id, pr_state="merged"
        ).count()
        _apply_all_prs_resolved_transitions(db, project, total_count, merged_count)
        # Reconcile linked reusable workflows owned by RWX projects
        if merged_count == total_count:
            _sync_linked_reusable_workflows_after_merge(db, project.project_id)

    # Create a "pr_merged" version entry for each non-reusable workflow so History shows ⭐
    _create_pr_merged_version_entries(db, project, pr_number, repo_name)

    # Attempt to delete the source branch (best-effort; never fails the merge)
    branch_deleted = False
    branch_delete_warning = None
    if pr_record and pr_record.branch_name and pr_record.target_branch:
        branch_deleted, branch_delete_warning = _delete_actions_manager_branch(
            owner=owner,
            repo=repo,
            branch_name=pr_record.branch_name,
            target_branch=pr_record.target_branch,
            github_user=github_user,
        )
    else:
        branch_delete_warning = "PR record or " + BRANCH_INFO_NOT_FOUND
        print(f"⚠️ {branch_delete_warning}")

    return {
        "message": "Pull request merged successfully",
        "pr_number": pr_number,
        "repo_name": repo_name,
        "sha": merge_data.get("sha"),
        "merged": True,
        "merge_method": merge_method,
        "branch_deleted": branch_deleted,
        "branch_delete_warning": branch_delete_warning,
    }


@router.put("/api/merge-pull-request", responses=_responses(400, 401, 404, 500))
def merge_pull_request(
    payload: MergePullRequestRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """
    Merge a pull request for a project.
    Updates the PR state in the database and triggers project state transition if needed.
    """
    try:
        github_user = _resolve_github_user(x_github_user, payload.github_user)
        project_name = payload.project_name
        repo_name = payload.repo_name
        pr_number = payload.pr_number
        
        # Check authentication
        if github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
        
        token = user_tokens[github_user]
        
        # Get project
        project = _find_project_by_name(db, github_user, project_name)
        
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)
        
        # Validate repo_name format
        if "/" not in repo_name:
            raise HTTPException(status_code=400, detail="Invalid repository name format. Expected 'owner/repo'")
        
        owner, repo = repo_name.split("/", 1)
        
        # Merge PR using GitHub API
        merge_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}/merge"
        headers = {
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION,
            "Authorization": f"token {token}"
        }
        
        response, merge_method, merge_error = _merge_pull_request_with_fallback(
            merge_url=merge_url,
            github_user=github_user,
            db=db,
            headers=headers,
            commit_title=f"Merge pull request #{pr_number}",
        )
        
        if response.status_code == 200:
            # Successfully merged
            return _handle_merged_pull_request(
                response=response,
                project=project,
                repo_name=repo_name,
                pr_number=pr_number,
                owner=owner,
                repo=repo,
                github_user=github_user,
                db=db,
                merge_method=merge_method,
            )
        elif response.status_code == 405:
            # PR cannot be merged (conflicts, checks failing, etc.)
            raise HTTPException(
                status_code=400,
                detail=merge_error or _github_error_message(
                    response,
                    "Pull request cannot be merged. Check permissions, branch protection, draft status, "
                    "conflicts, and required checks.",
                )
            )
        elif response.status_code == 404:
            raise HTTPException(status_code=404, detail="Pull request not found")
        else:
            # Other errors
            raise HTTPException(
                status_code=response.status_code,
                detail=_github_error_message(response, f"Failed to merge pull request: {response.status_code}")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error merging pull request: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/api/close-pull-request", responses=_responses(400, 401, 404, 500))
def close_pull_request(
    payload: ClosePullRequestRequest,
    db: Annotated[Session, Depends(get_db)],

    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """
    Close a pull request for a project without merging.
    Updates the PR state in the database and triggers project state transition if needed.
    """
    try:
        github_user = _resolve_github_user(x_github_user, payload.github_user)
        project_name = payload.project_name
        repo_name = payload.repo_name
        pr_number = payload.pr_number
        
        # Check authentication
        if github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
        
        token = user_tokens[github_user]
        
        # Get project
        project = _find_project_by_name(db, github_user, project_name)
        
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)
        
        # Validate repo_name format
        if "/" not in repo_name:
            raise HTTPException(status_code=400, detail="Invalid repository name format. Expected 'owner/repo'")
        
        owner, repo = repo_name.split("/", 1)
        
        # Close PR using GitHub API
        pr_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = {
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION,
            "Authorization": f"token {token}"
        }
        
        close_payload = {
            "state": "closed"
        }
        
        response = github_patch(pr_url, github_user, db, json=close_payload, headers=headers)
        
        if response.status_code == 200:
            # Successfully closed
            pr_data = response.json()
            print(f"✅ Successfully closed PR #{pr_number} in {repo_name}")
            
            # Update PR state in database
            pr_record = db.query(ProjectPullRequest).filter_by(
                project_id=project.project_id,
                repo_name=repo_name,
                pr_number=pr_number
            ).first()
            
            if pr_record:
                pr_record.pr_state = "closed"
                pr_record.closed_at = datetime.now(timezone.utc)
                db.commit()
                print(f"✅ Updated PR #{pr_number} state to closed in database")
            
            # Check if any PRs are still open; if not, revert workflow statuses and project state
            open_prs = db.query(ProjectPullRequest).filter_by(
                project_id=project.project_id,
                pr_state="open"
            ).count()
            if open_prs == 0:
                # No remaining open PRs: revert "under_review" workflows to "committed_locally"
                _update_project_workflows_status(
                    db, project.project_id, "committed_locally", only_if_status="under_review"
                )
                _update_project_custom_files_status(db, project.project_id, "committed_locally", only_if_status="under_review")
                _update_project_codeowners_status(db, project.project_id, "committed_locally", only_if_status="under_review")
                _update_project_pr_state(db, project.project_id, "draft")

            return {
                "message": "Pull request closed successfully",
                "pr_number": pr_number,
                "repo_name": repo_name,
                "state": pr_data.get("state"),
                "closed": True
            }
        elif response.status_code == 404:
            raise HTTPException(status_code=404, detail="Pull request not found")
        else:
            # Other errors
            raise HTTPException(
                status_code=response.status_code,
                detail=_github_error_message(response, f"Failed to close pull request: {response.status_code}")
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error closing pull request: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/project-pr-history", responses=_responses(401, 404, 500))
def get_project_pr_history(
    github_user: str,
    project_name: str,
    db: Annotated[Session, Depends(get_db)],
    state_filter: str = "all",  # "all", "merged", "closed"
    repo_filter: Optional[str] = None,
    workflow_filter: Optional[str] = None
) -> PRHistoryResponse:
    """
    Return the PR history (merged and closed PRs) for a project.

    This endpoint is read-only and only surfaces historical PRs — open PRs are
    intentionally excluded so they remain the exclusive domain of the existing
    PR Status panel.

    Cross-project visibility
    ------------------------
    Pull requests are surfaced across linked Standard ↔ Reusable-Workflow (RWX)
    project pairs so that users see the full picture from either side:

    * Standard Project queried → also includes PRs created by each linked
      RWX project (``LinkedReusableWorkflow.rwx_project_id`` rows where
      ``standard_project_id`` matches).
    * RWX Project queried → also includes PRs created by each Standard Project
      that links to it (``LinkedReusableWorkflow.standard_project_id`` rows
      where ``rwx_project_id`` matches).

    PR records are never duplicated — each ``ProjectPullRequest`` row belongs to
    exactly one project.  A single query spanning all related ``project_id``
    values achieves cross-project visibility without redundant data.
    ``source_project_name`` is populated on response items whose
    ``project_id`` differs from the queried project so the UI can label them.

    Args:
        github_user:     GitHub username (must be authenticated).
        project_name:    Project identifier.
        state_filter:    "all" (default), "merged", or "closed".
        repo_filter:     Optional full repo name (owner/repo) to narrow results.
        workflow_filter: Optional substring to match against stored workflow names.
        db:              SQLAlchemy database session.
    """
    try:
        if github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

        project = _find_project_by_name(db, github_user, project_name)
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)

        # ------------------------------------------------------------------
        # Collect related project IDs via LinkedReusableWorkflow so that PR
        # history is shared across linked Standard ↔ RWX project pairs.
        # ------------------------------------------------------------------
        # project_id_map: {project_id -> project_name} for every project whose
        # PRs should appear in this view (current + linked projects).
        project_id_map: dict[int, str] = {project.project_id: project.project_name}

        if project.project_type == "standard":
            # Standard project: include PRs from each linked RWX project.
            linked_rwx_rows = (
                db.query(LinkedReusableWorkflow)
                .filter(LinkedReusableWorkflow.standard_project_id == project.project_id)
                .all()
            )
            rwx_project_ids = {row.rwx_project_id for row in linked_rwx_rows}
            if rwx_project_ids:
                rwx_projects = db.query(Project).filter(
                    Project.project_id.in_(rwx_project_ids)
                ).all()
                for rwx_proj in rwx_projects:
                    project_id_map[rwx_proj.project_id] = rwx_proj.project_name
        else:
            # RWX project: include PRs from each Standard project that links to it.
            linked_std_rows = (
                db.query(LinkedReusableWorkflow)
                .filter(LinkedReusableWorkflow.rwx_project_id == project.project_id)
                .all()
            )
            std_project_ids = {row.standard_project_id for row in linked_std_rows}
            if std_project_ids:
                std_projects = db.query(Project).filter(
                    Project.project_id.in_(std_project_ids)
                ).all()
                for std_proj in std_projects:
                    project_id_map[std_proj.project_id] = std_proj.project_name

        # Base query: only resolved (non-open) PRs across all related projects
        query = db.query(ProjectPullRequest).filter(
            ProjectPullRequest.project_id.in_(project_id_map.keys()),
            ProjectPullRequest.pr_state.in_(["merged", "closed"]),
        )

        if state_filter in ("merged", "closed"):
            query = query.filter(ProjectPullRequest.pr_state == state_filter)

        if repo_filter:
            query = query.filter(ProjectPullRequest.repo_name == repo_filter)

        if workflow_filter:
            query = query.filter(
                ProjectPullRequest.workflow_names.contains(workflow_filter)
            )

        prs = query.order_by(ProjectPullRequest.updated_at.desc()).all()

        items: List[PRHistoryItemResponse] = []
        merged_count = 0
        closed_count = 0

        for pr in prs:
            if pr.pr_state == "merged":
                merged_count += 1
            else:
                closed_count += 1

            # Populate source_project_name for cross-linked PRs so the UI can
            # display which project originally created the pull request.
            source_project_name = (
                project_id_map.get(pr.project_id)
                if pr.project_id != project.project_id
                else None
            )

            items.append(PRHistoryItemResponse(
                pr_id=pr.pr_id,
                repo_name=pr.repo_name,
                pr_number=pr.pr_number,
                pr_url=pr.pr_url,
                pr_state=pr.pr_state,
                branch_name=pr.branch_name,
                target_branch=pr.target_branch,
                title=pr.title,
                author=pr.author,
                body=pr.body,
                workflow_names=pr.workflow_names,
                created_at=pr.created_at.isoformat() if pr.created_at else "",
                updated_at=pr.updated_at.isoformat() if pr.updated_at else "",
                merged_at=pr.merged_at.isoformat() if pr.merged_at else None,
                closed_at=pr.closed_at.isoformat() if pr.closed_at else None,
                source_project_name=source_project_name,
            ))

        return PRHistoryResponse(
            pull_requests=items,
            total=len(items),
            merged_count=merged_count,
            closed_count=closed_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching PR history: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/project-pr-campaigns", responses=_responses(401, 404, 500))
def get_project_pr_campaigns(
    github_user: str,
    project_name: str,
    db: Annotated[Session, Depends(get_db)],
    refresh_from_github: bool = False
) -> PRCampaignsResponse:
    """
    Return PR Campaigns for a project.

    PRs created since campaign tracking was added are grouped by their unique
    campaign_id — every PR campaign creation run produces a new campaign record,
    so new PRs are never appended to a previous campaign. Legacy PR rows without
    a campaign_id are grouped heuristically by project, workflow set, target
    branch, and creation day so existing PR History data remains visible.
    """
    try:
        if github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

        token = user_tokens[github_user]
        project = _find_project_by_name(db, github_user, project_name)
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)

        project_id_map = _get_pr_visibility_project_map(db, project)
        visible_projects = db.query(Project).filter(
            Project.project_id.in_(project_id_map.keys())
        ).all()
        linked_rows = db.query(LinkedReusableWorkflow, Workflow).join(
            Workflow, LinkedReusableWorkflow.workflow_id == Workflow.workflow_id
        ).filter(
            or_(
                LinkedReusableWorkflow.standard_project_id.in_(project_id_map.keys()),
                LinkedReusableWorkflow.rwx_project_id.in_(project_id_map.keys()),
            )
        ).all()
        reusable_workflow_names: set[str] = {
            _normalize_reusable_workflow_name(workflow.workflow_name)
            for _link, workflow in linked_rows
        }
        prs = db.query(ProjectPullRequest).filter(
            ProjectPullRequest.project_id.in_(project_id_map.keys())
        ).order_by(ProjectPullRequest.created_at.desc()).all()

        for pr in prs:
            pr.pr_state = _resolve_pr_state(pr, refresh_from_github, github_user, token, db)

        if refresh_from_github:
            projects_by_id = {p.project_id: p for p in visible_projects}
            for visible_project_id, visible_project in projects_by_id.items():
                project_prs = [pr for pr in prs if pr.project_id == visible_project_id]
                if not project_prs:
                    continue
                open_count = sum(1 for pr in project_prs if pr.pr_state == "open")
                merged_count = sum(1 for pr in project_prs if pr.pr_state == "merged")
                if open_count == 0:
                    _apply_all_prs_resolved_transitions(
                        db, visible_project, len(project_prs), merged_count
                    )

        grouped: dict[tuple, List[ProjectPullRequest]] = {}
        for pr in prs:
            if pr.campaign_id is not None:
                key = (pr.project_id, "campaign", pr.campaign_id)
            else:
                # Legacy rows created before campaign tracking: best-effort grouping.
                key = _campaign_group_key(pr)
            grouped.setdefault(key, []).append(pr)

        tracked_campaign_ids = {pr.campaign_id for pr in prs if pr.campaign_id is not None}
        campaign_records: dict[int, ProjectPRCampaign] = {}
        if tracked_campaign_ids:
            campaign_records = {
                record.campaign_id: record
                for record in db.query(ProjectPRCampaign).filter(
                    ProjectPRCampaign.campaign_id.in_(tracked_campaign_ids)
                ).all()
            }

        campaigns: List[PRCampaignResponse] = []
        pr_items: List[PRCampaignPRResponse] = []
        open_prs = 0
        merged_prs = 0
        closed_prs = 0

        for key, campaign_prs in grouped.items():
            campaign_prs.sort(key=lambda item: item.created_at or datetime.min)
            campaign_project_id = key[0]
            open_count = sum(1 for pr in campaign_prs if pr.pr_state == "open")
            merged_count = sum(1 for pr in campaign_prs if pr.pr_state == "merged")
            closed_count = sum(1 for pr in campaign_prs if pr.pr_state == "closed")
            total_count = len(campaign_prs)
            status = _campaign_status_from_counts(open_count, merged_count, closed_count)
            completed_prs = [pr for pr in campaign_prs if pr.pr_state in ("merged", "closed")]
            completed_at = None
            if status != "open" and completed_prs:
                completed_at_dt = max(
                    (pr.merged_at or pr.closed_at or pr.updated_at)
                    for pr in completed_prs
                    if pr.merged_at or pr.closed_at or pr.updated_at
                )
                completed_at = completed_at_dt.isoformat() if completed_at_dt else None

            target_branches = sorted({pr.target_branch for pr in campaign_prs if pr.target_branch})
            workflow_names = []
            for pr in campaign_prs:
                for workflow in _split_workflow_names(pr.workflow_names):
                    if workflow not in workflow_names:
                        workflow_names.append(workflow)
            repositories = sorted({pr.repo_name for pr in campaign_prs})
            # For open campaigns, surface the under_review custom files for this project.
            # (Custom files have no stored campaign_id; under_review implies the active campaign.)
            custom_file_paths: List[str] = []
            if status == "open":
                custom_file_paths = [
                    cf.file_path for cf in db.query(CustomFile).filter(
                        CustomFile.project_id == campaign_project_id,
                        CustomFile.file_status == "under_review",
                    ).order_by(CustomFile.file_path).all()
                ]
            campaign_items = [
                _campaign_pr_response(pr, project_id_map, project.project_id, reusable_workflow_names)
                for pr in sorted(campaign_prs, key=lambda item: item.updated_at or item.created_at or datetime.min, reverse=True)
            ]
            pr_items.extend(campaign_items)

            created_at_dt = campaign_prs[0].created_at
            updated_at_dt = max(
                (pr.updated_at or pr.created_at)
                for pr in campaign_prs
                if pr.updated_at or pr.created_at
            )
            campaign_record = (
                campaign_records.get(key[2])
                if len(key) == 3 and key[1] == "campaign"
                else None
            )
            if campaign_record is not None:
                try:
                    record_campaign_status_transition(
                        db, campaign_project_id, project_id_map.get(campaign_project_id, project.project_name),
                        campaign_record, status, open_count, merged_count, closed_count,
                    )
                except Exception as exc:
                    # Never let a notification race (e.g. a concurrent duplicate
                    # dedup_key insert) turn this read endpoint into a 500.
                    print(f"⚠️ Error recording campaign.completed notification: {exc}")
                    db.rollback()
                campaign_id_str = f"campaign-{campaign_record.campaign_id}"
                created_by = campaign_record.created_by or next(
                    (pr.author for pr in campaign_prs if pr.author), github_user
                )
                created_at_dt = campaign_record.created_at or created_at_dt
            elif len(key) == 3 and key[1] == "campaign":
                campaign_id_str = f"campaign-{key[2]}"
                created_by = next((pr.author for pr in campaign_prs if pr.author), github_user)
            else:
                # Legacy rows (created before campaign tracking, campaign_id NULL)
                # are isolated under a distinct "legacy-" id so they can never be
                # confused with — or merged into — tracked campaigns.
                campaign_id_str = "legacy-" + "-".join(
                    str(part).replace("/", "-").replace(",", "-") for part in key
                )
                created_by = next((pr.author for pr in campaign_prs if pr.author), github_user)
            campaigns.append(PRCampaignResponse(
                campaign_id=campaign_id_str,
                campaign_name=_derive_campaign_name(campaign_prs),
                campaign_status=status,
                project_name=project_id_map.get(campaign_project_id, project.project_name),
                project_code=project.project_code if campaign_project_id == project.project_id else None,
                created_by=created_by,
                created_at=created_at_dt.isoformat() if created_at_dt else "",
                updated_at=updated_at_dt.isoformat() if updated_at_dt else "",
                completed_at=completed_at,
                target_branches=target_branches,
                workflow_names=workflow_names,
                custom_file_paths=custom_file_paths,
                repositories=repositories,
                open_count=open_count,
                merged_count=merged_count,
                closed_count=closed_count,
                failed_count=0,
                completion_percentage=round(((merged_count + closed_count) / total_count) * 100) if total_count else 0,
                pull_requests=campaign_items,
            ))

            open_prs += open_count
            merged_prs += merged_count
            closed_prs += closed_count

        campaigns.sort(key=lambda campaign: campaign.updated_at or campaign.created_at, reverse=True)
        pr_items.sort(key=lambda pr: pr.updated_at or pr.created_at, reverse=True)

        # One deferred commit for every campaign.last_known_status update /
        # notification event queued above, instead of one commit per campaign —
        # avoids expire_on_commit re-fetching objects still needed by the
        # response we just built, and keeps this read endpoint resilient to a
        # notification-write failure (falls back to returning what was already
        # computed in memory).
        try:
            db.commit()
        except Exception as exc:
            print(f"⚠️ Error committing campaign notification state: {exc}")
            db.rollback()

        return PRCampaignsResponse(
            campaigns=campaigns,
            pull_requests=pr_items,
            total_campaigns=len(campaigns),
            active_campaigns=sum(1 for campaign in campaigns if campaign.campaign_status == "open"),
            completed_campaigns=sum(1 for campaign in campaigns if campaign.campaign_status != "open"),
            open_prs=open_prs,
            merged_prs=merged_prs,
            closed_prs=closed_prs,
            repositories_affected=len({pr.repo_name for pr in prs}),
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching PR campaigns: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _verify_pr_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify GitHub webhook signature using HMAC SHA-256.

    Args:
        payload: Raw request body bytes
        signature: X-Hub-Signature-256 header value

    Returns:
        bool: True only if the signature is valid. An unset
        GITHUB_PR_WEBHOOK_SECRET rejects every request rather than accepting
        it, so an exposed endpoint with no secret configured is inert.
    """
    if not GITHUB_PR_WEBHOOK_SECRET:
        print("❌ GITHUB_PR_WEBHOOK_SECRET is not set — rejecting webhook to prevent unauthenticated state changes.")
        return False

    if not signature:
        print("❌ No X-Hub-Signature-256 header in PR webhook request")
        return False

    if not signature.startswith("sha256="):
        print(f"❌ Invalid signature format in PR webhook: {signature}")
        return False

    expected = signature[7:]
    mac = hmac.new(
        GITHUB_PR_WEBHOOK_SECRET.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    )
    return hmac.compare_digest(mac.hexdigest(), expected)


def _handle_pr_merged(db: Session, pr_record, pr_number: int, repo_full_name: str) -> dict:
    """Handle a PR that was merged on GitHub."""
    project_id = pr_record.project_id

    pr_record.pr_state = "merged"
    db.commit()
    print(f"✅ Updated PR #{pr_number} state to merged in database")

    # No UI drives this path, so without clearing here the caches keep
    # reporting drift the merge already fixed until someone opens the project.
    merged_project = db.query(Project).filter(Project.project_id == project_id).first()
    if merged_project:
        _clear_drift_for_merged_pr(db, merged_project, pr_record)

    # Only mark project/workflows as synced if ALL remaining PRs are also merged
    remaining_non_merged = db.query(ProjectPullRequest).filter(
        ProjectPullRequest.project_id == project_id,
        ProjectPullRequest.pr_state != "merged",
    ).count()

    if remaining_non_merged == 0:
        _update_project_workflows_status(
            db, project_id, "synced_with_github", only_if_status="under_review"
        )
        _update_project_custom_files_status(db, project_id, "synced_with_github", only_if_status="under_review")
        _update_project_codeowners_status(db, project_id, "synced_with_github", only_if_status="under_review")
        _update_project_pr_state(db, project_id, "synced")
        _sync_linked_reusable_workflows_after_merge(db, project_id)

    # Record a version entry so History shows the merge
    try:
        nr_workflows = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project_id,
            Workflow.reusable_workflow == False,
        ).all()
        for wf in nr_workflows:
            create_workflow_version(
                db,
                wf.workflow_id,
                wf.workflow_yaml,
                metadata={
                    "action": "pr_merged",
                    "pr_number": pr_number,
                    "repo_name": repo_full_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                commit=False,
            )
        db.commit()
        print(f"✅ Created pr_merged version entries for {len(nr_workflows)} workflow(s)")
    except Exception as e:
        print(f"❌ Error creating pr_merged version entries: {str(e)}")
        db.rollback()

    return {"status": "processed", "action": "merged", "pr_number": pr_number, "repo_name": repo_full_name}


def _handle_pr_closed_without_merge(db: Session, pr_record, pr_number: int, repo_full_name: str) -> dict:
    """Handle a PR that was closed without merging on GitHub."""
    project_id = pr_record.project_id

    pr_record.pr_state = "closed"
    db.commit()
    print(f"✅ Updated PR #{pr_number} state to closed in database")

    # Revert workflows if no open PRs remain
    open_prs = db.query(ProjectPullRequest).filter_by(
        project_id=project_id,
        pr_state="open",
    ).count()

    if open_prs == 0:
        _update_project_workflows_status(
            db, project_id, "committed_locally", only_if_status="under_review"
        )
        _update_project_custom_files_status(db, project_id, "committed_locally", only_if_status="under_review")
        _update_project_codeowners_status(db, project_id, "committed_locally", only_if_status="under_review")
        _update_project_pr_state(db, project_id, "draft")

    return {"status": "processed", "action": "closed", "pr_number": pr_number, "repo_name": repo_full_name}


WEBHOOK_DOCS_URL = "https://actionsmanager.io/guides/WEBHOOK_ENDPOINT.html"


def _describe_webhook_reachability(app_url: str) -> Optional[str]:
    """Why GitHub probably cannot reach ``app_url``, or None if it looks fine.

    Deliberately a heuristic on the configured URL rather than a probe: we
    cannot ask GitHub to try, and an outbound self-request would succeed from
    inside the network even when the instance is unreachable from outside —
    which is exactly the case this is meant to catch.
    """
    parsed = urlsplit(app_url)
    hostname = (parsed.hostname or "").strip("[]")

    if not hostname:
        return "No APP_URL is configured, so there is no address to give GitHub."

    if _host_is_loopback(hostname):
        return (
            f"APP_URL is {app_url}, which only resolves on the machine running "
            f"ActionsManager. GitHub cannot deliver to it."
        )

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # A hostname — could well be public; DNS resolution here would only
        # tell us what *this* network sees, so treat it as plausible.
        return None

    if ip.is_private or ip.is_link_local or ip.is_reserved:
        return (
            f"APP_URL is {app_url}, a private address. It is reachable on your "
            f"network but not from GitHub."
        )
    return None


def get_webhook_readiness() -> dict:
    """Whether this instance can receive GitHub webhooks, and what is missing.

    Webhooks are optional — delivery and drift detection call out to GitHub and
    need no inbound access — so this reports status rather than failing
    anything. It exists so the UI can explain *why* an event-driven feature is
    unavailable and link to the setup guide, instead of appearing broken.
    """
    app_url = resolve_app_url()
    unreachable_reason = _describe_webhook_reachability(app_url)
    secret_configured = bool(GITHUB_PR_WEBHOOK_SECRET)

    blockers = []
    if unreachable_reason:
        blockers.append(unreachable_reason)
    if not secret_configured:
        blockers.append(
            "GITHUB_PR_WEBHOOK_SECRET is not set. Until it is, every inbound "
            "webhook is rejected — nothing is exposed, the feature is simply off."
        )

    return {
        "ready": not blockers,
        "public_url_configured": unreachable_reason is None,
        "secret_configured": secret_configured,
        "app_url": app_url,
        "webhook_url": f"{app_url}/webhooks/github" if not unreachable_reason else None,
        "blockers": blockers,
        "docs_url": WEBHOOK_DOCS_URL,
    }


@router.get("/api/webhooks/readiness")
def webhook_readiness():
    """Report whether GitHub can deliver webhooks to this instance.

    Unauthenticated on purpose: it returns only this instance's own
    configuration shape — never the secret itself — and the UI needs it to
    explain an unavailable feature before a user has done anything.
    """
    return get_webhook_readiness()


@router.post("/webhooks/github", responses=_responses(400, 401))
async def github_pr_webhook(request: Request, db: Annotated[Session, Depends(get_db)]):
    """
    Handle GitHub pull_request webhook events.

    When a PR that was created by Actions Manager is closed on GitHub directly:
    - If merged: workflow status → synced_with_github, project state → synced
    - If closed without merge: workflow status → committed_locally, project state → draft

    Configure GitHub to send pull_request events to this endpoint.
    Set GITHUB_PR_WEBHOOK_SECRET to the same secret configured in GitHub for signature verification.
    """
    event_type = request.headers.get("X-GitHub-Event")

    # Only process pull_request events
    if event_type != "pull_request":
        return {"status": "ignored", "reason": f"Event type '{event_type}' not handled"}

    body = await request.body()

    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_pr_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")

    action = payload.get("action")

    # We only care about PRs being closed (merged or not)
    if action != "closed":
        return {"status": "ignored", "reason": f"Action '{action}' not handled"}

    pr_data = payload.get("pull_request", {})
    pr_number = pr_data.get("number")
    merged = pr_data.get("merged", False) or bool(pr_data.get("merged_at"))
    repo_full_name = payload.get("repository", {}).get("full_name")

    if not pr_number or not repo_full_name:
        raise HTTPException(status_code=400, detail="Missing pr number or repository in payload")

    print(f"📥 GitHub PR webhook: PR #{pr_number} in {repo_full_name} closed (merged={merged})")

    # Find the PR record in the database
    pr_record = db.query(ProjectPullRequest).filter_by(
        repo_name=repo_full_name,
        pr_number=pr_number,
    ).first()

    if not pr_record:
        print(f"ℹ️ PR #{pr_number} in {repo_full_name} not tracked by Actions Manager, ignoring")
        return {"status": "ignored", "reason": "PR not tracked by Actions Manager"}

    if merged:
        return _handle_pr_merged(db, pr_record, pr_number, repo_full_name)

    return _handle_pr_closed_without_merge(db, pr_record, pr_number, repo_full_name)


def _fetch_branches_page(branches_url: str, headers: dict, params: dict,
                          owner: str, repo: str, page: int,
                          user: str = None, db: Session = None):
    """Fetch a single page of the branches listing. Returns None on API failure."""
    try:
        if user and db:
            return github_get(branches_url, user, db, headers=headers, params=params)
        return requests.get(branches_url, headers=headers, params=params, timeout=GITHUB_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        print(f"⚠️ Failed to fetch branches for {owner}/{repo} (page {page}): {e}")
        return None


def _collect_head_shas(payload: list, head_shas: dict) -> None:
    # The listing already carries each branch's head commit. Capturing
    # it here is free and lets the recency cache invalidate exactly:
    # if the head has not moved, the branch has not moved.
    for b in payload:
        head_shas[b["name"]] = (b.get("commit") or {}).get("sha")


# Reserved cache key for a repo's branch *listing*, as opposed to one branch.
# '*' is not a legal character in a git ref name, so it can never collide with
# a real branch stored in the same table.
BRANCH_LIST_CACHE_KEY = "*"

# ponytail: not a branch-count limit — real repos exit on page 1. This only
# bounds an upstream that ignores `page` and returns the same page forever,
# which would otherwise consume all host memory.
MAX_BRANCH_PAGES = 50


def _cached_branch_listing(db: Session, repo_name: str, owner: str, repo: str,
                           headers: dict, head_shas: Optional[dict]) -> Optional[List[str]]:
    """Branch listing for a repo, conditional on a stored ETag.

    This was the last chargeable call in a warm drift check: the per-branch
    Trees reads answer 304 and the recency answers are cached, but the listing
    itself was fetched in full every time. It supports ETags (verified against
    the live API), so an unchanged repo now costs nothing at all.

    Returns None when the caller should fall back to the normal paginated
    fetch — no cache available, a multi-page repo, or any failure.
    """
    if db is None or not repo_name:
        return None

    row = _get_tree_cache_row(db, repo_name, BRANCH_LIST_CACHE_KEY)
    request_headers = dict(headers)
    if row and row.etag:
        request_headers["If-None-Match"] = row.etag

    try:
        response = requests.get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/branches",
            headers=request_headers, params={"per_page": 100, "page": 1},
            timeout=GITHUB_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None

    if response.status_code == 304 and row and row.sha_map_json:
        cached = json.loads(row.sha_map_json)
        if head_shas is not None:
            head_shas.update(cached)
        print(f"🟢 {repo_name} branch listing unchanged (304, no rate-limit cost)")
        return list(cached.keys())

    if response.status_code != 200:
        return None

    payload = response.json()
    if len(payload) >= 100:
        # Paginated: the stored ETag only covers page 1, so caching it would
        # replay an incomplete list. Rare enough to just not cache.
        return None

    listing = {b["name"]: (b.get("commit") or {}).get("sha") for b in payload}
    if head_shas is not None:
        head_shas.update(listing)
    _store_tree_cache(db, repo_name, BRANCH_LIST_CACHE_KEY, listing, response.headers.get("ETag"))
    return list(listing.keys())


def _fetch_all_branches(owner: str, repo: str, headers: dict,
                        user: str = None, db: Session = None,
                        head_shas: Optional[dict] = None,
                        repo_name: str = None) -> Optional[List[str]]:
    """Fetch all branch names for a repository using pagination. Returns None on API failure.

    Pass a dict as ``head_shas`` to also collect {branch: head_commit_sha} from
    the same response — the return type stays a plain name list so existing
    callers and their mocks are unaffected.

    Pass ``repo_name`` to allow a conditional request against a stored ETag,
    which the drift path does; delivery leaves it unset and always fetches.
    """
    if repo_name:
        cached = _cached_branch_listing(db, repo_name, owner, repo, headers, head_shas)
        if cached is not None:
            return cached

    branches_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/branches"
    all_branches: List[str] = []
    page = 1

    while page <= MAX_BRANCH_PAGES:
        params = {"per_page": 100, "page": page}
        response = _fetch_branches_page(branches_url, headers, params, owner, repo, page, user, db)
        if response is None or response.status_code != 200:
            return None

        payload = response.json()
        page_branches = [b["name"] for b in payload]
        if head_shas is not None:
            _collect_head_shas(payload, head_shas)
        all_branches.extend(page_branches)
        if len(page_branches) < 100:
            break
        page += 1
    else:
        print(f"⚠️ {owner}/{repo} branch listing hit the {MAX_BRANCH_PAGES}-page cap; "
              f"using the first {len(all_branches)} branches")

    return all_branches


def _match_branches_by_pattern(all_branches: List[str], regex_pattern: str) -> List[str]:
    """Match branches using a regex pattern, falling back to exact match on invalid regex."""
    try:
        pattern = re.compile(regex_pattern)
        return [b for b in all_branches if pattern.match(b)]
    except re.error as e:
        print(f"⚠️ Invalid regex pattern '{regex_pattern}', falling back to exact branch name match: {str(e)}")
        return [regex_pattern] if regex_pattern in all_branches else []


def _is_branch_recent(owner: str, repo: str, branch_name: str, cutoff_date: datetime,
                      headers: dict, user: str = None, db: Session = None) -> bool:
    """Return True if the branch has had a commit on or after cutoff_date."""
    commits_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits"
    params = {"sha": branch_name, "per_page": 1}
    try:
        if user and db:
            response = github_get(commits_url, user, db, headers=headers, params=params)
        else:
            response = requests.get(commits_url, headers=headers, params=params, timeout=GITHUB_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        print(f"⚠️ Failed to fetch commits for branch '{branch_name}' in {owner}/{repo}: {e}")
        return False

    if response.status_code != 200:
        return False
    commits = response.json()
    if not commits:
        return False

    commit_date = datetime.fromisoformat(commits[0]["commit"]["committer"]["date"].replace('Z', '+00:00'))
    if commit_date >= cutoff_date:
        print(f"✅ Branch '{branch_name}' included (last commit: {commit_date.strftime('%Y-%m-%d')})")
        return True
    print(f"⏭️ Branch '{branch_name}' excluded - stale (last commit: {commit_date.strftime('%Y-%m-%d')}, cutoff: {cutoff_date.strftime('%Y-%m-%d')})")
    return False


def _cached_branch_recency(db: Session, repo_name: str, branch: str, head_sha: Optional[str]):
    """The stored "is this branch recent" answer, if it still applies.

    Only reusable while the branch head is unchanged — then the answer provably
    cannot have changed, so this never wrongly skips a branch that just became
    active (which a time-based cache would).
    """
    if db is None or not repo_name or not head_sha:
        return None
    row = _get_tree_cache_row(db, repo_name, branch)
    if row is None or row.branch_is_recent is None:
        return None
    if row.branch_head_sha != head_sha:
        return None
    return row.branch_is_recent


def _store_branch_recency(db: Session, repo_name: str, branch: str,
                          head_sha: Optional[str], is_recent: bool) -> None:
    if db is None or not repo_name or not head_sha:
        return
    repo = db.query(Repo).filter(Repo.repo_name == repo_name).first()
    if repo is None:
        return
    row = _get_tree_cache_row(db, repo_name, branch)
    if row is None:
        row = WorkflowTreeCache(repo_id=repo.repo_id, branch=branch)
        db.add(row)
    row.branch_is_recent = is_recent
    row.branch_head_sha = head_sha
    db.commit()


def _filter_branches_by_recency(owner: str, repo: str, matched_branches: List[str],
                                branch_max_age_days: int, headers: dict,
                                user: str = None, db: Session = None,
                                repo_name: str = None, head_shas: Optional[dict] = None) -> List[str]:
    """Filter branches to those with a recent commit; returns matched_branches unchanged when no age limit.

    ``repo_name``/``head_shas`` enable the recency cache, which the drift path
    uses: this otherwise costs one API call per matched branch on every check.
    Delivery leaves them unset and always asks GitHub, since it decides where
    we actually write.
    """
    if not branch_max_age_days or branch_max_age_days <= 0:
        return matched_branches

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=branch_max_age_days)
    head_shas = head_shas or {}
    recent = []
    for b in matched_branches:
        head_sha = head_shas.get(b)
        cached = _cached_branch_recency(db, repo_name, b, head_sha)
        if cached is not None:
            if cached:
                recent.append(b)
            continue
        is_recent = _is_branch_recent(owner, repo, b, cutoff_date, headers, user, db)
        _store_branch_recency(db, repo_name, b, head_sha, is_recent)
        if is_recent:
            recent.append(b)
    if not recent:
        print(f"⚠️ No branches with commits in last {branch_max_age_days} days, falling back to default branch")
    return recent


def resolve_branch_config_for_repo(db: Session, project: "Project", repo_name: str,
                                   assoc: "ProjectRepo" = None) -> dict:
    """Resolve the effective branch configuration for ``repo_name`` in ``project``.

    Resolution order:
      1. Repository override (when ``project_repos.branch_config_mode == 'override'``)
      2. Project branch configuration
      3. Hard-coded safe defaults (``"default"``, no pattern, 30 days)

    The repository's GitHub default branch is the ultimate fallback used by
    the lower-level ``_resolve_branches_for_repo`` helper when no pattern
    matches; this resolver only decides which option/pattern/max-age to feed
    into that helper for a given (project, repo) pair.

    Pass an already-loaded ``ProjectRepo`` row as ``assoc`` to skip the
    redundant association lookup (useful when iterating over a project's
    repos).

    Returns a dict with:
        ``branch_option``       – ``"default"`` or ``"pattern"``
        ``branch_regex``        – pattern string (may be empty)
        ``branch_max_age_days`` – integer
        ``using_project_default`` – bool, True when no override is in effect
        ``branch_config_mode``  – ``"inherit"`` or ``"override"`` (raw row value)
    """
    proj_option = project.branch_option or "default"
    proj_regex = project.branch_regex or ""
    proj_max_age = project.branch_max_age_days or 30

    # Migrate legacy values inline so callers always see the current set.
    if proj_option == "all":
        proj_option = "default"
    elif proj_option == "regex":
        proj_option = "pattern"

    if assoc is None:
        repo = db.query(Repo).filter(Repo.repo_name == repo_name.strip()).first()
        if repo is None:
            return {
                "branch_option": proj_option,
                "branch_regex": proj_regex,
                "branch_max_age_days": proj_max_age,
                "using_project_default": True,
                "branch_config_mode": "inherit",
            }
        assoc = (
            db.query(ProjectRepo)
            .filter(
                ProjectRepo.project_id == project.project_id,
                ProjectRepo.repo_id == repo.repo_id,
            )
            .first()
        )

    mode = (getattr(assoc, "branch_config_mode", None) or "inherit") if assoc else "inherit"
    if assoc is None or mode != "override":
        return {
            "branch_option": proj_option,
            "branch_regex": proj_regex,
            "branch_max_age_days": proj_max_age,
            "using_project_default": True,
            "branch_config_mode": mode,
        }

    repo_option = assoc.branch_option or proj_option
    if repo_option == "all":
        repo_option = "default"
    elif repo_option == "regex":
        repo_option = "pattern"

    return {
        "branch_option": repo_option,
        "branch_regex": (assoc.branch_regex if assoc.branch_regex is not None else proj_regex) or "",
        "branch_max_age_days": assoc.branch_max_age_days if assoc.branch_max_age_days is not None else proj_max_age,
        "using_project_default": False,
        "branch_config_mode": "override",
    }


def _resolve_branches_for_repo(owner: str, repo: str, branch_option: str,
                               regex_pattern: str, branch_max_age_days: int,
                               headers: dict, user: str = None, db: Session = None,
                               recency_cache_repo: str = None) -> List[str]:
    """
    Resolve which branches to update based on the branch option.

    Args:
        owner: Repository owner
        repo: Repository name
        branch_option: "default" or "pattern"
        regex_pattern: Regex pattern or exact branch name (used when branch_option is "pattern")
        branch_max_age_days: Filter branches by recency (1-30 days)
        headers: GitHub API headers
        user: GitHub username (optional, for API tracking)
        db: Database session (optional, for API tracking)
        recency_cache_repo: "owner/name" to enable the branch-recency cache.
            Drift passes it (the per-branch commit lookup is its dominant cost);
            delivery leaves it unset and always asks GitHub, since it decides
            where we actually write.

    Returns:
        List[str]: List of branch names to update
    """
    if branch_option != "pattern" or not regex_pattern:
        return [get_default_branch(owner, repo, headers, user, db)]

    head_shas: dict = {}
    all_branches = _fetch_all_branches(
        owner, repo, headers, user, db, head_shas=head_shas, repo_name=recency_cache_repo,
    )
    if all_branches is None:
        return [get_default_branch(owner, repo, headers, user, db)]

    matched_branches = _match_branches_by_pattern(all_branches, regex_pattern)
    if not matched_branches:
        return [get_default_branch(owner, repo, headers, user, db)]

    recent_branches = _filter_branches_by_recency(
        owner, repo, matched_branches, branch_max_age_days, headers, user, db,
        repo_name=recency_cache_repo, head_shas=head_shas,
    )
    if not recent_branches:
        return [get_default_branch(owner, repo, headers, user, db)]

    return recent_branches


def _ensure_workflows_directory_exists(owner: str, repo: str, branch: str, 
                                     headers: dict, user: str = None, db: Session = None) -> bool:
    """
    Ensure the .github/workflows directory exists in the repository.
    If it doesn't exist, create it by adding a .gitkeep file.
    
    Returns:
        bool: True if directory exists or was created successfully, False otherwise
    """
    # First, check if the directory already exists by checking for any file in it
    dir_check_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/.github/workflows?ref={branch}"
    
    if user and db:
        check_response = github_get(dir_check_url, user, db, headers=headers)
    else:
        check_response = requests.get(dir_check_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    
    # If directory exists (200) or is empty (200 with empty array), we're good
    if check_response.status_code == 200:
        print(f"✅ .github/workflows directory already exists in {owner}/{repo} on {branch}")
        return True
    
    # If we get 404, the directory doesn't exist, so create it
    if check_response.status_code == 404:
        print(f"📁 Creating .github/workflows directory in {owner}/{repo} on {branch}")
        
        # Create the directory by creating a .gitkeep file in it
        gitkeep_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/.github/workflows/.gitkeep"
        gitkeep_content = base64.b64encode(b"").decode()  # Empty file
        
        payload = {
            "message": f"Create .github/workflows directory [skip ci]",
            "content": gitkeep_content,
            "branch": branch
        }
        
        if user and db:
            create_response = github_put(gitkeep_url, user, db, json=payload, headers=headers)
        else:
            create_response = requests.put(gitkeep_url, json=payload, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
        
        if create_response.status_code in [200, 201]:
            print(f"✅ Successfully created .github/workflows directory in {owner}/{repo} on {branch}")
            return True
        else:
            print(f"❌ Failed to create .github/workflows directory: {create_response.status_code}")
            print(f"   Response: {create_response.text[:500]}")
            return False
    
    # Unexpected status code
    print(f"⚠️ Unexpected response when checking for .github/workflows: {check_response.status_code}")
    return False


def _check_existing_workflow_content(file_url: str, encoded_content: str, headers: dict, user: str = None, db: Session = None) -> tuple:
    """
    Check if existing workflow content matches the new content.
    
    Returns:
        tuple: (sha_or_none, content_unchanged_boolean)
    """
    if user and db:
        response = github_get(file_url, user, db, headers=headers)
    else:
        response = requests.get(file_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    
    if response.status_code == 200:
        github_data = response.json()
        sha = github_data.get("sha")
        existing_content = github_data.get("content", "")
        
        # Compare the content - if it's the same, skip the update
        # GitHub returns base64 wrapped at 60 chars with a trailing newline,
        # while b64encode produces one unwrapped line — comparing them verbatim
        # was never equal for a file over ~45 bytes, so "unchanged" never fired.
        content_unchanged = (
            "".join(existing_content.split()) == "".join(encoded_content.split())
        )
        return sha, content_unchanged
    
    return None, False  # File doesn't exist, will be created


def _get_authenticated_headers(user: str, headers: dict) -> Optional[dict]:
    """
    Get headers with authentication token for the user.
    
    Args:
        user: GitHub username
        headers: Base headers to copy
    
    Returns:
        dict with authentication or None if user not authenticated
    """
    from auth import user_tokens
    token = user_tokens.get(user)
    if not token:
        return None
    
    headers_with_auth = headers.copy()
    headers_with_auth["Authorization"] = f"token {token}"
    return headers_with_auth


def _get_reusable_workflow_repo(project: Optional["Project"], user: str, db: Optional[Session]) -> str:
    """
    Determine the target repository for reusable workflows.

    For RWX projects the repo is the project's own selected repository (stored
    via the ``ProjectRepo`` association).  When multiple repos are associated,
    the first one is used — RWX projects are expected to have exactly one repo.

    For standard projects with linked reusable workflows the repo is determined
    from the source RWX project's first repository.

    Falls back to ``{user}/am-reuseable-workflow`` only when no repository can
    be determined from the database, preserving backward compatibility.
    """
    if project and db:
        if project.project_type == "rwx":
            project_repos = db.query(Repo).join(ProjectRepo).filter(
                ProjectRepo.project_id == project.project_id
            ).all()
            if project_repos:
                # RWX projects are expected to have one repo; use the first.
                return project_repos[0].repo_name

        # Standard project — look up the linked RWX project's repo
        linked = db.query(LinkedReusableWorkflow).filter(
            LinkedReusableWorkflow.standard_project_id == project.project_id
        ).first()
        if linked:
            rwx_repos = db.query(Repo).join(ProjectRepo).filter(
                ProjectRepo.project_id == linked.rwx_project_id
            ).all()
            if rwx_repos:
                # Use the first repo from the linked RWX project.
                return rwx_repos[0].repo_name

    # Fallback for backward compatibility
    return f"{user}/am-reuseable-workflow"


def _ensure_reusable_repo_exists(owner: str, repo: str, auth_headers: dict,
                                 user: str = None, db: Session = None) -> tuple:
    """
    Check whether a GitHub repository exists and create it if it does not.

    For org-owned repositories the org creation endpoint is used when the
    authenticated user's account type is ``Organization``.  For personal
    accounts (or when the account type cannot be determined) the user endpoint
    ``POST /user/repos`` is used.

    Auto-creation is only attempted when the *owner* matches the authenticated
    *user*.  If the owner is different (e.g. someone else's account) and the
    repo does not exist, a clear error is returned instead of silently creating
    a repo under the wrong account.

    Returns:
        tuple: (True, None) on success, or (False, error_msg) on failure
    """
    repo_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}"
    check_response = requests.get(repo_url, headers=auth_headers, timeout=GITHUB_TIMEOUT_SECONDS)

    if check_response.status_code == 200:
        print(f"✅ Repository '{owner}/{repo}' already exists")
        return True, None

    if check_response.status_code != 404:
        error_msg = f"Failed to check repository '{owner}/{repo}': {check_response.status_code} - {check_response.text[:500]}"
        print(f"❌ {error_msg}")
        return False, error_msg

    # Safety check: only auto-create when the owner matches the authenticated
    # user so we don't accidentally create a repo under the wrong account.
    if user and owner != user:
        error_msg = (
            f"Repository '{owner}/{repo}' does not exist and cannot be auto-created "
            f"because the owner '{owner}' differs from the authenticated user '{user}'"
        )
        print(f"❌ {error_msg}")
        return False, error_msg

    # Repository does not exist — create it.
    # Determine the correct endpoint (user vs org) via get_github_api_endpoints.
    print(f"🔧 Repository '{owner}/{repo}' not found, creating it...")
    endpoints = (get_github_api_endpoints(owner, db) or {}) if db else {}
    create_url = endpoints.get("repos_create", f"{GITHUB_API_URL}/user/repos")
    create_payload = {
        "name": repo,
        "description": "Actions Manager Reusable Workflows repository",
        "private": True,
        "auto_init": False,  # branches are initialized later via the Contents API
    }
    create_response = requests.post(create_url, json=create_payload, headers=auth_headers, timeout=GITHUB_TIMEOUT_SECONDS)

    if create_response.status_code == 201:
        print(f"✅ Created repository '{owner}/{repo}'")
        return True, None

    error_msg = f"Failed to create repository '{owner}/{repo}': {create_response.status_code} - {create_response.text[:500]}"
    print(f"❌ {error_msg}")
    return False, error_msg


def _initialize_am_branch_in_empty_repo(owner: str, repo: str, am_branch_name: str,
                                        target_branch: str, project_code: str, headers: dict,
                                        user: str = None, db: Session = None) -> tuple:
    """
    Initialize an empty (no commits) repository by creating an initial commit
    via the Contents API, then creating the AM branch.

    The Contents API (PUT /repos/{owner}/{repo}/contents/{path}) is used instead
    of the Git Data API (blobs/trees/commits) because the latter returns
    ``409 Git Repository is empty`` on repositories that have zero commits.
    The Contents API handles this correctly and creates the default branch
    automatically.

    Also ensures the target branch exists so that a pull request from the AM
    branch to the target branch can be opened afterwards.

    If the repository does not exist at all it is created first via the
    GitHub Repos API.

    Returns:
        tuple: (am_branch_name, created_bool, error_or_none)
            - On success: (am_branch_name, True, None) when the AM branch was newly created.
            - On success: (am_branch_name, False, None) when the AM branch already existed (422).
            - On failure: (None, False, error_msg).
    """
    auth_headers = _get_authenticated_headers(user, headers) if (user and db) else headers
    if user and db and not auth_headers:
        return None, False, f"User {user} not authenticated"

    print(f"🔧 Initializing empty repo '{owner}/{repo}' with AM branch '{am_branch_name}'")

    # Step 0: Ensure the repository exists — create it if it doesn't
    repo_ok, repo_error = _ensure_reusable_repo_exists(owner, repo, auth_headers, user=user, db=db)
    if not repo_ok:
        return None, False, repo_error

    # Step 1: Create an initial file via the Contents API.
    # This works on completely empty repos (unlike the Git Data API) and
    # automatically creates the default branch with the first commit.
    readme_content = "# Actions Manager Reusable Workflows\n\nThis repository is managed by Actions Manager.\n"
    contents_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/README.md"
    contents_payload = {
        "message": f"Initialize repository for Actions Manager (project: {project_code})",
        "content": base64.b64encode(readme_content.encode()).decode(),
    }
    contents_response = requests.put(contents_url, json=contents_payload, headers=auth_headers, timeout=GITHUB_TIMEOUT_SECONDS)

    if contents_response.status_code in (200, 201):
        commit_sha = contents_response.json()["commit"]["sha"]
        print(f"✅ Created initial commit in '{owner}/{repo}' via Contents API (SHA: {commit_sha[:8]})")
    elif contents_response.status_code in (409, 422):
        # File already exists (e.g. repo was previously initialized) — fetch
        # the target branch SHA instead.
        print(f"⚠️ README.md already exists in '{owner}/{repo}', fetching target branch SHA...")
        ref_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs/heads/{target_branch}"
        ref_response = requests.get(ref_url, headers=auth_headers, timeout=GITHUB_TIMEOUT_SECONDS)
        if ref_response.status_code == 200:
            commit_sha = ref_response.json()["object"]["sha"]
            print(f"✅ Got target branch '{target_branch}' SHA: {commit_sha[:8]}")
        else:
            error_msg = (
                f"Failed to initialize repo: README.md already exists but target branch "
                f"'{target_branch}' not found ({ref_response.status_code})"
            )
            print(f"❌ {error_msg}")
            return None, False, error_msg
    else:
        error_msg = f"Failed to initialize repo (contents): {contents_response.status_code} - {contents_response.text[:500]}"
        print(f"❌ {error_msg}")
        return None, False, error_msg

    # Step 2: Ensure the target branch exists.
    # The Contents API creates the repo's *default* branch which is usually the
    # target branch, but we create it explicitly in case they differ.
    ref_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs"
    target_ref_payload = {
        "ref": f"refs/heads/{target_branch}",
        "sha": commit_sha,
    }
    target_ref_response = requests.post(ref_url, json=target_ref_payload, headers=auth_headers, timeout=GITHUB_TIMEOUT_SECONDS)
    if target_ref_response.status_code == 201:
        print(f"✅ Created target branch '{target_branch}' in '{owner}/{repo}'")
    elif target_ref_response.status_code == 422:
        print(f"⚠️ Target branch '{target_branch}' already exists in '{owner}/{repo}'")
    else:
        error_msg = f"Failed to create target branch '{target_branch}': {target_ref_response.status_code} - {target_ref_response.text[:200]}"
        print(f"❌ {error_msg}")
        return None, False, error_msg

    # Step 3: Create the AM branch ref pointing to the same commit
    am_ref_payload = {
        "ref": f"refs/heads/{am_branch_name}",
        "sha": commit_sha,
    }
    am_ref_response = requests.post(ref_url, json=am_ref_payload, headers=auth_headers, timeout=GITHUB_TIMEOUT_SECONDS)
    if am_ref_response.status_code == 201:
        print(f"✅ Initialized empty repo '{owner}/{repo}' with AM branch '{am_branch_name}'")
        return am_branch_name, True, None
    elif am_ref_response.status_code == 422:
        print(f"⚠️ AM branch '{am_branch_name}' already exists during initialization")
        return am_branch_name, False, None
    else:
        error_msg = f"Failed to initialize repo (AM ref): {am_ref_response.status_code} - {am_ref_response.text[:200]}"
        print(f"❌ {error_msg}")
        return None, False, error_msg


def _create_or_get_am_branch(owner: str, repo: str, target_branch: str, 
                            project_code: str, headers: dict, 
                            user: str = None, db: Session = None) -> tuple:
    """
    Create a new unique Actions Manager dedicated branch for a project.
    Branch name format: actions-manager/<project_code>/<repo_slug>/<short_id>-<target_branch>

    A new branch is always created — branches are never reused — to prevent
    stale-branch merge conflicts and confusing PR behaviour across repositories.

    Args:
        owner: Repository owner
        repo: Repository name
        target_branch: Target branch to base the dedicated branch on
        project_code: Project code for naming
        headers: GitHub API headers
        user: GitHub username for authenticated API calls
        db: Database session for authenticated API calls
    
    Returns:
        tuple: (am_branch_name, created_or_existed_boolean, error_message_or_none)
    """
    # Sanitize components for use in a Git branch name
    sanitized_branch = re.sub(r'[^a-zA-Z0-9._-]', '-', target_branch)
    sanitized_repo = re.sub(r'[^a-zA-Z0-9._-]', '-', repo)
    short_id = uuid.uuid4().hex[:8]
    am_branch_name = (
        f"actions-manager/{project_code.lower()}"
        f"/{sanitized_repo}/{short_id}-{sanitized_branch}"
    )

    # Branch doesn't exist yet (always unique), create it based on the target branch
    # Get the target branch's HEAD SHA
    target_ref_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/ref/heads/{target_branch}"
    
    if user and db:
        target_response = github_get(target_ref_url, user, db, headers=headers)
    else:
        target_response = requests.get(target_ref_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    
    if target_response.status_code != 200:
        if target_response.status_code == 409:
            # 409 = "Git Repository is empty" — no commits at all.
            # Definitely needs to be bootstrapped with an initial commit.
            print(f"⚠️ Repository '{owner}/{repo}' is empty (409), bootstrapping with initial commit...")
            return _initialize_am_branch_in_empty_repo(
                owner, repo, am_branch_name, target_branch, project_code, headers, user, db
            )
        elif target_response.status_code == 404:
            # 404 can mean (a) the repo is empty with no commits, or (b) the
            # repo has commits but the specific target branch doesn't exist.
            # Disambiguate by checking if the repo has any commits.
            commits_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits?per_page=1"
            if user and db:
                commits_response = github_get(commits_url, user, db, headers=headers)
            else:
                commits_response = requests.get(commits_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)

            if commits_response.status_code == 200:
                try:
                    commits_data = commits_response.json()
                except (ValueError, Exception):
                    commits_data = []
                if commits_data:
                    # Repo is non-empty but the target branch simply doesn't exist —
                    # return an error instead of mutating the repo.
                    error_msg = (
                        f"Target branch '{target_branch}' does not exist in non-empty "
                        f"repository '{owner}/{repo}'. Please create the branch first."
                    )
                    print(f"❌ {error_msg}")
                    return None, False, error_msg
            
            # Repo is empty (no commits) or commits endpoint returned non-200 — bootstrap it.
            print(f"⚠️ Repository '{owner}/{repo}' has no commits, bootstrapping with initial commit...")
            return _initialize_am_branch_in_empty_repo(
                owner, repo, am_branch_name, target_branch, project_code, headers, user, db
            )
        else:
            error_msg = f"Failed to get target branch '{target_branch}': {target_response.status_code}"
            print(f"❌ {error_msg}")
            return None, False, error_msg
    
    target_sha = target_response.json()["object"]["sha"]
    print(f"📌 Target branch '{target_branch}' HEAD SHA: {target_sha}")
    
    # Create the new Actions Manager branch
    am_branch_ref = f"heads/{am_branch_name}"
    create_ref_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs"
    create_payload = {
        "ref": f"refs/{am_branch_ref}",
        "sha": target_sha
    }
    
    if user and db:
        # Use requests.post directly since github_put is for PUT requests
        headers_with_auth = _get_authenticated_headers(user, headers)
        if not headers_with_auth:
            return None, False, f"User {user} not authenticated"
        create_response = requests.post(create_ref_url, json=create_payload, headers=headers_with_auth, timeout=GITHUB_TIMEOUT_SECONDS)
    else:
        create_response = requests.post(create_ref_url, json=create_payload, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    
    if create_response.status_code == 201:
        print(f"✅ Created Actions Manager branch '{am_branch_name}' in {owner}/{repo}")
        return am_branch_name, True, None
    elif create_response.status_code == 422:
        # 422 can mean "Reference already exists" (rare race condition with unique names)
        # but also covers invalid ref names, permission errors, etc.
        # Only treat it as success when GitHub explicitly says the ref already exists.
        try:
            error_body = create_response.json()
        except Exception:
            error_body = {}
        gh_message = error_body.get("message", "")
        if "already exists" in gh_message.lower():
            print(f"⚠️ Branch '{am_branch_name}' already exists (422) — treating as success")
            return am_branch_name, False, None
        error_msg = f"Failed to create branch (422): {gh_message or create_response.text[:200]}"
        print(f"❌ {error_msg}")
        return None, False, error_msg
    else:
        error_msg = f"Failed to create branch: {create_response.status_code} - {create_response.text[:200]}"
        print(f"❌ {error_msg}")
        return None, False, error_msg


def _check_existing_pr(owner: str, repo: str, am_branch: str, 
                      target_branch: str, headers: dict,
                      user: str = None, db: Session = None) -> Optional[dict]:
    """
    Check if an open PR already exists from the Actions Manager branch to the target branch.
    
    Args:
        owner: Repository owner
        repo: Repository name
        am_branch: Actions Manager dedicated branch name
        target_branch: Target branch name
        headers: GitHub API headers
        user: GitHub username for authenticated API calls
        db: Database session for authenticated API calls
    
    Returns:
        dict or None: PR data if exists, None otherwise
    """
    # GitHub API requires head in format "owner:branch" or just "branch" for same repo
    head_param = f"{owner}:{am_branch}"
    pulls_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls"
    params = {
        "head": head_param,
        "base": target_branch,
        "state": "open"
    }
    
    if user and db:
        # Manually construct URL with params since github_get doesn't support params parameter
        url_with_params = f"{pulls_url}?head={head_param}&base={target_branch}&state=open"
        response = github_get(url_with_params, user, db, headers=headers)
    else:
        response = requests.get(pulls_url, params=params, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    
    if response.status_code == 200:
        prs = response.json()
        if prs and len(prs) > 0:
            print(f"✅ Found existing PR #{prs[0]['number']} from '{am_branch}' to '{target_branch}'")
            return prs[0]
    
    print(f"📌 No existing PR found from '{am_branch}' to '{target_branch}'")
    return None


def _create_pull_request(owner: str, repo: str, am_branch: str, 
                        target_branch: str, project_code: str,
                        workflows_committed: List[str], headers: dict,
                        user: str = None, db: Session = None) -> Optional[dict]:
    """
    Create a new Pull Request from the Actions Manager branch to the target branch.
    
    Args:
        owner: Repository owner
        repo: Repository name
        am_branch: Actions Manager dedicated branch name
        target_branch: Target branch name
        project_code: Project code for PR title
        workflows_committed: List of workflow names committed
        headers: GitHub API headers
        user: GitHub username for authenticated API calls
        db: Database session for authenticated API calls
    
    Returns:
        dict or None: PR data if created successfully, None otherwise
    """
    pr_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls"
    
    # Build PR body with list of workflows
    workflows_list = "\n".join([f"- {wf}" for wf in workflows_committed])
    pr_body = f"""This PR updates Actions Manager workflows for project **{project_code}**.

## Workflows Updated
{workflows_list}

---
*This PR was automatically created by Actions Manager.*
"""
    
    pr_payload = {
        "title": f"[Actions Manager] Update {project_code} workflows",
        "body": pr_body,
        "head": am_branch,
        "base": target_branch
    }
    
    if user and db:
        # Use requests.post directly since github_put is for PUT requests
        headers_with_auth = _get_authenticated_headers(user, headers)
        if not headers_with_auth:
            print(f"❌ User {user} not authenticated")
            return None
        response = requests.post(pr_url, json=pr_payload, headers=headers_with_auth, timeout=GITHUB_TIMEOUT_SECONDS)
    else:
        response = requests.post(pr_url, json=pr_payload, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    
    if response.status_code == 201:
        pr_data = response.json()
        print(f"✅ Created PR #{pr_data['number']}: {pr_data['html_url']}")
        return pr_data
    else:
        print(f"❌ Failed to create PR: {response.status_code} - {response.text[:200]}")
        return None


def _update_workflow_to_github(owner: str, repo: str, workflow: dict, 
                              project_code: str, am_branch: str, 
                              headers: dict, repo_name: str, user: str = None, db: Session = None, use_prefix: bool = True) -> tuple:
    """
    Update a single workflow to GitHub on the Actions Manager dedicated branch.
    Only updates if content has actually changed to prevent blank commits.
    
    Args:
        owner: Repository owner
        repo: Repository name
        workflow: Workflow dict with 'name' and 'content' keys
        project_code: Project code for file naming
        am_branch: Actions Manager dedicated branch name (e.g., 'actions-manager/myapp-main')
        headers: GitHub API headers
        repo_name: Full repository name for logging
        user: GitHub username for authenticated API calls
        db: Database session for authenticated API calls
        use_prefix: Whether to use the AM_{PROJECT_CODE}_ prefix
    
    Returns:
        tuple: (status_code, new_sha_or_none)
    """
    # Validate workflow name is not empty
    workflow_name = workflow.get('name', '').strip()
    if not workflow_name:
        error_msg = f"❌ Workflow name cannot be empty for {repo_name}"
        print(error_msg)
        return 400, None  # Bad Request
    
    # Remove .yml/.yaml extension from workflow name if present to avoid double extensions
    workflow_base_name = workflow_name
    if workflow_base_name.endswith('.yml'):
        workflow_base_name = workflow_base_name[:-4]
    elif workflow_base_name.endswith('.yaml'):
        workflow_base_name = workflow_base_name[:-5]
    
    formatted_name = format_workflow_name(workflow_base_name, project_code, use_prefix)
    encoded_content = base64.b64encode(workflow["content"].encode()).decode()
    path = f".github/workflows/{formatted_name}"
    
    print(f"🔍 _update_workflow_to_github:")
    print(f"   Owner: {owner}, Repo: {repo}")
    print(f"   Workflow name: {workflow.get('name')}")
    print(f"   Formatted name: {formatted_name}")
    print(f"   Path: {path}")
    print(f"   AM Branch: {am_branch}")
    print(f"   User for API calls: {user}")
    
    # Check existing content on the AM branch
    file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}?ref={am_branch}"
    print(f"🔍 Checking file at: {file_url}")
    
    sha, content_unchanged = _check_existing_workflow_content(file_url, encoded_content, headers, user, db)
    print(f"🔍 File check result - SHA: {sha}, Content unchanged: {content_unchanged}")
    
    if content_unchanged:
        print(f"📌 Workflow content unchanged for {formatted_name} in {repo_name} on {am_branch}, skipping update")
        return 204, sha  # No Content (unchanged)

    # If file doesn't exist (sha is None), ensure .github/workflows directory exists
    if sha is None:
        # Verify the AM branch exists
        branch_check_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/branches/{am_branch}"
        print(f"🔍 Verifying branch exists: {branch_check_url}")
        if user and db:
            branch_response = github_get(branch_check_url, user, db, headers=headers)
        else:
            branch_response = requests.get(branch_check_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
        
        if branch_response.status_code == 404:
            print(f"❌ Branch '{am_branch}' does not exist in {owner}/{repo}")
            print(f"   Cannot create workflow file on non-existent branch")
            return 404, None
        elif branch_response.status_code != 200:
            print(f"⚠️ Unexpected status checking branch: {branch_response.status_code}")
            print(f"   Response: {branch_response.text[:500]}")
        else:
            print(f"✅ Branch '{am_branch}' exists in {owner}/{repo}")
        
        if not _ensure_workflows_directory_exists(owner, repo, am_branch, headers, user, db):
            # Failed to create directory, mark as error
            print(f"❌ Failed to ensure .github/workflows directory exists in {repo_name} on {am_branch}")
            return 404, None

    # Content has changed or file doesn't exist, proceed with update
    payload = {
        "message": f"Updating {formatted_name} in {repo_name} for {project_code} [skip ci]",
        "content": encoded_content,
        "branch": am_branch,
    }
    if sha:
        payload["sha"] = sha

    # PUT request should NOT include ?ref={branch} - branch is specified in the payload body
    put_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}"
    print(f"🔍 Sending PUT request to: {put_url}")
    print(f"🔍 Payload has SHA: {sha is not None}")
    print(f"🔍 Payload message: {payload['message']}")
    print(f"🔍 Payload branch: {payload['branch']}")
    
    try:
        if user and db:
            print(f"🔍 Using github_put with user: {user}")
            put_response = github_put(put_url, user, db, json=payload, headers=headers)
        else:
            print(f"🔍 Using requests.put directly")
            put_response = requests.put(put_url, json=payload, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
            
        print(f"🔍 PUT response status: {put_response.status_code}")
        if put_response.status_code not in [200, 201]:
            print(f"❌ PUT failed. Response: {put_response.text[:500]}")
            # Try to parse and provide more helpful error message
            try:
                error_data = put_response.json()
                error_msg = error_data.get('message', 'Unknown error')
                print(f"   GitHub API Error: {error_msg}")
                if put_response.status_code == 404:
                    print(f"   Possible causes:")
                    print(f"   - Repository '{owner}/{repo}' doesn't exist or isn't accessible")
                    print(f"   - Branch '{am_branch}' doesn't exist")
                    print(f"   - OAuth app lacks 'contents: write' permission")
                    print(f"   - Token is invalid or expired")
            except Exception:
                # If response parsing fails, continue with existing error message
                pass
            return put_response.status_code, None
    except Exception as put_error:
        print(f"❌ Exception during PUT request: {str(put_error)}")
        import traceback
        traceback.print_exc()
        raise
    
    # Extract the new SHA from the successful response
    new_sha = None
    if put_response.status_code in [200, 201]:
        response_data = put_response.json()
        new_sha = response_data.get("content", {}).get("sha")
        print(f"✅ Successfully created/updated workflow. New SHA: {new_sha}")
    
    return put_response.status_code, new_sha


def _update_workflow_git_hash(db: Session, workflow_name: str, new_sha: str,
                              project_code: str, is_reusable: bool = False) -> None:
    """Update the workflow's git hash in the database, scoped to one project.

    Workflow names are deliberately not globally unique — two projects may each
    own a workflow called "ci". This previously did an unscoped
    ``filter_by(workflow_name=...).first()``, so committing project A's workflow
    could stamp A's GitHub blob SHA onto project B's row, corrupting B's drift
    baseline and making real drift read as "synchronized".

    Note the name arrives unprefixed in both naming modes: ``use_prefix`` is
    applied only when building the GitHub path, so prefixing does not protect
    against this collision.
    """
    if not new_sha:
        return

    db_workflow = (
        db.query(Workflow)
        .join(ProjectWorkflow, ProjectWorkflow.workflow_id == Workflow.workflow_id)
        .join(Project, Project.project_id == ProjectWorkflow.project_id)
        .filter(
            Project.project_code == project_code,
            Workflow.workflow_name == workflow_name,
            Workflow.reusable_workflow == is_reusable,
        )
        .first()
    )
    if db_workflow:
        db_workflow.workflow_git_hash = new_sha
        db.commit()
        print(f"✅ Updated git hash for workflow '{workflow_name}' in {project_code}: {new_sha}")


def _db_update_custom_file_sha(db: Session, file_id: int, new_sha: Optional[str]) -> None:
    """Persist the blob SHA returned by GitHub after a successful custom file write."""
    if not new_sha:
        return
    cf = db.query(CustomFile).filter_by(id=file_id).first()
    if cf:
        cf.git_hash = new_sha
        db.commit()


def _resolve_effective_target_branches(repo_name: str, owner: str, repo: str, project: "Project", db: Session,
                                        branch_option: str, regex_pattern: str, branch_max_age_days: int,
                                        headers: dict, user: str) -> tuple:
    """Resolve target branches for a repo, honoring a project's per-repo branch override when given.

    Returns (target_branches, error_result) — error_result is non-None (and target_branches is
    None) when branch resolution fails; the caller should return error_result immediately.
    """
    if project is not None:
        cfg = resolve_branch_config_for_repo(db, project, repo_name)
        eff_option = cfg["branch_option"]
        eff_regex = cfg["branch_regex"]
        eff_max_age = cfg["branch_max_age_days"]
        if not cfg["using_project_default"]:
            print(
                f"   🔧 Using repo override for {repo_name}: "
                f"option={eff_option}, regex={eff_regex!r}, max_age={eff_max_age}"
            )
    else:
        eff_option, eff_regex, eff_max_age = branch_option, regex_pattern, branch_max_age_days

    try:
        target_branches = _resolve_branches_for_repo(
            owner, repo, eff_option, eff_regex, eff_max_age, headers, user, db
        )
        print(f"🔍 Resolved target branches for {repo_name}: {target_branches}")
        return target_branches, None
    except ValueError as e:
        print(f"❌ Error resolving branches: {str(e)}")
        return None, {"error": str(e), "status": 400}
    except Exception as e:
        print(f"❌ Unexpected error resolving branches: {str(e)}")
        return None, {"error": f"Failed to resolve branches: {str(e)}", "status": 500}


def _commit_workflows_to_branch(workflows: List[dict], owner: str, repo: str, project_code: str, am_branch: str,
                                 headers: dict, repo_name: str, user: str, db: Session, use_prefix: bool) -> tuple:
    """Commit each workflow to the AM branch. Returns (workflows_committed, workflow_errors)."""
    workflows_committed = []
    workflow_errors = []
    for workflow in workflows:
        workflow_name = workflow.get('name', 'unknown')
        print(f"\n🔍 Committing workflow '{workflow_name}' to {am_branch}")
        try:
            status_code, new_sha = _update_workflow_to_github(
                owner, repo, workflow, project_code, am_branch,
                headers, repo_name, user, db, use_prefix
            )
            if status_code in [200, 201]:
                workflows_committed.append(workflow_name)
                print(f"✅ Committed workflow '{workflow_name}' (status: {status_code})")
                _update_workflow_git_hash(db, workflow_name, new_sha, project_code, is_reusable=False)
            elif status_code == 204:
                workflows_committed.append(workflow_name)
                print(f"📌 Workflow '{workflow_name}' unchanged (status: 204)")
            else:
                workflow_errors.append(f"{workflow_name}: HTTP {status_code}")
                print(f"❌ Failed to commit workflow '{workflow_name}': {status_code}")
        except Exception as e:
            workflow_errors.append(f"{workflow_name}: {str(e)}")
            print(f"❌ Exception committing workflow '{workflow_name}': {str(e)}")
            import traceback
            traceback.print_exc()
    return workflows_committed, workflow_errors


def _commit_reusable_workflows_to_branch(rxworkflows: List[dict], owner: str, repo: str, project_code: str,
                                          am_branch: str, headers: dict, reusable_repo: str, user: str,
                                          db: Session, use_prefix: bool) -> tuple:
    """Commit each reusable workflow to the AM branch. Returns (workflows_committed, workflow_errors)."""
    workflows_committed = []
    workflow_errors = []
    for workflow in rxworkflows:
        workflow_name = workflow.get('name', '').strip()
        if not workflow_name:
            print("❌ Reusable workflow name cannot be empty")
            workflow_errors.append("<empty-name>: Empty workflow name")
            continue

        print(f"\n🔍 Committing reusable workflow '{workflow_name}' to {am_branch}")
        try:
            status_code, new_sha = _update_workflow_to_github(
                owner, repo, workflow, project_code, am_branch,
                headers, reusable_repo, user, db, use_prefix
            )
            if status_code in [200, 201]:
                workflows_committed.append(workflow_name)
                print(f"✅ Committed reusable workflow '{workflow_name}' (status: {status_code})")
                _update_workflow_git_hash(db, workflow_name, new_sha, project_code, is_reusable=True)
            elif status_code == 204:
                workflows_committed.append(workflow_name)
                print(f"📌 Reusable workflow '{workflow_name}' unchanged (status: 204)")
            else:
                workflow_errors.append(f"{workflow_name}: HTTP {status_code}")
                print(f"❌ Failed to commit reusable workflow '{workflow_name}': {status_code}")
        except Exception as e:
            workflow_errors.append(f"{workflow_name}: {str(e)}")
            print(f"❌ Exception committing reusable workflow '{workflow_name}': {str(e)}")
            import traceback
            traceback.print_exc()
    return workflows_committed, workflow_errors


def _delete_custom_file_from_am_branch(owner: str, repo: str, cf_path: str, am_branch: str, project_code: str,
                                        user: str, db: Session, headers: dict) -> tuple:
    """Returns (success, error_message)."""
    sha_resp = github_get(
        f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{cf_path}",
        user, db,
        headers={**headers, "params": {"ref": am_branch}},
        params={"ref": am_branch},
    )
    if sha_resp.status_code == 200:
        current_sha = sha_resp.json().get("sha")
        del_resp = requests.delete(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{cf_path}",
            headers=headers,
            json={
                "message": f"Delete {cf_path} via ActionsManager [{project_code}] [skip ci]",
                "sha": current_sha,
                "branch": am_branch,
            },
            timeout=GITHUB_TIMEOUT_SECONDS,
        )
        if del_resp.status_code in (200, 201):
            print(f"✅ Deleted custom file '{cf_path}' from {am_branch}")
            return True, None
        print(f"❌ Failed to delete custom file '{cf_path}': {del_resp.status_code}")
        return False, f"{cf_path}: HTTP {del_resp.status_code}"
    if sha_resp.status_code == 404:
        print(f"📌 Custom file '{cf_path}' already absent from {am_branch}")
        return True, None
    return False, f"{cf_path}: HTTP {sha_resp.status_code} fetching SHA"


def _upsert_custom_file_to_am_branch(owner: str, repo: str, cf: dict, am_branch: str, project_code: str,
                                      user: str, db: Session, headers: dict) -> tuple:
    """Returns (success, error_message)."""
    cf_path = cf.get("file_path", "")
    sha_resp = github_get(
        f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{cf_path}",
        user, db,
        headers=headers,
        params={"ref": am_branch},
    )
    existing_sha = sha_resp.json().get("sha") if sha_resp.status_code == 200 else None
    put_body: dict = {
        "message": f"Update {cf_path} via ActionsManager [{project_code}] [skip ci]",
        "content": base64.b64encode(cf["file_content"].encode()).decode(),
        "branch": am_branch,
    }
    if existing_sha:
        put_body["sha"] = existing_sha
    put_resp = requests.put(
        f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{cf_path}",
        headers=headers,
        json=put_body,
        timeout=GITHUB_TIMEOUT_SECONDS,
    )
    if put_resp.status_code in (200, 201):
        new_sha = put_resp.json().get("content", {}).get("sha")
        _db_update_custom_file_sha(db, cf["id"], new_sha)
        print(f"✅ Committed custom file '{cf_path}' (SHA: {new_sha})")
        return True, None
    print(f"❌ Failed to commit custom file '{cf_path}': {put_resp.status_code}")
    return False, f"{cf_path}: HTTP {put_resp.status_code}"


def _commit_custom_files_to_branch(custom_files: List[dict], owner: str, repo: str, am_branch: str,
                                    project_code: str, user: str, db: Session, headers: dict) -> tuple:
    """Delete or upsert each custom file on the AM branch. Returns (custom_files_committed, custom_file_errors)."""
    custom_files_committed = []
    custom_file_errors = []
    for cf in custom_files:
        cf_path = cf.get("file_path", "")
        try:
            if cf.get("pending_delete"):
                success, error = _delete_custom_file_from_am_branch(
                    owner, repo, cf_path, am_branch, project_code, user, db, headers
                )
            else:
                success, error = _upsert_custom_file_to_am_branch(
                    owner, repo, cf, am_branch, project_code, user, db, headers
                )
            if success:
                custom_files_committed.append(cf_path)
            else:
                custom_file_errors.append(error)
        except Exception as e:
            custom_file_errors.append(f"{cf_path}: {str(e)}")
            print(f"❌ Exception committing custom file '{cf_path}': {str(e)}")
    return custom_files_committed, custom_file_errors


def _commit_codeowners_to_branch(codeowners_for_repo: Optional[dict], owner: str, repo: str, am_branch: str,
                                  project_code: str, user: str, db: Session, headers: dict) -> tuple:
    """Commit CODEOWNERS to the same AM branch as workflows/custom files, so it rides the same PR.

    Returns (codeowners_committed_path, error_message) — both empty/None when there's nothing to commit.
    """
    if not codeowners_for_repo:
        return "", None
    co_path = codeowners_for_repo["file_path"]
    try:
        sha_resp = github_get(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{co_path}",
            user, db,
            headers=headers,
            params={"ref": am_branch},
        )
        existing_sha = sha_resp.json().get("sha") if sha_resp.status_code == 200 else None
        put_body = {
            "message": f"Update {co_path} via ActionsManager [{project_code}] [skip ci]",
            "content": base64.b64encode(codeowners_for_repo["content"].encode()).decode(),
            "branch": am_branch,
        }
        if existing_sha:
            put_body["sha"] = existing_sha
        put_resp = requests.put(
            f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{co_path}",
            headers=headers,
            json=put_body,
            timeout=GITHUB_TIMEOUT_SECONDS,
        )
        if put_resp.status_code in (200, 201):
            new_co_sha = put_resp.json().get("content", {}).get("sha")
            _mark_codeowners_committed(
                db, codeowners_for_repo["project_id"], codeowners_for_repo["repo_id"], new_co_sha
            )
            print(f"✅ Committed CODEOWNERS '{co_path}' to {am_branch}")
            return co_path, None
        print(f"❌ Failed to commit CODEOWNERS '{co_path}': {put_resp.status_code}")
        return "", f"{co_path}: HTTP {put_resp.status_code}"
    except Exception as e:
        print(f"❌ Exception committing CODEOWNERS '{co_path}': {str(e)}")
        return "", f"{co_path}: {str(e)}"


def _build_pr_error_result(workflows_committed: list, workflow_errors: list, custom_files_result: Optional[dict],
                            am_branch: str, target_branch: str, progress_callback, result_key: str) -> dict:
    print(f"❌ Failed to create PR for {am_branch} -> {target_branch}")
    result = {
        "status": "error",
        "error": PR_CREATION_FAILED,
        "workflows_committed": workflows_committed,
        "workflow_errors": workflow_errors,
    }
    if custom_files_result is not None:
        result["custom_files_committed"] = custom_files_result.get("custom_files_committed")
        result["custom_file_errors"] = custom_files_result.get("custom_file_errors")
    if progress_callback:
        progress_callback(result_key, PROGRESS_OPENING_PR, "error", PR_CREATION_FAILED)
    return result


def _build_pr_success_result(pr: dict, existing_pr: Optional[dict], am_branch: str, workflows_committed: list,
                              workflow_errors: list, custom_files_result: Optional[dict],
                              progress_callback, result_key: str) -> dict:
    print(f"✅ {'Updated existing' if existing_pr else 'Created new'} PR #{pr['number']}: {pr['html_url']}")
    result = {
        "status": "pr_updated" if existing_pr else "pr_created",
        "pr_url": pr['html_url'],
        "pr_number": pr['number'],
        "pr_title": pr.get('title'),
        "pr_author": (pr.get('user') or {}).get('login'),
        "pr_body": pr.get('body'),
        "branch_name": am_branch,
        "workflows_committed": workflows_committed,
    }
    if custom_files_result is not None:
        result["custom_files_committed"] = custom_files_result.get("custom_files_committed")
        result["codeowners_committed"] = custom_files_result.get("codeowners_committed")
    if workflow_errors:
        result["workflow_errors"] = workflow_errors
    if custom_files_result is not None and custom_files_result.get("custom_file_errors"):
        result["custom_file_errors"] = custom_files_result.get("custom_file_errors")
    if progress_callback:
        progress_callback(result_key, PROGRESS_OPENING_PR, "completed")
    return result


def _finalize_pr_result(owner: str, repo: str, am_branch: str, target_branch: str, headers: dict, user: str,
                         db: Session, project_code: str, workflows_committed: list, workflow_errors: list,
                         progress_callback, result_key: str,
                         custom_files_result: Optional[dict] = None) -> dict:
    """Resolve existing-PR-update vs new-PR-create and shape the per-branch result dict.

    Shared by the regular and reusable workflow update flows — pass custom_files_result
    (a dict with custom_files_committed/custom_file_errors/codeowners_committed keys) to
    include the custom-files/CODEOWNERS keys the regular flow needs; leave it None (the
    reusable flow's case) to omit them entirely.
    """
    existing_pr = _check_existing_pr(owner, repo, am_branch, target_branch, headers, user, db)
    pr = existing_pr or _create_pull_request(
        owner, repo, am_branch, target_branch, project_code, workflows_committed, headers, user, db
    )

    if not pr:
        return _build_pr_error_result(
            workflows_committed, workflow_errors, custom_files_result,
            am_branch, target_branch, progress_callback, result_key
        )

    return _build_pr_success_result(
        pr, existing_pr, am_branch, workflows_committed, workflow_errors,
        custom_files_result, progress_callback, result_key
    )


def _process_regular_workflows_update(repo_names: List[str], workflows: List[dict],
                                    project_code: str, branch_option: str,
                                    regex_pattern: str, branch_max_age_days: int,
                                    headers: dict, db: Session, user: str = None, use_prefix: bool = True,
                                    project: "Project" = None, progress_callback=None,
                                    custom_files: Optional[List[dict]] = None,
                                    codeowners_files: Optional[dict] = None) -> dict:
    """
    Process updates for regular workflows across multiple repositories.
    Creates dedicated Actions Manager branches and Pull Requests per (repo, target_branch).

    When ``project`` is provided, the per-repository branch override (if any)
    on ``project_repos`` takes precedence over the supplied ``branch_option``/
    ``regex_pattern``/``branch_max_age_days`` arguments — these arguments are
    used as the project-level fallback only.

    ``custom_files`` (list of dicts with id/file_path/file_content/pending_delete) are
    committed to the same AM branch as workflows so they land in the same PR.

    ``codeowners_files`` (dict keyed by repo_name, with file_path/content/repo_id/
    project_id) are committed to that repo's same AM branch for the same reason —
    so CODEOWNERS never opens a second PR against a repo already getting one here.

    Returns:
        dict: Results with PR URLs and status per repo/branch combination
    """
    results = {}
    custom_files = custom_files or []
    codeowners_files = codeowners_files or {}

    print(f"🔍 _process_regular_workflows_update starting:")
    print(f"   Repositories: {repo_names}")
    print(f"   Workflows: {[w.get('name') for w in workflows]}")
    print(f"   Custom files: {[cf.get('file_path') for cf in custom_files]}")
    print(f"   CODEOWNERS repos: {list(codeowners_files.keys())}")
    print(f"   Project code: {project_code}")
    print(f"   Use prefix: {use_prefix}")
    
    for repo_name in repo_names:
        print(f"🔍 Processing repo: {repo_name}")
        owner, repo = repo_name.split("/")
        codeowners_for_repo = codeowners_files.get(repo_name)

        target_branches, branch_error = _resolve_effective_target_branches(
            repo_name, owner, repo, project, db, branch_option, regex_pattern, branch_max_age_days, headers, user
        )
        if branch_error:
            return branch_error

        # Process each target branch separately
        for target_branch in target_branches:
            print(f"\n🔍 Processing target branch: {target_branch}")
            result_key = f"{repo_name} on {target_branch}"
            if progress_callback:
                progress_callback(result_key, PROGRESS_CREATING_BRANCH, "running")

            # Step 1: Create or get the Actions Manager dedicated branch
            am_branch, branch_created, error_msg = _create_or_get_am_branch(
                owner, repo, target_branch, project_code, headers, user, db
            )

            if not am_branch:
                print(f"❌ Failed to create/get AM branch: {error_msg}")
                results[result_key] = {"status": "error", "error": error_msg}
                if progress_callback:
                    progress_callback(result_key, PROGRESS_CREATING_BRANCH, "error", error_msg)
                continue

            print(f"{'✅ Created' if branch_created else '📌 Using existing'} AM branch: {am_branch}")
            if progress_callback:
                progress_callback(result_key, PROGRESS_COMMITTING_FILES, "running")

            # Step 2: commit workflows, custom files, and CODEOWNERS to the AM branch
            workflows_committed, workflow_errors = _commit_workflows_to_branch(
                workflows, owner, repo, project_code, am_branch, headers, repo_name, user, db, use_prefix
            )
            custom_files_committed, custom_file_errors = _commit_custom_files_to_branch(
                custom_files, owner, repo, am_branch, project_code, user, db, headers
            )
            codeowners_committed, codeowners_error = _commit_codeowners_to_branch(
                codeowners_for_repo, owner, repo, am_branch, project_code, user, db, headers
            )
            if codeowners_error:
                custom_file_errors.append(codeowners_error)

            if not workflows_committed and not custom_files_committed and not codeowners_committed:
                print(f"❌ No workflows, custom files, or CODEOWNERS were successfully committed to {am_branch}")
                results[result_key] = {
                    "status": "error",
                    "error": NO_WORKFLOWS_COMMITTED,
                    "workflow_errors": workflow_errors,
                    "custom_file_errors": custom_file_errors,
                }
                if progress_callback:
                    progress_callback(result_key, PROGRESS_COMMITTING_FILES, "error", NO_WORKFLOWS_COMMITTED)
                continue

            # Step 3/4: update existing PR, or create a new one
            if progress_callback:
                progress_callback(result_key, PROGRESS_OPENING_PR, "running")
            results[result_key] = _finalize_pr_result(
                owner, repo, am_branch, target_branch, headers, user, db,
                project_code, workflows_committed, workflow_errors,
                progress_callback, result_key,
                custom_files_result={
                    "custom_files_committed": custom_files_committed,
                    "custom_file_errors": custom_file_errors,
                    "codeowners_committed": codeowners_committed,
                },
            )

    print(f"\n🔍 _process_regular_workflows_update complete. Results: {results}")
    return results


def _process_reusable_workflows_update(rxworkflows: List[dict], user: str,
                                     project_code: str,
                                     regex_pattern: str, branch_max_age_days: int,
                                     headers: dict, db: Session = None,
                                     reusable_repo: str = None, use_prefix: bool = True, progress_callback=None) -> dict:
    """
    Process updates for reusable workflows in the dedicated repository.
    Creates dedicated Actions Manager branches and Pull Requests per target_branch.

    Args:
        reusable_repo: Full repo name (owner/repo) to push reusable workflows to.
                       When None, falls back to ``{user}/am-reuseable-workflow``.
        use_prefix: Whether to use the AM_{PROJECT_CODE}_ prefix for workflow names.

    Returns:
        dict: Results with PR URLs and status per branch combination
    """
    results = {}
    if not reusable_repo:
        reusable_repo = f"{user}/am-reuseable-workflow"
    
    if "/" not in reusable_repo:
        return {"error": f"Invalid repo name format: '{reusable_repo}'", "status": 400}
        
    owner, repo = reusable_repo.split("/", 1)
    
    print(f"🔍 _process_reusable_workflows_update starting:")
    print(f"   Reusable repo: {reusable_repo}")
    print(f"   Workflows: {[w.get('name') for w in rxworkflows]}")
    print(f"   Project code: {project_code}")

    # For reusable workflows, we always target default branch
    # (reusable workflows are centralized, not per-branch)
    target_branches = [get_default_branch(owner, repo, headers, user, db)]
    
    print(f"🔍 Resolved target branches: {target_branches}")
    
    # Process each target branch separately
    for target_branch in target_branches:
        print(f"\n🔍 Processing target branch: {target_branch}")
        result_key = f"{reusable_repo} on {target_branch}"
        if progress_callback:
            progress_callback(result_key, PROGRESS_CREATING_BRANCH, "running")

        # Step 1: Create or get the Actions Manager dedicated branch
        am_branch, branch_created, error_msg = _create_or_get_am_branch(
            owner, repo, target_branch, project_code, headers, user, db
        )

        if not am_branch:
            print(f"❌ Failed to create/get AM branch: {error_msg}")
            results[result_key] = {"status": "error", "error": error_msg}
            if progress_callback:
                progress_callback(result_key, PROGRESS_CREATING_BRANCH, "error", error_msg)
            continue

        print(f"{'✅ Created' if branch_created else '📌 Using existing'} AM branch: {am_branch}")
        if progress_callback:
            progress_callback(result_key, PROGRESS_COMMITTING_FILES, "running")

        # Step 2: Commit all reusable workflows to the AM branch
        workflows_committed, workflow_errors = _commit_reusable_workflows_to_branch(
            rxworkflows, owner, repo, project_code, am_branch, headers, reusable_repo, user, db, use_prefix
        )

        if not workflows_committed:
            print(f"❌ No reusable workflows were successfully committed to {am_branch}")
            results[result_key] = {
                "status": "error",
                "error": NO_WORKFLOWS_COMMITTED,
                "workflow_errors": workflow_errors
            }
            if progress_callback:
                progress_callback(result_key, PROGRESS_COMMITTING_FILES, "error", NO_WORKFLOWS_COMMITTED)
            continue

        # Step 3/4: update existing PR, or create a new one
        if progress_callback:
            progress_callback(result_key, PROGRESS_OPENING_PR, "running")
        results[result_key] = _finalize_pr_result(
            owner, repo, am_branch, target_branch, headers, user, db,
            project_code, workflows_committed, workflow_errors,
            progress_callback, result_key,
        )

    print(f"\n🔍 _process_reusable_workflows_update complete. Results: {results}")
    return results


def _validate_reusable_workflows_for_caller(
    project: "Project", rxworkflows: list, db: Session
) -> Optional[dict]:
    """Validate linked reusable workflows for a caller (standard) project.

    Returns an error dict if validation fails, otherwise None.
    """
    selected_norm = {
        _normalize_reusable_workflow_name(w.get("name"))
        for w in rxworkflows
        if w.get("name")
    }
    linked_rows = db.query(Workflow, LinkedReusableWorkflow, Project).join(
        LinkedReusableWorkflow, LinkedReusableWorkflow.workflow_id == Workflow.workflow_id
    ).join(
        Project, Project.project_id == LinkedReusableWorkflow.rwx_project_id
    ).filter(
        LinkedReusableWorkflow.standard_project_id == project.project_id
    ).all()
    for workflow, _link, rwx_project in linked_rows:
        if _normalize_reusable_workflow_name(workflow.workflow_name) not in selected_norm:
            continue
        validation = validate_reusable_workflow_link(project, rwx_project, db)
        if not validation.allowed:
            return {
                "error": validation.reason or "Unable to validate reusable workflow compatibility. Please refresh and try again.",
                "status": 400,
            }
    return None


def _resolve_effective_rwx_params(
    project: "Project", project_code: str, db: Session
) -> tuple:
    """Resolve effective project code and prefix for reusable workflow updates.

    For standard (caller) projects, uses the owning RWX project's settings.
    Returns (effective_code, effective_prefix).
    """
    if project.project_type != "standard":
        return project_code, project.use_prefix

    linked_rwx = db.query(Project).join(
        LinkedReusableWorkflow, LinkedReusableWorkflow.rwx_project_id == Project.project_id
    ).filter(
        LinkedReusableWorkflow.standard_project_id == project.project_id
    ).first()
    if linked_rwx:
        return linked_rwx.project_code.upper(), linked_rwx.use_prefix
    return project_code, project.use_prefix


def _restore_under_review_after_pr_update(
    db: Session, project: "Project", workflows: list, rxworkflows: list, results: dict
) -> None:
    """Restore under_review status for workflows after a successful PR update.

    save_workflows resets status to committed_locally; this re-applies under_review
    so the PR-backed lock persists across reloads.
    """
    has_pr_result = any(
        isinstance(r, dict) and r.get("status") in ("pr_updated", "pr_created")
        for r in results.values()
    )
    if not has_pr_result:
        return

    updated_workflow_names: List[str] = []
    updated_workflow_names.extend(w.get("name") for w in workflows if w.get("name"))
    updated_workflow_names.extend(w.get("name") for w in rxworkflows if w.get("name"))
    if not updated_workflow_names:
        return

    _update_project_workflows_status(
        db, project.project_id, "under_review",
        workflow_names=updated_workflow_names
    )
    print(f"✅ Restored under_review status for {len(updated_workflow_names)} workflow(s) after PR update")

    linked_wf_ids = _get_linked_workflow_ids_for_project(
        db, project.project_id, workflow_names=updated_workflow_names
    )
    if linked_wf_ids:
        db.query(Workflow).filter(
            Workflow.workflow_id.in_(linked_wf_ids)
        ).update({"workflow_status": "under_review"}, synchronize_session=False)
        db.commit()
        print(f"✅ Restored under_review status for {len(linked_wf_ids)} linked workflow(s) after PR update")


def _handle_regular_workflows_section(
    repo_names: list, workflows: list, project_code: str, branch_option: str,
    regex_pattern: str, branch_max_age_days: int, headers: dict, db: Session,
    user: str, project: "Project", results: dict
) -> Optional[dict]:
    """Process regular workflows and merge into results.

    Returns an error dict if processing fails, otherwise None.
    """
    if not repo_names:
        print(f"⚠️ Skipping regular workflows: No repo_names provided")
        return None
    if not workflows:
        print(f"⚠️ Skipping regular workflows: No workflows provided")
        return None

    print(f"✅ Processing {len(workflows)} regular workflows across {len(repo_names)} repositories")
    regular_results = _process_regular_workflows_update(
        repo_names, workflows, project_code, branch_option,
        regex_pattern, branch_max_age_days, headers, db, user,
        project=project,
    )

    if "error" in regular_results:
        return regular_results
    results.update(regular_results)
    return None


def _handle_reusable_workflows_section(
    rxworkflows: list, project: "Project", project_code: str,
    regex_pattern: str, branch_max_age_days: int, headers: dict,
    db: Session, user: str, results: dict
) -> Optional[dict]:
    """Process reusable workflows and merge into results.

    Returns an error dict if validation/processing fails, otherwise None.
    """
    if not rxworkflows:
        print(f"⚠️ Skipping reusable workflows: No rxworkflows provided")
        return None

    if project.project_type == "standard":
        validation_error = _validate_reusable_workflows_for_caller(project, rxworkflows, db)
        if validation_error:
            return validation_error

    effective_code, effective_prefix = _resolve_effective_rwx_params(project, project_code, db)
    print(f"✅ Processing {len(rxworkflows)} reusable workflows")
    reusable_results = _process_reusable_workflows_update(
        rxworkflows, user, effective_code,
        regex_pattern, branch_max_age_days, headers, db,
        reusable_repo=_get_reusable_workflow_repo(project, user, db),
        use_prefix=effective_prefix
    )

    if "error" in reusable_results:
        return reusable_results
    results.update(reusable_results)
    return None


@router.post("/api/update-workflow", responses=_responses(401))
async def update_workflow(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Updates GitHub workflows and rxworkflows (reusable workflows)."""
    try:
        data = await request.json()
        # Use the authenticated header user; fall back to body for legacy clients
        user = _resolve_github_user(x_github_user, data.get("user"))
        repo_names = data.get("repo_names") or []
        workflows = data.get("workflows") or []
        rxworkflows = data.get("rxworkflows") or []
        regex_pattern = str(data.get("regex_pattern", "")).strip()
        branch_option = data.get("branch_option", "default").strip()
        project_name = data.get("project_name", "").strip()

        print(f"📌 update_workflow called with:")
        print(f"   user: {user}")
        print(f"   project_name: {project_name}")
        print(f"   repo_names: {repo_names}")
        print(f"   workflows count: {len(workflows)}")
        print(f"   rxworkflows count: {len(rxworkflows)}")
        print(f"   branch_option: {branch_option}")

        if user not in user_tokens:
            return {"error": NOT_AUTHENTICATED_DETAIL, "status": 401}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            return {"error": f"Project '{project_name}' not found in database", "status": 404}

        project_code = project.project_code.upper()
        branch_max_age_days = project.branch_max_age_days or 30
        print(f"📌 Debug: Using Project Code: {project_code}, branch_max_age_days: {branch_max_age_days}")

        results = {}

        error = _handle_regular_workflows_section(
            repo_names, workflows, project_code, branch_option,
            regex_pattern, branch_max_age_days, headers, db, user, project, results
        )
        if error:
            return error

        error = _handle_reusable_workflows_section(
            rxworkflows, project, project_code,
            regex_pattern, branch_max_age_days, headers, db, user, results
        )
        if error:
            return error

        if not results:
            print(f"⚠️ No workflows were processed - check that repo_names and workflows/rxworkflows are provided")
            return {"message": "⚠️ No workflows processed - missing repo_names or workflows data", "results": {}}

        _restore_under_review_after_pr_update(db, project, workflows, rxworkflows, results)

        return {"message": "✅ All workflows updated", "results": results}

    except Exception as e:
        print(f"❌ Error updating workflows: {str(e)}")
        return {"error": str(e), "status": 500}



@router.delete("/api/delete-workflow", responses=_responses(400, 401, 404, 500))
async def delete_workflow(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Deletes a GitHub workflow file from all branches where it exists."""
    try:
        data = await request.json()
        print(f"📌 Debug: Incoming Delete Request: {data}")

        user = data.get("user")
        repo_names = data.get("repo_names", [])
        workflow_name = data.get("workflow_name", "").strip()
        project_name = data.get("project_name", "").strip()

        if not workflow_name:
            raise HTTPException(status_code=400, detail=MISSING_WORKFLOW_NAME_DETAIL)

        if user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # ✅ Fetch project_code from the database
        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in database")

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix
        print(f"📌 Debug: Using Project Code: {project_code}, Use Prefix: {use_prefix}")

        results = {}
        formatted_workflow_name = format_workflow_name(workflow_name, project_code, use_prefix)

        async with httpx.AsyncClient() as client:
            for repo_name in repo_names:
                results[repo_name] = await _delete_workflow_from_repo(
                    client, repo_name, formatted_workflow_name, workflow_name, headers
                )

        # Persisted drift compares the managed version against a file that no
        # longer exists in these repos, so it is stale. Scoped to repos the
        # delete actually succeeded in - a failed one may still be drifted.
        deleted_repos = [
            name for name, outcome in results.items()
            if isinstance(outcome, dict) and outcome.get("deleted")
        ]
        if deleted_repos:
            deleted_wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == project.project_id,
                Workflow.workflow_name.ilike(workflow_name),
            ).first()
            if deleted_wf:
                for repo_name in deleted_repos:
                    clear_workflow_drift(db, project, deleted_wf.workflow_id, repo_name)

        return {"message": "✅ Workflow deletions completed!", "results": results}

    except HTTPException:
        # Re-raise HTTPExceptions as-is (e.g., 401 Unauthorized)
        raise
    except Exception as e:
        print(f"❌ Error deleting workflows: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def _delete_workflow_from_repo(client, repo_name: str, formatted_workflow_name: str, workflow_name: str, headers: dict):
    """Delete a workflow file from all branches in a single repository."""
    owner, repo = repo_name.split("/")
    workflow_path = f".github/workflows/{formatted_workflow_name}"

    # Fetch all branches
    branches_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/branches"
    branches_response = await client.get(branches_url, headers=headers)

    if branches_response.status_code != 200:
        print(f"❌ Error: Failed to fetch branches for {repo_name}")
        return "Branch fetch failed"

    branches = [branch["name"] for branch in branches_response.json()]
    deleted_branches = []
    failed_branches = {}

    for branch in branches:
        workflow_file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{workflow_path}?ref={branch}"

        # Check if workflow file exists
        response = await client.get(workflow_file_url, headers=headers)
        if response.status_code != 200:
            print(f"⚠️ Workflow {workflow_name} not found in {repo_name} on branch {branch}")
            continue

        sha = response.json().get("sha")
        if not sha:
            print(f"❌ Error: Could not retrieve SHA for {workflow_path} in {repo_name} on {branch}")
            failed_branches[branch] = "SHA retrieval failed"
            continue

        print(f"📌 Debug: Deleting {workflow_path} in {repo_name} on branch {branch}")

        # Send DELETE request with JSON body using request() method
        delete_payload = {
            "message": f"Deleting {formatted_workflow_name} workflow",
            "sha": sha,
            "branch": branch
        }

        # Add Content-Type header for JSON payload
        delete_headers = {**headers, "Content-Type": "application/json"}
        delete_response = await client.request(
            "DELETE",
            workflow_file_url,
            content=json.dumps(delete_payload),
            headers=delete_headers
        )

        if delete_response.status_code == 200:
            deleted_branches.append(branch)
        else:
            failed_branches[branch] = delete_response.status_code

    return {
        "deleted": deleted_branches,
        "failed": failed_branches
    }


@router.delete("/api/delete-reusable-workflow", responses=_responses(400, 401, 404, 500))
async def delete_reusable_workflow(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Deletes a reusable workflow from the am-reuseable-workflow repository."""
    try:
        data = await request.json()
        print(f"📌 Debug: Incoming Delete Reusable Workflow Request: {data}")

        user = data.get("user")
        workflow_name = data.get("workflow_name", "").strip()
        project_name = data.get("project_name", "").strip()

        if not workflow_name:
            raise HTTPException(status_code=400, detail=MISSING_WORKFLOW_NAME_DETAIL)

        if user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        # ✅ Fetch project_code from the database
        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in database")

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix
        print(f"📌 Debug: Using Project Code: {project_code}, Use Prefix: {use_prefix}")

        # 🔧 Target the reusable workflow repository
        reusable_repo_name = _get_reusable_workflow_repo(project, user, db)
        if "/" not in reusable_repo_name:
            raise HTTPException(status_code=400, detail=f"Invalid reusable repository name: '{reusable_repo_name}'")
            
        owner, repo = reusable_repo_name.split("/", 1)
        formatted_workflow_name = format_workflow_name(workflow_name, project_code, use_prefix)
        workflow_path = f".github/workflows/{formatted_workflow_name}"

        # Fetch all branches
        branches_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/branches"
        
        async with httpx.AsyncClient() as client:
            branches_response = await client.get(branches_url, headers=headers)

            if branches_response.status_code != 200:
                print(f"❌ Error: Failed to fetch branches for {reusable_repo_name}")
                raise HTTPException(status_code=branches_response.status_code, detail=f"Failed to fetch branches for {reusable_repo_name}")

            branches = [branch["name"] for branch in branches_response.json()]
            deleted_branches = []
            failed_branches = {}

            for branch in branches:
                workflow_file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{workflow_path}?ref={branch}"

                # Check if workflow file exists
                response = await client.get(workflow_file_url, headers=headers)
                if response.status_code != 200:
                    print(f"⚠️ Reusable workflow {workflow_name} not found in {reusable_repo_name} on branch {branch}")
                    continue  # Skip to next branch

                sha = response.json().get("sha")
                if not sha:
                    print(f"❌ Error: Could not retrieve SHA for {workflow_path} in {reusable_repo_name} on {branch}")
                    failed_branches[branch] = "SHA retrieval failed"
                    continue

                print(f"📌 Debug: Deleting reusable workflow {workflow_path} in {reusable_repo_name} on branch {branch}")

                # Send DELETE request with JSON body using request() method
                delete_payload = {
                    "message": f"Deleting reusable workflow {formatted_workflow_name}",
                    "sha": sha,
                    "branch": branch
                }

                # Add Content-Type header for JSON payload
                delete_headers = {**headers, "Content-Type": "application/json"}
                delete_response = await client.request(
                    "DELETE",
                    workflow_file_url,
                    content=json.dumps(delete_payload),
                    headers=delete_headers
                )

                if delete_response.status_code == 200:
                    deleted_branches.append(branch)
                else:
                    failed_branches[branch] = delete_response.status_code

        results = {
            reusable_repo_name: {
                "deleted": deleted_branches,
                "failed": failed_branches
            }
        }

        return {"message": "✅ Reusable workflow deletion completed!", "results": results}

    except HTTPException:
        # Re-raise HTTPExceptions as-is (e.g., 401 Unauthorized)
        raise
    except Exception as e:
        print(f"❌ Error deleting reusable workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/delete-db-workflow", responses=_responses(400, 401, 404, 500))
async def delete_db_workflow(request: Request, db: Annotated[Session, Depends(get_db)]):
    """
    Deletes a workflow from the specified project and removes it completely 
    only if no other projects are using it.
    """
    try:
        data = await request.json()
        print(f"📌 Debug: Incoming Delete DB Workflow Request: {data}")

        user = data.get("user")
        workflow_name = data.get("workflow_name", "").strip()
        project_name = data.get("project_name", "").strip()

        if not workflow_name:
            raise HTTPException(status_code=400, detail=MISSING_WORKFLOW_NAME_DETAIL)

        if user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

        # ✅ Fetch project from the database
        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in database")

        print(f"📌 Debug: Found Project '{project_name}' with ID {project.project_id}")

        # 🔧 FIX: Find workflow within the current project scope
        workflow = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.workflow_name.ilike(workflow_name)
        ).first()
        
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow '{workflow_name}' not found in project '{project_name}'")

        print(f"📌 Debug: Found Workflow '{workflow_name}' with ID {workflow.workflow_id}")
        # Captured up front: the instance is detached after the commit below
        # when the workflow itself gets deleted.
        deleted_workflow_id = workflow.workflow_id

        # ✅ Remove association from current project
        deleted_associations = db.query(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.project_id,
            ProjectWorkflow.workflow_id == workflow.workflow_id
        ).delete()
        print(f"📌 Removed {deleted_associations} associations from project '{project_name}'")

        # A workflow belongs to exactly one project (unique index on
        # project_workflows.workflow_id), so removing the association above
        # always leaves it orphaned — there is no other project to keep it for.
        db.delete(workflow)

        # ✅ Commit changes
        db.commit()
        drop_workflow_drift(db, project, deleted_workflow_id)
        print(f"✅ Successfully removed workflow '{workflow_name}' from project '{project_name}'")

        return {"message": f"✅ Workflow '{workflow_name}' removed from project '{project_name}'!"}

    except HTTPException:
        # Re-raise HTTPExceptions as-is (e.g., 401 Unauthorized)
        raise
    except Exception as e:
        print(f"❌ Error deleting workflow from database: {str(e)}")
        db.rollback()  # Ensure database consistency
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_single_workflow_status(client, owner: str, repo: str, formatted_workflow_name: str, headers: dict) -> dict:
    """Fetch the latest run status for a single workflow in a repository."""
    try:
        workflows_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/workflows"
        workflows_response = await client.get(workflows_url, headers=headers)

        if workflows_response.status_code != 200:
            return {"status": "error", "message": f"Failed to fetch workflows: {workflows_response.status_code}", "html_url": None}

        workflows_data = workflows_response.json()
        target_workflow = None
        for workflow in workflows_data.get("workflows", []):
            if workflow.get("path", "").endswith(formatted_workflow_name):
                target_workflow = workflow
                break

        if not target_workflow:
            return {"status": "not_found", "message": "Workflow not found in repository", "html_url": None}

        workflow_id = target_workflow["id"]
        runs_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs?per_page=1"
        runs_response = await client.get(runs_url, headers=headers)

        if runs_response.status_code != 200:
            return {"status": "error", "message": f"Failed to fetch runs: {runs_response.status_code}", "html_url": None}

        runs_data = runs_response.json()
        if not runs_data.get("workflow_runs"):
            return {"status": "no_runs", "message": "No workflow runs found", "html_url": None}

        latest_run = runs_data["workflow_runs"][0]
        return {
            "status": latest_run["conclusion"] or latest_run["status"],
            "run_number": latest_run["run_number"],
            "html_url": latest_run["html_url"],
            "created_at": latest_run["created_at"],
            "updated_at": latest_run["updated_at"]
        }
    except Exception as e:
        print(f"❌ Error fetching workflow status: {str(e)}")
        return {"status": "error", "message": str(e), "html_url": None}


@router.get("/api/workflow-status", responses=_responses(400, 401, 500))
async def get_workflow_status(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Get the latest workflow run status for workflows in selected repositories."""
    try:
        # Get query parameters
        user = request.query_params.get("user")
        repo_names = request.query_params.get("repo_names", "").split(",")
        workflow_names = request.query_params.get("workflow_names", "").split(",")
        project_name = request.query_params.get("project_name", "").strip()

        if not user or not repo_names or not workflow_names or not project_name:
            raise HTTPException(status_code=400, detail="Missing required parameters")

        if user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        # Get project code from database
        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            return {"error": f"Project '{project_name}' not found in database", "status": 404}

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix
        workflow_statuses = {}

        # Filter out empty repo names and workflow names
        repo_names = [repo.strip() for repo in repo_names if repo.strip()]
        workflow_names = [workflow.strip() for workflow in workflow_names if workflow.strip()]

        async with httpx.AsyncClient() as client:
            for repo_name in repo_names:
                if "/" not in repo_name:
                    continue
                    
                owner, repo = repo_name.split("/", 1)
                
                for workflow_name in workflow_names:
                    formatted_workflow_name = format_workflow_name(workflow_name, project_code, use_prefix)
                    workflow_key = f"{repo_name}/{workflow_name}"
                    workflow_statuses[workflow_key] = await _fetch_single_workflow_status(
                        client, owner, repo, formatted_workflow_name, headers
                    )
        
        return {"workflow_statuses": workflow_statuses}
        
    except Exception as e:
        print(f"❌ Error getting workflow status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workflow-templates/types", responses=_responses(500))
def get_template_types(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Get available workflow template types."""
    auth_module.resolve_authenticated_user(request, db)
    try:
        template_types = get_available_template_types()
        return {
            "message": "Available template types retrieved successfully",
            "template_types": template_types
        }
    except Exception as e:
        print(f"❌ Error getting template types: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workflow-templates/generate", responses=_responses(500))
def generate_workflow_templates(request: Request, body: WorkflowTemplateRequest, db: Annotated[Session, Depends(get_db)]):
    """Generate a complete set of reusable workflow templates."""
    auth_module.resolve_authenticated_user(request, db)
    try:
        templates = generate_template_set(
            user_org=body.user_org,
            build_type=body.build_type,
            project_code=body.project_code
        )

        # Format templates for frontend consumption
        formatted_templates = []

        # Standard workflow template
        formatted_templates.append(TemplateResponse(
            template_type="standard",
            content=templates["standard_workflow"],
            name=f"standard-pipeline",
            description=f"Standard pipeline that calls reusable workflow for {body.build_type} projects"
        ))

        # Reusable workflow template
        formatted_templates.append(TemplateResponse(
            template_type="reusable",
            content=templates["reusable_workflow"],
            name=f"main-workflow",
            description=f"Main reusable workflow for {body.build_type} projects"
        ))

        # Build-specific workflow template
        formatted_templates.append(TemplateResponse(
            template_type="build",
            content=templates["build_workflow"],
            name=f"am-{body.build_type}-build",
            description=f"Build-specific workflow for {body.build_type} projects"
        ))

        return {
            "message": "Workflow templates generated successfully",
            "build_type": body.build_type,
            "user_org": body.user_org,
            "project_code": body.project_code,
            "templates": [template.model_dump() for template in formatted_templates]
        }

    except Exception as e:
        print(f"❌ Error generating workflow templates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workflow-templates/standard", responses=_responses(500))
def generate_standard_template(request: Request, body: WorkflowTemplateRequest, db: Annotated[Session, Depends(get_db)]):
    """Generate just the standard workflow template."""
    auth_module.resolve_authenticated_user(request, db)
    try:
        template = generate_standard_workflow_template(
            user_org=body.user_org,
            project_code=body.project_code,
            build_type=body.build_type
        )

        return {
            "message": "Standard workflow template generated successfully",
            "template": {
                "name": "standard-pipeline",
                "content": template,
                "description": f"Standard pipeline that calls reusable workflow for {body.build_type} projects"
            }
        }

    except Exception as e:
        print(f"❌ Error generating standard template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workflow-templates/reusable", responses=_responses(500))
def generate_reusable_template(request: Request, body: WorkflowTemplateRequest, db: Annotated[Session, Depends(get_db)]):
    """Generate just the reusable workflow template."""
    auth_module.resolve_authenticated_user(request, db)
    try:
        template = generate_reusable_workflow_template(
            build_type=body.build_type,
            project_code=body.project_code
        )

        return {
            "message": "Reusable workflow template generated successfully",
            "template": {
                "name": "main-workflow",
                "content": template,
                "description": f"Main reusable workflow for {body.build_type} projects"
            }
        }

    except Exception as e:
        print(f"❌ Error generating reusable template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/sync-workflow")
async def sync_workflow(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Syncs a workflow to all repositories that don't have it"""
    try:
        data = await request.json()
        user = data.get("user")
        repo_names = data.get("repo_names", [])
        workflow_name = data.get("workflow_name", "").strip()

        if user not in user_tokens:
            return {"error": NOT_AUTHENTICATED_DETAIL, "status": 401}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        async with httpx.AsyncClient() as client:
            workflow_content, existing_workflows = await _fetch_existing_workflow_content(
                client, repo_names, workflow_name, headers
            )

            if workflow_content is None:
                return {"error": f"Workflow '{workflow_name}' not found in any repository", "status": 404}

            results, created_count = await _create_missing_workflows(
                client, repo_names, existing_workflows, workflow_name, workflow_content, headers
            )

        return {
            "message": f"✅ Workflow '{workflow_name}' synced! Created in {created_count} repositories.",
            "results": results
        }

    except Exception as e:
        print(f"❌ Error syncing workflow: {str(e)}")
        return {"error": str(e), "status": 500}


async def _fetch_existing_workflow_content(client, repo_names, workflow_name, headers):
    """Return (workflow_content, existing_workflows) discovered across ``repo_names``.

    ``workflow_content`` is the decoded text from the first repo that already
    contains the workflow, or ``None`` if no repo has it.
    """
    workflow_content = None
    existing_workflows: dict = {}
    workflow_path = f".github/workflows/{workflow_name}.yml"

    for repo_name in repo_names:
        owner, repo = repo_name.split("/")
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{workflow_path}"
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            continue
        content_data = response.json()
        if workflow_content is None:
            workflow_content = base64.b64decode(content_data["content"]).decode("utf-8")
        existing_workflows[repo_name] = True

    return workflow_content, existing_workflows


async def _create_missing_workflows(
    client, repo_names, existing_workflows, workflow_name, workflow_content, headers
):
    """Create the workflow file in each repo of ``repo_names`` that lacks it."""
    results: dict = {}
    created_count = 0
    workflow_path = f".github/workflows/{workflow_name}.yml"
    content_base64 = base64.b64encode(workflow_content.encode()).decode()

    for repo_name in repo_names:
        if repo_name in existing_workflows:
            results[repo_name] = "already exists"
            continue

        owner, repo = repo_name.split("/")
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{workflow_path}"
        workflow_data = {
            "message": f"Add {workflow_name} workflow via ActionsManager sync",
            "content": content_base64,
            "branch": "main"  # Default to main branch
        }
        response = await client.put(url, json=workflow_data, headers=headers)
        if response.status_code in [200, 201]:
            results[repo_name] = "created"
            created_count += 1
        else:
            results[repo_name] = f"failed ({response.status_code})"

    return results, created_count


@router.get("/api/workflows-count")
async def get_workflows_count(user: str, project_name: str, db: Annotated[Session, Depends(get_db)]):
    """Get the count of regular workflows for a project"""
    try:
        print(f"📌 Getting workflows count for user={user}, project={project_name}")
        
        if user not in user_tokens:
            return {"error": NOT_AUTHENTICATED_DETAIL, "status": 401}
        
        project = _find_project_by_name(db, user, project_name)
        
        if not project:
            return {"error": PROJECT_ERROR, "status": 404}
        
        # Count regular workflows for this project
        workflow_count = count_project_workflows(user, project_name)
        
        print(f"✅ Found {workflow_count} regular workflows for project {project_name}")
        return {"count": workflow_count}
        
    except Exception as e:
        print(f"❌ Error getting workflows count: {str(e)}")
        return {"error": str(e), "status": 500}


@router.get("/api/rxworkflows-count")
async def get_rxworkflows_count(user: str, project_name: str, db: Annotated[Session, Depends(get_db)]):
    """Get the count of reusable workflows for a project"""
    try:
        print(f"📌 Getting reusable workflows count for user={user}, project={project_name}")
        
        if user not in user_tokens:
            return {"error": NOT_AUTHENTICATED_DETAIL, "status": 401}
        
        project = _find_project_by_name(db, user, project_name)
        
        if not project:
            return {"error": PROJECT_ERROR, "status": 404}
        
        # Count reusable workflows for this project
        workflow_count = count_project_reusable_workflows(user, project_name)
        
        print(f"✅ Found {workflow_count} reusable workflows for project {project_name}")
        return {"count": workflow_count}
        
    except Exception as e:
        print(f"❌ Error getting reusable workflows count: {str(e)}")
        return {"error": str(e), "status": 500}


# ========== Workflow Version History API Endpoints ==========

class WorkflowVersionResponse(BaseModel):
    version_id: int
    version_number: int
    content: str
    metadata: Optional[str] = None
    created_at: str

class VersionHistoryResponse(BaseModel):
    workflow_id: int
    workflow_name: str
    versions: List[WorkflowVersionResponse]
    total_versions: int

class RestoreVersionRequest(BaseModel):
    github_user: str
    project_name: str
    workflow_name: str
    version_id: int

@router.get("/api/workflows/{workflow_name}/versions", responses=_responses(401, 404, 500))
async def get_workflow_versions(
    workflow_name: str,
    user: str,
    project_name: str,
    db: Annotated[Session, Depends(get_db)]
):
    """Get all version history for a specific workflow"""
    try:
        print(f"📌 Getting version history for workflow '{workflow_name}' in project '{project_name}'")
        
        if user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
        
        project = _find_project_by_name(db, user, project_name)
        
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)
        
        # Find workflow within this project
        workflow = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.workflow_name == workflow_name
        ).first()
        
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow '{workflow_name}' not found in project")
        
        # Get all versions for this workflow
        versions = db.query(WorkflowVersion).filter(
            WorkflowVersion.workflow_id == workflow.workflow_id
        ).order_by(WorkflowVersion.version_number.desc()).all()
        
        version_list = [
            WorkflowVersionResponse(
                version_id=v.version_id,
                version_number=v.version_number,
                content=v.content,
                metadata=v.version_metadata,
                created_at=v.created_at.isoformat() if v.created_at else None
            )
            for v in versions
        ]
        
        print(f"✅ Found {len(versions)} versions for workflow '{workflow_name}'")
        
        return VersionHistoryResponse(
            workflow_id=workflow.workflow_id,
            workflow_name=workflow.workflow_name,
            versions=version_list,
            total_versions=len(versions)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting workflow versions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workflows/{workflow_name}/versions/{version_id}", responses=_responses(401, 404, 500))
async def get_workflow_version(
    workflow_name: str,
    version_id: int,
    user: str,
    project_name: str,
    db: Annotated[Session, Depends(get_db)]
):
    """Get a specific version of a workflow"""
    try:
        print(f"📌 Getting version {version_id} for workflow '{workflow_name}'")
        
        if user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
        
        project = _find_project_by_name(db, user, project_name)
        
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)
        
        # Find workflow within this project
        workflow = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.workflow_name == workflow_name
        ).first()
        
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow '{workflow_name}' not found")
        
        # Get specific version
        version = db.query(WorkflowVersion).filter(
            WorkflowVersion.version_id == version_id,
            WorkflowVersion.workflow_id == workflow.workflow_id
        ).first()
        
        if not version:
            raise HTTPException(status_code=404, detail=f"Version {version_id} not found")
        
        print(f"✅ Retrieved version {version.version_number} for workflow '{workflow_name}'")
        
        return WorkflowVersionResponse(
            version_id=version.version_id,
            version_number=version.version_number,
            content=version.content,
            metadata=version.version_metadata,
            created_at=version.created_at.isoformat() if version.created_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting workflow version: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workflows/restore-version", responses=_responses(401, 404, 500))
async def restore_workflow_version(
    payload: RestoreVersionRequest,
    db: Annotated[Session, Depends(get_db)]
):
    """Restore a workflow to a previous version"""
    try:
        print(f"📌 Restoring workflow '{payload.workflow_name}' to version {payload.version_id}")
        
        if payload.github_user not in user_tokens:
            raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
        
        project = _find_project_by_name(db, payload.github_user, payload.project_name)
        
        if not project:
            raise HTTPException(status_code=404, detail=PROJECT_ERROR)
        
        # Find workflow within this project
        workflow = db.query(Workflow).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.project_id,
            Workflow.workflow_name == payload.workflow_name
        ).first()
        
        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow '{payload.workflow_name}' not found")
        
        # Get the version to restore
        version = db.query(WorkflowVersion).filter(
            WorkflowVersion.version_id == payload.version_id,
            WorkflowVersion.workflow_id == workflow.workflow_id
        ).first()
        
        if not version:
            raise HTTPException(status_code=404, detail=f"Version {payload.version_id} not found")
        
        # Restore the workflow content from this version
        workflow.workflow_yaml = version.content
        workflow.workflow_git_hash = "0000000000000000000000000000000000000000"
        db.commit()
        
        # Create a new version entry to track this restoration
        create_workflow_version(
            db,
            workflow.workflow_id,
            version.content,
            metadata={
                'action': 'restore',
                'restored_from_version': version.version_number,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        )
        
        print(f"✅ Restored workflow '{payload.workflow_name}' to version {version.version_number}")
        
        return {
            "message": f"Workflow restored to version {version.version_number}",
            "workflow_name": workflow.workflow_name,
            "restored_version": version.version_number,
            "restored_content": version.content
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error restoring workflow version: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
