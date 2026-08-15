import React, { useCallback, useEffect, useState } from "react";
import { Button, Checkbox, Input } from "./ui";
import {
  fetchDriftSettings,
  saveDriftSettings,
  DriftSettings,
  DEFAULT_DRIFT_SETTINGS,
  DRIFT_INTERVAL_OPTIONS,
} from "../api/driftSettings";

interface WorkspaceDriftSettingsProps {
  readonly currentUserRole?: string;
}

const inputSelectClassName =
  "flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-sm transition-colors border-input-border bg-input-background-color text-text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-input-focus dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100";

const WorkspaceDriftSettings: React.FC<WorkspaceDriftSettingsProps> = ({ currentUserRole }) => {
  // undefined means the role has not arrived yet. Treating that as "not an
  // admin" flashes an access-denied message at an actual admin on every
  // refresh, which reads as having lost the role.
  const roleKnown = currentUserRole !== undefined;
  const isAdmin = currentUserRole === "admin";

  const [settings, setSettings] = useState<DriftSettings>(DEFAULT_DRIFT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const loadSettings = useCallback(async () => {
    try {
      setSettings(await fetchDriftSettings());
      setLoadFailed(false);
    } catch {
      // Saving a form still showing defaults would overwrite the real stored
      // settings with them, so refuse to show an editable form at all.
      setLoadFailed(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (isAdmin) {
      void loadSettings();
    }
  }, [isAdmin, loadSettings]);

  const update = <K extends keyof DriftSettings>(key: K, value: DriftSettings[K]): void => {
    setSettings((current) => ({ ...current, [key]: value }));
    setMessage(null);
  };

  /** Number("") is 0, so clearing the field to retype a value would submit 0
   *  and be rejected by the backend's lower bound. Keep the previous number
   *  until something parseable is typed. */
  const updateNumber = (key: "recheck_interval_minutes" | "batch_size" | "poll_interval_seconds",
                        raw: string): void => {
    const parsed = Number(raw);
    if (raw.trim() === "" || Number.isNaN(parsed)) return;
    update(key, parsed);
  };

  const handleSave = async (): Promise<void> => {
    setSaving(true);
    setMessage(null);
    const result = await saveDriftSettings(settings);
    if (result.success) {
      setMessage({ text: "Drift settings saved. They apply from the next check.", type: "success" });
      await loadSettings();
    } else {
      setMessage({ text: result.message || "Could not save drift settings", type: "error" });
    }
    setSaving(false);
  };

  if (!roleKnown) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-xl font-semibold text-text-primary dark:text-text-primary-dark mb-2">Drift Settings</h1>
        <p className="text-sm text-text-secondary dark:text-secondary-dark">Checking your access…</p>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-xl font-semibold text-text-primary dark:text-text-primary-dark mb-2">Drift Settings</h1>
        <p className="text-sm text-text-secondary dark:text-secondary-dark">
          Only workspace admins can configure drift checking.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary dark:text-text-primary-dark mb-2">Drift Settings</h1>
        <p className="text-sm text-text-secondary dark:text-secondary-dark">
          ActionsManager re-checks projects in the background so none can sit showing “in sync”
          while GitHub has moved on. These are the workspace defaults — any project can override
          the schedule, or switch its own checks off, under Project Configs → Drift Detection.
        </p>
      </div>

      {loading && <p className="text-sm text-text-secondary dark:text-secondary-dark">Loading…</p>}

      {!loading && loadFailed && (
        <div className="space-y-3" data-testid="drift-settings-load-error">
          <p className="text-sm text-red-600 dark:text-red-400">
            Could not load the current drift settings, so they are not shown — saving now would
            overwrite them.
          </p>
          <Button onClick={() => { setLoading(true); void loadSettings(); }}>Retry</Button>
        </div>
      )}

      {!loading && !loadFailed && (
        <div className="space-y-5" data-testid="drift-settings-form">
          <label className="flex items-start gap-3">
            <Checkbox
              checked={settings.sweep_enabled}
              onCheckedChange={(checked) => update("sweep_enabled", checked === true)}
              data-testid="drift-sweep-enabled"
            />
            <span className="text-sm text-text-primary dark:text-text-primary-dark">
              <span className="block">Check projects for drift automatically</span>
              <span className="block text-xs text-text-secondary dark:text-secondary-dark">
                With this off, drift only updates when someone presses Check Now.
              </span>
            </span>
          </label>

          <div>
            <label
              htmlFor="drift-recheck-interval"
              className="block text-sm font-medium text-text-primary dark:text-text-primary-dark mb-1"
            >
              Default check schedule
            </label>
            <select
              id="drift-recheck-interval"
              className={inputSelectClassName}
              value={settings.recheck_interval_minutes}
              disabled={!settings.sweep_enabled}
              onChange={(e) => update("recheck_interval_minutes", Number(e.target.value))}
            >
              {DRIFT_INTERVAL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-text-secondary dark:text-secondary-dark">
              How long a project stays fresh before it is due for another check.
            </p>
          </div>

          <div>
            <label
              htmlFor="drift-batch-size"
              className="block text-sm font-medium text-text-primary dark:text-text-primary-dark mb-1"
            >
              Projects checked per tick
            </label>
            <Input
              id="drift-batch-size"
              type="number"
              min={1}
              max={50}
              value={settings.batch_size}
              disabled={!settings.sweep_enabled}
              onChange={(e) => updateNumber("batch_size", e.target.value)}
            />
            <p className="mt-1 text-xs text-text-secondary dark:text-secondary-dark">
              Caps how much work one tick can do, spreading load instead of checking everything at
              once. 1–50.
            </p>
          </div>

          <div>
            <label
              htmlFor="drift-poll-seconds"
              className="block text-sm font-medium text-text-primary dark:text-text-primary-dark mb-1"
            >
              Seconds between ticks
            </label>
            <Input
              id="drift-poll-seconds"
              type="number"
              min={10}
              max={3600}
              value={settings.poll_interval_seconds}
              disabled={!settings.sweep_enabled}
              onChange={(e) => updateNumber("poll_interval_seconds", e.target.value)}
            />
            <p className="mt-1 text-xs text-text-secondary dark:text-secondary-dark">
              How often the worker wakes to look for projects that are due. 10–3600.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={handleSave} disabled={saving} data-testid="drift-settings-save">
              {saving ? "Saving…" : "Save"}
            </Button>
            {message && (
              <output
                aria-live="polite"
                className={`text-sm ${
                  message.type === "success"
                    ? "text-green-600 dark:text-green-400"
                    : "text-red-600 dark:text-red-400"
                }`}
              >
                {message.text}
              </output>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default WorkspaceDriftSettings;
