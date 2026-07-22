---
layout: default
title: Drift Detection
parent: Features
nav_order: 4
---

# Drift Detection
{: .no_toc }

Continuously detect when repositories diverge from their managed workflow state and resolve the differences.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What is Drift?

**Drift** occurs when the workflow content in a repository diverges from the definition managed by ActionsManager. Common causes include:

- Manual edits to workflow YAML files in the repository
- Direct commits that bypass ActionsManager
- Merging PRs that modify managed workflow files outside of a campaign
- Workflow files deleted or renamed in the repository
- The reusable workflow referenced by a caller workflow was updated

## How Drift Detection Works

ActionsManager compares the current workflow content in each repository against the managed definition stored in the platform. When a difference is detected, the repository is marked as **drifted**.

Drift checks run:
- On a scheduled interval (background refresh)
- After PR campaigns complete
- On manual trigger from the dashboard

## Drift States

| State | Description |
|-------|-------------|
| In sync | Repository workflow matches the managed definition |
| Drifted | Repository workflow differs from the managed definition |
| Missing | Workflow file not found in the repository |
| Unknown | Drift state could not be determined (API error, permission issue) |

## Viewing Drift

The drift dashboard shows:
- A summary of in-sync vs. drifted repositories across all projects
- Per-repository drift state with last-checked timestamp
- A diff view comparing the repository workflow against the managed definition

## Resolving Drift

When a repository is drifted, you can:

1. **View the diff** — see exactly what changed in the repository versus the managed definition
2. **Sync the repository** — overwrite the repository's workflow with the managed definition, either by direct commit or a new PR
3. **Accept the drift** — update the managed definition to match the repository's current state
4. **Ignore** — mark as acknowledged without changing either side

## Reusable Workflow Drift

For **Reusable Workflow Projects**, drift detection also checks whether caller workflows are still referencing the correct version of the reusable workflow. If the reusable workflow was updated (for example, a new version or changed inputs), caller workflows that reference the old version are flagged as drifted.

## Scheduled Refresh

ActionsManager runs periodic background drift checks to keep the dashboard current without requiring manual refreshes. The check interval is configured based on the deployment size.

## Related Topics

- [Projects]({% link features/projects.md %}) — the scope for drift detection
- [Workflows]({% link features/workflows.md %}) — manage the workflow definitions used for comparison
- [PR Campaigns]({% link features/pr-campaigns.md %}) — deliver drift resolution as reviewed pull requests
- [Reusable Workflows]({% link features/reusable-workflows.md %}) — reusable workflow drift
