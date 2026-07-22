import config from "../config";

const BACKEND_URL = config.BACKEND_URL;

// ===== Type Definitions =====

export interface RateLimitInfo {
  limit: number;
  used: number;
  remaining: number;
  percentage_used: number;
  should_warn: boolean;
  reset_at: string;
}

// UserDetails interface represents the user data structure returned from the API
// - username is optional as it may not always be present in API responses
// - index signature allows for additional fields that may be added by the API in the future
export interface UserDetails {
  username?: string;
  avatar_url: string;
  github_user: string;
  account_type: string;
  github_account_type?: string | null;
  connected_github_account?: string | null;
  connected_github_account_type?: string | null;
  rate_limit?: RateLimitInfo;
  workspace_role?: string;
  github_token?: GitHubTokenStatus;
  [key: string]: any;
}

export interface GitHubTokenStatus {
  configured: boolean;
  status: "not_configured" | "configured" | "valid" | "missing_scopes" | "missing_repo_access" | "missing_org_approval" | "insufficient_repo_permissions" | "token_invalid" | "unknown_error";
  message: string;
  token_type?: "oauth_token" | "classic_pat" | "fine_grained_pat" | "github_app_user" | "github_app_installation" | "unknown" | null;
  checked_at?: string | null;
  updated_at?: string | null;
}

// GitHub Permission Validation Result
export interface PermissionValidationResult {
  status: "valid" | "missing_scopes" | "missing_repo_access" | "missing_org_approval" | "insufficient_repo_permissions" | "token_invalid" | "unknown_error";
  valid: boolean;
  missing_scopes: string[];
  granted_scopes: string[];
  issues: string[];
  warnings: string[];
  recommendations: string[];
  message: string;
  details?: {
    auth_type?: "oauth" | "github_app" | "personal_access_token";
    token_type?: GitHubTokenStatus["token_type"];
    scopes?: {
      granted_scopes: string[];
      missing_scopes: string[];
      has_all_required: boolean;
      note?: string;
    };
    repository_access?: {
      has_repo_access: boolean;
      total_repos?: number;
      accessible_repos?: string[];
      has_write_restrictions?: boolean;
      limited_repos?: string[];
      note?: string;
    };
    organization_access?: {
      has_orgs: boolean;
      organizations?: string[];
      accessible_orgs?: string[];
      restricted_orgs?: string[];
      has_org_restrictions: boolean;
    };
    app_permissions?: {
      has_required_permissions: boolean;
      missing_permissions?: string[];
      optional_missing?: string[];
    };
  };
}

export interface SaveGitHubTokenResult {
  saved: boolean;
}

export interface RemoveGitHubTokenResult {
  removed: boolean;
  token: GitHubTokenStatus;
}

export interface LoginWithGitHubTokenResult {
  user: string;
}

// ===== API Functions =====

// Fetch user details including avatar URL
export const getUserDetails = async (username: string): Promise<UserDetails | null> => {
  try {
    const response = await fetch(`${BACKEND_URL}/api/user/${username}`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch user details: ${response.status}`);
    }

    const data: UserDetails = await response.json();
    return data;
  } catch (error) {
    console.error("❌ Error fetching user details:", error);
    return null;
  }
};

// Check GitHub permissions for a user
export const checkGitHubPermissions = async (username: string): Promise<PermissionValidationResult | null> => {
  try {
    const response = await fetch(`${BACKEND_URL}/api/user/${username}/permissions`, {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Failed to check GitHub permissions: ${response.status}`);
    }

    const data: PermissionValidationResult = await response.json();
    return data;
  } catch (error) {
    console.error("❌ Error checking GitHub permissions:", error);
    return null;
  }
};

async function performGitHubTokenRequest<T>(
  username: string,
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || `GitHub token request failed: ${response.status}`);
  }
  return data as T;
}

export const getGitHubTokenStatus = async (username: string): Promise<GitHubTokenStatus | null> => {
  try {
    const response = await fetch(`${BACKEND_URL}/api/user/${username}/github-token`, {
      credentials: "include",
    });
    if (!response.ok) {
      throw new Error(`Failed to fetch GitHub token status: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error("❌ Error fetching GitHub token status:", error);
    return null;
  }
};

export const testGitHubToken = async (username: string, token: string): Promise<PermissionValidationResult> => {
  return performGitHubTokenRequest<PermissionValidationResult>(
    username,
    `${BACKEND_URL}/api/user/${username}/github-token/test`,
    {
      method: "POST",
      body: JSON.stringify({ token }),
    },
  );
};

export const saveGitHubToken = async (username: string, token: string): Promise<SaveGitHubTokenResult> => {
  return performGitHubTokenRequest<SaveGitHubTokenResult>(
    username,
    `${BACKEND_URL}/api/user/${username}/github-token`,
    {
      method: "PUT",
      body: JSON.stringify({ token }),
    },
  );
};

export const removeGitHubToken = async (username: string): Promise<RemoveGitHubTokenResult> => {
  return performGitHubTokenRequest<RemoveGitHubTokenResult>(
    username,
    `${BACKEND_URL}/api/user/${username}/github-token`,
    {
      method: "DELETE",
    },
  );
};

export const loginWithGitHubToken = async (token: string): Promise<LoginWithGitHubTokenResult> => {
  const response = await fetch(`${BACKEND_URL}/auth/token`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ token }),
  });

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || `GitHub token login failed: ${response.status}`);
  }
  return data as LoginWithGitHubTokenResult;
};

export const logout = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${BACKEND_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    return response.ok;
  } catch {
    return false;
  }
};
