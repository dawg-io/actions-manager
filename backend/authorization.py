"""
Authorization module for ActionsManager.xyz

Provides:
- get_current_user: FastAPI dependency to resolve the authenticated user from the request
- require_role: Factory that returns a dependency enforcing minimum workspace role
- ROLE_HIERARCHY: Ordered role levels for permission comparison

Roles (highest → lowest):
  admin  →  member  →  read_only
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db as _get_db
from models import Account, WorkspaceMember, ProjectMembership

# Ordered from lowest to highest privilege
ROLE_HIERARCHY = ["read_only", "member", "admin"]
VALID_ROLES = set(ROLE_HIERARCHY)

# Valid project-level roles
PROJECT_ROLES = {"project_editor", "project_viewer"}


def get_current_user(
    request: Request,
    db: Session = Depends(_get_db),
) -> Account:
    """
    Resolve the currently authenticated user from a server-issued session token.

    X-GitHub-User is never trusted for identity; it is accepted only as an
    optional consistency check by the auth session resolver.

    Returns the Account row or raises 401.
    """
    from auth import resolve_authenticated_user, set_request_user

    user = resolve_authenticated_user(request, db)
    set_request_user(user.github_user)
    return user


def get_current_member(
    current_user: Account = Depends(get_current_user),
    db: Session = Depends(_get_db),
) -> WorkspaceMember:
    """
    Resolve the workspace membership for the current user.
    Returns WorkspaceMember or raises 403 if no membership exists.
    """
    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == current_user.user_id)
        .first()
    )
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a workspace member",
        )
    if member.workspace_role == "co_admin":
        # Transitional safety for pre-migration data: normalize deprecated role in-place.
        member.workspace_role = "admin"
        db.commit()
        db.refresh(member)
    return member


def _role_level(role: str) -> int:
    """Return the numeric privilege level for a role."""
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1


def require_role(minimum_role: str):
    """
    Factory: returns a FastAPI dependency that ensures the caller has
    *at least* the given workspace role.

    Usage in an endpoint::

        @router.post("/api/projects/")
        def create_project(
            ...,
            _auth: WorkspaceMember = Depends(require_role("admin")),
        ):
            ...
    """
    if minimum_role not in VALID_ROLES:
        raise ValueError(
            f"Invalid minimum_role '{minimum_role}'. Must be one of: {', '.join(ROLE_HIERARCHY)}"
        )
    min_level = _role_level(minimum_role)

    def _check(member: WorkspaceMember = Depends(get_current_member)) -> WorkspaceMember:
        if _role_level(member.workspace_role) < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {minimum_role}",
            )
        return member

    return _check


def is_project_admin(member: WorkspaceMember) -> bool:
    """Return True if the workspace role grants automatic project_admin access
    across all projects, without requiring explicit ProjectMembership records.

    Only admin roles receive implicit full project access.
    Members must have explicit ProjectMembership records (project_editor or
    project_viewer) to access individual projects.
    """
    # Transitional runtime safety: treat any remaining deprecated co_admin rows as admin.
    # Once all environments have run migrate_co_admin_to_admin.py, this fallback can be removed.
    return member.workspace_role in ("admin", "co_admin")


def get_project_membership(
    db: Session, user_id: int, project_id: int
) -> Optional[ProjectMembership]:
    """Look up the project membership for a user, or return None."""
    return (
        db.query(ProjectMembership)
        .filter(
            ProjectMembership.user_id == user_id,
            ProjectMembership.project_id == project_id,
        )
        .first()
    )


def check_project_access(
    db: Session, member: WorkspaceMember, project_id: int
) -> Optional[str]:
    """
    Check whether a workspace member can access a project.

    Returns the effective project role string:
      - "project_admin"   for admin workspace members (full access)
      - "project_editor"  for explicit project_editor membership
      - "project_viewer"  for explicit project_viewer membership
      - None              if the user has no access

    Does NOT raise — callers decide how to handle None.
    """
    if is_project_admin(member):
        return "project_admin"

    pm = get_project_membership(db, member.user_id, project_id)
    if pm:
        return pm.project_role
    return None


def require_project_access(minimum_project_role: str = "project_viewer"):
    """
    Factory: returns a FastAPI dependency that ensures the caller can access
    the project identified by *project_id* in the path.

    ``minimum_project_role`` can be ``"project_viewer"`` (default, read access)
    or ``"project_editor"`` (write access).

    Admin workspace members always pass.
    """
    # project role hierarchy: viewer < editor < admin
    _project_role_level = {"project_viewer": 0, "project_editor": 1, "project_admin": 2}
    min_level = _project_role_level.get(minimum_project_role, 0)

    def _check(
        project_id: int,
        member: WorkspaceMember = Depends(get_current_member),
        db: Session = Depends(_get_db),
    ) -> WorkspaceMember:
        effective_role = check_project_access(db, member, project_id)
        if effective_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this project",
            )
        if _project_role_level.get(effective_role, -1) < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient project permissions. Required: {minimum_project_role}",
            )
        return member

    return _check
