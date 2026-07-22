import axios from "axios";
import apiClient from "./apiClient";
import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

export interface AIReusableWorkflowRequest {
  user: string;
  project_name: string;
  project_code: string;
  repository_info: { selected_repos: string[] };
  build_types: string[];
}

export interface AIWorkflowResponse {
  session_id: string;
  reusable_workflow_yaml: string;
  caller_workflow_yaml: string;
  explanation: string;
  suggested_questions?: string[];
}

export interface AIChatResponse {
  response_message: string;
  updated_workflow?: string;
  workflow_updates?: string[];
  suggested_questions?: string[];
}

export const generateWorkflowWithAI = async (requestData: unknown): Promise<unknown> => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/ai/generate-workflow`, requestData);
    return response.data;
  } catch (error) {
    console.error("❌ Error generating workflow with AI:", error);
    throw error;
  }
};

export const sendChatMessage = async (
  sessionId: string,
  userMessage: string,
  currentWorkflow: string | null = null
): Promise<AIChatResponse> => {
  try {
    const requestData = { session_id: sessionId, user_message: userMessage, current_workflow: currentWorkflow };
    const response = await apiClient.post(`${BACKEND_URL}/api/ai/chat-interaction`, requestData);
    return response.data;
  } catch (error) {
    console.error("❌ Error sending chat message:", error);
    throw error;
  }
};

export const editWorkflowWithAI = async (requestData: unknown): Promise<unknown> => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/ai/edit-workflow`, requestData);
    return response.data;
  } catch (error) {
    console.error("❌ Error editing workflow with AI:", error);
    throw error;
  }
};

export const getSessionInfo = async (sessionId: string): Promise<unknown> => {
  try {
    const response = await axios.get(`${BACKEND_URL}/api/ai/session/${sessionId}`);
    return response.data;
  } catch (error) {
    console.error("❌ Error getting session info:", error);
    throw error;
  }
};

export const deleteSession = async (sessionId: string): Promise<unknown> => {
  try {
    const response = await apiClient.delete(`${BACKEND_URL}/api/ai/session/${sessionId}`);
    return response.data;
  } catch (error) {
    console.error("❌ Error deleting session:", error);
    throw error;
  }
};

export const testAIIntegration = async (): Promise<unknown> => {
  try {
    const response = await axios.get(`${BACKEND_URL}/api/ai/test`);
    return response.data;
  } catch (error) {
    console.error("❌ Error testing AI integration:", error);
    throw error;
  }
};

export const generateReusableWorkflowWithAI = async (
  requestData: AIReusableWorkflowRequest
): Promise<AIWorkflowResponse> => {
  try {
    const response = await apiClient.post(`${BACKEND_URL}/api/ai/generate-reusable-workflow`, requestData);
    return response.data;
  } catch (error) {
    console.error("❌ Error generating reusable workflow with AI:", error);
    throw error;
  }
};

export const getSessionWorkflows = async (sessionId: string): Promise<unknown> => {
  try {
    const response = await axios.get(`${BACKEND_URL}/api/ai/session/${sessionId}/workflows`);
    return response.data;
  } catch (error) {
    console.error("❌ Error getting session workflows:", error);
    throw error;
  }
};

export const checkAIIntegration = async (): Promise<boolean> => {
  try {
    const response = await testAIIntegration() as { status?: string };
    return response.status === "success";
  } catch (error) {
    console.error("❌ AI integration check failed:", error);
    return false;
  }
};
