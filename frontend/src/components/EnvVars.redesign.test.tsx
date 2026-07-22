import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import EnvVars from './EnvVars';
import { updateEnvVars } from '../api/envVars';

vi.mock('../api/envVars', () => ({
  handleDeleteEnvVars: vi.fn().mockResolvedValue(undefined),
  updateEnvVars: vi.fn().mockResolvedValue(undefined),
  getEnvVars: vi.fn().mockResolvedValue([]),
  syncEnvVar: vi.fn().mockResolvedValue(undefined),
  getEnvVarsCount: vi.fn().mockResolvedValue(0),
}));

vi.mock('../utils/copyUtils', () => ({
  CopyButton: ({ textToCopy, title }: { textToCopy: string; title: string }) => (
    <button title={title}>Copy {textToCopy}</button>
  ),
  copyToClipboard: jest.fn(),
}));

vi.mock('./PrefixedInput', () => ({
  default: function PrefixedInput({
    prefix,
    value,
    onChange,
    placeholder,
    id,
    disabled,
  }: any) {
    return (
      <input
        id={id}
        placeholder={`${prefix}${placeholder}`}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange && onChange(e.target.value)}
        data-testid="prefixed-input"
      />
    );
  },
}));

const baseProps = {
  user: 'testuser',
  projectName: 'test-project',
  selectedRepos: ['repo1'],
  envVars: [],
  setEnvVars: jest.fn(),
  manualEnvVars: [{ key: '', value: '' }],
  setManualEnvVars: jest.fn(),
  accountType: 'enterprise',
  onAddEnvVar: jest.fn(),
  projectCode: 'TEST',
  usePrefix: true,
};

describe('EnvVars redesigned UI', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('renders polished header with title and description', () => {
    render(<EnvVars {...baseProps} />);
    expect(
      screen.getByRole('heading', { name: /Environment Variables/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Manage non-sensitive configuration values for workflows and environments/i,
      ),
    ).toBeInTheDocument();
  });

  test('shows empty state when no variables exist', () => {
    render(<EnvVars {...baseProps} />);
    expect(screen.getByText(/No variables yet/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Add your first environment variable for this project/i),
    ).toBeInTheDocument();
  });

  test('Add Variable button is disabled until both fields are valid', () => {
    const setManualEnvVars = jest.fn();
    const { rerender } = render(
      <EnvVars
        {...baseProps}
        manualEnvVars={[{ key: '', value: '' }]}
        setManualEnvVars={setManualEnvVars}
      />,
    );
    expect(screen.getByTestId('envvars-add-submit')).toBeDisabled();

    // Provide key only
    rerender(
      <EnvVars
        {...baseProps}
        manualEnvVars={[{ key: 'API_URL', value: '' }]}
        setManualEnvVars={setManualEnvVars}
      />,
    );
    expect(screen.getByTestId('envvars-add-submit')).toBeDisabled();

    // Provide both
    rerender(
      <EnvVars
        {...baseProps}
        manualEnvVars={[{ key: 'API_URL', value: 'https://x' }]}
        setManualEnvVars={setManualEnvVars}
      />,
    );
    expect(screen.getByTestId('envvars-add-submit')).not.toBeDisabled();
  });

  test('does not render Draft / Under Review / Committed Locally badges on saved variables', () => {
    render(
      <EnvVars
        {...baseProps}
        envVars={[{ env_key: 'DEV_API_URL', repo: 'repo1', value: 'https://dev' }]}
      />,
    );
    const card = screen.getByTestId('envvar-card-DEV_API_URL');
    expect(within(card).getByText('Variable')).toBeInTheDocument();
    expect(within(card).getByText(/Synced/)).toBeInTheDocument();
    expect(within(card).queryByText(/Draft/)).not.toBeInTheDocument();
    expect(within(card).queryByText(/Under Review/)).not.toBeInTheDocument();
    expect(within(card).queryByText(/Committed Locally/)).not.toBeInTheDocument();
  });

  test('renders saved variable values (non-sensitive)', () => {
    render(
      <EnvVars
        {...baseProps}
        envVars={[{ env_key: 'LOG_LEVEL', repo: 'repo1', value: 'info' }]}
      />,
    );
    expect(screen.getByText('LOG_LEVEL')).toBeInTheDocument();
    expect(screen.getByText('info')).toBeInTheDocument();
  });

  test('surfaces backend error when saving fails', async () => {
    vi.mocked(updateEnvVars).mockRejectedValueOnce(new Error('boom'));

    const setManualEnvVars = jest.fn();
    render(
      <EnvVars
        {...baseProps}
        manualEnvVars={[{ key: 'API_URL', value: 'v' }]}
        setManualEnvVars={setManualEnvVars}
      />,
    );

    fireEvent.click(screen.getByTestId('envvars-add-submit'));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/Failed to save/i),
    );
  });
});
