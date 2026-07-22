---
layout: default
title: Container Startup
parent: Troubleshooting
nav_order: 3
---

# Container Startup
{: .no_toc }

Diagnosing and resolving container startup issues for ActionsManager Self-Hosted.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Quick Diagnostics

Run these commands first for any startup issue:

```bash
# Check if the container is running
docker ps --filter name=actions-manager

# View recent logs
docker logs actions-manager --tail=100

# Check port availability
curl -I http://localhost:8080
```

For Docker Compose:

```bash
docker compose -f docker-compose.self-hosted.yml ps
docker compose -f docker-compose.self-hosted.yml logs --tail=100
```

## Container Fails to Start

### Port 8080 Already in Use

**Symptom:** Container exits immediately or port binding fails.

**Solution:**
```bash
# Find what is using port 8080
lsof -i :8080
# or
ss -tlnp | grep 8080

# Stop the conflicting service, or run ActionsManager on a different port:
docker run -p 9090:8080 ...  # map host port 9090 to container port 8080
```

---

### Missing or Invalid SECRET_KEY

**Symptom:** Container starts but immediately fails with a configuration error.

**Solution:** Ensure `SECRET_KEY` is set when running the container. Generate a stable value once and reuse it on every restart:

```bash
# Generate once and store it (do not regenerate on every run)
openssl rand -hex 32
```

Then pass it as an environment variable:

```bash
-e SECRET_KEY=<your_generated_key>
```

**Warning:** Changing `SECRET_KEY` on a running deployment will invalidate all existing sessions and saved tokens.

---

### Volume Mount Permission Error

**Symptom:** Container fails with a permissions error when writing to the data volume.

**Solution:**
```bash
# Check the volume
docker volume inspect actions-manager-data

# Remove and recreate the volume (this deletes all data)
docker volume rm actions-manager-data
docker volume create actions-manager-data
```

---

## Container Starts but UI is Inaccessible

### Checking Service Health

```bash
# Check backend API health - proxies to the backend's own health route,
# so it fails if uvicorn is down even though nginx is still up
curl http://localhost:8080/healthz

# Check frontend static files are served - nginx serves these directly and
# will return 200 even if the backend is down, so this alone does not
# confirm the app is actually working
curl -I http://localhost:8080
```

If the backend health check fails, review logs for startup errors:

```bash
docker logs actions-manager --tail=200
```

---

### Database Initialization Errors

**Symptom:** Logs show database migration or initialization errors.

**Solution:**
1. Check if the data volume is mounted correctly
2. Check disk space: `df -h`
3. If the database is corrupted, back up the volume and reinitialize:

```bash
# Stop the container
docker stop actions-manager

# Inspect the volume path
docker volume inspect actions-manager-data

# Restart — the application will attempt to reinitialize the database
docker start actions-manager
```

---

## Environment Variable Issues

### Required Environment Variables

Ensure these are set before starting the container:

| Variable | Required | Description |
|----------|----------|-------------|
| `INSTALLATION_MODE` | Yes | Set to `self-hosted` |
| `SECRET_KEY` | Yes | Random secret for session encryption |
| `VITE_BACKEND_URL` | Yes | URL where the backend is accessible |
| `VITE_FRONTEND_URL` | Yes | URL where the frontend is accessible |
| `VITE_WEBSOCKET_URL` | Yes | WebSocket URL (`ws://` prefix) |
| `GITHUB_CLIENT_ID` | OAuth only | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | OAuth only | GitHub OAuth App client secret |

### Checking Environment Variables in a Running Container

```bash
docker exec actions-manager env | grep -E 'INSTALLATION_MODE|VITE_|GITHUB_CLIENT'
```

---

## Memory and Disk Issues

```bash
# Check memory
free -h

# Check disk space
df -h

# Check container resource usage
docker stats actions-manager
```

ActionsManager requires at least 4 GB RAM. If the container is OOM-killed, increase available memory or add a swap file.

---

## Getting More Help

If you cannot resolve the issue:
1. Collect logs: `docker logs actions-manager > actions-manager.log 2>&1`
2. Review the [Common Errors]({% link troubleshooting/common-errors.md %}) page
3. Check [GitHub Issues](https://github.com/dawg-io/actions-manager/issues) for similar reports
4. Open a new issue with your logs (redact all secrets and tokens before posting)

## Related Topics

- [Common Errors]({% link troubleshooting/common-errors.md %}) — authentication, API, and workflow errors
- [GitHub Permissions]({% link troubleshooting/github-permissions.md %}) — permission requirements
- [Installation]({% link getting-started/installation.md %}) — installation guide
