import { generateWorkflowWithAI as generateAIWorkflow, generateReusableWorkflowWithAI as generateReusableWorkflowAPI, sendChatMessage, editWorkflowWithAI as editAIWorkflow, checkAIIntegration } from '../api/aiWorkflows';
import { generateAIWorkflowName, generateReusableWorkflowNames } from './workflowNaming';
import { Workflow, RXWorkflow, DetectedBuildResult, AIChatMessage, AIWorkflowResponse, AIEditResponse, AIWorkflowAction } from '../types/workflow';
import { normalizeWorkflowStem, setWorkflowYamlName } from './workflowFilename';
import { toast } from './toast';

// Generate AI Workflow for regular workflows
export const generateRegularWorkflowWithAI = async (
  selectedRepos: string[],
  projectName: string,
  projectCode: string | null,
  detectedBuildTypes: DetectedBuildResult[],
  workflows: Workflow[],
  workflowName: string,
  user: string,
  setWorkflows: (workflows: Workflow[]) => void,
  setAISessionId: (id: string) => void,
  setSelectedWorkflowId: (id: string) => void,
  setAIChatMessages: (messages: AIChatMessage[]) => void,
  setShowAIChat: (show: boolean) => void
): Promise<void> => {
  if (!selectedRepos || selectedRepos.length === 0) {
    toast.error("Please select repositories first to generate AI workflows.");
    return;
  }

  try {
    // Check AI integration first
    const isAIWorking = await checkAIIntegration();
    if (!isAIWorking) {
      toast.error("AI integration is not configured. Please check that an OpenAI API key is set.");
      return;
    }

    const buildTypes = detectedBuildTypes.length > 0 ? 
      detectedBuildTypes.flatMap(result => result.detected_build_types || []) :
      [];

    // Prepare request data to match the correct API format
    const requestData = {
      user: user,
      project_name: projectName,
      project_code: projectCode || '',
      repository_info: {
        selected_repos: selectedRepos,
        repo_count: selectedRepos.length
      },
      build_types: buildTypes.map(bt => bt.technology),
      user_requirements: `Generate a CI/CD workflow for project ${projectName}`
    };

    console.log("📌 Debug: Generating AI workflow with data:", requestData);

    const response: AIWorkflowResponse = await generateAIWorkflow(requestData);
    
    if (response && response.workflow_yaml) {
      setAISessionId(response.session_id);
      
      const buildTypesArray = buildTypes.map(bt => bt.technology);
      const intelligentName = normalizeWorkflowStem(workflowName) || generateAIWorkflowName(response.workflow_yaml, projectName, buildTypesArray);
      
      const newWorkflow: Workflow = {
        name: intelligentName,
        content: setWorkflowYamlName(response.workflow_yaml, intelligentName),
        isReusable: false,
        isModified: true
      };
      
      const newWorkflows = [...workflows, newWorkflow];
      setWorkflows(newWorkflows);
      setSelectedWorkflowId(`regular-${newWorkflows.length - 1}`);
      
      const welcomeMessage: AIChatMessage = {
        type: "ai",
        message: response.explanation || "I've generated a comprehensive CI/CD workflow based on your repositories and requirements.",
        workflow_updates: [intelligentName],
        timestamp: new Date().toISOString()
      };
      
      setAIChatMessages([welcomeMessage]);
      setShowAIChat(true);
      
      console.log("✅ AI workflow generated successfully");
      toast.success("AI workflow generated. Check the AI chat for details and suggestions.");
    }
  } catch (error: any) {
    console.error("❌ Error generating AI workflow:", error);
    toast.error(`Failed to generate AI workflow: ${error.message}`);
  }
};

// Generate Reusable Workflow with AI
export const generateReusableWorkflowWithAI = async (
  selectedRepos: string[],
  projectName: string,
  projectCode: string | null,
  detectedBuildTypes: DetectedBuildResult[],
  workflowName: string,
  user: string,
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void,
  setAISessionId: (id: string) => void,
  setSelectedWorkflowId: (id: string) => void,
  setAIChatMessages: (messages: AIChatMessage[]) => void,
  setShowAIChat: (show: boolean) => void
): Promise<void> => {
  if (!selectedRepos || selectedRepos.length === 0) {
    toast.error("Please select repositories first to generate reusable workflows.");
    return;
  }

  try {
    const buildTypes = detectedBuildTypes.length > 0 ? 
      detectedBuildTypes.flatMap(result => result.detected_build_types || []) :
      [];

    const response = await generateReusableWorkflowAPI({
      user,
      project_name: projectName,
      project_code: projectCode || '',
      repository_info: {
        selected_repos: selectedRepos,
      },
      build_types: buildTypes.map(bt => bt.technology)
    });
    
    if (response && response.reusable_workflow_yaml) {
      setAISessionId(response.session_id);
      
      const workflowNames = generateReusableWorkflowNames(buildTypes.map(bt => bt.technology), projectCode || '', { includeActions: true });
      const intelligentName = normalizeWorkflowStem(workflowName) || workflowNames.reusable;
      
      const newWorkflow: RXWorkflow = {
        name: intelligentName,
        content: setWorkflowYamlName(response.reusable_workflow_yaml, intelligentName),
        isReusable: true,
        isModified: true
      };
      
      setRXWorkflows(prev => {
        const newWorkflows = Array.isArray(prev) ? [...prev, newWorkflow] : [newWorkflow];
        setSelectedWorkflowId(`reusable-${newWorkflows.length - 1}`);
        return newWorkflows;
      });
      
      const welcomeMessage: AIChatMessage = {
        type: "ai",
        message: response.explanation || "I've generated a reusable workflow that can be called by other workflows across your repositories.",
        workflow_updates: [intelligentName],
        timestamp: new Date().toISOString()
      };
      
      setAIChatMessages([welcomeMessage]);
      setShowAIChat(true);
      
      console.log("✅ AI reusable workflow generated successfully");
      toast.success("AI reusable workflow generated. Check the AI chat for details and suggestions.");
    }
  } catch (error: any) {
    console.error("❌ Error generating AI reusable workflow:", error);
    toast.error(`Failed to generate AI reusable workflow: ${error.message}`);
  }
};

// Edit with AI functionality
export const editWithAI = async (
  index: number,
  type: 'regular' | 'reusable',
  action: AIWorkflowAction,
  workflows: Workflow[],
  rxworkflows: RXWorkflow[],
  user: string,
  projectName: string,
  projectCode: string | null,
  selectedRepos: string[],
  detectedBuildTypes: DetectedBuildResult[],
  optionalInstruction: string,
  setAISessionId: (id: string) => void,
  setAIChatMessages: (messages: AIChatMessage[] | ((prev: AIChatMessage[]) => AIChatMessage[])) => void,
  setShowAIChat: (show: boolean) => void,
  setEditingWorkflowIndex: (index: number | null) => void,
  setEditingWorkflowType: (type: 'regular' | 'reusable' | null) => void
): Promise<AIEditResponse | null> => {
  const workflow = type === 'regular' ? workflows[index] : rxworkflows[index];
  
  if (!workflow) {
    toast.error("Please select a workflow before using AI actions.");
    return null;
  }

  if (action !== 'generate' && !workflow.content) {
    toast.error("Please provide workflow content before editing with AI.");
    return null;
  }

  if (action === 'generate' && (!selectedRepos || selectedRepos.length === 0)) {
    toast.error("Please select repositories first to generate AI workflows.");
    return null;
  }

  setEditingWorkflowIndex(index);
  setEditingWorkflowType(type);

  try {
    // Check AI integration first
    const isAIWorking = await checkAIIntegration();
    if (!isAIWorking) {
      toast.error("AI integration is not configured. Please check that an OpenAI API key is set.");
      return null;
    }

    // Prepare request data for editing
    const requestData = {
      user: user,
      project_name: projectName,
      project_code: projectCode || '',
      workflow_name: workflow.name || `${type}-workflow-${index + 1}`,
      current_workflow: workflow.content || '',
      action,
      optional_instruction: optionalInstruction,
      repository_info: {
        selected_repos: selectedRepos,
        repo_count: selectedRepos.length
      },
      build_types: detectedBuildTypes.flatMap(repo => 
        repo.detected_build_types?.map(bt => bt.technology) || []
      )
    };

    console.log("📌 Debug: Editing workflow with AI:", requestData);

    const response = await editAIWorkflow(requestData);

    if (response?.updated_workflow) {
      setAISessionId(response.session_id);
      console.log("✅ AI workflow action completed");
      return response;
    }

    toast.error("AI did not return a workflow YAML preview.");
    return null;
  } catch (error: any) {
    console.error("❌ Error editing workflow with AI:", error);
    toast.error(`Failed to analyze workflow with AI: ${error.message}`);
    return null;
  }
};

// AI Chat message handler
export const handleAIChatMessage = async (
  message: string,
  aiSessionId: string,
  selectedWorkflowContent: string | undefined,
  setAIChatMessages: (messages: AIChatMessage[] | ((prev: AIChatMessage[]) => AIChatMessage[])) => void,
  handleWorkflowChange?: (field: string, value: string) => void
): Promise<void> => {
  const newUserMessage: AIChatMessage = {
    type: "user",
    message,
    timestamp: new Date().toISOString()
  };
  setAIChatMessages(prev => [...prev, newUserMessage]);
  
  const response = await sendChatMessage(
    aiSessionId,
    message,
    selectedWorkflowContent
  );
  
  const aiResponse: AIChatMessage = {
    type: "ai",
    message: response.response_message,
    workflow_updates: response.workflow_updates,
    timestamp: new Date().toISOString()
  };
  
  setAIChatMessages(prev => [...prev, aiResponse]);
  
  // Update workflow if AI provided updates
  if (response.updated_workflow && handleWorkflowChange) {
    handleWorkflowChange('content', response.updated_workflow);
  }
};
