import React, { useState, useEffect, useCallback } from "react";
import { getProjectDeletionSummary } from "../api/projectDeletion";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";

// TypeScript interfaces based on backend ProjectDeletionSummary
interface Workflow {
  name: string;
  is_reusable: boolean;
  created_at?: string;
  updated_at?: string;
}

interface Secret {
  name: string;
  repository: string;
  created_at?: string;
  updated_at?: string;
}

interface EnvironmentVariable {
  name: string;
  repository: string;
  environment: string;
  value?: string;
}

interface DeploymentEnvironment {
  name: string;
  repository: string;
  url?: string;
}

interface ProjectDeletionSummary {
  project_name: string;
  project_code: string;
  workflows: Workflow[];
  reusable_workflows: Workflow[];
  secrets: Secret[];
  environment_variables: EnvironmentVariable[];
  deployment_environments: DeploymentEnvironment[];
}

interface DeleteProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmDelete: (deleteGitHubResources: boolean, deleteDeploymentEnvironments: boolean) => void;
  projectName: string;
  githubUser: string;
}

const DeleteProjectModal: React.FC<DeleteProjectModalProps> = ({ 
  isOpen, 
  onClose, 
  onConfirmDelete,
  projectName, 
  githubUser 
}) => {
  const [summary, setSummary] = useState<ProjectDeletionSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteGitHubResources, setDeleteGitHubResources] = useState<boolean>(false);
  const [keepDeploymentEnvironments, setKeepDeploymentEnvironments] = useState<boolean>(false);

  const fetchDeletionSummary = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      console.log(`🔍 Fetching deletion summary for project: ${projectName}, user: ${githubUser}`);
      const summaryData = await getProjectDeletionSummary(githubUser, projectName);
      console.log("📊 Deletion summary received:", summaryData);
      console.log("📊 Resource counts:", {
        workflows: summaryData.workflows?.length || 0,
        reusable_workflows: summaryData.reusable_workflows?.length || 0,
        secrets: summaryData.secrets?.length || 0,
        environment_variables: summaryData.environment_variables?.length || 0,
        deployment_environments: summaryData.deployment_environments?.length || 0
      });
      
      // Log individual resources for debugging
      if (summaryData.secrets?.length > 0) {
        console.log("🔑 Found secrets:", summaryData.secrets.map((s: Secret) => s.name));
      }
      if (summaryData.environment_variables?.length > 0) {
        console.log("🔧 Found environment variables:", summaryData.environment_variables.map((v: EnvironmentVariable) => v.name));
      }
      if (summaryData.deployment_environments?.length > 0) {
        console.log("🌐 Found deployment environments:", summaryData.deployment_environments.map((e: DeploymentEnvironment) => e.name));
      }
      
      setSummary(summaryData);
    } catch (err) {
      const errorMsg = "Failed to load project deletion summary. You can still delete the project from the database only.";
      setError(errorMsg);
      console.error("❌ Error fetching deletion summary:", err);
      console.error("❌ Error response:", (err as any).response?.data);
      console.error("❌ Error status:", (err as any).response?.status);
      console.error("❌ Full error object:", err);
    } finally {
      setLoading(false);
    }
  }, [projectName, githubUser]);

  useEffect(() => {
    if (isOpen && projectName && githubUser) {
      fetchDeletionSummary();
    }
  }, [isOpen, projectName, githubUser, fetchDeletionSummary]);

  const handleDeleteConfirm = (): void => {
    // keepDeploymentEnvironments is the user-facing "keep" checkbox; the API takes a
    // "delete" flag, so the polarity is inverted here.
    onConfirmDelete(deleteGitHubResources, !keepDeploymentEnvironments);
  };

  const resetState = (): void => {
    setSummary(null);
    setError(null);
    setDeleteGitHubResources(false);
    setKeepDeploymentEnvironments(false);
  };

  const handleClose = (): void => {
    resetState();
    onClose();
  };

  const totalGitHubResources = summary ? 
    summary.workflows.length + 
    summary.reusable_workflows.length + 
    summary.secrets.length + 
    summary.environment_variables.length + 
    summary.deployment_environments.length : 0;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-red-600 dark:text-red-400">
            🗑️ Delete Project: {projectName}
          </DialogTitle>
          <DialogDescription className="sr-only">
            Review and confirm project deletion with options to delete database only or include GitHub resources
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {loading && (
            <div className="text-center py-10">
              <p className="text-lg text-slate-600 dark:text-slate-400">
                🔍 Analyzing project resources...
              </p>
            </div>
          )}

          {error && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-5 dark:bg-amber-950 dark:border-amber-800">
              <p className="text-amber-800 font-medium dark:text-amber-200">
                ⚠️ {error}
              </p>
            </div>
          )}

          {summary && (
            <div className="space-y-6">
              <div className="bg-slate-50 border-l-4 border-blue-500 rounded-lg p-4 dark:bg-slate-800 dark:border-blue-400">
                <h3 className="text-blue-600 text-lg font-semibold mb-2 dark:text-blue-400">
                  📊 Deletion Summary
                </h3>
                <p className="text-slate-700 leading-relaxed dark:text-slate-300">
                  This project <strong>"{summary.project_name}"</strong> (Code: <code className="bg-slate-200 px-2 py-0.5 rounded font-mono text-sm text-pink-600 font-semibold dark:bg-slate-700 dark:text-pink-400">{summary.project_code}</code>) 
                  contains the following GitHub resources that can be deleted:
                </p>
                <div className="bg-cyan-50 border border-cyan-200 rounded-md p-3 mt-3 dark:bg-cyan-950 dark:border-cyan-800">
                  <p className="text-cyan-800 text-sm font-medium dark:text-cyan-200">
                    ℹ️ <strong>Note:</strong> Repositories themselves are never deleted - only specific resources within them (workflows, secrets, environments).
                  </p>
                </div>
              </div>

              <div className="space-y-5">
                <div>
                  <h4 className="text-base font-semibold text-slate-900 pb-1 border-b border-slate-200 mb-2 dark:text-slate-100 dark:border-slate-700">
                    ⚙️ Workflows ({summary.workflows.length})
                  </h4>
                  {summary.workflows.length > 0 ? (
                    <ul className="space-y-1">
                      {summary.workflows.map((workflow, index) => (
                        <li key={index} className="bg-white border border-slate-200 rounded-md p-2 px-3 flex items-center justify-between text-slate-800 font-medium hover:bg-slate-50 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-600">
                          🔧 {workflow.name}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic text-center bg-slate-50 p-3 rounded-md dark:bg-slate-800 dark:text-slate-400">
                      No regular workflows in this project.
                    </p>
                  )}
                </div>

                <div>
                  <h4 className="text-base font-semibold text-slate-900 pb-1 border-b border-slate-200 mb-2 dark:text-slate-100 dark:border-slate-700">
                    🔄 Reusable Workflows ({summary.reusable_workflows.length})
                  </h4>
                  {summary.reusable_workflows.length > 0 ? (
                    <ul className="space-y-1">
                      {summary.reusable_workflows.map((workflow, index) => (
                        <li key={index} className="bg-white border border-slate-200 rounded-md p-2 px-3 flex items-center justify-between text-slate-800 font-medium hover:bg-slate-50 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-600">
                          🔁 {workflow.name}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic text-center bg-slate-50 p-3 rounded-md dark:bg-slate-800 dark:text-slate-400">
                      No reusable workflows in this project.
                    </p>
                  )}
                </div>

                <div>
                  <h4 className="text-base font-semibold text-slate-900 pb-1 border-b border-slate-200 mb-2 dark:text-slate-100 dark:border-slate-700">
                    🔐 GitHub Secrets ({summary.secrets.length})
                  </h4>
                  {summary.secrets.length > 0 ? (
                    <ul className="space-y-1">
                      {summary.secrets.map((secret, index) => (
                        <li key={index} className="bg-white border border-slate-200 rounded-md p-2 px-3 flex items-center justify-between text-slate-800 font-medium hover:bg-slate-50 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-600">
                          <span>🔑 {secret.name}</span>
                          <span className="bg-slate-600 text-white px-2 py-0.5 rounded-full text-xs font-medium">
                            in {secret.repository}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic text-center bg-slate-50 p-3 rounded-md dark:bg-slate-800 dark:text-slate-400">
                      No GitHub secrets found for this project.
                    </p>
                  )}
                </div>

                <div>
                  <h4 className="text-base font-semibold text-slate-900 pb-1 border-b border-slate-200 mb-2 dark:text-slate-100 dark:border-slate-700">
                    🌍 Environment Variables ({summary.environment_variables.length})
                  </h4>
                  {summary.environment_variables.length > 0 ? (
                    <ul className="space-y-1">
                      {summary.environment_variables.map((envVar, index) => (
                        <li key={index} className="bg-white border border-slate-200 rounded-md p-2 px-3 flex items-center justify-between text-slate-800 font-medium hover:bg-slate-50 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-600">
                          <span>🔧 {envVar.name}</span>
                          <span className="bg-slate-600 text-white px-2 py-0.5 rounded-full text-xs font-medium">
                            in {envVar.repository}/{envVar.environment}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic text-center bg-slate-50 p-3 rounded-md dark:bg-slate-800 dark:text-slate-400">
                      No environment variables found for this project.
                    </p>
                  )}
                </div>

                <div>
                  <h4 className="text-base font-semibold text-slate-900 pb-1 border-b border-slate-200 mb-2 dark:text-slate-100 dark:border-slate-700">
                    🚀 Deployment Environments ({summary.deployment_environments.length})
                  </h4>
                  {summary.deployment_environments.length > 0 ? (
                    <ul className="space-y-1">
                      {summary.deployment_environments.map((env, index) => (
                        <li key={index} className="bg-white border border-slate-200 rounded-md p-2 px-3 flex items-center justify-between text-slate-800 font-medium hover:bg-slate-50 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-600">
                          <span>🌐 {env.name}</span>
                          <span className="bg-slate-600 text-white px-2 py-0.5 rounded-full text-xs font-medium">
                            in {env.repository}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 italic text-center bg-slate-50 p-3 rounded-md dark:bg-slate-800 dark:text-slate-400">
                      No deployment environments found for this project.
                    </p>
                  )}
                </div>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-lg p-5 space-y-4 dark:bg-slate-800 dark:border-slate-700">
                <h3 className="text-red-600 text-lg font-semibold dark:text-red-400">
                  🎯 Deletion Options
                </h3>
                
                <div className="border-2 border-slate-200 rounded-lg transition-all hover:border-blue-500 dark:border-slate-600 dark:hover:border-blue-400">
                  <label className="flex items-start p-4 cursor-pointer" aria-label="Database Only">
                    <input
                      type="radio"
                      name="deletionType"
                      checked={!deleteGitHubResources}
                      onChange={() => setDeleteGitHubResources(false)}
                      className="mt-1 mr-3 flex-shrink-0"
                    />
                    <div className="flex-1">
                      <strong className="block text-base text-slate-900 mb-1 dark:text-slate-100">
                        🏠 Database Only
                      </strong>
                      <p className="text-slate-600 text-sm leading-relaxed dark:text-slate-400">
                        Remove the project from ActionsManager database only. All GitHub resources (workflows, secrets, environments) will remain untouched in your repositories.
                      </p>
                    </div>
                  </label>
                </div>

                <div className={`border-2 rounded-lg transition-all ${totalGitHubResources === 0 ? 'opacity-60 cursor-not-allowed border-slate-200 dark:border-slate-600' : 'border-slate-200 hover:border-blue-500 dark:border-slate-600 dark:hover:border-blue-400'}`}>
                  <label className={`flex items-start p-4 ${totalGitHubResources === 0 ? 'cursor-not-allowed' : 'cursor-pointer'}`}>
                    <input
                      type="radio"
                      name="deletionType"
                      checked={deleteGitHubResources}
                      onChange={() => setDeleteGitHubResources(true)}
                      disabled={totalGitHubResources === 0}
                      className="mt-1 mr-3 flex-shrink-0"
                    />
                    <div className="flex-1">
                      <strong className="block text-base text-slate-900 mb-1 dark:text-slate-100">
                        💥 Everything (Database + GitHub Resources)
                      </strong>
                      <p className="text-slate-600 text-sm leading-relaxed dark:text-slate-400">
                        Remove the project from database AND delete {totalGitHubResources - (keepDeploymentEnvironments ? summary.deployment_environments.length : 0)} GitHub resources from your repositories (workflows, secrets, environments, environment variables).
                        {totalGitHubResources === 0 && " (No GitHub resources to delete)"}
                      </p>
                      {deleteGitHubResources && summary.deployment_environments.length > 0 && (
                        <label className="flex items-center mt-3 text-sm text-slate-700 dark:text-slate-300">
                          <input
                            type="checkbox"
                            checked={keepDeploymentEnvironments}
                            onChange={(e) => setKeepDeploymentEnvironments(e.target.checked)}
                            className="mr-2"
                          />{' '}
                          Keep deployment environments (don't delete them from GitHub)
                        </label>
                      )}
                      {deleteGitHubResources && totalGitHubResources > 0 && (
                        <div className="bg-amber-50 border border-amber-200 rounded-md p-3 mt-3 dark:bg-amber-950 dark:border-amber-800">
                          <p className="text-amber-800 text-sm dark:text-amber-200">
                            ⚠️ <strong>Warning:</strong> This action cannot be undone! GitHub resources will be permanently deleted from your repositories.
                          </p>
                        </div>
                      )}
                    </div>
                  </label>
                </div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="bg-slate-50 rounded-b-lg dark:bg-slate-800">
          <div className="flex justify-end gap-3 w-full">
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button 
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={loading}
              className="min-w-[160px]"
            >
              {deleteGitHubResources ? "🗑️ Delete Everything" : "🗑️ Delete Project Only"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DeleteProjectModal;
