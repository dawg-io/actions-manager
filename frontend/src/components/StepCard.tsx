import React, { useState } from 'react';
import { WorkflowStep, ValidationError } from '../utils/workflowGuiConversion';

interface StepCardProps {
  step: WorkflowStep;
  stepIndex: number;
  onChange: (step: WorkflowStep) => void;
  onRemove: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDuplicate: () => void;
  validationErrors: ValidationError[];
}

// Keep in sync with backend/action_versions.py (source of record for these pins).
const COMMON_ACTIONS = [
  { value: 'actions/checkout@v7.0.1', label: 'Checkout Repository', description: 'Check out repository content' },
  { value: 'actions/setup-node@v7.0.0', label: 'Setup Node.js', description: 'Set up Node.js environment' },
  { value: 'actions/setup-python@v7.0.0', label: 'Setup Python', description: 'Set up Python environment' },
  { value: 'actions/setup-java@v5.6.0', label: 'Setup Java', description: 'Set up Java environment' },
  { value: 'actions/cache@v6.1.0', label: 'Cache Dependencies', description: 'Cache dependencies and build outputs' },
  { value: 'actions/upload-artifact@v7.0.1', label: 'Upload Artifacts', description: 'Upload build artifacts' },
  { value: 'actions/download-artifact@v8.0.1', label: 'Download Artifacts', description: 'Download build artifacts' }
];

const SHELL_OPTIONS = [
  { value: 'bash', label: 'Bash' },
  { value: 'pwsh', label: 'PowerShell' },
  { value: 'cmd', label: 'Command Prompt' },
  { value: 'sh', label: 'Shell' }
];

const StepCard: React.FC<StepCardProps> = ({
  step,
  stepIndex,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
  onDuplicate,
  validationErrors
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [stepType, setStepType] = useState<'uses' | 'run'>(
    step.uses ? 'uses' : 'run'
  );

  const getFieldError = (field: string): ValidationError | undefined => {
    return validationErrors.find(error => 
      error.field === field || error.field.endsWith(`.${field}`)
    );
  };

  const hasErrors = validationErrors.some(error => error.severity === 'error');
  const hasWarnings = validationErrors.some(error => error.severity === 'warning');

  const handleFieldChange = (field: keyof WorkflowStep, value: any) => {
    onChange({
      ...step,
      [field]: value
    });
  };

  const handleStepTypeChange = (newType: 'uses' | 'run') => {
    setStepType(newType);
    
    if (newType === 'uses') {
      // Switching to uses - clear run field
      onChange({
        ...step,
        uses: step.uses ?? '',
        run: undefined,
        shell: undefined
      });
    } else {
      // Switching to run - clear uses and with fields
      onChange({
        ...step,
        uses: undefined,
        with: undefined,
        run: step.run ?? ''
      });
    }
  };

  const handleWithChange = (with_: { [key: string]: string }) => {
    onChange({
      ...step,
      with: Object.keys(with_).length > 0 ? with_ : undefined
    });
  };

  const handleEnvChange = (env: { [key: string]: string }) => {
    onChange({
      ...step,
      env: Object.keys(env).length > 0 ? env : undefined
    });
  };

  const getStepTitle = () => {
    if (step.name) return step.name;
    if (step.uses) return step.uses;
    if (step.run) return step.run.split('\n')[0].substring(0, 50) + (step.run.length > 50 ? '...' : '');
    return `Step ${stepIndex + 1}`;
  };

  return (
    <div className={`step-card ${hasErrors ? 'has-errors' : ''} ${hasWarnings ? 'has-warnings' : ''}`}>
      {/* Step Header */}
      <div className="step-header">
        <div className="step-title-section">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="expand-toggle"
          >
            {isExpanded ? '▼' : '▶'}
          </button>
          <div className="step-title">
            <span className="step-number">{stepIndex + 1}.</span>
            <span className="step-title-text">{getStepTitle()}</span>
          </div>
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

      {/* Step Content */}
      {isExpanded && (
        <div className="step-content">
          {/* Step Type Selection */}
          <div className="step-type-selection">
            <label className="form-label" htmlFor={`step-type-uses-${step.id}`}>Step Type</label>
            <div className="radio-group">
              <label className="radio-item">
                <input
                  id={`step-type-uses-${step.id}`}
                  type="radio"
                  name={`step-type-${step.id}`}
                  value="uses"
                  checked={stepType === 'uses'}
                  onChange={() => handleStepTypeChange('uses')}
                />
                <span>Use Action</span>
              </label>
              <label className="radio-item">
                <input
                  id={`step-type-run-${step.id}`}
                  type="radio"
                  name={`step-type-${step.id}`}
                  value="run"
                  checked={stepType === 'run'}
                  onChange={() => handleStepTypeChange('run')}
                />
                <span>Run Script</span>
              </label>
            </div>
          </div>

          {/* Step Name */}
          <div className="form-field">
            <label className="form-label" htmlFor={`step-name-${step.id}`}>Step Name (optional)</label>
            <input
              id={`step-name-${step.id}`}
              type="text"
              value={step.name ?? ''}
              onChange={(e) => handleFieldChange('name', e.target.value || undefined)}
              placeholder="Descriptive step name..."
              className="form-input"
            />
          </div>

          {/* Uses Action */}
          {stepType === 'uses' && (
            <div className="uses-section">
              <div className="form-field">
                <label className="form-label" htmlFor={`step-uses-${step.id}`}>
                  Action *
                  {getFieldError('uses') && (
                    <span className="field-error">{getFieldError('uses')!.message}</span>
                  )}
                </label>
                <div className="action-input-section">
                  <input
                    id={`step-uses-${step.id}`}
                    type="text"
                    value={step.uses ?? ''}
                    onChange={(e) => handleFieldChange('uses', e.target.value)}
                    placeholder="e.g., actions/checkout@v5"
                    className={`form-input ${getFieldError('uses') ? 'error' : ''}`}
                    list={`common-actions-${step.id}`}
                  />
                  <datalist id={`common-actions-${step.id}`}>
                    {COMMON_ACTIONS.map(action => (
                      <option key={action.value} value={action.value}>
                        {action.label}
                      </option>
                    ))}
                  </datalist>
                </div>
                <div className="common-actions">
                  <span className="common-actions-label">Common actions:</span>
                  {COMMON_ACTIONS.map(action => (
                    <button
                      key={action.value}
                      type="button"
                      onClick={() => handleFieldChange('uses', action.value)}
                      className="common-action-button"
                      title={action.description}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Action Parameters (with) */}
              <div className="form-field">
                <label className="form-label" htmlFor={`action-params-${step.id}`}>Action Parameters (with)</label>
                <div className="with-section" id={`action-params-${step.id}`}>
                  {step.with && Object.keys(step.with).length > 0 ? (
                    <div className="with-list">
                      {Object.entries(step.with).map(([key, value], index) => (
                        <div key={index} className="with-item">
                          <input
                            type="text"
                            value={key}
                            onChange={(e) => {
                              const newWith = { ...step.with };
                              delete newWith[key];
                              if (e.target.value) {
                                newWith[e.target.value] = value;
                              }
                              handleWithChange(newWith);
                            }}
                            placeholder="Parameter name"
                            className="with-key"
                          />
                          <input
                            type="text"
                            value={value}
                            onChange={(e) => {
                              const newWith = { ...step.with };
                              newWith[key] = e.target.value;
                              handleWithChange(newWith);
                            }}
                            placeholder="Parameter value"
                            className="with-value"
                          />
                          <button
                            type="button"
                            onClick={() => {
                              const newWith = { ...step.with };
                              delete newWith[key];
                              handleWithChange(newWith);
                            }}
                            className="with-remove"
                            title="Remove parameter"
                          >
                            ✕
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="with-empty">No parameters defined</div>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      const newWith = { ...step.with };
                      const newKey = `param-${Object.keys(newWith).length + 1}`;
                      newWith[newKey] = '';
                      handleWithChange(newWith);
                    }}
                    className="add-with-button"
                  >
                    ➕ Add Parameter
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Run Script */}
          {stepType === 'run' && (
            <div className="run-section">
              <div className="form-field">
                <label className="form-label" htmlFor={`step-run-${step.id}`}>
                  Script *
                  {getFieldError('run') && (
                    <span className="field-error">{getFieldError('run')!.message}</span>
                  )}
                </label>
                <textarea
                  id={`step-run-${step.id}`}
                  value={step.run ?? ''}
                  onChange={(e) => handleFieldChange('run', e.target.value)}
                  placeholder="Enter your script commands here..."
                  className={`form-textarea ${getFieldError('run') ? 'error' : ''}`}
                  rows={4}
                />
              </div>

              <div className="form-field">
                <label className="form-label" htmlFor={`step-shell-${step.id}`}>Shell (optional)</label>
                <select
                  id={`step-shell-${step.id}`}
                  value={step.shell ?? ''}
                  onChange={(e) => handleFieldChange('shell', e.target.value || undefined)}
                  className="form-select"
                >
                  <option value="">Default</option>
                  {SHELL_OPTIONS.map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

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
            <div className="step-advanced-settings">
              {/* If Condition */}
              <div className="form-field">
                <label className="form-label" htmlFor={`step-if-${step.id}`}>If Condition (optional)</label>
                <input
                  id={`step-if-${step.id}`}
                  type="text"
                  value={step.if ?? ''}
                  onChange={(e) => handleFieldChange('if', e.target.value || undefined)}
                  placeholder="e.g., success() || failure()"
                  className="form-input"
                />
              </div>

              {/* Working Directory (for run steps) */}
              {stepType === 'run' && (
                <div className="form-field">
                  <label className="form-label" htmlFor={`step-workdir-${step.id}`}>Working Directory (optional)</label>
                  <input
                    id={`step-workdir-${step.id}`}
                    type="text"
                    value={step.workingDirectory ?? ''}
                    onChange={(e) => handleFieldChange('workingDirectory', e.target.value || undefined)}
                    placeholder="e.g., ./src"
                    className="form-input"
                  />
                </div>
              )}

              {/* Continue on Error */}
              <div className="form-field">
                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={step.continueOnError || false}
                    onChange={(e) => handleFieldChange('continueOnError', e.target.checked || undefined)}
                  />
                  <span>Continue on error</span>
                </label>
              </div>

              {/* Timeout */}
              <div className="form-field">
                <label className="form-label" htmlFor={`step-timeout-${step.id}`}>Timeout (minutes)</label>
                <input
                  id={`step-timeout-${step.id}`}
                  type="number"
                  value={step.timeoutMinutes ?? ''}
                  onChange={(e) => handleFieldChange('timeoutMinutes', e.target.value ? parseInt(e.target.value) : undefined)}
                  placeholder="30"
                  min="1"
                  max="2160"
                  className="form-input"
                />
              </div>

              {/* Step Environment Variables */}
              <div className="form-field">
                <label className="form-label" htmlFor={`step-env-${step.id}`}>Step Environment Variables</label>
                <div className="env-vars-section" id={`step-env-${step.id}`}>
                  {step.env && Object.keys(step.env).length > 0 ? (
                    <div className="env-vars-list">
                      {Object.entries(step.env).map(([key, value], index) => (
                        <div key={index} className="env-var-item">
                          <input
                            type="text"
                            value={key}
                            onChange={(e) => {
                              const newEnv = { ...step.env };
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
                              const newEnv = { ...step.env };
                              newEnv[key] = e.target.value;
                              handleEnvChange(newEnv);
                            }}
                            placeholder="Variable value"
                            className="env-var-value"
                          />
                          <button
                            type="button"
                            onClick={() => {
                              const newEnv = { ...step.env };
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
                    <div className="env-vars-empty">No step environment variables defined</div>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      const newEnv = { ...step.env };
                      const newKey = `STEP_VAR_${Object.keys(newEnv).length + 1}`;
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

          {/* Unsupported Fields Notice */}
          {step.unsupportedFields && Object.keys(step.unsupportedFields).length > 0 && (
            <div className="unsupported-fields-notice">
              <span className="info-icon">ℹ️</span>
              <span>
                Unsupported fields: <code>{Object.keys(step.unsupportedFields).join(', ')}</code>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default StepCard;