import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { getEnvironments } from '../api/environments';
import { WorkflowResource, toResources } from '../utils/workflowResources';

interface WorkflowResourcesValue {
  resources: WorkflowResource[];
  loadingEnvironments: boolean;
  environmentsError: string | null;
  /** Called when a picker opens, so environments are fetched only if actually used. */
  requestEnvironments: () => void;
}

// Defaults to empty/no-op so the GUI step editors still render outside a
// provider - in tests, and anywhere the picker isn't wanted. Same contract as
// StepSelectionContext.
const WorkflowResourcesContext = createContext<WorkflowResourcesValue>({
  resources: [],
  loadingEnvironments: false,
  environmentsError: null,
  requestEnvironments: () => {},
});

export const useWorkflowResources = (): WorkflowResourcesValue =>
  useContext(WorkflowResourcesContext);

interface WorkflowResourcesProviderProps {
  user?: string;
  selectedRepos?: string[];
  secrets?: Array<{ secret_key?: string; name?: string; repo?: string }>;
  envVars?: Array<{ env_key?: string; repo?: string }>;
  children: React.ReactNode;
}

/**
 * Supplies the workflow editor with the project's secrets, variables and
 * deployment environments.
 *
 * Secrets and variables are already in the parent's state, so they cost nothing
 * here. Deployment environments are not loaded on the workflows page at all, and
 * fetching them costs one GitHub call per repository - so they are fetched only
 * once a picker is actually opened, and cached until the repository set changes.
 */
export const WorkflowResourcesProvider: React.FC<WorkflowResourcesProviderProps> = ({
  user,
  selectedRepos = [],
  secrets = [],
  envVars = [],
  children,
}) => {
  const [environments, setEnvironments] = useState<Array<{ name: string; repo: string }>>([]);
  const [loadingEnvironments, setLoadingEnvironments] = useState(false);
  const [environmentsError, setEnvironmentsError] = useState<string | null>(null);
  // Which repository set the user has asked for, rather than a bare boolean: a
  // boolean stays true across a repo change for one render, which is long
  // enough to fire a round of GitHub calls that are then thrown away.
  const [requestedFor, setRequestedFor] = useState<string | null>(null);
  const runIdRef = useRef(0);

  // selectedRepos is a fresh array on every parent render; key the effects off
  // its contents so they don't refetch on unrelated re-renders.
  const repoKey = selectedRepos.join(',');
  const repos = useMemo(() => (repoKey ? repoKey.split(',') : []), [repoKey]);

  // A changed repository set invalidates whatever was cached for the old one.
  useEffect(() => {
    setEnvironments([]);
    setEnvironmentsError(null);
    setLoadingEnvironments(false);
  }, [repoKey]);

  useEffect(() => {
    if (requestedFor !== repoKey || !user || repos.length === 0) return;

    // Only the newest run may publish. Guarding on a captured `cancelled` flag
    // instead would leave the loading flag stuck on whenever a run is discarded.
    const runId = runIdRef.current + 1;
    runIdRef.current = runId;

    setLoadingEnvironments(true);
    setEnvironmentsError(null);

    Promise.all(
      repos.map(async (repo) => {
        const repoEnvironments = await getEnvironments(user, repo);
        return (repoEnvironments ?? []).map((environment: { name: string }) => ({
          name: environment.name,
          repo,
        }));
      })
    )
      .then((perRepo) => {
        if (runIdRef.current === runId) setEnvironments(perRepo.flat());
      })
      .catch((error: unknown) => {
        if (runIdRef.current !== runId) return;
        setEnvironmentsError(
          error instanceof Error ? error.message : 'Failed to load deployment environments.'
        );
      })
      .finally(() => {
        if (runIdRef.current === runId) setLoadingEnvironments(false);
      });
  }, [requestedFor, repoKey, user, repos]);

  const value = useMemo<WorkflowResourcesValue>(
    () => ({
      resources: toResources({ secrets, envVars, environments }),
      loadingEnvironments,
      environmentsError,
      requestEnvironments: () => setRequestedFor(repoKey),
    }),
    [secrets, envVars, environments, loadingEnvironments, environmentsError, repoKey]
  );

  return (
    <WorkflowResourcesContext.Provider value={value}>
      {children}
    </WorkflowResourcesContext.Provider>
  );
};

export const WorkflowResourcesRawProvider = WorkflowResourcesContext.Provider;
