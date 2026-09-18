import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import type { RenameImpact } from '../api/workflows';
import type { RenameImpactItem } from '../hooks/useRenameConfirmation';

export interface RenameImpactDialogProps {
  open: boolean;
  /** One entry per renamed workflow in the save being confirmed. */
  items: RenameImpactItem[];
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Where the old filename is, or may still be, on GitHub — so where the rename lands. */
const renameTargets = (impact: RenameImpact) =>
  impact.targets.filter(t => t.old_file_present !== false);

/**
 * Whether GitHub answered for every target. When it did not, the dialog must
 * say so rather than presenting an incomplete list as the whole story — the
 * report deliberately reports `null` instead of `false` for exactly this.
 */
const hasUnknowns = (impact: RenameImpact) =>
  impact.classification === 'unknown' ||
  impact.targets.some(t => t.old_file_present === null);

const RenameSection: React.FC<{ item: RenameImpactItem; showHeading: boolean }> = ({
  item,
  showHeading,
}) => {
  const { impact, error } = item;

  return (
    <div className="space-y-2" data-testid={`rename-item-${item.previousName}`}>
      {showHeading && (
        <p className="font-medium text-slate-700 dark:text-slate-300">
          {item.previousName} → {item.newName}
        </p>
      )}

      {impact?.blocked_reason && (
        <p className="text-red-600 dark:text-red-400" data-testid="rename-blocked-reason">
          {impact.blocked_reason}
        </p>
      )}

      {!impact && (
        <p className="text-amber-600 dark:text-amber-400" data-testid="rename-check-failed">
          The impact check failed{error ? `: ${error}` : ''}. Renaming is still safe to
          attempt — the save refuses a rename that cannot be performed and tells you why,
          and the next pull request carries the rename either way. What you lose is the
          list of repositories it will touch.
        </p>
      )}

      {impact && !impact.blocked_reason && renameTargets(impact).length > 0 && (
        <div data-testid="rename-targets">
          <p>
            The next pull request renames <strong>{impact.old_filename}</strong> to{' '}
            <strong>{impact.new_filename}</strong> in:
          </p>
          <ul className="mt-1 list-disc pl-5">
            {renameTargets(impact).map(t => (
              <li key={`${t.repo}@${t.branch}`}>
                {t.repo} @ {t.branch}
                {t.old_file_present === null && ' (could not be checked)'}
              </li>
            ))}
          </ul>
          <p className="mt-1">Merging that pull request completes the rename.</p>
        </div>
      )}

      {impact && !impact.blocked_reason && renameTargets(impact).length === 0 && (
        <p data-testid="rename-not-delivered">
          Nothing has been delivered under the old name, so this renames it here only.
        </p>
      )}

      {impact && impact.consumers.length > 0 && (
        <div data-testid="rename-consumers">
          <p>{impact.consumers.length} caller workflow(s) reference it by filename:</p>
          <ul className="mt-1 list-disc pl-5">
            {impact.consumers.map(c => (
              <li key={`${c.project_name}/${c.workflow_name}`}>
                {c.project_name} — {c.workflow_name}
              </li>
            ))}
          </ul>
        </div>
      )}

      {impact && impact.overrides.length > 0 && (
        <p data-testid="rename-overrides">
          Per-repository overrides exist for: {impact.overrides.join(', ')}.
        </p>
      )}

      {impact && hasUnknowns(impact) && (
        <p className="text-amber-600 dark:text-amber-400" data-testid="rename-unknown">
          GitHub could not be reached for every repository, so this list may be incomplete.
        </p>
      )}

      {impact?.warnings.map(w => (
        <p key={w} className="text-amber-600 dark:text-amber-400">{w}</p>
      ))}
    </div>
  );
};

const RenameImpactDialog: React.FC<RenameImpactDialogProps> = ({
  open,
  items,
  loading = false,
  onConfirm,
  onCancel,
}) => {
  // One blocked rename blocks the whole save: a project save carries its
  // workflows together, so letting it through would apply the others and fail
  // this one partway.
  const blocked = items.some(i => i.impact?.blocked_reason);
  const single = items.length === 1 ? items[0] : null;

  const describe = (): string => {
    if (loading) return 'Checking what this rename would affect…';
    if (single?.impact) return `${single.impact.old_filename} → ${single.impact.new_filename}`;
    if (single) return `${single.previousName} → ${single.newName}`;
    return `${items.length} workflows are renamed by this save.`;
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onCancel(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {(() => {
              if (blocked) return 'This save cannot be applied';
              return items.length > 1 ? 'Save these renames?' : 'Rename this workflow?';
            })()}
          </DialogTitle>
          <DialogDescription>{describe()}</DialogDescription>
        </DialogHeader>

        {/* The dialog opens on the loading state and swaps the whole body in when
            the answer arrives. Without a live region a screen reader hears
            "Checking what this rename would affect…" and is never told the
            result, while the Rename button silently becomes enabled. */}
        <div aria-live="polite" aria-busy={loading}>
        {!loading && items.length > 0 && (
          <div className="space-y-4 text-sm text-slate-600 dark:text-slate-400">
            {items.map(item => (
              <RenameSection
                key={`${item.previousName}->${item.newName}`}
                item={item}
                showHeading={items.length > 1}
              />
            ))}
          </div>
        )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCancel} data-testid="rename-dismiss">
            {blocked ? 'Close' : 'Cancel'}
          </Button>
          {!blocked && (
            <Button onClick={onConfirm} disabled={loading}>
              {items.length > 1 ? 'Save' : 'Rename'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default RenameImpactDialog;
