import { saveWorkflows, updateWorkflows, deleteWorkflowFromGitHub, deleteWorkflowFromDatabase, deleteReusableWorkflowFromGitHub } from '../api/workflows';
import { saveRxWorkflows } from '../api/rxworkflows';
import { updateLinkedReusableWorkflow } from '../api/projects';
import { Workflow, RXWorkflow, UnifiedWorkflowItem } from '../types/workflow';
import { WorkflowResult } from '../types/workflowResponse';
import { RwxWorkflow } from '../api/projects';
import { normalizeWorkflowStem, setWorkflowYamlName } from './workflowFilename';
import { toast } from './toast';
import { WorkflowGUI } from './workflowGuiConversion';
import { tour } from './tour';

// Save Draft functionality
export const saveDraftWorkflow = async (
  index: number | null,
  type: 'regular' | 'reusable',
  workflows: Workflow[],
  rxworkflows: RXWorkflow[],
  user: string,
  projectName: string,
  accountType?: string,
  markWorkflowAsSaved?: (index: number, type: 'regular' | 'reusable', workflowStatus?: string) => void,
  fetchWorkflowsCount?: () => Promise<void>,
  refreshProjectsList?: () => Promise<void>,
  onProjectStateChange?: (state: string) => void
): Promise<void> => {
  if (index === null) return;
  
  const workflow = type === 'regular' ? workflows[index] : rxworkflows[index];
  
  if (!workflow?.name || !workflow?.content) {
    toast.error("Please provide both a workflow name and content before saving as draft.");
    return;
  }

  // Normalize to stem: trim whitespace and strip any .yml/.yaml extension.
  // The backend stores workflow_name as a stem and appends .yml itself via
  // format_workflow_name(), so we must send the stem to avoid duplicate rows
  // and double-extension issues in prefix mode (AM_CODE_name.yml.yml).
  const stem = normalizeWorkflowStem(workflow.name);
  if (!stem) {
    toast.error("Please provide a valid workflow name before saving as draft.");
    return;
  }

  try {
    console.log("Saving workflow as draft:", stem);
    
    // Determine new status: first-ever save → "new"; subsequent saves → "committed_locally"
    const newWorkflowStatus =
      (workflow.workflowStatus != null && workflow.workflowStatus !== '')
        ? 'committed_locally'
        : 'new';

    if (type === 'regular') {
      const singleWorkflow: Workflow[] = [{ ...workflows[index], name: stem }];
      const saveResponse = await saveWorkflows(user, projectName, singleWorkflow);
      if (!saveResponse) {
        throw new Error("Invalid response from save API");
      }
      // Notify parent of project state change if it changed (e.g. new → draft)
      if (onProjectStateChange && saveResponse.pr_state) {
        onProjectStateChange(saveResponse.pr_state);
      }
    } else {
      const singleWorkflow: RXWorkflow[] = [{ ...rxworkflows[index], name: stem }];
      const saveResponse = await saveRxWorkflows(user, projectName, singleWorkflow);
      if (!saveResponse) {
        throw new Error("Invalid response from save API");
      }
      // Notify parent of project state change if it changed (e.g. new → draft)
      // so the Create Pull Requests button enables without a page refresh
      if (onProjectStateChange && saveResponse.pr_state) {
        onProjectStateChange(saveResponse.pr_state);
      }
    }
    
    if (markWorkflowAsSaved) {
      markWorkflowAsSaved(index, type, newWorkflowStatus);
    }
    // This is the "Commit Locally" the tour points at — the editor's primary
    // action routes here, not through ProjectMgmt's toolbar save.
    tour.completed('commit-workflow');
    toast.success(`Workflow '${stem}.yml' saved as draft.`);
    
    // Update count for free accounts
    if (accountType === "free" && fetchWorkflowsCount) {
      await fetchWorkflowsCount();
    }
    
    // Refresh projects list to update status
    if (refreshProjectsList) {
      await refreshProjectsList();
    }
  } catch (error: any) {
    console.error("❌ Error saving workflow draft:", error);
    toast.error(`Failed to save workflow '${stem}.yml' as draft: ${error.message}`);
  }
};

// Commit workflow changes and update the existing open pull request
export const commitAndUpdatePRWorkflow = async (
  index: number | null,
  type: 'regular' | 'reusable',
  workflows: Workflow[],
  rxworkflows: RXWorkflow[],
  user: string,
  projectName: string,
  selectedRepos: string[],
  regexPattern: string,
  branchOption: string = "default",
  markWorkflowAsSaved?: (index: number, type: 'regular' | 'reusable', workflowStatus?: string) => void,
  fetchWorkflowsCount?: () => Promise<void>,
  refreshProjectsList?: () => Promise<void>,
  onProjectStateChange?: (state: string) => void
): Promise<boolean> => {
  if (index === null) return false;

  const workflow = type === 'regular' ? workflows[index] : rxworkflows[index];
  if (!workflow?.name || !workflow?.content) {
    toast.error("Please provide both a workflow name and content before updating.");
    return false;
  }

  // Normalize to stem: trim whitespace and strip any .yml/.yaml extension.
  // Store the stem in DB (backend appends .yml via format_workflow_name).
  // The GitHub update API also strips extensions server-side before formatting.
  const stem = normalizeWorkflowStem(workflow.name);
  if (!stem) {
    toast.error("Please provide a valid workflow name before updating.");
    return false;
  }

  try {
    // Step 1: Save updated content to DB (as stem — backend handles .yml suffix)
    if (type === 'regular') {
      const saveResponse = await saveWorkflows(user, projectName, [{ ...workflows[index], name: stem }]);
      if (!saveResponse) throw new Error("Invalid response from save API");
      if (onProjectStateChange && saveResponse.pr_state) {
        onProjectStateChange(saveResponse.pr_state);
      }
    } else {
      const saveResponse = await saveRxWorkflows(user, projectName, [{ ...rxworkflows[index], name: stem }]);
      if (!saveResponse) throw new Error("Invalid response from save API");
      if (onProjectStateChange && saveResponse.pr_state) {
        onProjectStateChange(saveResponse.pr_state);
      }
    }

    // Step 2: Push to GitHub to update the existing PR branch (stem sent; backend adds prefix+.yml)
    const workflowsPayload: Workflow[] = type === 'regular' ? [{ ...workflows[index], name: stem }] : [];
    // RXWorkflow is structurally compatible with Workflow for the API (name + content)
    const rxworkflowsPayload: Workflow[] = type === 'reusable'
      ? [{ name: stem, content: workflow.content, isReusable: true }]
      : [];

    const updateResponse = await updateWorkflows(
      user,
      selectedRepos,
      workflowsPayload,
      rxworkflowsPayload,
      regexPattern,
      branchOption,
      projectName
    );

    if (updateResponse.error) {
      throw new Error(updateResponse.error);
    }

    // Check per-repo results for errors
    const results = updateResponse.results || {};
    const hasErrors = Object.values(results).some(
      (r): r is WorkflowResult => typeof r === 'object' && r !== null && r.status === 'error'
    );
    if (hasErrors) {
      throw new Error("One or more repositories failed to update. Check console for details.");
    }

    // Mark as saved in the frontend state – keep workflowStatus as 'under_review'
    if (markWorkflowAsSaved) {
      markWorkflowAsSaved(index, type, 'under_review');
    }

    toast.success(`Workflow '${stem}.yml' committed and pull request updated.`);

    if (fetchWorkflowsCount) {
      await fetchWorkflowsCount();
    }
    if (refreshProjectsList) {
      await refreshProjectsList();
    }

    return true;
  } catch (error: any) {
    console.error("❌ Error committing and updating PR:", error);
    toast.error(`Failed to commit and update PR for '${stem}.yml': ${error.message}`);
    return false;
  }
};

// Commit and Update PR for linked reusable workflows.
// Linked workflows are stored in the RWX project's repo/DB, but their association to
// an open PR is tracked via the standard project's ProjectPullRequest.  The save step
// must target the RWX project so the correct DB record is updated, while the push step
// uses the standard project name so the backend can resolve the right RWX repo via
// LinkedReusableWorkflow.
export const commitAndUpdatePRLinkedWorkflow = async (
  index: number,
  linkedWorkflows: Array<{ workflow_id?: number; workflow_name: string; workflow_yaml: string; rwx_project_name: string }>,
  user: string,
  projectName: string,        // standard project name – used for the GitHub push
  selectedRepos: string[],
  regexPattern: string,
  branchOption: string = "default",
  fetchWorkflowsCount?: () => Promise<void>,
  refreshProjectsList?: () => Promise<void>,
  onProjectStateChange?: (state: string) => void
): Promise<boolean> => {
  const linkedWf = linkedWorkflows[index];
  if (!linkedWf?.workflow_name || !linkedWf?.workflow_yaml) {
    toast.error("The selected linked workflow data is incomplete. Please reload the project and try again.");
    return false;
  }

  try {
    // Step 1: Save updated content to the canonical reusable workflow row
    // via the dedicated linked-workflow endpoint.  Resolution is by
    // workflow_id joined through LinkedReusableWorkflow to the standard
    // project — using the generic save-workflows endpoint here would create
    // a duplicate workflow row in the RWX project because the display
    // workflow_name (e.g. "AM_RWW1_testrwx.yml") does not match the
    // canonical stored stem ("testrwx").
    if (typeof linkedWf.workflow_id !== 'number') {
      throw new Error("Linked workflow is missing workflow_id; please reload the project.");
    }
    await updateLinkedReusableWorkflow(
      user,
      projectName,
      linkedWf.workflow_id,
      linkedWf.workflow_yaml
    );

    // Step 2: Push to GitHub using the standard project context.
    // The backend resolves the target RWX repo via LinkedReusableWorkflow for the
    // standard project, so passing project_name=standardProjectName is correct.
    const rxPayload: Workflow[] = [
      { name: linkedWf.workflow_name, content: linkedWf.workflow_yaml, isReusable: true }
    ];
    const updateResponse = await updateWorkflows(
      user,
      selectedRepos,
      [],
      rxPayload,
      regexPattern,
      branchOption,
      projectName
    );

    if (updateResponse.error) {
      throw new Error(updateResponse.error);
    }

    const results = updateResponse.results || {};
    const hasErrors = Object.values(results).some(
      (r): r is WorkflowResult => typeof r === 'object' && r !== null && r.status === 'error'
    );
    if (hasErrors) {
      throw new Error("One or more repositories failed to update. Check console for details.");
    }

    if (onProjectStateChange) {
      onProjectStateChange('open');
    }

    toast.success(`Linked workflow '${linkedWf.workflow_name}' committed and pull request updated.`);

    if (fetchWorkflowsCount) {
      await fetchWorkflowsCount();
    }
    if (refreshProjectsList) {
      await refreshProjectsList();
    }

    return true;
  } catch (error: any) {
    console.error("❌ Error committing and updating linked workflow PR:", error);
    toast.error(`Failed to commit and update PR for '${linkedWf.workflow_name}': ${error.message}`);
    return false;
  }
};

// Save draft for linked reusable workflows.
// Updates the canonical reusable workflow row in the source RWX project via
// the dedicated /api/projects/{name}/linked-reusable-workflows/{id} endpoint.
// The backend resolves the workflow by ID joined through LinkedReusableWorkflow
// (NOT by workflow_name) so the display-formatted name returned for linked
// workflows can no longer cause a duplicate workflow row to be created in the
// source RWX project.
export const saveDraftLinkedWorkflow = async (
  index: number,
  linkedWorkflows: RwxWorkflow[],
  user: string,
  standardProjectName: string,
  setLinkedWorkflows?: (updater: (prev: RwxWorkflow[]) => RwxWorkflow[]) => void,
  refreshProjectsList?: () => Promise<void>
): Promise<void> => {
  const linkedWf = linkedWorkflows[index];
  if (!linkedWf?.workflow_name || !linkedWf?.workflow_yaml) {
    toast.error("The selected linked workflow data is incomplete. Please reload the project and try again.");
    return;
  }
  if (typeof linkedWf.workflow_id !== 'number') {
    toast.error("Linked workflow source could not be resolved. Please reload the project and try again.");
    return;
  }

  try {
    const result = await updateLinkedReusableWorkflow(
      user,
      standardProjectName,
      linkedWf.workflow_id,
      linkedWf.workflow_yaml
    );

    // Update isModified and workflowStatus from the API response so the
    // editor badge, sidebar card, and PR campaign modal all reflect the new
    // status immediately — without requiring a page refresh.
    if (setLinkedWorkflows) {
      setLinkedWorkflows((prev: RwxWorkflow[]) => {
        const updated = [...prev];
        if (updated[index]) {
          updated[index] = {
            ...updated[index],
            isModified: false,
            workflowStatus: result.workflow_status ?? 'committed_locally',
          };
        }
        return updated;
      });
    }

    toast.success(`Reusable workflow '${linkedWf.workflow_name}' saved in ${linkedWf.rwx_project_name}.`);

    if (refreshProjectsList) {
      await refreshProjectsList();
    }
  } catch (error: any) {
    console.error("❌ Error saving linked workflow draft:", error);
    const detail = error?.response?.data?.detail;
    const baseMessage = detail || error.message || "Unknown error";
    if (error?.response?.status === 404) {
      toast.error(`Could not find the source reusable workflow for '${linkedWf.workflow_name}'. Please reload the project and try again.`);
    } else {
      toast.error(`Failed to update '${linkedWf.workflow_name}' in ${linkedWf.rwx_project_name}: ${baseMessage}`);
    }
  }
};

// Helper function to handle authentication errors
const handleAuthenticationError = (): void => {
  toast.error("Authentication required. Please log in again.");
  localStorage.removeItem("github_user");
  globalThis.setTimeout(() => {
    globalThis.location.reload();
  }, 1500);
};

// Helper function to handle workflow deletion errors
const handleDeleteError = (error: any): void => {
  console.error("❌ Error deleting workflow:", error);
  
  // Handle specific error cases - Type guard for axios error
  if (error && typeof error === 'object' && 'response' in error) {
    if (error.response?.status === 401) {
      handleAuthenticationError();
    } else if (error.response?.status === 404) {
      toast.error("Workflow or project not found. The workflow may have already been deleted.");
    } else {
      const errorMessage = error.response?.data?.detail ?? (error as Error).message ?? "Unknown error";
      toast.error(`Error deleting workflow: ${errorMessage}`);
    }
  } else {
    const errorMessage = error instanceof Error ? error.message : "Unknown error";
    toast.error(`Error deleting workflow: ${errorMessage}`);
  }
};

// Helper function to delete regular workflow
const deleteRegularWorkflow = async (
  params: {
    user: string;
    selectedRepos: string[];
    workflowName: string;
    regexPattern: string;
    projectName: string;
  },
  state: {
    workflows: Workflow[];
    index: number;
    setWorkflows: (workflows: Workflow[]) => void;
  }
): Promise<void> => {
  await deleteWorkflowFromGitHub(
    params.user,
    params.selectedRepos,
    params.workflowName,
    params.regexPattern,
    params.projectName
  );
  await deleteWorkflowFromDatabase(params.user, params.projectName, params.workflowName);
  const newWorkflows = state.workflows.filter((_, i) => i !== state.index);
  state.setWorkflows(newWorkflows);
};

// Helper function to delete reusable workflow
const deleteReusableWorkflow = async (
  user: string,
  selectedRepos: string[],
  workflowName: string,
  projectName: string,
  index: number,
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void
): Promise<void> => {
  await deleteReusableWorkflowFromGitHub(user, workflowName, projectName);
  await deleteWorkflowFromDatabase(user, projectName, workflowName);
  setRXWorkflows(prev => {
    const newWorkflows = Array.isArray(prev) ? [...prev] : [];
    return newWorkflows.filter((_, i) => i !== index);
  });
};

// Delete workflow functionality
export const deleteWorkflow = async (
  index: number,
  type: 'regular' | 'reusable',
  workflows: Workflow[],
  rxworkflows: RXWorkflow[],
  user: string,
  projectName: string,
  selectedRepos: string[],
  regexPattern: string,
  setWorkflows: (workflows: Workflow[]) => void,
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void,
  setSelectedWorkflowId: (id: string | null) => void
): Promise<void> => {
  const workflow = type === 'regular' ? workflows[index] : rxworkflows[index];
  
  if (!workflow) return;

  try {
    if (type === 'regular') {
      await deleteRegularWorkflow(
        {
          user,
          selectedRepos,
          workflowName: workflow.name,
          regexPattern,
          projectName,
        },
        {
          workflows,
          index,
          setWorkflows,
        }
      );
    } else {
      await deleteReusableWorkflow(user, selectedRepos, workflow.name, projectName, index, setRXWorkflows);
    }
    
    setSelectedWorkflowId(null);
    toast.success(`Workflow "${workflow.name}" deleted successfully.`);
  } catch (error: any) {
    handleDeleteError(error);
  }
};

// Workflow creation utilities
export const createBlankWorkflow = (
  type: 'regular' | 'reusable',
  workflowName: string,
  workflows: Workflow[],
  setWorkflows: (workflows: Workflow[]) => void,
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void,
  setSelectedWorkflowId: (id: string) => void
): void => {
  const stem = normalizeWorkflowStem(workflowName);
  const content = setWorkflowYamlName('', stem);

  if (type === 'regular') {
    const newWorkflow: Workflow = {
      name: stem,
      content,
      isReusable: false,
      isModified: true
    };
    
    const newWorkflows = [...workflows, newWorkflow];
    setWorkflows(newWorkflows);
    setSelectedWorkflowId(`regular-${newWorkflows.length - 1}`);
  } else {
    const newWorkflow: RXWorkflow = {
      name: stem,
      content,
      isReusable: true,
      isModified: true
    };
    
    setRXWorkflows(prev => {
      const newWorkflows = Array.isArray(prev) ? [...prev, newWorkflow] : [newWorkflow];
      setSelectedWorkflowId(`reusable-${newWorkflows.length - 1}`);
      return newWorkflows;
    });
  }
};

export interface WorkflowChangeParams {
  field: string;
  value: string;
  selectedWorkflow: UnifiedWorkflowItem | undefined;
  workflows: Workflow[];
  setWorkflows: (workflows: Workflow[] | ((prev: Workflow[]) => Workflow[])) => void;
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void;
  editMode: 'yaml' | 'gui';
  regularGuiWorkflow: WorkflowGUI;
  guiWorkflow: WorkflowGUI;
  setRegularGuiWorkflow: (workflow: WorkflowGUI) => void;
  setGuiWorkflow: (workflow: WorkflowGUI) => void;
  markWorkflowAsModified: (index: number, type: 'regular' | 'reusable') => void;
  setLinkedWorkflows?: (updater: (prev: any[]) => any[]) => void;
}

export const handleWorkflowChange = ({
  field,
  value,
  selectedWorkflow,
  workflows,
  setWorkflows,
  setRXWorkflows,
  editMode,
  regularGuiWorkflow,
  guiWorkflow,
  setRegularGuiWorkflow,
  setGuiWorkflow,
  markWorkflowAsModified,
  setLinkedWorkflows,
}: WorkflowChangeParams) => {
  if (!selectedWorkflow) return;

  if (selectedWorkflow.type === 'regular') {
    setWorkflows(prev => {
      const newWorkflows = [...prev];
      newWorkflows[selectedWorkflow.originalIndex] = {
        ...newWorkflows[selectedWorkflow.originalIndex],
        [field]: value,
        isModified: true
      };
      return newWorkflows;
    });
    if (field === 'name' && editMode !== 'gui') {
      setRegularGuiWorkflow({ ...regularGuiWorkflow, name: value });
    }
    markWorkflowAsModified(selectedWorkflow.originalIndex, 'regular');
  } else if (selectedWorkflow.type === 'reusable') {
    setRXWorkflows(prev => {
      const newWorkflows = Array.isArray(prev) ? [...prev] : [];
      const workflow = newWorkflows[selectedWorkflow.originalIndex];
      if (workflow) {
        newWorkflows[selectedWorkflow.originalIndex] = {
          ...workflow,
          [field]: value,
          isModified: true
        };
        if (field === 'name' && editMode !== 'gui') {
          setGuiWorkflow({ ...guiWorkflow, name: value });
        }
      }
      return newWorkflows;
    });
    markWorkflowAsModified(selectedWorkflow.originalIndex, 'reusable');
  } else if (selectedWorkflow.type === 'linked') {
    if (setLinkedWorkflows && field === 'content') {
      setLinkedWorkflows((prev: any[]) => {
        const updated = [...prev];
        if (updated[selectedWorkflow.originalIndex]) {
          updated[selectedWorkflow.originalIndex] = {
            ...updated[selectedWorkflow.originalIndex],
            workflow_yaml: value,
            isModified: true,
          };
        }
        return updated;
      });
    }
  }
};
