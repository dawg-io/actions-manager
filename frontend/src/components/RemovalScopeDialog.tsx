import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';

/**
 * Which copies of a project resource a removal should destroy. 'github' is the
 * inverse of 'project': it stops enforcing the resource on the repositories but
 * keeps ActionsManager's record, so it can be applied again. Only offered where
 * the backend accepts it — see `offerGitHubOnly`.
 */
export type RemovalScope = 'project' | 'github' | 'project_and_github';

/** How a GitHub-scoped removal reaches the repositories. */
export type RemovalDelivery = 'campaign' | 'direct';

export interface RemovalScopeDialogProps {
  open: boolean;
  /** e.g. `Remove workflow "AM-ci.yml"?` */
  title: string;
  /** Where the GitHub copy lives, e.g. "your project's repositories". */
  githubLocation: string;
  /**
   * What the resource is called in the dialog's prose. Defaults to "file",
   * which is what workflows and custom files are; a ruleset is repository
   * settings, so calling it a file would be wrong.
   */
  resourceNoun?: string;
  /**
   * What ActionsManager stops doing for the resource once it is untracked, when
   * the file-shaped default does not apply — a ruleset has no drift detection,
   * delivery or version history to lose.
   */
  projectScopeDetail?: string;
  /** True when the resource has never been pushed, so there is no GitHub copy to delete. */
  neverSynced?: boolean;
  /**
   * Why the GitHub option cannot apply, when a copy does exist but this project
   * may not delete it — a reusable workflow living in a caller project, whose
   * repository belongs to the Reusable Workflow Project that owns it. Disables
   * the option and says so, rather than letting the request earn a 409.
   */
  githubScopeDisabledReason?: string;
  /**
   * What the GitHub-scoped removal actually does, when it is not an immediate
   * permanent delete — custom files, for instance, only queue the deletion for
   * the next delivery and can be restored until then.
   */
  githubScopeWarning?: string;
  /**
   * Offer a delivery choice under the GitHub option. Omit it and the dialog keeps
   * its single-question shape, which is all a resource deleted straight from
   * GitHub (workflows) needs.
   */
  offerDelivery?: boolean;
  /**
   * Offer "remove from GitHub only", keeping the ActionsManager record. Opt-in:
   * the workflow and custom-file routes accept just 'project' and
   * 'project_and_github', so offering it there would earn a 400.
   */
  offerGitHubOnly?: boolean;
  /** What keeping the ActionsManager record buys, under the GitHub-only option. */
  githubOnlyDetail?: string;
  /**
   * How a campaign-delivered removal is undone, when it is not the Restore
   * button custom files have. Workflows have no Restore, so for them the only
   * way back is closing the pull request — saying "Restore" would point at
   * something that does not exist.
   */
  campaignReversal?: string;
  onConfirm: (scope: RemovalScope, delivery: RemovalDelivery) => void;
  onCancel: () => void;
}

interface ScopeOptionProps {
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
  label: string;
  ariaLabel: string;
  /** Radio group. The delivery options form their own group inside a scope option. */
  group?: string;
  children: React.ReactNode;
}

const ScopeOption: React.FC<ScopeOptionProps> = ({
  selected,
  disabled,
  onSelect,
  label,
  ariaLabel,
  group = 'removalScope',
  children,
}) => (
  <div
    className={`border-2 rounded-lg transition-all ${
      disabled
        ? 'opacity-60 border-slate-200 dark:border-slate-600'
        : 'border-slate-200 hover:border-blue-500 dark:border-slate-600 dark:hover:border-blue-400'
    }`}
  >
    <label className={`flex items-start p-4 ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}>
      {/* Named on the input rather than the label: the label wraps a paragraph of
          explanation, which would otherwise become the radio's accessible name. */}
      <input
        type="radio"
        name={group}
        aria-label={ariaLabel}
        checked={selected}
        onChange={onSelect}
        disabled={disabled}
        className="mt-1 mr-3 flex-shrink-0"
      />
      <div className="flex-1">
        <strong className="block text-base text-slate-900 mb-1 dark:text-slate-100">{label}</strong>
        {children}
      </div>
    </label>
  </div>
);

const DEFAULT_GITHUB_WARNING =
  'This action cannot be undone! The file will be permanently deleted from GitHub.';

const DEFAULT_PROJECT_SCOPE_DETAIL =
  'its drift detection, delivery and version history are removed';

const DEFAULT_GITHUB_ONLY_DETAIL =
  'ActionsManager keeps tracking it, so you can apply it again later';

/**
 * Shown under whichever scope reaches GitHub. Keeping the ActionsManager record
 * does not make the GitHub deletion reversible, so the GitHub-only option needs
 * this every bit as much as the delete-everywhere one.
 */
const GitHubScopeWarning: React.FC<{ warning: string }> = ({ warning }) => (
  <div className="bg-amber-50 border border-amber-200 rounded-md p-3 mt-3 dark:bg-amber-950 dark:border-amber-800">
    <p className="text-amber-800 text-sm dark:text-amber-200">
      ⚠️ <strong>Warning:</strong> {warning}
    </p>
  </div>
);

const DEFAULT_CAMPAIGN_REVERSAL = 'you can Restore it here until then';

interface DeliveryChoiceProps {
  delivery: RemovalDelivery;
  onChange: (delivery: RemovalDelivery) => void;
  githubLocation: string;
  campaignReversal: string;
}

const DeliveryOption: React.FC<{
  label: string;
  selected: boolean;
  onSelect: () => void;
  children: React.ReactNode;
}> = ({ label, selected, onSelect, children }) => (
  <label className="flex items-start cursor-pointer">
    <input
      type="radio"
      name="removalDelivery"
      aria-label={label}
      checked={selected}
      onChange={onSelect}
      className="mt-1 mr-3 flex-shrink-0"
    />
    <span className="text-sm text-slate-600 dark:text-slate-400">
      <strong className="block text-slate-900 dark:text-slate-100">{label}</strong>
      <span className="block">{children}</span>
    </span>
  </label>
);

const DeliveryChoice: React.FC<DeliveryChoiceProps> = ({ delivery, onChange, githubLocation, campaignReversal }) => (
  <fieldset className="mt-3 border-t border-slate-200 pt-3 dark:border-slate-600">
    <legend className="text-sm font-semibold text-slate-900 mb-2 dark:text-slate-100">
      How should the file be removed from GitHub?
    </legend>
    <div className="space-y-2">
      <DeliveryOption
        label="Create a PR Campaign"
        selected={delivery === 'campaign'}
        onSelect={() => onChange('campaign')}
      >
        Opens a PR Campaign covering {githubLocation}, so the deletion is tracked and merged from
        PR Campaigns like any other delivery. The file is removed when the campaign merges, and
        {' '}{campaignReversal}.
      </DeliveryOption>
      <DeliveryOption
        label="Commit directly to the target branch"
        selected={delivery === 'direct'}
        onSelect={() => onChange('direct')}
      >
        The file is deleted immediately, with no review. There is nothing to restore afterwards.
      </DeliveryOption>
    </div>
  </fieldset>
);

/**
 * Asks whether a project resource should be removed from ActionsManager only or
 * from GitHub as well, mirroring the choice DeleteProjectModal offers for a whole
 * project. Shared by every resource that keeps a local copy and a GitHub copy.
 */
const RemovalScopeDialog: React.FC<RemovalScopeDialogProps> = ({
  open,
  title,
  githubLocation,
  resourceNoun = 'file',
  projectScopeDetail = DEFAULT_PROJECT_SCOPE_DETAIL,
  neverSynced = false,
  githubScopeDisabledReason,
  githubScopeWarning = DEFAULT_GITHUB_WARNING,
  offerDelivery = false,
  offerGitHubOnly = false,
  githubOnlyDetail = DEFAULT_GITHUB_ONLY_DETAIL,
  campaignReversal = DEFAULT_CAMPAIGN_REVERSAL,
  onConfirm,
  onCancel,
}) => {
  const [scope, setScope] = useState<RemovalScope>('project');
  const [delivery, setDelivery] = useState<RemovalDelivery>('campaign');

  // Consumers may keep this mounted between removals, so the safe options have to
  // be re-selected each time it opens rather than only at mount.
  useEffect(() => {
    if (open) {
      setScope('project');
      setDelivery('campaign');
    }
  }, [open]);

  const githubDisabled = neverSynced || !!githubScopeDisabledReason;
  const deletesFromGitHub = scope === 'project_and_github';
  const githubOnly = scope === 'github';
  const showsDelivery = offerDelivery && deletesFromGitHub;
  // Reviewable removal is reversible, so the permanent-deletion warning is only
  // honest for a direct commit.
  const warning = showsDelivery && delivery === 'campaign'
    ? `The ${resourceNoun} is removed from ${githubLocation} when the campaign merges — ${campaignReversal}.`
    : githubScopeWarning;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onCancel(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Choose whether the copy in {githubLocation} is deleted too.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <ScopeOption
            selected={scope === 'project'}
            onSelect={() => setScope('project')}
            label="🏠 Remove from ActionsManager only"
            ariaLabel="Remove from ActionsManager only"
          >
            <p className="text-slate-600 text-sm leading-relaxed dark:text-slate-400">
              {neverSynced
                ? 'Nothing was ever delivered, so this only removes the ActionsManager record.'
                : `The ${resourceNoun} stays in ${githubLocation}. ActionsManager stops tracking it, so ${projectScopeDetail}.`}
            </p>
          </ScopeOption>

          {offerGitHubOnly && (
            <ScopeOption
              selected={githubOnly}
              disabled={githubDisabled}
              onSelect={() => setScope('github')}
              label="☁️ Remove from GitHub only"
              ariaLabel="Remove from GitHub only"
            >
              <p className="text-slate-600 text-sm leading-relaxed dark:text-slate-400">
                {githubScopeDisabledReason ??
                  `Removes the ${resourceNoun} from ${githubLocation}. ${githubOnlyDetail}.`}
                {neverSynced && ' (Nothing in GitHub yet.)'}
              </p>
              {githubOnly && <GitHubScopeWarning warning={githubScopeWarning} />}
            </ScopeOption>
          )}

          <ScopeOption
            selected={deletesFromGitHub}
            disabled={githubDisabled}
            onSelect={() => setScope('project_and_github')}
            label="💥 Delete from ActionsManager and GitHub"
            ariaLabel="Delete from ActionsManager and GitHub"
          >
            <p className="text-slate-600 text-sm leading-relaxed dark:text-slate-400">
              {githubScopeDisabledReason ??
                `Removes it from ActionsManager and deletes the ${resourceNoun} from ${githubLocation}.`}
              {neverSynced && ' (Nothing in GitHub yet.)'}
            </p>
            {showsDelivery && (
              <DeliveryChoice
                campaignReversal={campaignReversal}
                delivery={delivery}
                onChange={setDelivery}
                githubLocation={githubLocation}
              />
            )}
            {deletesFromGitHub && (
              <GitHubScopeWarning warning={warning} />
            )}
          </ScopeOption>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={() => onConfirm(scope, delivery)}>
            {deletesFromGitHub && '🗑️ Delete Everywhere'}
            {githubOnly && '🗑️ Remove from GitHub'}
            {scope === 'project' && '🗑️ Remove from ActionsManager'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default RemovalScopeDialog;
