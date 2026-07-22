# Workflow Delivery Modes Guide

Actions Manager provides two distinct workflow delivery modes to accommodate different team workflows and organizational requirements. This guide explains both modes and helps you choose the right one for your needs.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Direct Commit Mode](#direct-commit-mode)
3. [PR-Based Delivery Mode](#pr-based-delivery-mode)
4. [Comparison](#comparison)
5. [Choosing the Right Mode](#choosing-the-right-mode)
6. [How to Use Each Mode](#how-to-use-each-mode)
7. [Workflow State Machine](#workflow-state-machine)
8. [Troubleshooting](#troubleshooting)

---

## Overview

Actions Manager supports two workflow delivery modes:

### 🚀 **Direct Commit Mode** (Traditional)
Workflows are committed directly to the default or specified branches in your repositories. This is the quickest way to deploy workflows and is ideal for rapid development and trusted environments.

### 🔍 **PR-Based Delivery Mode** (Review-First)
Workflows are pushed to a dedicated Actions Manager branch and a pull request is created. This enables code review, testing, and approval before workflows are merged into target branches. Ideal for compliance-heavy environments and teams that require peer review.

**Key Difference:**
- **Direct Commit**: Workflows go live immediately upon deployment
- **PR-Based**: Workflows require explicit merge action to go live

---

## Direct Commit Mode

### What It Does

Direct Commit Mode pushes workflow files directly to your repository's target branches without creating a pull request. The workflows become active immediately after deployment.

### How It Works

1. You configure workflows in Actions Manager
2. You click "Deploy to GitHub" or use the API
3. Actions Manager commits the workflows directly to your selected branches
4. Workflows are immediately active in GitHub Actions

### Workflow States

In Direct Commit mode, projects follow this state progression:
- **`new`** - Project just created, no workflows saved yet
- **`draft`** - Workflows saved locally in Actions Manager database
- **`synced`** - Workflows deployed to GitHub and synchronized

### Advantages

✅ **Fast Deployment** - No waiting for PR review or approval  
✅ **Simple Workflow** - Fewer steps from creation to deployment  
✅ **Immediate Feedback** - See results in CI/CD pipelines immediately  
✅ **Best for Prototyping** - Rapid iteration during development  
✅ **Lower Overhead** - No PR management required  

### Disadvantages

❌ **No Review Process** - Changes go live without peer review  
❌ **Less Auditable** - Harder to track who approved what  
❌ **Risk of Errors** - Mistakes deploy immediately  
❌ **No Testing Window** - Can't test workflows before merging  
❌ **Compliance Issues** - May not meet regulatory requirements  

### Best For

- **Development environments** - Rapid prototyping and iteration
- **Personal projects** - Single developer or trusted small teams
- **Internal tools** - Low-risk automation workflows
- **Trusted teams** - Teams with high confidence in their workflows
- **Non-production** - Staging/development environments

### API Endpoint

**POST** `/api/update-workflow`

```json
{
  "user": "github_username",
  "project_name": "My Project",
  "repo_names": ["owner/repo1", "owner/repo2"],
  "workflows": [
    {
      "name": "ci-build",
      "content": "name: CI Build\n..."
    }
  ],
  "branch_option": "default",
  "regex_pattern": ""
}
```

**Response:**
```json
{
  "message": "✅ All workflows updated",
  "results": {
    "owner/repo1 on main": "✅ Workflow updated successfully",
    "owner/repo2 on main": "✅ Workflow updated successfully"
  }
}
```

---

## PR-Based Delivery Mode

### What It Does

PR-Based Delivery Mode creates a dedicated Actions Manager branch in your repositories, commits workflows to that branch, and opens a pull request for review. Workflows only become active after the PR is merged.

### How It Works

1. You configure workflows in Actions Manager
2. You click "Create Pull Requests"
3. Actions Manager:
   - Creates a branch named `actions-manager/{project_code}-{target_branch}`
   - Commits workflows to this branch
   - Opens a PR against your target branch(es)
4. Team reviews the PR in GitHub
5. You merge the PR from:
   - GitHub's PR interface, or
   - Actions Manager's PR Status Panel
6. Workflows become active after merge

### Workflow States

In PR-Based mode, projects follow this state progression:
- **`new`** - Project just created, no workflows saved yet
- **`draft`** - Workflows saved locally in Actions Manager database
- **`open`** - Pull requests created and awaiting review/merge
- **`synced`** - All PRs merged, workflows synchronized with GitHub

### Advantages

✅ **Code Review** - Changes reviewed before going live  
✅ **Testing Opportunity** - Can test workflows on the PR branch  
✅ **Audit Trail** - Full history of who approved what  
✅ **Compliance Friendly** - Meets regulatory requirements  
✅ **Collaboration** - Team discussion on workflow changes  
✅ **Rollback Easy** - Can close PRs without merging  
✅ **Branch Protection** - Works with protected branches  

### Disadvantages

❌ **Slower Deployment** - Requires PR review and merge  
❌ **Additional Steps** - More complex workflow  
❌ **Overhead** - Managing PRs takes time  
❌ **Delayed Feedback** - Can't test in real CI/CD immediately  

### Best For

- **Production environments** - Critical workflows that need review
- **Regulated industries** - Compliance requirements (SOC2, HIPAA, etc.)
- **Large teams** - Multiple developers need to review changes
- **Protected branches** - Repositories with branch protection rules
- **High-risk workflows** - Deployment, security, or financial workflows
- **Open source projects** - Community review and contribution

### API Endpoints

#### 1. Create Pull Requests

**POST** `/api/create-pull-requests`

```json
{
  "github_user": "github_username",
  "project_name": "My Project",
  "selected_repos": ["owner/repo1", "owner/repo2"]
}
```

**Response:**
```json
{
  "message": "Pull requests created successfully",
  "results": {
    "owner/repo1 on main": {
      "status": "pr_created",
      "pr_number": 42,
      "pr_url": "https://github.com/owner/repo1/pull/42",
      "branch": "actions-manager/proj-main"
    }
  },
  "prs_created": 2
}
```

#### 2. Get PR Status

**GET** `/api/project-pr-status?github_user=username&project_name=My+Project&refresh_from_github=false`

**Response:**
```json
{
  "project_state": "open",
  "pull_requests": [
    {
      "repo_name": "owner/repo1",
      "pr_number": 42,
      "pr_url": "https://github.com/owner/repo1/pull/42",
      "pr_state": "open",
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

#### 3. Merge Pull Request

**PUT** `/api/merge-pull-request`

```json
{
  "github_user": "github_username",
  "project_name": "My Project",
  "repo_name": "owner/repo1",
  "pr_number": 42
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

#### 4. Close Pull Request (Without Merging)

**PATCH** `/api/close-pull-request`

```json
{
  "github_user": "github_username",
  "project_name": "My Project",
  "repo_name": "owner/repo1",
  "pr_number": 42
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

---

## Comparison

| Feature | Direct Commit Mode | PR-Based Delivery Mode |
|---------|-------------------|------------------------|
| **Speed** | ⚡ Immediate | 🐢 Requires review |
| **Review Process** | ❌ None | ✅ Full PR review |
| **Audit Trail** | ⚠️ Commit history only | ✅ PR history + comments |
| **Testing** | ⚠️ In production | ✅ Test on PR branch |
| **Rollback** | ⚠️ Manual revert | ✅ Close PR |
| **Compliance** | ❌ Limited | ✅ Full compliance |
| **Branch Protection** | ⚠️ May bypass | ✅ Respects rules |
| **Team Collaboration** | ⚠️ Limited | ✅ Full discussion |
| **Complexity** | ✅ Simple | ⚠️ More steps |
| **Best For** | Development/Testing | Production/Compliance |

### Performance Comparison

**Direct Commit Mode:**
- ⚡ Deployment: ~1-2 seconds per repository
- ⚡ Feedback: Immediate
- ⚡ Total time: < 1 minute

**PR-Based Mode:**
- ⚡ PR Creation: ~2-3 seconds per repository
- ⏳ Review time: Minutes to hours (team dependent)
- ⏳ Merge time: ~1-2 seconds per PR
- ⏳ Total time: Variable (typically 5-60 minutes)

---

## Choosing the Right Mode

### Use **Direct Commit Mode** when:

- ✅ You're in a **development or testing environment**
- ✅ You're working **solo or with a small trusted team**
- ✅ You need **rapid iteration** during prototyping
- ✅ **Compliance is not a requirement**
- ✅ You have **high confidence** in your workflows
- ✅ Your repositories **don't have branch protection**

### Use **PR-Based Delivery Mode** when:

- ✅ You're in a **production environment**
- ✅ You work in a **regulated industry** (finance, healthcare, etc.)
- ✅ You have **branch protection rules** enabled
- ✅ You need an **audit trail** for compliance
- ✅ You want to **test workflows** before they go live
- ✅ You need **team review and approval**
- ✅ You're working on **critical workflows** (deployments, security)

### Hybrid Approach

Many teams use both modes:
- **Direct Commit** for development/staging repositories
- **PR-Based** for production repositories

You can configure this per repository by:
1. Creating separate projects for dev and prod environments
2. Using Direct Commit for dev projects
3. Using PR-Based for prod projects

---

## How to Use Each Mode

### Direct Commit Mode - Step by Step

#### Via UI

1. **Create and configure workflows** in Actions Manager
2. **Save workflows** to local database (project state: `new` → `draft`)
3. **Click "Deploy to GitHub"** button
4. **Select repositories** to deploy to
5. **Choose branch option:**
   - Default branch (usually `main`)
   - Branch pattern (regex matching)
6. **Click "Deploy"**
7. **Workflows are live!** (project state: `draft` → `synced`)

#### Via API

```bash
curl -X POST http://localhost:8000/api/update-workflow \
  -H "Content-Type: application/json" \
  -d '{
    "user": "myusername",
    "project_name": "My Project",
    "repo_names": ["owner/repo1", "owner/repo2"],
    "workflows": [
      {
        "name": "ci-build",
        "content": "name: CI Build\non:\n  push:\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v5"
      }
    ],
    "branch_option": "default"
  }'
```

### PR-Based Mode - Step by Step

#### Via UI

1. **Create and configure workflows** in Actions Manager
2. **Save workflows** to local database (project state: `new` → `draft`)
3. **Click "Create Pull Requests"** button
4. **Select repositories** to create PRs for
5. **Click "Create PRs"**
6. **PRs are created** (project state: `draft` → `open`)
7. **Open PR Status Panel** to view all PRs
8. **Review PRs on GitHub:**
   - View workflow changes
   - Run tests on PR branch
   - Add comments and reviews
9. **Merge PRs** via:
   - GitHub PR interface (click "Merge pull request"), or
   - Actions Manager PR Status Panel (click "Merge" button)
10. **Workflows are live!** (when all PRs merged, state: `open` → `synced`)

#### Via API

**Step 1: Create Pull Requests**

```bash
curl -X POST http://localhost:8000/api/create-pull-requests \
  -H "Content-Type: application/json" \
  -d '{
    "github_user": "myusername",
    "project_name": "My Project",
    "selected_repos": ["owner/repo1", "owner/repo2"]
  }'
```

**Step 2: Check PR Status**

```bash
curl -X GET "http://localhost:8000/api/project-pr-status?github_user=myusername&project_name=My%20Project&refresh_from_github=true"
```

**Step 3: Merge a PR**

```bash
curl -X PUT http://localhost:8000/api/merge-pull-request \
  -H "Content-Type: application/json" \
  -d '{
    "github_user": "myusername",
    "project_name": "My Project",
    "repo_name": "owner/repo1",
    "pr_number": 42
  }'
```

**Step 4: Close a PR (without merging)**

```bash
curl -X PATCH http://localhost:8000/api/close-pull-request \
  -H "Content-Type: application/json" \
  -d '{
    "github_user": "myusername",
    "project_name": "My Project",
    "repo_name": "owner/repo1",
    "pr_number": 42
  }'
```

---

## Workflow State Machine

Actions Manager tracks project state to manage the workflow delivery lifecycle.

### State Definitions

| State | Description | Available in Mode |
|-------|-------------|-------------------|
| **`new`** | Project created, no workflows saved | Both |
| **`draft`** | Workflows saved locally, not deployed | Both |
| **`open`** | PRs created and pending review | PR-Based only |
| **`synced`** | Workflows deployed/merged to GitHub | Both |

### State Transitions

#### Direct Commit Mode
```
new → draft → synced
 ↑              ↓
 └──────────────┘
  (delete workflows)
```

**Transitions:**
1. **`new` → `draft`**: Save workflows to Actions Manager database
2. **`draft` → `synced`**: Deploy workflows to GitHub via direct commit
3. **`synced` → `draft`**: Delete all workflows from GitHub (rare)

#### PR-Based Mode
```
new → draft → open → synced
 ↑              ↓
 └──────────────┘
  (close all PRs)
```

**Transitions:**
1. **`new` → `draft`**: Save workflows to Actions Manager database
2. **`draft` → `open`**: Create pull requests for repositories
3. **`open` → `synced`**: All PRs merged to target branches
4. **`open` → `draft`**: All PRs closed without merging (rare)

### Checking Project State

#### Via API
```bash
curl "http://localhost:8000/api/project-pr-status?github_user=myusername&project_name=My%20Project"
```

#### Via Database
```sql
SELECT project_name, pr_state FROM projects WHERE project_name = 'My Project';
```

---

## Troubleshooting

### Common Issues

#### Issue: "Cannot create PR - branch already exists"

**Cause:** A previous PR was closed and the branch wasn't deleted.

**Solution:**
```bash
# Delete the branch manually on GitHub or via API
git push origin --delete actions-manager/proj-main
```

Or use GitHub's UI: Repository → Branches → Delete the branch

#### Issue: "PR shows as open but doesn't exist on GitHub"

**Cause:** Database is out of sync with GitHub state.

**Solution:**
```bash
# Refresh from GitHub to update database
curl "http://localhost:8000/api/project-pr-status?github_user=myusername&project_name=My%20Project&refresh_from_github=true"
```

#### Issue: "Direct commit fails with 'protected branch'"

**Cause:** Repository has branch protection rules enabled.

**Solution:** Use PR-Based Delivery Mode instead, which respects branch protection.

#### Issue: "PR merge fails with conflicts"

**Cause:** Target branch has changes that conflict with workflow files.

**Solution:**
1. Close the PR from Actions Manager
2. Resolve conflicts manually in GitHub
3. Create a new PR from Actions Manager

#### Issue: "Cannot create PRs - unauthorized"

**Cause:** GitHub OAuth token expired or lacks permissions.

**Solution:**
1. Log out of Actions Manager
2. Log back in to refresh OAuth token
3. Ensure OAuth app has `repo` and `workflow` permissions

### Performance Tips

**For Direct Commit Mode:**
- Deploy to fewer branches to reduce API calls
- Use `branch_option: "default"` for fastest deployment
- Batch multiple workflow changes together

**For PR-Based Mode:**
- Use `refresh_from_github=false` (default) for fast PR status checks
- Only use `refresh_from_github=true` when you need real-time GitHub state
- Merge PRs in batches to reduce API calls

### Best Practices

**Direct Commit Mode:**
1. ✅ Test workflows locally before deploying
2. ✅ Use semantic workflow names for easy identification
3. ✅ Monitor GitHub Actions runs after deployment
4. ✅ Keep workflows in Actions Manager as source of truth
5. ✅ Enable drift detection to catch manual changes

**PR-Based Mode:**
1. ✅ Add descriptive PR titles and descriptions
2. ✅ Review workflows in GitHub PR interface
3. ✅ Test workflows on the PR branch before merging
4. ✅ Use PR Status Panel to track all PRs in one place
5. ✅ Close stale PRs that are no longer needed
6. ✅ Delete Actions Manager branches after merging

---

## Next Steps

- **Migration Guide:** See [MIGRATION_DIRECT_TO_PR.md](MIGRATION_DIRECT_TO_PR.md) for moving from Direct to PR-Based mode
- **PR-Based Feature Details:** See [PR_BASED_DELIVERY.md](../features/PR_BASED_DELIVERY.md) for technical implementation details
- **API Reference:** See [ARCHITECTURE.md](../ARCHITECTURE.md) for complete API documentation
- **Drift Detection:** See [WORKFLOW_OPTIMIZATION.md](../features/WORKFLOW_OPTIMIZATION.md) for drift detection with both modes

---

**Last Updated:** February 2026  
**Version:** 1.0  
**Applies to:** Actions Manager v1.0+
