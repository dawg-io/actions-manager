import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { WorkflowResourcesProvider, useWorkflowResources } from './WorkflowResourcesContext';
import { getEnvironments } from '../api/environments';

vi.mock('../api/environments', () => ({
  getEnvironments: jest.fn(),
}));

const mockedGetEnvironments = getEnvironments as unknown as ReturnType<typeof jest.fn>;

const Probe: React.FC = () => {
  const { resources, loadingEnvironments, environmentsError, requestEnvironments } =
    useWorkflowResources();
  return (
    <div>
      <button type="button" onClick={requestEnvironments}>
        open
      </button>
      <span data-testid="names">{resources.map((r) => `${r.kind}:${r.name}`).join(',')}</span>
      <span data-testid="loading">{String(loadingEnvironments)}</span>
      <span data-testid="error">{environmentsError ?? ''}</span>
    </div>
  );
};

const renderProvider = (repos: string[] = ['acme/web']) =>
  render(
    <WorkflowResourcesProvider
      user="tester"
      selectedRepos={repos}
      secrets={[{ secret_key: 'TOKEN', repo: 'acme/web' }]}
      envVars={[{ env_key: 'REGISTRY', repo: 'acme/web' }]}
    >
      <Probe />
    </WorkflowResourcesProvider>
  );

describe('WorkflowResourcesProvider', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedGetEnvironments.mockResolvedValue([{ name: 'production' }]);
  });

  test('exposes secrets and variables without fetching anything', () => {
    renderProvider();

    expect(screen.getByTestId('names')).toHaveTextContent('secret:TOKEN,variable:REGISTRY');
    expect(mockedGetEnvironments).not.toHaveBeenCalled();
  });

  test('fetches environments once a picker asks for them', async () => {
    renderProvider();

    await userEvent.click(screen.getByRole('button', { name: 'open' }));

    await waitFor(() => {
      expect(screen.getByTestId('names')).toHaveTextContent('environment:production');
    });
    expect(mockedGetEnvironments).toHaveBeenCalledWith('tester', 'acme/web');
    expect(screen.getByTestId('loading')).toHaveTextContent('false');
  });

  test('fetches once per repository and does not refetch on reopen', async () => {
    renderProvider(['acme/web', 'acme/api']);

    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(mockedGetEnvironments).toHaveBeenCalledTimes(2);

    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    expect(mockedGetEnvironments).toHaveBeenCalledTimes(2);
  });

  test('surfaces a fetch failure and clears the loading flag', async () => {
    mockedGetEnvironments.mockRejectedValue(new Error('GitHub request failed'));
    renderProvider();

    await userEvent.click(screen.getByRole('button', { name: 'open' }));

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('GitHub request failed');
    });
    expect(screen.getByTestId('loading')).toHaveTextContent('false');
  });

  // A repo change used to leave a stale "requested" flag set for one render,
  // firing a round of GitHub calls that were discarded - and because the
  // discard also skipped the cleanup, the loading flag stayed on forever.
  test('changing repositories drops cached environments without refetching or hanging', async () => {
    const { rerender } = renderProvider(['acme/web']);

    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    await waitFor(() => {
      expect(screen.getByTestId('names')).toHaveTextContent('environment:production');
    });
    expect(mockedGetEnvironments).toHaveBeenCalledTimes(1);

    rerender(
      <WorkflowResourcesProvider
        user="tester"
        selectedRepos={['acme/other']}
        secrets={[{ secret_key: 'TOKEN', repo: 'acme/other' }]}
        envVars={[]}
      >
        <Probe />
      </WorkflowResourcesProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('names')).not.toHaveTextContent('environment:production');
    });
    expect(mockedGetEnvironments).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('loading')).toHaveTextContent('false');
  });

  test('re-requesting after a repository change fetches the new repository', async () => {
    const { rerender } = renderProvider(['acme/web']);
    await userEvent.click(screen.getByRole('button', { name: 'open' }));
    await waitFor(() => expect(mockedGetEnvironments).toHaveBeenCalledTimes(1));

    rerender(
      <WorkflowResourcesProvider user="tester" selectedRepos={['acme/other']} secrets={[]} envVars={[]}>
        <Probe />
      </WorkflowResourcesProvider>
    );

    await userEvent.click(screen.getByRole('button', { name: 'open' }));

    await waitFor(() => {
      expect(mockedGetEnvironments).toHaveBeenCalledWith('tester', 'acme/other');
    });
  });

  test('does not fetch when there are no repositories', async () => {
    renderProvider([]);

    await userEvent.click(screen.getByRole('button', { name: 'open' }));

    expect(mockedGetEnvironments).not.toHaveBeenCalled();
    expect(screen.getByTestId('loading')).toHaveTextContent('false');
  });
});
