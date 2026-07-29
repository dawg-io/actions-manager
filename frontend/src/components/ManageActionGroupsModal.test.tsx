import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import ManageActionGroupsModal from './ManageActionGroupsModal';
import {
  createActionGroup,
  updateActionGroup,
  deleteActionGroup,
  addActionToGroup,
  removeActionFromGroup,
  ActionGroup,
} from '../api/actionGroups';
import type { ActionsProject } from '../api/actionsProjects';

vi.mock('../api/actionGroups', () => ({
  createActionGroup: jest.fn(),
  updateActionGroup: jest.fn(),
  deleteActionGroup: jest.fn(),
  addActionToGroup: jest.fn(),
  removeActionFromGroup: jest.fn(),
}));

vi.mock('../utils/toast', () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() },
}));

// Minimal Dialog shim — renders children directly, same pattern as LinkedWorkflowsModal.test.tsx
vi.mock('./ui/dialog', () => ({
  Dialog: ({ open, children }: any) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: any) => <div>{children}</div>,
  DialogHeader: ({ children }: any) => <div>{children}</div>,
  DialogTitle: ({ children }: any) => <h2>{children}</h2>,
  DialogDescription: ({ children }: any) => <p>{children}</p>,
  DialogFooter: ({ children }: any) => <div>{children}</div>,
}));

vi.mock('./ui/button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
  ),
}));

const checkout: ActionsProject = {
  actions_project_id: 1,
  name: 'Checkout',
  description: null,
  source_url: 'https://github.com/actions/checkout',
  owner: 'actions',
  repo: 'checkout',
  ref: 'main',
  yaml_path: 'action.yml',
  inputs: [],
  branding_icon: null,
  branding_color: null,
};

const deploymentGroup: ActionGroup = {
  action_group_id: 10,
  name: 'Deployment',
  description: null,
  actions_project_ids: [],
};

const defaultProps = {
  isOpen: true,
  user: 'test-user',
  projects: [checkout],
  actionGroups: [] as ActionGroup[],
  onGroupsChange: jest.fn(),
  onClose: jest.fn(),
};

describe('ManageActionGroupsModal', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('creates a group and reports it to the parent', async () => {
    (createActionGroup as jest.Mock).mockResolvedValue(deploymentGroup);
    const onGroupsChange = jest.fn();

    render(<ManageActionGroupsModal {...defaultProps} onGroupsChange={onGroupsChange} />);

    await user.type(screen.getByTestId('new-action-group-name'), 'Deployment');
    await user.click(screen.getByTestId('create-action-group-button'));

    await waitFor(() => expect(createActionGroup).toHaveBeenCalledWith('test-user', 'Deployment', null));
    expect(onGroupsChange).toHaveBeenCalledWith([deploymentGroup]);
  });

  it('renames a group inline', async () => {
    (updateActionGroup as jest.Mock).mockResolvedValue({ ...deploymentGroup, name: 'Deploy' });
    const onGroupsChange = jest.fn();

    render(<ManageActionGroupsModal {...defaultProps} actionGroups={[deploymentGroup]} onGroupsChange={onGroupsChange} />);

    await user.click(screen.getByLabelText('Rename Deployment'));
    const input = screen.getByDisplayValue('Deployment');
    await user.clear(input);
    await user.type(input, 'Deploy{Enter}');

    await waitFor(() =>
      expect(updateActionGroup).toHaveBeenCalledWith('test-user', 10, 'Deploy', null)
    );
    expect(onGroupsChange).toHaveBeenCalledWith([{ ...deploymentGroup, name: 'Deploy' }]);
  });

  it('deletes a group after confirmation', async () => {
    (deleteActionGroup as jest.Mock).mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onGroupsChange = jest.fn();

    render(<ManageActionGroupsModal {...defaultProps} actionGroups={[deploymentGroup]} onGroupsChange={onGroupsChange} />);

    await user.click(screen.getByLabelText('Delete Deployment'));

    await waitFor(() => expect(deleteActionGroup).toHaveBeenCalledWith('test-user', 10));
    expect(onGroupsChange).toHaveBeenCalledWith([]);
    confirmSpy.mockRestore();
  });

  it('does not delete when the confirmation is dismissed', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(<ManageActionGroupsModal {...defaultProps} actionGroups={[deploymentGroup]} />);

    await user.click(screen.getByLabelText('Delete Deployment'));

    expect(deleteActionGroup).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('toggles an action into and out of the selected group', async () => {
    const updatedWithMember = { ...deploymentGroup, actions_project_ids: [1] };
    (addActionToGroup as jest.Mock).mockResolvedValue(updatedWithMember);
    (removeActionFromGroup as jest.Mock).mockResolvedValue(deploymentGroup);
    const onGroupsChange = jest.fn();

    const { rerender } = render(
      <ManageActionGroupsModal {...defaultProps} actionGroups={[deploymentGroup]} onGroupsChange={onGroupsChange} />
    );

    await user.click(screen.getByTestId('action-group-item-10'));
    const checkbox = screen.getByRole('checkbox', { name: 'Checkout' });
    expect(checkbox).not.toBeChecked();

    await user.click(checkbox);
    await waitFor(() => expect(addActionToGroup).toHaveBeenCalledWith('test-user', 10, 1));
    expect(onGroupsChange).toHaveBeenCalledWith([updatedWithMember]);

    // Re-render with the updated group (as the parent would after onGroupsChange) to exercise removal.
    rerender(
      <ManageActionGroupsModal {...defaultProps} actionGroups={[updatedWithMember]} onGroupsChange={onGroupsChange} />
    );
    await user.click(screen.getByTestId('action-group-item-10'));
    await user.click(screen.getByRole('checkbox', { name: 'Checkout' }));
    await waitFor(() => expect(removeActionFromGroup).toHaveBeenCalledWith('test-user', 10, 1));
  });
});
