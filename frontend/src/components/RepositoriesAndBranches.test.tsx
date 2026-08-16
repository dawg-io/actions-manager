import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import RepositoriesAndBranches from "./RepositoriesAndBranches";
import { fetchRepos } from "../api/repos";

import type { Mock } from 'vitest';
// Mock the API
vi.mock("../api/repos", () => ({
  fetchRepos: vi.fn(),
}));

// Mock child components to isolate tests
vi.mock("./RepoBranchOverridesPanel", () => ({
  default: function MockRepoBranchOverridesPanel() {
    return <div data-testid="repo-branch-overrides-panel">Overrides Panel</div>;
  },
}));

vi.mock("./RepositoryBranchSelector", () => ({
  default: function MockRepositoryBranchSelector({
    availableRepositories,
    visibilityScope,
  }: any) {
    return (
      <div data-testid="repository-branch-selector">
        <div data-testid="visibility-scope">{visibilityScope || "none"}</div>
        <div data-testid="available-repos-count">
          {availableRepositories.length}
        </div>
        {availableRepositories.map((repo: any) => (
          <div key={repo.id} data-testid={`available-repo-${repo.full_name}`}>
            {repo.full_name}
          </div>
        ))}
      </div>
    );
  },
}));

describe("RepositoriesAndBranches", () => {
  const mockSetRepos = vi.fn();
  const mockSetSelectedRepos = vi.fn();
  const mockSetRegexPattern = vi.fn();
  const mockSetBranchOption = vi.fn();
  const mockSetBranchMaxAgeDays = vi.fn();

  const defaultProps = {
    user: "testuser",
    repos: [],
    setRepos: mockSetRepos,
    selectedRepos: [],
    setSelectedRepos: mockSetSelectedRepos,
    setRegexPattern: mockSetRegexPattern,
    regexPattern: "",
    branchOption: "default" as const,
    setBranchOption: mockSetBranchOption,
    branchMaxAgeDays: 30,
    setBranchMaxAgeDays: mockSetBranchMaxAgeDays,
    projectId: 1,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (fetchRepos as Mock).mockResolvedValue([]);
  });

  describe("Visibility Scope Filtering", () => {
    it("filters to show only public repos when visibilityScope is public", async () => {
      const mockRepos = [
        {
          id: 1,
          name: "pub1",
          full_name: "org/pub1",
          private: false,
          owner: "org",
          owner_type: "Organization",
        },
        {
          id: 2,
          name: "priv1",
          full_name: "org/priv1",
          private: true,
          owner: "org",
          owner_type: "Organization",
        },
        {
          id: 3,
          name: "pub2",
          full_name: "org/pub2",
          private: false,
          owner: "org",
          owner_type: "Organization",
        },
      ];

      render(
        <RepositoriesAndBranches
          {...defaultProps}
          repos={mockRepos}
          visibilityScope="public"
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId("visibility-scope")).toHaveTextContent(
          "public"
        );
      });

      // Should show only 2 public repos
      expect(screen.getByTestId("available-repos-count")).toHaveTextContent(
        "2"
      );
      expect(screen.getByTestId("available-repo-org/pub1")).toBeInTheDocument();
      expect(screen.getByTestId("available-repo-org/pub2")).toBeInTheDocument();
      expect(
        screen.queryByTestId("available-repo-org/priv1")
      ).not.toBeInTheDocument();
    });

    it("filters to show only private repos when visibilityScope is private", async () => {
      const mockRepos = [
        {
          id: 1,
          name: "pub1",
          full_name: "org/pub1",
          private: false,
          owner: "org",
          owner_type: "Organization",
        },
        {
          id: 2,
          name: "priv1",
          full_name: "org/priv1",
          private: true,
          owner: "org",
          owner_type: "Organization",
        },
        {
          id: 3,
          name: "priv2",
          full_name: "org/priv2",
          private: true,
          owner: "org",
          owner_type: "Organization",
        },
      ];

      render(
        <RepositoriesAndBranches
          {...defaultProps}
          repos={mockRepos}
          visibilityScope="private"
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId("visibility-scope")).toHaveTextContent(
          "private"
        );
      });

      // Should show only 2 private repos
      expect(screen.getByTestId("available-repos-count")).toHaveTextContent(
        "2"
      );
      expect(
        screen.getByTestId("available-repo-org/priv1")
      ).toBeInTheDocument();
      expect(
        screen.getByTestId("available-repo-org/priv2")
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId("available-repo-org/pub1")
      ).not.toBeInTheDocument();
    });

    it("defaults to public scope when visibilityScope prop is not provided", async () => {
      const mockRepos = [
        {
          id: 1,
          name: "pub1",
          full_name: "org/pub1",
          private: false,
          owner: "org",
          owner_type: "Organization",
        },
        {
          id: 2,
          name: "priv1",
          full_name: "org/priv1",
          private: true,
          owner: "org",
          owner_type: "Organization",
        },
      ];

      render(<RepositoriesAndBranches {...defaultProps} repos={mockRepos} />);

      await waitFor(() => {
        expect(screen.getByTestId("visibility-scope")).toHaveTextContent(
          "public"
        );
      });

      // Should show only public repos by default
      expect(screen.getByTestId("available-repos-count")).toHaveTextContent(
        "1"
      );
      expect(screen.getByTestId("available-repo-org/pub1")).toBeInTheDocument();
      expect(
        screen.queryByTestId("available-repo-org/priv1")
      ).not.toBeInTheDocument();
    });

    it("handles repositories with mixed organization and personal ownership", async () => {
      const mockRepos = [
        {
          id: 1,
          name: "pub-org",
          full_name: "my-org/pub-org",
          private: false,
          owner: "my-org",
          owner_type: "Organization",
        },
        {
          id: 2,
          name: "pub-user",
          full_name: "johndoe/pub-user",
          private: false,
          owner: "johndoe",
          owner_type: "User",
        },
        {
          id: 3,
          name: "priv-org",
          full_name: "my-org/priv-org",
          private: true,
          owner: "my-org",
          owner_type: "Organization",
        },
        {
          id: 4,
          name: "priv-user",
          full_name: "johndoe/priv-user",
          private: true,
          owner: "johndoe",
          owner_type: "User",
        },
      ];

      render(
        <RepositoriesAndBranches
          {...defaultProps}
          repos={mockRepos}
          visibilityScope="public"
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId("visibility-scope")).toHaveTextContent(
          "public"
        );
      });

      // Should show both public org and public user repos
      expect(screen.getByTestId("available-repos-count")).toHaveTextContent(
        "2"
      );
      expect(
        screen.getByTestId("available-repo-my-org/pub-org")
      ).toBeInTheDocument();
      expect(
        screen.getByTestId("available-repo-johndoe/pub-user")
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId("available-repo-my-org/priv-org")
      ).not.toBeInTheDocument();
      expect(
        screen.queryByTestId("available-repo-johndoe/priv-user")
      ).not.toBeInTheDocument();
    });

    it("renders validation repository separately from target repositories", async () => {
      const mockSetValidationRepo = vi.fn();
      const mockSetPreflightRequired = vi.fn();
      const mockRepos = [
        { id: 1, name: "target", full_name: "org/target", private: false },
        { id: 2, name: "validation", full_name: "org/validation", private: false },
      ];

      render(
        <RepositoriesAndBranches
          {...defaultProps}
          repos={mockRepos}
          validationRepo="org/validation"
          setValidationRepo={mockSetValidationRepo}
          preflightRequired={false}
          setPreflightRequired={mockSetPreflightRequired}
        />
      );

      expect(screen.getByText("Target Repositories")).toBeInTheDocument();
      expect(screen.getByText("Validation Repository")).toBeInTheDocument();
      expect(screen.getByLabelText("Validation Repository")).toHaveValue("org/validation");

      fireEvent.change(screen.getByLabelText("Validation Repository"), {
        target: { value: "org/target" },
      });
      expect(mockSetValidationRepo).toHaveBeenCalledWith("org/target");

      fireEvent.click(screen.getByLabelText(/Require successful preflight/i));
      expect(mockSetPreflightRequired).toHaveBeenCalledWith(true);
    });

    it("filters correctly when all repos are private and scope is public", async () => {
      const mockRepos = [
        {
          id: 1,
          name: "priv1",
          full_name: "org/priv1",
          private: true,
          owner: "org",
          owner_type: "Organization",
        },
        {
          id: 2,
          name: "priv2",
          full_name: "org/priv2",
          private: true,
          owner: "org",
          owner_type: "Organization",
        },
      ];

      render(
        <RepositoriesAndBranches
          {...defaultProps}
          repos={mockRepos}
          visibilityScope="public"
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId("visibility-scope")).toHaveTextContent(
          "public"
        );
      });

      // Should show 0 repos since all are private
      expect(screen.getByTestId("available-repos-count")).toHaveTextContent(
        "0"
      );
    });

    it("filters correctly when all repos are public and scope is private", async () => {
      const mockRepos = [
        {
          id: 1,
          name: "pub1",
          full_name: "org/pub1",
          private: false,
          owner: "org",
          owner_type: "Organization",
        },
        {
          id: 2,
          name: "pub2",
          full_name: "org/pub2",
          private: false,
          owner: "org",
          owner_type: "Organization",
        },
      ];

      render(
        <RepositoriesAndBranches
          {...defaultProps}
          repos={mockRepos}
          visibilityScope="private"
        />
      );

      await waitFor(() => {
        expect(screen.getByTestId("visibility-scope")).toHaveTextContent(
          "private"
        );
      });

      // Should show 0 repos since all are public
      expect(screen.getByTestId("available-repos-count")).toHaveTextContent(
        "0"
      );
    });
  });
});
