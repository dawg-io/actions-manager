/**
 * Actions Projects API client (issue #1687).
 *
 * Custom GitHub Actions imported from a repo's actions.yaml — preview,
 * create, list, get, update, delete.
 */

import config from '../config';

const API_BASE_URL = config.BACKEND_URL;

export interface ActionInput {
  name: string;
  description: string | null;
  required: boolean;
  default: string | null;
  type: 'string' | 'number' | 'boolean' | 'choice';
  options: string[] | null;
}

export interface PreviewResponse {
  name: string;
  description: string | null;
  owner: string;
  repo: string;
  ref: string;
  yaml_path: string;
  source_url: string;
  inputs: ActionInput[];
  branding_icon: string | null;
  branding_color: string | null;
}

export interface ActionsProject {
  actions_project_id: number;
  name: string;
  description: string | null;
  source_url: string;
  owner: string;
  repo: string;
  ref: string;
  yaml_path: string;
  inputs: ActionInput[];
  branding_icon: string | null;
  branding_color: string | null;
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

export async function previewActionsProject(githubUser: string, url: string): Promise<PreviewResponse> {
  const params = new URLSearchParams({ github_user: githubUser, url });
  const response = await fetch(`${API_BASE_URL}/api/actions-projects/preview?${params}`, {
    method: 'GET',
    credentials: 'include',
  });
  return unwrap(response, 'Preview failed');
}

export async function createActionsProject(
  githubUser: string,
  preview: PreviewResponse,
  name: string,
  description: string | null,
  inputs: ActionInput[]
): Promise<ActionsProject> {
  const response = await fetch(`${API_BASE_URL}/api/actions-projects/`, {
    method: 'POST',
    credentials: 'include',
    headers: jsonHeaders(),
    body: JSON.stringify({
      github_user: githubUser,
      name,
      description,
      source_url: preview.source_url,
      owner: preview.owner,
      repo: preview.repo,
      ref: preview.ref,
      yaml_path: preview.yaml_path,
      inputs,
      branding_icon: preview.branding_icon,
      branding_color: preview.branding_color,
    }),
  });
  return unwrap(response, 'Create failed');
}

export async function listActionsProjects(githubUser: string): Promise<ActionsProject[]> {
  const params = new URLSearchParams({ github_user: githubUser });
  const response = await fetch(`${API_BASE_URL}/api/actions-projects/?${params}`, {
    method: 'GET',
    credentials: 'include',
  });
  return unwrap(response, 'List failed');
}

export async function getActionsProject(githubUser: string, id: number): Promise<ActionsProject> {
  const params = new URLSearchParams({ github_user: githubUser });
  const response = await fetch(`${API_BASE_URL}/api/actions-projects/${id}?${params}`, {
    method: 'GET',
    credentials: 'include',
  });
  return unwrap(response, 'Fetch failed');
}

export async function updateActionsProject(
  githubUser: string,
  id: number,
  name: string,
  description: string | null,
  inputs: ActionInput[]
): Promise<ActionsProject> {
  const response = await fetch(`${API_BASE_URL}/api/actions-projects/${id}`, {
    method: 'PUT',
    credentials: 'include',
    headers: jsonHeaders(),
    body: JSON.stringify({ github_user: githubUser, name, description, inputs }),
  });
  return unwrap(response, 'Update failed');
}

export async function deleteActionsProject(githubUser: string, id: number): Promise<void> {
  const params = new URLSearchParams({ github_user: githubUser });
  const response = await fetch(`${API_BASE_URL}/api/actions-projects/${id}?${params}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Delete failed: ${response.status}`);
  }
}
