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

## Managed version vs. GitHub version

Every drift is a difference between two versions of the same workflow:

- **ActionsManager managed version** — the workflow definition ActionsManager stores and delivers for the project. Shown in the left column of the diff.
- **Current GitHub version** — the workflow file as it exists in the repository right now. Shown in the right column of the diff.

Resolving a drift means deciding which of these two should win, and how the change is applied.

Here's an example: a `lint` step was added straight to the workflow file in GitHub, bypassing ActionsManager. The added line is highlighted on the GitHub side:

![Side-by-side diff showing an npm run lint step added directly in GitHub, highlighted against the ActionsManager managed version](../assets/screenshots/drift-detection/drift-diff-view.png)

## Resolving Drift

Open **Review Drift** to see every drifted workflow across the project. Select a single workflow's **View Diff** to see the side-by-side diff and the resolution actions, or select multiple drifted workflows using the checkboxes to resolve them together. Each action names the repository and target branch it affects — or, for a bulk action, every repository and branch among the selected workflows. There are three actions.

### Create Fix Pull Request

Opens a pull request **only** in the drifted repository that restores the workflow to the ActionsManager-managed version. No other repository is changed.

- **Writes to GitHub?** Yes, but only as a pull request branch — nothing lands on the target branch until you merge it.
- **Pull request created?** Yes, one, in the affected repository, against that repository's configured target branch.
- **Repository affected:** just the one shown in the drift record.
- **Resulting state:** the workflow moves to `under_review` and the project's PR state becomes `open`. The drift is **not** cleared yet — it still shows as drifted until the PR is merged.
- **After the PR merges:** the target branch now matches the managed version, ActionsManager marks the workflow `synced_with_github`, and the drift clears on the next check.

This is the recommended option: the change is reviewable and reversible before it reaches your default branch.

### Restore Directly

Immediately overwrites the workflow on the target branch in the drifted repository with the ActionsManager-managed version. No pull request is created.

- **Writes to GitHub?** Yes, immediately, straight to the target branch.
- **Pull request created?** No.
- **Repository affected:** just the one shown in the drift record.
- **Resulting state:** the commit is pushed and the workflow is marked `synced_with_github` once the push succeeds.
- **Why it is riskier:** there is no review step. The current GitHub version is replaced right away, so a mistake reaches your default branch (and anyone watching it) with no chance to catch it in a PR. ActionsManager asks you to confirm the repository and target branch before running it.

### Adopt GitHub Version

Imports the current GitHub version into ActionsManager instead of restoring the managed version. Opening this action presents three sub-modes:

| Sub-mode | Writes to GitHub? | What it does |
|----------|-------------------|--------------|
| Adopt for project and sync other repositories (recommended) | **Yes** | Makes the GitHub version the new managed project workflow, then delivers it to the project's other repositories via pull request or direct commit (your choice). |
| Adopt locally only | **No** | Updates the ActionsManager managed draft to the GitHub version and stops. The draft is reviewed and delivered later through the normal workflow flow. |
| Create repo-specific override | **No** | Pins this repository to its own GitHub version as a per-repo override. The shared project workflow and the other repositories are left unchanged. |

**Effect on other repositories:** because a project workflow is shared across its repositories, changing the managed version affects them all. "Adopt for project and sync" brings the others into line immediately. "Adopt locally only" changes the managed draft without touching GitHub, so the other repositories may now show drift against the new managed version until they are delivered to. "Create repo-specific override" isolates this one repository and leaves everything else as it was.

### Resolving Several Workflows at Once

Workflows that drifted with the **identical** GitHub-side change are grouped automatically — a "N identical — select all" link appears next to any workflow that shares a group, so a change that landed the same way across several repositories can be selected in one click instead of one at a time.

![Drift review list with checkboxes and a "2 identical — select all" grouping link](../assets/screenshots/drift-detection/drift-bulk-select.png)

Select any combination of drifted workflows — individually via their checkboxes, or a whole identical group at once — to reveal a bulk action toolbar with the same three resolution actions, applied to every selected workflow.

![Bulk action toolbar showing 2 of 2 selected and the three bulk resolution actions](../assets/screenshots/drift-detection/drift-bulk-toolbar.png)

Restoring directly still asks for confirmation before overwriting GitHub, naming how many workflows are affected.

## Which option should I use?

| Option | Writes to GitHub | Pull request | Repositories changed |
|--------|------------------|--------------|----------------------|
| Create Fix Pull Request | One repository, via a reviewable PR | Yes | One |
| Adopt GitHub Version | Only "adopt & sync" writes; local-only and override make no GitHub change | Only in "adopt & sync" (PR mode) | "Adopt & sync": the project's repos; otherwise none |
| Restore Directly | One repository, immediately | No | One |

## When Resolution Fails

Resolution talks to GitHub with your stored credentials, so most failures come from GitHub itself. ActionsManager surfaces the specific reason (not a generic error); common cases:

- **Insufficient permissions** — your token lacks write access (or `workflow` scope) for the repository. Reconnect with a token that can push and open pull requests.
- **Branch protection** — the target branch requires reviews, status checks, or blocks direct pushes. "Restore Directly" will be rejected; use "Create Fix Pull Request" so the change goes through review.
- **Missing branch** — the configured target branch no longer exists in the repository. Recreate it or update the project's branch configuration.
- **Existing pull request conflict** — an open ActionsManager PR/branch for this workflow already exists. Merge or close it before opening a new fix PR; ActionsManager will not silently reuse an unrelated PR.
- **Expired or revoked credentials** — the GitHub token is no longer valid. Re-authenticate, then retry.

If a resolution fails, the diff stays open with the reason shown, and no partial state is left behind — nothing is marked synced and no PR record is created.

## Reusable Workflow Drift

For **Reusable Workflow Projects**, drift detection also checks whether caller workflows are still referencing the correct version of the reusable workflow. If the reusable workflow was updated (for example, a new version or changed inputs), caller workflows that reference the old version are flagged as drifted.

## Scheduled Refresh

ActionsManager runs periodic background drift checks to keep the dashboard current without requiring manual refreshes. The check interval is configured based on the deployment size.

## Related Topics

- [Projects]({% link features/projects.md %}) — the scope for drift detection
- [Workflows]({% link features/workflows.md %}) — manage the workflow definitions used for comparison
- [PR Campaigns]({% link features/pr-campaigns.md %}) — deliver drift resolution as reviewed pull requests
- [Reusable Workflows]({% link features/reusable-workflows.md %}) — reusable workflow drift
