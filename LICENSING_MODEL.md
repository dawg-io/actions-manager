# ActionsManager Licensing Model

This page explains the product licensing structure in engineering terms. It is not legal advice. Final license notices, EULA, Terms of Service, Privacy Policy, and commercial terms should be reviewed by a qualified attorney before public launch.

> **Beta notice:** The first public release is the free, self-hosted ActionsManager beta. No paid plans are currently available, and the Self-hosted Professional/Enterprise and Cloud/SaaS modes described below are not active offerings for this release — they document the intended future model, not current availability.

## Document Types

| Document | Purpose |
|----------|---------|
| [LICENSE](LICENSE) | Apache License 2.0 terms for Community/Core source code in this repository. |
| [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md) | Plain-language overview for paid Professional and Enterprise capabilities and separate commercial terms. |
| [EULA.md](EULA.md) | Draft self-hosted/commercial end-user terms for packaged or paid deployments. |
| [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md) | Draft Cloud/SaaS service terms. |
| [PRIVACY_POLICY.md](PRIVACY_POLICY.md) | Placeholder describing high-level data handling. |

## Deployment Modes

### Self-hosted Free

- Community/Core portions are licensed under Apache License 2.0.
- No license key is required for the Free tier.
- An EULA may apply if the project is distributed as a packaged product.

### Self-hosted Professional / Enterprise

- Community/Core portions remain under Apache License 2.0.
- Paid features, support, packaged distributions, and license-key-enabled tiers may be governed by a commercial license and EULA.
- A valid self-hosted license key may be required for Professional or Enterprise capabilities.
- Invalid or expired license keys should fail closed to the Free tier.

### Cloud / SaaS

- Cloud access is governed by Terms of Service, Privacy Policy, GitHub Marketplace terms, and any applicable commercial subscription terms.
- Account tiers are managed by GitHub Marketplace subscriptions and verified Marketplace webhooks.
- Cloud tier management should not use self-hosted license keys.

## Maintainer Guidance

- Keep Apache 2.0 Community/Core code separate from proprietary-only features if the project later separates editions.
- Do not place private signing keys, license generation secrets, customer secrets, webhook secrets, OAuth secrets, GitHub tokens, or repository secret values in public source code.
- Do not implement security-sensitive license gating only in the frontend. Server-side tier checks remain the source of truth.
- Clearly label maintainer-only tooling and do not ask customers to provide signing secrets for self-hosted licenses.
