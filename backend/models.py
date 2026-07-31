"""
Database Models for ActionsManager.xyz

Defines SQLAlchemy models for:
- Account: User accounts with GitHub OAuth
- WorkspaceMember: Application/workspace membership and roles
- Project: Project containers for organizing repositories
- Repo: GitHub repositories
- Workflow: GitHub Actions workflows
- ProjectWorkflow: Many-to-many relationship between projects and workflows
- ProjectRepo: Many-to-many relationship between projects and repositories
"""

import secrets
import string
from sqlalchemy import Column, Index, Integer, String, DateTime, ForeignKey, Boolean, UniqueConstraint, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

_FK_ACCOUNTS_USER_ID = "accounts.user_id"
_FK_REPOS_REPO_ID = "repos.repo_id"
_FK_WORKFLOWS_WORKFLOW_ID = "workflows.workflow_id"
_FK_PROJECTS_PROJECT_ID = "projects.project_id"


def generate_random_id():
    """Generate a random 4-character project code"""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))


def generate_project_key_from_name(project_name):
    """Generate a project key from project name using first letters of words"""
    if not project_name or not project_name.strip():
        return generate_random_id()
    
    # Remove special characters and split into words (only alphabetic words)
    import re
    words = re.findall(r'\b[A-Za-z]+\b', project_name.upper())
    
    if not words:
        return generate_random_id()
    
    # For single word, take first 3 characters (or less if word is shorter)
    if len(words) == 1:
        word = words[0]
        key = word[:3] if len(word) >= 3 else word
    else:
        # Multiple words: use first letter of each word (up to 6 letters)
        # This creates abbreviations like "My Cool Project" -> "MCP"
        key = ''.join(word[0] for word in words[:6])
    
    # If resulting key is too short (less than 2 chars), fallback to random
    if len(key) < 2:
        return generate_random_id()
    
    return key


class Account(Base):
    """User accounts table with GitHub OAuth integration"""
    __tablename__ = "accounts"

    user_id = Column(Integer, primary_key=True, index=True)
    github_user = Column(String(255), unique=True, nullable=False)
    github_email = Column(String(255), unique=True, nullable=False)
    account_type = Column(String(50), nullable=False)  # billing plan: free, pro, enterprise
    github_account_type = Column(String(20), nullable=True, default="User")  # GitHub account type: User or Organization
    connected_github_account = Column(String(255), nullable=True)  # GitHub App installation account login
    connected_github_account_type = Column(String(20), nullable=True)  # GitHub App installation account type: User or Organization
    avatar_url = Column(String, nullable=True)
    last_login_at = Column(DateTime, nullable=True)  # Track last login timestamp
    last_login_ip = Column(String(45), nullable=True)  # Track last login IP address (45 chars for IPv6)
    github_api_calls = Column(Integer, default=0, nullable=False)  # Track total GitHub API calls made by this user
    github_api_calls_today = Column(Integer, default=0, nullable=False)  # Track API calls in last 24 hours
    api_calls_reset_at = Column(DateTime, nullable=True)  # Timestamp of last daily counter reset

    # Marketplace billing metadata
    marketplace_account_id = Column(Integer, nullable=True)  # GitHub Marketplace account ID
    marketplace_plan = Column(String(50), nullable=True)  # Current marketplace plan name
    marketplace_unit_count = Column(Integer, nullable=True)  # Number of units purchased
    marketplace_on_free_trial = Column(Boolean, default=False)  # Free trial status
    marketplace_next_billing_date = Column(DateTime, nullable=True)  # Next billing date
    marketplace_updated_at = Column(DateTime, nullable=True)  # Last marketplace update timestamp

    # Admin override for tier management
    admin_override = Column(Boolean, default=False, nullable=False)  # Whether tier is manually overridden by admin
    admin_override_until = Column(DateTime, nullable=True)  # When admin override expires (None = indefinite)

    # GitHub permission tracking
    github_permission_status = Column(String(50), nullable=True)  # Permission validation status: valid, missing_scopes, etc.
    github_permission_checked_at = Column(DateTime, nullable=True)  # Last time permissions were checked
    github_pat_token_encrypted = Column(Text, nullable=True)  # Encrypted personal access token / alternate GitHub token
    github_pat_token_type = Column(String(50), nullable=True)  # oauth_token, classic_pat, fine_grained_pat
    github_pat_status = Column(String(50), nullable=True)  # PAT validation status for UI feedback
    github_pat_last_error = Column(Text, nullable=True)  # Last PAT validation error shown in UI
    github_pat_checked_at = Column(DateTime, nullable=True)  # Last PAT validation timestamp
    github_pat_updated_at = Column(DateTime, nullable=True)  # Last PAT save / replace timestamp

    projects = relationship("Project", back_populates="user")
    workspace_membership = relationship("WorkspaceMember", back_populates="user", uselist=False)
    actions_projects = relationship("ActionsProject", back_populates="user")


class WorkspaceMember(Base):
    """
    Workspace/application membership for multi-user support.
    
    Tracks which users belong to the Actions Manager workspace and their role.
    Roles:
      - admin: Full management access (original owner)
      - member: Standard user — can view and edit assigned projects
      - read_only: Can view but cannot modify (default for new users)
    
    Designed so project-level permissions can be added cleanly in Phase 2
    via a separate ProjectMemberPermission table referencing this membership.
    """
    __tablename__ = "workspace_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(_FK_ACCOUNTS_USER_ID, ondelete="CASCADE"), nullable=False, unique=True, index=True)
    workspace_role = Column(String(20), nullable=False, default="read_only")  # admin, member, read_only
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("Account", back_populates="workspace_membership")


class AuthSession(Base):
    """Opaque server-side login sessions keyed by a hashed session token."""
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    github_user = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class Repo(Base):
    """GitHub repositories table"""
    __tablename__ = "repos"

    repo_id = Column(Integer, primary_key=True, index=True)
    repo_name = Column(String(255), unique=True, nullable=False)


class Workflow(Base):
    """GitHub Actions workflows table"""
    __tablename__ = "workflows"

    workflow_id = Column(Integer, primary_key=True, index=True)
    workflow_name = Column(String(255), nullable=False)
    workflow_yaml = Column(String, nullable=False)
    workflow_git_hash = Column(String(255), nullable=True)
    reusable_workflow = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    workflow_status = Column(String(30), nullable=False, default="new")  # Workflow lifecycle status: new, committed_locally, under_review, synced_with_github

    # Audit: track who last modified this workflow
    last_modified_by = Column(String(255), nullable=True)  # GitHub username of last editor

    # Remove unique constraints - allow multiple workflows with same name across projects
    
    # Relationship to versions
    versions = relationship("WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan", order_by="desc(WorkflowVersion.version_number)")


class WorkflowVersion(Base):
    """Version history for workflows - tracks all saved versions"""
    __tablename__ = "workflow_versions"

    version_id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey(_FK_WORKFLOWS_WORKFLOW_ID, ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)  # Auto-incremented version number per workflow
    content = Column(Text, nullable=False)  # Workflow YAML content at this version
    version_metadata = Column(Text, nullable=True)  # JSON metadata: author, session info, etc.
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Relationship to parent workflow
    workflow = relationship("Workflow", back_populates="versions")
    
    # Ensure version numbers are unique per workflow
    __table_args__ = (
        UniqueConstraint('workflow_id', 'version_number', name='uix_workflow_version'),
    )


class Project(Base):
    """Projects table for organizing repositories and workflows"""
    __tablename__ = "projects"

    project_id = Column(Integer, primary_key=True, index=True)  
    project_code = Column(String(10), unique=True, default=generate_random_id)
    project_name = Column(String(255), nullable=False)  
    user_id = Column(Integer, ForeignKey(_FK_ACCOUNTS_USER_ID, ondelete="CASCADE"), nullable=False)  
    branch_regex = Column(String(255), nullable=True) 
    branch_option = Column(String(50), nullable=True, default="default")  # default, pattern
    branch_max_age_days = Column(Integer, nullable=True, default=30)  # Filter branches by recency (1-30 days)
    reusable_workflows_enabled = Column(Boolean, default=False, nullable=False)  # Per-project reusable workflow setting
    use_prefix = Column(Boolean, default=True, nullable=False)  # Whether to use AM_{PROJECT_CODE}_ prefix for resources
    pr_state = Column(String(20), nullable=False, default="new")  # Project state: new, draft, open, synced
    project_type = Column(String(20), nullable=False, default="standard")  # Project type: standard, rwx
    repository_visibility_scope = Column(String(10), nullable=False, default="public")  # Project repository visibility scope: public, private
    project_color = Column(String(20), nullable=True)  # Project identity color key (blue, purple, etc.)
    validation_repo_id = Column(Integer, ForeignKey(_FK_REPOS_REPO_ID, ondelete="SET NULL"), nullable=True)
    preflight_required = Column(Boolean, default=False, nullable=False)
    last_preflight_status = Column(String(40), nullable=True)
    last_preflight_run_at = Column(DateTime, nullable=True)
    last_preflight_error = Column(String(500), nullable=True)
    last_preflight_pr_url = Column(String(500), nullable=True)
    last_preflight_content_hash = Column(String(64), nullable=True)
    drift_status = Column(String(20), nullable=False, default="unknown")  # unknown, clean, drifted, check_failed
    drift_count = Column(Integer, nullable=False, default=0)
    last_drift_check_at = Column(DateTime, nullable=True)
    drift_error_summary = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())  
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now()) 

    # Audit: track who last modified this project
    last_modified_by = Column(String(255), nullable=True)  # GitHub username of last editor

    user = relationship("Account", back_populates="projects")


class ActionsProject(Base):
    """A single custom GitHub Action imported from a repo's actions.yaml.

    Unlike Project (standard/rwx), this has no branch/PR/drift state — it's
    just a saved reference to an action plus its editable default inputs.
    """
    __tablename__ = "actions_projects"

    actions_project_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(_FK_ACCOUNTS_USER_ID, ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    source_url = Column(String(500), nullable=False)  # Original pasted GitHub URL
    owner = Column(String(255), nullable=False)
    repo = Column(String(255), nullable=False)
    ref = Column(String(255), nullable=False)  # branch, tag, or commit SHA
    yaml_path = Column(String(500), nullable=False, default="actions.yaml")
    inputs_json = Column(Text, nullable=False, default="[]")  # JSON list of {name, description, required, default}
    branding_icon = Column(String(50), nullable=True)  # Feather icon name from action.yml branding
    branding_color = Column(String(20), nullable=True)  # GitHub's fixed branding color enum
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_modified_by = Column(String(255), nullable=True)  # GitHub username of last editor

    user = relationship("Account", back_populates="actions_projects")


class ActionGroup(Base):
    """A user-created, shared, workspace-wide label for organizing ActionsProjects."""
    __tablename__ = "action_groups"

    action_group_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_modified_by = Column(String(255), nullable=True)  # GitHub username of last editor


class ActionGroupMembership(Base):
    """Many-to-many relationship table between ActionGroups and ActionsProjects"""
    __tablename__ = "action_group_memberships"

    action_group_id = Column(Integer, ForeignKey("action_groups.action_group_id", ondelete="CASCADE"), primary_key=True)
    actions_project_id = Column(Integer, ForeignKey("actions_projects.actions_project_id", ondelete="CASCADE"), primary_key=True)


class ProjectWorkflow(Base):
    """Many-to-many relationship table between Projects and Workflows"""
    __tablename__ = "project_workflows"

    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), primary_key=True)
    workflow_id = Column(Integer, ForeignKey(_FK_WORKFLOWS_WORKFLOW_ID, ondelete="CASCADE"), primary_key=True)


class ProjectRepo(Base):
    """Many-to-many relationship table between Projects and Repositories.

    Also stores optional per-repository branch configuration overrides for
    multi-repository projects. When ``branch_config_mode`` is ``"inherit"``
    (the default), the project-level branch settings are used for this
    repository. When set to ``"override"``, the override columns on this
    row take precedence for any GitHub read/write that targets this repo.
    """
    __tablename__ = "project_repos"

    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), primary_key=True)
    repo_id = Column(Integer, ForeignKey(_FK_REPOS_REPO_ID, ondelete="CASCADE"), primary_key=True)

    # Per-repository branch configuration overrides. All nullable so
    # existing rows continue to behave as "inherit project settings".
    branch_config_mode = Column(String(20), nullable=False, default="inherit")  # "inherit" | "override"
    branch_option = Column(String(50), nullable=True)  # "default" | "pattern"
    branch_regex = Column(String(255), nullable=True)
    branch_max_age_days = Column(Integer, nullable=True)


class Ruleset(Base):
    """GitHub repository rulesets table"""
    __tablename__ = "rulesets"

    ruleset_id = Column(Integer, primary_key=True, index=True)
    ruleset_name = Column(String(255), nullable=False)
    ruleset_json = Column(String, nullable=False)  # JSON data of the ruleset
    description = Column(String(500), nullable=True)
    user_id = Column(Integer, ForeignKey(_FK_ACCOUNTS_USER_ID, ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("Account")


class ProjectRuleset(Base):
    """Many-to-many relationship table between Projects and Rulesets"""
    __tablename__ = "project_rulesets"

    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), primary_key=True)
    ruleset_id = Column(Integer, ForeignKey("rulesets.ruleset_id", ondelete="CASCADE"), primary_key=True)


class ProjectPRCampaign(Base):
    """PR campaigns table — one row per PR campaign creation run.

    Each time a user opens a PR campaign, a new unique campaign record is
    created so newly-created PRs never get appended to a previous campaign.
    PR rows reference their campaign via ProjectPullRequest.campaign_id.
    """
    __tablename__ = "project_pr_campaigns"

    campaign_id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(String(255), nullable=True)  # GitHub login of the user who opened the campaign
    created_at = Column(DateTime, default=func.now())


class ProjectPullRequest(Base):
    """Pull requests table for tracking PRs created by Actions Manager"""
    __tablename__ = "project_pull_requests"

    pr_id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False, index=True)
    # Campaign this PR row belongs to. Nullable so legacy rows created before
    # campaign tracking remain valid (they are grouped heuristically instead).
    campaign_id = Column(Integer, ForeignKey("project_pr_campaigns.campaign_id", ondelete="SET NULL"), nullable=True, index=True)
    repo_name = Column(String(255), nullable=False)  # Full repository name (owner/repo)
    pr_number = Column(Integer, nullable=False)  # GitHub PR number
    pr_url = Column(String(500), nullable=False)  # GitHub PR URL
    pr_state = Column(String(20), nullable=False, default="open")  # PR state: open, merged, closed
    branch_name = Column(String(255), nullable=False)  # Actions Manager branch name
    target_branch = Column(String(255), nullable=False)  # Target/base branch name
    # Extended fields for PR history display
    title = Column(String(500), nullable=True)  # PR title from GitHub
    author = Column(String(255), nullable=True)  # PR author login from GitHub
    body = Column(String, nullable=True)  # PR description/body from GitHub
    merged_at = Column(DateTime, nullable=True)  # When the PR was merged
    closed_at = Column(DateTime, nullable=True)  # When the PR was closed (without merge)
    workflow_names = Column(String, nullable=True)  # Comma-separated list of associated workflow names
    file_names = Column(String, nullable=True)  # Comma-separated list of custom file paths + CODEOWNERS committed in this PR
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Add composite unique constraint to prevent duplicate entries
    __table_args__ = (UniqueConstraint('project_id', 'repo_name', 'branch_name', 'target_branch', 
                                       name='uq_project_pr_branch_target'),)


class MarketplaceWebhookEvent(Base):
    """GitHub Marketplace webhook events table for auditing and troubleshooting"""
    __tablename__ = "marketplace_webhook_events"

    event_id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)  # purchased, cancelled, pending_change, etc.
    action = Column(String(50), nullable=True, index=True)  # changed, cancelled, pending_change, pending_cancelled
    github_user = Column(String(255), nullable=True, index=True)  # Associated GitHub user
    marketplace_account_id = Column(Integer, nullable=True)  # GitHub Marketplace account ID
    plan_name = Column(String(50), nullable=True)  # Plan name from webhook
    effective_date = Column(DateTime, nullable=True)  # When the plan change takes effect
    payload = Column(String, nullable=False)  # Full webhook payload as JSON string
    signature = Column(String(255), nullable=True)  # Webhook signature for verification
    processed = Column(Boolean, default=False, nullable=False)  # Processing status
    processing_error = Column(String(500), nullable=True)  # Error message if processing failed
    retry_count = Column(Integer, default=0, nullable=False)  # Number of retry attempts
    received_at = Column(DateTime, default=func.now(), nullable=False, index=True)  # When webhook was received
    processed_at = Column(DateTime, nullable=True)  # When webhook was successfully processed
    source_ip = Column(String(45), nullable=True)  # Source IP address (45 chars for IPv6)
    headers = Column(String, nullable=True)  # Request headers as JSON string


class ProjectSecret(Base):
    """
    Stores secret names (NOT values) for projects without prefix.
    Only used when project.use_prefix = False.
    Values remain secure in GitHub; only names are tracked locally.
    """
    __tablename__ = "project_secrets"

    secret_id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False, index=True)
    secret_name = Column(String(255), nullable=False)  # Secret name without prefix (e.g., "DATABASE_PASSWORD")
    created_at = Column(DateTime, default=func.now())

    # Ensure unique secret names per project
    __table_args__ = (UniqueConstraint('project_id', 'secret_name', name='uq_project_secret_name'),)


class ProjectEnvVar(Base):
    """
    Stores environment variable names (NOT values) for projects without prefix.
    Only used when project.use_prefix = False.
    Values remain in GitHub; only names are tracked locally.
    """
    __tablename__ = "project_env_vars"

    env_var_id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False, index=True)
    env_var_name = Column(String(255), nullable=False)  # Env var name without prefix (e.g., "DEBUG_MODE")
    created_at = Column(DateTime, default=func.now())

    # Ensure unique env var names per project
    __table_args__ = (UniqueConstraint('project_id', 'env_var_name', name='uq_project_env_var_name'),)


class ProjectMembership(Base):
    """
    Project-level access control for non-admin users.

    Grants a workspace member access to a specific project with a role:
      - project_editor: can edit workflows, create PRs, manage project config
      - project_viewer: read-only access to the project

    Admins bypass this table and have implicit full access to
    all projects.  This table is only consulted for read_only workspace members
    who need explicit per-project grants.

    Designed for future extensibility (e.g. teams, additional roles).
    """
    __tablename__ = "project_memberships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey(_FK_ACCOUNTS_USER_ID, ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False, index=True)
    project_role = Column(String(30), nullable=False, default="project_viewer")  # project_editor, project_viewer
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Each user can only have one membership per project
    __table_args__ = (
        UniqueConstraint('user_id', 'project_id', name='uq_user_project_membership'),
    )

    user = relationship("Account")
    project = relationship("Project")


class Codeowners(Base):
    """
    CODEOWNERS file management table.

    Stores the locally-managed CODEOWNERS content for a repository within a
    project, mirroring how workflows are tracked.  The ``git_hash`` field
    captures the GitHub blob SHA from the last successful sync so drift can
    be detected efficiently against the live GitHub copy.

    The ``status`` lifecycle mirrors the workflow status field:
        - ``new``                  – first save, never deployed
        - ``committed_locally``    – local edits not yet pushed to GitHub
        - ``under_review``         – PR opened against the target branch
        - ``synced_with_github``   – local content matches GitHub
    """
    __tablename__ = "codeowners"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False, index=True)
    repo_id = Column(Integer, ForeignKey(_FK_REPOS_REPO_ID, ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False, default="")
    file_path = Column(String(64), nullable=False, default=".github/CODEOWNERS")  # .github/CODEOWNERS or CODEOWNERS
    git_hash = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="new")
    last_modified_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Each repo within a project has at most one CODEOWNERS draft
    __table_args__ = (
        UniqueConstraint('project_id', 'repo_id', name='uq_codeowners_project_repo'),
    )


class CustomFile(Base):
    """
    Project-level custom file management table.

    Stores workflow-adjacent text files (scripts, config files, action
    definitions, etc.) that belong to a project and are deployed to every
    repository in that project alongside workflow YAML files.

    The ``file_status`` lifecycle mirrors the workflow status field:
        - ``new``                  – just created, never synced to GitHub
        - ``committed_locally``    – local edits not yet pushed to GitHub
        - ``under_review``         – included in an open PR Campaign
        - ``synced_with_github``   – content matches the GitHub target branch

    ``pending_delete`` marks a file for deletion on next PR/direct delivery.
    The row is hard-deleted after successful removal from GitHub.
    """
    __tablename__ = "custom_files"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False)
    display_name = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=False)
    file_content = Column(Text, nullable=False, default="")
    git_hash = Column(String(255), nullable=True)
    file_status = Column(String(30), nullable=False, default="new")
    pending_delete = Column(Boolean, nullable=False, default=False)
    last_modified_by = Column(String(255), nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('project_id', 'file_path', name='uq_custom_file_project_path'),
        Index('ix_custom_files_project_id', 'project_id'),
    )


class RepoWorkflowOverride(Base):
    """
    Per-repository workflow override.

    Allows a single repository within a project to use a different version of a
    project workflow than the shared project-level workflow.  This is the
    foundation of the scope-aware drift resolution flow: when a user resolves
    drift in a single repo, they can either (a) adopt the GitHub version into
    the project (and sync the other repos), (b) adopt locally only, or
    (c) create a per-repo override so this repo can intentionally diverge from
    the project default without re-triggering drift on every detection cycle.

    Drift detection consults this table first: if an override exists for
    (project, repo, workflow) the override's YAML/hash is compared against
    GitHub instead of the shared project workflow.

    A row in this table does NOT replace the underlying ``Workflow``; it simply
    captures a divergent expected content/hash for a single repo.  Removing
    the override row reverts the repo back to comparing against the shared
    project workflow.
    """
    __tablename__ = "repo_workflow_overrides"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False, index=True)
    repo_id = Column(Integer, ForeignKey(_FK_REPOS_REPO_ID, ondelete="CASCADE"), nullable=False, index=True)
    workflow_id = Column(Integer, ForeignKey(_FK_WORKFLOWS_WORKFLOW_ID, ondelete="CASCADE"), nullable=False, index=True)
    workflow_name = Column(String(255), nullable=False)  # Snapshot of the workflow_name at override creation
    workflow_yaml = Column(Text, nullable=False)  # Repo-specific expected YAML
    workflow_git_hash = Column(String(255), nullable=True)  # Last-known GitHub SHA for this override
    source_repo_name = Column(String(255), nullable=True)  # Repo that originally provided the override content
    last_modified_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # One override per (project, repo, workflow)
    __table_args__ = (
        UniqueConstraint('project_id', 'repo_id', 'workflow_id', name='uq_repo_workflow_override'),
    )


class LinkedReusableWorkflow(Base):
    """
    Links a specific reusable workflow from an RWX project into a standard project.
    Tracks which standard project is using which workflow from which RWX source project.
    """
    __tablename__ = "linked_reusable_workflows"

    id = Column(Integer, primary_key=True, index=True)
    standard_project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False, index=True)
    rwx_project_id = Column(Integer, ForeignKey(_FK_PROJECTS_PROJECT_ID, ondelete="CASCADE"), nullable=False)
    workflow_id = Column(Integer, ForeignKey(_FK_WORKFLOWS_WORKFLOW_ID, ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # Ensure a workflow is only linked once per standard project
    __table_args__ = (
        UniqueConstraint('standard_project_id', 'workflow_id', name='unique_standard_workflow'),
    )
