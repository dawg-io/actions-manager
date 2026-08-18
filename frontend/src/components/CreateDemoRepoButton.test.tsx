import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import CreateDemoRepoButton, { DEMO_REPO_NAME, describeFailure } from './CreateDemoRepoButton';
import { createGitHubRepo } from '../api/repos';
import { toast } from '../utils/toast';

vi.mock('../api/repos', () => ({ createGitHubRepo: vi.fn() }));

const mockedCreate = vi.mocked(createGitHubRepo);

describe('CreateDemoRepoButton', () => {
  beforeEach(() => {
    mockedCreate.mockReset();
  });

  test('creates the demo repository with the chosen visibility', async () => {
    mockedCreate.mockResolvedValue({ repo_name: DEMO_REPO_NAME, owner: 'testuser' });
    const onCreated = vi.fn();
    render(<CreateDemoRepoButton user="testuser" visibility="public" onCreated={onCreated} />);

    await userEvent.click(screen.getByTestId('create-demo-repo-button'));

    await waitFor(() =>
      expect(mockedCreate).toHaveBeenCalledWith(
        'testuser',
        'public',
        undefined,
        expect.objectContaining({ name: DEMO_REPO_NAME }),
      ),
    );
  });

  test('reports the created repository as owner/name so the picker can select it', async () => {
    mockedCreate.mockResolvedValue({ repo_name: DEMO_REPO_NAME, owner: 'acme-corp' });
    const onCreated = vi.fn();
    render(<CreateDemoRepoButton user="testuser" visibility="private" onCreated={onCreated} />);

    await userEvent.click(screen.getByTestId('create-demo-repo-button'));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(`acme-corp/${DEMO_REPO_NAME}`));
  });

  test('surfaces a failure instead of pretending the repo exists', async () => {
    const errorToast = vi.spyOn(toast, 'error').mockImplementation(() => {});
    mockedCreate.mockResolvedValue({ error: 'name already exists on this account' });
    const onCreated = vi.fn();
    render(<CreateDemoRepoButton user="testuser" visibility="public" onCreated={onCreated} />);

    await userEvent.click(screen.getByTestId('create-demo-repo-button'));

    await waitFor(() =>
      expect(errorToast).toHaveBeenCalledWith(
        expect.stringMatching(/already have a actionsmanager-demo/i),
      ),
    );
    expect(onCreated).not.toHaveBeenCalled();
    errorToast.mockRestore();
  });

  test('re-enables the button after a failure, so it can be retried', async () => {
    vi.spyOn(toast, 'error').mockImplementation(() => {});
    mockedCreate.mockResolvedValue({ error: 'boom' });
    render(<CreateDemoRepoButton user="testuser" visibility="public" onCreated={vi.fn()} />);

    const button = screen.getByTestId('create-demo-repo-button');
    await userEvent.click(button);

    await waitFor(() => expect(button).not.toBeDisabled());
  });
});

describe('describeFailure', () => {
  test('names the existing repository instead of a generic failure', () => {
    // GitHub replies to a duplicate with a nested object, so a string check
    // falls through — and this is the likely case on a second tour run.
    const githubError = { errors: [{ message: 'name already exists on this account' }] };
    expect(describeFailure(githubError)).toMatch(/already have a actionsmanager-demo/i);
  });

  test('passes a plain string detail through', () => {
    expect(describeFailure('Repository name may only contain letters')).toBe(
      'Repository name may only contain letters',
    );
  });

  test('falls back to something actionable when there is no detail', () => {
    expect(describeFailure(undefined)).toMatch(/pick an existing repository/i);
  });
});
