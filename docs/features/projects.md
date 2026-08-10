---
layout: default
title: Projects
parent: Features
nav_order: 1
---

# Projects
{: .no_toc }

Projects are the primary organizational unit in ActionsManager, grouping related repositories for coordinated workflow management.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What is a Project?

A **project** in ActionsManager is a named collection of repositories that share a workflow management scope. Projects are the unit you operate on — permissions, workflows, secrets, and rollouts are all coordinated at the project level.

Instead of managing workflows repository by repository, you group related repositories into a project and apply changes to all of them in a single operation.

## Project Types

ActionsManager uses two project types that reflect the two sides of GitHub Actions reusability:

### Caller Workflow Project

A **Caller Workflow Project** (referred to internally as `standard`) manages the repositories whose workflows *call* reusable workflows using the `uses:` directive.

Use this project type when you want to:
- Manage multiple repositories that share a common workflow pattern
- Apply, update, or remove caller workflows across a fleet of repositories
- Keep all repositories synchronized against a shared workflow definition

### Reusable Workflow Project

A **Reusable Workflow Project** (referred to internally as `rwx`) manages the *producer* side — the repository that defines and publishes the reusable workflows that other repositories call.

Use this project type when you want to:
- Author and version reusable workflow definitions centrally
- Track which caller workflows across your organization reference your reusable workflows
- Propagate changes from the producer to all consumers

### Working Together

The real power of ActionsManager comes from managing both project types together. When a reusable workflow changes in a producer project, ActionsManager identifies which caller projects are affected and can roll out the update across the entire consumer fleet.

## Creating a Project

1. Click **New Project** in the dashboard
2. Choose a project type (Caller Workflow or Reusable Workflow)
3. Name the project
4. Add repositories to the project

## Managing Repositories

Within a project you can:
- **Add repositories** — include repositories from your GitHub account or organizations
- **Remove repositories** — take a repository out of scope without deleting its workflows
- **Configure per-repository settings** — specify branches, labels, and delivery preferences

## Branch Configuration

**Repositories & Branches** decides which branches a project writes to. The same answer is used for
[drift detection]({% link features/drift-detection.md %}#which-branches-are-checked), so a project is
always compared against the branches it actually delivers to — never against a branch nobody chose.

| Option | What it targets |
|--------|-----------------|
| **Default branch** | Each repository's own GitHub default branch |
| **Branch name or pattern** | Every branch matching the name or regular expression you enter (`main`, `release-.*`, `feature/auth`) |

Pattern mode adds a **Max branch age** (1–30 days, 30 by default): only branches with a commit
inside that window are targeted, so stale branches matching the pattern are left alone. If a pattern
matches nothing — or every match is older than the window — ActionsManager falls back to the
repository's default branch.

**Per-repository override.** Each repository in the list either uses **Use project default** or
**Override for this repository**, which gives that one repository its own option, pattern and age
window. Everything else in the project keeps the project setting.

## Ordering Projects

The Projects dashboard keeps the arrangement you choose. Drag a card by its grip
handle (to the left of the three-dot menu) and drop it anywhere in the grid.

- **Opening or editing a project no longer moves its card.** The dashboard used to
  sort by last-updated time, so simply viewing a project pushed it to the front.
- **Your order is your own.** It is saved per user, so rearranging your dashboard
  never changes what a teammate sees.
- **It follows you.** The order persists across refreshes, sessions, browsers and
  devices, because it is stored on the server rather than in the browser.
- **New projects appear at the end**, so an existing arrangement is never disturbed.
- **Reordering is disabled while searching or filtering.** A filtered grid only shows
  some of your projects, and saving from that view would lose the position of the
  hidden ones. Clear the filters to re-enable the handles — your full order is
  preserved while filtering.

Dragging never opens a project: clicking a card still navigates, and the three-dot
menu keeps working as before. If an order fails to save, the grid returns to its
previous arrangement and shows an error rather than leaving the dashboard and the
server out of step.

The first time you open the dashboard, projects are arranged most-recently-updated
first and that arrangement is saved as your starting point.

## Project Permissions

Access to a project is tied to your GitHub authentication. You can only manage repositories that your configured GitHub token or OAuth session can access.

## Related Topics

- [Workflows]({% link features/workflows.md %}) — manage workflow content across project repositories
- [PR Campaigns]({% link features/pr-campaigns.md %}) — roll out changes through reviewable pull requests
- [Drift Detection]({% link features/drift-detection.md %}) — detect when repositories diverge from the managed state
- [Reusable Workflows]({% link features/reusable-workflows.md %}) — manage producer-consumer workflow relationships
