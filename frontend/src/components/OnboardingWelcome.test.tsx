import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import OnboardingWelcome, { shouldShowWelcome } from './OnboardingWelcome';
import type { UserDetails } from '../api/user';

const baseUser = (overrides: Partial<UserDetails> = {}): UserDetails => ({
  github_user: 'testuser',
  avatar_url: '',
  account_type: 'free',
  workspace_role: 'admin',
  onboarding: { completed: false, completed_at: null, step: null },
  ...overrides,
});

describe('shouldShowWelcome', () => {
  test('shows for a member who has never seen onboarding', () => {
    expect(shouldShowWelcome(baseUser({ workspace_role: 'member' }))).toBe(true);
  });

  test('never shows when the API does not report onboarding state', () => {
    // A missing field means the backend does not serve onboarding state, not
    // that onboarding is pending. Showing it here would put a dialog in front
    // of every user of a frontend running ahead of its backend, and the PUT
    // recording the dismissal would 404 — so it could never be closed for good.
    const { onboarding, ...withoutOnboarding } = baseUser();
    expect(shouldShowWelcome(withoutOnboarding as UserDetails)).toBe(false);
  });

  test('does not show once onboarding is completed', () => {
    const user = baseUser({
      onboarding: { completed: true, completed_at: '2026-08-16T00:00:00Z', step: null },
    });
    expect(shouldShowWelcome(user)).toBe(false);
  });

  test('does not show once a tour is under way', () => {
    // A recorded step means the welcome screen has already been answered.
    // Without this it would reopen on top of the running tour after a reload.
    const user = baseUser({
      onboarding: { completed: false, completed_at: null, step: 'open-wizard' },
    });
    expect(shouldShowWelcome(user)).toBe(false);
  });

  test('never shows for read_only members, who cannot dismiss it', () => {
    // WriteProtectionMiddleware rejects every /api/* write for read_only users,
    // so offering this to them would produce a dialog they can never close.
    const user = baseUser({ workspace_role: 'read_only' });
    expect(shouldShowWelcome(user)).toBe(false);
  });

  test('does not show before user details have loaded', () => {
    expect(shouldShowWelcome(undefined)).toBe(false);
  });
});

describe('OnboardingWelcome', () => {
  test('does not render when closed', () => {
    render(<OnboardingWelcome open={false} onDismiss={vi.fn()} onStartTour={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  test('renders the product introduction when open', () => {
    render(<OnboardingWelcome open onDismiss={vi.fn()} onStartTour={vi.fn()} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Welcome to ActionsManager')).toBeInTheDocument();
    expect(screen.getByText('Group repositories into projects')).toBeInTheDocument();
    expect(screen.getByText('Deliver changes as pull requests')).toBeInTheDocument();
    expect(screen.getByText('Catch drift before it spreads')).toBeInTheDocument();
  });

  test('links to the Quick Start docs in a new tab', () => {
    render(<OnboardingWelcome open onDismiss={vi.fn()} onStartTour={vi.fn()} />);

    const link = screen.getByRole('link', { name: /quick start/i });
    expect(link).toHaveAttribute('href', 'https://actionsmanager.io/getting-started/quick-start.html');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noreferrer');
  });

  test('dismisses when the primary button is clicked', async () => {
    const onDismiss = vi.fn().mockResolvedValue(undefined);
    render(<OnboardingWelcome open onDismiss={onDismiss} onStartTour={vi.fn()} />);

    await userEvent.click(screen.getByTestId('onboarding-welcome-dismiss'));

    await waitFor(() => expect(onDismiss).toHaveBeenCalledTimes(1));
  });

  test('dismisses on Escape, so it never traps the user', async () => {
    const onDismiss = vi.fn().mockResolvedValue(undefined);
    render(<OnboardingWelcome open onDismiss={onDismiss} onStartTour={vi.fn()} />);

    await userEvent.keyboard('{Escape}');

    await waitFor(() => expect(onDismiss).toHaveBeenCalledTimes(1));
  });

  test('starts the tour when the primary button is clicked', async () => {
    const onStartTour = vi.fn().mockResolvedValue(undefined);
    const onDismiss = vi.fn();
    render(<OnboardingWelcome open onDismiss={onDismiss} onStartTour={onStartTour} />);

    await userEvent.click(screen.getByTestId('onboarding-welcome-start-tour'));

    await waitFor(() => expect(onStartTour).toHaveBeenCalledTimes(1));
    expect(onDismiss).not.toHaveBeenCalled();
  });

  test('disables the dismiss button while the write is in flight', async () => {
    let release: () => void = () => {};
    const onDismiss = vi.fn().mockReturnValue(new Promise<void>((resolve) => { release = resolve; }));
    render(<OnboardingWelcome open onDismiss={onDismiss} onStartTour={vi.fn()} />);

    const button = screen.getByTestId('onboarding-welcome-dismiss');
    await userEvent.click(button);

    await waitFor(() => expect(button).toBeDisabled());

    release();
    await waitFor(() => expect(onDismiss).toHaveBeenCalledTimes(1));
  });
});
