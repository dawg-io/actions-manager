---
title: Managed Actions
description: Import third-party GitHub Actions into a shared catalog so their inputs are ready to use when you build workflows.
---

Import third-party GitHub Actions into a shared catalog so their inputs are ready to use when you build workflows.


---

## What is a Managed Action?

A **Managed Action** is a catalog entry for a third-party GitHub Action: a slug (`owner/repo`), a pinned ref, and a set of typed inputs (name, description, required, default) parsed from the action's `action.yml`. It exists so you don't have to re-read an action's metadata every time you add a step that uses it.

A Managed Action is **not** a project. It has no repository scope, no branch, no pull requests, and no drift lifecycle — it's a reference entry, not something ActionsManager delivers or keeps in sync with GitHub. See [Projects](projects.html) for the project types that do have that lifecycle.

## Adding a Managed Action

Adding a Managed Action starts with a URL. ActionsManager supports three formats:

- **Bare repo URL** — `https://github.com/<owner>/<repo>`. ActionsManager looks for `action.yml`, `action.yaml`, `actions.yml`, or `actions.yaml` at the repository root.
- **Direct file URL** — `https://github.com/<owner>/<repo>/blob/<ref>/<path>`. Use this for actions whose metadata file isn't at the repo root (composite actions in a subdirectory, for example).
- **GitHub Marketplace listing URL** — `https://github.com/marketplace/actions/<slug>`. ActionsManager resolves the listing to its backing repository.

Paste one of these into the add flow and ActionsManager fetches and parses the action's metadata into a **preview**: name, description, and the full list of inputs. From there you can edit the name, description, or any input's default before saving. Saving adds it to the shared catalog.

## The default catalog

Every install starts with 8 pre-seeded, commonly used actions:

- `actions/checkout`
- `actions/setup-node`
- `actions/setup-python`
- `actions/setup-java`
- `actions/cache`
- `actions/upload-artifact`
- `actions/download-artifact`
- `dawg-io/am-build-vars` — reads per-repository build variables from a committed `am-build-vars.yml`, exports them as env vars, and shares them across jobs, workflows and runs

Any user can remove entries they don't want. Removal is **permanent** — deleted defaults are not re-seeded and won't reappear on restart.

When a later release adds an action to the defaults, an install that is already running picks it up on its next start, once. ActionsManager records each default it has offered, so a new one arrives exactly one time and a default you deleted stays deleted — including one you delete after it arrives this way.

## Shared across your workspace

The Managed Actions catalog is shared and workspace-wide, not per-user. Any authenticated user can view, edit, or delete any entry, including ones imported by someone else.

## Using Managed Actions in the workflow editor

In the GUI workflow editor's step picker, imported Managed Actions appear under **Your imported actions** when you're configuring a `uses:` step. Selecting one fills in its `owner/repo@ref` and turns its known inputs into typed `with:` fields, so you don't have to look up the action's inputs separately. Each input renders according to its type — a checkbox for `boolean`, a dropdown for `choice`, a number field for `number`, and a text field otherwise.

Actions often declare far more inputs than a given step needs, so the editor only shows the ones that matter up front:

- **Required inputs** are always visible.
- **Optional inputs you've set a value for** are visible too, marked with a small **Set** badge so you can tell them apart from the required ones at a glance.
- **Everything else** sits behind a **Show N more options** disclosure. Expand it to set any of them; once set, an input joins the visible list and stays there.

Clearing an optional input's value removes it from the generated `with:` block, but the field stays on screen while you're working so you can type a new value straight back in.

Inputs the action doesn't declare — anything you add yourself — still appear under **Additional Parameters** as free-text key/value pairs, and are never hidden.

## Related Topics

- [Projects](projects.html) — the project types that do have a repo/branch/PR/drift lifecycle
- [Workflows](workflows.html) — the GUI editor where Managed Actions surface as step suggestions
