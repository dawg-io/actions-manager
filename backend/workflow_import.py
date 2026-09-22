"""
Workflow Import Module for ActionsManager.

Provides guided import flow for existing GitHub Actions workflows:
- Discover existing workflows from selected project repositories
- Preview workflow content before importing
- Import workflows locally (reusing existing save logic)
- Import and create PR Campaign (reusing existing PR creation logic)

All imported workflows use existing state model values:
- workflow_status: new → committed_locally → under_review → synced_with_github
- project.pr_state: new → draft → open → synced
- workflow_git_hash remains null/zeros until a real GitHub baseline is established
"""

import re
import requests
import base64
import traceback
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
import auth as auth_module
from auth import user_tokens
from reusable_workflow_detection import is_reusable_workflow_yaml
from models import (
    Workflow, ProjectWorkflow, Account, Project, Repo, ProjectRepo,
    WorkflowVersion, WorkspaceMember,
)
from workflows import (
    _find_project_by_name,
    create_or_update_workflow,
    get_all_workflow_shas,
    get_default_branch,
    WorkflowSchema,
    GITHUB_API_URL,
    ACCEPT_HEADER,
    X_API_VERSION,
    GITHUB_TIMEOUT_SECONDS,
)
from authorization import check_project_access

router = APIRouter()

# Error responses these endpoints can return, declared on each route so they
# appear in the OpenAPI schema (and so generated clients know about them).
# Codes raised inside shared helpers count too - the rule tracks the call.
_ERROR_RESPONSES = {
    400: {"description": "Invalid request"},
    401: {"description": "Not authenticated"},
    403: {"description": "Access denied"},
    404: {"description": "Not found"},
    502: {"description": "Upstream GitHub request failed"},
}


def _responses(*codes: int) -> dict:
    """Subset of _ERROR_RESPONSES for a route's `responses=` parameter."""
    return {code: _ERROR_RESPONSES[code] for code in codes}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class DiscoveredWorkflow(BaseModel):
    """A workflow file discovered in a GitHub repository."""
    repo_name: str
    branch: str
    file_name: str
    path: str
    blob_sha: Optional[str] = None
    is_reusable: bool = False


class DiscoveryRepoResult(BaseModel):
    """Discovery result per repository."""
    repo_name: str
    branch: str
    workflows: List[DiscoveredWorkflow] = Field(default_factory=list)
    warning: Optional[str] = None
    error: Optional[str] = None


class DiscoveryResponse(BaseModel):
    """Response from the workflow discovery endpoint."""
    repositories_scanned: int
    workflows_found: int
    results: List[DiscoveryRepoResult]
    cross_repo_matches: List[dict] = Field(default_factory=list)


class PreviewRequest(BaseModel):
    """Query parameters for previewing a workflow."""
    github_user: str
    project_name: str
    repo_name: str
    branch: str
    workflow_path: str


class PreviewResponse(BaseModel):
    """Response from the workflow preview endpoint."""
    repo_name: str
    branch: str
    path: str
    file_name: str
    content: str
    blob_sha: Optional[str] = None
    is_reusable: bool = False


class ImportWorkflowItem(BaseModel):
    """A single workflow to import."""
    source_repo: str
    source_branch: str
    workflow_path: str
    content_sha: Optional[str] = None


class ImportRequest(BaseModel):
    """Request body for importing workflows."""
    github_user: str
    project_name: str
    workflows: List[ImportWorkflowItem]
    import_mode: str = "save_local_only"  # save_local_only | save_and_create_pr_campaign
    target_repos: Optional[List[str]] = None  # Only used for PR campaign mode
    # Reusable workflows discovered in a caller project's repositories can be
    # filed into a Reusable Workflow Project instead. The source repository is
    # still validated against the project being viewed; only the destination of
    # the saved row changes. Addressed by id, not name: project names are unique
    # only per owner, and the privileged lookup path falls back to a global name
    # match, so a name can resolve to a project the user did not pick.
    destination_project_id: Optional[int] = None


class ImportResult(BaseModel):
    """Result of importing a single workflow."""
    workflow_path: str
    source_repo: str
    status: str  # success | error
    message: str
    workflow_name: Optional[str] = None


class ImportResponse(BaseModel):
    """Response from the workflow import endpoint."""
    message: str
    import_mode: str
    results: List[ImportResult]
    pr_state: Optional[str] = None
    pr_results: Optional[dict] = None
    # Set when the workflows were filed into a different project than the one
    # being viewed, so the UI can say where they went.
    destination_project_name: Optional[str] = None
    destination_project_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_VALID_WORKFLOW_EXTENSIONS = (".yml", ".yaml")
_VALID_WORKFLOW_DIR = ".github/workflows/"
_PATH_TRAVERSAL_PATTERN = re.compile(r"\.\.")
_ALREADY_MANAGED_WARNING = "All discovered workflows are already managed by this project."
_ERR_PROJECT_ID_MISMATCH = "Project ID does not match authenticated project"
_ERR_DESTINATION_NOT_FOUND = "Destination project not found or access denied"


def _validate_workflow_path(path: str) -> str:
    """Validate that the path is a .github/workflows/*.yml or .yaml file.
    
    Returns the validated path or raises HTTPException.
    """
    if not path or not path.strip():
        raise HTTPException(status_code=400, detail="Workflow path cannot be empty")

    path = path.strip()

    # Prevent path traversal
    if _PATH_TRAVERSAL_PATTERN.search(path):
        raise HTTPException(status_code=400, detail="Invalid workflow path: path traversal not allowed")

    # Must be in .github/workflows/
    if not path.startswith(_VALID_WORKFLOW_DIR):
        raise HTTPException(status_code=400, detail=f"Workflow path must start with {_VALID_WORKFLOW_DIR}")

    # Must have valid extension
    if not path.lower().endswith(_VALID_WORKFLOW_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Workflow path must end with .yml or .yaml")

    # Must have a filename (not just the directory)
    filename = path[len(_VALID_WORKFLOW_DIR):]
    if not filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid workflow path: must be a file directly in .github/workflows/")

    return path


def _validate_repo_format(repo_name: str) -> tuple:
    """Validate owner/repo format and return (owner, repo) tuple."""
    if not repo_name or "/" not in repo_name:
        raise HTTPException(status_code=400, detail=f"Repository must be in 'owner/repo' format: {repo_name}")
    parts = repo_name.split("/", 1)
    if not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail=f"Repository must be in 'owner/repo' format: {repo_name}")
    return parts[0], parts[1]


def _get_authenticated_user_and_project(request: Request, db: Session, github_user: str, project_name: str, require_write: bool = False):
    """Validate authentication and project access. Returns (token, project).

    ``github_user`` is a client-supplied query parameter, so it is checked
    against the server-issued session before it is used to select any data.

    When require_write=True, ensures the user has at least project_editor access.
    Read-only / project_viewer users are rejected for write operations.
    """
    auth_module.assert_session_owns_user(github_user, request, db)

    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail="User not authenticated")

    project = _find_project_by_name(db, github_user, project_name)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied")

    # Enforce write permission when required (import, PR creation)
    if require_write:
        account = db.query(Account).filter_by(github_user=github_user).first()
        if not account:
            raise HTTPException(status_code=401, detail="User not authenticated")

        # Always allow project owner, otherwise require project_editor/project_admin.
        if account.user_id != project.user_id:
            member = db.query(WorkspaceMember).filter(
                WorkspaceMember.user_id == account.user_id
            ).first()
            effective_role = check_project_access(db, member, project.project_id) if member else None
            if effective_role not in ("project_editor", "project_admin"):
                raise HTTPException(
                    status_code=403,
                    detail="Insufficient permissions. Import requires project editor or admin access."
                )

    token = user_tokens[github_user]
    return token, project


def _resolve_import_destination(request: Request, db: Session, payload: "ImportRequest", project):
    """Resolve which project the imported workflow rows are written to.

    Defaults to the project being viewed. When the caller picks a different
    destination it must be a Reusable Workflow Project they can write to: this
    is the "file this reusable workflow where it belongs" path, not a general
    cross-project import. The source repository is still validated against the
    viewed project by the caller.

    The destination is looked up by id and then authorized through the same
    helper the viewed project uses, so a caller cannot reach a project the
    name-based lookup would not have given them.
    """
    requested_id = payload.destination_project_id
    if requested_id is None or requested_id == project.project_id:
        return project

    # "Missing", "not yours" and "resolved to a different project" all answer
    # the same way, so the response never tells an authenticated caller which
    # project ids exist. The picker only offers projects the caller can already
    # see, so this costs a legitimate user nothing.
    candidate = db.query(Project).filter(Project.project_id == requested_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail=_ERR_DESTINATION_NOT_FOUND)

    try:
        _token, destination = _get_authenticated_user_and_project(
            request, db, payload.github_user, candidate.project_name, require_write=True
        )
    except HTTPException as exc:
        if exc.status_code in (403, 404):
            raise HTTPException(
                status_code=404, detail=_ERR_DESTINATION_NOT_FOUND
            ) from exc
        raise

    # The name lookup can resolve to a different project of the same name, which
    # is exactly the ambiguity the id is here to avoid - refuse rather than
    # write somewhere the caller did not pick.
    if destination.project_id != requested_id:
        raise HTTPException(status_code=404, detail=_ERR_DESTINATION_NOT_FOUND)
    if (destination.project_type or "standard") != "rwx":
        raise HTTPException(
            status_code=400,
            detail="Workflows can only be redirected to a Reusable Workflow Project",
        )
    if payload.import_mode != "save_local_only":
        raise HTTPException(
            status_code=400,
            detail="Importing into another project supports save_local_only",
        )
    return destination


def _strip_source_project_prefix(project, workflow_stem: str) -> str:
    """Drop the viewed project's ``AM_{code}_`` prefix from a discovered name.

    Discovery reads files as GitHub stores them, so in prefix mode a stem still
    carries this project's prefix. ``create_or_update_workflow`` only strips the
    *destination's* prefix, so a redirected import would otherwise store - and
    later deliver - a doubly-prefixed name.
    """
    if not getattr(project, "use_prefix", False):
        return workflow_stem

    project_code = (getattr(project, "project_code", "") or "").strip()
    if not project_code:
        return workflow_stem

    prefix = f"am_{project_code}_".lower()
    if workflow_stem.lower().startswith(prefix):
        return workflow_stem[len(prefix):] or workflow_stem
    return workflow_stem


def _destination_already_owns(db: Session, project_id: int, workflow_stem: str) -> bool:
    """Whether the destination project already owns a workflow of this name.

    A redirected import would otherwise land on ``create_or_update_workflow``'s
    update branch and replace the destination's copy - zeroing its git hash and
    dropping it out of ``synced_with_github`` - which for a reusable workflow
    several caller projects link to means silently rewriting a shared asset.
    """
    return (
        db.query(Workflow.workflow_id)
        .join(ProjectWorkflow, ProjectWorkflow.workflow_id == Workflow.workflow_id)
        .filter(
            ProjectWorkflow.project_id == project_id,
            func.lower(Workflow.workflow_name) == workflow_stem.lower(),
        )
        .first()
        is not None
    )


def _get_project_repos(db: Session, project_id: int) -> List[Repo]:
    """Get all repos associated with a project."""
    return (
        db.query(Repo)
        .join(ProjectRepo, ProjectRepo.repo_id == Repo.repo_id)
        .filter(ProjectRepo.project_id == project_id)
        .all()
    )


def _get_managed_workflow_names(db: Session, project_id: int) -> set[str]:
    """Get normalized workflow names already attached to the project."""
    workflow_names = (
        db.query(Workflow.workflow_name)
        .join(ProjectWorkflow, ProjectWorkflow.workflow_id == Workflow.workflow_id)
        .filter(ProjectWorkflow.project_id == project_id)
        .all()
    )
    return {
        workflow_name.strip().lower()
        for (workflow_name,) in workflow_names
        if workflow_name and workflow_name.strip()
    }


def _get_discovered_workflow_match_names(file_name: str, project) -> set[str]:
    """Return normalized discovery names to compare against managed workflow names."""
    stem = file_name.rsplit(".", 1)[0].strip().lower()
    if not stem:
        return set()

    match_names = {stem}
    if getattr(project, "use_prefix", False):
        project_code = (getattr(project, "project_code", "") or "").strip().lower()
        if project_code:
            expected_prefix = f"am_{project_code}_"
            if stem.startswith(expected_prefix):
                stripped_stem = stem[len(expected_prefix):]
                if stripped_stem:
                    match_names.add(stripped_stem)
    return match_names


# A GitHub blob SHA is a hash of the content, so "is this blob a reusable
# workflow" is fixed for the life of that SHA. Caching it means re-opening the
# import panel, or scanning repos that share a workflow file, costs no further
# reads. Bounded so a long-lived worker cannot accumulate an entry per workflow
# file the workspace has ever scanned.
_REUSABLE_BLOB_CACHE: dict = {}
_REUSABLE_BLOB_CACHE_MAX = 5000


def _cache_reusable_blob(blob_sha: str, is_reusable: bool) -> None:
    """Remember a blob's classification, clearing the cache if it grows too big."""
    if len(_REUSABLE_BLOB_CACHE) >= _REUSABLE_BLOB_CACHE_MAX:
        _REUSABLE_BLOB_CACHE.clear()
    _REUSABLE_BLOB_CACHE[blob_sha] = is_reusable


def _fetch_blob_text(owner: str, repo: str, blob_sha: str, headers: dict) -> Optional[str]:
    """Return a blob's decoded text, or None when it cannot be read.

    Classification is advisory - a blob we cannot read is reported as a plain
    workflow rather than failing the whole discovery scan.
    """
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/blobs/{blob_sha}"
    try:
        response = requests.get(url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        # ValueError covers a malformed JSON body, bad base64 (binascii.Error)
        # and a non-UTF-8 blob (UnicodeDecodeError) - all subclasses.
        return base64.b64decode(response.json().get("content", "")).decode("utf-8")
    except ValueError:
        return None


def _flag_reusable_workflows(pending: List[tuple], headers: dict) -> None:
    """Set ``is_reusable`` on each discovered workflow, in place.

    ``pending`` holds ``(entry, owner, repo)`` triples. Byte-identical files
    share a blob SHA, so the case this product exists for - the same file in
    every repo of a project - costs one content read for the whole scan rather
    than one per repository, and none at all once cached.

    A blob that cannot be read is left unflagged rather than cached, so a
    transient failure does not stick for the life of the process.
    """
    for entry, owner, repo in pending:
        if not entry.blob_sha:
            continue
        if entry.blob_sha not in _REUSABLE_BLOB_CACHE:
            content = _fetch_blob_text(owner, repo, entry.blob_sha, headers)
            if content is None:
                continue
            _cache_reusable_blob(entry.blob_sha, is_reusable_workflow_yaml(content))
        entry.is_reusable = _REUSABLE_BLOB_CACHE[entry.blob_sha]


# ---------------------------------------------------------------------------
# Discover endpoint
# ---------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/workflow-import/discover", responses=_responses(400, 401, 403, 404))
def discover_workflows(
    project_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
    project_name: Annotated[str, Query(..., description="Project name")],
):
    """
    Discover existing GitHub Actions workflows from all repositories in the project.
    
    Uses Git Trees API for efficient batch SHA lookup.
    """
    token, project = _get_authenticated_user_and_project(request, db, github_user, project_name)

    # Validate project_id matches
    if project.project_id != project_id:
        raise HTTPException(status_code=403, detail=_ERR_PROJECT_ID_MISMATCH)

    repos = _get_project_repos(db, project.project_id)
    if not repos:
        return DiscoveryResponse(
            repositories_scanned=0,
            workflows_found=0,
            results=[],
            cross_repo_matches=[],
        )

    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }

    results: List[DiscoveryRepoResult] = []
    # Track workflows by filename for cross-repo comparison
    workflow_by_path: dict = {}  # {filename: [{repo, branch, sha}]}
    total_workflows = 0
    managed_workflow_names = _get_managed_workflow_names(db, project.project_id)
    # Every row we are going to return, with the repo each one's blob lives in,
    # so reusable classification runs once per distinct blob after the scan.
    pending_classification: List[tuple] = []

    for repo in repos:
        owner, repo_name_short = _validate_repo_format(repo.repo_name)
        
        try:
            branch = get_default_branch(owner, repo_name_short, headers, user=github_user, db=db)
        except Exception:
            branch = "main"

        try:
            shas = get_all_workflow_shas(owner, repo_name_short, branch, token)
        except Exception as e:
            results.append(DiscoveryRepoResult(
                repo_name=repo.repo_name,
                branch=branch,
                workflows=[],
                error=f"Failed to scan repository: {str(e)}",
            ))
            continue

        if not shas:
            results.append(DiscoveryRepoResult(
                repo_name=repo.repo_name,
                branch=branch,
                workflows=[],
                warning="No workflow files found in .github/workflows/",
            ))
            continue

        discovered = []
        yaml_workflows_found = 0
        for filename, sha in shas.items():
            # Only support top-level files directly under .github/workflows/.
            if "/" in filename or "\\" in filename:
                continue

            # Only include .yml/.yaml files
            if not filename.lower().endswith(_VALID_WORKFLOW_EXTENSIONS):
                continue

            yaml_workflows_found += 1
            workflow_match_names = _get_discovered_workflow_match_names(filename, project)
            if workflow_match_names & managed_workflow_names:
                continue

            path = f"{_VALID_WORKFLOW_DIR}{filename}"
            entry = DiscoveredWorkflow(
                repo_name=repo.repo_name,
                branch=branch,
                file_name=filename,
                path=path,
                blob_sha=sha,
            )
            discovered.append(entry)
            pending_classification.append((entry, owner, repo_name_short))

            # Track for cross-repo matching
            if filename not in workflow_by_path:
                workflow_by_path[filename] = []
            workflow_by_path[filename].append({
                "repo_name": repo.repo_name,
                "branch": branch,
                "blob_sha": sha,
            })

        total_workflows += len(discovered)
        results.append(DiscoveryRepoResult(
            repo_name=repo.repo_name,
            branch=branch,
            workflows=discovered,
            warning=_ALREADY_MANAGED_WARNING if yaml_workflows_found > 0 and not discovered else None,
        ))

    # Flag the reusable workflows so the import UI can label them and offer to
    # file them into a Reusable Workflow Project instead.
    _flag_reusable_workflows(pending_classification, headers)

    # Build cross-repo matches
    cross_repo_matches = []
    for filename, locations in workflow_by_path.items():
        if len(locations) > 1:
            shas_set = {loc["blob_sha"] for loc in locations if loc["blob_sha"]}
            cross_repo_matches.append({
                "file_name": filename,
                "path": f"{_VALID_WORKFLOW_DIR}{filename}",
                "repos": locations,
                "identical_across_repos": len(shas_set) <= 1,
            })

    return DiscoveryResponse(
        repositories_scanned=len(repos),
        workflows_found=total_workflows,
        results=results,
        cross_repo_matches=cross_repo_matches,
    )


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/workflow-import/preview", responses=_responses(400, 401, 403, 404, 502))
def preview_workflow(
    project_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(..., description="GitHub username")],
    project_name: Annotated[str, Query(..., description="Project name")],
    repo_name: Annotated[str, Query(..., description="Repository in owner/repo format")],
    branch: Annotated[str, Query(..., description="Branch name")],
    workflow_path: Annotated[str, Query(..., description="Path to workflow file")],
):
    """
    Preview a specific workflow file content from GitHub before importing.
    """
    token, project = _get_authenticated_user_and_project(request, db, github_user, project_name)

    if project.project_id != project_id:
        raise HTTPException(status_code=403, detail=_ERR_PROJECT_ID_MISMATCH)

    # Validate inputs
    validated_path = _validate_workflow_path(workflow_path)
    owner, repo_short = _validate_repo_format(repo_name)

    # Validate the repo is in this project
    repo_record = db.query(Repo).filter(Repo.repo_name == repo_name).first()
    if not repo_record:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found")

    project_repo = db.query(ProjectRepo).filter_by(
        project_id=project.project_id, repo_id=repo_record.repo_id
    ).first()
    if not project_repo:
        raise HTTPException(status_code=403, detail=f"Repository '{repo_name}' is not part of this project")

    # Fetch file content from GitHub
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }

    file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo_short}/contents/{validated_path}?ref={branch}"

    try:
        response = requests.get(file_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API request failed: {str(e)}")

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Workflow file not found: {validated_path}")
    elif response.status_code == 403:
        raise HTTPException(status_code=403, detail="Access denied to repository or rate limit exceeded")
    elif response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {response.status_code}")

    file_data = response.json()
    content = base64.b64decode(file_data.get("content", "")).decode("utf-8")
    blob_sha = file_data.get("sha")
    file_name = validated_path.split("/")[-1]

    return PreviewResponse(
        repo_name=repo_name,
        branch=branch,
        path=validated_path,
        file_name=file_name,
        content=content,
        blob_sha=blob_sha,
        is_reusable=is_reusable_workflow_yaml(content),
    )


# ---------------------------------------------------------------------------
# Import endpoint
# ---------------------------------------------------------------------------

@router.post("/api/projects/{project_id}/workflow-import", responses=_responses(400, 401, 403, 404))
def import_workflows(
    project_id: int,
    payload: ImportRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """
    Import one or more existing GitHub workflow files into ActionsManager.

    Modes:
    - save_local_only: Saves workflow locally, does NOT write to GitHub, does NOT create drift.
    - save_and_create_pr_campaign: Saves locally and creates PRs for target repositories.
    """
    token, project = _get_authenticated_user_and_project(
        request, db, payload.github_user, payload.project_name, require_write=True
    )

    if project.project_id != project_id:
        raise HTTPException(status_code=403, detail=_ERR_PROJECT_ID_MISMATCH)

    if payload.import_mode not in ("save_local_only", "save_and_create_pr_campaign"):
        raise HTTPException(status_code=400, detail="import_mode must be 'save_local_only' or 'save_and_create_pr_campaign'")

    if not payload.workflows:
        raise HTTPException(status_code=400, detail="At least one workflow must be specified for import")

    destination = _resolve_import_destination(request, db, payload, project)
    redirected = destination.project_id != project.project_id

    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }

    import_results: List[ImportResult] = []
    # A campaign carries reusable workflows in their own field, so the two kinds
    # have to be told apart when the payload is built below.
    reusable_stems: set = set()

    for item in payload.workflows:
        try:
            # Validate inputs
            validated_path = _validate_workflow_path(item.workflow_path)
            owner, repo_short = _validate_repo_format(item.source_repo)

            # Validate the repo is in this project
            repo_record = db.query(Repo).filter(Repo.repo_name == item.source_repo).first()
            if not repo_record:
                import_results.append(ImportResult(
                    workflow_path=item.workflow_path,
                    source_repo=item.source_repo,
                    status="error",
                    message=f"Repository '{item.source_repo}' not found",
                ))
                continue

            project_repo = db.query(ProjectRepo).filter_by(
                project_id=project.project_id, repo_id=repo_record.repo_id
            ).first()
            if not project_repo:
                import_results.append(ImportResult(
                    workflow_path=item.workflow_path,
                    source_repo=item.source_repo,
                    status="error",
                    message=f"Repository '{item.source_repo}' is not part of this project",
                ))
                continue

            # Fetch workflow content from GitHub
            file_url = f"{GITHUB_API_URL}/repos/{owner}/{repo_short}/contents/{validated_path}?ref={item.source_branch}"
            response = requests.get(file_url, headers=headers, timeout=GITHUB_TIMEOUT_SECONDS)

            if response.status_code != 200:
                import_results.append(ImportResult(
                    workflow_path=item.workflow_path,
                    source_repo=item.source_repo,
                    status="error",
                    message=f"Failed to fetch workflow from GitHub (status {response.status_code})",
                ))
                continue

            file_data = response.json()
            content = base64.b64decode(file_data.get("content", "")).decode("utf-8")
            blob_sha = file_data.get("sha")

            # Extract workflow name (stem without extension)
            file_name = validated_path.split("/")[-1]
            workflow_stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
            workflow_stem = _strip_source_project_prefix(project, workflow_stem)

            # Use existing create_or_update_workflow to save locally
            # This reuses the exact same logic as the /api/save-workflows endpoint
            if redirected and _destination_already_owns(db, destination.project_id, workflow_stem):
                import_results.append(ImportResult(
                    workflow_path=item.workflow_path,
                    source_repo=item.source_repo,
                    status="error",
                    message=(
                        f"'{destination.project_name}' already has a workflow named "
                        f"'{workflow_stem}'. Rename one of them, or edit it there instead "
                        f"of importing over it."
                    ),
                ))
                continue

            workflow_schema = WorkflowSchema(name=workflow_stem, content=content)
            is_reusable = is_reusable_workflow_yaml(content)

            create_or_update_workflow(
                db, workflow_schema, destination.project_id,
                is_reusable=is_reusable,
                last_modified_by=payload.github_user,
            )

            # Store import metadata in version metadata.
            # Case-insensitive equality rather than ILIKE: '_' is a single-char
            # wildcard in SQL LIKE and workflow names routinely contain it.
            saved_wf = (
                db.query(Workflow)
                .join(ProjectWorkflow)
                .filter(
                    ProjectWorkflow.project_id == destination.project_id,
                    func.lower(Workflow.workflow_name) == workflow_stem.lower(),
                )
                .first()
            )

            if saved_wf:
                # Update the latest version with import metadata
                latest_version = (
                    db.query(WorkflowVersion)
                    .filter_by(workflow_id=saved_wf.workflow_id)
                    .order_by(WorkflowVersion.version_number.desc())
                    .first()
                )
                if latest_version:
                    import json
                    try:
                        existing_meta = json.loads(latest_version.version_metadata or "{}")
                    except (json.JSONDecodeError, TypeError):
                        existing_meta = {}
                    existing_meta.update({
                        "imported_from_repo": item.source_repo,
                        "imported_from_branch": item.source_branch,
                        "imported_from_path": validated_path,
                        "imported_git_hash": blob_sha,
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                    })
                    latest_version.version_metadata = json.dumps(existing_meta)
                    db.commit()

            if is_reusable:
                reusable_stems.add(workflow_stem)

            import_results.append(ImportResult(
                workflow_path=item.workflow_path,
                source_repo=item.source_repo,
                status="success",
                message="Workflow imported and saved locally",
                workflow_name=workflow_stem,
            ))

        except HTTPException as he:
            import_results.append(ImportResult(
                workflow_path=item.workflow_path,
                source_repo=item.source_repo,
                status="error",
                message=he.detail,
            ))
        except Exception as e:
            import_results.append(ImportResult(
                workflow_path=item.workflow_path,
                source_repo=item.source_repo,
                status="error",
                message=f"Unexpected error: {str(e)}",
            ))

    success_count = sum(1 for r in import_results if r.status == "success")

    # Transition project state: new/synced → draft (same as save-workflows),
    # but only when at least one workflow was imported successfully. The
    # project that gained the workflows is the one whose state moves, which is
    # the destination when the import was redirected to an RWX project.
    if success_count > 0 and destination.pr_state in ("new", "synced"):
        destination.pr_state = "draft"
        destination.last_modified_by = payload.github_user
        db.commit()
        db.refresh(destination)

    # If save_and_create_pr_campaign, invoke existing PR creation logic
    pr_results = None
    if payload.import_mode == "save_and_create_pr_campaign":
        successful_workflow_names = [
            r.workflow_name for r in import_results
            if r.status == "success" and r.workflow_name
        ]
        # Default target_repos to the project's configured repositories if not provided
        effective_target_repos = payload.target_repos
        if not effective_target_repos:
            project_repos = _get_project_repos(db, project.project_id)
            effective_target_repos = [r.repo_name for r in project_repos]

        if successful_workflow_names and effective_target_repos:
            try:
                from workflows import create_pull_requests, CreatePullRequestsRequest
                # Reusable workflows travel in their own field.
                # _build_reusable_workflow_results covers both the ones this
                # project owns and the ones it links from an RWX project, but
                # only when selected_reusable_workflows is set - left None it
                # returns nothing, which is how an imported reusable workflow
                # used to end up saved and absent from every pull request.
                #
                # "or None" is load-bearing on both lines: None means "no
                # workflows of this kind", while an empty list would still mark
                # this a regular-workflow run (see _includes_regular_workflows).
                regular_names = [
                    n for n in successful_workflow_names if n not in reusable_stems
                ]
                reusable_names = [
                    n for n in successful_workflow_names if n in reusable_stems
                ]
                pr_payload = CreatePullRequestsRequest(
                    github_user=payload.github_user,
                    project_name=payload.project_name,
                    selected_repos=effective_target_repos,
                    selected_workflows=regular_names or None,
                    selected_reusable_workflows=reusable_names or None,
                )
                # create_pull_requests is a route function
                # (payload, background_tasks, db, ...); called directly it needs
                # background_tasks supplied positionally and db passed
                # explicitly. async_mode defaults False, so BackgroundTasks()
                # is never used.
                pr_response = create_pull_requests(
                    pr_payload, BackgroundTasks(), db, github_user=payload.github_user
                )
                pr_results = pr_response
                # Refresh project state after PR creation
                db.refresh(project)
            except Exception as e:
                # This reported a signature error to the user as a campaign
                # failure and to the logs not at all, which is how the call
                # above stayed broken (#2070).
                traceback.print_exc()
                pr_results = {"error": str(e)}

    error_count = sum(1 for r in import_results if r.status == "error")

    campaign_failed = isinstance(pr_results, dict) and bool(pr_results.get("error"))

    if redirected:
        message = f"Imported {success_count} workflow(s) into '{destination.project_name}'."
    elif payload.import_mode == "save_local_only":
        message = f"Imported {success_count} workflow(s) locally."
    elif campaign_failed or pr_results is None:
        # Saying a campaign was created when none was is worse than saying
        # nothing: the workflows are saved either way, the PRs are not.
        message = f"Imported {success_count} workflow(s) locally. No PR Campaign was created."
    else:
        message = f"Imported {success_count} workflow(s) and created PR Campaign."

    if error_count > 0:
        message += f" {error_count} workflow(s) failed."

    return ImportResponse(
        message=message,
        import_mode=payload.import_mode,
        results=import_results,
        pr_state=project.pr_state,
        pr_results=pr_results,
        destination_project_name=destination.project_name if redirected else None,
        destination_project_id=destination.project_id if redirected else None,
    )
