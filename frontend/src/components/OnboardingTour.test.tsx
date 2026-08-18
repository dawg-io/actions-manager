import React from 'react';
import { MemoryRouter } from 'react-router';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import OnboardingTour, { TOUR_STEPS, resolveActiveStep } from './OnboardingTour';
import { tour, TourSignals } from '../utils/tour';
import type { OnboardingState, UserDetails } from '../api/user';

const withOnboarding = (onboarding: Partial<OnboardingState>): UserDetails => ({
  github_user: 'testuser',
  avatar_url: '',
  account_type: 'free',
  workspace_role: 'admin',
  onboarding: { completed: false, completed_at: null, step: null, ...onboarding },
});

const renderTour = (userDetails: UserDetails | undefined, onAdvance = vi.fn()) => {
  const view = render(
    <MemoryRouter>
      <OnboardingTour onAdvance={onAdvance} user="testuser" userDetails={userDetails} />
    </MemoryRouter>,
  );
  return { ...view, onAdvance };
};

describe('TourSignals', () => {
  test('delivers a completion to every subscriber', () => {
    const signals = new TourSignals();
    const a = vi.fn();
    const b = vi.fn();
    signals.subscribe(a);
    signals.subscribe(b);

    signals.completed('open-wizard');

    expect(a).toHaveBeenCalledWith('open-wizard');
    expect(b).toHaveBeenCalledWith('open-wizard');
  });

  test('firing with no subscribers is harmless', () => {
    // Product code calls this unconditionally, so it must not care whether a
    // tour is running.
    expect(() => new TourSignals().completed('open-wizard')).not.toThrow();
  });

  test('unsubscribing stops delivery', () => {
    const signals = new TourSignals();
    const listener = vi.fn();
    const unsubscribe = signals.subscribe(listener);

    unsubscribe();
    signals.completed('open-wizard');

    expect(listener).not.toHaveBeenCalled();
  });
});

describe('resolveActiveStep', () => {
  test('is inactive when onboarding state is absent', () => {
    expect(resolveActiveStep(undefined)).toBe(-1);
  });

  test('is inactive before the user opts in', () => {
    expect(resolveActiveStep({ completed: false, completed_at: null, step: null })).toBe(-1);
  });

  test('is inactive once onboarding is complete', () => {
    expect(
      resolveActiveStep({ completed: true, completed_at: '2026-08-16T00:00:00Z', step: 'open-wizard' }),
    ).toBe(-1);
  });

  test('resumes at the recorded step', () => {
    expect(resolveActiveStep({ completed: false, completed_at: null, step: 'open-wizard' })).toBe(0);
  });

  test('is inactive for a step name it does not recognise', () => {
    // An unknown step (older or newer frontend) must not crash the tour.
    expect(
      resolveActiveStep({ completed: false, completed_at: null, step: 'not-a-real-step' }),
    ).toBe(-1);
  });
});

describe('TOUR_STEPS anchoring', () => {
  // Every step must point at the control that ADVANCES it, never at the thing
  // being explained. Anchoring at the explanation put the callout in the
  // middle of the form and covered the fields below it — the colour picker on
  // step 2, the visibility options on step 3. This table is the guard.
  const ADVANCING_CONTROLS = new Set([
    'new-project-button',
    'wizard-continue',
    'create-project-button',
    'add-workflow-button',
    'workflow-type-regular',
    'workflow-start-blank',
    'commit-locally-button',
    'create-pull-requests-button',
    'confirm-create-prs',
    'pr-campaigns-nav',
    'pr-merge-button',
  ]);

  test.each(TOUR_STEPS.map((step) => [step.id, step.targetTestId]))(
    '%s anchors to an actionable control (%s)',
    (_id, targetTestId) => {
      expect(ADVANCING_CONTROLS.has(targetTestId as string)).toBe(true);
    },
  );

  test('every step has a distinct id', () => {
    const ids = TOUR_STEPS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe('OnboardingTour', () => {
  // Remove only the stub targets these tests append. Wiping document.body
  // would take Radix's dialog portal with it, and Testing Library's own
  // cleanup then fails trying to unmount a node that is already gone.
  afterEach(() => {
    document.querySelectorAll('[data-testid="new-project-button"]').forEach((el) => el.remove());
  });

  test('renders nothing when no tour is running', () => {
    renderTour(withOnboarding({ step: null }));
    expect(screen.queryByTestId('tour-callout')).not.toBeInTheDocument();
  });

  test('renders nothing once onboarding is completed', () => {
    renderTour(withOnboarding({ completed: true, step: 'open-wizard' }));
    expect(screen.queryByTestId('tour-callout')).not.toBeInTheDocument();
  });

  test('shows the active step with its position in the tour', () => {
    renderTour(withOnboarding({ step: 'open-wizard' }));

    expect(screen.getByTestId('tour-callout')).toBeInTheDocument();
    expect(screen.getByText('Start with a project')).toBeInTheDocument();
    expect(screen.getByText(`Step 1 of ${TOUR_STEPS.length}`)).toBeInTheDocument();
  });

  test('labels itself for assistive tech', () => {
    renderTour(withOnboarding({ step: 'open-wizard' }));

    expect(
      screen.getByRole('complementary', { name: `Onboarding step 1 of ${TOUR_STEPS.length}` }),
    ).toBeInTheDocument();
  });

  test('moves to the next step when the real signal for the active step arrives', async () => {
    const { onAdvance } = renderTour(withOnboarding({ step: 'open-wizard' }));

    tour.completed('open-wizard');

    await waitFor(() => expect(onAdvance).toHaveBeenCalledWith({ step: 'project-basics' }));
  });

  test('holds the closing screen open after the last step, rather than vanishing', async () => {
    const last = TOUR_STEPS.at(-1)!;
    const { onAdvance } = renderTour(withOnboarding({ step: last.id }));

    tour.completed(last.id);

    // 'finished' is not completion: the user still has to acknowledge the
    // closing screen, which is where the docs links live.
    await waitFor(() => expect(onAdvance).toHaveBeenCalledWith({ step: 'finished' }));
  });

  test('ignores a signal for a step that is not active', async () => {
    const { onAdvance } = renderTour(withOnboarding({ step: 'open-wizard' }));

    tour.completed('commit-workflow');

    await waitFor(() => expect(onAdvance).not.toHaveBeenCalled());
  });

  test('skipping records completion so it does not come back', async () => {
    const { onAdvance } = renderTour(withOnboarding({ step: 'open-wizard' }));

    await userEvent.click(screen.getByTestId('tour-callout-skip'));

    await waitFor(() => expect(onAdvance).toHaveBeenCalledWith({ completed: true }));
  });

  test('Escape ends the tour, so it never traps the user', async () => {
    const { onAdvance } = renderTour(withOnboarding({ step: 'open-wizard' }));

    await userEvent.keyboard('{Escape}');

    await waitFor(() => expect(onAdvance).toHaveBeenCalledWith({ completed: true }));
  });

  test('Escape aimed at an open dialog does not end the tour', async () => {
    // Several steps point at a control inside a dialog. Escape there means
    // "close this modal"; treating it as "end the tour" killed onboarding
    // permanently, and nothing ships a way to restart it.
    const dialog = document.createElement('div');
    dialog.setAttribute('role', 'dialog');
    dialog.dataset.state = 'open';
    document.body.appendChild(dialog);

    try {
      const { onAdvance } = renderTour(withOnboarding({ step: 'choose-workflow-type' }));

      await userEvent.keyboard('{Escape}');

      expect(onAdvance).not.toHaveBeenCalled();
    } finally {
      dialog.remove();
    }
  });

  test('offers a way to the target when it is not on this screen', () => {
    // No element carries the step's data-testid here, and the step's route
    // differs from the current one, so there is somewhere to send the user.
    render(
      <MemoryRouter initialEntries={['/project/testuser']}>
        <OnboardingTour
          onAdvance={vi.fn()}
          user="testuser"
          userDetails={withOnboarding({ step: 'project-basics' })}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('tour-callout-navigate')).toBeInTheDocument();
    expect(screen.getByText(/happens on another screen/i)).toBeInTheDocument();
  });

  test('does not offer a navigate button that goes nowhere', () => {
    // The step's route IS the current route. Rendering "Take me there" here
    // gives the user a button that does nothing when clicked.
    render(
      <MemoryRouter initialEntries={['/project/testuser/new']}>
        <OnboardingTour
          onAdvance={vi.fn()}
          user="testuser"
          userDetails={withOnboarding({ step: 'project-basics' })}
        />
      </MemoryRouter>,
    );

    expect(screen.queryByTestId('tour-callout-navigate')).not.toBeInTheDocument();
  });

  test('points at the project card when the user backs out to the dashboard', () => {
    // Real recovery case: pressing "Back to Projects" mid-tour previously left
    // the user with a callout naming a control that was nowhere on screen.
    tour.demoProjectName = 'Demo-Project-2';
    const card = document.createElement('div');
    card.dataset.testid = 'project-row-Demo-Project-2';
    document.body.appendChild(card);

    try {
      render(
        <MemoryRouter initialEntries={['/project/testuser']}>
          <OnboardingTour
            onAdvance={vi.fn()}
            user="testuser"
            userDetails={withOnboarding({ step: 'commit-workflow' })}
          />
        </MemoryRouter>,
      );

      expect(card).toHaveClass('am-tour-target');
      expect(screen.getByText(/Open Demo-Project-2 to carry on/i)).toBeInTheDocument();
    } finally {
      card.remove();
      tour.demoProjectName = null;
    }
  });

  test('highlights the target element without covering it', () => {
    const target = document.createElement('button');
    target.dataset.testid = 'new-project-button';
    document.body.appendChild(target);

    renderTour(withOnboarding({ step: 'open-wizard' }));

    // The ring is an outline on the real control, not an overlay over it, so
    // the click the step is asking for still reaches the button.
    expect(target).toHaveClass('am-tour-target');
    expect(screen.queryByTestId('tour-callout-navigate')).not.toBeInTheDocument();
  });

  test('advances off the first step when the wizard route is reached', async () => {
    // Opening the wizard has no product-code success branch to fire from; the
    // route is the only honest evidence the user got there.
    const onAdvance = vi.fn();
    render(
      <MemoryRouter initialEntries={['/project/testuser/new']}>
        <OnboardingTour
          onAdvance={onAdvance}
          user="testuser"
          userDetails={withOnboarding({ step: 'open-wizard' })}
        />
      </MemoryRouter>,
    );

    await waitFor(() => expect(onAdvance).toHaveBeenCalledWith({ step: 'project-basics' }));
  });

  test('shows the closing screen with docs links when finished', () => {
    renderTour(withOnboarding({ step: 'finished' }));

    expect(screen.getByTestId('onboarding-complete')).toBeInTheDocument();
    expect(screen.queryByTestId('tour-callout')).not.toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /quick start/i }),
    ).toHaveAttribute('href', 'https://actionsmanager.io/getting-started/quick-start.html');
  });

  test('closing the closing screen is what records completion', async () => {
    const { onAdvance } = renderTour(withOnboarding({ step: 'finished' }));

    await userEvent.click(screen.getByTestId('onboarding-complete-close'));

    await waitFor(() => expect(onAdvance).toHaveBeenCalledWith({ completed: true }));
  });

  test('publishes the active step so other screens can seed themselves', () => {
    const { unmount } = renderTour(withOnboarding({ step: 'project-basics' }));
    expect(tour.isActive()).toBe(true);
    expect(tour.activeStep).toBe('project-basics');

    unmount();

    // Must not leak: a stale active step would make NewProject seed demo
    // values for a user who is not on the tour at all.
    expect(tour.isActive()).toBe(false);
  });

  test('is not active when no tour is running', () => {
    renderTour(withOnboarding({ step: null }));
    expect(tour.isActive()).toBe(false);
  });

  test('highlights a target that only mounts after the step is active', async () => {
    // The usual case, not an edge one: resolve-pr activates while the
    // campaigns panel is still fetching, and add-workflow right as the wizard
    // navigates. Resolving the element once meant the ring never appeared —
    // which is the entire affordance of the step.
    renderTour(withOnboarding({ step: 'open-wizard' }));
    expect(screen.getByTestId('tour-callout-navigate')).toBeInTheDocument();

    const late = document.createElement('button');
    late.dataset.testid = 'new-project-button';
    document.body.appendChild(late);

    await waitFor(() => expect(late).toHaveClass('am-tour-target'));
  });

  test('releases the highlight when the tour ends', () => {
    const target = document.createElement('button');
    target.dataset.testid = 'new-project-button';
    document.body.appendChild(target);

    const { rerender } = renderTour(withOnboarding({ step: 'open-wizard' }));
    expect(target).toHaveClass('am-tour-target');

    rerender(
      <MemoryRouter>
        <OnboardingTour
          onAdvance={vi.fn()}
          user="testuser"
          userDetails={withOnboarding({ completed: true, step: 'open-wizard' })}
        />
      </MemoryRouter>,
    );

    expect(target).not.toHaveClass('am-tour-target');
  });
});
