export const PROJECT_COLOR_KEYS = [
  'blue',
  'purple',
  'green',
  'amber',
  'rose',
  'cyan',
  'slate',
  'orange',
  'sky',
] as const;

export type ProjectColorKey = (typeof PROJECT_COLOR_KEYS)[number];

// Purple and green are reserved for Reusable Workflow (rwx) projects; Caller
// Workflow (standard) projects may use the remaining colors.
export const RWX_ONLY_PROJECT_COLOR_KEYS: readonly ProjectColorKey[] = ['purple', 'green'];

export const PROJECT_COLOR_OPTIONS: Array<{ key: ProjectColorKey; label: string }> = [
  { key: 'blue', label: 'Blue' },
  { key: 'purple', label: 'Purple' },
  { key: 'green', label: 'Green' },
  { key: 'amber', label: 'Amber' },
  { key: 'rose', label: 'Rose' },
  { key: 'cyan', label: 'Cyan' },
  { key: 'slate', label: 'Slate' },
  { key: 'orange', label: 'Orange' },
  { key: 'sky', label: 'Sky' },
];

export function getProjectColorOptionsForType(
  projectType: 'standard' | 'rwx',
): Array<{ key: ProjectColorKey; label: string }> {
  if (projectType === 'rwx') return PROJECT_COLOR_OPTIONS.filter((option) => RWX_ONLY_PROJECT_COLOR_KEYS.includes(option.key));
  return PROJECT_COLOR_OPTIONS.filter((option) => !RWX_ONLY_PROJECT_COLOR_KEYS.includes(option.key));
}

export function normalizeProjectColorKey(value: unknown): ProjectColorKey {
  if (typeof value !== 'string') return 'blue';
  const normalized = value.trim().toLowerCase();
  return (PROJECT_COLOR_KEYS as readonly string[]).includes(normalized) ? (normalized as ProjectColorKey) : 'blue';
}

export const PROJECT_COLOR_STYLES: Record<
  ProjectColorKey,
  {
    borderLeft: string;
    dot: string;
    icon: string;
    iconBg: string;
    swatch: string;
    focusRing: string;
    selectedRing: string;
  }
> = {
  blue: {
    borderLeft: 'border-l-blue-500 dark:border-l-blue-400',
    dot: 'bg-blue-500 dark:bg-blue-400',
    icon: 'text-blue-500 dark:text-blue-400',
    iconBg: 'bg-blue-500/10 dark:bg-blue-400/10',
    swatch: 'bg-blue-500 dark:bg-blue-400',
    focusRing: 'peer-focus-visible:ring-blue-400/40',
    selectedRing: 'ring-blue-400/35',
  },
  purple: {
    borderLeft: 'border-l-purple-500 dark:border-l-purple-400',
    dot: 'bg-purple-500 dark:bg-purple-400',
    icon: 'text-purple-500 dark:text-purple-400',
    iconBg: 'bg-purple-500/10 dark:bg-purple-400/10',
    swatch: 'bg-purple-500 dark:bg-purple-400',
    focusRing: 'peer-focus-visible:ring-purple-400/40',
    selectedRing: 'ring-purple-400/35',
  },
  green: {
    borderLeft: 'border-l-emerald-500 dark:border-l-emerald-400',
    dot: 'bg-emerald-500 dark:bg-emerald-400',
    icon: 'text-emerald-500 dark:text-emerald-400',
    iconBg: 'bg-emerald-500/10 dark:bg-emerald-400/10',
    swatch: 'bg-emerald-500 dark:bg-emerald-400',
    focusRing: 'peer-focus-visible:ring-emerald-400/40',
    selectedRing: 'ring-emerald-400/35',
  },
  amber: {
    borderLeft: 'border-l-amber-500 dark:border-l-amber-400',
    dot: 'bg-amber-500 dark:bg-amber-400',
    icon: 'text-amber-500 dark:text-amber-400',
    iconBg: 'bg-amber-500/10 dark:bg-amber-400/10',
    swatch: 'bg-amber-500 dark:bg-amber-400',
    focusRing: 'peer-focus-visible:ring-amber-400/40',
    selectedRing: 'ring-amber-400/35',
  },
  rose: {
    borderLeft: 'border-l-rose-500 dark:border-l-rose-400',
    dot: 'bg-rose-500 dark:bg-rose-400',
    icon: 'text-rose-500 dark:text-rose-400',
    iconBg: 'bg-rose-500/10 dark:bg-rose-400/10',
    swatch: 'bg-rose-500 dark:bg-rose-400',
    focusRing: 'peer-focus-visible:ring-rose-400/40',
    selectedRing: 'ring-rose-400/35',
  },
  cyan: {
    borderLeft: 'border-l-cyan-500 dark:border-l-cyan-400',
    dot: 'bg-cyan-500 dark:bg-cyan-400',
    icon: 'text-cyan-500 dark:text-cyan-400',
    iconBg: 'bg-cyan-500/10 dark:bg-cyan-400/10',
    swatch: 'bg-cyan-500 dark:bg-cyan-400',
    focusRing: 'peer-focus-visible:ring-cyan-400/40',
    selectedRing: 'ring-cyan-400/35',
  },
  slate: {
    borderLeft: 'border-l-slate-500 dark:border-l-slate-400',
    dot: 'bg-slate-500 dark:bg-slate-400',
    icon: 'text-slate-500 dark:text-slate-400',
    iconBg: 'bg-slate-500/10 dark:bg-slate-400/10',
    swatch: 'bg-slate-500 dark:bg-slate-400',
    focusRing: 'peer-focus-visible:ring-slate-400/40',
    selectedRing: 'ring-slate-400/35',
  },
  orange: {
    borderLeft: 'border-l-orange-500 dark:border-l-orange-400',
    dot: 'bg-orange-500 dark:bg-orange-400',
    icon: 'text-orange-500 dark:text-orange-400',
    iconBg: 'bg-orange-500/10 dark:bg-orange-400/10',
    swatch: 'bg-orange-500 dark:bg-orange-400',
    focusRing: 'peer-focus-visible:ring-orange-400/40',
    selectedRing: 'ring-orange-400/35',
  },
  sky: {
    borderLeft: 'border-l-sky-500 dark:border-l-sky-400',
    dot: 'bg-sky-500 dark:bg-sky-400',
    icon: 'text-sky-500 dark:text-sky-400',
    iconBg: 'bg-sky-500/10 dark:bg-sky-400/10',
    swatch: 'bg-sky-500 dark:bg-sky-400',
    focusRing: 'peer-focus-visible:ring-sky-400/40',
    selectedRing: 'ring-sky-400/35',
  },
};
