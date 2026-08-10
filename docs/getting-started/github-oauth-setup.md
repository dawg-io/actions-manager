---
layout: default
title: GitHub OAuth Setup
parent: Getting Started
nav_order: 4
---

# GitHub OAuth Setup
{: .no_toc }

Configure GitHub OAuth App for browser-based GitHub login.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## When to Use OAuth

- You prefer the standard **Sign in with GitHub** browser flow
- Your team members will log in with their own GitHub accounts
- Your organization manages app access through GitHub OAuth App approvals

For the fastest single-user setup, a [Personal Access Token]({% link getting-started/github-pat-setup.md %}) may be simpler.

## Step 1: Create a GitHub OAuth App

1. Go to **GitHub → Settings → Developer settings → OAuth Apps**
2. Click **New OAuth App**
3. Fill in the application details:

| Field | Value |
|-------|-------|
| Application name | `ActionsManager` (or your preferred name) |
| Homepage URL | `http://localhost:8080` (or your deployment URL) |
| Authorization callback URL | `http://localhost:8080/auth/callback` |

4. Click **Register application**
5. Copy the **Client ID**
6. Click **Generate a new client secret** and copy the **Client Secret**

{: .important }
If you deploy ActionsManager on a real domain (e.g., `https://actions.example.com`), update **both** the Homepage URL and Authorization callback URL to that domain before registering.

## Step 2: Configure the Container

Pass the OAuth credentials as environment variables when starting ActionsManager:

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
  -e VITE_BACKEND_URL=http://localhost:8080 \
  -e VITE_FRONTEND_URL=http://localhost:8080 \
  -e VITE_WEBSOCKET_URL=ws://localhost:8080/ws \
  -e GITHUB_CLIENT_ID=your_client_id \
  -e GITHUB_CLIENT_SECRET=your_client_secret \
  ghcr.io/dawg-io/actions-manager:latest
```

`ALLOW_INSECURE_HTTP=true` is required because these URLs are plain HTTP; drop it once you register HTTPS URLs and put ActionsManager behind a TLS reverse proxy — see [HTTPS Setup]({% link getting-started/https-setup.md %}).

Or in Docker Compose (using a `.env` file):

```yaml
environment:
  - ALLOW_INSECURE_HTTP=true
  - GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}
  - GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}
```

{: .warning }
Never commit your `GITHUB_CLIENT_SECRET` to source control. Use environment variables, a `.env` file that is excluded from git, or a secrets manager.

## Step 3: Sign In with GitHub

1. Open `http://localhost:8080`
2. Click **Sign in with GitHub**
3. GitHub redirects to the authorization page
4. Authorize the OAuth App
5. GitHub redirects back to ActionsManager

## Using Both OAuth and PAT

You can use OAuth login AND save a Personal Access Token for API operations:

- OAuth provides the browser login session
- The saved PAT is used for GitHub API calls (workflow management, PR creation, etc.)
- If a PAT is saved, it takes precedence over the OAuth token for API operations

See [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %}) for PAT management.

## Troubleshooting OAuth Issues

**Redirect URI mismatch:** The `VITE_BACKEND_URL` environment variable must exactly match the Homepage URL registered in your GitHub OAuth App. Update both if you change deployment URLs.

**OAuth App requires approval:** Some GitHub organizations require OAuth Apps to be approved by an organization admin before members can authorize them.

**Sign in button not appearing:** Check that `GITHUB_CLIENT_ID` is set and the container was restarted after adding it.
