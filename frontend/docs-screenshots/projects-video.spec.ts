import { test } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import {
  createMockState,
  installApiMocks,
  makeProject,
  makeWorkflow,
  seedAuthenticatedSession,
} from "../e2e/fixtures/mocks";
import { DOCS_USER, seedDocsUserProfile } from "./docs-fixtures";

/**
 * Regenerates the video embedded in docs/features/projects.md
 * (docs/assets/videos/projects/project-view.webm). Run with
 * `npm run docs:screenshots` (shares testDir/config with features.spec.ts).
 *
 * Playwright names recorded videos with a random hash, so the file is
 * recorded into the test's default output dir and then renamed into place
 * after the page (and its video) is closed/flushed.
 */
test.use({ video: { mode: "on", size: { width: 1710, height: 900 } } });

test.describe("docs video", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page, DOCS_USER);
  });

  test("projects dashboard walkthrough", async ({ page }) => {
    const projects = [
      makeProject({
        project_id: 1,
        project_name: "Payments Platform",
        project_code: "PAY",
        github_user: DOCS_USER,
        last_modified_by: DOCS_USER,
        updated_at: "2026-07-24T00:00:00Z",
        pr_state: "draft",
        project_color: "amber",
        selected_repos: ["acme-corp/payments-service", "acme-corp/payments-worker"],
        workflows: [makeWorkflow({ name: "build-and-test.yml", lastModifiedBy: DOCS_USER })],
      }),
      makeProject({
        project_id: 2,
        project_name: "Web Storefront",
        project_code: "WEB",
        github_user: DOCS_USER,
        last_modified_by: DOCS_USER,
        updated_at: "2026-07-24T00:00:00Z",
        pr_state: "synced",
        selected_repos: ["acme-corp/storefront-web"],
        workflows: [makeWorkflow({ name: "deploy-production.yml", lastModifiedBy: DOCS_USER })],
      }),
      makeProject({
        project_id: 3,
        project_name: "Internal Tools",
        project_code: "TOOLS",
        github_user: DOCS_USER,
        last_modified_by: DOCS_USER,
        updated_at: "2026-07-24T00:00:00Z",
        pr_state: "open",
        use_prefix: true,
        selected_repos: ["acme-corp/internal-cli", "acme-corp/internal-dashboard"],
        workflows: [makeWorkflow({ name: "release.yml", lastModifiedBy: DOCS_USER })],
      }),
      makeProject({
        project_id: 4,
        project_name: "Shared Workflows",
        project_code: "SHARED",
        project_type: "rwx",
        github_user: DOCS_USER,
        last_modified_by: DOCS_USER,
        updated_at: "2026-07-24T00:00:00Z",
        pr_state: "synced",
        project_color: "purple",
        selected_repos: ["acme-corp/reusable-workflows"],
        workflows: [makeWorkflow({ name: "shared-build.yml", isReusable: true, lastModifiedBy: DOCS_USER })],
      }),
    ];
    await installApiMocks(page, createMockState({ projects }));
    await seedDocsUserProfile(page);

    await page.goto(`/project/${DOCS_USER}`);
    await page.getByText("Payments Platform", { exact: true }).waitFor({ timeout: 15000 });
    await page.waitForTimeout(500);

    // Light hover pauses over a few cards so the clip reads as a short loop
    // rather than a frozen frame — not a full product demo. Each card is a
    // full-bleed "Open project <name>" button overlaying the card content,
    // so that's the element to hover, not the underlying text span.
    await page.getByRole("button", { name: "Open project Payments Platform" }).hover();
    await page.waitForTimeout(700);
    await page.getByRole("button", { name: "Open project Web Storefront" }).hover();
    await page.waitForTimeout(700);
    await page.getByRole("button", { name: "Open project Internal Tools" }).hover();
    await page.waitForTimeout(900);

    await page.close(); // finalizes/flushes the video file
    const videoPath = await page.video()!.path();
    const outPath = path.join(__dirname, "../../docs/assets/videos/projects/project-view.webm");
    await fs.promises.mkdir(path.dirname(outPath), { recursive: true });
    await fs.promises.rename(videoPath, outPath);
  });
});
