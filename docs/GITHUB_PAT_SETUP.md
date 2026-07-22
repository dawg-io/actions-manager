# GitHub Personal Access Token Setup

Use this guide when you want to sign in to Actions Manager with a GitHub Personal Access Token instead of configuring a GitHub OAuth App.

## When to Use a PAT

- **Fastest self-hosted setup** when you do not want to create an OAuth App
- **Local development or testing** where a direct token is simpler
- **Repository-scoped access** with fine-grained PATs
- **Short-lived credentials** that you can rotate regularly

OAuth remains supported for browser-based GitHub login. Actions Manager can use either method.

## Quick Self-Hosted Install with a PAT

1. Create a PAT using the steps below
2. Start Actions Manager with this Docker command:

```bash
# Generate a stable SECRET_KEY once and reuse it on every start:
# SECRET_KEY=$(openssl rand -hex 32)
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e INSTALLATION_MODE=self-hosted \
  -e SECRET_KEY=<your_generated_key> \
  ghcr.io/dawg-io/actions-manager:latest
```

3. Open `http://localhost:8080`
4. Choose **Sign in with Personal Access Token**
5. Paste the token and submit it

Do **not** place your personal PAT in the Docker command or `GITHUB_TOKEN` for normal sign-in. Start the container first, then enter the PAT in the UI so it is not exposed in shell history or config files.

The automated `install.sh` path still prompts for OAuth credentials today, so Docker run / Docker Compose is the fastest PAT-only path.

## Supported Token Types

- **Fine-grained personal access token** — recommended
- **Classic personal access token**

## Fine-Grained PAT Setup

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Select the owner and expiration date
4. Under **Repository access**, choose **Only select repositories**
5. Select every repository that Actions Manager should manage
6. Grant these minimum permissions:
   - **Metadata:** Read-only
   - **Contents:** Read and write
   - **Actions:** Read and write
   - **Pull requests:** Read and write if you use PR-based delivery
   - **Secrets:** Read and write if you manage repository secrets
   - **Variables:** Read and write if you manage repository variables
   - **Administration / rulesets:** only if you manage repository rulesets
7. Generate the token and copy it immediately

## Classic PAT Setup

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **Generate new token**
3. Choose an expiration date
4. Select the scopes required by the current Actions Manager implementation:
   - **repo** for private repository access and repository writes
   - **workflow** for workflow file updates
   - **read:org** for organization visibility and membership checks
   - **user:email** for the current permission validation flow
5. Generate the token and copy it immediately

## Log In with a PAT

1. Open Actions Manager
2. On the login screen, choose **Sign in with Personal Access Token**
3. Paste your fine-grained or classic PAT
4. Submit the form
5. Actions Manager validates the token with GitHub
6. If valid, the app signs you in and stores the token encrypted

For a screenshot walkthrough of the login screen and first-run flow, see the [First Workflow Walkthrough](https://actionsmanager.io/getting-started/first-workflow-walkthrough) in the documentation site, or the [First Workflow Walkthrough section](QUICK_START.md#first-workflow-walkthrough) in `docs/QUICK_START.md`.

## Manage a Saved PAT

After signing in, open the user menu to:

- **Test token**
- **Save token**
- **Replace token**
- **Remove token**

The UI never shows the raw token after you save it. It only shows masked states such as:

- **Not configured**
- **Configured**
- **Invalid or expired**
- **Missing required permissions**

## Credential Resolution Order

For GitHub API operations, Actions Manager resolves credentials in this order:

1. Use the **saved PAT** when one is configured
2. Fall back to the current **OAuth token** when no PAT is configured
3. Return an authentication error when neither credential is available

Removing a saved PAT returns the account to OAuth fallback behavior if an OAuth session exists.

## Troubleshooting

### Invalid Token

Possible causes:

- The token was mistyped
- The token was revoked
- The token expired
- The token format is not recognized

### Missing Repositories

Possible causes:

- A fine-grained PAT was created for only selected repositories
- The repository was not selected when the token was created
- Organization policy blocks token access
- Your GitHub user does not have access to that repository

### Missing Write Permissions

Possible causes:

- The fine-grained PAT is read-only
- **Contents** is not set to read/write
- **Pull requests** is missing for PR delivery
- **Actions** is missing for workflow file updates

### Organization Restrictions

Possible causes:

- The organization blocks fine-grained PATs
- The organization requires approval before the token can be used
- Organization policy prevents token access even when the user can browse the repository in GitHub

### Token Saved but OAuth Is Still Being Used

- Saved PATs are preferred over OAuth
- OAuth is used only when no saved PAT is configured
- Remove the saved PAT if you want to return to OAuth fallback

## Security Best Practices

- Treat PATs like passwords
- Never paste PATs into GitHub issues, logs, screenshots, or support requests
- Rotate the token immediately if it may have been exposed
- Prefer **fine-grained PATs** over classic PATs
- Prefer **expiration dates** over never-expiring tokens
