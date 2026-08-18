import React, { useState } from 'react';
import { FolderGit2, GitPullRequest, Radar } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import BrandLogo from './BrandLogo';
import { getDocsUrl } from '../help/helpLinks';
import type { UserDetails } from '../api/user';

/**
 * Whether the first-login welcome screen should be offered to this user.
 *
 * Read-only members are deliberately excluded. WriteProtectionMiddleware
 * rejects every /api/* write for them, so they could never dismiss it and it
 * would reappear on every login. They also cannot create a project, which is
 * what the onboarding is for. Promoting them to member later makes the
 * welcome screen appear then, which is the behaviour we want.
 *
 * The backend must say so explicitly: a missing `onboarding` field means the
 * API does not report onboarding state at all, not that onboarding is
 * pending. Treating absence as "show it" would put an undismissable dialog in
 * front of every user of a frontend running ahead of its backend — the PUT
 * that records the dismissal would 404, so the screen would return on every
 * login.
 */
export function shouldShowWelcome(userDetails: UserDetails | undefined): boolean {
  if (!userDetails?.onboarding) return false;
  if (userDetails.workspace_role === 'read_only') return false;
  // A recorded step means the tour is already under way, so the welcome screen
  // has been answered. Without this it would reopen over the tour on reload.
  if (userDetails.onboarding.step) return false;
  return userDetails.onboarding.completed !== true;
}

const HIGHLIGHTS = [
  {
    Icon: FolderGit2,
    title: 'Group repositories into projects',
    body: 'A project holds the repositories you want to manage together, so one workflow change can target all of them at once.',
  },
  {
    Icon: GitPullRequest,
    title: 'Deliver changes as pull requests',
    body: 'Workflows are saved as local drafts first. Nothing reaches GitHub until you create a PR campaign and the pull requests are merged.',
  },
  {
    Icon: Radar,
    title: 'Catch drift before it spreads',
    body: 'Drift detection tells you when a repository has diverged from the workflow definition you expect it to have.',
  },
];

export interface OnboardingWelcomeProps {
  /** Whether the welcome screen is shown. */
  open: boolean;
  /** Called once the user has acknowledged it; should persist the dismissal. */
  onDismiss: () => void | Promise<void>;
  /** Called when the user opts into the guided tour. */
  onStartTour: () => void | Promise<void>;
}

const OnboardingWelcome: React.FC<OnboardingWelcomeProps> = ({ open, onDismiss, onStartTour }) => {
  const [isBusy, setIsBusy] = useState(false);

  const run = async (action: () => void | Promise<void>): Promise<void> => {
    setIsBusy(true);
    try {
      await action();
    } finally {
      setIsBusy(false);
    }
  };

  const handleDismiss = (): Promise<void> => run(onDismiss);

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) void handleDismiss(); }}>
      <DialogContent className="max-w-xl" data-testid="onboarding-welcome">
        <DialogHeader>
          <div className="mb-2 flex justify-center sm:justify-start">
            <BrandLogo variant="full" size="md" />
          </div>
          <DialogTitle>Welcome to ActionsManager</DialogTitle>
          <DialogDescription>
            A control plane for GitHub Actions across every repository you manage, rather than one
            repository at a time.
          </DialogDescription>
        </DialogHeader>

        <ul className="space-y-4">
          {HIGHLIGHTS.map(({ Icon, title, body }) => (
            <li key={title} className="flex gap-3">
              <span
                className="mt-0.5 shrink-0 text-primary dark:text-primary-dark"
                aria-hidden="true"
              >
                <Icon size={18} strokeWidth={1.75} />
              </span>
              <div>
                <p className="text-sm font-medium text-text-primary dark:text-text-primary-dark">
                  {title}
                </p>
                <p className="text-sm text-text-muted dark:text-text-muted-dark">{body}</p>
              </div>
            </li>
          ))}
        </ul>

        <DialogFooter className="sm:items-center sm:justify-between">
          <a
            className="text-sm text-primary underline-offset-4 hover:underline dark:text-primary-dark"
            href={getDocsUrl('quickStart')}
            rel="noreferrer"
            target="_blank"
          >
            Read the Quick Start guide
          </a>
          <div className="flex gap-2">
            <Button
              data-testid="onboarding-welcome-dismiss"
              disabled={isBusy}
              onClick={() => { void handleDismiss(); }}
              variant="outline"
            >
              Not now
            </Button>
            <Button
              data-testid="onboarding-welcome-start-tour"
              disabled={isBusy}
              onClick={() => { void run(onStartTour); }}
            >
              Show me around
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default OnboardingWelcome;
