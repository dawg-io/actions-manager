import React from 'react';
import { WorkflowStep, ValidationError } from '../utils/workflowGuiConversion';
import { useStepSelection } from './StepSelectionContext';

interface StepCardProps {
  step: WorkflowStep;
  stepIndex: number;
  jobId: string;
  onRemove: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDuplicate: () => void;
  validationErrors: ValidationError[];
}

/**
 * Step ids are only unique within a job — `yamlToGui` mints `step-1`, `step-2`
 * per job — so the DOM id has to carry the job too, or every job's first step
 * claims the same element id.
 */
export const stepRowId = (jobId: string, stepId: string): string => `step-row-${jobId}-${stepId}`;

export const getStepTitle = (step: WorkflowStep, stepIndex: number): string => {
  if (step.name) return step.name;
  if (step.uses) return step.uses;
  if (step.run) return step.run.split('\n')[0].substring(0, 50) + (step.run.length > 50 ? '...' : '');
  return `Step ${stepIndex + 1}`;
};

const StepCard: React.FC<StepCardProps> = ({
  step,
  stepIndex,
  jobId,
  onRemove,
  onMoveUp,
  onMoveDown,
  onDuplicate,
  validationErrors
}) => {
  const { selected, onSelect } = useStepSelection();

  const isSelected = selected?.jobId === jobId && selected?.stepId === step.id;
  const hasErrors = validationErrors.some(error => error.severity === 'error');
  const hasWarnings = validationErrors.some(error => error.severity === 'warning');

  return (
    <div
      className={`step-card ${hasErrors ? 'has-errors' : ''} ${hasWarnings ? 'has-warnings' : ''} ${
        isSelected ? 'ring-2 ring-primary dark:ring-primary-dark' : ''
      }`}
    >
      {/* Step Header */}
      <div className="step-header">
        <div className="step-title-section">
          <button
            type="button"
            id={stepRowId(jobId, step.id)}
            onClick={() => onSelect({ jobId, stepId: step.id })}
            aria-current={isSelected}
            className="step-title cursor-pointer bg-transparent text-left"
          >
            <span className="step-number">{stepIndex + 1}.</span>
            <span className="step-title-text">{getStepTitle(step, stepIndex)}</span>
          </button>
          {(hasErrors || hasWarnings) && (
            <div className="step-status">
              {hasErrors && <span className="error-badge">❌</span>}
              {hasWarnings && <span className="warning-badge">⚠️</span>}
            </div>
          )}
        </div>

        <div className="step-actions">
          {onMoveUp && (
            <button type="button" onClick={onMoveUp} className="step-action" title="Move up">
              ↑
            </button>
          )}
          {onMoveDown && (
            <button type="button" onClick={onMoveDown} className="step-action" title="Move down">
              ↓
            </button>
          )}
          <button type="button" onClick={onDuplicate} className="step-action" title="Duplicate step">
            📋
          </button>
          <button type="button" onClick={onRemove} className="step-action delete" title="Remove step">
            ✕
          </button>
        </div>
      </div>
    </div>
  );
};

export default StepCard;
