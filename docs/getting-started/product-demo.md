---
layout: default
title: Product Demo
parent: Getting Started
nav_order: 1.5
---

# ActionsManager Product Demo
{: .no_toc }

See a complete multi-repository GitHub Actions workflow rollout, start to finish, in ActionsManager Self-Hosted.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Watch the demo

<div class="video-embed">
  <iframe
    src="https://www.youtube-nocookie.com/embed/WkDYK7pCBjI"
    title="ActionsManager product demo: multi-repository workflow rollout"
    frameborder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
    allowfullscreen>
  </iframe>
</div>

[Watch on YouTube ↗](https://youtu.be/WkDYK7pCBjI){: .fs-4 }

Can't load the embedded player above? Watch it directly on YouTube instead:

[![ActionsManager product demo thumbnail - click to watch on YouTube](https://img.youtube.com/vi/WkDYK7pCBjI/maxresdefault.jpg)](https://youtu.be/WkDYK7pCBjI)

## What's in the video

The demo walks through a complete rollout to a multi-repository Maven project:

1. **Authenticate using a GitHub PAT** — sign in with a fine-grained or classic personal access token.
2. **Create the `MavenBuilds` Caller Workflow Project** — set up a project to manage a group of repositories.
3. **Add three repositories** — bring the target repos under management.
4. **Detect the Maven build type** — ActionsManager inspects each repository and identifies its build type.
5. **Generate workflow changes and create pull requests** — a caller workflow is generated per repository and proposed as a pull request.
6. **Manage the pull requests** — review and track PR status for all three repositories from one place.
7. **Merge the pull requests** — apply the workflow changes to each repository.

{: .note }
Never expose a Personal Access Token in recordings, screenshots, shell history, documentation, or committed files. This demo does not require you to provide a PAT to YouTube or any third-party service — PAT authentication happens only between your browser and your own ActionsManager instance.

## What this demonstrates

- **Multi-repository project management** — grouping repositories under one Caller Workflow Project
- **Automated build detection** — identifying a repository's build type without manual inspection
- **Consistent workflow generation** — the same workflow template applied uniformly across every repository
- **PR-based delivery** — proposing changes as reviewable pull requests instead of direct commits
- **Centralized PR management** — tracking and merging pull requests across repositories from one interface
- **Workflow synchronization after merge** — keeping caller workflows aligned with the managed definition once merged

## Next steps

- **→ [Self-Hosted Installation]({% link getting-started/installation.md %})**
- **→ [Quick Start]({% link getting-started/quick-start.md %})**
- **→ [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %})**
- **→ [ActionsManager on GitHub](https://github.com/dawg-io/actions-manager)**
