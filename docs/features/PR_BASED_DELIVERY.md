# PR-Based Workflow Delivery - Technical Documentation

This document provides technical implementation details for the PR-Based Workflow Delivery feature in Actions Manager.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Database Schema](#database-schema)
4. [API Endpoints](#api-endpoints)
5. [Workflow Lifecycle](#workflow-lifecycle)
6. [Frontend Components](#frontend-components)
7. [Error Handling](#error-handling)
8. [Performance Considerations](#performance-considerations)
9. [Security](#security)
10. [Testing](#testing)

---

## Overview

PR-Based Workflow Delivery enables teams to create pull requests for GitHub Actions workflows instead of committing directly. This provides:

- Code review workflow for infrastructure changes
- Testing opportunity before deployment
- Audit trail for compliance
- Integration with branch protection rules

### Key Components

**Backend:**
- FastAPI endpoints for PR management
- SQLAlchemy models for PR tracking
- GitHub API integration for PR operations

**Frontend:**
- React components for PR creation and management
- PR Status Panel for lifecycle tracking
- API client for backend communication

**Database:**
- `projects` table with `pr_state` field
- `project_pull_requests` table for PR metadata

---

## Architecture

### System Components

```
┌─────────────────┐
│   React UI      │
│                 │
│  CreatePRModal  │──┐
│  PRStatusPanel  │  │
└─────────────────┘  │
                     │ HTTP/REST
                     ▼
┌─────────────────────────────────┐
│     FastAPI Backend             │
│                                 │
│  /api/create-pull-requests      │
│  /api/project-pr-status         │
│  /api/merge-pull-request        │
│  /api/close-pull-request        │
└─────────────────────────────────┘
         │                │
         │ GitHub API     │ Database
         ▼                ▼
┌──────────────┐   ┌──────────────┐
│   GitHub     │   │  PostgreSQL  │
│              │   │  / SQLite    │
│  - PRs       │   │              │
│  - Branches  │   │  - projects  │
│  - Commits   │   │  - prs       │
└──────────────┘   └──────────────┘
```

### Request Flow

**Creating PRs:**
```
1. User clicks "Create Pull Requests"
2. CreatePRModal sends POST to /api/create-pull-requests
3. Backend:
   a. Validates user authentication
   b. Fetches project workflows from database
   c. For each selected repository:
      - Creates branch: actions-manager/{project_code}-{target_branch}
      - Commits workflows to branch
      - Creates PR via GitHub API
      - Saves PR metadata to database
   d. Updates project.pr_state to 'open'
4. Returns PR creation results
5. UI displays success and updates state
```

**Checking PR Status:**
```
1. User opens PR Status Panel
2. Frontend requests /api/project-pr-status?refresh_from_github=false
3. Backend:
   a. Queries project_pull_requests table
   b. Returns cached PR data (fast)
4. User clicks "Refresh"
5. Frontend requests with refresh_from_github=true
6. Backend:
   a. Queries GitHub API for each PR
   b. Updates database with current states
   c. Returns fresh data
```

**Merging PRs:**
```
1. User clicks "Merge" in PR Status Panel
2. Frontend sends PUT to /api/merge-pull-request
3. Backend:
   a. Calls GitHub API to merge PR
   b. Updates pr.pr_state to 'merged' in database
   c. Checks if all project PRs are merged
   d. If yes, updates project.pr_state to 'synced'
4. Returns success
5. UI refreshes PR list
```

---

## Database Schema

### Project Table

```python
class Project(Base):
    __tablename__ = "projects"
    
    project_id = Column(Integer, primary_key=True)
    project_code = Column(String(10), unique=True)
    project_name = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("accounts.user_id"))
    
    # PR-based workflow state tracking
    pr_state = Column(String(20), nullable=False, default="new")
    # States: new, draft, open, synced
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

**`pr_state` Values:**

| Value | Description | Next States |
|-------|-------------|-------------|
| `new` | Project created, no workflows | → `draft` |
| `draft` | Workflows saved locally | → `open` (PR), → `synced` (direct) |
| `open` | PRs created, awaiting merge | → `synced`, → `draft` |
| `synced` | Workflows synchronized | → `draft` |

### ProjectPullRequest Table

```python
class ProjectPullRequest(Base):
    __tablename__ = "project_pull_requests"
    
    pr_id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.project_id"), nullable=False, index=True)
    repo_name = Column(String(255), nullable=False)  # Format: owner/repo
    pr_number = Column(Integer, nullable=False)
    pr_url = Column(String(500), nullable=False)
    pr_state = Column(String(20), nullable=False, default="open")  # open, merged, closed
    branch_name = Column(String(255), nullable=False)  # actions-manager/{code}-{target}
    target_branch = Column(String(255), nullable=False)  # main, develop, etc.
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Unique constraint to prevent duplicate PRs
    __table_args__ = (
        UniqueConstraint('project_id', 'repo_name', 'branch_name', 'target_branch'),
    )
```

**`pr_state` Values:**

| Value | Description | GitHub State | Merged |
|-------|-------------|--------------|--------|
| `open` | PR open and awaiting review | open | false |
| `merged` | PR merged to target branch | closed | true |
| `closed` | PR closed without merging | closed | false |

### Database Queries

**Get all open PRs for a project:**
```sql
SELECT * FROM project_pull_requests 
WHERE project_id = ? AND pr_state = 'open';
```

**Count PRs by state:**
```sql
SELECT pr_state, COUNT(*) 
FROM project_pull_requests 
WHERE project_id = ? 
GROUP BY pr_state;
```

**Find stale PRs (open > 7 days):**
```sql
SELECT * FROM project_pull_requests 
WHERE pr_state = 'open' 
  AND created_at < NOW() - INTERVAL '7 days';
```

---

## API Endpoints

### 1. Create Pull Requests

**Endpoint:** `POST /api/create-pull-requests`

**Purpose:** Creates pull requests for selected repositories with project workflows.

**Request Body:**
```json
{
  "github_user": "string (required)",
  "project_name": "string (required)",
  "selected_repos": ["string"] (optional, defaults to all project repos)
}
```

**Response:**
```json
{
  "message": "Pull requests created successfully",
  "results": {
    "owner/repo1 on main": {
      "status": "pr_created" | "pr_updated",
      "pr_number": 42,
      "pr_url": "https://github.com/owner/repo1/pull/42",
      "branch": "actions-manager/proj-main"
    }
  },
  "prs_created": 2
}
```

**State Changes:**
- `project.pr_state`: `draft` → `open`

**Errors:**
- `401` - User not authenticated
- `404` - Project or repositories not found
- `500` - GitHub API error or branch creation failed

**Implementation:**
```python
@router.post("/api/create-pull-requests")
def create_pull_requests(payload: CreatePullRequestsRequest, db: Session = Depends(get_db)):
    # 1. Validate authentication
    if payload.github_user not in user_tokens:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # 2. Get project and workflows
    project = db.query(Project).filter_by(project_name=payload.project_name).first()
    workflows = db.query(Workflow).join(ProjectWorkflow).filter(
        ProjectWorkflow.project_id == project.project_id
    ).all()
    
    # 3. Create PRs for each repository
    results = _process_regular_workflows_update(...)
    
    # 4. Save PR metadata to database
    for repo_branch, result in results.items():
        if result.get("status") in ["pr_created", "pr_updated"]:
            _save_pr_to_database(db, project.project_id, ...)
    
    # 5. Update project state
    _update_project_pr_state(db, project.project_id, "open")
    
    return {"message": "Pull requests created successfully", ...}
```

### 2. Get Project PR Status

**Endpoint:** `GET /api/project-pr-status`

**Purpose:** Retrieves PR status for a project, optionally refreshing from GitHub.

**Query Parameters:**
```
github_user: string (required)
project_name: string (required)
refresh_from_github: boolean (optional, default: false)
```

**Response:**
```json
{
  "project_state": "open" | "synced",
  "pull_requests": [
    {
      "repo_name": "owner/repo1",
      "pr_number": 42,
      "pr_url": "https://github.com/owner/repo1/pull/42",
      "pr_state": "open" | "merged" | "closed",
      "branch_name": "actions-manager/proj-main",
      "target_branch": "main",
      "created_at": "2026-02-17T10:30:00Z",
      "updated_at": "2026-02-17T10:30:00Z"
    }
  ],
  "total_prs": 3,
  "open_prs": 2,
  "merged_prs": 1,
  "closed_prs": 0
}
```

**Performance:**
- `refresh_from_github=false`: Fast (~100ms), uses cached database data
- `refresh_from_github=true`: Slower (~1-5s), fetches from GitHub API

**Errors:**
- `401` - User not authenticated
- `404` - Project not found

**Implementation:**
```python
@router.get("/api/project-pr-status")
def get_project_pr_status(
    github_user: str,
    project_name: str,
    refresh_from_github: bool = False,
    db: Session = Depends(get_db)
):
    # 1. Get all PRs from database
    prs = db.query(ProjectPullRequest).filter_by(project_id=project.project_id).all()
    
    # 2. Optionally refresh from GitHub
    if refresh_from_github:
        for pr in prs:
            github_pr_data = _fetch_pr_from_github(pr.repo_name, pr.pr_number)
            pr.pr_state = _determine_pr_state(github_pr_data)
            db.commit()
    
    # 3. Count PRs by state
    open_prs = sum(1 for pr in prs if pr.pr_state == "open")
    merged_prs = sum(1 for pr in prs if pr.pr_state == "merged")
    closed_prs = sum(1 for pr in prs if pr.pr_state == "closed")
    
    return {
        "project_state": project.pr_state,
        "pull_requests": [pr_to_response(pr) for pr in prs],
        "total_prs": len(prs),
        "open_prs": open_prs,
        "merged_prs": merged_prs,
        "closed_prs": closed_prs
    }
```

### 3. Merge Pull Request

**Endpoint:** `PUT /api/merge-pull-request`

**Purpose:** Merges a pull request via GitHub API.

**Request Body:**
```json
{
  "github_user": "string (required)",
  "project_name": "string (required)",
  "repo_name": "string (required)",
  "pr_number": "integer (required)"
}
```

**Response:**
```json
{
  "message": "Pull request merged successfully",
  "pr_number": 42,
  "repo_name": "owner/repo1"
}
```

**State Changes:**
- `pr.pr_state`: `open` → `merged`
- `project.pr_state`: `open` → `synced` (if all PRs merged)

**Errors:**
- `401` - User not authenticated
- `404` - PR not found
- `409` - PR has conflicts or cannot be merged
- `500` - GitHub API error

**Implementation:**
```python
@router.put("/api/merge-pull-request")
def merge_pull_request(payload: MergePullRequestRequest, db: Session = Depends(get_db)):
    # 1. Call GitHub API to merge PR
    owner, repo = payload.repo_name.split("/")
    merge_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/pulls/{payload.pr_number}/merge"
    
    response = github_put(merge_url, github_user, db, headers=headers, json={
        "commit_title": f"Merge PR #{payload.pr_number}: Actions Manager workflows",
        "merge_method": "merge"
    })
    
    # 2. Update database
    pr = db.query(ProjectPullRequest).filter_by(
        project_id=project.project_id,
        pr_number=payload.pr_number
    ).first()
    pr.pr_state = "merged"
    db.commit()
    
    # 3. Check if all PRs are merged
    open_prs = db.query(ProjectPullRequest).filter_by(
        project_id=project.project_id,
        pr_state="open"
    ).count()
    
    if open_prs == 0:
        _update_project_pr_state(db, project.project_id, "synced")
    
    return {"message": "Pull request merged successfully", ...}
```

### 4. Close Pull Request

**Endpoint:** `PATCH /api/close-pull-request`

**Purpose:** Closes a pull request without merging.

**Request Body:**
```json
{
  "github_user": "string (required)",
  "project_name": "string (required)",
  "repo_name": "string (required)",
  "pr_number": "integer (required)"
}
```

**Response:**
```json
{
  "message": "Pull request closed successfully",
  "pr_number": 42,
  "repo_name": "owner/repo1"
}
```

**State Changes:**
- `pr.pr_state`: `open` → `closed`
- `project.pr_state`: remains `open` (unless all PRs closed)

**Errors:**
- `401` - User not authenticated
- `404` - PR not found
- `500` - GitHub API error

---

## Workflow Lifecycle

### State Machine

```
Project States:
new → draft → open → synced
 ↑                      ↓
 └──────────────────────┘
```

### Detailed Flow

**1. Project Creation (`new` state)**
```python
project = Project(
    project_name="My Project",
    pr_state="new"
)
db.add(project)
db.commit()
```

**2. Save Workflows (`new` → `draft`)**
```python
# User saves workflows via /api/save-workflows
workflow = Workflow(workflow_name="ci-build", workflow_yaml="...")
db.add(workflow)

project.pr_state = "draft"
db.commit()
```

**3. Create PRs (`draft` → `open`)**
```python
# User clicks "Create Pull Requests"
# Backend creates PRs via GitHub API
for repo in selected_repos:
    pr = create_github_pr(repo, workflows)
    
    db_pr = ProjectPullRequest(
        project_id=project.project_id,
        pr_number=pr["number"],
        pr_state="open"
    )
    db.add(db_pr)

project.pr_state = "open"
db.commit()
```

**4. Merge PRs (`open` → `synced`)**
```python
# User merges PR
merge_github_pr(pr_number)

pr.pr_state = "merged"

# Check if all PRs merged
open_count = db.query(ProjectPullRequest).filter_by(
    project_id=project.project_id,
    pr_state="open"
).count()

if open_count == 0:
    project.pr_state = "synced"

db.commit()
```

---

## Frontend Components

### CreatePRModal Component

**Location:** `frontend/src/components/CreatePRModal.tsx`

**Purpose:** Modal dialog for creating pull requests.

**Key Features:**
- Repository selection (all or subset)
- Batch PR creation
- Progress indication
- Error handling

**Usage:**
```tsx
<CreatePRModal
  user="myusername"
  projectName="My Project"
  repositories={[{name: "owner/repo1"}, {name: "owner/repo2"}]}
  onClose={() => setShowModal(false)}
  onSuccess={() => refreshProjectState()}
/>
```

**State Management:**
```tsx
const [selectedRepos, setSelectedRepos] = useState<Set<string>>(new Set());
const [creating, setCreating] = useState<boolean>(false);
const [error, setError] = useState<string | null>(null);
const [results, setResults] = useState<any>(null);
```

### PRStatusPanel Component

**Location:** `frontend/src/components/PRStatusPanel.tsx`

**Purpose:** Panel for viewing and managing pull requests.

**Key Features:**
- List all PRs with status
- Refresh from GitHub
- Merge individual PRs
- Close PRs without merging
- Visual state indicators

**Usage:**
```tsx
<PRStatusPanel
  user="myusername"
  projectName="My Project"
  onClose={() => setShowPanel(false)}
  refreshProjectsList={async () => await loadProjects()}
/>
```

**PR Display:**
```tsx
{prStatus.pull_requests.map(pr => (
  <div key={pr.pr_number} className="pr-item">
    <span className={getPRStateColor(pr.pr_state)}>
      {pr.pr_state.toUpperCase()}
    </span>
    <a href={pr.pr_url} target="_blank">
      PR #{pr.pr_number} - {pr.repo_name}
    </a>
    {pr.pr_state === "open" && (
      <>
        <Button onClick={() => handleMergePR(pr.pr_number, pr.repo_name)}>
          Merge
        </Button>
        <Button onClick={() => handleClosePR(pr.pr_number, pr.repo_name)}>
          Close
        </Button>
      </>
    )}
  </div>
))}
```

---

## Error Handling

### Common Errors and Solutions

**1. Branch Already Exists**

**Error:**
```json
{
  "error": "Reference already exists",
  "status": 422
}
```

**Cause:** Previous PR was closed but branch not deleted.

**Solution:**
```python
# Delete existing branch before creating PR
delete_url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/git/refs/heads/{branch_name}"
github_delete(delete_url, github_user, db, headers=headers)
```

**2. Merge Conflicts**

**Error:**
```json
{
  "error": "Pull Request is not mergeable",
  "status": 405
}
```

**Cause:** Target branch has conflicting changes.

**Solution:** Close PR, resolve conflicts manually, create new PR.

**3. Insufficient Permissions**

**Error:**
```json
{
  "error": "Resource not accessible by integration",
  "status": 403
}
```

**Cause:** OAuth token lacks permissions.

**Solution:** Re-authenticate with correct scopes (`repo`, `workflow`).

**4. Rate Limiting**

**Error:**
```json
{
  "error": "API rate limit exceeded",
  "status": 403
}
```

**Cause:** Too many GitHub API requests.

**Solution:**
- Implement exponential backoff
- Cache PR status
- Use conditional requests with ETags

---

## Performance Considerations

### Optimization Strategies

**1. Cached PR Status**

Default to cached database queries:
```python
# Fast: Query database only
GET /api/project-pr-status?refresh_from_github=false  # ~100ms

# Slow: Query GitHub API for each PR
GET /api/project-pr-status?refresh_from_github=true   # ~1-5s
```

**2. Batch PR Creation**

Create PRs in parallel:
```python
import asyncio
import httpx

async def create_prs_batch(repos, workflows):
    async with httpx.AsyncClient() as client:
        tasks = [create_pr(client, repo, workflows) for repo in repos]
        results = await asyncio.gather(*tasks)
    return results
```

**3. GitHub API Rate Limiting**

- **Authenticated requests:** 5,000 per hour
- **Average PR creation:** ~5 API calls
- **Capacity:** ~1,000 PRs per hour

**4. Database Indexing**

```sql
-- Index for fast PR lookups
CREATE INDEX idx_project_prs_state ON project_pull_requests(project_id, pr_state);

-- Index for stale PR queries
CREATE INDEX idx_project_prs_created ON project_pull_requests(created_at);
```

---

## Security

### Authentication

All PR endpoints require an authenticated GitHub user session. That can come from OAuth or from a saved Personal Access Token resolved on the server:
```python
if github_user not in user_tokens:
    raise HTTPException(status_code=401, detail="User not authenticated")
```

### Authorization

Only users with write access to repositories can:
- Create PRs
- Merge PRs
- Close PRs

GitHub enforces this via OAuth token permissions.

### Input Validation

```python
class CreatePullRequestsRequest(BaseModel):
    github_user: str
    project_name: str
    selected_repos: Optional[List[str]] = None
    
    @validator('github_user')
    def validate_user(cls, v):
        if not v or not v.strip():
            raise ValueError('github_user cannot be empty')
        return v
    
    @validator('selected_repos')
    def validate_repos(cls, v):
        if v is not None:
            for repo in v:
                if '/' not in repo:
                    raise ValueError(f'Invalid repo format: {repo}')
        return v
```

### SQL Injection Prevention

SQLAlchemy ORM prevents SQL injection:
```python
# Safe: Parameterized query
project = db.query(Project).filter_by(project_name=payload.project_name).first()

# Unsafe: Never do this
# db.execute(f"SELECT * FROM projects WHERE project_name = '{payload.project_name}'")
```

---

## Testing

### Unit Tests

**Test PR Creation:**
```python
def test_create_pull_requests():
    # Setup
    user = "testuser"
    project_name = "Test Project"
    
    # Execute
    response = client.post("/api/create-pull-requests", json={
        "github_user": user,
        "project_name": project_name,
        "selected_repos": ["owner/repo1"]
    })
    
    # Assert
    assert response.status_code == 200
    assert response.json()["prs_created"] == 1
```

**Test PR Status:**
```python
def test_get_pr_status():
    # Setup
    create_test_pr(project_id=1, pr_number=42, pr_state="open")
    
    # Execute
    response = client.get(f"/api/project-pr-status?github_user=testuser&project_name=Test")
    
    # Assert
    assert response.json()["open_prs"] == 1
    assert response.json()["merged_prs"] == 0
```

### Integration Tests

**Test End-to-End PR Workflow:**
```python
async def test_pr_lifecycle():
    # 1. Create PR
    create_response = await create_pull_requests(...)
    assert create_response["prs_created"] > 0
    
    # 2. Check status
    status = await get_project_pr_status(..., refresh_from_github=True)
    assert status["open_prs"] > 0
    
    # 3. Merge PR
    merge_response = await merge_pull_request(...)
    assert merge_response["message"] == "Pull request merged successfully"
    
    # 4. Verify state
    final_status = await get_project_pr_status(...)
    assert final_status["merged_prs"] > 0
    assert final_status["project_state"] == "synced"
```

### Manual Testing Checklist

- [ ] Create PRs for multiple repositories
- [ ] Refresh PR status from GitHub
- [ ] Merge PRs individually
- [ ] Close PRs without merging
- [ ] Handle merge conflicts gracefully
- [ ] Test with branch protection enabled
- [ ] Verify state transitions
- [ ] Test error scenarios (auth failure, rate limiting)

---

## Next Steps

- **User Guide:** See [WORKFLOW_DELIVERY_MODES.md](../guides/WORKFLOW_DELIVERY_MODES.md)
- **Migration Guide:** See [MIGRATION_DIRECT_TO_PR.md](../guides/MIGRATION_DIRECT_TO_PR.md)
- **API Reference:** See [ARCHITECTURE.md](../ARCHITECTURE.md)

---

**Last Updated:** February 2026  
**Version:** 1.0  
**Applies to:** Actions Manager v1.0+
