---
layout: default
title: Reusable Workflow Repository Setup
parent: Features
nav_order: 6
---

# Reusable Workflow Repository Setup
{: .no_toc }

A step-by-step guide for first-time users: create a dedicated reusable workflow repository, add workflow files, and connect caller workflows to it through ActionsManager.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

> **Beta notice:** ActionsManager Self-Hosted is currently a **free beta preview**. The setup below is self-hosted focused and does not reference paid, cloud, or Marketplace features that are not yet available.

## What is a reusable workflow repository?

A **reusable workflow repository** is a regular GitHub repository whose only job is to store shared GitHub Actions workflow files. Other repositories call those workflows using the `uses:` directive instead of copying the same YAML into every repo. ActionsManager manages the repository as a **Reusable Workflow Project** (the producer side).

## Should I create a dedicated repository?

Yes. Keeping reusable workflows in their own repository makes versioning, access control, and rollout easier. Do not store reusable workflows alongside your application code — a dedicated repository keeps the surface area small and the ownership clear.

## Recommended repository names

Pick a name that makes the purpose obvious. Common conventions:

- `reusable-workflows`
- `actions-workflows`
- `platform-workflows`
- `github-actions-templates`

There is no required name. Choose whatever fits your organization's naming standards.

## Required repository structure

Reusable workflows **must** live under `.github/workflows/` in the repository. GitHub enforces this path — files stored elsewhere cannot be called with `uses:`.

```
reusable-workflows/
└── .github/
    └── workflows/
        ├── reusable-node-ci.yml
        ├── reusable-python-ci.yml
        └── reusable-docker-build.yml
```

Every reusable workflow file must include `on: workflow_call` — that is the trigger that makes it callable from another repository.

## Example reusable workflow

**File path:** `.github/workflows/reusable-node-ci.yml`

```yaml
name: Reusable Node CI

on:
  workflow_call:
    inputs:
      node-version:
        description: Node.js version to use
        required: false
        type: string
        default: "24"
    secrets:
      NPM_TOKEN:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v6

      - name: Setup Node.js
        uses: actions/setup-node@v6
        with:
          node-version: ${{ inputs.node-version }}
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Run tests
        run: npm test -- --watch=false

      - name: Build
        run: npm run build
```

## Example caller workflow

Application repositories call the reusable workflow above with a caller workflow like this.

**File path:** `.github/workflows/node-ci.yml`

```yaml
name: Node CI

on:
  pull_request:
    branches:
      - main
  push:
    branches:
      - main

jobs:
  node-ci:
    uses: YOUR_ORG_OR_USER/reusable-workflows/.github/workflows/reusable-node-ci.yml@main
    with:
      node-version: "24"
    secrets: inherit
```

Replace `YOUR_ORG_OR_USER` with your actual GitHub owner (organization or personal account) and `reusable-workflows` with your actual repository name.

## Choosing a reference: `@main` vs. a pinned tag

| Reference | Best for | Trade-off |
|-----------|----------|-----------|
| `@main` | Beta testing and rapid iteration | Caller workflows pick up every push to `main` automatically |
| `@v1.2.0` (tag) | Production-style rollouts | Caller workflows only change when you explicitly update the tag |
| `@stable` (branch) | Controlled releases without semver | Middle ground — promote commits to the branch when ready |

For beta testing, `@main` is the simplest option. For production-style usage, prefer a version tag or a dedicated release branch so caller repositories do not change unexpectedly when you push to `main`.

## Topic requirement: `am-rwx`

ActionsManager discovers reusable workflow repositories by looking for the `am-rwx` GitHub topic. Before selecting a repository as the source for a Reusable Workflow Project, add the `am-rwx` topic to it:

1. Open the repository on GitHub
2. Click the gear icon next to **About**
3. Add `am-rwx` to the **Topics** field and save

## End-to-end setup walkthrough

1. Create a GitHub repository — for example, `reusable-workflows`.
2. Add the `am-rwx` topic to the repository (**About → Topics**).
3. Add reusable workflow files under `.github/workflows/`. Each file must include `on: workflow_call`.
4. In ActionsManager, click **New Project** and choose **Reusable Workflow Project**.
5. Select the `reusable-workflows` repository.
6. Add or import your reusable workflow YAML inside ActionsManager.
7. Create a **Caller Workflow Project** for your application repositories.
8. Link or reference the reusable workflow from the caller workflow project.
9. Use PR-based delivery to roll the caller workflow into each target repository.
10. Review and merge the generated pull requests before the changes take effect.
11. Use drift detection to surface manual edits or outdated caller workflow references over time.

## ActionsManager manages workflow definitions — you review the PRs

ActionsManager generates and distributes workflow files, but it does not merge pull requests automatically. Every change lands as a pull request that your team reviews and merges. This keeps the standard GitHub review process intact.

## Related topics

- [Reusable Workflows]({% link features/reusable-workflows.md %}) — overview of the producer-consumer model
- [Projects]({% link features/projects.md %}) — Reusable Workflow Projects and Caller Workflow Projects
- [PR Campaigns]({% link features/pr-campaigns.md %}) — roll out changes through reviewable pull requests
- [Drift Detection]({% link features/drift-detection.md %}) — detect when consumers diverge from the producer
