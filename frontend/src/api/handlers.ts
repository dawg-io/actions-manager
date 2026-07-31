import React from "react";
import { updateWorkflows } from "./workflows";
import { createSecrets } from "./secrets";
import { updateEnvVars } from "./envVars";
import { createEnvironment } from "./environments";
import { saveProject, fetchProjects, loadProject, Project } from "./projects";
import { WorkflowUpdateResponse } from "../types/workflowResponse";
import type { ProjectColorKey } from "../utils/projectColors";
import { toast } from "../utils/toast";

// ===== Type Definitions =====

export interface Repository {
  full_name?: string;
  name: string;
}

export interface Workflow {
  name: string;
  content: string;
  isModified?: boolean;
}

export interface Secret {
  env_key?: string;
  key?: string;
  value?: string;
  repo?: string;
}

export interface DeploymentEnvironment {
  name: string;
  protection_rules?: any[];
  deployment_branch_policy?: any;
}

export interface EnvironmentVariable {
  env_key?: string;
  key?: string;
  value?: string;
  repo?: string;
}

// Export Project type from projects.ts for consistency
export type { Project };

export interface SaveProjectPayload {
  github_user: string;
  project_name: string;
  custom_project_key?: string | null;
  selected_repos: string[];
  workflows: Workflow[];
  rxworkflows: Workflow[];
  branch_regex: string;
  branch_option: string;
  branch_max_age_days: number;
  project_id?: string | number | null;
  reusable_workflows_enabled: boolean;
  use_prefix: boolean;
  repository_visibility_scope?: "public" | "private";
  project_color?: ProjectColorKey | null;
  validation_repo?: string | null;
  preflight_required?: boolean;
}

export interface SaveProjectResponse {
  project_code: string;
  project_id: string;
  pr_state?: string;
}

export interface SaveProjectResult {
  success: boolean;
  error?: string;
  projectId?: string;
  projectCode?: string;
  message?: string;
  prState?: string;
}

export interface SelectedItems {
  workflows?: boolean;
  rxworkflows?: boolean;
  secrets?: boolean;
  envVars?: boolean;
  deploymentEnvironments?: boolean;
}

export interface UpdateFlags {
  updateAll: boolean;
  shouldUpdateWorkflows: boolean;
  shouldUpdateSecrets: boolean;
  shouldUpdateEnvVars: boolean;
  shouldUpdateDeploymentEnvironments: boolean;
}

export interface UpdateConfig {
  updateAll: boolean;
  regexPattern: string;
  branchOption: string;
  projectName: string;
}

export interface GitHubUpdateConfig {
  user: string;
  selectedRepos: (Repository | string)[];
  workflows: Workflow[];
  rxworkflows: Workflow[];
  envVars: EnvironmentVariable[];
  manualEnvVars: EnvironmentVariable[];
  regexPattern: string;
  branchOption: string;
  branchMaxAgeDays: number;
  secrets: Secret[];
  manualSecrets: Secret[];
  projectName: string;
  setIsCreatingProject: SetIsCreatingProjectFunction | null;
  setProjects: SetProjectsFunction | null;
  projectId: string | number | null;
  selectedItems: SelectedItems | null;
  deploymentEnvironments: (string | DeploymentEnvironment)[];
  reusableWorkflowsEnabled: boolean;
  onProgress: ProgressCallback | null;
  usePrefix?: boolean;
  repositoryVisibilityScope?: "public" | "private";
  projectColor?: ProjectColorKey | null;
  validationRepo?: string | null;
  preflightRequired?: boolean;
}

export interface UpdateResult {
  success: boolean;
  results: string[];
  githubUpdatePerformed?: boolean;
  projectId?: string;
  projectCode?: string;
  prState?: string;
}

export interface SaveProjectWithModalParams {
  user: string;
  projectName: string;
  selectedRepos: (Repository | string)[];
  workflows: Workflow[];
  rxworkflows: Workflow[];
  envVars: EnvironmentVariable[];
  manualEnvVars: EnvironmentVariable[];
  secrets: Secret[];
  manualSecrets: Secret[];
  deploymentEnvironments: (string | DeploymentEnvironment)[];
  branchRegex: string;
  branchOption: string;
  branchMaxAgeDays: number;
  projectId: string | number | null;
  selectedItems: SelectedItems | null;
  updateGitHub?: boolean;
  reusableWorkflowsEnabled?: boolean;
  onProgress?: ProgressCallback | null;
  projectKey?: string | null;
  usePrefix?: boolean;
  repositoryVisibilityScope?: "public" | "private";
  projectColor?: ProjectColorKey | null;
  validationRepo?: string | null;
  preflightRequired?: boolean;
}

export interface HandleUpdateGitHubParams {
  user: string;
  selectedRepos: (Repository | string)[];
  workflows: Workflow[];
  rxworkflows: Workflow[];
  envVars: EnvironmentVariable[];
  manualEnvVars: EnvironmentVariable[];
  regexPattern: string;
  branchOption: string;
  branchMaxAgeDays: number;
  secrets: Secret[];
  manualSecrets: Secret[];
  projectName: string;
  setIsCreatingProject: SetIsCreatingProjectFunction | null;
  setProjects: SetProjectsFunction | null;
  projectId: string | number | null;
  selectedItems?: SelectedItems | null;
  deploymentEnvironments?: (string | DeploymentEnvironment)[];
  reusableWorkflowsEnabled?: boolean;
  onProgress?: ProgressCallback | null;
  skipProjectSave?: boolean;
  usePrefix?: boolean;
  repositoryVisibilityScope?: "public" | "private";
  projectColor?: ProjectColorKey | null;
}

export interface ProgressCallback {
  (percentage: number, message: string): void;
}

export type SetProjectsFunction = React.Dispatch<React.SetStateAction<Project[]>>;
export type SetIsCreatingProjectFunction = React.Dispatch<React.SetStateAction<boolean>>;

// ===== Main Functions =====

// ✅ ================================= ✅ handleSaveProject ✅ ================================= ✅
export const handleSaveProject = async (
    user: string,
    projectName: string,
    selectedRepos: (Repository | string)[],
    workflows: Workflow[],
    rxworkflows: Workflow[],
    setIsCreatingProject: SetIsCreatingProjectFunction | null,
    setProjects: SetProjectsFunction | null,
    branchRegex: string,
    branchOption: string,
    branchMaxAgeDays: number,
    projectId: string | number | null,
    stayOnProject: boolean = false,
    selectedItems: SelectedItems | null = null,
    reusableWorkflowsEnabled: boolean = false,
    projectKey: string | null = null,
    usePrefix: boolean = false,
    projectColor?: ProjectColorKey | null,
    repositoryVisibilityScope?: "public" | "private",
    validationRepo?: string | null,
    preflightRequired?: boolean
): Promise<SaveProjectResult> => {
    console.log("📌 handleSaveProject projectId:", projectId);
    if (!projectName || typeof projectName !== "string" || projectName.trim() === "") {
      return { success: false, error: "Enter a valid project name." };
    }   
    if (selectedRepos.length === 0) {
        return { success: false, error: "Please select at least one repository." };
    }   
    // Note: Workflows are no longer required - users can create projects without workflows
    // and add them later (addresses issue #381)   

    // Filter workflows based on selected items
    const workflowsToSave = (selectedItems && !selectedItems.workflows) ? [] : workflows;
    const rxworkflowsToSave = (selectedItems && !selectedItems.rxworkflows) ? [] : rxworkflows;

    // Filter out empty workflows (workflows with no name or content) to send clean arrays
    // ✅ FIX: Add null/undefined checks before calling trim() to prevent TypeError
    const formattedWorkflows = workflowsToSave
        .filter(w => w.name?.trim() || w.content?.trim()) // Only include workflows with name or content
        .map(w => ({
            name: (w.name || "").trim(),
            content: (w.content || "").trim(),
        }));    
    const formattedRXWorkflows = rxworkflowsToSave
        .filter(w => w.name?.trim() || w.content?.trim()) // Only include workflows with name or content
        .map(w => ({
            name: (w.name || "").trim(),
            content: (w.content || "").trim(),
        }));    
    const formattedRepos = selectedRepos.map(repo => {
        if (typeof repo === "string") return repo;
        return repo.full_name || repo.name;
    });  

    // ✅ Fix `project_name` instead of `name`
    const payload: SaveProjectPayload = {
        github_user: user,
        project_name: projectName.trim(),
        custom_project_key: projectKey,
        selected_repos: formattedRepos,
        workflows: formattedWorkflows,
        rxworkflows: formattedRXWorkflows,
        branch_regex: branchRegex.trim(),
        branch_option: branchOption.trim(),
        branch_max_age_days: branchMaxAgeDays,
        project_id: projectId,
        reusable_workflows_enabled: reusableWorkflowsEnabled,
        use_prefix: usePrefix,
        repository_visibility_scope: repositoryVisibilityScope,
        validation_repo: validationRepo,
        preflight_required: preflightRequired,
        ...(projectColor !== undefined ? { project_color: projectColor } : {}),
    };  

    console.log("📌 Debugging Payload:", payload);

    try {
        const response: SaveProjectResponse = await saveProject(payload);

        if (!response?.project_code) {
            throw new Error("Unexpected API response, missing project_code.");
        }
        if (!response?.project_id) {
            throw new Error("Unexpected API response, missing project_id.");
        }
        const projectCode = response.project_code ? response.project_code : "N/A"; 

        if (!stayOnProject && setIsCreatingProject) {
            setIsCreatingProject(false);
        }

        if (setProjects && typeof setProjects === 'function') {
            setProjects((prevProjects: Project[]) => [
                { 
                  id: new Date().getTime(), 
                  name: projectName,
                  project_code: projectCode,
                  updated_at: new Date().toISOString() 
                }, 
                ...prevProjects
            ]);

            fetchProjects(user).then(setProjects);
        }

        // Return success result with project details
        return {
            success: true,
            projectId: response.project_id,
            projectCode: projectCode,
            prState: response.pr_state,
            message: "Project saved successfully"
        };

    } catch (error) {
        console.error("❌ Error saving project:", error);
        return {
            success: false,
            error: (error as Error).message || "Failed to save project"
        };
    }
};

// Helper function for handleSaveProjectWithModal: performs the optional
// GitHub-sync step and reports progress, isolated so the caller's own
// cognitive complexity doesn't also account for this branching.
const applyGithubUpdateIfRequested = async (
    results: string[],
    params: SaveProjectWithModalParams
): Promise<void> => {
    const { onProgress = null, updateGitHub } = params;

    if (!updateGitHub) {
        if (onProgress) onProgress(100, "Save completed successfully!");
        return;
    }

    if (onProgress) onProgress(50, "Updating GitHub repositories...");

    const githubResult = await handleUpdateGitHub({
        user: params.user,
        selectedRepos: params.selectedRepos,
        workflows: params.workflows,
        rxworkflows: params.rxworkflows,
        envVars: params.envVars,
        manualEnvVars: params.manualEnvVars,
        regexPattern: params.branchRegex,
        branchOption: params.branchOption,
        branchMaxAgeDays: params.branchMaxAgeDays,
        secrets: params.secrets,
        manualSecrets: params.manualSecrets,
        projectName: params.projectName,
        setIsCreatingProject: null,
        setProjects: null,
        projectId: params.projectId,
        selectedItems: params.selectedItems,
        deploymentEnvironments: params.deploymentEnvironments,
        reusableWorkflowsEnabled: params.reusableWorkflowsEnabled,
        onProgress,
        repositoryVisibilityScope: params.repositoryVisibilityScope,
        skipProjectSave: true // project already saved above
    });

    if (githubResult.success && githubResult?.results) {
        results.push(...githubResult.results);
    } else if (!githubResult.success) {
        results.push("❌ GitHub update failed");
    }

    if (onProgress) onProgress(100, "Save completed successfully!");
};

// ✅ ================================= ✅ handleSaveProjectWithModal ✅ ================================= ✅
export const handleSaveProjectWithModal = async (
    params: SaveProjectWithModalParams
): Promise<UpdateResult> => {
    try {
        // Destructure parameters from interface
        const {
            user,
            projectName,
            selectedRepos,
            workflows,
            rxworkflows,
            branchRegex,
            branchOption,
            branchMaxAgeDays,
            projectId,
            selectedItems,
            updateGitHub = false,
            reusableWorkflowsEnabled = false,
            onProgress = null,
            projectKey = null,
            usePrefix = false,
            repositoryVisibilityScope,
            projectColor,
            validationRepo,
            preflightRequired
        } = params;

        // First, save the project
        if (onProgress) onProgress(20, "Saving project to database...");
        
        const saveResult = await handleSaveProject(
            user,
            projectName,
            selectedRepos,
            workflows,
            rxworkflows,
            null, // setIsCreatingProject - not needed here
            null, // setProjects - not needed here
            branchRegex,
            branchOption,
            branchMaxAgeDays,
            projectId,
            true, // stayOnProject
            selectedItems,
            reusableWorkflowsEnabled,
            projectKey, // Pass through custom project key
            usePrefix ?? false, // Use the provided usePrefix or default to false
            projectColor,
            repositoryVisibilityScope,
            validationRepo,
            preflightRequired
        );

        if (!saveResult?.success) {
            throw new Error(saveResult?.error || "Failed to save project");
        }

        const results = ["✅ Project saved to database successfully"];

        if (onProgress) onProgress(40, "Project saved to database");

        // If GitHub update is requested, perform it
        await applyGithubUpdateIfRequested(results, params);

        return {
            success: true,
            results: results,
            githubUpdatePerformed: updateGitHub,
            projectId: saveResult.projectId,
            projectCode: saveResult.projectCode,
            prState: saveResult.prState
        };

    } catch (error) {
        console.error("❌ Error in handleSaveProjectWithModal:", error);
        return {
            success: false,
            results: [`❌ Save failed: ${(error as Error).message}`],
            githubUpdatePerformed: false
        };
    }
};

// ✅ ================================= ✅ Helper Functions for handleUpdateGitHub ✅ ================================= ✅

// Helper function to validate inputs for GitHub update
const validateUpdateInputs = (selectedRepos: (Repository | string)[], selectedItems: SelectedItems | null): boolean => {
  if (selectedRepos.length === 0) {
    toast.error("Please select at least one repository.");
    return false;
  }

  // When selectedItems is provided, validate that at least one item is selected
  if (selectedItems && !Object.values(selectedItems).some(Boolean)) {
    toast.error("Please select at least one item to update.");
    return false;
  }

  return true;
};

// Helper function to determine what should be updated
const getUpdateFlags = (selectedItems: SelectedItems | null): UpdateFlags => {
  const updateAll = !selectedItems;
  return {
    updateAll,
    shouldUpdateWorkflows: updateAll || selectedItems?.workflows || selectedItems?.rxworkflows || false,
    shouldUpdateSecrets: updateAll || selectedItems?.secrets || false,
    shouldUpdateEnvVars: updateAll || selectedItems?.envVars || false,
    shouldUpdateDeploymentEnvironments: updateAll || selectedItems?.deploymentEnvironments || false
  };
};

// Helper function to handle secrets update
const handleSecretsUpdate = async (
  shouldUpdateSecrets: boolean, 
  secrets: Secret[], 
  manualSecrets: Secret[], 
  user: string, 
  selectedRepos: (Repository | string)[], 
  projectName: string
): Promise<string[]> => {
  const results: string[] = [];
  
  if (shouldUpdateSecrets) {
    // Filter out empty manual secrets (those without key or value)
    const validManualSecrets = manualSecrets.filter(secret => {
      // Check all possible property names used across the codebase
      const secretKey = (secret as any).secret_key || (secret as any).name || secret.key || secret.env_key;
      const secretValue = (secret as any).secret_value || secret.value;
      return secretKey && secretValue && secretValue.trim() !== "";
    });

    // Only proceed with update if there are new manual secrets
    if (validManualSecrets.length === 0) {
      console.log("📌 Debug: No new secrets to update, skipping GitHub API call");
      results.push("✅ No secret changes");
      return results;
    }

    console.log("📌 Debug: Merging manually added secrets with GitHub secrets...");

    const allSecrets = [...secrets, ...validManualSecrets];
    console.log("📌 Debug: Final Secrets List:", allSecrets);

    if (allSecrets.length > 0) {
      const secretResponse = await createSecrets(user, selectedRepos, allSecrets, projectName);
      
      if (secretResponse?.error) {
        console.error("❌ Error saving secrets:", secretResponse.error);
        results.push("❌ Secrets update failed");
      } else {
        console.log("✅ Secrets saved successfully:", secretResponse);
        results.push("✅ Secrets updated successfully");
      }
    }
  }
  
  return results;
};

// Helper function to strip project prefix from environment variable key
const stripProjectPrefix = (envKey: string, projectCode: string | null): string => {
  if (!projectCode || !envKey) return envKey;
  
  const prefix = `AM_${projectCode.toUpperCase()}_`;
  if (envKey.startsWith(prefix)) {
    return envKey.substring(prefix.length);
  }
  return envKey;
};

// Helper function to fetch project code if not provided
const fetchProjectCodeIfNeeded = async (user: string, projectName: string, projectCode: string | null): Promise<string | null> => {
  if (projectCode) return projectCode;
  
  try {
    const projectData = await loadProject(user, projectName);
    if (projectData) {
      return projectData.project_code;
    }
  } catch (error) {
    console.warn("⚠️ Could not fetch project code for env var prefix stripping:", error);
  }
  return null;
};

// Helper function to format environment variables
const formatEnvironmentVariables = (allEnvVars: EnvironmentVariable[], projectCode: string | null): Array<{key: string, value: string}> => {
  return allEnvVars
    .filter(env => env.env_key || env.key)
    .map(env => {
      const rawKey = (env.env_key || env.key || "").toUpperCase();
      const cleanKey = stripProjectPrefix(rawKey, projectCode);
      
      console.log(`📌 Debug: Env var key transformation: '${rawKey}' -> '${cleanKey}' (project: ${projectCode})`);
      
      return {
        key: cleanKey,
        value: env.value || "N/A"
      };
    });
};

// Helper function to send environment variables to GitHub
const sendEnvironmentVariablesToGitHub = async (
  user: string, 
  selectedRepos: (Repository | string)[], 
  formattedEnvVars: Array<{key: string, value: string}>, 
  projectName: string
): Promise<string[]> => {
  if (formattedEnvVars.length === 0) {
    return [];
  }

  const envVarResponse = await updateEnvVars(user, selectedRepos, formattedEnvVars, projectName);
  console.log("📌 Debug: GitHub API Response for Env Vars:", envVarResponse);

  if (envVarResponse?.error) {
    console.error(`❌ Error updating env vars:`, envVarResponse.error);
    return ["❌ Environment variables update failed"];
  } else {
    console.log(`✅ Environment variables updated in GitHub`);
    return ["✅ Environment variables updated successfully"];
  }
};

// Helper function to handle environment variables update
const handleEnvVarsUpdate = async (
  shouldUpdateEnvVars: boolean, 
  envVars: EnvironmentVariable[], 
  manualEnvVars: EnvironmentVariable[], 
  user: string, 
  selectedRepos: (Repository | string)[], 
  projectName: string, 
  projectCode: string | null = null
): Promise<string[]> => {
  const results: string[] = [];
  
  if (shouldUpdateEnvVars) {
    // Filter out empty manual environment variables (those without key or value)
    const validManualEnvVars = manualEnvVars.filter(env => 
      (env.env_key || env.key) && env.value && env.value.trim() !== ""
    );

    // Only proceed with update if there are new manual environment variables
    if (validManualEnvVars.length === 0) {
      console.log("📌 Debug: No new environment variables to update, skipping GitHub API call");
      results.push("✅ No environment variable changes");
      return results;
    }

    console.log("📌 Debug: Formatting and sending environment variables to GitHub...");
    const allEnvVars = [...envVars, ...validManualEnvVars];

    // Fetch project code if not provided
    const resolvedProjectCode = await fetchProjectCodeIfNeeded(user, projectName, projectCode);

    // Format environment variables
    const formattedEnvVars = formatEnvironmentVariables(allEnvVars, resolvedProjectCode);
    console.log("📌 Debug: Final Env Vars to be sent:", formattedEnvVars);

    // Send to GitHub
    const envResults = await sendEnvironmentVariablesToGitHub(user, selectedRepos, formattedEnvVars, projectName);
    results.push(...envResults);
  }
  
  return results;
};

// Helper function to handle deployment environments update
const handleDeploymentEnvironmentsUpdate = async (
  shouldUpdateDeploymentEnvironments: boolean, 
  deploymentEnvironments: (string | DeploymentEnvironment)[], 
  user: string, 
  selectedRepos: (Repository | string)[]
): Promise<string[]> => {
  const results: string[] = [];
  
  if (shouldUpdateDeploymentEnvironments && deploymentEnvironments && deploymentEnvironments.length > 0) {
    console.log("📌 Debug: Updating deployment environments...");
    
    try {
      const environmentResults: string[] = [];
      
      for (const environment of deploymentEnvironments) {
        const environmentName = typeof environment === "string" ? environment : environment.name;
        for (const repo of selectedRepos) {
          try {
            const repoName = typeof repo === "string" ? repo : (repo.full_name || repo.name);
            const response = await createEnvironment(user, repoName, environmentName);
            
            // Check if environment was created or already existed
            if (response && response.created === false) {
              environmentResults.push(`ℹ️ Environment '${environmentName}' already exists in ${repoName} - no changes made`);
            } else {
              environmentResults.push(`✅ Environment '${environmentName}' created in ${repoName}`);
            }
          } catch (error) {
            const repoName = typeof repo === "string" ? repo : (repo.full_name || repo.name);
            console.error(`❌ Error creating environment '${environmentName}' in ${repoName}:`, error);
            environmentResults.push(`❌ Failed to update environment '${environmentName}' in ${repoName}`);
          }
        }
      }
      
      if (environmentResults.length > 0) {
        results.push(...environmentResults);
      }
    } catch (error) {
      console.error("❌ Error updating deployment environments:", error);
      results.push("❌ Deployment environments update failed");
    }
  }
  
  return results;
};

// Helper function to process workflow results
const processWorkflowResults = (response: WorkflowUpdateResponse | null): string[] => {
  const results: string[] = [];
  
  // Handle null or undefined response
  if (!response) {
    results.push("❌ Workflow update failed: No response from server");
    return results;
  }

  console.log("📌 Debug: Workflow Update Response:", response);
  
  // Handle error responses from backend
  if (response.error) {
    const errorMessage = response.error || "Unknown error occurred";
    results.push(`❌ Workflow update failed: ${errorMessage}`);
    return results;
  }
  
  // Handle missing results property
  if (!response.results) {
    results.push("❌ Workflow update failed: Invalid response format");
    return results;
  }
  
  // Process each repo/branch combination result
  Object.entries(response.results).forEach(([repoBranch, result]) => {
    // Handle legacy numeric status codes for backward compatibility
    if (typeof result === 'number') {
      if (result === 200 || result === 201 || result === 204) {
        results.push(`✅ Workflows committed to: ${repoBranch}`);
      } else {
        results.push(`❌ Workflow update failed in: ${repoBranch} (Error ${result})`);
      }
      return;
    }

    // Handle new PR-based response format
    const { status, pr_url, pr_number, workflows_committed, workflow_errors, error } = result;
    
    if (status === "pr_created") {
      const workflowsList = workflows_committed && workflows_committed.length > 0 
        ? ` (${workflows_committed.join(", ")})` 
        : "";
      results.push(`✅ Created PR #${pr_number} for ${repoBranch}${workflowsList}: ${pr_url}`);
      
      // Add any workflow-specific errors as warnings
      if (workflow_errors && workflow_errors.length > 0) {
        workflow_errors.forEach(err => {
          results.push(`⚠️ ${repoBranch}: ${err}`);
        });
      }
    } else if (status === "pr_updated") {
      const workflowsList = workflows_committed && workflows_committed.length > 0 
        ? ` (${workflows_committed.join(", ")})` 
        : "";
      results.push(`✅ Updated existing PR #${pr_number} for ${repoBranch}${workflowsList}: ${pr_url}`);
      
      // Add any workflow-specific errors as warnings
      if (workflow_errors && workflow_errors.length > 0) {
        workflow_errors.forEach(err => {
          results.push(`⚠️ ${repoBranch}: ${err}`);
        });
      }
    } else if (status === "error") {
      const errorMsg = error || "Unknown error";
      results.push(`❌ Failed to update ${repoBranch}: ${errorMsg}`);
      
      // Add any workflow-specific errors
      if (workflow_errors && workflow_errors.length > 0) {
        workflow_errors.forEach(err => {
          results.push(`❌ ${repoBranch}: ${err}`);
        });
      }
    } else {
      // Unknown status
      results.push(`⚠️ Unknown status for ${repoBranch}: ${status}`);
    }
  });
  
  return results;
};

// Helper function to handle project saving before GitHub updates
const handleProjectSaveForUpdate = async (config: GitHubUpdateConfig): Promise<SaveProjectResult | null> => {
  console.log("📌 Debug: Saving project before updating GitHub...");
  
  const projectResponse = await handleSaveProject(
    config.user,
    config.projectName,
    config.selectedRepos,
    config.workflows,
    config.rxworkflows,
    config.setIsCreatingProject,
    config.setProjects,
    config.regexPattern,
    config.branchOption,
    config.branchMaxAgeDays,
    config.projectId,
    true,
    null, // selectedItems
    config.reusableWorkflowsEnabled,
    null, // projectKey
    config.usePrefix ?? false, // Use the provided usePrefix or default to false
    config.projectColor,
    config.repositoryVisibilityScope
  );

  if (projectResponse?.error) {
    console.error("❌ Error saving project:", projectResponse.error);
  } else {
    console.log("✅ Project saved successfully:", projectResponse);
  }

  return projectResponse;
};

// Helper function to execute all GitHub updates in sequence
const executeGitHubUpdates = async (
  config: GitHubUpdateConfig, 
  updateFlags: UpdateFlags, 
  projectResponse: SaveProjectResult | null
): Promise<string[]> => {
  const updateResults: string[] = [];

  // Update secrets if selected
  if (config.onProgress) config.onProgress(60, "Updating secrets...");
  const secretResults = await handleSecretsUpdate(
    updateFlags.shouldUpdateSecrets, 
    config.secrets, 
    config.manualSecrets, 
    config.user, 
    config.selectedRepos, 
    config.projectName
  );
  updateResults.push(...secretResults);

  // Update environment variables if selected
  if (config.onProgress) config.onProgress(70, "Updating environment variables...");
  const envVarResults = await handleEnvVarsUpdate(
    updateFlags.shouldUpdateEnvVars, 
    config.envVars, 
    config.manualEnvVars, 
    config.user, 
    config.selectedRepos, 
    config.projectName,
    projectResponse?.projectCode // Pass project code if available
  );
  updateResults.push(...envVarResults);

  // Update deployment environments if selected
  if (config.onProgress) config.onProgress(80, "Updating deployment environments...");
  const environmentResults = await handleDeploymentEnvironmentsUpdate(
    updateFlags.shouldUpdateDeploymentEnvironments, 
    config.deploymentEnvironments, 
    config.user, 
    config.selectedRepos
  );
  updateResults.push(...environmentResults);

  // Update workflows if selected
  if (config.onProgress) config.onProgress(90, "Updating workflows...");
  const workflowResults = await handleWorkflowsUpdate(
    updateFlags.shouldUpdateWorkflows, 
    config.workflows, 
    config.rxworkflows, 
    config.selectedItems, 
    config.user, 
    config.selectedRepos, 
    {
      updateAll: updateFlags.updateAll,
      regexPattern: config.regexPattern,
      branchOption: config.branchOption,
      projectName: config.projectName
    }
  );
  updateResults.push(...workflowResults);

  return updateResults;
};

// Helper function to handle workflows update
const handleWorkflowsUpdate = async (
  shouldUpdateWorkflows: boolean, 
  workflows: Workflow[], 
  rxworkflows: Workflow[], 
  selectedItems: SelectedItems | null, 
  user: string, 
  selectedRepos: (Repository | string)[], 
  updateConfig: UpdateConfig
): Promise<string[]> => {
  const results: string[] = [];
  
  if (shouldUpdateWorkflows) {
    console.log("📌 Debug: Proceeding to workflow update...");

    const workflowsToUpdate: Workflow[] = [];
    const rxworkflowsToUpdate: Workflow[] = [];

    if (updateConfig.updateAll || selectedItems?.workflows) {
      // FIXED: Always filter to only include workflows that have been modified,
      // even when updateAll is true. This prevents blank commits.
      const modifiedWorkflows = workflows.filter(workflow => 
        workflow.isModified === true
      );
      workflowsToUpdate.push(...modifiedWorkflows);
      console.log(`📌 Debug: Filtered ${workflows.length} workflows down to ${modifiedWorkflows.length} modified workflows`);
      console.log(`📌 Debug: Modified workflow names: ${modifiedWorkflows.map(w => w.name).join(', ') || 'none'}`);
    }
    if (updateConfig.updateAll || selectedItems?.rxworkflows) {
      // FIXED: Always filter to only include reusable workflows that have been modified,
      // even when updateAll is true. This prevents blank commits.
      const modifiedRXWorkflows = rxworkflows.filter(workflow => 
        workflow.isModified === true
      );
      rxworkflowsToUpdate.push(...modifiedRXWorkflows);
      console.log(`📌 Debug: Filtered ${rxworkflows.length} reusable workflows down to ${modifiedRXWorkflows.length} modified workflows`);
      console.log(`📌 Debug: Modified RX workflow names: ${modifiedRXWorkflows.map(w => w.name).join(', ') || 'none'}`);
    }

    if (workflowsToUpdate.length > 0 || rxworkflowsToUpdate.length > 0) {
      console.log(`📌 Debug: Sending ${workflowsToUpdate.length} regular workflows and ${rxworkflowsToUpdate.length} reusable workflows to GitHub`);
      // Convert Repository objects to strings
      const repoNames = selectedRepos.map(repo => typeof repo === "string" ? repo : (repo.full_name || repo.name));
      const response = await updateWorkflows(user, repoNames, workflowsToUpdate, rxworkflowsToUpdate, updateConfig.regexPattern, updateConfig.branchOption, updateConfig.projectName); 
      const workflowResults = processWorkflowResults(response);
      results.push(...workflowResults);
    } else {
      console.log("📌 Debug: No modified workflows to update, skipping GitHub API call");
      results.push("✅ No workflow changes to commit");
    }
  }
  
  return results;
};

// ✅ ================================= ✅ handleUpdateGitHub ✅ ================================= ✅
export const handleUpdateGitHub = async (
  params: HandleUpdateGitHubParams
): Promise<UpdateResult> => {
  // Destructure parameters from interface
  const {
    user,
    selectedRepos,
    workflows,
    rxworkflows,
    envVars,
    manualEnvVars,
    regexPattern,
    branchOption,
    branchMaxAgeDays,
    secrets,
    manualSecrets,
    projectName,
    setIsCreatingProject,
    setProjects,
    projectId,
    selectedItems = null,
    deploymentEnvironments = [],
    reusableWorkflowsEnabled = false,
    onProgress = null,
    skipProjectSave = false,
    repositoryVisibilityScope
  } = params;

  // Create configuration object
  const config: GitHubUpdateConfig = {
    user, selectedRepos, workflows, rxworkflows, envVars, manualEnvVars,
    regexPattern, branchOption, branchMaxAgeDays, secrets, manualSecrets,
    projectName, setIsCreatingProject, setProjects, projectId, selectedItems,
    deploymentEnvironments, reusableWorkflowsEnabled, onProgress, repositoryVisibilityScope
  };

  // Validate inputs
  if (!validateUpdateInputs(config.selectedRepos, config.selectedItems)) {
    return {
      success: false,
      results: ["❌ Input validation failed"]
    };
  }

  // Determine what should be updated
  const updateFlags = getUpdateFlags(config.selectedItems);

  try {
    // Conditionally save project before updating GitHub
    let projectResponse: SaveProjectResult | null = null;
    if (skipProjectSave) {
      console.log("📌 Skipping project save - already saved previously");
      // Create a mock response with the project info we have
      projectResponse = {
        success: true,
        projectId: projectId?.toString() || "",
        projectCode: "", // Will be filled in by actual save
        message: "Project save skipped"
      };
    } else {
      projectResponse = await handleProjectSaveForUpdate(config);
    }
    
    // Execute all GitHub updates
    const updateResults = await executeGitHubUpdates(config, updateFlags, projectResponse);

    // Return consolidated results
    return {
      success: true,
      results: updateResults.length > 0 ? updateResults : ["✅ Update completed successfully!"]
    };

  } catch (error) {
    console.error("❌ Error updating GitHub:", error);
    return {
      success: false,
      results: [`❌ An error occurred while updating GitHub: ${(error as Error).message}`]
    };
  }
};
