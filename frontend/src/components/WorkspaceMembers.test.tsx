vi.mock('../api/workspaceMembers', () => ({
  getWorkspaceMembers: jest.fn(),
  updateMemberRole: jest.fn(),
}));

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import WorkspaceMembers from './WorkspaceMembers';
import { getWorkspaceMembers, updateMemberRole } from '../api/workspaceMembers';

const mockGetMembers = getWorkspaceMembers as jest.MockedFunction<typeof getWorkspaceMembers>;
const mockUpdateRole = updateMemberRole as jest.MockedFunction<typeof updateMemberRole>;

const MEMBERS = [
  { user_id: 1, github_user: 'admin-user', avatar_url: 'https://example.com/a.jpg', workspace_role: 'admin' },
  { user_id: 2, github_user: 'reader-user', avatar_url: null, workspace_role: 'read_only' },
];

describe('WorkspaceMembers Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetMembers.mockResolvedValue(MEMBERS);
  });

  test('renders loading state initially', () => {
    // Never resolve to keep loading
    mockGetMembers.mockReturnValue(new Promise(() => {}));
    render(<WorkspaceMembers currentUser="admin-user" currentUserRole="admin" />);
    expect(screen.getByText(/loading members/i)).toBeInTheDocument();
  });

  test('renders member list after loading', async () => {
    render(<WorkspaceMembers currentUser="admin-user" currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByText('admin-user')).toBeInTheDocument());
    expect(screen.getByText('reader-user')).toBeInTheDocument();
    expect(screen.getByText(/2 members/i)).toBeInTheDocument();
  });

  test('admin sees role dropdowns for each member', async () => {
    render(<WorkspaceMembers currentUser="admin-user" currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByText('admin-user')).toBeInTheDocument());

    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBe(2);
    expect(screen.queryByRole('option', { name: 'Co-Admin' })).not.toBeInTheDocument();
  });

  test('non-admin sees role badges instead of dropdowns', async () => {
    render(<WorkspaceMembers currentUser="reader-user" currentUserRole="read_only" />);
    await waitFor(() => expect(screen.getByText('admin-user')).toBeInTheDocument());

    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('Read Only')).toBeInTheDocument();
  });

  test('shows (you) indicator for current user', async () => {
    render(<WorkspaceMembers currentUser="admin-user" currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByText('admin-user')).toBeInTheDocument());
    expect(screen.getByText('(you)')).toBeInTheDocument();
  });

  test('shows info message for non-admins', async () => {
    render(<WorkspaceMembers currentUser="reader-user" currentUserRole="read_only" />);
    await waitFor(() => expect(screen.getByText('admin-user')).toBeInTheDocument());
    expect(screen.getByText(/only workspace admins/i)).toBeInTheDocument();
  });

  test('handles successful role update', async () => {
    mockUpdateRole.mockResolvedValue({ success: true, message: 'Role updated to admin' });
    // After update, return updated members
    const updatedMembers = [
      MEMBERS[0],
      { ...MEMBERS[1], workspace_role: 'admin' },
    ];

    render(<WorkspaceMembers currentUser="admin-user" currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByText('admin-user')).toBeInTheDocument());

    // Change the role of the second member
    const selects = screen.getAllByRole('combobox');
    mockGetMembers.mockResolvedValue(updatedMembers);
    fireEvent.change(selects[1], { target: { value: 'admin' } });

    await waitFor(() => expect(mockUpdateRole).toHaveBeenCalledWith(2, 'admin'));
    await waitFor(() => expect(screen.getByText(/role updated/i)).toBeInTheDocument());
  });

  test('handles failed role update', async () => {
    mockUpdateRole.mockResolvedValue({ success: false, message: 'Cannot remove last admin' });

    render(<WorkspaceMembers currentUser="admin-user" currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByText('admin-user')).toBeInTheDocument());

    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'read_only' } });

    await waitFor(() => expect(screen.getByText(/cannot remove last admin/i)).toBeInTheDocument());
  });

  test('displays empty state with zero members', async () => {
    mockGetMembers.mockResolvedValue([]);
    render(<WorkspaceMembers currentUser="admin-user" currentUserRole="admin" />);
    await waitFor(() => expect(screen.getByText(/0 members/i)).toBeInTheDocument());
  });
});
