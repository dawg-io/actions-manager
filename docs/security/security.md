---
layout: default
title: Security Policy
parent: Security
nav_order: 1
---

# Security Policy
{: .no_toc }

Security information and hardening guidance for ActionsManager Self-Hosted Beta.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

> **Beta notice:** ActionsManager Self-Hosted is currently a free beta preview provided as-is, without warranty, SLA, support guarantee, uptime guarantee, production-readiness guarantee, or formal compliance certification. The beta may interact with GitHub repositories, workflow files, pull requests, secrets metadata, tokens, OAuth credentials, environment variables, and local databases.

## Reporting a Vulnerability

**Do not open a public GitHub issue for suspected vulnerabilities.** Report security issues privately by using [GitHub private vulnerability reporting](https://github.com/dawg-io/actions-manager/security/advisories/new) if enabled, or the maintainer contact channel listed on the repository profile.

When reporting, please include:
- Affected version, commit, image tag, or deployment mode
- A clear description of the vulnerability and affected component
- Reproduction steps or proof-of-concept details
- Expected and actual impact
- Relevant logs or screenshots with all secrets redacted
- Suggested fix or mitigation, if known

Please follow responsible disclosure: allow maintainers a reasonable opportunity to investigate and fix before public disclosure.

## Supported Versions

Security fixes are prioritized for the active beta branch and current published self-hosted beta image. Older pre-1.0 snapshots may not receive backported fixes. No formal SLA or response-time guarantee is provided during beta.

## Built-In Application Protections

These are enabled by default and don't require operator configuration:

- **Security response headers** on every API response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(), camera=(), microphone=()`, and `Strict-Transport-Security` (HSTS) when the request is served over HTTPS
- Saved PATs and OAuth tokens are encrypted at rest and never returned to the UI in raw form
- Session tokens are opaque and stored server-side only as a hash, not as a decodable JWT
- CORS is restricted to configured origins; credentialed requests are rejected if the resolved origin list falls back to a wildcard

## Self-Hosted Hardening

Operators are responsible for securing their own deployment. At minimum:

### Credential Protection
- Keep `.env.self-hosted` and all real `.env` files private — never commit them
- Protect GitHub OAuth client secrets, PATs, webhook secrets, and database files
- Rotate credentials immediately if they may have been exposed in logs, shell history, screenshots, issues, or commits

### Network Security
- Use HTTPS behind a reverse proxy if exposing ActionsManager beyond localhost
- Restrict access to port 8080 to trusted networks when not behind a proxy
- Do not expose the container directly to the public internet without TLS

### Operational Security
- Review all generated or edited workflow changes before merging or applying them
- Prefer **PR-based delivery** for beta testing — direct commits cannot be reviewed before taking effect
- Keep the container image updated and pin image tags for controlled upgrades
- Back up the SQLite volume or PostgreSQL database before upgrades
- Disable debug, mock, and stub settings for any shared or exposed deployment

### Access Control
- Prefer fine-grained GitHub PATs or OAuth with least-privilege repository access
- Do not grant ActionsManager access to repositories it does not need to manage
- Do not use placeholder credentials such as `admin/admin` in production deployments

## No Formal Compliance Claim

This repository may use security tools and secure-development practices, but the beta does not claim SOC 2, ISO 27001, HIPAA, FedRAMP, PCI, or other formal compliance certification.

## Related Topics

- [Privacy]({% link security/privacy.md %}) — data handling and privacy information
- [Token Handling]({% link security/token-handling.md %}) — GitHub token security practices
- [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %}) — creating tokens with least privilege
