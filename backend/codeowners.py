"""
CODEOWNERS Management API for ActionsManager.xyz

Manages the GitHub ``CODEOWNERS`` file for repositories within a project.
Mirrors the conventions used by ``rulesets`` and ``workflows``:

* GET    /api/repos/{repo_id}/codeowners            – fetch current GitHub copy
* POST   /api/repos/{repo_id}/codeowners            – save local draft
* POST   /api/repos/{repo_id}/codeowners/deploy     – commit to GitHub (direct or PR)
* GET    /api/repos/{repo_id}/codeowners/drift      – compare local vs GitHub

All endpoints require ``github_user`` and ``project_name`` query parameters
(or body fields) so that ownership and RBAC checks can be performed using
the same helpers as the rest of the application.
"""

import base64
from typing import Annotated, Optional

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import user_tokens
from database import get_db
from models import (
    Codeowners,
    Project,
    ProjectPRCampaign,
    ProjectPullRequest,
    ProjectRepo,
    Repo,
)
from workflows import _find_project_by_name


router = APIRouter()

GITHUB_API_URL = "https://api.github.com"
ACCEPT_HEADER = "application/vnd.github+json"
X_API_VERSION = "2022-11-28"

# Allowed GitHub locations for CODEOWNERS, in priority order when reading.
# Note: GitHub also supports ``docs/CODEOWNERS`` but the issue specifies only
# the two most common locations.
ALLOWED_PATHS = (".github/CODEOWNERS", "CODEOWNERS")




# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class CodeownersSaveRequest(BaseModel):
    """Body for saving a CODEOWNERS draft."""
    github_user: str
    project_name: str
    content: str
    file_path: Optional[str] = ALLOWED_PATHS[0]


class CodeownersDeployRequest(BaseModel):
    """Body for deploying a CODEOWNERS file to GitHub."""
    github_user: str
    project_name: str
    content: Optional[str] = None  # if omitted, the stored draft is used
    file_path: Optional[str] = None  # if omitted, the stored or default path is used
    branch: Optional[str] = None  # target branch; defaults to the repo default branch
    mode: str = "direct"  # "direct" → commit to branch, "pr" → branch + PR
    commit_message: Optional[str] = None
    campaign_id: Optional[int] = None  # attach this PR to an existing campaign


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _validate_file_path(path: Optional[str]) -> str:
    """Return a validated CODEOWNERS path, defaulting to ``.github/CODEOWNERS``."""
    if not path:
        return ALLOWED_PATHS[0]
    cleaned = path.strip().lstrip("/")
    if cleaned not in ALLOWED_PATHS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file_path; must be one of {ALLOWED_PATHS}",
        )
    return cleaned


def _resolve_repo_in_project(db: Session, project: Project, repo_ref: str) -> Repo:
    """Return the Repo if it belongs to *project*, else raise 404.

    ``repo_ref`` may be either the numeric ``repo_id`` (as a string) or the
    full ``owner/repo`` name.  This dual lookup keeps the URL stable while
    matching how the rest of the application identifies repositories.
    """
    query = (
        db.query(Repo)
        .join(ProjectRepo, ProjectRepo.repo_id == Repo.repo_id)
        .filter(ProjectRepo.project_id == project.project_id)
    )
    if repo_ref.isdigit():
        repo = query.filter(Repo.repo_id == int(repo_ref)).first()
    else:
        repo = query.filter(Repo.repo_name == repo_ref).first()
    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repository {repo_ref!r} not found in project '{project.project_name}'",
        )
    return repo


def _resolve_caller_and_project(
    db: Session,
    github_user: str,
    project_name: str,
    x_github_user: Optional[str] = None,
):
    """Resolve token + project, raising HTTPException on failure.

    When ``x_github_user`` (the authenticated header user) is provided, it
    must match ``github_user`` so a caller cannot use another user's token by
    passing a different username in the query/body.
    """
    if x_github_user is not None and x_github_user != github_user:
        raise HTTPException(
            status_code=403,
            detail="github_user does not match authenticated X-GitHub-User",
        )
    if github_user not in user_tokens:
        raise HTTPException(status_code=401, detail="User not authenticated")
    token = user_tokens[github_user]
    project = _find_project_by_name(db, github_user, project_name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    return token, project


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION,
    }


def _split_repo(repo_name: str):
    """Split ``owner/repo`` safely."""
    if not repo_name or "/" not in repo_name:
        raise HTTPException(status_code=400, detail=f"Invalid repository name: {repo_name!r}")
    owner, repo = repo_name.split("/", 1)
    return owner.strip(), repo.strip()


def _get_default_branch(owner: str, repo: str, headers: dict) -> str:
    resp = requests.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}", headers=headers, timeout=15)
    if resp.status_code == 200:
        return resp.json().get("default_branch", "main")
    return "main"


def _fetch_github_codeowners(owner: str, repo: str, headers: dict, branch: Optional[str] = None):
    """
    Fetch CODEOWNERS from GitHub.  Tries the standard locations in priority
    order and returns ``(content, sha, path)`` when found, or
    ``(None, None, None)`` if no CODEOWNERS file exists.
    """
    ref_qs = f"?ref={branch}" if branch else ""
    for path in ALLOWED_PATHS:
        url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{path}{ref_qs}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            try:
                content = base64.b64decode(data["content"]).decode("utf-8")
            except Exception:
                content = ""
            return content, data.get("sha"), path
        if resp.status_code == 404:
            continue
        if resp.status_code in (401, 403):
            # Auth issues should not be silently treated as "no CODEOWNERS file".
            raise HTTPException(
                status_code=502,
                detail=(
                    f"GitHub API authorization error ({resp.status_code}) reading {path}. "
                    "The GitHub token may be invalid, expired, or missing required permissions."
                ),
            )
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API error ({resp.status_code}) reading {path}",
        )
    return None, None, None


def _serialize_codeowners(record: Optional[Codeowners]) -> Optional[dict]:
    if not record:
        return None
    return {
        "id": record.id,
        "project_id": record.project_id,
        "repo_id": record.repo_id,
        "content": record.content,
        "file_path": record.file_path,
        "git_hash": record.git_hash,
        "status": record.status,
        "last_modified_by": record.last_modified_by,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _validate_codeowners_syntax(content: str) -> list:
    """
    Minimal best-effort CODEOWNERS validator.  Returns a list of warning
    strings.  Lines that are blank or comments are ignored; every other
    line must contain at least one owner token starting with ``@`` or
    looking like an email address.
    """
    warnings = []
    for idx, raw in enumerate(content.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            warnings.append(f"Line {idx}: missing owner(s) for pattern '{parts[0]}'")
            continue
        owners = parts[1:]
        for owner in owners:
            # Tighten the email check: at least one character on either side of '@'.
            looks_like_email = "@" in owner and 0 < owner.index("@") < len(owner) - 1
            if not (owner.startswith("@") or looks_like_email):
                warnings.append(
                    f"Line {idx}: owner '{owner}' is neither a @user/@team handle nor an email"
                )
    return warnings


# --------------------------------------------------------------------------- #
# Endpoints                                                                   #
# --------------------------------------------------------------------------- #


@router.get("/api/repos/{repo_ref:path}/codeowners")
def get_codeowners(
    repo_ref: str,
    github_user: str,
    project_name: str,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """
    Fetch the CODEOWNERS file from GitHub (trying both standard locations)
    and return it alongside any locally-stored draft.

    ``repo_ref`` is either the integer ``repo_id`` or the full
    ``owner/repo`` name.
    """
    token, project = _resolve_caller_and_project(db, github_user, project_name, x_github_user)
    repo = _resolve_repo_in_project(db, project, repo_ref)
    owner, repo_short = _split_repo(repo.repo_name)
    headers = _gh_headers(token)

    github_content, github_sha, github_path = _fetch_github_codeowners(owner, repo_short, headers)

    record = (
        db.query(Codeowners)
        .filter(Codeowners.project_id == project.project_id, Codeowners.repo_id == repo.repo_id)
        .first()
    )

    return {
        "success": True,
        "repo_id": repo.repo_id,
        "repo_name": repo.repo_name,
        "github": {
            "exists": github_content is not None,
            "content": github_content,
            "sha": github_sha,
            "path": github_path,
        },
        "local": _serialize_codeowners(record),
    }


@router.post("/api/repos/{repo_ref:path}/codeowners")
def save_codeowners_draft(
    repo_ref: str,
    payload: CodeownersSaveRequest,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Save a CODEOWNERS draft to the database."""
    _, project = _resolve_caller_and_project(db, payload.github_user, payload.project_name, x_github_user)
    repo = _resolve_repo_in_project(db, project, repo_ref)
    file_path = _validate_file_path(payload.file_path)

    record = (
        db.query(Codeowners)
        .filter(Codeowners.project_id == project.project_id, Codeowners.repo_id == repo.repo_id)
        .first()
    )

    if record is None:
        record = Codeowners(
            project_id=project.project_id,
            repo_id=repo.repo_id,
            content=payload.content,
            file_path=file_path,
            status="committed_locally",
            last_modified_by=payload.github_user,
        )
        db.add(record)
    else:
        record.content = payload.content
        record.file_path = file_path
        # Once edited locally, status becomes committed_locally until deployed.
        record.status = "committed_locally"
        record.last_modified_by = payload.github_user

    db.commit()
    db.refresh(record)

    warnings = _validate_codeowners_syntax(payload.content)

    return {
        "success": True,
        "message": "CODEOWNERS draft saved",
        "codeowners": _serialize_codeowners(record),
        "validation_warnings": warnings,
    }


@router.get("/api/repos/{repo_ref:path}/codeowners/drift")
def get_codeowners_drift(
    repo_ref: str,
    github_user: str,
    project_name: str,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """
    Compare the locally-stored CODEOWNERS content against the live GitHub
    copy and return a structured drift report.

    Note: when the local content matches GitHub but the stored ``git_hash``
    is stale (e.g. file was previously committed outside the platform),
    this endpoint opportunistically refreshes the local ``git_hash`` and
    flips the status to ``synced_with_github`` so subsequent drift checks
    can short-circuit on SHA equality.  This is the only side effect.
    """
    token, project = _resolve_caller_and_project(db, github_user, project_name, x_github_user)
    repo = _resolve_repo_in_project(db, project, repo_ref)
    owner, repo_short = _split_repo(repo.repo_name)
    headers = _gh_headers(token)

    github_content, github_sha, github_path = _fetch_github_codeowners(owner, repo_short, headers)
    record = (
        db.query(Codeowners)
        .filter(Codeowners.project_id == project.project_id, Codeowners.repo_id == repo.repo_id)
        .first()
    )

    local_content = record.content if record else None
    local_sha = record.git_hash if record else None

    if record is None and github_content is None:
        drift_status = "absent"
        has_drift = False
        reason = "No CODEOWNERS file managed locally or on GitHub"
    elif record is None and github_content is not None:
        drift_status = "missing_locally"
        has_drift = True
        reason = "CODEOWNERS exists on GitHub but is not managed locally"
    elif record is not None and github_content is None:
        drift_status = "missing_on_github"
        has_drift = True
        reason = "Local CODEOWNERS draft has not been deployed to GitHub"
    elif local_content == github_content:
        drift_status = "synced"
        has_drift = False
        reason = "Local content matches GitHub"
        # Opportunistically refresh the stored git_hash so future drift checks
        # short-circuit on SHA equality.
        if record and github_sha and record.git_hash != github_sha:
            record.git_hash = github_sha
            record.status = "synced_with_github"
            db.commit()
    else:
        drift_status = "content_mismatch"
        has_drift = True
        reason = "Local CODEOWNERS content differs from GitHub"

    return {
        "success": True,
        "repo_id": repo.repo_id,
        "repo_name": repo.repo_name,
        "drift_status": drift_status,
        "has_drift": has_drift,
        "reason": reason,
        "local_sha": local_sha,
        "github_sha": github_sha,
        "github_path": github_path,
    }


def _create_branch(owner: str, repo: str, new_branch: str, base_branch: str, headers: dict):
    """Create *new_branch* off the head of *base_branch* if it doesn't exist."""
    # Look up base SHA
    base_resp = requests.get(
        f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs/heads/{base_branch}",
        headers=headers,
        timeout=15,
    )
    if base_resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Could not look up base branch '{base_branch}' ({base_resp.status_code})",
        )
    base_sha = base_resp.json()["object"]["sha"]

    # Check if branch already exists
    head_resp = requests.get(
        f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs/heads/{new_branch}",
        headers=headers,
        timeout=15,
    )
    if head_resp.status_code == 200:
        return  # already exists

    create_resp = requests.post(
        f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs",
        headers=headers,
        json={"ref": f"refs/heads/{new_branch}", "sha": base_sha},
        timeout=15,
    )
    if create_resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Could not create branch '{new_branch}' ({create_resp.status_code}): {create_resp.text[:200]}",
        )


@router.post("/api/repos/{repo_ref:path}/codeowners/deploy")
def deploy_codeowners(
    repo_ref: str,
    payload: CodeownersDeployRequest,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """
    Commit the CODEOWNERS file to GitHub, either directly to a branch or via
    a pull request.

    * ``mode = "direct"`` (default) — commits to ``branch`` (or the repository
      default branch) and updates the local record's ``git_hash``.
    * ``mode = "pr"`` — creates a dedicated branch
      ``actions-manager/codeowners-{project_code}`` from the target branch,
      commits there, and opens a PR back to the target branch.
    """
    if payload.mode not in ("direct", "pr"):
        raise HTTPException(status_code=400, detail="mode must be 'direct' or 'pr'")

    token, project = _resolve_caller_and_project(db, payload.github_user, payload.project_name, x_github_user)
    repo = _resolve_repo_in_project(db, project, repo_ref)
    owner, repo_short = _split_repo(repo.repo_name)
    headers = _gh_headers(token)

    record = (
        db.query(Codeowners)
        .filter(Codeowners.project_id == project.project_id, Codeowners.repo_id == repo.repo_id)
        .first()
    )

    # Resolve content + path from payload, falling back to the saved draft.
    content = payload.content if payload.content is not None else (record.content if record else None)
    if content is None:
        raise HTTPException(
            status_code=400,
            detail="No CODEOWNERS content provided and no draft has been saved",
        )
    file_path = _validate_file_path(payload.file_path or (record.file_path if record else None))

    target_branch = payload.branch or _get_default_branch(owner, repo_short, headers)

    # Determine the branch we will actually commit to.
    # For PR mode, resolve (or create) the campaign this PR belongs to.
    pr_campaign_id: Optional[int] = None
    if payload.mode == "pr":
        commit_branch = f"actions-manager/codeowners-{project.project_code}"
        _create_branch(owner, repo_short, commit_branch, target_branch, headers)

        if payload.campaign_id is not None:
            pr_campaign_id = payload.campaign_id
        else:
            # Standalone deploy: create a dedicated campaign record.
            campaign = ProjectPRCampaign(
                project_id=project.project_id,
                created_by=payload.github_user,
            )
            db.add(campaign)
            db.commit()
            db.refresh(campaign)
            pr_campaign_id = campaign.campaign_id
    else:
        commit_branch = target_branch

    # Look up the file SHA on the commit branch (required for updates).
    contents_url = f"{GITHUB_API_URL}/repos/{owner}/{repo_short}/contents/{file_path}"
    existing_resp = requests.get(
        f"{contents_url}?ref={commit_branch}", headers=headers, timeout=15
    )
    existing_sha = None
    if existing_resp.status_code == 200:
        existing_sha = existing_resp.json().get("sha")
    elif existing_resp.status_code not in (404,):
        raise HTTPException(
            status_code=502,
            detail=f"Could not check existing CODEOWNERS ({existing_resp.status_code})",
        )

    body = {
        "message": payload.commit_message
        or f"Update {file_path} via Actions Manager [skip ci]",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": commit_branch,
    }
    if existing_sha:
        body["sha"] = existing_sha

    put_resp = requests.put(contents_url, headers=headers, json=body, timeout=30)
    if put_resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Failed to commit CODEOWNERS ({put_resp.status_code}): {put_resp.text[:200]}",
        )

    new_sha = put_resp.json().get("content", {}).get("sha")

    pr_info = None
    if payload.mode == "pr":
        pr_resp = requests.post(
            f"{GITHUB_API_URL}/repos/{owner}/{repo_short}/pulls",
            headers=headers,
            json={
                "title": f"[Actions Manager] Update {file_path}",
                "head": commit_branch,
                "base": target_branch,
                "body": (
                    f"Automated update of `{file_path}` from project "
                    f"**{project.project_name}** ({project.project_code})."
                ),
            },
            timeout=30,
        )
        if pr_resp.status_code in (200, 201):
            pr_data = pr_resp.json()
            pr_info = {"number": pr_data.get("number"), "url": pr_data.get("html_url")}

            # Track the PR in ProjectPullRequest table so it appears in "Opened PR's" list
            try:
                pr_number = pr_data.get("number")
                pr_url = pr_data.get("html_url")
                pr_title = pr_data.get("title", f"[Actions Manager] Update {file_path}")
                pr_author = pr_data.get("user", {}).get("login")
                pr_body = pr_data.get("body", "")

                # Check if PR entry already exists
                existing_pr = (
                    db.query(ProjectPullRequest)
                    .filter(
                        ProjectPullRequest.project_id == project.project_id,
                        ProjectPullRequest.repo_name == repo.repo_name,
                        ProjectPullRequest.branch_name == commit_branch,
                        ProjectPullRequest.target_branch == target_branch,
                    )
                    .first()
                )

                if existing_pr:
                    # Update existing PR entry
                    existing_pr.pr_number = pr_number
                    existing_pr.pr_url = pr_url
                    existing_pr.pr_state = "open"
                    existing_pr.title = pr_title
                    existing_pr.author = pr_author
                    existing_pr.body = pr_body
                    existing_pr.workflow_names = "CODEOWNERS"
                    if pr_campaign_id is not None and existing_pr.campaign_id is None:
                        existing_pr.campaign_id = pr_campaign_id
                else:
                    # Create new PR entry
                    new_pr = ProjectPullRequest(
                        project_id=project.project_id,
                        repo_name=repo.repo_name,
                        pr_number=pr_number,
                        pr_url=pr_url,
                        pr_state="open",
                        branch_name=commit_branch,
                        target_branch=target_branch,
                        title=pr_title,
                        author=pr_author,
                        body=pr_body,
                        workflow_names="CODEOWNERS",
                        campaign_id=pr_campaign_id,
                    )
                    db.add(new_pr)

                db.commit()
            except Exception as e:
                # Don't fail the entire operation if PR tracking fails
                print(f"⚠️ Failed to track CODEOWNERS PR in database: {str(e)}")
                db.rollback()

        elif pr_resp.status_code == 422:
            # PR likely already exists for this branch — look it up and upsert
            # the tracking record so the unified PR panel stays in sync.
            pr_info = {"warning": "Pull request already exists for this branch", "raw": pr_resp.json()}
            try:
                list_resp = requests.get(
                    f"{GITHUB_API_URL}/repos/{owner}/{repo_short}/pulls",
                    headers=headers,
                    params={"head": f"{owner}:{commit_branch}", "state": "open"},
                    timeout=15,
                )
                if list_resp.status_code == 200:
                    open_prs = list_resp.json() or []
                    if open_prs:
                        pr_data = open_prs[0]
                        pr_number = pr_data.get("number")
                        pr_url = pr_data.get("html_url")
                        pr_title = pr_data.get("title", f"[Actions Manager] Update {file_path}")
                        pr_author = pr_data.get("user", {}).get("login")
                        pr_body = pr_data.get("body", "")
                        pr_info = {"number": pr_number, "url": pr_url, "warning": "Pull request already exists for this branch"}

                        existing_pr = (
                            db.query(ProjectPullRequest)
                            .filter(
                                ProjectPullRequest.project_id == project.project_id,
                                ProjectPullRequest.repo_name == repo.repo_name,
                                ProjectPullRequest.branch_name == commit_branch,
                                ProjectPullRequest.target_branch == target_branch,
                            )
                            .first()
                        )
                        if existing_pr:
                            existing_pr.pr_number = pr_number
                            existing_pr.pr_url = pr_url
                            existing_pr.pr_state = "open"
                            existing_pr.title = pr_title
                            existing_pr.author = pr_author
                            existing_pr.body = pr_body
                            existing_pr.workflow_names = "CODEOWNERS"
                            if pr_campaign_id is not None and existing_pr.campaign_id is None:
                                existing_pr.campaign_id = pr_campaign_id
                        else:
                            db.add(ProjectPullRequest(
                                project_id=project.project_id,
                                repo_name=repo.repo_name,
                                pr_number=pr_number,
                                pr_url=pr_url,
                                pr_state="open",
                                branch_name=commit_branch,
                                target_branch=target_branch,
                                title=pr_title,
                                author=pr_author,
                                body=pr_body,
                                workflow_names="CODEOWNERS",
                                campaign_id=pr_campaign_id,
                            ))
                        db.commit()
            except Exception as e:
                print(f"⚠️ Failed to upsert existing CODEOWNERS PR tracking: {str(e)}")
                db.rollback()
        else:
            raise HTTPException(
                status_code=502,
                detail=f"Commit succeeded but PR creation failed ({pr_resp.status_code}): {pr_resp.text[:200]}",
            )

    # Persist updated state locally.
    if record is None:
        record = Codeowners(
            project_id=project.project_id,
            repo_id=repo.repo_id,
            content=content,
            file_path=file_path,
            git_hash=new_sha,
            status="under_review" if payload.mode == "pr" else "synced_with_github",
            last_modified_by=payload.github_user,
        )
        db.add(record)
    else:
        record.content = content
        record.file_path = file_path
        record.git_hash = new_sha
        record.status = "under_review" if payload.mode == "pr" else "synced_with_github"
        record.last_modified_by = payload.github_user
    db.commit()
    db.refresh(record)

    return {
        "success": True,
        "message": "CODEOWNERS deployed to GitHub",
        "mode": payload.mode,
        "branch": commit_branch,
        "target_branch": target_branch,
        "file_path": file_path,
        "git_hash": new_sha,
        "pull_request": pr_info,
        "campaign_id": pr_campaign_id,
        "codeowners": _serialize_codeowners(record),
    }


@router.get("/api/project-codeowners-statuses")
def get_project_codeowners_statuses(
    project_name: str,
    github_user: str,
    db: Annotated[Session, Depends(get_db)],
    x_github_user: Annotated[Optional[str], Header(alias="X-GitHub-User")] = None,
):
    """Return the local status of every CODEOWNERS record in a project (DB only, no GitHub calls)."""
    _, project = _resolve_caller_and_project(db, github_user, project_name, x_github_user)
    rows = (
        db.query(Codeowners.status, Repo.repo_name)
        .join(Repo, Codeowners.repo_id == Repo.repo_id)
        .filter(Codeowners.project_id == project.project_id)
        .all()
    )
    return {
        "statuses": [
            {"repo_name": repo_name, "status": status or "new"}
            for status, repo_name in rows
        ]
    }
