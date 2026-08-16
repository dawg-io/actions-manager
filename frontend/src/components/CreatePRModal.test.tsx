import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import CreatePRModal from "./CreatePRModal";
import * as pullRequestApi from "../api/pullRequests";

import type { Mock } from 'vitest';
vi.mock("../api/pullRequests", () => ({
  createPullRequests: vi.fn(),
  getCreatePullRequestsStatus: vi.fn(),
  runPreflightValidation: vi.fn(),
  getPreflightValidationStatus: vi.fn(),
  closePreflightValidationPR: vi.fn(),
  mergePreflightValidationPR: vi.fn(),
}));

describe("CreatePRModal", () => {
  const baseProps = {
    user: "testuser",
    projectName: "Test Project",
    repositories: [{ name: "owner/repo-a" }, { name: "owner/repo-b" }],
    workflows: [{ name: "build" }],
    reusableWorkflows: [],
    onPreflightStatusChange: vi.fn(),
    onClose: vi.fn(),
    onSuccess: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("defaults workflow selection to only changed workflows", () => {
    render(
      <CreatePRModal
        {...baseProps}
        workflows={[
          { name: "build", status: "committed_locally" },
          { name: "deploy", status: "synced_with_github" },
          { name: "test", status: "new" },
        ]}
      />
    );

    // Repos (2) + changed workflows (build, test) = 4 checkboxes visible
    // "deploy" is synced and should be hidden by default
    // Workflow names are displayed with .yml extension
    expect(screen.getByText("build.yml")).toBeInTheDocument();
    expect(screen.getByText("test.yml")).toBeInTheDocument();
    expect(screen.queryByText("deploy.yml")).not.toBeInTheDocument();
    // The toggle to show unchanged should appear
    expect(screen.getByText(/show unchanged workflows/i)).toBeInTheDocument();
  });

  it("shows unchanged workflows when toggle is enabled", () => {
    render(
      <CreatePRModal
        {...baseProps}
        workflows={[
          { name: "build", status: "committed_locally" },
          { name: "deploy", status: "synced_with_github" },
        ]}
      />
    );

    expect(screen.queryByText("deploy.yml")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/show unchanged workflows/i));
    expect(screen.getByText("deploy.yml")).toBeInTheDocument();
  });

  it("unchanged workflows are not selected by default", () => {
    render(
      <CreatePRModal
        {...baseProps}
        workflows={[
          { name: "build", status: "committed_locally" },
          { name: "deploy", status: "synced_with_github" },
        ]}
      />
    );

    // Show unchanged
    fireEvent.click(screen.getByText(/show unchanged workflows/i));
    // Find the deploy checkbox - it should be unchecked
    const deployItem = screen.getByText("deploy.yml").closest(".repo-item");
    const deployCheckbox = deployItem!.querySelector("input[type='checkbox']") as HTMLInputElement;
    expect(deployCheckbox.checked).toBe(false);

    // build should be checked
    const buildItem = screen.getByText("build.yml").closest(".repo-item");
    const buildCheckbox = buildItem!.querySelector("input[type='checkbox']") as HTMLInputElement;
    expect(buildCheckbox.checked).toBe(true);
  });

  it("shows all workflows when none have status info (backward compat)", () => {
    render(
      <CreatePRModal
        {...baseProps}
        workflows={[
          { name: "build" },
          { name: "deploy" },
        ]}
      />
    );

    expect(screen.getByText("build.yml")).toBeInTheDocument();
    expect(screen.getByText("deploy.yml")).toBeInTheDocument();
    expect(screen.queryByText(/show unchanged workflows/i)).not.toBeInTheDocument();
  });

  it("shows unchanged toggle for reusable workflows when they have changed and synced items", () => {
    render(
      <CreatePRModal
        {...baseProps}
        workflows={[]}
        reusableWorkflows={[
          { name: "shared-build", status: "committed_locally" },
          { name: "shared-test", status: "synced_with_github" },
        ]}
      />
    );

    expect(screen.getByText(/show unchanged workflows/i)).toBeInTheDocument();
    expect(screen.queryByText("shared-test.yml")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText(/show unchanged workflows/i));
    expect(screen.getByText("shared-test.yml")).toBeInTheDocument();
  });

  describe("linked reusable workflows", () => {
    it("includes linked reusable workflows in total workflow count", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[{ name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo" }]}
        />
      );

      // Campaign summary should show total count including both standard and reusable workflows
      expect(screen.getByText(/2 of 2 workflow/i)).toBeInTheDocument();
      expect(screen.getByText(/1 standard, 1 reusable/i)).toBeInTheDocument();
    });

    it("only auto-selects changed linked reusable workflows", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[
            { name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo" },
            { name: "shared-test", status: "synced_with_github", sourceRepo: "owner/rwx-repo" },
          ]}
        />
      );

      // shared-build should be auto-selected (changed)
      const sharedBuildItem = screen.getByText("shared-build.yml").closest(".repo-item");
      const sharedBuildCheckbox = sharedBuildItem!.querySelector("input[type='checkbox']") as HTMLInputElement;
      expect(sharedBuildCheckbox.checked).toBe(true);

      // shared-test should not be visible initially (synced), and when shown should not be selected
      expect(screen.queryByText("shared-test.yml")).not.toBeInTheDocument();
      fireEvent.click(screen.getByText(/show unchanged workflows/i));
      const sharedTestItem = screen.getByText("shared-test.yml").closest(".repo-item");
      const sharedTestCheckbox = sharedTestItem!.querySelector("input[type='checkbox']") as HTMLInputElement;
      expect(sharedTestCheckbox.checked).toBe(false);
    });

    it("does not auto-select synced linked reusable workflows when no changed ones exist", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[
            { name: "shared-test", status: "synced_with_github", sourceRepo: "owner/rwx-repo" },
            { name: "shared-deploy", status: "synced_with_github", sourceRepo: "owner/rwx-repo" },
          ]}
        />
      );

      // No reusable workflows should be auto-selected since they're all synced
      // Campaign summary should show only 1 selected (the standard workflow)
      expect(screen.getByText(/1 of 3 workflow/i)).toBeInTheDocument();
      expect(screen.getByText(/1 standard, 0 reusable/i)).toBeInTheDocument();
    });

    it("allows manual selection of synced linked reusable workflows", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[
            { name: "shared-test", status: "synced_with_github", sourceRepo: "owner/rwx-repo" },
          ]}
        />
      );

      // Initially 1 workflow selected (the changed standard workflow)
      expect(screen.getByText(/1 of 2 workflow/i)).toBeInTheDocument();

      // The synced reusable workflow should be visible (since there's no changed reusable workflow,
      // it falls through to show all reusable workflows) and not selected
      const sharedTestItem = screen.getByText("shared-test.yml").closest(".repo-item");
      expect(sharedTestItem).toBeInTheDocument();
      
      // Manually select the synced reusable workflow
      fireEvent.click(sharedTestItem!);

      // Now 2 workflows should be selected
      expect(screen.getByText(/2 of 2 workflow/i)).toBeInTheDocument();
    });

    it("shows workflow count in Create Campaign button", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[{ name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo" }]}
        />
      );

      // Button should include workflow count - 3 PRs (2 caller repos + 1 source repo), 2 workflows
      expect(screen.getByRole("button", { name: /create 3 pr.*2 workflow/i })).toBeInTheDocument();
    });

    it("updates button count when workflow selection changes", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[{ name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo" }]}
        />
      );

      // Initially 3 PRs (2 caller + 1 source) and 2 workflows selected
      expect(screen.getByRole("button", { name: /3 pr.*2 workflow/i })).toBeInTheDocument();

      // Deselect the reusable workflow
      const sharedBuildItem = screen.getByText("shared-build.yml").closest(".repo-item");
      fireEvent.click(sharedBuildItem!);

      // Now 2 PRs (just caller repos) and 1 workflow
      expect(screen.getByRole("button", { name: /2 pr.*1 workflow\)/i })).toBeInTheDocument();
    });

    it("only counts source repos when only reusable workflows are selected", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[{ name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo" }]}
        />
      );

      // Initially 3 PRs (2 caller + 1 source) and 2 workflows selected
      expect(screen.getByRole("button", { name: /3 pr.*2 workflow/i })).toBeInTheDocument();

      // Deselect the standard workflow - keep only reusable workflow selected
      const buildItem = screen.getByText("build.yml").closest(".repo-item");
      fireEvent.click(buildItem!);

      // Now only 1 PR (just source repo for reusable workflow) and 1 workflow
      // Caller repos should NOT be counted when no standard workflows are selected
      expect(screen.getByRole("button", { name: /1 pr.*1 workflow\)/i })).toBeInTheDocument();
    });

    it("counts PR targets correctly with multiple reusable workflows from same source repo", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[
            { name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo" },
            { name: "shared-deploy", status: "committed_locally", sourceRepo: "owner/rwx-repo" },
          ]}
        />
      );

      // Both reusable workflows are from the same source repo, so only 1 additional PR target
      // 2 caller repos + 1 source repo = 3 PRs, but 3 workflows
      expect(screen.getByRole("button", { name: /3 pr.*3 workflow/i })).toBeInTheDocument();
    });

    it("counts PR targets correctly with reusable workflows from different source repos", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[
            { name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo-1" },
            { name: "shared-deploy", status: "committed_locally", sourceRepo: "owner/rwx-repo-2" },
          ]}
        />
      );

      // 2 caller repos + 2 source repos = 4 PRs, 3 workflows
      expect(screen.getByRole("button", { name: /4 pr.*3 workflow/i })).toBeInTheDocument();
    });

    it("shows reusable workflow source repositories section when workflows are selected", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[{ name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo" }]}
        />
      );

      // Source repositories section should be visible
      expect(screen.getByText("Reusable Workflow Source Repositories")).toBeInTheDocument();
      expect(screen.getByText("owner/rwx-repo")).toBeInTheDocument();
      expect(screen.getByText(/these repositories will also receive prs/i)).toBeInTheDocument();
    });

    it("hides source repositories section when no reusable workflows are selected", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[{ name: "shared-build", status: "synced_with_github", sourceRepo: "owner/rwx-repo" }]}
        />
      );

      // Source repositories section should not be visible (no changed reusable workflows selected by default)
      expect(screen.queryByText("Reusable Workflow Source Repositories")).not.toBeInTheDocument();
    });

    it("deduplicates PR count when caller repo is also a source repo", () => {
      render(
        <CreatePRModal
          {...baseProps}
          repositories={[{ name: "owner/repo-a" }, { name: "owner/rwx-repo" }]}
          workflows={[{ name: "build", status: "committed_locally" }]}
          reusableWorkflows={[{ name: "shared-build", status: "committed_locally", sourceRepo: "owner/rwx-repo" }]}
        />
      );

      // owner/rwx-repo appears as both caller and source, so it should only be counted once
      // 2 caller repos (one of which is the source) = 2 PRs, 2 workflows
      expect(screen.getByRole("button", { name: /2 pr.*2 workflow/i })).toBeInTheDocument();
    });

    it("counts CODEOWNERS as 1 file in create button text", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          codeownersRepos={["owner/repo-a", "owner/repo-b"]}
        />
      );

      // 2 caller repos + CODEOWNERS selected for both = 2 PRs, 1 workflow, 1 file (CODEOWNERS)
      expect(screen.getByRole("button", { name: /create 2 pr.*1 workflow.*1 file/i })).toBeInTheDocument();
    });

    it("sums custom files and CODEOWNERS in create button text", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "committed_locally" }]}
          customFiles={[
            { id: 1, file_path: ".github/scripts/setup.sh", file_status: "committed_locally", pending_delete: false },
            { id: 2, file_path: ".github/myfiles/test.txt", file_status: "committed_locally", pending_delete: false },
          ]}
          codeownersRepos={["owner/repo-a"]}
        />
      );

      // 2 workflows selected=1, 2 custom files selected by default + 1 CODEOWNERS = 3 files
      expect(screen.getByRole("button", { name: /create 2 pr.*1 workflow.*3 file/i })).toBeInTheDocument();
    });
  });

  it("shows actionable message for validation_repo_inaccessible status", () => {
    render(
      <CreatePRModal
        {...baseProps}
        validationRepo="owner/validation"
        preflightRequired={true}
        preflightStatus="validation_repo_inaccessible"
        preflightRunAt={null}
        preflightError={null}
        preflightPrUrl={null}
      />
    );

    // The status message should include actionable instructions about required permissions
    const modal = document.querySelector(".create-pr-modal")!;
    expect(modal.textContent).toMatch(/Pull requests.*read/i);
    expect(modal.textContent).toMatch(/personal access tokens/i);
  });

  it("disables Create Campaign when preflight is required and not passed", () => {
    render(
      <CreatePRModal
        {...baseProps}
        validationRepo="owner/validation"
        preflightRequired={true}
        preflightStatus="not_run"
        preflightRunAt={null}
        preflightError={null}
        preflightPrUrl={null}
      />
    );

    expect(screen.getByRole("heading", { name: /campaign readiness/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create campaign/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /run preflight/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh status/i })).toBeInTheDocument();
    expect(screen.getByText(/campaign creation is gated/i)).toHaveTextContent(
      /preflight is required/i
    );
  });

  it("enables Create Campaign when preflight is optional", () => {
    render(
      <CreatePRModal
        {...baseProps}
        validationRepo="owner/validation"
        preflightRequired={false}
        preflightStatus="not_run"
        preflightRunAt={null}
        preflightError={null}
        preflightPrUrl={null}
      />
    );

    expect(screen.getByRole("button", { name: /create campaign/i })).toBeEnabled();
  });

  it("shows and runs validation PR management actions", async () => {
    (pullRequestApi.getPreflightValidationStatus as Mock).mockResolvedValue({
      status: "validation_pr_open",
      validation_repo: "owner/validation",
      last_preflight_run_at: "2026-05-27T02:00:00Z",
      last_preflight_error: null,
      last_preflight_pr_url: "https://github.com/owner/validation/pull/1",
      pr_state: "open",
      can_merge: true,
      can_close: true,
    });
    (pullRequestApi.mergePreflightValidationPR as Mock).mockResolvedValue({
      message: "Validation PR merged",
      status: "passed",
      last_preflight_pr_url: "https://github.com/owner/validation/pull/1",
      branch_deleted: true,
      branch_delete_warning: null,
    });

    render(
      <CreatePRModal
        {...baseProps}
        validationRepo="owner/validation"
        preflightRequired={true}
        preflightStatus="validation_pr_open"
        preflightRunAt="2026-05-27T02:00:00Z"
        preflightError={null}
        preflightPrUrl="https://github.com/owner/validation/pull/1"
      />
    );

    expect(screen.getAllByRole("link", { name: /open validation pr/i })[0]).toHaveAttribute(
      "href",
      "https://github.com/owner/validation/pull/1"
    );
    expect(screen.getByRole("button", { name: /refresh status/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /merge validation pr/i })).toBeEnabled();
      expect(screen.getByRole("button", { name: /close validation pr/i })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /merge validation pr/i }));

    await waitFor(() => {
      expect(pullRequestApi.mergePreflightValidationPR).toHaveBeenCalledWith("testuser", "Test Project", true);
    });
    expect(pullRequestApi.getPreflightValidationStatus).toHaveBeenCalled();
  });

  it("explains closed preflight state and disabled validation actions", () => {
    render(
      <CreatePRModal
        {...baseProps}
        validationRepo="owner/validation"
        preflightRequired={true}
        preflightStatus="closed"
        preflightRunAt="2026-05-27T02:00:00Z"
        preflightError={null}
        preflightPrUrl="https://github.com/owner/validation/pull/1"
      />
    );

    expect(screen.getByRole("heading", { name: /campaign readiness/i })).toBeInTheDocument();
    expect(
      screen.getByText(/validation PR was closed without merging/i)
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/closed without merge/i).length
    ).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /re-run preflight/i })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /close validation pr/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /merge validation pr/i })).not.toBeInTheDocument();
  });

  describe("PR creation progress", () => {
    const propsWithWorkflows = {
      ...baseProps,
      workflows: [{ name: "build", status: "committed_locally" }],
      reusableWorkflows: [{ name: "shared-deploy", status: "committed_locally" }],
    };

    it("shows Creating PRs... button text and progress during creation", async () => {
      (pullRequestApi.createPullRequests as Mock).mockReturnValue(
        new Promise(() => {}) // never resolves - stays in creating state
      );

      render(<CreatePRModal {...propsWithWorkflows} />);
      fireEvent.click(screen.getByRole("button", { name: /create 2 pr/i }));

      // During creation, the progress section appears and footer Close is disabled
      await waitFor(() => {
        expect(screen.getByTestId("pr-creation-progress")).toBeInTheDocument();
      });
      // Close button in footer should be disabled while creating
      const closeBtn = screen.getByRole("button", { name: /close/i });
      expect(closeBtn).toBeDisabled();
    });

    it("shows per-repository progress rows during async creation", async () => {
      (pullRequestApi.createPullRequests as Mock).mockResolvedValue({
        task_id: "test-task-123",
        status: "running",
      });
      (pullRequestApi.getCreatePullRequestsStatus as Mock).mockResolvedValue({
        status: "running",
        repos: {
          "owner/repo-a on main": { step: "Creating branch", status: "running", error: null },
        },
        results: {},
        prs_created: 0,
      });

      render(<CreatePRModal {...propsWithWorkflows} />);
      fireEvent.click(screen.getByRole("button", { name: /create 2 pr/i }));

      await waitFor(() => {
        expect(screen.getByTestId("pr-creation-progress")).toBeInTheDocument();
      });
      await waitFor(() => {
        expect(screen.getByTestId("repo-progress-list")).toBeInTheDocument();
      });
      // Shows repo-a with its running step
      await waitFor(() => {
        const rows = screen.getAllByTestId("repo-status-row");
        expect(rows.length).toBe(2); // owner/repo-a and owner/repo-b
      });
    });

    it("shows linked reusable workflow source repo as a progress row during creation", async () => {
      (pullRequestApi.createPullRequests as Mock).mockResolvedValue({
        task_id: "test-task-rwx",
        status: "running",
      });
      (pullRequestApi.getCreatePullRequestsStatus as Mock).mockResolvedValue({
        status: "running",
        repos: {
          "owner/repo-a on main": { step: "Creating branch", status: "running", error: null },
          "owner/repo-b on main": { step: "Pending", status: "running", error: null },
          "owner/rwx-repo on main": { step: "Committing files", status: "running", error: null },
        },
        results: {},
        prs_created: 0,
      });

      const propsWithLinkedReusable = {
        ...baseProps,
        workflows: [{ name: "build", status: "committed_locally" }],
        reusableWorkflows: [
          { name: "shared-deploy", status: "committed_locally", sourceRepo: "owner/rwx-repo" },
        ],
      };

      render(<CreatePRModal {...propsWithLinkedReusable} />);
      // 2 caller repos + 1 RWX source repo = 3 PR targets
      fireEvent.click(screen.getByRole("button", { name: /create 3 pr/i }));

      await waitFor(() => {
        expect(screen.getByTestId("pr-creation-progress")).toBeInTheDocument();
      });
      await waitFor(() => {
        const rows = screen.getAllByTestId("repo-status-row");
        // 2 caller repos + 1 reusable source repo
        expect(rows.length).toBe(3);
      });
      // The RWX source repo is explicitly visible in the progress list
      expect(screen.getByText("owner/rwx-repo")).toBeInTheDocument();
    });

    it("deduplicates caller repo and RWX source repo when they are the same", async () => {
      (pullRequestApi.createPullRequests as Mock).mockResolvedValue({
        task_id: "test-task-dedup",
        status: "running",
      });
      (pullRequestApi.getCreatePullRequestsStatus as Mock).mockResolvedValue({
        status: "running",
        repos: {
          "owner/repo-a on main": { step: "Committing files", status: "running", error: null },
        },
        results: {},
        prs_created: 0,
      });

      // repo-a is both a caller repo and the RWX source repo
      const propsWithSameRepo = {
        ...baseProps,
        repositories: [{ name: "owner/repo-a" }],
        workflows: [{ name: "build", status: "committed_locally" }],
        reusableWorkflows: [
          { name: "shared-deploy", status: "committed_locally", sourceRepo: "owner/repo-a" },
        ],
      };

      render(<CreatePRModal {...propsWithSameRepo} />);
      fireEvent.click(screen.getByRole("button", { name: /create 1 pr/i }));

      await waitFor(() => {
        expect(screen.getByTestId("pr-creation-progress")).toBeInTheDocument();
      });
      await waitFor(() => {
        const rows = screen.getAllByTestId("repo-status-row");
        // Deduplication: only 1 unique target repo
        expect(rows.length).toBe(1);
      });
    });

    it("shows workflow files with .yml during creation", async () => {
      (pullRequestApi.createPullRequests as Mock).mockResolvedValue({
        task_id: "test-task-456",
        status: "running",
      });
      (pullRequestApi.getCreatePullRequestsStatus as Mock).mockResolvedValue({
        status: "running",
        repos: {},
        results: {},
        prs_created: 0,
      });

      render(<CreatePRModal {...propsWithWorkflows} />);
      fireEvent.click(screen.getByRole("button", { name: /create 2 pr/i }));

      await waitFor(() => {
        expect(screen.getByTestId("pr-creation-progress")).toBeInTheDocument();
      });
      // Standard workflow name gets .yml
      expect(screen.getByText("build.yml")).toBeInTheDocument();
      // Reusable workflow name gets .yml
      expect(screen.getByText("shared-deploy.yml")).toBeInTheDocument();
    });

    it("does not double .yml on workflow names that already have extension", async () => {
      (pullRequestApi.createPullRequests as Mock).mockResolvedValue({
        task_id: "test-task-789",
        status: "running",
      });
      (pullRequestApi.getCreatePullRequestsStatus as Mock).mockResolvedValue({
        status: "running",
        repos: {},
        results: {},
        prs_created: 0,
      });

      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build.yml", status: "committed_locally" }]}
          reusableWorkflows={[{ name: "shared.yaml", status: "committed_locally" }]}
        />
      );
      fireEvent.click(screen.getByRole("button", { name: /create 2 pr/i }));

      await waitFor(() => {
        expect(screen.getByTestId("pr-creation-progress")).toBeInTheDocument();
      });
      expect(screen.getByText("build.yml")).toBeInTheDocument();
      expect(screen.getByText("shared.yml")).toBeInTheDocument();
      expect(screen.queryByText("build.yml.yml")).not.toBeInTheDocument();
      expect(screen.queryByText("shared.yaml.yml")).not.toBeInTheDocument();
    });

    it("shows partial failure with error message", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });

      (pullRequestApi.createPullRequests as Mock).mockResolvedValue({
        task_id: "test-task-err",
        status: "running",
      });
      (pullRequestApi.getCreatePullRequestsStatus as Mock).mockResolvedValue({
        status: "error",
        repos: {
          "owner/repo-a on main": { step: "Opening PR", status: "error", error: "GitHub returned 422" },
        },
        results: {},
        prs_created: 0,
        error: "Failed to create PRs",
      });

      render(<CreatePRModal {...propsWithWorkflows} />);
      fireEvent.click(screen.getByRole("button", { name: /create 2 pr/i }));

      // Allow the createPullRequests promise to resolve
      await waitFor(() => {
        expect(pullRequestApi.createPullRequests).toHaveBeenCalled();
      });

      // Advance timer to trigger the polling interval
      vi.advanceTimersByTime(1500);

      await waitFor(() => {
        expect(screen.getByText(/failed to create prs/i)).toBeInTheDocument();
      });

      vi.useRealTimers();
    });
  });

  describe("campaign naming", () => {
    it("prefills the name from the selection", () => {
      render(<CreatePRModal {...baseProps} workflows={[{ name: "build", status: "new" }]} />);

      expect(screen.getByLabelText("Campaign name")).toHaveValue("Update build.yml");
    });

    it("summarises the count when several workflows are selected", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[
            { name: "build", status: "new" },
            { name: "deploy", status: "new" },
            { name: "test", status: "new" },
          ]}
        />
      );

      expect(screen.getByLabelText("Campaign name")).toHaveValue("Update build.yml + 2 more");
    });

    it("keeps an edited name when the selection changes afterwards", () => {
      render(
        <CreatePRModal
          {...baseProps}
          workflows={[{ name: "build", status: "new" }, { name: "deploy", status: "new" }]}
        />
      );
      const nameInput = screen.getByLabelText("Campaign name");
      fireEvent.change(nameInput, { target: { value: "Q3 security rollout" } });

      // Deselecting a workflow re-derives the suggestion — it must not win.
      fireEvent.click(screen.getByLabelText(/deploy/i));

      expect(nameInput).toHaveValue("Q3 security rollout");
    });

    it("sends the name and description with the create call", async () => {
      (pullRequestApi.createPullRequests as Mock).mockResolvedValue({ prs_created: 1, results: {} });
      render(<CreatePRModal {...baseProps} workflows={[{ name: "build", status: "new" }]} />);

      fireEvent.change(screen.getByLabelText("Campaign name"), { target: { value: "Q3 security rollout" } });
      fireEvent.change(screen.getByLabelText("Description (optional)"), { target: { value: "Pinning actions." } });
      fireEvent.click(screen.getByRole("button", { name: /create \d+ pr/i }));

      await waitFor(() => expect(pullRequestApi.createPullRequests).toHaveBeenCalled());
      const { campaign } = (pullRequestApi.createPullRequests as Mock).mock.calls[0][2];
      expect(campaign).toEqual({ name: "Q3 security rollout", description: "Pinning actions." });
    });

    it("sends nothing rather than an empty string when the name is cleared", async () => {
      (pullRequestApi.createPullRequests as Mock).mockResolvedValue({ prs_created: 1, results: {} });
      render(<CreatePRModal {...baseProps} workflows={[{ name: "build", status: "new" }]} />);

      fireEvent.change(screen.getByLabelText("Campaign name"), { target: { value: "   " } });
      fireEvent.click(screen.getByRole("button", { name: /create \d+ pr/i }));

      await waitFor(() => expect(pullRequestApi.createPullRequests).toHaveBeenCalled());
      const { campaign } = (pullRequestApi.createPullRequests as Mock).mock.calls[0][2];
      expect(campaign).toEqual({ name: undefined, description: undefined });
    });
  });
});
