import React from "react";
import {
  PROJECT_COLOR_OPTIONS,
  PROJECT_COLOR_STYLES,
  getProjectColorOptionsForType,
  type ProjectColorKey,
} from "../utils/projectColors";
import { cn } from "../lib/utils";

interface ProjectColorSelectorProps {
  value: ProjectColorKey;
  onChange: (color: ProjectColorKey) => void;
  projectType?: "standard" | "rwx";
  disabled?: boolean;
  name?: string;
  className?: string;
}

const ProjectColorSelector: React.FC<ProjectColorSelectorProps> = ({
  value,
  onChange,
  projectType = "standard",
  disabled = false,
  name = "projectColor",
  className,
}) => {
  const typeOptions = getProjectColorOptionsForType(projectType);
  // Keep a grandfathered (pre-restriction) color visible while it is still selected.
  const options = typeOptions.some((option) => option.key === value)
    ? typeOptions
    : PROJECT_COLOR_OPTIONS.filter(
        (option) => option.key === value || typeOptions.some((allowed) => allowed.key === option.key),
      );
  return (
    <div className={className}>
      <div className="text-sm font-semibold text-gray-900 dark:text-white">Project Color</div>
      <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">Used as a visual accent on project cards.</p>
      <div
        className={cn(
          "mt-3 flex flex-wrap gap-2",
          disabled ? "pointer-events-none opacity-60" : null,
        )}
        role="radiogroup"
        aria-label="Project Color"
      >
        {options.map((option) => {
          const isSelected = value === option.key;
          const styles = PROJECT_COLOR_STYLES[option.key];
          return (
            <label
              key={option.key}
              className={cn(
                "relative inline-flex cursor-pointer items-center justify-center rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800/60 p-2 transition focus-within:ring-2 focus-within:ring-blue-400/50",
                isSelected ? "border-gray-400 dark:border-slate-500" : "hover:border-gray-400 dark:hover:border-slate-500",
              )}
            >
              <input
                type="radio"
                name={name}
                value={option.key}
                checked={isSelected}
                onChange={() => onChange(option.key)}
                className="peer sr-only"
                aria-label={option.label}
                disabled={disabled}
              />
              <span
                aria-hidden="true"
                className={cn(
                  "relative h-6 w-6 rounded-full ring-1 ring-black/10 dark:ring-white/10 ring-offset-2 ring-offset-white dark:ring-offset-slate-950 peer-focus-visible:outline-none peer-focus-visible:ring-2",
                  styles.swatch,
                  styles.focusRing,
                  isSelected ? cn("ring-2", styles.selectedRing) : null,
                )}
              >
                {isSelected && (
                  <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-white">
                    ✓
                  </span>
                )}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
};

export default ProjectColorSelector;
