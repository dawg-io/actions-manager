import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProjectMembers from './ProjectMembers';
import * as projectMembershipsApi from '../api/projectMemberships';
import * as workspaceMembersApi from '../api/workspaceMembers';

import type { Mock } from 'vitest';

vi.mock('../api/projectMemberships', () => ({
  getProjectMembers: vi.fn(),
  addProjectMember: vi.fn(),
  updateProjectMemberRole: vi.fn(),
  removeProjectMember: vi.fn(),
}));

vi.mock('../api/workspaceMembers', () => ({
  getWorkspaceMembers: vi.fn(),
}));

/**
 * A grant means different things per workspace role, and the picker has to
 * offer both of them:
 *
 *   member    — already sees every project; a grant gives edit rights here
 *   read_only — sees nothing without a grant; a grant gives sight of it
 *
 * The picker previously filtered to `workspace_role === 'read_only'`, so a
 * member could never be promoted to project_editor at all, even though the
 * backend accepts it.
 */
describe('ProjectMembers — who can be granted a project role', () => {
  const WORKSPACE = [
    { user_id: 1, github_user: 'example-admin', workspace_role: 'admin' },
    { user_id: 2, github_user: 'example-user', workspace_role: 'member' },
    { user_id: 3, github_user: 'example-readonly', workspace_role: 'read_only' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    (projectMembershipsApi.getProjectMembers as Mock).mockResolvedValue({
      success: true, data: [],
    });
    (workspaceMembersApi.getWorkspaceMembers as Mock).mockResolvedValue(WORKSPACE);
  });

  /** Render, wait for the workspace load, and open the Add Member form. */
  const openAddForm = async () => {
    render(
      <ProjectMembers projectId={1} projectName="rwx123" workspaceRole="admin" />
    );
    await waitFor(() => {
      expect(workspaceMembersApi.getWorkspaceMembers).toHaveBeenCalled();
    });
    fireEvent.click(await screen.findByRole('button', { name: /add member/i }));
  };

  it('offers a member, so they can be promoted to editor', async () => {
    await openAddForm();

    const options = await screen.findAllByRole('option');
    const labels = options.map((o) => o.textContent);
    expect(labels.some((l) => l?.includes('example-user'))).toBe(true);
  });

  it('still offers a read-only user', async () => {
    await openAddForm();

    const options = await screen.findAllByRole('option');
    const labels = options.map((o) => o.textContent);
    expect(labels.some((l) => l?.includes('example-readonly'))).toBe(true);
  });

  it('does not offer an admin, who already has full access everywhere', async () => {
    await openAddForm();

    const options = await screen.findAllByRole('option');
    const labels = options.map((o) => o.textContent);
    expect(labels.some((l) => l?.includes('example-admin'))).toBe(false);
  });

  it('offers Editor as an assignable role', async () => {
    await openAddForm();

    const options = await screen.findAllByRole('option');
    const labels = options.map((o) => o.textContent);
    expect(labels).toContain('Editor');
  });
});
