import apiClient from "./apiClient";

export interface CustomFile {
  id: number;
  project_id: number;
  display_name: string | null;
  file_path: string;
  file_content: string;
  git_hash: string | null;
  file_status: string;
  pending_delete: boolean;
  last_modified_by: string | null;
  description: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateCustomFilePayload {
  github_user?: string;
  display_name?: string;
  file_path: string;
  file_content: string;
  description?: string;
}

export interface UpdateCustomFilePayload {
  github_user?: string;
  display_name?: string;
  file_path?: string;
  file_content?: string;
  description?: string;
}

export const createCustomFile = (projectId: number, data: CreateCustomFilePayload): Promise<{ custom_file: CustomFile }> =>
  apiClient.post(`/api/projects/${projectId}/custom-files`, data).then((r) => r.data);

export const updateCustomFile = (projectId: number, id: number, data: UpdateCustomFilePayload): Promise<{ custom_file: CustomFile }> =>
  apiClient.put(`/api/projects/${projectId}/custom-files/${id}`, data).then((r) => r.data);

export const deleteCustomFile = (projectId: number, id: number): Promise<{ deleted: boolean; hard_deleted?: boolean; pending_delete?: boolean; custom_file?: CustomFile }> =>
  apiClient.delete(`/api/projects/${projectId}/custom-files/${id}`).then((r) => r.data);

export const restoreCustomFile = (projectId: number, id: number): Promise<{ custom_file: CustomFile }> =>
  apiClient.post(`/api/projects/${projectId}/custom-files/${id}/restore`).then((r) => r.data);

/** Client-side path validation (mirrors server-side rules). Returns error string or null. */
export const validateFilePath = (path: string): string | null => {
  if (!path?.trim()) return "File path is required";
  const p = path.trim();
  if (p.startsWith("/")) return "Absolute paths are not allowed";
  const parts = p.replaceAll("\\", "/").split("/");
  if (parts.includes("..")) return "Path traversal (..) is not allowed";
  if (parts[0] === ".git" || parts.slice(1).includes(".git"))
    return ".git/ paths are not allowed";
  const basename = (parts.at(-1) ?? "").toLowerCase();
  if (basename === ".env" || basename.startsWith(".env."))
    return ".env files are not allowed";
  const blocked = [".pem", ".key", ".p12", ".pfx", ".crt", ".cert", ".jks"];
  const lower = p.toLowerCase();
  for (const ext of blocked) {
    if (lower.endsWith(ext)) return `${ext} files are not allowed`;
  }
  return null;
};
