"""
Action Groups module for ActionsManager.

Lets users organize the shared Actions Projects catalog into named,
workspace-wide groups (e.g. "Deployment") — an action can belong to any
number of groups. Like Actions Projects themselves, groups are shared:
any authenticated user can create, view, edit, or delete any group.
"""

from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth as auth_module
from database import get_db
from auth import user_tokens
from models import ActionGroup, ActionGroupMembership, ActionsProject

router = APIRouter()

_MSG_NOT_AUTHENTICATED = "User not authenticated"
_MSG_GROUP_NOT_FOUND = "Action Group not found"


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ActionGroupCreateRequest(BaseModel):
    github_user: str
    name: str
    description: Optional[str] = None


class ActionGroupUpdateRequest(BaseModel):
    github_user: str
    name: str
    description: Optional[str] = None


class ActionGroupResponse(BaseModel):
    action_group_id: int
    name: str
    description: Optional[str] = None
    actions_project_ids: List[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _ApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def _require_token(request: Request, db: Session, github_user: str) -> str:
    """Verify the caller's actual session belongs to github_user, then return
    their stored GitHub token. github_user is client-supplied (query param or
    request body), so it must never be trusted as identity on its own -
    resolve_authenticated_user reads the server-issued session cookie instead."""
    account = auth_module.resolve_authenticated_user(request, db)
    if account.github_user.lower() != github_user.lower():
        raise _ApiError(403, "Access denied")
    if github_user not in user_tokens:
        raise _ApiError(401, _MSG_NOT_AUTHENTICATED)
    return user_tokens[github_user]


def _get_group_or_404(db: Session, action_group_id: int) -> ActionGroup:
    group = db.query(ActionGroup).filter_by(action_group_id=action_group_id).first()
    if not group:
        raise _ApiError(404, _MSG_GROUP_NOT_FOUND)
    return group


def _member_ids(db: Session, action_group_id: int) -> List[int]:
    rows = db.query(ActionGroupMembership.actions_project_id).filter_by(
        action_group_id=action_group_id
    ).all()
    return [row[0] for row in rows]


def _to_group_response(group: ActionGroup, member_ids: List[int]) -> ActionGroupResponse:
    return ActionGroupResponse(
        action_group_id=group.action_group_id,
        name=group.name,
        description=group.description,
        actions_project_ids=member_ids,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/api/action-groups/",
    response_model=ActionGroupResponse,
    status_code=201,
    responses={401: {"description": _MSG_NOT_AUTHENTICATED}},
)
def create_action_group(
    request: Request,
    payload: ActionGroupCreateRequest,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        _require_token(request, db, payload.github_user)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    group = ActionGroup(
        name=payload.name,
        description=payload.description,
        last_modified_by=payload.github_user,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return _to_group_response(group, [])


@router.get(
    "/api/action-groups/",
    response_model=List[ActionGroupResponse],
    responses={401: {"description": _MSG_NOT_AUTHENTICATED}},
)
def list_action_groups(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
):
    try:
        _require_token(request, db, github_user)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    groups = db.query(ActionGroup).order_by(ActionGroup.name).all()

    members_by_group: Dict[int, List[int]] = {}
    for group_id, actions_project_id in db.query(
        ActionGroupMembership.action_group_id, ActionGroupMembership.actions_project_id
    ).all():
        members_by_group.setdefault(group_id, []).append(actions_project_id)

    return [
        _to_group_response(group, members_by_group.get(group.action_group_id, []))
        for group in groups
    ]


@router.get(
    "/api/action-groups/{action_group_id}",
    response_model=ActionGroupResponse,
    responses={
        401: {"description": _MSG_NOT_AUTHENTICATED},
        404: {"description": _MSG_GROUP_NOT_FOUND},
    },
)
def get_action_group(
    request: Request,
    action_group_id: int,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
):
    try:
        _require_token(request, db, github_user)
        group = _get_group_or_404(db, action_group_id)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return _to_group_response(group, _member_ids(db, action_group_id))


@router.put(
    "/api/action-groups/{action_group_id}",
    response_model=ActionGroupResponse,
    responses={
        401: {"description": _MSG_NOT_AUTHENTICATED},
        404: {"description": _MSG_GROUP_NOT_FOUND},
    },
)
def update_action_group(
    request: Request,
    action_group_id: int,
    payload: ActionGroupUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        _require_token(request, db, payload.github_user)
        group = _get_group_or_404(db, action_group_id)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    group.name = payload.name
    group.description = payload.description
    group.last_modified_by = payload.github_user
    db.commit()
    db.refresh(group)
    return _to_group_response(group, _member_ids(db, action_group_id))


@router.delete(
    "/api/action-groups/{action_group_id}",
    status_code=204,
    responses={
        401: {"description": _MSG_NOT_AUTHENTICATED},
        404: {"description": _MSG_GROUP_NOT_FOUND},
    },
)
def delete_action_group(
    request: Request,
    action_group_id: int,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
):
    try:
        _require_token(request, db, github_user)
        group = _get_group_or_404(db, action_group_id)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    db.delete(group)
    db.commit()


@router.post(
    "/api/action-groups/{action_group_id}/actions/{actions_project_id}",
    response_model=ActionGroupResponse,
    responses={
        401: {"description": _MSG_NOT_AUTHENTICATED},
        404: {"description": "Action Group or Actions Project not found"},
    },
)
def add_action_to_group(
    request: Request,
    action_group_id: int,
    actions_project_id: int,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
):
    try:
        _require_token(request, db, github_user)
        group = _get_group_or_404(db, action_group_id)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    project = db.query(ActionsProject).filter_by(actions_project_id=actions_project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Actions Project not found")

    existing = db.query(ActionGroupMembership).filter_by(
        action_group_id=action_group_id, actions_project_id=actions_project_id
    ).first()
    if not existing:
        db.add(ActionGroupMembership(
            action_group_id=action_group_id, actions_project_id=actions_project_id
        ))
        db.commit()

    return _to_group_response(group, _member_ids(db, action_group_id))


@router.delete(
    "/api/action-groups/{action_group_id}/actions/{actions_project_id}",
    response_model=ActionGroupResponse,
    responses={
        401: {"description": _MSG_NOT_AUTHENTICATED},
        404: {"description": _MSG_GROUP_NOT_FOUND},
    },
)
def remove_action_from_group(
    request: Request,
    action_group_id: int,
    actions_project_id: int,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
):
    try:
        _require_token(request, db, github_user)
        group = _get_group_or_404(db, action_group_id)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    db.query(ActionGroupMembership).filter_by(
        action_group_id=action_group_id, actions_project_id=actions_project_id
    ).delete()
    db.commit()

    return _to_group_response(group, _member_ids(db, action_group_id))
