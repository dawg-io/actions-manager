---
layout: default
title: Environment Rulesets
parent: Features
nav_order: 8
---

# Environment Rulesets
{: .no_toc }

Keep one GitHub repository ruleset in ActionsManager and apply it across a project's repositories, instead of recreating the same branch protection by hand in each one.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What a ruleset is here

A **ruleset** in ActionsManager is a stored copy of a [GitHub repository ruleset](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) — the JSON GitHub itself accepts, held once and applied to many repositories.

ActionsManager stores the definition and applies it. It does not edit rules, validate them against GitHub's schema, or keep a repository's copy in step automatically. What it adds is the fan-out: one definition, applied to every repository in a project, and a way to see which repositories have it.

Rulesets are not workflows. They have no drift lifecycle, no pull request delivery, and no campaign — see [Drift Detection]({% link features/drift-detection.md %}) and [PR Campaigns]({% link features/pr-campaigns.md %}) for the features that do.

Rulesets live under **🛡️ Environment Rulesets** on the project page.

## Adding a ruleset

Two ways in, both storing the same thing:

- **Upload a JSON file.** The file must end in `.json` and contain a JSON object. Its `name` and `description` fields become the ruleset's name and description; without a `name`, the filename is used.
- **Create from JSON** pasted in directly, with a name and optional description supplied alongside it.

The easiest way to get a valid file is to export an existing ruleset from a repository that already has the rules you want, through GitHub's own ruleset UI or API.

A ruleset uploaded from a project page is associated with that project. That association is what later decides which repositories a GitHub-side removal reaches, so it matters more than it looks — see [Which repositories a removal reaches](#which-repositories-a-removal-reaches).

The association is made only if the project name resolves to a project owned by the same account. If it does not, the ruleset is still stored and the upload still reports success — but with no project attached, so a later GitHub-side removal resolves no repositories and reports that it removed nothing.

## Applying a ruleset

**🚀 Apply** sends the stored JSON to every repository currently ticked in **Repositories & Branches**, one `POST` per repository.

> **Select the repositories first.** Apply acts on the current selection in Repositories & Branches, not on a saved list.

The result reports how many repositories succeeded and how many failed. A failure on one repository does not stop the others — applying to five repositories where two fail applies to three and tells you about the two.

Apply always **creates**; it never updates a copy already on the repository. Re-applying a ruleset a repository already has is therefore either a second copy or a validation error from GitHub, which ActionsManager counts as a failure for that repository. Check the sync panel below before re-applying.

### Permissions

Rulesets are repository administration. Your GitHub token needs **admin access** to each repository you apply to, read or remove from. Without it GitHub returns 403 and ActionsManager reports that repository as failed rather than failing the whole operation. Rulesets need the **Administration: Read and write** permission — see [GitHub Permissions]({% link troubleshooting/github-permissions.md %}) for the full table and [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %}) for creating the token.

Apply reports a failed repository without saying why — the reason GitHub gave (permission denied, repository not found, validation error) is written to the backend log. Check there when a repository fails and the cause is not obvious. The sync panel does distinguish the cases, so it is often the quicker answer.

## Checking which repositories have it

The sync panel reads each selected repository's rulesets from GitHub and matches on the ruleset's **name** — the `name` inside the stored JSON, which can differ from the name shown in ActionsManager if the JSON was edited after import.

Each repository comes back as one of:

| Status | Meaning |
|---|---|
| `exists` | A ruleset with that name is on the repository |
| `not_found` | No ruleset with that name; the repository is reported as missing it |
| `permission_denied` | Your token lacks admin access, so it could not be checked — counted as missing, because it cannot be confirmed either way |
| `repo_not_found` | The repository could not be read at all |
| `error` | The check itself failed — a network error, or anything GitHub returned other than the three above — also counted as missing |

When any repository is missing it, the panel shows **⚠️ Missing in N repositories** with a **🔄 Sync** button.

**🔄 Sync** is an apply narrowed to the repositories the panel has confirmed are missing it. Repositories that could not be checked are skipped rather than guessed at, and the message says how many were skipped. If nothing is confirmed missing, Sync applies nothing and says so.

## Removing a ruleset

Deleting asks which copies to destroy, because the ActionsManager record and the GitHub policy are separate things and removing the wrong one has very different consequences.

| Option | ActionsManager record | GitHub policy |
|---|---|---|
| 🏠 **Remove from ActionsManager only** | Deleted | **Left in place and still enforced** |
| ☁️ **Remove from GitHub only** | Kept | Deleted |
| 💥 **Delete from ActionsManager and GitHub** | Deleted | Deleted |

**🏠 Remove from ActionsManager only** is the default, and it is the one to reach for if you only want to stop managing a ruleset here. Branch protection the ruleset enforces keeps applying to the repositories; ActionsManager simply stops tracking it, so it no longer checks whether those repositories still have it.

**☁️ Remove from GitHub only** lifts the policy but keeps the definition, so you can apply it again later without re-importing the JSON. This is the option for temporarily relaxing a rule.

**💥 Delete from ActionsManager and GitHub** does both, and is not reversible from ActionsManager — the definition is gone, so re-applying means finding the JSON again.

> **Removing from GitHub stops the branch protection those rules enforce.** Merges the ruleset was blocking become possible immediately, on every repository it is removed from.

### Which repositories a removal reaches

A GitHub-side removal does not ask you which repositories to touch. It resolves them from the **saved** repositories of the projects the ruleset is associated with, and deletes any ruleset matching the stored name from each.

Two consequences worth knowing:

- A repository that was never saved to the project — ticked in Repositories & Branches but not saved — is not reached, even if Apply reached it. This is a known gap, tracked in [issue #2054](https://github.com/dawg-io/actions-manager/issues/2054): Apply trusts the current selection while removal resolves saved rows, so the two can disagree and leave a ruleset enforced with nothing in ActionsManager tracking it. **Save your repository selection before applying a ruleset you may later want to remove.**
- A ruleset associated with no project resolves no repositories at all — including one whose upload silently failed to attach it, as above. Rather than reporting a removal that touched nothing, ActionsManager says the ruleset was not applied to any of the project's repositories.

A repository that has no ruleset by that name is not an error — it was never applied, or was already removed by hand, and that is an acceptable end state.

### When part of a removal fails

If GitHub rejects the removal on any repository, the whole operation returns an error naming the repositories that failed, and **the ActionsManager records are kept**. Dropping them would leave a ruleset enforcing branch protection with nothing here still pointing at it, which is the exact leftover the GitHub-side option exists to prevent.

The removal is not atomic across repositories: the ones that succeeded before the failure have already had their ruleset deleted. The sync panel is re-read after a failed removal so it reflects what actually happened rather than what was attempted.

## Limitations

Stated plainly, because each one is a thing the feature does not do:

- **No rule editing.** ActionsManager stores and applies the JSON. Changing a rule means editing the JSON and applying it again.
- **No automatic sync.** Nothing re-applies a ruleset when a repository is added to a project, and nothing notices a ruleset changed or deleted on GitHub until you check the sync panel.
- **Matching is by name.** A ruleset renamed on GitHub reads as missing, and re-applying adds a second copy rather than reconciling.
- **Apply and removal can disagree on targets.** See [Which repositories a removal reaches](#which-repositories-a-removal-reaches).
