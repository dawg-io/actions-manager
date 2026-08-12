import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";

import FirstBootRestore from "./FirstBootRestore";
import * as setupApi from "../api/setup";

const REPORT: setupApi.RestoreReport = {
  upload_token: "tok123",
  ok: true,
  errors: [],
  warnings: [],
  total_rows: 42,
  tables: { accounts: 2, projects: 40 },
  app_version: "1.0.0",
  created_at: "2026-08-11T20:00:00+00:00",
  dialect: "sqlite",
};

function archive(): File {
  return new File([new Blob(["archive-bytes"])], "backup.tar.gz", { type: "application/gzip" });
}

async function upload(): Promise<void> {
  await userEvent.upload(screen.getByLabelText(/backup archive/i), archive());
}

async function confirmAndRestore(): Promise<void> {
  await userEvent.type(screen.getByLabelText(/type restore to confirm/i), "restore");
  await userEvent.click(screen.getByRole("button", { name: /restore this backup/i }));
}

describe("FirstBootRestore", () => {
  afterEach(() => vi.restoreAllMocks());

  it("summarises the backup before anything is applied", async () => {
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue(REPORT);
    const apply = vi.spyOn(setupApi, "applyBackup");

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();

    expect(await screen.findByText(/42 row\(s\) across 2 table\(s\)/i)).toBeInTheDocument();
    expect(screen.getByText(/ActionsManager 1\.0\.0/)).toBeInTheDocument();
    expect(apply).not.toHaveBeenCalled();
  });

  it("will not restore until the confirmation phrase is typed", async () => {
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue(REPORT);

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();
    await screen.findByText(/42 row\(s\)/i);

    expect(screen.getByRole("button", { name: /restore this backup/i })).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/type restore to confirm/i), "restore");
    expect(screen.getByRole("button", { name: /restore this backup/i })).toBeEnabled();
  });

  it("refuses an incompatible backup and offers no way to apply it", async () => {
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue({
      ...REPORT,
      ok: false,
      errors: ["Backup came from a newer schema; upgrade first."],
    });

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();

    expect(await screen.findByText(/came from a newer schema/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/type restore to confirm/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore this backup/i })).toBeDisabled();
  });

  it("surfaces a SECRET_KEY mismatch without blocking the restore", async () => {
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue({
      ...REPORT,
      warnings: ["SECRET_KEY differs from the one this backup was written under."],
    });

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();

    expect(await screen.findByText(/SECRET_KEY differs/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/type restore to confirm/i), "restore");
    expect(screen.getByRole("button", { name: /restore this backup/i })).toBeEnabled();
  });

  it("tells the operator to sign in again once the restore lands", async () => {
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue(REPORT);
    vi.spyOn(setupApi, "applyBackup").mockResolvedValue({
      restored_rows: 42,
      restored_tables: 2,
      skipped_tables: [],
      warnings: [],
      migrations_ran: true,
    });

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();
    await screen.findByText(/42 row\(s\)/i);
    await confirmAndRestore();

    expect(await screen.findByText(/restore complete/i)).toBeInTheDocument();
    expect(screen.getByText(/sign in with github to continue/i)).toBeInTheDocument();
  });

  it("flags a restore whose migrations did not complete", async () => {
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue(REPORT);
    vi.spyOn(setupApi, "applyBackup").mockResolvedValue({
      restored_rows: 42,
      restored_tables: 2,
      skipped_tables: [],
      warnings: [],
      migrations_ran: false,
    });

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();
    await screen.findByText(/42 row\(s\)/i);
    await confirmAndRestore();

    expect(await screen.findByText(/migrations did not complete cleanly/i)).toBeInTheDocument();
  });

  it("reports a rejected upload instead of failing silently", async () => {
    vi.spyOn(setupApi, "validateBackup").mockRejectedValue(new Error("Archive is unreadable or corrupt"));

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();

    expect(await screen.findByText(/unreadable or corrupt/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /restore this backup/i })).toBeDisabled();
    });
  });

  it("clears a typed confirmation when a different archive is chosen", async () => {
    // Otherwise the phrase typed for archive A still counts for archive B, and
    // one click wipes the installation with a backup nobody confirmed.
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue(REPORT);

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();
    await screen.findByText(/42 row\(s\)/i);
    await userEvent.type(screen.getByLabelText(/type restore to confirm/i), "restore");
    expect(screen.getByRole("button", { name: /restore this backup/i })).toBeEnabled();

    await upload();

    await waitFor(() => {
      expect(screen.getByLabelText(/type restore to confirm/i)).toHaveValue("");
    });
    expect(screen.getByRole("button", { name: /restore this backup/i })).toBeDisabled();
  });

  it("sends the operator back to the file picker when applying fails", async () => {
    // The server discards the staged archive on failure, so leaving the report
    // on screen would only produce a second, unrelated 404 on retry.
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue(REPORT);
    vi.spyOn(setupApi, "applyBackup").mockRejectedValue(new Error("Restore failed and was rolled back"));

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();
    await screen.findByText(/42 row\(s\)/i);
    await confirmAndRestore();

    expect(await screen.findByText(/rolled back/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/type restore to confirm/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore this backup/i })).toBeDisabled();
  });

  it("reports a completed restore so the caller can re-check setup status", async () => {
    const onRestored = vi.fn();
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue(REPORT);
    vi.spyOn(setupApi, "applyBackup").mockResolvedValue({
      restored_rows: 42,
      restored_tables: 2,
      skipped_tables: [],
      warnings: [],
      migrations_ran: true,
    });

    render(<FirstBootRestore onCancel={vi.fn()} onRestored={onRestored} />);
    await upload();
    await screen.findByText(/42 row\(s\)/i);
    await confirmAndRestore();

    await screen.findByText(/restore complete/i);
    expect(onRestored).toHaveBeenCalledTimes(1);
  });

  it("accepts the same archive again after a failed apply", async () => {
    // Browsers fire no change event when the selection is unchanged, so the
    // handler must clear the input. userEvent.upload assigns input.files and
    // dispatches change unconditionally, which would hide this — drive the
    // input the way a browser actually does instead.
    vi.spyOn(setupApi, "validateBackup").mockResolvedValue(REPORT);
    vi.spyOn(setupApi, "applyBackup").mockRejectedValue(new Error("network blip"));

    render(<FirstBootRestore onCancel={vi.fn()} />);
    await upload();
    await screen.findByText(/42 row\(s\)/i);
    await confirmAndRestore();
    await screen.findByText(/network blip/i);

    const input = screen.getByLabelText(/backup archive/i) as HTMLInputElement;
    expect(input.value).toBe("");
  });
});
