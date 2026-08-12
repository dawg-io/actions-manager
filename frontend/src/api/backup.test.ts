import { fetchBackupInfo, downloadBackup } from "./backup";

const INFO = {
  backup_format_version: "1.0",
  table_count: 2,
  total_rows: 3,
  tables: { accounts: 1, projects: 2 },
  excluded_tables: ["auth_sessions"],
};

function mockResponse(overrides: Partial<Response> & { headerMap?: Record<string, string> } = {}): Response {
  const headerMap = overrides.headerMap ?? {};
  return {
    ok: true,
    status: 200,
    json: vi.fn().mockResolvedValue(INFO),
    blob: vi.fn().mockResolvedValue(new Blob(["archive-bytes"])),
    headers: { get: (name: string) => headerMap[name.toLowerCase()] ?? null },
    ...overrides,
  } as unknown as Response;
}

describe("backup API", () => {
  let anchor: { href: string; download: string; click: ReturnType<typeof vi.fn>; remove: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    vi.restoreAllMocks();
    anchor = { href: "", download: "", click: vi.fn(), remove: vi.fn() };
    vi.spyOn(document, "createElement").mockReturnValue(anchor as unknown as HTMLAnchorElement);
    vi.spyOn(document.body, "appendChild").mockImplementation((node) => node);
    URL.createObjectURL = vi.fn().mockReturnValue("blob:fake-url");
    URL.revokeObjectURL = vi.fn();
  });

  describe("fetchBackupInfo", () => {
    it("returns the row counts a backup would capture", async () => {
      global.fetch = vi.fn().mockResolvedValue(mockResponse());

      await expect(fetchBackupInfo()).resolves.toEqual(INFO);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/workspace/backup/info"),
        expect.objectContaining({ method: "GET", credentials: "include" })
      );
    });

    it("surfaces the server's reason when the request is rejected", async () => {
      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({ ok: false, status: 403, json: vi.fn().mockResolvedValue({ detail: "Admin role required" }) })
      );

      await expect(fetchBackupInfo()).rejects.toThrow("Admin role required");
    });

    it("falls back to the status code when the error body is not JSON", async () => {
      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({ ok: false, status: 500, json: vi.fn().mockRejectedValue(new Error("not json")) })
      );

      await expect(fetchBackupInfo()).rejects.toThrow("500");
    });
  });

  describe("downloadBackup", () => {
    it("saves the archive under the filename the server chose", async () => {
      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({
          headerMap: { "content-disposition": 'attachment; filename="actionsmanager-backup-2026-08-11.tar.gz"' },
        })
      );

      const filename = await downloadBackup();

      expect(filename).toBe("actionsmanager-backup-2026-08-11.tar.gz");
      expect(anchor.download).toBe("actionsmanager-backup-2026-08-11.tar.gz");
      expect(anchor.href).toBe("blob:fake-url");
      expect(anchor.click).toHaveBeenCalledTimes(1);
    });

    it("releases the object URL so the blob is not retained", async () => {
      global.fetch = vi.fn().mockResolvedValue(mockResponse({ headerMap: {} }));

      await downloadBackup();

      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
      expect(anchor.remove).toHaveBeenCalledTimes(1);
    });

    it("uses a default filename when the server sends no content-disposition", async () => {
      global.fetch = vi.fn().mockResolvedValue(mockResponse({ headerMap: {} }));

      await expect(downloadBackup()).resolves.toBe("actionsmanager-backup.tar.gz");
    });

    it("does not trigger a download when the request fails", async () => {
      global.fetch = vi.fn().mockResolvedValue(
        mockResponse({ ok: false, status: 403, json: vi.fn().mockResolvedValue({ detail: "Admin role required" }) })
      );

      await expect(downloadBackup()).rejects.toThrow("Admin role required");
      expect(anchor.click).not.toHaveBeenCalled();
      expect(URL.createObjectURL).not.toHaveBeenCalled();
    });
  });
});
