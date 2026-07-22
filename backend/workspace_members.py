"""
Workspace Members Router for ActionsManager.xyz

Provides API endpoints for managing workspace members:
- GET  /api/workspace/members         — List all workspace members
- PATCH /api/workspace/members/{user_id}/role — Update a member's role (admin only)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Annotated, Optional

from database import get_db
from models import Account, WorkspaceMember
from authorization import require_role, get_current_member, VALID_ROLES

router = APIRouter()




def _normalize_legacy_roles(db: Session) -> None:
    """
    Normalize deprecated workspace roles.

    Converts legacy `co_admin` rows to `admin` so API responses and auth checks
    use the current role model.
    """
    updated = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_role == "co_admin")
        .update({WorkspaceMember.workspace_role: "admin"}, synchronize_session=False)
    )
    if updated:
        db.commit()


# --- Pydantic schemas ---

class RoleUpdate(BaseModel):
    """Request body for updating a member's workspace role."""
    workspace_role: str

    @field_validator("workspace_role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"workspace_role must be one of: {', '.join(sorted(VALID_ROLES))}")
        return v


class MemberResponse(BaseModel):
    """Response schema for a single workspace member."""
    user_id: int
    github_user: str
    avatar_url: Optional[str] = None
    workspace_role: str


# --- Endpoints ---

@router.get("/api/workspace/members", response_model=list[MemberResponse])
def list_workspace_members(
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(get_current_member)],
):
    """
    List all workspace members.
    Any authenticated workspace member can view the member list.
    """
    _normalize_legacy_roles(db)

    rows = (
        db.query(Account, WorkspaceMember)
        .join(WorkspaceMember, Account.user_id == WorkspaceMember.user_id)
        .order_by(Account.user_id)
        .all()
    )

    return [
        MemberResponse(
            user_id=account.user_id,
            github_user=account.github_user,
            avatar_url=account.avatar_url,
            workspace_role=member.workspace_role,
        )
        for account, member in rows
    ]


@router.patch("/api/workspace/members/{user_id}/role")
def update_member_role(
    user_id: int,
    body: RoleUpdate,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """
    Update the workspace role of a member.
    Only admins can change roles.
    
    Admins cannot demote themselves — there must always be at least one admin.
    """
    _normalize_legacy_roles(db)

    member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == user_id)
        .first()
    )
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace member not found",
        )

    # Prevent the last admin from losing admin role
    if member.workspace_role == "admin" and body.workspace_role != "admin":
        admin_count = (
            db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_role == "admin")
            .count()
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the last admin. Promote another user to admin first.",
            )

    member.workspace_role = body.workspace_role
    db.commit()

    # Fetch the associated account for the response
    account = db.query(Account).filter(Account.user_id == user_id).first()

    return {
        "user_id": user_id,
        "github_user": account.github_user if account else "unknown",
        "workspace_role": member.workspace_role,
        "message": f"Role updated to {body.workspace_role}",
    }
