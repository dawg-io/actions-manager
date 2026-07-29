"""
Actions Projects module for ActionsManager (issue #1687).

Lets a user paste a GitHub repo (or direct file) URL pointing at an
``actions.yaml``/``actions.yml``, previews its parsed name/description/inputs,
and saves the (possibly edited) result as a standalone ActionsProject row.
Unlike Project (standard/rwx) there is no branch/PR/drift lifecycle here.
"""

import re
import json
import base64
from typing import Annotated, List, Literal, Optional, Tuple

import requests
import yaml
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth as auth_module
from database import get_db
from auth import user_tokens
from models import Account, ActionsProject
from workflows import GITHUB_API_URL, ACCEPT_HEADER, X_API_VERSION, get_default_branch

router = APIRouter()

_PATH_TRAVERSAL_PATTERN = re.compile(r"\.\.")
_REPO_ROOT_URL = re.compile(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$")
_BLOB_FILE_URL = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")
_MARKETPLACE_URL = re.compile(r"^https?://github\.com/marketplace/actions/([^/?#]+)/?$")
_EMBEDDED_DATA_PATTERN = re.compile(
    r'<script type="application/json" data-target="react-app\.embeddedData">(.*?)</script>',
    re.DOTALL,
)

_MSG_NOT_AUTHENTICATED = "User not authenticated"
# GitHub's real convention is the singular action.yml/action.yaml at a repo's
# (or composite action subdirectory's) root; the plural spellings are kept as
# a fallback in case a repo genuinely named its file that way.
_ACTION_METADATA_FILENAMES = ("action.yml", "action.yaml", "actions.yml", "actions.yaml")
# GitHub's fixed branding.color enum (see actions/toolkit's metadata schema).
_BRANDING_COLORS = frozenset({
    "white", "yellow", "blue", "green", "orange", "red", "purple", "gray-dark",
})


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ActionInput(BaseModel):
    name: str
    description: Optional[str] = None
    required: bool = False
    default: Optional[str] = None
    # action.yml itself never declares a type, so parsed/imported inputs
    # always start as "string" - a user can upgrade a specific input to a
    # richer type afterward via the editor (issue #1693).
    type: Literal["string", "number", "boolean", "choice"] = "string"
    options: Optional[List[str]] = None


class PreviewResponse(BaseModel):
    name: str
    description: Optional[str] = None
    owner: str
    repo: str
    ref: str
    yaml_path: str
    source_url: str
    inputs: List[ActionInput]
    branding_icon: Optional[str] = None
    branding_color: Optional[str] = None


class CreateActionsProjectRequest(BaseModel):
    github_user: str
    name: str
    description: Optional[str] = None
    source_url: str
    owner: str
    repo: str
    ref: str
    yaml_path: str
    inputs: List[ActionInput] = []
    branding_icon: Optional[str] = None
    branding_color: Optional[str] = None


class UpdateActionsProjectRequest(BaseModel):
    github_user: str
    name: str
    description: Optional[str] = None
    inputs: List[ActionInput] = []


class ActionsProjectResponse(BaseModel):
    actions_project_id: int
    name: str
    description: Optional[str] = None
    source_url: str
    owner: str
    repo: str
    ref: str
    yaml_path: str
    inputs: List[ActionInput]
    branding_icon: Optional[str] = None
    branding_color: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _ApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


def _resolve_marketplace_action(slug: str):
    """Resolve a GitHub Marketplace action listing to (owner, repo, subdir).

    There's no REST API for marketplace action metadata, so this reads the
    public listing page's embedded React payload, which carries the backing
    repo as ``ownerLogin`` + ``externalUsesPathPrefix`` ("owner/repo[/subdir]@").
    The listing page itself is public, so this fetch doesn't need a token.
    """
    url = f"https://github.com/marketplace/actions/{slug}"
    try:
        response = requests.get(url)
    except Exception as e:
        raise _ApiError(502, f"Failed to reach GitHub Marketplace: {str(e)}")

    if response.status_code == 404:
        raise _ApiError(404, f"No marketplace action found for '{slug}'")
    elif response.status_code != 200:
        raise _ApiError(502, f"GitHub Marketplace returned {response.status_code}")

    match = _EMBEDDED_DATA_PATTERN.search(response.text)
    if not match:
        raise _ApiError(502, "Could not read marketplace action metadata")

    try:
        action = json.loads(match.group(1))["payload"]["action"]
        owner = action["ownerLogin"]
        repo_and_subdir = action["externalUsesPathPrefix"].split("/", 1)[1].split("@")[0]
    except (ValueError, KeyError, TypeError, IndexError):
        raise _ApiError(502, "Could not read marketplace action metadata")

    if not repo_and_subdir:
        raise _ApiError(502, "Could not resolve repository for this marketplace action")

    repo, _sep, subdir = repo_and_subdir.partition("/")
    return owner, repo, subdir


def parse_actions_yaml_url(url: str):
    """Parse a pasted GitHub URL into (owner, repo, ref, path, search_dir).

    ``path`` is the exact file path when known (direct file URLs); otherwise
    it's None and ``search_dir`` ("" for repo root, or a subdirectory) is
    where the caller should look for one of ``_ACTION_METADATA_FILENAMES``.
    Accepts a bare repo URL, a direct ``/blob/<ref>/<path>`` file URL, or a
    GitHub Marketplace action listing URL.
    """
    url = (url or "").strip()

    blob_match = _BLOB_FILE_URL.match(url)
    if blob_match:
        owner, repo, ref, path = blob_match.groups()
        if _PATH_TRAVERSAL_PATTERN.search(path):
            raise ValueError("Invalid file path: path traversal not allowed")
        return owner, repo, ref, path, None

    marketplace_match = _MARKETPLACE_URL.match(url)
    if marketplace_match:
        owner, repo, subdir = _resolve_marketplace_action(marketplace_match.group(1))
        return owner, repo, None, None, subdir

    root_match = _REPO_ROOT_URL.match(url)
    if root_match:
        owner, repo = root_match.groups()
        return owner, repo, None, None, ""

    raise ValueError(
        "URL must be a GitHub repo URL (https://github.com/owner/repo), a direct file URL "
        "(https://github.com/owner/repo/blob/<ref>/<path>), or a GitHub Marketplace action "
        "URL (https://github.com/marketplace/actions/<slug>)"
    )


def _normalize_inputs(inputs_raw) -> List[ActionInput]:
    """Turn actions.yaml's `inputs: {name: {description, required, default}}`
    map into a flat list. Defensive against malformed/missing fields since
    this comes from an external repo's file content."""
    if not isinstance(inputs_raw, dict):
        return []

    result = []
    for input_name, spec in inputs_raw.items():
        spec = spec if isinstance(spec, dict) else {}
        default = spec.get("default")
        result.append(ActionInput(
            name=str(input_name),
            description=spec.get("description") if spec.get("description") is not None else None,
            required=bool(spec.get("required", False)),
            default=str(default) if default is not None else None,
        ))
    return result


def _parse_branding(branding_raw) -> Tuple[Optional[str], Optional[str]]:
    """Parse actions.yaml's optional `branding: {icon, color}` block, the
    same one GitHub Marketplace reads to render its icon badges. Defensive
    against malformed/missing fields since this comes from an external
    repo's file content."""
    if not isinstance(branding_raw, dict):
        return None, None

    icon = branding_raw.get("icon")
    icon = icon.strip().lower() if isinstance(icon, str) and icon.strip() else None

    color = branding_raw.get("color")
    color = color.strip().lower() if isinstance(color, str) else None
    if color not in _BRANDING_COLORS:
        color = None

    return icon, color


def _fetch_repo_file(owner: str, repo: str, ref: str, path: str, token: str) -> str:
    """Fetch and base64-decode a single file via the GitHub Contents API."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }
    file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}?ref={ref}"

    try:
        response = requests.get(file_url, headers=headers)
    except Exception as e:
        raise _ApiError(502, f"GitHub API request failed: {str(e)}")

    if response.status_code == 404:
        raise _ApiError(404, f"File not found: {path}")
    elif response.status_code == 403:
        raise _ApiError(403, "Access denied to repository or rate limit exceeded")
    elif response.status_code != 200:
        raise _ApiError(502, f"GitHub API error: {response.status_code}")

    file_data = response.json()
    try:
        return base64.b64decode(file_data.get("content", "")).decode("utf-8")
    except Exception:
        raise _ApiError(422, "File content could not be decoded as text")


def _fetch_actions_file_in_dir(owner: str, repo: str, ref: str, search_dir: str, token: str):
    """Try each candidate action-metadata filename within search_dir ("" for
    repo root), returning (content, path) for the first one that exists.
    Raises the last error if none match."""
    last_error = None
    for filename in _ACTION_METADATA_FILENAMES:
        candidate = f"{search_dir}/{filename}" if search_dir else filename
        try:
            return _fetch_repo_file(owner, repo, ref, candidate, token), candidate
        except _ApiError as e:
            if e.status_code != 404:
                raise
            last_error = e
    location = f"'{search_dir}/'" if search_dir else "the repo root"
    last_error.detail = (
        f"None of {', '.join(_ACTION_METADATA_FILENAMES)} found in {location} of {owner}/{repo}"
    )
    raise last_error


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


def _get_project_or_404(db: Session, actions_project_id: int) -> ActionsProject:
    """Actions Projects are a shared, workspace-wide catalog — any authenticated
    user can view/edit/delete any entry, not just the one who imported it."""
    project = db.query(ActionsProject).filter_by(actions_project_id=actions_project_id).first()
    if not project:
        raise _ApiError(404, "Actions Project not found")
    return project


def _to_response(project: ActionsProject) -> ActionsProjectResponse:
    try:
        raw_inputs = json.loads(project.inputs_json or "[]")
    except (TypeError, ValueError):
        raw_inputs = []

    return ActionsProjectResponse(
        actions_project_id=project.actions_project_id,
        name=project.name,
        description=project.description,
        source_url=project.source_url,
        owner=project.owner,
        repo=project.repo,
        ref=project.ref,
        yaml_path=project.yaml_path,
        inputs=[ActionInput(**i) for i in raw_inputs],
        branding_icon=project.branding_icon,
        branding_color=project.branding_color,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/api/actions-projects/preview",
    response_model=PreviewResponse,
    responses={
        400: {"description": "Invalid URL"},
        401: {"description": _MSG_NOT_AUTHENTICATED},
        403: {"description": "Access denied to repository"},
        404: {"description": "File not found"},
        422: {"description": "Invalid YAML or missing required fields"},
        502: {"description": "GitHub API error"},
    },
)
def preview_actions_project(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
    url: Annotated[str, Query(..., description="GitHub repo or actions.yaml file URL")],
):
    """Fetch and parse an action's metadata file from the pasted URL. Persists nothing."""
    try:
        token = _require_token(request, db, github_user)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    try:
        owner, repo, ref, path, search_dir = parse_actions_yaml_url(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    if ref is None:
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION,
        }
        ref = get_default_branch(owner, repo, headers)

    try:
        if path is None:
            content, path = _fetch_actions_file_in_dir(owner, repo, ref, search_dir, token)
        else:
            content = _fetch_repo_file(owner, repo, ref, path, token)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=422, detail=f"Invalid YAML in {path}: {str(e)}")

    if not isinstance(parsed, dict) or not parsed.get("name"):
        raise HTTPException(status_code=422, detail=f"{path} must define at least a 'name' field")

    branding_icon, branding_color = _parse_branding(parsed.get("branding"))

    return PreviewResponse(
        name=parsed.get("name"),
        description=parsed.get("description"),
        owner=owner,
        repo=repo,
        ref=ref,
        yaml_path=path,
        source_url=url,
        inputs=_normalize_inputs(parsed.get("inputs")),
        branding_icon=branding_icon,
        branding_color=branding_color,
    )


@router.post(
    "/api/actions-projects/",
    response_model=ActionsProjectResponse,
    status_code=201,
    responses={401: {"description": _MSG_NOT_AUTHENTICATED}},
)
def create_actions_project(
    request: Request,
    payload: CreateActionsProjectRequest,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        _require_token(request, db, payload.github_user)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    account = db.query(Account).filter_by(github_user=payload.github_user).first()
    if not account:
        raise HTTPException(status_code=401, detail=_MSG_NOT_AUTHENTICATED)

    project = ActionsProject(
        user_id=account.user_id,
        name=payload.name,
        description=payload.description,
        source_url=payload.source_url,
        owner=payload.owner,
        repo=payload.repo,
        ref=payload.ref,
        yaml_path=payload.yaml_path,
        inputs_json=json.dumps([i.model_dump() for i in payload.inputs]),
        branding_icon=payload.branding_icon,
        branding_color=payload.branding_color,
        last_modified_by=payload.github_user,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_response(project)


@router.get(
    "/api/actions-projects/",
    response_model=List[ActionsProjectResponse],
    responses={401: {"description": _MSG_NOT_AUTHENTICATED}},
)
def list_actions_projects(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
):
    """Shared, workspace-wide catalog — returns every Actions Project regardless
    of who imported it, not just the caller's own."""
    try:
        _require_token(request, db, github_user)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    projects = db.query(ActionsProject).order_by(ActionsProject.created_at.desc()).all()
    return [_to_response(p) for p in projects]


@router.get(
    "/api/actions-projects/{actions_project_id}",
    response_model=ActionsProjectResponse,
    responses={
        401: {"description": _MSG_NOT_AUTHENTICATED},
        404: {"description": "Actions Project not found"},
    },
)
def get_actions_project(
    request: Request,
    actions_project_id: int,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
):
    try:
        _require_token(request, db, github_user)
        project = _get_project_or_404(db, actions_project_id)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return _to_response(project)


@router.put(
    "/api/actions-projects/{actions_project_id}",
    response_model=ActionsProjectResponse,
    responses={
        401: {"description": _MSG_NOT_AUTHENTICATED},
        404: {"description": "Actions Project not found"},
    },
)
def update_actions_project(
    request: Request,
    actions_project_id: int,
    payload: UpdateActionsProjectRequest,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        _require_token(request, db, payload.github_user)
        project = _get_project_or_404(db, actions_project_id)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    project.name = payload.name
    project.description = payload.description
    project.inputs_json = json.dumps([i.model_dump() for i in payload.inputs])
    project.last_modified_by = payload.github_user
    db.commit()
    db.refresh(project)
    return _to_response(project)


@router.delete(
    "/api/actions-projects/{actions_project_id}",
    status_code=204,
    responses={
        401: {"description": _MSG_NOT_AUTHENTICATED},
        404: {"description": "Actions Project not found"},
    },
)
def delete_actions_project(
    request: Request,
    actions_project_id: int,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
):
    try:
        _require_token(request, db, github_user)
        project = _get_project_or_404(db, actions_project_id)
    except _ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    db.delete(project)
    db.commit()
