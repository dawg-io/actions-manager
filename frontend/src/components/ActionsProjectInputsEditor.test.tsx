import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import ActionsProjectInputsEditor from './ActionsProjectInputsEditor';
import type { ActionInput } from '../api/actionsProjects';

function makeInput(overrides: Partial<ActionInput> = {}): ActionInput {
  return {
    name: 'greeting', description: null, required: false, default: null,
    type: 'string', options: null,
    ...overrides,
  };
}

describe('ActionsProjectInputsEditor', () => {
  it('adds a new input defaulted to type string', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ActionsProjectInputsEditor inputs={[]} onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: /Add input/ }));

    expect(onChange).toHaveBeenCalledWith([
      { name: '', description: null, required: false, default: null, type: 'string', options: null },
    ]);
  });

  it('shows an options textarea only when type is choice', () => {
    const { rerender } = render(
      <ActionsProjectInputsEditor inputs={[makeInput({ type: 'string' })]} onChange={vi.fn()} />
    );
    expect(screen.queryByLabelText(/Options/)).not.toBeInTheDocument();

    rerender(
      <ActionsProjectInputsEditor
        inputs={[makeInput({ type: 'choice', options: ['a', 'b'] })]}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByLabelText(/Options/)).toBeInTheDocument();
  });

  it('renders a checkbox default field for boolean-typed inputs', () => {
    render(<ActionsProjectInputsEditor inputs={[makeInput({ type: 'boolean', default: 'true' })]} onChange={vi.fn()} />);
    const checkbox = screen.getByRole('checkbox', { name: /Default: true/ });
    expect(checkbox).toBeChecked();
  });

  it('renders a select default field populated from options for choice-typed inputs', () => {
    render(
      <ActionsProjectInputsEditor
        inputs={[makeInput({ type: 'choice', options: ['low', 'high'], default: 'high' })]}
        onChange={vi.fn()}
      />
    );
    const select = screen.getByLabelText('Default') as HTMLSelectElement;
    expect(select.value).toBe('high');
    expect(screen.getByRole('option', { name: 'low' })).toBeInTheDocument();
  });

  it('clears options and default when switching away from choice', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ActionsProjectInputsEditor
        inputs={[makeInput({ type: 'choice', options: ['a', 'b'], default: 'a' })]}
        onChange={onChange}
      />
    );

    await user.selectOptions(screen.getByLabelText('Type'), 'string');

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ type: 'string', options: null, default: null }),
    ]);
  });
});
