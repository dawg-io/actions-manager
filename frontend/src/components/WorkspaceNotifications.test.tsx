vi.mock('../api/notifications', async () => {
  const actual = await vi.importActual<typeof import('../api/notifications')>('../api/notifications');
  return {
    ...actual,
    sendTestEmail: jest.fn(),
    fetchSubscriptions: jest.fn(),
    createSubscription: jest.fn(),
    deleteSubscription: jest.fn(),
    fetchDeliveries: jest.fn(),
  };
});
vi.mock('../api/projects', () => ({
  fetchProjects: jest.fn(),
}));

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import WorkspaceNotifications from './WorkspaceNotifications';
import {
  sendTestEmail,
  fetchSubscriptions,
  createSubscription,
  deleteSubscription,
  fetchDeliveries,
} from '../api/notifications';
import { fetchProjects } from '../api/projects';

const mockSendTestEmail = sendTestEmail as jest.MockedFunction<typeof sendTestEmail>;
const mockFetchSubscriptions = fetchSubscriptions as jest.MockedFunction<typeof fetchSubscriptions>;
const mockCreateSubscription = createSubscription as jest.MockedFunction<typeof createSubscription>;
const mockDeleteSubscription = deleteSubscription as jest.MockedFunction<typeof deleteSubscription>;
const mockFetchDeliveries = fetchDeliveries as jest.MockedFunction<typeof fetchDeliveries>;
const mockFetchProjects = fetchProjects as jest.MockedFunction<typeof fetchProjects>;

describe('WorkspaceNotifications Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchSubscriptions.mockResolvedValue([]);
    mockFetchDeliveries.mockResolvedValue([]);
    mockFetchProjects.mockResolvedValue([]);
  });

  test('non-admin sees a permission message instead of the form', () => {
    render(<WorkspaceNotifications currentUserRole="read_only" />);
    expect(screen.getByText(/only workspace admins/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send test email/i })).not.toBeInTheDocument();
    expect(mockFetchSubscriptions).not.toHaveBeenCalled();
  });

  test('admin sees the recipient input and send button', () => {
    render(<WorkspaceNotifications currentUserRole="admin" />);
    expect(screen.getAllByPlaceholderText(/recipient@example.com/i)[0]).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send test email/i })).toBeInTheDocument();
  });

  test('send button is disabled until a recipient is entered', () => {
    render(<WorkspaceNotifications currentUserRole="admin" />);
    expect(screen.getByRole('button', { name: /send test email/i })).toBeDisabled();

    fireEvent.change(screen.getAllByPlaceholderText(/recipient@example.com/i)[0], {
      target: { value: 'a@example.com' },
    });
    expect(screen.getByRole('button', { name: /send test email/i })).not.toBeDisabled();
  });

  test('shows success message after a successful send', async () => {
    mockSendTestEmail.mockResolvedValue({ success: true, message: 'Test email sent to a@example.com' });
    render(<WorkspaceNotifications currentUserRole="admin" />);

    fireEvent.change(screen.getAllByPlaceholderText(/recipient@example.com/i)[0], {
      target: { value: 'a@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send test email/i }));

    await waitFor(() => expect(screen.getByText('Test email sent to a@example.com')).toBeInTheDocument());
    expect(mockSendTestEmail).toHaveBeenCalledWith('a@example.com');
  });

  test('shows the specific error message after a failed send', async () => {
    mockSendTestEmail.mockResolvedValue({ success: false, message: 'SMTP authentication failed: bad credentials' });
    render(<WorkspaceNotifications currentUserRole="admin" />);

    fireEvent.change(screen.getAllByPlaceholderText(/recipient@example.com/i)[0], {
      target: { value: 'a@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send test email/i }));

    await waitFor(() => expect(screen.getByText(/SMTP authentication failed/i)).toBeInTheDocument());
  });

  test('loads and displays existing subscriptions', async () => {
    mockFetchSubscriptions.mockResolvedValue([
      { subscription_id: 1, recipient_email: 'team@example.com', project_id: null, project_name: null, event_types: ['drift.detected'], notify_on_resolved: true },
    ]);

    render(<WorkspaceNotifications currentUserRole="admin" />);

    await waitFor(() => expect(screen.getByText(/team@example.com/)).toBeInTheDocument());
    expect(screen.getByRole('listitem').textContent).toMatch(/all projects/);
  });

  test('creates a subscription and refreshes the list', async () => {
    mockCreateSubscription.mockResolvedValue({ success: true });
    render(<WorkspaceNotifications currentUserRole="admin" />);
    await waitFor(() => expect(mockFetchSubscriptions).toHaveBeenCalledTimes(1));

    const recipientInputs = screen.getAllByPlaceholderText(/recipient@example.com/i);
    fireEvent.change(recipientInputs[1], { target: { value: 'new@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: /add subscription/i }));

    await waitFor(() => expect(mockCreateSubscription).toHaveBeenCalledWith(
      expect.objectContaining({ recipientEmail: 'new@example.com', projectId: null, eventTypes: null })
    ));
    await waitFor(() => expect(mockFetchSubscriptions).toHaveBeenCalledTimes(2));
  });

  test('removes a subscription', async () => {
    mockFetchSubscriptions.mockResolvedValue([
      { subscription_id: 7, recipient_email: 'gone@example.com', project_id: null, project_name: null, event_types: null, notify_on_resolved: true },
    ]);
    mockDeleteSubscription.mockResolvedValue({ success: true });

    render(<WorkspaceNotifications currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByText(/gone@example.com/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /remove/i }));

    await waitFor(() => expect(mockDeleteSubscription).toHaveBeenCalledWith(7));
  });

  test('delivery history is on its own tab, hidden until selected', async () => {
    mockFetchDeliveries.mockResolvedValue([
      {
        delivery_id: 1,
        event_type: 'drift.detected',
        project_id: 5,
        project_name: 'acme-project',
        recipient_email: 'oncall@example.com',
        status: 'failed',
        attempt_count: 5,
        last_error: 'SMTP authentication failed',
        created_at: '2026-01-01T00:00:00Z',
        sent_at: null,
      },
    ]);

    render(<WorkspaceNotifications currentUserRole="admin" />);
    await waitFor(() => expect(mockFetchDeliveries).toHaveBeenCalled());

    expect(screen.queryByText('acme-project')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /delivery history/i }));

    expect(screen.getByText('acme-project')).toBeInTheDocument();
    expect(screen.getByText('SMTP authentication failed')).toBeInTheDocument();
  });

  test('switching to the history tab hides the settings form', async () => {
    render(<WorkspaceNotifications currentUserRole="admin" />);
    expect(screen.getByRole('button', { name: /send test email/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /delivery history/i }));

    expect(screen.queryByRole('button', { name: /send test email/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^settings$/i }));

    expect(screen.getByRole('button', { name: /send test email/i })).toBeInTheDocument();
  });
});
