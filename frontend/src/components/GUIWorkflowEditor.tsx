import React, { useState, useEffect, useMemo } from 'react';
import EventPicker from './EventPicker';
import JobList from './JobList';
import StepDetailPanel from './StepDetailPanel';
import { StepSelection, StepSelectionProvider } from './StepSelectionContext';
import {
  WorkflowGUI,
  WorkflowJob,
  WorkflowEvent,
  validateWorkflow,
  ValidationError
} from '../utils/workflowGuiConversion';
import { uniqueId } from '../utils/stepSelection';
import { ActionsProject } from '../api/actionsProjects';
import { ActionGroup } from '../api/actionGroups';
// eslint-disable-next-line no-restricted-imports -- Legacy: TODO migrate CSS file to Tailwind CSS classes
import '../styles/GUIWorkflowEditor.css';

interface GUIWorkflowEditorProps {
  workflow: WorkflowGUI;
  onChange: (workflow: WorkflowGUI) => void;
  onValidationChange?: (errors: ValidationError[]) => void;
  importedActions: ActionsProject[];
  actionGroups: ActionGroup[];
}

const GUIWorkflowEditor: React.FC<GUIWorkflowEditorProps> = ({
  workflow,
  onChange,
  onValidationChange,
  importedActions,
  actionGroups
}) => {
  const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);
  const [selected, setSelected] = useState<StepSelection | null>(null);

  // Memoize validation errors to prevent infinite re-renders
  const memoizedValidationErrors = useMemo(() => {
    return validateWorkflow(workflow);
  }, [workflow]);

  // Update validation errors only when memoized errors change
  useEffect(() => {
    setValidationErrors(memoizedValidationErrors);
    if (onValidationChange) {
      onValidationChange(memoizedValidationErrors);
    }
  }, [memoizedValidationErrors, onValidationChange]);

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({
      ...workflow,
      name: e.target.value
    });
  };

  const handleEventsChange = (events: WorkflowEvent[]) => {
    onChange({
      ...workflow,
      events
    });
  };

  const handleJobsChange = (jobs: WorkflowJob[]) => {
    onChange({
      ...workflow,
      jobs
    });
  };

  const handleEnvChange = (env: { [key: string]: string }) => {
    onChange({
      ...workflow,
      env
    });
  };

  const addJob = () => {
    const id = uniqueId(workflow.jobs.map(j => j.id), `job-${workflow.jobs.length + 1}`);
    const newJob: WorkflowJob = {
      id,
      name: `Job ${workflow.jobs.length + 1}`,
      runsOn: 'ubuntu-latest',
      steps: []
    };

    onChange({
      ...workflow,
      jobs: [...workflow.jobs, newJob]
    });
  };

  const getFieldError = (field: string): ValidationError | undefined => {
    return validationErrors.find(error => error.field === field);
  };

  const hasErrors = validationErrors.some(error => error.severity === 'error');
  const hasWarnings = validationErrors.some(error => error.severity === 'warning');

  return (
    <div className="gui-workflow-editor">
      {/* Validation Summary */}
      {validationErrors.length > 0 && (
        <div className="validation-summary">
          {hasErrors && (
            <div className="validation-errors">
              <span className="error-icon">❌</span>
              <span>Workflow has {validationErrors.filter(e => e.severity === 'error').length} error(s)</span>
            </div>
          )}
          {hasWarnings && (
            <div className="validation-warnings">
              <span className="warning-icon">⚠️</span>
              <span>Workflow has {validationErrors.filter(e => e.severity === 'warning').length} warning(s)</span>
            </div>
          )}
        </div>
      )}

      {/* Workflow Name */}
      <div className="form-section">
        <label className="form-label">
          Workflow Name *
          {getFieldError('name') && (
            <span className="field-error">{getFieldError('name')!.message}</span>
          )}
        </label>
        <input
          type="text"
          value={workflow.name}
          onChange={handleNameChange}
          placeholder="Enter workflow name..."
          className={`form-input ${getFieldError('name') ? 'error' : ''}`}
        />
      </div>

      {/* Trigger Events */}
      <div className="form-section">
        <label className="form-label">
          Trigger Events *
          {getFieldError('events') && (
            <span className="field-error">{getFieldError('events')!.message}</span>
          )}
        </label>
        <EventPicker
          events={workflow.events}
          onChange={handleEventsChange}
        />
      </div>

      {/* Environment Variables (Global) */}
      <div className="form-section">
        <div className="form-label">Global Environment Variables</div>
        <div className="env-vars-section">
          {workflow.env && Object.keys(workflow.env).length > 0 ? (
            <div className="env-vars-list">
              {Object.entries(workflow.env).map(([key, value], index) => (
                <div key={index} className="env-var-item">
                  <input
                    type="text"
                    value={key}
                    onChange={(e) => {
                      const newEnv = { ...workflow.env };
                      delete newEnv[key];
                      if (e.target.value) {
                        newEnv[e.target.value] = value;
                      }
                      handleEnvChange(newEnv);
                    }}
                    placeholder="Variable name"
                    className="env-var-key"
                  />
                  <input
                    type="text"
                    value={value}
                    onChange={(e) => {
                      const newEnv = { ...workflow.env };
                      newEnv[key] = e.target.value;
                      handleEnvChange(newEnv);
                    }}
                    placeholder="Variable value"
                    className="env-var-value"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const newEnv = { ...workflow.env };
                      delete newEnv[key];
                      handleEnvChange(newEnv);
                    }}
                    className="env-var-remove"
                    title="Remove variable"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="env-vars-empty">No global environment variables defined</div>
          )}
          <button
            type="button"
            onClick={() => {
              const newEnv = { ...workflow.env };
              const newKey = `VAR_${Object.keys(newEnv).length + 1}`;
              newEnv[newKey] = '';
              handleEnvChange(newEnv);
            }}
            className="add-env-var-button"
          >
            ➕ Add Environment Variable
          </button>
        </div>
      </div>

      {/* Jobs */}
      <div className="form-section">
        <div className="section-header">
          <label className="form-label">
            Jobs *
            {getFieldError('jobs') && (
              <span className="field-error">{getFieldError('jobs')!.message}</span>
            )}
          </label>
          <button
            type="button"
            onClick={addJob}
            className="add-job-button"
          >
            ➕ Add Job
          </button>
        </div>
        
        <StepSelectionProvider value={{ selected, onSelect: setSelected }}>
          <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start lg:gap-4">
            <JobList
              jobs={workflow.jobs}
              onChange={handleJobsChange}
              validationErrors={validationErrors}
            />
            <StepDetailPanel
              workflow={workflow}
              selected={selected}
              onSelect={setSelected}
              onChange={onChange}
              validationErrors={validationErrors}
              importedActions={importedActions}
              actionGroups={actionGroups}
            />
          </div>
        </StepSelectionProvider>
      </div>

      {/* Unsupported Fields Notice */}
      {workflow.unsupportedFields && Object.keys(workflow.unsupportedFields).length > 0 && (
        <div className="unsupported-fields-notice">
          <div className="notice-header">
            <span className="info-icon">ℹ️</span>
            <span>Unsupported YAML Fields</span>
          </div>
          <div className="notice-content">
            The following fields are not supported in GUI mode but will be preserved:{' '}
            <code>{Object.keys(workflow.unsupportedFields).join(', ')}</code>
          </div>
          <div className="notice-action">
            Switch to YAML mode to edit these fields
          </div>
        </div>
      )}
    </div>
  );
};

export default GUIWorkflowEditor;
