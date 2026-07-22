---
layout: default
title: GitHub Permissions
parent: Troubleshooting
nav_order: 2
---

# GitHub Permissions
{: .no_toc }

Required GitHub permissions for ActionsManager features.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Required Permissions by Feature

This reference maps ActionsManager features to the GitHub token permissions they require.

### Fine-Grained PAT Permissions

| Feature | Permission | Level |
|---------|-----------|-------|
| Browse repositories | Metadata | Read-only |
| Read workflow files | Contents | Read-only |
| Write/update workflow files | Contents | Read and write |
| Trigger workflows | Actions | Read and write |
| Create pull requests | Pull requests | Read and write |
| Merge pull requests | Pull requests | Read and write |
| Manage repository secrets | Secrets | Read and write |
| Manage repository variables | Variables | Read and write |
| Manage repository rulesets | Administration | Read and write |

### Classic PAT Scopes

| Feature | Required Scope |
|---------|---------------|
| Repository access (private repos) | `repo` |
| Workflow file management | `workflow` |
| Organization visibility | `read:org` |
| User validation | `user:email` |

## Organization Token Policies

Some GitHub organizations restrict how personal access tokens can be used:

### Fine-Grained PAT Restrictions

Organizations can:
- **Require approval** before a fine-grained PAT can access organization resources
- **Block fine-grained PATs entirely**, requiring classic PATs or OAuth instead

**Check:** Go to your GitHub organization's settings → **Personal access tokens** to see the policy.

**Resolution:** If approval is required, request access or ask an organization admin to approve the token.

### Classic PAT Restrictions

Organizations can also block classic PATs or require SSO authorization:

- **SAML SSO:** If the organization uses SAML SSO, the PAT must be authorized for SSO at **GitHub → Settings → Developer settings → Personal access tokens → [token] → Authorize SSO**

## Repository Access Scope

Fine-grained PATs require explicit repository selection. If ActionsManager cannot see a repository:

1. Edit the fine-grained PAT in GitHub settings
2. Under **Repository access**, confirm the specific repository is selected
3. Save the token — you do not need to generate a new one

## Checking Current Permissions

To verify what permissions a saved PAT has:
1. Open the user menu in ActionsManager
2. Check the token status — if it shows **Missing required permissions**, the token needs updated scopes
3. Generate a new token with the correct permissions and update it in ActionsManager

## GitHub App vs. PAT vs. OAuth

ActionsManager uses Personal Access Tokens and GitHub OAuth. It does not use GitHub Apps. If you see documentation about GitHub App installation, it does not apply to the self-hosted beta.

## Related Topics

- [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %}) — creating tokens with correct permissions
- [Common Errors]({% link troubleshooting/common-errors.md %}) — error messages and solutions
- [Token Handling]({% link security/token-handling.md %}) — token security and storage
