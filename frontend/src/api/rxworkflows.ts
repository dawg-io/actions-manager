import { AxiosResponse } from "axios";
import apiClient from "./apiClient";
import config from "../config";
import { RXWorkflow } from "../types/workflow";

const BACKEND_URL = config.BACKEND_URL;

// API response interfaces
interface SaveRxWorkflowsResponse {
  success?: boolean;
  message?: string;
  project_code?: string;
  pr_state?: string;
  [key: string]: any;
}

/** Shape of a single workflow entry sent to the backend save API. */
interface WorkflowSavePayload {
  name: string;
  content: string;
  isReusable?: boolean;
  original_name?: string;
}

export const saveRxWorkflows = async (
  user: string, 
  projectName: string, 
  rxworkflows: RXWorkflow[]
): Promise<SaveRxWorkflowsResponse> => {
  try {
    // Map savedName → original_name for the backend rename path; strip the
    // frontend-only savedName field so the payload stays clean.
    const mapPayload = ({ savedName, name, content, isReusable }: RXWorkflow): WorkflowSavePayload => {
      const base: WorkflowSavePayload = { name, content, isReusable };
      if (savedName && savedName !== name) {
        base.original_name = savedName;
      }
      return base;
    };

    const response: AxiosResponse<SaveRxWorkflowsResponse> = await apiClient.post(`${BACKEND_URL}/api/save-workflows`, {
      project_name: projectName,
      workflows: [],         // must send both for validation
      rxworkflows: rxworkflows.map(mapPayload),
    });

    console.log("✅ RX Workflows saved to DB:", response.data);
    return response.data;
  } catch (error) {
    console.error("❌ Error saving RX workflows:", error);
    throw error;
  }
};
