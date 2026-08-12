"""
Project Memberships Router for ActionsManager

Provides API endpoints for managing project-level access control:
- GET    /api/projects/{project_id}/members          — List members of a project
- POST   /api/projects/{project_id}/members          — Add a user to a project
- PATCH  /api/projects/{project_id}/members/{user_id} — Update a member's project role
- DELETE /api/projects/{project_id}/members/{user_id} — Remove a user from a project

Only admin workspace members can manage project memberships.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Annotated, Optional

from database import get_db
from models import Account, WorkspaceMember, Project, ProjectMembership
from authorization import (
    require_role,
    PROJECT_ROLES,
)

router = APIRouter()




# --- Pydantic schemas ---

class ProjectMemberCreate(BaseModel):
    """Request body for adding a user to a project."""
    user_id: int
    project_role: str = "project_viewer"

    @field_validator("project_role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in PROJECT_ROLES:
            raise ValueError(f"project_role must be one of: {', '.join(sorted(PROJECT_ROLES))}")
        return v


class ProjectMemberUpdate(BaseModel):
    """Request body for updating a project member's role."""
    project_role: str

    @field_validator("project_role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in PROJECT_ROLES:
            raise ValueError(f"project_role must be one of: {', '.join(sorted(PROJECT_ROLES))}")
        return v


class ProjectMemberResponse(BaseModel):
    """Response schema for a project member."""
    id: int
    user_id: int
    project_id: int
    project_role: str
    github_user: str
    avatar_url: Optional[str] = None


# --- Endpoints ---

@router.get(
    "/projects/{project_id}/members",
    response_model=list[ProjectMemberResponse],
)
def list_project_members(
    project_id: int,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """
    List all members assigned to a project.
    Only admins can view project membership assignments.
    """
    # Verify the project exists
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    rows = (
        db.query(ProjectMembership, Account)
        .join(Account, ProjectMembership.user_id == Account.user_id)
        .filter(ProjectMembership.project_id == project_id)
        .order_by(Account.github_user)
        .all()
    )

    return [
        ProjectMemberResponse(
            id=pm.id,
            user_id=pm.user_id,
            project_id=pm.project_id,
            project_role=pm.project_role,
            github_user=account.github_user,
            avatar_url=account.avatar_url,
        )
        for pm, account in rows
    ]


@router.post(
    "/projects/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_project_member(
    project_id: int,
    body: ProjectMemberCreate,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """
    Add a user to a project with a specified role.
    Only admins can assign project memberships.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Verify target user exists
    account = db.query(Account).filter(Account.user_id == body.user_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check for existing membership
    existing = (
        db.query(ProjectMembership)
        .filter(
            ProjectMembership.user_id == body.user_id,
            ProjectMembership.project_id == project_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this project",
        )

    membership = ProjectMembership(
        user_id=body.user_id,
        project_id=project_id,
        project_role=body.project_role,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    return ProjectMemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        project_id=membership.project_id,
        project_role=membership.project_role,
        github_user=account.github_user,
        avatar_url=account.avatar_url,
    )


@router.patch(
    "/projects/{project_id}/members/{user_id}",
    response_model=ProjectMemberResponse,
)
def update_project_member(
    project_id: int,
    user_id: int,
    body: ProjectMemberUpdate,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """
    Update a project member's role.
    Only admins can update project memberships.
    """
    membership = (
        db.query(ProjectMembership)
        .filter(
            ProjectMembership.user_id == user_id,
            ProjectMembership.project_id == project_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project membership not found",
        )

    membership.project_role = body.project_role
    db.commit()

    account = db.query(Account).filter(Account.user_id == user_id).first()

    return ProjectMemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        project_id=membership.project_id,
        project_role=membership.project_role,
        github_user=account.github_user if account else "unknown",
        avatar_url=account.avatar_url if account else None,
    )


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_project_member(
    project_id: int,
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """
    Remove a user from a project.
    Only admins can remove project memberships.
    """
    membership = (
        db.query(ProjectMembership)
        .filter(
            ProjectMembership.user_id == user_id,
            ProjectMembership.project_id == project_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project membership not found",
        )

    db.delete(membership)
    db.commit()
