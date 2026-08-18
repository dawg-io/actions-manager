import React, { useState } from 'react';
import { FolderPlus } from 'lucide-react';
import { Button } from './ui/button';
import { createGitHubRepo } from '../api/repos';
import { toast } from '../utils/toast';

export const DEMO_REPO_NAME = 'actionsmanager-demo';

interface CreateRepoResult {
  repo_name?: string;
  owner?: string;
  error?: unknown;
}

/**
 * Turn the backend's failure into something the user can act on.
 *
 * GitHub replies to a duplicate name with a nested errors array, which the
 * endpoint passes through as an object — so a plain string check falls through
 * to a generic message. That case is also the most likely one here: running the
 * tour twice hits an `actionsmanager-demo` that already exists, and the repo
 * the user needs is sitting in the list below.
 */
export function describeFailure(error: unknown): string {
  const text = typeof error === 'string' ? error : JSON.stringify(error ?? '');
  if (/already exists/i.test(text)) {
    return `You already have a ${DEMO_REPO_NAME} repository — pick it from the list below.`;
  }
  if (typeof error === 'string' && error.trim()) return error;
  return 'Could not create the demo repository. Pick an existing repository instead.';
}

export interface CreateDemoRepoButtonProps {
  user: string;
  /** "public" or "private" — matches the visibility scope chosen in the wizard. */
  visibility: string;
  /** Called with `owner/repo` once the repository exists on GitHub. */
  onCreated: (fullName: string) => void;
}

/**
 * Creates a throwaway repository for the guided tour.
 *
 * Offered so a first-run user with nothing safe to experiment on does not have
 * to leave the app and go make one — the tour opens a real pull request later,
 * and it should not be against something they care about.
 */
const CreateDemoRepoButton: React.FC<CreateDemoRepoButtonProps> = ({ user, visibility, onCreated }) => {
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async (): Promise<void> => {
    setIsCreating(true);
    try {
      const result = (await createGitHubRepo(user, visibility, undefined, {
        name: DEMO_REPO_NAME,
        description: 'Throwaway repository for trying out ActionsManager.',
      })) as CreateRepoResult;

      if (result?.error || !result?.repo_name) {
        toast.error(describeFailure(result?.error));
        return;
      }

      const fullName = `${result.owner || user}/${result.repo_name}`;
      toast.success(`Created ${fullName}. It is selected below.`);
      onCreated(fullName);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    // Accent border and a filled button: this is an offer the user is meant to
    // notice, and as a neutral card it read as more form furniture.
    <div className="mb-3 rounded-lg border-2 border-primary bg-primary-light/40 p-3 dark:border-primary-dark dark:bg-primary/10">
      <p className="text-sm text-text-secondary dark:text-text-secondary-dark">
        Nothing safe to experiment on? Create a throwaway repository named{' '}
        <code>{DEMO_REPO_NAME}</code> and the tour will use that instead.
      </p>
      <Button
        className="mt-2"
        data-testid="create-demo-repo-button"
        disabled={isCreating}
        onClick={() => { void handleCreate(); }}
        size="sm"
      >
        <FolderPlus className="h-4 w-4" aria-hidden="true" />
        {isCreating ? 'Creating…' : 'Create a demo repository'}
      </Button>
    </div>
  );
};

export default CreateDemoRepoButton;
