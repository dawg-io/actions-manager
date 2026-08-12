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
