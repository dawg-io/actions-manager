import { useCallback, useState } from 'react';
import { getWorkflowsCount } from '../api/workflows';
import { Workflow, RXWorkflow, DetectedBuildResult, BuildType, WorkflowTemplate } from '../types/workflow';
import { RwxWorkflow, unlinkReusableWorkflow } from '../api/projects';
import { saveDraftWorkflow, commitAndUpdatePRWorkflow, commitAndUpdatePRLinkedWorkflow, saveDraftLinkedWorkflow, deleteWorkflow, createBlankWorkflow } from '../utils/workflowOperations';
import { detectBuildTypesForRepos, addWorkflowFromDetection, generateTemplates, selectTemplate } from '../utils/buildDetectionUtils';
import { tour } from '../utils/tour';

export interface UseWorkflowOperationsProps {
  workflows: Workflow[];
  rxworkflows: RXWorkflow[];
  linkedWorkflows?: RwxWorkflow[];
  setLinkedWorkflows?: (updater: (prev: RwxWorkflow[]) => RwxWorkflow[]) => void;
  user: string;
  projectName: string;
  projectCode: string | null;
  selectedRepos: string[];
  regexPattern: string;
  accountType?: string;
  detectedBuildTypes: DetectedBuildResult[];
  setWorkflows: (workflows: Workflow[]) => void;
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void;
  setSelectedWorkflowId: (id: string | null) => void;
  markWorkflowAsSaved: (index: number, type: 'regular' | 'reusable', workflowStatus?: string) => void;
  setDetectedBuildTypes: (types: DetectedBuildResult[]) => void;
  setShowDetectionResults: (show: boolean) => void;
  setShowDetectionResultsInModal: (show: boolean) => void;
  setTemplatesByType: (templates: any) => void;
  setShowTemplateModal: (show: boolean) => void;
  setShowWorkflowCreationDialog: (show: boolean) => void;
  setWorkflowCreationType: (type: 'regular' | 'reusable' | null) => void;
  setEditingWorkflowIndex: (index: number | null) => void;
  setEditingWorkflowType: (type: 'regular' | 'reusable' | null) => void;
  setWorkflowsCount: (count: number | null) => void;
  setIsDetecting: (detecting: boolean) => void;
  setIsGeneratingTemplates: (generating: boolean) => void;
  refreshProjectsList?: () => Promise<void>;
  onProjectStateChange?: (state: string) => void;
  branchOption?: string;
}

export const useWorkflowOperations = (props: UseWorkflowOperationsProps) => {
  const [pendingWorkflowName, setPendingWorkflowName] = useState<string | null>(null);

  const {
    workflows,
    rxworkflows,
    linkedWorkflows = [],
    setLinkedWorkflows,
    user,
    projectName,
    projectCode,
    selectedRepos,
    regexPattern,
    accountType,
    detectedBuildTypes,
    setWorkflows,
    setRXWorkflows,
    setSelectedWorkflowId,
    markWorkflowAsSaved,
    setDetectedBuildTypes,
    setShowDetectionResults,
    setShowDetectionResultsInModal,
    setTemplatesByType,
    setShowTemplateModal,
    setShowWorkflowCreationDialog,
    setWorkflowCreationType,
    setWorkflowsCount,
    setIsDetecting,
    setIsGeneratingTemplates,
    refreshProjectsList,
    onProjectStateChange,
    branchOption = "default"
  } = props;

  // Workflow count fetching for free accounts
  const fetchWorkflowsCount = useCallback(async (): Promise<void> => {
    if (accountType === "free") {
      try {
        const count = await getWorkflowsCount(user, projectName);
        setWorkflowsCount(count);
      } catch (error) {
        console.error("Error fetching workflows count:", error);
      }
    }
  }, [user, projectName, accountType, setWorkflowsCount]);

  // Save Draft functionality wrapper
  const handleSaveDraftWorkflow = useCallback(async (index: number | null, type: 'regular' | 'reusable'): Promise<void> => {
    await saveDraftWorkflow(
      index, type, workflows, rxworkflows, user, projectName, accountType, 
      markWorkflowAsSaved, fetchWorkflowsCount, refreshProjectsList, onProjectStateChange
    );
  }, [workflows, rxworkflows, user, projectName, accountType, markWorkflowAsSaved, fetchWorkflowsCount, refreshProjectsList, onProjectStateChange]);

  // Commit and Update PR functionality wrapper – used when a workflow already has an open PR
  const handleCommitAndUpdatePR = useCallback(async (index: number | null, type: 'regular' | 'reusable'): Promise<boolean> => {
    return commitAndUpdatePRWorkflow(
      index, type, workflows, rxworkflows, user, projectName,
      selectedRepos, regexPattern, branchOption,
      markWorkflowAsSaved, fetchWorkflowsCount, refreshProjectsList, onProjectStateChange
    );
  }, [workflows, rxworkflows, user, projectName, selectedRepos, regexPattern, branchOption, markWorkflowAsSaved, fetchWorkflowsCount, refreshProjectsList, onProjectStateChange]);

  // Commit and Update PR for linked reusable workflows – save goes to the RWX project,
  // push uses the standard project to resolve the correct RWX repo.
  const handleCommitAndUpdatePRLinked = useCallback(async (index: number): Promise<boolean> => {
    return commitAndUpdatePRLinkedWorkflow(
      index, linkedWorkflows, user, projectName,
      selectedRepos, regexPattern, branchOption,
      fetchWorkflowsCount, refreshProjectsList, onProjectStateChange
    );
  }, [linkedWorkflows, user, projectName, selectedRepos, regexPattern, branchOption, fetchWorkflowsCount, refreshProjectsList, onProjectStateChange]);

  // Draft save for linked reusable workflows – persists content to the RWX project DB
  // without pushing to GitHub, and clears isModified on success.
  const handleSaveDraftLinkedWorkflow = useCallback(async (index: number): Promise<void> => {
    return saveDraftLinkedWorkflow(index, linkedWorkflows, user, projectName, setLinkedWorkflows, refreshProjectsList);
  }, [linkedWorkflows, user, projectName, setLinkedWorkflows, refreshProjectsList]);

  // Delete workflow functionality wrapper
  const handleDeleteWorkflow = useCallback(async (index: number, type: 'regular' | 'reusable'): Promise<void> => {
    await deleteWorkflow(
      index, type, workflows, rxworkflows, user, projectName, selectedRepos, 
      regexPattern, setWorkflows, setRXWorkflows, setSelectedWorkflowId
    );
  }, [workflows, rxworkflows, user, projectName, selectedRepos, regexPattern, setWorkflows, setRXWorkflows, setSelectedWorkflowId]);

  // Unlink a linked reusable workflow from the current project
  const handleUnlinkWorkflow = useCallback(async (workflowId: number): Promise<void> => {
    await unlinkReusableWorkflow(user, projectName, workflowId);
    // Remove the unlinked workflow from local state
    if (setLinkedWorkflows) {
      setLinkedWorkflows((prev: RwxWorkflow[]) => prev.filter(w => w.workflow_id !== workflowId));
    }
    // Clear selection since the workflow is gone
    setSelectedWorkflowId(null);
  }, [user, projectName, setLinkedWorkflows, setSelectedWorkflowId]);

  // Build detection wrapper
  const handleDetectBuildTypes = useCallback(async (): Promise<void> => {
    setIsDetecting(true);
    try {
      await detectBuildTypesForRepos(
        selectedRepos, user, setDetectedBuildTypes, 
        setShowDetectionResults, setShowDetectionResultsInModal
      );
    } finally {
      setIsDetecting(false);
    }
  }, [selectedRepos, user, setDetectedBuildTypes, setShowDetectionResults, setShowDetectionResultsInModal, setIsDetecting]);

  // Add workflow from detection wrapper
  const handleAddWorkflowFromDetection = useCallback(async (repo: string, buildType: BuildType, workflowName: string): Promise<void> => {
    await addWorkflowFromDetection(
      repo, buildType, workflowName, workflows, projectCode, user, setWorkflows, setSelectedWorkflowId,
      setShowWorkflowCreationDialog, setWorkflowCreationType, setShowDetectionResultsInModal,
      setShowDetectionResults, setDetectedBuildTypes
    );
  }, [workflows, projectCode, user, setWorkflows, setSelectedWorkflowId, setShowWorkflowCreationDialog, setWorkflowCreationType, setShowDetectionResultsInModal, setShowDetectionResults, setDetectedBuildTypes]);

  // Generate templates wrapper
  const handleGenerateTemplates = useCallback(async (): Promise<void> => {
    setIsGeneratingTemplates(true);
    try {
      await generateTemplates(
        selectedRepos, detectedBuildTypes, projectCode, user, 
        setTemplatesByType, setShowTemplateModal
      );
    } finally {
      setIsGeneratingTemplates(false);
    }
  }, [selectedRepos, detectedBuildTypes, projectCode, user, setTemplatesByType, setShowTemplateModal, setIsGeneratingTemplates]);

  // Select template wrapper
  const handleSelectTemplate = useCallback((template: WorkflowTemplate, isReusable: boolean = false): void => {
    selectTemplate(
      template, isReusable, projectName, workflows, setWorkflows, 
      setRXWorkflows, setSelectedWorkflowId, setShowTemplateModal, pendingWorkflowName
    );
    // The template path only really creates the workflow here, not when the
    // dialog closes, so this is the honest completion point for both routes.
    tour.completed('start-workflow');
    setPendingWorkflowName(null);
  }, [projectName, workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId, setShowTemplateModal, pendingWorkflowName]);

  // Create blank workflow wrapper
  const handleCreateBlankWorkflow = useCallback((type: 'regular' | 'reusable', workflowName: string): void => {
    createBlankWorkflow(type, workflowName, workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId);
    tour.completed('start-workflow');
    setShowWorkflowCreationDialog(false);
    setWorkflowCreationType(null);
  }, [workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId, setShowWorkflowCreationDialog, setWorkflowCreationType]);

  // Workflow creation dialog functions
  const openWorkflowCreationDialog = useCallback(() => {
    setShowWorkflowCreationDialog(true);
    setWorkflowCreationType(null);
    // Opening the dialog is what "Add a workflow" asked for; the choices
    // inside it are the next two steps.
    tour.completed('add-workflow');
  }, [setShowWorkflowCreationDialog, setWorkflowCreationType]);

  const selectWorkflowType = useCallback((type: 'regular' | 'reusable') => {
    setWorkflowCreationType(type);
    tour.completed('choose-workflow-type');
  }, [setWorkflowCreationType]);

  const handleCreateFromTemplates = useCallback((type: 'regular' | 'reusable', workflowName: string) => {
    setPendingWorkflowName(workflowName);
    setShowWorkflowCreationDialog(false);
    setWorkflowCreationType(null);
    handleGenerateTemplates();
  }, [setShowWorkflowCreationDialog, setWorkflowCreationType, handleGenerateTemplates]);

  return {
    fetchWorkflowsCount,
    handleSaveDraftWorkflow,
    handleSaveDraftLinkedWorkflow,
    handleCommitAndUpdatePR,
    handleCommitAndUpdatePRLinked,
    handleDeleteWorkflow,
    handleUnlinkWorkflow,
    handleDetectBuildTypes,
    handleAddWorkflowFromDetection,
    handleGenerateTemplates,
    handleSelectTemplate,
    handleCreateBlankWorkflow,
    openWorkflowCreationDialog,
    selectWorkflowType,
    handleCreateFromTemplates
  };
};
