import React, { useCallback, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router';
import TourCallout from './TourCallout';
import OnboardingComplete from './OnboardingComplete';
import { tour, TourStepId } from '../utils/tour';
import type { OnboardingState, UserDetails } from '../api/user';

interface TourStepDefinition {
  id: TourStepId;
  title: string;
  body: string;
  /**
   * data-testid of the control that ADVANCES this step — the button the user
   * presses next, not the thing being explained. Anchoring at the explanation
   * put the callout in the middle of the form, covering the fields below it.
   */
  targetTestId: string;
  /** Where the target lives, for the "Take me there" action. */
  path: (user: string, project: string | null) => string;
}

/** Route for a step that happens inside the created project. */
const inProject = (user: string, project: string | null): string =>
  project ? `/project/${user}/${encodeURIComponent(project)}` : `/project/${user}`;

/**
 * The guided tour's steps, in order.
 *
 * The tour fills forms in; the user presses the buttons. Every step advances
 * only when the product code reports the user really did the thing — nothing
 * here clicks on their behalf, because these are real changes against their
 * own GitHub repositories.
 */
export const TOUR_STEPS: readonly TourStepDefinition[] = [
  {
    id: 'open-wizard',
    title: 'Start with a project',
    body: 'A project groups the repositories you want to manage together, so one workflow change can target all of them. Click New Project to open the guided setup.',
    targetTestId: 'new-project-button',
    path: (user) => `/project/${user}`,
  },
  {
    id: 'project-basics',
    title: 'Name, type and colour',
    body: 'The name and colour are filled in for you. Leave the type as Caller Workflow Project — that manages repositories which consume workflows. A Reusable Workflow Project authors the shared workflows they call, which is not what you want first. Press Continue.',
    targetTestId: 'wizard-continue',
    path: (user) => `/project/${user}/new`,
  },
  {
    id: 'pick-repos',
    title: 'Choose a repository',
    body: 'This part is yours: pick a throwaway repository, because the tour opens a real pull request against it later. No spare repo? Use "Create a demo repository" above the list. Then press Continue.',
    targetTestId: 'wizard-continue',
    path: (user) => `/project/${user}/new`,
  },
  {
    id: 'naming-mode',
    title: 'How resources get named',
    body: 'Prefix Mode is already selected. It prefixes generated resources so they cannot collide with anything already in the repository. No Prefix Mode leaves names untouched — advanced only, for when you manage collisions yourself. Press Create Project.',
    targetTestId: 'create-project-button',
    path: (user) => `/project/${user}/new`,
  },
  {
    id: 'add-workflow',
    title: 'Add a workflow',
    body: 'Your project exists but has no files yet. Click Add Workflow to create the first one.',
    targetTestId: 'add-workflow-button',
    path: inProject,
  },
  {
    id: 'choose-workflow-type',
    title: 'Pick Workflow',
    body: 'Choose "Workflow" — a standard workflow that runs in the repositories this project manages. "Reusable Workflow" is for authoring shared workflows that others call, which belongs in a Reusable Workflow Project.',
    targetTestId: 'workflow-type-regular',
    path: inProject,
  },
  {
    id: 'start-workflow',
    title: 'Name it and start from blank',
    body: 'The name is filled in for you. Click "Open Blank Workflow" to get an editable file straight away. "Detect Build Types" and "Generate Templates" inspect your repositories and suggest workflows instead — worth trying once you have finished the tour.',
    targetTestId: 'workflow-start-blank',
    path: inProject,
  },
  {
    id: 'commit-workflow',
    title: 'Save it as a local draft',
    body: 'Commit Locally saves the workflow inside ActionsManager only. Nothing reaches GitHub until you deliberately create pull requests, so you can edit freely first.',
    targetTestId: 'commit-locally-button',
    path: inProject,
  },
  {
    id: 'create-campaign',
    title: 'Propose it to GitHub',
    body: 'A PR campaign opens one pull request per repository in the project. This is the first step that writes to GitHub, so review the selection before you confirm.',
    targetTestId: 'create-pull-requests-button',
    path: inProject,
  },
  {
    id: 'confirm-campaign',
    title: 'Confirm the pull requests',
    body: 'Everything in this project is selected by default. Check the workflow and repository lists, then press the create button to open the pull requests on GitHub.',
    targetTestId: 'confirm-create-prs',
    path: inProject,
  },
  {
    id: 'open-campaigns',
    title: 'Find your campaign',
    body: 'The pull requests are open. PR Campaigns is where you track and finish a rollout — open it from the sidebar, or from the Manage PR Campaign button on the banner.',
    targetTestId: 'pr-campaigns-nav',
    path: inProject,
  },
  {
    id: 'resolve-pr',
    title: 'Merge or close the pull request',
    body: 'Merging delivers the workflow and marks it synced. Closing it without merging is just as valid for a trial run — either one finishes the campaign.',
    targetTestId: 'pr-merge-button',
    path: inProject,
  },
];

/** Index of the step to show, or -1 when no tour should be running. */
export function resolveActiveStep(onboarding: OnboardingState | undefined): number {
  if (!onboarding || onboarding.completed || !onboarding.step) return -1;
  return TOUR_STEPS.findIndex((step) => step.id === onboarding.step);
}

export interface OnboardingTourProps {
  user: string;
  userDetails: UserDetails | undefined;
  /** Persists the new state and updates the copy App holds. */
  onAdvance: (state: { step?: TourStepId; completed?: boolean }) => void | Promise<void>;
}

const OnboardingTour: React.FC<OnboardingTourProps> = ({ user, userDetails, onAdvance }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const onboarding = userDetails?.onboarding;
  const activeIndex = resolveActiveStep(onboarding);
  const activeStep = activeIndex >= 0 ? TOUR_STEPS[activeIndex] : null;
  const isFinished = !onboarding?.completed && onboarding?.step === 'finished';

  // Publish the active step so a screen can seed demo values without being
  // wired to the tour. See utils/tour.ts.
  useEffect(() => {
    tour.activeStep = activeStep?.id ?? (isFinished ? 'finished' : null);
    return () => {
      tour.activeStep = null;
    };
  }, [activeStep, isFinished]);

  const advance = useCallback((): void => {
    const next = TOUR_STEPS[activeIndex + 1];
    // Past the last step the tour is over but not dismissed: 'finished' holds
    // the closing screen open until the user acknowledges it.
    void onAdvance({ step: next ? next.id : 'finished' });
  }, [activeIndex, onAdvance]);

  useEffect(() => {
    if (!activeStep) return;
    return tour.subscribe((stepId) => {
      if (stepId === activeStep.id) advance();
    });
  }, [activeStep, advance]);

  // The first step has no product-code signal to fire: reaching the wizard is
  // itself the completion, and the route is the only honest evidence of it.
  useEffect(() => {
    if (activeStep?.id === 'open-wizard' && location.pathname.endsWith('/new')) {
      advance();
    }
  }, [activeStep, location.pathname, advance]);

  if (isFinished) {
    return <OnboardingComplete onClose={() => { void onAdvance({ completed: true }); }} open />;
  }

  if (!activeStep) return null;

  const demoProject = tour.demoProjectName;
  const destination = activeStep.path(user, demoProject);
  // A button that navigates to the route you are already on does nothing, so
  // only offer it when it actually goes somewhere.
  const canNavigate = destination !== location.pathname;

  // On the dashboard mid-tour — the user pressed Back to Projects — point at
  // their project's card rather than at a control that is not on this screen.
  const onDashboard = location.pathname === `/project/${user}`;
  const showProjectCard = onDashboard && canNavigate && demoProject;

  return (
    <TourCallout
      // When the card is on screen it becomes the thing to click, so the body
      // has to say that — the away message only shows with no anchor at all.
      body={
        showProjectCard
          ? `Open ${demoProject} to carry on with "${activeStep.title}".`
          : activeStep.body
      }
      navigateLabel={demoProject ? `Open ${demoProject}` : 'Take me there'}
      onNavigate={canNavigate ? () => navigate(destination) : undefined}
      onSkip={() => { void onAdvance({ completed: true }); }}
      stepNumber={activeIndex + 1}
      targetTestId={showProjectCard ? `project-row-${demoProject}` : activeStep.targetTestId}
      title={activeStep.title}
      totalSteps={TOUR_STEPS.length}
    />
  );
};

export default OnboardingTour;
