import { useCallback } from 'react';
import { yamlToGuiResult, WorkflowGUI, DEFAULT_REUSABLE_WORKFLOW_GUI, DEFAULT_WORKFLOW_GUI } from '../utils/workflowGuiConversion';
import { UnifiedWorkflowItem } from '../types/workflow';

export interface UseWorkflowSelectionLogicProps {
  unifiedWorkflows: UnifiedWorkflowItem[];
  setSelectedWorkflowId: (id: string) => void;
  setGuiWorkflow: (workflow: WorkflowGUI) => void;
  setRegularGuiWorkflow: (workflow: WorkflowGUI) => void;
}

export const useWorkflowSelectionLogic = ({
  unifiedWorkflows,
  setSelectedWorkflowId,
  setGuiWorkflow,
  setRegularGuiWorkflow
}: UseWorkflowSelectionLogicProps) => {
  
  // Empty template carrying the workflow's own name — used for new workflows and
  // whenever the YAML can't be converted. The name is applied as-is, even when
  // empty, rather than falling back to the template's default.
  const applyDefaultModel = useCallback((workflow: UnifiedWorkflowItem) => {
    if (workflow.isReusable) {
      setGuiWorkflow({ ...DEFAULT_REUSABLE_WORKFLOW_GUI, name: workflow.name });
    } else {
      setRegularGuiWorkflow({ ...DEFAULT_WORKFLOW_GUI, name: workflow.name });
    }
  }, [setGuiWorkflow, setRegularGuiWorkflow]);

  const applyParsedModel = useCallback((workflow: UnifiedWorkflowItem, gui: WorkflowGUI) => {
    // Prefer workflow.name from the workflow object over parsed YAML name
    // This ensures the name field stays synchronized with the workflow state
    gui.name = workflow.name !== undefined && workflow.name !== null ? workflow.name : gui.name;

    if (!workflow.isReusable) {
      setRegularGuiWorkflow(gui);
      return;
    }

    if (!gui.events.some(e => e.type === 'workflow_call')) {
      gui.events = [{ type: 'workflow_call', inputs: {} }];
    }
    setGuiWorkflow(gui);
  }, [setGuiWorkflow, setRegularGuiWorkflow]);

  /**
   * Rebuilds the GUI model from a workflow's YAML.
   *
   * Returns the conversion error, or `null` on success, so callers that would
   * write the model back over the document (the YAML→GUI mode switch) can refuse
   * rather than serialise a default template over the user's work. Selection
   * ignores the return value and keeps its existing fall-back behaviour.
   */
  const initializeWorkflowGUI = useCallback((workflow: UnifiedWorkflowItem): string | null => {
    // New workflow with nothing in it yet.
    if (!workflow.content) {
      applyDefaultModel(workflow);
      return null;
    }

    try {
      const { gui, error } = yamlToGuiResult(workflow.content);
      if (error) {
        // Fall back to a default model, as before, but tell the caller.
        applyDefaultModel(workflow);
        return error;
      }
      applyParsedModel(workflow, gui);
      return null;
    } catch (error) {
      console.warn('Failed to convert YAML to GUI:', error);
      applyDefaultModel(workflow);
      return error instanceof Error ? error.message : 'Failed to convert YAML to GUI.';
    }
  }, [applyDefaultModel, applyParsedModel]);

  const handleSelectWorkflow = useCallback((workflowId: string) => {
    setSelectedWorkflowId(workflowId);
    const workflow = unifiedWorkflows.find(w => w.id === workflowId);
    
    if (workflow) {
      initializeWorkflowGUI(workflow);
    } else {
      setRegularGuiWorkflow(DEFAULT_WORKFLOW_GUI);
    }
  }, [unifiedWorkflows, setSelectedWorkflowId, initializeWorkflowGUI, setRegularGuiWorkflow]);

  return { handleSelectWorkflow, initializeWorkflowGUI };
};