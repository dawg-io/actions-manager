import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";
import CustomFiles, { CustomFilePanel } from "./CustomFiles";
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

  describe("removal scope", () => {
    const syncedFile = () =>
      mockFile({ file_status: "synced_with_github", git_hash: "a".repeat(40) });

    const openRemovalDialog = (file: api.CustomFile) => {
      render(<CustomFiles {...defaultProps} initialFiles={[file]} />);
      fireEvent.click(screen.getByTestId("custom-file-row"));
      fireEvent.click(screen.getByTestId("delete-button"));
    };

    test("delete opens the scope dialog with the safe option preselected", () => {
      openRemovalDialog(syncedFile());

      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByLabelText("Remove from ActionsManager only")).toBeChecked();
      expect(api.deleteCustomFile).not.toHaveBeenCalled();
    });

    test("project-scoped removal drops the row and leaves the file in GitHub", async () => {
      vi.mocked(api.deleteCustomFile).mockResolvedValue({ deleted: true, hard_deleted: true });
      const onChange = vi.fn();
      const file = syncedFile();

      render(<CustomFiles {...defaultProps} initialFiles={[file]} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("custom-file-row"));
      fireEvent.click(screen.getByTestId("delete-button"));
      fireEvent.click(screen.getByRole("button", { name: /Remove from ActionsManager/i }));

      await waitFor(() => {
        expect(api.deleteCustomFile).toHaveBeenCalledWith(42, file.id, "project", "campaign");
      });
      // The list updates from the response, with no refetch and no reload.
      expect(onChange).toHaveBeenCalledWith([]);
    });

    test("delete-everywhere defaults to a PR Campaign", async () => {
      vi.mocked(api.deleteCustomFile).mockResolvedValue({
        deleted: false,
        pending_delete: true,
        custom_file: { ...syncedFile(), pending_delete: true },
        campaign_id: 7,
        prs_created: 2,
      });
      const onChange = vi.fn();

      render(<CustomFiles {...defaultProps} initialFiles={[syncedFile()]} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("custom-file-row"));
      fireEvent.click(screen.getByTestId("delete-button"));
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
      fireEvent.click(screen.getByRole("button", { name: /Delete Everywhere/i }));

      await waitFor(() => {
        expect(api.deleteCustomFile).toHaveBeenCalledWith(42, 1, "project_and_github", "campaign");
      });
      // The row stays until the PR merges, so Restore still has something to act on.
      expect(onChange).toHaveBeenCalledWith([
        expect.objectContaining({ pending_delete: true }),
      ]);
    });

    test("delete-everywhere can commit the removal directly instead", async () => {
      vi.mocked(api.deleteCustomFile).mockResolvedValue({
        deleted: true,
        hard_deleted: true,
        targets: [{ repo: "acme/app", branch: "main", status: "deleted" }],
      });
      const onChange = vi.fn();

      render(<CustomFiles {...defaultProps} initialFiles={[syncedFile()]} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("custom-file-row"));
      fireEvent.click(screen.getByTestId("delete-button"));
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
      fireEvent.click(screen.getByLabelText("Commit directly to the target branch"));
      fireEvent.click(screen.getByRole("button", { name: /Delete Everywhere/i }));

      await waitFor(() => {
        expect(api.deleteCustomFile).toHaveBeenCalledWith(42, 1, "project_and_github", "direct");
      });
      // Gone from GitHub, so gone from the list — no pending-delete row left behind.
      expect(onChange).toHaveBeenCalledWith([]);
    });

    test("reports the new project state so Create PR Campaign enables without a reload", async () => {
      vi.mocked(api.deleteCustomFile).mockResolvedValue({
        deleted: false,
        pending_delete: true,
        custom_file: { ...syncedFile(), pending_delete: true },
        campaign_id: 7,
        prs_created: 2,
        pr_state: "draft",
      });
      const onProjectStateChange = vi.fn();

      render(
        <CustomFiles
          {...defaultProps}
          initialFiles={[syncedFile()]}
          onChange={vi.fn()}
          onProjectStateChange={onProjectStateChange}
        />
      );
      fireEvent.click(screen.getByTestId("custom-file-row"));
      fireEvent.click(screen.getByTestId("delete-button"));
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
      fireEvent.click(screen.getByRole("button", { name: /Delete Everywhere/i }));

      await waitFor(() => expect(onProjectStateChange).toHaveBeenCalledWith("draft"));
    });

    test("GitHub option is disabled for a file GitHub has never seen", () => {
      openRemovalDialog(mockFile({ file_status: "new", git_hash: null }));

      expect(screen.getByLabelText("Delete from ActionsManager and GitHub")).toBeDisabled();
    });

    test("the warning matches the delivery the user picked", () => {
      openRemovalDialog(syncedFile());
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

      // A pull request can be closed and the file restored until it merges.
      // Said in both the delivery option and the amber warning.
      expect(screen.getAllByText(/you can Restore it here until then/).length).toBeGreaterThan(0);
      expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument();

      fireEvent.click(screen.getByLabelText("Commit directly to the target branch"));

      // A direct commit really is permanent.
      expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
    });

    test("CustomFilePanel tells its parent to clear the selection when the row is gone", async () => {
      vi.mocked(api.deleteCustomFile).mockResolvedValue({ deleted: true, hard_deleted: true });
      const onRemoved = vi.fn();
      const file = syncedFile();

      render(
        <CustomFilePanel
          cf={file}
          allFiles={[file]}
          projectId={42}
          githubUser="testuser"
          onChange={vi.fn()}
          onRemoved={onRemoved}
        />
      );
      fireEvent.click(screen.getByTestId("delete-button"));
      fireEvent.click(screen.getByRole("button", { name: /Remove from ActionsManager/i }));

      // Without this the parent keeps an id that no longer exists and the panel
      // silently renders the "add file" form in place of the removed file.
      await waitFor(() => expect(onRemoved).toHaveBeenCalled());
    });
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
