import apiClient from "./apiClient";

export interface DriftSettings {
  sweep_enabled: boolean;
  recheck_interval_minutes: number;
  batch_size: number;
  poll_interval_seconds: number;
}

// Mirrors the backend defaults, so a failed read still renders a usable form
// and the per-project "inherit" label still names a real interval.
export const DEFAULT_DRIFT_SETTINGS: DriftSettings = {
  sweep_enabled: true,
  recheck_interval_minutes: 15,
  batch_size: 5,
  poll_interval_seconds: 60,
};

// The intervals the backend accepts. Keep in step with
// ALLOWED_DRIFT_INTERVAL_MINUTES in backend/projects.py — anything else is
// rejected with a 422.
export const DRIFT_INTERVAL_OPTIONS: ReadonlyArray<{ value: number; label: string }> = [
  { value: 15, label: "Every 15 minutes" },
  { value: 30, label: "Every 30 minutes" },
  { value: 60, label: "Every hour" },
  { value: 360, label: "Every 6 hours" },
  { value: 1440, label: "Daily" },
];

export const formatDriftInterval = (minutes: number): string =>
  DRIFT_INTERVAL_OPTIONS.find((option) => option.value === minutes)?.label ?? `Every ${minutes} minutes`;

/** Throws on failure. A caller that only needs the value for display can fall
 *  back to DEFAULT_DRIFT_SETTINGS, but the settings form must not: saving a
 *  form populated with defaults would overwrite the real stored settings. */
export const fetchDriftSettings = async (): Promise<DriftSettings> => {
  const response = await apiClient.get<DriftSettings>("/api/drift/settings");
  return response.data;
};

/** FastAPI returns `detail` as a string for HTTPException, but as an array of
 *  error objects for request-validation failures. Stringifying the array
 *  yields "[object Object]", so pull the messages out. */
const describeError = (error: any): string | undefined => {
  const detail = error.response?.data?.detail;
  if (!detail) return undefined;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => item?.msg).filter(Boolean);
    if (messages.length > 0) return messages.join("; ");
  }
  return undefined;
};

export const saveDriftSettings = async (
  settings: DriftSettings
): Promise<{ success: boolean; message?: string }> => {
  try {
    await apiClient.put("/api/drift/settings", settings);
    return { success: true };
  } catch (error: any) {
    return { success: false, message: describeError(error) || "Network error" };
  }
};
