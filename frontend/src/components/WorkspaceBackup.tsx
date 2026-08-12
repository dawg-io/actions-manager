import React, { useCallback, useEffect, useState } from "react";
import { Button } from "./ui";
import { fetchBackupInfo, downloadBackup, BackupInfo } from "../api/backup";

interface WorkspaceBackupProps {
  readonly currentUserRole?: string;
}

const WorkspaceBackup: React.FC<WorkspaceBackupProps> = ({ currentUserRole }) => {
  // undefined means the role has not arrived yet. Treating that as "not an
  // admin" flashes an access-denied message at an actual admin on every
  // refresh, which reads as having lost the role.
  const roleKnown = currentUserRole !== undefined;
  const isAdmin = currentUserRole === "admin";

  const [info, setInfo] = useState<BackupInfo | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const loadInfo = useCallback(async () => {
    try {
      setInfo(await fetchBackupInfo());
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : "Could not load backup info", type: "error" });
    }
  }, []);

  useEffect(() => {
    if (isAdmin) {
      void loadInfo();
    }
  }, [isAdmin, loadInfo]);

  const handleDownload = async (): Promise<void> => {
    setDownloading(true);
    setMessage(null);
    try {
      const filename = await downloadBackup();
      setMessage({ text: `Backup downloaded as ${filename}`, type: "success" });
      // Row counts move as the workspace is used; re-read them so the panel
      // reflects what the next backup would capture, not what this one did.
      await loadInfo();
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : "Backup failed", type: "error" });
    } finally {
      setDownloading(false);
    }
  };

  if (!roleKnown) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-xl font-semibold text-text-primary dark:text-text-primary-dark mb-2">Backup</h1>
        <p className="text-sm text-text-secondary dark:text-secondary-dark">Checking your access…</p>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-xl font-semibold text-text-primary dark:text-text-primary-dark mb-2">Backup</h1>
        <p className="text-sm text-text-secondary dark:text-secondary-dark">
          Only workspace admins can download a backup.
        </p>
      </div>
    );
  }

  const populatedTables = info
    ? Object.entries(info.tables).filter(([, rows]) => rows > 0).sort(([a], [b]) => a.localeCompare(b))
    : [];

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary dark:text-text-primary-dark mb-2">Backup</h1>
        <p className="text-sm text-text-secondary dark:text-secondary-dark">
          Download a complete backup of this installation — projects, workflows, repositories,
          rulesets, and settings. Take one before upgrading.
        </p>
      </div>

      <div className="rounded-md border border-border dark:border-border-dark p-4 space-y-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-text-primary dark:text-text-primary-dark">
              {info ? `${info.total_rows} row(s) across ${info.table_count} table(s)` : "Reading workspace…"}
            </p>
            <p className="text-xs text-text-secondary dark:text-secondary-dark mt-1">
              Saved access tokens are included in their encrypted form. Keep your{" "}
              <code className="font-mono">SECRET_KEY</code> safe — without it, a restored
              installation cannot decrypt them.
            </p>
          </div>
          <Button onClick={handleDownload} disabled={downloading}>
            {downloading ? "Preparing…" : "Download backup"}
          </Button>
        </div>

        {info && info.excluded_tables.length > 0 && (
          <p className="text-xs text-text-secondary dark:text-secondary-dark">
            Not included: {info.excluded_tables.join(", ")} — sign-in sessions deliberately do not
            survive a restore.
          </p>
        )}
      </div>

      {message && (
        <p
          className={`text-sm ${
            message.type === "success" ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"
          }`}
        >
          {message.text}
        </p>
      )}

      {populatedTables.length > 0 && (
        <div>
          <h2 className="text-sm font-medium text-text-primary dark:text-text-primary-dark mb-2">
            What this backup contains
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="text-text-secondary dark:text-secondary-dark">
                  <th className="pr-4 py-1">Table</th>
                  <th className="pr-4 py-1">Rows</th>
                </tr>
              </thead>
              <tbody>
                {populatedTables.map(([table, rows]) => (
                  <tr key={table} className="border-t border-border dark:border-border-dark">
                    <td className="pr-4 py-1 font-mono text-xs text-text-primary dark:text-text-primary-dark">{table}</td>
                    <td className="pr-4 py-1 text-text-primary dark:text-text-primary-dark">{rows}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="rounded-md border border-border dark:border-border-dark p-4">
        <h2 className="text-sm font-medium text-text-primary dark:text-text-primary-dark mb-2">Restoring</h2>
        <p className="text-sm text-text-secondary dark:text-secondary-dark">
          A backup is restored into a fresh installation from the sign-in screen, before the first
          account is created. To restore over an installation that is already in use, or to recover
          one that no longer starts, run:
        </p>
        <pre className="mt-2 overflow-x-auto rounded bg-gray-100 dark:bg-gray-800 p-2 text-xs font-mono text-text-primary dark:text-text-primary-dark">
          python backup_cli.py restore --in /app/data/backup.tar.gz
        </pre>
        <p className="mt-3 text-sm text-text-secondary dark:text-secondary-dark">
          Looking for a single project? Each project&apos;s config page has an Export Config section
          that captures just that project&apos;s settings and workflows.
        </p>
      </div>
    </div>
  );
};

export default WorkspaceBackup;
