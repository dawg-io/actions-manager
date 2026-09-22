import { describe, it, expect } from "vitest";
import { campaignReusableWorkflows } from "./campaignReusableWorkflows";

const REPOS = ["whatsupdawg/test1", "whatsupdawg/test2"];

describe("campaignReusableWorkflows", () => {
  it("offers a Caller Workflow Project its own reusable workflows", () => {
    // The reported bug: these were dropped, so the campaign modal showed no
    // reusable section and ook.yml could never be selected.
    const result = campaignReusableWorkflows({
      projectType: "standard",
      ownedReusable: [
        { name: "ook", workflowStatus: "committed_locally" },
        { name: "shared-workflow", workflowStatus: "synced_with_github" },
      ],
      linkedWorkflows: [],
      selectedRepos: REPOS,
    });

    expect(result.map((w) => w.name)).toEqual(["ook", "shared-workflow"]);
  });

  it("binds an owned reusable workflow to the project's repos, not one source repo", () => {
    const [ook] = campaignReusableWorkflows({
      projectType: "standard",
      ownedReusable: [{ name: "ook", workflowStatus: "committed_locally" }],
      linkedWorkflows: [],
      selectedRepos: REPOS,
    });

    expect(ook.deliversToProjectRepos).toBe(true);
    // A single sourceRepo would have counted one repo instead of every target.
    expect(ook.sourceRepo).toBeUndefined();
    expect(ook.isLinked).toBeUndefined();
  });

  it("keeps an RWX project's own workflows bound to its repo", () => {
    const [own] = campaignReusableWorkflows({
      projectType: "rwx",
      ownedReusable: [{ name: "rwx-own", workflowStatus: "committed_locally" }],
      linkedWorkflows: [],
      selectedRepos: ["whatsupdawg/rwx-repo"],
    });

    expect(own.sourceRepo).toBe("whatsupdawg/rwx-repo");
    expect(own.deliversToProjectRepos).toBeUndefined();
  });

  it("keeps a linked workflow bound to the project that owns it", () => {
    const [linked] = campaignReusableWorkflows({
      projectType: "standard",
      ownedReusable: [],
      linkedWorkflows: [
        { workflow_name: "linked-shared", workflowStatus: "committed_locally", rwx_repo: "whatsupdawg/rwx-repo" },
      ],
      selectedRepos: REPOS,
    });

    expect(linked.sourceRepo).toBe("whatsupdawg/rwx-repo");
    expect(linked.isLinked).toBe(true);
    expect(linked.deliversToProjectRepos).toBeUndefined();
  });

  it("offers both kinds together, each bound its own way", () => {
    const result = campaignReusableWorkflows({
      projectType: "standard",
      ownedReusable: [{ name: "ook", workflowStatus: "committed_locally" }],
      linkedWorkflows: [
        { workflow_name: "linked-shared", workflowStatus: "committed_locally", rwx_repo: "whatsupdawg/rwx-repo" },
      ],
      selectedRepos: REPOS,
    });

    expect(result.map((w) => w.name)).toEqual(["ook", "linked-shared"]);
    expect(result[0].deliversToProjectRepos).toBe(true);
    expect(result[1].sourceRepo).toBe("whatsupdawg/rwx-repo");
  });
});
