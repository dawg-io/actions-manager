import React, { useCallback, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { WorkflowGUI, WorkflowStep, ValidationError } from '../utils/workflowGuiConversion';
import { findSelectedStep, replaceStepAt, isFieldUnder } from '../utils/stepSelection';
import { StepSelection } from './StepSelectionContext';
import StepFields from './StepFields';
import { getStepTitle, stepRowId } from './StepCard';
import { ActionsProject } from '../api/actionsProjects';
import { ActionGroup } from '../api/actionGroups';

interface StepDetailPanelProps {
  workflow: WorkflowGUI;
  selected: StepSelection | null;
  onSelect: (selection: StepSelection | null) => void;
  onChange: (workflow: WorkflowGUI) => void;
  validationErrors: ValidationError[];
  importedActions: ActionsProject[];
  actionGroups: ActionGroup[];
}

const HEADING_ID = 'step-detail-heading';

/**
 * The selected step's editor, docked beside the job list.
 *
 * Deliberately a labelled landmark rather than a dialog: the panel is
 * non-modal, so trapping focus or dimming the list would fight the point of
 * having it open while you browse steps.
 */
const StepDetailPanel: React.FC<StepDetailPanelProps> = ({
  workflow,
  selected,
  onSelect,
  onChange,
  validationErrors,
  importedActions,
  actionGroups
}) => {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const resolved = findSelectedStep(workflow, selected);
  // Step ids repeat across jobs, so everything keyed on identity here has to
  // carry the job too - otherwise selecting job B's `step-1` after job A's
  // looks like no change at all.
  const resolvedKey = resolved && selected ? `${selected.jobId}:${resolved.step.id}` : undefined;
  const rowId = resolved && selected ? stepRowId(selected.jobId, resolved.step.id) : undefined;

  useEffect(() => {
    if (!resolvedKey) return;
    // preventScroll matters: focus() scrolls its target into view by default,
    // and the panel is its own scroll container (lg:overflow-y-auto), so
    // focusing the heading yanked both the panel and the page on every step
    // click - the row you just clicked slid out from under the cursor. The
    // focus move itself still has to happen so the panel is announced and
    // Escape reaches its handler; only the scrolling side effect is unwanted.
    headingRef.current?.focus({ preventScroll: true });
    // Below lg the panel sits under the whole job list, so selecting a step
    // would otherwise leave its fields off-screen. `nearest` is a no-op once
    // the sticky desktop column is already in view, so this needs no viewport
    // branching.
    panelRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [resolvedKey]);

  const close = useCallback((originatingRowId: string) => {
    onSelect(null);
    document.getElementById(originatingRowId)?.focus();
  }, [onSelect]);

  // Bound to the panel node rather than an onKeyDown prop: <aside> is a
  // landmark, not an interactive element, and shouldn't carry key handlers.
  useEffect(() => {
    const panel = panelRef.current;
    if (!panel || !rowId) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        close(rowId);
      }
    };
    panel.addEventListener('keydown', onKeyDown);
    return () => panel.removeEventListener('keydown', onKeyDown);
  }, [rowId, close]);

  const handleStepChange = (step: WorkflowStep) => {
    if (!resolved) return;
    onChange(replaceStepAt(workflow, resolved.jobIndex, resolved.stepIndex, step));
  };

  const stepErrors = resolved
    ? validationErrors.filter(error =>
        isFieldUnder(error.field, `jobs[${resolved.jobIndex}].steps[${resolved.stepIndex}]`)
      )
    : [];

  // The height cap is a variable, not a constant: calc(100vh-8rem) is the
  // page's chrome, but expanded into a full-screen dialog the chrome is the
  // dialog's own header and padding instead. The container overrides
  // --step-panel-max-h; everywhere else falls back to the page value.
  return (
    <aside
      ref={panelRef}
      aria-labelledby={HEADING_ID}
      // Read by the expanded editor's dialog: Radix listens for Escape at the
      // document in the CAPTURE phase, so it always runs before this panel's
      // own bubble-phase listener and stopPropagation here would be too late.
      // The dialog checks this flag instead and lets the panel take Escape
      // first; a second press, with nothing selected, collapses the editor.
      data-step-selected={resolved ? 'true' : undefined}
      className="mt-4 rounded-lg border border-border bg-container p-3 dark:border-border-dark dark:bg-container-dark lg:mt-0 lg:sticky lg:top-4 lg:max-h-[var(--step-panel-max-h,calc(100vh-8rem))] lg:overflow-y-auto"
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <h3
          id={HEADING_ID}
          ref={headingRef}
          tabIndex={-1}
          className="text-sm font-semibold text-text-primary dark:text-text-primary-dark"
        >
          {resolved ? getStepTitle(resolved.step, resolved.stepIndex) : 'Step details'}
        </h3>
        {resolved && (
          <button
            type="button"
            onClick={() => close(rowId!)}
            aria-label="Close step details"
            className="shrink-0 rounded-md p-1 text-text-secondary hover:bg-hover-bg dark:text-text-secondary-dark dark:hover:bg-hover-dark-bg"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>

      {resolved ? (
        <StepFields
          key={resolvedKey}
          step={resolved.step}
          onChange={handleStepChange}
          validationErrors={stepErrors}
          importedActions={importedActions}
          actionGroups={actionGroups}
        />
      ) : (
        <p className="text-sm text-text-secondary dark:text-text-secondary-dark">
          Select a step to edit it.
        </p>
      )}
    </aside>
  );
};

export default StepDetailPanel;
