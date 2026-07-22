/* eslint-disable no-restricted-syntax -- Legacy: TODO migrate inline styles to Tailwind CSS classes */
import React from 'react';

/**
 * Known workflow status keys that map to a specific visual style and label.
 * Unknown string values are accepted; if no `label` override is provided they
 * render nothing (the component returns `null`).  Provide an explicit `label`
 * prop when you need to render a badge for a custom or future status value.
 */
export type WorkflowStatus =
  | 'new'
  | 'committed_locally'
  | 'under_review'
  | 'synced_with_github'
  | 'linked'
  | 'draft'
  | 'unsaved'
  | string;

interface StatusConfig {
  /** Default user-facing label for this status */
  label: string;
  /** Color of the small leading dot */
  dot: string;
  /** Very subtle background tint */
  background: string;
  /** Muted border color */
  border: string;
  /** Subdued text color */
  color: string;
}

/**
 * Centralized status → visual style mapping.
 *
 * Color palette uses low-opacity fills so badges blend into dark-mode cards
 * without high-contrast pastel backgrounds.
 */
export const WORKFLOW_STATUS_CONFIG: Record<string, StatusConfig> = {
  new: {
    label: 'New Local',
    dot: '#60a5fa',                         // blue-400
    background: 'rgba(59, 130, 246, 0.08)',
    border: 'rgba(59, 130, 246, 0.30)',
    color: '#93c5fd',                        // blue-300
  },
  committed_locally: {
    label: 'Committed Locally',
    dot: '#60a5fa',                         // blue-400
    background: 'rgba(59, 130, 246, 0.08)',
    border: 'rgba(59, 130, 246, 0.30)',
    color: '#93c5fd',                        // blue-300
  },
  under_review: {
    label: 'Under Review',
    dot: '#c084fc',                         // purple-400
    background: 'rgba(168, 85, 247, 0.08)',
    border: 'rgba(168, 85, 247, 0.30)',
    color: '#d8b4fe',                        // purple-300
  },
  synced_with_github: {
    label: 'Synced',
    dot: '#4ade80',                         // green-400
    background: 'rgba(34, 197, 94, 0.08)',
    border: 'rgba(34, 197, 94, 0.30)',
    color: '#86efac',                        // green-300
  },
  linked: {
    label: 'Linked',
    dot: '#a78bfa',                         // violet-400
    background: 'rgba(139, 92, 246, 0.08)',
    border: 'rgba(139, 92, 246, 0.30)',
    color: '#c4b5fd',                        // violet-300
  },
  draft: {
    label: 'Draft',
    dot: '#60a5fa',                         // blue-400
    background: 'rgba(59, 130, 246, 0.08)',
    border: 'rgba(59, 130, 246, 0.30)',
    color: '#93c5fd',                        // blue-300
  },
  unsaved: {
    label: 'Unsaved',
    dot: '#fbbf24',                         // amber-400
    background: 'rgba(245, 158, 11, 0.08)',
    border: 'rgba(245, 158, 11, 0.30)',
    color: '#fcd34d',                        // amber-300
  },
};

/** Neutral fallback style for unknown or future status values. */
export const WORKFLOW_STATUS_FALLBACK: StatusConfig = {
  label: '',
  dot: '#94a3b8',                           // slate-400
  background: 'rgba(148, 163, 184, 0.08)',
  border: 'rgba(148, 163, 184, 0.30)',
  color: '#cbd5e1',                          // slate-300
};

interface WorkflowStatusBadgeProps {
  /**
   * The workflow status key (e.g. 'new', 'committed_locally').
   * Determines the dot color, background, and border style.
   */
  status: WorkflowStatus;
  /**
   * Override the default label derived from `status`.
   * Use this when the display text differs from the canonical label
   * (e.g. showing "Draft" instead of "Committed Locally" in the editor header).
   */
  label?: string;
  /** Forwarded to the wrapping element as data-testid. */
  'data-testid'?: string;
  /** Additional CSS class names. */
  className?: string;
  /** Additional inline styles merged on top of the computed badge styles. */
  style?: React.CSSProperties;
}

/**
 * WorkflowStatusBadge – compact, minimal pill badge for workflow lifecycle states.
 *
 * Designed for the ActionsManager dark theme: uses very subtle tinted backgrounds,
 * muted borders, a small leading dot, and subdued text so the badge reads as
 * secondary information relative to the workflow filename.
 *
 * Usage:
 * ```tsx
 * <WorkflowStatusBadge status="synced_with_github" />
 * // → shows "Synced" with green dot/border
 *
 * <WorkflowStatusBadge status="committed_locally" label="Draft" />
 * // → shows "Draft" with blue dot/border
 * ```
 */
const WorkflowStatusBadge: React.FC<WorkflowStatusBadgeProps> = ({
  status,
  label,
  'data-testid': dataTestId,
  className,
  style,
}) => {
  const config = WORKFLOW_STATUS_CONFIG[status.toLowerCase()] ?? WORKFLOW_STATUS_FALLBACK;
  const displayLabel = label !== undefined ? label : config.label;

  // Unknown status with no label override → render nothing.
  if (!displayLabel) return null;

  return (
    <span
      className={className}
      data-testid={dataTestId ?? 'workflow-status-badge'}
      title={displayLabel}
      aria-label={`Status: ${displayLabel}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.375rem',
        padding: '0.125rem 0.5rem',
        borderRadius: '0.375rem',
        border: `1px solid ${config.border}`,
        backgroundColor: config.background,
        color: config.color,
        fontSize: '0.7rem',
        fontWeight: 500,
        whiteSpace: 'nowrap',
        lineHeight: 1.4,
        userSelect: 'none',
        ...style,
      }}
    >
      {/* Small leading status dot */}
      <span
        aria-hidden="true"
        style={{
          width: '0.375rem',
          height: '0.375rem',
          borderRadius: '9999px',
          backgroundColor: config.dot,
          flexShrink: 0,
        }}
      />
      {displayLabel}
    </span>
  );
};

export default WorkflowStatusBadge;
