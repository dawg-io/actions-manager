import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { WorkflowStep, ValidationError, WorkflowCallInput } from '../utils/workflowGuiConversion';
import { getActionInputSchema } from '../utils/actionInputSchemas';
import { ActionsProject } from '../api/actionsProjects';
import { ActionGroup } from '../api/actionGroups';
import { ActionBrandingIcon } from '../utils/actionBranding';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

interface StepCardProps {
  step: WorkflowStep;
  stepIndex: number;
  onChange: (step: WorkflowStep) => void;
  onRemove: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onDuplicate: () => void;
  validationErrors: ValidationError[];
  importedActions: ActionsProject[];
  actionGroups: ActionGroup[];
}

const ALL_ACTION_GROUPS = 'all';

const SHELL_OPTIONS = [
  { value: 'bash', label: 'Bash' },
  { value: 'pwsh', label: 'PowerShell' },
  { value: 'cmd', label: 'Command Prompt' },
  { value: 'sh', label: 'Shell' }
];

interface TypedWithInputProps {
  fieldId: string;
  inputDef: WorkflowCallInput;
  value: string | undefined;
  onChange: (value: string) => void;
}

// A single catalog-driven `with:` field, rendered per input `type`. Split out
// of StepCard so the type switch is a plain if-chain instead of a nested
// ternary, and so it doesn't count toward StepCard's own complexity budget.
const TypedWithInput: React.FC<TypedWithInputProps> = ({ fieldId, inputDef, value, onChange }) => {
  if (inputDef.type === 'boolean') {
    const checked = value === undefined ? Boolean(inputDef.default) : value === 'true';
    return (
      <label className="checkbox-item">
        <input id={fieldId} type="checkbox" checked={checked} onChange={(e) => onChange(String(e.target.checked))} />
        <span>{inputDef.default !== undefined ? `Default: ${inputDef.default}` : ''}</span>
      </label>
    );
  }

  if (inputDef.type === 'choice') {
    return (
      <select id={fieldId} value={value ?? ''} onChange={(e) => onChange(e.target.value)} className="form-select">
        <option value="">{inputDef.default !== undefined ? `Default (${inputDef.default})` : 'Not set'}</option>
        {(inputDef.options || []).map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    );
  }

  return (
    <input
      id={fieldId}
      type={inputDef.type === 'number' ? 'number' : 'text'}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={inputDef.default !== undefined ? String(inputDef.default) : ''}
      className="form-input"
    />
  );
};

const StepCard: React.FC<StepCardProps> = ({
  step,
  stepIndex,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
  onDuplicate,
  validationErrors,
  importedActions,
  actionGroups
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [stepType, setStepType] = useState<'uses' | 'run'>(
    step.uses ? 'uses' : 'run'
  );
  const [pickerGroupFilter, setPickerGroupFilter] = useState<string>(ALL_ACTION_GROUPS);

  // Filters the quick-fill button row only — never the datalist, and never a
  // sectioned/grouped-by-group layout — so an action in multiple groups is
  // still shown at most once, regardless of which group is selected.
  const selectedPickerGroup = actionGroups.find((g) => String(g.action_group_id) === pickerGroupFilter);
  const pickerActions = selectedPickerGroup
    ? importedActions.filter((a) => selectedPickerGroup.actions_project_ids.includes(a.actions_project_id))
    : importedActions;

  const groupPillClass = (active: boolean): string =>
    `rounded-full border px-2 py-0.5 text-xs transition-colors ${
      active
        ? 'border-primary bg-primary text-white dark:border-primary-dark dark:bg-primary-dark'
        : 'border-border text-text-secondary hover:bg-hover-bg dark:border-border-dark dark:text-text-secondary-dark dark:hover:bg-hover-dark-bg'
    }`;

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

  // When `uses` matches a catalog entry, its known inputs get typed form
  // fields instead of the generic key/value editor. Any pre-existing or
  // manually-added keys the catalog doesn't cover still show up below as
  // free-text "additional parameters" so nothing is silently dropped.
  const inputSchema = step.uses ? getActionInputSchema(step.uses, importedActions) : undefined;
  const catalogInputNames = inputSchema ? Object.keys(inputSchema) : [];
  const extraWithEntries = Object.entries(step.with || {}).filter(([key]) => !catalogInputNames.includes(key));
  const withEntries = inputSchema ? extraWithEntries : Object.entries(step.with || {});

  const handleTypedInputChange = (inputName: string, value: string) => {
    const newWith = { ...step.with };
    if (value === '') {
      delete newWith[inputName];
    } else {
      newWith[inputName] = value;
    }
    handleWithChange(newWith);
  };

  const updateWithKey = (oldKey: string, newKey: string, value: string) => {
    const newWith = { ...step.with };
    delete newWith[oldKey];
    if (newKey) {
      newWith[newKey] = value;
    }
    handleWithChange(newWith);
  };

  const updateWithValue = (key: string, value: string) => {
    handleWithChange({ ...step.with, [key]: value });
  };

  const removeWithKey = (key: string) => {
    const newWith = { ...step.with };
    delete newWith[key];
    handleWithChange(newWith);
  };

  const addWithParam = () => {
    const newWith = { ...step.with };
    const newKey = `param-${Object.keys(newWith).length + 1}`;
    newWith[newKey] = '';
    handleWithChange(newWith);
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
                    {importedActions.map(project => (
                      <option key={project.actions_project_id} value={`${project.owner}/${project.repo}@${project.ref}`}>
                        {project.name}
                      </option>
                    ))}
                  </datalist>
                </div>
                {importedActions.length > 0 && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        className="mt-2 inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-text-secondary hover:bg-hover-bg dark:border-border-dark dark:text-text-secondary-dark dark:hover:bg-hover-dark-bg"
                      >
                        Browse imported actions ({importedActions.length})
                        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="max-h-80 w-72 overflow-y-auto">
                      {actionGroups.length > 0 && (
                        <>
                          <fieldset className="m-0 border-0 p-0 flex flex-wrap gap-1 px-2 py-1.5">
                            <legend className="sr-only">Filter imported actions by group</legend>
                            <button
                              type="button"
                              aria-pressed={pickerGroupFilter === ALL_ACTION_GROUPS}
                              onClick={() => setPickerGroupFilter(ALL_ACTION_GROUPS)}
                              className={groupPillClass(pickerGroupFilter === ALL_ACTION_GROUPS)}
                            >
                              All
                            </button>
                            {actionGroups.map(group => (
                              <button
                                key={group.action_group_id}
                                type="button"
                                aria-pressed={pickerGroupFilter === String(group.action_group_id)}
                                onClick={() => setPickerGroupFilter(String(group.action_group_id))}
                                className={groupPillClass(pickerGroupFilter === String(group.action_group_id))}
                              >
                                {group.name}
                              </button>
                            ))}
                          </fieldset>
                          <DropdownMenuSeparator />
                        </>
                      )}
                      {pickerActions.map(project => (
                        <DropdownMenuItem
                          key={project.actions_project_id}
                          onSelect={() => handleFieldChange('uses', `${project.owner}/${project.repo}@${project.ref}`)}
                          title={`${project.owner}/${project.repo}`}
                        >
                          <ActionBrandingIcon icon={project.branding_icon} color={project.branding_color} size={14} />
                          {project.name}
                        </DropdownMenuItem>
                      ))}
                      {pickerActions.length === 0 && (
                        <div className="px-2 py-1.5 text-xs text-text-secondary">No actions in this group.</div>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>

              {/* Action Parameters (with) */}
              <div className="form-field">
                <label className="form-label" htmlFor={`action-params-${step.id}`}>Action Parameters (with)</label>
                <div className="with-section" id={`action-params-${step.id}`}>
                  {inputSchema && (
                    <div className="with-list typed-with-list">
                      {Object.entries(inputSchema).map(([inputName, inputDef]) => (
                        <div className="form-field typed-with-item" key={inputName}>
                          <label className="form-label" htmlFor={`with-${inputName}-${step.id}`}>
                            {inputName}{inputDef.required && ' *'}
                            {inputDef.description && (
                              <span className="field-hint"> — {inputDef.description}</span>
                            )}
                          </label>
                          <TypedWithInput
                            fieldId={`with-${inputName}-${step.id}`}
                            inputDef={inputDef}
                            value={step.with?.[inputName]}
                            onChange={(value) => handleTypedInputChange(inputName, value)}
                          />
                        </div>
                      ))}
                    </div>
                  )}

                  {inputSchema && (
                    <div className="form-label extra-params-label">Additional Parameters</div>
                  )}
                  {withEntries.length > 0 && (
                    <div className="with-list">
                      {withEntries.map(([key, value]) => (
                        <div key={key} className="with-item">
                          <input
                            type="text"
                            value={key}
                            onChange={(e) => updateWithKey(key, e.target.value, value)}
                            placeholder="Parameter name"
                            className="with-key"
                          />
                          <input
                            type="text"
                            value={value}
                            onChange={(e) => updateWithValue(key, e.target.value)}
                            placeholder="Parameter value"
                            className="with-value"
                          />
                          <button
                            type="button"
                            onClick={() => removeWithKey(key)}
                            className="with-remove"
                            title="Remove parameter"
                          >
                            ✕
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  {withEntries.length === 0 && !inputSchema && (
                    <div className="with-empty">No parameters defined</div>
                  )}
                  <button
                    type="button"
                    onClick={addWithParam}
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
                  onChange={(e) => handleFieldChange('timeoutMinutes', e.target.value ? Number.parseInt(e.target.value) : undefined)}
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