import apiClient from "./apiClient";
import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

export interface WorkflowTemplatesResponse {
  templates: Array<{ name: string; content: string }>;
}

export const generateWorkflowTemplates = async (
  userOrg: string,
  buildType = "generic",
  projectCode: string | null = null
): Promise<WorkflowTemplatesResponse> => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/workflow-templates/generate`, {
      user_org: userOrg,
      build_type: buildType,
      project_code: projectCode,
    });
    return response.data;
  } catch (error) {
    console.error("❌ Error generating workflow templates:", error);
    throw error;
  }
};
