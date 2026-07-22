import { useState, useCallback } from 'react';
import { WorkflowGUI, DEFAULT_REUSABLE_WORKFLOW_GUI, DEFAULT_WORKFLOW_GUI } from '../utils/workflowGuiConversion';
import { AIChatMessage, WorkflowStatusData, DetectedBuildResult, TemplatesByType } from '../types/workflow';

export interface UseUnifiedWorkflowsStateReturn {
  // UI State
  selectedWorkflowId: string | null;
  setSelectedWorkflowId: (id: string | null) => void;
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
  editMode: 'yaml' | 'gui';
  setEditMode: (mode: 'yaml' | 'gui') => void;
  
  // GUI Workflow State
  guiWorkflow: WorkflowGUI;
  setGuiWorkflow: (workflow: WorkflowGUI) => void;
  regularGuiWorkflow: WorkflowGUI;
  setRegularGuiWorkflow: (workflow: WorkflowGUI) => void;
  
  // AI State
  showAIChat: boolean;
  setShowAIChat: (show: boolean) => void;
  aiChatMessages: AIChatMessage[];
  setAIChatMessages: (messages: AIChatMessage[] | ((prev: AIChatMessage[]) => AIChatMessage[])) => void;
  isAILoading: boolean;
  setIsAILoading: (loading: boolean) => void;
  aiSessionId: string;
  setAISessionId: (id: string) => void;
  
  // Workflow Modification State
  modifiedWorkflows: Set<number>;
  setModifiedWorkflows: (modified: Set<number> | ((prev: Set<number>) => Set<number>)) => void;
  modifiedRXWorkflows: Set<number>;
  setModifiedRXWorkflows: (modified: Set<number> | ((prev: Set<number>) => Set<number>)) => void;
  
  // Editor State
  editingWorkflowIndex: number | null;
  setEditingWorkflowIndex: (index: number | null) => void;
  editingWorkflowType: 'regular' | 'reusable' | null;
  setEditingWorkflowType: (type: 'regular' | 'reusable' | null) => void;
  
  // Workflow Count State
  workflowsCount: number | null;
  setWorkflowsCount: (count: number | null) => void;
  
  // Build Detection State
  isDetecting: boolean;
  setIsDetecting: (detecting: boolean) => void;
  detectedBuildTypesState: DetectedBuildResult[];
  setDetectedBuildTypes: (types: DetectedBuildResult[]) => void;
  showDetectionResults: boolean;
  setShowDetectionResults: (show: boolean) => void;
  showDetectionResultsInModal: boolean;
  setShowDetectionResultsInModal: (show: boolean) => void;
  
  // Template State
  showTemplateModal: boolean;
  setShowTemplateModal: (show: boolean) => void;
  templatesByType: TemplatesByType;
  setTemplatesByType: (templates: TemplatesByType) => void;
  isGeneratingTemplates: boolean;
  setIsGeneratingTemplates: (generating: boolean) => void;
  
  // Workflow Creation State
  showWorkflowCreationDialog: boolean;
  setShowWorkflowCreationDialog: (show: boolean) => void;
  workflowCreationType: 'regular' | 'reusable' | null;
  setWorkflowCreationType: (type: 'regular' | 'reusable' | null) => void;
  
  // Status State
  workflowStatuses: Record<string, WorkflowStatusData>;
  setWorkflowStatuses: (statuses: Record<string, WorkflowStatusData>) => void;
  loadingStatuses: boolean;
  setLoadingStatuses: (loading: boolean) => void;
  
  // Helper Functions
  markWorkflowAsModified: (index: number, type: 'regular' | 'reusable') => void;
  markWorkflowAsSaved: (index: number, type: 'regular' | 'reusable', workflowStatus?: string) => void;
}

export const useUnifiedWorkflowsState = (
  workflows: any[], 
  setWorkflows: (workflows: any[]) => void,
  setRXWorkflows: (workflows: any[] | ((prev: any[]) => any[])) => void
): UseUnifiedWorkflowsStateReturn => {
  // UI State
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [editMode, setEditMode] = useState<'yaml' | 'gui'>('yaml');
  
  // GUI Workflow State
  const [guiWorkflow, setGuiWorkflow] = useState<WorkflowGUI>(DEFAULT_REUSABLE_WORKFLOW_GUI);
  const [regularGuiWorkflow, setRegularGuiWorkflow] = useState<WorkflowGUI>(DEFAULT_WORKFLOW_GUI);
  
  // AI State
  const [showAIChat, setShowAIChat] = useState(false);
  const [aiChatMessages, setAIChatMessages] = useState<AIChatMessage[]>([]);
  const [isAILoading, setIsAILoading] = useState(false);
  const [aiSessionId, setAISessionId] = useState<string>("");
  
  // Workflow Modification State
  const [modifiedWorkflows, setModifiedWorkflows] = useState<Set<number>>(new Set());
  const [modifiedRXWorkflows, setModifiedRXWorkflows] = useState<Set<number>>(new Set());
  
  // Editor State
  const [editingWorkflowIndex, setEditingWorkflowIndex] = useState<number | null>(null);
  const [editingWorkflowType, setEditingWorkflowType] = useState<'regular' | 'reusable' | null>(null);
  
  // Workflow Count State
  const [workflowsCount, setWorkflowsCount] = useState<number | null>(null);
  
  // Build Detection State
  const [isDetecting, setIsDetecting] = useState(false);
  const [detectedBuildTypesState, setDetectedBuildTypes] = useState<DetectedBuildResult[]>([]);
  const [showDetectionResults, setShowDetectionResults] = useState(false);
  const [showDetectionResultsInModal, setShowDetectionResultsInModal] = useState(false);
  
  // Template State
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [templatesByType, setTemplatesByType] = useState<TemplatesByType>({});
  const [isGeneratingTemplates, setIsGeneratingTemplates] = useState(false);
  
  // Workflow Creation State
  const [showWorkflowCreationDialog, setShowWorkflowCreationDialog] = useState(false);
  const [workflowCreationType, setWorkflowCreationType] = useState<'regular' | 'reusable' | null>(null);
  
  // Status State
  const [workflowStatuses, setWorkflowStatuses] = useState<Record<string, WorkflowStatusData>>({});
  const [loadingStatuses, setLoadingStatuses] = useState(false);
  
  // Helper Functions
  const markWorkflowAsModified = useCallback((index: number, type: 'regular' | 'reusable') => {
    if (type === 'regular') {
      setModifiedWorkflows(prev => new Set(prev).add(index));
    } else {
      setModifiedRXWorkflows(prev => new Set(prev).add(index));
    }
  }, []);

  const markWorkflowAsSaved = useCallback((index: number, type: 'regular' | 'reusable', workflowStatus?: string) => {
    if (type === 'regular') {
      setModifiedWorkflows(prev => {
        const newSet = new Set(prev);
        newSet.delete(index);
        return newSet;
      });
      // Also update the workflow in state - create new object instead of mutating
      const newWorkflows = [...workflows];
      if (newWorkflows[index]) {
        newWorkflows[index] = {
          ...newWorkflows[index],
          isModified: false,
          // Update savedName to the current name so future saves use the new name
          // as the baseline and won't treat it as another rename.
          savedName: newWorkflows[index].name,
          ...(workflowStatus !== undefined ? { workflowStatus } : {})
        };
        setWorkflows(newWorkflows);
      }
    } else {
      setModifiedRXWorkflows(prev => {
        const newSet = new Set(prev);
        newSet.delete(index);
        return newSet;
      });
      // Also update the workflow in state - create new object instead of mutating
      setRXWorkflows(prev => {
        const newWorkflows = Array.isArray(prev) ? [...prev] : [];
        if (newWorkflows[index]) {
          newWorkflows[index] = {
            ...newWorkflows[index],
            isModified: false,
            // Update savedName to the current name so future saves use the new name
            // as the baseline and won't treat it as another rename.
            savedName: newWorkflows[index].name,
            ...(workflowStatus !== undefined ? { workflowStatus } : {})
          };
        }
        return newWorkflows;
      });
    }
  }, [workflows, setWorkflows, setRXWorkflows]);

  return {
    // UI State
    selectedWorkflowId,
    setSelectedWorkflowId,
    isCollapsed,
    setIsCollapsed,
    editMode,
    setEditMode,
    
    // GUI Workflow State
    guiWorkflow,
    setGuiWorkflow,
    regularGuiWorkflow,
    setRegularGuiWorkflow,
    
    // AI State
    showAIChat,
    setShowAIChat,
    aiChatMessages,
    setAIChatMessages,
    isAILoading,
    setIsAILoading,
    aiSessionId,
    setAISessionId,
    
    // Workflow Modification State
    modifiedWorkflows,
    setModifiedWorkflows,
    modifiedRXWorkflows,
    setModifiedRXWorkflows,
    
    // Editor State
    editingWorkflowIndex,
    setEditingWorkflowIndex,
    editingWorkflowType,
    setEditingWorkflowType,
    
    // Workflow Count State
    workflowsCount,
    setWorkflowsCount,
    
    // Build Detection State
    isDetecting,
    setIsDetecting,
    detectedBuildTypesState,
    setDetectedBuildTypes,
    showDetectionResults,
    setShowDetectionResults,
    showDetectionResultsInModal,
    setShowDetectionResultsInModal,
    
    // Template State
    showTemplateModal,
    setShowTemplateModal,
    templatesByType,
    setTemplatesByType,
    isGeneratingTemplates,
    setIsGeneratingTemplates,
    
    // Workflow Creation State
    showWorkflowCreationDialog,
    setShowWorkflowCreationDialog,
    workflowCreationType,
    setWorkflowCreationType,
    
    // Status State
    workflowStatuses,
    setWorkflowStatuses,
    loadingStatuses,
    setLoadingStatuses,
    
    // Helper Functions
    markWorkflowAsModified,
    markWorkflowAsSaved
  };
};