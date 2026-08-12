# Environment Variables Reference Guide

## Overview

This guide explains environment variables used by Actions Manager. The first public beta is self-hosted only; Cloud/SaaS and GitHub Marketplace variables are retained for future planning/internal validation and are not required for beta users. Environment variables can contain secrets, so never commit a real `.env` file.

### Deployment Modes

ActionsManager supports two distinct deployment modes, each with different environment variable requirements:

| Aspect | Self-Hosted | Cloud |
|--------|-------------|-------|
| **Installation Mode** | `self-hosted` | `cloud` |
| **Architecture** | Single container | Two containers (frontend + backend) |
| **Licensing** | Free during beta; optional future license-key behavior | Future GitHub Marketplace billing |
| **Database** | SQLite (default) or PostgreSQL | PostgreSQL (required) |
| **Marketplace** | Not supported | Required |
| **Target Users** | Self-hosted beta operators | Future SaaS/internal validation |

### How to Use This Guide

1. **Use self-hosted for the public beta** - Cloud mode is future/internal validation only.
2. **Check the "Mode" column** - Variables marked as "Both" work in either mode
3. **Note the "Required" status** - Required variables must be set for deployment
4. **Review the default values** - Many variables have sensible defaults
5. **Check the examples** - See "Common Configuration Scenarios" section for complete examples

---

## Complete Environment Variables Reference

### Installation Mode

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `INSTALLATION_MODE` | ✅ Yes | `self-hosted` | Deployment mode selection | Both | `self-hosted` or `cloud` |

**Details:**
- **Values**: `self-hosted` or `cloud`
- **Purpose**: Determines which features are enabled (marketplace, licensing, etc.)
- **Impact**: Must be set correctly; changing requires application restart
- **Notes**: Cannot be changed after initial setup without reconfiguration. If unset or empty, defaults to `self-hosted`. The official self-hosted image also forces `INSTALLATION_MODE=self-hosted` in `start.sh`, so setting a different value there has no effect.

---

### Application URLs

> **Runtime injection — no rebuild needed.** The self-hosted image bakes placeholder strings into the JS bundle at build time. When the container starts, `start.sh` replaces those placeholders with the values from the environment. You can update any URL variable in `.env.self-hosted`, restart the container, and the new URLs take effect immediately.

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `APP_URL` | ⚠️ See below | auto-detect | Primary simplified all-in-one runtime URL for self-hosted; backend/frontend/ws derived automatically | Self-hosted | `http://192.168.1.100:8080` or `https://actions.example.com` |
| `VITE_APP_URL` | ⚠️ Deprecated alias | `APP_URL` | Deprecated alias for `APP_URL`; still accepted by `start.sh` | Self-hosted | `http://192.168.1.100:8080` or `https://actions.example.com` |
| `VITE_BACKEND_URL` | ⚠️ See below | `APP_URL` / `VITE_APP_URL` or auto-detect | Backend API URL injected into the frontend by `start.sh`; used when no all-in-one app URL is set | Self-hosted | `http://192.168.1.100:8080` |
| `VITE_FRONTEND_URL` | ⚠️ See below | `APP_URL` / `VITE_APP_URL` or auto-detect | Frontend URL injected into the frontend by `start.sh`; used when no all-in-one app URL is set | Self-hosted | `http://192.168.1.100:8080` |
| `VITE_WEBSOCKET_URL` | ⚠️ See below | derived from `APP_URL` / `VITE_APP_URL` or auto-detect | WebSocket URL injected into the frontend by `start.sh`; used when no all-in-one app URL is set | Self-hosted | `ws://192.168.1.100:8080/ws` |

> **Backward compatibility:** `VITE_APP_URL` and `REACT_APP_BACKEND_URL` / `REACT_APP_FRONTEND_URL` / `REACT_APP_WEBSOCKET_URL` from older `.env.self-hosted` files are still accepted by `start.sh` as deprecated fallbacks. Existing files do not need to be updated immediately.

**Self-hosted: auto-detection vs explicit URL**

For self-hosted deployments, URL configuration is **optional**. When left unset, the frontend auto-detects the browser's current URL (`window.location`). This means:

- A user accessing via `http://192.168.1.100:8080` automatically sends API calls to that same URL
- A user accessing via `http://localhost:8080` automatically sends API calls to that same URL
- No configuration changes are needed when the server IP changes

**For PAT login:** Leave URL configuration commented out (auto-detection works perfectly).

**For GitHub OAuth login:** Set `APP_URL` to the actual URL that browsers will use to reach the server. `VITE_APP_URL` still works as a deprecated alias. GitHub needs this fixed callback URL registered in your OAuth App settings. Use the IP or domain users type in their browser — not `localhost` for shared servers.

```bash
# PAT login (recommended): no URL config needed
# (Frontend auto-detects via window.location)

# OAuth login: simple option — set APP_URL and everything is derived
APP_URL=http://192.168.1.100:8080
# Plain http:// on a non-loopback address — required, or startup fails
ALLOW_INSECURE_HTTP=true
# Results in:
#   backend  → http://192.168.1.100:8080
#   frontend → http://192.168.1.100:8080
#   websocket → ws://192.168.1.100:8080/ws   (wss:// for https://)

# Advanced: override each URL individually (rarely needed)
# VITE_BACKEND_URL=http://192.168.1.100:8080
# VITE_FRONTEND_URL=http://192.168.1.100:8080
# VITE_WEBSOCKET_URL=ws://192.168.1.100:8080/ws
```

**Configuration priority (frontend runtime URL resolution):**
1. `APP_URL` — primary all-in-one self-hosted option; remaining URLs derived from it (runtime, injected by `start.sh`)
2. `VITE_APP_URL` — deprecated alias for `APP_URL`
3. `VITE_BACKEND_URL` / `VITE_FRONTEND_URL` / `VITE_WEBSOCKET_URL` — explicit per-service fallback when no all-in-one app URL is set
4. Legacy `REACT_APP_*` — backward-compat fallbacks accepted by `start.sh` and backend/Docker startup paths
5. `window.location` auto-detection — default when none of the above are set

**Details:**
- **`APP_URL`** (simplified, recommended for self-hosted):
  - Set this single variable to your server's URL for OAuth login
  - `start.sh` derives `BACKEND_URL`, `FRONTEND_URL`, and `WEBSOCKET_URL` from it automatically
  - `https://` input produces a `wss://` WebSocket URL; `http://` produces `ws://`
  - Not needed for PAT login (auto-detection works)

- **`VITE_APP_URL`**:
  - Deprecated alias for `APP_URL`
  - Still works for backward compatibility, but new configs should use `APP_URL`

- **`VITE_BACKEND_URL`** / **`VITE_FRONTEND_URL`** / **`VITE_WEBSOCKET_URL`**:
  - Runtime values injected into the built JS by `start.sh` at container startup
  - Used when `APP_URL` / `VITE_APP_URL` are not set
  - Also used in `frontend/.env` for local Vite dev server runs
  - Must be accessible from client browsers

**Common Mistakes:**
- ❌ Setting `APP_URL=http://localhost:8080` on a shared server — remote users' browsers can't reach `localhost` on the server
- ❌ Using `http://localhost:8000` (backend dev port) or `http://localhost:3000` (frontend dev port)
- ❌ Mismatched protocols (http vs https)
- ✅ Self-hosted with PAT login: leave URL config commented out (auto-detection handles it)
- ❌ Setting a non-loopback `http://` `APP_URL` without `ALLOW_INSECURE_HTTP=true` — the container refuses to start
- ✅ Self-hosted with OAuth login: `APP_URL=http://YOUR_SERVER_IP:8080` plus `ALLOW_INSECURE_HTTP=true`
- ✅ Self-hosted with OAuth login: `VITE_APP_URL=http://YOUR_SERVER_IP:8080` (deprecated alias)

---

### GitHub Authentication Configuration

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `GITHUB_CLIENT_ID` | ❌ No | Not set | GitHub OAuth app client ID | Both | `abc123def456` |
| `GITHUB_CLIENT_SECRET` | ❌ No | Not set | GitHub OAuth app client secret | Both | `gho_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxyyyyyyy` |
| `GITHUB_TOKEN` | ❌ No | Not set | Server-level GitHub token for automation / service operations | Both | `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `GITHUB_PR_WEBHOOK_SECRET` | ❌ No | Not set | Shared secret for verifying inbound GitHub webhooks | Both | `abc123def456ghi789jkl012` |
| `GITHUB_TIMEOUT_SECONDS` | ❌ No | `30` | Timeout for outbound GitHub API requests | Both | `30` |

**Details:**
- **`GITHUB_PR_WEBHOOK_SECRET`**:
  - Verifies `X-Hub-Signature-256` on requests to `POST /webhooks/github` using HMAC-SHA256
  - Must match the **Secret** field configured on the webhook in GitHub
  - Generate with: `openssl rand -hex 32`
  - **When this is unset, every inbound webhook is rejected.** The endpoint will not accept
    unauthenticated state changes, so leaving it unset is safe — the feature is simply inactive
  - Only needed if you want GitHub to notify this instance. Workflow delivery and drift detection
    call *out* to GitHub and need no inbound access
  - See [Exposing the Webhook Endpoint](guides/WEBHOOK_ENDPOINT.md) for reachability
    options, including instances with no public URL

- **`GITHUB_CLIENT_ID` & `GITHUB_CLIENT_SECRET`**:
  - Obtained from GitHub Settings → Developer settings → OAuth Apps
  - Required only for browser-based OAuth login
  - OAuth App **Authorization callback URL** must be set to: `{VITE_BACKEND_URL}/auth/callback`
  - OAuth App **Homepage URL** should be: `{VITE_FRONTEND_URL}`
  - In self-hosted mode both URLs are the same (e.g. `http://localhost:8080`)
  - Keep `GITHUB_CLIENT_SECRET` private (don't commit to git)
  - PAT login through the UI does not require these values at startup

- **`GITHUB_TOKEN`** (Optional):
  - Server-level token for automated GitHub API operations
  - Not the same as a user-level saved PAT configured through the UI
  - Most self-hosted users should sign in with a PAT in the app instead of storing a personal token in `.env`
  - If used as a classic token, the current implementation expects scopes such as `repo`, `workflow`, `read:org`, and `user:email`

**Security Notes:**
- Store secrets in `.env` file (which should be in `.gitignore`)
- Use environment-specific values in production
- Rotate tokens periodically
- Prefer UI-configured fine-grained PATs for normal user authentication
- Use secrets management service (e.g., AWS Secrets Manager, HashiCorp Vault)
- Never commit secrets to version control

---

### Drift Detection Sweep

ActionsManager re-checks projects for drift on a background schedule, so a
project cannot sit showing "in sync" while the workflow has been edited on
GitHub. Nothing needs configuring for this to work — the defaults are sensible.

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `DRIFT_SWEEP_ENABLED` | ❌ No | `true` | Master switch for automatic drift re-checking | Both | `false` |
| `DRIFT_RECHECK_INTERVAL_MINUTES` | ❌ No | `15` | How stale a project's last check must be before it is re-checked | Both | `30` |
| `DRIFT_SWEEP_BATCH_SIZE` | ❌ No | `5` | Projects checked per tick, capping burst API usage | Both | `10` |
| `DRIFT_SWEEP_POLL_SECONDS` | ❌ No | `60` | How often the worker wakes to look for due projects | Both | `120` |

**Details:**
- **Cost is low by design.** An unchanged branch answers GitHub's conditional
  request with a `304`, which does **not** count against the rate limit, so
  re-checking a quiet project costs roughly one call per repository. Raise
  `DRIFT_RECHECK_INTERVAL_MINUTES` if you run many projects against a tight
  rate limit.
- The worker wakes often but only picks up projects older than the recheck
  interval, which staggers load instead of checking everything at once.
- **A project is only checked if its owner has a usable GitHub credential.** A
  saved PAT works with no one logged in; an OAuth session token only lasts
  until the server restarts. Projects without one are skipped and keep their
  previous "last checked" time rather than being falsely marked as checked.
- **Repeated failures back off.** A project whose check keeps failing (expired
  token, rate limit, repository no longer readable) waits twice as long after
  each consecutive failure, up to 32× `DRIFT_RECHECK_INTERVAL_MINUTES`. The
  first successful check resets it. Projects behind a failing or skipped one
  are not held up.
- **The sweep only reads.** It never pushes to GitHub; every write still comes
  from a resolution someone chose.
- Setting `DRIFT_SWEEP_ENABLED=false` stops all automatic checking; drift then
  only updates when someone clicks **Check Now** (or when a resolution clears
  it).

---

### Build Metrics Sync

Workflow runs are stored locally so the [Build Metrics](features/build-metrics.md)
panel can be opened without spending GitHub API calls. Runs are re-fetched only
when the stored copy is stale, or when someone presses **Refresh**.

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `BUILD_METRICS_SYNC_INTERVAL_MINUTES` | ❌ No | `15` | How stale stored runs must be before opening the panel triggers a sync | Both | `30` |

**Details:**
- **A sync costs one call per repository**, not one per workflow — a single
  listing returns every workflow's runs. Raise the interval if you run many
  projects against a tight rate limit.
- Unlike the drift sweep, this is not a background worker: nothing is fetched
  until someone opens the panel. There is no switch to disable it, because a
  project nobody looks at never syncs.
- **Refresh always syncs**, regardless of the interval.
- A failed sync does not advance the staleness cursor, so the next open retries
  rather than reporting stale numbers as fresh.

---

### License Configuration (Self-Hosted Only)

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `LICENSE_KEY` | ❌ No | — | Vendor-issued JWT-signed license key (reserved for future paid tiers; no paid plans are currently available during beta) | Self-hosted | `****** |

**Details:**
- **Beta note:** No paid plans are currently available. The beta runs without a license key; leaving `LICENSE_KEY` unset is the correct configuration for the self-hosted beta. The license-key code path is retained for future commercial tier behavior.

- **JWT License Format** (for future use):
  - Signed using RS256 algorithm
  - Required payload: `{"tier": "professional"}` or `"enterprise"`
  - Optional payload: `{"tier": "professional", "exp": 1735689600}`
  - Customers configure only `LICENSE_KEY`; no customer-provided signing secret is required

- **Supported Tiers (internal/future)**:
  - `free` - Legacy default; 3 projects, 2 secrets per project (not used in self-hosted beta)
  - `professional` / `pro` - 10 projects, 10 secrets per project (not currently available)
  - `enterprise` - Unlimited projects and secrets (not currently available)

- **Self-Hosted Beta Limits** (current, no license key required):
  - 4 Caller Workflow Projects
  - 2 Reusable Workflow Projects
  - 6 secrets per project
  - 6 environment variables per project
  - 6 GitHub deployment environments per project
  - Public and private repositories allowed

- **License Issuance**:
  - Professional and Enterprise license keys are issued by the vendor.
  - Maintainer-only signing material must not be sent to self-hosted customers.

- **Validation**:
  - Happens at application startup
  - Result is cached for application lifetime
  - Invalid/expired licenses fall back to free tier
  - No network calls needed (purely cryptographic)

- **Error Handling**:
  - Invalid format → free tier fallback, with warning
  - Expired license → free tier fallback, with warning
  - Invalid signature → free tier fallback, with warning
  - No license → self-hosted beta limits (normal operation)

**Note:** This is only used in `INSTALLATION_MODE=self-hosted`. Cloud mode refuses self-hosted license-key configuration and uses GitHub Marketplace for tier management.
---

### Database Configuration

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `DATABASE_URL` | ❌ No (Self-hosted) / ✅ Yes (Cloud) | SQLite (self-hosted only) | Database connection string | Both | `postgresql://user:pass@localhost:5432/actions_manager` |
| `POSTGRES_USER` | ❌ No | Not set | PostgreSQL username | Both | `actions_manager` |
| `POSTGRES_PASSWORD` | ❌ No | Not set | PostgreSQL password | Both | `secure_password_123` |
| `POSTGRES_DB` | ❌ No | `actions_manager` | PostgreSQL database name | Both | `actions_manager` |
| `POSTGRES_HOST` | ❌ No | `localhost` | PostgreSQL host | Both | `db` (docker) or `db.example.com` (cloud) |
| `POSTGRES_PORT` | ❌ No | `5432` | PostgreSQL port | Both | `5432` |

**Details:**

- **Default Behavior (Self-Hosted)**:
  - If `DATABASE_URL` not set: Uses SQLite in `/app/data/database.db`
  - SQLite suitable for teams < 10 users
  - No additional setup required

- **PostgreSQL Setup**:
  - Required for cloud deployments
  - Recommended for self-hosted with > 100 concurrent users
  - Connection string format: `postgresql://[user[:password]@][netloc][:port][/dbname][?param1=value1&...]`
  
  - **Docker Compose Example**:
    ```yaml
    services:
      db:
        image: postgres:15
        environment:
          POSTGRES_USER: actions_manager
          POSTGRES_PASSWORD: secure_password
          POSTGRES_DB: actions_manager
        volumes:
          - postgres_data:/var/lib/postgresql/data
    
    volumes:
      postgres_data:
    ```

  - **Connection String Examples**:
    - Local: `postgresql://user:password@localhost:5432/actions_manager`
    - Docker: `postgresql://user:password@db:5432/actions_manager`
    - Cloud RDS: `postgresql://user:password@mydb.xxxxx.rds.amazonaws.com:5432/actions_manager`

- **Database Initialization**:
  - Tables auto-created on first startup
  - Run migrations automatically
  - No manual schema setup needed

- **Connection Pooling**:
  - SQLAlchemy handles pooling
  - Default: 5-10 connections
  - Cloud deployments should use PgBouncer for connection pooling

**Recommendations**:
- **Development**: SQLite is fine
- **Small teams (< 10 users)**: SQLite acceptable
- **Medium teams (10-100 users)**: PostgreSQL recommended
- **Large teams (> 100 users)**: PostgreSQL required
- **Production**: Always use PostgreSQL with backups

---

### GitHub Marketplace & Webhooks (Cloud Only)

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `GITHUB_WEBHOOK_SECRET` | ✅ Yes | N/A | Secret for validating webhook signatures | Cloud | `abc123def456ghi789jkl012` |
| `GITHUB_WEBHOOK_IPS` | ❌ No | All allowed | Comma-separated GitHub webhook IP CIDR ranges | Cloud | `192.30.252.0/22,185.199.108.0/22,140.82.112.0/20` |
| `VERIFY_WEBHOOK_IP` | ❌ No | `false` | Enable webhook source IP verification | Cloud | `true` |
| `WEBHOOK_RATE_LIMIT` | ❌ No | `60` | Rate limit for webhook endpoints (requests/min) | Cloud | `60` |
| `USE_STUBBED_MARKETPLACE_API` | ❌ No | `false` | Use stubbed API for testing (dev only) | Cloud | `true` |

**Details:**

- **`GITHUB_WEBHOOK_SECRET`**:
  - Used for HMAC-SHA256 signature verification
  - Generate with: `openssl rand -hex 32`
  - Must match secret configured in GitHub Marketplace settings
  - **Never hardcode in code; use environment variable only**
  - Critical for security; validates webhooks are from GitHub

  - **Generating**:
    ```bash
    # Generate 32-byte random hex string
    openssl rand -hex 32
    # Output: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
    ```

- **`GITHUB_WEBHOOK_IPS`**:
  - GitHub publishes webhook IP ranges at: `https://api.github.com/meta`
  - Format: Comma-separated CIDR ranges
  - Only required if `VERIFY_WEBHOOK_IP=true`
  - Must be updated periodically (GitHub may change IPs)
  - Example update script:
    ```bash
    curl -s https://api.github.com/meta | jq -r '.hooks[]' | tr '\n' ','
    ```

- **`VERIFY_WEBHOOK_IP`**:
  - When `true`: Validates webhook source IP is from GitHub
  - When `false`: Skips IP verification (less secure)
  - Recommended: Always `true` in production
  - Requires `GITHUB_WEBHOOK_IPS` to be configured

- **`WEBHOOK_RATE_LIMIT`**:
  - Requests per minute limit for webhook endpoints
  - Prevents abuse and DoS attacks
  - Typical value: 60 req/min
  - Adjust based on marketplace event volume
  - Excess requests get HTTP 429 response

- **`USE_STUBBED_MARKETPLACE_API`**:
  - For development/testing only
  - When `true`: Returns mock data instead of real GitHub API calls
  - Should be `false` in production
  - Useful for webhook testing without hitting GitHub API

**Webhook Signature Verification**:
```python
import hmac
import hashlib

def verify_webhook_signature(payload_body, signature, secret):
    """Verify GitHub webhook signature"""
    expected_sig = 'sha256=' + hmac.new(
        secret.encode(),
        payload_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_sig)
```

**Security Checklist**:
- ✅ Generate strong `GITHUB_WEBHOOK_SECRET` (32+ chars, truly random)
- ✅ Set `VERIFY_WEBHOOK_IP=true` for production
- ✅ Configure correct `GITHUB_WEBHOOK_IPS`
- ✅ Implement rate limiting
- ✅ Log all webhook events for audit trail
- ✅ Monitor webhook delivery in GitHub settings
- ✅ Implement retry logic for failed webhook processing

---

### Admin Panel Configuration

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `ADMIN_USERNAME` | Future cloud/admin only | unset | Username for admin panel access if enabled | Cloud/future admin | `unique_admin_user` |
| `ADMIN_PASSWORD` | Future cloud/admin only | unset | Password for admin panel access if enabled | Cloud/future admin | `openssl rand -base64 32` |

**Details:**

- **Purpose**: Controls access to admin panel for user and system management
- **Default Credentials**: Placeholder admin credentials must not be used for exposed deployments
- **Security**: Must be changed immediately after deployment
- **Access**: Admin panel typically at `/admin` path
- **Storage**: Credentials should be in environment, not hardcoded

**Security Best Practices**:
- ❌ Use placeholder credentials in any exposed deployment
- ❌ Share credentials in documentation
- ❌ Commit `.env` file with real credentials
- ✅ Generate strong passwords (16+ chars, mix of character types)
- ✅ Change credentials immediately after deployment
- ✅ Use secrets management service
- ✅ Rotate credentials periodically
- ✅ Log all admin actions
- ✅ Restrict admin panel by IP if possible

**Strong Password Requirements**:
- Minimum 16 characters
- Mix of uppercase, lowercase, numbers, symbols
- Not based on dictionary words
- Unique per deployment
- Change every 90 days

---

### Security Settings

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `SECRET_KEY` | ✅ Yes (for PAT login) | none | Encryption key for saved GitHub PATs/OAuth tokens at rest | Both | output of `openssl rand -hex 32` |
| `ENVIRONMENT` | ❌ No | `production` | Operational environment; drives auto-disable of API docs and other production hardening checks | Both | `production` or `development` |
| `ALLOW_INSECURE_HTTP` | ❌ No | `false` | Allow startup and PAT login/token endpoints over plain HTTP on non-loopback hosts | Both | `true` |
| `CORS_ALLOWED_ORIGINS` | ⚠️ Recommended | none (falls back to `APP_URL` / `VITE_APP_URL` / `VITE_FRONTEND_URL`, then wildcard) | Comma-separated list of allowed CORS origins | Both | `https://actionsmanager.example.com` |
| `DISABLE_API_DOCS` | ❌ No | (auto) | Disable FastAPI interactive docs (`/docs`, `/redoc`, `/openapi.json`) | Both | `true` |
| `DEBUG_MODE` | ❌ No | `false` | Enable verbose debug logging | Both | `true` |
| `USE_MOCK_RESPONSES` | ❌ No | `false` | Use mock data instead of GitHub API | Both | `true` |

**Details:**

- **`SECRET_KEY`**:
  - Required for PAT login — without it, saving/encrypting a PAT fails with a 503 rather than falling back to any default key
  - Generate once with `openssl rand -hex 32` and keep it stable across restarts; changing it invalidates previously-saved tokens
  - Never commit this value or share it between deployments

- **`ENVIRONMENT`**:
  - Values: `production` (default) or `development`
  - Unset, empty, or an unrecognized value all resolve to `production` — the app fails closed toward the hardened setting rather than the permissive one
  - `production` auto-disables `/docs`/`/openapi.json` unless `DISABLE_API_DOCS=false` is explicitly set, and tightens other startup validation checks
  - `.env.self-hosted.example` sets this to `production` by default

- **`ALLOW_INSECURE_HTTP`**:
  - Required for the app to start when the effective app URL is non-loopback HTTP (for example `APP_URL=http://192.168.1.100:8080`)
  - Also required to use PAT login/token endpoints over plain HTTP from a non-localhost origin as defense-in-depth
  - Not needed when accessing via `localhost` / other loopback hosts or when the deployment is behind HTTPS

- **`CORS_ALLOWED_ORIGINS`**:
  - First in the CORS-origin resolution order, checked before `APP_URL` / `VITE_APP_URL` / `VITE_FRONTEND_URL` fallbacks
  - If left unset and no fallback resolves either, CORS defaults to a wildcard (`*`) with a runtime warning printed, and credentialed requests are automatically rejected in that case
  - Set this explicitly for any deployment reachable by more than one trusted origin

- **`DISABLE_API_DOCS`**:
  - When `true`: Disables `/docs`, `/redoc`, and `/openapi.json` endpoints
  - When `false`: Keeps docs enabled regardless of environment
  - When unset: Auto-disables in production (`ENVIRONMENT=production`), enabled in development
  - Reduces attack surface on exposed instances by hiding API endpoint discovery
  - For local beta development, docs remain available by default

- **`DEBUG_MODE`**:
  - When `true`: Enables verbose logging of all operations
  - Includes API requests, responses, database queries
  - May log sensitive information (use with caution)
  - Useful for troubleshooting issues
  - Performance impact: ~5-10% slower
  - Should be `false` in production

- **`USE_MOCK_RESPONSES`**:
  - When `true`: Returns mock GitHub data (no API calls)
  - Useful for development without valid OAuth credentials
  - Simulates user repositories and workflows
  - Does not require GitHub authentication
  - Should be `false` in production
  - Never enable in production (security risk)

**When to Enable Debug Mode**:
- Troubleshooting authentication issues
- Investigating performance problems
- Testing webhook handling
- Debugging marketplace integration
- API integration issues

**Disabling in Production**:
```bash
# .env.production
DEBUG_MODE=false
USE_MOCK_RESPONSES=false
```

---

### Development & Debug Settings

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `DEBUG_MODE` | ❌ No | `false` | Enable debug logging | Both | `true` |
| `USE_MOCK_RESPONSES` | ❌ No | `false` | Use mock GitHub data | Both | `true` |

**See Security Settings section above for details.**

---

### Container & Build Settings

The frontend uses **Vite** as the build tool (replacing Create React App). File-watching polling for Docker volumes is configured in `vite.config.ts` (`server.watch.usePolling: true`) rather than via environment variables.

| Variable | Required | Default | Description | Mode | Example |
|----------|----------|---------|-------------|------|---------|
| `NODE_OPTIONS` | ❌ No | — | Node.js memory limit during build | Both | `--max-old-space-size=4096` |

**Notes:**
- `WATCHPACK_POLLING`, `CHOKIDAR_USEPOLLING`, `CHOKIDAR_INTERVAL`, `GENERATE_SOURCEMAP`, and `INLINE_RUNTIME_CHUNK` were webpack/CRA-specific and are no longer used.
- Source map generation is controlled by `build.sourcemap` in `vite.config.ts`.

---

## Configuration Examples by Deployment Scenario

### Example 1: Basic Self-Hosted (Development)

```bash
# URLs (read by the backend Python process for OAuth and CORS;
# also injected into the frontend JS bundle by start.sh at container startup)
APP_URL=http://localhost:8080

# GitHub OAuth (from https://github.com/settings/developers)
GITHUB_CLIENT_ID=your_client_id_here
GITHUB_CLIENT_SECRET=your_client_secret_here

# Admin (CHANGE THESE!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_this_password

# Development
DEBUG_MODE=false
USE_MOCK_RESPONSES=false
```

**Setup Steps**:
1. Create `.env.self-hosted` with above content
2. Register GitHub OAuth app at https://github.com/settings/developers
3. Set OAuth callback URL to `http://localhost:8080/auth/callback`
4. Copy Client ID and Secret to `.env.self-hosted`
5. Run: `docker compose -f docker-compose.self-hosted.yml up --build`
6. Access at http://localhost:8080

---

### Example 2: Production Self-Hosted with PostgreSQL

```bash
# URLs (use your actual domain)
APP_URL=https://workflows.company.com

# GitHub OAuth
GITHUB_CLIENT_ID=your_prod_client_id
GITHUB_CLIENT_SECRET=your_prod_client_secret

# Database (PostgreSQL required for production)
DATABASE_URL=postgresql://actions_manager:SecurePassword123!@postgres-prod.company.com:5432/actions_manager
POSTGRES_HOST=postgres-prod.company.com
POSTGRES_PORT=5432
POSTGRES_DB=actions_manager
POSTGRES_USER=actions_manager
POSTGRES_PASSWORD=SecurePassword123!

# Licensing (Professional tier for larger teams)
LICENSE_KEY=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...

# Admin (CHANGE IMMEDIATELY!)
ADMIN_USERNAME=sysadmin
ADMIN_PASSWORD=GeneratedSecurePasswordWith32CharsMinimum!

# Production settings
DEBUG_MODE=false
USE_MOCK_RESPONSES=false
```

**Setup Steps**:
1. Set up PostgreSQL database with backups
2. Create `.env.self-hosted` with above values
3. Register production GitHub OAuth app
4. Update OAuth callback URL to production domain
5. Add the vendor-issued `LICENSE_KEY` for Professional/Enterprise tiers, or leave it unset for Free
6. Use SSL/TLS certificate for HTTPS
7. Set up reverse proxy (nginx/caddy) for SSL termination
8. Configure monitoring and logging
9. Run with production docker-compose
10. Set up regular backups

---

### Example 3: Cloud Deployment with Marketplace Integration

```bash
# Installation
INSTALLATION_MODE=cloud

# URLs (use your actual domain)
VITE_BACKEND_URL=https://api.example.com
VITE_FRONTEND_URL=https://example.com
VITE_WEBSOCKET_URL=wss://api.example.com/ws

# GitHub OAuth
GITHUB_CLIENT_ID=your_cloud_client_id
GITHUB_CLIENT_SECRET=your_cloud_client_secret

# Database (PostgreSQL required)
DATABASE_URL=postgresql://user:password@db:5432/actions_manager
POSTGRES_USER=actions_manager
POSTGRES_PASSWORD=SecurePassword456!
POSTGRES_DB=actions_manager
POSTGRES_HOST=db
POSTGRES_PORT=5432

# GitHub Marketplace & Webhooks (REQUIRED for cloud)
GITHUB_WEBHOOK_SECRET=abc123def456ghi789jkl012mno345pqr678stu901vwx
GITHUB_WEBHOOK_IPS=192.30.252.0/22,185.199.108.0/22,140.82.112.0/20,143.55.64.0/20
VERIFY_WEBHOOK_IP=true
WEBHOOK_RATE_LIMIT=60

# Admin
ADMIN_USERNAME=cloudadmin
ADMIN_PASSWORD=GeneratedSecureCloudAdminPassword32Chars!

# Production settings
DEBUG_MODE=false
USE_MOCK_RESPONSES=false
```

**Setup Steps**:
1. Set up PostgreSQL database with connection pooling
2. Register GitHub OAuth app for your domain
3. Set OAuth callback URL to `https://api.example.com/auth/callback`
4. Register GitHub Marketplace app
5. Generate webhook secret: `openssl rand -hex 32`
6. Create `.env.cloud` with above values
7. Set up SSL/TLS certificates
8. Configure DNS for both frontend and API domains
9. Deploy with `docker compose -f docker-compose.cloud.yml`
10. Configure GitHub Marketplace app webhook to point to your domain
11. Set up monitoring and alert on webhook failures
12. Configure CDN for static assets

---

## Best Practices for Secrets Management

### 1. Never Commit Secrets to Version Control

```bash
# .gitignore - ensure these files are ignored
.env
.env.local
.env.*.local
.env.production
.env.cloud
.env.self-hosted
.secret
```

### 2. Use Environment-Specific .env Files

```bash
# Development
.env.development

# Self-hosted production
.env.self-hosted.production

# Cloud production
.env.cloud.production

# Load appropriate file based on deployment
docker compose --env-file .env.cloud.production -f docker-compose.cloud.yml up
```

### 3. Use Secrets Management Services

- **AWS**: AWS Secrets Manager or Parameter Store
- **Azure**: Azure Key Vault
- **Google Cloud**: Cloud Secret Manager
- **HashiCorp**: Vault
- **Docker**: Docker Secrets (for swarm mode)
- **Kubernetes**: Kubernetes Secrets

**Example with AWS Secrets Manager**:
```bash
#!/bin/bash
# Get secrets from AWS and load into environment
export GITHUB_CLIENT_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id github-client-secret \
  --query SecretString --output text)

export ADMIN_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id admin-password \
  --query SecretString --output text)

docker compose up
```

### 4. Principle of Least Privilege

- Use service accounts with minimal required permissions
- Separate secrets per service/environment
- Rotate credentials regularly
- Remove/revoke unused credentials

### 5. Audit and Logging

```bash
# Log secret usage (without exposing values)
echo "Starting deployment with secrets from: AWS Secrets Manager"
echo "Time: $(date)"
echo "Deployer: $(whoami)"
echo "Host: $(hostname)"

# Rotate secrets
aws secretsmanager rotate-secret --secret-id github-client-secret
```

### 6. CI/CD Integration

**GitHub Actions Example**:
```yaml
name: Deploy to Production
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy
        env:
          GITHUB_CLIENT_SECRET: ${{ secrets.GITHUB_CLIENT_SECRET }}
          ADMIN_PASSWORD: ${{ secrets.ADMIN_PASSWORD }}
          LICENSE_KEY: ${{ secrets.LICENSE_KEY }}
        run: |
          docker compose -f docker-compose.self-hosted.yml up -d
```

### 7. .env File Template

Create `.env.example` (safe to commit) without actual values:
```bash
# Installation
# INSTALLATION_MODE=self-hosted  # the official self-hosted image forces this

# URLs
APP_URL=http://localhost:8080

# GitHub OAuth (get from https://github.com/settings/developers)
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Database
DATABASE_URL=

# Admin (CHANGE THESE IN PRODUCTION!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=

# Development
DEBUG_MODE=false
USE_MOCK_RESPONSES=false
```

---

## Troubleshooting Common Variable Configuration Issues

### Issue: "redirect_uri mismatch" Error

**Symptom**: OAuth login fails with "The redirect_uri is not associated with this application"

**Cause**: `VITE_BACKEND_URL` doesn't match the GitHub OAuth app callback URL

**Solution**:
1. Check your `VITE_BACKEND_URL` value (the backend uses this to construct the OAuth `redirect_uri`)
2. Go to GitHub Settings → Developer settings → OAuth Apps
3. Edit your OAuth app
4. Set **Authorization callback URL** to: `{VITE_BACKEND_URL}/auth/callback`
5. Set Homepage URL to: `{VITE_FRONTEND_URL}`
6. Restart the application
7. Test the OAuth flow again

**Common Mistakes**:
- ❌ Using localhost:8000 instead of localhost:8080 (wrong port for self-hosted)
- ❌ Missing `/auth/callback` path
- ❌ Using http instead of https in production
- ❌ Trailing slash mismatch (e.g. `http://localhost:8080/auth/callback/`)
- ❌ Setting the callback URL to `VITE_FRONTEND_URL` when it differs from `VITE_BACKEND_URL` (cloud mode)
- ✅ Exact match between `VITE_BACKEND_URL` + `/auth/callback` and the GitHub OAuth app callback

---

### Issue: Cannot Connect to Database

**Symptom**: "PostgreSQL connection refused" or "database not found"

**Cause**: `DATABASE_URL` is incorrect or database service not running

**Solutions**:

1. **Verify connection string format**:
   ```bash
   # Correct format
   postgresql://username:password@hostname:port/dbname
   
   # Check your values:
   # username: POSTGRES_USER
   # password: POSTGRES_PASSWORD
   # hostname: POSTGRES_HOST (use 'db' for Docker Compose)
   # port: POSTGRES_PORT (default 5432)
   # dbname: POSTGRES_DB
   ```

2. **Test connection directly**:
   ```bash
   # Install psql client
   apt-get install postgresql-client
   
   # Test connection
   psql postgresql://user:password@db:5432/actions_manager
   ```

3. **Check if PostgreSQL is running**:
   ```bash
   # Docker Compose
   docker compose ps
   
   # Verify 'db' service is 'Up'
   # If not running: docker compose up -d db
   ```

4. **Check logs**:
   ```bash
   # View application logs
   docker compose logs -f backend
   
   # Look for database connection errors
   ```

5. **Verify credentials**:
   ```bash
   # In docker-compose.yml, verify environment variables match DATABASE_URL
   POSTGRES_USER=user
   POSTGRES_PASSWORD=password
   POSTGRES_DB=actions_manager
   ```

---

### Issue: Webhook Signature Verification Fails

**Symptom**: "Invalid webhook signature" errors in logs; GitHub marketplace webhooks not processed

**Cause**: `GITHUB_WEBHOOK_SECRET` mismatch or not set

**Solutions**:

1. **Generate new webhook secret**:
   ```bash
   # Generate 32-byte random hex
   openssl rand -hex 32
   # abc123def456ghi789jkl012mno345pqr678stu
   ```

2. **Update environment variable**:
   ```bash
   GITHUB_WEBHOOK_SECRET=abc123def456ghi789jkl012mno345pqr678stu
   ```

3. **Update GitHub webhook configuration**:
   - Go to GitHub Settings → Marketplace → Manage
   - Edit webhook settings
   - Set Webhook secret to same value as `GITHUB_WEBHOOK_SECRET`
   - Save

4. **Verify in application logs**:
   ```bash
   docker compose logs -f backend | grep -i webhook
   ```

5. **Test webhook delivery**:
   - Go to GitHub Marketplace settings
   - Look for Recent Deliveries
   - Check delivery status (green = success, red = failure)
   - Click to view payload and response

---

### Issue: WebSocket Connection Fails

**Symptom**: Real-time updates not working; WebSocket connection refused

**Cause**: `VITE_WEBSOCKET_URL` incorrect or WebSocket not proxied properly

**Solutions**:

1. **Verify WebSocket URL format**:
   ```bash
   # Self-hosted (http)
   ws://localhost:8080/ws
   
   # Production (https)
   wss://api.yourdomain.com/ws
   
   # Make sure protocol matches:
   # http → ws://
   # https → wss://
   ```

2. **Check nginx proxy configuration** (self-hosted):
   ```nginx
   location /ws {
       proxy_pass http://backend:8000;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       proxy_set_header Host $host;
   }
   ```

3. **Verify backend WebSocket is running**:
   ```bash
   # Check backend logs
   docker compose logs -f backend | grep -i websocket
   ```

4. **Test WebSocket connection**:
   ```bash
   # Using wscat (npm install -g wscat)
   wscat -c ws://localhost:8080/ws
   
   # Should show "Connected"
   # Type anything to test echo
   ```

---

### Issue: Admin Panel Access Denied

**Symptom**: Cannot log in to admin panel with configured credentials

**Cause**: Wrong `ADMIN_USERNAME` or `ADMIN_PASSWORD`

**Solutions**:

1. **Verify credentials are set**:
   ```bash
   # Check .env file
   grep ADMIN_ .env
   
   # Output should show username and password
   ```

2. **Ensure credentials are loaded**:
   ```bash
   # Check if environment variables are passed to container
   docker compose config | grep ADMIN
   ```

3. **Restart application to reload variables**:
   ```bash
   docker compose restart
   ```

4. **Reset to defaults if forgotten**:
   ```bash
   # Set to known values temporarily
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=admin
   
   # Login and change admin password in panel
   # Update .env after
   ```

5. **Check admin panel URL**:
   ```bash
   # Usually at /admin
   http://localhost:8080/admin
   
   # Or for cloud:
   https://yourdomain.com/admin
   ```

---

### Issue: License Key Validation Fails

**Symptom**: Application always shows free tier despite valid license key

**Cause**: `LICENSE_KEY` is invalid, expired, or not loaded; `INSTALLATION_MODE` is not set to `self-hosted`

**Solutions**:

1. **Verify installation mode**:
   ```bash
   # Check .env
   echo $INSTALLATION_MODE
   
   # Should output: self-hosted
   # (Cloud mode ignores license keys)
   ```

2. **Inspect JWT token format without trusting it**:
   ```python
   import jwt
    
   # Decode token to inspect payload shape only; this does not verify signature
   # and must never be used for actual license verification.
   token = "your_license_key"
   payload = jwt.decode(token, options={"verify_signature": False})
   print(payload)
   ```

3. **Check license tier**:
   ```bash
   # Look at startup logs
   docker compose logs backend | grep -i "license\|tier"
   
   # Should show: "License Tier: professional" or similar
   ```

4. **Verify environment variables are loaded**:
   ```bash
   # Check if variables made it to container
   docker compose exec backend env | grep LICENSE
   ```

5. **Request a new license key** from the vendor if the key is expired, malformed, or not issued for the expected tier.

---

### Issue: High Memory Usage During Build

**Symptom**: Docker build fails with "out of memory" error or killed container

**Cause**: Node.js build process uses too much memory

**Solutions**:

1. **Increase Docker/Podman memory** (Recommended):
   - Docker Desktop: Settings → Resources → Memory (increase to 4GB+)
   - Podman:
     ```bash
     podman machine stop
     podman machine set --memory 4096
     podman machine start
     ```

2. **Set Node.js memory limit**:
   ```dockerfile
   # In Dockerfile.self-hosted, modify line ~9:
   ENV NODE_OPTIONS="--max-old-space-size=4096"
   
   # For low-memory systems:
   ENV NODE_OPTIONS="--max-old-space-size=2048"
   ```

3. **Pre-build frontend locally**:
   ```bash
   # Build on host machine
   cd frontend
   npm install
   CI=false GENERATE_SOURCEMAP=false npm run build
   cd ..
   
   # Then build container (will use cached build)
   docker compose up --build
   ```

4. **Use multi-stage build optimization**:
   - Already in Dockerfile.self-hosted
   - Removes build dependencies from final image

---

### Issue: Cannot Access WebSocket from Different Network

**Symptom**: WebSocket works on localhost but fails when accessing from another computer/network

**Cause**: `VITE_WEBSOCKET_URL` uses localhost; needs actual hostname/IP

**Solutions**:

1. **Update WebSocket URL to use hostname/IP**:
   ```bash
   # Instead of
   VITE_WEBSOCKET_URL=ws://localhost:8080/ws
   
   # Use
   VITE_WEBSOCKET_URL=ws://your-server-hostname:8080/ws
   # or
   VITE_WEBSOCKET_URL=ws://192.168.1.100:8080/ws
   ```

2. **Use full domain for production**:
   ```bash
   VITE_WEBSOCKET_URL=wss://workflows.company.com/ws
   ```

3. **Verify firewall allows WebSocket port**:
   ```bash
   # Test connectivity from remote machine
   nc -zv your-server-hostname 8080
   
   # Or use curl
   curl -v http://your-server-hostname:8080/ws
   ```

4. **Check proxy/firewall rules**:
   - Ensure WebSocket traffic is not blocked
   - Some proxies block WebSocket by default
   - Verify nginx/Apache proxy configuration

---

## Summary Table: Quick Reference

### Required vs Optional Variables

| Context | Required Variables |
|---------|-------------------|
| **All Deployments** | `INSTALLATION_MODE`, `SECRET_KEY` (required for PAT login), `APP_URL` (preferred for self-hosted), `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` |
| **Cloud Only** | `GITHUB_WEBHOOK_SECRET`, `DATABASE_URL` |
| **Self-Hosted Optional** | `DATABASE_URL` (defaults to SQLite), `LICENSE_KEY` |
| **Optional (All)** | `GITHUB_TOKEN`, `DEBUG_MODE`, `USE_MOCK_RESPONSES` |

### Variable by Category

| Category | Variables | Self-Hosted | Cloud |
|----------|-----------|-------------|-------|
| **Core** | INSTALLATION_MODE | ✅ | ✅ |
| **URLs** | APP_URL, VITE_*, REACT_APP_* | ✅ | ✅ |
| **OAuth** | GITHUB_CLIENT_* | ✅ | ✅ |
| **Database** | DATABASE_URL, POSTGRES_* | ⚠️ | ✅ |
| **Licensing** | LICENSE_KEY | ✅ | ❌ |
| **Webhooks** | GITHUB_WEBHOOK_* | ❌ | ✅ |
| **Admin** | ADMIN_* | ✅ | ✅ |
| **Development** | DEBUG_MODE, etc | ✅ | ✅ |
| **Security** | SECRET_KEY, ENVIRONMENT, ALLOW_INSECURE_HTTP, CORS_ALLOWED_ORIGINS | ✅ | ✅ |

---

## References

- [Docker Deployment Modes](../DOCKER_DEPLOYMENT_MODES.md)
- [License Key Guide](../LICENSE_KEY_GUIDE.md)
- [Marketplace Webhooks](../MARKETPLACE_WEBHOOKS.md)
- [Main README](../README.md)
- [Installation Guide](../INSTALLATION.md)
