import React from 'react';
import { BookOpen, GitPullRequest, Radar, Workflow } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { getDocsUrl, HelpTopic } from '../help/helpLinks';

const NEXT_READS: { topic: HelpTopic; Icon: typeof BookOpen; label: string; blurb: string }[] = [
  {
    topic: 'quickStart',
    Icon: BookOpen,
    label: 'Quick Start',
    blurb: 'The same path you just walked, written down.',
  },
  {
    topic: 'workflows',
    Icon: Workflow,
    label: 'Workflows',
    blurb: 'Editing, importing and versioning workflows across a project.',
  },
  {
    topic: 'prCampaigns',
    Icon: GitPullRequest,
    label: 'PR campaigns',
    blurb: 'Rolling one change out to many repositories, and rolling it back.',
  },
  {
    topic: 'driftDetection',
    Icon: Radar,
    label: 'Drift detection',
    blurb: 'Spotting repositories that have diverged from the definition you expect.',
  },
];

export interface OnboardingCompleteProps {
  open: boolean;
  /** Called when the user closes it; should record onboarding as completed. */
  onClose: () => void;
}

const OnboardingComplete: React.FC<OnboardingCompleteProps> = ({ open, onClose }) => (
  <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
    <DialogContent className="max-w-xl" data-testid="onboarding-complete">
      <DialogHeader>
        <DialogTitle>That is the whole loop</DialogTitle>
        <DialogDescription>
          You created a project, added a workflow, saved it as a local draft, proposed it to GitHub
          as a pull request, and closed the campaign out. Everything else in ActionsManager is a
          variation on those steps.
        </DialogDescription>
      </DialogHeader>

      <ul className="space-y-3">
        {NEXT_READS.map(({ topic, Icon, label, blurb }) => (
          <li key={topic}>
            <a
              className="flex gap-3 rounded-lg border border-border p-3 transition-colors hover:bg-hover-bg dark:border-border-dark dark:hover:bg-hover-dark-bg"
              href={getDocsUrl(topic)}
              rel="noreferrer"
              target="_blank"
            >
              <span className="mt-0.5 shrink-0 text-primary dark:text-primary-dark" aria-hidden="true">
                <Icon size={18} strokeWidth={1.75} />
              </span>
              <span>
                <span className="block text-sm font-medium text-text-primary dark:text-text-primary-dark">
                  {label}
                </span>
                <span className="block text-sm text-text-muted dark:text-text-muted-dark">{blurb}</span>
              </span>
            </a>
          </li>
        ))}
      </ul>

      <DialogFooter>
        <Button data-testid="onboarding-complete-close" onClick={onClose}>
          Done
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
);

export default OnboardingComplete;
