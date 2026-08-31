import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import EnvVars from './EnvVars';
import { getEnvVarsCount } from '../api/envVars';

vi.mock('../api/envVars', () => ({
  handleDeleteEnvVars: vi.fn(),
  updateEnvVars: vi.fn(),
  getEnvVars: vi.fn(),
  syncEnvVar: vi.fn(),
  getEnvVarsCount: vi.fn().mockResolvedValue(0),
}));

vi.mock('../utils/copyUtils', () => ({
  CopyButton: ({ textToCopy, title }: { textToCopy: string; title?: string }) => (
    <button type="button" title={title}>Copy {textToCopy}</button>
  ),
  copyToClipboard: vi.fn(),
}));

vi.mock('./PrefixedInput', () => ({
  default: function PrefixedInput({
    prefix,
    value,
    onChange,
    placeholder,
    className,
    disabled,
  }: {
    prefix: string;
    value: string;
    onChange: React.ChangeEventHandler<HTMLInputElement>;
    placeholder?: string;
    className?: string;
    disabled?: boolean;
  }) {
    return (
      <input
        className={className}
        placeholder={`${prefix}${placeholder}`}
        value={`${prefix}${value}`}
        onChange={onChange}
        disabled={disabled}
        data-testid="prefixed-input"
      />
    );
  },
}));

const mockedGetEnvVarsCount = vi.mocked(getEnvVarsCount);

const mockProps = {
  user: 'testuser',
  projectName: 'test-project',
  selectedRepos: ['repo1', 'repo2'],
  envVars: [{ env_key: 'TEST_VAR', repo: 'repo1', value: 'test-value' }],
  setEnvVars: vi.fn(),
  manualEnvVars: [{ key: '', value: '' }],
  setManualEnvVars: vi.fn(),
  accountType: 'premium',
  onAddEnvVar: vi.fn(),
  projectCode: 'TEST',
};

const atLimitEnvVars = (count: number) =>
  Array.from({ length: count }, (_, i) => ({
    env_key: `AM_TEST_VAR${i + 1}`,
    repo: 'repo1',
    value: `value${i + 1}`,
  }));

describe('EnvVars Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetEnvVarsCount.mockResolvedValue(0);
  });

  test('renders without crashing', () => {
    render(<EnvVars {...mockProps} />);
    expect(screen.getByText('TEST_VAR')).toBeInTheDocument();
  });

  describe('Free Plan Limit Behavior', () => {
    test('should show input boxes when below limit', async () => {
      render(
        <EnvVars {...mockProps} accountType="free" envVars={atLimitEnvVars(1)} />
      );

      expect(await screen.findByText('0/2 used')).toBeInTheDocument();
      expect(screen.getByText(/Free/)).toBeInTheDocument();
      expect(
        screen.getByText(/You can create up to 2 environment variables per project/)
      ).toBeInTheDocument();

      expect(screen.getAllByTestId('prefixed-input').length).toBeGreaterThan(0);
    });

    test('disables the add form once the limit is reached', async () => {
      mockedGetEnvVarsCount.mockResolvedValue(2);

      render(
        <EnvVars {...mockProps} accountType="free" envVars={atLimitEnvVars(2)} />
      );

      await waitFor(() => {
        expect(screen.getByTestId('prefixed-input')).toBeDisabled();
      });
      expect(screen.getByText('Limited')).toBeInTheDocument();
    });

    test('should show limit reached message when at limit', async () => {
      mockedGetEnvVarsCount.mockResolvedValue(2);
      const onAddEnvVar = vi.fn();

      render(
        <EnvVars
          {...mockProps}
          accountType="free"
          envVars={atLimitEnvVars(2)}
          onAddEnvVar={onAddEnvVar}
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('prefixed-input')).toBeDisabled();
      });

      const focusAddForm = onAddEnvVar.mock.calls.at(-1)?.[0] as () => void;
      React.act(() => focusAddForm());

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Upgrade to Professional for up to 10 environment variables per project.'
      );
    });

    test('should update count when environment variables change', async () => {
      const { rerender } = render(
        <EnvVars {...mockProps} accountType="free" envVars={[]} />
      );
      expect(await screen.findByText('0/2 used')).toBeInTheDocument();

      mockedGetEnvVarsCount.mockClear();
      rerender(
        <EnvVars {...mockProps} accountType="free" envVars={atLimitEnvVars(2)} />
      );

      await waitFor(() => expect(mockedGetEnvVarsCount).toHaveBeenCalled());
    });
  });

  describe('Professional Plan Limit Behavior', () => {
    test('should show input boxes when below limit', async () => {
      render(
        <EnvVars
          {...mockProps}
          accountType="professional"
          envVars={atLimitEnvVars(1)}
        />
      );

      expect(await screen.findByText('0/10 used')).toBeInTheDocument();
      expect(screen.getByText(/Professional/)).toBeInTheDocument();
      expect(
        screen.getByText(/You can create up to 10 environment variables per project/)
      ).toBeInTheDocument();

      expect(screen.getAllByTestId('prefixed-input').length).toBeGreaterThan(0);
    });

    test('should show upgrade to Enterprise message when at limit', async () => {
      mockedGetEnvVarsCount.mockResolvedValue(10);
      const onAddEnvVar = vi.fn();

      render(
        <EnvVars
          {...mockProps}
          accountType="professional"
          envVars={atLimitEnvVars(10)}
          onAddEnvVar={onAddEnvVar}
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId('prefixed-input')).toBeDisabled();
      });

      const focusAddForm = onAddEnvVar.mock.calls.at(-1)?.[0] as () => void;
      React.act(() => focusAddForm());

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Upgrade to Enterprise for unlimited environment variables.'
      );
    });
  });
});
