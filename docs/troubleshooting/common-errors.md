---
layout: default
title: Common Errors
parent: Troubleshooting
nav_order: 1
---

# Common Errors
{: .no_toc }

Quick reference for common errors and their solutions.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Authentication Errors

### "Invalid token" on sign-in

**Symptoms:** Signing in with a PAT returns an invalid token error.

**Causes:**
- Token was mistyped or contains extra whitespace
- Token has been revoked in GitHub
- Token has expired
- Token type is not recognized

**Solutions:**
1. Copy the token directly from GitHub — avoid retyping
2. Check the token status at **GitHub → Settings → Developer settings → Personal access tokens**
3. Generate a new token and try again

---

### "Sign in with GitHub" button not appearing

**Symptoms:** The OAuth login button is missing from the login page.

**Causes:** `GITHUB_CLIENT_ID` environment variable is not set or the container was not restarted after adding it.

**Solutions:**
1. Verify `GITHUB_CLIENT_ID` is set in your container environment
2. Restart the container to apply the new environment variable
3. Check container logs for OAuth configuration errors

---

### "Redirect URI mismatch"

**Symptoms:** After authorizing the GitHub OAuth App, GitHub returns a redirect URI mismatch error.

**Causes:** The `VITE_BACKEND_URL` environment variable does not match the callback URL registered in your GitHub OAuth App.

**Solutions:**
1. Check the Authorization callback URL in your GitHub OAuth App settings
2. Verify the `VITE_BACKEND_URL` environment variable matches exactly (including protocol and port)
3. Update the OAuth App or environment variable so they match

---

## API and Permission Errors

### "Not found" or missing repositories

**Symptoms:** Repositories are not visible or return 404 errors.

**Causes:**
- Fine-grained PAT was created with limited repository access
- The GitHub token does not have access to the repository
- The repository is in an organization with restricted token access

**Solutions:**
1. Check which repositories are authorized on the fine-grained PAT
2. Verify the signed-in GitHub account has access to the repository
3. For organization repositories, check if the organization has blocked token access

---

### "Insufficient permissions" on workflow operations

**Symptoms:** Creating, updating, or deleting workflows fails with a permission error.

**Causes:** The token is missing required permissions.

**Solutions:**
1. For fine-grained PATs, verify **Contents: Read and write** and **Actions: Read and write** are set
2. For classic PATs, verify the `repo` and `workflow` scopes are granted
3. Generate a new token with the correct permissions

---

## Workflow and PR Errors

### PR campaign creates no PRs

**Symptoms:** Starting a PR campaign completes without creating any pull requests.

**Causes:**
- No repositories in the project are configured
- The workflow is already up to date in all repositories
- The GitHub token lacks **Pull requests: Read and write** permission

**Solutions:**
1. Verify the project has repositories added
2. Check drift status — if all repositories are in sync, no PRs are needed
3. Verify the PAT has pull request permissions

---

### "Branch already exists" when creating campaign PRs

**Symptoms:** PR creation fails because the branch already exists.

**Causes:** A previous campaign created a branch that was never merged or deleted.

**Solutions:**
1. Check the repository on GitHub for open or abandoned campaign branches
2. Delete the old branch and retry the campaign
3. Or merge/close the existing PR first

---

## Next Steps

- [GitHub Permissions]({% link troubleshooting/github-permissions.md %}) — GitHub permission requirements in detail
- [Container Startup]({% link troubleshooting/container-startup.md %}) — container startup and health issues
