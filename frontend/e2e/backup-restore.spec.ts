import { test, expect, Page } from "@playwright/test";
import {
  TEST_USER_DETAILS,
  createMockState,
  installApiMocks,
  seedAuthenticatedSession,
} from "./fixtures/mocks";

/**
 * Installation backup and first-boot restore (issue #1878).
 *
 * The unit tests cover each screen in isolation. What only a browser can show
 * is that the download actually produces a file, and that the first-boot
 * restore is offered exactly when the server says the workspace is empty —
 * the gate the whole security argument rests on.
 */

const BACKUP_INFO = {
  backup_format_version: "1.0",
  table_count: 3,
  total_rows: 128,
  tables: { accounts: 4, projects: 12, workflows: 112 },
  excluded_tables: ["auth_sessions"],
};

const VALID_REPORT = {
  upload_token: "e2e-token",
  ok: true,
  errors: [],
  warnings: [],
  total_rows: 128,
  tables: { accounts: 4, projects: 12, workflows: 112 },
  app_version: "1.0.0",
  created_at: "2026-08-11T20:00:00+00:00",
  dialect: "sqlite",
};

/** Override the workspace role. Must run AFTER installApiMocks — Playwright
 *  routes are LIFO, so the last registered handler wins. */
async function withWorkspaceRole(page: Page, role: string): Promise<void> {
  await page.route(
    (url) => /^\/api\/user\/[^/]+$/.test(url.pathname),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...TEST_USER_DETAILS, workspace_role: role }),
      }),
  );
}

async function mockSetupStatus(page: Page, uninitialized: boolean): Promise<void> {
  await page.route("**/api/setup/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ uninitialized }),
    }),
  );
}

async function mockBackupEndpoints(page: Page): Promise<void> {
  await page.route("**/api/workspace/backup/info", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(BACKUP_INFO),
    }),
  );
  await page.route("**/api/workspace/backup", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/gzip",
      headers: {
        "content-disposition": 'attachment; filename="actionsmanager-backup-2026-08-11.tar.gz"',
        // Mirrors the server's CORS config. Without this the browser receives
        // the header but JS cannot read it, and the filename silently degrades.
        "access-control-expose-headers": "Content-Disposition",
      },
      body: "not-a-real-archive-but-a-real-download",
    }),
  );
}

/** Put a file on the upload input without touching the filesystem. */
async function chooseBackupFile(page: Page): Promise<void> {
  await page.getByLabel(/backup archive/i).setInputFiles({
    name: "backup.tar.gz",
    mimeType: "application/gzip",
    buffer: Buffer.from("archive-bytes"),
  });
}

test.describe("Workspace backup download", () => {
  test("an admin sees what the backup holds and downloads it", async ({ page }) => {
    await seedAuthenticatedSession(page);
    await installApiMocks(page, createMockState());
    await mockBackupEndpoints(page);
    await withWorkspaceRole(page, "admin");

    await page.goto("/workspace/backup");

    await expect(page.getByText(/128 row\(s\) across 3 table\(s\)/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/SECRET_KEY/)).toBeVisible();

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: /download backup/i }).click(),
    ]);

    expect(download.suggestedFilename()).toBe("actionsmanager-backup-2026-08-11.tar.gz");
  });
});

test.describe("Workspace backup — non-admins", () => {
  for (const role of ["member", "read_only"]) {
    test(`a ${role} user is told this is admin-only and gets no control`, async ({ page }) => {
      await seedAuthenticatedSession(page);
      await installApiMocks(page, createMockState());
      await mockBackupEndpoints(page);
      await withWorkspaceRole(page, role);

      await page.goto("/workspace/backup");

      await expect(page.getByText(/only workspace admins/i)).toBeVisible({ timeout: 15_000 });
      await expect(page.getByRole("button", { name: /download backup/i })).toHaveCount(0);
    });
  }
});

test.describe("First-boot restore — the uninitialized gate", () => {
  test("an untouched installation offers to restore", async ({ page }) => {
    await installApiMocks(page, createMockState());
    await mockSetupStatus(page, true);

    await page.goto("/");

    await expect(page.getByRole("button", { name: /restore from a backup/i })).toBeVisible({
      timeout: 15_000,
    });
  });

  test("an installation someone has already signed into does not", async ({ page }) => {
    // The window closes permanently once the workspace has a member. If this
    // ever regresses, an anonymous visitor is offered a destructive action.
    await installApiMocks(page, createMockState());
    await mockSetupStatus(page, false);

    await page.goto("/");

    await expect(page.getByRole("button", { name: /log in with github/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("button", { name: /restore from a backup/i })).toHaveCount(0);
  });

  test("the offer is withheld when the status probe fails", async ({ page }) => {
    // Fail closed: offering a restore we could not verify is worse than not offering one.
    await installApiMocks(page, createMockState());
    await page.route("**/api/setup/status", (route) => route.fulfill({ status: 500, body: "boom" }));

    await page.goto("/");

    await expect(page.getByRole("button", { name: /log in with github/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("button", { name: /restore from a backup/i })).toHaveCount(0);
  });
});

test.describe("First-boot restore — the flow", () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page, createMockState());
    await mockSetupStatus(page, true);
  });

  test("upload, review, confirm, done", async ({ page }) => {
    await page.route("**/api/setup/restore/validate", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(VALID_REPORT),
      }),
    );
    await page.route("**/api/setup/restore/apply", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          restored_rows: 128,
          restored_tables: 3,
          skipped_tables: [],
          warnings: [],
          migrations_ran: true,
        }),
      }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: /restore from a backup/i }).click();
    await chooseBackupFile(page);

    await expect(page.getByText(/128 row\(s\) across 3 table\(s\)/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/ActionsManager 1\.0\.0/)).toBeVisible();

    // Nothing is applied until the phrase is typed.
    const restoreButton = page.getByRole("button", { name: /restore this backup/i });
    await expect(restoreButton).toBeDisabled();

    await page.getByLabel(/type restore to confirm/i).fill("restore");
    await expect(restoreButton).toBeEnabled();
    await restoreButton.click();

    await expect(page.getByText(/restore complete/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/sign in with github to continue/i)).toBeVisible();
  });

  test("an incompatible backup is explained and never offers to apply", async ({ page }) => {
    await page.route("**/api/setup/restore/validate", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...VALID_REPORT,
          ok: false,
          errors: ["Backup came from a newer schema; this installation is missing 2 migration(s)."],
        }),
      }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: /restore from a backup/i }).click();
    await chooseBackupFile(page);

    await expect(page.getByText(/came from a newer schema/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel(/type restore to confirm/i)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /restore this backup/i })).toBeDisabled();
  });

  test("a SECRET_KEY mismatch warns but still allows the restore", async ({ page }) => {
    // Everything except saved tokens recovers fine under a different key, so
    // this must inform rather than block.
    await page.route("**/api/setup/restore/validate", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...VALID_REPORT,
          warnings: [
            "SECRET_KEY differs from the one this backup was written under. Saved personal access tokens will not decrypt and must be re-entered after restoring.",
          ],
        }),
      }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: /restore from a backup/i }).click();
    await chooseBackupFile(page);

    await expect(page.getByText(/SECRET_KEY differs/)).toBeVisible({ timeout: 15_000 });
    await page.getByLabel(/type restore to confirm/i).fill("restore");
    await expect(page.getByRole("button", { name: /restore this backup/i })).toBeEnabled();
  });

  test("a rejected upload is reported rather than failing silently", async ({ page }) => {
    await page.route("**/api/setup/restore/validate", (route) =>
      route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Archive is unreadable or corrupt: not a gzip file" }),
      }),
    );

    await page.goto("/");
    await page.getByRole("button", { name: /restore from a backup/i }).click();
    await chooseBackupFile(page);

    await expect(page.getByText(/unreadable or corrupt/i)).toBeVisible({ timeout: 15_000 });
  });
});
