---
layout: home
title: ActionsManager
nav_order: 1
description: "Multi-repository GitHub Actions workflow management for teams."
permalink: /
---

# ActionsManager
{: .fs-9 }

A multi-repository control plane for GitHub Actions workflows. Manage, synchronize, and review workflow changes across your entire repository fleet from one self-hosted interface.
{: .fs-6 .fw-300 }

[Get Started]({% link getting-started/quick-start.md %}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/dawg-io/actions-manager){: .btn .fs-5 .mb-4 .mb-md-0 }

---

> **Beta notice:** ActionsManager Self-Hosted is currently a **free beta preview** for testing, evaluation, and feedback. No paid plans are currently available. The beta is self-hosted only. Features, limits, and licensing may change before general availability. See [Beta Notes]({% link beta/beta-notes.md %}) for details.

## What is ActionsManager?

ActionsManager is a control plane for GitHub Actions, designed for teams that manage workflows across many repositories rather than one at a time. Instead of editing YAML in each repo separately, you operate on a fleet:

- **Manage workflows across repositories** from a single interface, with project-based grouping for multi-repo operations
- **Bulk operations** to apply, update, or remove workflows across every repository in a project in one action
- **Synchronize workflows at scale** by treating reusable workflows as the source of truth and propagating changes to consumers
- **Drift detection and resolution** to surface when a repository's workflow diverges from the managed definition
- **PR orchestration** to deliver changes through reviewable pull requests across many repositories at once
- **GitHub authentication** with OAuth and fine-grained or classic personal access tokens

## Watch ActionsManager in Action

<div class="video-embed">
  <iframe
    src="https://www.youtube-nocookie.com/embed/WkDYK7pCBjI"
    title="ActionsManager product demo: multi-repository workflow rollout"
    frameborder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
    allowfullscreen>
  </iframe>
</div>

See a complete multi-repository workflow rollout — PAT sign-in, project creation, build detection, pull request creation, review, and merge — all from ActionsManager.

[Watch the full demo](https://youtu.be/WkDYK7pCBjI){: .btn .btn-primary .mr-2 }
[Read the demo walkthrough]({% link getting-started/product-demo.md %}){: .btn .mr-2 }
[Install ActionsManager]({% link getting-started/quick-start.md %}){: .btn }

## Quick Start

Run ActionsManager as a single self-hosted container:

```bash
# Generate a stable SECRET_KEY once and reuse it on every start:
# SECRET_KEY=$(openssl rand -hex 32)
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e INSTALLATION_MODE=self-hosted \
  -e SECRET_KEY=<your_generated_key> \
  -e ALLOW_INSECURE_HTTP=true \
  ghcr.io/dawg-io/actions-manager:latest
```

`ALLOW_INSECURE_HTTP=true` is required because this command serves the app over plain HTTP. Drop it once you put ActionsManager behind HTTPS — see [HTTPS Setup]({% link getting-started/https-setup.md %}).

Then open `http://localhost:8080` and sign in with a GitHub Personal Access Token or configure GitHub OAuth.

**→ [Full Quick Start Guide]({% link getting-started/quick-start.md %})**

## Documentation Sections

| Section | Description |
|---------|-------------|
| [Getting Started]({% link getting-started/quick-start.md %}) | Installation, PAT setup, OAuth setup |
| [Features]({% link features/projects.md %}) | Projects, workflows, PR campaigns, drift detection |
| [Security]({% link security/security.md %}) | Security policy, privacy, token handling |
| [Troubleshooting]({% link troubleshooting/common-errors.md %}) | Common errors, GitHub permissions, container startup |
| [Beta Notes]({% link beta/beta-notes.md %}) | Beta scope, limitations, feedback |
