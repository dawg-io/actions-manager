import React, { useRef } from 'react';
import WorkflowResourcePicker from './WorkflowResourcePicker';
import { useWorkflowResources } from './WorkflowResourcesContext';
import { insertIntoText } from '../utils/workflowResources';

interface ResourceTextInputProps {
  value: string;
  onChange: (value: string) => void;
  id?: string;
  className?: string;
  placeholder?: string;
  multiline?: boolean;
  rows?: number;
  ariaLabel?: string;
  /** Extra classes for the picker trigger, so it can align inside block layouts. */
  pickerClassName?: string;
}

/**
 * A GUI-editor text field paired with the project resource picker.
 *
 * Renders as a fragment so the field and the trigger stay siblings inside the
 * caller's existing flex row - wrapping them would break the `flex: 1` sizing
 * the legacy row styles rely on.
 *
 * The trigger is omitted when the project has no resources, so forms in
 * projects without secrets or variables stay uncluttered.
 */
const ResourceTextInput: React.FC<ResourceTextInputProps> = ({
  value,
  onChange,
  id,
  className,
  placeholder,
  multiline = false,
  rows,
  ariaLabel,
  pickerClassName,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { resources } = useWorkflowResources();

  // Matches what the field-variant picker will actually offer: environments are
  // filtered out there, so a project with only environments gets no trigger
  // rather than one that opens onto an empty list.
  const hasInsertableResource = resources.some((resource) => resource.kind !== 'environment');

  // An untouched field still reports a caret at offset 0, which would insert
  // before the existing text. Only trust a caret the user actually placed;
  // otherwise append.
  const caretRef = useRef<{ start: number; end: number } | null>(null);

  const rememberCaret = (event: React.SyntheticEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const target = event.currentTarget;
    caretRef.current = {
      start: target.selectionStart ?? target.value.length,
      end: target.selectionEnd ?? target.value.length,
    };
  };

  const handleInsert = (text: string) => {
    const caret = caretRef.current ?? { start: value.length, end: value.length };
    const next = insertIntoText(value, caret.start, caret.end, text);

    onChange(next.text);
    caretRef.current = { start: next.cursor, end: next.cursor };

    // The value lands via the parent's state, so the caret can only be restored
    // once that render has flushed.
    requestAnimationFrame(() => {
      const field: HTMLInputElement | HTMLTextAreaElement | null =
        inputRef.current ?? textareaRef.current;
      if (!field) return;
      field.focus();
      field.setSelectionRange(next.cursor, next.cursor);
    });
  };

  const shared = {
    id,
    value,
    placeholder,
    className,
    'aria-label': ariaLabel,
    onSelect: rememberCaret,
    onKeyUp: rememberCaret,
    onClick: rememberCaret,
  };

  return (
    <>
      {multiline ? (
        <textarea
          {...shared}
          ref={textareaRef}
          rows={rows}
          onChange={(event) => {
            rememberCaret(event);
            onChange(event.target.value);
          }}
        />
      ) : (
        <input
          {...shared}
          ref={inputRef}
          type="text"
          onChange={(event) => {
            rememberCaret(event);
            onChange(event.target.value);
          }}
        />
      )}
      {hasInsertableResource && (
        <span className={pickerClassName}>
          <WorkflowResourcePicker variant="field" onInsert={handleInsert} />
        </span>
      )}
    </>
  );
};

export default ResourceTextInput;
