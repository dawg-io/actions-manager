/**
 * The panel must never make a number mean something it doesn't.
 *
 * "No runs" and "everything failed" both look like zero unless they are
 * rendered differently, and a failed sync must flag the numbers as stale rather
 * than hide them. The refresh test is the UI-state regression guard: the new
 * values have to appear from the response itself, with no remount.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import { vi } from "vitest";
import BuildMetricsPanel, { formatDuration } from "./BuildMetricsPanel";
import type { BuildMetricsSummary, RecentRun } from "../api/buildMetrics";

vi.mock("../api/buildMetrics", () => ({
  getProjectBuildMetrics: vi.fn(),
}));

import { getProjectBuildMetrics } from "../api/buildMetrics";

const mockSummary = (overrides: Partial<BuildMetricsSummary> = {}): BuildMetricsSummary => ({
  project_id: 1,
  project_name: "proj",
  window_days: 30,
  last_synced: new Date().toISOString(),
  total_runs: 10,
  decided_runs: 10,
  conclusion_counts: { success: 8, failure: 2 },
  success_rate: 80,
  avg_duration_seconds: 102,
  p50_duration_seconds: 90,
  p95_duration_seconds: 240,
  avg_queue_seconds: 12,
  trend: [
    { date: "2026-08-09", total: 4, success: 4, failure: 0 },
    { date: "2026-08-10", total: 6, success: 4, failure: 2 },
  ],
  selected_workflow: null,
  workflows: [
    {
      workflow_name: "ci",
      workflow_filename: "ci.yml",
      total: 8,
      success_rate: 75,
      avg_duration_seconds: 110,
      actions_url: "https://github.com/acme/api/actions/workflows/ci.yml",
    },
    {
      workflow_name: "release",
      workflow_filename: "release.yml",
      total: 2,
      success_rate: 100,
      avg_duration_seconds: 60,
      actions_url: null,
    },
  ],
  recent_runs: [mockRun()],
  sync_failed: false,
  sync_message: null,
  ...overrides,
});

function mockRun(overrides: Partial<RecentRun> = {}): RecentRun {
  return {
    github_run_id: 4242,
    run_number: 42,
    workflow_name: "ci",
    repo: "acme/api",
    branch: "main",
    event: "push",
    status: "completed",
    conclusion: "failure",
    created_at: new Date().toISOString(),
    duration_seconds: 102,
    html_url: "https://github.com/acme/api/actions/runs/4242",
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(getProjectBuildMetrics).mockReset();
});

describe("BuildMetricsPanel", () => {
  test("renders the headline stats from the API response", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(mockSummary());

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByText("80%")).toBeInTheDocument();
    expect(screen.getByText("10 decided of 10 runs")).toBeInTheDocument();
    expect(screen.getByText("1m 42s")).toBeInTheDocument();
    expect(screen.getByText(/Last 30 days/)).toBeInTheDocument();
  });

  test("refresh updates the rendered numbers in place, without a remount", async () => {
    vi.mocked(getProjectBuildMetrics)
      .mockResolvedValueOnce(mockSummary())
      .mockResolvedValueOnce(mockSummary({ success_rate: 92, total_runs: 25, decided_runs: 25 }));

    render(<BuildMetricsPanel projectId={1} user="alice" />);
    const panel = await screen.findByTestId("build-metrics-panel");
    expect(await screen.findByText("80%")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("build-metrics-refresh"));

    expect(await screen.findByText("92%")).toBeInTheDocument();
    expect(screen.queryByText("80%")).not.toBeInTheDocument();
    // Same DOM node: the panel re-rendered from state, it was not replaced.
    expect(screen.getByTestId("build-metrics-panel")).toBe(panel);
    expect(vi.mocked(getProjectBuildMetrics)).toHaveBeenLastCalledWith(
      1, "alice", { refresh: true, onlyFailures: false, workflow: "" },
    );
  });

  test("an empty project says so instead of reporting a 0% success rate", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(
      mockSummary({ total_runs: 0, decided_runs: 0, success_rate: null, workflows: [] }),
    );

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByTestId("build-metrics-empty")).toHaveTextContent(
      "No runs recorded in the last 30 days.",
    );
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  test("a project with runs but no verdicts shows an unknown rate, not zero", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(
      mockSummary({ success_rate: null, decided_runs: 0, conclusion_counts: { cancelled: 10 } }),
    );

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByText("0 decided of 10 runs")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  test("never synced does not render a relative time", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(mockSummary({ last_synced: null }));

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByText(/not synced yet/)).toBeInTheDocument();
  });

  test("a failed sync warns but still shows the last known numbers", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(
      mockSummary({ sync_failed: true, sync_message: "GitHub API rate limit reached" }),
    );

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByTestId("build-metrics-sync-warning")).toHaveTextContent(
      "GitHub API rate limit reached",
    );
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  test("renders one trend bar per day with an accessible summary", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(mockSummary());

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByTestId("build-metrics-trend")).toHaveAttribute(
      "aria-label",
      "Daily runs over the last 2 days, 80% success",
    );
    expect(screen.getAllByTestId("build-metrics-trend-bar")).toHaveLength(2);
  });

  test("lists the per-workflow breakdown", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(mockSummary());

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByTestId("build-metrics-workflow-row-ci.yml")).toHaveTextContent("ci");
    expect(screen.getByText(/8 runs · 75% · 1m 50s/)).toBeInTheDocument();
  });

  test("a slow request for a previous project cannot overwrite the current one", async () => {
    let resolveSlow: (value: BuildMetricsSummary) => void = () => {};
    vi.mocked(getProjectBuildMetrics)
      .mockReturnValueOnce(new Promise<BuildMetricsSummary>((resolve) => { resolveSlow = resolve; }))
      .mockResolvedValueOnce(mockSummary({ success_rate: 92 }));

    const { rerender } = render(<BuildMetricsPanel projectId={1} user="alice" />);
    rerender(<BuildMetricsPanel projectId={2} user="alice" />);
    expect(await screen.findByText("92%")).toBeInTheDocument();

    resolveSlow(mockSummary({ success_rate: 11 }));

    await waitFor(() => expect(screen.getByText("92%")).toBeInTheDocument());
    expect(screen.queryByText("11%")).not.toBeInTheDocument();
  });

  test("surfaces a load error", async () => {
    vi.mocked(getProjectBuildMetrics).mockRejectedValue(new Error("boom"));

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByText("Could not load build metrics.")).toBeInTheDocument();
  });
});

describe("BuildMetricsPanel links out to GitHub", () => {
  test("each run links to itself on GitHub, in a new tab", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(mockSummary());

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    const link = await screen.findByRole("link", { name: /ci, run 42, acme\/api, main, failure/i });
    expect(link).toHaveAttribute("href", "https://github.com/acme/api/actions/runs/4242");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  test("a run with no stored URL still renders, just not as a link", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(
      mockSummary({ recent_runs: [mockRun({ html_url: null })] }),
    );

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByTestId("build-metrics-run")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /run 42/i })).not.toBeInTheDocument();
  });

  test("the workflow breakdown links to that workflow's Actions page", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(mockSummary());

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByRole("link", { name: /^ci — open in GitHub$/i })).toHaveAttribute(
      "href",
      "https://github.com/acme/api/actions/workflows/ci.yml",
    );
    // release has no actions_url — its row must still render, just without a
    // dead link next to it.
    expect(screen.queryByRole("link", { name: /release/i })).not.toBeInTheDocument();
    expect(screen.getByTestId("build-metrics-workflow-row-release.yml")).toHaveTextContent("release");
  });

  test("the failures toggle refetches server-side and leaves the aggregates alone", async () => {
    vi.mocked(getProjectBuildMetrics)
      .mockResolvedValueOnce(mockSummary())
      .mockResolvedValueOnce(mockSummary({
        recent_runs: [mockRun({ github_run_id: 7, run_number: 7, conclusion: "failure" })],
      }));

    render(<BuildMetricsPanel projectId={1} user="alice" />);
    expect(await screen.findByText("80%")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("build-metrics-failures-toggle"));

    await waitFor(() => expect(vi.mocked(getProjectBuildMetrics)).toHaveBeenLastCalledWith(
      1, "alice", { refresh: undefined, onlyFailures: true, workflow: "" },
    ));
    expect(screen.getByTestId("build-metrics-failures-toggle")).toHaveAttribute("aria-pressed", "true");
    // Filtering the list must not move the headline number.
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  test("says so when the failures filter finds nothing", async () => {
    vi.mocked(getProjectBuildMetrics)
      .mockResolvedValueOnce(mockSummary())
      .mockResolvedValueOnce(mockSummary({ recent_runs: [] }));

    render(<BuildMetricsPanel projectId={1} user="alice" />);
    await screen.findByText("80%");

    await userEvent.click(screen.getByTestId("build-metrics-failures-toggle"));

    expect(await screen.findByTestId("build-metrics-runs-empty")).toHaveTextContent(
      "No failed runs in the last 30 days.",
    );
  });
});

describe("BuildMetricsPanel scoping to one workflow", () => {
  const scopedToCi = () => mockSummary({
    selected_workflow: "ci.yml",
    total_runs: 8,
    decided_runs: 8,
    success_rate: 75,
  });

  test("the dropdown offers every workflow plus the whole project", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(mockSummary());

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    const select = await screen.findByTestId("build-metrics-workflow-filter");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.textContent))
      .toEqual(["All workflows", "ci", "release"]);
  });

  test("choosing a workflow refetches scoped to it", async () => {
    vi.mocked(getProjectBuildMetrics)
      .mockResolvedValueOnce(mockSummary())
      .mockResolvedValueOnce(scopedToCi());

    render(<BuildMetricsPanel projectId={1} user="alice" />);
    await screen.findByText("80%");

    await userEvent.selectOptions(screen.getByTestId("build-metrics-workflow-filter"), "ci.yml");

    await waitFor(() => expect(vi.mocked(getProjectBuildMetrics)).toHaveBeenLastCalledWith(
      1, "alice", { refresh: undefined, onlyFailures: false, workflow: "ci.yml" },
    ));
    expect(await screen.findByText("75%")).toBeInTheDocument();
    // The header must say which workflow the numbers now describe.
    expect(screen.getByText(/Last 30 days · ci ·/)).toBeInTheDocument();
  });

  test("clicking a breakdown row scopes to that workflow", async () => {
    vi.mocked(getProjectBuildMetrics)
      .mockResolvedValueOnce(mockSummary())
      .mockResolvedValueOnce(scopedToCi());

    render(<BuildMetricsPanel projectId={1} user="alice" />);
    await screen.findByText("80%");

    await userEvent.click(await screen.findByTestId("build-metrics-workflow-row-ci.yml"));

    await waitFor(() => expect(vi.mocked(getProjectBuildMetrics)).toHaveBeenLastCalledWith(
      1, "alice", { refresh: undefined, onlyFailures: false, workflow: "ci.yml" },
    ));
  });

  test("the scoped row is marked as current, and clicking it again clears the scope", async () => {
    vi.mocked(getProjectBuildMetrics)
      .mockResolvedValueOnce(scopedToCi())
      .mockResolvedValueOnce(mockSummary());

    render(<BuildMetricsPanel projectId={1} user="alice" />);
    const row = await screen.findByTestId("build-metrics-workflow-row-ci.yml");
    await waitFor(() => expect(row).toHaveAttribute("aria-current", "true"));

    await userEvent.click(row);

    await waitFor(() => expect(vi.mocked(getProjectBuildMetrics)).toHaveBeenLastCalledWith(
      1, "alice", { refresh: undefined, onlyFailures: false, workflow: "" },
    ));
  });

  test("the breakdown stays project-wide while scoped, so you can switch away", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(scopedToCi());

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    // Scoped to ci, but release is still listed and still selectable.
    expect(await screen.findByTestId("build-metrics-workflow-row-release.yml")).toBeInTheDocument();
  });

  test("scoping to a workflow with no runs still leaves a way back", async () => {
    vi.mocked(getProjectBuildMetrics)
      .mockResolvedValueOnce(mockSummary())
      .mockResolvedValueOnce(mockSummary({
        selected_workflow: "release.yml",
        total_runs: 0,
        decided_runs: 0,
        success_rate: null,
        recent_runs: [],
      }));

    render(<BuildMetricsPanel projectId={1} user="alice" />);
    await screen.findByText("80%");

    await userEvent.selectOptions(screen.getByTestId("build-metrics-workflow-filter"), "release.yml");

    expect(await screen.findByTestId("build-metrics-empty")).toHaveTextContent(
      "No runs for release in the last 30 days.",
    );
    // The regression this guards: an empty scope must not hide the switcher.
    expect(screen.getByTestId("build-metrics-workflow-filter")).toBeInTheDocument();
    expect(screen.getByTestId("build-metrics-workflow-row-ci.yml")).toBeInTheDocument();
  });

  test("switching project does not leave the previous project's numbers on screen", async () => {
    let resolveSecond: (value: BuildMetricsSummary) => void = () => {};
    vi.mocked(getProjectBuildMetrics)
      .mockResolvedValueOnce(mockSummary())
      .mockReturnValueOnce(new Promise<BuildMetricsSummary>((r) => { resolveSecond = r; }));

    const { rerender } = render(<BuildMetricsPanel projectId={1} user="alice" />);
    expect(await screen.findByText("80%")).toBeInTheDocument();

    rerender(<BuildMetricsPanel projectId={2} user="alice" />);

    // Project 2's request is still in flight — project 1's figures must be gone.
    await waitFor(() => expect(screen.queryByText("80%")).not.toBeInTheDocument());
    resolveSecond(mockSummary({ success_rate: 55 }));
    expect(await screen.findByText("55%")).toBeInTheDocument();
  });

  test("the header says what the numbers describe", async () => {
    vi.mocked(getProjectBuildMetrics).mockResolvedValue(mockSummary());

    render(<BuildMetricsPanel projectId={1} user="alice" />);

    expect(await screen.findByText(/Last 30 days · all workflows/)).toBeInTheDocument();
  });
});

describe("formatDuration", () => {
  test.each([
    [null, "—"],
    [0, "0s"],
    [45, "45s"],
    [60, "1m"],
    [102, "1m 42s"],
    [3720, "1h 2m"],
  ])("formats %s as %s", (seconds, expected) => {
    expect(formatDuration(seconds as number | null)).toBe(expected);
  });
});
