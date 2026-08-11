/**
 * Project resources (secrets, variables, deployment environments) surfaced in the
 * workflow editor so users can insert references without retyping names.
 *
 * Names are used exactly as the backend returns them. In prefix mode the stored
 * GitHub name already carries the `AM_{PROJECT_CODE}_` prefix (see
 * `format_secret_name` / `_format_env_var_key` on the backend), and
 * `/api/get-secrets` and `/api/get-env-vars` return that full name filtered to
 * the project — so a workflow must reference the prefixed name verbatim and
 * nothing here rewrites it.
 */

export type WorkflowResourceKind = 'secret' | 'variable' | 'environment';

export interface WorkflowResource {
  kind: WorkflowResourceKind;
  /** Full GitHub name, already prefixed in prefix mode. Never a value. */
  name: string;
  /** Repository the resource lives in — the "scope" shown next to the name. */
  repo: string;
}

/** Shapes as returned by the existing APIs. Values are accepted but never kept. */
interface SecretRow {
  secret_key?: string;
  name?: string;
  repo?: string;
}

interface EnvVarRow {
  env_key?: string;
  repo?: string;
}

interface EnvironmentRow {
  name: string;
  repo: string;
}

export const buildResourceExpression = (resource: WorkflowResource): string => {
  if (resource.kind === 'secret') return `\${{ secrets.${resource.name} }}`;
  if (resource.kind === 'variable') return `\${{ vars.${resource.name} }}`;
  // Deployment environments are a job-level key, not an expression.
  return `environment: ${resource.name}`;
};

/**
 * Replaces the current selection in a plain input/textarea value.
 * Returns the new text plus the caret offset immediately after the insertion.
 */
export const insertIntoText = (
  text: string,
  selectionStart: number,
  selectionEnd: number,
  insert: string
): { text: string; cursor: number } => {
  const start = Math.max(0, Math.min(selectionStart, text.length));
  const end = Math.max(start, Math.min(selectionEnd, text.length));
  return {
    text: text.slice(0, start) + insert + text.slice(end),
    cursor: start + insert.length,
  };
};

/**
 * Maps API rows to the picker's model.
 *
 * This is the security boundary for the feature: only the name and the owning
 * repo are carried across, so a stored value can never reach the picker's props
 * or the DOM. Secret values are never returned by GitHub's list API in the first
 * place; variable values are, and are dropped here.
 */
export const toResources = ({
  secrets = [],
  envVars = [],
  environments = [],
}: {
  secrets?: SecretRow[];
  envVars?: EnvVarRow[];
  environments?: EnvironmentRow[];
}): WorkflowResource[] => {
  const resources: WorkflowResource[] = [];

  for (const secret of secrets) {
    const name = secret.secret_key ?? secret.name;
    if (name) resources.push({ kind: 'secret', name, repo: secret.repo ?? '' });
  }

  for (const envVar of envVars) {
    if (envVar.env_key) {
      resources.push({ kind: 'variable', name: envVar.env_key, repo: envVar.repo ?? '' });
    }
  }

  for (const environment of environments) {
    if (environment.name) {
      resources.push({ kind: 'environment', name: environment.name, repo: environment.repo ?? '' });
    }
  }

  return resources;
};

/**
 * De-duplicates by kind+name so a secret synced across several repos appears
 * once, with every repo it covers listed as its scope.
 */
export const groupResourceScopes = (
  resources: WorkflowResource[]
): Array<WorkflowResource & { repos: string[] }> => {
  const byKey = new Map<string, WorkflowResource & { repos: string[] }>();

  for (const resource of resources) {
    const key = `${resource.kind}:${resource.name}`;
    const existing = byKey.get(key);
    if (existing) {
      if (resource.repo && !existing.repos.includes(resource.repo)) {
        existing.repos.push(resource.repo);
      }
    } else {
      byKey.set(key, { ...resource, repos: resource.repo ? [resource.repo] : [] });
    }
  }

  return [...byKey.values()];
};
