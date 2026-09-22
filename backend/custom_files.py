"""
Custom Files API for ActionsManager

Manages workflow-adjacent text files (scripts, action definitions, config
files, etc.) at the project level.  Custom files are deployed to every
repository in a project alongside workflow YAML files and participate in the
same PR Campaign / drift-detection lifecycle.

Endpoints:
  GET    /api/projects/{project_id}/custom-files            – list all
  POST   /api/projects/{project_id}/custom-files            – create
  PUT    /api/projects/{project_id}/custom-files/{file_id}  – update
  DELETE /api/projects/{project_id}/custom-files/{file_id}  – remove from the project, optionally from GitHub too
  POST   /api/projects/{project_id}/custom-files/{file_id}/restore – cancel pending delete

Security: path validation is enforced server-side on every create/update.
File content is never logged.
"""

from typing import Annotated, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import user_tokens
from database import get_db
from models import Account, CustomFile, Project, ProjectMembership, ProjectRepo, WorkspaceMember
from authorization import check_project_access, is_project_admin

router = APIRouter()


# Which copies of a custom file a delete destroys. "project" removes only the
# ActionsManager record and leaves the committed file in GitHub;
# "project_and_github" also removes it from the repositories, now rather than on
# some later delivery. It stays the default, so a parameterless DELETE reaches
# GitHub — see `delivery` below for how.
_SCOPE_PROJECT = "project"
_SCOPE_PROJECT_AND_GITHUB = "project_and_github"
_VALID_SCOPES = (_SCOPE_PROJECT, _SCOPE_PROJECT_AND_GITHUB)

# How a GitHub-scoped removal reaches the repositories. "campaign" runs a real
# PR Campaign for the deletion, so its pull requests are grouped, tracked and
# merged like every other delivery this product makes; "direct" commits the
# removal straight to each target branch. Neither defers the work — the dialog
# offers to delete from GitHub, so the request has to reach GitHub now.
_DELIVERY_CAMPAIGN = "campaign"
_DELIVERY_DIRECT = "direct"
_VALID_DELIVERIES = (_DELIVERY_CAMPAIGN, _DELIVERY_DIRECT)


# ── Path validation ──────────────────────────────────────────────────────────

_BLOCKED_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".crt", ".cert", ".jks"}


def validate_file_path(path: str) -> Optional[str]:
    """Return an error message string, or None when the path is safe."""
    if not path or not path.strip():
        return "File path is required"
    path = path.strip()
    if path.startswith("/"):
        return "Absolute paths are not allowed"
    # The stored path is interpolated into a GitHub contents URL, where the
    # server percent-decodes it. Without this, "%2e%2e" survives the ".." check
    # below and still reaches GitHub as "..", escaping the contents endpoint.
    if "%" in path:
        return "Percent-encoded characters are not allowed in a file path"
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        return "Path traversal (..) is not allowed"
    if parts[0] == ".git" or ".git" in parts[1:]:
        return ".git/ paths are not allowed"
    basename = parts[-1].lower()
    if basename == ".env" or basename.startswith(".env."):
        return ".env files are not allowed"
    lower = path.lower()
    for ext in _BLOCKED_EXTENSIONS:
        if lower.endswith(ext):
            return f"{ext} files are not allowed (may contain secrets)"
    return None


# ── Auth helpers ─────────────────────────────────────────────────────────────

# Error responses these endpoints can return, declared on each route so they
# appear in the OpenAPI schema (and so generated clients know about them).
# Codes raised inside shared helpers count too - the rule tracks the call.
_ERROR_RESPONSES = {
    400: {"description": "Invalid request"},
    401: {"description": "Not authenticated"},
    403: {"description": "Access denied"},
    404: {"description": "Not found"},
    409: {"description": "Conflicts with an existing custom file"},
    502: {"description": "GitHub rejected part of the request"},
}


def _responses(*codes: int) -> dict:
    """Subset of _ERROR_RESPONSES for a route's `responses=` parameter."""
    return {code: _ERROR_RESPONSES[code] for code in codes}


def _resolve_user(
    x_github_user: Optional[str],
    github_user_query: Optional[str],
) -> str:
    """Return the authenticated github username, raising 401 if not found."""
    user = x_github_user or github_user_query
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail="User not authenticated")
    return user


def _get_project_for_user(db: Session, project_id: int, github_user: str) -> Project:
    """Return the project if the caller has access, else raise 403/404."""
    account = db.query(Account).filter_by(github_user=github_user).first()
    if not account:
        raise HTTPException(status_code=401, detail="User not authenticated")

    project = db.query(Project).filter_by(project_id=project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_member = db.query(WorkspaceMember).filter_by(user_id=account.user_id).first()
    has_access = (
        (workspace_member and is_project_admin(workspace_member))
        or project.user_id == account.user_id
        or bool(db.query(ProjectMembership).filter_by(user_id=account.user_id, project_id=project_id).first())
        # A full workspace member reads every project in this single-workspace
        # model. Safe to widen only because every write behind this helper now
        # carries its own project_editor gate; until this change it *was* the
        # gate for create, update and restore.
        or bool(workspace_member and workspace_member.workspace_role == "member")
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")
    return project


_ERR_NOT_FOUND = "Custom file not found"
_ERR_NOT_EDITOR = "Editor access to this project is required to change it on GitHub"


def _require_project_editor(db: Session, project: Project, github_user: str) -> None:
    """Require project_editor before a removal is allowed to reach GitHub.

    ``_get_project_for_user`` proves only that the caller can *see* the project:
    it accepts any ProjectMembership row, and project_viewer is documented as
    read-only access. That was enough while a GitHub-scoped delete merely set
    pending_delete on the row — a reversible database change. It is not enough
    now that the same request commits the deletion to the target branches, or
    opens a campaign to.

    Mirrors ``workflows._require_project_editor``, which exists for this exact
    reason on the other path that writes to GitHub directly.
    """
    account = db.query(Account).filter_by(github_user=github_user).first()
    if not account:
        raise HTTPException(status_code=403, detail=_ERR_NOT_EDITOR)

    # Owning the project is full rights, and owners need no membership row.
    if project.user_id == account.user_id:
        return

    member = db.query(WorkspaceMember).filter_by(user_id=account.user_id).first()
    if not member:
        raise HTTPException(status_code=403, detail=_ERR_NOT_EDITOR)
    if check_project_access(db, member, project.project_id) not in ("project_editor", "project_admin"):
        raise HTTPException(status_code=403, detail=_ERR_NOT_EDITOR)

# ── Project state helper ─────────────────────────────────────────────────────

def _current_pr_state(db: Session, project_id: int) -> Optional[str]:
    """The project's pr_state, for a mutation to hand back.

    Only the project-load endpoint computes it otherwise, so a caller that does
    not return it leaves Create PR Campaign stale until the user refreshes.
    """
    project = db.query(Project).filter_by(project_id=project_id).first()
    return project.pr_state if project else None


def _mark_project_draft(db: Session, project_id: int) -> Optional[str]:
    """Promote project pr_state to 'draft' when a custom file change is saved.

    Mirrors the same promotion that workflow saves perform so that the Create
    PR Campaign button becomes available without touching a workflow first.

    Returns the resulting pr_state so a mutation can hand it back — the value is
    otherwise only computed by the project-load endpoint, and the button stays
    disabled until the user refreshes.
    """
    project = db.query(Project).filter_by(project_id=project_id).first()
    if not project:
        return None
    if project.pr_state in ("new", "synced"):
        project.pr_state = "draft"
        db.commit()
    return project.pr_state


# ── Serialiser ───────────────────────────────────────────────────────────────

def _serialize(cf: CustomFile) -> dict:
    return {
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
        "created_at": cf.created_at.isoformat() if cf.created_at else None,
        "updated_at": cf.updated_at.isoformat() if cf.updated_at else None,
    }


# ── Request schemas ───────────────────────────────────────────────────────────

class CreateCustomFileRequest(BaseModel):
    github_user: Optional[str] = None
    display_name: Optional[str] = None
    file_path: str
    file_content: str = ""
    description: Optional[str] = None


class UpdateCustomFileRequest(BaseModel):
    github_user: Optional[str] = None
    display_name: Optional[str] = None
    file_path: Optional[str] = None
    file_content: Optional[str] = None
    description: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/projects/{project_id}/custom-files", responses=_responses(401, 403, 404))
def list_custom_files(
    project_id: int,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
    github_user: Optional[str] = None,
):
    user = _resolve_user(x_github_user, github_user)
    _get_project_for_user(db, project_id, user)
    files = db.query(CustomFile).filter_by(project_id=project_id).all()
    return {"custom_files": [_serialize(f) for f in files]}


@router.post("/api/projects/{project_id}/custom-files", responses=_responses(400, 401, 403, 404, 409))
def create_custom_file(
    project_id: int,
    payload: CreateCustomFileRequest,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    user = _resolve_user(x_github_user, payload.github_user)
    _project = _get_project_for_user(db, project_id, user)

    # Creating, editing and restoring a custom file all change what this
    # project delivers, so seeing the project is not enough - the resolve
    # above proves only that. delete_custom_file already carried this.
    _require_project_editor(db, _project, user)

    path_error = validate_file_path(payload.file_path)
    if path_error:
        raise HTTPException(status_code=400, detail=path_error)

    existing = db.query(CustomFile).filter_by(
        project_id=project_id, file_path=payload.file_path.strip()
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A custom file already exists at path '{payload.file_path}' in this project",
        )

    cf = CustomFile(
        project_id=project_id,
        display_name=payload.display_name,
        file_path=payload.file_path.strip(),
        file_content=payload.file_content,
        description=payload.description,
        file_status="new",
        last_modified_by=user,
    )
    db.add(cf)
    db.commit()
    db.refresh(cf)
    _mark_project_draft(db, project_id)
    return {"custom_file": _serialize(cf)}


@router.put("/api/projects/{project_id}/custom-files/{file_id}", responses=_responses(400, 401, 403, 404, 409))
def update_custom_file(
    project_id: int,
    file_id: int,
    payload: UpdateCustomFileRequest,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    user = _resolve_user(x_github_user, payload.github_user)
    _project = _get_project_for_user(db, project_id, user)

    # Creating, editing and restoring a custom file all change what this
    # project delivers, so seeing the project is not enough - the resolve
    # above proves only that. delete_custom_file already carried this.
    _require_project_editor(db, _project, user)

    cf = db.query(CustomFile).filter_by(id=file_id, project_id=project_id).first()
    if not cf:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    if payload.file_path is not None and payload.file_path.strip() != cf.file_path:
        path_error = validate_file_path(payload.file_path)
        if path_error:
            raise HTTPException(status_code=400, detail=path_error)
        conflict = db.query(CustomFile).filter_by(
            project_id=project_id, file_path=payload.file_path.strip()
        ).filter(CustomFile.id != file_id).first()
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"A custom file already exists at path '{payload.file_path}' in this project",
            )
        cf.file_path = payload.file_path.strip()

    if payload.display_name is not None:
        cf.display_name = payload.display_name
    if payload.description is not None:
        cf.description = payload.description

    content_changed = payload.file_content is not None and payload.file_content != cf.file_content
    if content_changed:
        cf.file_content = payload.file_content

    if content_changed or (payload.file_path is not None and payload.file_path.strip() != cf.file_path):
        cf.file_status = "committed_locally"
        cf.git_hash = None

    cf.last_modified_by = user
    cf.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(cf)
    _mark_project_draft(db, project_id)
    return {"custom_file": _serialize(cf)}


def _hard_delete(db: Session, cf: CustomFile, targets: Optional[List[dict]] = None) -> dict:
    project_id = cf.project_id
    db.delete(cf)
    db.commit()
    response = {
        "deleted": True,
        "hard_deleted": True,
        "pr_state": _current_pr_state(db, project_id),
    }
    if targets is not None:
        response["targets"] = targets
    return response


def _assert_name_resolves_to(db: Session, project: Project, user: str) -> None:
    """Refuse to run the campaign if the project name would resolve elsewhere.

    ``create_pull_requests`` takes a project *name*, and ``_find_project_by_name``
    falls back to a global name match for privileged workspace members. This route
    resolved its project by id, so for an admin acting on someone else's project
    while owning a same-named project of their own, the campaign would silently
    target the wrong repositories. Fail loudly instead of guessing.
    """
    from workflows import _find_project_by_name

    resolved = _find_project_by_name(db, user, project.project_name)
    if resolved is None or resolved.project_id != project.project_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"More than one project is named '{project.project_name}' and the "
                "deletion campaign would target a different one. Rename one of them "
                "first, or remove the file from ActionsManager only."
            ),
        )


def _campaign_errors(results: dict) -> List[str]:
    """Per-target reasons from a campaign result, labelled by target."""
    reasons = []
    for target, outcome in results.items():
        if not isinstance(outcome, dict) or outcome.get("status") != "error":
            continue
        reasons.append(f"{target}: {outcome.get('error') or 'no reason reported'}")
    return reasons


def _delete_via_campaign(db: Session, project: Project, cf: CustomFile, user: str) -> dict:
    """Run a PR Campaign whose only change is removing this file.

    The campaign machinery already knows how to deliver a pending_delete custom
    file: it cuts the AM branch, removes the file on it, opens the PR and records
    a ProjectPRCampaign linking them. Going through it rather than opening loose
    pull requests is what puts the deletion in the PR Campaigns view with the
    grouping, status and merge that every other delivery gets.

    The row stays until those PRs merge — that is what Restore cancels and what
    the campaign's synced_with_github transition cleans up.
    """
    from fastapi import BackgroundTasks
    from workflows import CreatePullRequestsRequest, create_pull_requests

    # Before anything is written: a rejection after the mark would leave the file
    # pending_delete for a campaign that never ran.
    _assert_name_resolves_to(db, project, user)

    # A project with no repositories has nowhere to deliver to, so a campaign
    # would have no target and fail with "nothing was selected". There is no
    # GitHub copy this project can reach: drop the record.
    if not db.query(ProjectRepo).filter_by(project_id=project.project_id).first():
        return _hard_delete(db, cf)

    # Committed before the campaign runs: it selects the file out of the database,
    # and pending_delete is what tells it to remove rather than upsert.
    previous_status = cf.file_status
    cf.pending_delete = True
    cf.file_status = "committed_locally"
    cf.last_modified_by = user
    cf.updated_at = datetime.now(timezone.utc)
    db.commit()

    payload = CreatePullRequestsRequest(
        project_name=project.project_name,
        github_user=user,
        # Scoped to this one deletion. Empty lists rather than None: None means
        # "everything changed", which would sweep unrelated work into a campaign
        # the user asked for by clicking Delete.
        selected_workflows=[],
        selected_reusable_workflows=[],
        selected_custom_file_ids=[cf.id],
        selected_codeowners_repos=[],
        campaign_name=f"Remove {cf.file_path}",
        campaign_description=f"Removes {cf.file_path} from {project.project_name}.",
    )

    def _unmark():
        # Leaving the row marked for a deletion that never got delivered would
        # strand it in "pending delete" — the state this whole change exists to
        # get rid of.
        cf.pending_delete = False
        cf.file_status = previous_status
        db.commit()

    try:
        campaign = create_pull_requests(payload, BackgroundTasks(), db, github_user=user)
    except Exception:
        _unmark()
        raise

    # A campaign can return 200 having opened nothing — every target failing
    # branch creation, say. The campaign marks its custom files under_review
    # either way, so without this the file sits pending_delete with no pull
    # request that will ever remove it.
    if not campaign.get("prs_created"):
        _unmark()
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"No pull request was opened to remove '{cf.file_path}'",
                "errors": _campaign_errors(campaign.get("results") or {}),
                "targets": campaign.get("results") or {},
            },
        )

    db.refresh(cf)
    return {
        "deleted": False,
        "pending_delete": True,
        "custom_file": _serialize(cf),
        "pr_state": _current_pr_state(db, project.project_id),
        "campaign_id": campaign.get("campaign_id"),
        "prs_created": campaign["prs_created"],
        "results": campaign.get("results", {}),
    }


@router.delete("/api/projects/{project_id}/custom-files/{file_id}", responses=_responses(400, 401, 403, 404, 409, 502))
def delete_custom_file(
    project_id: int,
    file_id: int,
    db: Annotated[Session, Depends(get_db)],
    scope: Annotated[str, Query(description="'project' or 'project_and_github'")] = _SCOPE_PROJECT_AND_GITHUB,
    delivery: Annotated[str, Query(description="'campaign' or 'direct'; only used when scope includes GitHub")] = _DELIVERY_CAMPAIGN,
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
    github_user: Optional[str] = None,
):
    user = _resolve_user(x_github_user, github_user)
    project = _get_project_for_user(db, project_id, user)

    if scope not in _VALID_SCOPES:
        raise HTTPException(
            status_code=400,
            detail=f"scope must be one of {', '.join(_VALID_SCOPES)}",
        )
    if delivery not in _VALID_DELIVERIES:
        raise HTTPException(
            status_code=400,
            detail=f"delivery must be one of {', '.join(_VALID_DELIVERIES)}",
        )

    cf = db.query(CustomFile).filter_by(id=file_id, project_id=project_id).first()
    if not cf:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    # A project-scoped removal leaves nothing to deliver, and a file that was
    # created but never saved to GitHub has no copy there to chase, so both drop
    # the row outright without touching GitHub.
    if scope == _SCOPE_PROJECT or cf.file_status == "new":
        return _hard_delete(db, cf)

    # Past this point the request reaches GitHub, so seeing the project is not
    # enough. Checked before anything is written.
    _require_project_editor(db, project, user)

    if delivery == _DELIVERY_CAMPAIGN:
        return _delete_via_campaign(db, project, cf, user)

    # Imported from workflows lazily: workflows.py owns every GitHub helper and
    # imports nothing from here, so a module-level import would only add a cycle
    # risk for one call.
    from workflows import delete_custom_file_directly

    outcome = delete_custom_file_directly(db, project, cf.file_path, user)

    if outcome["errors"]:
        # Keep the row. Dropping it here would leave the file in the repositories
        # that failed with nothing in ActionsManager still pointing at it.
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"Could not remove '{cf.file_path}' from every repository",
                "errors": outcome["errors"],
                "targets": outcome["targets"],
            },
        )

    return _hard_delete(db, cf, outcome["targets"])


@router.post("/api/projects/{project_id}/custom-files/{file_id}/restore", responses=_responses(401, 403, 404))
def restore_custom_file(
    project_id: int,
    file_id: int,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
    github_user: Optional[str] = None,
):
    user = _resolve_user(x_github_user, github_user)
    _project = _get_project_for_user(db, project_id, user)

    # Creating, editing and restoring a custom file all change what this
    # project delivers, so seeing the project is not enough - the resolve
    # above proves only that. delete_custom_file already carried this.
    _require_project_editor(db, _project, user)

    cf = db.query(CustomFile).filter_by(id=file_id, project_id=project_id).first()
    if not cf:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    cf.pending_delete = False
    cf.last_modified_by = user
    cf.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cf)
    return {"custom_file": _serialize(cf)}
