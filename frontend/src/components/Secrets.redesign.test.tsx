import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import Secrets from './Secrets';
import { createSecrets } from '../api/secrets';

vi.mock('../api/secrets', () => ({
  deleteSecrets: vi.fn().mockResolvedValue(undefined),
  createSecrets: vi.fn().mockResolvedValue(undefined),
  getSecretsCount: vi.fn().mockResolvedValue(0),
}));

vi.mock('../utils/copyUtils', () => ({
  CopyButton: ({ textToCopy, title }: { textToCopy: string; title: string }) => (
    <button title={title}>Copy {textToCopy}</button>
  ),
  copyToClipboard: vi.fn(),
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
  secrets: [],
  setSecrets: vi.fn(),
  manualSecrets: [{ secret_key: '', secret_value: '' }],
  setManualSecrets: vi.fn(),
  accountType: 'enterprise',
  onAddSecret: vi.fn(),
  projectCode: 'TEST',
  usePrefix: true,
};

describe('Secrets redesigned UI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders polished header with title and write-only description', () => {
    render(<Secrets {...baseProps} />);
    expect(
      screen.getByRole('heading', { name: /Environment Secrets/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Manage encrypted GitHub environment secrets\. Values are write-only once saved\./i,
      ),
    ).toBeInTheDocument();
  });

  test('shows empty state when no secrets exist', () => {
    render(<Secrets {...baseProps} />);
    expect(screen.getByText(/No secrets yet/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Add your first GitHub Actions secret for this project/i),
    ).toBeInTheDocument();
  });

  test('Add Secret button is disabled until both fields are valid', () => {
    const setManualSecrets = vi.fn();
    const { rerender } = render(
      <Secrets
        {...baseProps}
        manualSecrets={[{ secret_key: '', secret_value: '' }]}
        setManualSecrets={setManualSecrets}
      />,
    );
    expect(screen.getByTestId('secrets-add-submit')).toBeDisabled();

    rerender(
      <Secrets
        {...baseProps}
        manualSecrets={[{ secret_key: 'DB_PASSWORD', secret_value: '' }]}
        setManualSecrets={setManualSecrets}
      />,
    );
    expect(screen.getByTestId('secrets-add-submit')).toBeDisabled();

    rerender(
      <Secrets
        {...baseProps}
        manualSecrets={[{ secret_key: 'DB_PASSWORD', secret_value: 's3cret' }]}
        setManualSecrets={setManualSecrets}
      />,
    );
    expect(screen.getByTestId('secrets-add-submit')).not.toBeDisabled();
  });

  test('saved secrets always render masked values, never the secret_value', () => {
    render(
      <Secrets
        {...baseProps}
        secrets={[
          {
            secret_key: 'DEV_DB_PASSWORD',
            secret_value: 'super-leaky-value',
            repo: 'repo1',
          },
        ]}
      />,
    );
    const card = screen.getByTestId('secret-card-DEV_DB_PASSWORD');
    // The actual secret value must never appear in the rendered card.
    expect(within(card).queryByText('super-leaky-value')).not.toBeInTheDocument();
    // The masked placeholder must be present.
    expect(within(card).getByLabelText(/Masked secret value/i)).toBeInTheDocument();
  });

  test('saved secrets show Secret + Synced + Write-only badges, never Draft', () => {
    render(
      <Secrets
        {...baseProps}
        secrets={[{ secret_key: 'PROD_API_TOKEN', secret_value: 'x', repo: 'repo1' }]}
      />,
    );
    const card = screen.getByTestId('secret-card-PROD_API_TOKEN');
    expect(within(card).getByText('Secret')).toBeInTheDocument();
    expect(within(card).getByText(/Synced/)).toBeInTheDocument();
    expect(within(card).getByText(/Write-only/)).toBeInTheDocument();
    expect(within(card).queryByText(/Draft/)).not.toBeInTheDocument();
    expect(within(card).queryByText(/Under Review/)).not.toBeInTheDocument();
    expect(within(card).queryByText(/Committed Locally/)).not.toBeInTheDocument();
  });

  test('secret value input is password-style by default and toggleable', () => {
    const setManualSecrets = vi.fn();
    render(
      <Secrets
        {...baseProps}
        manualSecrets={[{ secret_key: 'A', secret_value: 'hello' }]}
        setManualSecrets={setManualSecrets}
      />,
    );
    const valueInput = screen.getByTestId('secrets-add-value') as HTMLInputElement;
    expect(valueInput.type).toBe('password');

    fireEvent.click(screen.getByTestId('secrets-toggle-reveal'));
    expect(
      (screen.getByTestId('secrets-add-value') as HTMLInputElement).type,
    ).toBe('text');
  });

  test('clears typed secret value after a successful save', async () => {
    const setManualSecrets = vi.fn();
    render(
      <Secrets
        {...baseProps}
        manualSecrets={[{ secret_key: 'API_TOKEN', secret_value: 'topsecret' }]}
        setManualSecrets={setManualSecrets}
      />,
    );

    fireEvent.click(screen.getByTestId('secrets-add-submit'));

    await waitFor(() => {
      // Component should clear the draft after save by setting it to an empty pair.
      expect(setManualSecrets).toHaveBeenCalledWith([
        { secret_key: '', secret_value: '' },
      ]);
    });
  });

  test('surfaces backend error without leaking the secret value', async () => {
    vi.mocked(createSecrets).mockRejectedValueOnce(new Error('GitHub rejected the request'));

    const setManualSecrets = vi.fn();
    render(
      <Secrets
        {...baseProps}
        manualSecrets={[{ secret_key: 'A', secret_value: 'super-leaky-value' }]}
        setManualSecrets={setManualSecrets}
      />,
    );

    fireEvent.click(screen.getByTestId('secrets-add-submit'));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Failed to save secret/i);
    expect(alert).not.toHaveTextContent('super-leaky-value');
  });
});
