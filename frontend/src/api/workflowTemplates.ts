import apiClient from "./apiClient";
import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

export interface TemplateTypesResponse {
  template_types: Record<string, string>;
}

export interface WorkflowTemplatesResponse {
  templates: Array<{ name: string; content: string }>;
}

export const getTemplateTypes = async (): Promise<TemplateTypesResponse> => {
  try {
    const response = await apiClient.get(`${BACKEND_URL}/api/workflow-templates/types`);
    return response.data;
  } catch (error) {
    console.error("❌ Error getting template types:", error);
    throw error;
  }
};

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

export const generateStandardTemplate = async (
  userOrg: string,
  buildType = "generic",
  projectCode: string | null = null
): Promise<unknown> => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/workflow-templates/standard`, {
      user_org: userOrg,
      build_type: buildType,
      project_code: projectCode,
    });
    return response.data;
  } catch (error) {
    console.error("❌ Error generating standard template:", error);
    throw error;
  }
};

export const generateReusableTemplate = async (
  userOrg: string,
  buildType = "generic",
  projectCode: string | null = null
): Promise<unknown> => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/workflow-templates/reusable`, {
      user_org: userOrg,
      build_type: buildType,
      project_code: projectCode,
    });
    return response.data;
  } catch (error) {
    console.error("❌ Error generating reusable template:", error);
    throw error;
  }
};
