# Actions Manager Self-Hosted Beta Quick Start

Actions Manager Self-Hosted is currently a free beta preview for testing, evaluation, and feedback. No paid plans are currently available. The beta is self-hosted only; Cloud/SaaS and GitHub Marketplace billing are not part of the first public beta.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Choose Your Path](#choose-your-path)
3. [Self-Hosted Quick Start (5 minutes)](#self-hosted-quick-start-5-minutes)
4. [Cloud Deployment Quick Start (Future/Not Beta)](#cloud-deployment-quick-start-futurenot-beta)
5. [Common First Tasks](#common-first-tasks)
6. [Quick Troubleshooting](#quick-troubleshooting)
7. [Next Steps](#next-steps)

---

## Overview

**ActionsManager.io** is a centralized platform for managing GitHub Actions workflows across your repositories. With ActionsManager.io, you can:

✅ **Create and deploy workflows** from an intuitive visual interface  
✅ **Two deployment modes** - Direct commit for speed, PR-based for review  
✅ **Detect build types automatically** (Maven, npm, .NET, Python, Go, Rust, Docker)  
✅ **Manage secrets securely** across multiple repositories  
✅ **Monitor drift** between local and GitHub workflow versions  
✅ **Collaborate in real-time** with your team  
✅ **Organize repositories** into projects for better management  

### What You'll Accomplish Today

- Install Actions Manager Self-Hosted Beta
- Authenticate with GitHub using OAuth or a Personal Access Token
- Create your first project
- Add repositories
- Create or review your first workflow change

**Time to beta evaluation:** about 5-15 minutes. This is not a production-readiness guarantee.

---

## Choose Your Path

### Self-Hosted Deployment ⚙️

**Best for:** Teams wanting full control, on-premise deployments, or learning

**Setup Time:** 5 minutes (automated) | 15 minutes (manual)

**You get:**
- Single-instance deployment on your infrastructure
- Direct control over all settings and data
- Self-hosted beta access included
- 4 Caller Workflow Projects, 2 Reusable Workflow Projects
- 6 secrets, 6 environment variables, 6 deployment environments per project
- Public and private repositories allowed
- Free during beta; paid plans are not currently available
- Operators control their own infrastructure, backups, and credentials

**Requirements:**
- Docker 20.10+ or Podman 3.0+
- Linux or macOS
- 4GB RAM (8GB recommended)
- 10GB disk space
- Either a GitHub Personal Access Token or a GitHub OAuth App

👉 **[Go to Self-Hosted Quick Start →](#self-hosted-quick-start-5-minutes)**

### Cloud Deployment ☁️ (Future / Not Beta)

Cloud/SaaS, GitHub Marketplace billing, paid plans, and hosted enterprise deployments are not part of the first public self-hosted beta. Cloud-related files remain in the repository for future planning and internal validation only.

---

## Self-Hosted Quick Start (5 minutes)

### Fastest Path: PAT Quick Install

If you want the quickest self-hosted install, use a GitHub Personal Access Token and skip OAuth setup entirely.

1. Create a PAT using [GitHub PAT Setup](GITHUB_PAT_SETUP.md)
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
  -e ALLOW_INSECURE_HTTP=true \
  ghcr.io/dawg-io/actions-manager:latest
```

`ALLOW_INSECURE_HTTP=true` is required because this command serves the app over plain HTTP: ActionsManager refuses to start on a non-loopback `http://` address without it, and blocks PAT login over non-local HTTP. Drop it once you put ActionsManager behind HTTPS — see [HTTPS setup](SELF_HOSTED_INSTALL.md#using-https-with-reverse-proxy).

3. Open `http://localhost:8080`
4. Click **Sign in with Personal Access Token**
5. Start the container first, then paste your PAT into the login screen so it is not stored in shell history.

> 💡 **Note:** The automated `install.sh` installer still prompts for OAuth credentials today. Use the container command above for the quickest PAT-only install.

### Prerequisites Checklist

Before you start, make sure you have:

- [ ] **Docker or Podman** installed
  - Check: `docker --version` or `podman --version`
- [ ] **Git** (optional but recommended)
  - Check: `git --version`
- [ ] **4GB+ RAM** available
- [ ] **10GB+ disk space** available
- [ ] **GitHub account** with repository access
- [ ] **GitHub PAT ready** or **GitHub OAuth App created**

**Don't have Docker?**
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# macOS
brew install docker
# Run Docker Desktop from Applications or: colima start

# Verify
docker --version
docker compose version
```

### Step 1: Choose Your GitHub Authentication Method (2 minutes)

**Option A — Personal Access Token (fastest)**

1. Go to [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens)
2. Choose **Fine-grained tokens** (recommended) or **Tokens (classic)**
3. Generate a token with the repositories and permissions described in [GitHub PAT Setup](GITHUB_PAT_SETUP.md)
4. Copy the token and keep it secure

**Option B — GitHub OAuth App**

1. Go to [GitHub Settings > Developer settings > OAuth Apps](https://github.com/settings/developers)
2. Click **"New OAuth App"**
3. Fill in the details:
   - **Application name:** `ActionsManager.io` (or your preferred name)
   - **Homepage URL:** `http://localhost:8080`
   - **Authorization callback URL:** `http://localhost:8080/auth/callback`
   - **Application description:** (optional) `Self-hosted GitHub Actions manager`
4. Click **"Register application"**
5. **Copy your Client ID** and generate a **Client Secret** (save these!)

### Step 2: Run the Automated Installer (3 minutes, OAuth-oriented)

**Option A: Direct installation (one command)**

```bash
curl -fsSL https://raw.githubusercontent.com/dawg-io/actions-manager/main/install.sh | bash
```

**Option B: Clone first for more control**

```bash
git clone https://github.com/dawg-io/actions-manager.git
cd actions-manager
chmod +x install.sh
./install.sh
```

### Step 3: Answer Installation Prompts

The installer will ask:

**Port (press Enter for default 8080):**
```
Port [default: 8080]: 
```
→ Just press Enter unless you need a different port

**GitHub OAuth Credentials (from Step 1, only if you chose OAuth):**
```
GitHub Client ID: <paste your Client ID>
GitHub Client Secret: <paste your Client Secret>
```

**License (press Enter to skip — not required for self-hosted beta):**
```
License Key (optional): 
```
→ Leave blank (no paid plans are currently available during beta)

**Admin Credentials:**
```
Admin Username [default: admin]: 
Admin Password: <enter a secure password>
Confirm Admin Password: <re-enter>
```

The installer will then:
- ✅ Validate Docker/Podman
- ✅ Generate secure configuration
- ✅ Build containers (10-15 minutes)
- ✅ Start ActionsManager.io
- ✅ Display your access information

### Step 4: First Login (1 minute)

Once installation completes:

1. **Open your browser:** http://localhost:8080
2. **Choose a sign-in method**
   - **Log in with GitHub** for OAuth
   - **Sign in with Personal Access Token** for PAT login
3. If using OAuth, authorize ActionsManager.io on GitHub
4. If using a PAT, paste your fine-grained or classic PAT and submit it
5. **You're logged in!** Manage saved PATs later from the user menu

> 💡 **Tip:** If PAT login fails, check the token scopes / permissions and selected repositories. If OAuth login fails, ensure the callback URL exactly matches your OAuth app settings.

> ⚠️ **Security Warning:** The quick start uses HTTP on localhost, which is safe for local testing. **Never expose ActionsManager over HTTP on a network or to the internet.** PATs and credentials will be transmitted in plaintext. For any non-localhost deployment, use HTTPS with a reverse proxy (Caddy, Traefik, or nginx). See [HTTPS setup documentation](SELF_HOSTED_INSTALL.md#using-https-with-reverse-proxy) for examples. Starting from this version, ActionsManager blocks PAT login over non-local HTTP by default unless `ALLOW_INSECURE_HTTP=true` is set.

### Step 5: Create Your First Project (1 minute)

1. Click **"Create Project"** on the dashboard
2. Enter project details:
   - **Name:** (e.g., "My Team", "Production Pipelines")
   - **Description:** (optional)
3. Click **"Create"**

### Step 6: Add Repositories (1 minute)

1. In your new project, click **"Add Repository"**
2. **Select repositories** from the dropdown (showing your GitHub repositories)
3. Click **"Add Repositories"**
4. Your repositories now appear in the project

### Step 7: Create Your First Workflow (2 minutes)

1. **Select a repository** from your project
2. Click **"Create Workflow"**
3. **Choose a template** (or start from scratch)
   - Examples: Node.js CI, Python CI, Docker Build
4. **Edit the workflow YAML** if needed
5. **Save and choose delivery method:**
   - Click **"Commit Locally"** to save the workflow draft in Actions Manager
   - **Option A - Direct Commit:** Click **"Direct commit"** to push directly to GitHub
   - **Option B - PR-Based (Recommended):** Click **"Create Pull Requests"** for review workflow
6. **Workflow draft saved locally!** Use **Direct commit** or **Create Pull Requests** when you're ready to push to GitHub

> 💡 **Tip:** For production environments, use **PR-Based delivery** to enable code review. For development, **Direct Commit** is faster. [Learn more about delivery modes →](guides/WORKFLOW_DELIVERY_MODES.md)

🎉 **You're done!** Your first workflow draft is saved locally. When ready, use **Create Pull Requests** to push it to GitHub.

---

## First Workflow Walkthrough

The walkthrough below describes the happy path for a first-time Self-Hosted Beta user — from signing in with a PAT through saving the first local workflow draft.

### 1. Start the self-hosted container

Use the Docker command from [Fastest Path: PAT Quick Install](#fastest-path-pat-quick-install) and open `http://localhost:8080`.

### 2. Sign in using a fine-grained or classic GitHub PAT

On the login screen, choose **Sign in with Personal Access Token**. Paste your PAT and click **Sign In**.

> Do **not** include your PAT in Docker command lines, shell history, screenshots, or GitHub issues. Enter it in the UI after the container starts.

Recommended permissions for the PAT:

| Permission | Level | Required for |
|-----------|-------|-------------|
| Metadata | Read-only | All operations |
| Contents | Read and write | Workflow file management |
| Actions | Read and write | Workflow triggering |
| Pull requests | Read and write | PR-based delivery |
| Secrets | Read and write | Repository secrets management (optional) |
| Variables | Read and write | Repository variables management (optional) |

### 3. From the Saved Projects dashboard, choose `New Project`

After signing in you land on the **Saved Projects** dashboard. The header shows beta usage limits. Click **New Project**.

### 4. Create a Caller Workflow Project

In the **Project Basics** step, enter a project name and choose **Caller Workflow Project** (the most common starting type). Pick an identity color and continue.

### 5. Select repository visibility and choose one or more repositories

Choose **public** or **private** repository visibility, then select the repositories this project should manage. Review the repository summary and continue.

### 6. Keep Prefix Mode enabled unless you intentionally want unmanaged names

On the **Resource Naming and Review** step, **Prefix Mode** is enabled by default. It prefixes generated workflow filenames with a project-specific identifier so ActionsManager-managed workflows are easy to distinguish. Review the final project summary and click **Create Project**.

### 7. Open the new project and choose `Add Workflow`

The project workspace shows the project sidebar and an empty workflow state. Click **Add Workflow**.

### 8. Select `Regular Workflow`

In the **Create New Workflow** modal, choose **Regular Workflow** and click **Next**.

### 9. Create a blank workflow, detect build types, or use a template

Enter a workflow name and select one of the creation options:

- **Open Blank Workflow** — empty YAML editor
- **Detect Build Types** — inspects selected repositories and recommends templates
- **Generate Templates** — curated template library

### 10. Review the YAML in the editor

The workflow editor shows the generated filename (with prefix), the selected repository, and the current **Unsaved** state. Review and edit the YAML as needed.

### 11. Save the workflow as a local draft

Click **Commit Locally**. The workflow is saved immediately, and the editor shows the **New Local** status badge with a toast notification confirming the draft was saved.

> **Saving a draft does not push to GitHub.** The workflow file does not appear in any repository until you create pull requests or use direct commit mode.

### 12. Create pull requests when ready to push the workflow to GitHub

Return to the project workspace and click **Create Pull Requests** to propose the draft workflow to your selected repositories as reviewable pull requests. PR-based delivery is the recommended path for beta testing.

---

## Cloud Deployment Quick Start (Future/Not Beta)

Cloud/SaaS deployment is not part of the first public self-hosted beta. Do not use this path for beta evaluation unless you are intentionally working on future cloud/internal validation.


### Prerequisites

Before you start, ensure you have:

- [ ] **GitHub Marketplace listing** for your application
  - Contact GitHub at marketplace@github.com for approval
- [ ] **GitHub OAuth App** created in your organization
- [ ] **PostgreSQL database** (cloud-hosted or self-managed)
- [ ] **Domain name** with HTTPS configured
- [ ] **Cloud infrastructure** (AWS, Google Cloud, Azure, DigitalOcean, etc.)
- [ ] **Docker Compose** support on your infrastructure

### Step 1: Set Up GitHub Marketplace (5 minutes)

1. Go to [GitHub Marketplace Developer](https://github.com/marketplace/new)
2. **Create your app listing:**
   - Configure webhook URL: `https://your-domain.com/webhooks/marketplace`
   - Set webhook secret (you'll use this in `.env.cloud`)
3. **Test webhook delivery:**
   - GitHub Marketplace > Settings > Webhook deliveries
   - Verify successful webhook deliveries
4. **Note the webhook secret** (save this!)

### Step 2: Clone Repository

```bash
git clone https://github.com/dawg-io/actions-manager.git
cd actions-manager
```

### Step 3: Create Cloud Configuration

```bash
cp .env.cloud.example .env.cloud
```

Edit `.env.cloud` with your settings:

```bash
# ===== INSTALLATION MODE =====
INSTALLATION_MODE=cloud

# ===== GITHUB OAUTH =====
GITHUB_CLIENT_ID=your_oauth_app_client_id
GITHUB_CLIENT_SECRET=your_oauth_app_client_secret

# ===== GITHUB MARKETPLACE WEBHOOK =====
GITHUB_WEBHOOK_SECRET=your_marketplace_webhook_secret
VERIFY_WEBHOOK_IP=false  # Set to true in production with GitHub IP ranges

# ===== DATABASE (PostgreSQL Required) =====
POSTGRES_USER=actions_manager_user
POSTGRES_PASSWORD=strong_random_password_here
POSTGRES_DB=actions_manager_db
POSTGRES_HOST=your-postgres-host.example.com
POSTGRES_PORT=5432
DATABASE_URL=postgresql://actions_manager_user:strong_random_password_here@your-postgres-host.example.com:5432/actions_manager_db

# ===== APPLICATION URLS =====
VITE_BACKEND_URL=https://your-domain.com
VITE_FRONTEND_URL=https://your-domain.com
VITE_WEBSOCKET_URL=wss://your-domain.com/ws

# ===== ADMIN CREDENTIALS =====
ADMIN_USERNAME=admin
ADMIN_PASSWORD=strong_admin_password

# ===== LICENSE (Optional) =====
LICENSE_KEY=your_enterprise_license_key_if_applicable

# ===== SECURITY =====
SECRET_KEY=your_64_character_random_hex_string
```

**Generate SECRET_KEY:**
```bash
# Option 1: Using OpenSSL
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env.cloud

# Option 2: Using Python
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
```

### Step 4: Configure Docker Compose

Update `docker-compose.cloud.yml` to use your PostgreSQL:

```yaml
version: '3.8'

services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      VITE_BACKEND_URL: ${VITE_BACKEND_URL}
      VITE_FRONTEND_URL: ${VITE_FRONTEND_URL}
      VITE_WEBSOCKET_URL: ${VITE_WEBSOCKET_URL}
    depends_on:
      - backend
    restart: unless-stopped

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.cloud
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: ${DATABASE_URL}
      GITHUB_CLIENT_ID: ${GITHUB_CLIENT_ID}
      GITHUB_CLIENT_SECRET: ${GITHUB_CLIENT_SECRET}
      GITHUB_WEBHOOK_SECRET: ${GITHUB_WEBHOOK_SECRET}
      ADMIN_USERNAME: ${ADMIN_USERNAME}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      SECRET_KEY: ${SECRET_KEY}
      INSTALLATION_MODE: cloud
      VERIFY_WEBHOOK_IP: ${VERIFY_WEBHOOK_IP}
    depends_on:
      - postgres
    restart: unless-stopped

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

volumes:
  postgres_data:
```

### Step 5: Build and Deploy

**Build containers:**
```bash
docker compose -f docker-compose.cloud.yml build
```

**Start services:**
```bash
docker compose -f docker-compose.cloud.yml up -d
```

**Verify startup:**
```bash
docker compose -f docker-compose.cloud.yml logs -f
```

Wait for "✓ Application started successfully" message.

### Step 6: Set Up Reverse Proxy

Set up Nginx or Apache to proxy traffic to your backend/frontend.

**Nginx example:**

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    # Marketplace Webhooks
    location /webhooks/marketplace {
        proxy_pass http://localhost:8000/webhooks/marketplace;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### Step 7: Configure Marketplace Webhooks

1. Go to your **GitHub Marketplace app settings**
2. Navigate to **Webhook deliveries**
3. Verify webhook secret is set to `GITHUB_WEBHOOK_SECRET` from `.env.cloud`
4. Test webhook delivery to `https://your-domain.com/webhooks/marketplace`
5. Verify successful delivery (HTTP 200)

### Step 8: First Login

1. Open your domain: `https://your-domain.com`
2. Choose a sign-in method:
   - **Log in with GitHub** for OAuth
   - **Sign in with Personal Access Token** for PAT login
3. If using OAuth, authorize the OAuth app
4. Subscribe to a plan on GitHub Marketplace
5. Your account tier updates automatically!

🎉 **Cloud deployment complete!**

---

## Common First Tasks

### ✅ Task 1: Configure GitHub OAuth (Already Done!)

Your OAuth app is configured during installation. To verify:

1. Go to Admin Panel: `http://localhost:8080/admin` (self-hosted) or `https://your-domain.com/admin`
2. Login with admin credentials
3. Check "GitHub OAuth Status" shows ✓ Active

**Need to update?**
1. Edit `.env.self-hosted` or `.env.cloud`
2. Update `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`
3. Restart: `docker compose -f docker-compose.*.yml restart`

### ✅ Task 2: Set Up Secrets

**Create a repository secret:**

1. From your project, select a repository
2. Click **"Secrets"**
3. Click **"Add Secret"**
4. Enter secret name (e.g., `DOCKER_USERNAME`)
5. Enter secret value
6. Click **"Add"** - Secret synced to GitHub!

**Bulk deploy secrets:**
1. Click **"Bulk Deploy"**
2. Select repositories
3. Select secrets to deploy
4. Confirm - All secrets deployed!

### ✅ Task 3: Use Workflow Templates

**Apply a template to your workflow:**

1. In your repository, click **"Create Workflow"**
2. **Choose a template:**
   - Node.js CI/CD
   - Python CI/CD
   - Docker Build & Push
   - Maven Build
   - .NET Build
   - Go Build
   - Rust Build
   - Custom...
3. **Customize the template** for your needs
4. **Deploy to GitHub**

**Create custom templates:**
1. Go to Admin Panel > Templates
2. Click **"Add Custom Template"**
3. Name your template
4. Write YAML workflow
5. Save - Now available in template list!

### ✅ Task 4: Enable Drift Detection

Monitor when workflows change outside ActionsManager.io:

1. From your repository, click **"Settings"**
2. Toggle **"Enable Drift Detection"** ON
3. ActionsManager.io now monitors for changes
4. When drift detected:
   - 🔔 Alert shown on dashboard
   - Options: Sync from GitHub, Override with ActionsManager.io version

### ✅ Task 5: Invite Team Members

Collaborate with your team:

1. Go to **"Team Settings"** (or Admin Panel for self-hosted)
2. Click **"Add Team Member"**
3. Enter their GitHub username
4. Select permissions:
   - 👁️ View Only
   - ✏️ Editor
   - 🔧 Admin
5. Click **"Invite"** - Invitation sent!

---

## Quick Troubleshooting

### 🔴 Problem: Can't connect to ActionsManager.io

**Self-Hosted:**
```bash
# Check if containers are running
docker compose -f docker-compose.self-hosted.yml ps

# View logs for errors
docker compose -f docker-compose.self-hosted.yml logs

# Verify port is accessible
curl http://localhost:8080
```

**Cloud:**
```bash
# Check container status
docker compose -f docker-compose.cloud.yml ps

# View logs
docker compose -f docker-compose.cloud.yml logs

# Verify HTTPS is working
curl https://your-domain.com
```

### 🔴 Problem: GitHub OAuth login fails

**Solution:**

1. Verify OAuth App settings on GitHub:
   - [GitHub Settings > OAuth Apps](https://github.com/settings/developers)
   - Check Client ID matches your configuration
   - **Authorization callback URL must be exactly:**
     - Self-hosted: `http://localhost:8080/auth/callback`
     - Cloud: `https://your-domain.com/auth/callback`

2. Restart the application:
   ```bash
   docker compose -f docker-compose.*.yml restart
   ```

3. Clear browser cookies and try again in private/incognito window

### 🔴 Problem: Out of memory during build

**Docker:**
1. Open Docker Desktop Settings
2. Go to Resources
3. Increase Memory to 8GB+
4. Click Apply & Restart
5. Retry installation

**Podman:**
```bash
podman machine stop
podman machine set --memory 8192
podman machine start
```

### 🔴 Problem: Port already in use

**Self-Hosted:**
```bash
# Check what's using the port
lsof -i :8080

# Either kill the process or use a different port
# Edit .env.self-hosted and change VITE_BACKEND_URL
# Then rebuild: docker compose -f docker-compose.self-hosted.yml up --build -d
```

### 🔴 Problem: Webhook not receiving events

**Cloud Deployment:**

1. Verify webhook secret matches:
   - GitHub Marketplace settings vs `.env.cloud` `GITHUB_WEBHOOK_SECRET`

2. Check webhook deliveries:
   - GitHub Marketplace > Settings > Webhook deliveries
   - View recent deliveries to see response codes

3. Verify endpoint is accessible:
   ```bash
   curl -X POST https://your-domain.com/webhooks/marketplace \
     -H "Content-Type: application/json" \
     -d '{"test": "webhook"}'
   ```

### 📚 Need More Help?

- **Documentation:** [SELF_HOSTED_INSTALL.md](SELF_HOSTED_INSTALL.md) | [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)
- **GitHub Issues:** [Create an issue](https://github.com/dawg-io/actions-manager/issues)
- **GitHub Discussions:** [Join the community](https://github.com/dawg-io/actions-manager/discussions)

---

## Next Steps

### 🚀 After Basic Setup

1. **Read the feature docs:**
   - [Project Management](../README.md#projects--repositories)
   - [Workflow Creation](../README.md#workflow-creation--management)
   - [Secret Management](../README.md#secrets--environment-management)

2. **Explore the Admin Panel:**
   - System status and health checks
   - User management
   - License information
   - Workflow templates

3. **Configure advanced features:**
   - Custom OAuth apps for different environments
   - Multiple GitHub organizations

### 📚 Recommended Reading

**For Self-Hosted:**
- [SELF_HOSTED_INSTALL.md](SELF_HOSTED_INSTALL.md) - Complete installation reference
- [LICENSE_KEYS.md](LICENSE_KEYS.md) - License-key behavior and future tier notes (for internal/planning reference; no paid plans are currently available during beta)
- [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) - All configuration options

**For Cloud:**
- [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) - Complete cloud setup reference
- [MARKETPLACE_WEBHOOKS.md](../MARKETPLACE_WEBHOOKS.md) - Webhook integration details
- [MARKETPLACE_SUBSCRIPTION_INTEGRATION_SUMMARY.md](../MARKETPLACE_SUBSCRIPTION_INTEGRATION_SUMMARY.md) - Billing system

### 🎓 Learning Resources

1. **GitHub Actions Basics:**
   - [GitHub Actions Documentation](https://docs.github.com/en/actions)
   - [GitHub Actions Examples](https://github.com/actions)

2. **CI/CD Patterns:**
   - [CI/CD Best Practices](https://github.com/dawg-io/actions-manager#core-features)
   - [Workflow Templates](../WORKFLOW_TEMPLATE.md)

3. **Team Collaboration:**
   - Set up OAuth for your organization
   - Create shared workflow templates
   - Enable drift detection for compliance

### 💡 Pro Tips

✨ **Productivity Hacks:**
- Use workflow templates to standardize CI/CD across your team
- Enable drift detection to catch unauthorized changes
- Create separate projects for different teams/departments
- Use secrets bulk deploy to sync across multiple repos
- Set up team members with appropriate permissions

⚡ **Performance Tips:**
- Use GitHub Actions caching in your workflows
- Parallelize jobs when possible
- Set up branch protection rules to require successful builds
- Monitor workflow execution times in ActionsManager.io dashboard

🔒 **Security Best Practices:**
- Rotate admin passwords regularly
- Use strong secrets (Docker credentials, etc.)
- Enable HTTPS for cloud deployments
- Audit team member access regularly
- Keep ActionsManager.io updated with latest security patches

---

## Self-Hosted Beta Limits

ActionsManager Self-Hosted is a **free beta preview**. No paid plans are currently available. The beta limits are:

| Resource | Beta Limit |
|---|---|
| Caller Workflow Projects | 4 |
| Reusable Workflow Projects | 2 |
| Secrets per project | 6 |
| Environment variables per project | 6 |
| GitHub environments per project | 6 |
| Repositories per project | 10 |

All users running the self-hosted beta image get the same limits. Cloud/SaaS and GitHub Marketplace billing are future/planned paths and are not part of the beta.

---

## Summary

### Self-Hosted in 5 Minutes

```bash
# 1. Create GitHub OAuth App (2 min)
# https://github.com/settings/developers → New OAuth App

# 2. Run installer (1 min)
curl -fsSL https://raw.githubusercontent.com/dawg-io/actions-manager/main/install.sh | bash

# 3. Answer prompts (1 min)
# Port, OAuth credentials, admin password

# 4. Wait for build (10-15 min)
# Let Docker build containers

# 5. Login (1 min)
# http://localhost:8080 → Log in with GitHub or Sign in with Personal Access Token

# 6. Create project (1 min)
# Dashboard → Create Project

# 7. Add repos & deploy workflow (2 min)
# Project → Add Repository → Create Workflow
```

### Cloud in 15 Minutes

```bash
# 1. Set up GitHub Marketplace (5 min)
# GitHub Marketplace Developer settings

# 2. Clone & configure (5 min)
# git clone + edit .env.cloud

# 3. Deploy containers (3 min)
# docker compose -f docker-compose.cloud.yml up -d

# 4. Set up reverse proxy (2 min)
# Nginx/Apache configuration

# 5. Configure webhooks (optional, 2 min)
# GitHub Marketplace webhook settings

# 6. Login & subscribe (1 min)
# https://your-domain.com → GitHub Marketplace subscription
```

---

## Success! 🎉

You now have ActionsManager.io running! Next:

1. ✅ Create your first project
2. ✅ Add repositories
3. ✅ Deploy your first workflow
4. ✅ Invite team members
5. ✅ Configure secrets
6. ✅ Enable drift detection

**Questions?** Open an issue on [GitHub](https://github.com/dawg-io/actions-manager/issues)

**Ready to go deeper?** See [SELF_HOSTED_INSTALL.md](SELF_HOSTED_INSTALL.md) or [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)

---

**Last updated:** January 2026  
**Compatible with:** ActionsManager.io 1.0+

*Happy workflow managing! 🚀*
