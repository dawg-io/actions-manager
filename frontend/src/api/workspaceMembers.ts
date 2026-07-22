import apiClient from "./apiClient";

// ===== Type Definitions =====

export interface WorkspaceMember {
  user_id: number;
  github_user: string;
  avatar_url: string | null;
  workspace_role: string;
}

// ===== API Functions =====

/**
 * Fetch all workspace members.
 * Authentication is handled by apiClient's X-GitHub-User interceptor.
 */
export const getWorkspaceMembers = async (): Promise<WorkspaceMember[]> => {
  try {
    const response = await apiClient.get<WorkspaceMember[]>("/api/workspace/members");
    return response.data;
  } catch (error) {
    console.error("❌ Error fetching workspace members:", error);
    return [];
  }
};

/**
 * Update a workspace member's role.
 * Authentication is handled by apiClient's X-GitHub-User interceptor.
 */
export const updateMemberRole = async (
  userId: number,
  newRole: string
): Promise<{ success: boolean; message?: string }> => {
  try {
    const response = await apiClient.patch(
      `/api/workspace/members/${userId}/role`,
      { workspace_role: newRole },
    );

    return { success: true, message: response.data.message };
  } catch (error: any) {
    if (error.response?.data?.detail) {
      return { success: false, message: error.response.data.detail };
    }
    console.error("❌ Error updating member role:", error);
    return { success: false, message: "Network error" };
  }
};
