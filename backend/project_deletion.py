"""
Project Deletion API Module

Provides endpoints for enhanced project deletion functionality including:
- Listing all GitHub resources associated with a project
- Deleting GitHub resources (workflows, secrets, environment variables)
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Annotated, List, Dict, Any, Optional, Set
import requests
from pydantic import BaseModel

from database import get_db
from auth import user_tokens
from models import Project, Account, Repo, Workflow, ProjectRepo, ProjectWorkflow, ProjectSecret, ProjectEnvVar
from workflows import cleanup_orphaned_workflows

router = APIRouter()

_DEBUG_NO_PREFIX_LOOKUP = "🔍 Debug: Using database lookup for no_prefix project"

GITHUB_API_URL = "https://api.github.com"


class ProjectDeletionSummary(BaseModel):
    """Summary of resources that would be deleted for a project"""
    project_name: str
    project_code: str
    workflows: List[Dict[str, Any]]
    reusable_workflows: List[Dict[str, Any]]
    secrets: List[Dict[str, Any]]
    environment_variables: List[Dict[str, Any]]
    deployment_environments: List[Dict[str, Any]]

class DeleteProjectRequest(BaseModel):
    """Request model for project deletion"""
    github_user: str
    project_name: str
    delete_github_resources: bool = False
    delete_deployment_environments: bool = True


def _fetch_repository_secrets(repo_name: str, headers: Dict[str, str], project_prefix: str, project: Project = None, db: Session = None) -> List[Dict[str, Any]]:
    """Fetch repository secrets that match the project prefix or are tracked in database."""
    secrets = []
    secrets_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/secrets"
    
    try:
        response = requests.get(secrets_url, headers=headers)
        print(f"🔍 Debug: Repository secrets API response: {response.status_code}")
        
        if response.status_code == 200:
            secrets_data = response.json()
            all_secrets = secrets_data.get('secrets', [])
            print(f"🔍 Debug: Found {len(all_secrets)} total repository secrets")
            
            if all_secrets:
                print(f"🔍 Debug: All secret names: {[s['name'] for s in all_secrets]}")
                
                # For no_prefix projects, use database to identify project secrets
                if project and db and not project.use_prefix:
                    print(_DEBUG_NO_PREFIX_LOOKUP)
                    db_secrets = db.query(ProjectSecret).filter(
                        ProjectSecret.project_id == project.project_id
                    ).all()
                    tracked_names = {s.secret_name for s in db_secrets}
                    print(f"🔍 Debug: Tracked secret names in database: {tracked_names}")
                    matching_secrets = [s for s in all_secrets if s["name"] in tracked_names]
                else:
                    # For prefix projects, use prefix matching (but prevent empty prefix from matching everything)
                    if not project_prefix:
                        print("⚠️  Warning: Empty project_prefix with use_prefix=True - skipping to prevent matching all secrets")
                        matching_secrets = []
                    else:
                        matching_secrets = [s for s in all_secrets if s["name"].startswith(project_prefix)]
                
                print(f"🔍 Debug: Secrets matching project: {len(matching_secrets)}")
                
                if matching_secrets:
                    print(f"🔍 Debug: Matching secret names: {[s['name'] for s in matching_secrets]}")
                
                for secret in matching_secrets:
                    secrets.append({
                        "name": secret["name"],
                        "repository": repo_name,
                        "created_at": secret.get("created_at"),
                        "updated_at": secret.get("updated_at")
                    })
                    print(f"✅ Added repository secret: {secret['name']}")
            else:
                print("🔍 Debug: No repository secrets found")
        else:
            print(f"❌ Repository secrets API failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching repository secrets for {repo_name}: {str(e)}")
    
    return secrets


def _fetch_repository_variables(repo_name: str, headers: Dict[str, str], project_prefix: str, project: Project = None, db: Session = None) -> List[Dict[str, Any]]:
    """Fetch repository variables that match the project prefix or are tracked in database."""
    variables = []
    variables_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables"
    
    try:
        response = requests.get(variables_url, headers=headers)
        print(f"🔍 Debug: Repository variables API response: {response.status_code}")
        
        if response.status_code == 200:
            variables_data = response.json()
            all_variables = variables_data.get('variables', [])
            print(f"🔍 Debug: Found {len(all_variables)} total repository variables")
            
            if all_variables:
                print(f"🔍 Debug: All repository variable names: {[v['name'] for v in all_variables]}")
                
                # For no_prefix projects, use database to identify project variables
                if project and db and not project.use_prefix:
                    print(_DEBUG_NO_PREFIX_LOOKUP)
                    db_vars = db.query(ProjectEnvVar).filter(
                        ProjectEnvVar.project_id == project.project_id
                    ).all()
                    tracked_names = {v.env_var_name for v in db_vars}
                    print(f"🔍 Debug: Tracked variable names in database: {tracked_names}")
                    matching_variables = [v for v in all_variables if v["name"] in tracked_names]
                else:
                    # For prefix projects, use prefix matching (but prevent empty prefix from matching everything)
                    if not project_prefix:
                        print("⚠️  Warning: Empty project_prefix with use_prefix=True - skipping to prevent matching all variables")
                        matching_variables = []
                    else:
                        matching_variables = [v for v in all_variables if v["name"].startswith(project_prefix)]
                
                print(f"🔍 Debug: Repository variables matching project: {len(matching_variables)}")
                
                if matching_variables:
                    print(f"🔍 Debug: Matching repository variable names: {[v['name'] for v in matching_variables]}")
                
                for variable in matching_variables:
                    variables.append({
                        "name": variable["name"],
                        "value": variable.get("value", ""),
                        "repository": repo_name,
                        "environment": "repository",
                        "created_at": variable.get("created_at"),
                        "updated_at": variable.get("updated_at")
                    })
                    print(f"✅ Added repository variable: {variable['name']}")
            else:
                print("🔍 Debug: No repository variables found")
        else:
            print(f"❌ Repository variables API failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching repository variables for {repo_name}: {str(e)}")
    
    return variables


def _fetch_environment_secrets(repo_name: str, env_name: str, headers: Dict[str, str], project_prefix: str, project: Project = None, db: Session = None) -> List[Dict[str, Any]]:
    """Fetch environment secrets that match the project prefix or are tracked in database."""
    secrets = []
    env_secrets_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments/{env_name}/secrets"
    
    try:
        response = requests.get(env_secrets_url, headers=headers)
        
        if response.status_code == 200:
            env_secrets_data = response.json()
            all_env_secrets = env_secrets_data.get('secrets', [])
            print(f"🔍 Debug: Found {len(all_env_secrets)} environment secrets in '{env_name}'")
            
            if all_env_secrets:
                print(f"🔍 Debug: Secret names in '{env_name}': {[s['name'] for s in all_env_secrets]}")
                
                # For no_prefix projects, use database to identify project secrets
                if project and db and not project.use_prefix:
                    print(_DEBUG_NO_PREFIX_LOOKUP)
                    db_secrets = db.query(ProjectSecret).filter(
                        ProjectSecret.project_id == project.project_id
                    ).all()
                    tracked_names = {s.secret_name for s in db_secrets}
                    print(f"🔍 Debug: Tracked secret names in database: {tracked_names}")
                    
                    for secret in all_env_secrets:
                        secret_in_database = secret["name"] in tracked_names
                        print(f"🔍 Debug: Environment secret '{secret['name']}' in database: {secret_in_database}")
                        
                        if secret_in_database:
                            secrets.append({
                                "name": secret["name"],
                                "repository": repo_name,
                                "environment": env_name,
                                "created_at": secret.get("created_at"),
                                "updated_at": secret.get("updated_at")
                            })
                            print(f"✅ Added environment secret: {secret['name']} (found in database)")
                else:
                    # For prefix projects, use prefix matching (but prevent empty prefix from matching everything)
                    for secret in all_env_secrets:
                        if not project_prefix:
                            print(f"⚠️  Warning: Empty project_prefix - skipping environment secret '{secret['name']}'")
                            continue
                            
                        secret_matches_prefix = secret["name"].startswith(project_prefix)
                        print(f"🔍 Debug: Environment secret '{secret['name']}' matches prefix '{project_prefix}': {secret_matches_prefix}")
                        
                        if secret_matches_prefix:
                            secrets.append({
                                "name": secret["name"],
                                "repository": repo_name,
                                "environment": env_name,
                                "created_at": secret.get("created_at"),
                                "updated_at": secret.get("updated_at")
                            })
                            print(f"✅ Added environment secret: {secret['name']} (secret name matches prefix)")
        else:
            print(f"❌ Environment secrets API failed for '{env_name}': {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching environment secrets for {repo_name}/{env_name}: {str(e)}")
    
    return secrets


def _fetch_environment_variables(repo_name: str, env_name: str, headers: Dict[str, str], project_prefix: str, project: Project = None, db: Session = None) -> List[Dict[str, Any]]:
    """Fetch environment variables that match the project prefix or are tracked in database."""
    variables = []
    env_vars_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments/{env_name}/variables"
    
    try:
        response = requests.get(env_vars_url, headers=headers)
        
        if response.status_code == 200:
            env_vars_data = response.json()
            all_env_vars = env_vars_data.get('variables', [])
            print(f"🔍 Debug: Found {len(all_env_vars)} environment variables in '{env_name}'")
            
            if all_env_vars:
                print(f"🔍 Debug: Variable names in '{env_name}': {[v['name'] for v in all_env_vars]}")
                
                # For no_prefix projects, use database to identify project variables
                if project and db and not project.use_prefix:
                    print(_DEBUG_NO_PREFIX_LOOKUP)
                    db_vars = db.query(ProjectEnvVar).filter(
                        ProjectEnvVar.project_id == project.project_id
                    ).all()
                    tracked_names = {v.env_var_name for v in db_vars}
                    print(f"🔍 Debug: Tracked variable names in database: {tracked_names}")
                    
                    for var in all_env_vars:
                        var_in_database = var["name"] in tracked_names
                        print(f"🔍 Debug: Variable '{var['name']}' in database: {var_in_database}")
                        
                        if var_in_database:
                            variables.append({
                                "name": var["name"],
                                "value": var["value"],
                                "repository": repo_name,
                                "environment": env_name,
                                "created_at": var.get("created_at"),
                                "updated_at": var.get("updated_at")
                            })
                            print(f"✅ Added environment variable: {var['name']} (found in database)")
                else:
                    # For prefix projects, use prefix matching (but prevent empty prefix from matching everything)
                    for var in all_env_vars:
                        if not project_prefix:
                            print(f"⚠️  Warning: Empty project_prefix - skipping environment variable '{var['name']}'")
                            continue
                            
                        var_matches_prefix = var["name"].startswith(project_prefix)
                        print(f"🔍 Debug: Variable '{var['name']}' matches prefix '{project_prefix}': {var_matches_prefix}")
                        
                        if var_matches_prefix:
                            variables.append({
                                "name": var["name"],
                                "value": var["value"],
                                "repository": repo_name,
                                "environment": env_name,
                                "created_at": var.get("created_at"),
                                "updated_at": var.get("updated_at")
                            })
                            print(f"✅ Added environment variable: {var['name']} (variable name matches prefix)")
        else:
            print(f"❌ Environment variables API failed for '{env_name}': {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching environment variables for {repo_name}/{env_name}: {str(e)}")
    
    return variables


def _fetch_deployment_environments(repo_name: str, headers: Dict[str, str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Fetch deployment environments and their associated secrets/variables."""
    environments = []
    all_env_secrets = []
    all_env_variables = []
    
    environments_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments"
    
    try:
        response = requests.get(environments_url, headers=headers)
        print(f"🔍 Debug: Environments API response: {response.status_code}")
        
        if response.status_code == 200:
            environments_data = response.json()
            all_environments = environments_data.get('environments', [])
            print(f"🔍 Debug: Found {len(all_environments)} total environments")
            
            if all_environments:
                print(f"🔍 Debug: All environment names: {[e['name'] for e in all_environments]}")
                print(f"🔍 Debug: Adding all {len(all_environments)} deployment environments (no prefix filtering)")
                
                for env in all_environments:
                    print(f"\n🔍 Debug: Processing environment '{env['name']}' (deployment environments don't use prefix)")
                    
                    environments.append({
                        "name": env["name"],
                        "repository": repo_name,
                        "created_at": env.get("created_at"),
                        "updated_at": env.get("updated_at")
                    })
                    print(f"✅ Added deployment environment: {env['name']}")
            else:
                print("🔍 Debug: No environments found")
        else:
            print(f"❌ Environments API failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching environments for {repo_name}: {str(e)}")
    
    return environments, all_env_secrets, all_env_variables


def _process_single_environment(repo_name: str, env_name: str, headers: Dict[str, str], project_prefix: str, project: Project = None, db: Session = None) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Process secrets and variables for a single environment."""
    env_secrets = _fetch_environment_secrets(repo_name, env_name, headers, project_prefix, project, db)
    env_variables = _fetch_environment_variables(repo_name, env_name, headers, project_prefix, project, db)
    return env_secrets, env_variables


def _validate_repository_access(repo_name: str, headers: Dict[str, str]) -> bool:
    """Test repository accessibility and log access status."""
    repo_url = f"{GITHUB_API_URL}/repos/{repo_name}"
    
    try:
        response = requests.get(repo_url, headers=headers)
        print(f"🔍 Debug: Repository '{repo_name}' accessibility: {response.status_code}")
        
        if response.status_code != 200:
            if response.status_code == 404:
                print(f"❌ Repository '{repo_name}' not found or no access")
            elif response.status_code == 401:
                print(f"❌ Authentication failed for repository '{repo_name}'")
            elif response.status_code == 403:
                print(f"❌ Access forbidden for repository '{repo_name}'")
            return False
        return True
    except Exception as e:
        print(f"❌ Error validating repository access for {repo_name}: {str(e)}")
        return False


def _process_repository_resources(repo_name: str, headers: Dict[str, str], project_prefix: str, project: Project = None, db: Session = None) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Process all GitHub resources for a single repository."""
    print(f"\n🔍 Debug: Processing repository: {repo_name}")
    
    # Validate repository access first
    if not _validate_repository_access(repo_name, headers):
        return [], [], []
    
    # Collect repository-level resources
    repo_secrets = _fetch_repository_secrets(repo_name, headers, project_prefix, project, db)
    repo_variables = _fetch_repository_variables(repo_name, headers, project_prefix, project, db)
    
    # Collect deployment environments and their resources
    environments, _, _ = _fetch_deployment_environments(repo_name, headers)
    
    # Process environment-specific resources
    all_env_secrets = []
    all_env_variables = []
    
    for env in environments:
        env_secrets, env_variables = _process_single_environment(
            repo_name, env["name"], headers, project_prefix, project, db
        )
        all_env_secrets.extend(env_secrets)
        all_env_variables.extend(env_variables)
    
    # Combine all resources
    all_secrets = repo_secrets + all_env_secrets
    all_variables = repo_variables + all_env_variables
    
    return all_secrets, all_variables, environments


def _get_tracked_workflow_names(project: Project, db: Session) -> Set[str]:
    """Return a set of normalized workflow filenames tracked in the DB for a no_prefix project.

    Workflow names may be stored with or without a .yml/.yaml suffix.  Both the
    '.yml' and '.yaml' variants of each base name are included so that the set
    matches whatever extension GitHub happens to use in the repository path.
    """
    print(f"🔍 Debug: Using database lookup for no_prefix project workflows")
    tracked: Set[str] = set()
    # Single join query – avoids N+1 per-row Workflow lookups
    rows = (
        db.query(Workflow.workflow_name)
        .join(ProjectWorkflow, ProjectWorkflow.workflow_id == Workflow.workflow_id)
        .filter(ProjectWorkflow.project_id == project.project_id)
        .all()
    )
    for (raw_name,) in rows:
        raw_name = raw_name or ""
        # Strip any existing suffix to obtain the base name
        if raw_name.endswith(".yaml"):
            base_name = raw_name[:-5]
        elif raw_name.endswith(".yml"):
            base_name = raw_name[:-4]
        else:
            base_name = raw_name
        # Include both variants so we match regardless of the extension on disk
        tracked.add(f"{base_name}.yml")
        tracked.add(f"{base_name}.yaml")
    print(f"🔍 Debug: Tracked workflow names in database: {tracked}")
    return tracked


def _workflow_belongs_to_project(
    filename: str,
    project_prefix: str,
    project: Optional[Project],
    tracked_workflow_names: Set[str],
) -> bool:
    """Return True if the workflow file belongs to the given project.

    For no_prefix projects the filename is checked against the set of workflow
    filenames tracked in the database.  For prefix-based projects the filename
    must start with project_prefix (empty prefix never matches anything).
    """
    if project and not project.use_prefix:
        belongs = filename in tracked_workflow_names
        print(f"  - Filename in tracked workflows: {belongs}")
        return belongs
    if not project_prefix:
        print(f"  - ⚠️  Warning: Empty project_prefix - skipping workflow")
        return False
    belongs = filename.startswith(project_prefix)
    print(f"  - Filename starts with prefix: {belongs}")
    return belongs


def _delete_workflow_file(
    repo_name: str,
    headers: Dict[str, str],
    filename: str,
    workflow_path: str,
    deletion_results: Dict[str, Any],
) -> None:
    """Fetch file metadata and delete a single workflow file from GitHub.

    On success a human-readable summary string is appended to
    deletion_results['github_resources_deleted'].
    On failure the error message is appended to deletion_results['errors'].
    """
    file_url = f"{GITHUB_API_URL}/repos/{repo_name}/contents/{workflow_path}"
    file_response = requests.get(file_url, headers=headers)
    if file_response.status_code != 200:
        error_msg = f"Failed to get workflow file data for {filename} from {repo_name}: HTTP {file_response.status_code}"
        deletion_results["errors"].append(error_msg)
        print(f"❌ {error_msg}")
        return
    file_data = file_response.json()
    sha = file_data.get("sha")
    if not sha:
        error_msg = f"Missing SHA for workflow file {filename} from {repo_name} – cannot delete"
        deletion_results["errors"].append(error_msg)
        print(f"❌ {error_msg}")
        return
    delete_response = requests.delete(
        file_url,
        headers=headers,
        json={
            "message": f"Delete workflow {filename} (ActionsManager project deletion)",
            "sha": sha,
        },
    )
    if delete_response.status_code == 200:
        deletion_results["github_resources_deleted"].append(f"Workflow: {filename} from {repo_name}")
        print(f"✅ Successfully deleted workflow {filename} from {repo_name}")
    else:
        error_msg = f"Failed to delete workflow {filename} from {repo_name}: HTTP {delete_response.status_code}"
        deletion_results["errors"].append(error_msg)
        print(f"❌ {error_msg}")
        print(f"   Response: {delete_response.text}")


def _delete_project_workflows(repo_name: str, headers: Dict[str, str], project_prefix: str, deletion_results: Dict[str, Any], project: Optional[Project] = None, db: Optional[Session] = None) -> None:
    """Delete GitHub workflows that match the project prefix or are tracked in database."""
    workflows_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/workflows"
    try:
        workflows_response = requests.get(workflows_url, headers=headers)
        if workflows_response.status_code != 200:
            return
        workflows_data = workflows_response.json()

        # For no_prefix projects, build the set of tracked workflow filenames once
        tracked_workflow_names: Set[str] = set()
        if project and db and not project.use_prefix:
            tracked_workflow_names = _get_tracked_workflow_names(project, db)

        for workflow in workflows_data.get("workflows", []):
            workflow_name = workflow["name"]
            workflow_path = workflow.get("path", "")
            filename = workflow_path.split("/")[-1] if workflow_path else ""

            print(f"🔍 Debug: Checking workflow for deletion:")
            print(f"  - Workflow name (from YAML): {workflow_name}")
            print(f"  - Workflow path: {workflow_path}")
            print(f"  - Filename: {filename}")
            print(f"  - Project prefix: {project_prefix}")

            if _workflow_belongs_to_project(filename, project_prefix, project, tracked_workflow_names):
                print(f"✅ Workflow {filename} identified for deletion from {repo_name}")
                _delete_workflow_file(repo_name, headers, filename, workflow_path, deletion_results)
            else:
                print(f"⚪ Skipping workflow {filename} - does not belong to project")
    except Exception as e:
        error_msg = f"Error deleting workflows from {repo_name}: {str(e)}"
        deletion_results["errors"].append(error_msg)
        print(f"❌ {error_msg}")


def _delete_repository_secrets(repo_name: str, headers: Dict[str, str], project_prefix: str, deletion_results: Dict[str, Any], project: Project = None, db: Session = None) -> None:
    """Delete repository secrets that match the project prefix or are tracked in database."""
    secrets_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/secrets"
    
    try:
        secrets_response = requests.get(secrets_url, headers=headers)
        
        if secrets_response.status_code == 200:
            secrets_data = secrets_response.json()
            
            # For no_prefix projects, get secret names from database
            if project and db and not project.use_prefix:
                db_secrets = db.query(ProjectSecret).filter(
                    ProjectSecret.project_id == project.project_id
                ).all()
                tracked_names = {s.secret_name for s in db_secrets}
                
                for secret in secrets_data.get("secrets", []):
                    if secret["name"] in tracked_names:
                        delete_secret_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/secrets/{secret['name']}"
                        delete_response = requests.delete(delete_secret_url, headers=headers)
                        
                        if delete_response.status_code == 204:
                            deletion_results["github_resources_deleted"].append(f"Repository Secret: {secret['name']} from {repo_name}")
                        else:
                            deletion_results["errors"].append(f"Failed to delete repository secret {secret['name']} from {repo_name}")
            else:
                # For prefix projects, use prefix matching (but prevent empty prefix from matching everything)
                for secret in secrets_data.get("secrets", []):
                    if project_prefix and secret["name"].startswith(project_prefix):
                        delete_secret_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/secrets/{secret['name']}"
                        delete_response = requests.delete(delete_secret_url, headers=headers)
                        
                        if delete_response.status_code == 204:
                            deletion_results["github_resources_deleted"].append(f"Repository Secret: {secret['name']} from {repo_name}")
                        else:
                            deletion_results["errors"].append(f"Failed to delete repository secret {secret['name']} from {repo_name}")
    except Exception as e:
        error_msg = f"Error deleting repository secrets from {repo_name}: {str(e)}"
        deletion_results["errors"].append(error_msg)
        print(f"❌ {error_msg}")


def _delete_repository_variables(repo_name: str, headers: Dict[str, str], project_prefix: str, deletion_results: Dict[str, Any], project: Project = None, db: Session = None) -> None:
    """Delete repository variables that match the project prefix or are tracked in database."""
    variables_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables"
    
    try:
        variables_response = requests.get(variables_url, headers=headers)
        
        if variables_response.status_code == 200:
            variables_data = variables_response.json()
            
            # For no_prefix projects, get variable names from database
            if project and db and not project.use_prefix:
                db_vars = db.query(ProjectEnvVar).filter(
                    ProjectEnvVar.project_id == project.project_id
                ).all()
                tracked_names = {v.env_var_name for v in db_vars}
                
                for variable in variables_data.get("variables", []):
                    if variable["name"] in tracked_names:
                        delete_variable_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables/{variable['name']}"
                        delete_response = requests.delete(delete_variable_url, headers=headers)
                        
                        if delete_response.status_code == 204:
                            deletion_results["github_resources_deleted"].append(f"Repository Variable: {variable['name']} from {repo_name}")
                        else:
                            deletion_results["errors"].append(f"Failed to delete repository variable {variable['name']} from {repo_name}")
            else:
                # For prefix projects, use prefix matching (but prevent empty prefix from matching everything)
                for variable in variables_data.get("variables", []):
                    if project_prefix and variable["name"].startswith(project_prefix):
                        delete_variable_url = f"{GITHUB_API_URL}/repos/{repo_name}/actions/variables/{variable['name']}"
                        delete_response = requests.delete(delete_variable_url, headers=headers)
                        
                        if delete_response.status_code == 204:
                            deletion_results["github_resources_deleted"].append(f"Repository Variable: {variable['name']} from {repo_name}")
                        else:
                            deletion_results["errors"].append(f"Failed to delete repository variable {variable['name']} from {repo_name}")
    except Exception as e:
        error_msg = f"Error deleting repository variables from {repo_name}: {str(e)}"
        deletion_results["errors"].append(error_msg)
        print(f"❌ {error_msg}")


def _delete_deployment_environments(repo_name: str, headers: Dict[str, str], deletion_results: Dict[str, Any]) -> None:
    """Delete all deployment environments for the repository."""
    environments_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments"
    
    try:
        env_response = requests.get(environments_url, headers=headers)
        
        if env_response.status_code == 200:
            environments_data = env_response.json()
            for env in environments_data.get("environments", []):
                delete_env_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments/{env['name']}"
                delete_response = requests.delete(delete_env_url, headers=headers)
                
                if delete_response.status_code == 204:
                    deletion_results["github_resources_deleted"].append(f"Deployment Environment: {env['name']} from {repo_name}")
                else:
                    deletion_results["errors"].append(f"Failed to delete deployment environment {env['name']} from {repo_name}")
    except Exception as e:
        error_msg = f"Error deleting deployment environments from {repo_name}: {str(e)}"
        deletion_results["errors"].append(error_msg)
        print(f"❌ {error_msg}")


def _delete_environment_secrets(repo_name: str, headers: Dict[str, str], project_prefix: str, deletion_results: Dict[str, Any], project: Project = None, db: Session = None) -> None:
    """Delete environment-scoped secrets that match the project prefix or are tracked in database."""
    environments_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments"
    
    try:
        env_response = requests.get(environments_url, headers=headers)
        
        if env_response.status_code == 200:
            environments_data = env_response.json()
            
            # For no_prefix projects, get secret names from database
            tracked_names = set()
            if project and db and not project.use_prefix:
                db_secrets = db.query(ProjectSecret).filter(
                    ProjectSecret.project_id == project.project_id
                ).all()
                tracked_names = {s.secret_name for s in db_secrets}
            
            for env in environments_data.get("environments", []):
                env_secrets_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments/{env['name']}/secrets"
                env_secrets_response = requests.get(env_secrets_url, headers=headers)
                
                if env_secrets_response.status_code == 200:
                    env_secrets_data = env_secrets_response.json()
                    for secret in env_secrets_data.get("secrets", []):
                        # Check if secret belongs to project
                        belongs_to_project = False
                        if project and db and not project.use_prefix:
                            belongs_to_project = secret["name"] in tracked_names
                        else:
                            belongs_to_project = project_prefix and secret["name"].startswith(project_prefix)
                        
                        if belongs_to_project:
                            delete_env_secret_url = f"{GITHUB_API_URL}/repos/{repo_name}/environments/{env['name']}/secrets/{secret['name']}"
                            delete_response = requests.delete(delete_env_secret_url, headers=headers)
                            
                            if delete_response.status_code == 204:
                                deletion_results["github_resources_deleted"].append(f"Environment Secret: {secret['name']} from {repo_name}/{env['name']}")
                            else:
                                deletion_results["errors"].append(f"Failed to delete environment secret {secret['name']} from {repo_name}/{env['name']}")
    except Exception as e:
        error_msg = f"Error deleting environment secrets from {repo_name}: {str(e)}"
        deletion_results["errors"].append(error_msg)
        print(f"❌ {error_msg}")


def _delete_github_resources_for_repository(repo_name: str, headers: Dict[str, str], project_prefix: str, deletion_results: Dict[str, Any], project: Project = None, db: Session = None, delete_deployment_environments: bool = True) -> None:
    """Delete all GitHub resources for a single repository."""
    try:
        print(f"🔍 Processing repository: {repo_name}")

        # Delete workflows that match project prefix or are tracked in database
        _delete_project_workflows(repo_name, headers, project_prefix, deletion_results, project, db)

        # Delete repository secrets with project prefix or tracked in database
        _delete_repository_secrets(repo_name, headers, project_prefix, deletion_results, project, db)

        # Delete repository variables with project prefix or tracked in database
        _delete_repository_variables(repo_name, headers, project_prefix, deletion_results, project, db)

        # Delete ALL deployment environments (they don't use project prefix), unless the user opted to keep them
        if delete_deployment_environments:
            _delete_deployment_environments(repo_name, headers, deletion_results)

        # Delete environment-scoped secrets with project prefix or tracked in database
        _delete_environment_secrets(repo_name, headers, project_prefix, deletion_results, project, db)

    except Exception as e:
        deletion_results["errors"].append(f"Error deleting GitHub resources from {repo_name}: {str(e)}")


def _delete_all_github_resources(repo_names: List[str], headers: Dict[str, str], project_code: str, deletion_results: Dict[str, Any], project: Project = None, db: Session = None, delete_deployment_environments: bool = True) -> None:
    """Delete GitHub resources across all repositories for the project."""
    # Only use prefix if project.use_prefix is True
    project_prefix = f"AM_{project_code}_" if (project and project.use_prefix) else ""

    # Delete GitHub resources for each repository
    for repo_name in repo_names:
        _delete_github_resources_for_repository(repo_name, headers, project_prefix, deletion_results, project, db, delete_deployment_environments)


def _debug_resource_summary(github_secrets: List[Dict[str, Any]], github_env_vars: List[Dict[str, Any]], 
                           github_environments: List[Dict[str, Any]], project_prefix: str) -> None:
    """Log resource discovery summary."""
    prefix_matched_count = len(github_secrets) + len(github_env_vars) + len(github_environments)
    
    print(f"\n🔍 Debug: Resource summary:")
    print(f"  - Prefix-matched resources: {prefix_matched_count}")
    print(f"✅ Only showing resources that match project prefix '{project_prefix}'")


def _build_deletion_summary(project: Project, workflows: List[Dict[str, Any]], reusable_workflows: List[Dict[str, Any]], 
                           github_secrets: List[Dict[str, Any]], github_env_vars: List[Dict[str, Any]], 
                           github_environments: List[Dict[str, Any]]) -> ProjectDeletionSummary:
    """Build the final deletion summary response."""
    print(f"🔍 Debug: Final summary:")
    print(f"  - Workflows: {len(workflows)}")
    print(f"  - Reusable workflows: {len(reusable_workflows)}")
    print(f"  - GitHub secrets: {len(github_secrets)}")
    print(f"  - Environment variables: {len(github_env_vars)}")
    print(f"  - Deployment environments: {len(github_environments)}")

    return ProjectDeletionSummary(
        project_name=project.project_name,
        project_code=project.project_code,
        workflows=workflows,
        reusable_workflows=reusable_workflows,
        secrets=github_secrets,
        environment_variables=github_env_vars,
        deployment_environments=github_environments
    )


def _get_project_and_user(project_name: str, github_user: str, db: Session) -> tuple[Account, Project]:
    """Get and validate user and project from database."""
    user = db.query(Account).filter(Account.github_user == github_user.strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="GitHub user not found")

    project = db.query(Project).filter(
        Project.project_name.ilike(project_name.strip()),
        Project.user_id == user.user_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found or access denied")
    
    return user, project


def _get_project_repositories(project: Project, db: Session) -> List[str]:
    """Get repository names associated with the project."""
    return [
        db.query(Repo.repo_name).filter(Repo.repo_id == pr.repo_id).scalar()
        for pr in db.query(ProjectRepo).filter(ProjectRepo.project_id == project.project_id).all()
    ]


def _get_project_workflows(project: Project, db: Session) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Get and categorize workflows associated with the project."""
    all_workflows = db.query(Workflow) \
        .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id) \
        .filter(ProjectWorkflow.project_id == project.project_id) \
        .all()

    workflows = []
    reusable_workflows = []

    for w in all_workflows:
        workflow_info = {
            "name": w.workflow_name,
            "is_reusable": w.reusable_workflow,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None
        }
        
        if w.reusable_workflow:
            reusable_workflows.append(workflow_info)
        else:
            workflows.append(workflow_info)
    
    return workflows, reusable_workflows


@router.get("/projects/{project_name}/deletion-summary")
async def get_project_deletion_summary(
    project_name: str,
    db: Annotated[Session, Depends(get_db)],
    github_user: Annotated[str, Query(description="GitHub username is required")],
):
    """
    Get a summary of all resources that would be affected when deleting a project.
    This includes database records and GitHub resources.
    """
    try:
        # Get user and project from database
        user, project = _get_project_and_user(project_name, github_user, db)

        # Get repositories and workflows from database  
        repo_names = _get_project_repositories(project, db)
        workflows, reusable_workflows = _get_project_workflows(project, db)

        # Initialize GitHub resource collections
        github_secrets = []
        github_env_vars = []
        github_environments = []

        # Debug authentication and repository status
        print(f"🔍 Debug: Authentication check:")
        print(f"  - github_user: '{github_user}'")
        print(f"  - github_user in user_tokens: {github_user in user_tokens if github_user else 'No github_user'}")
        print(f"  - active credential cache entries: {len(list(user_tokens.keys()))}")
        print(f"🔍 Debug: Repository check:")
        print(f"  - repo_names: {repo_names}")
        print(f"  - repo_count: {len(repo_names) if repo_names else 0}")
        print(f"🔍 Debug: Project details:")
        print(f"  - project_code: '{project.project_code}'")
        print(f"  - expected_prefix: 'AM_{project.project_code}_'")

        # Handle case where no repositories are found
        if not repo_names:
            print("⚠️ DEBUG: No repositories found for this project - GitHub API calls will be skipped")
            print("🔍 DEBUG: Checking project-repository associations...")
            project_repos = db.query(ProjectRepo).filter(ProjectRepo.project_id == project.project_id).all()
            print(f"🔍 DEBUG: Found {len(project_repos)} project-repo associations")
            for pr in project_repos:
                repo = db.query(Repo).filter(Repo.repo_id == pr.repo_id).first()
                print(f"🔍 DEBUG: Repo ID {pr.repo_id} -> {repo.repo_name if repo else 'NOT FOUND'}")

        # Fetch GitHub resources if authenticated and repositories exist
        if github_user in user_tokens and repo_names:
            token = user_tokens[github_user]
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }
            # Only use prefix if project.use_prefix is True
            project_prefix = f"AM_{project.project_code}_" if project.use_prefix else ""
            
            print(f"🔍 Debug: Starting GitHub API calls")
            print(f"🔍 Debug: Project use_prefix setting: {project.use_prefix}")
            print(f"🔍 Debug: Project prefix for filtering: '{project_prefix}'")
            print(f"🔍 Debug: Authentication token available: {bool(token)}")

            # Process each repository to collect GitHub resources
            for repo_name in repo_names:
                try:
                    repo_secrets, repo_env_vars, repo_environments = _process_repository_resources(
                        repo_name, headers, project_prefix, project, db
                    )
                    
                    github_secrets.extend(repo_secrets)
                    github_env_vars.extend(repo_env_vars)
                    github_environments.extend(repo_environments)
                    
                except Exception as e:
                    print(f"Warning: Could not fetch GitHub resources for {repo_name}: {str(e)}")
                    # Continue with other repositories even if one fails

            # Log resource discovery summary
            _debug_resource_summary(github_secrets, github_env_vars, github_environments, project_prefix)
        else:
            print(f"🔍 Debug: Skipping GitHub API calls - Missing token or repos")
            print(f"  - github_user in user_tokens: {github_user in user_tokens if github_user else False}")
            print(f"  - repo_names: {repo_names}")

        # Build and return the deletion summary
        return _build_deletion_summary(
            project, workflows, reusable_workflows, 
            github_secrets, github_env_vars, github_environments
        )

    except Exception as e:
        print(f"Error getting project deletion summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving project deletion summary: {str(e)}")


@router.delete("/projects/{project_name}/enhanced")
async def delete_project_enhanced(
    project_name: str,
    request: DeleteProjectRequest,
    db: Annotated[Session, Depends(get_db)]
):
    """
    Enhanced project deletion that can optionally delete GitHub resources.
    """
    try:
        # Get user and project from database
        user, project = _get_project_and_user(project_name, request.github_user, db)

        deletion_results = {
            "project_deleted": False,
            "github_resources_deleted": [],
            "errors": []
        }

        # If requested, delete GitHub resources first
        if request.delete_github_resources and request.github_user in user_tokens:
            token = user_tokens[request.github_user]
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }

            # Get repositories for this project
            repo_names = _get_project_repositories(project, db)
            
            # Delete GitHub resources across all repositories
            _delete_all_github_resources(repo_names, headers, project.project_code, deletion_results, project, db, request.delete_deployment_environments)

        # Delete the project from the database (this will cascade to related records)
        db.delete(project)
        db.commit()
        deletion_results["project_deleted"] = True

        # Clean up any orphaned workflows that are no longer associated with any projects
        cleanup_orphaned_workflows(db)

        return {
            "message": "✅ Project deletion completed",
            "details": deletion_results
        }

    except Exception as e:
        db.rollback()
        print(f"Error in enhanced project deletion: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting project: {str(e)}")

    finally:
        db.close()
