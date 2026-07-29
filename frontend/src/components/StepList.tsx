import React from 'react';
import StepCard from './StepCard';
import { WorkflowStep, ValidationError } from '../utils/workflowGuiConversion';
import { ActionsProject } from '../api/actionsProjects';
import { ActionGroup } from '../api/actionGroups';

interface StepListProps {
  steps: WorkflowStep[];
  onChange: (steps: WorkflowStep[]) => void;
  validationErrors: ValidationError[];
  jobIndex: number;
  importedActions: ActionsProject[];
  actionGroups: ActionGroup[];
}

const StepList: React.FC<StepListProps> = ({ steps, onChange, validationErrors, jobIndex, importedActions, actionGroups }) => {
  const updateStep = (index: number, updatedStep: WorkflowStep) => {
    const newSteps = [...steps];
    newSteps[index] = updatedStep;
    onChange(newSteps);
  };

  const removeStep = (index: number) => {
    onChange(steps.filter((_, i) => i !== index));
  };

  const moveStep = (fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= steps.length) return;
    
    const newSteps = [...steps];
    const [movedStep] = newSteps.splice(fromIndex, 1);
    newSteps.splice(toIndex, 0, movedStep);
    onChange(newSteps);
  };

  const duplicateStep = (index: number) => {
    const step = steps[index];
    const newStep: WorkflowStep = {
      ...step,
      id: `${step.id}-copy`,
      name: step.name ? `${step.name} (Copy)` : undefined
    };
    
    const newSteps = [...steps];
    newSteps.splice(index + 1, 0, newStep);
    onChange(newSteps);
  };

  const getStepErrors = (stepIndex: number): ValidationError[] => {
    return validationErrors.filter(error => 
      error.field.startsWith(`jobs[${jobIndex}].steps[${stepIndex}]`)
    );
  };

  return (
    <div className="step-list">
      {steps.length === 0 ? (
        <div className="no-steps-notice">
          No steps defined. Click "Add Step" to create your first step.
        </div>
      ) : (
        steps.map((step, index) => (
          <StepCard
            key={step.id}
            step={step}
            stepIndex={index}
            onChange={(updatedStep) => updateStep(index, updatedStep)}
            onRemove={() => removeStep(index)}
            onMoveUp={index > 0 ? () => moveStep(index, index - 1) : undefined}
            onMoveDown={index < steps.length - 1 ? () => moveStep(index, index + 1) : undefined}
            onDuplicate={() => duplicateStep(index)}
            validationErrors={getStepErrors(index)}
            importedActions={importedActions}
            actionGroups={actionGroups}
          />
        ))
      )}
    </div>
  );
};

export default StepList;