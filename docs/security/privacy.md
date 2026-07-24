---
layout: default
title: Privacy
parent: Security
nav_order: 2
---

# Privacy Notice
{: .no_toc }

How ActionsManager Self-Hosted Beta handles your data.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

> **Note:** This notice describes the current self-hosted beta behavior. It is product documentation, not legal advice. Privacy terms for any future Cloud/SaaS or paid offering will be reviewed and published separately before launch.

## Where Data is Stored

The self-hosted beta runs on infrastructure controlled by the operator. ActionsManager stores application data in the user-configured database for that deployment:

- **Default:** SQLite stored in the mounted application data volume
- **Optional:** PostgreSQL, where configured by the operator

The operator controls where this infrastructure runs and who has access to it.

## What the Application May Store

Depending on how the application is used, stored data may include:

- GitHub account identifiers, usernames, avatar URLs, and related profile metadata
- Repository names, organization or owner names, project configuration, workflow YAML, workflow state, and configuration metadata
- Pull request metadata, branch names, workflow rollout state, drift-detection state, and audit or webhook metadata needed by enabled features
- License tier metadata derived from a configured self-hosted `LICENSE_KEY`, when present

## Secrets and Credentials

Repository secret **values** are not stored locally by ActionsManager. Secret names or metadata may be tracked where needed to support repository and environment secret management.

Operators must protect:
- GitHub OAuth client secrets
- Saved personal access tokens
- Local environment variables and `.env.self-hosted` files
- Database files and backups
- Webhook secrets, license keys, and any optional external API keys

**Never commit a real `.env` file or token to source control.**

## Telemetry and External Calls

The self-hosted beta does **not** include documented product telemetry, crash reporting, or phone-home analytics.

The application does call external services that the operator configures or explicitly uses:
- **GitHub APIs** for authentication and repository/workflow operations

## Backups and Deletion

Self-hosted operators control database backups, retention, access, and deletion. Review backups before sharing logs or support bundles, as they may contain repository metadata, workflow YAML, pull request metadata, credentials metadata, and other configuration details.

## Related Topics

- [Security Policy]({% link security/security.md %}) — hardening guidance and vulnerability reporting
- [Token Handling]({% link security/token-handling.md %}) — GitHub token security
