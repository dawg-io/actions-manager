import { useEffect } from 'react';

export interface UseParentCallbacksProps {
  onAddWorkflow?: (addWorkflowFn: () => void) => void;
  onAddRXWorkflow?: (addFn: () => void) => void;
  onGenerateTemplates?: (generateFn: () => Promise<void>, isGenerating: boolean) => void;
  onClearModifiedStates?: (clearFn: () => void) => void;
  openWorkflowCreationDialog: () => void;
  selectWorkflowType?: (type: 'regular' | 'reusable') => void;
  handleGenerateTemplates: () => Promise<void>;
  isGeneratingTemplates: boolean;
  setModifiedWorkflows: (modified: Set<number>) => void;
  setModifiedRXWorkflows: (modified: Set<number>) => void;
}

export const useParentCallbacks = ({
  onAddWorkflow,
  onAddRXWorkflow,
  onGenerateTemplates,
  onClearModifiedStates,
  openWorkflowCreationDialog,
  selectWorkflowType,
  handleGenerateTemplates,
  isGeneratingTemplates,
  setModifiedWorkflows,
  setModifiedRXWorkflows
}: UseParentCallbacksProps) => {

  // Expose functions to parent via callbacks
  useEffect(() => {
    if (onAddWorkflow) {
      onAddWorkflow(() => openWorkflowCreationDialog());
    }
  }, [onAddWorkflow, openWorkflowCreationDialog]);

  useEffect(() => {
    if (onAddRXWorkflow) {
      onAddRXWorkflow(() => {
        openWorkflowCreationDialog();
        selectWorkflowType?.('reusable');
      });
    }
  }, [onAddRXWorkflow, openWorkflowCreationDialog, selectWorkflowType]);

  useEffect(() => {
    if (onGenerateTemplates) {
      onGenerateTemplates(handleGenerateTemplates, isGeneratingTemplates);
    }
  }, [onGenerateTemplates, handleGenerateTemplates, isGeneratingTemplates]);

  useEffect(() => {
    if (onClearModifiedStates) {
      onClearModifiedStates(() => {
        setModifiedWorkflows(new Set());
        setModifiedRXWorkflows(new Set());
      });
    }
  }, [onClearModifiedStates, setModifiedWorkflows, setModifiedRXWorkflows]);
};
