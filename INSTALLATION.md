# Self-Hosted Beta Installation

> **Beta notice:** ActionsManager Self-Hosted is currently a free beta preview for testing, evaluation, and feedback. No paid plans are currently available. The beta is self-hosted only and is provided as-is, without warranty, SLA, support guarantee, uptime guarantee, or production-readiness guarantee. You are responsible for securing your deployment, protecting GitHub credentials and local environment files, reviewing workflow changes, and backing up data.

## Overview

Use this guide to run ActionsManager as a **single self-hosted beta container** on **port 8080**.

You have two install options:
1. Docker Run
2. Docker Compose

Both options use the prebuilt image:

`ghcr.io/dawg-io/actions-manager:latest`

SQLite is the default database.

## Prerequisites

- Docker Engine with Docker Compose plugin
- A GitHub account
- A free port: `8080`

## GitHub Authentication Options

You can use either of these authentication methods:

1. **GitHub OAuth** (default) — configure a GitHub OAuth app and use the normal browser login flow
2. **GitHub personal access token** — sign in directly from the login screen with a fine-grained or classic PAT

Fine-grained PATs are recommended for self-hosted setups because they can be limited to selected repositories and short expiration windows.

For the fastest setup, use a PAT. OAuth remains available if you prefer browser-based GitHub login.

Detailed token guidance: [GitHub PAT Setup](docs/GITHUB_PAT_SETUP.md)

## Quick PAT Install (Recommended)

If you want the fastest self-hosted setup, you do **not** need a GitHub OAuth App.

1. Create a fine-grained or classic PAT using the steps in [GitHub PAT Setup](docs/GITHUB_PAT_SETUP.md)
2. Generate a stable secret key and store it somewhere safe (you will need the same value on every restart):

```bash
openssl rand -hex 32
```

3. Start ActionsManager with this Docker command for PAT-based login:

```bash
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e INSTALLATION_MODE=self-hosted \
  -e SECRET_KEY=<your_generated_key> \
  ghcr.io/dawg-io/actions-manager:latest
```

Replace `<your_generated_key>` with the output of the `openssl` command above.
**Use the same `SECRET_KEY` value every time you recreate the container.** Changing it will
invalidate any saved encrypted tokens.

4. Open `http://localhost:8080`
5. Choose **Sign in with Personal Access Token**
6. Paste the token and submit it

The app validates the token with GitHub, stores it encrypted, and uses the saved PAT for GitHub API calls.

Do **not** put your personal PAT on the Docker command line or in `GITHUB_TOKEN` for normal user login. Enter it in the UI after the container starts so it does not end up in shell history or deployment config.

> **Important:** The automated `install.sh` flow still prompts for OAuth credentials today. For a PAT-only quick install, use the Docker run or Docker Compose examples in this guide instead of the installer.

## Create a GitHub OAuth App

In GitHub, go to **Settings → Developer settings → OAuth Apps → New OAuth App** and use:

- **Application name:** `ActionsManager`
- **Homepage URL:** `http://localhost:8080`
- **Authorization callback URL:** `http://localhost:8080/auth/callback`

Then copy the generated:
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`

If you deploy on a real domain, update **both URLs** to that same domain.

## GitHub PAT Setup

### Create a Fine-Grained PAT

1. Go to **GitHub**
2. Open **Settings**
3. Open **Developer settings**
4. Open **Personal access tokens**
5. Choose **Fine-grained tokens**
6. Click **Generate new token**
7. Select the repositories ActionsManager should manage
8. Copy the token once and keep it secure
9. Open ActionsManager
10. Choose **Sign in with Personal Access Token**
11. Paste the token
12. Submit the form
13. After login, manage the saved token from the user menu

### Fine-Grained PAT Permissions

Minimum recommended permissions for repository workflow management:

- **Repository access:** select the repositories ActionsManager should manage
- **Contents:** Read and write
- **Actions:** Read and write
- **Pull requests:** Read and write
- **Metadata:** Read-only

Additional permissions when you use those features:

- **Secrets:** Read and write for repository secrets management
- **Variables:** Read and write for repository variables management
- **Administration / rulesets:** only when you manage rulesets

### Classic PAT Setup

Classic PATs are supported for compatibility. Use these scopes for the current implementation:

- **repo** for private repository access and repository writes
- **workflow** for modifying GitHub Actions workflow files
- **read:org** for organization visibility and membership checks
- **user:email** for the current permission validation flow

### PAT vs OAuth

**PAT**
- No OAuth App setup required
- Best for self-hosted installs and quick testing
- Token access is controlled directly in GitHub
- Fine-grained PATs are recommended where possible

**OAuth**
- Requires GitHub OAuth App client ID and secret
- Best for browser login
- Access follows the authenticated GitHub user
- Some organizations may require OAuth app approval

## Option 1: Docker Run

First generate a stable secret key and store it somewhere safe:

```bash
openssl rand -hex 32
```

Then run the container (replace `<your_generated_key>` with the output above):

```bash
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e INSTALLATION_MODE=self-hosted \
  -e SECRET_KEY=<your_generated_key> \
  ghcr.io/dawg-io/actions-manager:latest
```

**Always use the same `SECRET_KEY` value** when recreating or updating the container so that
saved encrypted tokens remain readable.

**For GitHub OAuth login**, add OAuth credentials and set the application URL:

```bash
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e INSTALLATION_MODE=self-hosted \
  -e SECRET_KEY=<your_generated_key> \
  -e APP_URL=http://YOUR_SERVER_IP_OR_DOMAIN:8080 \
  -e GITHUB_CLIENT_ID=your_github_client_id \
  -e GITHUB_CLIENT_SECRET=your_github_client_secret \
  ghcr.io/dawg-io/actions-manager:latest
```

Replace `YOUR_SERVER_IP_OR_DOMAIN` with the actual IP or domain users will access (not `localhost` for shared servers).

Optional:
- Omit OAuth credentials if you plan to sign in only with a GitHub PAT
- `LICENSE_KEY` is optional and reserved for future/commercial licensing behavior; no paid plans are currently available during beta

## Option 2: Docker Compose

Create `.env` (or `.env.self-hosted`) and set a stable secret key:

```bash
# Generate once and paste the output into your .env file
openssl rand -hex 32
```

Create `docker-compose.yml`:

```yaml
services:
  actions-manager:
    image: ghcr.io/dawg-io/actions-manager:latest
    container_name: actions-manager
    ports:
      - "8080:8080"
    environment:
      INSTALLATION_MODE: self-hosted
      SECRET_KEY: ${SECRET_KEY}
      # Optional: Set APP_URL for OAuth login (not needed for PAT login)
      # APP_URL: http://YOUR_SERVER_IP_OR_DOMAIN:8080
      # GITHUB_CLIENT_ID: your_github_client_id
      # GITHUB_CLIENT_SECRET: your_github_client_secret
    volumes:
      - actions-manager-data:/app/data
    restart: unless-stopped

volumes:
  actions-manager-data:
```

Add `SECRET_KEY=<your_generated_key>` to your `.env` file, then start:

```bash
docker compose up -d
```

For OAuth login, uncomment and configure `APP_URL`, `GITHUB_CLIENT_ID`, and `GITHUB_CLIENT_SECRET`.

## Environment Variables

| Variable | Required | Notes |
|---|---|---|
| `INSTALLATION_MODE` | Yes | Use `self-hosted` |
| `SECRET_KEY` | Yes | Encryption key for saved PATs; generate with `openssl rand -hex 32` |
| `APP_URL` | Recommended | Application URL (e.g., `http://192.168.1.100:8080`). Required for OAuth login. Also sets the allowed CORS origin — omitting it leaves CORS open to all origins (`*`), which allows cross-origin requests using any session token. Always set this for non-localhost deployments, even when using PAT login. |
| `GITHUB_CLIENT_ID` | No | GitHub OAuth client ID (required only for OAuth login) |
| `GITHUB_CLIENT_SECRET` | No | GitHub OAuth client secret (required only for OAuth login) |
| `LICENSE_KEY` | No | Optional self-hosted license key; no paid plans are currently available during beta |

For advanced configuration and architecture details, see [DOCKER_DEPLOYMENT_MODES.md](DOCKER_DEPLOYMENT_MODES.md) and [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md).

## First Login

{: .warning }
**⚠️ Security Warning:** The default installation uses HTTP on localhost, which is safe for local testing. **Never expose ActionsManager over plain HTTP on a network or to the internet.** Personal Access Tokens (PATs) and credentials will be transmitted in plaintext and can be intercepted. For any non-localhost deployment, use HTTPS with a reverse proxy. See [HTTPS setup examples](docs/SELF_HOSTED_INSTALL.md#using-https-with-reverse-proxy) for Caddy, Traefik, and nginx configurations. Starting from this version, ActionsManager blocks PAT login over non-local HTTP by default unless `ALLOW_INSECURE_HTTP=true` is set.

1. Open `http://localhost:8080`
2. Choose one of the available sign-in methods:
   - **Log in with GitHub** to use OAuth
   - **Sign in with Personal Access Token** to use a fine-grained or classic PAT
3. If using a PAT, paste the token and ActionsManager will validate it with GitHub
4. If valid, ActionsManager stores it encrypted and uses it for GitHub API calls

For a step-by-step screenshot walkthrough of the login screen, project creation, workflow creation, and saving the first local draft, see the [First Workflow Walkthrough](https://actionsmanager.io/getting-started/first-workflow-walkthrough) in the documentation site, or [docs/QUICK_START.md](docs/QUICK_START.md#first-workflow-walkthrough) in this repository.

### Recommended PAT Permissions

For a fine-grained PAT, start with:
- Metadata: read
- Contents: read/write
- Actions: read/write
- Pull requests: read/write if you use PR delivery
- Secrets: read/write only if you manage secrets
- Variables: read/write only if you manage variables
- Administration / rulesets only if you manage rulesets

Classic PAT guidance:
- `repo` for private repositories and write operations
- `workflow` for workflow file updates
- `read:org` for organization visibility or membership checks
- `user:email` for the current permission validation flow
- `public_repo` may be enough only for public-only usage, but it does not satisfy the full current classic PAT validation path

### PAT Troubleshooting

- Invalid or expired token → regenerate and save a new token
- Token format not recognized → verify you copied the full GitHub token value
- Missing repository access → add the repositories to the fine-grained PAT
- Repository missing from the PAT → recreate or update the fine-grained PAT with that repository selected
- Missing Contents write permission → update the PAT permissions
- Missing Pull requests write permission → required for PR-based delivery
- Missing Actions write permission → required for workflow file updates
- Organization blocks PAT access → ask an org admin to allow PAT usage or switch to OAuth
- Token saved but OAuth still appears in use → remove the saved PAT to return to OAuth fallback behavior when an OAuth session exists

### Security Reminders

- Never paste PATs into GitHub issues, logs, screenshots, or support requests
- Rotate the token if it may have been exposed
- Prefer fine-grained PATs with only the required repositories
- Prefer expiration dates over never-expiring tokens

## Updating

### Docker Run

```bash
docker pull ghcr.io/dawg-io/actions-manager:latest
docker rm -f actions-manager
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e INSTALLATION_MODE=self-hosted \
  -e SECRET_KEY=<same_key_as_before> \
  ghcr.io/dawg-io/actions-manager:latest
```

If you use GitHub OAuth login, add your `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and
`APP_URL` back to the command above — see [Option 1: Docker Run](#option-1-docker-run).

**Use the same `SECRET_KEY` you used when you first installed** — do not regenerate it.
Changing the key will invalidate all saved encrypted tokens and require users to re-authenticate.

### Docker Compose

```bash
docker compose pull
docker compose up -d
```

Your data persists automatically via the named volume. No other steps are required.

## Stopping

### Docker Run

```bash
docker stop actions-manager
```

### Docker Compose

```bash
docker compose down
```

## Troubleshooting

- **Container exits immediately:** run `docker logs actions-manager`
- **Port already in use:** pick another host port and update OAuth URLs to match
- **OAuth redirect mismatch:** callback must be exactly `http://localhost:8080/auth/callback`
- **Can't open UI:** confirm container is running with `docker ps`
- **Configuration validation errors:** The container runs in production mode by default and rejects unsafe settings. If you see errors about `DEBUG_MODE`, `USE_MOCK_RESPONSES`, or `ADMIN_USERNAME/ADMIN_PASSWORD`, ensure you're not setting these to development defaults. For local development with relaxed validation, add `-e ENVIRONMENT=development` to your docker run command or `ENVIRONMENT: development` to your compose file.
- **Data missing after image update:** ensure your volume is mounted to `/app/data` (not `/app/backend`). The SQLite database lives at `/app/data/actions_manager.db` inside the container. If you previously mounted `/app/backend`, see the migration note below.

### Migrating from an Earlier Beta Release

Earlier beta documentation showed volume mounts pointing to `/app/backend`:

```bash
-v actions-manager-data:/app/backend  # OLD — do not use
```

The correct persistent path is now `/app/data`:

```bash
-v actions-manager-data:/app/data     # CORRECT
```

If you have an existing installation that used the old `/app/backend` mount and want to
preserve your data, copy the database out of the old volume before switching mounts:

```bash
# 1. Start the container with the old volume to extract the database
docker run --rm -v actions-manager-data:/app/backend \
  ghcr.io/dawg-io/actions-manager:latest \
  cat /app/backend/test.db > /tmp/actions_manager_backup.db

# 2. Create a new volume and load the backup
docker run --rm -v actions-manager-new-data:/app/data \
  -v /tmp:/tmp \
  ghcr.io/dawg-io/actions-manager:latest \
  cp /tmp/actions_manager_backup.db /app/data/actions_manager.db

# 3. Update your docker run / compose to use the new volume name and /app/data mount
```

Alternatively, set `DATABASE_URL=sqlite:////app/backend/test.db` in `.env.self-hosted`
to keep using the old path until you are ready to migrate.

## Hardening Notes for Beta Operators

- ENVIRONMENT defaults to `production` with strict validation. Only use `ENVIRONMENT=development` for local testing.
- Use HTTPS behind a reverse proxy if exposing ActionsManager beyond localhost.
- Keep image tags pinned for controlled upgrades and update containers when beta fixes are published.
- Back up persistent data regularly, including the SQLite volume or PostgreSQL database.
- Keep `.env.self-hosted`, OAuth credentials, PATs, database files, backups, license keys, and optional API keys private. Never commit a real `.env` file.
- Prefer PR-based workflow delivery while evaluating the beta. Use direct commit mode only after carefully checking the target repository and branch.
