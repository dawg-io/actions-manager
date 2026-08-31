import { test, expect, Page } from "@playwright/test";
import {
  TEST_USER,
  createMockState,
  installApiMocks,
  makeProject,
  SAMPLE_WORKFLOW,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Resource naming in both prefix modes.
 *
 * A project either prefixes the resources it manages with `AM_{PROJECT_CODE}_`
 * or it does not. That choice is made once in the Create Project wizard and has
 * to hold everywhere afterwards, so these tests cover both halves: the mode the
 * wizard actually submits, and the names every surface shows once a project in
 * that mode is opened.
 *
 * Deployment environments are checked too, and are expected to be unprefixed in
 * BOTH modes: their names are picked by the user and referenced by name from
 * workflow `environment:` keys and branch protection rules, so prefixing them
 * would break those references.
 */

const PREFIXED = { name: "alpha-prefixed", code: "ALPHA" };
const UNPREFIXED = { name: "beta-plain", code: "BETA" };

/** Walk the wizard to the review step and pick a naming mode. */
async function createProjectWithMode(page: Page, projectName: string, mode: "prefix" | "no-prefix") {
  await page.goto(`/project/${TEST_USER}/new`);

  await page.getByLabel(/Project Name:/i).fill(projectName);
  await page.getByTestId("wizard-continue").click();

  await page.getByTestId("available-checkbox-octocat/hello-world").click();
  await page.getByTestId("wizard-continue").click();

  await page.locator(`input[name="resourceNamingMode"][value="${mode}"]`).check();
  await page.getByTestId("create-project-button").click();
}

/** The Repository Configs page renders all five sections at once. */
async function openRepositoryConfigs(page: Page) {
  await page.getByRole("button", { name: "Deploy Environments" }).click();
  await expect(page.getByRole("region", { name: "Environment Variables" })).toBeVisible({
    timeout: 15_000,
  });
}

const section = (page: Page, name: string) => page.getByRole("region", { name });

test.describe("Project creation submits the chosen naming mode", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
  });

  test("prefix mode is submitted as use_prefix true", async ({ page }) => {
    const state = await installApiMocks(page, createMockState({ projects: [] }));

    await createProjectWithMode(page, PREFIXED.name, "prefix");

    await expect
      .poll(() => state.lastProjectCreateRequest?.project_name, { timeout: 15_000 })
      .toBe(PREFIXED.name);
    expect(state.lastProjectCreateRequest?.use_prefix).toBe(true);
  });

  test("no-prefix mode is submitted as use_prefix false", async ({ page }) => {
    const state = await installApiMocks(page, createMockState({ projects: [] }));

    await createProjectWithMode(page, UNPREFIXED.name, "no-prefix");

    await expect
      .poll(() => state.lastProjectCreateRequest?.project_name, { timeout: 15_000 })
      .toBe(UNPREFIXED.name);
    expect(state.lastProjectCreateRequest?.use_prefix).toBe(false);
  });
});

test.describe("A project in prefix mode", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
    const project = makeProject({
      project_name: PREFIXED.name,
      project_code: PREFIXED.code,
      use_prefix: true,
      workflows: [SAMPLE_WORKFLOW],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
  });

  test("names the workflow file as it will land on GitHub", async ({ page }) => {
    await page.goto(`/project/${TEST_USER}/${PREFIXED.name}`);

    // The row reads, and is announced as, the file the delivery actually
    // produces — not the bare stem the user typed.
    await expect(
      page.getByRole("button", { name: `AM_${PREFIXED.code}_${SAMPLE_WORKFLOW.name}, No status` }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".pf-row-prefix").first()).toHaveText(`AM_${PREFIXED.code}_`);
  });

  test("prefixes variable and secret keys, but never environment names", async ({ page }) => {
    await page.goto(`/project/${TEST_USER}/${PREFIXED.name}`);
    await openRepositoryConfigs(page);

    await expect(
      section(page, "Environment Variables").getByTestId("prefixed-input-prefix"),
    ).toHaveText(`AM_${PREFIXED.code}_`);
    await expect(
      section(page, "Environment Secrets").getByTestId("prefixed-input-prefix"),
    ).toHaveText(`AM_${PREFIXED.code}_`);

    const environments = section(page, "Deploy Environments");
    await expect(environments.getByText("production").first()).toBeVisible();
    await expect(environments.getByText(/AM_/)).toHaveCount(0);
  });
});

test.describe("A project in no-prefix mode", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedSession(page);
    const project = makeProject({
      project_name: UNPREFIXED.name,
      project_code: UNPREFIXED.code,
      use_prefix: false,
      workflows: [SAMPLE_WORKFLOW],
    });
    await installApiMocks(page, createMockState({ projects: [project] }));
  });

  test("names the workflow file with no prefix at all", async ({ page }) => {
    await page.goto(`/project/${TEST_USER}/${UNPREFIXED.name}`);

    await expect(
      page.getByRole("button", { name: `${SAMPLE_WORKFLOW.name}, No status` }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".pf-row-prefix")).toHaveCount(0);
  });

  test("leaves variable keys, secret keys and environment names unprefixed", async ({ page }) => {
    await page.goto(`/project/${TEST_USER}/${UNPREFIXED.name}`);
    await openRepositoryConfigs(page);

    await expect(
      section(page, "Environment Variables").getByTestId("prefixed-input-prefix"),
    ).toHaveCount(0);
    await expect(
      section(page, "Environment Secrets").getByTestId("prefixed-input-prefix"),
    ).toHaveCount(0);

    const environments = section(page, "Deploy Environments");
    await expect(environments.getByText("production").first()).toBeVisible();
    await expect(environments.getByText(/AM_/)).toHaveCount(0);
  });
});
