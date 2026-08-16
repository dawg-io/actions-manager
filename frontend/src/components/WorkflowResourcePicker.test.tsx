import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import WorkflowResourcePicker from './WorkflowResourcePicker';
import { WorkflowResourcesRawProvider } from './WorkflowResourcesContext';
import { toResources, WorkflowResource } from '../utils/workflowResources';

const RESOURCES: WorkflowResource[] = [
  { kind: 'secret', name: 'DOCKER_PASSWORD', repo: 'acme/web' },
  { kind: 'secret', name: 'NPM_TOKEN', repo: 'acme/web' },
  { kind: 'variable', name: 'DOCKER_REGISTRY', repo: 'acme/web' },
  { kind: 'environment', name: 'production', repo: 'acme/web' },
];

const renderPicker = (
  overrides: Partial<{
    resources: WorkflowResource[];
    loadingEnvironments: boolean;
    environmentsError: string | null;
    requestEnvironments: () => void;
  }> = {},
  onInsert: (text: string) => void = vi.fn()
) => {
  const value = {
    resources: RESOURCES,
    loadingEnvironments: false,
    environmentsError: null,
    requestEnvironments: vi.fn(),
    ...overrides,
  };

  render(
    <WorkflowResourcesRawProvider value={value}>
      <WorkflowResourcePicker onInsert={onInsert} />
    </WorkflowResourcesRawProvider>
  );

  return { value, onInsert };
};

const openPicker = async () => {
  await userEvent.click(screen.getByTestId('resource-picker-trigger'));
  await screen.findByTestId('resource-picker');
};

describe('WorkflowResourcePicker', () => {
  test('is closed until the trigger is clicked, then lists available resources', async () => {
    renderPicker();

    expect(screen.queryByTestId('resource-picker')).not.toBeInTheDocument();

    await openPicker();

    expect(screen.getByTestId('resource-item-DOCKER_PASSWORD')).toBeInTheDocument();
    expect(screen.getByTestId('resource-item-NPM_TOKEN')).toBeInTheDocument();
    expect(screen.getByTestId('resource-item-DOCKER_REGISTRY')).toBeInTheDocument();
    expect(screen.getByTestId('resource-item-production')).toBeInTheDocument();
  });

  test('identifies secrets, variables and environments as separate groups', async () => {
    renderPicker();
    await openPicker();

    const secrets = screen.getByTestId('resource-group-secrets');
    const variables = screen.getByTestId('resource-group-variables');
    const environments = screen.getByTestId('resource-group-environments');

    expect(secrets).toHaveTextContent('Secrets (2)');
    expect(variables).toHaveTextContent('Variables (1)');
    expect(environments).toHaveTextContent('Environments (1)');

    // A secret must not be listed as a variable, and vice versa.
    expect(secrets).toContainElement(screen.getByTestId('resource-item-DOCKER_PASSWORD'));
    expect(variables).toContainElement(screen.getByTestId('resource-item-DOCKER_REGISTRY'));
    expect(secrets).not.toContainElement(screen.getByTestId('resource-item-DOCKER_REGISTRY'));
  });

  test('shows the repository each resource belongs to as its scope', async () => {
    renderPicker();
    await openPicker();

    expect(screen.getByTestId('resource-item-DOCKER_PASSWORD')).toHaveTextContent('acme/web');
  });

  test('collapses a resource synced across repositories into one row listing both', async () => {
    renderPicker({
      resources: [
        { kind: 'secret', name: 'SHARED_TOKEN', repo: 'acme/web' },
        { kind: 'secret', name: 'SHARED_TOKEN', repo: 'acme/api' },
      ],
    });
    await openPicker();

    expect(screen.getAllByTestId('resource-item-SHARED_TOKEN')).toHaveLength(1);
    expect(screen.getByTestId('resource-item-SHARED_TOKEN')).toHaveTextContent('acme/web, acme/api');
  });

  describe('inserting the correct expression', () => {
    test('a secret inserts a secrets expression', async () => {
      const onInsert = vi.fn();
      renderPicker({}, onInsert);
      await openPicker();

      await userEvent.click(screen.getByTestId('resource-item-DOCKER_PASSWORD'));

      expect(onInsert).toHaveBeenCalledWith('${{ secrets.DOCKER_PASSWORD }}');
    });

    test('a variable inserts a vars expression, not a secrets one', async () => {
      const onInsert = vi.fn();
      renderPicker({}, onInsert);
      await openPicker();

      await userEvent.click(screen.getByTestId('resource-item-DOCKER_REGISTRY'));

      expect(onInsert).toHaveBeenCalledWith('${{ vars.DOCKER_REGISTRY }}');
    });

    test('an environment inserts the environment job key', async () => {
      const onInsert = vi.fn();
      renderPicker({}, onInsert);
      await openPicker();

      await userEvent.click(screen.getByTestId('resource-item-production'));

      expect(onInsert).toHaveBeenCalledWith('environment: production');
    });

    test('prefix-mode names are inserted exactly as stored in GitHub', async () => {
      const onInsert = vi.fn();
      renderPicker({ resources: [{ kind: 'secret', name: 'AM_REG1_DOCKER_PASSWORD', repo: 'acme/web' }] }, onInsert);
      await openPicker();

      await userEvent.click(screen.getByTestId('resource-item-AM_REG1_DOCKER_PASSWORD'));

      expect(onInsert).toHaveBeenCalledWith('${{ secrets.AM_REG1_DOCKER_PASSWORD }}');
    });

    test('closes after a selection', async () => {
      renderPicker();
      await openPicker();

      await userEvent.click(screen.getByTestId('resource-item-NPM_TOKEN'));

      await waitFor(() => {
        expect(screen.queryByTestId('resource-picker')).not.toBeInTheDocument();
      });
    });
  });

  test('searching filters the list across groups', async () => {
    renderPicker();
    await openPicker();

    await userEvent.type(screen.getByTestId('resource-picker-search'), 'docker');

    expect(screen.getByTestId('resource-item-DOCKER_PASSWORD')).toBeInTheDocument();
    expect(screen.getByTestId('resource-item-DOCKER_REGISTRY')).toBeInTheDocument();
    expect(screen.queryByTestId('resource-item-NPM_TOKEN')).not.toBeInTheDocument();
    expect(screen.queryByTestId('resource-item-production')).not.toBeInTheDocument();
  });

  test('reports when nothing matches the search, without claiming the project is empty', async () => {
    renderPicker();
    await openPicker();

    await userEvent.type(screen.getByTestId('resource-picker-search'), 'nope');

    expect(screen.getByTestId('resource-picker-no-match')).toHaveTextContent('No resources match "nope"');
    expect(screen.queryByTestId('resource-picker-empty')).not.toBeInTheDocument();
  });

  test('shows an empty state pointing at Repository Configs when nothing is configured', async () => {
    renderPicker({ resources: [] });
    await openPicker();

    expect(screen.getByTestId('resource-picker-empty')).toHaveTextContent('No secrets or variables yet');
    expect(screen.getByTestId('resource-picker-empty')).toHaveTextContent('Repository Configs');
    expect(screen.queryByTestId('resource-picker-no-match')).not.toBeInTheDocument();
  });

  test('surfaces an environment load failure without hiding secrets and variables', async () => {
    renderPicker({ environmentsError: 'GitHub request failed' });
    await openPicker();

    const error = screen.getByTestId('resource-picker-error');
    expect(error).toHaveTextContent('GitHub request failed');
    expect(error).toHaveAttribute('role', 'alert');
    // Secrets are already in memory, so an environments failure must not blank the list.
    expect(screen.getByTestId('resource-item-DOCKER_PASSWORD')).toBeInTheDocument();
  });

  test('shows a loading note while environments are being fetched', async () => {
    renderPicker({ loadingEnvironments: true });
    await openPicker();

    expect(screen.getByTestId('resource-picker-loading')).toBeInTheDocument();
  });

  test('does not show the empty state while environments are still loading', async () => {
    renderPicker({ resources: [], loadingEnvironments: true });
    await openPicker();

    expect(screen.queryByTestId('resource-picker-empty')).not.toBeInTheDocument();
  });

  test('requests environments only once the picker is opened', async () => {
    const requestEnvironments = vi.fn();
    renderPicker({ requestEnvironments });

    expect(requestEnvironments).not.toHaveBeenCalled();

    await openPicker();

    expect(requestEnvironments).toHaveBeenCalled();
  });

  test('never renders a secret or variable value', async () => {
    // Built through the real mapper, from rows that still carry values.
    const resources = toResources({
      secrets: [{ secret_key: 'DOCKER_PASSWORD', repo: 'acme/web', secret_value: 'super-secret-value' } as any],
      envVars: [{ env_key: 'DOCKER_REGISTRY', repo: 'acme/web', value: 'ghcr.io/acme' } as any],
    });

    renderPicker({ resources });
    await openPicker();

    const dialog = screen.getByTestId('resource-picker');
    expect(dialog).toHaveTextContent('DOCKER_PASSWORD');
    expect(dialog).toHaveTextContent('DOCKER_REGISTRY');
    expect(dialog.textContent).not.toContain('super-secret-value');
    expect(dialog.textContent).not.toContain('ghcr.io/acme');
    expect(document.body.innerHTML).not.toContain('super-secret-value');
    expect(document.body.innerHTML).not.toContain('ghcr.io/acme');
  });

  describe('field variant', () => {
    const renderField = (
      available: WorkflowResource[] = RESOURCES,
      onInsert: (text: string) => void = vi.fn()
    ) => {
      render(
        <WorkflowResourcesRawProvider
          value={{
            resources: available,
            loadingEnvironments: false,
            environmentsError: null,
            requestEnvironments: vi.fn(),
          }}
        >
          <WorkflowResourcePicker onInsert={onInsert} variant="field" />
        </WorkflowResourcesRawProvider>
      );
      return onInsert;
    };

    // `environment: NAME` is a job key; pasted into a run script or a `with:`
    // value it is just invalid text.
    test('omits deployment environments, which are not valid inside a field', async () => {
      renderField();
      await openPicker();

      expect(screen.getByTestId('resource-item-DOCKER_PASSWORD')).toBeInTheDocument();
      expect(screen.getByTestId('resource-item-DOCKER_REGISTRY')).toBeInTheDocument();
      expect(screen.queryByTestId('resource-item-production')).not.toBeInTheDocument();
      expect(screen.queryByTestId('resource-group-environments')).not.toBeInTheDocument();
    });

    test('shows the empty state when only environments exist', async () => {
      renderField([{ kind: 'environment', name: 'production', repo: 'acme/web' }]);
      await openPicker();

      expect(screen.getByTestId('resource-picker-empty')).toBeInTheDocument();
    });

    test('still inserts secrets and variables normally', async () => {
      const onInsert = renderField();
      await openPicker();

      await userEvent.click(screen.getByTestId('resource-item-DOCKER_REGISTRY'));

      expect(onInsert).toHaveBeenCalledWith('${{ vars.DOCKER_REGISTRY }}');
    });

    test('the toolbar variant keeps offering environments', async () => {
      renderPicker();
      await openPicker();

      expect(screen.getByTestId('resource-item-production')).toBeInTheDocument();
    });
  });

  test('can be disabled', async () => {
    render(
      <WorkflowResourcesRawProvider
        value={{
          resources: RESOURCES,
          loadingEnvironments: false,
          environmentsError: null,
          requestEnvironments: vi.fn(),
        }}
      >
        <WorkflowResourcePicker onInsert={vi.fn()} disabled />
      </WorkflowResourcesRawProvider>
    );

    const trigger = screen.getByTestId('resource-picker-trigger');
    expect(trigger).toBeDisabled();

    await userEvent.click(trigger);
    expect(screen.queryByTestId('resource-picker')).not.toBeInTheDocument();
  });
});
