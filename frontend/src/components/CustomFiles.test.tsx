import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";
import CustomFiles from "./CustomFiles";
import * as api from "../api/customFiles";

vi.mock("./PlainFileEditor", () => ({
  default: ({ value, onChange }: { value: string; onChange?: (v: string) => void }) => (
    <textarea
      data-testid="file-content-input"
      value={value ?? ""}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
}));

vi.mock("../api/customFiles", () => ({
  createCustomFile: vi.fn(),
  updateCustomFile: vi.fn(),
  deleteCustomFile: vi.fn(),
  restoreCustomFile: vi.fn(),
  validateFilePath: vi.fn((p: string) => {
    if (!p?.trim()) return "File path is required";
    if (p.startsWith("/")) return "Absolute paths are not allowed";
    if (p.includes("..")) return "Path traversal (..) is not allowed";
    if (p.endsWith(".env") || p.includes(".env.")) return ".env files are not allowed";
    return null;
  }),
}));

const mockFile = (overrides = {}): api.CustomFile => ({
  id: 1,
  project_id: 42,
  display_name: "Build Script",
  file_path: ".github/scripts/build.sh",
  file_content: "#!/bin/bash",
  git_hash: null,
  file_status: "new",
  pending_delete: false,
  last_modified_by: "testuser",
  description: null,
  created_at: null,
  updated_at: null,
  ...overrides,
});

describe("CustomFiles", () => {
  const defaultProps = { projectId: 42, githubUser: "testuser", initialFiles: [] };

  test("renders empty state when no files", () => {
    render(<CustomFiles {...defaultProps} />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  test("renders file list when files provided", () => {
    render(<CustomFiles {...defaultProps} initialFiles={[mockFile()]} />);
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
    expect(screen.getByTestId("custom-file-row")).toBeInTheDocument();
    expect(screen.getByText(".github/scripts/build.sh")).toBeInTheDocument();
  });

  test("shows pending delete badge for pending_delete files", () => {
    render(<CustomFiles {...defaultProps} initialFiles={[mockFile({ pending_delete: true })]} />);
    expect(screen.getByTestId("pending-delete-badge")).toBeInTheDocument();
  });

  test("shows restore button for pending_delete files", () => {
    render(<CustomFiles {...defaultProps} initialFiles={[mockFile({ pending_delete: true })]} />);
    fireEvent.click(screen.getByTestId("custom-file-row"));
    expect(screen.getByTestId("restore-button")).toBeInTheDocument();
    expect(screen.queryByTestId("delete-button")).not.toBeInTheDocument();
  });

  test("shows add file form when button clicked", () => {
    render(<CustomFiles {...defaultProps} />);
    fireEvent.click(screen.getByTestId("add-custom-file-button"));
    expect(screen.getByTestId("file-path-input")).toBeInTheDocument();
    expect(screen.getByTestId("file-content-input")).toBeInTheDocument();
  });

  test("add form disables save button when path is empty", () => {
    render(<CustomFiles {...defaultProps} />);
    fireEvent.click(screen.getByTestId("add-custom-file-button"));
    expect(screen.getByTestId("save-button")).toBeDisabled();
  });

  test("add form validates absolute path", async () => {
    render(<CustomFiles {...defaultProps} />);
    fireEvent.click(screen.getByTestId("add-custom-file-button"));
    fireEvent.change(screen.getByTestId("file-path-input"), { target: { value: "/etc/passwd" } });
    expect(screen.getByTestId("path-error")).toBeInTheDocument();
    expect(screen.getByTestId("save-button")).toBeDisabled();
  });

  test("add form validates dotenv path", async () => {
    render(<CustomFiles {...defaultProps} />);
    fireEvent.click(screen.getByTestId("add-custom-file-button"));
    fireEvent.change(screen.getByTestId("file-path-input"), { target: { value: ".env.production" } });
    expect(screen.getByTestId("path-error")).toBeInTheDocument();
  });

  test("saving calls create API and updates state", async () => {
    const newFile = mockFile({ id: 99, file_path: "sonar-project.properties" });
    vi.mocked(api.createCustomFile).mockResolvedValueOnce({ custom_file: newFile });
    const onChange = vi.fn();
    render(<CustomFiles {...defaultProps} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("add-custom-file-button"));
    fireEvent.change(screen.getByTestId("file-path-input"), { target: { value: "sonar-project.properties" } });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => expect(api.createCustomFile).toHaveBeenCalledWith(42, expect.objectContaining({ file_path: "sonar-project.properties" })));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([newFile]));
  });

  test("editing calls update API", async () => {
    const cf = mockFile({ file_status: "synced_with_github", git_hash: "a".repeat(40) });
    const updated = { ...cf, file_status: "committed_locally", git_hash: null };
    vi.mocked(api.updateCustomFile).mockResolvedValueOnce({ custom_file: updated });
    render(<CustomFiles {...defaultProps} initialFiles={[cf]} />);
    fireEvent.click(screen.getByTestId("custom-file-row"));
    fireEvent.click(screen.getByTestId("edit-button"));
    fireEvent.change(screen.getByTestId("file-content-input"), { target: { value: "new content" } });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => expect(api.updateCustomFile).toHaveBeenCalledWith(42, 1, expect.objectContaining({ file_content: "new content" })));
  });

  test("restore calls restore API", async () => {
    const cf = mockFile({ pending_delete: true, git_hash: "a".repeat(40), file_status: "committed_locally" });
    const restored = { ...cf, pending_delete: false };
    vi.mocked(api.restoreCustomFile).mockResolvedValueOnce({ custom_file: restored });
    render(<CustomFiles {...defaultProps} initialFiles={[cf]} />);
    fireEvent.click(screen.getByTestId("custom-file-row"));
    fireEvent.click(screen.getByTestId("restore-button"));
    await waitFor(() => expect(api.restoreCustomFile).toHaveBeenCalledWith(42, 1));
  });

  // ── Bug 1 regression: onChange must fire on every mutation ──────────────────

  test("add fires onChange so parent can promote pr_state to draft", async () => {
    const newFile = mockFile({ id: 99, file_path: "sonar.properties", file_status: "new" });
    vi.mocked(api.createCustomFile).mockResolvedValueOnce({ custom_file: newFile });
    const onChange = vi.fn();
    render(<CustomFiles {...defaultProps} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("add-custom-file-button"));
    fireEvent.change(screen.getByTestId("file-path-input"), { target: { value: "sonar.properties" } });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([newFile]));
  });

  test("edit fires onChange so parent can promote pr_state to draft", async () => {
    const cf = mockFile({ file_status: "synced_with_github", git_hash: "a".repeat(40) });
    const updated = { ...cf, file_status: "committed_locally", git_hash: null };
    vi.mocked(api.updateCustomFile).mockResolvedValueOnce({ custom_file: updated });
    const onChange = vi.fn();
    render(<CustomFiles {...defaultProps} initialFiles={[cf]} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("custom-file-row"));
    fireEvent.click(screen.getByTestId("edit-button"));
    fireEvent.change(screen.getByTestId("file-content-input"), { target: { value: "changed" } });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([updated]));
  });

  // ── Bug 2 regression: component must reflect parent-driven prop updates ─────

  test("synced files remain visible after parent reloads customFiles", () => {
    const syncedFile = mockFile({ file_status: "synced_with_github", git_hash: "a".repeat(40) });
    const { rerender } = render(<CustomFiles {...defaultProps} initialFiles={[]} />);
    expect(screen.queryByTestId("custom-file-row")).not.toBeInTheDocument();

    // Simulate parent (ProjectMgmt) refreshing customFiles after PR merge
    rerender(<CustomFiles {...defaultProps} initialFiles={[syncedFile]} />);
    expect(screen.getByTestId("custom-file-row")).toBeInTheDocument();
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
  });

  test("synced file shows correct status badge", () => {
    const syncedFile = mockFile({ file_status: "synced_with_github", git_hash: "a".repeat(40) });
    render(<CustomFiles {...defaultProps} initialFiles={[syncedFile]} />);
    expect(screen.getByTestId("custom-file-row")).toBeInTheDocument();
    // No pending-delete badge on a clean synced file
    expect(screen.queryByTestId("pending-delete-badge")).not.toBeInTheDocument();
  });

  test("prop update replaces previous list (no stale internal state)", () => {
    const fileA = mockFile({ id: 1, file_path: ".yamllint.yml" });
    const fileB = mockFile({ id: 2, file_path: "sonar.properties", file_status: "synced_with_github" });
    const { rerender } = render(<CustomFiles {...defaultProps} initialFiles={[fileA]} />);
    expect(screen.getByText(".yamllint.yml")).toBeInTheDocument();

    // Parent swaps in a different list (e.g. after a project reload post-merge)
    rerender(<CustomFiles {...defaultProps} initialFiles={[fileB]} />);
    expect(screen.queryByText(".yamllint.yml")).not.toBeInTheDocument();
    expect(screen.getByText("sonar.properties")).toBeInTheDocument();
  });
});
