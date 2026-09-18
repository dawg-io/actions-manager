import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";
import RemovalScopeDialog from "./RemovalScopeDialog";

describe("RemovalScopeDialog", () => {
  const defaultProps = {
    open: true,
    title: 'Remove workflow "ci.yml"?',
    githubLocation: "your project's repositories",
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("offers both scopes and preselects the one that keeps the GitHub copy", () => {
    render(<RemovalScopeDialog {...defaultProps} />);

    expect(screen.getByText('Remove workflow "ci.yml"?')).toBeInTheDocument();
    expect(screen.getByLabelText("Remove from ActionsManager only")).toBeChecked();
    expect(screen.getByLabelText("Delete from ActionsManager and GitHub")).not.toBeChecked();
  });

  test("confirms with the project scope by default", () => {
    render(<RemovalScopeDialog {...defaultProps} />);

    fireEvent.click(screen.getByRole("button", { name: /Remove from ActionsManager/i }));

    expect(defaultProps.onConfirm).toHaveBeenCalledWith("project", "campaign");
  });

  test("confirms with both scopes once the GitHub option is chosen", () => {
    render(<RemovalScopeDialog {...defaultProps} />);

    fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
    fireEvent.click(screen.getByRole("button", { name: /Delete Everywhere/i }));

    expect(defaultProps.onConfirm).toHaveBeenCalledWith("project_and_github", "campaign");
  });

  test("warns before a removal that also deletes from GitHub", () => {
    render(<RemovalScopeDialog {...defaultProps} />);
    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
  });

  test("calls the resource a file unless told otherwise", () => {
    render(<RemovalScopeDialog {...defaultProps} />);

    expect(screen.getByText(/The file stays in your project's repositories/)).toBeInTheDocument();
    expect(screen.getByText(/deletes the file from your project's repositories/)).toBeInTheDocument();
  });

  test("names the resource and what tracking it loses when given both", () => {
    render(
      <RemovalScopeDialog
        {...defaultProps}
        resourceNoun="ruleset"
        projectScopeDetail="it stops checking the repositories"
      />
    );

    expect(
      screen.getByText(
        /The ruleset stays in your project's repositories\. ActionsManager stops tracking it, so it stops checking the repositories\./
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/deletes the ruleset from your project's repositories/)).toBeInTheDocument();
    expect(screen.queryByText(/drift detection/)).not.toBeInTheDocument();
  });

  test("does not offer the GitHub-only scope unless asked", () => {
    // Workflows and custom files would earn a 400: their routes take only
    // 'project' and 'project_and_github'.
    render(<RemovalScopeDialog {...defaultProps} />);

    expect(screen.queryByLabelText("Remove from GitHub only")).not.toBeInTheDocument();
  });

  test("offers all three scopes when the GitHub-only option is enabled", () => {
    render(<RemovalScopeDialog {...defaultProps} offerGitHubOnly />);

    expect(screen.getByLabelText("Remove from ActionsManager only")).toBeChecked();
    expect(screen.getByLabelText("Remove from GitHub only")).toBeInTheDocument();
    expect(screen.getByLabelText("Delete from ActionsManager and GitHub")).toBeInTheDocument();
  });

  test("confirms with the github scope, leaving the other options unselected", () => {
    render(<RemovalScopeDialog {...defaultProps} offerGitHubOnly />);

    fireEvent.click(screen.getByLabelText("Remove from GitHub only"));

    // The first option used to be "anything that is not project_and_github",
    // which lit up for this scope too.
    expect(screen.getByLabelText("Remove from ActionsManager only")).not.toBeChecked();
    expect(screen.getByLabelText("Delete from ActionsManager and GitHub")).not.toBeChecked();
    // Keeping the ActionsManager record does not make the GitHub deletion
    // reversible, so this scope is warned about like the other GitHub one.
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Remove from GitHub/i }));
    expect(defaultProps.onConfirm).toHaveBeenCalledWith("github", "campaign");
  });

  test("warns before a GitHub-only removal, not just the delete-everywhere one", () => {
    render(<RemovalScopeDialog {...defaultProps} offerGitHubOnly />);
    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Remove from GitHub only"));

    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
  });

  test("disables the GitHub-only scope when there is no GitHub copy", () => {
    render(<RemovalScopeDialog {...defaultProps} offerGitHubOnly neverSynced />);

    expect(screen.getByLabelText("Remove from GitHub only")).toBeDisabled();
  });

  test("disables the GitHub option when there is no GitHub copy", () => {
    render(<RemovalScopeDialog {...defaultProps} neverSynced />);

    expect(screen.getByLabelText("Delete from ActionsManager and GitHub")).toBeDisabled();
    expect(screen.getByText(/Nothing in GitHub yet/i)).toBeInTheDocument();
  });

  test("cancel reports nothing to remove", () => {
    render(<RemovalScopeDialog {...defaultProps} />);

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));

    expect(defaultProps.onCancel).toHaveBeenCalled();
    expect(defaultProps.onConfirm).not.toHaveBeenCalled();
  });

  test("the safe option does not claim a GitHub copy exists when none does", () => {
    const { rerender } = render(<RemovalScopeDialog {...defaultProps} />);
    expect(screen.getByText(/The file stays in your project's repositories/)).toBeInTheDocument();

    rerender(<RemovalScopeDialog {...defaultProps} neverSynced />);

    // Otherwise the preselected option promises the file stays in GitHub while
    // the disabled one says nothing is there.
    expect(screen.queryByText(/The file stays in/)).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing was ever delivered/)).toBeInTheDocument();
  });

  test("a caller whose GitHub delete is reversible can replace the warning", () => {
    render(
      <RemovalScopeDialog
        {...defaultProps}
        githubScopeWarning="The file is removed on the next delivery. You can Restore it until then."
      />
    );

    fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

    expect(screen.getByText(/You can Restore it until then/)).toBeInTheDocument();
    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument();
  });

  test("reopening resets to the safe option after a GitHub-scoped removal", () => {
    const { rerender } = render(<RemovalScopeDialog {...defaultProps} />);
    fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

    rerender(<RemovalScopeDialog {...defaultProps} open={false} />);
    rerender(<RemovalScopeDialog {...defaultProps} open={true} />);

    expect(screen.getByLabelText("Remove from ActionsManager only")).toBeChecked();
  });
  describe("delivery choice", () => {
    const withDelivery = { ...defaultProps, offerDelivery: true };

    test("is not offered unless the caller asks for it", () => {
      render(<RemovalScopeDialog {...defaultProps} />);
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

      expect(screen.queryByLabelText("Create a PR Campaign")).not.toBeInTheDocument();
    });

    test("stays hidden while the removal does not reach GitHub", () => {
      render(<RemovalScopeDialog {...withDelivery} />);

      expect(screen.queryByLabelText("Create a PR Campaign")).not.toBeInTheDocument();
    });

    test("appears with the reviewable option preselected", () => {
      render(<RemovalScopeDialog {...withDelivery} />);
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

      expect(screen.getByLabelText("Create a PR Campaign")).toBeChecked();
      expect(screen.getByLabelText("Commit directly to the target branch")).not.toBeChecked();
    });

    test("confirms with the chosen delivery", () => {
      render(<RemovalScopeDialog {...withDelivery} />);
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
      fireEvent.click(screen.getByLabelText("Commit directly to the target branch"));
      fireEvent.click(screen.getByRole("button", { name: /Delete Everywhere/i }));

      expect(withDelivery.onConfirm).toHaveBeenCalledWith("project_and_github", "direct");
    });

    test("only warns that the deletion is permanent when it actually is", () => {
      render(<RemovalScopeDialog {...withDelivery} />);
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

      // A PR can be closed and the file restored, so "cannot be undone" would be a lie.
      // Both the delivery option and the amber warning say it.
      expect(screen.getAllByText(/you can Restore it here until then/).length).toBeGreaterThan(0);
      expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument();

      fireEvent.click(screen.getByLabelText("Commit directly to the target branch"));

      expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
    });

    test("says how the removal is undone when it is not a Restore button", () => {
      // Workflows have no Restore. Naming one would point the user at something
      // that does not exist, so the consumer supplies the wording that is true
      // for it and the dialog must use that instead of its custom-file default.
      render(
        <RemovalScopeDialog
          {...withDelivery}
          campaignReversal="closing that pull request cancels the removal"
        />,
      );
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

      expect(
        screen.getAllByText(/closing that pull request cancels the removal/).length,
      ).toBeGreaterThan(0);
      expect(screen.queryByText(/Restore/)).not.toBeInTheDocument();
    });

    test("reopening resets the delivery choice too", () => {
      const { rerender } = render(<RemovalScopeDialog {...withDelivery} />);
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
      fireEvent.click(screen.getByLabelText("Commit directly to the target branch"));

      rerender(<RemovalScopeDialog {...withDelivery} open={false} />);
      rerender(<RemovalScopeDialog {...withDelivery} open={true} />);
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));

      expect(screen.getByLabelText("Create a PR Campaign")).toBeChecked();
    });

    test("scope and delivery are independent radio groups", () => {
      render(<RemovalScopeDialog {...withDelivery} />);
      fireEvent.click(screen.getByLabelText("Delete from ActionsManager and GitHub"));
      fireEvent.click(screen.getByLabelText("Commit directly to the target branch"));

      // A shared group name would have let the delivery radio clear the scope.
      expect(screen.getByLabelText("Delete from ActionsManager and GitHub")).toBeChecked();
    });
  });
  describe("a GitHub copy this project may not delete", () => {
    const REASON =
      "This reusable workflow lives in its Reusable Workflow Project's repository, not this project's.";

    test("disables the GitHub option and gives the reason", () => {
      render(<RemovalScopeDialog {...defaultProps} githubScopeDisabledReason={REASON} />);

      expect(screen.getByLabelText("Delete from ActionsManager and GitHub")).toBeDisabled();
      expect(screen.getByText(/Reusable Workflow Project/)).toBeInTheDocument();
    });

    test("does not claim nothing was ever delivered", () => {
      render(<RemovalScopeDialog {...defaultProps} githubScopeDisabledReason={REASON} />);

      // The file IS in GitHub — it just belongs to another project.
      expect(screen.queryByText(/Nothing in GitHub yet/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Nothing was ever delivered/)).not.toBeInTheDocument();
      expect(screen.getByText(/The file stays in/)).toBeInTheDocument();
    });

    test("confirming can only remove it from ActionsManager", () => {
      render(<RemovalScopeDialog {...defaultProps} githubScopeDisabledReason={REASON} />);

      fireEvent.click(screen.getByRole("button", { name: /Remove from ActionsManager/i }));

      expect(defaultProps.onConfirm).toHaveBeenCalledWith("project", "campaign");
    });
  });
});
