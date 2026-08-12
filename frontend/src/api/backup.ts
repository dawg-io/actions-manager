/**
 * Workspace backup API client (issue #1878).
 *
 * Download only. Restoring happens at first boot, before anyone has signed in,
 * or through backup_cli.py — never as an authenticated action against a running
 * installation.
 */

import config from '../config';

const API_BASE_URL = config.BACKEND_URL;

export interface BackupInfo {
  backup_format_version: string;
  table_count: number;
  total_rows: number;
  tables: Record<string, number>;
  excluded_tables: string[];
}

/** The server's reason when it sent one, otherwise the status code — which is
 *  what distinguishes "not an admin" from "the server broke". */
async function failure(response: Response, fallback: string): Promise<Error> {
  const body = await response.json().catch(() => null);
  return new Error(body?.detail || `${fallback}: ${response.status}`);
}

export async function fetchBackupInfo(): Promise<BackupInfo> {
  const response = await fetch(`${API_BASE_URL}/api/workspace/backup/info`, {
    method: 'GET',
    credentials: 'include',
  });
  if (!response.ok) {
    throw await failure(response, 'Could not read backup info');
  }
  return response.json();
}

/** Filename the server chose, so a saved backup keeps its timestamp. */
function filenameFrom(header: string | null, fallback: string): string {
  const match = header ? /filename="?([^"]+)"?/.exec(header) : null;
  return match ? match[1] : fallback;
}

export async function downloadBackup(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/workspace/backup`, {
    method: 'GET',
    credentials: 'include',
  });
  if (!response.ok) {
    throw await failure(response, 'Backup failed');
  }

  const blob = await response.blob();
  const filename = filenameFrom(
    response.headers.get('content-disposition'),
    'actionsmanager-backup.tar.gz'
  );

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);

  return filename;
}
