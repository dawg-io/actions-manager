import { useCallback, useRef, useState } from 'react';
import { getRenameImpact, type RenameImpact } from '../api/workflows';
import { normalizeWorkflowStem } from '../utils/workflowFilename';

/** A workflow whose name changed since it was last saved. */
export interface PendingRename {
  previousName: string;
  newName: string;
  isReusable: boolean;
}

/** One rename, with what the backend says it would do. */
export interface RenameImpactItem extends PendingRename {
  impact: RenameImpact | null;
  /** Why the impact could not be fetched, when it could not. */
  error: string | null;
}

/** Every workflow in `workflows` whose name differs from its persisted one. */
export const collectRenames = (
  workflows: Array<{ name?: string; savedName?: string }> | undefined,
  isReusable: boolean
): PendingRename[] =>
  (workflows ?? []).flatMap(w => {
    const previousName = (w.savedName || '').trim();
    // The backend stores a stem and appends .yml itself, so typing the
    // extension over an unchanged name is not a rename.
    const newName = normalizeWorkflowStem(w.name ?? '');
    return previousName && newName && previousName !== newName
      ? [{ previousName, newName, isReusable }]
      : [];
  });

const describeError = (error: unknown): string => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return (error as Error)?.message || 'Unknown error';
};

/**
 * Hold a save back until the user has seen what its renames would do.
 *
 * Renaming changes the delivered filename. The next campaign carries the
 * rename — Git stores a rename as a remove plus an add, so both halves ride
 * the same pull request and merging it completes the change — but a caller's
 * `uses:` line still points at the old name, and nothing rewrites that. The
 * backend refuses the cases it cannot reconcile, but a refusal arriving as a
 * bare 409 after the user has committed to the change is not a verification —
 * so the impact is fetched and shown first.
 *
 * Shared by the project toolbar's Save and the editor's Commit Locally so the
 * two cannot drift apart, which is the mistake that produced two
 * create_or_update_workflow implementations in the first place.
 */
export const useRenameConfirmation = (user: string, projectName: string) => {
  const [items, setItems] = useState<RenameImpactItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const proceedRef = useRef<(() => Promise<void>) | null>(null);
  // Which confirmation the in-flight request belongs to. Cancelling used to
  // leave the request running: it resolved, setItems ran unconditionally, and
  // the dialog re-opened for a rename the user had dismissed — with a Rename
  // button that silently did nothing, because cancel() had already dropped the
  // proceed callback. Bumping this on every start, confirm and cancel makes a
  // superseded response land nowhere.
  const generationRef = useRef(0);

  /** Run `proceed`, first confirming any renames it carries. */
  const confirmThen = useCallback(async (
    renames: PendingRename[],
    proceed: () => Promise<void>
  ): Promise<void> => {
    if (renames.length === 0) {
      await proceed();
      return;
    }

    const generation = ++generationRef.current;
    const current = () => generationRef.current === generation;

    proceedRef.current = proceed;
    setItems([]);
    setLoading(true);
    try {
      const resolved = await Promise.all(renames.map(async (rename): Promise<RenameImpactItem> => {
        try {
          return {
            ...rename,
            impact: await getRenameImpact(
              user, projectName, rename.previousName, rename.newName, rename.isReusable
            ),
            error: null,
          };
        } catch (error) {
          console.error('Error checking rename impact:', error);
          // Advisory only: the save enforces the same refusals. Failing closed
          // would make an unreachable preview block every rename.
          return { ...rename, impact: null, error: describeError(error) };
        }
      }));
      if (current()) setItems(resolved);
    } finally {
      if (current()) setLoading(false);
    }
  }, [user, projectName]);

  const confirm = useCallback(async (): Promise<void> => {
    const proceed = proceedRef.current;
    generationRef.current += 1;
    proceedRef.current = null;
    setItems(null);
    if (proceed) await proceed();
  }, []);

  const cancel = useCallback((): void => {
    generationRef.current += 1;
    proceedRef.current = null;
    setItems(null);
    setLoading(false);
  }, []);

  // `items` is null when no confirmation is pending, which is what drives
  // `renameOpen`; the dialog only wants the list, so it never sees the null.
  return {
    renameItems: items ?? [],
    renameLoading: loading,
    renameOpen: items !== null,
    confirmThen,
    confirm,
    cancel,
  };
};
