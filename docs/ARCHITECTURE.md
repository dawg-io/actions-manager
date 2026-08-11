# Architecture Guide

This document provides a high-level overview of the Actions Manager architecture, key components, and design decisions.

## Table of Contents

- [System Overview](#system-overview)
- [Architecture Diagram](#architecture-diagram)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Technology Stack](#technology-stack)
- [Design Decisions](#design-decisions)
- [Security Architecture](#security-architecture)
- [Deployment Modes](#deployment-modes)

## System Overview

Actions Manager is a web application for managing GitHub Actions workflows across multiple repositories. It provides a centralized interface for creating, editing, and deploying CI/CD pipelines with features like GitHub OAuth authentication, personal access token authentication, build detection, drift detection, and secrets management.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Client Layer                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         React Frontend (Port 3000/8080)             │   │
│  │  • OAuth / PAT Auth  • Workflow Editor  • Project UI│   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/REST API
                           │ WebSocket (Real-time)
┌──────────────────────────┴──────────────────────────────────┐
│                      Backend Layer                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │       FastAPI Backend (Port 8000/8080)              │   │
│  │  • REST API  • OAuth/PAT  • Business Logic • WS     │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
┌─────────────────┐ ┌──────────────┐ ┌─────────────────┐
│  GitHub API     │ │   Database   │ │  External APIs  │
│  • OAuth / PAT  │ │  • SQLite    │ │  • Marketplace  │
│  • Repos        │ │  • PostgreSQL│ │  • Webhooks     │
│  • Workflows    │ │              │ │                 │
└─────────────────┘ └──────────────┘ └─────────────────┘
```

## Architecture Diagram

### Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                        │
├─────────────────────────────────────────────────────────────┤
│  Components:                                                │
│  • ProjectsView      • WorkflowEditor    • SecretsManager   │
│  • RepositoryList    • DriftDetection    • UserAvatar       │
│  • WorkflowCreation  • TemplateSelection • AdminPanel       │
├─────────────────────────────────────────────────────────────┤
│  State Management:                                          │
│  • React Context (Theme, User)                              │
│  • Local State (Component-level)                            │
├─────────────────────────────────────────────────────────────┤
│  API Layer:                                                 │
│  • Axios HTTP Client                                        │
│  • WebSocket Client (Real-time updates)                     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                        │
├─────────────────────────────────────────────────────────────┤
│  API Routes:                                                │
│  • /auth/*           - OAuth + PAT authentication           │
│  • /api/projects/*   - Project management                   │
│  • /api/repos/*      - Repository management                │
│  • /api/workflows/*  - Workflow CRUD operations             │
│  • /api/secrets/*    - Secrets management                   │
│  • /api/drift/*      - Drift detection                      │
│  • /webhooks/*       - Webhook handlers (Marketplace)       │
│  • /admin/*          - Admin panel APIs                     │
├─────────────────────────────────────────────────────────────┤
│  Business Logic:                                            │
│  • BuildDetector     - Detect build types from repo         │
│  • DriftDetector     - Compare workflows for drift          │
│  • TemplateGenerator - Generate workflow templates          │
│  • LicenseValidator  - Validate JWT license keys            │
│  • TierManager       - Manage account tiers/limits          │
├─────────────────────────────────────────────────────────────┤
│  Data Layer:                                                │
│  • SQLAlchemy ORM                                           │
│  • Database Models (User, Project, Workflow, etc.)          │
│  • Session Management                                       │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### Frontend Components

#### 1. Authentication
- **OAuth / Token Login**: Supports GitHub OAuth and direct PAT sign-in
- **Session Management**: Stores OAuth session tokens plus encrypted saved PAT metadata
- **Protected Routes**: Requires authentication for certain pages

#### 2. Project Management
- **ProjectsView**: Lists all projects with creation/edit
- **ProjectDetails**: Shows project configuration and repos

#### 3. Workflow Management
- **WorkflowEditor**: CodeMirror editor for YAML editing, with a picker for inserting project secrets and variables
- **TemplateSelection**: Browse and select workflow templates
- **WorkflowCreation**: Guided workflow creation wizard

#### 4. Repository Management
- **RepositoryList**: Displays repositories in project
- **RepositoryFilter**: Filter by build type, visibility
- **BuildTypeDetection**: Shows detected build types

#### 5. Drift Detection
- **DriftDetection**: Status row / banner rendered from the last stored check, "Check Now" for a live check, and the Review Drift modal listing one row per (workflow, repo, branch)
- **SideBySideDiff**: Managed version vs GitHub's current content, with the per-row resolution actions
- **DeletedInGithubPanel**: Shown instead of a diff when the file no longer exists in GitHub (recreate, or Delete Everywhere)

#### 6. Secrets Management
- **SecretsPanel**: CRUD for repository secrets
- **BulkSecretDeployment**: Deploy secrets to multiple repos

### Backend Modules

#### 1. Authentication (`auth.py`)
- GitHub OAuth 2.0 flow
- Direct PAT authentication flow
- Token validation and encrypted PAT storage
- User account creation
- Masked PAT status and saved-token lifecycle endpoints

#### 2. Project Management (`projects.py`)
- CRUD operations for projects
- Repository associations
- Tier-based limits enforcement

#### 3. Workflow Management (`workflows.py`)
- Workflow CRUD operations
- Template management
- Deployment to GitHub
- Version tracking

#### 4. Build Detection (`build_detector.py`)
- Analyzes repository files
- Detects build tools (Maven, Gradle, npm, etc.)
- Suggests appropriate templates
- Multi-language support

#### 5. Drift Detection (`workflows.py`, `drift_worker.py`, `drift_notifications.py`)
- `workflows.py` — the check itself (`run_project_drift_check`), the `/api/projects/{id}/drift` and `/api/workflows/{id}/drift` endpoints, and the resolution endpoints
- `drift_worker.py` — in-process asyncio sweep that re-checks stale projects on a timer, with per-project backoff
- `drift_notifications.py` — persists `WorkflowDriftState` per (workflow, repo, branch), emits `drift.detected` / `drift.resolved` / `drift.check_failed`, and keeps the cached `projects.drift_*` columns in step

#### 6. Secrets Management (`github_secrets.py`)
- Encrypts secrets for GitHub
- Creates/updates repository secrets
- Bulk operations
- Validation

#### 7. Tier Management (`tier_service.py`)
- License key validation (self-hosted)
- Marketplace subscription handling (cloud)
- Feature gating by tier
- Usage limits enforcement

#### 8. Webhook Handler (`marketplace_webhooks.py`)
- Processes GitHub Marketplace events
- Updates account tiers automatically
- Event logging and auditing
- HMAC signature verification

## Data Flow

### Workflow Creation Flow

```
1. User clicks "Create Workflow"
   │
   ▼
2. Frontend: Show repository selection
   │
   ▼
3. Frontend: Detect build type (API call)
   │
   ▼
4. Backend: BuildDetector analyzes repo
   │
   ▼
5. Backend: Returns detected build types
   │
   ▼
6. Frontend: Show template suggestions
   │
   ▼
7. User selects template and customizes
   │
   ▼
8. Frontend: Send workflow to backend
   │
   ▼
9. Backend: Save to database
   │
   ▼
10. Backend: Deploy to GitHub via API
    │
    ▼
11. Backend: Return success/failure
    │
    ▼
12. Frontend: Show result to user
```

### GitHub Authentication Flows

#### OAuth Authentication Flow

```
1. User clicks "Login with GitHub"
   │
   ▼
2. Frontend: Redirect to /auth/github
   │
   ▼
3. Backend: Redirect to GitHub OAuth
   │
   ▼
4. User authorizes on GitHub
   │
   ▼
5. GitHub: Redirect to /auth/callback
   │
   ▼
6. Backend: Exchange code for token
   │
   ▼
7. Backend: Create/update user in DB
   │
   ▼
8. Backend: Redirect to frontend with username
   │
   ▼
9. Frontend: Store user, load dashboard
```

#### Personal Access Token Authentication Flow

```
1. User opens the login screen
   │
   ▼
2. User pastes a fine-grained or classic PAT
   │
   ▼
3. Frontend: POST /auth/token
   │
   ▼
4. Backend: Validate token format and call GitHub /user
   │
   ▼
5. Backend: Store encrypted token metadata in the accounts table
   │
   ▼
6. Frontend: Store username, load dashboard
```

#### Implemented Authentication Routes

- `GET /auth/github`
- `GET /auth/callback`
- `POST /auth/token`
- `GET /api/user/{username}/github-token`
- `POST /api/user/{username}/github-token/test`
- `PUT /api/user/{username}/github-token`
- `DELETE /api/user/{username}/github-token`

### Drift Detection Flow

**Optimized with conditional Git Trees reads and per-(repo, branch) state**

```
1. Trigger: background sweep (drift_worker) or refresh=true from the UI
   │        Opening a project does NOT trigger a check - it reads stored state
   ▼
2. Backend: Resolve the (repo, branch) pairs the project delivers to
   │        resolve_branch_config_for_repo + _resolve_branches_for_repo,
   │        the same path delivery uses (never the GitHub default branch on its own)
   ▼
3. Backend: For each (repo, branch), ONE Git Trees call, conditional on the
   │        stored ETag in workflow_tree_cache
   │        304 → replay cached {filename: sha}, no rate-limit cost
   │        Listing failure → None ("unknown"), never {} ("no workflow files")
   ▼
4. Backend: Compare tree SHAs against workflow_git_hash (or the repo override's hash)
   │
   ▼
5. Backend: Fetch full content only where the SHA differs (or the file is missing)
   │
   ▼
6. Backend: Compare normalized YAML; classify local-edit / under-review /
   │        pending-merge / deleted / drift / check_failed
   ▼
7. Backend: Persist WorkflowDriftState per (workflow, repo, branch), emit
   │        transition notifications, cache the project drift summary
   ▼
8. Frontend: Render banner/list from stored state; fetch GitHub's side of a
   │        diff only when a row is expanded
   ▼
9. User: Resolve (fix PR / restore directly / adopt GitHub version)
   │
   ▼
10. Backend: Apply to GitHub, update DB, and clear the persisted drift for the
    │        repo+branch it acted on (no re-check needed)
```

**Performance Improvement:**
- **Before:** N API calls (one per workflow per repo)
- **After:** 1 conditional call per (repo, branch) + content only for changed files
- **Example:** 10 workflows across 5 repos with no drift: 50 calls → 5 calls, and those 5 answer 304 (no rate-limit cost) while the branches are untouched



## Technology Stack

### Frontend
- **React 19**: UI framework
- **TypeScript**: Type safety (migration in progress)
- **Tailwind CSS v3**: Styling framework
- **CodeMirror 6**: Code editor for YAML
- **Axios**: HTTP client
- **React Router**: Navigation

### Backend
- **FastAPI**: Web framework
- **Python 3.9+**: Programming language
- **SQLAlchemy**: ORM
- **Pydantic**: Data validation
- **PyJWT**: JWT token handling
- **httpx**: Async HTTP client

### Database
- **SQLite**: Default (development, self-hosted)
- **PostgreSQL**: Production (cloud deployment)

### Infrastructure
- **Docker**: Containerization
- **Nginx**: Reverse proxy (self-hosted mode)
- **GitHub Actions**: CI/CD pipelines

### External Services
- **GitHub API**: Repository/workflow management
- **GitHub OAuth / PATs**: Authentication
- **GitHub Marketplace**: Subscription billing (cloud)

## Design Decisions

### 1. Dual Deployment Modes

**Decision:** Support both self-hosted and cloud deployment modes.

**Rationale:**
- Self-hosted: Data sovereignty, on-premise requirements
- Cloud: Multi-tenancy, marketplace integration, scalability

**Implementation:** Separate docker-compose files and configuration

### 2. SQLite Default for Self-Hosted

**Decision:** Use SQLite by default for self-hosted deployments.

**Rationale:**
- Zero configuration
- Suitable for small teams
- Easy backups (single file)
- PostgreSQL available for scaling

### 3. Monolithic Self-Hosted Container

**Decision:** Combine frontend and backend in single container for self-hosted.

**Rationale:**
- Simplified deployment
- Lower resource requirements
- Easier maintenance for small installations
- Built-in Nginx handles routing

### 4. JWT-Based Licensing

**Decision:** Use JWT tokens for self-hosted license keys.

**Rationale:**
- Offline verification
- No phone-home requirement
- Cryptographically secure
- Contains tier and expiration data

### 5. WebSocket for Real-Time Updates

**Decision:** Use WebSockets for real-time collaboration features.

**Rationale:**
- Live workflow editing collaboration
- Instant drift notifications
- Better UX for multi-user scenarios

### 6. Build Type Auto-Detection

**Decision:** Automatically detect build types from repository files.

**Rationale:**
- Reduces user effort
- Suggests relevant templates
- Improves workflow creation UX
- Handles multi-language repos

## Security Architecture

### Authentication & Authorization

1. **GitHub OAuth 2.0 and PAT Support**
   - Secure OAuth token exchange
   - Direct fine-grained / classic PAT authentication via `POST /auth/token`
   - PAT values are never returned to the frontend after save

2. **Credential Storage**
   - OAuth session tokens stay in server memory
   - Saved PATs are encrypted before database storage
   - Validation status is stored separately from the raw token
   - Masked token status endpoints never expose raw token values

3. **API Authorization**
   - Server-side token resolution prefers a saved PAT, then OAuth
   - OAuth is used only when no saved PAT is configured
   - GitHub token validation is performed through GitHub API checks
   - Per-request validation and project membership checks still apply
   - Tier-based access control remains unchanged

### Data Security

1. **Secrets Encryption**
   - GitHub's public key encryption for secrets
   - No plaintext secret storage
   - Secure transmission

2. **Database Security**
   - Parameterized queries (SQLAlchemy)
   - No SQL injection vulnerabilities
   - Access control per user

3. **Webhook Security**
   - HMAC SHA-256 signature verification
   - Source IP verification (optional)
   - Event logging and auditing

### Network Security

1. **HTTPS/TLS**
   - Enforced in production
   - Secure communication with GitHub
   - Certificate validation

2. **CORS Configuration**
   - Restricted origins
   - Credential support (disabled automatically if origins fall back to a wildcard)

3. **Response Security Headers** (`SecurityHeadersMiddleware` in `backend/main.py`, applied to every response)
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Permissions-Policy: geolocation=(), camera=(), microphone=()`
   - `Strict-Transport-Security` (HSTS) when the request is served over HTTPS

## Deployment Modes

### Self-Hosted Mode

```
┌────────────────────────────────────┐
│   Nginx (Port 8080)                │
│   ┌───────────────────────────┐    │
│   │  Static Frontend          │    │
│   └───────────────────────────┘    │
│   ┌───────────────────────────┐    │
│   │  FastAPI Backend          │    │
│   │  (Proxied to /api/*)      │    │
│   └───────────────────────────┘    │
│   ┌───────────────────────────┐    │
│   │  SQLite Database          │    │
│   └───────────────────────────┘    │
└────────────────────────────────────┘
```

**Features:**
- Single container deployment
- Port 8080 (unprivileged)
- SQLite or PostgreSQL
- JWT license-based tiers

### Cloud Mode

```
┌────────────────────┐     ┌────────────────────┐
│  Frontend          │     │  Backend           │
│  Container         │────▶│  Container         │
│  (Nginx + React)   │     │  (FastAPI)         │
└────────────────────┘     └─────────┬──────────┘
                                     │
                           ┌─────────┴──────────┐
                           │                    │
                      ┌────▼────┐      ┌───────▼──────┐
                      │  Postgres│      │   Webhooks   │
                      │  Database│      │  (Marketplace)│
                      └──────────┘      └──────────────┘
```

**Features:**
- Multi-container architecture
- Scalable separately
- PostgreSQL required
- Marketplace webhook integration

## Scalability Considerations

### Current Limitations
- Single backend instance
- No built-in load balancing
- SQLite limited concurrency (self-hosted)

### Future Enhancements
- Horizontal scaling with load balancer
- Redis for session storage
- Message queue for async tasks
- CDN for static assets

## Related Documentation

- **[Development Guide](DEVELOPMENT.md)** - Local setup and workflows
- **[Deployment Guide](DEPLOYMENT.md)** - Production deployment
- **[Database Schema](../DATABASE_SCHEMA.md)** - Data model details
- **[Frontend Development](FRONTEND_DEVELOPMENT.md)** - Frontend architecture
- **[Workflow Delivery Modes](guides/WORKFLOW_DELIVERY_MODES.md)** - Direct vs PR-based delivery
- **[PR-Based Delivery](features/PR_BASED_DELIVERY.md)** - Technical implementation

---

## Workflow Delivery State Machine

Actions Manager supports two workflow delivery modes, each with its own state progression.

### Project States

Projects track their workflow deployment state using the `pr_state` field:

| State | Description | Next Possible States |
|-------|-------------|---------------------|
| `new` | Project just created, no workflows saved | → `draft` |
| `draft` | Workflows saved locally in database, not deployed | → `open` (PR-based), → `synced` (direct commit) |
| `open` | Pull requests created, awaiting review/merge | → `synced` (all merged), → `draft` (all closed) |
| `synced` | Workflows synchronized with GitHub | → `draft` (workflows modified) |

### State Transition Diagram

**Direct Commit Mode:**
```
┌─────┐ Save      ┌───────┐ Deploy    ┌────────┐
│ new │ ────────> │ draft │ ────────> │ synced │
└─────┘ workflows └───────┘  direct   └────────┘
                                            │
                                    Modify  │
                                   workflows│
                                            ▼
                                       ┌───────┐
                                       │ draft │
                                       └───────┘
```

**PR-Based Mode:**
```
┌─────┐ Save      ┌───────┐ Create    ┌──────┐ Merge     ┌────────┐
│ new │ ────────> │ draft │ ────────> │ open │ ────────> │ synced │
└─────┘ workflows └───────┘   PRs     └──────┘  all PRs  └────────┘
                                           │                   │
                                   Close   │           Modify  │
                                   all PRs │          workflows│
                                           ▼                   ▼
                                       ┌───────┐         ┌───────┐
                                       │ draft │         │ draft │
                                       └───────┘         └───────┘
```

### State Transition Details

**1. Project Creation (`new`)**
```python
# When a user creates a new project
project = Project(
    project_name="My Project",
    pr_state="new"  # Initial state
)
```

**2. Save Workflows (`new` → `draft`)**
```python
# User saves workflows via UI or API
POST /api/save-workflows
# Creates Workflow records and transitions project state
project.pr_state = "draft"
```

**3. Direct Commit Deployment (`draft` → `synced`)**
```python
# User deploys workflows directly to GitHub
POST /api/update-workflow
# Commits workflows to repository branches
project.pr_state = "synced"
```

**4. Create Pull Requests (`draft` → `open`)**
```python
# User creates PRs for review workflow
POST /api/create-pull-requests
# Creates PRs and ProjectPullRequest records
project.pr_state = "open"
```

**5. Merge All PRs (`open` → `synced`)**
```python
# User merges all PRs
PUT /api/merge-pull-request (for each PR)
# When last PR is merged:
if all_prs_merged(project):
    project.pr_state = "synced"
```

**6. Close All PRs (`open` → `draft`)**
```python
# User closes all PRs without merging
PATCH /api/close-pull-request (for each PR)
# When last PR is closed:
if all_prs_closed_or_merged(project) and has_open_prs == False:
    project.pr_state = "draft"
```

### Pull Request States

Individual PRs also track their state:

| PR State | Description | GitHub State | Merged |
|----------|-------------|--------------|--------|
| `open` | PR awaiting review/merge | open | false |
| `merged` | PR merged to target branch | closed | true |
| `closed` | PR closed without merging | closed | false |

### State Validation

The backend enforces valid state transitions:

```python
def _update_project_pr_state(db: Session, project_id: int, new_state: str):
    """Update project state with validation."""
    VALID_STATES = ["new", "draft", "open", "synced"]
    
    if new_state not in VALID_STATES:
        raise ValueError(f"Invalid state: {new_state}")
    
    project = db.query(Project).filter_by(project_id=project_id).first()
    
    # Validate state transition
    if project.pr_state == "new" and new_state not in ["draft"]:
        raise ValueError(f"Cannot transition from 'new' to '{new_state}'")
    
    # Update state
    project.pr_state = new_state
    db.commit()
```

### Monitoring State Changes

**Query project state:**
```sql
SELECT project_name, pr_state, updated_at 
FROM projects 
WHERE user_id = ?;
```

**Find projects stuck in 'open' state:**
```sql
SELECT p.project_name, COUNT(pr.pr_id) as open_prs
FROM projects p
JOIN project_pull_requests pr ON p.project_id = pr.project_id
WHERE p.pr_state = 'open' AND pr.pr_state = 'open'
GROUP BY p.project_id, p.project_name;
```

For detailed information on workflow delivery modes, see:
- **[Workflow Delivery Modes Guide](guides/WORKFLOW_DELIVERY_MODES.md)** - User guide
- **[PR-Based Delivery Technical Docs](features/PR_BASED_DELIVERY.md)** - Implementation details
- **[Migration Guide](guides/MIGRATION_DIRECT_TO_PR.md)** - Moving from direct to PR-based

---

**Last Updated:** February 2026  
**Version:** 2.0
