import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import EditableNameField from './EditableNameField';

// Mock PrefixedInput to a simple controlled <input> with a stable testid so
// we can drive it from tests regardless of the (Tailwind-heavy) markup.
vi.mock('./PrefixedInput', () => ({
  __esModule: true,
  default: ({ value, onChange, placeholder, prefix, suffix, onKeyDown, id }: any) => (
    <span data-testid="prefixed-input-wrapper" data-prefix={prefix} data-suffix={suffix}>
      <input
        id={id}
        data-testid="prefixed-input"
        value={value || ''}
        onChange={(e) => onChange && onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
      />
    </span>
  ),
}));

describe('EditableNameField', () => {
  const user = userEvent.setup();

  test('renders read-only display by default with prefix/suffix concatenated', () => {
    const onSave = jest.fn();
    render(
      <EditableNameField
        value="my-workflow"
        onSave={onSave}
        prefix="AM_PROJ_"
        suffix=".yml"
        ariaLabel="workflow name"
      />,
    );

    expect(screen.getByTestId('editable-name-field')).toHaveAttribute('data-mode', 'readonly');
    expect(screen.getByTestId('editable-name-display')).toHaveTextContent('AM_PROJ_my-workflow.yml');
    // Input should not be present until user clicks edit.
    expect(screen.queryByTestId('prefixed-input')).not.toBeInTheDocument();
    // Save & Cancel buttons should not be present in read-only mode.
    expect(screen.queryByTestId('editable-name-save-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('editable-name-cancel-button')).not.toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  test('clicking the edit button switches to edit mode', async () => {
    render(
      <EditableNameField
        value="my-name"
        onSave={jest.fn()}
        ariaLabel="project name"
      />,
    );

    await user.click(screen.getByTestId('editable-name-edit-button'));

    expect(screen.getByTestId('editable-name-field')).toHaveAttribute('data-mode', 'editing');
    expect(screen.getByTestId('editable-name-save-button')).toBeInTheDocument();
    expect(screen.getByTestId('editable-name-cancel-button')).toBeInTheDocument();
  });

  test('Save is disabled when value is unchanged', async () => {
    render(
      <EditableNameField
        value="my-name"
        onSave={jest.fn()}
        ariaLabel="project name"
      />,
    );

    await user.click(screen.getByTestId('editable-name-edit-button'));
    expect(screen.getByTestId('editable-name-save-button')).toBeDisabled();
  });

  test('Cancel restores the original value and exits edit mode', async () => {
    const onSave = jest.fn();
    render(
      <EditableNameField
        value="original-name"
        onSave={onSave}
        ariaLabel="project name"
      />,
    );

    await user.click(screen.getByTestId('editable-name-edit-button'));
    const input = screen.getByLabelText('project name');
    await user.clear(input);
    await user.type(input, 'changed-name');
    await user.click(screen.getByTestId('editable-name-cancel-button'));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByTestId('editable-name-display')).toHaveTextContent('original-name');

    // Re-entering edit mode should show the original value, not the discarded one.
    await user.click(screen.getByTestId('editable-name-edit-button'));
    expect(screen.getByLabelText('project name')).toHaveValue('original-name');
  });

  test('Save persists the new value via onSave and exits edit mode', async () => {
    const onSave = jest.fn();
    render(
      <EditableNameField
        value="old"
        onSave={onSave}
        ariaLabel="project name"
      />,
    );

    await user.click(screen.getByTestId('editable-name-edit-button'));
    const input = screen.getByLabelText('project name');
    await user.clear(input);
    await user.type(input, 'new');
    await user.click(screen.getByTestId('editable-name-save-button'));

    expect(onSave).toHaveBeenCalledWith('new');
    expect(screen.getByTestId('editable-name-field')).toHaveAttribute('data-mode', 'readonly');
  });

  test('blocks Save and surfaces validation error for invalid input', async () => {
    const onSave = jest.fn();
    render(
      <EditableNameField
        value="ok"
        onSave={onSave}
        ariaLabel="workflow name"
        validate={(v) => (v.includes('/') ? 'no slashes allowed' : null)}
      />,
    );

    await user.click(screen.getByTestId('editable-name-edit-button'));
    const input = screen.getByLabelText('workflow name');
    await user.clear(input);
    await user.type(input, 'bad/name');

    const saveBtn = screen.getByTestId('editable-name-save-button');
    expect(saveBtn).toBeDisabled();
    expect(screen.getByTestId('editable-name-error')).toHaveTextContent('no slashes allowed');
    expect(onSave).not.toHaveBeenCalled();
  });

  test('disabled prop hides the edit affordance', () => {
    render(
      <EditableNameField
        value="locked"
        onSave={jest.fn()}
        ariaLabel="project name"
        disabled
      />,
    );

    expect(screen.getByTestId('editable-name-edit-button')).toBeDisabled();
  });

  test('Escape key cancels editing', async () => {
    const onSave = jest.fn();
    render(
      <EditableNameField value="orig" onSave={onSave} ariaLabel="project name" />,
    );

    await user.click(screen.getByTestId('editable-name-edit-button'));
    const input = screen.getByLabelText('project name');
    await user.clear(input);
    await user.type(input, 'edited');
    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.getByTestId('editable-name-field')).toHaveAttribute('data-mode', 'readonly');
    });
    expect(onSave).not.toHaveBeenCalled();
  });
});
