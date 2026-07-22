# Deployment Guide Index

This index helps you navigate between TektonHub's deployment documentation.

## Deployment Documentation Structure

```
├── DOCKER_DEPLOYMENT_MODES.md
│   └── Compares Self-Hosted vs Cloud deployments
│   └── Architecture diagrams for both modes
│   └── Quick comparison table
│
├── CLOUD_DEPLOYMENT.md (NEW - 2,174 lines)
│   ├── Complete cloud deployment guide
│   ├── 16 major sections covering all aspects
│   ├── GitHub Marketplace integration guide
│   ├── Security, scaling, monitoring, troubleshooting
│   └── Production best practices & migration guide
│
├── README.md
│   └── Main project documentation
│   └── Quick start for both modes
│   └── Development setup for contributors
│
├── MARKETPLACE_WEBHOOKS.md
│   └── In-depth webhook implementation details
│   └── Event schema and payload documentation
│   └── Testing procedures and debugging
│
├── MARKETPLACE_TIER_INTEGRATION.md
│   └── Tier system integration with marketplace
│   └── Admin override management
│   └── Free trial and pending change handling
│
└── SECURITY.md
    └── General security practices
    └── Vulnerability reporting
```

## Quick Navigation

### For Cloud Deployment
1. Start with [DOCKER_DEPLOYMENT_MODES.md](../DOCKER_DEPLOYMENT_MODES.md#cloud-deployment) - Overview of cloud architecture
2. Read [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md) - Complete deployment guide
3. Reference [MARKETPLACE_WEBHOOKS.md](../MARKETPLACE_WEBHOOKS.md) - Webhook integration details
4. Check [MARKETPLACE_TIER_INTEGRATION.md](../MARKETPLACE_TIER_INTEGRATION.md) - Subscription management

### For Self-Hosted Deployment
1. Start with [DOCKER_DEPLOYMENT_MODES.md](../DOCKER_DEPLOYMENT_MODES.md#self-hosted-deployment) - Overview
2. Read [README.md](../README.md#docker-deployment) - Installation instructions
3. Check [SELF_HOSTED_INSTALL.md](./SELF_HOSTED_INSTALL.md) - Detailed setup guide

### For Development
1. Read [README.md](../README.md#development-setup-for-contributors) - Development setup
2. Check relevant feature documentation

## CLOUD_DEPLOYMENT.md Overview

A comprehensive 2,174-line guide covering:

| Section | Purpose | Pages |
|---------|---------|-------|
| Overview | Key features and when to use | 2 |
| Architecture | Diagrams and system design | 5 |
| Prerequisites | System, software, and GitHub requirements | 3 |
| Quick Start | 7-step deployment (30 min) | 2 |
| Installation | Step-by-step with Docker Compose | 8 |
| Marketplace Setup | 6-step GitHub integration | 4 |
| Post-Installation | Reverse proxy, SSL/TLS, backups, admin panel | 5 |
| Subscription Management | Webhook flow, tier limits, free trials, overrides | 6 |
| Environment Variables | 25+ variables explained | 4 |
| Database Setup | PostgreSQL installation and configuration | 6 |
| Security | Webhooks, HTTPS/TLS, secrets, API security | 8 |
| Scaling & Performance | Horizontal scaling, caching, CDN, monitoring | 8 |
| Monitoring & Logging | Health checks, logging, Prometheus/Grafana | 5 |
| Troubleshooting | 15+ common issues with solutions | 12 |
| Production Best Practices | Deployment strategies, HA, backups, DR | 6 |
| Migration | Self-hosted to cloud migration guide | 5 |

## Key Concepts

### Cloud vs Self-Hosted

**Cloud Deployment** (Multi-tenant with Marketplace):
- 2 separate containers (frontend + backend)
- PostgreSQL database required
- GitHub Marketplace webhook integration
- Horizontal scaling support
- Future HA/production hardening requires separate review

**Self-Hosted** (Single-tenant with licenses):
- 1 combined container
- SQLite default (PostgreSQL optional)
- License key-based tiers
- Simple single-container setup
- Great for small teams

### Webhook Integration

Marketplace webhooks automatically:
1. Update user account tiers
2. Track free trials
3. Handle plan changes
4. Manage cancellations
5. Support pending changes

All with complete audit trail and security verification.

### Security Layers

1. **Signature Verification** - HMAC SHA-256
2. **IP Verification** - GitHub IP ranges (optional)
3. **Rate Limiting** - Per-IP protection
4. **HTTPS/TLS** - All traffic encrypted
5. **Secrets Management** - Environment variables, vaults

## Common Tasks

### I want to deploy TektonHub as a SaaS
→ Read [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md) sections 1-6

### I need to troubleshoot webhook issues
→ Read [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md#troubleshooting) → Webhook Issues

### I want to scale TektonHub
→ Read [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md#scaling--performance)

### I need production best practices
→ Read [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md#production-best-practices)

### I want to migrate from self-hosted
→ Read [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md#migration-guide)

### I need to understand marketplace integration
→ Read [MARKETPLACE_WEBHOOKS.md](../MARKETPLACE_WEBHOOKS.md)

### I want to set up monitoring
→ Read [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md#monitoring--logging)

### I need to secure my deployment
→ Read [CLOUD_DEPLOYMENT.md](./CLOUD_DEPLOYMENT.md#security-configuration)

## Environment Configuration

### Cloud Deployment (.env.cloud)

**Required Variables:**
```bash
INSTALLATION_MODE=cloud
VITE_BACKEND_URL=https://api.yourdomain.com
VITE_FRONTEND_URL=https://yourdomain.com
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
GITHUB_WEBHOOK_SECRET=your_webhook_secret
DATABASE_URL=postgresql://user:password@db:5432/actions_manager
```

**See:** [CLOUD_DEPLOYMENT.md - Environment Variables](./CLOUD_DEPLOYMENT.md#environment-variables)

### Self-Hosted Deployment (.env.self-hosted)

**Required Variables:**
```bash
INSTALLATION_MODE=self-hosted
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
```

**See:** [README.md - Docker Deployment](../README.md#docker-deployment)

## Architecture Diagrams

### Cloud Architecture
```
Load Balancer → Frontend (3000) ↔ Backend (8000) ↔ PostgreSQL
                                      ↕
                            GitHub Marketplace API
```

**See:** [CLOUD_DEPLOYMENT.md - Architecture](./CLOUD_DEPLOYMENT.md#architecture)

### Webhook Flow
```
GitHub Marketplace → Webhook Validation → Event Storage → Background Processing → Tier Update
```

**See:** [CLOUD_DEPLOYMENT.md - Subscription Management](./CLOUD_DEPLOYMENT.md#subscription-management)

## Related Resources

### Official Documentation
- [GitHub Marketplace API](https://docs.github.com/en/apps/github-marketplace)
- [Docker Documentation](https://docs.docker.com/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

### TektonHub Documentation
- [README.md](../README.md) - Main project docs
- [DATABASE_SCHEMA.md](../DATABASE_SCHEMA.md) - Database structure
- [SECURITY.md](../SECURITY.md) - Security practices
- [CI_CD_PIPELINE.md](../CI_CD_PIPELINE.md) - Pipeline documentation

## Version History

- **v1.0** (2025-11-04) - Initial comprehensive cloud deployment guide

## Support

For issues or questions:
1. Check the troubleshooting section of relevant guide
2. Review GitHub Issues
3. Consult the support resources in [README.md](../README.md#getting-help)

---

**Last Updated**: 2025-11-04
**Maintained By**: TektonHub Team
