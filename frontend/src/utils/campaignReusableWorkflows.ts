/**
 * Which reusable workflows a PR campaign should offer, and where each is bound.
 *
 * Owning a workflow is what decides where it is delivered — not the reusable
 * label. A workflow the project owns lives in that project's own repositories,
 * so the campaign delivers it there with the rest of the files that project
 * changed. Only a workflow LINKED from a Reusable Workflow Project belongs in
 * that project's repository instead.
 *
 * This lived inline in the campaign modal's props, where it could not be tested
 * and where a standard project's own reusable workflows were dropped entirely.
 */
export interface OwnedReusableWorkflow {
  name: string;
  workflowStatus?: string;
}

export interface LinkedReusableWorkflow {
  workflow_name: string;
  workflowStatus?: string;
  rwx_repo?: string;
}

export interface CampaignReusableWorkflow {
  name: string;
  status?: string;
  sourceRepo?: string;
  isLinked?: boolean;
  /** Delivered to every selected repo rather than to one source repo. */
  deliversToProjectRepos?: boolean;
}

export function campaignReusableWorkflows(params: {
  projectType: string | undefined;
  ownedReusable: OwnedReusableWorkflow[];
  linkedWorkflows: LinkedReusableWorkflow[];
  selectedRepos: string[];
}): CampaignReusableWorkflow[] {
  const { projectType, ownedReusable, linkedWorkflows, selectedRepos } = params;
  const isRwx = projectType === "rwx";

  const owned: CampaignReusableWorkflow[] = (ownedReusable ?? []).map((w) =>
    isRwx
      ? {
          // An RWX project has one repo, and its workflows go to it.
          name: w.name,
          status: w.workflowStatus,
          sourceRepo: selectedRepos.length > 0 ? selectedRepos[0] : undefined,
        }
      : {
          // A caller project can own reusable workflows too (imported). They
          // live in this project's repositories, so they are offered like any
          // other file it changed and delivered to every selected repo.
          name: w.name,
          status: w.workflowStatus,
          deliversToProjectRepos: true,
        },
  );

  // Linked workflows carry their owning project's name, in that project's
  // naming mode, and go to that project's repo.
  const linked: CampaignReusableWorkflow[] = (linkedWorkflows ?? []).map((w) => ({
    name: w.workflow_name,
    status: w.workflowStatus,
    sourceRepo: w.rwx_repo,
    isLinked: true,
  }));

  return [...owned, ...linked];
}
