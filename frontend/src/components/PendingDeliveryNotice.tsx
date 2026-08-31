import React from "react";
import { Button } from "./ui/button";

interface PendingDeliveryNoticeProps {
  /** Repositories that have never received any of the project's workflows. */
  repos: string[];
  /** Opens the PR campaign scoped to `repos`. Omitted for a read-only viewer. */
  onCreatePullRequests?: () => void;
}

/**
 * Reminds the user that repositories they added are still waiting for the
 * project's workflows.
 *
 * Deliberately not a warning. Nothing is broken — the repo simply hasn't been
 * delivered to yet, which is also why drift stays silent about it (see
 * `_delivery_confirmed_on_branch`). So this uses the blue informational palette
 * rather than the amber the drift banner owns, and the copy carries no urgency.
 * It clears itself once the workflows land.
 *
 * Anatomy mirrors the drift status row so the top of a project reads as one
 * consistent channel rather than a stack of unrelated bars.
 */
const PendingDeliveryNotice: React.FC<PendingDeliveryNoticeProps> = ({
  repos,
  onCreatePullRequests,
}) => {
  if (repos.length === 0) return null;

  const single = repos.length === 1;

  return (
    <output
      className="mx-4 mb-2 px-4 py-2.5 rounded-lg flex items-center gap-3 bg-blue-50 border border-blue-200 text-blue-900 dark:bg-blue-900/20 dark:border-blue-500/30 dark:text-blue-100"
      data-testid="pending-delivery-notice"
    >
      <svg
        className="h-[18px] w-[18px] shrink-0 text-blue-600 dark:text-blue-400"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="10" />
        <path d="m16 12-4-4-4 4" />
        <path d="M12 16V8" />
      </svg>

      <span className="flex-1 flex flex-col gap-0.5">
        <span className="text-sm font-medium">
          {single
            ? `${repos[0]} doesn't have this project's workflows yet`
            : `${repos.length} repositories don't have this project's workflows yet`}
        </span>
        <span className="text-xs leading-[17px] text-blue-700 dark:text-blue-300">
          {single ? "It was" : `${repos.join(", ")} were`} saved to the project.
          Create a pull request whenever it's convenient.
        </span>
      </span>

      {onCreatePullRequests && (
        <Button
          variant="outline"
          size="sm"
          onClick={onCreatePullRequests}
          className="shrink-0 gap-1.5"
          data-testid="pending-delivery-create-pr-button"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="18" cy="18" r="3" />
            <circle cx="6" cy="6" r="3" />
            <path d="M13 6h3a2 2 0 0 1 2 2v7" />
            <line x1="6" x2="6" y1="9" y2="21" />
          </svg>
          {single ? "Create pull request" : "Create pull requests"}
        </Button>
      )}
    </output>
  );
};

export default PendingDeliveryNotice;
