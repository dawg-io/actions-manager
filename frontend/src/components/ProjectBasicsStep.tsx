import React from 'react';
import { Input } from './ui/input';
import { Label } from './ui/label';
import ProjectColorSelector from './ProjectColorSelector';
import { PROJECT_TYPE_CONFIG, ProjectType } from '../utils/projectTypeConfig';
import type { ProjectColorKey } from '../utils/projectColors';
import { getDocsUrl } from '../help/helpLinks';
import {
  SELF_HOSTED_BETA_CALLER_LIMIT,
  SELF_HOSTED_BETA_RWX_LIMIT,
} from '../utils/accountTier';

const FINAL_WIZARD_STEP = 3;

const getProjectTypeLabel = (type: ProjectType): string => PROJECT_TYPE_CONFIG[type].label;

/** Beta limit message for a type, or null when the type is still available. */
function betaLimitMessage(type: ProjectType, callerReached: boolean, rwxReached: boolean): string | null {
  if (type === 'standard' && callerReached) {
    return `Beta limit reached (${SELF_HOSTED_BETA_CALLER_LIMIT}/${SELF_HOSTED_BETA_CALLER_LIMIT} Caller Workflow Projects).`;
  }
  if (type === 'rwx' && rwxReached) {
    return `Beta limit reached (${SELF_HOSTED_BETA_RWX_LIMIT}/${SELF_HOSTED_BETA_RWX_LIMIT} Reusable Workflow Projects).`;
  }
  return null;
}

/** Card styling for a selectable option: disabled, selected, or neither. */
export function optionCardClass(isDisabled: boolean, isSelected: boolean, disabledClass: string, selectedClass: string, restingClass: string): string {
  if (isDisabled) return disabledClass;
  return isSelected ? selectedClass : restingClass;
}

export interface ProjectBasicsStepProps {
  readonly projectName: string;
  readonly setProjectName: (name: string) => void;
  readonly setProjectNameTouched: (touched: boolean) => void;
  readonly projectNameDescriptionIds: string;
  readonly showProjectNameError: boolean;
  readonly projectNameError: string | null;
  readonly projectType: ProjectType;
  readonly setProjectType: (type: ProjectType) => void;
  readonly projectColor: ProjectColorKey;
  readonly setProjectColor: (color: ProjectColorKey) => void;
  readonly betaCallerLimitReached: boolean;
  readonly betaRwxLimitReached: boolean;
}

/** Wizard step 1: name, project type and colour. */
const ProjectBasicsStep: React.FC<ProjectBasicsStepProps> = ({
  projectName,
  setProjectName,
  setProjectNameTouched,
  projectNameDescriptionIds,
  showProjectNameError,
  projectNameError,
  projectType,
  setProjectType,
  projectColor,
  setProjectColor,
  betaCallerLimitReached,
  betaRwxLimitReached,
}) => (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
          Step 1 of {FINAL_WIZARD_STEP}
        </p>
        <h3 className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">
          Project Basics
        </h3>
        <p className="mt-2 text-sm text-gray-600 dark:text-slate-300">
          Start with a clear project name, then choose whether this project manages caller workflows or reusable workflows.
        </p>
      </div>

      <div className="rounded-xl border border-blue-500/40 bg-blue-500/5 p-4">
        <Label htmlFor="project-name" className="mb-2 block text-base font-semibold text-gray-900 dark:text-white">
          Project Name:
        </Label>
        <Input
          id="project-name"
          data-testid="project-name-input"
          type="text"
          placeholder="Enter project name"
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
          onBlur={() => setProjectNameTouched(true)}
          aria-describedby={projectNameDescriptionIds}
          aria-invalid={showProjectNameError}
          className="h-12 text-base"
        />
        <p id="project-name-help" className="mt-2 text-xs text-gray-500 dark:text-slate-400">
          Use a recognizable name for the workflow project you want to manage.
        </p>
        {showProjectNameError && (
          <p id="project-name-error" className="mt-2 text-xs font-medium text-red-600 dark:text-red-400">
            {projectNameError}
          </p>
        )}
      </div>

      <div>
        <Label className="mb-3 block text-sm font-semibold text-gray-900 dark:text-white">
          What type of project are you creating?
        </Label>
        <div className="grid gap-3 md:grid-cols-2" data-testid="project-type-selector">
          {(["standard", "rwx"] as ProjectType[]).map((type) => {
            const cfg = PROJECT_TYPE_CONFIG[type];
            const TypeIcon = cfg.icon;
            const isSelected = projectType === type;
            const isTypeDisabled =
              (type === "standard" && betaCallerLimitReached) ||
              (type === "rwx" && betaRwxLimitReached);
            const limitHelperText = betaLimitMessage(type, betaCallerLimitReached, betaRwxLimitReached);
            return (
              <label
                key={type}
                className={`flex gap-3 rounded-lg border p-4 transition focus-within:ring-2 focus-within:ring-blue-400 ${optionCardClass(
                  isTypeDisabled,
                  isSelected,
                  "cursor-not-allowed opacity-50 border-gray-200 dark:border-slate-700 bg-gray-100/50 dark:bg-slate-800/40",
                  "cursor-pointer border-blue-500 bg-blue-500/10",
                  "cursor-pointer border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800/60 hover:border-blue-400/60",
                )}`}
              >
                <input
                  type="radio"
                  name="projectType"
                  value={type}
                  checked={isSelected}
                  disabled={isTypeDisabled}
                  onChange={() => !isTypeDisabled && setProjectType(type)}
                  className="mt-1"
                />
                <span className="flex-1">
                  <span className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
                    <TypeIcon size={16} />
                    {getProjectTypeLabel(type)}
                    {isSelected && (
                      <span className={`ml-auto ${isTypeDisabled ? "text-gray-400 dark:text-slate-500" : "text-blue-600 dark:text-blue-400"}`}>✓</span>
                    )}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-gray-600 dark:text-slate-300">
                    {cfg.description}
                  </span>
                  {limitHelperText && (
                    <span className="mt-1 block text-xs font-medium text-amber-700 dark:text-amber-400">
                      {limitHelperText}
                    </span>
                  )}
                </span>
              </label>
            );
          })}
        </div>
        {projectType === "rwx" && (
          <p className="mt-3 text-sm text-gray-600 dark:text-slate-300">
            ℹ️ Only repositories tagged with <code>am-rwx</code> are shown in the repository step.
            Add the <code>am-rwx</code> topic to repositories that should be discoverable for reusable workflows.
          </p>
        )}
      </div>

      {projectType === "rwx" && (
        <div className="rounded-xl border border-purple-500/40 bg-purple-500/5 p-4 space-y-2">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            🔄 About Reusable Workflow Projects
          </p>
          <p className="text-sm text-gray-600 dark:text-slate-300">
            Reusable Workflow Projects are producer projects. They store shared GitHub Actions workflows that other repositories can call using <code>uses:</code>. For best results, create a dedicated GitHub repository such as <code>reusable-workflows</code>, then store reusable workflow files under <code>.github/workflows/</code>.
          </p>
          <p className="text-sm text-gray-600 dark:text-slate-300">
            Each reusable workflow file must include <code>on: workflow_call</code> as its trigger. Caller repositories reference it with a path like{" "}
            <code>your-org/reusable-workflows/.github/workflows/reusable-node-ci.yml@main</code>.
          </p>
          <a
            className="inline-block text-sm font-medium text-purple-600 dark:text-purple-400 hover:underline"
            href={getDocsUrl("reusableWorkflowSetup")}
            rel="noreferrer"
            target="_blank"
          >
            Reusable Workflow Repository Setup guide →
          </a>
        </div>
      )}

      <ProjectColorSelector value={projectColor} onChange={setProjectColor} projectType={projectType} />
    </div>
);

export default ProjectBasicsStep;
