from fastapi import APIRouter, Request, Depends
import httpx
import base64
import nacl.public
from sqlalchemy.orm import Session
from typing import Annotated
from database import get_db
from auth import user_tokens
from models import Project, Account, ProjectSecret  # ✅ Import ProjectSecret for storing secret names

router = APIRouter()

GITHUB_API_URL = "https://api.github.com"
ACCEPT_HEADER = "application/vnd.github+json"
X_API_VERSION = "2022-11-28"

async def count_project_secrets(user: str, project_code: str, repo_names: list, use_prefix: bool = True, project_id: int = None, db: Session = None) -> int:
    """Helper function to count secrets for a project across repositories"""
    if user not in user_tokens:
        return 0
    
    # If prefix is disabled, count from local database
    if not use_prefix and project_id is not None and db is not None:
        count = db.query(ProjectSecret).filter(
            ProjectSecret.project_id == project_id
        ).count()
        return count
    
    # For prefixed secrets, count from GitHub
    token = user_tokens[user]
    headers = {
        "Authorization": f"token {token}",
        "Accept": ACCEPT_HEADER,
        "X-GitHub-Api-Version": X_API_VERSION
    }
    
    unique_secrets = set()
    
    async with httpx.AsyncClient() as client:
        for repo_name in repo_names:
            try:
                secrets_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/secrets"
                response = await client.get(secrets_url, headers=headers)
                
                if response.status_code == 200:
                    secret_data = response.json()
                    secrets = secret_data.get("secrets", [])
                    
                    for secret in secrets:
                        secret_name = secret["name"]
                        if secret_name.startswith(f"AM_{project_code}_"):
                            unique_secrets.add(secret_name)
            except Exception as e:
                print(f"❌ Error counting secrets for {repo_name}: {str(e)}")
    
    return len(unique_secrets)


def encrypt_secret(public_key: str, secret_value: str) -> str:
    """Encrypts the secret using GitHub's public key."""
    public_key_bytes = base64.b64decode(public_key)
    sealed_box = nacl.public.SealedBox(nacl.public.PublicKey(public_key_bytes))
    encrypted_value = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted_value).decode("utf-8")


async def _validate_account_limits(user: str, project_name: str, secrets: list, repo_names: list, db: Session) -> dict | None:
    """Helper function to validate account limits using tier service."""
    from tier_service import get_effective_tier, get_tier_limits, is_self_hosted_beta, SELF_HOSTED_BETA_LIMITS
    
    user_obj = db.query(Account).filter(Account.github_user == user).first()
    
    if not user_obj:
        return {"error": "User not found", "status": 404}
    
    # Get project code to check current secret count
    project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
    if not project:
        return {"error": f"Project '{project_name}' not found", "status": 404}
    
    project_code = project.project_code.upper()
    use_prefix = project.use_prefix
    current_count = await count_project_secrets(user, project_code, repo_names, use_prefix, project.project_id, db)
    
    # Check how many new secrets are being added
    truly_new_secrets = [s for s in secrets if s.get("secret_key", "").strip() and s.get("secret_value", "").strip()]
    new_secrets_count = len(truly_new_secrets)

    # Self-hosted beta: enforce beta secret limit (6 per project)
    if is_self_hosted_beta():
        max_secrets = SELF_HOSTED_BETA_LIMITS["secrets_per_project"]
        if current_count + new_secrets_count > max_secrets:
            return {
                "error": (
                    f"Self-hosted beta allows up to {max_secrets} secrets per project. "
                    f"You currently have {current_count} and are trying to add {new_secrets_count} new secret(s). "
                    f"Paid plans are not available during the self-hosted beta."
                ),
                "status": 403,
                "current_count": current_count,
                "new_count": new_secrets_count,
                "limit": max_secrets,
            }
        return None

    # Cloud mode: use effective tier limits
    tier = get_effective_tier(user_obj)
    limits = get_tier_limits(tier)
    max_secrets = limits["secrets_per_project"]
    
    # Unlimited tier (enterprise)
    if max_secrets is None:
        return None
    
    # Determine upgrade message based on tier
    if tier == "free":
        upgrade_message = "Upgrade to Professional for up to 10 secrets per project."
    elif tier == "professional":
        upgrade_message = "Upgrade to Enterprise for unlimited secrets."
    else:
        upgrade_message = ""
    
    if current_count + new_secrets_count > max_secrets:
        return {
            "error": f"{tier.capitalize()} accounts can create up to {max_secrets} secrets per project. You currently have {current_count} and are trying to add {new_secrets_count} new secrets. {upgrade_message}", 
            "status": 403,
            "current_count": current_count,
            "new_count": new_secrets_count,
            "limit": max_secrets
        }
    
    return None  # No limits exceeded


async def _get_repo_public_key(repo_name: str, headers: dict, client) -> tuple:
    """Helper function to get GitHub repository public key for encryption."""
    public_key_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/secrets/public-key"
    response = await client.get(public_key_url, headers=headers)

    if response.status_code != 200:
        print(f"❌ Failed to get public key for {repo_name}: {response.text}")
        return None, {"error": "Failed to get public key"}

    public_key_data = response.json()
    key_id = public_key_data.get("key_id")
    public_key = public_key_data.get("key")

    if not key_id or not public_key:
        return None, {"error": "Invalid public key data"}

    return (key_id, public_key), None


async def _process_repository_secrets(repo_name: str, secrets: list, project_code: str, key_id: str, public_key: str, headers: dict, client, use_prefix: bool = True) -> dict:
    """Helper function to process all secrets for a repository."""
    repo_results = {}

    for secret in secrets:
        secret_name = secret.get("secret_key", "").strip()
        secret_value = secret.get("secret_value", "").strip()

        if not secret_name or not secret_value:
            print(f"⚠️ Skipping empty secret for {repo_name}")
            continue  # Skip invalid secrets

        # Format secret name with or without prefix
        if use_prefix:
            formatted_secret_name = f"AM_{project_code}_{secret_name}".upper()
        else:
            formatted_secret_name = secret_name.upper()
        print(f"📌 Storing secret '{formatted_secret_name}' in '{repo_name}'")

        # Encrypt secret
        encrypted_secret = encrypt_secret(public_key, secret_value)

        # Store the secret
        put_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/secrets/{formatted_secret_name}"
        payload = {
            "encrypted_value": encrypted_secret,
            "key_id": key_id
        }

        put_response = await client.put(put_url, json=payload, headers=headers)

        if put_response.status_code in [201, 204]:
            repo_results[formatted_secret_name] = "✅ Secret stored successfully"
        else:
            repo_results[formatted_secret_name] = f"❌ Error: {put_response.text}"

    return repo_results


@router.post("/api/create-secrets")
async def create_secrets(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Creates multiple GitHub Actions secrets across multiple repositories."""
    try:
        data = await request.json()
        user = data.get("user")
        repo_names = data.get("repo_names", [])  
        secrets = data.get("secrets", [])  
        project_name = data.get("project_name", "").strip()

        if user not in user_tokens:
            return {"error": "User not authenticated", "status": 401}

        # Validate account limits for free accounts
        limit_error = await _validate_account_limits(user, project_name, secrets, repo_names, db)
        if limit_error:
            return limit_error

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        # Get project code — verify ownership before accessing
        account = db.query(Account).filter(Account.github_user == user).first()
        project = db.query(Project).filter(
            Project.project_name.ilike(project_name),
            Project.user_id == (account.user_id if account else -1),
        ).first()
        if not project:
            return {"error": f"Project '{project_name}' not found", "status": 404}

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix  # Get prefix setting from project
        print(f"📌 Using Project Code: {project_code}, Use Prefix: {use_prefix}")

        results = {}

        async with httpx.AsyncClient() as client:
            for repo_name in repo_names:
                # Get repository public key
                key_data, error = await _get_repo_public_key(repo_name, headers, client)
                if error:
                    results[repo_name] = error
                    continue

                key_id, public_key = key_data

                # Process secrets for this repository
                repo_results = await _process_repository_secrets(
                    repo_name, secrets, project_code, key_id, public_key, headers, client, use_prefix
                )
                results[repo_name] = repo_results

        # If prefix is disabled, store secret names locally (without values)
        if not use_prefix:
            _store_unprefixed_secret_names(db, project, secrets)

        return {"message": "✅ Secrets processed", "results": results}

    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return {"error": str(e)}


def _store_unprefixed_secret_names(db: Session, project, secrets: list):
    """Store secret names (without values) locally when prefix is disabled."""
    for secret in secrets:
        secret_name = secret.get("secret_key", "").strip()
        if not secret_name or not secret.get("secret_value", "").strip():
            continue
        # Check if this secret name already exists for the project
        existing = db.query(ProjectSecret).filter(
            ProjectSecret.project_id == project.project_id,
            ProjectSecret.secret_name == secret_name.upper()
        ).first()

        if not existing:
            # Store the secret name (not the value)
            db_secret = ProjectSecret(
                project_id=project.project_id,
                secret_name=secret_name.upper()
            )
            db.add(db_secret)

    try:
        db.commit()
        print(f"✅ Stored {len(secrets)} secret names locally")
    except Exception as e:
        db.rollback()
        print(f"⚠️ Warning: Could not store secret names: {str(e)}")



@router.get("/api/get-secrets")
async def get_secrets(user: str, repo_name: str, project_name: str, db: Annotated[Session, Depends(get_db)]):
    """Fetches GitHub secrets for a project.
    - If use_prefix=True: Filters GitHub secrets matching 'AM_<PROJECT_CODE>_*' format
    - If use_prefix=False: Retrieves secret names from ProjectSecret table and verifies they exist in GitHub
    """
    try:
        print(f"📌 Incoming API Call: user={user}, repo={repo_name}, project={project_name}")

        if not project_name or project_name.strip() == "":
            return {"error": "Missing or invalid project name", "status": 400}

        if user not in user_tokens:
            return {"error": "User not authenticated", "status": 401}

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        # ✅ Fetch project and check use_prefix flag
        project = db.query(Project).filter(Project.project_name.ilike(project_name.strip())).first()

        if not project:
            print(f"❌ Project '{project_name}' not found in DB")
            return {"error": f"Project '{project_name}' not found", "status": 404}

        project_code = project.project_code.upper()
        use_prefix = project.use_prefix
        print(f"📌 Found Project Code: {project_code}, use_prefix: {use_prefix}")

        # ✅ Fetch secrets from GitHub
        async with httpx.AsyncClient() as client:
            secrets_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/secrets"
            response = await client.get(secrets_url, headers=headers)

            if response.status_code != 200:
                return {"error": f"Failed to fetch secrets from GitHub for {repo_name}"}

            secret_data = response.json()
            all_secrets = secret_data.get("secrets", [])

        project_secrets = []

        if use_prefix:
            # ✅ PREFIX MODE: Filter secrets matching `AM_<PROJECT_CODE>_*`
            project_secrets = [
                {"secret_key": secret["name"], "repo": repo_name}
                for secret in all_secrets if secret["name"].startswith(f"AM_{project_code}_")
            ]
            print(f"✅ [PREFIX MODE] Found {len(project_secrets)} secrets with prefix AM_{project_code}_")
        else:
            # ✅ NO PREFIX MODE: Retrieve secret names from database
            db_secrets = db.query(ProjectSecret).filter(ProjectSecret.project_id == project.project_id).all()
            secret_names_from_db = {secret.secret_name for secret in db_secrets}

            # Verify each secret from DB exists in GitHub
            all_secret_names = {secret["name"] for secret in all_secrets}

            for secret_name in secret_names_from_db:
                if secret_name in all_secret_names:
                    project_secrets.append({"secret_key": secret_name, "repo": repo_name})

            print(f"✅ [NO PREFIX MODE] Found {len(project_secrets)} secrets from database (out of {len(secret_names_from_db)} stored)")

        return {"secrets": project_secrets}

    except Exception as e:
        print(f"❌ Error in /api/get-secrets: {str(e)}")
        return {"error": str(e)}



@router.delete("/api/delete-secrets")
async def delete_secrets(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Deletes GitHub repository secrets."""
    try:
        data = await request.json()
        user = data.get("user")
        project_name = data.get("project_name", "").strip()
        repo_names = data.get("repo_names", [])
        secret_name = data.get("secret_name", "").strip()

        if user not in user_tokens:
            return {"error": "User not authenticated", "status": 401}

        # ✅ Free accounts can delete secrets (within their limits)
        # Note: We allow deletion for free accounts since they need to manage their limited secrets

        token = user_tokens[user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": ACCEPT_HEADER,
            "X-GitHub-Api-Version": X_API_VERSION
        }

        # Fetch project — verify ownership before allowing deletion
        account = db.query(Account).filter(Account.github_user == user).first()
        project = db.query(Project).filter(
            Project.project_name.ilike(project_name),
            Project.user_id == (account.user_id if account else -1),
        ).first()
        if not project:
            return {"error": f"Project '{project_name}' not found", "status": 404}

        project_code = project.project_code.upper()

        # Handle both full names (with prefix) and truncated names (without prefix)
        if secret_name.startswith(f"AM_{project_code}_"):
            # Already has prefix, use as-is
            formatted_secret_name = secret_name.upper()
        else:
            # Truncated name, add prefix
            formatted_secret_name = f"AM_{project_code}_{secret_name.upper()}"

        results = {}
        async with httpx.AsyncClient() as client:
            for repo_name in repo_names:
                owner, repo = repo_name.split("/")
                delete_secret_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/actions/secrets/{formatted_secret_name}"

                delete_response = await client.delete(delete_secret_url, headers=headers)

                results[f"{repo_name}/secret/{formatted_secret_name}"] = delete_response.status_code

        return {"message": "✅ GitHub Repository Secrets deleted!", "results": results}

    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return {"error": str(e), "status": 500}


@router.post("/api/sync-secret")
async def sync_secret(request: Request, db: Annotated[Session, Depends(get_db)]):
    """Syncs a specific secret to all repositories that don't have it"""
    try:
        data = await request.json()
        user = data.get("user")
        project_name = data.get("project_name", "").strip()
        secret_key = data.get("secret_key", "").strip()

        if user not in user_tokens:
            return {"error": "User not authenticated", "status": 401}

        # Check account type - allow sync for free accounts since they're not creating new secrets
        # Note: We allow sync for free accounts since they're managing existing secrets, not creating new ones

        # Get project code
        project = db.query(Project).filter(Project.project_name.ilike(project_name)).first()
        if not project:
            return {"error": f"Project '{project_name}' not found", "status": 404}

        print(f"📌 Syncing secret '{secret_key}' to missing repos")

        # Note: GitHub API doesn't allow reading secret values, so we can't actually sync the value
        # Instead, we'll return an error asking the user to recreate the secret
        return {"error": "Cannot sync secrets because GitHub API doesn't allow reading secret values. Please delete and recreate the secret to add it to all repositories.", "status": 400}

    except Exception as e:
        print(f"❌ Error syncing secret: {str(e)}")
        return {"error": str(e), "status": 500}


@router.get("/api/secrets-count")
async def get_secrets_count(user: str, project_name: str, repo_names: str, db: Annotated[Session, Depends(get_db)]):
    """Get the count of secrets for a project"""
    try:
        print(f"📌 Getting secrets count for user={user}, project={project_name}, repos={repo_names}")
        
        if user not in user_tokens:
            return {"error": "User not authenticated", "status": 401}
        
        # Parse repo names
        repo_list = [repo.strip() for repo in repo_names.split(",") if repo.strip()]
        if not repo_list:
            return {"error": "No valid repository names provided", "status": 400}
        
        # Get project code
        project = db.query(Project).filter(Project.project_name.ilike(project_name.strip())).first()
        if not project:
            return {"error": f"Project '{project_name}' not found", "status": 404}
        
        project_code = project.project_code.upper()
        
        count = await count_project_secrets(user, project_code, repo_list)
        
        return {"count": count}
        
    except Exception as e:
        print(f"❌ Error getting secrets count: {str(e)}")
        return {"error": str(e), "status": 500}
