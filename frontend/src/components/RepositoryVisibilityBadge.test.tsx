import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import RepositoryVisibilityBadge from "./RepositoryVisibilityBadge";

describe("RepositoryVisibilityBadge", () => {
  it("renders 'Public Repos' for the 'public' scope", () => {
    render(<RepositoryVisibilityBadge visibilityScope="public" />);
    expect(screen.getByText("Public Repos")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Repository visibility: Public Repos"),
    ).toBeInTheDocument();
  });

  it("renders 'Private Repos' for the 'private' scope", () => {
    render(<RepositoryVisibilityBadge visibilityScope="private" />);
    expect(screen.getByText("Private Repos")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Repository visibility: Private Repos"),
    ).toBeInTheDocument();
  });

  it("defaults to 'Public Repos' when scope is missing", () => {
    render(<RepositoryVisibilityBadge />);
    expect(screen.getByText("Public Repos")).toBeInTheDocument();
  });

  it("normalizes case when matching the scope value", () => {
    render(<RepositoryVisibilityBadge visibilityScope={"PRIVATE" as "private"} />);
    expect(screen.getByText("Private Repos")).toBeInTheDocument();
  });

  it("uses the emerald palette for public and slate for private", () => {
    const { rerender } = render(
      <RepositoryVisibilityBadge visibilityScope="public" />,
    );
    const publicBadge = screen.getByLabelText(
      "Repository visibility: Public Repos",
    );
    // emerald-300 text + emerald-500/40 border tokens
    expect(publicBadge).toHaveStyle({ color: "rgb(110, 231, 183)" });
    expect(publicBadge.style.border).toContain("rgba(16, 185, 129, 0.4)");

    rerender(<RepositoryVisibilityBadge visibilityScope="private" />);
    const privateBadge = screen.getByLabelText(
      "Repository visibility: Private Repos",
    );
    // slate-300 text + slate-400/40 border tokens
    expect(privateBadge).toHaveStyle({ color: "rgb(203, 213, 225)" });
    expect(privateBadge.style.border).toContain("rgba(148, 163, 184, 0.4)");
  });
});
