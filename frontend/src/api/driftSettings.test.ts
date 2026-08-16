vi.mock("./apiClient", () => ({
  __esModule: true,
  default: { get: vi.fn(), put: vi.fn() },
}));

import apiClient from "./apiClient";
import { fetchDriftSettings, saveDriftSettings, DEFAULT_DRIFT_SETTINGS } from "./driftSettings";

import type { MockedFunction } from 'vitest';
const mockGet = apiClient.get as MockedFunction<typeof apiClient.get>;
const mockPut = apiClient.put as MockedFunction<typeof apiClient.put>;

describe("driftSettings api", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("fetch propagates failure rather than returning defaults", async () => {
    // The settings form must be able to tell "couldn't load" from "loaded 15",
    // or saving would overwrite the stored values with defaults.
    mockGet.mockRejectedValue(new Error("boom"));

    await expect(fetchDriftSettings()).rejects.toThrow("boom");
  });

  test("a string detail is passed through", async () => {
    mockPut.mockRejectedValue({ response: { data: { detail: "Insufficient permissions" } } });

    expect(await saveDriftSettings(DEFAULT_DRIFT_SETTINGS)).toEqual({
      success: false,
      message: "Insufficient permissions",
    });
  });

  test("a validation detail array becomes readable text", async () => {
    // FastAPI returns an array of error objects for 422s; String() on that
    // yields "[object Object]".
    mockPut.mockRejectedValue({
      response: {
        data: {
          detail: [
            { loc: ["body", "batch_size"], msg: "Input should be greater than 0" },
            { loc: ["body", "poll_interval_seconds"], msg: "Input should be greater than 9" },
          ],
        },
      },
    });

    const result = await saveDriftSettings(DEFAULT_DRIFT_SETTINGS);

    expect(result.success).toBe(false);
    expect(result.message).toBe(
      "Input should be greater than 0; Input should be greater than 9",
    );
    expect(result.message).not.toContain("[object Object]");
  });

  test("an unrecognised failure falls back to a network message", async () => {
    mockPut.mockRejectedValue(new Error("offline"));

    expect(await saveDriftSettings(DEFAULT_DRIFT_SETTINGS)).toEqual({
      success: false,
      message: "Network error",
    });
  });
});
