/* eslint-disable no-restricted-syntax, no-restricted-imports -- Legacy: TODO migrate inline styles and CSS imports to Tailwind CSS classes */
import React, { useState, useEffect, useCallback } from "react";
import { deleteWorkflowFromDatabase, deleteReusableWorkflowFromGitHub } from "../api/workflows";
import { saveRxWorkflows } from "../api/rxworkflows";
import { generateWorkflowTemplates } from "../api/workflowTemplates";
import { generateReusableWorkflowWithAI as generateReusableWorkflowAPI, sendChatMessage, editWorkflowWithAI as editWorkflowWithAIAPI } from "../api/aiWorkflows";
import YAMLEditor from "./YAMLEditor";
import type { WorkflowDiagnostic } from "./YAMLEditor";
import ValidationPanel from "./ValidationPanel";
import EditableNameField from "./EditableNameField";
import AIWorkflowChat from "./AIWorkflowChat";
import ReusableGUIWorkflowEditor from "./ReusableGUIWorkflowEditor";
import { generateReusableWorkflowNames, generateTemplateName, analyzeWorkflowContent, generateIntelligentName } from "../utils/workflowNaming";
import { stripWorkflowExtension, validateWorkflowName, normalizeWorkflowStem } from '../utils/workflowFilename';
import { 
  yamlToGui, 
  guiToYaml, 
  WorkflowGUI, 
  ValidationError, 
  DEFAULT_REUSABLE_WORKFLOW_GUI 
} from '../utils/workflowGuiConversion';
import "../styles/TemplateModal.css";
import "../styles/WorkflowsList.css";
import { toast } from '../utils/toast';
import ConfirmDialog from './ConfirmDialog';

// TypeScript interfaces
interface RXWorkflow {
  name: string;
  content: string;
  isReusable: boolean;
  isModified?: boolean;
}

interface BuildType {
  name: string;
  technology: string;
  confidence: number;
}

interface DetectedBuildResult {
  repo: string;
  detected_build_types?: BuildType[];
  error?: string;
}

interface AIChatMessage {
  type: "user" | "ai" | "error";
  message: string;
  workflow_updates?: string[];
  timestamp: string;
}

interface WorkflowTemplate {
  name: string;
  content: string;
}

interface TemplatesByType {
  standard?: WorkflowTemplate;
  reusable?: WorkflowTemplate;
  build?: WorkflowTemplate;
}

interface WorkflowNames {
  reusable: string;
  caller: string;
  technology: string | null;
}

interface RXWorkflowsProps {
  user: string;
  rxworkflows: RXWorkflow[];
  projectName: string;
  projectCode: string | null;
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void;
  addWorkflowToMain: (workflow: { name: string; content: string; isReusable: boolean }) => void;
  onGenerateTemplates: (generateFn: () => Promise<void>, isGenerating: boolean) => void;
  onAddWorkflow: (addFn: () => void) => void;
  onGenerateAIWorkflow: (generateFn: () => Promise<void>, isLoading: boolean) => void;
  selectedRepos: string[];
  detectedBuildTypes: DetectedBuildResult[];
  accountType?: string;
}

// Removed Monaco-specific worker configuration as we're now using CodeMirror

// Separate ReusableWorkflowEditor component to prevent re-render issues
interface ReusableWorkflowEditorProps {
  workflow: RXWorkflow;
  index: number;
  projectCode: string | null;
  modifiedWorkflows: Set<number>;
  isAILoading: boolean;
  onWorkflowChange: (index: number, field: string, value: string) => void;
  onEditWithAI: (index: number) => void;
  onSaveDraft: (index: number) => void;
  onCreateWorkflow: (index: number) => void;
  onDeleteWorkflow: (index: number) => void;
  onCloseEditor: () => void;
}

const ReusableWorkflowEditor: React.FC<ReusableWorkflowEditorProps> = ({
  workflow,
  index,
  projectCode,
  modifiedWorkflows,
  isAILoading,
  onWorkflowChange,
  onEditWithAI,
  onSaveDraft,
  onCreateWorkflow,
  onDeleteWorkflow,
  onCloseEditor
}) => {
  const [editMode, setEditMode] = useState<'yaml' | 'gui'>('yaml');
  const [guiWorkflow, setGuiWorkflow] = useState<WorkflowGUI>(DEFAULT_REUSABLE_WORKFLOW_GUI);
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);
  const [yamlDiagnostics, setYamlDiagnostics] = useState<WorkflowDiagnostic[]>([]);
  const [isConverting, setIsConverting] = useState(false);

  // Initialize GUI workflow from YAML content
  useEffect(() => {
    if (workflow?.content) {
      try {
        const gui = yamlToGui(workflow.content);
        // Ensure workflow_call event is present for reusable workflows
        if (!gui.events.some(e => e.type === 'workflow_call')) {
          gui.events = [{ type: 'workflow_call', inputs: {} }];
        }
        setGuiWorkflow(gui);
      } catch (error) {
        console.warn('Failed to convert YAML to GUI:', error);
      }
    } else {
      // Use default reusable template for new workflows
      setGuiWorkflow({
        ...DEFAULT_REUSABLE_WORKFLOW_GUI,
        name: workflow?.name || 'Reusable Workflow'
      });
    }
  }, [workflow?.content, workflow?.name]);

  const handleModeToggle = (newMode: 'yaml' | 'gui') => {
    if (newMode === editMode) return;
    
    setIsConverting(true);
    
    try {
      if (newMode === 'gui') {
        // Switching to GUI - convert YAML to GUI
        if (workflow?.content) {
          const gui = yamlToGui(workflow.content);
          // Ensure workflow_call event is present for reusable workflows
          if (!gui.events.some(e => e.type === 'workflow_call')) {
            gui.events = [{ type: 'workflow_call', inputs: {} }];
          }
          setGuiWorkflow(gui);
        }
      } else {
        // Switching to YAML - convert GUI to YAML
        const yamlContent = guiToYaml(guiWorkflow);
        onWorkflowChange(index, 'content', yamlContent);
      }
      
      setEditMode(newMode);
    } catch (error) {
      console.error('Failed to convert between modes:', error);
      toast.error('Failed to convert between editing modes. Please check the console for details.');
    } finally {
      setIsConverting(false);
    }
  };

  const handleGUIWorkflowChange = useCallback((updatedGui: WorkflowGUI) => {
    setGuiWorkflow(updatedGui);
    
    // Update workflow name if it changed
    if (updatedGui.name !== workflow?.name) {
      onWorkflowChange(index, 'name', updatedGui.name);
    }
    
    // Convert to YAML and update content
    try {
      const yamlContent = guiToYaml(updatedGui);
      onWorkflowChange(index, 'content', yamlContent);
    } catch (error) {
      console.error('Failed to convert GUI to YAML:', error);
    }
  }, [workflow?.name, onWorkflowChange, index]);

  const handleValidationChange = useCallback((errors: ValidationError[]) => {
    setValidationErrors(errors);
  }, []);

  const hasValidationErrors = validationErrors.some(error => error.severity === 'error');

  return (
    <div className="workflow-editor">
      <div className="workflow-editor-header">
        <div className="editor-title-section">
          <h3>Edit Reusable Workflow</h3>
          {modifiedWorkflows.has(index) && <span className="modified-badge">Unsaved changes</span>}
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
                <button
                  className="action-button ai-button"
                  onClick={() => onEditWithAI(index)}
                  disabled={isAILoading}
                  title="Edit this workflow with AI assistance"
                >
                  {isAILoading ? "⏳ Loading..." : "🤖 Edit with AI"}
                </button>
                
                <button
                  className="action-button save-button"
                  onClick={() => onSaveDraft(index)}
                  disabled={!modifiedWorkflows.has(index)}
                  title="Save workflow to database only (draft)"
                >
                  💾 Save Draft
                </button>
                
                <button
                  className="action-button create-button"
                  onClick={() => onCreateWorkflow(index)}
                  disabled={hasValidationErrors}
                  title={hasValidationErrors ? "Fix validation errors before creating" : "Create workflow in GitHub"}
                >
                  🔄 Create
                </button>
              </>
            )}
            
            <button
              className="action-button delete-button"
              onClick={() => onDeleteWorkflow(index)}
              title="Delete workflow"
            >
              ❌ Delete
            </button>
          </div>
          
          <button 
            className="close-button"
            onClick={onCloseEditor}
            title="Close editor"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="workflow-editor-content">
        <div className="workflow-name-section">
          <label htmlFor={`workflow-name-${index}`}>Workflow Name:</label>
          <EditableNameField
            inputId={`workflow-name-${index}`}
            value={stripWorkflowExtension(workflow.name)}
            onSave={(newValue) =>
              onWorkflowChange(index, 'name', stripWorkflowExtension(newValue))
            }
            validate={validateWorkflowName}
            prefix={`${projectCode ?? 'proj'}-`}
            suffix=".yml"
            placeholder="Enter workflow name"
            maxLength={50}
            ariaLabel="reusable workflow name"
            className="workflow-name-section-field"
            inputClassName="workflow-name-input"
          />
        </div>

        <div className="workflow-code-section">
          <div className="editor-toolbar">
            <span className="editor-label">
              {editMode === 'gui' ? 'Visual Editor' : 'Workflow YAML'}
            </span>
            {isConverting && (
              <span className="converting-indicator">⏳ Converting...</span>
            )}
          </div>
          
          <div className="editor-container">
            {editMode === 'gui' ? (
              <ReusableGUIWorkflowEditor
                workflow={guiWorkflow}
                onChange={handleGUIWorkflowChange}
                onValidationChange={handleValidationChange}
              />
            ) : (
              <div className="yaml-editor-container">
                <YAMLEditor
                  value={workflow.content || ""}
                  onChange={(value: string) => onWorkflowChange(index, 'content', value)}
                  onStructuralDiagnostics={setYamlDiagnostics}
                  height="400px"
                  theme="dark"
                />
                <ValidationPanel diagnostics={yamlDiagnostics} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const RXWorkflows: React.FC<RXWorkflowsProps> = ({ 
  user, 
  rxworkflows, 
  projectName, 
  projectCode, 
  setRXWorkflows, 
  addWorkflowToMain, 
  onGenerateTemplates, 
  onAddWorkflow, 
  onGenerateAIWorkflow, 
  selectedRepos, 
  detectedBuildTypes,
  accountType 
}) => {
  // List/Editor functionality - similar to Workflows.js
  const [selectedWorkflowIndex, setSelectedWorkflowIndex] = useState<number | null>(null);
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [modifiedWorkflows, setModifiedWorkflows] = useState<Set<number>>(new Set());
  
  const [showTemplateModal, setShowTemplateModal] = useState<boolean>(false);
  const [selectedBuildType, setSelectedBuildType] = useState<string>("generic");
  const [generatingTemplates, setGeneratingTemplates] = useState<boolean>(false);
  
  const FREE_PLAN_LIMIT = 5;
  
  // AI Workflow Chat states
  const [showAIChat, setShowAIChat] = useState<boolean>(false);
  const [aiSessionId, setAiSessionId] = useState<string | null>(null);
  const [aiChatHistory, setAiChatHistory] = useState<AIChatMessage[]>([]);
  const [aiSuggestedQuestions, setAiSuggestedQuestions] = useState<string[]>([]);
  const [aiCurrentWorkflowIndex, setAiCurrentWorkflowIndex] = useState<number | null>(null);
  const [isAILoading, setIsAILoading] = useState<boolean>(false);
  const [aiCallerWorkflow, setAiCallerWorkflow] = useState<RXWorkflow | null>(null); // Store the generated caller workflow
  const [pendingDeleteRXIndex, setPendingDeleteRXIndex] = useState<number | null>(null);

  // List/Editor functionality
  const handleSelectWorkflow = (index: number) => {
    setSelectedWorkflowIndex(index);
  };

  const handleCloseEditor = () => {
    setSelectedWorkflowIndex(null);
  };

  // Helper function to generate meaningful workflow names based on build types
  const generateWorkflowNames = React.useCallback((buildTypes: string[]): WorkflowNames => {
    return generateReusableWorkflowNames(buildTypes, projectCode ?? '', { includeActions: true });
  }, [projectCode]);

  const addWorkflow = React.useCallback(() => {
    // Generate a default name for manually created workflows
    const buildTypesArray = detectedBuildTypes ? detectedBuildTypes.flatMap(repo => 
      repo.detected_build_types?.map(bt => bt.technology) || []
    ) : [];
    
    const workflowNames = generateWorkflowNames(buildTypesArray);
    const defaultName = workflowNames.reusable || 'workflow';
    
    setRXWorkflows((prev: RXWorkflow[]) => {
      // Check limit for free accounts using current state
      if (accountType === "free") {
        if (prev.length >= FREE_PLAN_LIMIT) {
          toast.error(`Free plan users can create up to ${FREE_PLAN_LIMIT} reusable workflows per project. You have reached the limit.`);
          return prev; // Return current state without changes
        }
      }
      
      // Make name unique if workflow with same name already exists
      const existingNames = prev.map(w => w.name);
      let uniqueName = defaultName;
      let counter = 1;
      
      while (existingNames.includes(uniqueName)) {
        uniqueName = `${defaultName}_${counter}`;
        counter++;
      }
      
      return [...prev, { name: uniqueName, content: "", isReusable: true }];
    });
  }, [detectedBuildTypes, generateWorkflowNames, accountType]);

  // Helper function to validate prerequisites
  const validateTemplateGeneration = useCallback((): boolean => {
    if (!user) {
      toast.error("User information is required to generate templates");
      return false;
    }

    if (!addWorkflowToMain) {
      toast.error("Unable to access main workflows. Please refresh the page and try again.");
      return false;
    }

    return true;
  }, [user, addWorkflowToMain]);

  // Helper function to process templates and create workflows
  const processTemplates = (templates: any): { newRxWorkflows: RXWorkflow[]; templatesByType: TemplatesByType } => {
    const newRxWorkflows: RXWorkflow[] = [];
    const templatesByType: TemplatesByType = {};

    // Find templates by type
    templates.forEach((template: any) => {
      if (template.name.includes('reusable')) {
        templatesByType.reusable = template;
      } else if (template.name.includes('build')) {
        templatesByType.build = template;
      }
    });

    // Add reusable workflow template
    if (templatesByType.reusable) {
      newRxWorkflows.push({
        name: templatesByType.reusable.name,
        content: templatesByType.reusable.content,
        isReusable: true
      });
    }

    // Add build-specific workflow template
    if (templatesByType.build) {
      newRxWorkflows.push({
        name: templatesByType.build.name,
        content: templatesByType.build.content,
        isReusable: true
      });
    }

    return { newRxWorkflows, templatesByType };
  };

  // Helper function to create template names for display
  const createTemplateNames = useCallback((templatesByType: TemplatesByType) => {
    const safeProjectCode = projectCode ?? '';
    return {
      standard: templatesByType.standard?.name ?? generateTemplateName('standard', selectedBuildType, safeProjectCode),
      reusable: templatesByType.reusable?.name ?? generateTemplateName('reusable', selectedBuildType, safeProjectCode),
      build: templatesByType.build?.name ?? generateTemplateName('build', selectedBuildType, safeProjectCode)
    };
  }, [projectCode, selectedBuildType]);

  // Helper function to create success message
  const createSuccessMessage = (templateNames: { standard: string; reusable: string; build: string }, user: string): string => {
    return `✅ Templates generated successfully!\n\n` +
           `📁 Added to Workflows section:\n` +
           `• ${templateNames.standard}\n\n` +
           `📁 Added to Reusable-Workflows section:\n` +
           `• ${templateNames.reusable}\n` +
           `• ${templateNames.build}\n\n` +
           `🔄 The workflow in "Workflows" will call the workflow in "Reusable-Workflows" using:\n` +
           `uses: ${user}/am-reusable-workflows/.github/workflows/${templateNames.reusable}.yml@develop`;
  };

  const handleGenerateTemplates = useCallback(async () => {
    if (!validateTemplateGeneration()) {
      return;
    }

    setGeneratingTemplates(true);
    try {
      console.log("📌 Generating templates for:", { user, selectedBuildType, projectCode });
      
      const response = await generateWorkflowTemplates(user, selectedBuildType, projectCode);
      
      if (!response || !response.templates) {
        throw new Error("Invalid response from template generation API");
      }

      const { newRxWorkflows, templatesByType } = processTemplates(response.templates);
      
      // Add new reusable workflows to current list
      if (newRxWorkflows.length > 0) {
        setRXWorkflows((prev: RXWorkflow[]) => [...prev, ...newRxWorkflows]);
      }

      // Add main workflow to workflows section (if standard template exists)
      const standardTemplate = response.templates.find((t: any) => !t.name.includes('reusable') && !t.name.includes('build'));
      if (standardTemplate && addWorkflowToMain) {
        addWorkflowToMain({
          name: standardTemplate.name,
          content: standardTemplate.content,
          isReusable: false
        });
      }

      // Create template names for success message
      const templateNames = createTemplateNames(templatesByType);
      
      // Show success message
      toast.success(createSuccessMessage(templateNames, user));
      
      console.log("✅ Templates generated and workflows added successfully");
      
      // Close modal
      setShowTemplateModal(false);
      
    } catch (error) {
      console.error("❌ Error generating templates:", error);
      toast.error(`Failed to generate templates: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setGeneratingTemplates(false);
    }
  }, [user, selectedBuildType, projectCode, setRXWorkflows, addWorkflowToMain, validateTemplateGeneration, createTemplateNames]);

  // const openTemplateModal = async () => {
  //   await loadTemplateTypes();
  //   setShowTemplateModal(true);
  // };

  const handleWorkflowChange = (index: number, field: string, value: string) => {
    setRXWorkflows((prev: RXWorkflow[]) => {
      const updatedWorkflows = [...prev];
      (updatedWorkflows[index] as any)[field] = value;
      return updatedWorkflows;
    });
    
    // Track modifications
    setModifiedWorkflows(prev => new Set(prev).add(index));
  };

  // Enhanced workflows with modification status for list display
  const enhancedWorkflows = rxworkflows.map((workflow, index) => ({
    ...workflow,
    isModified: modifiedWorkflows.has(index)
  }));

  const clearModificationFlag = (index: number) => {
    setModifiedWorkflows(prev => {
      const newSet = new Set(prev);
      newSet.delete(index);
      return newSet;
    });
  };



  // Delete functionality  
  const doDeleteWorkflow = async (index: number) => {
    const workflow = rxworkflows[index];
    if (!workflow) return;

    try {
      console.log(`Deleting reusable workflow: ${workflow.name}`);
      
      // 🔧 FIX: Delete from GitHub first (am-reuseable-workflow repository)
      try {
        await deleteReusableWorkflowFromGitHub(user, workflow.name, projectName);
        console.log(`✅ Deleted reusable workflow "${workflow.name}" from GitHub`);
      } catch (githubError) {
        console.warn(`⚠️ Failed to delete from GitHub (may not exist): ${githubError instanceof Error ? githubError.message : String(githubError)}`);
        // Continue with database deletion even if GitHub deletion fails
      }
      
      // Then delete from database
      await deleteWorkflowFromDatabase(user, projectName, workflow.name);
      console.log(`✅ Deleted reusable workflow "${workflow.name}" from database`);
      
      // Remove from local state
      setRXWorkflows((prev: RXWorkflow[]) => prev.filter((_, i) => i !== index));
      
      // Clear modification flag if it was set
      clearModificationFlag(index);
      
      // Close editor if this workflow was being edited
      if (selectedWorkflowIndex === index) {
        setSelectedWorkflowIndex(null);
      } else if (selectedWorkflowIndex !== null && selectedWorkflowIndex > index) {
        setSelectedWorkflowIndex(selectedWorkflowIndex - 1);
      }
      
      console.log(`✅ Reusable workflow "${workflow.name}" deleted successfully from both GitHub and database`);
    } catch (error) {
      console.error("❌ Error deleting workflow:", error);
      
      // Handle specific error cases - Type guard for axios error
      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as any;
        if (axiosError.response?.status === 401) {
          toast.error("Authentication required. Please log in again.");
          // Redirect to authentication - clear user from localStorage and reload
          localStorage.removeItem("github_user");
          globalThis.setTimeout(() => {
            globalThis.location.reload();
          }, 1500);
        } else if (axiosError.response?.status === 404) {
          toast.error("Reusable workflow or project not found. The workflow may have already been deleted.");
        } else {
          const errorMessage = axiosError.response?.data?.detail ?? (axiosError as Error).message ?? "Unknown error";
          toast.error(`Error deleting reusable workflow: ${errorMessage}`);
        }
      } else {
        const errorMessage = error instanceof Error ? error.message : "Unknown error";
        toast.error(`Error deleting reusable workflow: ${errorMessage}`);
      }
    }
  };

  const deleteWorkflow = (index: number) => {
    setPendingDeleteRXIndex(index);
  };

  // Helper function to ensure unique workflow names
  const ensureUniqueName = (baseName: string, existingNames: string[]): string => {
    let uniqueName = baseName;
    let counter = 1;

    while (existingNames.includes(uniqueName)) {
      uniqueName = `${baseName}_${counter}`;
      counter++;
    }

    return uniqueName;
  };

  const saveDraft = async (index: number) => {
    const workflow = rxworkflows[index];
    if (!workflow) {
      console.error("❌ Workflow not found at index:", index);
      return;
    }

    if (!user || !projectName) {
      toast.error("User and project information are required to save workflow drafts");
      return;
    }

    if (!workflow.name?.trim()) {
      toast.error("Please provide a name for the workflow before saving");
      return;
    }

    if (!workflow.content?.trim()) {
      toast.error("Workflow content cannot be empty");
      return;
    }

    if (modifiedWorkflows.has(index)) {
      try {
        console.log("Saving reusable workflow as draft:", workflow.name);
        const stem = normalizeWorkflowStem(workflow.name) || workflow.name;
        const singleWorkflow = [rxworkflows[index]];
        
        const saveResponse = await saveRxWorkflows(user, projectName, singleWorkflow);
        
        if (!saveResponse) {
          throw new Error("Invalid response from save API");
        }
        
        clearModificationFlag(index);
        toast.success(`Workflow '${stem}.yml' saved as draft.`);
        console.log("📌 Debug: RX Workflow Draft Save Response:", saveResponse);
      } catch (error) {
        console.error("❌ Error saving reusable workflow draft:", error);
        const stem = normalizeWorkflowStem(workflow.name) || workflow.name;
        toast.error(`Failed to save workflow '${stem}.yml' as draft: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    }
  };

  const createWorkflow = async (index: number) => {
    console.log("Creating Workflow");
    try {
      const singleWorkflow = [rxworkflows[index]];
      const saveResponse = await saveRxWorkflows(user, projectName, singleWorkflow);

      if (!saveResponse) {
        throw new Error("Invalid response from GitHub API for saveWorkflows");
      }

      toast.success(`Reusable workflow '${rxworkflows[index].name}' created successfully!`);
      clearModificationFlag(index);
      console.log("📌 Debug: RX Workflow Creation Response:", saveResponse);
    } catch (error) {
      console.error("❌ Error creating reusable workflow:", error);
      toast.error(`Failed to create reusable workflow: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  // Edit workflow with AI
  const editWorkflowWithAI = async (index: number) => {
    const workflow = rxworkflows[index];
    if (!workflow || !workflow.content?.trim()) {
      toast.error("Please ensure the workflow has content before editing with AI");
      return;
    }

    if (!user) {
      toast.error("User information is required for AI workflow editing");
      return;
    }

    setIsAILoading(true);
    try {
      console.log("Editing reusable workflow with AI:", workflow.name);
      
      const response = await editWorkflowWithAIAPI({
        user,
        project_name: projectName,
        project_code: projectCode ?? '',
        workflow_name: workflow.name,
        current_workflow: workflow.content,
        repository_info: {
          selected_repos: selectedRepos,
        },
        build_types: detectedBuildTypes ? detectedBuildTypes.flatMap(repo => 
          repo.detected_build_types?.map(bt => bt.technology) || []
        ) : []
      });

      console.log("AI Edit Response:", response);

      // Set this workflow as current for chat
      setAiCurrentWorkflowIndex(index);
      
      // Set up chat session
      setAiSessionId(response.session_id);
      setAiSuggestedQuestions(response.suggested_questions ?? []);
      
      // Create initial chat message with analysis and suggestions
      setAiChatHistory([{
        type: "ai",
        message: response.workflow_analysis ?? "I've analyzed your reusable workflow. How can I help you improve it?",
        workflow_updates: response.enhancement_suggestions ?? [],
        timestamp: new Date().toISOString()
      }]);
      
      // Open chat modal
      setShowAIChat(true);
      
      console.log("✅ Reusable workflow edited successfully with AI");
      
    } catch (error) {
      console.error("❌ Error editing reusable workflow with AI:", error);
      toast.error(`Failed to edit reusable workflow with AI: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsAILoading(false);
    }
  };

  // AI Workflow Generation
  const generateReusableWorkflowWithAI = useCallback(async () => {
    if (!user) {
      toast.error("User information is required for AI workflow generation");
      return;
    }

    setIsAILoading(true);
    try {
      console.log("Generating AI reusable workflow...");
      
      const response = await generateReusableWorkflowAPI({
        user,
        project_name: projectName,
        project_code: projectCode ?? '',
        repository_info: {
          selected_repos: selectedRepos,
        },
        build_types: detectedBuildTypes ? detectedBuildTypes.flatMap(repo => 
          repo.detected_build_types?.map(bt => bt.technology) || []
        ) : []
      });

      console.log("AI Reusable Workflow Response:", response);

      if (!response.reusable_workflow_yaml) {
        throw new Error("No reusable workflow generated");
      }

      // Update workflows using functional setState to avoid dependency on rxworkflows
      let currentWorkflowIndex: number = -1;
      let tempCallerName: string = "";
      
      setRXWorkflows((prev: RXWorkflow[]) => {
        // Get existing workflow names for uniqueness check
        const existingNames = prev.map(w => w.name);
        
        // Use simple temporary names that will be replaced with intelligent names later
        const tempReusableName = ensureUniqueName("ai_reusable_workflow", existingNames);
        tempCallerName = ensureUniqueName("ai_caller_workflow", [...existingNames, tempReusableName]);
        
        // Check for existing blank template first
        const blankWorkflowIndex = prev.findIndex(w => 
          (!w.name || w.name.trim() === "") && (!w.content || w.content.trim() === "")
        );
        
        let updatedRXWorkflows: RXWorkflow[];
        
        if (blankWorkflowIndex !== -1) {
          // Fill existing blank template
          updatedRXWorkflows = [...prev];
          updatedRXWorkflows[blankWorkflowIndex] = {
            ...updatedRXWorkflows[blankWorkflowIndex],
            name: tempReusableName,
            content: response.reusable_workflow_yaml,
            isReusable: true
          };
          currentWorkflowIndex = blankWorkflowIndex;
        } else {
          // Create new reusable workflow if no blank template exists
          const newReusableWorkflow: RXWorkflow = {
            name: tempReusableName,
            content: response.reusable_workflow_yaml,
            isReusable: true
          };
          updatedRXWorkflows = [...prev, newReusableWorkflow];
          currentWorkflowIndex = updatedRXWorkflows.length - 1;
        }
        
        return updatedRXWorkflows;
      });
      
      // Set current workflow index after state update
      setAiCurrentWorkflowIndex(currentWorkflowIndex);
      
      // Store the caller workflow for later use with temporary name
      setAiCallerWorkflow({
        name: tempCallerName,
        content: response.caller_workflow_yaml,
        isReusable: false
      });
      
      // Set up chat session
      setAiSessionId(response.session_id);
      setAiSuggestedQuestions(response.suggested_questions ?? []);
      setAiChatHistory([{
        type: "ai",
        message: response.explanation,
        workflow_updates: ["Generated initial reusable CI/CD workflow", "Generated companion caller workflow"],
        timestamp: new Date().toISOString()
      }]);
      
      console.log("✅ AI reusable workflow generated successfully");
      setShowAIChat(true);
      
    } catch (error) {
      console.error("❌ Error generating AI reusable workflow:", error);
      toast.error(`Failed to generate AI reusable workflow: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsAILoading(false);
    }
  }, [user, projectName, projectCode, selectedRepos, detectedBuildTypes]);

  // AI Chat functionality
  const handleAIChatMessage = async (message: string) => {
    if (!aiSessionId || aiCurrentWorkflowIndex === null) {
      console.error("No AI session or workflow selected");
      return;
    }

    const userMessage: AIChatMessage = {
      type: "user",
      message,
      timestamp: new Date().toISOString()
    };

    setAiChatHistory(prev => [...prev, userMessage]);

    try {
      console.log("Sending chat message:", message);
      const response = await sendChatMessage(aiSessionId, message);
      
      console.log("AI Chat Response:", response);

      // Update workflow if provided
      if (response.updated_workflow && aiCurrentWorkflowIndex !== null) {
        setRXWorkflows((prev: RXWorkflow[]) => {
          const updatedRXWorkflows = [...prev];
          // Create new object instead of mutating
          updatedRXWorkflows[aiCurrentWorkflowIndex] = {
            ...updatedRXWorkflows[aiCurrentWorkflowIndex],
            content: response.updated_workflow!
          };
          return updatedRXWorkflows;
        });
      }

      const aiMessage: AIChatMessage = {
        type: "ai",
        message: response.response_message,
        workflow_updates: response.workflow_updates,
        timestamp: new Date().toISOString()
      };

      setAiChatHistory(prev => [...prev, aiMessage]);
      setAiSuggestedQuestions(response.suggested_questions ?? []);

    } catch (error) {
      console.error("❌ Error in AI chat:", error);
      const errorMessage: AIChatMessage = {
        type: "error",
        message: `Error: ${error instanceof Error ? error.message : 'Unknown error occurred'}`,
        timestamp: new Date().toISOString()
      };
      setAiChatHistory(prev => [...prev, errorMessage]);
    }
  };

  const handleCloseAIChat = () => {
    // Check if there's an AI workflow in progress
    if (aiCurrentWorkflowIndex !== null && aiSessionId) {
      // This is finishing the workflow successfully
      handleFinishAIWorkflow();
    } else {
      // This is canceling without a workflow
      handleCancelAIWorkflow();
    }
  };
  const handleFinishAIWorkflow = () => {
    if (aiCurrentWorkflowIndex === null) {
      console.error("No current AI workflow to finalize");
      return;
    }

    try {
      // Update workflow name using functional setState to avoid rxworkflows dependency
      let finalReusableName = "";
      let uniqueReusableName = "";
      
      setRXWorkflows((prev: RXWorkflow[]) => {
        const currentWorkflow = prev[aiCurrentWorkflowIndex];
        if (!currentWorkflow) {
          console.error("Current workflow not found");
          return prev;
        }
        
        // Analyze the workflow content to generate intelligent name
        const workflowAnalysis = analyzeWorkflowContent(currentWorkflow.content);
        finalReusableName = generateIntelligentName(workflowAnalysis, {
          projectCode: projectCode ?? '',
          includeProjectCode: false, // PrefixedInput handles the prefix
          maxLength: 40
        });
        
        // Get existing workflow names to ensure uniqueness (excluding current workflow)
        const existingNames = prev
          .filter((_, index) => index !== aiCurrentWorkflowIndex)
          .map(w => w.name);
        
        uniqueReusableName = ensureUniqueName(finalReusableName, existingNames);
        
        // Update the reusable workflow name - create new object instead of mutating
        const updatedRXWorkflows = [...prev];
        updatedRXWorkflows[aiCurrentWorkflowIndex] = {
          ...updatedRXWorkflows[aiCurrentWorkflowIndex],
          name: uniqueReusableName
        };
        return updatedRXWorkflows;
      });
      
      // Also update the caller workflow name if it exists
      if (aiCallerWorkflow && uniqueReusableName) {
        // Caller workflow should have the same base name as reusable workflow with "_caller" appended
        const finalCallerName = `${uniqueReusableName}_caller`;
        const existingCallerNames = [uniqueReusableName]; // Only exclude the reusable workflow name
        const uniqueCallerName = ensureUniqueName(finalCallerName, existingCallerNames);
        
        // Create updated caller workflow object with the new name
        const updatedCallerWorkflow: RXWorkflow = {
          ...aiCallerWorkflow,
          name: uniqueCallerName
        };
        
        // Add caller workflow to main workflows section
        if (addWorkflowToMain) {
          addWorkflowToMain({
            name: updatedCallerWorkflow.name,
            content: updatedCallerWorkflow.content,
            isReusable: false
          });
        }
        
        console.log(`✅ Added caller workflow "${uniqueCallerName}" to main workflows`);
      }
      
      // Clear AI session state
      setShowAIChat(false);
      setAiSessionId(null);
      setAiChatHistory([]);
      setAiSuggestedQuestions([]);
      setAiCurrentWorkflowIndex(null);
      setAiCallerWorkflow(null);
      
      console.log(`✅ AI workflow session completed. Reusable workflow named: "${uniqueReusableName}"`);
      
      // Show success message
      toast.success(
        `AI Workflow Generation Complete! Reusable Workflow: "${uniqueReusableName}" created. Caller Workflow: "${aiCallerWorkflow?.name ?? 'Not available'}" added to main Workflows section.`
      );
      
    } catch (error) {
      console.error("❌ Error finalizing AI workflow:", error);
      toast.error(`Error finalizing AI workflow: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };


  const handleCancelAIWorkflow = () => {
    if (aiCurrentWorkflowIndex !== null) {
      // Remove the AI-generated workflow from the list
      setRXWorkflows((prev: RXWorkflow[]) => prev.filter((_, index) => index !== aiCurrentWorkflowIndex));
    }
    
    // Clear AI session state
    setShowAIChat(false);
    setAiSessionId(null);
    setAiChatHistory([]);
    setAiSuggestedQuestions([]);
    setAiCurrentWorkflowIndex(null);
    setAiCallerWorkflow(null);
    
    console.log("AI workflow generation cancelled");
  };

  const updateCurrentAIWorkflow = (updatedWorkflow: string) => {
    if (aiCurrentWorkflowIndex !== null) {
      setRXWorkflows((prev: RXWorkflow[]) => {
        const updatedRXWorkflows = [...prev];
        // Create new object instead of mutating
        updatedRXWorkflows[aiCurrentWorkflowIndex] = {
          ...updatedRXWorkflows[aiCurrentWorkflowIndex],
          content: updatedWorkflow
        };
        return updatedRXWorkflows;
      });
    }
  };

  // Effect hooks for parent callbacks
  React.useEffect(() => {
    if (onGenerateTemplates) {
      onGenerateTemplates(handleGenerateTemplates, generatingTemplates);
    }
  }, [generatingTemplates, onGenerateTemplates]);

  React.useEffect(() => {
    if (onAddWorkflow) {
      onAddWorkflow(addWorkflow);
    }
  }, [onAddWorkflow]);

  React.useEffect(() => {
    if (onGenerateAIWorkflow) {
      onGenerateAIWorkflow(generateReusableWorkflowWithAI, isAILoading);
    }
  }, [isAILoading, onGenerateAIWorkflow]);

  return (
    <>
      {/* Reusable workflow count display for free accounts */}
      {accountType === "free" && (
        <div className="plan-usage-notice">
          <strong>Free Plan:</strong> You can create up to {FREE_PLAN_LIMIT} reusable workflows per project.
          <span> Currently using: {rxworkflows.length}/{FREE_PLAN_LIMIT}</span>
        </div>
      )}
      
      {/* Workflow List */}
      <div className="workflows-container">
        <div className={`workflows-list ${isCollapsed ? 'collapsed' : 'expanded'}`}>
          <div className="workflows-list-header">
            <div className="workflows-list-header-content">
              {!isCollapsed && <h4>🔄 Reusable Workflows</h4>}
              {isCollapsed && <h4>🔄</h4>}
            </div>
            <button 
              className="workflows-list-toggle"
              onClick={() => setIsCollapsed(!isCollapsed)}
              title={isCollapsed ? 'Expand reusable workflows list' : 'Collapse reusable workflows list'}
            >
              <span className="workflows-list-toggle-arrow">
                {isCollapsed ? '►' : '◄'}
              </span>
            </button>
          </div>
          {!isCollapsed && (
            <div className="workflows-list-container">
              {enhancedWorkflows.length === 0 ? (
                <div className="empty-workflow-list">
                  <p>No reusable workflows created yet</p>
                  <p style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>
                    Click "Add Workflow" to create your first reusable workflow
                  </p>
                </div>
              ) : (
                <ul className="workflow-items">
                  {enhancedWorkflows.map((workflow, index) => (
                    <li key={index} className="workflow-item-wrapper">
                      <button 
                        className={`workflow-item ${selectedWorkflowIndex === index ? 'selected' : ''}`}
                        onClick={() => handleSelectWorkflow(index)}
                      >
                        <div className="workflow-item-content">
                          <div className="workflow-name">
                            {workflow.name || `Untitled Reusable Workflow ${index + 1}`}
                            {workflow.name && (
                              <span className="workflow-prefix">
                                AM_{(projectCode ?? '').toUpperCase()}_
                              </span>
                            )}
                          </div>
                          
                          {/* Workflow Type Display */}
                          <div className="workflow-status">
                            <div className="repo-status">
                              <span className="repo-name">Type:</span>
                              <span className="status-icon" style={{ color: "var(--success-color)" }}>
                                Reusable
                              </span>
                            </div>
                          </div>
                        </div>
                        
                        {/* Modified indicator */}
                        {workflow.isModified && (
                          <div className="modified-indicator" title="Unsaved changes">
                            •
                          </div>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Workflow Editor */}
        {selectedWorkflowIndex !== null && rxworkflows[selectedWorkflowIndex] && (
          <ReusableWorkflowEditor 
            workflow={rxworkflows[selectedWorkflowIndex]} 
            index={selectedWorkflowIndex}
            projectCode={projectCode}
            modifiedWorkflows={modifiedWorkflows}
            isAILoading={isAILoading}
            onWorkflowChange={handleWorkflowChange}
            onEditWithAI={editWorkflowWithAI}
            onSaveDraft={saveDraft}
            onCreateWorkflow={createWorkflow}
            onDeleteWorkflow={deleteWorkflow}
            onCloseEditor={handleCloseEditor}
          />
        )}
      </div>

      {/* AI Workflow Chat Modal */}
      {showAIChat && aiCurrentWorkflowIndex !== null && (
        <AIWorkflowChat
          isOpen={showAIChat}
          onClose={handleCloseAIChat}
          sessionId={aiSessionId ?? ""}
          currentWorkflow={rxworkflows[aiCurrentWorkflowIndex]?.content || ''}
          onWorkflowUpdate={updateCurrentAIWorkflow}
          onSendMessage={handleAIChatMessage}
          chatHistory={aiChatHistory}
          suggestedQuestions={aiSuggestedQuestions}
          isLoading={false}
        />
      )}

      {/* Template Generation Modal */}
      {showTemplateModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h2>🚀 Generate Workflow Templates</h2>
              <button 
                className="modal-close" 
                onClick={() => setShowTemplateModal(false)}
                disabled={generatingTemplates}
              >
                ✕
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label htmlFor="template-build-type">Build Type:</label>
                <select
                  id="template-build-type"
                  value={selectedBuildType}
                  onChange={(e) => setSelectedBuildType(e.target.value)}
                  className="input"
                >
                  <option value="generic">Generic - Basic CI/CD workflow</option>
                  <option value="node">Node.js - JavaScript/TypeScript projects</option>
                  <option value="python">Python - Python applications</option>
                  <option value="java">Java - Java/Maven/Gradle projects</option>
                  <option value="dotnet">.NET - C#/.NET applications</option>
                  <option value="docker">Docker - Containerized applications</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="template-user-org">User/Organization:</label>
                <input 
                  id="template-user-org"
                  type="text" 
                  value={user || ""} 
                  disabled 
                  className="input"
                />
              </div>

              <div className="form-group">
                <label htmlFor="template-project-code">Project Code:</label>
                <input 
                  id="template-project-code"
                  type="text" 
                  value={projectCode ?? ""} 
                  disabled 
                  className="input"
                />
              </div>
            </div>
            <div className="modal-footer">
              <button 
                className="cancelButton" 
                onClick={() => setShowTemplateModal(false)}
                disabled={generatingTemplates}
              >
                Cancel
              </button>
              <button 
                className="createButton" 
                onClick={handleGenerateTemplates}
                disabled={generatingTemplates}
              >
                {generatingTemplates ? "Generating..." : "🚀 Generate Templates"}
              </button>
            </div>
          </div>
        </div>
      )}

      {pendingDeleteRXIndex !== null && (
        <ConfirmDialog
          open={true}
          title="Delete reusable workflow?"
          description={`This will permanently delete "${rxworkflows[pendingDeleteRXIndex]?.name}" from both GitHub and the database.`}
          confirmLabel="Delete"
          destructive
          onConfirm={() => { const idx = pendingDeleteRXIndex; setPendingDeleteRXIndex(null); doDeleteWorkflow(idx); }}
          onCancel={() => setPendingDeleteRXIndex(null)}
        />
      )}
    </>
  );
};

export default RXWorkflows;
