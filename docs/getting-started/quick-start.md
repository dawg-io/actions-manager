---
layout: default
title: Quick Start
parent: Getting Started
nav_order: 1
---

# Quick Start
{: .no_toc }

Get ActionsManager running in under 5 minutes.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

> **Beta notice:** ActionsManager Self-Hosted is currently a free beta preview for testing, evaluation, and feedback. No paid plans are currently available. The beta is provided as-is, without warranty or production-readiness guarantee.

## Prerequisites

- Docker 20.10+ or Podman 3.0+
- Linux or macOS
- 4 GB RAM (8 GB recommended)
- 10 GB available disk space
- A GitHub account with repositories to manage

## Step 1: Start the Container

Run ActionsManager as a single self-hosted container on port 8080:

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

`ALLOW_INSECURE_HTTP=true` is required because this command serves the app over plain HTTP: ActionsManager refuses to start on a non-loopback `http://` address without it, and blocks PAT login over non-local HTTP. Drop it once you put ActionsManager behind HTTPS — see [HTTPS Setup]({% link getting-started/https-setup.md %}).

## Step 2: Open the Interface

Open `http://localhost:8080` in your browser. You will see the ActionsManager sign-in page.

## Step 3: Sign In

Choose one of the two authentication methods:

**Option A — Personal Access Token (fastest):**
1. Click **Sign in with Personal Access Token**
2. Paste a GitHub PAT with the required permissions (see [PAT Setup]({% link getting-started/github-pat-setup.md %}))
3. Click **Sign In**

**Option B — GitHub OAuth:**
1. Create a GitHub OAuth App and configure it (see [OAuth Setup]({% link getting-started/github-oauth-setup.md %}))
2. Pass the OAuth credentials as environment variables when starting the container
3. Click **Sign in with GitHub**

{: .warning }
Do **not** place a personal PAT in the Docker command line or shell history. Start the container first, then enter the token in the UI.

## Step 4: Create Your First Project

> **First time signing in?** ActionsManager shows a short welcome screen before the dashboard, offering a guided tour that walks you through creating a project, adding a workflow, and delivering it as a pull request. Choose **Show me around** to take it, or **Not now** to go straight to the dashboard. You can start it again later from **Restart tour** in the user menu.

1. Click **New Project** in the dashboard
2. Choose a project type:
   - **Caller Workflow Project** — manages repositories that call reusable workflows
   - **Reusable Workflow Project** — manages a shared workflow producer repository
3. Select repository visibility (public or private) and add repositories to your project
4. Review the resource naming settings — keep **Prefix Mode** enabled unless you intentionally want unmanaged filenames
5. Open the new project and click **Add Workflow** to create your first workflow

For a detailed screenshot walkthrough of every step from sign-in through saving your first local draft, see [First Workflow Walkthrough]({% link getting-started/first-workflow-walkthrough.md %}).

## Next Steps

- [First Workflow Walkthrough]({% link getting-started/first-workflow-walkthrough.md %}) — screenshot guide from PAT login to first draft save
- [Full Installation Guide]({% link getting-started/installation.md %}) — detailed setup options
- [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %}) — create and configure a PAT
- [GitHub OAuth Setup]({% link getting-started/github-oauth-setup.md %}) — configure OAuth login
- [Projects]({% link features/projects.md %}) — understand the project model
- [Drift Detection]({% link features/drift-detection.md %}) — keep repositories in sync
