---
layout: default
title: Beta Notes
parent: Beta
nav_order: 1
---

# Beta Notes
{: .no_toc }

What the beta is, what it is not, and what to expect.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What is the Beta?

ActionsManager Self-Hosted is currently available as a **free beta preview** for testing, evaluation, and feedback.

This beta is **self-hosted only**. It is not:
- The hosted Cloud/SaaS service
- A GitHub Marketplace release
- A paid product

No paid plans are currently available.

## What Beta Means

- The beta is intended for testing, evaluation, and feedback
- It is **free during the beta period**
- Features, limits, licensing behavior, packaging, and commercial availability **may change** before general availability
- Paid plans or commercial licensing may be introduced in the future
- Free beta access does **not** grant permanent free access to future paid features or commercial offerings

## No Production Guarantee

The beta is provided **as-is**, without:
- Warranty
- SLA or uptime guarantee
- Support guarantee
- Production-readiness guarantee
- Enterprise/compliance/security certification

Do not rely on the beta as a guaranteed production service.

## What's Included in the Beta

- Single-container self-hosted deployment
- GitHub PAT and OAuth authentication
- Multi-repository project management
- Workflow management with PR-based and direct-commit delivery
- Drift detection and resolution
- Secrets and variables management
- Real-time WebSocket updates
- Reusable workflow producer/consumer management
- Build type detection and workflow templates

## Current Limitations

- **Self-hosted only** — no hosted/cloud version available in beta
- **Single instance** — no horizontal scaling or high-availability configuration
- **SQLite default** — PostgreSQL is supported but not the default
- **No formal SLA** — no uptime or response time guarantees
- **Beta API** — API shape may change between releases

## Operator Responsibilities

Self-hosted operators are responsible for:
- Securing their deployment and network access
- Using HTTPS when exposing the service beyond localhost
- Protecting GitHub OAuth credentials, personal access tokens, webhook secrets, environment files, database files, and backups
- Configuring GitHub access with least-privilege permissions
- Reviewing workflow changes before applying, merging, or directly committing them
- Choosing target repositories and branches carefully
- Backing up application data before upgrades or configuration changes
- Rotating credentials if they may have been exposed

## Providing Feedback

Feedback is welcome during the beta. You can:
- [Open an issue](https://github.com/dawg-io/actions-manager/issues) to report bugs or request features
- [Start a discussion](https://github.com/dawg-io/actions-manager/discussions) for questions and general feedback

When reporting issues, please include:
- ActionsManager version or image tag
- Deployment method (Docker run, Docker Compose)
- Steps to reproduce
- Expected and actual behavior
- Relevant logs with all secrets and tokens redacted

## Upcoming

The beta roadmap is not formally published. Features, limits, and availability may change. Watch the repository for release announcements.

## Related Topics

- [Installation]({% link getting-started/installation.md %}) — getting started with self-hosted
- [Security Policy]({% link security/security.md %}) — beta security scope
- [Privacy]({% link security/privacy.md %}) — beta data handling
