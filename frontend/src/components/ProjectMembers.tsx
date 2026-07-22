import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Avatar,
  AvatarImage,
  AvatarFallback,
} from './ui';
import {
  getProjectMembers,
  addProjectMember,
  updateProjectMemberRole,
  removeProjectMember,
  ProjectMember,
} from '../api/projectMemberships';
import {
  getWorkspaceMembers,
  WorkspaceMember,
} from '../api/workspaceMembers';
import ConfirmDialog from './ConfirmDialog';

interface ProjectMembersProps {
  readonly projectId: number | undefined;
  readonly projectName: string;
  readonly workspaceRole?: string;
}

const PROJECT_ROLE_OPTIONS = [
  { value: 'project_viewer', label: 'Viewer' },
  { value: 'project_editor', label: 'Editor' },
];

const PROJECT_ROLE_BADGE_STYLES: Record<string, string> = {
  project_editor: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  project_viewer: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

const formatProjectRole = (role: string): string => {
  switch (role) {
    case 'project_editor': return 'Editor';
    case 'project_viewer': return 'Viewer';
    default: return role;
  }
};

const ProjectMembers: React.FC<ProjectMembersProps> = ({
  projectId,
  projectName,
  workspaceRole,
}) => {
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [allWorkspaceMembers, setAllWorkspaceMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [notAuthorized, setNotAuthorized] = useState(false);
  const [updating, setUpdating] = useState<number | null>(null);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [selectedRole, setSelectedRole] = useState('project_viewer');
  const [adding, setAdding] = useState(false);
  const messageTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [pendingRemove, setPendingRemove] = useState<{ userId: number; username: string } | null>(null);

  const isAdmin = workspaceRole === 'admin';

  useEffect(() => {
    return () => {
      if (messageTimeoutRef.current) {
        clearTimeout(messageTimeoutRef.current);
      }
    };
  }, []);

  const showMessage = (text: string, type: 'success' | 'error') => {
    setMessage({ text, type });
    if (messageTimeoutRef.current) {
      clearTimeout(messageTimeoutRef.current);
    }
    messageTimeoutRef.current = setTimeout(() => setMessage(null), 4000);
  };

  const loadMembers = useCallback(async () => {
    if (!projectId) return;
    if (!isAdmin) {
      // Non-admin users cannot list project members — skip the API call
      setLoading(false);
      setNotAuthorized(true);
      return;
    }
    setLoading(true);
    const result = await getProjectMembers(projectId);
    if (!result.success && result.status === 403) {
      setNotAuthorized(true);
      setMembers([]);
    } else {
      setMembers(result.data);
    }
    setLoading(false);
  }, [projectId, isAdmin]);

  const loadWorkspaceMembers = useCallback(async () => {
    const data = await getWorkspaceMembers();
    setAllWorkspaceMembers(data);
  }, []);

  useEffect(() => {
    loadMembers();
    if (isAdmin) {
      loadWorkspaceMembers();
    }
  }, [loadMembers, loadWorkspaceMembers, isAdmin]);

  // Filter workspace members to only show read_only users not already assigned
  const availableUsers = allWorkspaceMembers.filter(
    (wm) =>
      wm.workspace_role === 'read_only' &&
      !members.some((pm) => pm.user_id === wm.user_id)
  );

  const handleAddMember = async () => {
    if (!projectId || !selectedUserId) return;
    setAdding(true);
    const result = await addProjectMember(projectId, selectedUserId, selectedRole);
    if (result.success) {
      showMessage('Member added to project', 'success');
      setShowAddForm(false);
      setSelectedUserId(null);
      setSelectedRole('project_viewer');
      await loadMembers();
    } else {
      showMessage(result.message || 'Failed to add member', 'error');
    }
    setAdding(false);
  };

  const handleRoleChange = async (userId: number, newRole: string) => {
    if (!projectId) return;
    setUpdating(userId);
    const result = await updateProjectMemberRole(projectId, userId, newRole);
    if (result.success) {
      showMessage('Project role updated', 'success');
      await loadMembers();
    } else {
      showMessage(result.message || 'Failed to update role', 'error');
    }
    setUpdating(null);
  };

  const handleRemoveMember = (userId: number, username: string) => {
    if (!projectId) return;
    setPendingRemove({ userId, username });
  };

  const doRemoveMember = async (userId: number) => {
    if (!projectId) return;
    setPendingRemove(null);
    setUpdating(userId);
    const result = await removeProjectMember(projectId, userId);
    if (result.success) {
      showMessage('Member removed from project', 'success');
      await loadMembers();
    } else {
      showMessage(result.message || 'Failed to remove member', 'error');
    }
    setUpdating(null);
  };

  if (!projectId) {
    return (
      <div className="flex items-center justify-center p-8">
        <span className="text-text-secondary dark:text-secondary-dark">
          Save the project first to manage members.
        </span>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <span className="text-text-secondary dark:text-secondary-dark">Loading members…</span>
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-text-primary dark:text-text-primary-dark">
            👥 Project Members
          </h2>
          <p className="text-sm text-text-secondary dark:text-secondary-dark mt-1">
            Manage who can access &quot;{projectName}&quot;
          </p>
        </div>
        {isAdmin && availableUsers.length > 0 && (
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="text-sm px-3 py-1.5 rounded-md bg-primary text-white hover:bg-primary/90 dark:bg-primary-dark dark:hover:bg-primary-dark/90 transition-colors"
          >
            {showAddForm ? 'Cancel' : '➕ Add Member'}
          </button>
        )}
      </div>

      {/* Status message */}
      {message && (
        <div
          className={`mb-4 px-4 py-2 rounded-lg text-sm font-medium ${
            message.type === 'success'
              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
              : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
          }`}
        >
          {message.type === 'success' ? '✅' : '❌'} {message.text}
        </div>
      )}

      {/* Add member form */}
      {showAddForm && isAdmin && (
        <div className="mb-4 p-4 rounded-lg border border-border dark:border-border-dark bg-container dark:bg-container-dark">
          <div className="flex flex-col sm:flex-row gap-3 items-end">
            <div className="flex-1">
              <label
                htmlFor="add-member-user"
                className="block text-sm font-medium text-text-primary dark:text-text-primary-dark mb-1"
              >
                User
              </label>
              <select
                id="add-member-user"
                value={selectedUserId ?? ''}
                onChange={(e) => setSelectedUserId(e.target.value ? Number(e.target.value) : null)}
                className="w-full text-sm rounded-md border border-border dark:border-border-dark bg-container dark:bg-container-dark text-text-primary dark:text-text-primary-dark px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">Select a user…</option>
                {availableUsers.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.github_user}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="add-member-role"
                className="block text-sm font-medium text-text-primary dark:text-text-primary-dark mb-1"
              >
                Role
              </label>
              <select
                id="add-member-role"
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value)}
                className="text-sm rounded-md border border-border dark:border-border-dark bg-container dark:bg-container-dark text-text-primary dark:text-text-primary-dark px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {PROJECT_ROLE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={handleAddMember}
              disabled={!selectedUserId || adding}
              className="text-sm px-4 py-1.5 rounded-md bg-primary text-white hover:bg-primary/90 dark:bg-primary-dark dark:hover:bg-primary-dark/90 disabled:opacity-50 transition-colors"
            >
              {adding ? 'Adding…' : 'Add'}
            </button>
          </div>
          {availableUsers.length === 0 && (
            <p className="mt-2 text-xs text-text-secondary dark:text-secondary-dark">
              No unassigned read-only workspace members available. All read-only users are already assigned to this project, or there are no read-only users in the workspace.
            </p>
          )}
        </div>
      )}

      {/* Info banner */}
      <div className="mb-4 px-4 py-2 rounded-lg text-sm bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300">
        ℹ️ Admin workspace role has automatic full access to all projects. Member and read-only users need explicit project assignments.
      </div>

      {/* Members list */}
      {notAuthorized ? (
        <div className="text-center py-8 text-text-secondary dark:text-secondary-dark">
          <p>You don&apos;t have permission to view project members.</p>
          <p className="mt-2 text-sm">
            Only workspace admins can view and manage project memberships.
          </p>
        </div>
      ) : members.length === 0 ? (
        <div className="text-center py-8 text-text-secondary dark:text-secondary-dark">
          <p>No members assigned to this project yet.</p>
          {isAdmin && (
            <p className="mt-2 text-sm">
              Use the &quot;Add Member&quot; button to grant read-only users access to this project.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {members.map((member) => (
            <div
              key={member.id}
              className="flex items-center justify-between px-4 py-3 rounded-lg border border-border dark:border-border-dark bg-container dark:bg-container-dark"
            >
              {/* Left: avatar + name */}
              <div className="flex items-center gap-3">
                <Avatar className="h-9 w-9">
                  <AvatarImage
                    src={member.avatar_url || undefined}
                    alt={`${member.github_user}'s avatar`}
                  />
                  <AvatarFallback className="text-sm font-medium">
                    {member.github_user.charAt(0).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <span className="text-sm font-medium text-text-primary dark:text-text-primary-dark">
                  {member.github_user}
                </span>
              </div>

              {/* Right: role selector + remove button */}
              <div className="flex items-center gap-2">
                {isAdmin ? (
                  <>
                    <select
                      value={member.project_role}
                      onChange={(e) => handleRoleChange(member.user_id, e.target.value)}
                      disabled={updating === member.user_id}
                      className="text-sm rounded-md border border-border dark:border-border-dark bg-container dark:bg-container-dark text-text-primary dark:text-text-primary-dark px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                      aria-label={`Change project role for ${member.github_user}`}
                    >
                      {PROJECT_ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleRemoveMember(member.user_id, member.github_user)}
                      disabled={updating === member.user_id}
                      className="text-sm px-2 py-1 rounded-md text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
                      aria-label={`Remove ${member.github_user} from project`}
                      title="Remove from project"
                    >
                      ✕
                    </button>
                  </>
                ) : (
                  <span
                    className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                      PROJECT_ROLE_BADGE_STYLES[member.project_role] || PROJECT_ROLE_BADGE_STYLES.project_viewer
                    }`}
                  >
                    {formatProjectRole(member.project_role)}
                  </span>
                )}
                {updating === member.user_id && (
                  <span className="text-xs text-text-secondary dark:text-secondary-dark">
                    Saving…
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Permission info for non-admins */}
      {!isAdmin && (
        <p className="mt-6 text-xs text-text-secondary dark:text-secondary-dark text-center">
          Only workspace admins can manage project members.
        </p>
      )}

      {pendingRemove && (
        <ConfirmDialog
          open={true}
          title={`Remove ${pendingRemove.username}?`}
          description={`This will remove ${pendingRemove.username} from this project. They will lose access to this project's workflows and settings.`}
          confirmLabel="Remove member"
          destructive
          onConfirm={() => { void doRemoveMember(pendingRemove.userId); }}
          onCancel={() => setPendingRemove(null)}
        />
      )}
    </div>
  );
};

export default ProjectMembers;
