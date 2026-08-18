/**
 * Validation for the Create Project wizard.
 *
 * These were closures inside NewProject. Nested functions count toward their
 * parent's cognitive complexity in Sonar, and the component was well over the
 * limit — so the branching lives here, where it is also directly testable.
 * Each returns the message to show, or null when the input is acceptable.
 */

export interface Repository {
  name: string;
  full_name: string;
  private: boolean;
}

export type VisibilityScope = 'public' | 'private';

export function repoMatchesVisibilityScope(repo: Repository, scope: VisibilityScope): boolean {
  return scope === 'private' ? !!repo.private : !repo.private;
}

export interface ProjectInputs {
  projectName: string;
  selectedRepos: string[];
  repos: Repository[];
  visibilityScope: VisibilityScope;
  privateAllowedByTier: boolean;
  useCustomKey: boolean;
  projectKey: string;
}

/** Repositories in the selection that do not match the chosen visibility. */
export function mismatchedRepos(inputs: ProjectInputs): string[] {
  return inputs.selectedRepos.filter((name) => {
    const repo = inputs.repos.find((r) => (r.full_name || r.name) === name);
    // Unknown repo — let the backend decide rather than blocking here.
    if (!repo) return false;
    return !repoMatchesVisibilityScope(repo, inputs.visibilityScope);
  });
}

export function validateProjectInputs(inputs: ProjectInputs): string | null {
  if (!inputs.projectName.trim()) return 'Project name cannot be empty.';
  if (inputs.selectedRepos.length === 0) return 'Please select at least one repository.';

  // Mirrors the backend's tier/scope enforcement.
  const mismatched = mismatchedRepos(inputs);
  if (mismatched.length > 0) {
    const label = inputs.visibilityScope === 'private' ? 'Private' : 'Public';
    return (
      `The following repositories do not match the selected ${label} visibility: ` +
      `${mismatched.join(', ')}. Remove them or change the visibility option.`
    );
  }

  if (inputs.visibilityScope === 'private' && !inputs.privateAllowedByTier) {
    return (
      'Free plan accounts cannot create private repository projects. ' +
      'Upgrade to Professional or Enterprise to enable private repository projects.'
    );
  }

  if (inputs.useCustomKey && inputs.projectKey.trim()) {
    const cleanKey = inputs.projectKey.trim().toUpperCase().replaceAll(/[^A-Z0-9]/g, '');
    if (cleanKey.length < 2 || cleanKey.length > 10) {
      return 'Project key must be 2–10 characters (letters and numbers only).';
    }
  }

  return null;
}

/** Turn a backend project-limit rejection into the message for this tier. */
export function describeProjectLimitError(errorMessage: string): string {
  // Beta errors already carry the right wording from the backend.
  if (errorMessage.includes('Self-hosted beta')) return errorMessage;
  if (
    errorMessage.includes('can only create up to 3 projects') ||
    errorMessage.includes('Free accounts')
  ) {
    return "Free plan users can create up to 3 projects. You've reached your limit. Please upgrade to Professional for up to 10 projects.";
  }
  if (
    errorMessage.includes('can create up to 10 projects') ||
    errorMessage.includes('Professional accounts')
  ) {
    return "Professional plan users can create up to 10 projects. You've reached your limit. Please upgrade to Enterprise for unlimited projects.";
  }
  return errorMessage;
}
