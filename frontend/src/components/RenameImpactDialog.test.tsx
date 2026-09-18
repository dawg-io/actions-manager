import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import RenameImpactDialog from "./RenameImpactDialog";
import type { RenameImpact } from "../api/workflows";
import type { RenameImpactItem } from "../hooks/useRenameConfirmation";

const impact = (overrides: Partial<RenameImpact> = {}): RenameImpact => ({
  classification: "delivered",
  blocked_reason: null,
  old_filename: "AM_ACME_ci.yml",
  new_filename: "AM_ACME_ci-v2.yml",
  targets: [],
  consumers: [],
  overrides: [],
  warnings: [],
  ...overrides,
});

/** One renamed workflow, as the confirmation hook hands it over. */
const item = (
  over: Partial<RenameImpact> | null,
  extra: Partial<RenameImpactItem> = {}
): RenameImpactItem => ({
  previousName: "ci",
  newName: "ci-v2",
  isReusable: false,
  impact: over === null ? null : impact(over),
  error: null,
  ...extra,
});

const target = (over: Partial<RenameImpact["targets"][number]> = {}) => ({
  repo: "acme/api",
  branch: "main",
  old_file_present: true,
  new_file_present: false,
  confirmed_present_at: null,
  ...over,
});

const props = { open: true, onConfirm: vi.fn(), onCancel: vi.fn() };

describe("RenameImpactDialog", () => {
  test("names both filenames so the user sees what the delivered path becomes", () => {
    render(<RenameImpactDialog {...props} items={[item({})]} />);

    expect(screen.getByText(/AM_ACME_ci\.yml → AM_ACME_ci-v2\.yml/)).toBeInTheDocument();
  });

  test("lists every repo and branch the old file is left behind in", () => {
    render(
      <RenameImpactDialog
        {...props}
        items={[item({
          targets: [target(), target({ repo: "acme/web", branch: "release/1.x" })],
        })]}
      />
    );

    expect(screen.getByText("acme/api @ main")).toBeInTheDocument();
    expect(screen.getByText("acme/web @ release/1.x")).toBeInTheDocument();
    expect(screen.getByText(/Merging that pull request completes the rename/)).toBeInTheDocument();
  });

  test("a target GitHub could not be checked is shown, not silently dropped", () => {
    // old_file_present null means "we could not ask" — presenting only the
    // confirmed rows would tell the user the list is complete when it is not.
    render(
      <RenameImpactDialog
        {...props}
        items={[item({
          classification: "unknown",
          targets: [target({ old_file_present: null, new_file_present: null })],
        })]}
      />
    );

    expect(screen.getByText(/acme\/api @ main \(could not be checked\)/)).toBeInTheDocument();
    expect(screen.getByTestId("rename-unknown")).toBeInTheDocument();
  });

  test("says plainly when nothing was delivered under the old name", () => {
    render(
      <RenameImpactDialog
        {...props}
        items={[item({
          classification: "never_delivered",
          targets: [target({ old_file_present: false })],
        })]}
      />
    );

    expect(screen.getByTestId("rename-not-delivered")).toBeInTheDocument();
    expect(screen.queryByTestId("rename-targets")).not.toBeInTheDocument();
  });

  test("a blocked rename shows the reason and offers no confirm button", () => {
    render(
      <RenameImpactDialog
        {...props}
        items={[item({
          classification: "blocked",
          blocked_reason: "This workflow is under review. Merge or close its pull request before renaming.",
        })]}
      />
    );

    expect(screen.getByText(/This save cannot be applied/)).toBeInTheDocument();
    expect(screen.getByTestId("rename-blocked-reason")).toHaveTextContent("under review");
    expect(screen.queryByRole("button", { name: "Rename" })).not.toBeInTheDocument();
    // The dialog chrome has its own "Close" control, so target the footer one.
    expect(screen.getByTestId("rename-dismiss")).toHaveTextContent("Close");
  });

  test("lists the caller workflows whose uses: line names the old filename", () => {
    render(
      <RenameImpactDialog
        {...props}
        items={[item({
          consumers: [
            { project_name: "Payments", workflow_name: "deploy", uses_line: "uses: acme/rwx/.github/workflows/AM_ACME_ci.yml@main" },
            { project_name: "Payments", workflow_name: "release", uses_line: "uses: acme/rwx/.github/workflows/AM_ACME_ci.yml@main" },
          ],
        })]}
      />
    );

    expect(screen.getByText(/2 caller workflow\(s\)/)).toBeInTheDocument();
    expect(screen.getByText("Payments — deploy")).toBeInTheDocument();
    expect(screen.getByText("Payments — release")).toBeInTheDocument();
  });

  test("while loading it says so rather than implying an empty impact", () => {
    render(<RenameImpactDialog {...props} items={[]} loading />);

    expect(screen.getByText(/Checking what this rename would affect/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rename" })).toBeDisabled();
  });

  test("a failed check says so and still lets the rename be attempted", () => {
    // A dialog with a title, a disabled button and no body is unreadable: the
    // user cannot tell whether the rename is safe, unsafe, or still loading.
    render(
      <RenameImpactDialog
        {...props}
        items={[item(null, { error: "Request failed with status code 401" })]}
      />
    );

    expect(screen.getByTestId("rename-check-failed")).toHaveTextContent("401");
    expect(screen.getByRole("button", { name: "Rename" })).toBeEnabled();
  });

  test("renders the payload the backend actually sends, field for field", () => {
    // Written out from backend/workflows.py's RenameImpactResponse rather than
    // built with the helper above: the helper is typed from RenameImpact, and
    // when the interface said `override_repos` while the server sent
    // `overrides`, every fixture agreed with the bug. `.length` on the missing
    // array threw during render, which unmounts the whole app.
    //
    // Typed, not cast — if the interface drifts from these names again, this
    // stops compiling as well as failing.
    const wire: RenameImpact = {
      classification: "delivered",
      blocked_reason: null,
      old_filename: "AM_MYP1_okokok.yml",
      new_filename: "AM_MYP1_renamed.yml",
      targets: [{
        repo: "acme/api",
        branch: "main",
        old_file_present: true,
        new_file_present: false,
        confirmed_present_at: null,
      }],
      consumers: [{
        project_name: "Payments",
        workflow_name: "deploy",
        uses_line: "uses: acme/rwx/.github/workflows/AM_MYP1_okokok.yml@main",
      }],
      overrides: ["acme/api"],
      warnings: [],
    };

    render(
      <RenameImpactDialog
        {...props}
        items={[{
          previousName: "okokok",
          newName: "renamed",
          isReusable: false,
          impact: wire,
          error: null,
        }]}
      />
    );

    expect(screen.getByTestId("rename-overrides")).toHaveTextContent("acme/api");
    expect(screen.getByText("acme/api @ main")).toBeInTheDocument();
    expect(screen.getByText("Payments — deploy")).toBeInTheDocument();
  });

  // --- a project save carries every rename at once --------------------------

  test("shows every rename in the save, each under its own heading", () => {
    render(
      <RenameImpactDialog
        {...props}
        items={[
          item({ targets: [target()] }),
          item(
            { old_filename: "AM_ACME_build.yml", new_filename: "AM_ACME_build-v2.yml" },
            { previousName: "build", newName: "build-v2" }
          ),
        ]}
      />
    );

    expect(screen.getByText("2 workflows are renamed by this save.")).toBeInTheDocument();
    expect(screen.getByText("ci → ci-v2")).toBeInTheDocument();
    expect(screen.getByText("build → build-v2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  test("one blocked rename blocks the whole save, not just its own workflow", () => {
    // The save carries them together, so confirming would apply the others and
    // fail this one partway through.
    render(
      <RenameImpactDialog
        {...props}
        items={[
          item({}),
          item(
            { blocked_reason: "This workflow is under review." },
            { previousName: "build", newName: "build-v2" }
          ),
        ]}
      />
    );

    expect(screen.getByText(/This save cannot be applied/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.getByTestId("rename-dismiss")).toHaveTextContent("Close");
  });
});
