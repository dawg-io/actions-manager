from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.concurrency import run_in_threadpool
import httpx
from sqlalchemy.orm import Session
from typing import Annotated, Optional
from database import get_db
import auth as auth_module
from auth import user_tokens, get_github_api_endpoints
from build_detector import BuildTypeDetector
from models import Account
from github_api_tracker import github_get

router = APIRouter()

NOT_AUTHENTICATED_DETAIL = "User not authenticated"
GITHUB_JSON_ACCEPT = "application/vnd.github+json"


def _resolve_target_owner(user: str, owner: str | None, token: str, db: Session) -> tuple[str, str]:
    """
    Resolve a target GitHub owner (user or organization) for a repo action.

    The authenticated ``user`` may want to operate on a different ``owner``
    (e.g. a personal user creating an RWX repo under an organization they
    belong to). When ``owner`` is omitted or equal to ``user``, the owner's
    type is read from the local ``Account`` record. Otherwise the type is
    discovered from GitHub (``GET /users/{owner}``) and access is validated:

    * If the target is the authenticated user, no extra check.
    * If the target is an ``Organization``, the user must be a member
      (verified via ``GET /user/memberships/orgs/{owner}``).
    * If the target is a different ``User``, access is denied — a user
      cannot create or list repositories under another user's account.

    Args:
        user: Authenticated GitHub username (used for auth + access checks).
        owner: Optional desired owner login. Falls back to ``user``.
        token: GitHub access token for API calls.
        db: Database session for local Account lookups.

    Returns:
        ``(owner_login, owner_type)`` where ``owner_type`` is ``"User"`` or
        ``"Organization"``.

    Raises:
        HTTPException: 404 if the owner does not exist on GitHub,
                       403 if the authenticated user has no access to it.
    """
    target = (owner or user).strip()
    auth_user = user.strip()

    # Fast path: target is the logged-in account; use stored type.
    if target.lower() == auth_user.lower():
        account = db.query(Account).filter(Account.github_user == auth_user).first()
        owner_type = (account.github_account_type if account and account.github_account_type else "User")
        return auth_user, owner_type

    headers = {
        "Authorization": f"token {token}",
        "Accept": GITHUB_JSON_ACCEPT,
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Discover owner type from GitHub.
    user_url = f"https://api.github.com/users/{quote(target, safe='')}"
    resp = github_get(user_url, user, db, headers=headers)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"GitHub owner '{target}' not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="GitHub API error resolving owner")

    payload = resp.json() or {}
    owner_type = payload.get("type") or "User"

    if owner_type == "Organization":
        # Verify the authenticated user is a member of the target org.
        membership_url = f"https://api.github.com/user/memberships/orgs/{quote(target, safe='')}"
        m_resp = github_get(membership_url, user, db, headers=headers)
        if m_resp.status_code in (403, 404):
            raise HTTPException(
                status_code=403,
                detail=f"You do not have access to organization '{target}'",
            )
        if m_resp.status_code != 200:
            raise HTTPException(
                status_code=m_resp.status_code,
                detail="GitHub API error verifying organization access",
            )
    else:
        # Target is another user account; we don't allow cross-user actions.
        raise HTTPException(
            status_code=403,
            detail=f"Cannot operate on another user's account '{target}'",
        )

    return target, owner_type


def _repos_create_url_for_owner(owner: str, owner_type: str) -> str:
    """Return the correct GitHub repo-create URL for the given owner type."""
    if owner_type == "Organization":
        return f"https://api.github.com/orgs/{quote(owner, safe='')}/repos"
    return "https://api.github.com/user/repos"

# ✅ Database dependency

def _assert_session_owns_user(user: str, request: Request, db: Session) -> None:
    """Raise 403 if the authenticated session belongs to a different GitHub user."""
    account = auth_module.resolve_authenticated_user(request, db)
    if account.github_user.lower() != user.lower():
        raise HTTPException(status_code=403, detail="Access denied")


def _should_restrict_to_public_repos(user: str, db: Session) -> bool:
    """
    Determine if a user should be restricted to public repositories only.
    Free users are restricted, while professional and enterprise users have full access.
    Uses tier_service to get effective tier considering installation mode.
    
    Args:
        user: GitHub username
        db: Database session
        
    Returns:
        bool: True if user should only see public repos, False if full access
    """
    try:
        account = db.query(Account).filter(Account.github_user == user).first()
        if not account:
            # No account record - restrict by default for safety
            return True
        
        # Get effective tier using tier_service (handles both cloud and self-hosted modes)
        from tier_service import get_effective_tier
        effective_tier = get_effective_tier(account)
        
        # Free accounts are restricted to public repos only
        if effective_tier == "free":
            return True
            
        # Professional and enterprise accounts have full access
        if effective_tier in ("professional", "enterprise"):
            return False
            
        # Any other tier - restrict by default for safety
        return True
        
    except Exception as e:
        # On any error, restrict by default for safety
        print(f"Error checking account type for user {user}: {e}")
        return True


@router.get("/api/repos", responses={403: {"description": "Access denied"}})
def get_repos(user: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Returns the authenticated user's repositories, filtered by account type.

    Paginates through all pages of the GitHub repos endpoint so that
    organizations (or users) with more than 100 repositories are fully
    represented.
    """
    _assert_session_owns_user(user, request, db)
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    token = user_tokens[user]
    
    # Get the correct API endpoint based on account type
    endpoints = get_github_api_endpoints(user, db)
    headers = {"Authorization": f"token {token}"}

    # Paginate through all pages (GitHub returns max 100 per page)
    # Include type=all to get repos the user owns, collaborates on, and is an org member of
    # Note: visibility parameter is only for GitHub Enterprise, not github.com
    # With repo OAuth scope, type=all will return both public and private repos
    all_repos: list = []
    page = 1
    while True:
        separator = "&" if "?" in endpoints["repos_list"] else "?"
        paginated_url = f"{endpoints['repos_list']}{separator}per_page=100&page={page}&type=all"
        response = github_get(paginated_url, user, db, headers=headers)

        if response.status_code != 200:
            return {"error": f"GitHub API error: {response.status_code}"}

        batch = response.json()
        if not batch:
            break
        all_repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    # Filter repositories based on account type
    restrict_to_public = _should_restrict_to_public_repos(user, db)
    
    filtered_repos = []
    for repo in all_repos:
        # For restricted accounts, only include public repositories
        if restrict_to_public and repo.get("private", False):
            continue  # Skip private repositories for free users
        
        owner_info = repo.get("owner", {})
        filtered_repos.append({
            "id": repo["id"], 
            "name": repo["name"], 
            "full_name": repo["full_name"],
            "private": repo.get("private", False),
            "owner": owner_info.get("login", user),
            "owner_type": owner_info.get("type", "User"),
        })
    
    return filtered_repos

@router.get("/api/branches/{owner}/{repo}", responses={403: {"description": "Access denied"}})
def get_branches(user: str, owner: str, repo: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Fetch all branches of a GitHub repository."""
    _assert_session_owns_user(user, request, db)
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    token = user_tokens[user]
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}

    url = f"https://api.github.com/repos/{owner}/{repo}/branches"
    response = github_get(url, user, db, headers=headers)

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="GitHub repository not found or access denied")

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="GitHub API error")

    return response.json()


@router.post("/api/create-repo")
async def create_github_repo(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Creates a GitHub repository named 'am-reuseable-workflow'.

    Accepts an optional ``owner`` field in the JSON body to create the repo
    under a specific user or organization. Defaults to the authenticated user.
    """
    try:
        data = await request.json()
        user = data.get("user")
        if user not in user_tokens:
            return {"error": NOT_AUTHENTICATED_DETAIL, "status": 401}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": GITHUB_JSON_ACCEPT,
            "X-GitHub-Api-Version": "2022-11-28"
        }
        repo_name = "am-reuseable-workflow"
        payload = {
            "name": repo_name,
            "description": "A repository for reusable workflows",
            "private": True,
            "auto_init": True  # Creates an initial commit with a README
        }

        # Resolve the target owner (defaults to the authenticated user) and
        # validate access. This lets a personal user create the repo under
        # an organization they belong to. Owner resolution issues blocking
        # GitHub HTTP requests via ``github_get`` (sync ``requests`` wrapper),
        # so we run it in a threadpool to avoid blocking the event loop.
        try:
            owner_login, owner_type = await run_in_threadpool(
                _resolve_target_owner, user, data.get("owner"), token, db
            )
        except HTTPException as he:
            return {"error": he.detail, "status": he.status_code}
        create_repo_url = _repos_create_url_for_owner(owner_login, owner_type)

        async with httpx.AsyncClient() as client:
            response = await client.post(create_repo_url, json=payload, headers=headers)
            response_data = response.json()

            if response.status_code == 201:
                return {
                    "message": f"✅ Repository '{repo_name}' created successfully!",
                    "repo_url": response_data.get("html_url"),
                    "owner": owner_login,
                    "repo_name": repo_name,
                }
            else:
                return {"error": response_data, "status": response.status_code}

    except Exception as e:
        return {"error": str(e)}

@router.post("/api/rwx-repos")
async def create_rwx_repo(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Creates a public GitHub repository for reusable workflows, labeled with the topic 'am-rwx'.

    Accepts an optional ``owner`` field in the JSON body to create the repo
    under a specific user or organization. Defaults to the authenticated user.
    """
    try:
        data = await request.json()
        user = data.get("user")
        repo_name = data.get("repo_name", "").strip()

        if not user or user not in user_tokens:
            return {"error": NOT_AUTHENTICATED_DETAIL, "status": 401}

        if not repo_name:
            return {"error": "Repository name is required", "status": 400}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": GITHUB_JSON_ACCEPT,
            "X-GitHub-Api-Version": "2022-11-28"
        }

        # Resolve the target owner (defaults to the authenticated user) and
        # validate access. This is what allows a personal user to create the
        # RWX repo under an organization they belong to. Run in a threadpool
        # because ``_resolve_target_owner`` calls the sync ``github_get``.
        try:
            owner_login, owner_type = await run_in_threadpool(
                _resolve_target_owner, user, data.get("owner"), token, db
            )
        except HTTPException as he:
            return {"error": he.detail, "status": he.status_code}
        create_repo_url = _repos_create_url_for_owner(owner_login, owner_type)

        payload = {
            "name": repo_name,
            "description": "Reusable workflows repository managed by Actions Manager",
            "private": False,
            "auto_init": True
        }

        async with httpx.AsyncClient() as client:
            # Create the repository
            response = await client.post(create_repo_url, json=payload, headers=headers)
            response_data = response.json()

            if response.status_code not in (200, 201):
                error_msg = response_data.get("message", str(response_data))
                return {"error": error_msg, "status": response.status_code}

            full_name = response_data.get("full_name", f"{owner_login}/{repo_name}")

            # Apply the topic 'am-rwx' to the new repository
            topics_url = f"https://api.github.com/repos/{full_name}/topics"
            topics_response = await client.put(
                topics_url,
                json={"names": ["am-rwx"]},
                headers=headers,
            )

            if topics_response.status_code != 200:
                # Surface topic application failures so the caller knows the repo
                # will not appear in /api/rwx-repos searches.
                try:
                    topics_data = topics_response.json()
                except ValueError:
                    topics_data = {}
                error_msg = topics_data.get(
                    "message",
                    f"Failed to apply 'am-rwx' topic (status {topics_response.status_code})",
                )
                return {"error": error_msg, "status": topics_response.status_code}
            return {
                "message": f"✅ Repository '{repo_name}' created successfully!",
                "repo_name": repo_name,
                "full_name": full_name,
                "owner": owner_login,
                "repo_url": response_data.get("html_url")
            }

    except Exception as e:
        return {"error": str(e)}


@router.get("/api/rwx-repos", responses={403: {"description": "Access denied"}})
async def get_rwx_repos(
    user: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    owner: Annotated[str | None, Query(description="Optional advanced override: scope search to a single owner (user or org).")] = None,
):
    """Returns reusable-workflow repositories accessible to the authenticated user.

    Discovery semantics
    -------------------
    * **No ``owner`` (default, recommended):** the endpoint mirrors the
      standard project repo picker — it lists every repository the
      authenticated account can see (including org-owned repos that the
      user or App installation has access to) via the same endpoint as
      ``/api/repos`` (``GET /user/repos`` for User accounts or
      ``GET /orgs/{org}/repos`` for Organization accounts) and then
      filters them down to those carrying the ``am-rwx`` topic.

      This means a personal user who belongs to ``my-org`` will see
      ``my-org/my-rwx`` alongside their personal RWX repos without
      having to type the org login.

    * **``owner`` provided (advanced override):** the endpoint scopes a
      ``GitHub /search/repositories`` call to that single owner using
      the appropriate qualifier (``user:`` vs ``org:``) based on the
      *target* owner's type. The owner is validated via
      ``_resolve_target_owner`` (membership checked for orgs) before
      any data is returned.
    """
    _assert_session_owns_user(user, request, db)
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    token = user_tokens[user]
    headers = {
        "Authorization": f"token {token}",
        "Accept": GITHUB_JSON_ACCEPT,
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # ---- Advanced: explicit single-owner search ----
    if owner:
        # ``_resolve_target_owner`` issues blocking GitHub HTTP calls via
        # the sync ``github_get`` helper, so run it in a threadpool.
        owner_login, owner_type = await run_in_threadpool(
            _resolve_target_owner, user, owner, token, db
        )
        qualifier = "org" if owner_type == "Organization" else "user"
        raw_query = f"{qualifier}:{owner_login} topic:am-rwx"
        encoded_query = quote(raw_query, safe="")

        items: list = []
        page = 1
        async with httpx.AsyncClient() as client:
            while True:
                search_url = (
                    f"https://api.github.com/search/repositories"
                    f"?q={encoded_query}&per_page=100&page={page}"
                )
                response = await client.get(search_url, headers=headers)
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="GitHub API error fetching RWX repos",
                    )
                batch = response.json().get("items", [])
                if not batch:
                    break
                items.extend(batch)
                if len(batch) < 100:
                    break
                page += 1

        return [
            _serialize_rwx_repo(repo, owner_login, owner_type)
            for repo in items
        ]

    # ---- Default: auto-discover across all accessible accounts ----
    # Use the same endpoint as the standard project picker so org repos
    # the user / App installation has access to are included automatically.
    # ``github_get`` is sync (uses ``requests``); offload to a threadpool so
    # paginating through many pages does not block the event loop.
    endpoints = get_github_api_endpoints(user, db)
    repos_list_url = endpoints["repos_list"]

    all_repos: list = []
    page = 1
    while True:
        separator = "&" if "?" in repos_list_url else "?"
        # Include type=all to match the standard repos endpoint behavior
        # Note: visibility parameter is only for GitHub Enterprise, not github.com
        paginated_url = f"{repos_list_url}{separator}per_page=100&page={page}&type=all"
        response = await run_in_threadpool(
            github_get, paginated_url, user, db, headers=headers
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="GitHub API error fetching RWX repos",
            )

        batch = response.json() or []
        if not batch:
            break
        all_repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    # Filter to RWX repos (those tagged with the am-rwx topic). The standard
    # /user/repos and /orgs/{org}/repos responses include `topics` by default.
    rwx_repos = [r for r in all_repos if "am-rwx" in (r.get("topics") or [])]

    # Apply tier-based visibility restriction (free users: public only) so
    # discovery matches the standard project picker's filtering.
    restrict_to_public = _should_restrict_to_public_repos(user, db)
    if restrict_to_public:
        rwx_repos = [r for r in rwx_repos if not r.get("private", False)]

    return [_serialize_rwx_repo(r) for r in rwx_repos]


def _serialize_rwx_repo(repo: dict, default_owner: str | None = None, default_owner_type: str = "User") -> dict:
    """Project a GitHub repo payload to the shape the RWX picker expects."""
    owner_info = repo.get("owner") or {}
    return {
        "id": repo["id"],
        "name": repo["name"],
        "full_name": repo["full_name"],
        "private": repo.get("private", False),
        "html_url": repo.get("html_url", ""),
        "owner": owner_info.get("login", default_owner or ""),
        "owner_type": owner_info.get("type", default_owner_type),
    }


@router.get("/api/repos/status/{user}/{repo_name}", responses={403: {"description": "Access denied"}})
def check_repo_status(user: str, repo_name: str, request: Request, db: Annotated[Session, Depends(get_db)], owner: Annotated[Optional[str], Query()] = None):
    """Checks if the specified repository exists on GitHub.

    Args:
        user: Authenticated GitHub username (used for auth token lookup).
        repo_name: Repository name to check.
        owner (str, optional): Owner (user or org) of the repo. Defaults to
            the authenticated user for backward compatibility, but callers
            should pass the actual owner when checking org-owned repositories.
    """
    _assert_session_owns_user(user, request, db)
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    token = user_tokens[user]
    headers = {
        "Authorization": f"token {token}",
        "Accept": GITHUB_JSON_ACCEPT,
        "X-GitHub-Api-Version": "2022-11-28"
    }
    repo_owner = owner or user
    repo_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
    response = github_get(repo_url, user, db, headers=headers)

    if response.status_code == 200:
        return {"exists": True}
    elif response.status_code == 404:
        return {"exists": False}
    else:
        return {"error": f"GitHub API error: {response.status_code}"}


@router.get("/api/repos/detect-build-type/{owner}/{repo}", responses={403: {"description": "Access denied"}})
def detect_build_type(user: str, owner: str, repo: str, request: Request, db: Annotated[Session, Depends(get_db)]):
    """Detect build types in a GitHub repository."""
    _assert_session_owns_user(user, request, db)
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    token = user_tokens[user]
    
    try:
        detector = BuildTypeDetector(token)
        build_types = detector.detect_build_types(owner, repo)
        
        # Convert BuildType objects to dictionaries for JSON response
        result = []
        for build_type in build_types:
            result.append({
                "name": build_type.name,
                "technology": build_type.technology,
                "confidence": build_type.confidence,
                "files_found": build_type.files_found,
                "suggested_workflow": build_type.suggested_workflow
            })
        
        return {
            "repository": f"{owner}/{repo}",
            "detected_build_types": result,
            "total_detected": len(result)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting build types: {str(e)}")


@router.get("/api/repos/suggest-workflow/{owner}/{repo}", responses={403: {"description": "Access denied"}})
def suggest_workflow(user: str, owner: str, repo: str, request: Request, db: Annotated[Session, Depends(get_db)], build_type: str = None):
    """Suggest a workflow based on detected build types or a specific build type."""
    _assert_session_owns_user(user, request, db)
    if user not in user_tokens:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    token = user_tokens[user]
    
    try:
        detector = BuildTypeDetector(token)
        
        if build_type:
            # Return workflow for specific build type
            workflow = detector._get_suggested_workflow(build_type)
            if workflow:
                return {
                    "repository": f"{owner}/{repo}",
                    "build_type": build_type,
                    "workflow": workflow
                }
            else:
                raise HTTPException(status_code=404, detail=f"No workflow template found for build type: {build_type}")
        else:
            # Auto-detect and return workflow for highest confidence build type
            build_types = detector.detect_build_types(owner, repo)
            
            if not build_types:
                raise HTTPException(status_code=404, detail="No build types detected in this repository")
            
            # Get the highest confidence build type
            primary_build_type = build_types[0]
            
            return {
                "repository": f"{owner}/{repo}",
                "detected_build_type": primary_build_type.name,
                "technology": primary_build_type.technology,
                "confidence": primary_build_type.confidence,
                "files_found": primary_build_type.files_found,
                "workflow": primary_build_type.suggested_workflow
            }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error suggesting workflow: {str(e)}")
