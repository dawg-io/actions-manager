import React, { useState } from 'react';
import { WorkflowEvent } from '../utils/workflowGuiConversion';

interface EventPickerProps {
  events: WorkflowEvent[];
  onChange: (events: WorkflowEvent[]) => void;
}

const EVENT_TYPES = [
  { value: 'push', label: 'Push', description: 'Triggered when commits are pushed' },
  { value: 'pull_request', label: 'Pull Request', description: 'Triggered on pull request events' },
  { value: 'workflow_dispatch', label: 'Manual Trigger', description: 'Allows manual workflow execution' },
  { value: 'schedule', label: 'Schedule', description: 'Runs on a cron schedule' },
  { value: 'release', label: 'Release', description: 'Triggered when releases are published' },
  { value: 'tag_push', label: 'Tag Push', description: 'Triggered when tags are pushed' }
] as const;

const PULL_REQUEST_TYPES = [
  'opened', 'edited', 'closed', 'reopened', 'synchronize', 'converted_to_draft', 'ready_for_review'
];

const RELEASE_TYPES = [
  'published', 'unpublished', 'created', 'edited', 'deleted', 'prereleased', 'released'
];

const EventPicker: React.FC<EventPickerProps> = ({ events, onChange }) => {
  const [showAdvanced, setShowAdvanced] = useState<{ [key: number]: boolean }>({});

  const addEvent = (eventType: WorkflowEvent['type']) => {
    const newEvent: WorkflowEvent = { type: eventType };
    
    // Set default configurations for certain event types
    if (eventType === 'pull_request') {
      newEvent.types = ['opened', 'synchronize'];
    } else if (eventType === 'release') {
      newEvent.types = ['published'];
    } else if (eventType === 'schedule') {
      newEvent.cron = '0 0 * * *'; // Daily at midnight
    }
    
    onChange([...events, newEvent]);
  };

  const removeEvent = (index: number) => {
    onChange(events.filter((_, i) => i !== index));
  };

  const updateEvent = (index: number, updatedEvent: WorkflowEvent) => {
    const newEvents = [...events];
    newEvents[index] = updatedEvent;
    onChange(newEvents);
  };

  const toggleAdvanced = (index: number) => {
    setShowAdvanced(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
  };

  const getEventTypeInfo = (type: WorkflowEvent['type']) => {
    return EVENT_TYPES.find(et => et.value === type);
  };

  return (
    <div className="event-picker">
      {/* Event List */}
      <div className="events-list">
        {events.map((event, index) => {
          const eventInfo = getEventTypeInfo(event.type);
          const isAdvancedOpen = showAdvanced[index];
          
          return (
            <div key={index} className="event-item">
              <div className="event-header">
                <div className="event-info">
                  <span className="event-type">{eventInfo?.label || event.type}</span>
                  <span className="event-description">{eventInfo?.description}</span>
                </div>
                <div className="event-actions">
                  <button
                    type="button"
                    onClick={() => toggleAdvanced(index)}
                    className="advanced-toggle"
                    title="Advanced options"
                  >
                    {isAdvancedOpen ? '▲' : '▼'} Advanced
                  </button>
                  <button
                    type="button"
                    onClick={() => removeEvent(index)}
                    className="remove-event"
                    title="Remove event"
                  >
                    ✕
                  </button>
                </div>
              </div>

              {/* Advanced Options */}
              {isAdvancedOpen && (
                <div className="event-advanced">
                  {/* Pull Request Types */}
                  {event.type === 'pull_request' && (
                    <div className="advanced-section">
                      <div className="advanced-label">Trigger Types</div>
                      <div className="checkbox-group">
                        {PULL_REQUEST_TYPES.map(type => (
                          <label key={type} className="checkbox-item">
                            <input
                              type="checkbox"
                              checked={event.types?.includes(type) || false}
                              onChange={(e) => {
                                const currentTypes = event.types || [];
                                const newTypes = e.target.checked
                                  ? [...currentTypes, type]
                                  : currentTypes.filter(t => t !== type);
                                updateEvent(index, { ...event, types: newTypes.length > 0 ? newTypes : undefined });
                              }}
                            />
                            <span>{type}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Release Types */}
                  {event.type === 'release' && (
                    <div className="advanced-section">
                      <div className="advanced-label">Release Types</div>
                      <div className="checkbox-group">
                        {RELEASE_TYPES.map(type => (
                          <label key={type} className="checkbox-item">
                            <input
                              type="checkbox"
                              checked={event.types?.includes(type) || false}
                              onChange={(e) => {
                                const currentTypes = event.types || [];
                                const newTypes = e.target.checked
                                  ? [...currentTypes, type]
                                  : currentTypes.filter(t => t !== type);
                                updateEvent(index, { ...event, types: newTypes.length > 0 ? newTypes : undefined });
                              }}
                            />
                            <span>{type}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Schedule Cron */}
                  {event.type === 'schedule' && (
                    <div className="advanced-section">
                      <label className="advanced-label" htmlFor={`cron-input-${index}`}>Cron Schedule</label>
                      <input
                        id={`cron-input-${index}`}
                        type="text"
                        value={event.cron || ''}
                        onChange={(e) => updateEvent(index, { ...event, cron: e.target.value })}
                        placeholder="0 0 * * * (daily at midnight)"
                        className="cron-input"
                      />
                      <div className="cron-help">
                        <a href="https://crontab.guru/" target="_blank" rel="noopener noreferrer">
                          📖 Cron syntax help
                        </a>
                      </div>
                    </div>
                  )}

                  {/* Branches Filter (for push, pull_request) */}
                  {(event.type === 'push' || event.type === 'pull_request') && (
                    <div className="advanced-section">
                      <div className="advanced-label">Branches (optional)</div>
                      <div className="array-input">
                        {event.branches?.map((branch, branchIndex) => (
                          <div key={branchIndex} className="array-item">
                            <input
                              type="text"
                              value={branch}
                              onChange={(e) => {
                                const newBranches = [...(event.branches || [])];
                                newBranches[branchIndex] = e.target.value;
                                updateEvent(index, { ...event, branches: newBranches });
                              }}
                              placeholder="branch name or pattern"
                              className="array-input-field"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                const newBranches = event.branches?.filter((_, i) => i !== branchIndex);
                                updateEvent(index, { ...event, branches: newBranches?.length ? newBranches : undefined });
                              }}
                              className="array-remove"
                            >
                              ✕
                            </button>
                          </div>
                        ))}
                        <button
                          type="button"
                          onClick={() => {
                            const newBranches = [...(event.branches || []), ''];
                            updateEvent(index, { ...event, branches: newBranches });
                          }}
                          className="array-add"
                        >
                          ➕ Add Branch
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Paths Filter (for push, pull_request) */}
                  {(event.type === 'push' || event.type === 'pull_request') && (
                    <div className="advanced-section">
                      <div className="advanced-label">Paths (optional)</div>
                      <div className="array-input">
                        {event.paths?.map((path, pathIndex) => (
                          <div key={pathIndex} className="array-item">
                            <input
                              type="text"
                              value={path}
                              onChange={(e) => {
                                const newPaths = [...(event.paths || [])];
                                newPaths[pathIndex] = e.target.value;
                                updateEvent(index, { ...event, paths: newPaths });
                              }}
                              placeholder="path pattern (e.g., src/**)"
                              className="array-input-field"
                            />
                            <button
                              type="button"
                              onClick={() => {
                                const newPaths = event.paths?.filter((_, i) => i !== pathIndex);
                                updateEvent(index, { ...event, paths: newPaths?.length ? newPaths : undefined });
                              }}
                              className="array-remove"
                            >
                              ✕
                            </button>
                          </div>
                        ))}
                        <button
                          type="button"
                          onClick={() => {
                            const newPaths = [...(event.paths || []), ''];
                            updateEvent(index, { ...event, paths: newPaths });
                          }}
                          className="array-add"
                        >
                          ➕ Add Path
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Add Event Buttons */}
      <div className="add-events">
        <div className="add-events-label">Add Trigger:</div>
        <div className="event-buttons">
          {EVENT_TYPES.map(eventType => {
            const isAlreadyAdded = events.some(e => e.type === eventType.value);
            return (
              <button
                key={eventType.value}
                type="button"
                onClick={() => addEvent(eventType.value)}
                disabled={isAlreadyAdded && eventType.value !== 'pull_request' && eventType.value !== 'release'}
                className={`event-button ${isAlreadyAdded ? 'added' : ''}`}
                title={eventType.description}
              >
                {eventType.label}
                {isAlreadyAdded && ' ✓'}
              </button>
            );
          })}
        </div>
      </div>

      {/* No Events Notice */}
      {events.length === 0 && (
        <div className="no-events-notice">
          No trigger events configured. Add at least one event to make the workflow runnable.
        </div>
      )}
    </div>
  );
};

export default EventPicker;