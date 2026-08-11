/** localStorage keys and clamping for the Project Files panel's layout preferences. */

export const PROJECT_FILES_COLLAPSED_KEY = 'projectFiles.collapsed';
export const PROJECT_FILES_WIDTH_KEY = 'projectFiles.width';
export const PROJECT_FILES_CLOSED_SECTIONS_KEY = 'projectFiles.closedSections';

export const PANEL_MIN_WIDTH = 180;
export const PANEL_MAX_WIDTH = 400;
export const PANEL_DEFAULT_WIDTH = 230;

/** Storage access throws in Safari private mode and when cookies are blocked. */
export const readStoredPreference = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

export const writeStoredPreference = (key: string, value: string): void => {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* preference is best-effort; a full or unavailable store must not break the panel */
  }
};

export const clampPanelWidth = (width: number): number =>
  Math.min(PANEL_MAX_WIDTH, Math.max(PANEL_MIN_WIDTH, Math.round(width)));

/** Falls back to the default for missing, non-numeric or out-of-range stored values. */
export const readStoredPanelWidth = (): number => {
  const stored = Number(readStoredPreference(PROJECT_FILES_WIDTH_KEY));
  return Number.isFinite(stored) && stored > 0 ? clampPanelWidth(stored) : PANEL_DEFAULT_WIDTH;
};

export const readStoredClosedSections = (): Set<string> => {
  const stored = readStoredPreference(PROJECT_FILES_CLOSED_SECTIONS_KEY);
  if (!stored) return new Set();
  try {
    const parsed = JSON.parse(stored);
    return Array.isArray(parsed) ? new Set(parsed.filter((s) => typeof s === 'string')) : new Set();
  } catch {
    return new Set();
  }
};
