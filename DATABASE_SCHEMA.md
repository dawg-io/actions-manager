## Database Schema

This document describes the database schema for ActionsManager, including all tables, columns, relationships, and behavioral notes for developers and contributors.

### Table of Contents

- [Core Tables](#core-tables)
- [Membership & Access Control Tables](#membership--access-control-tables)
- [PR & Delivery Tables](#pr--delivery-tables)
- [Drift & Override Tables](#drift--override-tables)
- [Marketplace Billing Tables](#marketplace-billing-tables)
- [Junction Tables](#junction-tables)
- [Relationships](#relationships)
- [Workflow & PR State Behavior](#workflow--pr-state-behavior)
- [Drift Detection Model](#drift-detection-model)
- [GitHub Data Mapping](#github-data-mapping)
- [Database Migrations](#database-migrations)
- [GitHub Credential Resolution](#github-credential-resolution)
- [Account Tiers & Feature Limits](#account-tiers--feature-limits)

---

### Core Tables

#### accounts
User accounts table with GitHub OAuth integration, optional encrypted personal access token storage, and marketplace billing metadata.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `user_id` | INTEGER | No | Primary key, auto-increment |
| `github_user` | VARCHAR(255) | No | GitHub username (unique) |
| `github_email` | VARCHAR(255) | No | GitHub email address (unique) |
| `account_type` | VARCHAR(50) | No | Account tier: `free`, `professional`, `enterprise` |
| `github_account_type` | VARCHAR(20) | Yes | OAuth account type: `User` or `Organization` |
| `connected_github_account` | VARCHAR(255) | Yes | GitHub App installation account login |
| `connected_github_account_type` | VARCHAR(20) | Yes | GitHub App installation account type: `User` or `Organization` |
| `avatar_url` | VARCHAR | Yes | GitHub profile avatar URL |
| `last_login_at` | TIMESTAMP | Yes | Last login timestamp |
| `last_login_ip` | VARCHAR(45) | Yes | Last login IP address (supports IPv6) |
| `github_api_calls` | INTEGER | No | Total GitHub API calls made by this user (default: 0) |
| `github_api_calls_today` | INTEGER | No | API calls in last 24 hours (default: 0) |
| `api_calls_reset_at` | TIMESTAMP | Yes | Timestamp of last daily counter reset |
| `marketplace_account_id` | INTEGER | Yes | GitHub Marketplace account ID |
| `marketplace_plan` | VARCHAR(50) | Yes | Current marketplace plan name |
| `marketplace_unit_count` | INTEGER | Yes | Number of units purchased |
| `marketplace_on_free_trial` | BOOLEAN | No | Free trial status (default: false) |
| `marketplace_next_billing_date` | TIMESTAMP | Yes | Next billing date |
| `marketplace_updated_at` | TIMESTAMP | Yes | Last marketplace update timestamp |
| `admin_override` | BOOLEAN | No | Whether tier is manually overridden by admin (default: false) |
| `admin_override_until` | TIMESTAMP | Yes | When admin override expires (NULL = indefinite) |
| `github_permission_status` | VARCHAR(50) | Yes | Permission validation status: `valid`, `missing_scopes`, etc. |
| `github_permission_checked_at` | TIMESTAMP | Yes | Last time GitHub permissions were validated |
| `github_pat_token_encrypted` | TEXT | Yes | Encrypted saved GitHub PAT / alternate token; never returned to the frontend after save |
| `github_pat_token_type` | VARCHAR(50) | Yes | Saved token type: `oauth_token`, `classic_pat`, or `fine_grained_pat` |
| `github_pat_status` | VARCHAR(50) | Yes | Last PAT validation status shown in the UI |
| `github_pat_last_error` | TEXT | Yes | Last PAT validation / troubleshooting message |
| `github_pat_checked_at` | TIMESTAMP | Yes | Last time the saved PAT was validated |
| `github_pat_updated_at` | TIMESTAMP | Yes | Last time the saved PAT was added or replaced |

**Indexes**:
- Primary key on `user_id`
- Unique index on `github_user`
- Unique index on `github_email`
- Index on `marketplace_account_id`

**Notes on `github_account_type`**:
- Set during OAuth login or PAT-based sign-in from the GitHub API response.
- `User` - personal GitHub account; repo access is scoped to the authenticated user.
- `Organization` - org-level account; repo access may span multiple org members.
- `connected_github_account` / `connected_github_account_type` track a separately-installed GitHub App, which can differ from the OAuth account.
- `github_pat_*` columns store only encrypted PAT material plus validation metadata; the UI receives masked status such as "configured" or "invalid/expired", never the raw token.

---

#### projects
Projects table for organizing repositories and workflows.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `project_id` | INTEGER | No | Primary key, auto-increment |
| `project_code` | VARCHAR(10) | No | Unique project code (e.g., "DEMO", "PROD"), auto-generated from name |
| `project_name` | VARCHAR(255) | No | Project display name |
| `user_id` | INTEGER | No | Foreign key to accounts.user_id (CASCADE DELETE) |
| `branch_regex` | VARCHAR(255) | Yes | Branch regex pattern for filtering (used when `branch_option = "pattern"`) |
| `branch_option` | VARCHAR(50) | Yes | Branch selection mode: `default`, `pattern` (default: `"default"`) |
| `branch_max_age_days` | INTEGER | Yes | Filter branches by recency in days (1-30, default: 30) |
| `reusable_workflows_enabled` | BOOLEAN | No | Per-project reusable workflow feature flag (default: false) |
| `use_prefix` | BOOLEAN | No | Whether to prefix resources with `AM_{PROJECT_CODE}_` (default: true) |
| `pr_state` | VARCHAR(20) | No | Project lifecycle state: `new`, `draft`, `open`, `synced` (default: `new`) |
| `project_type` | VARCHAR(20) | No | Project type: `standard` (Caller Workflow Project — consumer) or `rwx` (Reusable Workflow Project — producer). Column default is `"standard"`. The value `standard` is the internal/legacy identifier; the user interface displays it as **Caller Workflow Project**. |
| `repository_visibility_scope` | VARCHAR(10) | No | Repository visibility scope for the project: `public` or `private` (default: `"public"`). A "mixed" option is intentionally not supported — projects are public-only or private-only. In self-hosted beta, private repositories are allowed when GitHub credentials have access. On cloud, Free tier accounts may only create `public` projects. Existing projects created before this column existed default to `public`. |
| `validation_repo_id` | INTEGER | Yes | Optional foreign key to repos.repo_id for the safe validation repository used by preflight runs |
| `preflight_required` | BOOLEAN | No | Whether a successful validation preflight is required before PR campaign creation (default: false) |
| `last_preflight_status` | VARCHAR(40) | Yes | Latest validation preflight status, such as `not_run`, `running`, `passed`, or `failed` |
| `last_preflight_run_at` | TIMESTAMP | Yes | Timestamp of the most recent validation preflight attempt |
| `last_preflight_error` | VARCHAR(500) | Yes | Sanitized summary of the most recent validation preflight failure |
| `last_preflight_pr_url` | VARCHAR(500) | Yes | Pull request URL created in the validation repository by the most recent preflight run |
| `last_preflight_content_hash` | VARCHAR(64) | Yes | Content hash the most recent preflight ran against |
| `drift_status` | VARCHAR(20) | No | Cached project-level drift result: `unknown`, `clean`, `drifted`, `check_failed` (default: `unknown`) |
| `drift_count` | INTEGER | No | Number of drifted (workflow, repo, branch) combinations at the last check (default: 0) |
| `last_drift_check_at` | TIMESTAMP | Yes | When the last drift check completed. Never advanced by a skipped check |
| `drift_error_summary` | VARCHAR(500) | Yes | Why the last check failed, or why the project is being skipped by the sweep |
| `drift_check_failure_count` | INTEGER | No | Consecutive `check_failed` results, driving the sweep's exponential backoff; reset on `clean`/`drifted` (default: 0) |
| `drift_check_interval_minutes` | INTEGER | Yes | Per-project sweep schedule. `NULL` inherits the workspace default, `0` disables automatic checks, otherwise minutes between checks |
| `last_run_sync_at` | TIMESTAMP | Yes | Build-metrics sync cursor, kept here so a project with no runs yet doesn't re-hit GitHub on every panel open |
| `last_modified_by` | VARCHAR(255) | Yes | GitHub username of the last user to modify this project |
| `created_at` | TIMESTAMP | No | Project creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Indexes**:
- Primary key on `project_id`
- Unique index on `project_code`
- Foreign key on `user_id` → `accounts.user_id`
- Foreign key on `validation_repo_id` → `repos.repo_id` (SET NULL)

---

#### repos
GitHub repositories table. Acts as a lightweight cache of repository identity.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `repo_id` | INTEGER | No | Primary key, auto-increment |
| `repo_name` | VARCHAR(255) | No | Repository full name (unique, e.g., `"owner/repo"`) |

**Indexes**:
- Primary key on `repo_id`
- Unique index on `repo_name`

---

#### workflows
GitHub Actions workflow definitions managed by Actions Manager.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `workflow_id` | INTEGER | No | Primary key, auto-increment |
| `workflow_name` | VARCHAR(255) | No | Workflow display name (file name without `.yml`) |
| `workflow_yaml` | VARCHAR | No | Workflow YAML content (current local version), stored as a variable-length string in the backend schema |
| `workflow_git_hash` | VARCHAR(255) | Yes | GitHub blob SHA from last successful sync; `null` or `"0000...0"` means never synced |
| `workflow_status` | VARCHAR(30) | No | Lifecycle status: `new`, `committed_locally`, `under_review`, `synced_with_github` (default: `"new"`) |
| `reusable_workflow` | BOOLEAN | No | Whether this is a reusable workflow (default: false) |
| `last_modified_by` | VARCHAR(255) | Yes | GitHub username of the last user to edit this workflow |
| `created_at` | TIMESTAMP | No | Workflow creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Indexes**:
- Primary key on `workflow_id`

**Notes**:
- Multiple workflows with the same `workflow_name` can exist across different projects.
- `workflow_git_hash` is set to the PR-branch SHA after a PR is created and to the target-branch SHA after a successful sync. It is reset to `"0000...0"` on local edits.

---

#### workflow_versions
Version history for workflow YAML content. A new row is appended each time a workflow is saved.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `version_id` | INTEGER | No | Primary key, auto-increment |
| `workflow_id` | INTEGER | No | Foreign key to workflows.workflow_id (CASCADE DELETE) |
| `version_number` | INTEGER | No | Auto-incremented version number per workflow |
| `content` | TEXT | No | Workflow YAML content at this version |
| `version_metadata` | TEXT | Yes | JSON metadata: author, session info, etc. |
| `created_at` | TIMESTAMP | No | When this version was saved |

**Constraints**:
- Unique constraint on (`workflow_id`, `version_number`)

**Indexes**:
- Primary key on `version_id`
- Index on `workflow_id`

---

#### rulesets
GitHub repository rulesets table.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `ruleset_id` | INTEGER | No | Primary key, auto-increment |
| `ruleset_name` | VARCHAR(255) | No | Ruleset display name |
| `ruleset_json` | TEXT | No | Ruleset JSON configuration |
| `description` | VARCHAR(500) | Yes | Ruleset description |
| `user_id` | INTEGER | No | Foreign key to accounts.user_id (CASCADE DELETE) |
| `created_at` | TIMESTAMP | No | Ruleset creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Indexes**:
- Primary key on `ruleset_id`
- Foreign key on `user_id` → `accounts.user_id`

---

### Membership & Access Control Tables

#### workspace_members
Workspace/application-level membership for multi-user support.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Primary key, auto-increment |
| `user_id` | INTEGER | No | Foreign key to accounts.user_id (CASCADE DELETE), unique |
| `workspace_role` | VARCHAR(20) | No | Role: `admin`, `member`, `read_only` (default: `"read_only"`) |
| `created_at` | TIMESTAMP | No | Membership creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Indexes**:
- Primary key on `id`
- Unique index on `user_id`

**Role Descriptions**:
- `admin` — Full management access; bypasses all project-level permission checks.
- `member` — Standard user; requires explicit `project_memberships` grants for project access and can view and edit assigned projects.
- `read_only` — View-only role; requires explicit `project_memberships` grants for project access.

---

#### project_memberships
Project-level access control for non-admin workspace members.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Primary key, auto-increment |
| `user_id` | INTEGER | No | Foreign key to accounts.user_id (CASCADE DELETE) |
| `project_id` | INTEGER | No | Foreign key to projects.project_id (CASCADE DELETE) |
| `project_role` | VARCHAR(30) | No | Project role: `project_editor`, `project_viewer` (default: `"project_viewer"`) |
| `created_at` | TIMESTAMP | No | Assignment creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Constraints**:
- Unique constraint on (`user_id`, `project_id`)

**Indexes**:
- Primary key on `id`
- Index on `user_id`
- Index on `project_id`
- Foreign key on `user_id` → `accounts.user_id`
- Foreign key on `project_id` → `projects.project_id`

**Role Descriptions**:
- `project_editor` — Can edit workflows, create PRs, and manage project configuration.
- `project_viewer` — Read-only access to the project.

**Notes**:
- `admin` workspace members bypass this table and have implicit full access to all projects.
- All non-admin workspace members require explicit rows here to gain access to projects they do not own.

---

### PR & Delivery Tables

#### project_pull_requests
Tracks pull requests created by Actions Manager for workflow delivery.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `pr_id` | INTEGER | No | Primary key, auto-increment |
| `project_id` | INTEGER | No | Foreign key to projects.project_id (CASCADE DELETE) |
| `repo_name` | VARCHAR(255) | No | Full repository name (`owner/repo`) |
| `pr_number` | INTEGER | No | GitHub PR number |
| `pr_url` | VARCHAR(500) | No | GitHub PR URL |
| `pr_state` | VARCHAR(20) | No | PR state: `open`, `merged`, `closed` (default: `"open"`) |
| `branch_name` | VARCHAR(255) | No | Actions Manager source branch (`actions-manager/{code}/{repo_slug}/{id}-{base}`) |
| `target_branch` | VARCHAR(255) | No | Target/base branch name |
| `title` | VARCHAR(500) | Yes | PR title from GitHub |
| `author` | VARCHAR(255) | Yes | PR author login from GitHub |
| `body` | TEXT | Yes | PR description/body from GitHub |
| `workflow_names` | TEXT | Yes | Comma-and-space separated list of associated workflow names (e.g., `"ci, deploy"`) |
| `merged_at` | TIMESTAMP | Yes | When the PR was merged |
| `closed_at` | TIMESTAMP | Yes | When the PR was closed without merging |
| `created_at` | TIMESTAMP | No | Row creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Constraints**:
- Unique constraint on (`project_id`, `repo_name`, `branch_name`, `target_branch`)

**Indexes**:
- Primary key on `pr_id`
- Index on `project_id`

**Notes**:
- One PR row is created per repository when a project sync is triggered via PR delivery mode.
- Branch naming format: `actions-manager/{project_code}/{repo_slug}/{8-char-hex}-{base_branch}`. Each PR creates a new unique branch; branches are never reused and are deleted after a successful merge.
- `workflow_names` consumers must strip whitespace when splitting by `","`.

---

#### project_secrets
Tracks secret *names* (not values) for projects that disable the resource prefix (`use_prefix = false`).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `secret_id` | INTEGER | No | Primary key, auto-increment |
| `project_id` | INTEGER | No | Foreign key to projects.project_id (CASCADE DELETE) |
| `secret_name` | VARCHAR(255) | No | Secret name without the `AM_` prefix (e.g., `"DATABASE_PASSWORD"`) |
| `created_at` | TIMESTAMP | No | Row creation timestamp |

**Constraints**:
- Unique constraint on (`project_id`, `secret_name`)

**Indexes**:
- Primary key on `secret_id`
- Index on `project_id`

**Notes**:
- Secret *values* are never stored locally; they live exclusively in GitHub.
- Only populated when `projects.use_prefix = false`.

---

#### project_env_vars
Tracks environment variable *names* (not values) for projects that disable the resource prefix.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `env_var_id` | INTEGER | No | Primary key, auto-increment |
| `project_id` | INTEGER | No | Foreign key to projects.project_id (CASCADE DELETE) |
| `env_var_name` | VARCHAR(255) | No | Env var name without the `AM_` prefix (e.g., `"DEBUG_MODE"`) |
| `created_at` | TIMESTAMP | No | Row creation timestamp |

**Constraints**:
- Unique constraint on (`project_id`, `env_var_name`)

**Indexes**:
- Primary key on `env_var_id`
- Index on `project_id`

---

### Drift & Override Tables

#### drift_settings
Single-row table holding the workspace-wide defaults for the background drift sweep, edited by workspace admins under **Drift Settings**. Replaces the former `DRIFT_*` environment variables. Absence of the row means "use the built-in defaults", so an installation that has never opened the settings page behaves exactly as it did when the defaults lived in code.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `settings_id` | INTEGER | No | Primary key, auto-increment |
| `sweep_enabled` | BOOLEAN | No | Master switch for automatic drift checking (default: true) |
| `recheck_interval_minutes` | INTEGER | No | Default minutes before a project is due again, for projects that don't override it (default: 15) |
| `batch_size` | INTEGER | No | Projects checked per tick, capping burst API usage (default: 5) |
| `poll_interval_seconds` | INTEGER | No | How often the worker wakes to look for due projects (default: 60) |
| `updated_at` | TIMESTAMP | Yes | Last update timestamp |

**Indexes**:
- Primary key on `settings_id`

**Notes**:
- Read fresh on every sweep tick, so changes take effect without a restart.
- Per-project overrides live on `projects.drift_check_interval_minutes`; this table only supplies the default they inherit.

---

#### codeowners
Locally-managed CODEOWNERS file content for a repository within a project. Tracks sync state using a GitHub blob SHA, mirroring the workflow drift model.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Primary key, auto-increment |
| `project_id` | INTEGER | No | Foreign key to projects.project_id (CASCADE DELETE) |
| `repo_id` | INTEGER | No | Foreign key to repos.repo_id (CASCADE DELETE) |
| `content` | TEXT | No | CODEOWNERS file content (default: `""`) |
| `file_path` | VARCHAR(64) | No | File path: `.github/CODEOWNERS` or `CODEOWNERS` (default: `".github/CODEOWNERS"`) |
| `git_hash` | VARCHAR(255) | Yes | GitHub blob SHA from last successful sync |
| `status` | VARCHAR(30) | No | Sync status: `new`, `committed_locally`, `under_review`, `synced_with_github` (default: `"new"`) |
| `last_modified_by` | VARCHAR(255) | Yes | GitHub username of last editor |
| `created_at` | TIMESTAMP | No | Row creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Constraints**:
- Unique constraint on (`project_id`, `repo_id`) — one CODEOWNERS draft per repo per project

**Indexes**:
- Primary key on `id`
- Index on `project_id`
- Index on `repo_id`

---

#### repo_workflow_overrides
Per-repository workflow override. Allows a single repository within a project to track a different expected version of a workflow, without changing the shared project-level workflow definition.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Primary key, auto-increment |
| `project_id` | INTEGER | No | Foreign key to projects.project_id (CASCADE DELETE) |
| `repo_id` | INTEGER | No | Foreign key to repos.repo_id (CASCADE DELETE) |
| `workflow_id` | INTEGER | No | Foreign key to workflows.workflow_id (CASCADE DELETE) |
| `workflow_name` | VARCHAR(255) | No | Snapshot of the workflow name at override creation |
| `workflow_yaml` | TEXT | No | Repo-specific expected YAML content |
| `workflow_git_hash` | VARCHAR(255) | Yes | Last-known GitHub SHA for this override |
| `source_repo_name` | VARCHAR(255) | Yes | Repository that originally provided the override content |
| `last_modified_by` | VARCHAR(255) | Yes | GitHub username of last editor |
| `created_at` | TIMESTAMP | No | Row creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Constraints**:
- Unique constraint on (`project_id`, `repo_id`, `workflow_id`)

**Indexes**:
- Primary key on `id`
- Index on `project_id`
- Index on `repo_id`
- Index on `workflow_id`

**Notes**:
- Drift detection checks this table first: if a row exists for `(project_id, repo_id, workflow_id)`, the override YAML/hash is compared against GitHub instead of the shared project workflow.
- Deleting an override row reverts the repo to comparing against the shared project workflow.

---

#### linked_reusable_workflows
Links a reusable workflow from an `rwx` project (Reusable Workflow Project) into a `standard` project (Caller Workflow Project).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Primary key, auto-increment |
| `standard_project_id` | INTEGER | No | Foreign key to projects.project_id (CASCADE DELETE) — the consuming project (Caller Workflow Project; `project_type = "standard"`) |
| `rwx_project_id` | INTEGER | No | Foreign key to projects.project_id — the source RWX project (Reusable Workflow Project; `project_type = "rwx"`) |
| `workflow_id` | INTEGER | No | Foreign key to workflows.workflow_id (CASCADE DELETE) |
| `created_at` | TIMESTAMP | No | Row creation timestamp |

**Constraints**:
- Unique constraint on (`standard_project_id`, `workflow_id`) — a workflow is only linked once per consuming project

**Indexes**:
- Primary key on `id`
- Index on `standard_project_id`

---

### Marketplace Billing Tables

#### marketplace_webhook_events
GitHub Marketplace webhook events table for auditing and troubleshooting.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `event_id` | INTEGER | No | Primary key, auto-increment |
| `event_type` | VARCHAR(100) | No | Type of webhook event (e.g., `marketplace_purchase`) |
| `action` | VARCHAR(50) | Yes | Action: `purchased`, `cancelled`, `changed`, `pending_change`, etc. |
| `github_user` | VARCHAR(255) | Yes | GitHub username from webhook |
| `marketplace_account_id` | INTEGER | Yes | GitHub Marketplace account ID |
| `plan_name` | VARCHAR(50) | Yes | Plan name: `free`, `professional`, `enterprise` |
| `effective_date` | TIMESTAMP | Yes | When the plan change takes effect (for pending changes) |
| `payload` | TEXT | No | Full webhook payload as JSON string |
| `signature` | VARCHAR(255) | Yes | Webhook signature for verification (`sha256=...`) |
| `source_ip` | VARCHAR(45) | Yes | Source IP address (supports IPv6) |
| `headers` | TEXT | Yes | Request headers as JSON string |
| `processed` | BOOLEAN | No | Processing status (default: false) |
| `processing_error` | VARCHAR(500) | Yes | Error message if processing failed |
| `retry_count` | INTEGER | No | Number of retry attempts (default: 0) |
| `received_at` | TIMESTAMP | No | When webhook was received (auto-set) |
| `processed_at` | TIMESTAMP | Yes | When webhook was successfully processed |

**Indexes**:
- Primary key on `event_id`
- Index on `event_type`
- Index on `action`
- Index on `github_user`
- Index on `received_at`

**Purpose**:
- Complete audit trail for all marketplace billing events
- Enables troubleshooting of failed webhook processing
- Supports retry logic for transient failures

---

### Junction Tables

#### project_repos
Many-to-many relationship between projects and repositories, with optional per-repository branch configuration overrides.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `project_id` | INTEGER | No | Primary key, foreign key to projects.project_id (CASCADE DELETE) |
| `repo_id` | INTEGER | No | Primary key, foreign key to repos.repo_id (CASCADE DELETE) |
| `branch_config_mode` | VARCHAR(20) | No | `"inherit"` uses project-level branch settings; `"override"` uses the columns below (default: `"inherit"`) |
| `branch_option` | VARCHAR(50) | Yes | Override for branch selection mode: `"default"` or `"pattern"` |
| `branch_regex` | VARCHAR(255) | Yes | Override for branch regex pattern |
| `branch_max_age_days` | INTEGER | Yes | Override for branch recency filter (1-30 days) |

**Indexes**:
- Primary key on (`project_id`, `repo_id`)
- Foreign key on `project_id` → `projects.project_id`
- Foreign key on `repo_id` → `repos.repo_id`

**Notes**:
- Override columns are nullable, so after the migration adds these columns, existing rows continue to inherit project settings by default via `NULL` override values and `branch_config_mode = "inherit"`.

---

#### project_workflows
Many-to-many relationship between projects and workflows.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `project_id` | INTEGER | No | Primary key, foreign key to projects.project_id (CASCADE DELETE) |
| `workflow_id` | INTEGER | No | Primary key, foreign key to workflows.workflow_id (CASCADE DELETE) |

**Indexes**:
- Primary key on (`project_id`, `workflow_id`)
- Foreign key on `project_id` → `projects.project_id`
- Foreign key on `workflow_id` → `workflows.workflow_id`

---

#### project_rulesets
Many-to-many relationship between projects and rulesets.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `project_id` | INTEGER | No | Primary key, foreign key to projects.project_id (CASCADE DELETE) |
| `ruleset_id` | INTEGER | No | Primary key, foreign key to rulesets.ruleset_id (CASCADE DELETE) |

**Indexes**:
- Primary key on (`project_id`, `ruleset_id`)
- Foreign key on `project_id` → `projects.project_id`
- Foreign key on `ruleset_id` → `rulesets.ruleset_id`

---

### Relationships

```
accounts (1) ──────────< (0/1) workspace_members   [role: admin | member | read_only]
accounts (1) ──────────< (N) projects
accounts (1) ──────────< (N) rulesets
accounts (1) ──────────< (N) marketplace_webhook_events   (via github_user)

projects (1) ──────────< (N) project_repos >──────────── (N) repos
projects (1) ──────────< (N) project_workflows >──────── (N) workflows
projects (1) ──────────< (N) project_rulesets >────────── (N) rulesets
projects (1) ──────────< (N) project_pull_requests
projects (1) ──────────< (N) project_memberships >──────── (N) accounts
projects (1) ──────────< (N) project_secrets
projects (1) ──────────< (N) project_env_vars
projects (1) ──────────< (N) codeowners          (one per repo per project)
projects (1) ──────────< (N) repo_workflow_overrides
projects [rwx] (1) ────< (N) linked_reusable_workflows >── projects [standard]
                   Reusable Workflow Project          Caller Workflow Project

workflows (1) ─────────< (N) workflow_versions
workflows (1) ──── (overrides) repo_workflow_overrides
```

**Key Relationships**:
- Each **account** has at most one **workspace_member** row (role assignment).
- Each **account** can own multiple **projects**.
- Each **project** links to multiple **repos** (many-to-many via `project_repos`).
- Each **project** links to multiple **workflows** (many-to-many via `project_workflows`).
- Each **project** links to multiple **rulesets** (many-to-many via `project_rulesets`).
- Each **project** tracks its open/merged/closed **pull requests** via `project_pull_requests`.
- Each **project** grants access to workspace members via `project_memberships`.
- Each **workflow** keeps a full edit history in `workflow_versions`.
- **Drift overrides**: a `repo_workflow_overrides` row lets one repo within a project diverge from the shared workflow definition without affecting other repos.
- **Reusable Workflow Projects** (`project_type = "rwx"`) share workflows into Caller Workflow Projects (`project_type = "standard"`) via `linked_reusable_workflows`. The value `standard` is the internal/legacy identifier; the user interface displays these projects as **Caller Workflow Projects**.

---

### Workflow & PR State Behavior

#### Workflow Lifecycle (`workflow_status`)

Each `workflows` row progresses through the following states:

```
new  →  committed_locally  →  under_review  →  synced_with_github
 ↑                                                      │
 └──────────────── (local edit resets) ─────────────────┘
```

| Status | Meaning |
|--------|---------|
| `new` | Workflow saved for the first time; `workflow_git_hash` is null or `"0000...0"` |
| `committed_locally` | Workflow edited locally; `workflow_git_hash` reset to `"0000...0"`; not yet pushed to GitHub |
| `under_review` | A PR has been opened against the target branch; `workflow_git_hash` holds the PR-branch blob SHA |
| `synced_with_github` | Local YAML matches the target branch on GitHub; `workflow_git_hash` holds the target-branch blob SHA |

#### Project Lifecycle (`projects.pr_state`)

The project-level `pr_state` field summarises the overall delivery status across all workflows and repos in the project:

```
new  →  draft  →  open  →  synced
```

| State | Meaning |
|-------|---------|
| `new` | Project created; no workflows saved or PRs opened |
| `draft` | Workflows have been created/edited locally but not yet pushed |
| `open` | At least one PR is open in GitHub for this project |
| `synced` | All workflows are in sync with their target branches; no open PRs |

#### PR State (`project_pull_requests.pr_state`)

Each row in `project_pull_requests` tracks the GitHub PR lifecycle:

| State | Meaning |
|-------|---------|
| `open` | PR is open on GitHub |
| `merged` | PR was merged; `merged_at` is set |
| `closed` | PR was closed without merging; `closed_at` is set |

---

### Drift Detection Model

Drift detection compares the locally-stored workflow YAML/hash against what currently exists on the target branch in GitHub.

#### How `workflow_git_hash` Works

- **`null` or `"0000...0"` with no open PR**: Workflow has never been synced and has no open PR. Drift detection returns `None` for this workflow — it drops out of drift results entirely.
- **`null` or `"0000...0"` with an open PR**: Workflow has never been synced but a PR already exists. Drift detection surfaces this as `new_open_pr` (not skipped, not classified as drift).
- **PR-branch SHA**: Set after a PR is created (`workflow_status = "under_review"`). The hash points to the PR branch, not the target branch. Drift is checked against the target branch; workflows with open PRs are classified as `under_review` (not drifted).
- **Target-branch SHA**: Set after a successful sync (`workflow_status = "synced_with_github"`). On subsequent drift checks, this SHA is compared to the current GitHub blob SHA. A mismatch means drift.

#### Drift Detection Flow

```
1. For each workflow in the project:
   a. If workflow_git_hash is null/"0000...0" AND no open PR → drop from results (None)
   b. If workflow_git_hash is null/"0000...0" AND an open PR exists → classify as new_open_pr
   c. Fetch current blob SHA from the target branch on GitHub
   d. If blob not found on target branch → check for open PR (under_review) or flag as deleted
   e. If open PR exists (any hash) → classify as under_review (no drift)
   f. If SHA matches stored hash → no drift
   g. If SHA differs → drift detected; surface to user for resolution
2. Per-repo override check (repo_workflow_overrides):
   - If an override row exists for (project_id, repo_id, workflow_id),
     compare the override YAML/hash instead of the shared project workflow
```

#### Drift Resolution Options

When drift is detected, the user can resolve it in three ways:

| Option | Effect |
|--------|--------|
| `adopt_project_and_sync` | Updates the shared project workflow with the GitHub version and opens sync PRs for other repos |
| `adopt_local_only` | Accepts the GitHub version for this repo only without updating the project workflow |
| `create_repo_override` | Creates a `repo_workflow_overrides` row so this repo intentionally diverges from the project default |

#### What Is Stored vs. Computed

| Data | Stored | Computed at runtime |
|------|--------|---------------------|
| Workflow YAML | `workflows.workflow_yaml` | — |
| Last-known GitHub SHA | `workflows.workflow_git_hash` | — |
| Per-repo override YAML/hash | `repo_workflow_overrides` | — |
| Current GitHub SHA | — | Fetched via GitHub API |
| Drift status | — | Derived by comparing stored vs. live SHA |
| PR open/merged/closed | `project_pull_requests.pr_state` | Kept in sync via API calls |

---

### GitHub Data Mapping

Actions Manager maintains a partial cache of GitHub data. The table below shows what is persisted locally and what is fetched live.

| Data | Persisted locally | Fetched live from GitHub |
|------|-------------------|--------------------------|
| Repository full name (`owner/repo`) | `repos.repo_name` | — |
| Repository metadata (description, visibility, stars) | — | Yes |
| Workflow file name | `workflows.workflow_name` | — |
| Workflow YAML content | `workflows.workflow_yaml` | Yes (for drift comparison) |
| Workflow blob SHA | `workflows.workflow_git_hash` | Yes (for drift comparison) |
| PR number, URL, state | `project_pull_requests` | Yes (to keep state in sync) |
| PR title, author, body | `project_pull_requests` | Yes (enriched after creation) |
| Branch list for a repo | — | Yes |
| Secret names (no-prefix mode) | `project_secrets` | — |
| Secret values | **Never** | Yes (write-only to GitHub) |
| Env var names (no-prefix mode) | `project_env_vars` | — |
| Env var values | — | Yes |
| CODEOWNERS content | `codeowners.content` | Yes (for drift comparison) |
| GitHub user profile / avatar | `accounts` (partial) | Yes |

**Design rationale**: Repos and workflows are cached by identity (name) to avoid repeated API calls for list operations. Full metadata is always fetched live to avoid stale data. Secret and environment variable values are never persisted to the local database.

---

### Database Migrations

Run the master migration script to apply all pending migrations in order:

```bash
cd backend
python run_migrations.py
```

Migrations support both SQLite (self-hosted) and PostgreSQL (cloud) and are safe to run multiple times.

Recent migrations:

- `migrate_add_github_pat_fields.py` — adds encrypted PAT storage, token type, validation status, and timestamp columns to `accounts`
- `migrate_add_validation_preflight.py` — adds validation repository and preflight status columns to `projects`

See [backend/MIGRATIONS.md](./backend/MIGRATIONS.md) for the full list of available migrations and troubleshooting guidance.

---

### GitHub Credential Resolution

For GitHub API operations, Actions Manager resolves credentials in this order:

1. Use the saved encrypted PAT when one is configured
2. Fall back to the in-memory OAuth token when no PAT is configured
3. Return an authentication error when neither credential is available

Saved PAT validation status is tracked in the `accounts` table so the UI can show masked states such as configured, invalid/expired, or missing permissions without exposing the token value.

---

### Account Tiers & Feature Limits

> **Beta note:** Paid plans are not currently available. During the self-hosted beta, all users share the same beta limits regardless of the stored `account_type` value (see below). The tier table is retained for internal/future reference.

**Self-Hosted Beta Limits (enforced when `INSTALLATION_MODE=self-hosted`):**

| Resource | Beta Limit |
|---|---|
| Caller Workflow Projects (`standard`) | 4 |
| Reusable Workflow Projects (`rwx`) | 2 |
| Secrets per project | 6 |
| Environment variables per project | 6 |
| GitHub deployment environments per project | 6 |
| Private repositories | ✅ Allowed |

**Future/Internal Tier Reference (not active during beta):**

Account tiers are defined in the `accounts.account_type` column:

| Tier | Max Projects | Private Repos | Secrets per Project | API Rate Limit |
|------|--------------|---------------|---------------------|----------------|
| `free` | 3 | No | 2 | 5,000/hour |
| `professional` | 10 | Yes | 10 | 5,000/hour |
| `enterprise` | Unlimited | Yes | Unlimited | 15,000/hour |

Account tiers are automatically updated via marketplace webhooks when users purchase, upgrade, downgrade, or cancel a plan. The `admin_override` flag allows admins to manually set a tier regardless of marketplace state.

See [MARKETPLACE_WEBHOOKS.md](./MARKETPLACE_WEBHOOKS.md) for detailed webhook integration documentation.
