# Security Policy

ActionsManager Self-Hosted is currently a free beta preview. The beta may interact with GitHub repositories, workflow files, pull requests, secrets metadata, tokens, OAuth credentials, environment variables, and local databases. It is provided as-is, without warranty, SLA, support guarantee, uptime guarantee, production-readiness guarantee, or formal compliance certification.

## Reporting a vulnerability privately

Please do **not** open a public GitHub issue for suspected vulnerabilities. Report security issues privately to the maintainers by email or GitHub private vulnerability reporting if enabled for the repository. If private vulnerability reporting is not available, use the maintainer contact channel listed on the repository profile and avoid posting exploit details publicly.

Include as much of the following as you can safely share:

- Affected version, commit, image tag, or deployment mode.
- A clear description of the vulnerability and affected component.
- Reproduction steps or proof-of-concept details.
- Expected and actual impact, including whether GitHub repositories, workflows, secrets, tokens, or environment variables may be affected.
- Relevant logs or screenshots with secrets redacted.
- Suggested fix or mitigation, if known.

We ask reporters to follow responsible disclosure: give maintainers a reasonable opportunity to investigate and fix before public disclosure, avoid accessing data that is not yours, and avoid disrupting other users or GitHub services.

## Supported versions during beta

Security fixes are prioritized for the active beta branch and current published self-hosted beta image. Older pre-1.0 snapshots may not receive backported fixes. No formal SLA or response-time guarantee is provided during beta.

## Self-hosted hardening recommendations

Operators are responsible for securing their own deployment. At minimum:

- Keep `.env.self-hosted` and any real `.env` files private; never commit them.
- Protect GitHub OAuth client secrets, PATs, webhook secrets, license keys, OpenAI/API keys, database files, and backups.
- Use HTTPS behind a reverse proxy if exposing ActionsManager beyond localhost.
- Use strong, unique admin credentials if you enable any admin-only functionality. Do not use placeholder credentials such as `admin/admin123`.
- Prefer fine-grained GitHub PATs or OAuth permissions with least-privilege repository access.
- Rotate credentials immediately if they may have been exposed in logs, shell history, screenshots, issues, support bundles, or commits.
- Back up the SQLite volume or PostgreSQL database before upgrades.
- Review generated or edited workflow changes before merging or applying them. PR-based delivery is safer for beta testing than direct commits.
- Keep the container image updated and pin image tags for controlled upgrades.
- Disable debug, mock, and stub settings for any shared or exposed deployment.

## No formal compliance claim

This repository may use security tools and secure-development practices, but the beta does not claim SOC 2, ISO 27001, HIPAA, FedRAMP, PCI, or other formal compliance certification.
