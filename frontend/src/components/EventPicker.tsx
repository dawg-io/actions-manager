import React, { useRef, useState } from 'react';
import { WorkflowEvent } from '../utils/workflowGuiConversion';

interface EventPickerProps {
  events: WorkflowEvent[];
  onChange: (events: WorkflowEvent[]) => void;
}

const EVENT_TYPES = [
  { value: 'push', label: 'Push', description: 'Triggered when commits or tags are pushed' },
  { value: 'pull_request', label: 'Pull Request', description: 'Triggered on pull request events' },
  { value: 'workflow_dispatch', label: 'Manual Trigger', description: 'Allows manual workflow execution' },
  { value: 'schedule', label: 'Schedule', description: 'Runs on a cron schedule' },
  { value: 'release', label: 'Release', description: 'Triggered when releases are published' }
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

  // Tags are plain strings with no natural unique id, so array position
  // can't be used as a React key (it breaks on removal - see S6479). This
  // keeps a stable id per tag, spliced/pushed in lockstep with the tags
  // array itself rather than re-derived by position on every render.
  const tagKeysRef = useRef<Map<number, string[]>>(new Map());

  const getTagKeys = (index: number, length: number): string[] => {
    let keys = tagKeysRef.current.get(index);
    if (!keys) {
      keys = Array.from({ length }, () => crypto.randomUUID());
      tagKeysRef.current.set(index, keys);
    }
    return keys;
  };

  const updateTag = (index: number, tagIndex: number, value: string) => {
    const event = events[index];
    const newTags = [...(event.tags || [])];
    newTags[tagIndex] = value;
    updateEvent(index, { ...event, tags: newTags });
  };

  const addTag = (index: number) => {
    const event = events[index];
    getTagKeys(index, event.tags?.length || 0).push(crypto.randomUUID());
    updateEvent(index, { ...event, tags: [...(event.tags || []), ''] });
  };

  const removeTag = (index: number, tagIndex: number) => {
    const event = events[index];
    getTagKeys(index, event.tags?.length || 0).splice(tagIndex, 1);
    const newTags = event.tags?.filter((_, i) => i !== tagIndex);
    updateEvent(index, { ...event, tags: newTags?.length ? newTags : undefined });
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

                  {/* Tags Filter (push only - GitHub Actions has no separate
                      "tag push" event; a tag-triggered push is the push event
                      filtered by tags) */}
                  {event.type === 'push' && (
                    <div className="advanced-section">
                      <div className="advanced-label">Tags (optional)</div>
                      <div className="array-input">
                        {event.tags?.map((tag, tagIndex) => (
                          <div key={getTagKeys(index, event.tags?.length || 0)[tagIndex]} className="array-item">
                            <input
                              type="text"
                              value={tag}
                              onChange={(e) => updateTag(index, tagIndex, e.target.value)}
                              placeholder="tag name or pattern (e.g., v*)"
                              className="array-input-field"
                            />
                            <button
                              type="button"
                              onClick={() => removeTag(index, tagIndex)}
                              className="array-remove"
                            >
                              ✕
                            </button>
                          </div>
                        ))}
                        <button
                          type="button"
                          onClick={() => addTag(index)}
                          className="array-add"
                        >
                          ➕ Add Tag
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