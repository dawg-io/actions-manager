import apiClient from "./apiClient";

// ===== Type Definitions =====

export interface ProjectMember {
  id: number;
  user_id: number;
  project_id: number;
  project_role: string; // "project_editor" | "project_viewer"
  github_user: string;
  avatar_url: string | null;
}

// ===== API Functions =====

/**
 * Fetch all members of a project.
 * Requires admin workspace role.
 * Returns a structured result so the caller can distinguish between
 * "no members" and "not authorized".
 */
export const getProjectMembers = async (
  projectId: number
): Promise<{ success: boolean; data: ProjectMember[]; status?: number }> => {
  try {
    const response = await apiClient.get<ProjectMember[]>(
      `/api/projects/${projectId}/members`
    );
    return { success: true, data: response.data };
  } catch (error: any) {
    const status = error.response?.status;
    if (status === 403) {
      // Caller lacks permission — propagate so UI can show appropriate state
      return { success: false, data: [], status: 403 };
    }
    console.error("❌ Error fetching project members:", error);
    return { success: false, data: [], status };
  }
};

/**
 * Add a user to a project with a specific role.
 * Requires admin workspace role.
 */
export const addProjectMember = async (
  projectId: number,
  userId: number,
  projectRole: string = "project_viewer"
): Promise<{ success: boolean; member?: ProjectMember; message?: string }> => {
  try {
    const response = await apiClient.post<ProjectMember>(
      `/api/projects/${projectId}/members`,
      { user_id: userId, project_role: projectRole }
    );
    return { success: true, member: response.data };
  } catch (error: any) {
    if (error.response?.data?.detail) {
      return { success: false, message: error.response.data.detail };
    }
    console.error("❌ Error adding project member:", error);
    return { success: false, message: "Network error" };
  }
};

/**
 * Update a project member's role.
 * Requires admin workspace role.
 */
export const updateProjectMemberRole = async (
  projectId: number,
  userId: number,
  projectRole: string
): Promise<{ success: boolean; member?: ProjectMember; message?: string }> => {
  try {
    const response = await apiClient.patch<ProjectMember>(
      `/api/projects/${projectId}/members/${userId}`,
      { project_role: projectRole }
    );
    return { success: true, member: response.data };
  } catch (error: any) {
    if (error.response?.data?.detail) {
      return { success: false, message: error.response.data.detail };
    }
    console.error("❌ Error updating project member role:", error);
    return { success: false, message: "Network error" };
  }
};

/**
 * Remove a user from a project.
 * Requires admin workspace role.
 */
export const removeProjectMember = async (
  projectId: number,
  userId: number
): Promise<{ success: boolean; message?: string }> => {
  try {
    await apiClient.delete(`/api/projects/${projectId}/members/${userId}`);
    return { success: true };
  } catch (error: any) {
    if (error.response?.data?.detail) {
      return { success: false, message: error.response.data.detail };
    }
    console.error("❌ Error removing project member:", error);
    return { success: false, message: "Network error" };
  }
};
