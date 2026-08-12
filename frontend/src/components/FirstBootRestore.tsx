import React, { useState } from "react";
import { Button } from "./ui";
import { validateBackup, applyBackup, RestoreReport, RestoreResult } from "../api/setup";

interface FirstBootRestoreProps {
  readonly onCancel: () => void;
  /** Fired once a restore lands, so the sign-in screen can re-check whether
   *  it should still be offering one. */
  readonly onRestored?: () => void;
}

const CONFIRM_PHRASE = "restore";

const FirstBootRestore: React.FC<FirstBootRestoreProps> = ({ onCancel, onRestored }) => {
  const [report, setReport] = useState<RestoreReport | null>(null);
  const [result, setResult] = useState<RestoreResult | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (event: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = event.target.files?.[0];
    if (!file) return;
    // A failed apply sends the operator back here, and browsers fire no change
    // event when the selection is unchanged — so without clearing this, picking
    // the same archive again does nothing at all and the screen looks dead.
    event.target.value = "";

    setBusy(true);
    setError(null);
    setReport(null);
    // Without this, a phrase typed for the previous archive still counts and
    // the destructive button is live the moment this one's report lands.
    setConfirmation("");
    try {
      setReport(await validateBackup(file));
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : "Could not read that backup");
    } finally {
      setBusy(false);
    }
  };

  const handleApply = async (): Promise<void> => {
    if (!report) return;

    setBusy(true);
    setError(null);
    try {
      setResult(await applyBackup(report.upload_token));
      onRestored?.();
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : "Restore failed");
      // The server discards the staged archive when an apply fails, so the
      // token this report carries is already dead. Send the operator back to
      // the file picker rather than to a second, unrelated 404.
      setReport(null);
      setConfirmation("");
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <div className="flex flex-col bg-container dark:bg-container-dark p-8 rounded-2xl shadow-xl border border-border dark:border-border-dark max-w-lg w-full gap-4">
        <h2 className="text-lg font-semibold text-text-primary dark:text-text-primary-dark">Restore complete</h2>
        <p className="text-sm text-text-secondary dark:text-secondary-dark">
          Restored {result.restored_rows} row(s) across {result.restored_tables} table(s).
        </p>
        {!result.migrations_ran && (
          <p className="text-sm text-red-600 dark:text-red-400">
            Migrations did not complete cleanly. Check the server logs before using this installation.
          </p>
        )}
        {result.warnings.map((warning) => (
          <p key={warning} className="text-sm text-amber-700 dark:text-amber-400">{warning}</p>
        ))}
        <p className="text-sm text-text-secondary dark:text-secondary-dark">
          Sign in with GitHub to continue — sign-in sessions are deliberately not carried across a restore.
        </p>
        <Button onClick={onCancel}>Back to sign in</Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col bg-container dark:bg-container-dark p-8 rounded-2xl shadow-xl border border-border dark:border-border-dark max-w-lg w-full gap-4">
      <div>
        <h2 className="text-lg font-semibold text-text-primary dark:text-text-primary-dark">
          Restore from a backup
        </h2>
        <p className="mt-1 text-sm text-text-secondary dark:text-secondary-dark">
          Restore an ActionsManager backup into this new installation. This is only offered
          before the first account signs in.
        </p>
      </div>

      <label className="text-sm text-text-primary dark:text-text-primary-dark" htmlFor="backup-file">
        Backup archive
      </label>
      <input
        accept=".gz,.tar.gz,application/gzip"
        aria-label="Backup archive"
        className="w-full rounded-lg border border-border dark:border-border-dark bg-white dark:bg-gray-800 px-3 py-2 text-sm text-text-primary dark:text-text-primary-dark"
        disabled={busy}
        id="backup-file"
        onChange={(event) => { void handleFile(event); }}
        type="file"
      />

      {busy && !report && (
        <p className="text-sm text-text-secondary dark:text-secondary-dark">Checking the backup…</p>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-200">
          {error}
        </div>
      )}

      {report && (
        <div className="space-y-3">
          <div className="rounded-md border border-border dark:border-border-dark p-3 text-sm">
            <p className="text-text-primary dark:text-text-primary-dark">
              {report.total_rows} row(s) across {Object.keys(report.tables).length} table(s)
            </p>
            <p className="mt-1 text-xs text-text-secondary dark:text-secondary-dark">
              Written by ActionsManager {report.app_version ?? "unknown"}
              {report.created_at ? ` on ${new Date(report.created_at).toLocaleString()}` : ""}
              {report.dialect ? ` (${report.dialect})` : ""}
            </p>
          </div>

          {report.errors.map((message) => (
            <p key={message} className="text-sm text-red-600 dark:text-red-400">{message}</p>
          ))}
          {report.warnings.map((message) => (
            <p key={message} className="text-sm text-amber-700 dark:text-amber-400">{message}</p>
          ))}

          {report.ok && (
            <>
              <label className="block text-sm text-text-primary dark:text-text-primary-dark" htmlFor="confirm-restore">
                Type <code className="font-mono">{CONFIRM_PHRASE}</code> to confirm
              </label>
              <input
                aria-label={`Type ${CONFIRM_PHRASE} to confirm`}
                autoComplete="off"
                className="w-full rounded-lg border border-border dark:border-border-dark bg-white dark:bg-gray-800 px-3 py-2 text-sm text-text-primary dark:text-text-primary-dark"
                id="confirm-restore"
                onChange={(event) => setConfirmation(event.target.value)}
                type="text"
                value={confirmation}
              />
            </>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-3 pt-2">
        <button
          className="text-sm text-text-secondary dark:text-secondary-dark hover:text-text-primary dark:hover:text-text-primary-dark transition-colors"
          onClick={onCancel}
          type="button"
        >
          ← Back to sign in
        </button>
        <Button
          disabled={!report?.ok || busy || confirmation.trim().toLowerCase() !== CONFIRM_PHRASE}
          onClick={() => { void handleApply(); }}
        >
          {busy && report ? "Restoring…" : "Restore this backup"}
        </Button>
      </div>
    </div>
  );
};

export default FirstBootRestore;
