# Deployment Guide

This guide covers deploying Actions Manager in production environments, including CI/CD pipeline configuration, Docker deployment, and operational best practices.

## Table of Contents

- [Deployment Modes](#deployment-modes)
- [Self-Hosted Deployment](#self-hosted-deployment)
- [Cloud Deployment](#cloud-deployment)
- [CI/CD Pipeline](#cicd-pipeline)
- [Production Checklist](#production-checklist)
- [Monitoring & Operations](#monitoring--operations)
- [Backup & Recovery](#backup--recovery)

## Deployment Modes

Actions Manager supports two deployment architectures optimized for different use cases:

| Feature | Self-Hosted | Cloud/SaaS |
|---------|-------------|------------|
| **Architecture** | Single container | Multi-container |
| **Installation** | 5 minutes | 15 minutes |
| **Licensing** | JWT license keys | GitHub Marketplace |
| **Database** | SQLite (default) or PostgreSQL | PostgreSQL (required) |
| **Best For** | Small teams, on-premise | Multi-tenant, scalable |
| **Port** | 8080 | 3000 (frontend), 8000 (backend) |

For detailed architecture comparison, see [DOCKER_DEPLOYMENT_MODES.md](../DOCKER_DEPLOYMENT_MODES.md).

## Self-Hosted Deployment

### Quick Install

The fastest way to deploy self-hosted:

```bash
curl -fsSL https://raw.githubusercontent.com/dawg-io/actions-manager/main/install.sh | bash
```

Or clone and run locally:

```bash
git clone https://github.com/dawg-io/actions-manager.git
cd actions-manager
./install.sh
```

The installer will:
- ✅ Check system requirements
- ✅ Prompt for GitHub OAuth credentials
- ✅ Configure license key (optional)
- ✅ Generate secure SECRET_KEY
- ✅ Build and start containers
- ✅ Display access information

### Manual Self-Hosted Deployment

For custom configurations:

```bash
# 1. Copy environment template
cp .env.self-hosted.example .env.self-hosted

# 2. Edit configuration
nano .env.self-hosted

# 3. Build and start
docker compose -f docker-compose.self-hosted.yml up --build -d
```

**Access:** `http://localhost:8080`

For complete self-hosted installation guide, see [SELF_HOSTED_INSTALL.md](SELF_HOSTED_INSTALL.md).

### Self-Hosted Configuration

Required environment variables in `.env.self-hosted`:

```bash
# GitHub OAuth (Required)
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# Application URLs
FRONTEND_URL=http://localhost:8080
BACKEND_URL=http://localhost:8080

# Security
SECRET_KEY=generate_with_openssl_rand_hex_32

# License (Optional - defaults to Free tier)
LICENSE_KEY=your_jwt_license_key

# Database (Optional - defaults to SQLite)
# POSTGRES_USER=actionsmanager
# POSTGRES_PASSWORD=secure_password
# POSTGRES_DB=actionsmanager
# POSTGRES_HOST=postgres
# POSTGRES_PORT=5432
```

### Self-Hosted Production Checklist

- [ ] Change default admin password
- [ ] Configure SSL/TLS certificate
- [ ] Set strong SECRET_KEY
- [ ] Update OAuth callback URL to production domain
- [ ] Configure PostgreSQL (recommended for production)
- [ ] Set up regular backups
- [ ] Configure monitoring
- [ ] Review and apply security headers
- [ ] Test disaster recovery procedure

## Cloud Deployment

### Cloud Installation

For multi-tenant SaaS deployment:

```bash
# 1. Copy cloud environment template
cp .env.cloud.example .env.cloud

# 2. Configure environment variables
nano .env.cloud

# 3. Build and start
docker compose -f docker-compose.cloud.yml up --build -d
```

**Access:**
- Frontend: Configured domain (e.g., `https://yourdomain.com`)
- Backend: Same domain with `/api/*` prefix

For complete cloud deployment guide, see [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md).

### Cloud Configuration

Required environment variables in `.env.cloud`:

```bash
# GitHub OAuth (Required)
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# Application URLs
FRONTEND_URL=https://yourdomain.com
BACKEND_URL=https://yourdomain.com

# Security
SECRET_KEY=generate_with_openssl_rand_hex_32

# GitHub Marketplace (Required for cloud)
GITHUB_WEBHOOK_SECRET=generate_with_openssl_rand_hex_32
VERIFY_WEBHOOK_IP=true
GITHUB_WEBHOOK_IPS=192.30.252.0/22,185.199.108.0/22,140.82.112.0/20,143.55.64.0/20

# PostgreSQL (Required for cloud)
POSTGRES_USER=actionsmanager
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=actionsmanager
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Installation Mode
INSTALLATION_MODE=cloud
```

### Cloud Production Checklist

- [ ] Configure production domain with SSL/TLS
- [ ] Set up GitHub Marketplace app and webhooks
- [ ] Configure PostgreSQL with backups
- [ ] Set strong GITHUB_WEBHOOK_SECRET
- [ ] Enable webhook IP verification
- [ ] Configure CDN for static assets (optional)
- [ ] Set up load balancer (if scaling)
- [ ] Configure monitoring and alerting
- [ ] Set up log aggregation
- [ ] Test marketplace webhook flow
- [ ] Document disaster recovery procedure

## CI/CD Pipeline

Actions Manager includes a comprehensive CI/CD pipeline with automated testing, security scanning, and deployment.

### Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions Workflow                  │
├─────────────────────────────────────────────────────────────┤
│  Trigger: Push to main/develop, PR, Manual                 │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Lint       │  │   Test       │  │   Build      │    │
│  │              │  │              │  │              │    │
│  │ • Black      │  │ • pytest     │  │ • Backend    │    │
│  │ • flake8     │  │ • Jest       │  │ • Frontend   │    │
│  │ • ESLint     │  │ • Coverage   │  │ • Docker     │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Security   │  │   SBOM       │  │   Deploy     │    │
│  │              │  │              │  │              │    │
│  │ • Trivy      │  │ • CycloneDX  │  │ • GHCR       │    │
│  │ • Bandit     │  │ • Supply     │  │ • Kubernetes │    │
│  │ • Gitleaks   │  │   Chain      │  │ • Flux       │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Pipeline Features

1. **Code Quality**
   - Python: Black, flake8
   - JavaScript: ESLint, Prettier
   - Dockerfile: Hadolint

2. **Testing**
   - Backend: pytest with coverage
   - Frontend: Jest with coverage
   - Integration tests

3. **Security Scanning**
   - Container: Trivy
   - Python: Bandit
   - Secrets: Gitleaks
   - Dependencies: Dependabot

4. **SBOM Generation**
   - CycloneDX format
   - Supply chain security
   - Vulnerability tracking

5. **Deployment**
   - Docker images to GHCR
   - Kubernetes via Flux
   - Automated rollback on failure

### Workflow Configuration

Located in `.github/workflows/`:

- `docker-build-and-test.yml` - Main build and deploy workflow
- `security-scan.yml` - Security scanning
- `tests.yml` - Test suite
- `lint.yml` - Code quality checks

### Running Pipeline Locally

```bash
# Backend quality checks
cd backend
black . && flake8 . && pytest

# Frontend quality checks
cd frontend
npm run lint && npm test

# Docker build test
docker compose -f docker-compose.self-hosted.yml build
```

### Pipeline Quick Reference

For detailed pipeline commands and troubleshooting, see [PIPELINE_QUICK_REFERENCE.md](../PIPELINE_QUICK_REFERENCE.md).

## Production Checklist

### Pre-Deployment

- [ ] Review architecture diagram
- [ ] Choose deployment mode (self-hosted vs cloud)
- [ ] Provision infrastructure (servers, database, etc.)
- [ ] Configure DNS records
- [ ] Obtain SSL/TLS certificates
- [ ] Create GitHub OAuth app
- [ ] Configure environment variables
- [ ] Review security settings

### Deployment

- [ ] Deploy application
- [ ] Verify backend health (`/health` endpoint)
- [ ] Verify frontend loads
- [ ] Test OAuth flow
- [ ] Test core functionality
- [ ] Configure monitoring
- [ ] Set up log aggregation
- [ ] Test backup/restore procedure

### Post-Deployment

- [ ] Monitor application metrics
- [ ] Review logs for errors
- [ ] Test from external network
- [ ] Verify SSL/TLS configuration
- [ ] Document any custom configuration
- [ ] Train team on operations
- [ ] Create runbook for common tasks

## Monitoring & Operations

### Health Checks

```bash
# Backend health
curl http://localhost:8000/health

# Frontend health
curl -I http://localhost:3000

# Docker container status
docker ps
docker logs actions-manager-backend
docker logs actions-manager-frontend
```

### Metrics to Monitor

1. **Application Metrics**
   - Request rate
   - Response time
   - Error rate
   - Active users

2. **Infrastructure Metrics**
   - CPU usage
   - Memory usage
   - Disk usage
   - Network I/O

3. **Database Metrics**
   - Connection pool usage
   - Query performance
   - Database size

4. **External Service Metrics**
   - GitHub API rate limits
   - GitHub API response times
   - OAuth success rate

### Log Management

```bash
# View container logs
docker logs -f actions-manager-backend
docker logs -f actions-manager-frontend

# Export logs
docker logs actions-manager-backend > backend.log 2>&1

# Monitor all containers
docker compose logs -f
```

### Recommended Monitoring Tools

- **Prometheus + Grafana** - Metrics and dashboards
- **ELK Stack** - Log aggregation and analysis
- **Sentry** - Error tracking
- **UptimeRobot** - Uptime monitoring

## Backup & Recovery

### Backup Strategy

#### Self-Hosted (SQLite)

```bash
# Backup database (stop app first to avoid an inconsistent copy, then copy to host)
docker compose -f docker-compose.self-hosted.yml stop app
docker cp $(docker compose -f docker-compose.self-hosted.yml ps -q app):/app/data/actions_manager.db ./actions_manager.db.backup.$(date +%Y%m%d)
docker compose -f docker-compose.self-hosted.yml start app

# Backup environment
cp .env.self-hosted .env.self-hosted.backup

# Start application
docker compose -f docker-compose.self-hosted.yml up -d
```

#### Cloud (PostgreSQL)

```bash
# Backup database
docker exec postgres pg_dump -U actionsmanager actionsmanager > backup.sql

# Or with docker compose
docker compose -f docker-compose.cloud.yml exec postgres pg_dump -U actionsmanager actionsmanager > backup.sql

# Compress backup
gzip backup.sql
```

### Restore Procedure

#### Self-Hosted (SQLite)

```bash
# Stop application
docker compose -f docker-compose.self-hosted.yml down

# Restore database (copy backup back into the named volume)
docker compose -f docker-compose.self-hosted.yml run --rm app \
  cp /app/data/actions_manager.db.backup.20260214 /app/data/actions_manager.db

# Start application
docker compose -f docker-compose.self-hosted.yml up -d
```

#### Cloud (PostgreSQL)

```bash
# Restore database
gunzip backup.sql.gz
docker compose -f docker-compose.cloud.yml exec -T postgres psql -U actionsmanager actionsmanager < backup.sql
```

### Automated Backups

**Cron job example (daily backups):**

```bash
# Self-hosted (backs up database inside the named volume)
0 2 * * * docker compose -f /path/to/actions-manager/docker-compose.self-hosted.yml exec -T app cp /app/data/actions_manager.db /app/data/actions_manager.db.$(date +\%Y\%m\%d).backup

# Cloud (PostgreSQL)
0 2 * * * cd /path/to/actions-manager && docker compose -f docker-compose.cloud.yml exec -T postgres pg_dump -U actionsmanager actionsmanager | gzip > backups/backup-$(date +\%Y\%m\%d).sql.gz
```

## Troubleshooting

For common deployment issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Quick Diagnostics

```bash
# Check container status
docker ps -a

# View container logs
docker logs actions-manager-backend
docker logs actions-manager-frontend

# Check disk space
df -h

# Check memory
free -h

# Test network connectivity
curl -I https://api.github.com

# Verify environment variables
docker exec actions-manager-backend env | grep GITHUB_CLIENT_ID
```

## Related Documentation

- **[Self-Hosted Installation](SELF_HOSTED_INSTALL.md)** - Complete self-hosted guide
- **[Cloud Deployment](CLOUD_DEPLOYMENT.md)** - Complete cloud guide
- **[Environment Variables](ENVIRONMENT_VARIABLES.md)** - Configuration reference
- **[Architecture](ARCHITECTURE.md)** - System design
- **[CI/CD Pipeline](../CI_CD_PIPELINE.md)** - Pipeline details
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common issues

---

**Last Updated:** 2026-02-14  
**Version:** 1.0
