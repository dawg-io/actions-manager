---
layout: default
title: Workflows
parent: Features
nav_order: 2
---

# Workflows
{: .no_toc }

Manage GitHub Actions workflow files across all repositories in a project from a single interface.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Overview

ActionsManager treats workflow management as a fleet operation, not a per-repository task. When you define or update a workflow in a project, ActionsManager tracks every repository that should have that workflow and what state it should be in.

## Workflow Operations

### Applying a Workflow

**Applying** a workflow pushes the managed workflow definition to the `.github/workflows/` directory of each repository in the project. You can deliver the change via:

- **PR-based delivery** — opens a pull request in each repository for review before merging
- **Direct commit** — commits the change directly to the target branch (use carefully)

See [PR Campaigns]({% link features/pr-campaigns.md %}) for PR-based delivery.

### Updating a Workflow

When you edit a workflow definition in ActionsManager, the platform:
1. Updates the managed workflow content
2. Identifies which repositories in the project are affected
3. Delivers the updated workflow via your configured delivery method

### Removing a Workflow

Removing a workflow from a project scope deletes the `.github/workflows/` file from all repositories in the project, again via PR or direct commit.

## Delivery Modes

| Mode | Description | When to Use |
|------|-------------|-------------|
| PR-based | Opens a PR in each repository | Recommended for most changes; enables review |
| Direct commit | Commits directly to the target branch | Fast delivery when review is not required |

{: .note }
PR-based delivery is recommended for beta testing and production use. Direct commit mode should be used carefully — changes cannot be reviewed before taking effect.

## Build Detection

ActionsManager can inspect a repository's codebase to detect what build tooling it uses, then recommend matching workflow templates. Detected build types include:

- Maven, Gradle (Java/Kotlin)
- npm, Yarn (JavaScript/TypeScript)
- .NET (C#, F#)
- Python (pip, Poetry, pipenv)
- Go
- Rust (cargo)
- Docker

See [Build Detection]({% link features/build-detection.md %}) for complete details on supported build types, detection patterns, and suggested workflow templates.

## Workflow Editor

ActionsManager includes a YAML editor for creating and modifying workflow content directly in the interface. The editor provides:
- Syntax highlighting
- YAML validation
- Template selection

![Workflow page view showing the project file browser and YAML editor](../assets/screenshots/workflows/workflow-page-view.png)

## Related Topics

- [Projects]({% link features/projects.md %}) — organize repositories for workflow management
- [PR Campaigns]({% link features/pr-campaigns.md %}) — deliver changes through reviewable pull requests
- [Drift Detection]({% link features/drift-detection.md %}) — monitor workflow consistency
- [Reusable Workflows]({% link features/reusable-workflows.md %}) — manage reusable workflow producers
