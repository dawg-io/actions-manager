/* eslint-disable no-restricted-syntax -- Diff view uses inline grid styling */
/**
 * Review-then-confirm gate for rolling a merged PR campaign back.
 *
 * Loads the proposed inverse diff for every repository in the campaign that
 * actually merged, shows it, and only then offers to open the rollback
 * campaign. Repositories whose change cannot be inverted automatically render
 * their reason in place of a diff — they are visibly excluded, never silently
 * dropped. Repositories that never merged are not listed at all; those are
 * handled by "Close Open PRs".
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  createCampaignRollback,
  previewCampaignRollback,
  PRCampaign,
  RollbackAmAction,
  RollbackCreateResponse,
  RollbackPreviewResponse,
  RollbackTarget,
} from "../api/pullRequests";
import { DiffColumns, diffGridStyle } from "./DiffColumns";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

interface RollbackCampaignModalProps {
  open: boolean;
  user: string;
  projectName: string;
  campaign: PRCampaign | null;
  onClose: () => void;
  onRolledBack: (result: RollbackCreateResponse) => void;
}

const AM_ACTION_OPTIONS: { value: RollbackAmAction; label: string; hint: string }[] = [
  {
    value: "revert",
    label: "Abandon this change",
    hint: "ActionsManager goes back to the previous version too. Nothing will be reported as drifted.",
  },
  {
    value: "keep",
    label: "Keep this change to retry later",
    hint: "GitHub goes back to the previous version, but ActionsManager keeps the new one so you can fix it and deliver it again. The rolled-back repositories will be reported as drifted until you do.",
  },
];

const TargetDiff: React.FC<{ target: RollbackTarget }> = ({ target }) => (
  <div className="pr-rollback-target" data-testid="rollback-target">
    <div className="pr-rollback-target-header">
      <strong>
        {target.repo_name} on {target.target_branch}
      </strong>
      <a
        className="pr-campaign-pr-link"
        href={target.pr_url}
        target="_blank"
        rel="noopener noreferrer"
      >
        #{target.pr_number}
      </a>
      {target.invertible ? (
        <span className="pr-rollback-badge pr-rollback-badge--ok">Can be rolled back</span>
      ) : (
        <span className="pr-rollback-badge pr-rollback-badge--blocked">Not invertible</span>
      )}
    </div>

    {!target.invertible && (
      <p className="pr-rollback-reason" data-testid="rollback-reason">
        {target.reason}
      </p>
    )}

    {target.files.map((file) => (
      <div key={file.path} className="pr-rollback-file">
        <div className="pr-rollback-file-path">
          <code>{file.path}</code>
          {file.action === "delete" && (
            <span className="pr-rollback-badge pr-rollback-badge--delete">Will be deleted</span>
          )}
        </div>
        <div
          className="border border-slate-200 dark:border-slate-700 rounded-md overflow-hidden"
          style={diffGridStyle}
        >
          <DiffColumns
            left={file.before}
            right={file.after}
            leftLabel={`Current on ${target.target_branch}`}
            rightLabel="After rollback"
          />
        </div>
      </div>
    ))}
  </div>
);

const RollbackCampaignModal: React.FC<RollbackCampaignModalProps> = ({
  open,
  user,
  projectName,
  campaign,
  onClose,
  onRolledBack,
}) => {
  const [preview, setPreview] = useState<RollbackPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [amAction, setAmAction] = useState<RollbackAmAction>("revert");

  const campaignId = campaign?.campaign_id ?? null;

  const loadPreview = useCallback(async () => {
    if (!campaignId) return;
    setLoading(true);
    setError(null);
    try {
      setPreview(await previewCampaignRollback(user, projectName, campaignId));
    } catch (err: any) {
      setPreview(null);
      setError(err.message || "Failed to load the rollback preview");
    } finally {
      setLoading(false);
    }
  }, [campaignId, user, projectName]);

  useEffect(() => {
    if (!open) return;
    setPreview(null);
    setError(null);
    setSubmitting(false);
    setAmAction("revert");
    loadPreview();
  }, [open, loadPreview]);

  const invertibleCount = preview?.invertible_count ?? 0;

  const handleConfirm = async () => {
    if (!campaignId) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await createCampaignRollback(user, projectName, campaignId, {
        amAction,
      });
      onRolledBack(result);
    } catch (err: any) {
      setError(err.message || "Failed to create the rollback campaign");
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <DialogContent className="pr-rollback-modal">
        <DialogHeader>
          <DialogTitle>Roll back {campaign?.campaign_name}</DialogTitle>
          <DialogDescription>
            Review the proposed inverse below. Confirming opens a new rollback campaign of
            reviewable pull requests — nothing is committed directly, and repositories whose
            pull requests never merged are left alone.
          </DialogDescription>
        </DialogHeader>

        {loading && <p data-testid="rollback-loading">Computing the inverse diff…</p>}
        {error && <p className="pr-rollback-error" data-testid="rollback-error">{error}</p>}

        {preview && !loading && (
          <div className="pr-rollback-body">
            <p className="pr-rollback-summary" data-testid="rollback-summary">
              {invertibleCount} of {preview.targets.length} merged{" "}
              {preview.targets.length === 1 ? "repository" : "repositories"} can be rolled back
              automatically.
            </p>

            {preview.targets.length === 0 && (
              <p className="pr-campaign-muted">
                No pull request in this campaign has merged, so there is nothing to invert.
              </p>
            )}

            {preview.targets.map((target) => (
              <TargetDiff key={`${target.repo_name}-${target.target_branch}`} target={target} />
            ))}

            {invertibleCount > 0 && (
              <fieldset className="pr-rollback-am-action">
                <legend>Once the rollback merges</legend>
                {AM_ACTION_OPTIONS.map((option) => (
                  <div key={option.value} className="pr-rollback-am-option">
                    <input
                      id={`rollback-am-${option.value}`}
                      type="radio"
                      name="rollback-am-action"
                      value={option.value}
                      checked={amAction === option.value}
                      onChange={() => setAmAction(option.value)}
                    />
                    <span>
                      {/* The label's own text, not a wrapper around it: the
                          hint is supplementary and stays outside. */}
                      <label htmlFor={`rollback-am-${option.value}`}>{option.label}</label>
                      <small>{option.hint}</small>
                    </span>
                  </div>
                ))}
              </fieldset>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={loading || submitting || invertibleCount === 0}
            data-testid="rollback-confirm"
          >
            {submitting
              ? "Opening rollback campaign…"
              : `Open rollback campaign (${invertibleCount})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default RollbackCampaignModal;
