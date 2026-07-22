# Actions Manager Documentation

Welcome to the Actions Manager documentation! This guide will help you find the information you need to use, deploy, and contribute to Actions Manager.

## 📚 Documentation Index

### Getting Started

- **[Quick Start Guide](QUICK_START.md)** - Get up and running in 5-15 minutes
- **[Installation](SELF_HOSTED_INSTALL.md)** - Self-hosted deployment guide
- **[Cloud Deployment](CLOUD_DEPLOYMENT.md)** - Multi-tenant SaaS setup

### For Users

- **[GitHub PAT Setup](GITHUB_PAT_SETUP.md)** - Fine-grained and classic PAT setup, permissions, and troubleshooting
- **[Environment Variables](ENVIRONMENT_VARIABLES.md)** - Configuration reference
- **[License Keys](LICENSE_KEYS.md)** - License key management (self-hosted)
- **[Licensing Model](../LICENSING_MODEL.md)** - Open-source, commercial, EULA, SaaS terms, and privacy overview
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common issues and solutions
- **[Workflow Delivery Modes](guides/WORKFLOW_DELIVERY_MODES.md)** - Direct commit vs PR-based delivery
- **[Migration Guide](guides/MIGRATION_DIRECT_TO_PR.md)** - Moving from direct to PR-based workflow

### For Developers

- **[Development Guide](DEVELOPMENT.md)** - Local setup, workflows, testing
- **[Frontend Development](FRONTEND_DEVELOPMENT.md)** - React, TypeScript, styling
- **[Architecture](ARCHITECTURE.md)** - System design and components
- **[Contributing](../CONTRIBUTING.md)** - Contribution guidelines

### Advanced Topics

- **[Deployment Guide](DEPLOYMENT.md)** - CI/CD, Docker, production setup
- **[Staging via Cloudflare Tunnel](guides/STAGING_TUNNEL.md)** - Public HTTPS staging URL for per-commit cloud-deployment testing
- **[Database Schema](../DATABASE_SCHEMA.md)** - Database structure
- **[Security Policy](../SECURITY.md)** - Security practices and reporting
- **[PR-Based Delivery](features/PR_BASED_DELIVERY.md)** - Technical implementation details

## 🚀 Quick Links

### I want to...

- **Install Actions Manager** → [Quick Start](QUICK_START.md) or [Self-Hosted Install](SELF_HOSTED_INSTALL.md)
- **Configure GitHub PAT login** → [GitHub PAT Setup](GITHUB_PAT_SETUP.md)
- **Deploy to production** → [Deployment Guide](DEPLOYMENT.md)
- **Set up development environment** → [Development Guide](DEVELOPMENT.md)
- **Configure environment variables** → [Environment Variables](ENVIRONMENT_VARIABLES.md)
- **Fix an issue** → [Troubleshooting](TROUBLESHOOTING.md)
- **Contribute code** → [Contributing Guide](../CONTRIBUTING.md)
- **Report a security issue** → [Security Policy](../SECURITY.md)
- **Understand the architecture** → [Architecture](ARCHITECTURE.md)
- **Choose workflow delivery mode** → [Workflow Delivery Modes](guides/WORKFLOW_DELIVERY_MODES.md)
- **Migrate to PR-based delivery** → [Migration Guide](guides/MIGRATION_DIRECT_TO_PR.md)

## 📖 Documentation Structure

```
docs/
├── README.md                    # This file - documentation index
├── QUICK_START.md              # Getting started guide
├── DEVELOPMENT.md              # Development workflows
├── ARCHITECTURE.md             # System architecture
├── DEPLOYMENT.md               # Deployment and CI/CD
├── TROUBLESHOOTING.md          # Common issues
├── FRONTEND_DEVELOPMENT.md     # Frontend guide
├── SELF_HOSTED_INSTALL.md     # Self-hosted installation
├── CLOUD_DEPLOYMENT.md        # Cloud/SaaS deployment
├── ENVIRONMENT_VARIABLES.md   # Configuration reference
├── LICENSE_KEYS.md            # License management
├── guides/
│   ├── WORKFLOW_DELIVERY_MODES.md  # Direct commit vs PR-based delivery
│   └── MIGRATION_DIRECT_TO_PR.md   # Migration guide
└── features/
    └── PR_BASED_DELIVERY.md        # PR-based delivery technical docs
```

## 🔍 Finding Information

### By Topic

- **Installation & Setup**: [Quick Start](QUICK_START.md), [Self-Hosted Install](SELF_HOSTED_INSTALL.md)
- **Configuration**: [Environment Variables](ENVIRONMENT_VARIABLES.md)
- **Development**: [Development Guide](DEVELOPMENT.md), [Frontend Development](FRONTEND_DEVELOPMENT.md)
- **Architecture & Design**: [Architecture](ARCHITECTURE.md), [Database Schema](../DATABASE_SCHEMA.md)
- **Operations**: [Deployment](DEPLOYMENT.md), [Troubleshooting](TROUBLESHOOTING.md)
- **Contributing**: [Contributing Guide](../CONTRIBUTING.md)

### By Role

**End Users:**
1. [Quick Start](QUICK_START.md)
2. [Self-Hosted Install](SELF_HOSTED_INSTALL.md) or [Cloud Deployment](CLOUD_DEPLOYMENT.md)
3. [Environment Variables](ENVIRONMENT_VARIABLES.md)
4. [Troubleshooting](TROUBLESHOOTING.md)

**Developers:**
1. [Development Guide](DEVELOPMENT.md)
2. [Architecture](ARCHITECTURE.md)
3. [Frontend Development](FRONTEND_DEVELOPMENT.md)
4. [Contributing Guide](../CONTRIBUTING.md)

**DevOps/SRE:**
1. [Deployment Guide](DEPLOYMENT.md)
2. [Environment Variables](ENVIRONMENT_VARIABLES.md)
3. [Troubleshooting](TROUBLESHOOTING.md)
4. [Security Policy](../SECURITY.md)

## 📝 Documentation Guidelines

When updating documentation, please follow the [Contributing Guidelines](../CONTRIBUTING.md#documentation-policy).

**Key principles:**
- Update existing docs rather than creating new files
- Keep information consolidated and discoverable
- Use clear, concise language
- Include examples where helpful
- Link to related documentation

## 🆘 Need Help?

- **Found an error?** Open an issue or submit a PR
- **Have a question?** Check [Troubleshooting](TROUBLESHOOTING.md) or open an issue
- **Want to contribute?** See [Contributing Guide](../CONTRIBUTING.md)

---

**Last Updated:** 2026-02-14  
**Version:** 1.0
