# Actions Manager Documentation

> **Editing these docs:** `docs/` in the public repository
> ([dawg-io/actions-manager](https://github.com/dawg-io/actions-manager)) is generated
> by the release promotion and the docs publish, and is replaced wholesale by each — a commit made
> directly against the public copy is overwritten by the next one. A pull request there
> is still the right way to propose a documentation change: a maintainer ports it into
> the development repository, and it ships back out with the following release or docs publish.

## The documentation site

actionsmanager.io is an [Astro Starlight](https://starlight.astro.build/) site
built from this directory. Its pages are `src/content/docs/**` (Markdown/MDX);
the files at the top of `docs/`, `guides/`, `features/` and `archive/` are repository
documentation and are not published.

```bash
cd docs
npm ci
npm run dev     # local preview at http://localhost:4321
npm run build   # static output in dist/
```

Node version: see `.nvmrc`.

- `build.format: 'file'` emits `/path.html`. `url-parity.txt` lists every URL the
  site has ever published; CI fails if one stops resolving - add a redirect in
  `astro.config.mjs` before renaming or removing a page.
- There is no `CNAME`. The domain is set in the public repository's Pages settings;
  CI fails if `dist/CNAME` ever appears.
- Screenshots live in `src/content/docs/assets/screenshots/`, where
  `docs-media-refresh.yml` writes them.

### Theme

`src/styles/theme.css` (registered in `customCss`) holds the brand theme. It only
sets Starlight's CSS custom properties plus a few layout rules, so Starlight's
light/dark toggle switches it. Change colors there, never on individual components.

- Light mode: warm ground `#F6F5F1`, white surfaces, ink `#15171C`, body text
  `#4D515B`, rust accent `#B0482A`.
- Dark mode: the ActionsManager app's dark theme (Tailwind slate: page `#0f172a`,
  surfaces `#1e293b`, borders `#475569`), with the accent `#E8A184`.
- Fonts: Space Grotesk (headings), IBM Plex Sans (body), JetBrains Mono (code),
  self-hosted from `src/fonts/` (Latin subsets from Fontsource, SIL OFL 1.1, licenses
  alongside). Never add a Google Fonts link; CI fails if the build references one or
  drops a font file. Adding a weight means adding its file, an `@font-face`, and
  bumping the woff2 count in `.github/workflows/docs-preview.yml`.
- `src/components/` overrides three Starlight components: the header lockup
  (`SiteTitle`), the footer's copyright line (`Footer`) and the home page's hidden
  title (`PageTitle`).

Welcome to the Actions Manager documentation! This guide will help you find the information you need to use, deploy, and contribute to Actions Manager.

## 📚 Documentation Index

### Getting Started

- **[Quick Start Guide](QUICK_START.md)** - Get up and running in 5-15 minutes
- **[Installation](SELF_HOSTED_INSTALL.md)** - Self-hosted deployment guide
- **[Cloud Deployment](../internal-docs/CLOUD_DEPLOYMENT.md)** - Multi-tenant SaaS setup

### For Users

- **[GitHub PAT Setup](GITHUB_PAT_SETUP.md)** - Fine-grained and classic PAT setup, permissions, and troubleshooting
- **[Environment Variables](ENVIRONMENT_VARIABLES.md)** - Configuration reference
- **[License Keys](../internal-docs/LICENSE_KEYS.md)** - License key management (self-hosted)
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
- **[Public HTTPS via Cloudflare Tunnel](guides/STAGING_TUNNEL.md)** - Put your self-hosted install behind a public HTTPS hostname, no open ports
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
├── astro.config.mjs            # Documentation site config (Starlight)
├── src/content/docs/           # Published pages (actionsmanager.io)
├── url-parity.txt              # Every published URL, checked in CI
├── QUICK_START.md              # Getting started guide
├── DEVELOPMENT.md              # Development workflows
├── ARCHITECTURE.md             # System architecture
├── DEPLOYMENT.md               # Deployment and CI/CD
├── TROUBLESHOOTING.md          # Common issues
├── FRONTEND_DEVELOPMENT.md     # Frontend guide
├── SELF_HOSTED_INSTALL.md     # Self-hosted installation
├── ENVIRONMENT_VARIABLES.md   # Configuration reference
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
2. [Self-Hosted Install](SELF_HOSTED_INSTALL.md) or [Cloud Deployment](../internal-docs/CLOUD_DEPLOYMENT.md)
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
