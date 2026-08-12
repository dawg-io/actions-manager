import { isUninitialized, validateBackup, applyBackup } from "./setup";

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: vi.fn().mockResolvedValue(body) } as unknown as Response;
}

describe("setup API", () => {
  afterEach(() => vi.restoreAllMocks());

  describe("isUninitialized", () => {
    it("is true only while nobody has signed in", async () => {
      global.fetch = vi.fn().mockResolvedValue(jsonResponse({ uninitialized: true }));

      await expect(isUninitialized()).resolves.toBe(true);
    });

    it("is false once the workspace has a member", async () => {
      global.fetch = vi.fn().mockResolvedValue(jsonResponse({ uninitialized: false }));

      await expect(isUninitialized()).resolves.toBe(false);
    });

    it("fails closed when the probe itself fails", async () => {
      // Offering a restore we cannot verify is worse than not offering one.
      global.fetch = vi.fn().mockResolvedValue(jsonResponse({}, false, 500));

      await expect(isUninitialized()).resolves.toBe(false);
    });
  });

  describe("validateBackup", () => {
    it("posts the archive as multipart form data", async () => {
      global.fetch = vi.fn().mockResolvedValue(jsonResponse({ upload_token: "tok", ok: true }));
      const file = new File([new Blob(["bytes"])], "backup.tar.gz");

      await validateBackup(file);

      const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(url).toContain("/api/setup/restore/validate");
      expect(init.method).toBe("POST");
      expect(init.body).toBeInstanceOf(FormData);
      expect((init.body as FormData).get("file")).toBe(file);
    });

    it("surfaces the server's reason for rejecting an archive", async () => {
      global.fetch = vi.fn().mockResolvedValue(
        jsonResponse({ detail: "Archive is unreadable or corrupt" }, false, 400)
      );

      await expect(validateBackup(new File([""], "b.tar.gz"))).rejects.toThrow("unreadable or corrupt");
    });

    it("falls back to the status code when the body carries no detail", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 413,
        json: vi.fn().mockRejectedValue(new Error("not json")),
      } as unknown as Response);

      await expect(validateBackup(new File([""], "b.tar.gz"))).rejects.toThrow("413");
    });
  });

  describe("applyBackup", () => {
    it("sends the staging token from the validate step", async () => {
      global.fetch = vi.fn().mockResolvedValue(jsonResponse({ restored_rows: 3 }));

      await applyBackup("tok123");

      const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(url).toContain("/api/setup/restore/apply");
      expect((init.body as FormData).get("upload_token")).toBe("tok123");
    });

    it("surfaces a refusal once the workspace is no longer empty", async () => {
      global.fetch = vi.fn().mockResolvedValue(
        jsonResponse({ detail: "This installation is already in use." }, false, 409)
      );

      await expect(applyBackup("tok123")).rejects.toThrow("already in use");
    });
  });
});
