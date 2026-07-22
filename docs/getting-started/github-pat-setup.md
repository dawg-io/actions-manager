---
layout: default
title: GitHub PAT Setup
parent: Getting Started
nav_order: 3
---

# GitHub Personal Access Token Setup
{: .no_toc }

Sign in to ActionsManager using a GitHub Personal Access Token (no OAuth App required).
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## When to Use a PAT

- **Fastest self-hosted setup** — no OAuth App creation required
- **Local development or testing** — simpler than OAuth
- **Repository-scoped access** — fine-grained PATs limit access precisely
- **Short-lived credentials** — easy to rotate on a schedule

OAuth is also supported for browser-based GitHub login. See [GitHub OAuth Setup]({% link getting-started/github-oauth-setup.md %}).

## Supported Token Types

| Type | Recommended? | Notes |
|------|-------------|-------|
| Fine-grained PAT | ✅ Yes | Scoped to specific repos, expirable |
| Classic PAT | Supported | Broader scopes, use only if fine-grained is not available |

## Create a Fine-Grained PAT

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Set a name, expiration date, and resource owner
4. Under **Repository access**, choose **Only select repositories**
5. Select every repository that ActionsManager should manage
6. Grant these minimum permissions:

| Permission | Level | Required for |
|-----------|-------|-------------|
| Metadata | Read-only | All operations |
| Contents | Read and write | Workflow file management |
| Actions | Read and write | Workflow triggering |
| Pull requests | Read and write | PR-based delivery |
| Secrets | Read and write | Repository secrets management |
| Variables | Read and write | Repository variables management |

7. Click **Generate token** and copy it immediately — it is only shown once

## Create a Classic PAT

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **Generate new token (classic)**
3. Set an expiration date
4. Select these scopes:
   - `repo` — private repository access and writes
   - `workflow` — workflow file updates
   - `read:org` — organization visibility
   - `user:email` — user validation
5. Click **Generate token** and copy it immediately

## Sign In with a PAT

1. Start ActionsManager (see [Installation]({% link getting-started/installation.md %}))
2. Open `http://localhost:8080`
3. Click **Sign in with Personal Access Token**
4. Paste your PAT and submit
5. ActionsManager validates the token with GitHub and signs you in

{: .warning }
Never put your PAT in the Docker command line, shell history, environment files, GitHub issues, or screenshots. Enter it in the UI after the container starts.

For a screenshot walkthrough of the login screen and the full first-run flow, see [First Workflow Walkthrough]({% link getting-started/first-workflow-walkthrough.md %}).

## Manage a Saved PAT

After signing in, open the user menu to:
- **Test token** — verify the token is still valid
- **Save token** — store an updated token
- **Replace token** — swap to a new token
- **Remove token** — delete the saved token

The UI never displays the raw token value after saving; it shows only masked status such as **Configured**, **Invalid or expired**, or **Missing required permissions**.

## Troubleshooting PAT Issues

**Invalid token:** The token may be mistyped, revoked, or expired. Generate a new one.

**Missing repositories:** Check that the fine-grained PAT was created with repository access to the correct repositories.

**Missing write permissions:** Verify that **Contents**, **Actions**, and **Pull requests** permissions are set to read and write.

**Organization restrictions:** Some organizations block fine-grained PATs or require approval. Check your organization's token policy in GitHub settings.
