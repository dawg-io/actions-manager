import React, { useState, useEffect, useCallback, memo } from 'react';
import StepList from './StepList';
import { WorkflowJob, WorkflowStep, ValidationError } from '../utils/workflowGuiConversion';

interface JobCardProps {
  job: WorkflowJob;
  jobIndex: number;
  onChange: (job: WorkflowJob) => void;
  onRemove: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDuplicate: () => void;
  validationErrors: ValidationError[];
  availableJobIds: string[];
}

const RUNNER_OPTIONS = [
  { value: 'ubuntu-latest', label: 'Ubuntu Latest' },
  { value: 'ubuntu-22.04', label: 'Ubuntu 22.04' },
  { value: 'ubuntu-20.04', label: 'Ubuntu 20.04' },
  { value: 'windows-latest', label: 'Windows Latest' },
  { value: 'macos-latest', label: 'macOS Latest' },
  { value: 'macos-13', label: 'macOS 13' },
  { value: 'macos-12', label: 'macOS 12' },
  { value: 'self-hosted', label: 'Self-hosted' }
];

const JobCard: React.FC<JobCardProps> = memo(({
  job,
  jobIndex,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
  onDuplicate,
  validationErrors,
  availableJobIds
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Local buffers to prevent focus loss during typing
  const [localJobName, setLocalJobName] = useState(job.name || '');
  const [isNameFocused, setIsNameFocused] = useState(false);

  const [localJobId, setLocalJobId] = useState(job.id || '');
  const [isIdFocused, setIsIdFocused] = useState(false);

  // Sync local name when not focused
  useEffect(() => {
    if (!isNameFocused) setLocalJobName(job.name || '');
  }, [job.name, isNameFocused]);

  // Sync local id when not focused
  useEffect(() => {
    if (!isIdFocused) setLocalJobId(job.id || '');
  }, [job.id, isIdFocused]);

  const getFieldError = (field: string): ValidationError | undefined => {
    return validationErrors.find(error =>
      error.field === field || error.field.endsWith(`.${field}`)
    );
  };

  const hasErrors = validationErrors.some(error => error.severity === 'error');
  const hasWarnings = validationErrors.some(error => error.severity === 'warning');

  // Include `job` in deps so we don't spread a stale object
  const handleFieldChange = useCallback((field: keyof WorkflowJob, value: any) => {
    onChange({ ...job, [field]: value });
  }, [onChange, job]);

  // Job name buffered handlers
  const handleJobNameChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalJobName(e.target.value);
  }, []);

  const handleJobNameFocus = useCallback(() => setIsNameFocused(true), []);
  const handleJobNameBlur = useCallback(() => {
    setIsNameFocused(false);
    const finalValue = localJobName.trim() || undefined;
    if (finalValue !== job.name) {
      handleFieldChange('name', finalValue);
    }
  }, [localJobName, job.name, handleFieldChange]);

  const handleJobNameKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') e.currentTarget.blur();
  }, []);

  // Job id buffered handlers (fixes focus pop)
  const handleJobIdFocus = useCallback(() => setIsIdFocused(true), []);
  const handleJobIdBlur = useCallback(() => {
    setIsIdFocused(false);
    const finalValue = localJobId.trim();
    if (finalValue !== (job.id || '')) {
      handleFieldChange('id', finalValue);
    }
  }, [localJobId, job.id, handleFieldChange]);

  const handleJobIdKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') e.currentTarget.blur();
  }, []);

  const handleStepsChange = useCallback((steps: WorkflowStep[]) => {
    onChange({ ...job, steps });
  }, [onChange, job]);

  const handleEnvChange = useCallback((env: { [key: string]: string }) => {
    onChange({ ...job, env: Object.keys(env).length > 0 ? env : undefined });
  }, [onChange, job]);

  const handleNeedsChange = useCallback((needs: string[]) => {
    onChange({ ...job, needs: needs.length > 0 ? needs : undefined });
  }, [onChange, job]);

  const addStep = () => {
    const newStep: WorkflowStep = {
      id: `step-${job.steps.length + 1}`,
      name: `Step ${job.steps.length + 1}`
    };
    handleStepsChange([...(job.steps || []), newStep]);
  };

  return (
    <div className={`job-card ${hasErrors ? 'has-errors' : ''} ${hasWarnings ? 'has-warnings' : ''}`}>
      {/* Job Header */}
      <div className="job-header">
        <div className="job-title-section">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="expand-toggle"
          >
            {isExpanded ? '▼' : '▶'}
          </button>
          <div className="job-title">
            <span className="job-label">Job:</span>
            {/* FIXED: buffer job.id locally to avoid unfocus */}
            <input
              type="text"
              value={localJobId}
              onChange={(e) => setLocalJobId(e.target.value)}
              onFocus={handleJobIdFocus}
              onBlur={handleJobIdBlur}
              onKeyDown={handleJobIdKeyDown}
              placeholder="job-id"
              className={`job-id-input ${getFieldError('id') ? 'error' : ''}`}
            />
            {getFieldError('id') && (
              <span className="field-error">{getFieldError('id')!.message}</span>
            )}
          </div>
          {(hasErrors || hasWarnings) && (
            <div className="job-status">
              {hasErrors && <span className="error-badge">❌</span>}
              {hasWarnings && <span className="warning-badge">⚠️</span>}
            </div>
          )}
        </div>

        <div className="job-actions">
          {onMoveUp && (
            <button type="button" onClick={onMoveUp} className="job-action" title="Move up">
              ↑
            </button>
          )}
          {onMoveDown && (
            <button type="button" onClick={onMoveDown} className="job-action" title="Move down">
              ↓
            </button>
          )}
          <button type="button" onClick={onDuplicate} className="job-action" title="Duplicate job">
            📋
          </button>
          <button type="button" onClick={onRemove} className="job-action delete" title="Remove job">
            ✕
          </button>
        </div>
      </div>

      {/* Job Content */}
      {isExpanded && (
        <div className="job-content">
          {/* Basic Job Settings */}
          <div className="job-basic-settings">
            {/* Job Name */}
            <div className="form-field">
              <label className="form-label" htmlFor={`job-name-${job.id}`}>Display Name (optional)</label>
              <input
                id={`job-name-${job.id}`}
                type="text"
                value={localJobName}
                onChange={handleJobNameChange}
                onFocus={handleJobNameFocus}
                onBlur={handleJobNameBlur}
                onKeyDown={handleJobNameKeyDown}
                placeholder="Friendly job name..."
                className="form-input"
              />
            </div>

            {/* Runner */}
            <div className="form-field">
              <label className="form-label" htmlFor={`job-runner-${job.id}`}>
                Runner *
                {getFieldError('runsOn') && (
                  <span className="field-error">{getFieldError('runsOn')!.message}</span>
                )}
              </label>
              <select
                id={`job-runner-${job.id}`}
                value={job.runsOn}
                onChange={(e) => handleFieldChange('runsOn', e.target.value)}
                className={`form-select ${getFieldError('runsOn') ? 'error' : ''}`}
              >
                {RUNNER_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Job Dependencies (Needs) */}
            {availableJobIds.length > 0 && (
              <div className="form-field">
                <label className="form-label" htmlFor={`job-needs-${job.id}`}>Dependencies (needs)</label>
                <div className="needs-section" id={`job-needs-${job.id}`}>
                  {availableJobIds.map(jobId => (
                    <label key={jobId} className="checkbox-item">
                      <input
                        type="checkbox"
                        checked={job.needs?.includes(jobId) || false}
                        onChange={(e) => {
                          const currentNeeds = job.needs || [];
                          const newNeeds = e.target.checked
                            ? [...currentNeeds, jobId]
                            : currentNeeds.filter(id => id !== jobId);
                          handleNeedsChange(newNeeds);
                        }}
                      />
                      <span>{jobId}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Advanced Settings Toggle */}
          <div className="advanced-toggle-section">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="advanced-toggle-button"
            >
              {showAdvanced ? '▲' : '▼'} Advanced Settings
            </button>
          </div>

          {/* Advanced Settings */}
          {showAdvanced && (
            <div className="job-advanced-settings">
              {/* If Condition */}
              <div className="form-field">
                <label className="form-label" htmlFor={`job-if-${job.id}`}>If Condition (optional)</label>
                <input
                  id={`job-if-${job.id}`}
                  type="text"
                  value={job.if || ''}
                  onChange={(e) => handleFieldChange('if', e.target.value || undefined)}
                  placeholder="e.g., github.ref == 'refs/heads/main'"
                  className="form-input"
                />
              </div>

              {/* Timeout */}
              <div className="form-field">
                <label className="form-label" htmlFor={`job-timeout-${job.id}`}>Timeout (minutes)</label>
                <input
                  id={`job-timeout-${job.id}`}
                  type="number"
                  value={job.timeoutMinutes || ''}
                  onChange={(e) => handleFieldChange('timeoutMinutes', e.target.value ? parseInt(e.target.value, 10) : undefined)}
                  placeholder="360"
                  min="1"
                  max="2160"
                  className="form-input"
                />
              </div>

              {/* Job Environment Variables */}
              <div className="form-field">
                <label className="form-label" htmlFor={`job-env-${job.id}`}>Job Environment Variables</label>
                <div className="env-vars-section" id={`job-env-${job.id}`}>
                  {job.env && Object.keys(job.env).length > 0 ? (
                    <div className="env-vars-list">
                      {Object.entries(job.env).map(([key, value], index) => (
                        <div key={index} className="env-var-item">
                          <input
                            type="text"
                            value={key}
                            onChange={(e) => {
                              const newEnv = { ...(job.env || {}) };
                              delete newEnv[key];
                              if (e.target.value) newEnv[e.target.value] = value;
                              handleEnvChange(newEnv);
                            }}
                            placeholder="Variable name"
                            className="env-var-key"
                          />
                          <input
                            type="text"
                            value={value}
                            onChange={(e) => {
                              const newEnv = { ...(job.env || {}) };
                              newEnv[key] = e.target.value;
                              handleEnvChange(newEnv);
                            }}
                            placeholder="Variable value"
                            className="env-var-value"
                          />
                          <button
                            type="button"
                            onClick={() => {
                              const newEnv = { ...(job.env || {}) };
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
                    <div className="env-vars-empty">No job environment variables defined</div>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      const newEnv = { ...(job.env || {}) };
                      const newKey = `JOB_VAR_${Object.keys(newEnv).length + 1}`;
                      newEnv[newKey] = '';
                      handleEnvChange(newEnv);
                    }}
                    className="add-env-var-button"
                  >
                    ➕ Add Environment Variable
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Steps Section */}
          <div className="steps-section" id={`job-steps-${job.id}`}>
            <div className="section-header">
              <label className="form-label" htmlFor={`job-steps-${job.id}`}>
                Steps
                {getFieldError('steps') && (
                  <span className="field-error">{getFieldError('steps')!.message}</span>
                )}
              </label>
            </div>

            <StepList
              steps={job.steps}
              onChange={handleStepsChange}
              validationErrors={validationErrors}
              jobIndex={jobIndex}
            />
            <button
              type="button"
              onClick={addStep}
              className="add-step-button"
            >
              ➕ Add Step
            </button>
          </div>

          {/* Unsupported Fields Notice */}
          {job.unsupportedFields && Object.keys(job.unsupportedFields).length > 0 && (
            <div className="unsupported-fields-notice">
              <span className="info-icon">ℹ️</span>
              <span>
                Unsupported fields: <code>{Object.keys(job.unsupportedFields).join(', ')}</code>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export default JobCard;
