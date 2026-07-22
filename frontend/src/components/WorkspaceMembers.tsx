import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Avatar,
  AvatarImage,
  AvatarFallback,
} from './ui';
import {
  getWorkspaceMembers,
  updateMemberRole,
  WorkspaceMember,
} from '../api/workspaceMembers';

interface WorkspaceMembersProps {
  readonly currentUser: string;
  readonly currentUserRole?: string;
}

const ROLE_OPTIONS = [
  { value: 'read_only', label: 'Read Only' },
  { value: 'member', label: 'Member' },
  { value: 'admin', label: 'Admin' },
];

const ROLE_BADGE_STYLES: Record<string, string> = {
  admin: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  member: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
  read_only: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
};

const formatRole = (role: string): string => {
  switch (role) {
    case 'admin': return 'Admin';
    case 'member': return 'Member';
    case 'read_only': return 'Read Only';
    default: return role;
  }
};

const WorkspaceMembers: React.FC<WorkspaceMembersProps> = ({
  currentUser,
  currentUserRole,
}) => {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<number | null>(null);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const messageTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isAdmin = currentUserRole === 'admin';

  // Clear message timeout on unmount
  useEffect(() => {
    return () => {
      if (messageTimeoutRef.current) {
        clearTimeout(messageTimeoutRef.current);
      }
    };
  }, []);

  const loadMembers = useCallback(async () => {
    setLoading(true);
    const data = await getWorkspaceMembers();
    setMembers(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  const handleRoleChange = async (userId: number, newRole: string) => {
    setUpdating(userId);
    setMessage(null);

    const result = await updateMemberRole(userId, newRole);

    if (result.success) {
      setMessage({ text: result.message || 'Role updated', type: 'success' });
      await loadMembers();
    } else {
      setMessage({ text: result.message || 'Failed to update role', type: 'error' });
    }

    setUpdating(null);

    // Clear any existing message timeout before setting a new one
    if (messageTimeoutRef.current) {
      clearTimeout(messageTimeoutRef.current);
    }
    messageTimeoutRef.current = setTimeout(() => setMessage(null), 4000);
  };

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
            👥 Workspace Members
          </h2>
          <p className="text-sm text-text-secondary dark:text-secondary-dark mt-1">
            {members.length} member{members.length !== 1 ? 's' : ''}
          </p>
        </div>
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

      {/* Members list */}
      <div className="space-y-2">
        {members.map((member) => (
          <div
            key={member.user_id}
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

              <div className="flex flex-col">
                <span className="text-sm font-medium text-text-primary dark:text-text-primary-dark">
                  {member.github_user}
                  {member.github_user === currentUser && (
                    <span className="ml-2 text-xs text-text-secondary dark:text-secondary-dark">(you)</span>
                  )}
                </span>
              </div>
            </div>

            {/* Right: role badge or role selector */}
            <div className="flex items-center gap-2">
              {isAdmin ? (
                <select
                  value={member.workspace_role}
                  onChange={(e) => handleRoleChange(member.user_id, e.target.value)}
                  disabled={updating === member.user_id}
                  className="text-sm rounded-md border border-border dark:border-border-dark bg-container dark:bg-container-dark text-text-primary dark:text-text-primary-dark px-2 py-1 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
                  aria-label={`Change role for ${member.github_user}`}
                >
                  {ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              ) : (
                <span
                  className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                    ROLE_BADGE_STYLES[member.workspace_role] || ROLE_BADGE_STYLES.read_only
                  }`}
                >
                  {formatRole(member.workspace_role)}
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

      {/* Permission info for non-admins */}
      {!isAdmin && (
        <p className="mt-6 text-xs text-text-secondary dark:text-secondary-dark text-center">
          Only workspace admins can change member roles.
        </p>
      )}
    </div>
  );
};

export default WorkspaceMembers;
