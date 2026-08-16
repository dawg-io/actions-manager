import React, { useState, useEffect } from 'react';
import YAMLEditor from "./YAMLEditor";
import type { WorkflowDiagnostic } from "./YAMLEditor";
import ValidationPanel from "./ValidationPanel";
import EditableNameField from "./EditableNameField";
import GUIWorkflowEditor from "./GUIWorkflowEditor";
import ConfirmDialog from "./ConfirmDialog";
import { stripWorkflowExtension, validateWorkflowName } from '../utils/workflowFilename';
import { 
  yamlToGui, 
  guiToYaml, 
  WorkflowGUI, 
  ValidationError, 
  DEFAULT_WORKFLOW_GUI 
} from '../utils/workflowGuiConversion';
import { toast } from '../utils/toast';

// TypeScript interfaces
interface Workflow {
  name: string;
  content?: string;
  isReusable?: boolean;
  isModified?: boolean;
  gitHash?: string;
}

interface WorkflowEditorProps {
  workflow: Workflow | null;
  workflowIndex: number | null;
  projectCode?: string;
  isModified: boolean;
  onWorkflowChange: (index: number | null, field: string, value: string) => void;
  onClose: () => void;
  onSave?: (index: number | null) => void;
  onCreate?: (index: number | null) => void;
  onDelete?: (index: number | null) => void;
  onSync?: (workflowName: string) => void;
  workflowSyncStatus?: any; // Legacy prop, not used
}

const WorkflowEditor: React.FC<WorkflowEditorProps> = ({ 
  workflow,
  workflowIndex,
  projectCode,
  isModified,
  onWorkflowChange,
  onClose,
  onSave,
  onCreate,
  onDelete,
  onSync,
  workflowSyncStatus,
}) => {
  const [editMode, setEditMode] = useState<'yaml' | 'gui'>('yaml');
  const [guiWorkflow, setGuiWorkflow] = useState<WorkflowGUI>(DEFAULT_WORKFLOW_GUI);
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);
  const [yamlDiagnostics, setYamlDiagnostics] = useState<WorkflowDiagnostic[]>([]);
  const [isConverting, setIsConverting] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  // Initialize GUI workflow from YAML content
  // Force reload when workflow index OR workflow object changes
  useEffect(() => {
    // Always reinitialize when workflow changes to ensure clean state
    if (workflow?.content) {
      try {
        const gui = yamlToGui(workflow.content);
        setGuiWorkflow(gui);
      } catch (error) {
        console.warn('Failed to convert YAML to GUI:', error);
      }
    } else {
      // Use default template for new workflows
      setGuiWorkflow({
        ...DEFAULT_WORKFLOW_GUI,
        name: workflow?.name || 'CI'
      });
    }
    // Depend on both workflowIndex and workflow to ensure we reload when either changes
  }, [workflowIndex, workflow]);

  const handleModeToggle = (newMode: 'yaml' | 'gui') => {
    if (newMode === editMode) return;
    
    setIsConverting(true);
    
    try {
      if (newMode === 'gui') {
        // Switching to GUI - convert YAML to GUI
        if (workflow?.content) {
          const gui = yamlToGui(workflow.content);
          setGuiWorkflow(gui);
        }
      } else {
        // Switching to YAML - convert GUI to YAML
        const yamlContent = guiToYaml(guiWorkflow);
        onWorkflowChange(workflowIndex, 'content', yamlContent);
      }
      
      setEditMode(newMode);
    } catch (error) {
      console.error('Failed to convert between modes:', error);
      toast.error('Failed to convert between editing modes. Please check the workflow YAML for errors.');
    } finally {
      setIsConverting(false);
    }
  };

  const handleGUIWorkflowChange = (updatedGui: WorkflowGUI) => {
    setGuiWorkflow(updatedGui);
    
    // Update workflow name if it changed
    if (updatedGui.name !== workflow?.name) {
      onWorkflowChange(workflowIndex, 'name', updatedGui.name);
    }
    
    // Convert to YAML and update content
    try {
      const yamlContent = guiToYaml(updatedGui);
      onWorkflowChange(workflowIndex, 'content', yamlContent);
    } catch (error) {
      console.error('Failed to convert GUI to YAML:', error);
    }
  };

  const handleValidationChange = (errors: ValidationError[]) => {
    setValidationErrors(errors);
  };

  if (!workflow) {
    return (
      <div className="workflow-editor-empty">
        <div className="empty-editor-message">
          <h3>No workflow selected</h3>
          <p>Select a workflow from the list to start editing</p>
        </div>
      </div>
    );
  }

  const handleClose = () => {
    if (isModified) {
      setShowCloseConfirm(true);
    } else {
      onClose();
    }
  };

  const hasValidationErrors = validationErrors.some(error => error.severity === 'error');

  return (
    <>
    <div className="workflow-editor">
      <div className="workflow-editor-header">
        <div className="editor-title-section">
          <h3>Edit Workflow</h3>
          {isModified && (
            <span className="modified-badge">Unsaved changes</span>
          )}
          {hasValidationErrors && (
            <span className="validation-badge error">❌ Has errors</span>
          )}
        </div>
        
        <div className="header-actions-section">
          {/* Mode Toggle */}
          <div className="mode-toggle">
            <button
              type="button"
              className={`mode-toggle-button ${editMode === 'gui' ? 'active' : ''}`}
              onClick={() => handleModeToggle('gui')}
              disabled={isConverting}
              title="Edit with visual form interface"
            >
              📝 GUI
            </button>
            <button
              type="button"
              className={`mode-toggle-button ${editMode === 'yaml' ? 'active' : ''}`}
              onClick={() => handleModeToggle('yaml')}
              disabled={isConverting}
              title="Edit raw YAML"
            >
              📄 YAML
            </button>
          </div>
          
          <div className="workflow-editor-actions">
            {workflow.name && workflow.content && (
              <>
                {onSave && (
                  <button
                    className="action-button save-button"
                    onClick={() => onSave(workflowIndex)}
                    title="Save workflow to database only (draft)"
                  >
                    💾 Save Draft
                  </button>
                )}
                
                <button
                  className="action-button create-button"
                  onClick={() => onCreate && onCreate(workflowIndex)}
                  disabled={hasValidationErrors}
                  title={hasValidationErrors ? "Fix validation errors before creating" : "Create workflow in GitHub"}
                >
                  🔄 Create
                </button>
              </>
            )}
            
            {onDelete && (
              <button
                className="action-button delete-button"
                onClick={() => onDelete(workflowIndex)}
                title="Delete workflow"
              >
                ❌ Delete
              </button>
            )}
          </div>
          
          <button 
            className="close-button"
            onClick={handleClose}
            title="Close editor"
          >
            ✕
          </button>
        </div>
      </div>
      
      <div className="workflow-editor-content">
        <div className="workflow-name-section">
          <EditableNameField
            value={stripWorkflowExtension(workflow.name)}
            onSave={(newValue) =>
              onWorkflowChange(workflowIndex, "name", stripWorkflowExtension(newValue))
            }
            validate={validateWorkflowName}
            prefix={`AM_${(projectCode || '').toUpperCase()}_`}
            suffix=".yml"
            placeholder="workflow-name"
            ariaLabel="workflow name"
            className="workflow-name-section-field"
            inputClassName="workflow-name-input"
          />
        </div>
        
        <div className="workflow-code-section">         
          <div className="editor-container">
            {editMode === 'gui' ? (
              <GUIWorkflowEditor
                key={workflowIndex}
                workflow={guiWorkflow}
                onChange={handleGUIWorkflowChange}
                onValidationChange={handleValidationChange}
                // GUIWorkflowEditor requires these; this component never
                // received them, so they were silently undefined at runtime.
                // Empty is correct here - WorkflowEditor has no action data to
                // pass. NOTE: this component is not rendered anywhere (only its
                // own test imports it); UnifiedWorkflowEditor superseded it.
                importedActions={[]}
                actionGroups={[]}
              />
            ) : (
              <div className="yaml-editor-container">
                <YAMLEditor
                  key={workflowIndex}
                  height="400px"
                  value={workflow.content}
                  onChange={(value: string) => onWorkflowChange(workflowIndex, "content", value)}
                  onStructuralDiagnostics={setYamlDiagnostics}
                  placeholder="Enter your GitHub Actions workflow YAML here..."
                  theme="dark"
                />
                <ValidationPanel diagnostics={yamlDiagnostics} />
              </div>
            )}
          </div>
        </div>
        

      </div>
    </div>

    {showCloseConfirm && (
      <ConfirmDialog
        open={true}
        title="Discard unsaved changes?"
        description="You have unsaved changes to this workflow. Closing now will discard those changes."
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        destructive
        onConfirm={() => { setShowCloseConfirm(false); onClose(); }}
        onCancel={() => setShowCloseConfirm(false)}
      />
    )}
  </>
  );
};

export default WorkflowEditor;
