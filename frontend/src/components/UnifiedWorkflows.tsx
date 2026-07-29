import React, { useEffect, useState } from 'react';
import UnifiedWorkflowList from './UnifiedWorkflowList';
import UnifiedWorkflowEditor from './UnifiedWorkflowEditor';
import WorkflowCreationDialog from './WorkflowCreationDialog';
import TemplateSelectionModal from './TemplateSelectionModal';
import { handleWorkflowChange } from '../utils/workflowOperations';
import { useUnifiedWorkflowsState } from '../hooks/useUnifiedWorkflowsState';
import { useWorkflowOperations } from '../hooks/useWorkflowOperations';
import { useWorkflowSelectionLogic } from '../hooks/useWorkflowSelectionLogic';
import { useParentCallbacks } from '../hooks/useParentCallbacks';
import { UnifiedWorkflowsProps, UnifiedWorkflowItem } from '../types/workflow';
import { CustomFilePanel } from './CustomFiles';
import CodeownersManager from './CodeownersManager';
import { CustomFile } from '../api/customFiles';
// eslint-disable-next-line no-restricted-imports -- Legacy: TODO migrate CSS file to Tailwind CSS classes
import '../styles/UnifiedWorkflows.css';
// eslint-disable-next-line no-restricted-imports -- Legacy: TODO migrate CSS file to Tailwind CSS classes
import '../styles/TemplateModal.css';

const UnifiedWorkflows: React.FC<UnifiedWorkflowsProps> = ({
  user,
  projectName,
  projectCode,
  selectedRepos,
  regexPattern,
  accountType,
  projectPRState = "new",
  usePrefix = true,
  isReadOnly = false,
  branchOption = "default",
  workflows,
  setWorkflows,
  onRefreshStatus,
  onAddWorkflow,
  onClearModifiedStates,
  rxworkflows,
  setRXWorkflows,
  addWorkflowToMain,
  onGenerateTemplates,
  onAddRXWorkflow,
  detectedBuildTypes,
  reusableWorkflowsEnabled,
  repoExists,
  linkedWorkflows = [],
  setLinkedWorkflows,
  canLinkReusableWorkflows = false,
  onLinkReusableWorkflow,
  onImportExisting,
  refreshProjectsList,
  onProjectStateChange,
  driftedWorkflowNames,
  customFiles = [],
  setCustomFiles,
  projectId,
  onCustomFilesChange,
  codeownersRefreshCounter,
  codeownersAggregateStatus,
  onCodeownersSaved,
  importedActions = [],
  actionGroups = [],
}) => {
  // Project Files: custom file and codeowners selection
  const [selectedCustomFileId, setSelectedCustomFileId] = useState<number | null>(null);
  const [selectedCodeownersRepo, setSelectedCodeownersRepo] = useState<string | null>(null);
  // -1 sentinel = "add new custom file" mode
  const ADD_CUSTOM_FILE_SENTINEL = -1;

  const handleCustomFilesChange = (updated: CustomFile[]) => {
    setCustomFiles?.(updated);
    onCustomFilesChange?.(updated);
  };

  // Use custom hooks for state management
  const state = useUnifiedWorkflowsState(workflows, setWorkflows, setRXWorkflows);

  const handleSelectCustomFile = (id: number) => {
    setSelectedCustomFileId(id);
    state.setSelectedWorkflowId(null);
    setSelectedCodeownersRepo(null);
  };

  const handleSelectCodeowners = (repo: string) => {
    setSelectedCodeownersRepo(repo);
    state.setSelectedWorkflowId(null);
    setSelectedCustomFileId(null);
  };
  
  // Create unified workflow list
  const unifiedWorkflows: UnifiedWorkflowItem[] = [
    ...workflows.map((workflow, index) => ({
      id: `regular-${index}`,
      name: workflow.name,
      content: workflow.content,
      isReusable: false,
      isModified: workflow.isModified,
      gitHash: workflow.gitHash,
      workflowStatus: workflow.workflowStatus,
      originalIndex: index,
      type: 'regular' as const,
      lastModifiedBy: workflow.lastModifiedBy,
    })),
    ...(reusableWorkflowsEnabled && repoExists ? rxworkflows.map((workflow, index) => ({
      id: `reusable-${index}`,
      name: workflow.name,
      content: workflow.content,
      isReusable: true,
      isModified: workflow.isModified,
      gitHash: workflow.gitHash,
      workflowStatus: workflow.workflowStatus,
      originalIndex: index,
      type: 'reusable' as const,
      lastModifiedBy: workflow.lastModifiedBy,
    })) : []),
    ...linkedWorkflows.map((workflow, index) => ({
      id: `linked-${workflow.workflow_id}`,
      name: workflow.workflow_name,
      content: workflow.workflow_yaml,
      isReusable: true,
      isModified: workflow.isModified ?? false,
      gitHash: undefined,
      workflowStatus: workflow.workflowStatus,
      originalIndex: index,
      type: 'linked' as const,
      rwxProjectId: workflow.rwx_project_id,
      rwxProjectName: workflow.rwx_project_name,
      rwxRepo: workflow.rwx_repo
    }))
  ];

  const selectedWorkflow = unifiedWorkflows.find(w => w.id === state.selectedWorkflowId);

  // Use workflow operations hook
  const operations = useWorkflowOperations({
    workflows,
    rxworkflows,
    linkedWorkflows,
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
    setSelectedWorkflowId: state.setSelectedWorkflowId,
    markWorkflowAsSaved: state.markWorkflowAsSaved,
    setDetectedBuildTypes: state.setDetectedBuildTypes,
    setShowDetectionResults: state.setShowDetectionResults,
    setShowDetectionResultsInModal: state.setShowDetectionResultsInModal,
    setTemplatesByType: state.setTemplatesByType,
    setShowTemplateModal: state.setShowTemplateModal,
    setShowWorkflowCreationDialog: state.setShowWorkflowCreationDialog,
    setWorkflowCreationType: state.setWorkflowCreationType,
    setEditingWorkflowIndex: state.setEditingWorkflowIndex,
    setEditingWorkflowType: state.setEditingWorkflowType,
    setWorkflowsCount: state.setWorkflowsCount,
    setIsDetecting: state.setIsDetecting,
    setIsGeneratingTemplates: state.setIsGeneratingTemplates,
    refreshProjectsList,
    onProjectStateChange,
    branchOption
  });

  // Use workflow selection logic hook
  const { handleSelectWorkflow: _handleSelectWorkflow } = useWorkflowSelectionLogic({
    unifiedWorkflows,
    setSelectedWorkflowId: state.setSelectedWorkflowId,
    setGuiWorkflow: state.setGuiWorkflow,
    setRegularGuiWorkflow: state.setRegularGuiWorkflow
  });

  // Wrap to also clear non-workflow selections
  const handleSelectWorkflow = (workflowId: string) => {
    setSelectedCustomFileId(null);
    setSelectedCodeownersRepo(null);
    _handleSelectWorkflow(workflowId);
  };

  // Workflow change handler
  const handleWorkflowChangeWrapper = (field: string, value: string) => {
    handleWorkflowChange({
      field,
      value,
      selectedWorkflow,
      workflows,
      setWorkflows,
      setRXWorkflows,
      editMode: state.editMode,
      regularGuiWorkflow: state.regularGuiWorkflow,
      guiWorkflow: state.guiWorkflow,
      setRegularGuiWorkflow: state.setRegularGuiWorkflow,
      setGuiWorkflow: state.setGuiWorkflow,
      markWorkflowAsModified: state.markWorkflowAsModified,
      setLinkedWorkflows,
    });
  };

  // Use parent callbacks hook
  useParentCallbacks({
    onAddWorkflow,
    onAddRXWorkflow,
    onGenerateTemplates,
    onClearModifiedStates,
    openWorkflowCreationDialog: operations.openWorkflowCreationDialog,
    selectWorkflowType: operations.selectWorkflowType,
    handleGenerateTemplates: operations.handleGenerateTemplates,
    isGeneratingTemplates: state.isGeneratingTemplates,
    setModifiedWorkflows: state.setModifiedWorkflows,
    setModifiedRXWorkflows: state.setModifiedRXWorkflows
  });

  // Initialize workflows count for free accounts
  useEffect(() => {
    operations.fetchWorkflowsCount();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Initialize GUI state when a workflow is selected
  // This ensures that when createBlankWorkflow sets selectedWorkflowId,
  // the GUI state is properly initialized with the workflow's name
  useEffect(() => {
    if (state.selectedWorkflowId && selectedWorkflow) {
      handleSelectWorkflow(state.selectedWorkflowId);
    }
    // Only run when selectedWorkflowId changes, not on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.selectedWorkflowId]);

  return (
    <div className="unified-workflows-container">
      {/* Unified file list on the left — workflows + custom files + CODEOWNERS */}
      <UnifiedWorkflowList
        unifiedWorkflows={unifiedWorkflows}
        selectedWorkflowId={state.selectedWorkflowId}
        isCollapsed={state.isCollapsed}
        projectCode={projectCode}
        usePrefix={usePrefix}
        loadingStatuses={state.loadingStatuses}
        workflowStatuses={state.workflowStatuses}
        selectedRepos={selectedRepos}
        reusableWorkflowsEnabled={reusableWorkflowsEnabled}
        repoExists={repoExists}
        setIsCollapsed={state.setIsCollapsed}
        handleSelectWorkflow={handleSelectWorkflow}
        addWorkflowFn={operations.openWorkflowCreationDialog}
        driftedWorkflowNames={driftedWorkflowNames}
        customFiles={customFiles}
        selectedCustomFileId={selectedCustomFileId}
        onSelectCustomFile={handleSelectCustomFile}
        codeownersRepos={selectedRepos}
        selectedCodeownersRepo={selectedCodeownersRepo}
        onSelectCodeowners={handleSelectCodeowners}
        codeownersAggregateStatus={codeownersAggregateStatus}
      />

      {/* Right panel — switches based on what is selected */}
      {selectedCustomFileId !== null ? (
        <div className="unified-workflows-editor">
          <CustomFilePanel
            cf={selectedCustomFileId === ADD_CUSTOM_FILE_SENTINEL
              ? null
              : (customFiles.find(f => f.id === selectedCustomFileId) ?? null)}
            allFiles={customFiles}
            projectId={projectId ?? 0}
            githubUser={user}
            onChange={handleCustomFilesChange}
            onAfterAdd={(newId) => setSelectedCustomFileId(newId)}
          />
        </div>
      ) : selectedCodeownersRepo !== null ? (
        <div className="unified-workflows-editor overflow-auto">
          <CodeownersManager
            user={user}
            projectName={projectName}
            selectedRepos={selectedRepos}
            isReadOnly={isReadOnly}
            initialRepo={selectedCodeownersRepo}
            refreshCounter={codeownersRefreshCounter}
            onSave={onCodeownersSaved}
          />
        </div>
      ) : (
        <UnifiedWorkflowEditor
          selectedWorkflow={selectedWorkflow}
          editMode={state.editMode}
          regularGuiWorkflow={state.regularGuiWorkflow}
          guiWorkflow={state.guiWorkflow}
          projectCode={projectCode}
          projectPRState={projectPRState}
          usePrefix={usePrefix}
          isReadOnly={isReadOnly}
          user={user}
          projectName={projectName}
          selectedRepos={selectedRepos}
          importedActions={importedActions}
          actionGroups={actionGroups}
          setEditMode={state.setEditMode}
          setRegularGuiWorkflow={state.setRegularGuiWorkflow}
          setGuiWorkflow={state.setGuiWorkflow}
          handleWorkflowChange={handleWorkflowChangeWrapper}
          saveDraftWorkflow={operations.handleSaveDraftWorkflow}
          saveDraftLinkedWorkflow={operations.handleSaveDraftLinkedWorkflow}
          commitAndUpdatePR={operations.handleCommitAndUpdatePR}
          commitAndUpdatePRLinked={operations.handleCommitAndUpdatePRLinked}
          deleteWorkflow={operations.handleDeleteWorkflow}
          unlinkWorkflow={operations.handleUnlinkWorkflow}
          addWorkflowFn={operations.openWorkflowCreationDialog}
          onImportExisting={onImportExisting}
        />
      )}
      
      {/* Workflow Creation Dialog */}
      <WorkflowCreationDialog
        showWorkflowCreationDialog={state.showWorkflowCreationDialog}
        workflowCreationType={state.workflowCreationType}
        showDetectionResultsInModal={state.showDetectionResultsInModal}
        isDetecting={state.isDetecting}
        detectedBuildTypesState={state.detectedBuildTypesState}
        isGeneratingTemplates={state.isGeneratingTemplates}
        reusableWorkflowsEnabled={reusableWorkflowsEnabled}
        showLinkReusableWorkflow={canLinkReusableWorkflows}
        existingWorkflowNames={[...workflows.map(workflow => workflow.name), ...rxworkflows.map(workflow => workflow.name)]}
        selectedRepos={selectedRepos}
        onAddCustomFile={() => handleSelectCustomFile(ADD_CUSTOM_FILE_SENTINEL)}
        codeownersRepos={selectedRepos}
        onSelectCodeowners={handleSelectCodeowners}
        setShowWorkflowCreationDialog={state.setShowWorkflowCreationDialog}
        selectWorkflowType={operations.selectWorkflowType}
        onLinkReusableWorkflow={onLinkReusableWorkflow}
        createBlankWorkflow={operations.handleCreateBlankWorkflow}
        handleDetectBuildTypes={operations.handleDetectBuildTypes}
        handleCreateFromTemplates={operations.handleCreateFromTemplates}
        addWorkflowFromDetection={operations.handleAddWorkflowFromDetection}
        setWorkflowCreationType={state.setWorkflowCreationType}
        setShowDetectionResultsInModal={state.setShowDetectionResultsInModal}
        setDetectedBuildTypes={state.setDetectedBuildTypes}
      />
      
      {/* Template Selection Modal */}
      <TemplateSelectionModal
        showTemplateModal={state.showTemplateModal}
        templatesByType={state.templatesByType}
        setShowTemplateModal={state.setShowTemplateModal}
        selectTemplate={operations.handleSelectTemplate}
      />
    </div>
  );
};

export default UnifiedWorkflows;
