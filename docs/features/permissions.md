---
layout: default
title: Permissions
parent: Features
nav_order: 13
---

# Permissions
{: .no_toc }

Who can see a project, and who can change it.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Two levels

Access is decided by two things: your **workspace role**, set on the Workspace Members
page, and an optional **project role**, granted per project on that project's Project
Members page.

The workspace role decides what you can see. The project role decides what you can
change.

## Workspace roles

| Role | Sees | Changes |
|---|---|---|
| **Admin** | every project | everything, with no project assignment needed |
| **Member** | every project, read-only | only the projects an admin has made them an **Editor** of |
| **Read Only** | only projects they have been assigned to | nothing, ever |

ActionsManager is a single workspace: every project belongs to it. So adding someone as
a **Member** is what gives them the workspace — they can open any project and read its
workflows, campaigns and history immediately, without being assigned to it one by one.

A **Read Only** user is the opposite: they see nothing until an admin assigns them to a
specific project, and no assignment ever grants them write access. Writes are refused
before the request reaches the feature.

## Project roles

An admin grants these from **Project Configs → Project Members**.

| Project role | Effect on a Member | Effect on a Read Only user |
|---|---|---|
| **Editor** | can change the work inside this project | not applicable — read-only users never write |
| **Viewer** | no change; they already see it | lets them see this project |

So an assignment means different things depending on the workspace role. For a Member
it grants **write** access to one project. For a Read Only user it grants **sight** of
one project. Admins need no assignment at all and are not offered in the picker.

## What requires Editor

Everything that writes to GitHub or changes the project, including:

- creating a [PR campaign]({% link features/pr-campaigns.md %}), and merging or closing
  its pull requests
- running preflight validation, and merging or closing the validation pull request
- rolling a campaign back
- saving, renaming or removing a [workflow]({% link features/workflows.md %})
- importing workflows
- editing repository configuration — repositories and branches, deploy environments,
  environment variables, secrets and rulesets

Viewing any of the above is always allowed for a Member. A project opened without Editor
access shows a **Read Only** badge, and its editing controls are disabled rather than
hidden, so it is clear what exists and what you cannot change. The repository
configuration panels are shown the same way — readable, with every control disabled.

## What requires Admin

**Project Configs** manages the project itself rather than the work inside it, so it is
open to workspace Admins only. It holds Project Info, Project Members, Drift Detection,
Export Config and Danger Zone — and, in a Reusable Workflow Project, Linked Projects.

Unlike the controls above, this group is **hidden rather than disabled**: an Editor does
not see it either, and following a link straight to one of its sections lands on the
project's workflows instead. So changing a project's name or colour, managing its
members, adjusting drift detection, exporting its configuration, or deleting it are all
Admin actions, whatever project role you hold.

## Worked example

A workspace with three people and three projects:

- **example-admin** is an Admin. Sees all three, changes all three.
- **example-user** is a Member with no assignments. Sees all three, changes none.
  Opening one shows *"You have viewer access to this project. Editing is disabled."*
- Give **example-user** the **Editor** role on one project. They now change the work in
  that one and still only read the other two. Project Configs stays out of reach on all
  three — that group is for Admins.
- **example-readonly** is a Read Only user with no assignments, and sees no projects
  at all.

## Where it is enforced

Permission is checked on the server for every request, not only in the interface. A
disabled button is a convenience; the same rule is applied again when the request
arrives, so a request made outside the interface is refused the same way.
