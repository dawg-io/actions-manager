# ActionsManager Self-Hosted Beta Installation Guide

> **Beta notice:** ActionsManager Self-Hosted is currently a free beta preview for testing, evaluation, and feedback. No paid plans are currently available. The beta is self-hosted only and is provided as-is, without warranty, SLA, support guarantee, uptime guarantee, or production-readiness guarantee. Operators are responsible for securing their deployment, protecting credentials and `.env` files, reviewing workflow changes, and backing up data.

For the supported first-run path, prefer [../INSTALLATION.md](../INSTALLATION.md). This longer guide is retained as a detailed reference.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Installation Methods](#installation-methods)
5. [Post-Installation Setup](#post-installation-setup)
6. [Account Tiers](#account-tiers)
7. [Configuration Options](#configuration-options)
8. [Upgrading](#upgrading)
9. [Troubleshooting](#troubleshooting)
10. [Maintenance](#maintenance)
11. [Production Deployment](#production-deployment)
12. [Uninstalling](#uninstalling)
13. [Additional Resources](#additional-resources)
14. [Glossary](#glossary)

---

## Overview

### What is Self-Hosted Deployment?

Self-hosted deployment means running ActionsManager.io on your own servers or infrastructure. You maintain complete control over the application, data, and security. This may be useful for:

- **Teams and organizations** wanting to evaluate GitHub Actions workflow management on their own infrastructure
- **Data residency evaluation** where operators need local control over beta data
- **Air-gapped environments** with limited internet access
- **Cost optimization** for high-volume usage
- **Integration** with internal systems and platforms

### Key Features of Self-Hosted ActionsManager.io

✅ **Complete Control**
- Full control over data and infrastructure
- No dependency on external SaaS providers
- Full customization options

✅ **Operator-controlled deployment**
- Data stays on infrastructure you control unless you configure external integrations
- No documented product telemetry or phone-home behavior for the self-hosted beta
- You are responsible for hardening and access controls

✅ **Beta scope**
- Free during beta
- No paid plans are currently available
- Features, limits, and license behavior may change before GA
- Optional PostgreSQL for larger evaluations

✅ **Simple Deployment**
- Single container deployment via Docker/Podman
- Automated installation script
- Everything runs in a single port (8080)

---

## Architecture

### System Architecture

ActionsManager.io self-hosted uses a single-container deployment model:

```
┌─────────────────────────────────────────────────────────────┐
│              Self-Hosted Instance (Port 8080)                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Nginx Reverse Proxy (8080)                 │ │
│  │  • Serves static frontend files                         │ │
│  │  • Routes API requests to backend                       │ │
│  │  • Manages WebSocket connections (/ws)                 │ │
│  │  • TLS/SSL termination (optional, in production)        │ │
│  └────────┬─────────────────────────────────────────────┘ │
│           │                                                 │
│           │ proxies to                                      │
│           ↓                                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         FastAPI Backend (Internal 8000)                 │ │
│  │  • Python/FastAPI application                           │ │
│  │  • GitHub OAuth / PAT authentication                    │ │
│  │  • Workflow management                                  │ │
│  │  • License validation (JWT-based)                       │ │
│  │  • WebSocket real-time updates                          │ │
│  └────────┬─────────────────────────────────────────────┘ │
│           │                                                 │
│           │                                                 │
│           ↓                                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │           Database (SQLite or PostgreSQL)               │ │
│  │  • SQLite: Embedded, no setup required                  │ │
│  │  • PostgreSQL: Separate container, better performance   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Component Details

| Component | Purpose | Technology |
|-----------|---------|-----------|
| **Nginx** | HTTP server, reverse proxy, static file serving | Nginx 1.24 |
| **Backend** | Core application logic, API endpoints, OAuth | FastAPI (Python) |
| **Database** | Persistent data storage | SQLite (default) or PostgreSQL |
| **Frontend** | User interface, real-time updates | React with TypeScript |

---

## Prerequisites

### System Requirements

**Operating System:**
- Linux (Ubuntu 20.04+, Debian 11+, RHEL 8+, CentOS 8+, or compatible)
- macOS 11+ (Big Sur or later)

**Hardware (Minimum):**
- 2 CPU cores
- 4GB RAM
- 10GB disk space

**Hardware (Recommended):**
- 4+ CPU cores
- 8GB+ RAM
- 20GB+ disk space
- SSD for better I/O performance

### Required Software

#### Container Runtime (Required)

**Option 1: Docker**
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# macOS
brew install docker
# Run Docker Desktop from Applications or: colima start

# Verify installation
docker --version
docker compose version
```

**Option 2: Podman**
```bash
# Ubuntu/Debian
sudo apt-get install podman podman-compose

# macOS
brew install podman podman-compose

# Verify installation
podman --version
podman-compose --version
```

**System Tools:**
```bash
# curl - for downloading and health checks
curl --version

# git - optional but recommended
git --version
```

### GitHub Authentication Setup

Choose one of these authentication methods:

- **Personal Access Token (recommended for fastest setup)** — sign in directly from the login screen
- **GitHub OAuth App** — optional browser-based OAuth login

For PAT setup, see [GitHub PAT Setup](GITHUB_PAT_SETUP.md).

#### Optional GitHub OAuth App Setup

1. Go to [GitHub Settings > Developer settings > OAuth Apps](https://github.com/settings/developers)
2. Click "New OAuth App"
3. Fill in the application details:
   - **Application name**: `ActionsManager.io` (or your preferred name)
   - **Homepage URL**: `http://YOUR_SERVER_IP_OR_DOMAIN:8080` — use the IP/domain your users will type in their browser
   - **Authorization callback URL**: `http://YOUR_SERVER_IP_OR_DOMAIN:8080/auth/callback`
   - **Application description**: (optional) `Self-hosted GitHub Actions workflow manager`
4. Click "Register application"
5. Copy the **Client ID** and generate a **Client Secret**
6. Keep these credentials safe - you'll need them during installation

> ⚠️ **Critical:** The **Authorization callback URL** must **exactly** match your configured `APP_URL` plus `/auth/callback` (or `VITE_BACKEND_URL` + `/auth/callback` if you use the advanced per-service variables). Use the actual server IP or domain — **not** `localhost` unless every user runs the container on their own machine.

> **Note:** PAT (Personal Access Token) login does **not** require an OAuth App and works with zero URL configuration thanks to auto-detection.

### Network Requirements

**Outbound Access:**
- GitHub API (api.github.com) on port 443
- GitHub OAuth servers
- **GitHub Container Registry (ghcr.io) on port 443** — required to pull the official self-hosted image. Air-gapped installs can mirror the image to an internal registry and point `ACTIONS_MANAGER_IMAGE` at it.

**Inbound Access:**
- Port 8080 (or custom port) must be accessible to users
- Behind firewall/NAT is fine with appropriate port forwarding

---

## Installation Methods

### Method 1: Automated Installation (Recommended)

The automated installer guides you through all setup steps interactively.

#### Quick Install (One Command)

```bash
curl -fsSL https://raw.githubusercontent.com/dawg-io/actions-manager/main/install.sh | bash
```

#### Install with More Control

```bash
# Clone the repository
git clone https://github.com/dawg-io/actions-manager.git
cd actions-manager

# Run the installer
./install.sh
```

#### What the Installer Does

✅ Validates OS (Linux/macOS)
✅ Checks Docker/Podman installation
✅ Verifies system dependencies (curl, git)
✅ Prompts for port configuration
✅ Guides through GitHub OAuth setup
✅ Handles optional license key configuration
✅ Creates secure admin credentials
✅ Generates random SECRET_KEY
✅ Creates `.env.self-hosted` configuration
✅ **Pulls the official pre-built image** from GHCR (no local build required)
✅ Starts the application
✅ Displays access information

> **Contributors:** if you want to build the image from local source instead
> of pulling from GHCR, run `./install.sh --build`. The installer will then
> layer `docker-compose.self-hosted.dev.yml` on top of the release compose
> file and build `Dockerfile.self-hosted` locally. This is **not** the
> recommended flow for end users.

#### Interactive Prompts

When you run the installer, you'll be asked:

**1. Port Selection**
```
Port [default: 8080]:
```
Press Enter for default or enter a custom port (1-65535).

**2. GitHub OAuth Configuration**
```
GitHub Client ID:
GitHub Client Secret: [hidden input]
```
Paste your OAuth credentials from the GitHub app settings.

**3. License (Optional)**
```
License Key (optional):
License Key only; no signing secret is required for customers
```
Leave blank for free tier. Enter your license key if you have one.

**4. Admin Credentials**
```
Admin Username [default: admin]:
Admin Password: [hidden input]
Confirm Admin Password: [hidden input]
```
Set credentials for admin panel access.

#### After Installation

Once complete, you'll see:

```
============================================================
✓ ActionsManager.io Successfully Installed!
============================================================

Access your instance at:
  🌐 Web Interface:    http://localhost:8080
  📚 API Docs:         http://localhost:8080/docs
  ⚙️  Admin Panel:      http://localhost:8080/admin

Next steps:
  1. Open http://localhost:8080 in your browser
  2. Choose a sign-in method:
     - Log in with GitHub (OAuth)
     - Sign in with Personal Access Token
  3. If using OAuth, authorize the OAuth application
  4. If using a PAT, paste the token and submit it for validation
  5. Create your first project
  6. Add repositories and start creating workflows

For help: https://github.com/dawg-io/actions-manager/issues
============================================================
```

> **Note:** The API Docs link (`/docs`) is disabled by default. The installer's default config sets `ENVIRONMENT=production`, which auto-disables the interactive Swagger/OpenAPI UI. Set `DISABLE_API_DOCS=false` in your `.env.self-hosted` to re-enable it.

### Method 2: Manual Installation

For advanced users who want complete control:

#### Step 1: Clone Repository

```bash
git clone https://github.com/dawg-io/actions-manager.git
cd actions-manager
```

#### Step 2: Copy Environment Template

```bash
cp .env.self-hosted.example .env.self-hosted
```

#### Step 3: Edit Configuration File

Open `.env.self-hosted` in your editor and configure:

```bash
# REQUIRED: GitHub OAuth
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# URLs — leave commented out for auto-detection via window.location (recommended).
# Set explicitly only if you use GitHub OAuth login and need a fixed callback URL.
# APP_URL=http://YOUR_SERVER_IP_OR_DOMAIN:8080
# VITE_APP_URL=http://YOUR_SERVER_IP_OR_DOMAIN:8080  # deprecated alias

# OPTIONAL: License key (reserved for future paid tiers; no paid plans are currently available during beta)
# LICENSE_KEY=your_jwt_license_key

# OPTIONAL: PostgreSQL (default uses SQLite)
# POSTGRES_USER=actionsmanager
# POSTGRES_PASSWORD=secure_password
# POSTGRES_DB=actions_manager
# POSTGRES_HOST=postgres
# POSTGRES_PORT=5432
# DATABASE_URL=postgresql://actionsmanager:secure_password@postgres:5432/actions_manager
```

#### Step 4: Generate SECRET_KEY

Add a cryptographically secure random key:

```bash
# Option 1: Using openssl
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env.self-hosted

# Option 2: Using Python
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> .env.self-hosted

# Option 3: Manual
SECRET_KEY=your_32_character_hex_string
```

#### Step 5: Start the Application

The official self-hosted release pulls a **pre-built single-container image** from GitHub Container Registry — you do **not** need to build anything locally:

* Image: `ghcr.io/dawg-io/actions-manager`
* Default tag: `latest` (stable releases). Use `beta` for the public beta or pin a date-stamped tag like `2026.05.14`.
* Override the tag with the `ACTIONS_MANAGER_TAG` environment variable, or override the full image reference with `ACTIONS_MANAGER_IMAGE` (useful for private mirrors / air-gapped installs).

**With Docker:**
```bash
# Pull the published image, then start it
docker compose -f docker-compose.self-hosted.yml pull
docker compose -f docker-compose.self-hosted.yml up -d
```

**Pin a specific release tag (e.g. the public beta):**
```bash
ACTIONS_MANAGER_TAG=beta docker compose -f docker-compose.self-hosted.yml up -d
```

**With Podman:**
```bash
podman-compose -f docker-compose.self-hosted.yml pull
podman-compose -f docker-compose.self-hosted.yml up -d
```

**Contributors building from source (not for end users):**
```bash
docker compose -f docker-compose.self-hosted.yml \
               -f docker-compose.self-hosted.dev.yml up --build -d
```

#### Step 6: Verify Installation

```bash
# Check container status
docker compose -f docker-compose.self-hosted.yml ps

# Expected output:
# NAME                    STATUS              PORTS
# actions-manager-app-1   Up 2 minutes        127.0.0.1:8080->8080/tcp

# View logs
docker compose -f docker-compose.self-hosted.yml logs -f

# Test connectivity
curl http://localhost:8080

# When you see "Welcome to ActionsManager.io", installation is complete
```

> **Note:** The `/docs` API documentation link is disabled by default. `ENVIRONMENT=production` (the default in `.env.self-hosted.example`) auto-disables the interactive Swagger/OpenAPI UI. Set `DISABLE_API_DOCS=false` to re-enable it.

#### Step 7: Access the Application

Open your browser and navigate to:
- **Web Interface:** http://localhost:8080
- **API Documentation:** http://localhost:8080/docs (disabled by default — see note above)
- **Admin Panel:** http://localhost:8080/admin

---

## Post-Installation Setup

### First-Time Access

#### 1. Open Web Interface

Navigate to http://localhost:8080 in your browser.

#### 2. Choose a Sign-In Method

- **OAuth:** Click **Log in with GitHub**, authorize the OAuth application, and return to ActionsManager.io
- **PAT:** Click **Sign in with Personal Access Token**, paste your token, and submit it for validation
- Manage saved PATs later from the user menu

#### 3. Grant Repository Access

During first login, GitHub will ask you to authorize ActionsManager.io to:
- Read your repositories
- Access repository settings
- Manage workflows
- Read repository secrets

This is necessary for the application to function.

#### 4. Create Your First Project

Projects organize your repositories:

1. Click "Create Project"
2. Enter project name (e.g., "My Team", "Production Pipelines")
3. Add a description
4. Click "Create"

#### 5. Add Repositories

1. In your project, click "Add Repository"
2. Select repositories from the dropdown (showing your GitHub repositories)
3. Adjust settings for each repository
4. Click "Add Repositories"

#### 6. Create Your First Workflow

1. Select a repository
2. Click "Create Workflow"
3. Choose a template or start from scratch
4. Edit the workflow YAML
5. Deploy to GitHub

### Admin Panel Access

The self-hosted beta image does not require admin panel credentials for first use. Sign in with GitHub OAuth or a Personal Access Token instead. Do not rely on placeholder admin credentials such as `admin/admin123` for any exposed deployment.

### Checking Your Current Tier

View your installation tier in the application startup logs:

```bash
docker compose -f docker-compose.self-hosted.yml logs | grep -i "License Tier"
```

Output will show:
```
🔑 License Tier: free
```

Or view in admin panel:
- Navigate to Admin Panel > System Status
- Look for "Current License Tier"

### Understanding Your Tier

See [Account Tiers](#account-tiers) section for detailed feature comparison.

---

## Account Tiers

ActionsManager Self-Hosted is free during beta. No paid plans are currently available; future tier names, limits, support terms, and license behavior may change before general availability.

### Self-Hosted Beta Limits

All users running the self-hosted beta image get the same beta limits:

| Resource | Beta Limit |
|---|---|
| **Caller Workflow Projects** | 4 |
| **Reusable Workflow Projects** | 2 |
| **Secrets per project** | 6 |
| **Environment variables per project** | 6 |
| **GitHub environments per project** | 6 |
| **Repositories per project** | 10 |
| **Private repositories** | ✅ Yes |
| **Reusable workflows** | ✅ Yes |
| **Drift detection** | ✅ Yes |

> **Paid plans are not currently available during the self-hosted beta.** Cloud/SaaS and GitHub Marketplace billing are future/planned paths and are not part of this first public beta.

### Future Tiers (Not Yet Available)

The application contains tier and license-key code paths for future planning. During the beta, these are not active paid offerings. Future paid tiers may increase project counts, secrets, and other limits. Free beta access does not grant permanent free access to future paid features.

### Checking Your Tier

#### Option 1: View Startup Logs

```bash
docker compose -f docker-compose.self-hosted.yml logs | grep "License Tier"
```

#### Option 2: Admin Panel

1. Go to http://localhost:8080/admin
2. Login with admin credentials
3. Look for "License Status" or "System Status"
4. Current tier will be displayed


## Configuration Options

### Environment Variables

All configuration is done via `.env.self-hosted`. Edit this file and restart the application for changes to take effect.

#### Application URLs

**Auto-detection (recommended default):**

For PAT login, leave URL configuration commented out. The frontend auto-detects the browser location (`window.location`), so the app works whether users access it via `localhost`, a LAN IP address, or a custom domain — with zero configuration.

```bash
# Auto-detection: no URL configuration needed
```

**Fixed URL (required for GitHub OAuth login):**

GitHub needs a fixed callback URL registered in your OAuth App settings. Set `APP_URL` to the actual URL that browsers will use to reach the server:

```bash
# LAN / server IP example
APP_URL=http://192.168.1.100:8080

# Named domain with TLS
APP_URL=https://actionsmanager.example.com
```

> **Important:** Use the IP or domain your users type in their browser — **not** `localhost` unless every user runs the container on their own machine.

**Advanced:** For more granular control, you can use separate `VITE_BACKEND_URL`, `VITE_FRONTEND_URL`, and `VITE_WEBSOCKET_URL` variables instead of the single `APP_URL`. `VITE_APP_URL` is still accepted as a deprecated alias.

#### Changing Port

To use a different port (e.g. 9000):

**1. Edit `.env.self-hosted`:**
```bash
# Only needed if you use GitHub OAuth; otherwise leave this commented out.
# APP_URL=http://YOUR_SERVER_IP_OR_DOMAIN:9000
```

**2. Update `docker-compose.self-hosted.yml`:**
```yaml
ports:
  - "9000:8080"  # Change first number to your port
```

**3. Update your GitHub OAuth App** (Settings → Developer settings → OAuth Apps):
- **Homepage URL**: `http://YOUR_SERVER_IP_OR_DOMAIN:9000`
- **Authorization callback URL**: `http://YOUR_SERVER_IP_OR_DOMAIN:9000/auth/callback`

**4. Restart:**
```bash
docker compose -f docker-compose.self-hosted.yml restart
```

> ⚠️ **All three changes are required for OAuth login.** PAT login does not use the OAuth callback URL and works with auto-detection.

#### GitHub OAuth (optional)

```bash
# Optional for OAuth login
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# Optional server-level token for automation only
GITHUB_TOKEN=your_server_level_github_token
```

**Updating OAuth Credentials:**
1. Stop the application
2. Edit `.env.self-hosted`
3. Restart: `docker compose -f docker-compose.self-hosted.yml restart`

#### Database Configuration

**SQLite (Default)**
```bash
# No configuration needed - SQLite is embedded
# Database file: /app/data/actions_manager.db (inside the container)
# Persisted via the named volume mounted at /app/data
# Automatically created on first run
```

**PostgreSQL (Recommended for Production)**

```bash
# Enable PostgreSQL
POSTGRES_USER=actionsmanager
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=actions_manager
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
DATABASE_URL=postgresql://actionsmanager:your_secure_password@postgres:5432/actions_manager

# Note: PostgreSQL requires docker-compose modifications
# Update docker-compose.self-hosted.yml to include postgres service
```

**PostgreSQL Docker Compose Addition:**
```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

**Migrating from SQLite to PostgreSQL:**
```bash
# Backup SQLite database first (write to persisted volume)
docker compose -f docker-compose.self-hosted.yml exec app cp /app/data/actions_manager.db /app/data/actions_manager.db.backup

# Update .env.self-hosted with PostgreSQL settings
# Restart to apply migrations
docker compose -f docker-compose.self-hosted.yml up --build -d

# Verify migration
docker compose -f docker-compose.self-hosted.yml logs | grep -i "migration"
```

#### Admin Panel

```bash
# Admin credentials (change immediately in production!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_this_password
```

**Changing Admin Password:**
```bash
# Stop application
docker compose -f docker-compose.self-hosted.yml stop

# Edit .env.self-hosted
ADMIN_PASSWORD=new_secure_password

# Restart
docker compose -f docker-compose.self-hosted.yml start
```

#### License Configuration

```bash
# License key (reserved for future paid tiers; no paid plans are currently available during beta)
# Leave unset for self-hosted beta — no license key is required
# LICENSE_KEY=your_jwt_license_key_here
```

#### Debug & Development

```bash
# Enable debug mode (verbose logging)
DEBUG_MODE=false  # Set to true only for troubleshooting

# Enable mock responses (bypasses GitHub OAuth)
USE_MOCK_RESPONSES=false  # Only for development
```

---

## Troubleshooting

(Comprehensive troubleshooting section continues in the file...)



### Configuration Examples

#### Example 1: Basic Local Setup

```bash
# .env.self-hosted
# GitHub OAuth (required)
GITHUB_CLIENT_ID=abc123def456
GITHUB_CLIENT_SECRET=your_secret_here

# URLs
APP_URL=http://localhost:8080

# Admin
ADMIN_USERNAME=admin
ADMIN_PASSWORD=initial_password_123

# Self-hosted beta — no license key required
```

#### Example 2: Production with Custom Port

```bash
# .env.self-hosted
# GitHub OAuth
GITHUB_CLIENT_ID=prod_client_id
GITHUB_CLIENT_SECRET=prod_secret

# URLs - custom domain and port
APP_URL=https://actions.example.com:8443

# Admin
ADMIN_USERNAME=prodadmin
ADMIN_PASSWORD=strong_production_password

# No paid plans are currently available during beta; leave LICENSE_KEY unset
```

#### Example 3: Production with PostgreSQL

```bash
# .env.self-hosted
# PostgreSQL
DATABASE_URL=postgresql://actions:prod_password@postgres:5432/actions_manager
POSTGRES_USER=actions
POSTGRES_PASSWORD=prod_password
POSTGRES_DB=actions_manager

# Admin & License
ADMIN_USERNAME=prodadmin
ADMIN_PASSWORD=strong_password

LICENSE_KEY=eyJhbGc...

# GitHub OAuth
GITHUB_CLIENT_ID=prod_id
GITHUB_CLIENT_SECRET=prod_secret

# HTTPS URL
APP_URL=https://actions.example.com
```

### Applying Configuration Changes

#### Quick Changes (URLs, Secrets)

```bash
# 1. Edit .env.self-hosted
nano .env.self-hosted

# 2. Restart containers
docker compose -f docker-compose.self-hosted.yml restart

# 3. Verify changes
docker compose -f docker-compose.self-hosted.yml logs -f
```

#### Major Changes (Database, Build Settings)

```bash
# 1. Edit .env.self-hosted
nano .env.self-hosted

# 2. Rebuild containers
docker compose -f docker-compose.self-hosted.yml down
docker compose -f docker-compose.self-hosted.yml up --build -d

# 3. Monitor startup
docker compose -f docker-compose.self-hosted.yml logs -f
```

---

## Upgrading

### Upgrading the Application

Keep your installation up-to-date with bug fixes and features.

#### Pull the Latest Pre-Built Image (Recommended)

The official self-hosted release publishes new images to GHCR. Upgrading is just a re-pull of the official image — no source checkout or local build required:

```bash
cd actions-manager

# Pull the latest published image and recreate the container
docker compose -f docker-compose.self-hosted.yml pull
docker compose -f docker-compose.self-hosted.yml up -d

# Monitor startup
docker compose -f docker-compose.self-hosted.yml logs -f
```

To roll forward to (or roll back to) a specific tag:

```bash
ACTIONS_MANAGER_TAG=2026.05.14 docker compose -f docker-compose.self-hosted.yml up -d
```

#### Contributor / Build-from-Source Upgrade

Only contributors and developers should rebuild from local source:

```bash
cd actions-manager
git pull origin main

docker compose -f docker-compose.self-hosted.yml \
               -f docker-compose.self-hosted.dev.yml down
docker compose -f docker-compose.self-hosted.yml \
               -f docker-compose.self-hosted.dev.yml up --build -d

docker compose -f docker-compose.self-hosted.yml logs -f
```

#### Manual Update

```bash
# Download latest version
curl -fsSL https://github.com/dawg-io/actions-manager/archive/main.zip -o actions-manager.zip
unzip actions-manager.zip
cd actions-manager-main

# Copy your configuration
cp ../actions-manager/.env.self-hosted .env.self-hosted

# Build and start
docker compose -f docker-compose.self-hosted.yml up --build -d
```

### Database Migrations

Database migrations run automatically on startup.

**Verify migrations completed:**
```bash
docker compose -f docker-compose.self-hosted.yml logs | grep -i "migration"

# Expected output:
# ✓ Database migrations completed successfully
```

**If migrations fail:**
1. Stop the application: `docker compose -f docker-compose.self-hosted.yml stop`
2. Backup database: `docker compose -f docker-compose.self-hosted.yml exec app cp /app/data/actions_manager.db /app/data/actions_manager.db.backup`
3. Check logs for specific error
4. Review error messages for migration-specific details
5. For detailed schema information, consult DATABASE_SCHEMA.md (located at ../DATABASE_SCHEMA.md)
6. Restart: `docker compose -f docker-compose.self-hosted.yml start`

> **Note:** If migrations continue to fail, check application logs with `docker compose -f docker-compose.self-hosted.yml logs | grep -i migration` for specific error details.

### Backing Up Before Upgrade

**Important:** Always backup before upgrading!

```bash
# Backup database (stop app first to avoid an inconsistent copy, then write to persisted volume)
docker compose -f docker-compose.self-hosted.yml stop app
docker compose -f docker-compose.self-hosted.yml run --rm app cp /app/data/actions_manager.db /app/data/actions_manager.db.pre-upgrade-$(date +%Y%m%d)
docker compose -f docker-compose.self-hosted.yml start app

# Backup configuration
cp .env.self-hosted .env.self-hosted.backup

# Backup entire volume (if using volumes)
docker compose -f docker-compose.self-hosted.yml exec app tar -czf - -C /app/data actions_manager.db > backup_$(date +%Y%m%d_%H%M%S).tar.gz
```

### Upgrading Your License Tier

See [Account Tiers > Upgrading Your Tier](#upgrading-your-tier)

### Version Compatibility

Check if your data is compatible with new versions:

```bash
# View current version
docker compose -f docker-compose.self-hosted.yml exec app python -c "import sys; print(sys.version)"

# View application version (in logs)
docker compose -f docker-compose.self-hosted.yml logs | grep -i "version"
```

---

## Troubleshooting

Comprehensive troubleshooting guide for common issues.

### Installation Issues

#### Problem: Docker/Podman Not Found

**Symptoms:**
```
✗ Neither Docker nor Podman found
Please install Docker or Podman
```

**Solution:**

Install Docker:
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Verify
docker --version
docker compose version
```

Install Podman:
```bash
# Ubuntu/Debian
sudo apt-get install -y podman podman-compose

# macOS
brew install podman podman-compose

# Start Podman machine (macOS)
podman machine start

# Verify
podman --version
podman-compose --version
```

#### Problem: Out of Memory During Build

**Symptoms:**
```
ERROR: Service backend failed to build: OOMKilled
Killed signal: terminated
```

**Solution for Docker:**
1. Open Docker Desktop
2. Go to Settings > Resources
3. Increase Memory to 8GB or more
4. Apply & Restart
5. Retry installation

**Solution for Podman:**
```bash
# Stop Podman machine
podman machine stop

# Increase memory allocation
podman machine set --memory 8192

# Start machine
podman machine start

# Verify
podman machine inspect | grep memory
```

**Alternative:** Use a smaller build by reducing unused images:
```bash
docker system prune -a
podman system prune -a
```

#### Problem: Port Already in Use

**Symptoms:**
```
Error response from daemon: driver failed programming external connectivity on endpoint:
bind: address already in use
```

**Solution:**

Check what's using the port:
```bash
# macOS/Linux
lsof -i :8080

# Or with netstat
netstat -an | grep 8080
```

**Option 1: Stop conflicting service**
```bash
# Identify the process and stop it
kill -9 <PID>
```

**Option 2: Use different port**
```bash
# Edit .env.self-hosted
APP_URL=http://localhost:9000

# Edit docker-compose.self-hosted.yml
ports:
  - "9000:8080"  # Change 9000 to your desired port

# Rebuild
docker compose -f docker-compose.self-hosted.yml up --build -d
```

#### Problem: Installation Script Permission Denied

**Symptoms:**
```
-bash: ./install.sh: Permission denied
```

**Solution:**
```bash
# Make script executable
chmod +x install.sh

# Run again
./install.sh
```

### Runtime Issues

#### Problem: Application Won't Start

**Symptoms:**
- Container keeps restarting
- Application exits immediately
- Web page not accessible

**Diagnostic Steps:**

1. **Check logs:**
```bash
docker compose -f docker-compose.self-hosted.yml logs -f
```

2. **Check container status:**
```bash
docker compose -f docker-compose.self-hosted.yml ps
docker ps -a
```

3. **Look for common errors:**

**Missing environment variables:**
```
KeyError: 'GITHUB_CLIENT_ID'
```
→ Edit `.env.self-hosted` and add missing variables

**Invalid port binding:**
```
Address already in use
```
→ See "Port Already in Use" above

**Insufficient memory:**
```
MemoryError: Unable to allocate memory
```
→ See "Out of Memory" above

**File permissions:**
```
Permission denied: /app/data/actions_manager.db
```

The self-hosted container runs as a non-root user (`appuser`, uid 1001) and persists data in the named Docker volume `actionsmanager`, not a bind-mounted host directory — so this is almost always a volume ownership mismatch from an older container version (e.g. one that ran as root), not a host-side file permission issue. Chowning a local `backend/` directory does nothing, since that path isn't what the container reads.

**Solution: reset ownership inside the volume to match the container's user**
```bash
docker run --rm -v actionsmanager:/app/data alpine chown -R 1001:1001 /app/data
```

#### Problem: GitHub OAuth Fails

**Symptoms:**
- "Invalid OAuth credentials" error
- Redirect loop after clicking "Login with GitHub"
- 401 Unauthorized errors
- Blank page after OAuth callback

**Diagnostic Steps:**

1. **Verify OAuth App Settings:**
   - Go to [GitHub Settings > OAuth Apps](https://github.com/settings/developers)
   - Click your app
   - Check **Client ID** matches `GITHUB_CLIENT_ID` in `.env.self-hosted`
   - Verify **Authorization callback URL** is exactly `http://localhost:8080/auth/callback`

2. **Check Configuration:**
```bash
# Verify environment variables
docker compose -f docker-compose.self-hosted.yml exec app env | grep GITHUB

# Should show:
# GITHUB_CLIENT_ID=your_id
# GITHUB_CLIENT_SECRET=your_secret
```

3. **Check logs:**
```bash
docker compose -f docker-compose.self-hosted.yml logs | grep -i "oauth\|github\|auth"
```

**Solutions:**

**Solution 1: Update OAuth Credentials**
```bash
# If your credentials are wrong, update them:
nano .env.self-hosted
# Update GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET

# Restart
docker compose -f docker-compose.self-hosted.yml restart

# Wait 30 seconds and try again
```

**Solution 2: Fix Callback URL**
- Go to GitHub app settings
- Update **Authorization callback URL** to exactly match your deployment:
  - Local: `http://localhost:8080/auth/callback`
  - Production: `https://your-domain.com/auth/callback`

**Solution 3: Check OAuth App Status**
- GitHub app might be suspended
- Create a new OAuth app if needed
- Update credentials in `.env.self-hosted`

**Solution 4: Clear Browser Cache**
- Clear cookies for localhost:8080 (or your domain)
- Close all browser windows
- Open a new private/incognito window
- Try logging in again

#### Problem: License Validation Fails

**Symptoms:**
```
⚠️  License validation failed: Invalid license key format
🔑 License Tier: free
```

**Diagnostic Steps:**

```bash
# Check which license is being used
docker compose -f docker-compose.self-hosted.yml logs | grep -i "license"

# Verify license is set
docker compose -f docker-compose.self-hosted.yml exec app env | grep LICENSE
```

**Common Issues:**

**Issue 1: License key was copied incorrectly or modified**
- Re-copy the vendor-issued `LICENSE_KEY` into `.env.self-hosted`
- Verify there are no extra spaces, line wraps, or truncation

**Issue 2: License has expired**
```
⚠️  License validation failed: License key has expired
```
- Check expiration date (`exp` field) in JWT
- Request a renewed vendor-issued `LICENSE_KEY`

**Issue 3: Invalid JWT format**
```
⚠️  License validation failed: Invalid license key format
```
- Verify license key is valid JWT (use https://jwt.io to decode)
- Check no extra spaces or newlines
- Request a replacement vendor-issued `LICENSE_KEY` if corrupted

**Issue 4: Signature mismatch**
```
⚠️  License validation failed: Invalid license key signature
```
- License signature does not match the vendor-issued key
- Re-copy the exact key as issued (no edits)
- Request a new vendor-issued `LICENSE_KEY` if the error persists

**Solution: Request New License**

1. Open a support/sales request with your organization and request the tier.
2. Provide installation details (self-hosted deployment, expected tier, expiration window).
3. Replace `LICENSE_KEY` in `.env.self-hosted` with the newly issued token.
4. Restart services:
   ```bash
   docker compose -f docker-compose.self-hosted.yml restart
   ```

#### Problem: Database Errors

**SQLite Issues:**

**Symptoms:**
```
database is locked
unable to open database file
```

**Solution:**
```bash
# Check permissions inside the named volume (not a host backend/ directory -
# persistent data lives in the "actionsmanager" volume, mounted at /app/data)
docker run --rm -v actionsmanager:/app/data alpine ls -la /app/data

# Fix ownership to match the container's non-root user (appuser, uid 1001)
docker run --rm -v actionsmanager:/app/data alpine chown -R 1001:1001 /app/data

# Restart
docker compose -f docker-compose.self-hosted.yml restart
```

**PostgreSQL Issues:**

**Symptoms:**
```
could not connect to server: Connection refused
psql: FATAL: password authentication failed
```

**Solution:**

1. **Verify PostgreSQL container is running:**
```bash
docker ps | grep postgres
```

2. **Check PostgreSQL logs:**
```bash
docker logs <postgres_container_id>
```

3. **Verify connection settings:**
```bash
# In .env.self-hosted, check:
POSTGRES_USER=correct_user
POSTGRES_PASSWORD=correct_password
POSTGRES_HOST=postgres  # Should be 'postgres' for Docker service
POSTGRES_PORT=5432
```

4. **Restart PostgreSQL:**
```bash
docker compose -f docker-compose.self-hosted.yml restart postgres
```

#### Problem: "Module Not Found" Errors

**Symptoms:**
```
ModuleNotFoundError: No module named 'fastapi'
ImportError: cannot import name 'X' from 'Y'
```

**Solution:**

Rebuild containers to reinstall dependencies:
```bash
# Complete rebuild
docker compose -f docker-compose.self-hosted.yml down
docker system prune -a --volumes  # WARNING: removes all unused images
docker compose -f docker-compose.self-hosted.yml up --build -d

# Monitor
docker compose -f docker-compose.self-hosted.yml logs -f
```

#### Problem: WebSocket Connection Fails

**Symptoms:**
- Real-time updates don't appear
- Console shows WebSocket errors
- Status updates lag

**Diagnostic Steps:**

```bash
# Check WebSocket URL
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" http://localhost:8080/ws
```

**Solutions:**

1. **Verify WebSocket URL configuration:**
```bash
# In .env.self-hosted
VITE_WEBSOCKET_URL=ws://localhost:8080/ws

# For HTTPS production:
VITE_WEBSOCKET_URL=wss://your-domain.com/ws
```

2. **Check reverse proxy configuration:**
   - If using nginx/Apache, ensure WebSocket upgrade headers are passed
   - See [Production Deployment](#production-deployment) section

3. **Check firewall:**
   - WebSocket requires bidirectional connection
   - Port 8080 must be accessible
   - No blocking of long-lived connections

### Performance Issues

#### Slow Response Times

**Symptoms:**
- Pages load slowly
- Workflow creation takes long time
- API calls timeout

**Diagnostic Steps:**

1. **Check system resources:**
```bash
# View container resource usage
docker stats

# Check host resources
free -h        # Memory
df -h          # Disk
top -b -n 1    # CPU
```

2. **Check application logs:**
```bash
docker compose -f docker-compose.self-hosted.yml logs | grep -i "slow\|timeout\|error"
```

**Solutions:**

**Solution 1: Increase resource allocation**

For Docker Desktop:
- Settings > Resources
- Increase CPU cores to 4+
- Increase Memory to 8GB+
- Increase Disk image size if needed

For server deployment:
- Add more CPU cores
- Add more RAM
- Use SSD for better I/O

**Solution 2: Optimize database**

```bash
# If using SQLite, consider PostgreSQL for better performance
# See Database Configuration section
```

**Solution 3: Check network**

```bash
# Test GitHub API connectivity
curl -i https://api.github.com

# Check DNS resolution
nslookup api.github.com
```

#### High Memory Usage

**Symptoms:**
```
Container is using 2GB+ RAM
System running out of memory
Swap usage increasing
```

**Normal Baseline:**
- Backend container: 200-400 MB
- Total system: 500-800 MB

**Diagnostic Steps:**

```bash
# Check memory usage
docker stats --no-stream

# Check for memory leaks in logs
docker compose -f docker-compose.self-hosted.yml logs | grep -i "memory\|gc\|oom"
```

**Solutions:**

**Solution 1: Restart containers**
```bash
docker compose -f docker-compose.self-hosted.yml restart

# Clear unused Docker data
docker system prune
```

**Solution 2: Increase system memory**
- Add more RAM to server
- Increase Docker memory limit

**Solution 3: Check for runaway processes**
```bash
# View detailed memory usage
docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}"
```

#### Disk Space Issues

**Symptoms:**
```
No space left on device
unable to write to file
database file is full
```

**Diagnostic Steps:**

```bash
# Check disk usage
df -h

# Check Docker volume usage
docker system df

# Check database size
docker compose -f docker-compose.self-hosted.yml exec app du -sh /app/data/actions_manager.db
```

**Solutions:**

**Solution 1: Clean up Docker**
```bash
# Remove unused images and containers
docker system prune -a --volumes

# WARNING: This removes all unused images/containers
```

**Solution 2: Archive old data**
- Backup old database records
- Archive to separate storage

**Solution 3: Add disk space**
- Add storage to server
- Migrate to larger volume

### Getting More Help

If you continue experiencing issues:

#### 1. Check Documentation
- [README.md](../README.md) - General overview
- [LICENSE_KEY_GUIDE.md](../LICENSE_KEY_GUIDE.md) - License configuration
- [DOCKER_DEPLOYMENT_MODES.md](../DOCKER_DEPLOYMENT_MODES.md) - Deployment modes
- [DATABASE_SCHEMA.md](../DATABASE_SCHEMA.md) - Database details

#### 2. Check Logs
```bash
# View full application logs
docker compose -f docker-compose.self-hosted.yml logs -f

# Follow specific service
docker compose -f docker-compose.self-hosted.yml logs -f app

# View only errors
docker compose -f docker-compose.self-hosted.yml logs | grep -i error
```

#### 3. Search GitHub Issues
- [GitHub Issues](https://github.com/dawg-io/actions-manager/issues)
- Search for error message or keywords
- Check closed issues for resolutions

#### 4. Create New Issue

When creating an issue, include:
- Operating system and version (`uname -a`)
- Docker/Podman version (`docker --version`)
- Installation method (automated vs manual)
- Relevant error logs (anonymize secrets)
- Steps to reproduce
- Expected vs actual behavior

```bash
# Collect diagnostic information
echo "=== System Info ===" > diagnostics.txt
uname -a >> diagnostics.txt
echo "=== Docker/Podman ===" >> diagnostics.txt
docker --version >> diagnostics.txt
docker compose version >> diagnostics.txt
echo "=== Recent Logs ===" >> diagnostics.txt
docker compose -f docker-compose.self-hosted.yml logs --tail 100 >> diagnostics.txt
```

---

## Maintenance

### Regular Backups

Backup your data regularly to prevent data loss.

#### Backup Strategy

**Frequency:**
- Daily for production
- Weekly for development
- Before major changes
- After significant configuration

**Retention:**
- Keep 30 days of daily backups
- Keep 12 months of monthly backups

#### Automated Backup Script

```bash
#!/bin/bash
# backup.sh - Automated backup script

BACKUP_DIR="/backups/actions-manager"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_BACKUP="$BACKUP_DIR/actions_manager_$TIMESTAMP.db"
CONFIG_BACKUP="$BACKUP_DIR/.env.self-hosted_$TIMESTAMP"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
docker compose -f docker-compose.self-hosted.yml exec app cp /app/data/actions_manager.db $DB_BACKUP

# Backup configuration
cp .env.self-hosted $CONFIG_BACKUP

# Compress backups
tar -czf "$BACKUP_DIR/backup_$TIMESTAMP.tar.gz" $DB_BACKUP $CONFIG_BACKUP

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_DIR/backup_$TIMESTAMP.tar.gz"
```

**Set up cron job for daily backups:**
```bash
# Add to crontab
0 2 * * * /path/to/backup.sh  # Daily at 2 AM
```

#### Manual Backup

**Backup database:**
```bash
# SQLite
docker compose -f docker-compose.self-hosted.yml exec app cp /app/data/actions_manager.db actions_manager_$(date +%Y%m%d).db.backup

# PostgreSQL
docker compose -f docker-compose.self-hosted.yml exec postgres pg_dump -U actionsmanager actions_manager > actions_manager_$(date +%Y%m%d).sql
```

**Backup configuration:**
```bash
cp .env.self-hosted .env.self-hosted_$(date +%Y%m%d).backup
```

#### Restore from Backup

**Restore SQLite database:**
```bash
# Stop application
docker compose -f docker-compose.self-hosted.yml stop

# Restore backup
docker cp /tmp/actions_manager_20240101.db.backup $(docker compose -f docker-compose.self-hosted.yml ps -q app):/app/data/actions_manager.db

# Restart
docker compose -f docker-compose.self-hosted.yml start
```

**Restore PostgreSQL database:**
```bash
# Stop application
docker compose -f docker-compose.self-hosted.yml stop

# Restore backup
docker compose -f docker-compose.self-hosted.yml exec -T postgres psql -U actionsmanager actions_manager < actions_manager_20240101.sql

# Restart
docker compose -f docker-compose.self-hosted.yml start
```

### Monitoring

#### System Monitoring

```bash
# Real-time resource monitoring
docker stats

# Container health
docker compose -f docker-compose.self-hosted.yml ps

# Check application is responding (proxies to the backend, so this fails
# if uvicorn is down even though nginx/static files are still serving)
curl -I http://localhost:8080/healthz
```

#### Log Monitoring

```bash
# Follow application logs
docker compose -f docker-compose.self-hosted.yml logs -f

# Follow specific service
docker compose -f docker-compose.self-hosted.yml logs -f app

# View logs from last hour
docker compose -f docker-compose.self-hosted.yml logs --since 1h

# Filter errors
docker compose -f docker-compose.self-hosted.yml logs | grep -i "error\|warning\|critical"
```

#### Application Health Checks

```bash
# API health endpoint
curl http://localhost:8080/healthz

# Admin panel access
curl -u admin:password http://localhost:8080/admin

# Database connectivity
docker compose -f docker-compose.self-hosted.yml exec app python -c "from backend.database import db; print(db.health())"
```

### Regular Updates

Keep your installation secure and up-to-date.

#### Check for Updates

```bash
# Check latest available version
curl -s https://api.github.com/repos/dawg-io/actions-manager/releases/latest | grep tag_name

# View current version
docker compose -f docker-compose.self-hosted.yml exec app cat /app/version.txt
```

#### Security Updates

Always apply security updates immediately:

```bash
# Pull latest code
cd actions-manager
git pull origin main

# Apply updates
docker compose -f docker-compose.self-hosted.yml down
docker compose -f docker-compose.self-hosted.yml up --build -d

# Verify
docker compose -f docker-compose.self-hosted.yml logs | grep -i "version\|security"
```

---

## Production Deployment

Guidelines and best practices for production deployment.

### Security Checklist

Before going to production, verify:

#### Authentication & Authorization
- [ ] Change default admin password immediately
- [ ] Use strong, randomly-generated passwords
- [ ] Enable HTTPS/TLS (via reverse proxy)
- [ ] Implement role-based access control if available
- [ ] Regularly audit who has access

#### Secrets Management
- [ ] Never commit `.env.self-hosted` to version control
- [ ] Use environment-specific secrets
- [ ] Rotate secrets periodically
- [ ] Store secrets in secure secrets manager (Vault, AWS Secrets Manager)
- [ ] Audit secret access logs

#### Data Security
- [ ] Enable database encryption at rest
- [ ] Use PostgreSQL for better security features
- [ ] Enable database access logging
- [ ] Regular backups with encryption
- [ ] Test backup restoration procedures

#### Network Security
- [ ] Use HTTPS only (TLS 1.2+)
- [ ] Restrict inbound traffic via firewall
- [ ] Whitelist IP addresses if possible
- [ ] Use VPN for remote access
- [ ] Implement rate limiting and DDoS protection

#### GitHub OAuth Security
- [ ] Use HTTPS in callback URL
- [ ] Verify OAuth app permissions are minimal
- [ ] Monitor for suspicious authentication attempts
- [ ] Rotate OAuth credentials periodically

#### Application Security
- [ ] Keep application updated with security patches
- [ ] Enable DEBUG_MODE only when troubleshooting
- [ ] Disable mock responses in production
- [ ] Monitor logs for suspicious activity
- [ ] Set up alerts for errors and failures

#### Infrastructure Security
- [ ] Keep Docker/Podman updated
- [ ] Scan images for vulnerabilities
- [ ] Run containers with minimal privileges
- [ ] Separate services if possible (db on different server)
- [ ] Regular security audits

### Using HTTPS with Reverse Proxy

{: .warning }
**⚠️ CRITICAL SECURITY REQUIREMENT**: Do not expose ActionsManager over plain HTTP on a network or to the internet. Personal Access Tokens (PATs) and API credentials will be transmitted in plaintext and can be intercepted. Always use HTTPS for any non-localhost deployment.

ActionsManager now **refuses to start** if you configure a non-loopback HTTP `APP_URL` without `ALLOW_INSECURE_HTTP=true`, and it still blocks PAT login over non-local HTTP as defense-in-depth. To test without HTTPS (not recommended for production), set `ALLOW_INSECURE_HTTP=true` in your environment.

Production deployments must use HTTPS. Choose a reverse proxy that fits your infrastructure:

#### Option 1: Caddy (Easiest - Automatic HTTPS)

Caddy automatically obtains and renews TLS certificates from Let's Encrypt with zero configuration.

**Caddyfile:**
```caddy
# /etc/caddy/Caddyfile

actionsmanager.example.com {
    reverse_proxy localhost:8080
    
    # Enable compression
    encode gzip zstd
    
    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
    
    # Rate limiting (requires caddy-ratelimit plugin)
    # rate_limit {
    #     zone api {
    #         key {remote_host}
    #         events 100
    #         window 1m
    #     }
    # }
}
```

**Install and run:**
```bash
# Install Caddy
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# Start Caddy
sudo systemctl enable caddy
sudo systemctl start caddy

# Check status
sudo systemctl status caddy
```

**Update ActionsManager configuration:**
```bash
# Edit .env.self-hosted
APP_URL=https://actionsmanager.example.com

# Or set the per-service URLs explicitly instead of the single APP_URL
VITE_BACKEND_URL=https://actionsmanager.example.com
VITE_FRONTEND_URL=https://actionsmanager.example.com
VITE_WEBSOCKET_URL=wss://actionsmanager.example.com/ws

# VITE_APP_URL still works as a deprecated alias for APP_URL

# Restart
docker compose -f docker-compose.self-hosted.yml restart
```

#### Option 2: Traefik (Docker-Native)

Traefik integrates well with Docker and Docker Compose, with automatic service discovery.

**docker-compose.traefik.yml:**
```yaml
version: '3.8'

services:
  traefik:
    image: traefik:v2.10
    command:
      - "--api.insecure=false"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=admin@example.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
      # Redirect HTTP to HTTPS
      - "--entrypoints.web.http.redirections.entryPoint.to=websecure"
      - "--entrypoints.web.http.redirections.entryPoint.scheme=https"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "./letsencrypt:/letsencrypt"
    networks:
      - web

  actionsmanager:
    image: ghcr.io/dawg-io/actions-manager:latest
    env_file:
      - .env.self-hosted
    environment:
      - APP_URL=https://actionsmanager.example.com
    volumes:
      - ./data:/app/data
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.actionsmanager.rule=Host(`actionsmanager.example.com`)"
      - "traefik.http.routers.actionsmanager.entrypoints=websecure"
      - "traefik.http.routers.actionsmanager.tls.certresolver=letsencrypt"
      - "traefik.http.services.actionsmanager.loadbalancer.server.port=8080"
      # Security headers
      - "traefik.http.middlewares.security-headers.headers.stsSeconds=31536000"
      - "traefik.http.middlewares.security-headers.headers.stsIncludeSubdomains=true"
      - "traefik.http.middlewares.security-headers.headers.contentTypeNosniff=true"
      - "traefik.http.middlewares.security-headers.headers.browserXssFilter=true"
      - "traefik.http.routers.actionsmanager.middlewares=security-headers"
    networks:
      - web

networks:
  web:
    driver: bridge
```

**Start with Traefik:**
```bash
# Create letsencrypt directory
mkdir -p letsencrypt
chmod 600 letsencrypt

# Start services
docker compose -f docker-compose.traefik.yml up -d

# Check logs
docker compose -f docker-compose.traefik.yml logs -f traefik
```

#### Option 3: Nginx (Manual Configuration)

Nginx requires manual TLS certificate setup but offers maximum control.

```nginx
# /etc/nginx/sites-available/actions-manager

upstream backend {
    server localhost:8080;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name actions-manager.example.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name actions-manager.example.com;

    # SSL certificates (use Let's Encrypt Certbot)
    ssl_certificate /etc/letsencrypt/live/actions-manager.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/actions-manager.example.com/privkey.pem;

    # Strong SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Proxy settings
    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # Timeouts for WebSocket
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://backend;
    }
}
```

**Enable the site:**
```bash
sudo ln -s /etc/nginx/sites-available/actions-manager /etc/nginx/sites-enabled/actions-manager
sudo nginx -t
sudo systemctl restart nginx
```

**Get SSL certificate:**
```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d actions-manager.example.com
sudo certbot renew --dry-run  # Test automatic renewal
```

#### Update ActionsManager.io Configuration

```bash
# Edit .env.self-hosted
APP_URL=https://actions-manager.example.com

# Restart
docker compose -f docker-compose.self-hosted.yml restart
```

### Docker Security Best Practices

#### Run with Limited Privileges

Already done — nginx, database migrations, and the backend server (uvicorn) all run as a non-root user (`appuser`, uid 1001). The container briefly starts as root (via `start.sh`) only to fix ownership of the `/app/data` volume before dropping privileges — application code itself never runs as root. No operator action needed.

#### Use Read-Only Filesystem

```yaml
# docker-compose.self-hosted.yml
services:
  app:
    read_only: true
    tmpfs:
      - /tmp
      - /run
```

#### Limit Resource Usage

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

#### Scan Images for Vulnerabilities

```bash
# Using Trivy
trivy image dawg-io/actions-manager:latest

# Using Docker Scout
docker scout cves dawg-io/actions-manager:latest
```

### PostgreSQL Production Setup

For larger deployments, use PostgreSQL:

```yaml
# docker-compose.self-hosted.yml (updated)
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_INITDB_ARGS: "-c shared_buffers=256MB -c max_connections=200"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  app:
    build:
      context: .
      dockerfile: Dockerfile.self-hosted
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      GITHUB_CLIENT_ID: ${GITHUB_CLIENT_ID}
      GITHUB_CLIENT_SECRET: ${GITHUB_CLIENT_SECRET}
      ADMIN_USERNAME: ${ADMIN_USERNAME}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      SECRET_KEY: ${SECRET_KEY}
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  postgres_data:
```

---

## Uninstalling

Complete removal of ActionsManager.io installation.

### Backup Important Data First

**Before uninstalling, backup your data:**

```bash
# Backup database
docker compose -f docker-compose.self-hosted.yml exec app cp /app/data/actions_manager.db actions_manager_final.db.backup

# Backup configuration
cp .env.self-hosted .env.self-hosted.backup

# Archive everything
tar -czf actions-manager_backup_$(date +%Y%m%d).tar.gz .env.self-hosted actions_manager_final.db.backup
```

### Stop the Application

```bash
# Stop containers gracefully
docker compose -f docker-compose.self-hosted.yml stop

# Wait a few seconds
sleep 5

# Verify stopped
docker compose -f docker-compose.self-hosted.yml ps
```

### Remove Containers and Volumes

```bash
# Remove containers and volumes (data will be deleted!)
docker compose -f docker-compose.self-hosted.yml down -v

# Verify removed
docker compose -f docker-compose.self-hosted.yml ps
```

### Remove Images

```bash
# Remove images associated with ActionsManager.io
docker compose -f docker-compose.self-hosted.yml down --rmi all

# Or manually
docker rmi actions-manager-backend:latest  # Adjust tag as needed
```

### Remove Configuration

```bash
# Remove environment file
rm .env.self-hosted

# Remove Docker data
docker compose -f docker-compose.self-hosted.yml exec app rm -f /app/data/actions_manager.db
```

### Remove Repository

```bash
# Navigate out of repository
cd ..

# Remove entire repository
rm -rf actions-manager
```

### Verify Complete Removal

```bash
# List remaining Docker resources
docker ps -a | grep -i actions
docker images | grep -i actions
docker volumes ls | grep -i actions

# If any remain, remove them manually
docker rm <container_id>
docker rmi <image_id>
docker volume rm <volume_name>
```

### Cleanup System

```bash
# Remove unused Docker images and containers
docker system prune -a --volumes

# Clean up disk space
df -h  # Check available space
```

---

## Additional Resources

### Documentation
- [README.md](../README.md) - Main documentation
- [INSTALLATION.md](../INSTALLATION.md) - Installation guide
- [LICENSE_KEY_GUIDE.md](../LICENSE_KEY_GUIDE.md) - License configuration
- [DOCKER_DEPLOYMENT_MODES.md](../DOCKER_DEPLOYMENT_MODES.md) - Deployment modes
- [DATABASE_SCHEMA.md](../DATABASE_SCHEMA.md) - Database structure

### External Resources
- [Docker Documentation](https://docs.docker.com/)
- [Podman Documentation](https://podman.io/docs/)
- [GitHub OAuth Documentation](https://docs.github.com/en/apps/oauth-apps)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

### Getting Help
- [GitHub Issues](https://github.com/dawg-io/actions-manager/issues)
- [GitHub Discussions](https://github.com/dawg-io/actions-manager/discussions)

---

## Glossary

| Term | Definition |
|------|-----------|
| **Container** | Lightweight, isolated execution environment for applications |
| **Docker** | Container platform for packaging and deploying applications |
| **Podman** | Alternative container runtime, compatible with Docker |
| **JWT** | JSON Web Token, used for license key authentication |
| **OAuth** | Open authentication standard used for GitHub login |
| **SSL/TLS** | Encryption protocols for secure HTTPS connections |
| **PostgreSQL** | Advanced relational database (optional, for better performance) |
| **SQLite** | Embedded database (default, built-in) |
| **Reverse Proxy** | Server that sits in front of backend servers |
| **Webhook** | HTTP callback for real-time notifications |
| **CI/CD** | Continuous Integration / Continuous Deployment |

---

## Changelog

**Document Version:** 1.0
**Last Updated:** January 2024 (see version history for detailed updates)
**Compatible With:** ActionsManager.io 1.0+

### Version History
- **1.0** - January 2024 - Initial comprehensive guide creation with all major sections

---

**Questions or feedback?** [Create an issue](https://github.com/dawg-io/actions-manager/issues) on GitHub.

---

*This guide is maintained alongside the ActionsManager.io project. Please check for updates regularly.*
