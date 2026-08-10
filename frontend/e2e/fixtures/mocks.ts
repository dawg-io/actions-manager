/**
 * Shared Playwright route mocks for Actions Manager E2E tests.
 *
 * These helpers register `page.route(...)` handlers so the React app can be
 * driven against a fully mocked backend. Phase 1 and Phase 2 tests do not
 * depend on the real FastAPI service, the GitHub API, or live network access —
 * every outbound request goes through one of the handlers below.
 *
 * Route handlers use URL predicate functions (not substring regexes) so that
 * Vite source module requests like /src/api/drift.ts are never accidentally
 * intercepted. The apiPath() helper enforces this: it only matches when the
 * URL pathname starts with "/api/", which Vite-served source files never do.
 */
import { Page, Route } from "@playwright/test";

// ---- Test data ---------------------------------------------------------------

export const TEST_USER = "octocat";

// Keep mock project codes short and readable for E2E fixtures while still
// being long enough to stay unique across the small number of projects each
// test uses.
const MOCK_PROJECT_CODE_MAX_LENGTH = 6;

export const TEST_USER_DETAILS = {
  username: TEST_USER,
  github_user: TEST_USER,
  avatar_url: `https://github.com/${TEST_USER}.png`,
  account_type: "Free",
  github_account_type: "User",
  workspace_role: "admin",
};

export const TEST_PERMISSIONS_VALID = {
  status: "valid",
  valid: true,
  missing_scopes: [],
  granted_scopes: ["repo", "workflow", "read:org"],
  issues: [],
  warnings: [],
  recommendations: [],
  message: "All required permissions granted.",
};

// ---- Phase 2 predictable test data -------------------------------------------

/** Predictable repos used across Phase 2 tests. */
export const PHASE2_REPOS = {
  SERVICE_A: "test-org/service-a",
  SERVICE_B: "test-org/service-b",
  REUSABLE_WORKFLOWS: "test-org/reusable-workflows",
};

/** Predictable workflow filenames used across Phase 2 tests. */
export const PHASE2_WORKFLOWS = {
  CI: "ci.yml",
  REUSABLE_BUILD: "reusable-build.yml",
  CALLER_BUILD: "caller-build.yml",
};

/** Build a workflow stub suitable for use in project.workflows arrays. */
export function makeWorkflow(overrides: Partial<{
  name: string;
  content: string;
  isReusable: boolean;
  workflowStatus: string;
  lastModifiedBy: string;
}> = {}) {
  return {
    name: PHASE2_WORKFLOWS.CI,
    content: "name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n",
    isReusable: false,
    workflowStatus: "committed_locally",
    lastModifiedBy: TEST_USER,
    ...overrides,
  };
}

export interface ProjectStub {
  project_id: number;
  project_name: string;
  project_code: string;
  github_user: string;
  pr_state?: "new" | "draft" | "open" | "synced";
  project_type?: "standard" | "rwx";
  repository_visibility_scope?: "public" | "private";
  selected_repos?: string[];
  workflows?: any[];
  rxworkflows?: any[];
  use_prefix?: boolean;
  reusable_workflows_enabled?: boolean;
  updated_at?: string;
  created_at?: string;
  last_modified_by?: string;
  linked_reusable_workflows?: any[];
  project_color?: string;
  /**
   * Workflow names with drift persisted by the last check (issue #1793), as
   * returned by GET /api/projects/{name}. Seeds the drift banner on first
   * paint, before the live check resolves.
   */
  drifted_workflow_names?: string[];
}

export function makeProject(overrides: Partial<ProjectStub> = {}): ProjectStub {
  return {
    project_id: 1,
    project_name: "demo-project",
    project_code: "DEMO",
    github_user: TEST_USER,
    pr_state: "new",
    project_type: "standard",
    repository_visibility_scope: "public",
    selected_repos: ["octocat/hello-world"],
    workflows: [],
    rxworkflows: [],
    use_prefix: false,
    reusable_workflows_enabled: false,
    updated_at: "2025-01-01T00:00:00Z",
    created_at: "2025-01-01T00:00:00Z",
    last_modified_by: TEST_USER,
    linked_reusable_workflows: [],
    ...overrides,
  };
}

export const SAMPLE_WORKFLOW = {
  name: "ci.yml",
  content: "name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n",
  isReusable: false,
  workflowStatus: "saved",
};

// ---- Managed Actions (Actions Projects) test data ----------------------------

export interface ActionInputStub {
  name: string;
  description: string | null;
  required: boolean;
  default: string | null;
  type: "string" | "number" | "boolean" | "choice";
  options: string[] | null;
}

export interface ActionsProjectStub {
  actions_project_id: number;
  name: string;
  description: string | null;
  source_url: string;
  owner: string;
  repo: string;
  ref: string;
  yaml_path: string;
  inputs: ActionInputStub[];
  branding_icon: string | null;
  branding_color: string | null;
}

export function makeActionsProject(overrides: Partial<ActionsProjectStub> = {}): ActionsProjectStub {
  return {
    actions_project_id: 1,
    name: "Checkout",
    description: "Checkout a repo",
    source_url: "https://github.com/actions/checkout",
    owner: "actions",
    repo: "checkout",
    ref: "v4",
    yaml_path: "action.yml",
    inputs: [
      { name: "token", description: "GH token", required: false, default: null, type: "string", options: null },
    ],
    branding_icon: "zap",
    branding_color: "blue",
    ...overrides,
  };
}

/** Preview response returned by `GET /api/actions-projects/preview`, keyed off the pasted URL. */
export const SAMPLE_ACTIONS_PREVIEW = {
  name: "Checkout",
  description: "Checkout a repo",
  owner: "actions",
  repo: "checkout",
  ref: "v4",
  yaml_path: "action.yml",
  source_url: "https://github.com/actions/checkout",
  inputs: [
    { name: "token", description: "GH token", required: false, default: null, type: "string" as const, options: null },
  ],
  branding_icon: "zap",
  branding_color: "blue",
};

// ---- Mock state container ---------------------------------------------------

/**
 * Mutable state used by the route handlers. Tests update this object between
 * actions to simulate state transitions (e.g. project list pr_state changing
 * from `draft` to `open` after a PR is created).
 */
export interface MockState {
  projects: ProjectStub[];
  prStatus: {
    project_state: string;
    pull_requests: any[];
    total_prs: number;
    open_prs: number;
    merged_prs: number;
    closed_prs: number;
  };
  actionsProjects: ActionsProjectStub[];
  actionGroups: { action_group_id: number; name: string; description: string | null; actions_project_ids: number[] }[];
  actionsProjectPreview: typeof SAMPLE_ACTIONS_PREVIEW;
  failNextSave?: boolean;
  failProjectsList?: boolean;
}

export function createMockState(initial: Partial<MockState> = {}): MockState {
  return {
    projects: initial.projects ?? [],
    prStatus: initial.prStatus ?? {
      project_state: "new",
      pull_requests: [],
      total_prs: 0,
      open_prs: 0,
      merged_prs: 0,
      closed_prs: 0,
    },
    actionsProjects: initial.actionsProjects ?? [],
    actionGroups: initial.actionGroups ?? [],
    actionsProjectPreview: initial.actionsProjectPreview ?? SAMPLE_ACTIONS_PREVIEW,
    failNextSave: initial.failNextSave ?? false,
    failProjectsList: initial.failProjectsList ?? false,
  };
}

// ---- Helpers ----------------------------------------------------------------

export function corsHeaders(route: Route): Record<string, string> {
  // Credentialed requests (credentials: "include" / withCredentials: true)
  // require the response to reflect the exact request Origin rather than "*".
  const origin =
    route.request().headers()["origin"] ?? "http://localhost:3000";
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,PATCH,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };
}

function jsonResponse(route: Route, body: unknown, status = 200): Promise<void> {
  // Short-circuit CORS preflight so cross-origin POST/PUT calls from the
  // React dev server (http://localhost:3000) to the mocked backend
  // (http://localhost:8000) succeed without a real server on the other side.
  const headers = corsHeaders(route);
  if (route.request().method() === "OPTIONS") {
    return route.fulfill({ status: 204, headers, body: "" });
  }
  return route.fulfill({
    status,
    contentType: "application/json",
    headers,
    body: JSON.stringify(body),
  });
}

/**
 * Returns a Playwright URL predicate that only matches real backend API paths.
 *
 * Vite serves frontend source modules at paths like /src/api/drift.ts. When
 * the browser fetches those as ESM scripts, a broad regex such as /\/api\/drift/
 * would intercept them and return application/json — which the browser rejects
 * with a MIME type error, leaving the app partially mounted.
 *
 * This helper avoids the collision by requiring url.pathname to start with
 * "/api/". Source files served by Vite always start with "/src/" or "/@" and
 * are therefore never matched.
 *
 * @param match  Receives url.pathname and returns true when this handler
 *               should own the request.
 */
function apiPath(match: (pathname: string) => boolean): (url: URL) => boolean {
  return (url: URL) => url.pathname.startsWith("/api/") && match(url.pathname);
}

function campaignStatus(open: number, merged: number, closed: number): string {
  if (open > 0) return "open";
  if (merged > 0 && closed === 0) return "completed";
  if (merged > 0 && closed > 0) return "partially_completed";
  if (closed > 0) return "cancelled";
  return "open";
}

function buildCampaignsResponse(state: MockState) {
  const prs = state.prStatus.pull_requests.map((pr, index) => ({
    pr_id: index + 1,
    repo_name: pr.repo_name,
    pr_number: pr.pr_number,
    pr_url: pr.pr_url,
    pr_state: pr.pr_state,
    branch_name: pr.branch_name,
    target_branch: pr.target_branch,
    title: pr.title ?? `PR #${pr.pr_number}`,
    author: pr.author ?? TEST_USER,
    actor: pr.author ?? TEST_USER,
    body: pr.body ?? null,
    workflow_names: pr.workflow_names ?? PHASE2_WORKFLOWS.CI,
    created_at: pr.created_at,
    updated_at: pr.updated_at,
    merged_at: pr.merged_at ?? null,
    closed_at: pr.closed_at ?? null,
    source_project_name: null,
  }));
  const open = prs.filter((pr) => pr.pr_state === "open").length;
  const merged = prs.filter((pr) => pr.pr_state === "merged").length;
  const closed = prs.filter((pr) => pr.pr_state === "closed").length;
  const total = prs.length;
  const project = state.projects[0];
  const status = campaignStatus(open, merged, closed);
  const campaigns = total === 0 ? [] : [{
    campaign_id: "campaign-e2e",
    campaign_name: prs[0]?.title ?? "Update ci.yml",
    campaign_status: status,
    project_name: project?.project_name ?? "demo-project",
    project_code: project?.project_code ?? "DEMO",
    created_by: prs[0]?.author ?? TEST_USER,
    created_at: prs[0]?.created_at ?? "2025-01-02T00:00:00Z",
    updated_at: prs[0]?.updated_at ?? "2025-01-02T00:00:00Z",
    completed_at: status === "open" ? null : "2025-01-02T00:00:00Z",
    target_branches: Array.from(new Set(prs.map((pr) => pr.target_branch))),
    workflow_names: [prs[0]?.workflow_names ?? PHASE2_WORKFLOWS.CI],
    repositories: Array.from(new Set(prs.map((pr) => pr.repo_name))),
    open_count: open,
    merged_count: merged,
    closed_count: closed,
    failed_count: 0,
    completion_percentage: total ? Math.round(((merged + closed) / total) * 100) : 0,
    pull_requests: prs,
  }];
  return {
    campaigns,
    pull_requests: prs,
    total_campaigns: campaigns.length,
    active_campaigns: campaigns.filter((campaign) => campaign.campaign_status === "open").length,
    completed_campaigns: campaigns.filter((campaign) => campaign.campaign_status !== "open").length,
    open_prs: open,
    merged_prs: merged,
    closed_prs: closed,
    repositories_affected: new Set(prs.map((pr) => pr.repo_name)).size,
  };
}

/**
 * Establish a logged-in session before navigation by seeding localStorage.
 * The frontend treats `localStorage.github_user` as the source of truth for
 * the current user.
 */
export async function seedAuthenticatedSession(page: Page, user: string = TEST_USER): Promise<void> {
  await page.addInitScript((u) => {
    try {
      globalThis.localStorage.setItem("github_user", u);
    } catch {
      /* ignore */
    }
  }, user);
}

/**
 * Register catch-all route handlers for every backend endpoint Phase 1 & 2
 * tests touch. Returns the (mutable) state object so tests can mutate it.
 *
 * **Route-override ordering (IMPORTANT)**:
 * Playwright evaluates routes in Last-In-First-Out (LIFO) order — the most
 * recently registered handler runs first. To override a specific endpoint
 * (e.g. `mockDriftResponse`, `mockResolveDrift`, `mockCreatePullRequests`),
 * call `installApiMocks` FIRST, then register the override. That way the
 * override handler wins because it was registered later.
 *
 * ✅ Correct order:
 *   await installApiMocks(page, state);
 *   await mockDriftResponse(page, { ... });   // override — registered last, runs first
 *
 * ❌ Wrong order:
 *   await mockDriftResponse(page, { ... });   // registered first, runs last (overridden by installApiMocks)
 *   await installApiMocks(page, state);
 */
export async function installApiMocks(
  page: Page,
  state: MockState = createMockState(),
): Promise<MockState> {
  // User details + permissions (called on App mount)
  await page.route(
    apiPath((p) => /^\/api\/user\/[^/]+\/permissions$/.test(p)),
    (route) => jsonResponse(route, TEST_PERMISSIONS_VALID),
  );
  await page.route(
    apiPath((p) => /^\/api\/user\/[^/]+$/.test(p)),
    (route) => jsonResponse(route, TEST_USER_DETAILS),
  );

  // Project list
  await page.route(
    apiPath((p) => p === "/api/projects" || p === "/api/projects/"),
    async (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }
      if (method === "GET") {
        if (state.failProjectsList) {
          return jsonResponse(route, { detail: "boom" }, 500);
        }
        return jsonResponse(route, state.projects);
      }
      if (method === "POST") {
        if (state.failNextSave) {
          state.failNextSave = false;
          return jsonResponse(route, { detail: "Save failed" }, 500);
        }
        const payload = JSON.parse(route.request().postData() || "{}");
        const created = makeProject({
          project_id: state.projects.length + 1,
          project_name: payload.project_name,
          project_code: (payload.custom_project_key || payload.project_name || "PROJ").toUpperCase().slice(0, MOCK_PROJECT_CODE_MAX_LENGTH),
          project_type: payload.project_type ?? "standard",
          repository_visibility_scope: payload.repository_visibility_scope ?? "public",
          selected_repos: payload.selected_repos ?? [],
          pr_state: "new",
        });
        state.projects.push(created);
        return jsonResponse(route, {
          project_code: created.project_code,
          project_id: String(created.project_id),
          message: "ok",
          pr_state: "new",
        });
      }
      return route.continue();
    },
  );

  // Single-project load (GET /api/projects/{name})
  await page.route(
    apiPath((p) => /^\/api\/projects\/[^/]+(\/)?$/.test(p)),
    async (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }
      const url = new URL(route.request().url());
      const segments = url.pathname.split("/").filter(Boolean);
      // ['api','projects','<name>'] -> last is name
      const name = decodeURIComponent(segments.at(-1));
      if (method === "GET") {
        const project = state.projects.find((p) => p.project_name === name);
        if (!project) {
          return jsonResponse(route, { detail: "not found" }, 404);
        }
        return jsonResponse(route, project);
      }
      if (method === "PUT") {
        // Workflow save: flip state to draft
        const payload = JSON.parse(route.request().postData() || "{}");
        const project = state.projects.find((p) => p.project_name === name);
        if (project) {
          project.pr_state = "draft";
          if (Array.isArray(payload.workflows)) {
            project.workflows = payload.workflows;
          }
          state.prStatus.project_state = "draft";
        }
        return jsonResponse(route, {
          project_code: project?.project_code ?? "DEMO",
          project_id: String(project?.project_id ?? 1),
          message: "ok",
          pr_state: "draft",
        });
      }
      if (method === "DELETE") {
        state.projects = state.projects.filter((p) => p.project_name !== name);
        return jsonResponse(route, { ok: true });
      }
      return route.continue();
    },
  );

  // Project PR status
  await page.route(
    apiPath((p) => p === "/api/project-pr-status"),
    (route) => jsonResponse(route, state.prStatus),
  );
  await page.route(
    apiPath((p) => p === "/api/project-pr-campaigns"),
    (route) => jsonResponse(route, buildCampaignsResponse(state)),
  );
  await page.route(
    apiPath((p) => p === "/api/project-pr-history"),
    (route) => jsonResponse(route, { history: [] }),
  );

  // Create / merge / close PRs
  await page.route(
    apiPath((p) => p.startsWith("/api/create-pull-requests")),
    (route) => {
      state.prStatus.project_state = "open";
      state.prStatus.open_prs = 1;
      state.prStatus.total_prs = 1;
      state.prStatus.pull_requests = [
        {
          repo_name: "octocat/hello-world",
          pr_number: 42,
          pr_url: "https://github.com/octocat/hello-world/pull/42",
          pr_state: "open",
          branch_name: "actions-manager/demo",
          target_branch: "main",
          created_at: "2025-01-02T00:00:00Z",
          updated_at: "2025-01-02T00:00:00Z",
        },
      ];
      state.projects.forEach((p) => {
        p.pr_state = "open";
      });
      return jsonResponse(route, { message: "ok", results: {}, prs_created: 1 });
    },
  );
  await page.route(
    apiPath((p) => p.startsWith("/api/merge-pull-request")),
    (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }
      // The real backend mounts this endpoint with PUT (see
      // backend/workflows.py: @router.put("/api/merge-pull-request")). Reject
      // anything else so the E2E suite catches contract regressions.
      if (method !== "PUT") {
        return jsonResponse(route, { detail: `method ${method} not allowed` }, 405);
      }
      state.prStatus.project_state = "synced";
      state.prStatus.open_prs = 0;
      state.prStatus.merged_prs = 1;
      state.prStatus.pull_requests = state.prStatus.pull_requests.map((pr) => ({
        ...pr,
        pr_state: "merged",
      }));
      state.projects.forEach((p) => {
        p.pr_state = "synced";
        p.workflows = (p.workflows ?? []).map((workflow) => ({
          ...workflow,
          workflowStatus: workflow.workflowStatus === "under_review" ? "synced_with_github" : workflow.workflowStatus,
        }));
      });
      return jsonResponse(route, {
        message: "merged",
        pr_number: 42,
        repo_name: "octocat/hello-world",
        sha: "abc123",
        merged: true,
        branch_deleted: true,
        branch_delete_warning: null,
      });
    },
  );
  await page.route(
    apiPath((p) => p.startsWith("/api/close-pull-request")),
    (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }
      if (method !== "PATCH") {
        return jsonResponse(route, { detail: `method ${method} not allowed` }, 405);
      }
      state.prStatus.project_state = "draft";
      state.prStatus.open_prs = 0;
      state.prStatus.closed_prs = 1;
      state.prStatus.pull_requests = state.prStatus.pull_requests.map((pr) => ({
        ...pr,
        pr_state: "closed",
        closed_at: "2025-01-02T00:00:00Z",
      }));
      state.projects.forEach((p) => {
        p.pr_state = "draft";
        p.workflows = (p.workflows ?? []).map((workflow) => ({
          ...workflow,
          workflowStatus: workflow.workflowStatus === "under_review" ? "committed_locally" : workflow.workflowStatus,
        }));
      });
      return jsonResponse(route, {
        message: "closed",
        pr_number: 42,
        repo_name: "octocat/hello-world",
        state: "closed",
        closed: true,
      });
    },
  );

  // Repos (used by NewProject + ProjectMgmt)
  await page.route(
    apiPath((p) => p === "/api/repos"),
    (route) =>
      jsonResponse(route, [
        {
          id: 1,
          name: "hello-world",
          full_name: "octocat/hello-world",
          private: false,
          default_branch: "main",
        },
        {
          id: 2,
          name: "spoon-knife",
          full_name: "octocat/spoon-knife",
          private: false,
          default_branch: "main",
        },
        {
          id: 3,
          name: "secret-project",
          full_name: "octocat/secret-project",
          private: true,
          default_branch: "main",
        },
      ]),
  );
  await page.route(
    apiPath((p) => p === "/api/rwx-repos"),
    (route) => jsonResponse(route, []),
  );
  await page.route(
    apiPath((p) => p === "/api/rwx-workflows"),
    (route) => jsonResponse(route, []),
  );

  // Misc endpoints loaded by ProjectMgmt — return safe defaults
  await page.route(
    apiPath((p) => p === "/api/get-env-vars"),
    (route) => jsonResponse(route, []),
  );
  await page.route(
    apiPath((p) => p === "/api/env-vars-count"),
    (route) => jsonResponse(route, {}),
  );
  await page.route(
    apiPath((p) => p === "/api/secrets"),
    (route) => jsonResponse(route, []),
  );
  await page.route(
    apiPath((p) => p.startsWith("/api/workspace/members")),
    (route) => jsonResponse(route, []),
  );
  await page.route(
    apiPath((p) => p === "/api/notifications/subscriptions"),
    (route) => jsonResponse(route, []),
  );
  await page.route(
    apiPath((p) => p === "/api/notifications/deliveries"),
    (route) => jsonResponse(route, []),
  );
  await page.route(
    apiPath((p) => p.startsWith("/api/workflow-templates")),
    (route) => jsonResponse(route, []),
  );

  // Drift detection — never run a live check.
  // Uses apiPath() so /src/api/drift.ts Vite module requests are not intercepted.
  await page.route(
    apiPath((p) => p.startsWith("/api/drift")),
    (route) => jsonResponse(route, { drifted: false, workflows: [] }),
  );

  // Managed Actions (Actions Projects) — preview a repo's actions.yaml
  await page.route(
    apiPath((p) => p === "/api/actions-projects/preview"),
    (route) => jsonResponse(route, state.actionsProjectPreview),
  );

  // Managed Actions — list + create. Excludes "/preview" via the id-detail
  // route below so a plain "/api/actions-projects/{id}" pattern never
  // shadows the preview endpoint regardless of registration order.
  await page.route(
    apiPath((p) => p === "/api/actions-projects/" || p === "/api/actions-projects"),
    async (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }
      if (method === "GET") {
        return jsonResponse(route, state.actionsProjects);
      }
      if (method === "POST") {
        const payload = JSON.parse(route.request().postData() || "{}");
        const created = makeActionsProject({
          actions_project_id: state.actionsProjects.length + 1,
          name: payload.name,
          description: payload.description ?? null,
          source_url: payload.source_url,
          owner: payload.owner,
          repo: payload.repo,
          ref: payload.ref,
          yaml_path: payload.yaml_path,
          inputs: payload.inputs ?? [],
          branding_icon: payload.branding_icon ?? null,
          branding_color: payload.branding_color ?? null,
        });
        state.actionsProjects.push(created);
        return jsonResponse(route, created, 201);
      }
      return route.continue();
    },
  );

  // Managed Actions — get / update / delete a single project by id
  await page.route(
    apiPath((p) => /^\/api\/actions-projects\/(?!preview$)[^/]+$/.test(p)),
    async (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }
      const url = new URL(route.request().url());
      const id = Number(url.pathname.split("/").filter(Boolean).at(-1));
      const project = state.actionsProjects.find((p) => p.actions_project_id === id);
      if (method === "GET") {
        if (!project) return jsonResponse(route, { detail: "not found" }, 404);
        return jsonResponse(route, project);
      }
      if (method === "PUT") {
        if (!project) return jsonResponse(route, { detail: "not found" }, 404);
        const payload = JSON.parse(route.request().postData() || "{}");
        project.name = payload.name;
        project.description = payload.description ?? null;
        if (Array.isArray(payload.inputs)) project.inputs = payload.inputs;
        return jsonResponse(route, project);
      }
      if (method === "DELETE") {
        state.actionsProjects = state.actionsProjects.filter((p) => p.actions_project_id !== id);
        return jsonResponse(route, { ok: true });
      }
      return route.continue();
    },
  );

  // Managed Actions — action groups (used for the group filter + picker)
  await page.route(
    apiPath((p) => p === "/api/action-groups/" || p === "/api/action-groups"),
    (route) => jsonResponse(route, state.actionGroups),
  );

  // Hard fail any GitHub API attempts so we'd notice if a code path slipped through
  await page.route(/api\.github\.com/, (route) =>
    route.fulfill({ status: 503, body: "blocked-by-test" }),
  );

  return state;
}

// ---- Phase 2 helpers ---------------------------------------------------------

/**
 * Override the drift endpoint to return drifted workflows.
 *
 * Must be called AFTER `installApiMocks` — Playwright evaluates routes in
 * LIFO (last-in, first-out) order, so the most recently registered handler
 * wins. Registering this override after `installApiMocks` ensures it takes
 * priority over the catch-all drift handler in that helper.
 *
 * @param driftedWorkflows  Array of WorkflowDriftDetail-shaped objects.
 *                          Pass `[]` to simulate a clean (no-drift) check.
 */
export async function mockDriftResponse(
  page: Page,
  options: {
    driftedWorkflows?: Array<{
      workflow_id?: number;
      workflow_name: string;
      workflow_filename: string;
      repo: string;
      branch?: string;
      has_drift: boolean;
      actionsmanager_yaml?: string;
      github_yaml?: string;
      actionsmanager_sha?: string;
      github_sha?: string;
      last_checked?: string;
      message?: string;
      is_shared_workflow?: boolean;
      has_repo_override?: boolean;
      /** The file is gone from GitHub — renders the deleted panel, not a diff. */
      deleted_in_github?: boolean;
    }>;
    failWithStatus?: number;
    /** Hold the response back, to assert what renders before the check lands. */
    delayMs?: number;
    /** Why the reported state may be older than it looks (no saved token, etc). */
    staleReason?: string;
    /** When the reported state was established. Rendered as "Last checked …". */
    lastChecked?: string;
  } = {},
): Promise<void> {
  const {
    driftedWorkflows = [],
    failWithStatus,
    delayMs,
    staleReason,
    lastChecked = "2025-01-01T00:00:00Z",
  } = options;

  await page.route(
    apiPath((p) => /^\/api\/projects\/[^/]+\/drift$/.test(p)),
    async (route) => {
      if (delayMs) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
      if (failWithStatus) {
        return jsonResponse(route, { detail: "drift check failed" }, failWithStatus);
      }
      const drifted_workflows = driftedWorkflows.map((w, idx) => ({
        workflow_id: w.workflow_id ?? idx + 1,
        workflow_name: w.workflow_name,
        workflow_filename: w.workflow_filename,
        repo: w.repo,
        branch: w.branch ?? "main",
        has_drift: w.has_drift,
        actionsmanager_yaml: w.actionsmanager_yaml ?? "name: CI\n",
        github_yaml: w.github_yaml ?? "name: CI\n# changed in github\n",
        actionsmanager_sha: w.actionsmanager_sha ?? "abc123",
        github_sha: w.github_sha ?? "def456",
        last_checked: w.last_checked ?? lastChecked,
        message: w.message ?? (w.has_drift ? "Drift detected" : "No drift"),
        is_shared_workflow: w.is_shared_workflow ?? false,
        has_repo_override: w.has_repo_override ?? false,
        deleted_in_github: w.deleted_in_github ?? false,
        // Required by the adopt-github-version modal's handleConfirm guard
        project_id: 1,
        repo_id: idx + 1,
        affected_repo_count: 0,
        affected_repos: [],
      }));
      return jsonResponse(route, {
        project_id: 1,
        project_name: "test-project",
        drift_count: drifted_workflows.filter((w) => w.has_drift).length,
        drifted_workflows: drifted_workflows.filter((w) => w.has_drift),
        last_checked: lastChecked,
        stale_reason: staleReason ?? null,
      });
    },
  );

  // Also cover the per-workflow drift endpoint
  await page.route(
    apiPath((p) => /^\/api\/workflows\/[^/]+\/drift$/.test(p)),
    (route) =>
      jsonResponse(route, {
        workflow_id: 1,
        workflow_name: "ci.yml",
        workflow_filename: "ci.yml",
        has_drift: driftedWorkflows.length > 0,
        drift_details: driftedWorkflows,
        last_checked: "2025-01-01T00:00:00Z",
      }),
  );
}

/**
 * Override the resolve-drift endpoint with a canned response.
 *
 * @param responseState  "synced" | "drifted" | "pr_pending"
 */
export async function mockResolveDrift(
  page: Page,
  options: {
    responseState?: "synced" | "drifted" | "pr_pending";
    failWithStatus?: number;
  } = {},
): Promise<void> {
  const { responseState = "synced", failWithStatus } = options;
  await page.route(
    apiPath((p) => /^\/api\/workflows\/[^/]+\/resolve-drift/.test(p)),
    (route) => {
      if (failWithStatus) {
        return jsonResponse(route, { detail: "resolve failed" }, failWithStatus);
      }
      let message: string;
      if (responseState === "synced") {
        message = "Drift resolved – local version restored";
      } else if (responseState === "pr_pending") {
        message = "Pull request created";
      } else {
        message = "Drift was not resolved";
      }
      return jsonResponse(route, { state: responseState, message });
    },
  );

  // adopt-github-version endpoint
  await page.route(
    apiPath((p) => p.startsWith("/api/drift/adopt-github-version")),
    (route) => {
      if (failWithStatus) {
        return jsonResponse(route, { detail: "adopt failed" }, failWithStatus);
      }
      return jsonResponse(route, {
        state: responseState,
        message: "Drift resolved – adopted GitHub version",
      });
    },
  );
}

/**
 * Override the create-pull-requests endpoint with a multi-repo response.
 * Each entry in `results` maps a repo to success/failure state.
 */
export async function mockCreatePullRequests(
  page: Page,
  state: MockState,
  options: {
    repoResults?: Array<{
      repo: string;
      success: boolean;
      pr_number?: number;
      pr_url?: string;
      branch_name?: string;
      error?: string;
    }>;
  } = {},
): Promise<void> {
  const { repoResults = [] } = options;

  await page.route(
    apiPath((p) => p === "/api/create-pull-requests"),
    (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }

      if (method === "POST") {
        let body: { project_name?: string } = {};
        try {
          body = JSON.parse(route.request().postData() ?? "{}") as { project_name?: string };
        } catch {}
        const projectName = body.project_name ?? "";

        const successPRs = repoResults.filter((r) => r.success);
        const pull_requests = successPRs.map((r, idx) => ({
          repo_name: r.repo,
          pr_number: r.pr_number ?? 100 + idx,
          pr_url: r.pr_url ?? `https://github.com/${r.repo}/pull/${r.pr_number ?? 100 + idx}`,
          pr_state: "open",
          branch_name: r.branch_name ?? "actions-manager/test",
          target_branch: "main",
          created_at: "2025-01-02T00:00:00Z",
          updated_at: "2025-01-02T00:00:00Z",
        }));

        state.prStatus.pull_requests = pull_requests;
        state.prStatus.open_prs = pull_requests.length;
        state.prStatus.total_prs = pull_requests.length;
        state.prStatus.project_state = "open";
        state.projects.forEach((p) => {
          if (!projectName || p.project_name === projectName) {
            p.pr_state = "open";
          }
        });
        return jsonResponse(route, { task_id: "mock-task-id", status: "running" });
      }
    },
  );

  await page.route(
    apiPath((p) => p === "/api/create-pull-requests/mock-task-id"),
    (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }

      const successPRs = repoResults.filter((r) => r.success);
      const failedPRs = repoResults.filter((r) => !r.success);

      const results: Record<string, unknown> = {};
      successPRs.forEach((r) => {
        results[r.repo] = { pr_number: r.pr_number ?? 100, pr_url: r.pr_url ?? "" };
      });

      return jsonResponse(route, {
        status: "completed",
        results,
        prs_created: successPRs.length,
        repos: {},
        errors: failedPRs.reduce(
          (acc, r) => ({ ...acc, [r.repo]: r.error ?? "Failed" }),
          {} as Record<string, string>,
        ),
      });
    },
  );
}

/**
 * Override the merge-pull-request endpoint with a canned response.
 */
export async function mockMergePullRequest(
  page: Page,
  state: MockState,
  options: {
    failWithStatus?: number;
    errorMessage?: string;
  } = {},
): Promise<void> {
  const { failWithStatus, errorMessage } = options;
  await page.route(
    apiPath((p) => p.startsWith("/api/merge-pull-request")),
    (route) => {
      const method = route.request().method();
      if (method === "OPTIONS") {
        return jsonResponse(route, {});
      }
      if (method !== "PUT") {
        return jsonResponse(route, { detail: `method ${method} not allowed` }, 405);
      }
      if (failWithStatus) {
        return jsonResponse(route, { detail: errorMessage ?? "Merge failed" }, failWithStatus);
      }
      // Parse the request body to identify which project/repo is being merged.
      // Only update state for the named project so unrelated projects in the
      // same test are not incorrectly flipped to "synced".
      let body: { project_name?: string; repo_name?: string; pr_number?: number } = {};
      try {
        body = JSON.parse(route.request().postData() ?? "{}") as {
          project_name?: string;
          repo_name?: string;
          pr_number?: number;
        };
      } catch {
        // Malformed body — body stays empty; names default to "" below
      }
      const mergedProjectName = body.project_name ?? "";
      const mergedRepoName = body.repo_name ?? "";

      if (!mergedRepoName) {
        // repo_name is required by the real API. Fail loudly so tests notice
        // if the production client accidentally omits it.
        return jsonResponse(route, { detail: "repo_name is required" }, 422);
      }

      // Mark only the specified repo's PR as merged; leave others untouched.
      state.prStatus.pull_requests = state.prStatus.pull_requests.map((pr) => ({
        ...pr,
        pr_state: pr.repo_name === mergedRepoName ? "merged" : pr.pr_state,
      }));
      state.prStatus.merged_prs = (state.prStatus.merged_prs ?? 0) + 1;

      // Recalculate open count based on remaining open PRs.
      const stillOpen = state.prStatus.pull_requests.filter((pr) => pr.pr_state === "open");
      state.prStatus.open_prs = stillOpen.length;
      if (stillOpen.length === 0) {
        state.prStatus.project_state = "synced";
        state.projects.forEach((p) => {
          if (!mergedProjectName || p.project_name === mergedProjectName) {
            p.pr_state = "synced";
          }
        });
      }
      return jsonResponse(route, {
        message: "merged",
        pr_number: body.pr_number ?? 42,
        repo_name: mergedRepoName || "test-org/service-a",
        sha: "abc123",
        merged: true,
        branch_deleted: true,
        branch_delete_warning: null,
      });
    },
  );
}

/**
 * Register a mock for the linked reusable workflow APIs used by standard
 * projects (list of linked workflows) and RWX projects (list of linked
 * standard projects that use them).
 */
export async function mockReusableWorkflowLinks(
  page: Page,
  options: {
    linkedWorkflows?: Array<{
      workflow_id: number;
      workflow_name: string;
      rwx_project_id: number;
      rwx_project_name: string;
      workflowStatus?: string;
    }>;
    linkedStandardProjects?: Array<{
      project_id: number;
      project_name: string;
      project_code: string;
    }>;
  } = {},
): Promise<void> {
  const { linkedWorkflows = [], linkedStandardProjects = [] } = options;

  // GET /api/projects/{name}/linked-workflows  (standard project view)
  await page.route(
    apiPath((p) => /^\/api\/projects\/[^/]+\/linked-workflows$/.test(p)),
    (route) => jsonResponse(route, linkedWorkflows),
  );

  // GET /api/rwx-workflows  (used by some views)
  await page.route(
    apiPath((p) => p === "/api/rwx-workflows"),
    (route) => jsonResponse(route, linkedWorkflows),
  );

  // GET /api/projects/{name}/linked-projects  (RWX project view)
  await page.route(
    apiPath((p) => /^\/api\/projects\/[^/]+\/linked-projects$/.test(p)),
    (route) => jsonResponse(route, linkedStandardProjects),
  );
}

/**
 * Override the /api/user/:username endpoint to return a different account_type.
 *
 * Must be called AFTER `installApiMocks` so this handler wins (LIFO order).
 * Useful for testing features gated behind non-Free tiers, such as private
 * repository project creation.
 *
 * @example
 *   await installApiMocks(page, state);
 *   await overrideUserAccountType(page, "Professional");
 */
export async function overrideUserAccountType(
  page: Page,
  accountType: string,
  user: string = TEST_USER,
): Promise<void> {
  await page.route(
    apiPath((p) => /^\/api\/user\/[^/]+$/.test(p)),
    (route) =>
      jsonResponse(route, { ...TEST_USER_DETAILS, github_user: user, username: user, account_type: accountType }),
  );
}
