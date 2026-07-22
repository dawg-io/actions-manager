---
layout: default
title: Reusable Workflows
parent: Features
nav_order: 5
---

# Reusable Workflows
{: .no_toc }

Manage both sides of GitHub Actions reusability — producers and consumers — and keep them synchronized.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Overview

GitHub Actions supports **reusable workflows** — workflow files that define a `workflow_call` trigger and can be invoked by other workflows using the `uses:` directive. ActionsManager manages both sides:

- **Reusable Workflows (Producers)** — the centrally defined workflows that encode your organization's standards
- **Caller Workflows (Consumers)** — the per-repository workflows that invoke reusable workflows via `uses:`

Managing only one side leaves gaps: updating producers without updating consumers causes drift; managing consumers without versioning producers leads to duplication. ActionsManager manages both sides together.

## Reusable Workflow Projects (Producers)

A **Reusable Workflow Project** in ActionsManager manages the repository that defines and publishes shared workflow definitions.

With a producer project you can:
- Author and version reusable workflow YAML
- Track which repositories (consumers) reference the reusable workflow
- See which consumers are in sync vs. drifted against the current reusable workflow version

## Caller Workflow Projects (Consumers)

A **Caller Workflow Project** manages the repositories whose workflows call the reusable workflow.

With a consumer project you can:
- Generate and distribute caller workflows across many repositories
- Keep `uses:` references aligned with the current reusable workflow version
- Roll out reference updates through PR campaigns when the producer changes

## End-to-End Flow

A typical producer-to-consumer update cycle:

1. **Update the reusable workflow** in the producer repository (e.g., bump a version or change inputs)
2. **ActionsManager detects** which caller workflows across all consumer projects reference the updated reusable workflow
3. **Create a PR campaign** — each affected repository receives a pull request updating its caller workflow to the new version
4. **Merge or sync** the PRs individually, in bulk, or via direct commit
5. **Drift detection confirms** that all consumers are back in sync with the producer

## Inputs and Outputs

Reusable workflows define `inputs:` and `outputs:` that caller workflows must provide. ActionsManager:
- Tracks the inputs/outputs defined by the reusable workflow
- Validates that generated caller workflows provide the required inputs
- Surfaces mismatches when a reusable workflow changes its interface

## Related Topics

- [Reusable Workflow Repository Setup]({% link features/reusable-workflow-repository-setup.md %}) — step-by-step guide with YAML examples and end-to-end walkthrough
- [Projects]({% link features/projects.md %}) — project types for producer and consumer management
- [Workflows]({% link features/workflows.md %}) — workflow management and delivery
- [Drift Detection]({% link features/drift-detection.md %}) — keep producers and consumers in sync
- [PR Campaigns]({% link features/pr-campaigns.md %}) — roll out producer changes to consumers
