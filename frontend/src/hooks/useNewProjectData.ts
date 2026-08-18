import { useEffect, useState } from 'react';
import { fetchRepos, fetchRwxRepos } from '../api/repos';
import { fetchProjects } from '../api/projects';
import { getUserDetails } from '../api/user';

export interface Repository {
  id: string | number;
  name: string;
  full_name: string;
  private: boolean;
  default_branch: string;
  permissions?: any;
}

export interface AccountContext {
  accountType: string | null;
  installationMode: string | null;
  betaCallerCount: number;
  betaRwxCount: number;
}

/**
 * Account tier, installation mode and per-type project counts for the wizard.
 *
 * Extracted from the component so its branching does not count against
 * NewProject's cognitive complexity — the component is the largest function in
 * the frontend and was over the limit with all of this inlined.
 */
export function useNewProjectAccount(user: string): AccountContext {
  const [accountType, setAccountType] = useState<string | null>(null);
  const [installationMode, setInstallationMode] = useState<string | null>(null);
  const [betaCallerCount, setBetaCallerCount] = useState<number>(0);
  const [betaRwxCount, setBetaRwxCount] = useState<number>(0);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;

    const loadBetaCounts = async (): Promise<void> => {
      const allProjects = await fetchProjects(user);
      if (cancelled) return;
      setBetaCallerCount(
        allProjects.filter((p) => (p.project_type ?? 'standard') === 'standard').length,
      );
      setBetaRwxCount(allProjects.filter((p) => p.project_type === 'rwx').length);
    };

    const loadDetails = async (): Promise<void> => {
      const details = await getUserDetails(user);
      if (cancelled) return;
      setAccountType(details?.account_type ?? null);
      const mode = details?.installation_mode ?? null;
      setInstallationMode(mode);
      if (mode?.toLowerCase() === 'self-hosted') await loadBetaCounts();
    };

    void loadDetails();
    return () => {
      cancelled = true;
    };
  }, [user]);

  return { accountType, installationMode, betaCallerCount, betaRwxCount };
}

export interface RepoPickerState {
  repos: Repository[];
  setRepos: React.Dispatch<React.SetStateAction<Repository[]>>;
  loading: boolean;
  error: string | null;
}

/** Read a repo-list response that may instead be an `{error, status}` payload. */
function readRepoResponse(response: any, fallbackMessage: string): { repos: Repository[]; error: string | null } {
  if (Array.isArray(response)) return { repos: response, error: null };
  if (response && (response.error || response.status)) {
    return {
      repos: [],
      // Surface real transport / GitHub-API failures instead of falling through
      // to the empty state, which would look like the user has no repos at all.
      error: typeof response.error === 'string' ? response.error : fallbackMessage,
    };
  }
  console.error('❌ Error: Unexpected repository format:', response);
  return { repos: [], error: null };
}

/**
 * Repositories for the picker, reloaded when the project type changes.
 *
 * Reusable Workflow Projects are discovered across every accessible account and
 * filtered by the `am-rwx` topic, so the two branches fetch from different
 * endpoints and report their own errors.
 */
export function useNewProjectRepos(
  user: string,
  projectType: string,
  onTypeChange: () => void,
): RepoPickerState {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    const isRwx = projectType === 'rwx';
    setError(null);
    setLoading(true);
    // Clear first so the picker cannot briefly render the previous type's
    // repositories while the new request is in flight.
    if (isRwx) setRepos([]);

    const request = isRwx ? fetchRwxRepos(user) : fetchRepos(user);
    const fallback = isRwx
      ? 'Unable to load reusable workflow repositories.'
      : 'Unable to load repositories.';

    void request.then((response: any) => {
      const result = readRepoResponse(response, fallback);
      setRepos(result.repos);
      setError(result.error);
      onTypeChange();
      setLoading(false);
    });
    // onTypeChange is a setState wrapper and stable; re-running on its identity
    // would refetch on every render.
  }, [user, projectType]);

  return { repos, setRepos, loading, error };
}
