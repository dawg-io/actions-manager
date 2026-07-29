import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { ActionsProject } from '../api/actionsProjects';
import {
  ActionGroup,
  createActionGroup,
  updateActionGroup,
  deleteActionGroup,
  addActionToGroup,
  removeActionFromGroup,
} from '../api/actionGroups';
import { toast } from '../utils/toast';

interface ManageActionGroupsModalProps {
  isOpen: boolean;
  user: string;
  projects: ActionsProject[];
  actionGroups: ActionGroup[];
  onGroupsChange: (groups: ActionGroup[]) => void;
  onClose: () => void;
}

const ManageActionGroupsModal: React.FC<ManageActionGroupsModalProps> = ({
  isOpen,
  user,
  projects,
  actionGroups,
  onGroupsChange,
  onClose,
}) => {
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  const [newGroupName, setNewGroupName] = useState<string>('');
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState<string>('');
  const [busy, setBusy] = useState<boolean>(false);

  const selectedGroup = actionGroups.find((g) => g.action_group_id === selectedGroupId) ?? null;

  const replaceGroup = (updated: ActionGroup) => {
    onGroupsChange(actionGroups.map((g) => (g.action_group_id === updated.action_group_id ? updated : g)));
  };

  const handleCreate = async () => {
    const name = newGroupName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const created = await createActionGroup(user, name, null);
      onGroupsChange([...actionGroups, created]);
      setNewGroupName('');
      setSelectedGroupId(created.action_group_id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create group');
    } finally {
      setBusy(false);
    }
  };

  const startRename = (group: ActionGroup) => {
    setRenamingId(group.action_group_id);
    setRenameValue(group.name);
  };

  const handleRenameSubmit = async (group: ActionGroup) => {
    const name = renameValue.trim();
    setRenamingId(null);
    if (!name || name === group.name) return;
    setBusy(true);
    try {
      const updated = await updateActionGroup(user, group.action_group_id, name, group.description);
      replaceGroup(updated);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to rename group');
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (group: ActionGroup) => {
    if (!window.confirm(`Delete the "${group.name}" group? This won't delete any actions.`)) return;
    setBusy(true);
    try {
      await deleteActionGroup(user, group.action_group_id);
      onGroupsChange(actionGroups.filter((g) => g.action_group_id !== group.action_group_id));
      if (selectedGroupId === group.action_group_id) setSelectedGroupId(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete group');
    } finally {
      setBusy(false);
    }
  };

  const handleToggleMembership = async (project: ActionsProject) => {
    if (!selectedGroup) return;
    const isMember = selectedGroup.actions_project_ids.includes(project.actions_project_id);
    setBusy(true);
    try {
      const updated = isMember
        ? await removeActionFromGroup(user, selectedGroup.action_group_id, project.actions_project_id)
        : await addActionToGroup(user, selectedGroup.action_group_id, project.actions_project_id);
      replaceGroup(updated);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update group membership');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto" data-testid="manage-action-groups-modal">
        <DialogHeader>
          <DialogTitle>Manage Action Groups</DialogTitle>
          <DialogDescription>
            Groups are shared with everyone in this workspace. An action can belong to any number of groups.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[220px_1fr]">
          <div className="space-y-2">
            <div className="flex gap-2">
              <Input
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                placeholder="New group name"
                data-testid="new-action-group-name"
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                disabled={busy}
              />
              <Button size="sm" onClick={handleCreate} disabled={busy || !newGroupName.trim()} data-testid="create-action-group-button">
                Add
              </Button>
            </div>

            <ul className="space-y-1">
              {actionGroups.map((group) => (
                <li key={group.action_group_id}>
                  {renamingId === group.action_group_id ? (
                    <Input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onBlur={() => handleRenameSubmit(group)}
                      onKeyDown={(e) => e.key === 'Enter' && handleRenameSubmit(group)}
                      className="h-8"
                    />
                  ) : (
                    <div
                      className={`flex items-center justify-between gap-1 rounded-md px-2 py-1.5 text-sm ${
                        selectedGroupId === group.action_group_id
                          ? 'bg-primary/10 text-primary dark:bg-primary-dark/10 dark:text-primary-dark'
                          : 'hover:bg-slate-100 dark:hover:bg-slate-800'
                      }`}
                    >
                      <button
                        type="button"
                        className="min-w-0 flex-1 truncate text-left"
                        onClick={() => setSelectedGroupId(group.action_group_id)}
                        data-testid={`action-group-item-${group.action_group_id}`}
                      >
                        {group.name}{' '}
                        <span className="text-xs text-slate-400">({group.actions_project_ids.length})</span>
                      </button>
                      <span className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          className="text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                          onClick={() => startRename(group)}
                          aria-label={`Rename ${group.name}`}
                        >
                          ✏️
                        </button>
                        <button
                          type="button"
                          className="text-xs text-slate-500 hover:text-red-600"
                          onClick={() => handleDelete(group)}
                          aria-label={`Delete ${group.name}`}
                        >
                          🗑️
                        </button>
                      </span>
                    </div>
                  )}
                </li>
              ))}
              {actionGroups.length === 0 && (
                <li className="text-xs text-slate-500 dark:text-slate-400">No groups yet.</li>
              )}
            </ul>
          </div>

          <div>
            {!selectedGroup && (
              <p className="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
                Select or create a group to manage its actions.
              </p>
            )}
            {selectedGroup && (
              <div className="space-y-1">
                {projects.map((project) => {
                  const isMember = selectedGroup.actions_project_ids.includes(project.actions_project_id);
                  return (
                    <label
                      key={project.actions_project_id}
                      className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-200 p-2 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
                    >
                      <input
                        type="checkbox"
                        checked={isMember}
                        disabled={busy}
                        onChange={() => handleToggleMembership(project)}
                        className="h-4 w-4 rounded border-slate-300 accent-blue-600"
                      />
                      <span className="text-sm text-slate-900 dark:text-slate-100">{project.name}</span>
                    </label>
                  );
                })}
                {projects.length === 0 && (
                  <p className="text-sm text-slate-500 dark:text-slate-400">No actions in the catalog yet.</p>
                )}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ManageActionGroupsModal;
