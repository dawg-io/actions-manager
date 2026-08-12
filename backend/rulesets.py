"""
Rulesets API Module for ActionsManager

Handles GitHub repository ruleset management including:
- Uploading ruleset JSON files
- Storing rulesets in database
- Applying rulesets to repositories
- Managing rulesets across projects
"""

import json
from typing import Annotated, List, Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
import httpx
from database import get_db
from models import Ruleset, Project, ProjectRuleset, Account
import os
from auth import user_tokens


router = APIRouter()

# GitHub API configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ACCOUNT_NOT_FOUND = "User account not found"
RULESET_NOT_FOUND = "Ruleset not found"


class RulesetCreate(BaseModel):
    """Model for creating a new ruleset"""
    name: str
    description: Optional[str] = None
    ruleset_json: dict


class RulesetResponse(BaseModel):
    """Model for ruleset response"""
    ruleset_id: int
    ruleset_name: str
    description: Optional[str] = None
    created_at: str
    updated_at: str


class ApplyRulesetRequest(BaseModel):
    """Model for applying ruleset to repositories"""
    repo_names: List[str]
    github_user: str


class RulesetSyncStatusRequest(BaseModel):
    """Model for checking ruleset sync status across repositories"""
    repo_names: List[str]
    github_user: str


@router.post("/api/rulesets/upload")
async def upload_ruleset_file(
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    project_name: Annotated[str, Form()],
    github_user: Annotated[str, Form()],
):
    """Upload a ruleset JSON file and store it in the database"""
    
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="File must be a JSON file")
    
    try:
        # Read and parse JSON file
        content = await file.read()
        ruleset_data = json.loads(content.decode('utf-8'))
        
        # Validate that this looks like a GitHub ruleset
        if not isinstance(ruleset_data, dict):
            raise HTTPException(status_code=400, detail="Invalid ruleset format: must be a JSON object")
        
        # Get user account
        user_account = db.query(Account).filter(Account.github_user == github_user).first()
        if not user_account:
            raise HTTPException(status_code=404, detail=ACCOUNT_NOT_FOUND)
        
        # Extract name from ruleset or use filename
        ruleset_name = ruleset_data.get('name', file.filename.replace('.json', ''))
        description = ruleset_data.get('description', f"Imported from {file.filename}")
        
        # Create new ruleset
        new_ruleset = Ruleset(
            ruleset_name=ruleset_name,
            ruleset_json=json.dumps(ruleset_data),
            description=description,
            user_id=user_account.user_id
        )
        
        db.add(new_ruleset)
        db.commit()
        db.refresh(new_ruleset)
        
        # If project_name provided, associate with project
        if project_name:
            project = db.query(Project).filter(
                and_(Project.project_name == project_name, Project.user_id == user_account.user_id)
            ).first()
            
            if project:
                project_ruleset = ProjectRuleset(
                    project_id=project.project_id,
                    ruleset_id=new_ruleset.ruleset_id
                )
                db.add(project_ruleset)
                db.commit()
        
        return {
            "success": True,
            "message": f"Ruleset '{ruleset_name}' uploaded successfully",
            "ruleset_id": new_ruleset.ruleset_id,
            "ruleset_name": ruleset_name
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 404) without modification
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error uploading ruleset: {str(e)}")


@router.post("/api/rulesets/create")
async def create_ruleset(
    ruleset_data: RulesetCreate,
    db: Annotated[Session, Depends(get_db)],
    project_name: str = None,
    github_user: str = None
):
    """Create a new ruleset from JSON data"""
    
    try:
        # Get user account
        user_account = db.query(Account).filter(Account.github_user == github_user).first()
        if not user_account:
            raise HTTPException(status_code=404, detail=ACCOUNT_NOT_FOUND)
        
        # Create new ruleset
        new_ruleset = Ruleset(
            ruleset_name=ruleset_data.name,
            ruleset_json=json.dumps(ruleset_data.ruleset_json),
            description=ruleset_data.description,
            user_id=user_account.user_id
        )
        
        db.add(new_ruleset)
        db.commit()
        db.refresh(new_ruleset)
        
        # If project_name provided, associate with project
        if project_name:
            project = db.query(Project).filter(
                and_(Project.project_name == project_name, Project.user_id == user_account.user_id)
            ).first()
            
            if project:
                project_ruleset = ProjectRuleset(
                    project_id=project.project_id,
                    ruleset_id=new_ruleset.ruleset_id
                )
                db.add(project_ruleset)
                db.commit()
        
        return {
            "success": True,
            "message": f"Ruleset '{ruleset_data.name}' created successfully",
            "ruleset_id": new_ruleset.ruleset_id
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating ruleset: {str(e)}")


@router.get("/api/rulesets/{project_name}")
async def get_project_rulesets(
    project_name: str,
    github_user: str,
    db: Annotated[Session, Depends(get_db)]
):
    """Get all rulesets for a specific project"""
    
    try:
        # Get user account
        user_account = db.query(Account).filter(Account.github_user == github_user).first()
        if not user_account:
            raise HTTPException(status_code=404, detail=ACCOUNT_NOT_FOUND)
        
        # Get project
        project = db.query(Project).filter(
            and_(Project.project_name == project_name, Project.user_id == user_account.user_id)
        ).first()
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get project rulesets
        rulesets = db.query(Ruleset).join(ProjectRuleset).filter(
            ProjectRuleset.project_id == project.project_id
        ).all()
        
        return {
            "success": True,
            "rulesets": [
                {
                    "ruleset_id": ruleset.ruleset_id,
                    "ruleset_name": ruleset.ruleset_name,
                    "description": ruleset.description,
                    "created_at": ruleset.created_at.isoformat(),
                    "updated_at": ruleset.updated_at.isoformat(),
                    "ruleset_json": json.loads(ruleset.ruleset_json)
                }
                for ruleset in rulesets
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching rulesets: {str(e)}")


@router.post("/api/rulesets/{ruleset_id}/apply")
async def apply_ruleset_to_repos(
    ruleset_id: int,
    request_data: ApplyRulesetRequest,
    db: Annotated[Session, Depends(get_db)]
):
    """Apply a ruleset to specified repositories"""
    
    try:
        # Get user account
        user_account = db.query(Account).filter(Account.github_user == request_data.github_user).first()
        if not user_account:
            raise HTTPException(status_code=404, detail=ACCOUNT_NOT_FOUND)
        
        # Get ruleset
        ruleset = db.query(Ruleset).filter(
            and_(Ruleset.ruleset_id == ruleset_id, Ruleset.user_id == user_account.user_id)
        ).first()
        
        if not ruleset:
            raise HTTPException(status_code=404, detail=RULESET_NOT_FOUND)
        
        # Parse ruleset JSON
        ruleset_data = json.loads(ruleset.ruleset_json)
        
        results = []
        errors = []
        
        # Apply ruleset to each repository
        for repo_name in request_data.repo_names:
            try:
                result = await apply_ruleset_to_repo(
                    request_data.github_user, 
                    repo_name, 
                    ruleset_data
                )
                if result:
                    results.append(f"✅ Applied ruleset '{ruleset.ruleset_name}' to {repo_name}")
                else:
                    errors.append(f"❌ Failed to apply ruleset to {repo_name}")
            except Exception as e:
                errors.append(f"❌ Error applying ruleset to {repo_name}: {str(e)}")
        
        return {
            "success": len(errors) == 0,
            "message": f"Attempted to apply ruleset '{ruleset.ruleset_name}' to {len(request_data.repo_names)} repositories",
            "results": results,
            "errors": errors,
            "applied_count": len(results),
            "error_count": len(errors)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying ruleset: {str(e)}")


@router.post("/api/rulesets/{ruleset_id}/sync-status")
async def check_ruleset_sync_status(
    ruleset_id: int,
    request_data: RulesetSyncStatusRequest,
    db: Annotated[Session, Depends(get_db)]
):
    """Check if a ruleset exists across all specified repositories"""
    
    try:
        # Get user account
        user_account = db.query(Account).filter(Account.github_user == request_data.github_user).first()
        if not user_account:
            raise HTTPException(status_code=404, detail=ACCOUNT_NOT_FOUND)
        
        # Get ruleset
        ruleset = db.query(Ruleset).filter(
            and_(Ruleset.ruleset_id == ruleset_id, Ruleset.user_id == user_account.user_id)
        ).first()
        
        if not ruleset:
            raise HTTPException(status_code=404, detail=RULESET_NOT_FOUND)
        
        # Parse ruleset JSON to get the name
        ruleset_data = json.loads(ruleset.ruleset_json)
        ruleset_name = ruleset_data.get("name", ruleset.ruleset_name)
        
        # Check if user is authenticated with GitHub
        if request_data.github_user not in user_tokens:
            raise HTTPException(status_code=401, detail="User not authenticated with GitHub")
        
        # Get user's GitHub token
        token = user_tokens[request_data.github_user]
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        
        repo_statuses = {}
        missing_repos = []
        
        async with httpx.AsyncClient() as client:
            # Check each repository for the ruleset
            for repo_name in request_data.repo_names:
                if '/' not in repo_name:
                    # Skip invalid repo names
                    continue
                    
                owner, repo = repo_name.split('/', 1)
                
                try:
                    # Get repository rulesets
                    api_url = f"https://api.github.com/repos/{owner}/{repo}/rulesets"
                    response = await client.get(api_url, headers=headers, timeout=30)
                    
                    if response.status_code == 200:
                        rulesets = response.json()
                        
                        # Check if any ruleset matches our name
                        ruleset_found = False
                        for existing_ruleset in rulesets:
                            if existing_ruleset.get("name") == ruleset_name:
                                ruleset_found = True
                                break
                        
                        if ruleset_found:
                            repo_statuses[repo_name] = {
                                "status": "exists",
                                "message": f"Ruleset '{ruleset_name}' exists in repository"
                            }
                        else:
                            repo_statuses[repo_name] = {
                                "status": "not_found",
                                "message": f"Ruleset '{ruleset_name}' not found in repository"
                            }
                            missing_repos.append(repo_name)
                            
                    elif response.status_code == 403:
                        repo_statuses[repo_name] = {
                            "status": "permission_denied",
                            "message": "Permission denied - need admin access to check rulesets"
                        }
                        missing_repos.append(repo_name)  # Treat as missing since we can't verify
                        
                    elif response.status_code == 404:
                        repo_statuses[repo_name] = {
                            "status": "repo_not_found",
                            "message": "Repository not found"
                        }
                        missing_repos.append(repo_name)
                        
                    else:
                        repo_statuses[repo_name] = {
                            "status": "error",
                            "message": f"Error checking repository: HTTP {response.status_code}"
                        }
                        missing_repos.append(repo_name)
                        
                except Exception as e:
                    repo_statuses[repo_name] = {
                        "status": "error", 
                        "message": f"Error checking repository: {str(e)}"
                    }
                    missing_repos.append(repo_name)
        
        is_synced = len(missing_repos) == 0
        
        return {
            "success": True,
            "ruleset_name": ruleset_name,
            "is_synced": is_synced,
            "missing_repos": missing_repos,
            "repo_statuses": repo_statuses,
            "total_repos": len(request_data.repo_names),
            "synced_repos": len(request_data.repo_names) - len(missing_repos)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking ruleset sync status: {str(e)}")


@router.delete("/api/rulesets/{ruleset_id}")
async def delete_ruleset(
    ruleset_id: int,
    github_user: str,
    db: Annotated[Session, Depends(get_db)]
):
    """Delete a ruleset"""
    
    try:
        # Get user account
        user_account = db.query(Account).filter(Account.github_user == github_user).first()
        if not user_account:
            raise HTTPException(status_code=404, detail=ACCOUNT_NOT_FOUND)
        
        # Get ruleset
        ruleset = db.query(Ruleset).filter(
            and_(Ruleset.ruleset_id == ruleset_id, Ruleset.user_id == user_account.user_id)
        ).first()
        
        if not ruleset:
            raise HTTPException(status_code=404, detail=RULESET_NOT_FOUND)
        
        ruleset_name = ruleset.ruleset_name
        
        # Delete associated project relationships
        db.query(ProjectRuleset).filter(ProjectRuleset.ruleset_id == ruleset_id).delete()
        
        # Delete the ruleset
        db.delete(ruleset)
        db.commit()
        
        return {
            "success": True,
            "message": f"Ruleset '{ruleset_name}' deleted successfully"
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting ruleset: {str(e)}")


async def apply_ruleset_to_repo(github_user: str, repo_name: str, ruleset_data: dict) -> bool:
    """Apply a ruleset to a specific repository using GitHub API"""
    
    try:
        # Check if user is authenticated
        if github_user not in user_tokens:
            print(f"❌ User {github_user} is not authenticated")
            return False
        
        # Get user's GitHub token
        token = user_tokens[github_user]
        
        # Prepare headers for GitHub API
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json"
        }
        
        # Split repo_name into owner/repo format
        if '/' in repo_name:
            owner, repo = repo_name.split('/', 1)
        else:
            # If no slash, assume the user owns the repo
            owner = github_user
            repo = repo_name
        
        # Transform the exported ruleset data to the format required by GitHub API
        # The exported format includes metadata that we need to strip for creation
        api_ruleset_data = {
            "name": ruleset_data.get("name", "Imported Ruleset"),
            "target": ruleset_data.get("target", "branch"),
            "enforcement": ruleset_data.get("enforcement", "active"),
            "rules": ruleset_data.get("rules", []),
            "conditions": ruleset_data.get("conditions", {}),
            "bypass_actors": ruleset_data.get("bypass_actors", [])
        }
        
        # Remove any fields that are read-only or not needed for creation
        # The exported format includes 'id' and 'source_type' which are not needed for creation
        if "id" in api_ruleset_data:
            del api_ruleset_data["id"]
        if "source_type" in api_ruleset_data:
            del api_ruleset_data["source_type"]
        
        # GitHub API endpoint for creating repository rulesets
        api_url = f"https://api.github.com/repos/{owner}/{repo}/rulesets"
        
        print(f"📋 Applying ruleset '{api_ruleset_data['name']}' to {owner}/{repo}")
        print(f"📋 API URL: {api_url}")
        print(f"📋 Ruleset data: {json.dumps(api_ruleset_data, indent=2)}")
        
        # Make the API request to create the ruleset
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                headers=headers,
                json=api_ruleset_data,
                timeout=30
            )
        
            print(f"📋 GitHub API response status: {response.status_code}")
        
            if response.status_code == 201:
                # Success - ruleset created
                response_data = response.json()
                print(f"✅ Successfully applied ruleset to {owner}/{repo}. Created ruleset ID: {response_data.get('id')}")
                return True
            elif response.status_code == 422:
                # Validation error - likely the ruleset already exists or has invalid data
                error_data = response.json()
                print(f"⚠️ Validation error applying ruleset to {owner}/{repo}: {error_data.get('message', 'Unknown error')}")
                print(f"📋 Error details: {json.dumps(error_data, indent=2)}")
                return False
            elif response.status_code == 403:
                # Permission denied - user doesn't have admin rights to the repo
                print(f"❌ Permission denied applying ruleset to {owner}/{repo}. User needs admin access to the repository.")
                return False
            elif response.status_code == 404:
                # Repository not found
                print(f"❌ Repository {owner}/{repo} not found")
                return False
            else:
                # Other error
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {"message": response.text}
                print(f"❌ Error applying ruleset to {owner}/{repo}: HTTP {response.status_code}")
                print(f"📋 Error details: {json.dumps(error_data, indent=2)}")
                return False
        
    except httpx.RequestError as e:
        print(f"❌ Network error applying ruleset to {repo_name}: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error applying ruleset to {repo_name}: {str(e)}")
        return False
