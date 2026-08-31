# Docker Compose Deployment Modes

This document describes deployment-mode separation for Actions Manager. The first public beta is **Self-Hosted only**. Cloud/SaaS and GitHub Marketplace billing references are retained for future planning/internal validation and are not active beta offerings.

> For first-time self-hosted beta setup, use the simplified install guide: **[INSTALLATION.md](INSTALLATION.md)**.

## Build Separation Summary (Beta Release Readiness)

The Cloud and Self-hosted releases are produced and validated as **two separate
builds** with different startup rules. The split is enforced by
`backend/mode_validation.py` and verified by `scripts/validate_release.py`.

| Topic | Cloud build | Self-hosted build |
|-------|-------------|--------------------|
| Compose file | `docker-compose.cloud.yml` | `docker-compose.self-hosted.yml` |
| Env template | `.env.cloud.example` | `.env.self-hosted.example` |
| `INSTALLATION_MODE` | `cloud` | `self-hosted` |
| `ENVIRONMENT` | Future production-only cloud hardening | `production` recommended; `development` only for local testing |
| Billing source of truth | Future GitHub Marketplace + verified webhook | Free during beta; optional future `LICENSE_KEY` behavior |
| Database | PostgreSQL (required) | SQLite (default) or PostgreSQL |
| Self-hosted license-key variables | **Refused at startup** | `LICENSE_KEY` optional |
| Tier override env vars (`ACCOUNT_TYPE`, `TIER`, `PLAN`, `FORCE_TIER`, `OVERRIDE_TIER`) | **Refused at startup** | **Refused at startup** |
| `USE_MOCK_RESPONSES=true`, `USE_STUBBED_MARKETPLACE_API=true`, `DEBUG_MODE=true` | **Refused at startup** | Allowed only with `ENVIRONMENT=development` |
| `GITHUB_WEBHOOK_SECRET` | Required | Not required |
| Default admin credentials | **Refused at startup** | Refused in `production`; allowed in `development` |
| Missing/invalid license behaviour | N/A | Falls back to Free tier |

If a cloud deployment is misconfigured the backend prints every violation to
stderr and exits with code `2` so the orchestrator restarts (or alerts) instead
of running with weakened billing/security guarantees.

> **Note:** `ACTIONS_MANAGER_SKIP_MODE_VALIDATION` is honored only when
> `INSTALLATION_MODE=self-hosted` **and** `ENVIRONMENT=development`. It is
> ignored in cloud mode and in self-hosted production.

## Overview

ActionsManager supports two distinct deployment configurations optimized for different use cases:

| Aspect | Self-Hosted | Cloud |
|--------|-------------|-------|
| **Containers** | 1 (combined) | 2 (separate backend + frontend) |
| **Ports** | 8080 only | 3000 (frontend) + 8000 (backend) |
| **Installation** | Simple - one container | Standard - two containers |
| **Marketplace** | No | Yes |
| **Database** | SQLite (default) or PostgreSQL | PostgreSQL (required) |
| **Licensing** | Free during beta; optional license-key code path for future use | Future GitHub Marketplace billing |
| **Target Users** | Beta testers, small teams, individuals | Future SaaS providers/internal validation |

---

## Self-Hosted Deployment

### Architecture

The self-hosted deployment uses a **single container** that combines both frontend and backend:

```
┌─────────────────────────────────────────┐
│      Single Container (Port 8080)        │
├─────────────────────────────────────────┤
│  ┌─────────────────────────────────┐   │
│  │       Nginx (Port 8080)          │   │
│  │  - Serves frontend static files  │   │
│  │  - Proxies API requests          │   │
│  │  - Handles WebSocket routing     │   │
│  └──────────┬──────────────────────┘   │
│             │ proxies to               │
│             ↓                           │
│  ┌─────────────────────────────────┐   │
│  │   FastAPI Backend (Port 8000)    │   │
│  │  - Python/FastAPI application    │   │
│  │  - SQLite database (default)     │   │
│  │  - License-based tier management │   │
│  └─────────────────────────────────┘   │
│                                          │
│  Frontend build served as static files  │
└─────────────────────────────────────────┘
```

### Key Features

✅ **Simplified Installation**
- Single `docker compose` command
- One container to manage
- No port conflicts
- Official GHCR self-hosted image supports `linux/amd64` and `linux/arm64`

✅ **Single Port**
- Everything on port 8080
- Easier firewall configuration
- Simpler reverse proxy setup
- Compatible with rootless Podman

✅ **Built-in Nginx**
- Serves frontend efficiently
- API request proxying
- WebSocket support

✅ **Flexible Database**
- SQLite by default (no setup needed)
- Optional PostgreSQL for larger deployments

✅ **Beta Availability**
- Free during beta
- No paid plans currently available
- Optional license-key code path exists for future/commercial behavior
- No marketplace dependencies for self-hosted beta

### Files

- `Dockerfile.self-hosted` - Multi-stage Dockerfile combining frontend and backend
- `docker-compose.self-hosted.yml` - Single service configuration
- `.env.self-hosted.example` - Environment template without marketplace variables

### Deployment Commands

```bash
# Use INSTALLATION.md for the supported first-run commands:
# - Option 1: Docker Run
# - Option 2: Docker Compose
# This document is architecture/reference only.
```

### Environment Variables

Required:
- `INSTALLATION_MODE=self-hosted`
- `GITHUB_CLIENT_ID` - GitHub OAuth app client ID
- `GITHUB_CLIENT_SECRET` - GitHub OAuth app client secret
- `VITE_BACKEND_URL=http://localhost:8080`
- `VITE_FRONTEND_URL=http://localhost:8080`

Optional:
- `LICENSE_KEY` - optional self-hosted license key; no paid plans are currently available during beta
- `DATABASE_URL` - PostgreSQL connection (defaults to SQLite)

### OAuth Configuration

Register GitHub OAuth app with:
- **Homepage URL**: `http://localhost:8080` (or your domain)
- **Callback URL**: `http://localhost:8080/auth/callback`

---

## Cloud Deployment (Future / Not Part of Self-Hosted Beta)

> **Development-repository reference.** The cloud build is not part of the
> public self-hosted distribution, and neither is the tooling this section
> walks through. `deployment/`, `docker-compose.cloud.yml`,
> `.env.cloud.example` and `.github/workflows/` are all removed when a
> release is promoted to the public repository, so the paths below resolve
> only in the private development repository. Self-hosted operators want
> [INSTALLATION.md](INSTALLATION.md) and the Self-Hosted Deployment section
> above instead.

### Architecture

The cloud deployment uses **two separate containers** for scalability:

```
┌─────────────────────────────────────────┐
│      Frontend Container (Port 3000)      │
├─────────────────────────────────────────┤
│  - React development server              │
│  - Node.js environment                   │
│  - Hot reload for development            │
└──────────────┬──────────────────────────┘
               │ calls API
               ↓
┌─────────────────────────────────────────┐
│       Backend Container (Port 8000)      │
├─────────────────────────────────────────┤
│  - FastAPI application                   │
│  - PostgreSQL database (required)        │
│  - GitHub Marketplace webhooks           │
│  - Webhook signature verification        │
│  - Multi-tenant support                  │
└─────────────────────────────────────────┘
```

### Key Features

✅ **Marketplace Integration**
- GitHub Marketplace billing webhooks
- Automatic subscription management
- Usage-based pricing support

✅ **Scalable Architecture**
- Separate frontend and backend
- Independent scaling
- Load balancing support

✅ **Enhanced Security**
- Webhook signature verification (HMAC SHA-256)
- IP address verification
- Rate limiting

✅ **PostgreSQL Required**
- Multi-tenant data isolation
- Better performance at scale
- Advanced features

⚠️ **Not a beta offering**
- Cloud/SaaS and Marketplace billing are future/planning paths
- No hosted service, paid plan, Marketplace listing, SLA, or uptime guarantee is included in the self-hosted beta
- Any future cloud launch requires separate release, security, privacy, and legal review

### Files

- `backend/Dockerfile` - Backend container
- `frontend/Dockerfile` - Frontend container
- `docker-compose.cloud.yml` - Two service configuration
- `.env.cloud.example` - Environment template with marketplace variables

### Deployment Commands

```bash
# Copy and configure environment
cp .env.cloud.example .env.cloud
# Edit .env.cloud with production settings

# Build and start
docker compose -f docker-compose.cloud.yml up --build

# Access application
http://localhost:3000 (frontend)
http://localhost:8000 (API/docs)
```

### Environment Variables

Required:
- `INSTALLATION_MODE=cloud`
- `GITHUB_CLIENT_ID` - GitHub OAuth app client ID
- `GITHUB_CLIENT_SECRET` - GitHub OAuth app client secret
- `GITHUB_WEBHOOK_SECRET` - Secret for webhook signature verification
- `DATABASE_URL` - PostgreSQL connection string
- `VITE_BACKEND_URL` - Backend API URL
- `VITE_FRONTEND_URL` - Frontend URL

Security (Recommended):
- `VERIFY_WEBHOOK_IP=true` - Enable IP verification
- `GITHUB_WEBHOOK_IPS` - Comma-separated CIDR ranges
- `WEBHOOK_RATE_LIMIT=60` - Requests per minute

### OAuth Configuration

Register GitHub OAuth app with:
- **Homepage URL**: `https://yourdomain.com`
- **Callback URL**: `https://api.yourdomain.com/auth/callback`

### Local/VM Dev-Test Setup (No Kubernetes)

For a disposable dev/test instance of the cloud build on a plain Docker
Compose host (VM or workstation) — no Kubernetes, no external database to
hand-wire:

```bash
# 1. Add a local Postgres service via the example override
#    (the copy must land at repo root — the cloud compose file's build
#    contexts and env file are root-relative)
cp deployment/docker/docker-compose.cloud.override.example.yml docker-compose.override.yml

# 2. Configure environment
cp .env.cloud.example .env.cloud
# Edit .env.cloud — see minimum values below

# 3. Start from repo root (both -f flags are required: Compose does not
#    auto-merge docker-compose.override.yml once -f is used for another file)
docker compose -f docker-compose.cloud.yml -f docker-compose.override.yml \
  --env-file .env.cloud up --build -d
```

Minimum `.env.cloud` values for a from-scratch throwaway test:
- `INSTALLATION_MODE=cloud`
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` — from a throwaway GitHub OAuth App
- `GITHUB_WEBHOOK_SECRET` — any random value; only needs to satisfy startup validation on a dev/test box
- `DATABASE_URL` — pointing at the override's `postgres` service by name, e.g. `postgresql://actions_manager_dev:actions_manager_dev_only@postgres:5432/actions_manager`

This is dev/test tooling only. It does not change self-hosted beta behavior
and is not part of any release process.

### Cloud Dev Deployment Node

The long-lived internal cloud dev/staging environment runs as a Docker Compose
stack on the `deployment-host` self-hosted runner. It replaces the Kubernetes
cluster that Flux used to reconcile, which was decommissioned in PR #1956.

`.github/workflows/docker-images.yml` → `deploy-cloud-dev` redeploys it after
`build-cloud-images` publishes new `dev-backend` / `dev-frontend` images — on
PRs targeting `develop`, and on `workflow_dispatch` for a manual redeploy. The
node holds a single stack on one Postgres volume, so concurrent deploys would
fight over it; the job does not yet serialise itself with a `concurrency:`
group.

The compose file is `deployment/docker/docker-compose.cloud.deploy.yml`. Unlike
`docker-compose.cloud.yml` it never builds from source: it pulls the already-
published images by tag, so what runs on the node is exactly what CI pushed.

**Host provisioning (one-time, by hand).** Secrets are never committed to this
repo or stored as Actions secrets — the stack reads them from a file on the
node:

```bash
sudo mkdir -p /opt/actions-manager-cloud
sudo cp .env.cloud.example /opt/actions-manager-cloud/.env.cloud
sudo chmod 600 /opt/actions-manager-cloud/.env.cloud
# Then edit it — see the values below.
```

The deploy job fails with a pointer to this section if that file is missing.

**Deploying to a remote Docker host.** `deployment-host` is a runner *label*,
and it may well sit on the same machine as `pmox-runner` — adding the label
moves nothing by itself. What decides where the stack lands is
`CLOUD_DOCKER_HOST`: the runner is only the agent that drives a Docker daemon
somewhere else.

That daemon should not be the runner's own, because the runner's post-job
cleanup hook prunes containers and networks and will tear the stack down
between deploys. Point the job at a separate Docker host with these repository
variables (Settings → Secrets and variables → Actions → Variables):

| Variable | Example | Effect |
|---|---|---|
| `CLOUD_DOCKER_HOST` | `ssh://deploy@deploy-host.example.com` | **Required.** Sets `DOCKER_HOST` for every compose call. The job refuses to run without it |
| `CLOUD_HEALTH_HOST` | `deploy-host.example.com` | Host the post-deploy health checks curl. Optional — derived from `CLOUD_DOCKER_HOST` when absent |

Neither is a secret (they are hostnames), so they belong in Variables, not
Secrets.

Create `CLOUD_HEALTH_HOST` only when the daemon is reachable at a different
address than the published ports — behind NAT, split-horizon DNS, or an SSH
bastion. Otherwise **do not create the variable at all**: GitHub will not
accept an empty variable value, but an undefined variable renders as the empty
string, which is what the job's derivation expects. If you would rather have it
defined anyway, set it to the Docker host's address — that is exactly what the
derivation produces.

Set `CLOUD_DOCKER_HOST` as either a repository **Variable** or a repository
**Secret** — the job reads `vars.CLOUD_DOCKER_HOST || secrets.CLOUD_DOCKER_HOST`
and takes whichever is non-empty. A plain hostname is naturally a Variable, but
an internal `ssh://user@host` does reveal infrastructure, so a Secret is a
defensible choice; note that it then prints as `***` in the log, and the
`Deploying onto:` line from `docker info` becomes the way to confirm the
target. What does *not* work is an **Environment**-scoped entry, which
resolves as empty unless the job declares `environment:`.

The job refuses to run when it resolves empty, rather than falling back to the
runner's own daemon — that would deploy onto the wrong machine and still report
success.

For `ssh://`, the runner's user needs key-based SSH to that host and a
`known_hosts` entry for it; the job fails early with that hint if `docker
version` cannot reach the daemon. The job prints the daemon URL, the runner's
hostname, and `docker info`'s node name before deploying, so the target is
visible in the log. Note that `.env.cloud` still lives on the
**runner**, not the remote host — Compose resolves `env_file` client-side.

Values the node needs beyond `.env.cloud.example`'s defaults:

| Variable | Why |
|---|---|
| `APP_URL` | The node's reachable URL, e.g. `http://<node-host>:3100` — not in the template, add it |
| `VITE_BACKEND_URL` / `VITE_FRONTEND_URL` | Public URLs; the backend builds the OAuth `redirect_uri` from `VITE_BACKEND_URL` (`auth.py:67`, `auth.py:1181`) |
| `ALLOW_INSECURE_HTTP=true` | Required for non-loopback plain HTTP (see `backend/mode_validation.py`) — not in the template, add it. Unnecessary behind TLS |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | OAuth App whose callback URL matches `VITE_BACKEND_URL` |

The database needs **nothing**. The bundled `db` service defaults to
`actions_manager` / `actions_manager_dev_only` / `actions_manager`, and the
backend's `DATABASE_URL` defaults to match, so a deploy works with none of the
`POSTGRES_*` variables set. That password is not a secret in any meaningful
sense: the service publishes no port and is reachable only from inside the
compose network.

To use a different database, set `DATABASE_URL` in the env file and it wins.
If you instead want the bundled Postgres under different credentials, set the
`POSTGRES_*` variables **and** a matching `DATABASE_URL` — the four move
together, and overriding only some of them fails authentication. Note also
that these are read only when the data directory is first created: changing
them against an existing `cloud_dev_postgres_data` volume leaves the stored
role untouched, so use `ALTER USER` or recreate the volume.

Avoid `$` in any of these values — the deploy passes the env file to
`docker compose --env-file`, which treats `$` as the start of a substitution.

Optional overrides, all with working defaults:

| Variable | Default | Why change it |
|---|---|---|
| `CLOUD_FRONTEND_PORT` | `3100` | Defaults avoid `3000`/`8000`, which `health-check.yml` and the |
| `CLOUD_BACKEND_PORT` | `8100` | Playwright jobs bind on the same infra |
| `CLOUD_ENV_FILE` | `/opt/actions-manager-cloud/.env.cloud` | Env file location |
| `CLOUD_IMAGE_REPO` | `ghcr.io/dawg-io/actions-manager` | Pulling from a different registry path |

Note that cloud-mode startup validation is still relaxed
(`_CLOUD_PRELAUNCH_RELAXED = True` in `backend/mode_validation.py`), so this
node may run with stubbed Marketplace calls — that flag exists precisely for
this environment. Only the tier-bypass guards are enforced today.

To operate the stack by hand on the node:

```bash
cd /path/to/actions-manager
IMAGE_TAG=<tag> docker compose -p actions-manager-cloud \
  -f deployment/docker/docker-compose.cloud.deploy.yml ps
```

This node is internal dev/test infrastructure. It is not a hosted service, and
nothing about it is part of the self-hosted beta or any release process.

---

## Migration Between Modes

### Self-Hosted → Cloud

1. Export data from SQLite (if using SQLite)
2. Set up PostgreSQL database
3. Update environment variables to cloud mode
4. Configure GitHub Marketplace app
5. Set up webhook secret
6. Deploy with `docker-compose.cloud.yml`

### Cloud → Self-Hosted

1. Export subscription data (for reference)
2. Generate license keys for users
3. Update environment variables to self-hosted mode
4. Optional: Migrate to SQLite for simplicity
5. Deploy with `docker-compose.self-hosted.yml`

---

## Hardening Recommendations for Beta Operators

### Self-Hosted

- [ ] Change default `ADMIN_PASSWORD`
- [ ] Use HTTPS with SSL/TLS certificate (update port 80 → 443)
- [ ] Set up regular backups (SQLite or PostgreSQL)
- [ ] Configure monitoring and logging
- [ ] Update OAuth callback URL to production domain
- [ ] Consider PostgreSQL for >100 concurrent users

### Future Cloud/SaaS

Cloud/SaaS hardening, Marketplace billing, support terms, privacy terms, and production readiness must be reviewed separately before any hosted or paid launch.

---

## Troubleshooting

### Self-Hosted

**Container won't start:**
- Check logs: `docker compose -f docker-compose.self-hosted.yml logs`
- Verify port 8080 is available
- Check .env.self-hosted file exists

**Can't access application:**
- Verify container is running: `docker compose -f docker-compose.self-hosted.yml ps`
- Check firewall rules for port 8080
- Review nginx logs in container

**`no image found in image index for architecture arm64` when pulling:**
- Pull the latest image again so Docker refreshes manifest metadata:
  `docker compose -f docker-compose.self-hosted.yml pull`
- Then restart with the refreshed image:
  `docker compose -f docker-compose.self-hosted.yml up -d`

**GitHub OAuth error: "The redirect_uri is not associated with this application":**

This error means your GitHub OAuth App's callback URL doesn't match what the application is using.

**Solution:**
1. Go to GitHub Settings → Developer settings → OAuth Apps
2. Find your OAuth application
3. Update the **Authorization callback URL** to: `http://localhost:8080/auth/callback`
4. Also update **Homepage URL** to: `http://localhost:8080`
5. Save changes
6. Rebuild your container: `docker compose -f docker-compose.self-hosted.yml up --build`

**Common mistakes:**
- Using `http://localhost:8000/auth/callback` (local dev port, not Docker port)
- Using `http://localhost:3000` (frontend dev port, not combined container port)
- Missing `/auth/callback` path in the callback URL
- Using `https://` instead of `http://` for localhost

**Build fails with "out of memory" error (Podman/Docker):**

This typically occurs during the frontend build stage. Solutions:

1. **Increase container memory** (Recommended):
   ```bash
   # Docker Desktop: Settings → Resources → Memory (set to 4GB+)
   # Podman on macOS: 
   podman machine stop
   podman machine set --memory 4096
   podman machine start
   ```

2. **Reduce Node.js memory usage** (already configured in Dockerfile):
   - The Dockerfile sets `NODE_OPTIONS="--max-old-space-size=4096"`
   - For systems with <4GB RAM, edit Dockerfile.self-hosted line 9:
     ```dockerfile
     ENV NODE_OPTIONS="--max-old-space-size=2048"
     ```

3. **Use Docker instead of Podman** (if issues persist):
   ```bash
   docker compose -f docker-compose.self-hosted.yml up --build
   ```

4. **Pre-build frontend separately** (workaround):
   ```bash
   cd frontend
   npm install
   CI=false GENERATE_SOURCEMAP=false npm run build
   cd ..
   # Then build container (will use cached build)
   docker compose -f docker-compose.self-hosted.yml up --build
   ```

### Cloud

**Backend/Frontend connection issues:**
- Verify `VITE_BACKEND_URL` is correct
- Check CORS configuration
- Ensure both containers are on same network

**Webhook verification fails:**
- Verify `GITHUB_WEBHOOK_SECRET` matches GitHub settings
- Check webhook signature in logs
- Confirm IP verification settings if enabled

---

## Summary

Choose **Self-Hosted** for:
- Small teams (< 10 users)
- Simple installation requirements
- Single-tenant deployments
- License-based billing preference
- Limited DevOps resources

Choose **Cloud** for:
- Multi-tenant SaaS deployments
- GitHub Marketplace integration
- Scalability requirements
- Advanced monitoring needs
- Professional DevOps team
