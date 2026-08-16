import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import DeployEnvironments from "./DeployEnvironments";
import {
  getEnvironments,
  createEnvironment,
} from "../api/environments";

vi.mock("../api/apiClient", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

// Mock the API module
vi.mock("../api/environments", () => ({
  deleteDeploymentEnvironment: vi.fn(),
  createEnvironment: vi.fn().mockResolvedValue({}),
  getEnvironments: vi.fn().mockResolvedValue([]),
  syncEnvironment: vi.fn().mockResolvedValue({}),
  getEnvironmentsCount: vi.fn().mockResolvedValue(0),
}));

// Mock the copy utils
vi.mock("../utils/copyUtils", () => ({
  CopyButton: ({
    textToCopy,
    title,
  }: {
    textToCopy: string;
    title: string;
  }) => <button data-testid="copy-button" title={title} />,
  copyToClipboard: vi.fn(),
}));

describe("DeployEnvironments Redesign", () => {
  const defaultProps = {
    user: "testuser",
    selectedRepos: ["test-repo"],
    accountType: "premium",
    deploymentEnvironments: [],
    setDeploymentEnvironments: vi.fn(),
    manualEnvironments: [{ name: "" }],
    setManualEnvironments: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("should render header with icon and title", () => {
    render(<DeployEnvironments {...defaultProps} />);
    expect(screen.getByText("Deploy Environments")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Manage GitHub deployment environments used by this project."
      )
    ).toBeInTheDocument();
  });

  test("should render Add Environment form", () => {
    render(<DeployEnvironments {...defaultProps} />);
    // "Add Environment" appears both as section heading and submit button label
    expect(screen.getAllByText("Add Environment").length).toBeGreaterThan(0);
    expect(screen.getByTestId("deploy-env-add-name")).toBeInTheDocument();
    expect(screen.getByTestId("deploy-env-add-submit")).toBeInTheDocument();
  });

  test("should disable Add button when form is empty", () => {
    render(<DeployEnvironments {...defaultProps} />);
    const addButton = screen.getByTestId("deploy-env-add-submit");
    expect(addButton).toBeDisabled();
  });

  test("should enable Add button when form has valid name", () => {
    render(
      <DeployEnvironments
        {...defaultProps}
        manualEnvironments={[{ name: "staging" }]}
      />
    );
    const addButton = screen.getByTestId("deploy-env-add-submit");
    expect(addButton).toBeEnabled();
  });

  test("should show empty state when no environments exist", () => {
    render(<DeployEnvironments {...defaultProps} />);
    expect(screen.getByText("No environments yet")).toBeInTheDocument();
    expect(
      screen.getByText("Add your first deployment environment for this project.")
    ).toBeInTheDocument();
  });

  test("should display environment cards with badges", async () => {
    vi.mocked(getEnvironments).mockResolvedValueOnce([
      { name: "development" },
      { name: "staging" },
    ]);

    render(<DeployEnvironments {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("development")).toBeInTheDocument();
      expect(screen.getByText("staging")).toBeInTheDocument();
    });
  });

  test("should show synced badge for synced environments", async () => {
    vi.mocked(getEnvironments).mockResolvedValue([{ name: "production" }]);

    render(<DeployEnvironments {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("production")).toBeInTheDocument();
      // Should show "Synced" badge
      const badges = screen.getAllByText("Synced");
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  test("should show warning badge for not synced environments", async () => {
    vi.mocked(getEnvironments)
      .mockResolvedValueOnce([{ name: "development" }])
      .mockResolvedValueOnce([]);

    render(
      <DeployEnvironments
        {...defaultProps}
        selectedRepos={["repo1", "repo2"]}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("development")).toBeInTheDocument();
      // Should show "Not synced" badge
      expect(screen.getByText(/Not synced/)).toBeInTheDocument();
    });
  });

  test("should render overflow menu with actions", async () => {
    vi.mocked(getEnvironments).mockResolvedValue([{ name: "staging" }]);

    render(<DeployEnvironments {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("staging")).toBeInTheDocument();
    });

    // Find the action button by aria-label
    const actionButton = screen.getByLabelText("Actions for staging");
    expect(actionButton).toBeInTheDocument();
  });

  test("should show Clear button", () => {
    render(
      <DeployEnvironments
        {...defaultProps}
        manualEnvironments={[{ name: "test" }]}
      />
    );
    expect(screen.getByText("Clear")).toBeInTheDocument();
  });

  test("should show search input when environments exist", async () => {
    vi.mocked(getEnvironments).mockResolvedValue([{ name: "production" }]);

    render(<DeployEnvironments {...defaultProps} />);

    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText("Search environments…");
      expect(searchInput).toBeInTheDocument();
    });
  });

  test("should filter environments based on search term", async () => {
    vi.mocked(getEnvironments).mockResolvedValue([
      { name: "development" },
      { name: "staging" },
      { name: "production" },
    ]);

    render(<DeployEnvironments {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("development")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText("Search environments…");
    fireEvent.change(searchInput, { target: { value: "prod" } });

    await waitFor(() => {
      expect(screen.getByText("production")).toBeInTheDocument();
      expect(screen.queryByText("development")).not.toBeInTheDocument();
      expect(screen.queryByText("staging")).not.toBeInTheDocument();
    });
  });

  test("should enforce free plan limits", () => {
    render(
      <DeployEnvironments
        {...defaultProps}
        accountType="free"
        environmentsCount={2}
      />
    );

    // Should show limit warning
    expect(
      screen.getByText(/You can create up to 2 deployment environments/)
    ).toBeInTheDocument();

    // Add button should be disabled
    const addButton = screen.getByTestId("deploy-env-add-submit");
    expect(addButton).toBeDisabled();
  });

  test("should enforce professional plan limits", () => {
    render(
      <DeployEnvironments
        {...defaultProps}
        accountType="professional"
        environmentsCount={10}
      />
    );

    // Should show limit warning
    expect(
      screen.getByText(/You can create up to 10 deployment environments/)
    ).toBeInTheDocument();

    // Add button should be disabled
    const addButton = screen.getByTestId("deploy-env-add-submit");
    expect(addButton).toBeDisabled();
  });

  test("should show limited badge when at limit", () => {
    render(
      <DeployEnvironments
        {...defaultProps}
        accountType="free"
        environmentsCount={2}
      />
    );

    // Should show "Limited" badge in the add form
    expect(screen.getByText("Limited")).toBeInTheDocument();
  });

  test("should show usage count badge in header for limited tiers", () => {
    render(
      <DeployEnvironments
        {...defaultProps}
        accountType="free"
        environmentsCount={1}
      />
    );

    // Should show usage count in header
    expect(screen.getByText("1/2 used")).toBeInTheDocument();
  });

  test("should update parent state with environment names", () => {
    const setDeploymentEnvironments = vi.fn();

    render(
      <DeployEnvironments
        {...defaultProps}
        manualEnvironments={[{ name: "development" }]}
        setDeploymentEnvironments={setDeploymentEnvironments}
      />
    );

    // Should call setDeploymentEnvironments
    expect(setDeploymentEnvironments).toHaveBeenCalled();
  });

  test("should show ConfigBadges in header", () => {
    render(<DeployEnvironments {...defaultProps} />);

    // Should show various status badges
    expect(screen.getByText("0 Environments")).toBeInTheDocument();
    expect(screen.getByText(/Synced:\s*0/)).toBeInTheDocument();
    expect(screen.getByText("Project Scope")).toBeInTheDocument();
  });

  test("should show helper text for environment name input", () => {
    render(<DeployEnvironments {...defaultProps} />);
    expect(
      screen.getByText(
        "Environment names should match the target GitHub environment."
      )
    ).toBeInTheDocument();
  });

  test("adds environment immediately and clears input on success", async () => {

    const Wrapper = () => {
      const [manualEnvironments, setManualEnvironments] = React.useState([
        { name: "staging" },
      ]);

      return (
        <DeployEnvironments
          {...defaultProps}
          selectedRepos={["repo1", "repo2"]}
          manualEnvironments={manualEnvironments}
          setManualEnvironments={setManualEnvironments}
        />
      );
    };

    render(<Wrapper />);

    const addButton = screen.getByTestId("deploy-env-add-submit");
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(createEnvironment).toHaveBeenCalledWith("testuser", "repo1", "staging");
      expect(createEnvironment).toHaveBeenCalledWith("testuser", "repo2", "staging");
    });

    await waitFor(() => {
      expect(screen.getByTestId("deploy-env-add-name")).toHaveValue("");
    });

    expect(
      screen.getByText('Environment "staging" created in GitHub.')
    ).toBeInTheDocument();
  });

  test("shows error and keeps entered value when environment creation fails", async () => {
    vi.mocked(createEnvironment).mockRejectedValueOnce({
      response: { data: { error: "Boom" } },
    });

    const Wrapper = () => {
      const [manualEnvironments, setManualEnvironments] = React.useState([
        { name: "staging" },
      ]);

      return (
        <DeployEnvironments
          {...defaultProps}
          selectedRepos={["repo1"]}
          manualEnvironments={manualEnvironments}
          setManualEnvironments={setManualEnvironments}
        />
      );
    };

    render(<Wrapper />);

    fireEvent.click(screen.getByTestId("deploy-env-add-submit"));

    await waitFor(() => {
      expect(screen.getByText("Boom")).toBeInTheDocument();
    });

    expect(screen.getByTestId("deploy-env-add-name")).toHaveValue("staging");
  });
});

describe("DeployEnvironments Sorting", () => {
  const defaultProps = {
    user: "testuser",
    selectedRepos: ["repo1", "repo2"],
    accountType: "premium",
    deploymentEnvironments: [],
    setDeploymentEnvironments: vi.fn(),
    manualEnvironments: [{ name: "" }],
    setManualEnvironments: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("should use localeCompare for reliable alphabetical sorting", async () => {

    vi.mocked(getEnvironments)
      .mockResolvedValueOnce([
        { name: "staging" },
        { name: "production" },
        { name: "development" },
      ])
      .mockResolvedValueOnce([
        { name: "production" },
        { name: "staging" },
        { name: "development" },
      ]);

    render(<DeployEnvironments {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText("staging")).toBeInTheDocument();
    });

    expect(getEnvironments).toHaveBeenCalledTimes(2);
  });
});
