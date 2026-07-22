# Migration Guide: Direct Commit to PR-Based Delivery

This guide helps teams transition from Direct Commit mode to PR-Based Delivery mode for workflow management in Actions Manager.

## 📋 Table of Contents

1. [Why Migrate?](#why-migrate)
2. [Before You Begin](#before-you-begin)
3. [Migration Strategy](#migration-strategy)
4. [Step-by-Step Migration](#step-by-step-migration)
5. [Team Training](#team-training)
6. [Rollback Plan](#rollback-plan)
7. [FAQs](#faqs)

---

## Why Migrate?

Teams typically migrate from Direct Commit to PR-Based Delivery for these reasons:

### Compliance & Audit Requirements
- 🔒 **SOC 2, ISO 27001, HIPAA** - Regulations require peer review of infrastructure changes
- 📋 **Audit Trails** - Need detailed history of who approved workflow changes
- ✅ **Four-Eyes Principle** - Changes must be reviewed by someone other than the author

### Risk Management
- 🛡️ **Production Safety** - Prevent accidental workflow changes in critical environments
- 🧪 **Testing Requirements** - Need to test workflows before they affect production
- 🔄 **Change Control** - Formal approval process for CI/CD modifications

### Team Growth
- 👥 **Growing Team** - More developers need oversight and collaboration
- 🎓 **Onboarding** - New team members benefit from code review process
- 💬 **Knowledge Sharing** - PRs facilitate learning and discussion

### Branch Protection
- 🔐 **Protected Branches** - GitHub branch protection rules block direct commits
- 📝 **Required Reviews** - Organization policy mandates PR reviews
- 🚦 **Status Checks** - Need automated checks before workflow deployment

---

## Before You Begin

### Prerequisites Checklist

Before migrating, ensure you have:

- [ ] **Actions Manager v1.0+** installed and running
- [ ] **GitHub OAuth** configured with `repo` and `workflow` permissions
- [ ] **Team Buy-in** - All team members understand the change
- [ ] **Documentation Access** - Team has access to PR-based workflow guides
- [ ] **Communication Plan** - Announcements ready for migration day
- [ ] **Testing Environment** - Dev/staging repos to test migration
- [ ] **Backup Plan** - Can rollback if needed

### Assess Your Current Setup

Document your current workflow delivery:

```bash
# Get list of all projects and their current states
curl -X GET "http://localhost:8000/api/projects?user=myusername" | jq '.projects[] | {name: .project_name, state: .pr_state, repos: .repo_count}'
```

**Questions to answer:**
1. How many projects use Direct Commit mode?
2. Which projects contain production workflows?
3. Do any repositories have branch protection enabled?
4. How frequently do you deploy workflow changes?
5. Who currently has permission to deploy workflows?

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Team confusion | High | Medium | Training + documentation |
| Slower deployments | High | Low | Communicate expectations |
| Merge conflicts | Medium | Medium | Clear workflow ownership |
| Unauthorized changes | Low | High | Enable drift detection |
| Lost productivity | Medium | Low | Gradual rollout |

---

## Migration Strategy

### Recommended Approach: Phased Migration

Don't migrate all projects at once. Use a phased approach:

**Phase 1: Test (Week 1)**
- Migrate 1-2 non-critical projects
- Test PR workflow with small team
- Gather feedback and refine process

**Phase 2: Staging (Week 2)**
- Migrate staging/dev environments
- Train entire team on PR workflow
- Document lessons learned

**Phase 3: Production (Week 3+)**
- Migrate production projects one at a time
- Monitor closely for issues
- Provide team support

### Alternative: Big Bang Migration

For small teams or simple setups, migrate all at once:

**Pros:**
- ✅ Clean cutover
- ✅ Single training session
- ✅ No mixed-mode confusion

**Cons:**
- ❌ Higher risk
- ❌ Larger blast radius
- ❌ Limited testing

**Only use this approach if:**
- Team has < 5 developers
- < 10 total projects
- Low workflow change frequency
- Strong team communication

---

## Step-by-Step Migration

### Step 1: Enable Branch Protection (Optional but Recommended)

Enable branch protection on your repositories to enforce PR-based workflow:

**Via GitHub UI:**
1. Go to Repository → Settings → Branches
2. Add branch protection rule for `main` (or your default branch)
3. Enable:
   - ✅ Require a pull request before merging
   - ✅ Require approvals (at least 1)
   - ✅ Dismiss stale pull request approvals when new commits are pushed
   - ✅ Require review from Code Owners (optional)
4. Save changes

**Via GitHub API:**
```bash
curl -X PUT \
  "https://api.github.com/repos/OWNER/REPO/branches/main/protection" \
  -H "Authorization: token YOUR_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -d '{
    "required_pull_request_reviews": {
      "required_approving_review_count": 1,
      "dismiss_stale_reviews": true
    },
    "enforce_admins": false,
    "required_status_checks": null,
    "restrictions": null
  }'
```

### Step 2: Verify Current Workflow State

Before migration, ensure workflows are synchronized:

```bash
# Check if workflows match between Actions Manager and GitHub
curl -X POST "http://localhost:8000/api/detect-drift" \
  -H "Content-Type: application/json" \
  -d '{
    "github_user": "myusername",
    "project_name": "My Project",
    "repo_names": ["owner/repo1", "owner/repo2"]
  }' | jq '.drift_results[] | select(.has_drift == true)'
```

**If drift detected:**
1. Review differences in Actions Manager UI
2. Decide: use GitHub version or Actions Manager version
3. Resolve drift before migration

### Step 3: Communicate to Team

**Email Template:**

```
Subject: Workflow Deployment Process Changing to PR-Based Review

Team,

Starting [DATE], we're moving from direct commit to PR-based delivery for GitHub Actions workflows in [PROJECT NAME].

What's Changing:
- Workflow changes will create Pull Requests instead of direct commits
- All workflow PRs require review before merging
- You'll use the new "Create Pull Requests" button in Actions Manager

Why:
- Improves workflow quality through peer review
- Provides audit trail for compliance
- Enables testing before workflows go live

Action Required:
1. Review the PR-Based Workflow Guide: [LINK]
2. Attend training session: [DATE/TIME]
3. Test the new flow in our staging project

Questions? Contact [CONTACT].

Thanks,
[YOUR NAME]
```

### Step 4: Train Your Team

**Training Session Agenda (30 minutes):**

1. **Overview (5 min)** - Why we're migrating
2. **Demo (10 min)** - Show PR-based workflow end-to-end
3. **Practice (10 min)** - Team creates test PRs
4. **Q&A (5 min)** - Answer questions

**Hands-On Exercise:**

```
1. Create a simple workflow in test project
2. Click "Create Pull Requests"
3. Review the PR on GitHub
4. Merge the PR from Actions Manager
5. Verify workflow is active
```

### Step 5: Migrate First Project (Test)

Choose a low-risk project for your first migration:

**Good First Candidates:**
- ✅ Development/staging environment
- ✅ Single repository
- ✅ Infrequent workflow changes
- ✅ Managed by migration champion

**Bad First Candidates:**
- ❌ Critical production workflows
- ❌ High-change-frequency projects
- ❌ Repositories with complex branch strategies

**Migration Process:**

1. **Select Project:**
   - Go to Actions Manager
   - Select your test project

2. **Ensure Workflows are Saved:**
   - Verify all workflows are in `draft` or `synced` state
   - If workflows need updates, save them first

3. **Create First PR:**
   - Click "Create Pull Requests" button
   - Select all repositories
   - Click "Create PRs"

4. **Review PR:**
   - Open GitHub
   - Navigate to the PR (link in Actions Manager)
   - Review workflow changes
   - Add comments if needed

5. **Merge PR:**
   - Option A: Merge from GitHub PR interface
   - Option B: Use Actions Manager PR Status Panel → Click "Merge"

6. **Verify:**
   - Check that workflows are active on GitHub
   - Trigger a test run to confirm functionality
   - Check project state changed to `synced`

### Step 6: Monitor and Gather Feedback

After first migration, monitor for issues:

**Week 1 Checkpoints:**
- [ ] Day 1: All PRs created successfully?
- [ ] Day 2: Team comfortable with review process?
- [ ] Day 3: Any merge conflicts?
- [ ] Day 5: Workflows functioning as expected?
- [ ] Week end: Gather team feedback

**Feedback Form:**
```
1. How easy was the PR-based workflow? (1-5)
2. Did you encounter any issues?
3. How long did PR review/merge take?
4. What could be improved?
5. Ready to migrate more projects?
```

### Step 7: Migrate Remaining Projects

Based on feedback, migrate additional projects:

**Weekly Migration Schedule:**
- Week 1: 1-2 test projects
- Week 2: 3-5 staging projects
- Week 3: 2-3 production projects
- Week 4+: Remaining projects

**For Each Migration:**
1. Announce 24-48 hours in advance
2. Choose low-traffic time (avoid deployments)
3. Create PRs
4. Monitor for 1-2 hours
5. Document any issues

### Step 8: Update Documentation & Processes

After migration, update your documentation:

**Update These Documents:**
- [ ] Team workflow guide
- [ ] Onboarding documentation
- [ ] Deployment runbooks
- [ ] Incident response procedures
- [ ] Change management process

**Add PR-Based Workflow Sections:**
- How to create workflow PRs
- How to review workflow changes
- How to merge PRs
- How to handle merge conflicts
- Emergency procedures

### Step 9: Set Up Monitoring

Monitor PR lifecycle to ensure smooth operation:

**Daily Checks:**
```bash
# Check for stale PRs (open > 7 days)
curl "http://localhost:8000/api/project-pr-status?github_user=myusername&project_name=My%20Project&refresh_from_github=true" | jq '.pull_requests[] | select(.pr_state == "open")'
```

**Weekly Review:**
- Number of PRs created
- Average time to merge
- Number of PRs closed without merging
- Number of merge conflicts
- Team feedback

---

## Team Training

### Training Materials

**1. Quick Reference Card**

```markdown
# PR-Based Workflow Quick Reference

Create PRs:
1. Configure workflows in Actions Manager
2. Click "Create Pull Requests"
3. Select repositories → Create

Review PRs:
1. Open GitHub PR link
2. Review workflow changes
3. Add comments if needed
4. Approve or request changes

Merge PRs:
Option A: GitHub → "Merge pull request"
Option B: Actions Manager → "PR Status" → "Merge"

Need Help? See: [LINK TO DOCS]
```

**2. Video Tutorial Script**

```
[00:00] Introduction
- What is PR-based workflow delivery
- Why we're using it

[00:30] Creating PRs
- Demo: Configure workflow
- Demo: Click "Create Pull Requests"
- Demo: PR created on GitHub

[02:00] Reviewing PRs
- Demo: Open PR on GitHub
- Demo: Review workflow changes
- Demo: Add review comments

[04:00] Merging PRs
- Demo: Merge from GitHub
- Demo: Merge from Actions Manager
- Demo: Verify workflow active

[05:30] Troubleshooting
- What if PR fails to create?
- What if merge conflicts occur?
- How to close PR without merging?

[07:00] Q&A
```

**3. Hands-On Lab**

```markdown
# Lab: Your First PR-Based Workflow

Setup (5 min):
1. Login to Actions Manager
2. Navigate to "Training Project"

Exercise 1: Create PR (10 min)
1. Create a simple workflow
2. Save workflow
3. Click "Create Pull Requests"
4. Select training repository
5. Verify PR created

Exercise 2: Review PR (10 min)
1. Open PR on GitHub
2. Review workflow changes
3. Add a comment
4. Approve the PR

Exercise 3: Merge PR (5 min)
1. Merge PR from Actions Manager
2. Verify workflow active on GitHub
3. Check project state changed to synced

Bonus: Handle Conflict (10 min)
1. Create PR with conflicting workflow
2. Identify conflict in GitHub
3. Close PR
4. Fix workflow
5. Create new PR
```

### Training Schedule

| Audience | Duration | Format | Topics |
|----------|----------|--------|--------|
| All Team | 30 min | Group | Overview, demo, Q&A |
| Developers | 45 min | Hands-on | Create, review, merge PRs |
| DevOps | 60 min | Technical | API, troubleshooting, monitoring |
| Management | 15 min | Presentation | Business value, compliance |

---

## Rollback Plan

If migration causes significant issues, you can rollback to Direct Commit mode:

### When to Rollback

Consider rollback if:
- ❌ Critical workflow deployment blocked
- ❌ Widespread team confusion
- ❌ Severe performance issues
- ❌ Data loss or corruption
- ❌ Security incident

### Rollback Process

**Step 1: Close All Open PRs**

```bash
# Get list of open PRs
curl "http://localhost:8000/api/project-pr-status?github_user=myusername&project_name=My%20Project" | jq '.pull_requests[] | select(.pr_state == "open")'

# Close each PR
curl -X PATCH "http://localhost:8000/api/close-pull-request" \
  -H "Content-Type: application/json" \
  -d '{
    "github_user": "myusername",
    "project_name": "My Project",
    "repo_name": "owner/repo1",
    "pr_number": 42
  }'
```

**Step 2: Deploy via Direct Commit**

```bash
curl -X POST "http://localhost:8000/api/update-workflow" \
  -H "Content-Type: application/json" \
  -d '{
    "user": "myusername",
    "project_name": "My Project",
    "repo_names": ["owner/repo1"],
    "workflows": [...],
    "branch_option": "default"
  }'
```

**Step 3: Communicate to Team**

```
Subject: Workflow Deployment Rollback

Team,

We're temporarily reverting to direct commit mode for workflow deployment due to [REASON].

Immediate Actions:
- All open PRs have been closed
- Workflows deployed via direct commit
- Resume normal workflow changes

We'll address the issues and plan a future migration.

Thanks for your patience.
```

**Step 4: Post-Mortem**

Conduct a post-mortem to understand what went wrong:
1. Timeline of events
2. Root cause analysis
3. What worked well
4. What didn't work
5. Lessons learned
6. Action items for next attempt

---

## FAQs

### General Questions

**Q: How long does migration take?**

A: For a typical team:
- Small team (< 5 people, < 10 projects): 1-2 weeks
- Medium team (5-15 people, 10-30 projects): 3-4 weeks  
- Large team (> 15 people, > 30 projects): 6-8 weeks

**Q: Can we use both modes simultaneously?**

A: Yes! You can use:
- Direct Commit for dev/staging projects
- PR-Based for production projects

Just create separate projects for each environment.

**Q: Will this slow down our deployment velocity?**

A: Initially, yes:
- First week: 50% slower (learning curve)
- After 2 weeks: 20% slower (review overhead)
- After 1 month: Minimal impact

Most teams find the benefits outweigh the speed reduction.

**Q: What if a PR needs emergency merge?**

A: Options:
1. Merge from GitHub (if you have permissions)
2. Ask someone with merge permissions
3. Temporarily disable branch protection (not recommended)
4. Use Direct Commit mode for emergency (last resort)

### Technical Questions

**Q: What happens to existing workflows after migration?**

A: Nothing! Existing workflows on GitHub remain unchanged until:
1. You create a PR with updates
2. You merge the PR

The workflows continue running as-is.

**Q: Can I customize the PR branch name?**

A: Currently, branch names follow the pattern:
```
actions-manager/{project_code}-{target_branch}
```

This is not customizable to ensure consistency.

**Q: How do I handle merge conflicts?**

A: 
1. Actions Manager will show error if conflict detected
2. Close the PR from Actions Manager
3. Manually resolve conflict on GitHub or locally
4. Either:
   - Push resolution to PR branch, or
   - Update workflow in Actions Manager and create new PR

**Q: Do PRs trigger GitHub Actions workflows?**

A: Yes! If you have workflows that run on `pull_request` events, they'll trigger when Actions Manager creates PRs. This is useful for:
- Testing workflows before merge
- Running validation checks
- Automated reviews

**Q: Can I approve my own PRs?**

A: Depends on your GitHub branch protection settings:
- If "Require review from Code Owners" is enabled: No
- If CODEOWNERS file exists with different owners: No
- Otherwise: Yes (but not recommended)

### Process Questions

**Q: Who should review workflow PRs?**

A: Recommended reviewers:
- DevOps team members
- Senior developers
- Platform engineers
- Anyone familiar with CI/CD

Avoid: The person who created the workflow (for proper peer review).

**Q: How long should PRs stay open?**

A: Recommendations:
- Development workflows: 1-2 hours
- Staging workflows: 4-8 hours
- Production workflows: 24 hours
- Critical production: 48 hours

After 7 days, consider closing stale PRs.

**Q: What should I check when reviewing workflow PRs?**

A: Review checklist:
- [ ] Workflow syntax is valid YAML
- [ ] Job and step names are descriptive
- [ ] Secrets are properly referenced
- [ ] Triggers are appropriate
- [ ] No hardcoded credentials
- [ ] Permissions are minimal required
- [ ] Dependencies are pinned to versions
- [ ] Testing steps included

**Q: Can I test workflows before merging?**

A: Yes! Two options:
1. GitHub Actions runs on the PR branch (if configured)
2. Manually trigger workflow on PR branch using `workflow_dispatch`

---

## Success Metrics

Track these metrics to measure migration success:

### Leading Indicators (During Migration)

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Team training completion | 100% | Attendance records |
| First PR creation success rate | > 95% | API logs |
| PR review time (hours) | < 24 | GitHub PR metadata |
| Migration incidents | 0 critical | Incident tracker |

### Lagging Indicators (Post-Migration)

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Workflow deployment success rate | > 98% | GitHub Actions logs |
| Average PR merge time | < 4 hours | `project-pr-status` API |
| Number of workflow incidents | < 1/month | Incident tracker |
| Team satisfaction | > 4/5 | Survey |

---

## Additional Resources

- **Workflow Delivery Modes Guide:** [WORKFLOW_DELIVERY_MODES.md](WORKFLOW_DELIVERY_MODES.md)
- **PR-Based Feature Documentation:** [PR_BASED_DELIVERY.md](../features/PR_BASED_DELIVERY.md)
- **Actions Manager API Reference:** [ARCHITECTURE.md](../ARCHITECTURE.md)
- **GitHub Branch Protection:** [GitHub Docs](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)

---

## Summary

**Migration Checklist:**

Pre-Migration:
- [ ] Actions Manager v1.0+ installed
- [ ] Team trained on PR-based workflow
- [ ] Branch protection configured (optional)
- [ ] Communication plan ready
- [ ] Rollback plan documented

During Migration:
- [ ] Start with test project
- [ ] Gather feedback
- [ ] Migrate staging projects
- [ ] Migrate production projects
- [ ] Monitor closely

Post-Migration:
- [ ] Update documentation
- [ ] Set up monitoring
- [ ] Collect metrics
- [ ] Continuous improvement

**Remember:**
- Take it slow - phased migration reduces risk
- Communicate early and often
- Provide team support during transition
- Monitor and adjust based on feedback

---

**Last Updated:** February 2026  
**Version:** 1.0  
**Applies to:** Actions Manager v1.0+
