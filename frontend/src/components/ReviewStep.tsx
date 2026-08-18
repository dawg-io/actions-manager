import React from 'react';
import { Button } from './ui/button';
import { Checkbox } from './ui/checkbox';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { PREFIX_MODE_CONFIG, NO_PREFIX_MODE_CONFIG } from '../utils/prefixModeConfig';

const FINAL_WIZARD_STEP = 3;
const RESOURCE_PREFIX_TEMPLATE = 'AM_{PROJECT_CODE}_';

/** Disclosure marker: a custom key forces the section open, so it says so. */
function advancedOptionsIndicator(useCustomKey: boolean, visible: boolean): string {
  if (useCustomKey) return 'Custom key enabled';
  return visible ? '−' : '+';
}

export interface ReviewStepProps {
  readonly usePrefix: boolean | null;
  readonly setUsePrefix: (use: boolean) => void;
  readonly advancedOptionsVisible: boolean;
  readonly setAdvancedOptionsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  readonly useCustomKey: boolean;
  readonly setUseCustomKey: (use: boolean) => void;
  readonly projectKey: string;
  readonly setProjectKey: (key: string) => void;
  readonly isCreating: boolean;
  readonly formIsValid: boolean;
  readonly handleCreateProject: () => void;
}

/** Wizard step 3: resource naming mode, advanced options and create. */
const ReviewStep: React.FC<ReviewStepProps> = ({
  usePrefix,
  setUsePrefix,
  advancedOptionsVisible,
  setAdvancedOptionsOpen,
  useCustomKey,
  setUseCustomKey,
  projectKey,
  setProjectKey,
  isCreating,
  formIsValid,
  handleCreateProject,
}) => (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
          Step {FINAL_WIZARD_STEP} of {FINAL_WIZARD_STEP}
        </p>
        <h3 className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">
          Resource Naming and Review
        </h3>
        <p className="mt-2 text-sm text-gray-600 dark:text-slate-300">
          Pick how Actions Manager names generated resources, then review the project before creating it.
        </p>
      </div>

      <div>
        <Label className="mb-3 block text-sm font-semibold text-gray-900 dark:text-white">Resource Naming Mode:</Label>
        <div className="grid gap-3 md:grid-cols-2" data-testid="naming-mode-selector">
          <label
            className={`flex cursor-pointer gap-3 rounded-lg border p-4 transition focus-within:ring-2 focus-within:ring-emerald-400 ${
              usePrefix === true
                ? "border-emerald-400/70 bg-emerald-500/10"
                : "border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 hover:border-emerald-400/60"
            }`}
            aria-label={`${PREFIX_MODE_CONFIG.label} - Recommended`}
          >
            <input
              type="radio"
              name="resourceNamingMode"
              value="prefix"
              checked={usePrefix === true}
              onChange={() => setUsePrefix(true)}
              className="mt-1"
            />
            <span className="flex-1">
              <span className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
                {PREFIX_MODE_CONFIG.label} - Recommended
                {usePrefix === true && <span className="ml-auto text-emerald-600 dark:text-emerald-400">✓</span>}
              </span>
              <span className="mt-1 block text-xs leading-5 text-gray-600 dark:text-slate-300">
                Adds an <code>{RESOURCE_PREFIX_TEMPLATE}</code> prefix to generated resources to avoid naming conflicts.
              </span>
            </span>
          </label>

          <label
            className={`flex cursor-pointer gap-3 rounded-lg border p-4 transition focus-within:ring-2 focus-within:ring-amber-400 ${
              usePrefix === false
                ? "border-amber-400/70 bg-amber-500/10"
                : "border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 hover:border-amber-400/60"
            }`}
            aria-label={NO_PREFIX_MODE_CONFIG.label}
          >
            <input
              type="radio"
              name="resourceNamingMode"
              value="no-prefix"
              checked={usePrefix === false}
              onChange={() => setUsePrefix(false)}
              className="mt-1"
            />
            <span className="flex-1">
              <span className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
                {NO_PREFIX_MODE_CONFIG.label}
                {usePrefix === false && <span className="ml-auto text-amber-700 dark:text-amber-300">✓</span>}
              </span>
              <span className="mt-1 block text-xs leading-5 text-gray-600 dark:text-slate-300">
                Advanced option. Keeps names unchanged, but increases the chance of conflicts.
              </span>
            </span>
          </label>
        </div>
        {usePrefix === false && (
          <div className="mt-3 rounded-lg border border-amber-400/60 bg-amber-500/10 p-3 text-sm text-amber-900 dark:text-amber-100">
            <strong>No Prefix Mode is intended for advanced users.</strong>
            <p className="mt-1 text-xs leading-5">
              Resource names must be unique, and Actions Manager will store secret and environment variable names locally for tracking. Secret values must remain only in GitHub.
            </p>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60">
        <button
          type="button"
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-gray-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 disabled:cursor-default disabled:opacity-80"
          aria-expanded={advancedOptionsVisible}
          aria-label={
            useCustomKey
              ? "Advanced Options expanded because custom project key is enabled"
              : "Advanced Options"
          }
          disabled={useCustomKey}
          onClick={() => setAdvancedOptionsOpen((open) => !open)}
        >
          Advanced Options{' '}
          <span aria-hidden="true">
            {advancedOptionsIndicator(useCustomKey, advancedOptionsVisible)}
          </span>
        </button>
        {advancedOptionsVisible && (
          <div className="space-y-3 border-t border-gray-200 dark:border-slate-700 p-4">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="use-custom-key"
                checked={useCustomKey}
                onCheckedChange={(checked) => {
                  const enabled = checked as boolean;
                  setUseCustomKey(enabled);
                  if (enabled) setAdvancedOptionsOpen(true);
                }}
              />
              <Label htmlFor="use-custom-key" className="cursor-pointer text-gray-900 dark:text-white">
                Use custom project key
              </Label>
            </div>

            {useCustomKey && (
              <div>
                <Label htmlFor="project-key" className="mb-2 block text-sm font-medium text-gray-900 dark:text-white">
                  Project Key
                </Label>
                <Input
                  id="project-key"
                  type="text"
                  placeholder="Enter project key (2-10 chars, letters/numbers)"
                  value={projectKey}
                  onChange={(e) => setProjectKey(e.target.value)}
                  maxLength={10}
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">
                  Use 2-10 letters or numbers. Existing server-side validation is unchanged.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      <Button
        data-testid="create-project-button"
        onClick={handleCreateProject}
        disabled={isCreating || !formIsValid}
        className="w-full"
      >
        {isCreating ? "⏳ Creating..." : "🚀 Create Project"}
      </Button>
    </div>
);

export default ReviewStep;
