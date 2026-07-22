import React, { useState } from 'react';
import { WorkflowEvent, WorkflowCallInput } from '../utils/workflowGuiConversion';
import { toast } from '../utils/toast';

interface ReusableEventPickerProps {
  events: WorkflowEvent[];
  onChange: (events: WorkflowEvent[]) => void;
}

const INPUT_TYPES = [
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'choice', label: 'Choice' }
] as const;

const ReusableEventPicker: React.FC<ReusableEventPickerProps> = ({ events, onChange }) => {
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);

  // For reusable workflows, we always have exactly one workflow_call event
  const workflowCallEvent = events.find(e => e.type === 'workflow_call') ?? { 
    type: 'workflow_call' as const, 
    inputs: {} 
  };

  const updateEvent = (updatedEvent: WorkflowEvent) => {
    const newEvents = events.filter(e => e.type !== 'workflow_call');
    newEvents.push(updatedEvent);
    onChange(newEvents);
  };

  const addInput = () => {
    const inputs = { ...workflowCallEvent.inputs };
    const inputNames = Object.keys(inputs);
    const newInputName = `input_${inputNames.length + 1}`;
    
    inputs[newInputName] = {
      description: '',
      required: false,
      type: 'string'
    };

    updateEvent({
      ...workflowCallEvent,
      inputs
    });
  };

  const updateInput = (inputName: string, updatedInput: WorkflowCallInput) => {
    const inputs = { ...workflowCallEvent.inputs };
    inputs[inputName] = updatedInput;
    
    updateEvent({
      ...workflowCallEvent,
      inputs
    });
  };

  const removeInput = (inputName: string) => {
    const inputs = { ...workflowCallEvent.inputs };
    delete inputs[inputName];
    
    updateEvent({
      ...workflowCallEvent,
      inputs
    });
  };

  const renameInput = (oldName: string, newName: string) => {
    if (oldName === newName || !newName.trim()) return;
    
    const inputs = { ...workflowCallEvent.inputs };
    if (inputs[newName]) {
      toast.error('An input with this name already exists');
      return;
    }
    
    inputs[newName] = inputs[oldName];
    delete inputs[oldName];
    
    updateEvent({
      ...workflowCallEvent,
      inputs
    });
  };

  const toggleAdvanced = () => {
    setShowAdvanced(!showAdvanced);
  };

  const hasInputs = workflowCallEvent.inputs && Object.keys(workflowCallEvent.inputs).length > 0;

  return (
    <div className="event-picker">
      {/* Workflow Call Event Info */}
      <div className="events-list">
        <div className="event-item">
          <div className="event-header">
            <div className="event-info">
              <span className="event-type">Workflow Call</span>
              <span className="event-description">Triggered when called by another workflow</span>
            </div>
            <div className="event-actions">
              <button
                type="button"
                onClick={toggleAdvanced}
                className="advanced-toggle"
                title="Configure workflow inputs"
              >
                {showAdvanced ? '▲' : '▼'} Configure Inputs
              </button>
            </div>
          </div>

          {/* Advanced Options - Workflow Inputs */}
          {showAdvanced && (
            <div className="event-advanced">
              <div className="advanced-section">
                <div className="advanced-label">Workflow Inputs</div>
                
                {/* Input List */}
                {hasInputs ? (
                  <div className="workflow-inputs-list">
                    {Object.entries(workflowCallEvent.inputs!).map(([inputName, input]) => (
                      <div key={inputName} className="workflow-input-item">
                        <div className="input-header">
                          <input
                            type="text"
                            value={inputName}
                            onChange={(e) => renameInput(inputName, e.target.value)}
                            placeholder="Input name"
                            className="input-name-field"
                          />
                          <button
                            type="button"
                            onClick={() => removeInput(inputName)}
                            className="input-remove"
                            title="Remove input"
                          >
                            ✕
                          </button>
                        </div>
                        
                        <div className="input-config">
                          <div className="input-field">
                            <label htmlFor={`input-description-${inputName}`}>Description:</label>
                            <input
                              id={`input-description-${inputName}`}
                              type="text"
                              value={input.description ?? ''}
                              onChange={(e) => updateInput(inputName, { ...input, description: e.target.value })}
                              placeholder="Describe this input"
                              className="input-description"
                            />
                          </div>
                          
                          <div className="input-field">
                            <label htmlFor={`input-type-${inputName}`}>Type:</label>
                            <select
                              id={`input-type-${inputName}`}
                              value={input.type ?? 'string'}
                              onChange={(e) => updateInput(inputName, { 
                                ...input, 
                                type: e.target.value as any,
                                // Clear options when type changes from choice
                                ...(e.target.value !== 'choice' ? { options: undefined } : {})
                              })}
                              className="input-type"
                            >
                              {INPUT_TYPES.map(type => (
                                <option key={type.value} value={type.value}>
                                  {type.label}
                                </option>
                              ))}
                            </select>
                          </div>

                          {/* Choice options */}
                          {input.type === 'choice' && (
                            <div className="input-field">
                              <label htmlFor={`input-options-${inputName}`}>Options (one per line):</label>
                              <textarea
                                id={`input-options-${inputName}`}
                                value={(input.options ?? []).join('\n')}
                                onChange={(e) => updateInput(inputName, {
                                  ...input,
                                  options: e.target.value.split('\n').filter(opt => opt.trim())
                                })}
                                placeholder="option1&#10;option2&#10;option3"
                                className="input-options"
                                rows={3}
                              />
                            </div>
                          )}
                          
                          <div className="input-field">
                            <label htmlFor={`input-default-${inputName}`}>Default Value:</label>
                            <input
                              id={`input-default-${inputName}`}
                              type={input.type === 'number' ? 'number' : 'text'}
                              value={input.type === 'boolean' ? String(input.default ?? false) : String(input.default ?? '')}
                              onChange={(e) => {
                                let value: string | number | boolean = e.target.value;
                                if (input.type === 'number') {
                                  value = parseFloat(e.target.value) || 0;
                                } else if (input.type === 'boolean') {
                                  value = e.target.value.toLowerCase() === 'true';
                                }
                                updateInput(inputName, { ...input, default: value });
                              }}
                              placeholder={input.type === 'boolean' ? 'true or false' : 'Default value'}
                              className="input-default"
                            />
                          </div>
                          
                          <div className="input-field checkbox-field">
                            <label className="checkbox-item">
                              <input
                                type="checkbox"
                                checked={input.required ?? false}
                                onChange={(e) => updateInput(inputName, { ...input, required: e.target.checked })}
                              />
                              <span>Required input</span>
                            </label>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="no-inputs-notice">
                    No workflow inputs defined. Add inputs to make this workflow configurable.
                  </div>
                )}
                
                {/* Add Input Button */}
                <button
                  type="button"
                  onClick={addInput}
                  className="add-input-button"
                >
                  ➕ Add Input
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Info Notice */}
      <div className="reusable-workflow-notice">
        <div className="notice-header">
          <span className="info-icon">ℹ️</span>
          <span>Reusable Workflow</span>
        </div>
        <div className="notice-content">
          This workflow uses <code>workflow_call</code> as the trigger event, making it reusable by other workflows.
          Configure inputs above to make the workflow parameterized.
        </div>
      </div>
    </div>
  );
};

export default ReusableEventPicker;