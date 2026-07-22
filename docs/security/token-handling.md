---
layout: default
title: Token Handling
parent: Security
nav_order: 3
---

# Token Handling
{: .no_toc }

How ActionsManager handles GitHub tokens and best practices for keeping credentials secure.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## How Tokens Are Used

ActionsManager uses GitHub tokens to:
- Authenticate users (PAT login or OAuth)
- Make GitHub API calls for repository, workflow, pull request, and secrets management
- Validate repository access before performing operations

## Token Storage

Personal Access Tokens submitted via the login UI are stored **encrypted** in the ActionsManager database. The raw token value is:
- Never displayed in the UI after initial submission
- Never included in API responses
- Only decrypted when making GitHub API calls

The UI shows only masked token status: **Configured**, **Invalid or expired**, or **Missing required permissions**.

## Credential Resolution Order

For GitHub API operations, ActionsManager resolves credentials in this order:

1. The user's **saved PAT** (if configured)
2. The user's current **OAuth token** (if no PAT is saved)
3. Authentication error if neither is available

## Token Scope and Least Privilege

Always grant the minimum permissions necessary for your use case:

### Fine-Grained PAT (Recommended)

| Permission | Level | Purpose |
|-----------|-------|---------|
| Metadata | Read-only | Required for all repository operations |
| Contents | Read and write | Workflow file management |
| Actions | Read and write | Workflow triggering |
| Pull requests | Read and write | PR-based delivery |
| Secrets | Read and write | Only if using secrets management |
| Variables | Read and write | Only if using variables management |

Limit **Repository access** to only the repositories ActionsManager needs to manage.

### Classic PAT

Use only if fine-grained PATs are not available for your use case. Minimum scopes:
- `repo` — private repository access
- `workflow` — workflow file updates
- `read:org` — organization visibility
- `user:email` — user validation

## Security Best Practices

- **Use fine-grained PATs** with expiration dates rather than never-expiring classic PATs
- **Limit repository scope** on fine-grained PATs to only what ActionsManager needs
- **Enter tokens in the UI**, not on the Docker command line or in environment files
- **Rotate tokens** on a regular schedule and immediately if exposure is suspected
- **Do not share PATs** — each user or deployment should use its own token
- **Never commit tokens** to source control or paste them in GitHub issues, PRs, or screenshots

## What to Do If a Token Is Exposed

1. **Immediately revoke** the token in GitHub at **Settings → Developer settings → Personal access tokens**
2. Generate a new token and sign in to ActionsManager with the new token
3. Review GitHub audit logs for unauthorized activity
4. Check shell history, logs, environment files, and container configurations for additional exposures

## OAuth Token Handling

OAuth tokens obtained through GitHub OAuth login are:
- Stored in the session and used for authentication
- Scoped to the user's GitHub account access
- Not shared with other users

If you configure GitHub OAuth for ActionsManager, the `GITHUB_CLIENT_SECRET` must be kept confidential and never committed to source control.

## Related Topics

- [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %}) — creating tokens with least privilege
- [GitHub OAuth Setup]({% link getting-started/github-oauth-setup.md %}) — configuring OAuth login
- [Security Policy]({% link security/security.md %}) — hardening guidance
- [Privacy]({% link security/privacy.md %}) — how token data is stored
