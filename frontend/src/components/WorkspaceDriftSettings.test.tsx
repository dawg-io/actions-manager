vi.mock('../api/driftSettings', async () => {
  const actual = await vi.importActual<typeof import('../api/driftSettings')>('../api/driftSettings');
  return {
    ...actual,
    fetchDriftSettings: vi.fn(),
    saveDriftSettings: vi.fn(),
  };
});

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import WorkspaceDriftSettings from './WorkspaceDriftSettings';
import { fetchDriftSettings, saveDriftSettings, DriftSettings } from '../api/driftSettings';

import type { MockedFunction } from 'vitest';
const mockFetch = fetchDriftSettings as MockedFunction<typeof fetchDriftSettings>;
const mockSave = saveDriftSettings as MockedFunction<typeof saveDriftSettings>;

const SETTINGS: DriftSettings = {
  sweep_enabled: true,
  recheck_interval_minutes: 30,
  batch_size: 5,
  poll_interval_seconds: 60,
};

describe('WorkspaceDriftSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockResolvedValue(SETTINGS);
    mockSave.mockResolvedValue({ success: true });
  });

  test('a non-admin sees a permission message and no settings are fetched', () => {
    render(<WorkspaceDriftSettings currentUserRole="read_only" />);

    expect(screen.getByText(/only workspace admins/i)).toBeInTheDocument();
    expect(screen.queryByTestId('drift-settings-form')).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  test('an unknown role shows a checking state rather than access denied', () => {
    // The role arrives asynchronously; flashing "denied" at a real admin on
    // every refresh reads as having lost the role.
    render(<WorkspaceDriftSettings />);

    expect(screen.getByText(/checking your access/i)).toBeInTheDocument();
    expect(screen.queryByText(/only workspace admins/i)).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  test('an admin sees the saved settings', async () => {
    render(<WorkspaceDriftSettings currentUserRole="admin" />);

    await waitFor(() => expect(screen.getByTestId('drift-settings-form')).toBeInTheDocument());
    expect(screen.getByLabelText(/default check schedule/i)).toHaveValue('30');
    expect(screen.getByLabelText(/projects checked per tick/i)).toHaveValue(5);
  });

  test('changing the schedule and saving sends the new value', async () => {
    render(<WorkspaceDriftSettings currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByTestId('drift-settings-form')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/default check schedule/i), { target: { value: '1440' } });
    fireEvent.click(screen.getByTestId('drift-settings-save'));

    await waitFor(() =>
      expect(mockSave).toHaveBeenCalledWith({ ...SETTINGS, recheck_interval_minutes: 1440 }),
    );
  });

  test('the kill switch is sent as false when unchecked', async () => {
    render(<WorkspaceDriftSettings currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByTestId('drift-settings-form')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('drift-sweep-enabled'));
    fireEvent.click(screen.getByTestId('drift-settings-save'));

    await waitFor(() => expect(mockSave).toHaveBeenCalledWith({ ...SETTINGS, sweep_enabled: false }));
  });

  test('a successful save confirms and re-reads', async () => {
    render(<WorkspaceDriftSettings currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByTestId('drift-settings-form')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('drift-settings-save'));

    await waitFor(() => expect(screen.getByText(/drift settings saved/i)).toBeInTheDocument());
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  test('a failed load refuses to show the form instead of showing defaults', async () => {
    // Showing defaults would let Save overwrite a stored 1440 with 15.
    mockFetch.mockRejectedValue(new Error('network'));
    render(<WorkspaceDriftSettings currentUserRole="admin" />);

    await waitFor(() => expect(screen.getByTestId('drift-settings-load-error')).toBeInTheDocument());
    expect(screen.queryByTestId('drift-settings-form')).not.toBeInTheDocument();
    expect(screen.queryByTestId('drift-settings-save')).not.toBeInTheDocument();
  });

  test('retrying after a failed load shows the real settings', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network'));
    render(<WorkspaceDriftSettings currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByTestId('drift-settings-load-error')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => expect(screen.getByTestId('drift-settings-form')).toBeInTheDocument());
    expect(screen.getByLabelText(/default check schedule/i)).toHaveValue('30');
  });

  test('clearing a number field does not submit zero', async () => {
    // Number("") === 0, which the backend rejects (batch_size >= 1).
    render(<WorkspaceDriftSettings currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByTestId('drift-settings-form')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/projects checked per tick/i), { target: { value: '' } });
    fireEvent.click(screen.getByTestId('drift-settings-save'));

    await waitFor(() => expect(mockSave).toHaveBeenCalledWith(SETTINGS));
  });

  test('a validation error renders its messages, not [object Object]', async () => {
    // FastAPI sends `detail` as an array for 422s.
    mockSave.mockResolvedValue({ success: false, message: 'Input should be greater than 0' });
    render(<WorkspaceDriftSettings currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByTestId('drift-settings-form')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('drift-settings-save'));

    await waitFor(() => expect(screen.getByText(/input should be greater than 0/i)).toBeInTheDocument());
    expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
  });

  test('a rejected save surfaces the reason and does not claim success', async () => {
    mockSave.mockResolvedValue({ success: false, message: 'batch_size must be 1-50' });
    render(<WorkspaceDriftSettings currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByTestId('drift-settings-form')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('drift-settings-save'));

    await waitFor(() => expect(screen.getByText(/batch_size must be 1-50/i)).toBeInTheDocument());
    expect(screen.queryByText(/drift settings saved/i)).not.toBeInTheDocument();
  });
});
