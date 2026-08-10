# Troubleshooting Guide

This guide covers common issues, error messages, and solutions for Actions Manager. Use this reference to quickly resolve problems during development, deployment, and operation.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Installation Issues](#installation-issues)
- [Authentication Issues](#authentication-issues)
- [Backend Issues](#backend-issues)
- [Frontend Issues](#frontend-issues)
- [Database Issues](#database-issues)
- [Docker Issues](#docker-issues)
- [GitHub API Issues](#github-api-issues)
- [Performance Issues](#performance-issues)
- [Getting Help](#getting-help)

## Quick Diagnostics

Start here for any issue:

**For Docker Self-Hosted (single container on port 8080):**

```bash
# Check service status
docker compose -f docker-compose.self-hosted.yml ps

# View logs
docker compose -f docker-compose.self-hosted.yml logs --tail=100

# Check connectivity (self-hosted runs everything on port 8080)
curl -I http://localhost:8080       # Frontend + Backend via nginx
curl -I http://localhost:8080/docs  # Backend API docs

# Check disk space
df -h

# Check memory
free -h
```

**For Cloud or Local Development (separate containers):**

```bash
# Check service status
docker ps

# View logs
docker logs actions-manager-backend --tail=100
docker logs actions-manager-frontend --tail=100

# Check connectivity
curl -I http://localhost:8000/  # Backend
curl -I http://localhost:3000   # Frontend

# Check disk space
df -h

# Check memory
free -h
```

## Installation Issues

### npm install Takes Too Long or Hangs

**Symptom:** `npm install` in frontend directory takes over 15 minutes or appears hung.

**Solution:**
```bash
# This is expected! Frontend npm install takes 12-13 minutes
# DO NOT cancel the process

# If truly stuck after 20 minutes:
cd frontend
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

**Prevention:** Wait patiently. This is normal for the first install.

### pip install Fails with SSL Errors

**Symptom:**
```
SSL: CERTIFICATE_VERIFY_FAILED
Could not fetch URL https://pypi.org/simple/
```

**Solution:**
```bash
cd backend
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt
```

**Root Cause:** Network environment with SSL interception or certificate issues.

### Docker Build Fails with Network Errors

**Symptom:** Docker build fails downloading packages.

**Solution:**
```bash
# Backend Dockerfile - add to pip install lines
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt

# Frontend Dockerfile - add to npm install
RUN npm config set strict-ssl false && npm ci
```

**Note:** Use GitHub Actions workflow for reliable builds in production.

### Install Script Fails

**Symptom:** `install.sh` exits with error.

**Diagnostic:**
```bash
# Check Docker/Podman
docker --version
podman --version

# Check docker-compose
docker compose version

# Run with debug
bash -x install.sh
```

**Common Issues:**
- Docker/Podman not installed
- User not in docker group: `sudo usermod -aG docker $USER`
- Missing dependencies: `curl`, `git`

## Authentication Issues

### OAuth Flow Fails

**Symptom:** After GitHub authorization, redirected to an error page or the callback never completes.

**Diagnostic Checks:**
1. Verify the **Authorization callback URL** in your GitHub OAuth app matches your `VITE_BACKEND_URL` + `/auth/callback` exactly (e.g. `http://localhost:8080/auth/callback`)
2. Check Client ID and Secret in your `.env.self-hosted` (self-hosted) or `backend/.env` (local dev) file
3. Verify the application is running on the expected port

**Solutions:**

**For Docker Self-Hosted:**
```bash
# The GitHub OAuth app callback MUST match VITE_BACKEND_URL + /auth/callback
# For default settings:
http://localhost:8080/auth/callback

# For a custom port (e.g. 9000):
http://localhost:9000/auth/callback

# For a production domain:
https://yourdomain.com/auth/callback
```

**For Local Development (backend/frontend running separately):**
```bash
# OAuth app callback MUST point at the backend:
http://localhost:8000/auth/callback
```

**Common Mistakes:**
- ❌ Using `127.0.0.1` instead of `localhost`
- ❌ Including trailing slash in callback URL
- ❌ Wrong port number (e.g. 3000 or 8000 for self-hosted)
- ❌ Missing `/auth/callback` path
- ❌ Changing the port in `.env.self-hosted` without updating docker-compose port mapping AND the GitHub OAuth app callback URL

### "Invalid Credentials" Error

**Solution:**
```bash
# Regenerate Client Secret in GitHub OAuth app
# Update the environment file
# For self-hosted:
nano .env.self-hosted
# For local development:
nano backend/.env

# Set the correct values
GITHUB_CLIENT_ID=new_value
GITHUB_CLIENT_SECRET=new_value

# Restart
docker compose -f docker-compose.self-hosted.yml restart
```

### Session Expires Immediately

**Symptom:** Logged out right after login.

**Diagnostic:**
```bash
# Check SECRET_KEY is set
docker exec actions-manager-backend env | grep SECRET_KEY

# Check clock sync
date
```

**Solution:**
```bash
# Generate new SECRET_KEY
openssl rand -hex 32

# Add to .env file
SECRET_KEY=generated_value

# Restart services
docker compose restart
```

## Backend Issues

### Backend Won't Start

**Symptom:** Backend container exits immediately.

**Diagnostic:**
```bash
# View full logs
docker logs actions-manager-backend

# Check environment variables
docker exec actions-manager-backend env

# Check port availability
netstat -tlnp | grep 8000
```

**Common Causes:**

1. **Missing Environment Variables**
   ```bash
   # Verify required vars are set
   GITHUB_CLIENT_ID=...
   GITHUB_CLIENT_SECRET=...
   ```

2. **Port Already in Use**
   ```bash
   # Find process using port 8000
   lsof -i :8000
   
   # Kill process or change port
   kill -9 <PID>
   ```

3. **Database Connection Error**
   ```bash
   # Check PostgreSQL is running
   docker ps | grep postgres
   
   # Check connection settings
   POSTGRES_HOST=postgres  # Use service name in docker-compose
   ```

### "Module Not Found" Errors

**Symptom:**
```
ModuleNotFoundError: No module named 'workflows'
```

**Solution:**
```bash
# For running tests outside Docker
export PYTHONPATH=./backend
PYTHONPATH=./backend python test_drift_detection.py

# For development
source venv/bin/activate
cd backend
python main.py
```

### API Returns 500 Internal Server Error

**Diagnostic:**
```bash
# Check backend logs for stack trace
docker logs actions-manager-backend --tail=50

# Check database
docker exec actions-manager-backend ls -la *.db

# Check connectivity to GitHub
docker exec actions-manager-backend curl -I https://api.github.com
```

**Solutions:**
- Review stack trace in logs
- Check GitHub token is valid
- Verify database file exists and is writable
- Check GitHub API rate limits

## Frontend Issues

### Frontend Won't Start

**Symptom:** Frontend container exits or `npm start` fails.

**Diagnostic:**
```bash
# View logs
docker logs actions-manager-frontend

# Check node_modules
docker exec actions-manager-frontend ls node_modules | wc -l

# Check port
netstat -tlnp | grep 3000
```

**Solutions:**

1. **Dependencies Not Installed**
   ```bash
   cd frontend
   rm -rf node_modules
   npm install
   ```

2. **Port Already in Use**
   ```bash
   # Change port in package.json
   PORT=3001 npm start
   ```

### Build Fails with ESLint Errors

**Symptom:**
```
Treating warnings as errors because process.env.CI = true
```

**Solution:**
```bash
# Always use CI=false for builds
cd frontend
CI=false npm run build

# Or set in Dockerfile
ENV CI=false
```

### White Screen After Loading

**Symptom:** Frontend loads but shows blank page.

**Diagnostic:**
```bash
# Check browser console for errors (F12)
# Common issues:
# - CORS errors
# - API endpoint unreachable
# - JavaScript errors
```

**Solutions:**

1. **Backend Not Running**
   ```bash
   curl http://localhost:8000/health
   # Start backend if not running
   ```

2. **CORS Configuration**
   ```bash
   # Verify FRONTEND_URL in backend .env
   VITE_FRONTEND_URL=http://localhost:3000
   ```

3. **API URL Mismatch**
   ```bash
   # Check frontend environment
   VITE_BACKEND_URL=http://localhost:8000
   ```

## Database Issues

### "Purged N orphaned row(s)" on First Startup After Upgrading

**Symptom:**
```
🔄 Purging rows orphaned while SQLite foreign keys were disabled...
   pass 1: removed 214 orphaned row(s) across 6 table(s)
✅ Purged 214 orphaned row(s):
```

**This is expected, not an error.** Earlier versions never enabled SQLite's
`foreign_keys` pragma, which is off by default, so `ON DELETE CASCADE` never
fired. Deleting a project left its memberships, secrets, pull request records,
notification history and other child rows behind as orphans referencing a
project that no longer existed.

Foreign keys are now enforced, and a one-time migration removes those leftover
rows so the database matches its own constraints. The count reflects how much
had accumulated — a large number on a long-running install is normal. The
migration is idempotent, so later startups report
`No orphaned rows found`.

PostgreSQL deployments are unaffected: PostgreSQL has always enforced these
constraints, so orphans could never accumulate there and the migration skips.

**Note:** deleting a project now also deletes that project's notification
delivery history, which previously survived. This is intentional.

### SQLite Database Locked

**Symptom:**
```
sqlite3.OperationalError: database is locked
```

**Solution:**
```bash
# Stop all connections
docker compose down

# Check for lock file
ls -la *.db-*

# Remove lock files (backup first!)
mv actions-manager.db actions-manager.db.backup
cp actions-manager.db.backup actions-manager.db
rm -f actions-manager.db-*

# Restart
docker compose up -d
```

### PostgreSQL Connection Failed

**Symptom:**
```
could not connect to server: Connection refused
```

**Diagnostic:**
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Check connection from backend
docker exec actions-manager-backend psql -h postgres -U actionsmanager -d actionsmanager -c "SELECT 1"

# Check environment variables
docker exec actions-manager-backend env | grep POSTGRES
```

**Solutions:**

1. **Wrong Host Name**
   ```bash
   # In docker-compose, use service name
   POSTGRES_HOST=postgres  # NOT localhost
   ```

2. **Wrong Credentials**
   ```bash
   # Verify credentials match docker-compose.yml
   POSTGRES_USER=actionsmanager
   POSTGRES_PASSWORD=your_password
   ```

3. **Database Doesn't Exist**
   ```bash
   # Create database
   docker exec postgres psql -U actionsmanager -c "CREATE DATABASE actionsmanager"
   ```

### Database Migration Failed

**Solution:**
```bash
# Run migrations manually
docker exec -it actions-manager-backend bash
cd /app
python migrate_add_marketplace_webhooks.py
python migrate_add_webhook_security.py
```

## Docker Issues

### "No Space Left on Device"

**Diagnostic:**
```bash
docker system df
df -h
```

**Solution:**
```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove unused containers
docker container prune

# Full cleanup (careful!)
docker system prune -a --volumes
```

### Container Keeps Restarting

**Diagnostic:**
```bash
# Check restart count
docker ps -a

# View logs
docker logs actions-manager-backend --tail=100

# Check exit code
docker inspect actions-manager-backend | grep ExitCode
```

**Common Causes:**
- Application crash on startup
- Missing environment variables
- Port conflicts
- Out of memory

### Cannot Connect to Docker Daemon

**Symptom:**
```
Cannot connect to the Docker daemon. Is the docker daemon running?
```

**Solution:**
```bash
# Start Docker service
sudo systemctl start docker

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Check Docker is running
docker ps
```

## GitHub API Issues

### Rate Limit Exceeded

**Symptom:**
```
API rate limit exceeded
```

**Diagnostic:**
```bash
# Check rate limit status
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/rate_limit
```

**Solutions:**
- Wait for rate limit reset (shown in API response)
- Use authenticated requests (higher limits)
- Implement caching
- Upgrade to Enterprise tier (higher limits)

### Insufficient Permissions

**Symptom:**
```
Resource not accessible by integration
```

**Solution:**
1. Re-authorize GitHub OAuth with correct scopes
2. Check repository access permissions
3. Verify OAuth app has necessary permissions

### Workflow Deployment Failed

**Symptom:** Workflow created in Actions Manager but not visible on GitHub.

**Diagnostic:**
```bash
# Check API response in backend logs
docker logs actions-manager-backend | grep "workflow"

# Manually test GitHub API
curl -H "Authorization: token YOUR_TOKEN" \
  https://api.github.com/repos/OWNER/REPO/contents/.github/workflows/test.yml
```

**Solutions:**
- Verify GitHub token has `workflow` scope
- Check repository permissions
- Verify workflow YAML is valid
- Check if branch protection prevents workflow changes

## Performance Issues

### Slow Response Times

**Diagnostic:**
```bash
# Check resource usage
docker stats

# Check database performance
# For SQLite
sqlite3 actions-manager.db "ANALYZE; VACUUM;"

# For PostgreSQL
docker exec postgres psql -U actionsmanager -d actionsmanager -c "VACUUM ANALYZE"
```

**Solutions:**
- Increase container resources
- Optimize database queries
- Enable caching
- Use PostgreSQL instead of SQLite
- Add database indexes

### High Memory Usage

**Diagnostic:**
```bash
# Check container memory
docker stats --no-stream

# Check system memory
free -h
```

**Solutions:**
```bash
# Limit container memory in docker-compose.yml
services:
  backend:
    mem_limit: 1g
    mem_reservation: 512m

# Restart services
docker compose restart
```

### Frontend Slow to Load

**Solutions:**
- Build with production optimizations
- Enable gzip compression
- Use CDN for static assets
- Minimize bundle size
- Lazy load components

## Getting Help

### Before Asking for Help

1. **Check logs:**
   ```bash
   docker logs actions-manager-backend --tail=100
   docker logs actions-manager-frontend --tail=100
   ```

2. **Search existing issues:**
   - [GitHub Issues](https://github.com/dawg-io/actions-manager/issues)

3. **Try basic diagnostics:**
   - Restart services: `docker compose restart`
   - Check connectivity: `curl http://localhost:8000/health`
   - Verify configuration: `docker exec actions-manager-backend env`

### Creating a Bug Report

Include:
- **Description:** What went wrong?
- **Steps to reproduce:** How to trigger the issue?
- **Expected behavior:** What should happen?
- **Actual behavior:** What actually happens?
- **Environment:**
  - OS and version
  - Docker version
  - Deployment mode (self-hosted/cloud)
- **Logs:** Relevant log excerpts
- **Screenshots:** If applicable

### Where to Get Help

- **GitHub Issues:** Bug reports and feature requests
- **GitHub Discussions:** Questions and community support
- **Documentation:** [docs/README.md](README.md)

## Related Documentation

- **[Development Guide](DEVELOPMENT.md)** - Local development setup
- **[Deployment Guide](DEPLOYMENT.md)** - Production deployment
- **[Architecture](ARCHITECTURE.md)** - System architecture
- **[Environment Variables](ENVIRONMENT_VARIABLES.md)** - Configuration reference

---

**Last Updated:** 2026-02-14  
**Version:** 1.0
