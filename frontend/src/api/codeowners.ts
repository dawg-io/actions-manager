import apiClient from "./apiClient";

// ===== Type Definitions =====

export interface CodeownersRecord {
  id: number;
  project_id: number;
  repo_id: number;
  content: string;
  file_path: string;
  git_hash: string | null;
  status: string;
  last_modified_by: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CodeownersGitHubInfo {
  exists: boolean;
  content: string | null;
  sha: string | null;
  path: string | null;
}

export interface CodeownersGetResponse {
  success: boolean;
  repo_id: number;
  repo_name: string;
  github: CodeownersGitHubInfo;
  local: CodeownersRecord | null;
}

export interface CodeownersSaveResponse {
  success: boolean;
  message: string;
  codeowners: CodeownersRecord;
  validation_warnings: string[];
}

export type DriftStatus =
  | "synced"
  | "content_mismatch"
  | "missing_locally"
  | "missing_on_github"
  | "absent";

export interface CodeownersDriftResponse {
  success: boolean;
  repo_id: number;
  repo_name: string;
  drift_status: DriftStatus;
  has_drift: boolean;
  reason: string;
  local_sha: string | null;
  github_sha: string | null;
  github_path: string | null;
}

export interface CodeownersDeployResponse {
  success: boolean;
  message: string;
  mode: "direct" | "pr";
  branch: string;
  target_branch: string;
  file_path: string;
  git_hash: string | null;
  pull_request: { number?: number; url?: string; warning?: string } | null;
  codeowners: CodeownersRecord;
}

// ===== API Functions =====

const repoSegment = (repoRef: string | number): string =>
  typeof repoRef === "number" ? String(repoRef) : encodeURI(repoRef);

/** Fetch CODEOWNERS from GitHub and any local draft. */
export const getCodeowners = async (
  repoRef: string | number,
  githubUser: string,
  projectName: string
): Promise<CodeownersGetResponse> => {
  const response = await apiClient.get<CodeownersGetResponse>(
    `/api/repos/${repoSegment(repoRef)}/codeowners`,
    { params: { github_user: githubUser, project_name: projectName } }
  );
  return response.data;
};

/** Save the CODEOWNERS draft locally. */
export const saveCodeownersDraft = async (
  repoRef: string | number,
  githubUser: string,
  projectName: string,
  content: string,
  filePath: string = ".github/CODEOWNERS"
): Promise<CodeownersSaveResponse> => {
  const response = await apiClient.post<CodeownersSaveResponse>(
    `/api/repos/${repoSegment(repoRef)}/codeowners`,
    {
      github_user: githubUser,
      project_name: projectName,
      content,
      file_path: filePath,
    }
  );
  return response.data;
};

/** Detect drift between the local draft and GitHub. */
export const getCodeownersDrift = async (
  repoRef: string | number,
  githubUser: string,
  projectName: string
): Promise<CodeownersDriftResponse> => {
  const response = await apiClient.get<CodeownersDriftResponse>(
    `/api/repos/${repoSegment(repoRef)}/codeowners/drift`,
    { params: { github_user: githubUser, project_name: projectName } }
  );
  return response.data;
};

/** Get the local status of every CODEOWNERS record in a project (no GitHub calls). */
export const getProjectCodeownersStatuses = async (
  githubUser: string,
  projectName: string
): Promise<{ statuses: Array<{ repo_name: string; status: string }> }> => {
  const response = await apiClient.get('/api/project-codeowners-statuses', {
    params: { github_user: githubUser, project_name: projectName },
  });
  return response.data;
};

/** Commit the CODEOWNERS file to GitHub (direct commit or PR). */
export const deployCodeowners = async (
  repoRef: string | number,
  githubUser: string,
  projectName: string,
  options: {
    content?: string;
    filePath?: string;
    branch?: string;
    mode?: "direct" | "pr";
    commitMessage?: string;
    campaignId?: number;
  } = {}
): Promise<CodeownersDeployResponse> => {
  const response = await apiClient.post<CodeownersDeployResponse>(
    `/api/repos/${repoSegment(repoRef)}/codeowners/deploy`,
    {
      github_user: githubUser,
      project_name: projectName,
      content: options.content,
      file_path: options.filePath,
      branch: options.branch,
      mode: options.mode ?? "direct",
      commit_message: options.commitMessage,
      campaign_id: options.campaignId ?? null,
    }
  );
  return response.data;
};
