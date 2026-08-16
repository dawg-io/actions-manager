import { detectBuildTypes, suggestWorkflow } from '../api/repos';
import { generateWorkflowTemplates } from '../api/workflowTemplates';
import { generateBuildDetectionName, generateTemplateName } from './workflowNaming';
import { normalizeWorkflowStem, setWorkflowYamlName } from './workflowFilename';
import { DetectedBuildResult, BuildType, Workflow, RXWorkflow, WorkflowTemplate, TemplatesByType } from '../types/workflow';
import { toast } from './toast';

// Build Detection functionality
export const detectBuildTypesForRepos = async (
  selectedRepos: string[],
  user: string,
  setDetectedBuildTypes: (types: DetectedBuildResult[]) => void,
  setShowDetectionResults: (show: boolean) => void,
  setShowDetectionResultsInModal: (show: boolean) => void
): Promise<void> => {
  if (!selectedRepos || selectedRepos.length === 0) {
    toast.error("Please select repositories first to detect build types.");
    return;
  }

  setDetectedBuildTypes([]);
  
  try {
    const detectionPromises = selectedRepos
      .filter(repo => repo && typeof repo === 'string' && repo.includes('/'))
      .map(async (repo): Promise<DetectedBuildResult> => {
        const [owner, repoName] = repo.split('/');
        const result = await detectBuildTypes(user, owner, repoName);
        return { repo, ...result };
      });

    const results = await Promise.all(detectionPromises);
    setDetectedBuildTypes(results);
    setShowDetectionResults(false); // Don't show the old separate results
    setShowDetectionResultsInModal(true); // Show results in modal instead
    console.log("📌 Debug: Build types detected:", results);
  } catch (error) {
    console.error("❌ Error detecting build types:", error);
    toast.error("Error detecting build types. Please try again.");
  }
};

// Add workflow from build detection
export const addWorkflowFromDetection = async (
  repo: string,
  buildType: BuildType,
  workflowName: string,
  workflows: Workflow[],
  projectCode: string | null,
  user: string,
  setWorkflows: (workflows: Workflow[]) => void,
  setSelectedWorkflowId: (id: string) => void,
  setShowWorkflowCreationDialog: (show: boolean) => void,
  setWorkflowCreationType: (type: 'regular' | 'reusable' | null) => void,
  setShowDetectionResultsInModal: (show: boolean) => void,
  setShowDetectionResults: (show: boolean) => void,
  setDetectedBuildTypes: (types: DetectedBuildResult[]) => void
): Promise<void> => {
  try {
    // Validate input parameters
    if (!repo || typeof repo !== 'string') {
      throw new Error('Invalid repository name');
    }
    
    if (!buildType || !buildType.name) {
      throw new Error('Invalid build type');
    }
    
    const repoParts = repo.split('/');
    if (repoParts.length !== 2) {
      throw new Error('Repository name must be in format "owner/repo"');
    }
    
    const [owner, repoName] = repoParts;
    console.log("📌 Debug: suggestWorkflow call parameters:", { user, owner, repoName, buildType: buildType.name });
    const workflowResult = await suggestWorkflow(user, owner, repoName, buildType.name as any);
    
    // Check if the API returned an error object instead of YAML string
    if (!workflowResult || typeof workflowResult !== 'string') {
      // `!workflowResult` also matches the empty string, so this branch is not
      // narrowed to the error object by the outer guard alone.
      if (typeof workflowResult === 'object' && workflowResult?.error) {
        throw new Error(`Failed to generate workflow: ${workflowResult.error}`);
      } else {
        throw new Error('Failed to generate workflow: Invalid response from server');
      }
    }
    
    // Validate that we got a non-empty YAML string
    if (!workflowResult.trim()) {
      throw new Error('Failed to generate workflow: Empty response from server');
    }
    
    const finalWorkflowName = normalizeWorkflowStem(workflowName) || generateBuildDetectionName(buildType.technology, repo, projectCode || '');
    const newWorkflow: Workflow = {
      name: finalWorkflowName,
      content: setWorkflowYamlName(workflowResult, finalWorkflowName),
      isReusable: false,
      isModified: true
    };
    
    const newWorkflows = [...workflows, newWorkflow];
    setWorkflows(newWorkflows);
    setSelectedWorkflowId(`regular-${newWorkflows.length - 1}`);
    
    // Close the modal and reset state
    setShowWorkflowCreationDialog(false);
    setWorkflowCreationType(null);
    setShowDetectionResultsInModal(false);
    setShowDetectionResults(false);
    setDetectedBuildTypes([]);
    
    console.log(`✅ Added workflow for ${buildType.technology} in ${repo}`);
    toast.success(`Workflow "${finalWorkflowName}" added to the project.`);
  } catch (error: any) {
    console.error("❌ Error adding workflow from detection:", error);
    toast.error(`Failed to create workflow: ${error.message}`);
  }
};

// Generate Templates functionality
export const generateTemplates = async (
  selectedRepos: string[],
  detectedBuildTypes: DetectedBuildResult[],
  projectCode: string | null,
  user: string,
  setTemplatesByType: (templates: TemplatesByType) => void,
  setShowTemplateModal: (show: boolean) => void
): Promise<void> => {
  if (!selectedRepos || selectedRepos.length === 0) {
    toast.error("Please select repositories first to generate workflow templates.");
    return;
  }

  try {
    const buildTypes = detectedBuildTypes.length > 0 ? 
      detectedBuildTypes.flatMap(result => result.detected_build_types || []) :
      [];

    const templates = await generateWorkflowTemplates(
      user, 
      buildTypes.length > 0 ? buildTypes[0].technology : "generic", 
      projectCode
    );

    if (templates && templates.templates) {
      // Process templates into categories
      const templatesByType: TemplatesByType = {};
      
      templates.templates.forEach((template: any) => {
        if (template.name.includes('reusable')) {
          templatesByType.reusable = template;
        } else if (template.name.includes('build')) {
          templatesByType.build = template;
        } else {
          templatesByType.standard = template;
        }
      });

      setTemplatesByType(templatesByType);
    } else {
      setTemplatesByType({});
    }
    setShowTemplateModal(true);
    
    console.log("✅ Templates generated successfully");
  } catch (error: any) {
    console.error("❌ Error generating templates:", error);
    toast.error(`Failed to generate templates: ${error.message}`);
  }
};

// Template selection handler
export const selectTemplate = (
  template: WorkflowTemplate,
  isReusable: boolean = false,
  projectName: string,
  workflows: Workflow[],
  setWorkflows: (workflows: Workflow[]) => void,
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void,
  setSelectedWorkflowId: (id: string) => void,
  setShowTemplateModal: (show: boolean) => void,
  workflowName: string | null = null
): void => {
  const templateName = normalizeWorkflowStem(workflowName || '') || generateTemplateName(template.name, projectName);
  const templateContent = setWorkflowYamlName(template.content, templateName);
  
  if (isReusable) {
    const newWorkflow: RXWorkflow = {
      name: templateName,
      content: templateContent,
      isReusable: true,
      isModified: true
    };
    
    setRXWorkflows(prev => {
      const newWorkflows = Array.isArray(prev) ? [...prev, newWorkflow] : [newWorkflow];
      setSelectedWorkflowId(`reusable-${newWorkflows.length - 1}`);
      return newWorkflows;
    });
  } else {
    const newWorkflow: Workflow = {
      name: templateName,
      content: templateContent,
      isReusable: false,
      isModified: true
    };
    
    const newWorkflows = [...workflows, newWorkflow];
    setWorkflows(newWorkflows);
    setSelectedWorkflowId(`regular-${newWorkflows.length - 1}`);
  }
  
  setShowTemplateModal(false);
  toast.success(`Template "${template.name}" added to the project.`);
};
