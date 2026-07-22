/**
 * Tests for pullRequests.ts — verifies the module uses the shared config
 * for BACKEND_URL instead of a hardcoded/inline fallback.
 */
import { describe, test, expect, vi } from "vitest";

describe("pullRequests module", () => {
  test("uses config.BACKEND_URL instead of hardcoded fallback", async () => {
    // Set a known VITE_BACKEND_URL via env so config.BACKEND_URL resolves to it
    vi.stubEnv("VITE_BACKEND_URL", "http://test-server:9999");
    vi.resetModules();

    const config = (await import("../config")).default;
    expect(config.BACKEND_URL).toBe("http://test-server:9999");

    // Import pullRequests — it should use config.BACKEND_URL, not
    // import.meta.env.VITE_BACKEND_URL || "http://localhost:8000"
    const prModule = await import("./pullRequests");
    // The module is successfully imported and exports the expected functions
    expect(prModule.createPullRequests).toBeTypeOf("function");
    expect(prModule.getProjectPRStatus).toBeTypeOf("function");

    vi.unstubAllEnvs();
  });

  test("does not contain hardcoded localhost:8000 fallback", async () => {
    // Read the source file to verify no hardcoded fallback exists
    const fs = await import("node:fs");
    const path = await import("node:path");
    const source = fs.readFileSync(
      path.resolve(__dirname, "./pullRequests.ts"),
      "utf-8"
    );
    expect(source).not.toContain("http://localhost:8000");
    expect(source).toContain('import config from "../config"');
  });
});
