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
  DELETE /api/projects/{project_id}/custom-files/{file_id}  – mark pending delete (or hard delete if new)
  POST   /api/projects/{project_id}/custom-files/{file_id}/restore – cancel pending delete

Security: path validation is enforced server-side on every create/update.
File content is never logged.
"""

from typing import Annotated, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import user_tokens
from database import get_db
from models import Account, CustomFile, Project, ProjectMembership, WorkspaceMember
from authorization import is_project_admin

router = APIRouter()

_ZEROS = "0" * 40


# ── Path validation ──────────────────────────────────────────────────────────

_BLOCKED_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".crt", ".cert", ".jks"}


def validate_file_path(path: str) -> Optional[str]:
    """Return an error message string, or None when the path is safe."""
    if not path or not path.strip():
        return "File path is required"
    path = path.strip()
    if path.startswith("/"):
        return "Absolute paths are not allowed"
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
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")
    return project


_ERR_NOT_FOUND = "Custom file not found"

# ── Project state helper ─────────────────────────────────────────────────────

def _mark_project_draft(db: Session, project_id: int) -> None:
    """Promote project pr_state to 'draft' when a custom file change is saved.

    Mirrors the same promotion that workflow saves perform so that the Create
    PR Campaign button becomes available without touching a workflow first.
    """
    project = db.query(Project).filter_by(project_id=project_id).first()
    if project and project.pr_state in ("new", "synced"):
        project.pr_state = "draft"
        db.commit()


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

@router.get("/api/projects/{project_id}/custom-files")
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


@router.post("/api/projects/{project_id}/custom-files")
def create_custom_file(
    project_id: int,
    payload: CreateCustomFileRequest,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    user = _resolve_user(x_github_user, payload.github_user)
    _get_project_for_user(db, project_id, user)

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


@router.put("/api/projects/{project_id}/custom-files/{file_id}")
def update_custom_file(
    project_id: int,
    file_id: int,
    payload: UpdateCustomFileRequest,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    user = _resolve_user(x_github_user, payload.github_user)
    _get_project_for_user(db, project_id, user)

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


@router.delete("/api/projects/{project_id}/custom-files/{file_id}")
def delete_custom_file(
    project_id: int,
    file_id: int,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
    github_user: Optional[str] = None,
):
    user = _resolve_user(x_github_user, github_user)
    _get_project_for_user(db, project_id, user)

    cf = db.query(CustomFile).filter_by(id=file_id, project_id=project_id).first()
    if not cf:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    never_synced = cf.git_hash is None or cf.git_hash == _ZEROS
    if never_synced and cf.file_status == "new":
        db.delete(cf)
        db.commit()
        return {"deleted": True, "hard_deleted": True}

    cf.pending_delete = True
    cf.file_status = "committed_locally"
    cf.last_modified_by = user
    cf.updated_at = datetime.now(timezone.utc)
    db.commit()
    _mark_project_draft(db, project_id)
    return {"deleted": False, "pending_delete": True, "custom_file": _serialize(cf)}


@router.post("/api/projects/{project_id}/custom-files/{file_id}/restore")
def restore_custom_file(
    project_id: int,
    file_id: int,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
    github_user: Optional[str] = None,
):
    user = _resolve_user(x_github_user, github_user)
    _get_project_for_user(db, project_id, user)

    cf = db.query(CustomFile).filter_by(id=file_id, project_id=project_id).first()
    if not cf:
        raise HTTPException(status_code=404, detail=_ERR_NOT_FOUND)

    cf.pending_delete = False
    cf.last_modified_by = user
    cf.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cf)
    return {"custom_file": _serialize(cf)}
