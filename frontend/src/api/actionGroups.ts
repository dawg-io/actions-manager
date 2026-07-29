/**
 * Action Groups API client.
 *
 * User-created, shared, workspace-wide labels for organizing the Actions
 * Projects catalog. An action can belong to any number of groups.
 */

import config from '../config';

const API_BASE_URL = config.BACKEND_URL;

export interface ActionGroup {
  action_group_id: number;
  name: string;
  description: string | null;
  actions_project_ids: number[];
}

function jsonHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json' };
}

async function unwrap<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `${fallbackMessage}: ${response.status}`);
  }
  return response.json();
}

export async function listActionGroups(githubUser: string): Promise<ActionGroup[]> {
  const params = new URLSearchParams({ github_user: githubUser });
  const response = await fetch(`${API_BASE_URL}/api/action-groups/?${params}`, {
    method: 'GET',
    credentials: 'include',
  });
  return unwrap(response, 'List failed');
}

export async function createActionGroup(
  githubUser: string,
  name: string,
  description: string | null
): Promise<ActionGroup> {
  const response = await fetch(`${API_BASE_URL}/api/action-groups/`, {
    method: 'POST',
    credentials: 'include',
    headers: jsonHeaders(),
    body: JSON.stringify({ github_user: githubUser, name, description }),
  });
  return unwrap(response, 'Create failed');
}

export async function updateActionGroup(
  githubUser: string,
  id: number,
  name: string,
  description: string | null
): Promise<ActionGroup> {
  const response = await fetch(`${API_BASE_URL}/api/action-groups/${id}`, {
    method: 'PUT',
    credentials: 'include',
    headers: jsonHeaders(),
    body: JSON.stringify({ github_user: githubUser, name, description }),
  });
  return unwrap(response, 'Update failed');
}

export async function deleteActionGroup(githubUser: string, id: number): Promise<void> {
  const params = new URLSearchParams({ github_user: githubUser });
  const response = await fetch(`${API_BASE_URL}/api/action-groups/${id}?${params}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Delete failed: ${response.status}`);
  }
}

export async function addActionToGroup(
  githubUser: string,
  groupId: number,
  actionsProjectId: number
): Promise<ActionGroup> {
  const params = new URLSearchParams({ github_user: githubUser });
  const response = await fetch(
    `${API_BASE_URL}/api/action-groups/${groupId}/actions/${actionsProjectId}?${params}`,
    { method: 'POST', credentials: 'include' }
  );
  return unwrap(response, 'Add to group failed');
}

export async function removeActionFromGroup(
  githubUser: string,
  groupId: number,
  actionsProjectId: number
): Promise<ActionGroup> {
  const params = new URLSearchParams({ github_user: githubUser });
  const response = await fetch(
    `${API_BASE_URL}/api/action-groups/${groupId}/actions/${actionsProjectId}?${params}`,
    { method: 'DELETE', credentials: 'include' }
  );
  return unwrap(response, 'Remove from group failed');
}
