import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import WorkspaceBackup from "./WorkspaceBackup";
import * as backupApi from "../api/backup";

const INFO: backupApi.BackupInfo = {
  backup_format_version: "1.0",
  table_count: 3,
  total_rows: 7,
  tables: { accounts: 2, projects: 5, workflows: 0 },
  excluded_tables: ["auth_sessions"],
};

describe("WorkspaceBackup", () => {
  beforeEach(() => {
    vi.spyOn(backupApi, "fetchBackupInfo").mockResolvedValue(INFO);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("hides the backup controls from non-admins", () => {
    render(<WorkspaceBackup currentUserRole="member" />);

    expect(screen.getByText(/only workspace admins/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /download backup/i })).not.toBeInTheDocument();
    expect(backupApi.fetchBackupInfo).not.toHaveBeenCalled();
  });

  it("shows what the backup would contain", async () => {
    render(<WorkspaceBackup currentUserRole="admin" />);

    expect(await screen.findByText(/7 row\(s\) across 3 table\(s\)/i)).toBeInTheDocument();
    expect(screen.getByText("accounts")).toBeInTheDocument();
    expect(screen.getByText("projects")).toBeInTheDocument();
    // Empty tables are noise in the summary.
    expect(screen.queryByText("workflows")).not.toBeInTheDocument();
    expect(screen.getByText(/auth_sessions/)).toBeInTheDocument();
  });

  it("downloads a backup and reports the filename without needing a refresh", async () => {
    const download = vi
      .spyOn(backupApi, "downloadBackup")
      .mockResolvedValue("actionsmanager-backup-2026-08-11.tar.gz");

    render(<WorkspaceBackup currentUserRole="admin" />);
    await screen.findByText(/7 row\(s\)/i);

    await userEvent.click(screen.getByRole("button", { name: /download backup/i }));

    await waitFor(() => {
      expect(screen.getByText(/actionsmanager-backup-2026-08-11\.tar\.gz/)).toBeInTheDocument();
    });
    expect(download).toHaveBeenCalledTimes(1);
    // Counts are re-read so the panel describes the next backup, not the last one.
    expect(backupApi.fetchBackupInfo).toHaveBeenCalledTimes(2);
  });

  it("surfaces a failed download instead of failing silently", async () => {
    vi.spyOn(backupApi, "downloadBackup").mockRejectedValue(new Error("Backup failed: 500"));

    render(<WorkspaceBackup currentUserRole="admin" />);
    await screen.findByText(/7 row\(s\)/i);

    await userEvent.click(screen.getByRole("button", { name: /download backup/i }));

    expect(await screen.findByText(/Backup failed: 500/)).toBeInTheDocument();
  });

  it("tells the admin where SECRET_KEY matters and how to restore", async () => {
    render(<WorkspaceBackup currentUserRole="admin" />);

    expect(await screen.findByText(/SECRET_KEY/)).toBeInTheDocument();
    expect(screen.getByText(/backup_cli\.py restore/)).toBeInTheDocument();
  });

  it("does not accuse an admin of lacking access while their role is loading", async () => {
    // currentUserRole is undefined until getUserDetails resolves. Treating that
    // as "not an admin" flashes access-denied at a real admin on every refresh.
    render(<WorkspaceBackup currentUserRole={undefined} />);

    expect(screen.getByText(/checking your access/i)).toBeInTheDocument();
    expect(screen.queryByText(/only workspace admins/i)).not.toBeInTheDocument();
    expect(backupApi.fetchBackupInfo).not.toHaveBeenCalled();
  });
});
