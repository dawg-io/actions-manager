import { test, expect, Page } from "@playwright/test";
import {
  TEST_USER,
  createMockState,
  installApiMocks,
  makeProject,
  overrideOnboardingState,
  seedAuthenticatedSession,
  type OnboardingStub,
} from "./fixtures/mocks";

/**
 * First-login welcome screen and guided tour.
 *
 * These cover the things unit tests structurally cannot: that the callout is
 * anchored to a control that is really on the page, that the highlight lands
 * on the real element, and that nothing the tour renders blocks the app
 * underneath it. Every failure this feature actually shipped was of that kind
 * — a modal that swallowed clicks, and an anchor pointing at a component that
 * never mounts.
 */

const NOT_STARTED: OnboardingStub = { completed: false, completed_at: null, step: null };

async function arrive(
  page: Page,
  onboarding: OnboardingStub | null,
  options: { workspaceRole?: string } = {},
) {
  const state = createMockState({ projects: [makeProject({ project_name: "existing" })] });
  await seedAuthenticatedSession(page);
  await installApiMocks(page, state);
  const writes = await overrideOnboardingState(page, onboarding, options);
  await page.goto(`/project/${TEST_USER}`);
  return writes;
}

test.describe("Welcome screen", () => {
  test("is offered on a first login", async ({ page }) => {
    await arrive(page, NOT_STARTED);

    await expect(page.getByTestId("onboarding-welcome")).toBeVisible();
    await expect(page.getByText("Welcome to ActionsManager")).toBeVisible();
  });

  test("stays away once onboarding is completed", async ({ page }) => {
    await arrive(page, { completed: true, completed_at: "2026-08-17T00:00:00Z", step: null });

    // Anchor on something that only exists once the dashboard has really
    // rendered: toBeHidden() also passes for an element that is simply not
    // there yet, so without this the assertion below proves nothing.
    await expect(page.getByTestId("new-project-button")).toBeVisible();
    await expect(page.getByTestId("onboarding-welcome")).toBeHidden();
  });

  test("is not shown while a tour is already under way", async ({ page }) => {
    await arrive(page, { completed: false, completed_at: null, step: "open-wizard" });

    await expect(page.getByTestId("onboarding-welcome")).toBeHidden();
    await expect(page.getByTestId("tour-callout")).toBeVisible();
  });

  test("never appears for a read-only member", async ({ page }) => {
    // They cannot create a project and cannot persist a dismissal, so the
    // dialog would be undismissable for them.
    await arrive(page, NOT_STARTED, { workspaceRole: "read_only" });

    // Anchor on something that only exists once the dashboard has really
    // rendered: toBeHidden() also passes for an element that is simply not
    // there yet, so without this the assertion below proves nothing.
    await expect(page.getByTestId("new-project-button")).toBeVisible();
    await expect(page.getByTestId("onboarding-welcome")).toBeHidden();
  });

  test("is not shown when the API reports no onboarding state at all", async ({ page }) => {
    // A frontend running ahead of its backend must not show a dialog whose
    // dismissal would 404 — it would return on every single login.
    await arrive(page, null);

    // Anchor on something that only exists once the dashboard has really
    // rendered: toBeHidden() also passes for an element that is simply not
    // there yet, so without this the assertion below proves nothing.
    await expect(page.getByTestId("new-project-button")).toBeVisible();
    await expect(page.getByTestId("onboarding-welcome")).toBeHidden();
  });

  test("dismissing records completion and does not come back", async ({ page }) => {
    const writes = await arrive(page, NOT_STARTED);

    await page.getByTestId("onboarding-welcome-dismiss").click();

    await expect(page.getByTestId("onboarding-welcome")).toBeHidden();
    expect(writes).toContainEqual(expect.objectContaining({ completed: true }));
  });
});

test.describe("Guided tour", () => {
  test("starting it points the callout at New Project and highlights it", async ({ page }) => {
    await arrive(page, NOT_STARTED);
    await page.getByTestId("onboarding-welcome-start-tour").click();

    const callout = page.getByTestId("tour-callout");
    await expect(callout).toBeVisible();
    await expect(callout).toContainText("Start with a project");

    // The ring goes on the real control, not on an overlay above it.
    await expect(page.getByTestId("new-project-button")).toHaveClass(/am-tour-target/);
  });

  test("leaves the app underneath usable", async ({ page }) => {
    // The regression that broke every clicking test once: a modal overlay
    // rendering across the page and swallowing the click each step asks for.
    await arrive(page, NOT_STARTED);
    await page.getByTestId("onboarding-welcome-start-tour").click();
    await expect(page.getByTestId("tour-callout")).toBeVisible();

    await page.getByTestId("new-project-button").click();

    await expect(page).toHaveURL(new RegExp(`/project/${TEST_USER}/new$`));
  });

  test("stays inside the viewport", async ({ page }) => {
    // It used to run off the bottom beside a button near the foot of a form,
    // cutting the text off.
    await page.setViewportSize({ width: 1280, height: 720 });
    await arrive(page, NOT_STARTED);
    await page.getByTestId("onboarding-welcome-start-tour").click();

    const box = await page.getByTestId("tour-callout").boundingBox();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(720);
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(1280);
  });

  test("advances into the wizard when the user really opens it", async ({ page }) => {
    const writes = await arrive(page, NOT_STARTED);
    await page.getByTestId("onboarding-welcome-start-tour").click();

    await page.getByTestId("new-project-button").click();

    await expect(page.getByTestId("tour-callout")).toContainText("Name, type and colour");
    expect(writes).toContainEqual(expect.objectContaining({ step: "project-basics" }));
  });

  test("pre-fills the wizard so the step's promise is true", async ({ page }) => {
    await arrive(page, { completed: false, completed_at: null, step: "project-basics" });
    await page.goto(`/project/${TEST_USER}/new`);

    await expect(page.getByTestId("project-name-input")).toHaveValue(/^Demo-Project/);
  });

  test("skipping ends it and records completion", async ({ page }) => {
    const writes = await arrive(page, { completed: false, completed_at: null, step: "open-wizard" });

    await page.getByTestId("tour-callout-skip").click();

    await expect(page.getByTestId("tour-callout")).toBeHidden();
    expect(writes).toContainEqual(expect.objectContaining({ completed: true }));
  });

  test("Escape ends it when nothing else owns the key", async ({ page }) => {
    const writes = await arrive(page, { completed: false, completed_at: null, step: "open-wizard" });
    // Wait for it to actually be there: without this the assertion below
    // passes on a callout that had not rendered yet, proving nothing.
    await expect(page.getByTestId("tour-callout")).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(page.getByTestId("tour-callout")).toBeHidden();
    expect(writes).toContainEqual(expect.objectContaining({ completed: true }));
  });

  test("Escape aimed at an open dialog does not end it", async ({ page }) => {
    // Several steps point at a control inside a dialog. Treating that Escape
    // as "end the tour" killed onboarding permanently.
    await arrive(page, { completed: false, completed_at: null, step: "open-wizard" });
    await expect(page.getByTestId("tour-callout")).toBeVisible();

    await page.evaluate(() => {
      const dialog = document.createElement("div");
      dialog.setAttribute("role", "dialog");
      dialog.setAttribute("data-state", "open");
      dialog.id = "probe-dialog";
      document.body.appendChild(dialog);
    });
    await page.keyboard.press("Escape");

    await expect(page.getByTestId("tour-callout")).toBeVisible();
  });

  test("closing screen offers the docs and only then completes", async ({ page }) => {
    const writes = await arrive(page, { completed: false, completed_at: null, step: "finished" });

    const complete = page.getByTestId("onboarding-complete");
    await expect(complete).toBeVisible();
    await expect(complete.getByRole("link", { name: /quick start/i })).toHaveAttribute(
      "href",
      "https://actionsmanager.io/getting-started/quick-start.html",
    );
    expect(writes).toHaveLength(0);

    await page.getByTestId("onboarding-complete-close").click();

    expect(writes).toContainEqual(expect.objectContaining({ completed: true }));
  });
});

test.describe("Restart tour", () => {
  test("offers the welcome screen again from the user menu", async ({ page }) => {
    await arrive(page, { completed: true, completed_at: "2026-08-17T00:00:00Z", step: null });
    // Anchor on something that only exists once the dashboard has really
    // rendered: toBeHidden() also passes for an element that is simply not
    // there yet, so without this the assertion below proves nothing.
    await expect(page.getByTestId("new-project-button")).toBeVisible();
    await expect(page.getByTestId("onboarding-welcome")).toBeHidden();

    await page.getByRole("button", { name: `User menu for ${TEST_USER}` }).click();
    await page.getByTestId("restart-tour").click();

    await expect(page.getByTestId("onboarding-welcome")).toBeVisible();
  });

  test("is not offered to a read-only member", async ({ page }) => {
    await arrive(page, { completed: true, completed_at: "2026-08-17T00:00:00Z", step: null }, {
      workspaceRole: "read_only",
    });

    await page.getByRole("button", { name: `User menu for ${TEST_USER}` }).click();
    // Prove the menu actually opened before asserting an item is missing from it.
    await expect(page.getByRole("menuitem").first()).toBeVisible();

    await expect(page.getByTestId("restart-tour")).toBeHidden();
  });
});
