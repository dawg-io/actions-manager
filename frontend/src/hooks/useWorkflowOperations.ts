import { useCallback, useState } from 'react';
import { getWorkflowsCount } from '../api/workflows';
import { Workflow, RXWorkflow, DetectedBuildResult, BuildType, WorkflowTemplate, AIEditResponse, AIWorkflowAction } from '../types/workflow';
import { RwxWorkflow, unlinkReusableWorkflow } from '../api/projects';
import { saveDraftWorkflow, commitAndUpdatePRWorkflow, commitAndUpdatePRLinkedWorkflow, saveDraftLinkedWorkflow, deleteWorkflow, createBlankWorkflow } from '../utils/workflowOperations';
import { detectBuildTypesForRepos, addWorkflowFromDetection, generateTemplates, selectTemplate } from '../utils/buildDetectionUtils';
import { generateRegularWorkflowWithAI, generateReusableWorkflowWithAI, editWithAI } from '../utils/aiWorkflowUtils';

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
  setAISessionId: (id: string) => void;
  setAIChatMessages: (messages: any[] | ((prev: any[]) => any[])) => void;
  setShowAIChat: (show: boolean) => void;
  setEditingWorkflowIndex: (index: number | null) => void;
  setEditingWorkflowType: (type: 'regular' | 'reusable' | null) => void;
  setWorkflowsCount: (count: number | null) => void;
  setIsDetecting: (detecting: boolean) => void;
  setIsAILoading: (loading: boolean) => void;
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
    setAISessionId,
    setAIChatMessages,
    setShowAIChat,
    setEditingWorkflowIndex,
    setEditingWorkflowType,
    setWorkflowsCount,
    setIsDetecting,
    setIsAILoading,
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
    setPendingWorkflowName(null);
  }, [projectName, workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId, setShowTemplateModal, pendingWorkflowName]);

  // Create blank workflow wrapper
  const handleCreateBlankWorkflow = useCallback((type: 'regular' | 'reusable', workflowName: string): void => {
    createBlankWorkflow(type, workflowName, workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId);
    setShowWorkflowCreationDialog(false);
    setWorkflowCreationType(null);
  }, [workflows, setWorkflows, setRXWorkflows, setSelectedWorkflowId, setShowWorkflowCreationDialog, setWorkflowCreationType]);

  // Generate AI workflow wrappers
  const handleGenerateRegularWorkflowWithAI = useCallback(async (workflowName: string = ''): Promise<void> => {
    setIsAILoading(true);
    try {
      await generateRegularWorkflowWithAI(
        selectedRepos, projectName, projectCode, detectedBuildTypes, workflows, workflowName, user,
        setWorkflows, setAISessionId, setSelectedWorkflowId, setAIChatMessages, setShowAIChat
      );
    } finally {
      setIsAILoading(false);
    }
  }, [selectedRepos, projectName, projectCode, detectedBuildTypes, workflows, user, setWorkflows, setAISessionId, setSelectedWorkflowId, setAIChatMessages, setShowAIChat, setIsAILoading]);

  const handleGenerateReusableWorkflowWithAI = useCallback(async (workflowName: string = ''): Promise<void> => {
    setIsAILoading(true);
    try {
      await generateReusableWorkflowWithAI(
        selectedRepos, projectName, projectCode, detectedBuildTypes, workflowName, user,
        setRXWorkflows, setAISessionId, setSelectedWorkflowId, setAIChatMessages, setShowAIChat
      );
    } finally {
      setIsAILoading(false);
    }
  }, [selectedRepos, projectName, projectCode, detectedBuildTypes, user, setRXWorkflows, setAISessionId, setSelectedWorkflowId, setAIChatMessages, setShowAIChat, setIsAILoading]);

  // Edit with AI wrapper
  const handleEditWithAI = useCallback(async (
    index: number,
    type: 'regular' | 'reusable',
    action: AIWorkflowAction,
    optionalInstruction: string = ''
  ): Promise<AIEditResponse | null> => {
    setIsAILoading(true);
    try {
      return await editWithAI(
        index, type, action, workflows, rxworkflows, user, projectName, projectCode, selectedRepos,
        detectedBuildTypes, optionalInstruction, setAISessionId, setAIChatMessages, setShowAIChat, 
        setEditingWorkflowIndex, setEditingWorkflowType
      );
    } finally {
      setIsAILoading(false);
    }
  }, [workflows, rxworkflows, user, projectName, projectCode, selectedRepos, detectedBuildTypes, setAISessionId, setAIChatMessages, setShowAIChat, setEditingWorkflowIndex, setEditingWorkflowType, setIsAILoading]);

  // Workflow creation dialog functions
  const openWorkflowCreationDialog = useCallback(() => {
    setShowWorkflowCreationDialog(true);
    setWorkflowCreationType(null);
  }, [setShowWorkflowCreationDialog, setWorkflowCreationType]);

  const selectWorkflowType = useCallback((type: 'regular' | 'reusable') => {
    setWorkflowCreationType(type);
  }, [setWorkflowCreationType]);

  const handleCreateFromTemplates = useCallback((type: 'regular' | 'reusable', workflowName: string) => {
    setPendingWorkflowName(workflowName);
    setShowWorkflowCreationDialog(false);
    setWorkflowCreationType(null);
    handleGenerateTemplates();
  }, [setShowWorkflowCreationDialog, setWorkflowCreationType, handleGenerateTemplates]);

  const handleCreateWithAI = useCallback((type: 'regular' | 'reusable', workflowName: string) => {
    setShowWorkflowCreationDialog(false);
    setWorkflowCreationType(null);
    
    if (type === 'regular') {
      handleGenerateRegularWorkflowWithAI(workflowName);
    } else {
      handleGenerateReusableWorkflowWithAI(workflowName);
    }
  }, [setShowWorkflowCreationDialog, setWorkflowCreationType, handleGenerateRegularWorkflowWithAI, handleGenerateReusableWorkflowWithAI]);

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
    handleGenerateRegularWorkflowWithAI,
    handleGenerateReusableWorkflowWithAI,
    handleEditWithAI,
    openWorkflowCreationDialog,
    selectWorkflowType,
    handleCreateFromTemplates,
    handleCreateWithAI
  };
};
