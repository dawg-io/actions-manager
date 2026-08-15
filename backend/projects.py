import hashlib
import json
import pathlib
import random
import re
import string
import traceback
from typing import Annotated, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query, Path, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import func, union_all
from pydantic import BaseModel, field_validator
from github_api_tracker import github_get
from auth import user_tokens, resolve_optional_session_user
from models import (
    Project,
    Account,
    Repo,
    Workflow,
    ProjectRepo,
    ProjectWorkflow,
    LinkedReusableWorkflow,
    ProjectPullRequest,
    ProjectMembership,
    WorkflowVersion,
    ProjectRuleset,
    Ruleset,
    Codeowners,
    RepoWorkflowOverride,
    CustomFile,
    WorkflowDriftState,
    ProjectDisplayOrder,
    generate_project_key_from_name,
)
from database import get_db
from workflows import (
    cleanup_orphaned_workflows,
    format_workflow_name,
    resolve_branch_config_for_repo,
    _normalize_reusable_workflow_name,
    _reusable_workflow_ids_locked_by_open_campaign,
)
from tier_service import check_project_limit, check_project_type_limit, check_repo_limit, check_private_visibility_scope
from authorization import check_project_access, is_project_admin
from models import WorkspaceMember
from reusable_workflow_visibility import (
    reusable_workflow_validation_payload,
    validate_reusable_workflow_link,
)

router = APIRouter()

_ERR_AUTH_REQUIRED = "Authentication required"

# Error responses these endpoints can return, declared on each route so they
# appear in the OpenAPI schema (and so generated clients know about them).
# Codes raised inside shared helpers count too - the rule tracks the call.
_ERROR_RESPONSES = {
    400: {"description": "Invalid request"},
    401: {"description": _ERR_AUTH_REQUIRED},
    403: {"description": "Access denied"},
    404: {"description": "Not found"},
    422: {"description": "Request failed validation"},
    500: {"description": "Internal server error"},
}


def _responses(*codes: int) -> dict:
    """Subset of _ERROR_RESPONSES for a route's `responses=` parameter."""
    return {code: _ERROR_RESPONSES[code] for code in codes}


GITHUB_USER_NOT_FOUND = "GitHub user not found"
_ERR_PROJECT_NOT_FOUND = "Project not found or access denied"
_ERR_PROJECT_NOT_FOUND_PLAIN = "Project not found"
_ERR_NO_ACCESS = "You do not have access to this project"
_ERR_INTERNAL_VALIDATION = "Internal server error during project validation"
_ERR_INSUFFICIENT_PROJECT_ROLE = "Insufficient project permissions. Required: project_editor"
BACKUP_SCHEMA_VERSION = "1.1"
APP_NAME = "ActionsManager"


def _read_app_version() -> str:
    """Read the release version from VERSION at the repo root (../VERSION
    from this file). Only promote-to-public.yml ever writes a real value
    there, and only on release/<version> branches - everywhere else (local
    dev, dev/CI Docker images without repo-root in their build context)
    this stays a placeholder or falls back to "dev"."""
    try:
        return (pathlib.Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
    except OSError:
        return "dev"


APP_VERSION = _read_app_version()

# Allowed values for Project.repository_visibility_scope. A "mixed" option is
# intentionally NOT included — projects must be either public-only or
# private-only.
ALLOWED_VISIBILITY_SCOPES = ("public", "private")

# Allowed values for Project.project_color (project identity accent only).
# Purple and green are intentionally reserved for Reusable Workflow (rwx)
# projects; Caller Workflow (standard) projects may use the remaining colors.
RWX_ONLY_PROJECT_COLORS = ("purple", "green")
ALLOWED_PROJECT_COLORS = (
    "blue",
    "purple",
    "green",
    "amber",
    "rose",
    "cyan",
    "slate",
    "orange",
    "sky",
)
STANDARD_PROJECT_COLORS = tuple(
    color for color in ALLOWED_PROJECT_COLORS if color not in RWX_ONLY_PROJECT_COLORS
)

# Per-project drift cadence presets, in minutes. 0 means "never check this
# project"; omitting the value entirely (None) inherits the workspace default.
ALLOWED_DRIFT_INTERVAL_MINUTES = (0, 15, 30, 60, 360, 1440)


def _enforce_project_color_type_restriction(
    project_type: str | None,
    requested_color: str | None,
    existing_color: str | None = None,
) -> None:
    """Enforce mutually exclusive color palettes per project type.

    - RWX (Reusable Workflow) projects may only use purple/green.
    - Standard (Caller Workflow) projects may only use the remaining six.

    Standard projects that already had an RWX-only color before this
    restriction existed are grandfathered: re-submitting the unchanged
    color is allowed, but switching to a (different) RWX-only color is not.
    """
    if requested_color is None:
        return
    effective_type = project_type or "standard"
    if effective_type == "rwx":
        if requested_color in RWX_ONLY_PROJECT_COLORS:
            return
        if existing_color is not None and requested_color == existing_color:
            return  # Grandfathered pre-restriction color left unchanged
        raise HTTPException(
            status_code=422,
            detail=(
                f"project_color '{requested_color}' is not available for Reusable Workflow Projects. "
                f"Reusable Workflow Projects may use: {', '.join(RWX_ONLY_PROJECT_COLORS)}"
            ),
        )
    # Standard project
    if requested_color not in RWX_ONLY_PROJECT_COLORS:
        return
    if existing_color is not None and requested_color == existing_color:
        return  # Grandfathered pre-restriction color left unchanged
    raise HTTPException(
        status_code=422,
        detail=(
            f"project_color '{requested_color}' is reserved for Reusable Workflow Projects. "
            f"Caller Workflow Projects may use: {', '.join(STANDARD_PROJECT_COLORS)}"
        ),
    )


def _resolve_caller(db: Session, x_github_user: Optional[str]):
    """Look up the calling user's Account and WorkspaceMember from the
    ``X-GitHub-User`` header value.

    Returns ``(account, workspace_member)`` or ``(None, None)`` if no
    header / user not found.
    """
    if not x_github_user:
        return None, None
    caller = db.query(Account).filter(Account.github_user == x_github_user).first()
    if not caller:
        return None, None
    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == caller.user_id)
        .first()
    )
    return caller, member


def _find_project_by_id(db: Session, project_id: int, caller_member, github_user: str = None):
    """Look up a project by *project_id*, considering the caller's access.

    Privileged workspace members (admin) can access any project.
    Members fall through to ProjectMembership lookup.
    Other users fall back to ownership-based lookup.

    Returns the Project or ``None``.
    """
    if caller_member and is_project_admin(caller_member):
        # Privileged users — find by ID alone (no ownership filter)
        return db.query(Project).filter(Project.project_id == project_id).first()

    # Non-admin members (member, read_only): check ProjectMembership for explicit project access
    if caller_member:
        pm = db.query(ProjectMembership).filter(
            ProjectMembership.user_id == caller_member.user_id,
            ProjectMembership.project_id == project_id,
        ).first()
        if pm:
            return db.query(Project).filter(Project.project_id == project_id).first()

    # Fallback: try ownership check for backward compat
    if github_user:
        user = db.query(Account).filter(Account.github_user == github_user.strip()).first()
        if user:
            return db.query(Project).filter(
                Project.project_id == project_id,
                Project.user_id == user.user_id,
            ).first()
    return None


def _find_project_by_name(db: Session, project_name: str, caller_member, github_user: str = None):
    """Look up a project by *project_name*, considering the caller's access.

    Privileged workspace members (admin) can access any project.
    To avoid ambiguity when ``project_name`` is not globally unique, the
    lookup first tries the owner-scoped query (using *github_user*) and
    only falls back to a global name match when that does not produce a
    result.

    Members fall through to ProjectMembership-based lookup.
    Other users fall back to ownership-based lookup.

    Returns the Project or ``None``.
    """
    if caller_member and is_project_admin(caller_member):
        # Privileged users — try owner-scoped lookup first for disambiguation
        if github_user:
            owner = db.query(Account).filter(Account.github_user == github_user.strip()).first()
            if owner:
                project = db.query(Project).filter(
                    Project.project_name.ilike(project_name.strip()),
                    Project.user_id == owner.user_id,
                ).first()
                if project:
                    return project
        # Fallback: global name match (single-workspace model)
        return db.query(Project).filter(
            Project.project_name.ilike(project_name.strip())
        ).first()

    # Non-admin members (member, read_only): check ProjectMembership for explicit project access
    if caller_member and caller_member.workspace_role in ("member", "read_only"):
        project = db.query(Project).join(
            ProjectMembership, ProjectMembership.project_id == Project.project_id
        ).filter(
            Project.project_name.ilike(project_name.strip()),
            ProjectMembership.user_id == caller_member.user_id,
        ).first()
        if project:
            return project

    # Non-privileged: ownership check required
    if github_user:
        user = db.query(Account).filter(Account.github_user == github_user.strip()).first()
        if user:
            return db.query(Project).filter(
                Project.project_name.ilike(project_name.strip()),
                Project.user_id == user.user_id,
            ).first()
    return None

# ✅ Define Schema for Workflows
class WorkflowSchema(BaseModel):
    name: str
    content: str

# ✅ Define Schema for Project
class ProjectSchema(BaseModel):
    project_name: str
    custom_project_key: str | None = None  # Optional custom project key input from user
    selected_repos: list[str]
    workflows: list[WorkflowSchema]
    rxworkflows: list[WorkflowSchema] = [] 
    github_user: Optional[str] = None
    branch_regex: str = ""
    branch_option: str = "default"  # default, pattern
    branch_max_age_days: int = 30  # Filter branches by recency (1-30 days)
    reusable_workflows_enabled: bool = False  # Include reusable workflows setting
    use_prefix: bool = True  # Whether to use AM_{PROJECT_CODE}_ prefix (default: True)
    project_type: str = "standard"  # Project type: standard, rwx
    repository_visibility_scope: str = "public"  # Repository visibility scope: public, private
    project_color: str | None = None  # Project identity color key (decorative accent only)
    validation_repo: str | None = None
    preflight_required: bool = False

    @field_validator("repository_visibility_scope")
    @classmethod
    def _validate_visibility_scope(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in ALLOWED_VISIBILITY_SCOPES:
            raise ValueError(
                f"repository_visibility_scope must be one of: {', '.join(ALLOWED_VISIBILITY_SCOPES)}"
            )
        return normalized

    @field_validator("project_color")
    @classmethod
    def _validate_project_color(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip().lower()
        if not normalized:
            return None
        if normalized not in ALLOWED_PROJECT_COLORS:
            raise ValueError(
                f"project_color must be one of: {', '.join(ALLOWED_PROJECT_COLORS)}"
            )
        return normalized

    @field_validator("validation_repo")
    @classmethod
    def _validate_validation_repo(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip()
        if not normalized:
            return None
        if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", normalized):
            raise ValueError("validation_repo must use owner/repo format")
        return normalized


class ProjectOrderUpdateSchema(BaseModel):
    """Payload for saving a user's manual Projects-grid order (issue #1804).

    Local display metadata only — no GitHub writes and no change to any project
    row, so projects.updated_at is untouched.
    """

    github_user: Optional[str] = None
    project_ids: List[int]

    @field_validator("project_ids")
    @classmethod
    def _validate_project_ids(cls, v: List[int]) -> List[int]:
        if not v:
            raise ValueError("project_ids must not be empty")
        if len(set(v)) != len(v):
            raise ValueError("project_ids must not contain duplicates")
        return v


class ProjectColorUpdateSchema(BaseModel):
    """Patch-style payload for updating only a project's identity color.

    This is local ActionsManager metadata and must not trigger any GitHub writes.
    """

    github_user: Optional[str] = None
    project_color: str | None = None

    @field_validator("project_color")
    @classmethod
    def _validate_project_color(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip().lower()
        if not normalized:
            return None
        if normalized not in ALLOWED_PROJECT_COLORS:
            raise ValueError(
                f"project_color must be one of: {', '.join(ALLOWED_PROJECT_COLORS)}"
            )
        return normalized


class ProjectDriftConfigUpdateSchema(BaseModel):
    """Patch-style payload for how often this project is swept for drift.

    ``None`` inherits the workspace default, ``0`` turns automatic checks off,
    and anything else is minutes between checks. The value is restricted to the
    presets the UI offers so a hand-crafted request cannot set a 1-minute sweep
    and burn the install's GitHub rate limit.
    """

    github_user: Optional[str] = None
    drift_check_interval_minutes: Optional[int] = None

    @field_validator("drift_check_interval_minutes")
    @classmethod
    def _validate_interval(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if v not in ALLOWED_DRIFT_INTERVAL_MINUTES:
            allowed = ", ".join(str(i) for i in sorted(ALLOWED_DRIFT_INTERVAL_MINUTES))
            raise ValueError(f"drift_check_interval_minutes must be one of: {allowed}")
        return v


class ProjectNameUpdateSchema(BaseModel):
    """Patch-style payload for updating only a project's display name.

    project_code is intentionally absent — it must never change after creation.
    """

    github_user: Optional[str] = None
    project_name: str

    @field_validator("project_name")
    @classmethod
    def _validate_project_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("project_name must not be empty")
        return stripped


class ReusableWorkflowToggleSchema(BaseModel):
    github_user: Optional[str] = None
    project_name: str
    enabled: bool

class LinkWorkflowSchema(BaseModel):
    github_user: Optional[str] = None
    workflow_id: int
    rwx_project_id: int


class UpdateLinkedWorkflowSchema(BaseModel):
    """Payload for updating the YAML of a linked reusable workflow.

    The canonical workflow is resolved by the ``workflow_id`` path parameter
    and the ``LinkedReusableWorkflow`` row joining it to the standard
    consuming project — never by ``workflow_name``.
    """
    github_user: Optional[str] = None
    content: str


# ✅ Generate a unique 4-character project_code (legacy)
def generate_unique_code(db):
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if not db.query(Project).filter(Project.project_code == code).first():
            return code

def _clean_custom_key(custom_key: str | None) -> str | None:
    """Sanitize a user-supplied project key. Returns None if the result is too short."""
    if not custom_key:
        return None
    cleaned = re.sub(r'[^A-Z0-9]', '', custom_key.upper())
    if len(cleaned) > 9:  # Leave room for at least 1 digit
        cleaned = cleaned[:9]
    return cleaned if len(cleaned) >= 2 else None


# ✅ Generate a unique project key (either from name or custom)
def generate_unique_project_key(db, project_name, custom_key=None):
    """Generate a unique project key, preferring custom key if provided"""
    cleaned = _clean_custom_key(custom_key)

    if cleaned:
        # For custom keys, try with numbers starting from 1
        for i in range(1, 100):
            test_key = f"{cleaned}{i}"
            if len(test_key) <= 10 and not db.query(Project).filter(Project.project_code == test_key).first():
                return test_key

    # Generate from project name - always include number suffix
    base_key = generate_project_key_from_name(project_name)

    # Always try with numbers starting from 1 (e.g., MCP1, MCP2, etc.)
    for i in range(1, 100):
        test_key = f"{base_key}{i}"
        if len(test_key) <= 10 and not db.query(Project).filter(Project.project_code == test_key).first():
            return test_key

    # Fallback to old random generation
    return generate_unique_code(db)

def create_workflow_version_in_projects(db, workflow_id, content, metadata=None):
    """
    Thin wrapper around `workflows.create_workflow_version` to avoid
    duplicating versioning logic while keeping a local helper in this module.
    """
    # Import inside the function to minimize the risk of circular imports.
    from workflows import create_workflow_version as _create_workflow_version
    return _create_workflow_version(db, workflow_id, content, metadata)

def create_or_update_workflow(db, workflow, project_id, is_reusable, last_modified_by=None):
    """
    Create or update a workflow within the scope of a specific project.
    This ensures that each project maintains its own workflows without creating duplicates.
    Automatically creates a version entry on each save.
    """
    print(f"✅ Creating/updating workflow '{workflow.name}' for project {project_id}, reusable: {is_reusable}")
    
    # 🔧 FIX: Search for existing workflow within the current project only
    existing_workflow = db.query(Workflow).join(ProjectWorkflow).filter(
        ProjectWorkflow.project_id == project_id,
        # Case-insensitive equality rather than ILIKE: '_' is a wildcard in SQL
        # LIKE, so "ci_build" would match and overwrite an unrelated "ciXbuild".
        func.lower(Workflow.workflow_name) == workflow.name.strip().lower(),
        Workflow.reusable_workflow == is_reusable
    ).first()

    if existing_workflow:
        print(f"📌 ✅ Updating existing workflow in project: {existing_workflow.workflow_name}")
        existing_workflow.workflow_yaml = workflow.content.strip()
        existing_workflow.reusable_workflow = is_reusable
        # Set hash to zeros to indicate local modification (user doesn't use git locally)
        existing_workflow.workflow_git_hash = "0000000000000000000000000000000000000000"
        # Audit: record who made this change
        if last_modified_by:
            existing_workflow.last_modified_by = last_modified_by
        db.commit()
        print(f"✅ Set git hash to zeros (local modification)")
        
        # Create version entry for this update
        create_workflow_version_in_projects(
            db, 
            existing_workflow.workflow_id, 
            workflow.content.strip(),
            metadata={'action': 'update', 'timestamp': datetime.now(timezone.utc).isoformat()}
        )
        
        return existing_workflow
    else:
        print(f"📌 Creating new workflow for project: {workflow.name.strip()}")
        new_workflow = Workflow(
            workflow_name=workflow.name.strip(),
            workflow_yaml=workflow.content.strip(),
            reusable_workflow=is_reusable,
            # Set hash to zeros for new workflows (not yet pushed to GitHub)
            workflow_git_hash="0000000000000000000000000000000000000000",
            # Audit: record who created this workflow
            last_modified_by=last_modified_by
        )
        db.add(new_workflow)
        db.commit()
        db.refresh(new_workflow)
        
        # Create project association for new workflow
        db.add(ProjectWorkflow(
            project_id=project_id,
            workflow_id=new_workflow.workflow_id
        ))
        db.commit()
        print(f"✅ Created new workflow '{workflow.name}' (ID: {new_workflow.workflow_id}) for project {project_id}")
        print(f"✅ Set git hash to zeros (new workflow, not yet pushed)")
        
        # Create initial version entry for this new workflow
        create_workflow_version_in_projects(
            db, 
            new_workflow.workflow_id, 
            workflow.content.strip(),
            metadata={'action': 'create', 'timestamp': datetime.now(timezone.utc).isoformat()}
        )
        
        return new_workflow


def update_project_state_if_needed(project: Project, workflows: List, rxworkflows: List = None) -> None:
    """
    Update project state based on workflow changes.
    Transitions: new → draft, synced → draft when workflows are saved.
    
    Args:
        project: The project to update
        workflows: List of regular workflows being saved
        rxworkflows: List of reusable workflows being saved (optional)
    """
    all_workflows = list(workflows) + list(rxworkflows or [])
    has_workflows = any(w.name and w.name.strip() and w.content and w.content.strip() for w in all_workflows)
    if has_workflows and project.pr_state in ["new", "synced"]:
        project.pr_state = "draft"
        print(f"✅ Updated project state to 'draft' (workflows saved)")


def _validate_create_request(db: Session, project: ProjectSchema, github_user: str) -> Account:
    """Verify the user exists and enforce all account-based limits.

    Returns the matching Account on success, or raises an HTTPException.
    """
    from tier_service import is_self_hosted_beta

    user = db.query(Account).filter(Account.github_user == github_user.strip()).first()
    if not user:
        print(f"❌ POST /api/projects/ - GitHub user '{github_user}' not found")
        raise HTTPException(status_code=404, detail=GITHUB_USER_NOT_FOUND)

    user_projects_count = db.query(Project).filter(Project.user_id == user.user_id).count()

    if is_self_hosted_beta():
        # In self-hosted beta, enforce per-type limits (4 standard / 2 rwx)
        standard_count = (
            db.query(Project)
            .filter(Project.user_id == user.user_id, Project.project_type == "standard")
            .count()
        )
        rwx_count = (
            db.query(Project)
            .filter(Project.user_id == user.user_id, Project.project_type == "rwx")
            .count()
        )
        project_type = project.project_type or "standard"
        allowed, error_msg = check_project_type_limit(standard_count, rwx_count, project_type)
        if not allowed:
            print(f"❌ POST /api/projects/ - Beta project-type limit exceeded for user '{github_user}'")
            raise HTTPException(status_code=403, detail=error_msg)
    else:
        allowed, error_msg = check_project_limit(user, user_projects_count)
        if not allowed:
            print(f"❌ POST /api/projects/ - Project limit exceeded for user '{github_user}'")
            raise HTTPException(status_code=403, detail=error_msg)

    # Tier-gate the new repository_visibility_scope: Free tier accounts may only
    # create public-scope projects. Professional and Enterprise can create either.
    if project.repository_visibility_scope == "private":
        allowed, error_msg = check_private_visibility_scope(user)
        if not allowed:
            print(
                f"❌ POST /api/projects/ - Private visibility scope blocked for user "
                f"'{github_user}' on current tier"
            )
            raise HTTPException(status_code=403, detail=error_msg)

    # Private repositories are part of the core product and are available on
    # every tier (including Free), so we no longer gate on private repo access
    # here. Only the per-project repo count and per-account project count are
    # enforced as scale-based limits.

    allowed, error_msg = check_repo_limit(user, len(project.selected_repos))
    if not allowed:
        print(f"❌ POST /api/projects/ - Repo limit exceeded for user '{github_user}'")
        raise HTTPException(status_code=403, detail=error_msg)

    return user


def _get_or_create_project(db: Session, user_id: int, project: ProjectSchema) -> Project:
    """Fetch an existing project by name or create a new one.

    Flushes to obtain a primary key for new records but leaves the final
    commit to the caller so the whole request stays in one transaction.
    """
    existing_project = db.query(Project).filter(
        Project.project_name.ilike(project.project_name.strip()),
        Project.user_id == user_id
    ).first()

    if existing_project:
        if "project_color" in project.model_fields_set:
            _enforce_project_color_type_restriction(
                existing_project.project_type,
                project.project_color,
                existing_project.project_color,
            )
        existing_project.branch_regex = project.branch_regex.strip()
        existing_project.branch_option = project.branch_option.strip()
        existing_project.branch_max_age_days = project.branch_max_age_days
        existing_project.reusable_workflows_enabled = project.reusable_workflows_enabled
        existing_project.use_prefix = project.use_prefix
        existing_project.repository_visibility_scope = project.repository_visibility_scope
        if "project_color" in project.model_fields_set:
            existing_project.project_color = project.project_color
        # Explicitly update the updated_at timestamp to ensure it reflects the save operation
        existing_project.updated_at = func.now()
    else:
        if "project_color" in project.model_fields_set:
            _enforce_project_color_type_restriction(project.project_type, project.project_color)
        # Generate project key based on name and custom input
        project_key = generate_unique_project_key(db, project.project_name, project.custom_project_key)
        existing_project = Project(
            project_name=project.project_name.strip(),
            user_id=user_id,
            branch_regex=project.branch_regex.strip(),
            branch_option=project.branch_option.strip(),
            branch_max_age_days=project.branch_max_age_days,
            project_code=project_key,
            reusable_workflows_enabled=project.reusable_workflows_enabled,
            project_type=project.project_type,
            repository_visibility_scope=project.repository_visibility_scope,
        )
        if "project_color" in project.model_fields_set:
            existing_project.project_color = project.project_color
        # Explicitly set use_prefix after object creation to ensure it's not ignored
        existing_project.use_prefix = project.use_prefix
        db.add(existing_project)

    db.flush()
    db.refresh(existing_project)
    return existing_project


def _process_project_repos(db: Session, project_id: int, selected_repos: list[str]) -> None:
    """Sync project repo associations from ``selected_repos``.

    Preserves any per-repository branch override columns on rows that
    remain in the project. Rows that are no longer selected are removed
    (the cascade also drops their override config); newly selected repos
    are added with the default ``"inherit"`` mode.
    """
    desired_names = {name.strip() for name in selected_repos if name and name.strip()}

    existing_assocs = (
        db.query(ProjectRepo).filter(ProjectRepo.project_id == project_id).all()
    )
    existing_repo_ids = {a.repo_id for a in existing_assocs}

    # Resolve repo objects for each desired name (creating Repo rows as needed)
    desired_repo_ids = set()
    for repo_name in desired_names:
        repo = db.query(Repo).filter(Repo.repo_name == repo_name).first()
        if not repo:
            repo = Repo(repo_name=repo_name)
            db.add(repo)
            db.flush()
            db.refresh(repo)
        desired_repo_ids.add(repo.repo_id)
        if repo.repo_id not in existing_repo_ids:
            db.add(ProjectRepo(
                project_id=project_id,
                repo_id=repo.repo_id,
                branch_config_mode="inherit",
            ))

    # Remove associations (and their override config) for repos no longer
    # selected; the FK cascade on project_repos itself isn't involved here —
    # we just delete the join row directly.
    for assoc in existing_assocs:
        if assoc.repo_id not in desired_repo_ids:
            db.delete(assoc)


def _repo_name_for_id(db: Session, repo_id: int | None) -> str | None:
    if not repo_id:
        return None
    repo = db.query(Repo).filter(Repo.repo_id == repo_id).first()
    return repo.repo_name if repo else None


def _sync_validation_repo(db: Session, project_row: Project, project: ProjectSchema, github_user: str, preserve_unset: bool = False) -> None:
    """Persist optional validation repo metadata separately from target repos."""
    repo_provided = "validation_repo" in project.model_fields_set
    required_provided = "preflight_required" in project.model_fields_set
    if preserve_unset and not repo_provided and not required_provided:
        return

    repo_name = project.validation_repo if repo_provided else _repo_name_for_id(db, project_row.validation_repo_id)
    if not repo_name:
        project_row.validation_repo_id = None
        project_row.preflight_required = False
        project_row.last_preflight_status = None
        project_row.last_preflight_run_at = None
        project_row.last_preflight_error = None
        project_row.last_preflight_pr_url = None
        return

    token = user_tokens.get(github_user.strip())
    if token:
        owner, repo = repo_name.split("/", 1)
        response = github_get(
            f"https://api.github.com/repos/{owner}/{repo}",
            github_user.strip(),
            db,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Authorization": f"token {token}",
            },
            timeout=30,
        )
        if response.status_code == 404:
            raise HTTPException(status_code=400, detail="Validation repository is not accessible.")
        if response.status_code == 403:
            raise HTTPException(status_code=403, detail="Missing access to validation repository.")
        if response.status_code >= 400:
            raise HTTPException(status_code=400, detail="Unable to validate repository access.")

    repo_row = db.query(Repo).filter(Repo.repo_name == repo_name).first()
    if not repo_row:
        repo_row = Repo(repo_name=repo_name)
        db.add(repo_row)
        db.flush()
        db.refresh(repo_row)

    if project_row.validation_repo_id != repo_row.repo_id:
        project_row.last_preflight_status = "not_run"
        project_row.last_preflight_run_at = None
        project_row.last_preflight_error = None
        project_row.last_preflight_pr_url = None
    elif not project_row.last_preflight_status:
        project_row.last_preflight_status = "not_run"
    project_row.validation_repo_id = repo_row.repo_id
    if not preserve_unset or required_provided:
        project_row.preflight_required = bool(project.preflight_required)


def _is_workflow_non_empty(workflow) -> bool:
    """Return True if the workflow has a non-blank name and non-blank content."""
    return bool(workflow.name and workflow.name.strip() and workflow.content and workflow.content.strip())


def _process_project_workflows(db: Session, project: ProjectSchema, project_id: int, last_modified_by: str = None) -> None:
    """Process regular and (optionally) reusable workflows for a project.

    Empty workflow entries (blank name or content) are skipped.
    Reusable workflows are only processed when the feature is enabled on the project.
    """
    # Process regular workflows - skip empty ones
    for workflow in project.workflows:
        if _is_workflow_non_empty(workflow):
            print(f"✅ ✅ REG workflow: name='{workflow.name}', content_length={len(workflow.content)}")
            create_or_update_workflow(db, workflow, project_id, is_reusable=False, last_modified_by=last_modified_by)
        else:
            print(f"⚠️ Skipping empty regular workflow: name='{workflow.name}', content_length={len(workflow.content) if workflow.content else 0}")

    # Only process reusable workflows if the feature is enabled for this project
    if not project.reusable_workflows_enabled:
        print(f"⚠️ Skipping reusable workflows - feature disabled for project '{project.project_name}'")
        return

    for workflow in project.rxworkflows:
        if _is_workflow_non_empty(workflow):
            print(f"✅ RW workflow: name='{workflow.name}', content_length={len(workflow.content)}")
            create_or_update_workflow(db, workflow, project_id, is_reusable=True, last_modified_by=last_modified_by)
        else:
            print(f"⚠️ Skipping empty reusable workflow: name='{workflow.name}', content_length={len(workflow.content) if workflow.content else 0}")


@router.post(
    "/projects/",
    responses={
        **_responses(400, 401, 403, 404, 500),
        422: {"description": "Invalid project_color for this project type"},
    },
)
def create_project(
    project: ProjectSchema,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    github_user = x_github_user or (project.github_user or "")
    if not github_user:
        raise HTTPException(status_code=401, detail=_ERR_AUTH_REQUIRED)
    try:
        user = _validate_create_request(db, project, github_user)
        print(f"✅ POST /api/projects/ - Creating project '{project.project_name}' for user '{github_user}'")
    except HTTPException:
        # Re-raise HTTP exceptions (rollback not needed as validation only does reads)
        raise
    except Exception as e:
        print(f"❌ POST /api/projects/ - Unexpected error during validation: {e}")
        traceback.print_exc()
        db.rollback()  # Rollback any pending transaction for safety
        raise HTTPException(status_code=500, detail=_ERR_INTERNAL_VALIDATION)

    # Wrap the main creation logic in exception handling
    try:
        existing_project = _get_or_create_project(db, user.user_id, project)
        # Audit: record who created/saved this project
        existing_project.last_modified_by = github_user.strip()
        _process_project_repos(db, existing_project.project_id, project.selected_repos)
        _sync_validation_repo(db, existing_project, project, github_user=github_user)
        # Don't delete ProjectWorkflow associations - let create_or_update_workflow handle updates
        _process_project_workflows(db, project, existing_project.project_id, last_modified_by=github_user.strip())
        update_project_state_if_needed(existing_project, project.workflows, project.rxworkflows)
        db.commit()

        return {
            "message": "✅ Project saved successfully!",
            "project_id": existing_project.project_id,
            "project_code": existing_project.project_code,
            "pr_state": existing_project.pr_state,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        print(f"❌ POST /api/projects/ - Error during project creation: {e}")
        traceback.print_exc()
        db.rollback()  # Rollback the transaction on error
        raise HTTPException(status_code=500, detail="Internal server error during project creation")


def _require_project_editor(db: Session, caller_member, project_id: int) -> None:
    """Enforce that the caller has at least ``project_editor`` access to *project_id*.

    Admin workspace members always pass. Non-admin members must hold an explicit
    ``project_editor`` (or higher) ``ProjectMembership``; ``project_viewer`` members
    are rejected. Raises HTTPException(403) on failure.
    """
    if caller_member and not is_project_admin(caller_member):
        effective_role = check_project_access(db, caller_member, project_id)
        if effective_role is None:
            raise HTTPException(status_code=403, detail=_ERR_NO_ACCESS)
        if effective_role != "project_editor":
            raise HTTPException(status_code=403, detail=_ERR_INSUFFICIENT_PROJECT_ROLE)


@router.put(
    "/projects/order",
    responses={
        400: {"description": "Order does not match the caller's accessible projects"},
        401: {"description": _ERR_AUTH_REQUIRED},
        500: {"description": "Internal server error"},
    },
)
def update_project_order(
    payload: ProjectOrderUpdateSchema,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Save the caller's manual ordering of the Projects grid (issue #1804).

    Ordering is per user, so any user who can see a project may arrange it —
    including project_viewer. This changes no project data and no other user's
    view, so the project_editor gate the other write endpoints use would be
    wrong here. Access is still enforced: the submitted list must match the
    caller's accessible projects exactly.
    """
    try:
        caller_member = _resolve_caller_member(db, x_github_user)
        if caller_member is None:
            raise HTTPException(status_code=401, detail="Authentication required to save project order")

        accessible = _accessible_project_ids(db, caller_member)
        submitted = set(payload.project_ids)

        # An exact match is required. A partial list would silently drop
        # projects out of the saved order; unknown or inaccessible ids would let
        # a caller record positions for projects they cannot see.
        if submitted != accessible:
            unauthorized = submitted - accessible
            missing = accessible - submitted
            if unauthorized:
                detail = (
                    "project_ids contains projects that do not exist or are not "
                    f"accessible: {sorted(unauthorized)}"
                )
            else:
                detail = f"project_ids must list every accessible project; missing: {sorted(missing)}"
            raise HTTPException(status_code=400, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PUT /projects/order - Unexpected error during validation: {e}")
        raise HTTPException(status_code=500, detail=_ERR_INTERNAL_VALIDATION)

    try:
        # Full replace in one transaction, so a partly-applied order can never
        # be observed. No Project row is touched — updated_at must not move.
        db.query(ProjectDisplayOrder).filter(
            ProjectDisplayOrder.user_id == caller_member.user_id
        ).delete(synchronize_session=False)

        for position, project_id in enumerate(payload.project_ids):
            db.add(ProjectDisplayOrder(
                user_id=caller_member.user_id,
                project_id=project_id,
                position=position,
            ))
        db.commit()

        return {
            "message": "✅ Project order updated successfully!",
            "project_ids": payload.project_ids,
        }
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        print(f"❌ PUT /projects/order - Failed to save order: {e}")
        raise HTTPException(status_code=500, detail="Failed to save project order")


@router.put(
    "/projects/{project_id}/",
    responses={
        **_responses(400, 500),
        403: {"description": "Access denied"},
        404: {"description": _ERR_PROJECT_NOT_FOUND_PLAIN},
        422: {"description": "Invalid project_color for this project type"},
    },
)
def update_project(
    project_id: int,
    project: ProjectSchema,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    try:
        # Resolve caller identity from header (set by apiClient interceptor)
        _caller, caller_member = _resolve_caller(db, x_github_user)

        # Find the project — privileged users are not restricted to ownership
        existing_project = _find_project_by_id(db, project_id, caller_member, project.github_user)
        if not existing_project:
            print(f"❌ PUT /projects/{project_id}/ - Project not found (caller='{x_github_user}', github_user='{project.github_user}')")
            raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND_PLAIN)

        _require_project_editor(db, caller_member, existing_project.project_id)

        print(f"✅ PUT /projects/{project_id}/ - Updating project '{existing_project.project_name}' (caller='{x_github_user}')")
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"❌ PUT /projects/{project_id}/ - Unexpected error during validation: {e}")
        raise HTTPException(status_code=500, detail=_ERR_INTERNAL_VALIDATION)

    # Wrap the main update logic in exception handling
    try:
        existing_project.project_name = project.project_name.strip()
        existing_project.branch_regex = project.branch_regex.strip()
        existing_project.branch_option = project.branch_option.strip()
        existing_project.branch_max_age_days = project.branch_max_age_days
        existing_project.reusable_workflows_enabled = project.reusable_workflows_enabled
        if "project_color" in project.model_fields_set:
            _enforce_project_color_type_restriction(
                existing_project.project_type,
                project.project_color,
                existing_project.project_color,
            )
            existing_project.project_color = project.project_color

        # Tier-gate switching to private visibility scope on update.
        # Only enforce on actual transitions to "private" so that updates which
        # leave the scope unchanged (or set it back to public) are not blocked.
        # `new_scope` is already normalized (lower-cased, trimmed) by
        # ProjectSchema._validate_visibility_scope; `prior_scope` may have come
        # from a legacy row predating that validator, so normalize defensively.
        prior_scope = (existing_project.repository_visibility_scope or "public").strip().lower()
        # Pydantic's model_fields_set tracks explicitly supplied request fields,
        # letting legacy callers omit this field without applying its default.
        scope_was_provided = "repository_visibility_scope" in project.model_fields_set
        new_scope = project.repository_visibility_scope if scope_was_provided else prior_scope
        if new_scope == "private" and prior_scope != "private":
            owner = db.query(Account).filter(Account.user_id == existing_project.user_id).first()
            if owner is None:
                # The owner row should always exist for a persisted project.
                # If it doesn't, the DB is in an inconsistent state and we
                # cannot safely evaluate the tier gate — fail closed rather
                # than silently allowing the transition to "private".
                print(
                    f"❌ PUT /projects/{project_id}/ - Cannot evaluate private "
                    f"visibility tier gate: owner account user_id="
                    f"{existing_project.user_id} not found"
                )
                raise HTTPException(
                    status_code=403,
                    detail="Unable to verify account tier for private visibility scope.",
                )
            allowed, error_msg = check_private_visibility_scope(owner)
            if not allowed:
                raise HTTPException(status_code=403, detail=error_msg)
        existing_project.repository_visibility_scope = new_scope

        # Explicitly update the updated_at timestamp to ensure it reflects the save operation
        existing_project.updated_at = func.now()
        # Audit: record who updated this project
        existing_project.last_modified_by = (x_github_user or project.github_user or "").strip() or None

        # Preserve per-repo branch overrides on associations that survive.
        _process_project_repos(db, existing_project.project_id, project.selected_repos)
        _github_user_for_sync = (x_github_user or project.github_user or "").strip() or ""
        _sync_validation_repo(db, existing_project, project, github_user=_github_user_for_sync, preserve_unset=True)

        # Don't delete ProjectWorkflow associations - let create_or_update_workflow handle updates

        # Determine the caller for audit tracking
        _last_modifier = (x_github_user or project.github_user or "").strip() or None

        # Process regular workflows - skip empty ones
        for workflow in project.workflows:
            if workflow.name and workflow.name.strip() and workflow.content and workflow.content.strip():
                print(f"✅ REG: {workflow}")
                create_or_update_workflow(db, workflow, existing_project.project_id, is_reusable=False, last_modified_by=_last_modifier)
            else:
                print(f"⚠️ Skipping empty regular workflow: name='{workflow.name}', content_length={len(workflow.content) if workflow.content else 0}")

        # Only process reusable workflows if the feature is enabled for this project
        if project.reusable_workflows_enabled:
            for workflow in project.rxworkflows:
                if workflow.name and workflow.name.strip() and workflow.content and workflow.content.strip():
                    print(f"✅ ❌ ❌ RW: {workflow}")
                    create_or_update_workflow(db, workflow, existing_project.project_id, is_reusable=True, last_modified_by=_last_modifier)
                else:
                    print(f"⚠️ Skipping empty reusable workflow: name='{workflow.name}', content_length={len(workflow.content) if workflow.content else 0}")
        else:
            print(f"⚠️ Skipping reusable workflows - feature disabled for project '{project.project_name}'")

        # Update project state based on workflow changes (considers both regular and reusable)
        update_project_state_if_needed(existing_project, project.workflows, project.rxworkflows)
        
        db.commit()

        return {
            "message": "✅ Project updated successfully!",
            "project_id": existing_project.project_id,
            "project_code": existing_project.project_code,
            "pr_state": existing_project.pr_state
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        print(f"❌ PUT /projects/{project_id}/ - Error during project update: {e}")
        db.rollback()  # Rollback the transaction on error
        raise HTTPException(status_code=500, detail=f"Internal server error during project update: {str(e)}")



@router.patch(
    "/projects/{project_id}/project-color",
    responses={
        **_responses(500),
        403: {"description": "Access denied"},
        404: {"description": _ERR_PROJECT_NOT_FOUND_PLAIN},
        422: {"description": "Invalid project_color for this project type"},
    },
)
def update_project_color(
    project_id: int,
    payload: ProjectColorUpdateSchema,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Update a project's identity color without triggering GitHub writes."""
    try:
        _caller, caller_member = _resolve_caller(db, x_github_user)

        existing_project = _find_project_by_id(db, project_id, caller_member, payload.github_user)
        if not existing_project:
            print(
                f"❌ PATCH /projects/{project_id}/project-color - Project not found "
                f"(caller='{x_github_user}', github_user='{payload.github_user}')"
            )
            raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND_PLAIN)

        _require_project_editor(db, caller_member, existing_project.project_id)

        _enforce_project_color_type_restriction(
            existing_project.project_type,
            payload.project_color,
            existing_project.project_color,
        )

        print(
            f"✅ PATCH /projects/{project_id}/project-color - Updating color for "
            f"project '{existing_project.project_name}' (caller='{x_github_user}')"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PATCH /projects/{project_id}/project-color - Unexpected error during validation: {e}")
        raise HTTPException(status_code=500, detail=_ERR_INTERNAL_VALIDATION)

    try:
        existing_project.project_color = payload.project_color
        existing_project.updated_at = func.now()
        existing_project.last_modified_by = (x_github_user or payload.github_user or "").strip() or None
        db.commit()
        return {
            "message": "✅ Project color updated successfully!",
            "project_id": existing_project.project_id,
            "project_color": existing_project.project_color,
        }
    except Exception as e:
        print(f"❌ PATCH /projects/{project_id}/project-color - Error updating project color: {e}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error during project color update")


@router.patch(
    "/projects/{project_id}/drift-config",
    responses={
        403: {"description": "Access denied"},
        404: {"description": _ERR_PROJECT_NOT_FOUND_PLAIN},
        422: {"description": "Invalid drift_check_interval_minutes"},
        # Spelled out rather than via _responses(500): the analyzer reads this
        # dict statically and cannot see through the helper call.
        500: {"description": "Internal server error"},
    },
)
def update_project_drift_config(
    project_id: int,
    payload: ProjectDriftConfigUpdateSchema,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Set how often the background sweep checks this project for drift.

    Local ActionsManager metadata only — never triggers a GitHub call, and
    never runs a check itself. The next sweep tick picks up the new cadence.
    """
    try:
        _caller, caller_member = _resolve_caller(db, x_github_user)

        existing_project = _find_project_by_id(db, project_id, caller_member, payload.github_user)
        if not existing_project:
            print(
                f"❌ PATCH /projects/{project_id}/drift-config - Project not found "
                f"(caller='{x_github_user}', github_user='{payload.github_user}')"
            )
            raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND_PLAIN)

        _require_project_editor(db, caller_member, existing_project.project_id)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PATCH /projects/{project_id}/drift-config - Unexpected error during validation: {e}")
        raise HTTPException(status_code=500, detail=_ERR_INTERNAL_VALIDATION)

    try:
        existing_project.drift_check_interval_minutes = payload.drift_check_interval_minutes
        existing_project.updated_at = func.now()
        existing_project.last_modified_by = (x_github_user or payload.github_user or "").strip() or None
        db.commit()
        return {
            "message": "✅ Drift check schedule updated successfully!",
            "project_id": existing_project.project_id,
            "drift_check_interval_minutes": existing_project.drift_check_interval_minutes,
        }
    except Exception as e:
        print(f"❌ PATCH /projects/{project_id}/drift-config - Error updating drift config: {e}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error during drift config update")


@router.patch(
    "/projects/{project_id}/project-name",
    responses={
        404: {"description": _ERR_PROJECT_NOT_FOUND_PLAIN},
        500: {"description": "Internal server error"},
    },
)
def update_project_name(
    project_id: int,
    payload: ProjectNameUpdateSchema,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Update a project's display name without triggering GitHub writes.

    project_code is never touched — it is immutable after creation.
    """
    try:
        _caller, caller_member = _resolve_caller(db, x_github_user)

        existing_project = _find_project_by_id(db, project_id, caller_member, payload.github_user)
        if not existing_project:
            print(
                f"❌ PATCH /projects/{project_id}/project-name - Project not found "
                f"(caller='{x_github_user}', github_user='{payload.github_user}')"
            )
            raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND_PLAIN)

        print(
            f"✅ PATCH /projects/{project_id}/project-name - Renaming project "
            f"'{existing_project.project_name}' → '{payload.project_name}' (caller='{x_github_user}')"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PATCH /projects/{project_id}/project-name - Unexpected error during validation: {e}")
        raise HTTPException(status_code=500, detail=_ERR_INTERNAL_VALIDATION)

    try:
        existing_project.project_name = payload.project_name
        existing_project.updated_at = func.now()
        existing_project.last_modified_by = (x_github_user or payload.github_user or "").strip() or None
        db.commit()
        return {
            "message": "✅ Project name updated successfully!",
            "project_id": existing_project.project_id,
            "project_name": existing_project.project_name,
            "project_code": existing_project.project_code,
        }
    except Exception as e:
        print(f"❌ PATCH /projects/{project_id}/project-name - Error updating project name: {e}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error during project name update")


def _resolve_caller_member(db: Session, x_github_user: Optional[str]):
    """Resolve the calling user's workspace membership from the X-GitHub-User header."""
    if not x_github_user:
        return None
    caller = db.query(Account).filter(Account.github_user == x_github_user).first()
    if not caller:
        return None
    return (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == caller.user_id)
        .first()
    )


def _resolve_display_order_member(db: Session, request, x_github_user: Optional[str]):
    """Identity used to pick whose saved project order to apply.

    get_projects authorizes from the X-GitHub-User header, but the frontend's
    apiClient authenticates GETs with the session cookie alone, so that header
    is usually absent — without this fallback the saved order would silently
    never apply in the real app. Falls back to the session rather than the
    client-supplied github_user query param, which is spoofable and would let a
    caller read another user's arrangement.
    """
    member = _resolve_caller_member(db, x_github_user)
    if member is not None:
        return member

    session_user = resolve_optional_session_user(request, db)
    if session_user is None:
        return None
    return (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == session_user.user_id)
        .first()
    )


def _delete_project_display_order(db: Session, project_id: int) -> None:
    """Remove every user's saved position for a project being deleted.

    Cascade now handles this on both databases (issue #1811 enabled SQLite's
    `PRAGMA foreign_keys`, which had made every ON DELETE CASCADE a no-op).
    Kept as belt-and-braces so the cleanup is explicit at the call site and does
    not depend on engine configuration.
    """
    db.query(ProjectDisplayOrder).filter(
        ProjectDisplayOrder.project_id == project_id
    ).delete(synchronize_session=False)


def _accessible_project_ids(db: Session, caller_member) -> set:
    """Project IDs the caller may see, mirroring get_projects' two branches exactly.

    Admins see every project; non-admins only those with a ProjectMembership row.
    One query either way — resolving per project id would be N queries.
    """
    if is_project_admin(caller_member):
        return {pid for (pid,) in db.query(Project.project_id).all()}
    return {
        pid for (pid,) in
        db.query(ProjectMembership.project_id)
        .filter(ProjectMembership.user_id == caller_member.user_id)
        .all()
    }


def _apply_saved_display_order(db: Session, caller_member, rows: list) -> list:
    """Order project rows by the caller's saved arrangement (issue #1804).

    ``rows`` arrives ordered by updated_at DESC. Projects with a saved position
    come first in that order; anything without one keeps its incoming
    updated_at position and lands after, which is how new projects append to
    the end. project_id breaks any tie deterministically.

    Sorting here rather than in SQL keeps one code path for SQLite and
    PostgreSQL — "NULLS LAST" is spelled differently across them.
    """
    if caller_member is None:
        # No identity, so no per-user preference to apply.
        return rows

    positions = dict(
        db.query(ProjectDisplayOrder.project_id, ProjectDisplayOrder.position)
        .filter(ProjectDisplayOrder.user_id == caller_member.user_id)
        .all()
    )
    if not positions:
        return rows

    def sort_key(indexed):
        incoming_index, row = indexed
        project = row[0]
        saved = positions.get(project.project_id)
        if saved is None:
            return (1, incoming_index, project.project_id)
        return (0, saved, project.project_id)

    return [row for _, row in sorted(enumerate(rows), key=sort_key)]


def _initialize_display_order(db: Session, caller_member, rows: list) -> None:
    """Persist the current updated_at-descending order the first time a user lists projects.

    Without this, a user who has never dragged anything would keep falling back
    to updated_at, so editing a project would still move its card — the exact
    behaviour issue #1804 removes. Runs once: after this the user always has
    rows, and updated_at is never consulted for those projects again.
    """
    if caller_member is None or not rows:
        return

    already_ordered = (
        db.query(ProjectDisplayOrder.id)
        .filter(ProjectDisplayOrder.user_id == caller_member.user_id)
        .first()
    )
    if already_ordered:
        return

    try:
        for position, row in enumerate(rows):
            db.add(ProjectDisplayOrder(
                user_id=caller_member.user_id,
                project_id=row[0].project_id,
                position=position,
            ))
        db.commit()
    except Exception:
        # Never fail a read because the one-time seed lost a race with a
        # concurrent request; the next list call retries.
        db.rollback()


def _effective_pr_state(
    project: Project,
    rwx_ids_with_open_linked_prs: set,
    rwx_ids_with_draft_workflows: set,
) -> str:
    """Return pr_state, promoting for RWX projects with linked open PRs or draft workflows."""
    if (project.project_type or "standard") != "rwx":
        return project.pr_state
    # Open PRs take highest priority
    if (
        project.project_id in rwx_ids_with_open_linked_prs
        and project.pr_state in ("synced", "draft", "new", None)
    ):
        return "open"
    # Draft workflows promote to "draft"
    if (
        project.project_id in rwx_ids_with_draft_workflows
        and project.pr_state in ("synced", "new", None)
    ):
        return "draft"
    return project.pr_state


@router.get("/projects/")
def get_projects(
    github_user: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Fetches all projects for a given GitHub user, filtered by the caller's access."""
    # Build a combined workflow count per project that includes both:
    #   1. Own workflows (ProjectWorkflow rows)
    #   2. Linked reusable workflows (LinkedReusableWorkflow rows for standard projects)
    # This matches what users see when they open a project.
    pw_ids = db.query(
        ProjectWorkflow.project_id.label("project_id"),
    )
    lrw_ids = db.query(
        LinkedReusableWorkflow.standard_project_id.label("project_id"),
    )
    combined_ids = union_all(pw_ids, lrw_ids).subquery()
    workflow_count_subq = (
        db.query(
            combined_ids.c.project_id.label("project_id"),
            func.count().label("workflow_count"),
        )
        .group_by(combined_ids.c.project_id)
        .subquery()
    )

    caller_member = _resolve_caller_member(db, x_github_user)

    if caller_member and not is_project_admin(caller_member):
        # Non-admin (member/read_only): return projects the caller is explicitly assigned to
        # via ProjectMembership (regardless of project owner — projects may belong to any account)
        rows = (
            db.query(
                Project,
                Account.account_type,
                func.coalesce(workflow_count_subq.c.workflow_count, 0).label("workflow_count"),
            )
            .join(Account, Account.user_id == Project.user_id)
            .outerjoin(workflow_count_subq, workflow_count_subq.c.project_id == Project.project_id)
            .join(ProjectMembership, ProjectMembership.project_id == Project.project_id)
            .filter(ProjectMembership.user_id == caller_member.user_id)
            .order_by(Project.updated_at.desc())
            .all()
        )
    else:
        # Admin (or no header): show all workspace projects.
        # Privileged users see every project regardless of which account owns
        # them, so the URL-based github_user param does not restrict results.
        # NOTE: This application uses a single-workspace model — all projects
        # and members belong to the same workspace, so returning all projects
        # is correct.  If multi-workspace support is added, this query should
        # be scoped to the caller's workspace.
        rows = (
            db.query(
                Project,
                Account.account_type,
                func.coalesce(workflow_count_subq.c.workflow_count, 0).label("workflow_count"),
            )
            .join(Account, Account.user_id == Project.user_id)
            .outerjoin(workflow_count_subq, workflow_count_subq.c.project_id == Project.project_id)
            .order_by(Project.updated_at.desc())
            .all()
        )

    # updated_at only decides the *initial* arrangement now (issue #1804). Once a
    # user has a saved order it wins, so opening or editing a project no longer
    # moves its card.
    order_member = _resolve_display_order_member(db, request, x_github_user)
    _initialize_display_order(db, order_member, rows)
    rows = _apply_saved_display_order(db, order_member, rows)

    # For RWX projects, determine if any linked standard project has an open PR
    # campaign so the project list can show "Under Review" instead of "Synced".
    rwx_ids_with_open_linked_prs: set = set(
        rwx_id for (rwx_id,) in
        db.query(LinkedReusableWorkflow.rwx_project_id)
        .join(
            ProjectPullRequest,
            ProjectPullRequest.project_id == LinkedReusableWorkflow.standard_project_id,
        )
        .filter(ProjectPullRequest.pr_state == "open")
        .distinct()
        .all()
    )

    # For RWX projects, determine if any owned workflow has local uncommitted
    # changes so the project list shows "Draft" instead of "Synced".
    rwx_ids_with_draft_workflows: set = set(
        pid for (pid,) in
        db.query(ProjectWorkflow.project_id)
        .join(Workflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
        .join(Project, Project.project_id == ProjectWorkflow.project_id)
        .filter(
            Project.project_type == "rwx",
            Workflow.workflow_status == "committed_locally",
        )
        .distinct()
        .all()
    )

    return [
        {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "project_code": project.project_code,
            "reusable_workflows_enabled": project.reusable_workflows_enabled,
            "use_prefix": project.use_prefix,
            "account_type": owner_account_type,
            "pr_state": _effective_pr_state(project, rwx_ids_with_open_linked_prs, rwx_ids_with_draft_workflows),
            "project_type": project.project_type or "standard",
            "repository_visibility_scope": project.repository_visibility_scope or "public",
            "project_color": project.project_color,
            "validation_repo": _repo_name_for_id(db, project.validation_repo_id),
            "preflight_required": bool(project.preflight_required),
            "last_preflight_status": project.last_preflight_status,
            "last_preflight_run_at": project.last_preflight_run_at,
            "last_preflight_error": project.last_preflight_error,
            "last_preflight_pr_url": project.last_preflight_pr_url,
            "drift_status": project.drift_status or "unknown",
            "drift_count": int(project.drift_count or 0),
            "last_drift_check_at": project.last_drift_check_at,
            "drift_error_summary": project.drift_error_summary,
            "drift_check_interval_minutes": project.drift_check_interval_minutes,
            "last_modified_by": project.last_modified_by,
            "workflow_count": int(workflow_count or 0),
        }
        for project, owner_account_type, workflow_count in rows
    ]

def _get_repo_names(db: Session, project_id: int) -> list:
    """Return the list of repo names associated with a project."""
    return [
        name for (name,) in
        db.query(Repo.repo_name)
        .join(ProjectRepo, ProjectRepo.repo_id == Repo.repo_id)
        .filter(ProjectRepo.project_id == project_id)
        .all()
    ]


def _split_workflows(all_workflows: list) -> tuple:
    """Split a workflow list into regular workflows and reusable workflows."""
    workflows = []
    rxworkflows = []
    for w in all_workflows:
        wf_dict = {
            "name": w.workflow_name,
            "content": w.workflow_yaml,
            "isReusable": w.reusable_workflow,
            "gitHash": w.workflow_git_hash,
            "workflowStatus": w.workflow_status,
            "lastModifiedBy": w.last_modified_by,
        }
        if w.reusable_workflow:
            rxworkflows.append(wf_dict)
        else:
            workflows.append(wf_dict)
    return workflows, rxworkflows


def _get_under_review_linked_wf_ids(db: Session, project_id: int) -> list:
    """Return IDs of linked reusable workflows currently in 'under_review' status."""
    return [
        r[0] for r in
        db.query(Workflow.workflow_id).join(
            LinkedReusableWorkflow,
            LinkedReusableWorkflow.workflow_id == Workflow.workflow_id,
        ).filter(
            LinkedReusableWorkflow.standard_project_id == project_id,
            Workflow.workflow_status == "under_review",
        ).all()
    ]


def _linked_workflows_locked_by_open_campaign(db: Session, workflow_ids: list) -> set:
    """Return the subset of ``workflow_ids`` that must stay ``under_review``.

    Thin wrapper around the shared
    :func:`workflows._reusable_workflow_ids_locked_by_open_campaign` helper:
    the ``under_review`` lock is a *workflow-level* state that must persist
    globally until **every** open PR campaign referencing the workflow — from
    the owning RWX project or any linking caller project — is merged or
    closed.  Drift/sync auto-correction uses this to avoid unlocking a
    workflow whose open campaign is owned by a different project.
    """
    return _reusable_workflow_ids_locked_by_open_campaign(db, workflow_ids)


def _update_project_workflow_statuses(db: Session, project_id: int, new_status: str) -> list:
    """Bulk-update all 'under_review' workflows for a project to new_status.

    Returns the list of workflow IDs that were updated.
    Query IDs first (join is valid for SELECT), then update by ID
    because Query.update() cannot be used with join().
    """
    wf_ids = [
        r[0] for r in
        db.query(Workflow.workflow_id).join(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project_id,
            Workflow.workflow_status == "under_review",
        ).all()
    ]
    if wf_ids:
        db.query(Workflow).filter(
            Workflow.workflow_id.in_(wf_ids)
        ).update({"workflow_status": new_status}, synchronize_session=False)
    return wf_ids


def _autocorrect_pr_workflow_statuses(
    db: Session,
    project,
    workflows: list,
    rxworkflows: list,
    under_review_linked_wf_ids: list,
) -> None:
    """Auto-correct workflow statuses based on PR records already stored in the DB.

    This runs as a safety net on every project GET: if any workflow is still
    'under_review' but all tracked PRs reached a terminal state (merged or
    closed), the status is corrected before the response is returned.

    All PRs merged  → promote  under_review → synced_with_github
    All PRs closed  → revert   under_review → committed_locally
    """
    has_under_review = (
        any(wf.get("workflowStatus") == "under_review" for wf in workflows)
        or any(wf.get("workflowStatus") == "under_review" for wf in rxworkflows)
        or bool(under_review_linked_wf_ids)
    )
    if not has_under_review:
        return

    # Collect PRs from both this project and any linked projects so that
    # cross-project open PRs (e.g. a standard project's PR targeting an RWX
    # project's reusable workflow) prevent premature status transitions.
    related_project_ids = {project.project_id}
    if project.project_type == "rwx":
        linked_std_ids = [
            r[0] for r in
            db.query(LinkedReusableWorkflow.standard_project_id).filter(
                LinkedReusableWorkflow.rwx_project_id == project.project_id
            ).all()
        ]
        related_project_ids.update(linked_std_ids)
    elif project.project_type == "standard":
        linked_rwx_ids = [
            r[0] for r in
            db.query(LinkedReusableWorkflow.rwx_project_id).filter(
                LinkedReusableWorkflow.standard_project_id == project.project_id
            ).all()
        ]
        related_project_ids.update(linked_rwx_ids)

    tracked_prs = db.query(ProjectPullRequest).filter(
        ProjectPullRequest.project_id.in_(related_project_ids)
    ).all()
    total_tracked = len(tracked_prs)
    if total_tracked == 0:
        return

    open_pr_count = sum(1 for p in tracked_prs if p.pr_state == "open")
    if open_pr_count > 0:
        return

    merged_pr_count = sum(1 for p in tracked_prs if p.pr_state == "merged")
    if merged_pr_count == total_tracked:
        new_status = "synced_with_github"
        new_pr_state = "synced"
    else:
        new_status = "committed_locally"
        new_pr_state = "draft"

    # Update in-memory workflow dicts
    for wf in workflows:
        if wf.get("workflowStatus") == "under_review":
            wf["workflowStatus"] = new_status
    for wf in rxworkflows:
        if wf.get("workflowStatus") == "under_review":
            wf["workflowStatus"] = new_status

    # Persist project-owned workflow status changes
    _update_project_workflow_statuses(db, project.project_id, new_status)

    # Persist linked reusable workflow status changes (they live in the RWX
    # project's ProjectWorkflow so the join-based query above misses them).
    #
    # A reusable workflow's under_review lock is a global, workflow-level state:
    # it must persist while *any* project that shares the workflow (a sibling
    # caller or the owning RWX project) still has an open PR campaign for it.
    # Exclude those workflows from correction so a drift/sync refresh in one
    # caller never unlocks a workflow another caller is still reviewing.
    if under_review_linked_wf_ids:
        locked_wf_ids = _linked_workflows_locked_by_open_campaign(
            db, under_review_linked_wf_ids
        )
        correctable_wf_ids = [
            wid for wid in under_review_linked_wf_ids if wid not in locked_wf_ids
        ]
        if correctable_wf_ids:
            db.query(Workflow).filter(
                Workflow.workflow_id.in_(correctable_wf_ids)
            ).update({"workflow_status": new_status}, synchronize_session=False)
            print(f"✅ Auto-corrected: {len(correctable_wf_ids)} linked workflow(s) → {new_status}")

    # Update project PR state
    if new_status == "synced_with_github" and project.pr_state != "synced":
        project.pr_state = new_pr_state
    elif new_status == "committed_locally" and project.pr_state not in ("draft", "synced"):
        project.pr_state = new_pr_state

    db.commit()
    print(f"✅ Auto-corrected: workflows → {new_status} (project {project.project_id})")


def _migrate_branch_option(branch_option: str | None) -> str:
    """Migrate legacy branch_option values to the current set."""
    option = branch_option or "default"
    if option == "all":
        return "default"
    if option == "regex":
        return "pattern"
    return option


def _load_linked_reusable_workflows(db: Session, project_id: int) -> list:
    """Return linked reusable workflow metadata for a standard project.

    Each entry includes ``rwx_repo``: the first repo associated with the source
    RWX project, used by the frontend to build "Open in GitHub" deep-links.
    When the RWX project has no associated repo the field is omitted so
    callers must treat it as optional.
    """
    joined_links = (
        db.query(LinkedReusableWorkflow, Workflow, Project)
        .join(Workflow, Workflow.workflow_id == LinkedReusableWorkflow.workflow_id)
        .join(Project, Project.project_id == LinkedReusableWorkflow.rwx_project_id)
        .filter(LinkedReusableWorkflow.standard_project_id == project_id)
        .all()
    )

    if not joined_links:
        return []

    # Collect the distinct RWX project IDs referenced by this standard project's
    # linked workflows, then fetch their repos in a single query to avoid N+1.
    rwx_project_ids = list({link.rwx_project_id for link, _w, _p in joined_links})
    rwx_repo_rows = (
        db.query(ProjectRepo.project_id, Repo.repo_name)
        .join(Repo, Repo.repo_id == ProjectRepo.repo_id)
        .filter(ProjectRepo.project_id.in_(rwx_project_ids))
        .order_by(Repo.repo_name)
        .all()
    )
    # Build a mapping of rwx_project_id -> first repo name (alphabetically stable).
    rwx_repo_map: dict[int, str] = {}
    for proj_id, repo_name in rwx_repo_rows:
        if proj_id not in rwx_repo_map:
            rwx_repo_map[proj_id] = repo_name

    results = []
    for link, w, rwx_p in joined_links:
        # Format the workflow filename using the *source* RWX project's naming mode
        # so that the consuming standard project never re-normalises a foreign name.
        # e.g. a Prefix-Mode RWX project (use_prefix=True, code="RWW1") storing stem
        # "testrwx" must surface as "AM_RWW1_testrwx.yml", not "testrwx.yml".
        # Strip any trailing .yml/.yaml from the stored name first (idempotency guard
        # for any legacy rows that were written with an extension already attached).
        workflow_stem = re.sub(r'\.(yml|yaml)$', '', w.workflow_name, flags=re.IGNORECASE)
        formatted_name = format_workflow_name(
            workflow_stem, rwx_p.project_code.upper(), rwx_p.use_prefix
        )
        entry: dict = {
            "workflow_id": w.workflow_id,
            "workflow_name": formatted_name,
            "workflow_yaml": w.workflow_yaml,
            "rwx_project_id": link.rwx_project_id,
            "rwx_project_name": rwx_p.project_name,
            "workflowStatus": w.workflow_status,
        }
        if link.rwx_project_id in rwx_repo_map:
            entry["rwx_repo"] = rwx_repo_map[link.rwx_project_id]
        results.append(entry)
    return results


def _load_linked_standard_projects(db: Session, project_id: int, user_id: int) -> list:
    """Return standard projects that link to this RWX project.

    Scoped to projects owned by user_id and with project_type == 'standard'
    to prevent cross-account data exposure from stray rows.
    """
    std_project_alias = aliased(Project)
    joined_std_links = (
        db.query(LinkedReusableWorkflow, std_project_alias)
        .join(std_project_alias, std_project_alias.project_id == LinkedReusableWorkflow.standard_project_id)
        .filter(
            LinkedReusableWorkflow.rwx_project_id == project_id,
            std_project_alias.user_id == user_id,
            std_project_alias.project_type == "standard",
        )
        .all()
    )
    seen_project_ids: set[int] = set()
    result = []
    for link, std_p in joined_std_links:
        if link.standard_project_id not in seen_project_ids:
            seen_project_ids.add(link.standard_project_id)
            result.append({
                "project_id": std_p.project_id,
                "project_name": std_p.project_name,
                "project_code": std_p.project_code,
            })
    return result


def _format_export_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_version_metadata(metadata_value):
    if metadata_value is None:
        return {}
    parsed = metadata_value
    if isinstance(metadata_value, str):
        stripped = metadata_value.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return {"raw": metadata_value}
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def _sha256_json(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _serialize_custom_files(db: Session, project_id: int) -> list:
    rows = db.query(CustomFile).filter_by(project_id=project_id).all()
    return [
        {
            "id": cf.id,
            "project_id": cf.project_id,
            "display_name": cf.display_name,
            "file_path": cf.file_path,
            "file_content": cf.file_content,
            "git_hash": cf.git_hash,
            "file_status": cf.file_status,
            "pending_delete": cf.pending_delete,
            "last_modified_by": cf.last_modified_by,
            "description": cf.description,
            "created_at": _format_export_timestamp(cf.created_at) if cf.created_at else None,
            "updated_at": _format_export_timestamp(cf.updated_at) if cf.updated_at else None,
        }
        for cf in rows
    ]


def _build_project_backup_payload(db: Session, project: Project, exported_by: str) -> dict:
    exported_at = _format_export_timestamp(datetime.now(timezone.utc))

    repo_links = (
        db.query(ProjectRepo, Repo)
        .join(Repo, Repo.repo_id == ProjectRepo.repo_id)
        .filter(ProjectRepo.project_id == project.project_id)
        .order_by(Repo.repo_name.asc())
        .all()
    )
    repositories = [
        {
            "repo_name": repo.repo_name,
            "repo_full_name": repo.repo_name,
            "branch_config_mode": (link.branch_config_mode or "inherit"),
            "branch_option": link.branch_option,
            "branch_regex": _normalize_optional_text(link.branch_regex),
            "branch_max_age_days": link.branch_max_age_days,
            "source_metadata": {"repo_id": repo.repo_id},
        }
        for link, repo in repo_links
    ]

    workflow_rows = (
        db.query(Workflow)
        .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
        .filter(ProjectWorkflow.project_id == project.project_id)
        .order_by(Workflow.reusable_workflow.asc(), Workflow.workflow_name.asc(), Workflow.workflow_id.asc())
        .all()
    )
    workflow_ids = [w.workflow_id for w in workflow_rows]
    workflow_id_set = set(workflow_ids)

    version_rows = []
    if workflow_ids:
        version_rows = (
            db.query(WorkflowVersion)
            .filter(WorkflowVersion.workflow_id.in_(workflow_ids))
            .order_by(
                WorkflowVersion.workflow_id.asc(),
                WorkflowVersion.version_number.asc(),
                WorkflowVersion.version_id.asc(),
            )
            .all()
        )

    versions_by_workflow: dict[int, list] = {}
    for version in version_rows:
        versions_by_workflow.setdefault(version.workflow_id, []).append(
            {
                "version_number": version.version_number,
                "content": version.content,
                "metadata": _parse_version_metadata(version.version_metadata),
                "created_at": _format_export_timestamp(version.created_at) if version.created_at else None,
                "source_metadata": {"version_id": version.version_id},
            }
        )

    workflows = [
        {
            "name": w.workflow_name,
            "workflow_file_name": w.workflow_name,
            "content": w.workflow_yaml,
            "content_sha256": hashlib.sha256((w.workflow_yaml or "").encode("utf-8")).hexdigest(),
            "is_reusable": bool(w.reusable_workflow),
            "last_modified_by": w.last_modified_by,
            "version_history": versions_by_workflow.get(w.workflow_id, []),
            "source_metadata": {
                "workflow_id": w.workflow_id,
                "workflow_git_hash": w.workflow_git_hash,
                "workflow_status": w.workflow_status,
            },
        }
        for w in workflow_rows
    ]

    project_workflow_relationships = [
        {"project_code": project.project_code, "workflow_file_name": w.workflow_name}
        for w in workflow_rows
    ]

    ruleset_rows = (
        db.query(Ruleset)
        .join(ProjectRuleset, ProjectRuleset.ruleset_id == Ruleset.ruleset_id)
        .filter(ProjectRuleset.project_id == project.project_id)
        .order_by(Ruleset.ruleset_name.asc(), Ruleset.ruleset_id.asc())
        .all()
    )
    rulesets = [
        {
            "ruleset_name": r.ruleset_name,
            "description": r.description,
            "ruleset_json": r.ruleset_json,
            "created_at": _format_export_timestamp(r.created_at) if r.created_at else None,
            "updated_at": _format_export_timestamp(r.updated_at) if r.updated_at else None,
            "source_metadata": {"ruleset_id": r.ruleset_id},
        }
        for r in ruleset_rows
    ]

    codeowners_rows = (
        db.query(Codeowners, Repo)
        .join(Repo, Repo.repo_id == Codeowners.repo_id)
        .filter(Codeowners.project_id == project.project_id)
        .order_by(Repo.repo_name.asc(), Codeowners.id.asc())
        .all()
    )
    codeowners_records = [
        {
            "repo_name": repo.repo_name,
            "file_path": record.file_path,
            "content": record.content,
            "git_hash": record.git_hash,
            "status": record.status,
            "last_modified_by": record.last_modified_by,
            "created_at": _format_export_timestamp(record.created_at) if record.created_at else None,
            "updated_at": _format_export_timestamp(record.updated_at) if record.updated_at else None,
            "source_metadata": {
                "codeowners_id": record.id,
                "repo_id": record.repo_id,
            },
        }
        for record, repo in codeowners_rows
    ]

    repo_override_rows = (
        db.query(RepoWorkflowOverride, Repo)
        .join(Repo, Repo.repo_id == RepoWorkflowOverride.repo_id)
        .filter(RepoWorkflowOverride.project_id == project.project_id)
        .order_by(Repo.repo_name.asc(), RepoWorkflowOverride.workflow_name.asc(), RepoWorkflowOverride.id.asc())
        .all()
    )
    repo_workflow_overrides = [
        {
            "repo_name": repo.repo_name,
            "workflow_name": override.workflow_name,
            "workflow_file_name": override.workflow_name,
            "workflow_yaml": override.workflow_yaml,
            "source_repo_name": override.source_repo_name,
            "last_modified_by": override.last_modified_by,
            "created_at": _format_export_timestamp(override.created_at) if override.created_at else None,
            "updated_at": _format_export_timestamp(override.updated_at) if override.updated_at else None,
            "source_metadata": {
                "override_id": override.id,
                "repo_id": override.repo_id,
                "workflow_id": override.workflow_id,
                "workflow_git_hash": override.workflow_git_hash,
            },
        }
        for override, repo in repo_override_rows
    ]

    linked_reusable_rows = (
        db.query(LinkedReusableWorkflow, Workflow, Project)
        .join(Workflow, Workflow.workflow_id == LinkedReusableWorkflow.workflow_id)
        .join(Project, Project.project_id == LinkedReusableWorkflow.rwx_project_id)
        .filter(LinkedReusableWorkflow.standard_project_id == project.project_id)
        .order_by(Project.project_name.asc(), Workflow.workflow_name.asc(), LinkedReusableWorkflow.id.asc())
        .all()
    )
    linked_reusable_workflows = [
        {
            "standard_project_name": project.project_name,
            "standard_project_code": project.project_code,
            "rwx_project_name": rwx_project.project_name,
            "workflow_name": workflow.workflow_name,
            "workflow_file_name": workflow.workflow_name,
            "created_at": _format_export_timestamp(link.created_at) if link.created_at else None,
            "source_metadata": {
                "link_id": link.id,
                "standard_project_id": link.standard_project_id,
                "rwx_project_id": link.rwx_project_id,
                "workflow_id": workflow.workflow_id,
                "workflow_status": workflow.workflow_status,
            },
        }
        for link, workflow, rwx_project in linked_reusable_rows
    ]

    linked_standard_rows = (
        db.query(LinkedReusableWorkflow, Project, Workflow)
        .join(Project, Project.project_id == LinkedReusableWorkflow.standard_project_id)
        .join(Workflow, Workflow.workflow_id == LinkedReusableWorkflow.workflow_id)
        .filter(
            LinkedReusableWorkflow.rwx_project_id == project.project_id,
            Project.user_id == project.user_id,
            Project.project_type == "standard",
        )
        .order_by(Project.project_name.asc(), Workflow.workflow_name.asc(), LinkedReusableWorkflow.id.asc())
        .all()
    )
    linked_standard_projects = [
        {
            "standard_project_name": std_project.project_name,
            "standard_project_code": std_project.project_code,
            "workflow_name": workflow.workflow_name,
            "workflow_file_name": workflow.workflow_name,
            "created_at": _format_export_timestamp(link.created_at) if link.created_at else None,
            "source_metadata": {
                "link_id": link.id,
                "standard_project_id": std_project.project_id,
                "workflow_id": workflow.workflow_id,
            },
        }
        for link, std_project, workflow in linked_standard_rows
    ]

    project_repo_relationships = [
        {"project_code": project.project_code, "repo_name": repo["repo_name"]}
        for repo in repositories
    ]

    payload = {
        "backup_schema_version": BACKUP_SCHEMA_VERSION,
        "metadata": {
            "backup_schema_version": BACKUP_SCHEMA_VERSION,
            "exported_at": exported_at,
            "exported_by": exported_by,
            "project_name": project.project_name,
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "source_metadata": {"project_id": project.project_id},
        },
        "import_policy": {
            "id_strategy": "remap",
            "github_sync_strategy": "verify_after_import",
            "restore_version_history": True,
            "on_name_conflict": "rename_or_prompt",
            "missing_link_strategy": "skip_and_report",
            "default_workflow_status": "committed_locally",
        },
        "project": {
            "project_name": project.project_name,
            "project_code": project.project_code,
            "project_type": project.project_type or "standard",
            "branch_regex": _normalize_optional_text(project.branch_regex),
            "branch_option": _migrate_branch_option(project.branch_option),
            "branch_max_age_days": project.branch_max_age_days or 30,
            "reusable_workflows_enabled": bool(project.reusable_workflows_enabled),
            "use_prefix": bool(project.use_prefix),
            "pr_state": project.pr_state,
            "repository_visibility_scope": project.repository_visibility_scope or "public",
            "project_color": project.project_color,
            "last_modified_by": project.last_modified_by,
            "created_at": _format_export_timestamp(project.created_at) if project.created_at else None,
            "updated_at": _format_export_timestamp(project.updated_at) if project.updated_at else None,
            "source_metadata": {"project_id": project.project_id},
        },
        "repositories": repositories,
        "workflows": workflows,
        "rulesets": rulesets,
        "codeowners": codeowners_records,
        "repo_workflow_overrides": repo_workflow_overrides,
        "linked_reusable_workflows": linked_reusable_workflows,
        "linked_standard_projects": linked_standard_projects,
        "custom_files": _serialize_custom_files(db, project.project_id),
        "relationships": {
            "project_repositories": project_repo_relationships,
            "project_workflows": project_workflow_relationships,
        },
        "summary": {
            "repository_count": len(repositories),
            "workflow_count": len(workflows),
            "workflow_version_count": len(version_rows),
            "ruleset_count": len(rulesets),
            "codeowners_count": len(codeowners_records),
            "repo_workflow_override_count": len(repo_workflow_overrides),
            "linked_reusable_workflow_count": len(linked_reusable_workflows),
            "linked_standard_project_count": len(linked_standard_projects),
            "workflows_with_project_relationship": len(workflow_id_set),
        },
    }
    payload_without_integrity = dict(payload)
    payload["integrity"] = {
        "algorithm": "sha256",
        "payload_sha256": _sha256_json(payload_without_integrity),
        "workflow_content_sha256": [
            {"workflow_file_name": workflow["workflow_file_name"], "sha256": workflow["content_sha256"]}
            for workflow in workflows
        ],
    }
    return payload


@router.get("/projects/{project_name}", responses=_responses(403, 404))
def get_project(
    project_name: str,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    check_drift: Annotated[bool, Query(description="Whether to check for workflow drift")] = False,
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Fetch a project with its repositories and workflows (split into workflows + rxworkflows)."""

    user = db.query(Account).filter(Account.github_user == github_user.strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail=GITHUB_USER_NOT_FOUND)

    # Resolve the calling user's workspace membership
    caller_member = None
    if x_github_user:
        caller = db.query(Account).filter(Account.github_user == x_github_user).first()
        if caller:
            caller_member = (
                db.query(WorkspaceMember)
                .filter(WorkspaceMember.user_id == caller.user_id)
                .first()
            )

    # Try to find the project by owner first
    project = db.query(Project).filter(
        Project.project_name.ilike(project_name.strip()),
        Project.user_id == user.user_id
    ).first()

    # For privileged callers (admin/member), also look up globally
    # because the URL github_user may not be the project owner.
    if not project and caller_member and is_project_admin(caller_member):
        project = (
            db.query(Project)
            .filter(Project.project_name.ilike(project_name.strip()))
            .first()
        )
        if project:
            user = db.query(Account).filter(Account.user_id == project.user_id).first()

    # For non-admin callers, look up via ProjectMembership
    # (the project may belong to a different account)
    if not project and caller_member and not is_project_admin(caller_member):
        project = (
            db.query(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.project_id)
            .filter(
                Project.project_name.ilike(project_name.strip()),
                ProjectMembership.user_id == caller_member.user_id,
            )
            .first()
        )
        if project:
            # Re-resolve the owning account for account_type in the response
            user = db.query(Account).filter(Account.user_id == project.user_id).first()

    if not project:
        raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

    # Enforce project-level access for non-admin callers
    if caller_member and not is_project_admin(caller_member):
        effective_role = check_project_access(db, caller_member, project.project_id)
        if effective_role is None:
            raise HTTPException(status_code=403, detail=_ERR_NO_ACCESS)

    repo_names = _get_repo_names(db, project.project_id)

    all_workflows = (
        db.query(Workflow)
        .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
        .filter(ProjectWorkflow.project_id == project.project_id)
        .all()
    )
    workflows, rxworkflows = _split_workflows(all_workflows)

    # Auto-correct workflow statuses based on PR records already in the DB.
    # `ProjectPullRequest.pr_state` values are kept current by
    # `get_project_pr_status` (called on page load) and by the webhook
    # endpoint, so reading from DB here is reliable without an extra GitHub
    # API call.  Covers standard projects and RWX projects alike.
    under_review_linked_wf_ids = _get_under_review_linked_wf_ids(db, project.project_id)
    _autocorrect_pr_workflow_statuses(db, project, workflows, rxworkflows, under_review_linked_wf_ids)

    # Refresh so pr_state reflects any commits made inside the auto-correction
    db.refresh(project)

    project_type = project.project_type or "standard"

    linked_reusable_workflows = []
    linked_standard_projects = []
    if project_type == "standard":
        linked_reusable_workflows = _load_linked_reusable_workflows(db, project.project_id)
    elif project_type == "rwx":
        linked_standard_projects = _load_linked_standard_projects(db, project.project_id, user.user_id)

    # Determine the caller's effective project role for frontend use
    caller_project_role = "project_admin"  # default for admin or unknown caller
    if caller_member:
        caller_project_role = check_project_access(db, caller_member, project.project_id) or "project_viewer"

    # Per-workflow drift state persisted by the last drift check (see issue
    # #1793) — lets the initial page load show the correct drift badge
    # immediately instead of defaulting to "no drift" and flipping once the
    # client-side live check (DriftDetection component) resolves.
    workflow_ids = [wf.workflow_id for wf in all_workflows]
    drifted_workflow_ids = set()
    if workflow_ids:
        drifted_workflow_ids = {
            row.workflow_id
            for row in db.query(WorkflowDriftState.workflow_id)
            .filter(WorkflowDriftState.workflow_id.in_(workflow_ids), WorkflowDriftState.has_drift.is_(True))
            .distinct()
            .all()
        }
    drifted_workflow_names = sorted({
        wf.workflow_name for wf in all_workflows if wf.workflow_id in drifted_workflow_ids
    })

    return {
        "project_id": project.project_id,
        "project_name": project.project_name,
        "branch_regex": project.branch_regex,
        "branch_option": _migrate_branch_option(project.branch_option),
        "branch_max_age_days": project.branch_max_age_days or 30,
        "selected_repos": repo_names,
        "workflows": workflows,       # ⬅️ only non-reusable
        "rxworkflows": rxworkflows,   # ⬅️ only reusable
        "linked_reusable_workflows": linked_reusable_workflows,  # ⬅️ linked from RWX projects
        "linked_standard_projects": linked_standard_projects,  # ⬅️ standard projects using this RWX project
        "project_code": project.project_code,
        "account_type": user.account_type,
        "reusable_workflows_enabled": project.reusable_workflows_enabled,
        "use_prefix": project.use_prefix,
        "pr_state": project.pr_state,
        "project_type": project_type,
        "repository_visibility_scope": project.repository_visibility_scope or "public",
        "project_color": project.project_color,
        "validation_repo": _repo_name_for_id(db, project.validation_repo_id),
        "preflight_required": bool(project.preflight_required),
        "last_preflight_status": project.last_preflight_status,
        "last_preflight_run_at": project.last_preflight_run_at,
        "last_preflight_error": project.last_preflight_error,
        "last_preflight_pr_url": project.last_preflight_pr_url,
        "drift_detected": check_drift and len(repo_names) > 0,
        "drifted_workflow_names": drifted_workflow_names,
        "drift_check_interval_minutes": project.drift_check_interval_minutes,
        "caller_project_role": caller_project_role,
        "custom_files": _serialize_custom_files(db, project.project_id),
    }


@router.get("/projects/{project_id}/backup-export", responses=_responses(401, 403, 404))
def export_project_backup(
    project_id: int,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Export a deterministic project-scoped JSON backup without sensitive secrets/tokens."""
    caller, caller_member = _resolve_caller(db, x_github_user)
    if not caller:
        raise HTTPException(status_code=401, detail=_ERR_AUTH_REQUIRED)

    project = _find_project_by_id(db, project_id, caller_member, caller.github_user)
    if not project:
        raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

    if caller_member and not is_project_admin(caller_member):
        effective_role = check_project_access(db, caller_member, project.project_id)
        if effective_role is None:
            raise HTTPException(status_code=403, detail=_ERR_NO_ACCESS)

    payload = _build_project_backup_payload(db, project, caller.github_user)
    timestamp_for_filename = payload["metadata"]["exported_at"].replace(":", "-")
    safe_project_name = re.sub(r"[^A-Za-z0-9._-]+", "-", project.project_name.strip()).strip("-") or f"project-{project.project_id}"
    filename = f"actionsmanager-project-{safe_project_name}-{timestamp_for_filename}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/projects/{project_name}", responses=_responses(404, 500))
def delete_project(
    project_name: str,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Deletes a specific project by name and GitHub user."""
    
    try:
        print(f"📌 Debug: Attempting to delete project '{project_name}' for user '{github_user}'")

        _caller, caller_member = _resolve_caller(db, x_github_user)
        project = _find_project_by_name(db, project_name, caller_member, github_user)

        if not project:
            raise HTTPException(status_code=404, detail="❌ Project not found or access denied")

        _delete_project_display_order(db, project.project_id)
        db.delete(project)
        db.commit()
        
        # Clean up any orphaned workflows that are no longer associated with any projects
        cleanup_orphaned_workflows(db)
        
        return {"message": "✅ Project deleted successfully!"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting project: {str(e)}")

    finally:
        db.close()


@router.post("/projects/{project_name}/toggle-reusable-workflows", responses=_responses(404, 500))
def toggle_reusable_workflows(
    project_name: str,
    db: Annotated[Session, Depends(get_db)],
    payload: ReusableWorkflowToggleSchema = None,
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Toggle reusable workflows setting for a specific project."""
    
    try:
        print(f"📌 Debug: Toggling reusable workflows for project '{project_name}' to {payload.enabled}")

        _caller, caller_member = _resolve_caller(db, x_github_user)
        project = _find_project_by_name(db, project_name, caller_member, payload.github_user)

        if not project:
            raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

        # Update the reusable workflows setting
        project.reusable_workflows_enabled = payload.enabled
        project.updated_at = func.now()
        
        db.commit()
        
        return {
            "message": f"✅ Reusable workflows {'enabled' if payload.enabled else 'disabled'} for project '{project_name}'",
            "project_name": project.project_name,
            "reusable_workflows_enabled": project.reusable_workflows_enabled
        }

    except HTTPException:
        # Re-raise HTTPExceptions (like 404) without converting to 500
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating reusable workflow setting: {str(e)}")

    finally:
        db.close()

@router.get("/rwx-workflows", responses=_responses(404))
def get_rwx_workflows(
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    standard_project_name: Annotated[Optional[str], Query(description="Standard project name for link validation")] = None,
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Get all workflows from all RWX projects for a given user."""
    _caller, caller_member = _resolve_caller(db, x_github_user)

    if caller_member and is_project_admin(caller_member):
        # Privileged users see all RWX projects
        rwx_projects = db.query(Project).filter(
            Project.project_type == "rwx"
        ).all()
    else:
        # Fallback: owner-based lookup
        user = db.query(Account).filter(Account.github_user == github_user.strip()).first()
        if not user:
            raise HTTPException(status_code=404, detail=GITHUB_USER_NOT_FOUND)
        rwx_projects = db.query(Project).filter(
            Project.user_id == user.user_id,
            Project.project_type == "rwx"
        ).all()

    standard_project = None
    if standard_project_name:
        standard_project = _find_project_by_name(db, standard_project_name, caller_member, github_user)
        if not standard_project:
            raise HTTPException(status_code=404, detail=f"Project '{standard_project_name}' not found")

    rwx_repo_rows = []
    if rwx_projects:
        rwx_repo_rows = (
            db.query(ProjectRepo.project_id, Repo.repo_name)
            .join(Repo, Repo.repo_id == ProjectRepo.repo_id)
            .filter(ProjectRepo.project_id.in_([p.project_id for p in rwx_projects]))
            .order_by(Repo.repo_name)
            .all()
        )
    rwx_repo_map: dict[int, str] = {}
    for project_id, repo_name in rwx_repo_rows:
        if project_id not in rwx_repo_map:
            rwx_repo_map[project_id] = repo_name

    validation_by_project_id = {}
    if standard_project:
        for project in rwx_projects:
            validation_by_project_id[project.project_id] = reusable_workflow_validation_payload(
                validate_reusable_workflow_link(standard_project, project, db)
            )

    result = []
    for project in rwx_projects:
        project_workflows = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(ProjectWorkflow.project_id == project.project_id)
            .all()
        )
        for w in project_workflows:
            entry = {
                "workflow_id": w.workflow_id,
                "workflow_name": w.workflow_name,
                "workflow_yaml": w.workflow_yaml,
                "rwx_project_id": project.project_id,
                "rwx_project_name": project.project_name,
                "rwx_repo_visibility": project.repository_visibility_scope,
            }
            if project.project_id in rwx_repo_map:
                entry["rwx_repo"] = rwx_repo_map[project.project_id]
            if standard_project:
                entry["link_validation"] = validation_by_project_id[project.project_id]
            result.append(entry)

    return result


@router.post("/projects/{project_name}/linked-reusable-workflows", responses=_responses(404, 422, 500))
def link_reusable_workflow(
    project_name: str,
    payload: LinkWorkflowSchema,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Link a reusable workflow from an RWX project to a standard project."""
    try:
        _caller, caller_member = _resolve_caller(db, x_github_user)

        standard_project = _find_project_by_name(db, project_name, caller_member, payload.github_user)
        if not standard_project:
            raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND_PLAIN)

        rwx_project = _find_project_by_id(db, payload.rwx_project_id, caller_member, payload.github_user)
        if not rwx_project or rwx_project.project_type != "rwx":
            raise HTTPException(status_code=404, detail="RWX project not found")

        workflow = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(
                ProjectWorkflow.project_id == rwx_project.project_id,
                Workflow.workflow_id == payload.workflow_id
            )
            .first()
        )
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found in RWX project")

        existing = db.query(LinkedReusableWorkflow).filter(
            LinkedReusableWorkflow.standard_project_id == standard_project.project_id,
            LinkedReusableWorkflow.workflow_id == payload.workflow_id
        ).first()

        validation = validate_reusable_workflow_link(standard_project, rwx_project, db)
        if not validation.allowed:
            raise HTTPException(
                status_code=422,
                detail=validation.reason or "This reusable workflow cannot be linked by the selected project.",
            )

        if existing:
            return {"message": "Workflow already linked", "already_linked": True,
                    "workflow_id": workflow.workflow_id, "workflow_name": workflow.workflow_name}

        link = LinkedReusableWorkflow(
            standard_project_id=standard_project.project_id,
            rwx_project_id=rwx_project.project_id,
            workflow_id=workflow.workflow_id
        )
        db.add(link)
        db.commit()

        return {
            "message": f"✅ Workflow '{workflow.workflow_name}' linked to project '{standard_project.project_name}'",
            "workflow_id": workflow.workflow_id,
            "workflow_name": workflow.workflow_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error linking workflow: {str(e)}")


@router.delete("/projects/{project_name}/linked-reusable-workflows/{workflow_id}", responses=_responses(404, 500))
def unlink_reusable_workflow(
    project_name: str,
    workflow_id: int,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Unlink a reusable workflow from a standard project."""
    try:
        _caller, caller_member = _resolve_caller(db, x_github_user)

        standard_project = _find_project_by_name(db, project_name, caller_member, github_user)
        if not standard_project:
            raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND_PLAIN)

        link = db.query(LinkedReusableWorkflow).filter(
            LinkedReusableWorkflow.standard_project_id == standard_project.project_id,
            LinkedReusableWorkflow.workflow_id == workflow_id
        ).first()
        if not link:
            raise HTTPException(status_code=404, detail="Linked workflow not found")

        db.delete(link)
        db.commit()

        return {"message": "✅ Workflow unlinked successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error unlinking workflow: {str(e)}")


@router.put("/projects/{project_name}/linked-reusable-workflows/{workflow_id}", responses=_responses(403, 404, 500))
def update_linked_reusable_workflow(
    project_name: str,
    workflow_id: int,
    payload: UpdateLinkedWorkflowSchema,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Update the YAML of a reusable workflow that is linked into a standard project.

    Resolution rules (see issue: "Fix linked reusable workflow updates creating
    duplicate workflow files"):

    * The workflow is resolved by ``workflow_id`` joined through
      ``linked_reusable_workflows`` to the consuming standard project.
      ``workflow_name`` is intentionally **not** used as a key — display names
      returned for linked workflows are formatted with the source RWX project's
      prefix and a ``.yml`` extension and would not match the canonical stored
      stem.
    * The existing ``workflows`` row is updated in place.  No new ``workflows``
      row and no new ``project_workflows`` association are created (the
      canonical workflow is already associated with its source RWX project).
    * A new ``workflow_versions`` row is appended.
    * ``workflow_status`` is reset to ``committed_locally`` and
      ``workflow_git_hash`` is reset to all zeros, mirroring normal local-edit
      behaviour for reusable workflows.  Exception: while any open PR campaign
      (from any project) still references the workflow, ``workflow_status``
      stays ``under_review`` so the global lock is not bypassed.
    * Access is verified for both the consuming standard project **and** the
      source RWX project so that a user without rights to the RWX source
      cannot mutate it via the linked path.
    """
    try:
        _caller, caller_member = _resolve_caller(db, x_github_user)

        # Validate access to the consuming standard project
        standard_project = _find_project_by_name(
            db, project_name, caller_member, payload.github_user
        )
        if not standard_project:
            raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND_PLAIN)

        # Enforce project_editor (write) access on the consuming project so that
        # project_viewer/read_only members cannot mutate via this endpoint.
        if caller_member and not is_project_admin(caller_member):
            std_role = check_project_access(db, caller_member, standard_project.project_id)
            if std_role not in ("project_editor", "project_admin"):
                raise HTTPException(
                    status_code=403,
                    detail="Insufficient project permissions. Required: project_editor",
                )

        # Validate the workflow is actually linked to this standard project
        link = db.query(LinkedReusableWorkflow).filter(
            LinkedReusableWorkflow.standard_project_id == standard_project.project_id,
            LinkedReusableWorkflow.workflow_id == workflow_id,
        ).first()
        if not link:
            raise HTTPException(
                status_code=404,
                detail="Linked reusable workflow not found for this project",
            )

        # Validate access to the source RWX project (the user must own/manage it
        # to mutate its workflows even when editing through the linked path)
        rwx_project = _find_project_by_id(
            db, link.rwx_project_id, caller_member, payload.github_user
        )
        if not rwx_project:
            raise HTTPException(
                status_code=403,
                detail="Access denied to the source RWX project for this linked workflow",
            )

        # Enforce project_editor (write) access on the source RWX project too —
        # editing through the linked path mutates the RWX project's data.
        if caller_member and not is_project_admin(caller_member):
            rwx_role = check_project_access(db, caller_member, rwx_project.project_id)
            if rwx_role not in ("project_editor", "project_admin"):
                raise HTTPException(
                    status_code=403,
                    detail="Insufficient project permissions on the source RWX project. Required: project_editor",
                )

        # Resolve the canonical workflow row.  Confirm it is still associated with
        # the RWX project to avoid mutating an orphaned/migrated row.
        workflow = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(
                Workflow.workflow_id == workflow_id,
                ProjectWorkflow.project_id == rwx_project.project_id,
            )
            .first()
        )
        if not workflow:
            raise HTTPException(
                status_code=404,
                detail="Source reusable workflow not found in the RWX project",
            )

        # Update the existing row in place — never insert a new workflows row.
        new_content = (payload.content or "").strip()
        workflow.workflow_yaml = new_content
        workflow.reusable_workflow = True
        workflow.workflow_git_hash = "0" * 40
        if _linked_workflows_locked_by_open_campaign(db, [workflow.workflow_id]):
            # Global lock: an open PR campaign (from any project) still
            # references this workflow — keep it under_review everywhere.
            workflow.workflow_status = "under_review"
        else:
            workflow.workflow_status = "committed_locally"
        last_modifier = (x_github_user or payload.github_user or "").strip() or None
        if last_modifier:
            workflow.last_modified_by = last_modifier

        # Defensive: guarantee no duplicate reusable workflow exists in the
        # source RWX project for the canonical workflow's normalized name.
        # We must compare on the *normalized* stem (no .yml/.yaml extension and
        # no AM_{code}_ prefix) because the previous bug round-tripped the
        # display-formatted name (e.g. "AM_RWW1_testrwx.yml") through
        # save-workflows and inserted duplicates with that formatted name —
        # those rows would never match against the canonical bare stem
        # ("testrwx") if compared verbatim.  We never delete the row we are
        # updating.  Equality (case-insensitive) is used here instead of
        # ILIKE because workflow names commonly contain '_' which is a wildcard
        # in SQL LIKE/ILIKE.
        canonical_norm = _normalize_reusable_workflow_name(workflow.workflow_name)
        duplicate_candidates = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(
                ProjectWorkflow.project_id == rwx_project.project_id,
                Workflow.reusable_workflow.is_(True),
                Workflow.workflow_id != workflow.workflow_id,
            )
            .all()
        )
        duplicates = [
            cand for cand in duplicate_candidates
            if _normalize_reusable_workflow_name(cand.workflow_name) == canonical_norm
        ]
        for dup in duplicates:
            print(
                f"🧹 Removing accidental duplicate reusable workflow "
                f"'{dup.workflow_name}' (id={dup.workflow_id}) in RWX project "
                f"{rwx_project.project_id}"
            )
            db.query(ProjectWorkflow).filter_by(
                project_id=rwx_project.project_id, workflow_id=dup.workflow_id
            ).delete(synchronize_session=False)
            db.delete(dup)

        db.commit()
        db.refresh(workflow)

        # Append a new workflow_versions row for the existing workflow_id
        create_workflow_version_in_projects(
            db,
            workflow.workflow_id,
            new_content,
            metadata={
                "action": "update_linked",
                "standard_project_id": standard_project.project_id,
                "rwx_project_id": rwx_project.project_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {
            "message": f"Reusable workflow updated in {rwx_project.project_name}.",
            "workflow_id": workflow.workflow_id,
            "workflow_name": workflow.workflow_name,
            "rwx_project_id": rwx_project.project_id,
            "rwx_project_name": rwx_project.project_name,
            "workflow_status": workflow.workflow_status,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error updating linked reusable workflow: {str(e)}",
        )


# ===== Repository-level branch override endpoints =====

ALLOWED_BRANCH_CONFIG_MODES = ("inherit", "override")
ALLOWED_BRANCH_OPTIONS = ("default", "pattern")


class RepoBranchConfigSchema(BaseModel):
    """Payload for updating a single repository's branch configuration."""
    branch_config_mode: str = "inherit"  # "inherit" | "override"
    branch_option: Optional[str] = None  # "default" | "pattern"
    branch_regex: Optional[str] = None
    branch_max_age_days: Optional[int] = None


def _serialize_repo_branch_config(db: Session, project: Project, repo: Repo, assoc: ProjectRepo) -> dict:
    """Build the per-repo branch-config payload returned by the GET endpoint."""
    effective = resolve_branch_config_for_repo(db, project, repo.repo_name, assoc=assoc)
    mode = (assoc.branch_config_mode or "inherit") if assoc else "inherit"
    return {
        "repo_id": repo.repo_id,
        "repo_name": repo.repo_name,
        "branch_config_mode": mode,
        "branch_option": assoc.branch_option if assoc else None,
        "branch_regex": assoc.branch_regex if assoc else None,
        "branch_max_age_days": assoc.branch_max_age_days if assoc else None,
        "effective_branch_option": effective["branch_option"],
        "effective_branch_regex": effective["branch_regex"],
        "effective_branch_max_age_days": effective["branch_max_age_days"],
        "using_project_default": effective["using_project_default"],
    }


_PROJECT_ROLE_LEVEL = {"project_viewer": 0, "project_editor": 1, "project_admin": 2}


def _require_project_access(
    db: Session,
    project_id: int,
    github_user: str,
    x_github_user: Optional[str],
    minimum_project_role: str = "project_viewer",
) -> Project:
    """Resolve the project and enforce that the caller has access to it.

    ``minimum_project_role`` enforces the minimum project role required.
    Workspace/project admins always pass.

    Raises HTTPException(400/401/403/404) on failure, returns the Project on success.
    """
    if not github_user:
        raise HTTPException(status_code=400, detail="github_user is required")

    caller, caller_member = _resolve_caller(db, x_github_user or github_user)
    project = _find_project_by_id(db, project_id, caller_member, github_user=github_user)
    if not project:
        raise HTTPException(status_code=404, detail=_ERR_PROJECT_NOT_FOUND)

    if caller_member and not is_project_admin(caller_member):
        effective_role = check_project_access(db, caller_member, project.project_id)
        if effective_role is None:
            raise HTTPException(status_code=403, detail=_ERR_NO_ACCESS)
        min_level = _PROJECT_ROLE_LEVEL.get(minimum_project_role, 0)
        if _PROJECT_ROLE_LEVEL.get(effective_role, -1) < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient project permissions. Required: {minimum_project_role}",
            )
    return project


def _validate_repo_branch_config(payload: RepoBranchConfigSchema) -> None:
    mode = (payload.branch_config_mode or "inherit").strip().lower()
    if mode not in ALLOWED_BRANCH_CONFIG_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"branch_config_mode must be one of {ALLOWED_BRANCH_CONFIG_MODES}",
        )

    if mode == "inherit":
        # Override columns are ignored when inheriting; nothing to validate.
        return

    option = (payload.branch_option or "default").strip().lower()
    if option not in ALLOWED_BRANCH_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"branch_option must be one of {ALLOWED_BRANCH_OPTIONS}",
        )

    if option == "pattern":
        regex = (payload.branch_regex or "").strip()
        if not regex:
            raise HTTPException(
                status_code=400,
                detail="branch_regex is required when branch_option is 'pattern'",
            )
        try:
            re.compile(regex)
        except re.error as exc:
            raise HTTPException(status_code=400, detail=f"Invalid branch_regex: {exc}")

    if payload.branch_max_age_days is not None:
        try:
            max_age = int(payload.branch_max_age_days)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="branch_max_age_days must be an integer")
        if max_age < 1 or max_age > 30:
            raise HTTPException(
                status_code=400,
                detail="branch_max_age_days must be between 1 and 30",
            )


@router.get("/projects/{project_id}/repo-branch-configs", responses=_responses(400, 403, 404))
def list_project_repo_branch_configs(
    project_id: int,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """List all repositories in ``project_id`` along with their effective branch config."""
    project = _require_project_access(db, project_id, github_user, x_github_user)

    rows = (
        db.query(ProjectRepo, Repo)
        .join(Repo, Repo.repo_id == ProjectRepo.repo_id)
        .filter(ProjectRepo.project_id == project.project_id)
        .order_by(Repo.repo_name)
        .all()
    )

    return {
        "project_id": project.project_id,
        "project_branch_option": _migrate_branch_option(project.branch_option),
        "project_branch_regex": project.branch_regex or "",
        "project_branch_max_age_days": project.branch_max_age_days or 30,
        "repos": [_serialize_repo_branch_config(db, project, repo, assoc) for assoc, repo in rows],
    }


@router.patch("/projects/{project_id}/repos/{repo_id}/branch-config", responses=_responses(400, 403, 404))
def update_project_repo_branch_config(
    project_id: int,
    repo_id: int,
    payload: RepoBranchConfigSchema,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Update the branch override config for a single repo within a project."""
    project = _require_project_access(
        db, project_id, github_user, x_github_user, minimum_project_role="project_editor"
    )
    _validate_repo_branch_config(payload)

    assoc = (
        db.query(ProjectRepo)
        .filter(
            ProjectRepo.project_id == project.project_id,
            ProjectRepo.repo_id == repo_id,
        )
        .first()
    )
    if not assoc:
        raise HTTPException(
            status_code=404,
            detail="Repository is not part of this project",
        )

    repo = db.query(Repo).filter(Repo.repo_id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    mode = (payload.branch_config_mode or "inherit").strip().lower()
    assoc.branch_config_mode = mode
    if mode == "inherit":
        # Reset override columns so future reads always inherit project values.
        assoc.branch_option = None
        assoc.branch_regex = None
        assoc.branch_max_age_days = None
    else:
        option = (payload.branch_option or "default").strip().lower()
        assoc.branch_option = option
        if option == "pattern":
            assoc.branch_regex = (payload.branch_regex or "").strip()
            assoc.branch_max_age_days = (
                int(payload.branch_max_age_days)
                if payload.branch_max_age_days is not None
                else (project.branch_max_age_days or 30)
            )
        else:
            assoc.branch_regex = None
            assoc.branch_max_age_days = None

    db.commit()
    db.refresh(assoc)
    return _serialize_repo_branch_config(db, project, repo, assoc)


@router.delete("/projects/{project_id}/repos/{repo_id}/branch-config", responses=_responses(400, 403, 404))
def reset_project_repo_branch_config(
    project_id: int,
    repo_id: int,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Reset a repository back to the project's default branch configuration."""
    project = _require_project_access(
        db, project_id, github_user, x_github_user, minimum_project_role="project_editor"
    )

    assoc = (
        db.query(ProjectRepo)
        .filter(
            ProjectRepo.project_id == project.project_id,
            ProjectRepo.repo_id == repo_id,
        )
        .first()
    )
    if not assoc:
        raise HTTPException(
            status_code=404,
            detail="Repository is not part of this project",
        )
    repo = db.query(Repo).filter(Repo.repo_id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    assoc.branch_config_mode = "inherit"
    assoc.branch_option = None
    assoc.branch_regex = None
    assoc.branch_max_age_days = None
    db.commit()
    db.refresh(assoc)
    return _serialize_repo_branch_config(db, project, repo, assoc)
