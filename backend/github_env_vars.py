import httpx
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote
from typing import Annotated
from database import get_db
from auth import user_tokens
from models import Project, Account, ProjectEnvVar  # ✅ Import ProjectEnvVar for storing env var names

router = APIRouter()
GITHUB_API_URL = "https://api.github.com"
ACCEPT_HEADER = "application/vnd.github+json"
X_API_VERSION = "2022-11-28"
AUTH_STRING = "User not authenticated"
ERROR_CODE = "No repositories provided"

async def count_project_env_vars(user: str, project_code: str, repo_names: list, use_prefix: bool = True, project_id: int = None, db: Session = None) -> int:
    """Helper function to count environment variables for a project across repositories"""
    if user not in user_tokens:
        return 0
    
    # If prefix is disabled, count from local database
    if not use_prefix and project_id is not None and db is not None:
        count = db.query(ProjectEnvVar).filter(
            ProjectEnvVar.project_id == project_id
        ).count()
        return count
    
    # For prefixed env vars, count from GitHub
    token = user_tokens[user]
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION
    }
    
    unique_env_vars = set()
    
    async with httpx.AsyncClient() as client:
        for repo_name in repo_names:
            try:
                env_vars_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables?per_page=100"
                response = await client.get(env_vars_url, headers=headers)
                
                if response.status_code == 200:
                    env_var_data = response.json()
                    variables = env_var_data.get("variables", [])
                    
                    for env_var in variables:
                        env_var_name = env_var["name"]
                        if env_var_name.startswith(f"AM_{project_code}_"):
                            unique_env_vars.add(env_var_name)
            except Exception as e:
                print(f"❌ Error counting env vars for {repo_name}: {str(e)}")
    
    return len(unique_env_vars)


async def count_project_environments(user: str, repo_names: list) -> int:
    """Helper function to count deployment environments for a project across repositories"""
    if user not in user_tokens:
        return 0
    
    token = user_tokens[user]
    headers = {
        "Authorization": f"token {token}",
        "Accept":  ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION
    }
    
    unique_environments = set()
    
    async with httpx.AsyncClient() as client:
        for repo_name in repo_names:
            try:
                environments_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments"
                response = await client.get(environments_url, headers=headers)
                
                if response.status_code == 200:
                    env_data = response.json()
                    environments = env_data.get("environments", [])
                    
                    for env in environments:
                        env_name = env["name"]
                        unique_environments.add(env_name)
            
            except Exception as e:
                print(f"❌ Error counting environments for {repo_name}: {str(e)}")
    
    return len(unique_environments)




def _validate_request_data(data: dict) -> tuple[str, list, list, str]:
    """Extract and validate request data"""
    user = data.get("user")
    repo_names = data.get("repo_names")
    env_vars = data.get("env") if isinstance(data.get("env"), list) else []
    project_name = data.get("project_name", "").strip()
    return user, repo_names, env_vars, project_name


def _get_auth_headers(user: str) -> dict:
    """Get authentication headers for GitHub API"""
    if user not in user_tokens:
        return {}
    
    token = user_tokens[user]
    return {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION
    }


def _format_env_var_key(original_key: str, project_code: str, use_prefix: bool = True) -> str:
    """Format environment variable key with or without project prefix"""
    project_code = project_code.upper()
    prefix = f"AM_{project_code}_"
    
    if not use_prefix:
        # No prefix mode - just use the key as-is (uppercased)
        return original_key.upper()
    
    # Prefix mode
    if original_key.upper().startswith(prefix):
        # Key already has prefix, strip it first
        clean_key = original_key[len(prefix):]
        print(f"🔧 Stripped existing prefix from '{original_key}' -> '{clean_key}'")
    else:
        clean_key = original_key
    
    return f"AM_{project_code}_{clean_key.upper()}"


async def _check_variable_exists_in_repos(formatted_key: str, repo_names: list, headers: dict) -> bool:
    """Check if variable exists in any of the specified repositories"""
    async with httpx.AsyncClient() as client:
        for repo_name in repo_names:
            check_var_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables/{formatted_key}"
            check_var_response = await client.get(check_var_url, headers=headers)
            if check_var_response.status_code == 200:
                return True
    return False


def _validate_sync_environment_request(data: dict) -> tuple[str, str, list, str]:
    """Extract and validate sync environment request data"""
    user = data.get("user")
    project_name = data.get("project_name", "").strip()
    repo_names = data.get("repo_names", [])
    environment_name = data.get("environment_name", "").strip()
    return user, project_name, repo_names, environment_name


async def _check_free_account_environment_limits(user: str, repo_names: list, environment_name: str, client: httpx.AsyncClient, headers: dict) -> dict:
    """Check if creating environments would exceed account limits.

    In self-hosted beta mode the limit is 6 per project regardless of account
    type.  In cloud mode only free-tier accounts are gated here (at 2).
    """
    from tier_service import is_self_hosted_beta, SELF_HOSTED_BETA_LIMITS

    current_count = await count_project_environments(user, repo_names)
    
    # Count how many new environments we'll be creating
    new_envs_count = 0
    for repo_name in repo_names:
        owner, repo = repo_name.split("/")
        check_env_url = f"https://api.github.com/repos/{owner}/{repo}/environments/{environment_name}"
        check_response = await client.get(check_env_url, headers=headers)
        if check_response.status_code != 200:  # Environment doesn't exist
            new_envs_count += 1

    if is_self_hosted_beta():
        limit = SELF_HOSTED_BETA_LIMITS["environments_per_project"]
        if current_count + new_envs_count > limit:
            return {
                "error": (
                    f"Self-hosted beta allows up to {limit} GitHub environments per project. "
                    f"Syncing would create {new_envs_count} new environment(s), "
                    f"but you already have {current_count}. "
                    f"Paid plans are not available during the self-hosted beta."
                ),
                "status": 403,
                "current_count": current_count,
                "limit": limit,
            }
        return {}

    # Cloud mode: only gate free-tier accounts (limit 2)
    if current_count + new_envs_count > 2:
        return {
            "error": f"Free plan users can create up to 2 deployment environments per project. Syncing would create {new_envs_count} new environments, but you already have {current_count}.", 
            "status": 403,
            "current_count": current_count,
            "limit": 2
        }
    
    return {}


async def _find_existing_environments(repo_names: list, environment_name: str, client: httpx.AsyncClient, headers: dict) -> dict:
    """Find repositories that already have the specified environment"""
    existing_environments = {}
    for repo_name in repo_names:
        owner, repo = repo_name.split("/")
        url = f"https://api.github.com/repos/{owner}/{repo}/environments"
        
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            environments = response.json().get("environments", [])
            env_names = [env.get("name") for env in environments]
            if environment_name in env_names:
                existing_environments[repo_name] = True
    
    return existing_environments


async def _create_missing_environments(repo_names: list, environment_name: str, existing_environments: dict, client: httpx.AsyncClient, headers: dict) -> tuple[dict, int]:
    """Create environment in repositories that don't have it"""
    results = {}
    created_count = 0
    
    for repo_name in repo_names:
        if repo_name not in existing_environments:
            owner, repo = repo_name.split("/")
            create_env_url = f"https://api.github.com/repos/{owner}/{repo}/environments/{environment_name}"
            
            # Create with minimal configuration (can be extended later)
            env_data = {
                "wait_timer": 0,
                "reviewers": [],
                "deployment_branch_policy": None
            }
            
            response = await client.put(create_env_url, json=env_data, headers=headers)
            
            if response.status_code in [200, 201]:
                results[repo_name] = "created"
                created_count += 1
            else:
                results[repo_name] = f"failed ({response.status_code})"
        else:
            results[repo_name] = "already exists"
    
    return results, created_count


async def _get_truly_new_variables(env_vars: list, project_code: str, repo_names: list, headers: dict, use_prefix: bool = True) -> list:
    """Identify which environment variables are truly new (don't exist in any repo)"""
    truly_new_vars = []
    for env_var in env_vars:
        original_key = env_var.get("key", "").strip()
        if not original_key:
            continue
            
        formatted_key = _format_env_var_key(original_key, project_code, use_prefix)
        variable_exists = await _check_variable_exists_in_repos(formatted_key, repo_names, headers)
        
        if not variable_exists:
            truly_new_vars.append(env_var)
    
    return truly_new_vars


async def _check_free_account_limits(user_obj, user: str, project_code: str, repo_names: list, env_vars: list, headers: dict, use_prefix: bool = True, project_id: int = None, db: Session = None) -> dict:
    """Check if account would exceed env-var limits with new variables.

    In self-hosted beta mode the limit is 6 per project regardless of account
    type. In cloud mode only free-tier accounts are gated here (at 2).
    """
    from tier_service import is_self_hosted_beta, SELF_HOSTED_BETA_LIMITS

    if is_self_hosted_beta():
        limit = SELF_HOSTED_BETA_LIMITS["env_vars_per_project"]
        current_count = await count_project_env_vars(user, project_code, repo_names, use_prefix, project_id, db)
        truly_new_vars = await _get_truly_new_variables(env_vars, project_code, repo_names, headers, use_prefix)
        new_env_vars_count = len(truly_new_vars)
        if current_count + new_env_vars_count > limit:
            return {
                "error": (
                    f"Self-hosted beta allows up to {limit} environment variables per project. "
                    f"You currently have {current_count} and are trying to add {new_env_vars_count} new variable(s). "
                    f"Paid plans are not available during the self-hosted beta."
                ),
                "status": 403,
                "current_count": current_count,
                "limit": limit,
            }
        return {}

    if not user_obj or user_obj.account_type != "free":
        return {}
    
    current_count = await count_project_env_vars(user, project_code, repo_names, use_prefix, project_id, db)
    truly_new_vars = await _get_truly_new_variables(env_vars, project_code, repo_names, headers, use_prefix)
    new_env_vars_count = len(truly_new_vars)
    
    if current_count + new_env_vars_count > 2:
        return {
            "error": f"Free plan users can create up to 2 environment variables per project. You currently have {current_count} and are trying to add {new_env_vars_count} new variables.", 
            "status": 403,
            "current_count": current_count,
            "limit": 2
        }
    
    return {}


async def _update_or_create_variable(repo_name: str, formatted_key: str, value: str, headers: dict) -> int:
    """Update existing variable or create new one, return status code"""
    owner, repo = repo_name.split("/")
    
    async with httpx.AsyncClient() as client:
        # Check if the variable exists
        check_var_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/variables/{formatted_key}"
        check_var_response = await client.get(check_var_url, headers=headers)

        if check_var_response.status_code == 200:
            # Variable exists, update it using PATCH
            update_var_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/variables/{formatted_key}"
            update_payload = {"value": value}
            update_response = await client.patch(update_var_url, json=update_payload, headers=headers)
            return update_response.status_code
        else:
            # Variable does NOT exist, create it using POST
            create_var_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/variables"
            create_payload = {"name": formatted_key, "value": value}
            create_response = await client.post(create_var_url, json=create_payload, headers=headers)
            return create_response.status_code

def _store_env_var_names_in_db(env_vars: list, project: "Project", db: Session) -> None:
    """Store env var names (without values) in the DB when prefix is disabled."""
    try:
        keys = {env_var["key"].strip().upper() for env_var in env_vars if env_var["key"].strip()}
        if not keys:
            return
        existing_names = {
            row.env_var_name
            for row in db.query(ProjectEnvVar.env_var_name).filter(
                ProjectEnvVar.project_id == project.project_id,
                ProjectEnvVar.env_var_name.in_(keys)
            ).all()
        }
        new_records = [
            ProjectEnvVar(project_id=project.project_id, env_var_name=key)
            for key in keys
            if key not in existing_names
        ]
        if new_records:
            db.add_all(new_records)
        db.commit()
        print(f"✅ Stored {len(env_vars)} env var names locally")
    except SQLAlchemyError as e:
        db.rollback()
        print(f"⚠️ Warning: Could not store env var names: {str(e)}")


@router.post("/api/update-env-vars")
async def update_env_vars(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Updates GitHub repository environment variables"""
    try:
        # Validate request data
        data = await request.json()
        user, repo_names, env_vars, project_name = _validate_request_data(data)

        # Check authentication
        headers = _get_auth_headers(user)
        if not headers:
            return {"error": AUTH_STRING, "status": 401}

        # Get user and project from database
        user_obj = db.query(Account).filter(Account.github_user == user).first()
        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            return {"error": f"Project '{project_name}' not found in database", "status": 404}

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix  # Get prefix setting from project
        print(f"📌 Debug: Using Project Code: {project_code}, Use Prefix: {use_prefix}")

        # Check free account limits
        limit_error = await _check_free_account_limits(user_obj, user, project_code, repo_names, env_vars, headers, use_prefix, project.project_id, db)
        if limit_error:
            return limit_error

        # Update variables in all repositories
        results = {}
        for repo_name in repo_names:
            for env_var in env_vars:
                original_key = env_var["key"].strip()
                value = env_var["value"].strip()
                
                formatted_key = _format_env_var_key(original_key, project_code, use_prefix)
                print(f"✅ formatted_key: {formatted_key}")

                status_code = await _update_or_create_variable(repo_name, formatted_key, value, headers)
                results[f"{repo_name}/env/{formatted_key}"] = status_code

        # If prefix is disabled, store env var names locally (without values)
        if not use_prefix:
            _store_env_var_names_in_db(env_vars, project, db)

        return {"message": "✅ GitHub Repository Variables updated!", "results": results}
    
    except Exception as e:
        print(f"❌ Error updating env vars: {str(e)}")
        return {"error": str(e), "status": 500}


async def _fetch_all_github_variables(client, repo_name: str, headers: dict) -> list | None:
    """Fetches all GitHub Actions variables for a repo with pagination. Returns None on error."""
    all_env_vars = []
    page = 1
    while True:
        env_vars_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables?per_page=100&page={page}"
        response = await client.get(env_vars_url, headers=headers)

        if response.status_code != 200:
            return None

        variables = response.json().get("variables", [])
        if not variables:
            break

        all_env_vars.extend(variables)
        page += 1

    print(f"✅ Total environment variables fetched: {len(all_env_vars)}")
    return all_env_vars


async def _fetch_variable_value(client, repo_name: str, env_var_name: str, headers: dict) -> str:
    """Fetches the value of a single GitHub Actions variable. Returns 'N/A' on failure."""
    var_value_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables/{env_var_name}"
    value_response = await client.get(var_value_url, headers=headers)

    if value_response.status_code == 200:
        return value_response.json().get("value", "N/A")

    print(f"⚠️ Failed to fetch value for {env_var_name}. Status: {value_response.status_code}")
    return "N/A"


async def _get_prefix_mode_vars(client, all_env_vars: list, repo_name: str, project_code: str, headers: dict) -> list:
    """Collects env vars matching the AM_<PROJECT_CODE>_ prefix and fetches their values."""
    prefix = f"AM_{project_code}_"
    project_env_vars = []

    for env_var in all_env_vars:
        env_var_name = env_var["name"]
        if not env_var_name.startswith(prefix):
            continue

        print(f"✅ [PREFIX MODE] Processing Variable: {env_var_name}")
        env_var_value = await _fetch_variable_value(client, repo_name, env_var_name, headers)
        project_env_vars.append({"env_key": env_var_name, "value": env_var_value, "repo": repo_name})

    print(f"✅ [PREFIX MODE] Found {len(project_env_vars)} variables with prefix {prefix}")
    return project_env_vars


async def _get_no_prefix_mode_vars(client, all_env_vars: list, repo_name: str, project, db, headers: dict) -> list:
    """Retrieves env var names from DB, verifies they exist in GitHub, and fetches their values."""
    db_env_vars = db.query(ProjectEnvVar).filter(ProjectEnvVar.project_id == project.project_id).all()
    env_var_names_from_db = {ev.env_var_name for ev in db_env_vars}
    all_env_var_map = {var["name"] for var in all_env_vars}

    project_env_vars = []
    for env_var_name in env_var_names_from_db:
        if env_var_name not in all_env_var_map:
            continue

        print(f"✅ [NO PREFIX MODE] Processing Variable: {env_var_name}")
        env_var_value = await _fetch_variable_value(client, repo_name, env_var_name, headers)
        project_env_vars.append({"env_key": env_var_name, "value": env_var_value, "repo": repo_name})

    print(f"✅ [NO PREFIX MODE] Found {len(project_env_vars)} variables from database (out of {len(env_var_names_from_db)} stored)")
    return project_env_vars


@router.get("/api/get-env-vars")
async def get_env_vars(user: str, repo_name: str, project_name: str, db: Annotated[Session, Depends(get_db)]):
    """Fetches GitHub environment variables for a project.
    - If use_prefix=True: Filters environment variables matching 'AM_<PROJECT_CODE>_*' format
    - If use_prefix=False: Retrieves env var names from ProjectEnvVar table and verifies they exist in GitHub
    """
    try:
        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept":  ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        project = db.query(Project).filter(Project.project_name.ilike(project_name.strip())).first()
        if not project:
            print(f"❌ Project '{project_name}' not found in DB")
            return {"error": f"Project '{project_name}' not found in database", "status": 404}

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix
        print(f"📌 Found Project Code (Uppercase): {project_code}, use_prefix: {use_prefix}")

        if not project_code:
            return {"error": "Project code not found", "status": 400}

        async with httpx.AsyncClient() as client:
            all_env_vars = await _fetch_all_github_variables(client, repo_name, headers)
            if all_env_vars is None:
                return {"error": f"Failed to fetch environment variables from GitHub for {repo_name}"}

            if use_prefix:
                project_env_vars = await _get_prefix_mode_vars(client, all_env_vars, repo_name, project_code, headers)
            else:
                project_env_vars = await _get_no_prefix_mode_vars(client, all_env_vars, repo_name, project, db, headers)

        print(f"📌 Debug: Returning {len(project_env_vars)} environment variables for {repo_name}")

        return {"env_vars": project_env_vars}

    except Exception as e:
        print(f"❌ Error in /api/get-env-vars: {str(e)}")
        return {"error": str(e)}


@router.delete("/api/delete-env-vars")
async def delete_env_vars(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Deletes GitHub repository environment variables"""
    try:
        data = await request.json()
        user = data.get("user")
        project_name = data.get("project_name", "").strip()
        repo_names = data.get("repo_names", [])
        env_vars = data.get("env") if isinstance(data.get("env"), list) else []

        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept":  ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        # ✅ Fix: Query using `project_name` instead of `name`
        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            return {"error": f"Project '{project_name}' not found", "status": 404}

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix

        results = {}
        async with httpx.AsyncClient() as client:
            for repo_name in repo_names:
                owner, repo = repo_name.split("/")

                for env_var in env_vars:
                    env_key = env_var["env_key"].strip()
                    
                    formatted_key = _format_env_var_key(env_key, project_code, use_prefix)
                        
                    delete_var_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/variables/{formatted_key}"

                    delete_response = await client.delete(delete_var_url, headers=headers)

                    results[f"{repo_name}/env/{formatted_key}"] = delete_response.status_code

        # If prefix is disabled, remove env var names from local database
        if not use_prefix:
            keys_to_delete = {env_var["env_key"].strip().upper() for env_var in env_vars if env_var["env_key"].strip()}
            if keys_to_delete:
                try:
                    db.query(ProjectEnvVar).filter(
                        ProjectEnvVar.project_id == project.project_id,
                        ProjectEnvVar.env_var_name.in_(keys_to_delete)
                    ).delete(synchronize_session=False)
                    db.commit()
                except SQLAlchemyError as e:
                    db.rollback()
                    print(f"⚠️ Warning: Could not remove env var names from DB: {str(e)}")

        return {"message": "✅ GitHub Repository Variables deleted!", "results": results}

    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return {"error": str(e), "status": 500}


async def _sync_env_var_to_repo(client, repo_name: str, formatted_key: str, env_value: str, headers: dict):
    """Check if a variable exists in a repo and create it if missing."""
    check_var_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables/{formatted_key}"
    check_response = await client.get(check_var_url, headers=headers)

    if check_response.status_code == 404:
        create_var_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables"
        create_payload = {"name": formatted_key, "value": env_value}
        create_response = await client.post(create_var_url, json=create_payload, headers=headers)
        if create_response.status_code == 201:
            print(f"✅ Created env var '{formatted_key}' in {repo_name}")
        else:
            print(f"❌ Failed to create env var '{formatted_key}' in {repo_name}: {create_response.status_code}")
        return create_response.status_code

    print(f"ℹ️ Env var '{formatted_key}' already exists in {repo_name}")
    return "already_exists"


@router.post("/api/sync-env-var")
async def sync_env_var(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Syncs a specific environment variable to all repositories that don't have it"""
    try:
        data = await request.json()
        user = data.get("user")
        project_name = data.get("project_name", "").strip()
        repo_names = data.get("repo_names", [])
        env_key = data.get("env_key", "").strip()

        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept":  ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        #user_obj = db.query(Account).filter(Account.github_user == user).first()
        # Allow sync for free accounts since they're not creating new variables, just syncing existing ones
        
        # Get project code
        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            return {"error": f"Project '{project_name}' not found in database", "status": 404}

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix
        
        formatted_key = _format_env_var_key(env_key, project_code, use_prefix)

        # Find a repository that has this variable to get its value
        env_value = None
        source_repo = None
        
        async with httpx.AsyncClient() as client:
            for repo_name in repo_names:
                check_var_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables/{formatted_key}"
                check_response = await client.get(check_var_url, headers=headers)
                
                if check_response.status_code == 200:
                    var_data = check_response.json()
                    env_value = var_data.get("value")
                    source_repo = repo_name
                    break

            if not env_value:
                return {"error": f"Environment variable '{env_key}' not found in any repository", "status": 404}

            print(f"📌 Syncing env var '{env_key}' with value from {source_repo} to missing repos")

            # Sync to repositories that don't have it
            results = {}
            for repo_name in repo_names:
                result = await _sync_env_var_to_repo(client, repo_name, formatted_key, env_value, headers)
                results[f"{repo_name}/env/{formatted_key}"] = result

        return {"message": f"✅ Environment variable '{env_key}' synced!", "results": results}

    except Exception as e:
        print(f"❌ Error syncing env var: {str(e)}")
        return {"error": str(e), "status": 500}


async def _check_environment_limit(user: str, repo_name: str, environment_exists: bool, user_obj):
    """Check tier-based environment creation limits. Returns an error dict or None."""
    from tier_service import is_self_hosted_beta, SELF_HOSTED_BETA_LIMITS
    repo_list = [repo_name] if repo_name else []
    if is_self_hosted_beta():
        current_count = await count_project_environments(user, repo_list)
        beta_env_limit = SELF_HOSTED_BETA_LIMITS["environments_per_project"]
        if not environment_exists and current_count >= beta_env_limit:
            return {
                "error": (
                    f"Self-hosted beta allows up to {beta_env_limit} GitHub environments per project. "
                    f"You currently have {current_count} environment(s). "
                    f"Paid plans are not available during the self-hosted beta."
                ),
                "status": 403,
                "current_count": current_count,
                "limit": beta_env_limit,
            }
    elif user_obj and user_obj.account_type == "free":
        current_count = await count_project_environments(user, repo_list)
        if not environment_exists and current_count >= 2:
            return {
                "error": f"Free plan users can create up to 2 deployment environments per project. You currently have {current_count} environments.",
                "status": 403,
                "current_count": current_count,
                "limit": 2
            }
    return None


@router.post("/api/create-environment")
async def create_environment(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Creates a new deploy environment in a GitHub repository."""
    try:
        data = await request.json()
        user = data.get("user")
        repo_name = data.get("repo_name")
        environment_name = data.get("environment_name")

        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        if not isinstance(repo_name, str) or not repo_name.strip():
            return {"error": "Missing or invalid repository name", "status": 400}

        if not isinstance(environment_name, str) or not environment_name.strip():
            return {"error": "Missing or invalid environment name", "status": 400}

        repo_name = repo_name.strip()
        environment_name = environment_name.strip()
        if len(environment_name) > 255:
            return {"error": "Environment name is too long", "status": 400}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept":  ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        user_obj = db.query(Account).filter(Account.github_user == user).first()

        try:
            owner, repo = repo_name.split("/", 1)
        except ValueError:
            return {"error": f"Invalid repository name format: '{repo_name}'. Expected format: 'owner/repo'", "status": 400}

        encoded_env_name = quote(environment_name, safe="")
        check_env_url = f"https://api.github.com/repos/{owner}/{repo}/environments/{encoded_env_name}"

        async with httpx.AsyncClient() as client:
            check_response = await client.get(check_env_url, headers=headers)
            environment_exists = check_response.status_code == 200

            limit_error = await _check_environment_limit(user, repo_name, environment_exists, user_obj)
            if limit_error:
                return limit_error

            if environment_exists:
                return {
                    "message": f"Environment '{environment_name}' already exists - no changes made.",
                    "created": False
                }

            url = f"https://api.github.com/repos/{owner}/{repo}/environments/{encoded_env_name}"
            response = await client.put(url, headers=headers, json={})
            if response.status_code in [200, 201]:
                return {"message": f"Environment '{environment_name}' created successfully.", "created": True}
            else:
                return {"error": response.json(), "status": response.status_code}

    except Exception as e:
        print(f"❌ Error creating environment: {str(e)}")
        return {"error": str(e), "status": 500}


@router.get("/api/get-environments")
async def get_environments(user: str, repo_name: str, db: Annotated[Session, Depends(get_db)]):
    """Fetches all deploy environments for a GitHub repository."""
    try:
        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept":  ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        owner, repo = repo_name.split("/")
        url = f"https://api.github.com/repos/{owner}/{repo}/environments"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                environments = response.json().get("environments", [])
                return {"environments": environments}
            else:
                return {"error": f"Failed to fetch environments for {repo_name}", "status": response.status_code}

    except Exception as e:
        print(f"❌ Error fetching environments: {str(e)}")
        return {"error": str(e), "status": 500}


@router.delete("/api/delete-environment")
async def delete_environment(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Deletes a deployment environment from GitHub repositories."""
    try:
        data = await request.json()
        user = data.get("user")
        repo_names = data.get("repo_names", [])
        environment_name = data.get("environment_name", "")

        if not isinstance(environment_name, str) or not environment_name.strip():
            return {"error": "Missing or invalid environment name", "status": 400}
        environment_name = environment_name.strip()

        print(f"Request received to delete environment: {environment_name}")
        print(f"User: {user}, Repositories: {repo_names}")

        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        if not isinstance(repo_names, list) or len(repo_names) == 0:
            return {"error": "No repositories provided", "status": 400}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept":  ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        encoded_env_name = quote(environment_name, safe="")
        results = {}
        async with httpx.AsyncClient() as client:
            for repo_name in repo_names:
                if not isinstance(repo_name, str) or "/" not in repo_name:
                    results[f"{repo_name}/environment/{environment_name}"] = 400
                    continue
                owner, repo = repo_name.split("/", 1)
                delete_env_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/environments/{encoded_env_name}"

                print(f"Sending DELETE request to: {delete_env_url}")
                response = await client.delete(delete_env_url, headers=headers)
                print(f"Response for {repo_name}: {response.status_code}, {response.text}")

                results[f"{repo_name}/environment/{environment_name}"] = response.status_code

        return {"message": "✅ Deployment environments deleted!", "results": results}

    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return {"error": str(e), "status": 500}


@router.post("/api/sync-environment")
async def sync_environment(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Syncs a deployment environment to all repositories that don't have it"""
    try:
        data = await request.json()
        user, project_name, repo_names, environment_name = _validate_sync_environment_request(data)

        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        headers = _get_auth_headers(user)
        user_obj = db.query(Account).filter(Account.github_user == user).first()
        
        async with httpx.AsyncClient() as client:
            # Check account limits (self-hosted beta or free-tier cloud)
            from tier_service import is_self_hosted_beta
            if is_self_hosted_beta() or (user_obj and user_obj.account_type == "free"):
                limit_check = await _check_free_account_environment_limits(user, repo_names, environment_name, client, headers)
                if limit_check:
                    return limit_check

            # Find repositories that already have this environment
            existing_environments = await _find_existing_environments(repo_names, environment_name, client, headers)
            
            if not existing_environments:
                return {"error": f"Environment '{environment_name}' not found in any repository", "status": 404}

            # Create environment in repositories that don't have it
            results, created_count = await _create_missing_environments(repo_names, environment_name, existing_environments, client, headers)

        return {
            "message": f"✅ Environment '{environment_name}' synced! Created in {created_count} repositories.", 
            "results": results
        }

    except Exception as e:
        print(f"❌ Error syncing environment: {str(e)}")
        return {"error": str(e), "status": 500}


@router.get("/api/env-vars-count")
async def get_env_vars_count(user: str, project_name: str, repo_names: str, db: Annotated[Session, Depends(get_db)]):
    """Get the count of environment variables for a project"""
    try:
        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        # Parse repo_names parameter (comma-separated string)
        repo_list = [repo.strip() for repo in repo_names.split(",") if repo.strip()]
        
        if not repo_list:
            return {"error": ERROR_CODE, "status": 400}

        # Get project code
        project = db.query(Project).filter(Project.project_name.ilike(project_name.strip())).first()
        if not project:
            return {"error": f"Project '{project_name}' not found in database", "status": 404}

        project_code = project.project_code.upper()
        
        # Count environment variables
        count = await count_project_env_vars(user, project_code, repo_list)
        
        return {"count": count}

    except Exception as e:
        print(f"❌ Error getting env vars count: {str(e)}")
        return {"error": str(e), "status": 500}


@router.get("/api/environments-count")
async def get_environments_count(user: str, repo_names: str, db: Annotated[Session, Depends(get_db)]):
    """Get the count of deployment environments for a project"""
    try:
        if user not in user_tokens:
            return {"error": AUTH_STRING, "status": 401}

        # Parse repo_names parameter (comma-separated string)
        repo_list = [repo.strip() for repo in repo_names.split(",") if repo.strip()]
        
        if not repo_list:
            return {"error": ERROR_CODE, "status": 400}
        
        # Count deployment environments
        count = await count_project_environments(user, repo_list)
        
        return {"count": count}

    except Exception as e:
        print(f"❌ Error getting environments count: {str(e)}")
        return {"error": str(e), "status": 500}
