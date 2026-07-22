---
layout: default
title: PR Campaigns
parent: Features
nav_order: 3
---

# PR Campaigns
{: .no_toc }

Roll out workflow changes across many repositories simultaneously through coordinated pull requests.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What is a PR Campaign?

A **PR campaign** is a coordinated operation that opens a pull request in every repository in a project simultaneously. Instead of manually creating a pull request in each repository, ActionsManager creates them all in a single bulk action with consistent metadata.

PR campaigns are the recommended delivery method for rolling out workflow changes in a reviewable and auditable way.

## How a PR Campaign Works

1. **Define the change** — create or update a workflow in your project
2. **Start the campaign** — ActionsManager opens a pull request in each repository in scope
3. **Review and merge** — repository owners review the PRs individually, or you bulk-merge from ActionsManager
4. **Track progress** — the campaign dashboard shows which PRs are open, merged, or closed

## Creating a PR Campaign

1. Navigate to your project and select a workflow
2. Make your changes in the workflow editor
3. Choose **PR-based delivery**
4. Configure PR settings:
   - Branch name
   - PR title
   - PR description / commit message
5. Click **Create PRs**

ActionsManager creates a pull request in each repository using the configured GitHub token. All PRs share the same title, description, and branch name for consistency.

## Campaign Dashboard

![PR campaign dashboard showing campaign stats, status, and per-repository pull requests](../assets/screenshots/pr-campaigns/pr-campaign.png)

The campaign dashboard shows:
- Total repositories in scope
- PRs opened, merged, closed
- Individual PR status per repository
- Links to each PR on GitHub

## Bulk Operations

From the campaign dashboard you can:
- **Bulk merge** — merge all open PRs that have required checks passing
- **Bulk close** — close all open PRs without merging
- **Sync status** — refresh PR state from GitHub

## PR Metadata

ActionsManager adds consistent metadata to campaign PRs:
- Standardized branch names (e.g., `actions-manager/update-workflow`)
- Descriptive PR titles and bodies
- Labels for tracking and filtering

## Preflight Validation

Before a campaign can be created for critical changes, ActionsManager can run a **preflight validation** step — a validation PR that must be reviewed and merged before the full campaign proceeds. This ensures that the change is reviewed by at least one person before it is deployed across all repositories.

## Related Topics

- [Workflows]({% link features/workflows.md %}) — manage workflow content
- [Projects]({% link features/projects.md %}) — organize repositories into projects
- [Drift Detection]({% link features/drift-detection.md %}) — detect post-merge drift
