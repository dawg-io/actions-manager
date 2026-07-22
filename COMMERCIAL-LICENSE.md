# Commercial License Overview

This document explains the intended commercial licensing model for ActionsManager in product and engineering terms. It is not legal advice and is not a substitute for a signed commercial agreement. Final license, EULA, subscription, privacy, warranty, support, SLA, and commercial terms should be reviewed by a qualified attorney before any paid launch.

## Current beta status

ActionsManager Self-Hosted is currently available as a **free beta preview** for testing, evaluation, and feedback. No paid plans are currently available during the beta. The first public beta is self-hosted only; Cloud/SaaS and GitHub Marketplace billing are not active beta offerings.

Free beta access does not grant permanent free access to future paid features, paid limits, paid support, commercial distributions, or commercial licensing. Features, limits, license-key behavior, packaging, and commercial availability may change before general availability.

## Community/Core License

The public Community/Core source code in this repository is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

## Future paid capabilities

Professional, Enterprise, or other commercial capabilities may be introduced later under separate commercial terms. Examples could include higher tier limits, paid support, packaged self-hosted distributions, enterprise services, or commercial-only features that are not part of the Apache 2.0 Community/Core edition. These examples are future possibilities, not active paid plans or binding pricing commitments.

## Entitlement sources

- **Self-hosted beta:** Free during beta; `LICENSE_KEY` is optional and reserved for self-hosted license behavior.
- **Future self-hosted paid use:** A valid license key may be required to enable future Professional, Enterprise, or commercial capabilities.
- **Future Cloud/SaaS use:** A valid GitHub Marketplace subscription or other commercial agreement may be required if a hosted service is launched later.

License keys and Marketplace subscriptions control feature access where applicable. They do not transfer ownership of customer data.

## Separate agreement controls

If a signed order form, subscription agreement, enterprise agreement, or other commercial agreement applies in the future, that agreement controls the paid commercial rights and obligations for the covered customer or deployment.

## Maintainer guidance

Do not implement payment plans, pricing tables, Marketplace launch behavior, or paid support commitments until the release scope and legal/commercial terms are approved. Do not place proprietary-only business logic, license generation secrets, private signing keys, or commercial-only source code in files intended to remain part of the Apache 2.0 Community/Core edition. If editions are separated later, isolate commercial-only code in clearly marked packages, build targets, or private repositories.
