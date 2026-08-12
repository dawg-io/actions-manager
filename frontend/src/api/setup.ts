/**
 * First-boot setup API client (issue #1878).
 *
 * Only reachable while nobody has signed in yet. Once the workspace has a
 * member the server refuses these routes permanently, and the sign-in screen
 * stops offering them.
 */

import config from '../config';

const API_BASE_URL = config.BACKEND_URL;

export interface RestoreReport {
  upload_token: string;
  ok: boolean;
  errors: string[];
  warnings: string[];
  total_rows: number;
  tables: Record<string, number>;
  app_version: string | null;
  created_at: string | null;
  dialect: string | null;
}

export interface RestoreResult {
  restored_rows: number;
  restored_tables: number;
  skipped_tables: string[];
  warnings: string[];
  migrations_ran: boolean;
}

/** The server's reason when it sent one, otherwise the status code. */
async function failure(response: Response, fallback: string): Promise<Error> {
  const body = await response.json().catch(() => null);
  return new Error(body?.detail || `${fallback}: ${response.status}`);
}

/** False once anyone has signed in — the restore offer disappears for good. */
export async function isUninitialized(): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/api/setup/status`, {
    method: 'GET',
    credentials: 'include',
  });
  if (!response.ok) {
    return false;
  }
  const body = await response.json();
  return Boolean(body.uninitialized);
}

/** Upload a backup and find out what restoring it would do. Writes nothing. */
export async function validateBackup(file: File): Promise<RestoreReport> {
  const form = new FormData();
  form.append('file', file);

  const response = await fetch(`${API_BASE_URL}/api/setup/restore/validate`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  });
  if (!response.ok) {
    throw await failure(response, 'Could not read that backup');
  }
  return response.json();
}

export async function applyBackup(uploadToken: string): Promise<RestoreResult> {
  const form = new FormData();
  form.append('upload_token', uploadToken);

  const response = await fetch(`${API_BASE_URL}/api/setup/restore/apply`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  });
  if (!response.ok) {
    throw await failure(response, 'Restore failed');
  }
  return response.json();
}
