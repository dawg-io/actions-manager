import { useCallback } from 'react';
import { yamlToGui, WorkflowGUI, DEFAULT_REUSABLE_WORKFLOW_GUI, DEFAULT_WORKFLOW_GUI } from '../utils/workflowGuiConversion';
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
  
  const initializeWorkflowGUI = useCallback((workflow: UnifiedWorkflowItem) => {
    if (workflow.content) {
      try {
        if (workflow.isReusable) {
          const gui = yamlToGui(workflow.content);
          if (!gui.events.some(e => e.type === 'workflow_call')) {
            gui.events = [{ type: 'workflow_call', inputs: {} }];
          }
          // Prefer workflow.name from the workflow object over parsed YAML name
          // This ensures the name field stays synchronized with the workflow state
          gui.name = workflow.name !== undefined && workflow.name !== null ? workflow.name : gui.name;
          setGuiWorkflow(gui);
        } else {
          const gui = yamlToGui(workflow.content);
          // Prefer workflow.name from the workflow object over parsed YAML name
          // This ensures the name field stays synchronized with the workflow state
          gui.name = workflow.name !== undefined && workflow.name !== null ? workflow.name : gui.name;
          setRegularGuiWorkflow(gui);
        }
      } catch (error) {
        console.warn('Failed to convert YAML to GUI:', error);
        // If YAML parsing fails, use workflow's name as-is (even if empty string)
        if (workflow.isReusable) {
          setGuiWorkflow({ ...DEFAULT_REUSABLE_WORKFLOW_GUI, name: workflow.name });
        } else {
          setRegularGuiWorkflow({ ...DEFAULT_WORKFLOW_GUI, name: workflow.name });
        }
      }
    } else {
      // For new workflows with empty content, initialize GUI with workflow's name
      // Use the actual workflow name even if it's empty string - don't fallback to default
      if (workflow.isReusable) {
        setGuiWorkflow({ ...DEFAULT_REUSABLE_WORKFLOW_GUI, name: workflow.name });
      } else {
        setRegularGuiWorkflow({ ...DEFAULT_WORKFLOW_GUI, name: workflow.name });
      }
    }
  }, [setGuiWorkflow, setRegularGuiWorkflow]);

  const handleSelectWorkflow = useCallback((workflowId: string) => {
    setSelectedWorkflowId(workflowId);
    const workflow = unifiedWorkflows.find(w => w.id === workflowId);
    
    if (workflow) {
      initializeWorkflowGUI(workflow);
    } else {
      setRegularGuiWorkflow(DEFAULT_WORKFLOW_GUI);
    }
  }, [unifiedWorkflows, setSelectedWorkflowId, initializeWorkflowGUI, setRegularGuiWorkflow]);

  return { handleSelectWorkflow };
};