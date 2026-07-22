import React, { useEffect, useRef, useState } from 'react';
import PrefixedInput from './PrefixedInput';
import { Button } from './ui/button';
import { cn } from '../lib/utils';
import { Pencil } from 'lucide-react';

export interface EditableNameFieldProps {
  /** The current persisted value to display when read-only. */
  value: string;
  /**
   * Called with the new (trimmed) value when the user clicks Save with a
   * valid, changed value.  The parent owns persistence (state update / API
   * call); the field only gates editing behind an explicit action.
   */
  onSave: (newValue: string) => void;
  /**
   * Optional synchronous validator.  Return an error string to block Save and
   * surface the message under the input, or `null`/`undefined` when valid.
   */
  validate?: (draftValue: string) => string | null;
  /** Optional fixed prefix segment shown before the editable area. */
  prefix?: string;
  /** Optional fixed suffix segment shown after the editable area (e.g. ".yml"). */
  suffix?: string;
  /** Placeholder rendered inside the input while editing. */
  placeholder?: string;
  /** Maximum input length passed through to the underlying <input>. */
  maxLength?: number;
  /** Disables the entire control (no edit, no save).  Used for read-only roles. */
  disabled?: boolean;
  /** Accessible label for the read-only display, edit button, and input. */
  ariaLabel: string;
  /** DOM id applied to the inner <input> when editing. */
  inputId?: string;
  /** Class applied to the wrapping <div>. */
  className?: string;
  /** Class applied to the read-only display span. */
  displayClassName?: string;
  /** Class applied to the read-only edit button. */
  editButtonClassName?: string;
  /** Class applied to the inner input or PrefixedInput. */
  inputClassName?: string;
  /**
   * Optional renderer for the read-only display.  Defaults to rendering
   * `prefix + value + suffix` so the user sees the canonical name.
   */
  renderDisplay?: (value: string) => React.ReactNode;
}

/**
 * EditableNameField – a small, accessible "click-to-edit" control.
 *
 * The value is shown as plain text by default.  Users must explicitly click
 * the edit button to enter edit mode, where they get Save / Cancel
 * controls.  Save is disabled when the value is unchanged or fails
 * validation.  Cancel discards any local edits and restores the original
 * value.
 */
const EditableNameField: React.FC<EditableNameFieldProps> = ({
  value,
  onSave,
  validate,
  prefix,
  suffix,
  placeholder,
  maxLength,
  disabled = false,
  ariaLabel,
  inputId,
  className,
  displayClassName,
  editButtonClassName,
  inputClassName,
  renderDisplay,
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState<string>(value);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // If the persisted `value` changes externally while we're not editing
  // (e.g. a refresh / load), keep the draft in sync so cancelling later
  // restores the new value rather than the previous one.
  useEffect(() => {
    if (!isEditing) {
      setDraft(value);
    }
  }, [value, isEditing]);

  // Auto-focus the input when entering edit mode.
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const trimmedDraft = draft.trim();
  const trimmedValue = (value ?? '').trim();
  const isUnchanged = trimmedDraft === trimmedValue;
  const validationError = validate ? validate(draft) : null;
  const saveDisabled = isUnchanged || validationError !== null || trimmedDraft.length === 0;

  const startEditing = () => {
    if (disabled) return;
    setDraft(value);
    setError(null);
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setDraft(value);
    setError(null);
    setIsEditing(false);
  };

  const commitSave = () => {
    if (validationError) {
      setError(validationError);
      return;
    }
    if (isUnchanged) {
      // Nothing to do – just exit edit mode.
      setIsEditing(false);
      return;
    }
    onSave(trimmedDraft);
    setError(null);
    setIsEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (!saveDisabled) commitSave();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelEditing();
    }
  };

  if (!isEditing) {
    const displayContent = renderDisplay
      ? renderDisplay(value)
      : `${prefix ?? ''}${value ?? ''}${suffix ?? ''}`;

    return (
      <div
        className={cn('editable-name-field flex items-center gap-2', className)}
        data-testid="editable-name-field"
        data-mode="readonly"
      >
        <span
          className={cn(
            'editable-name-display text-text-primary dark:text-text-primary-dark',
            'select-text break-all',
            displayClassName,
          )}
          aria-label={ariaLabel}
          data-testid="editable-name-display"
        >
          {displayContent || (
            <span className="text-text-muted dark:text-text-muted-dark italic">
              {placeholder || 'Not set'}
            </span>
          )}
        </span>
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={startEditing}
          disabled={disabled}
          aria-label={`Edit ${ariaLabel}`}
          title={`Edit ${ariaLabel}`}
          data-testid="editable-name-edit-button"
          className={cn('h-8 w-8', editButtonClassName)}
        >
          <Pencil aria-hidden="true" />
        </Button>
      </div>
    );
  }

  // Edit mode.
  const usePrefixedInput = Boolean(prefix) || Boolean(suffix);
  const helperId = inputId ? `${inputId}-error` : undefined;

  return (
    <div
      className={cn('editable-name-field flex flex-col gap-1', className)}
      data-testid="editable-name-field"
      data-mode="editing"
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex-1 min-w-0 basis-48">
          {usePrefixedInput ? (
            <PrefixedInput
              id={inputId}
              prefix={prefix ?? ''}
              suffix={suffix}
              showPrefix={Boolean(prefix)}
              value={draft}
              onChange={(v: string) => {
                setDraft(v);
                if (error) setError(null);
              }}
              placeholder={placeholder}
              maxLength={maxLength}
              aria-label={ariaLabel}
              aria-invalid={Boolean(error || validationError)}
              aria-describedby={helperId}
              onKeyDown={handleKeyDown}
              className={cn('editable-name-input', inputClassName)}
            />
          ) : (
            <input
              ref={inputRef}
              id={inputId}
              type="text"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                if (error) setError(null);
              }}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              maxLength={maxLength}
              aria-label={ariaLabel}
              aria-invalid={Boolean(error || validationError)}
              aria-describedby={helperId}
              className={cn(
                'editable-name-input flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-sm transition-colors',
                'border-input-border bg-input-bg text-text-primary',
                'placeholder:text-text-muted',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-input-focus',
                'disabled:cursor-not-allowed disabled:opacity-50',
                'dark:border-input-dark-border dark:bg-input-dark-bg dark:text-text-primary-dark dark:placeholder:text-text-muted-dark',
                inputClassName,
              )}
            />
          )}
        </div>
        <Button
          type="button"
          variant="default"
          size="sm"
          onClick={commitSave}
          disabled={saveDisabled}
          aria-label={`Save ${ariaLabel}`}
          title={
            isUnchanged
              ? 'No changes to save'
              : validationError
              ? validationError
              : `Save ${ariaLabel}`
          }
          data-testid="editable-name-save-button"
        >
          Save
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={cancelEditing}
          aria-label={`Cancel editing ${ariaLabel}`}
          title="Cancel"
          data-testid="editable-name-cancel-button"
        >
          Cancel
        </Button>
      </div>
      {(error || validationError) && (
        <p
          id={helperId}
          role="alert"
          data-testid="editable-name-error"
          className="text-xs font-medium text-red-400"
        >
          {error || validationError}
        </p>
      )}
    </div>
  );
};

export default EditableNameField;
