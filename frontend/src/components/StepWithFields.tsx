import React, { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { WorkflowCallInput } from '../utils/workflowGuiConversion';
import { getActionInputSchema, partitionActionInputs, ActionInputEntry } from '../utils/actionInputSchemas';
import { ActionsProject } from '../api/actionsProjects';
import ResourceTextInput from './ResourceTextInput';

interface TypedWithInputProps {
  fieldId: string;
  inputDef: WorkflowCallInput;
  value: string | undefined;
  onChange: (value: string) => void;
}

// A single catalog-driven `with:` field, rendered per input `type`. Split out
// so the type switch is a plain if-chain instead of a nested ternary.
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

  if (inputDef.type === 'number') {
    return (
      <input
        id={fieldId}
        type="number"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={inputDef.default !== undefined ? String(inputDef.default) : ''}
        className="form-input"
      />
    );
  }

  return (
    <div className="flex items-center gap-2">
      <ResourceTextInput
        id={fieldId}
        value={value ?? ''}
        onChange={onChange}
        placeholder={inputDef.default !== undefined ? String(inputDef.default) : ''}
        className="form-input"
      />
    </div>
  );
};

const disclosureLabel = (expanded: boolean, hiddenCount: number, hasVisible: boolean): string => {
  const plural = hiddenCount === 1 ? '' : 's';
  if (expanded) return `Hide ${hiddenCount} option${plural}`;
  const more = hasVisible ? ' more' : '';
  return `Show ${hiddenCount}${more} option${plural}`;
};

interface StepWithFieldsProps {
  stepId: string;
  uses: string | undefined;
  withValues: { [key: string]: string } | undefined;
  onWithChange: (withValues: { [key: string]: string }) => void;
  importedActions: ActionsProject[];
}

const StepWithFields: React.FC<StepWithFieldsProps> = ({
  stepId,
  uses,
  withValues,
  onWithChange,
  importedActions
}) => {
  const [expanded, setExpanded] = useState(false);
  // Optional inputs that have been shown at least once and must not disappear
  // out from under the cursor when their value is cleared.
  const [sticky, setSticky] = useState<ReadonlySet<string>>(() => new Set<string>());

  // Switching the action on the same step (without a step-selection remount)
  // must not carry the previous action's disclosure/sticky state onto the
  // new one's unrelated input set.
  useEffect(() => {
    setExpanded(false);
    setSticky(new Set<string>());
  }, [uses]);

  // When `uses` matches a catalog entry, its known inputs get typed form
  // fields instead of the generic key/value editor. Any pre-existing or
  // manually-added keys the catalog doesn't cover still show up below as
  // free-text "additional parameters" so nothing is silently dropped.
  const inputSchema = uses ? getActionInputSchema(uses, importedActions) : undefined;
  const catalogInputNames = inputSchema ? Object.keys(inputSchema) : [];
  const extraWithEntries = Object.entries(withValues || {}).filter(([key]) => !catalogInputNames.includes(key));
  const extraEntries = inputSchema ? extraWithEntries : Object.entries(withValues || {});

  const { visible, hidden } = partitionActionInputs(inputSchema, withValues, sticky);
  const listId = `action-params-list-${stepId}`;

  // Expanded shows every input in the action's own order, in a single list.
  // Rendering the hidden group in its own container would move an input to a
  // new DOM parent the moment its first character made it "set", remounting
  // the field under the cursor and swallowing the rest of what was typed.
  const shown = expanded ? Object.entries(inputSchema || {}) : visible;

  const handleTypedInputChange = (inputName: string, value: string) => {
    const newWith = { ...withValues };
    if (value === '') {
      // Keep the row mounted so clearing a field doesn't yank it away mid-edit.
      setSticky(prev => new Set(prev).add(inputName));
      delete newWith[inputName];
    } else {
      newWith[inputName] = value;
    }
    onWithChange(newWith);
  };

  const updateWithKey = (oldKey: string, newKey: string, value: string) => {
    const newWith = { ...withValues };
    delete newWith[oldKey];
    if (newKey) {
      newWith[newKey] = value;
    }
    onWithChange(newWith);
  };

  const updateWithValue = (key: string, value: string) => {
    onWithChange({ ...withValues, [key]: value });
  };

  const removeWithKey = (key: string) => {
    const newWith = { ...withValues };
    delete newWith[key];
    onWithChange(newWith);
  };

  const addWithParam = () => {
    const newWith = { ...withValues };
    const newKey = `param-${Object.keys(newWith).length + 1}`;
    newWith[newKey] = '';
    onWithChange(newWith);
  };

  const renderTypedInput = ([inputName, inputDef]: ActionInputEntry) => {
    const isUserSet = Boolean(withValues && Object.hasOwn(withValues, inputName));
    return (
      <div className="form-field typed-with-item" key={inputName}>
        <label className="form-label" htmlFor={`with-${inputName}-${stepId}`}>
          {inputName}{inputDef.required && ' *'}
          {!inputDef.required && isUserSet && (
            <span
              className="ml-1.5 rounded-full border border-border px-1.5 py-0.5 text-[11px] font-normal text-text-secondary dark:border-border-dark dark:text-text-secondary-dark"
              title="Optional input — you set this value"
            >
              Set
            </span>
          )}
          {inputDef.description && (
            <span className="field-hint"> — {inputDef.description}</span>
          )}
        </label>
        <TypedWithInput
          fieldId={`with-${inputName}-${stepId}`}
          inputDef={inputDef}
          value={withValues?.[inputName]}
          onChange={(value) => handleTypedInputChange(inputName, value)}
        />
      </div>
    );
  };

  return (
    <div className="form-field">
      <label className="form-label" htmlFor={`action-params-${stepId}`}>Action Parameters (with)</label>
      <div className="with-section" id={`action-params-${stepId}`}>
        {shown.length > 0 && (
          <div className="with-list typed-with-list" id={listId}>
            {shown.map(renderTypedInput)}
          </div>
        )}

        {hidden.length > 0 && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            aria-controls={listId}
            className="mb-2 inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-text-secondary hover:bg-hover-bg dark:border-border-dark dark:text-text-secondary-dark dark:hover:bg-hover-dark-bg"
          >
            {disclosureLabel(expanded, hidden.length, visible.length > 0)}
            <ChevronDown className={`h-3.5 w-3.5 ${expanded ? 'rotate-180' : ''}`} aria-hidden="true" />
          </button>
        )}

        {inputSchema && (
          <div className="form-label extra-params-label">Additional Parameters</div>
        )}
        {extraEntries.length > 0 && (
          <div className="with-list">
            {extraEntries.map(([key, value]) => (
              <div key={key} className="with-item">
                <input
                  type="text"
                  value={key}
                  onChange={(e) => updateWithKey(key, e.target.value, value)}
                  placeholder="Parameter name"
                  className="with-key"
                />
                <ResourceTextInput
                  value={value}
                  onChange={(newValue) => updateWithValue(key, newValue)}
                  placeholder="Parameter value"
                  className="with-value"
                  ariaLabel={`Value for ${key}`}
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
        {extraEntries.length === 0 && !inputSchema && (
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
  );
};

export default StepWithFields;
