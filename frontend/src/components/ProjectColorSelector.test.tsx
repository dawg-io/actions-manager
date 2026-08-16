import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import ProjectColorSelector from './ProjectColorSelector';

describe('ProjectColorSelector', () => {
  const user = userEvent.setup();

  test('standard projects do not see the RWX-only purple/green options', () => {
    render(<ProjectColorSelector value="blue" onChange={vi.fn()} projectType="standard" />);

    expect(screen.queryByRole('radio', { name: 'Purple' })).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Green' })).not.toBeInTheDocument();
    ['Blue', 'Amber', 'Rose', 'Cyan', 'Slate', 'Orange', 'Sky'].forEach((label) => {
      expect(screen.getByRole('radio', { name: label })).toBeInTheDocument();
    });
    expect(screen.getAllByRole('radio')).toHaveLength(7);
  });

  test('defaults to the standard (restricted) color list when projectType is omitted', () => {
    render(<ProjectColorSelector value="blue" onChange={vi.fn()} />);

    expect(screen.queryByRole('radio', { name: 'Purple' })).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Green' })).not.toBeInTheDocument();
  });

  test('rwx projects see only purple and green', () => {
    render(<ProjectColorSelector value="purple" onChange={vi.fn()} projectType="rwx" />);

    expect(screen.getByRole('radio', { name: 'Purple' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Green' })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Blue' })).not.toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Amber' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
  });

  test('a grandfathered RWX-only color stays visible while selected on a standard project', () => {
    render(<ProjectColorSelector value="purple" onChange={vi.fn()} projectType="standard" />);

    expect(screen.getByRole('radio', { name: 'Purple' })).toBeChecked();
    expect(screen.queryByRole('radio', { name: 'Green' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(8);
  });

  test('a grandfathered standard color stays visible while selected on an rwx project', () => {
    render(<ProjectColorSelector value="blue" onChange={vi.fn()} projectType="rwx" />);

    expect(screen.getByRole('radio', { name: 'Blue' })).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Purple' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Green' })).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(3);
  });

  test('selecting a color calls onChange with the color key', async () => {
    const onChange = vi.fn();
    render(<ProjectColorSelector value="purple" onChange={onChange} projectType="rwx" />);

    await user.click(screen.getByRole('radio', { name: 'Green' }));

    expect(onChange).toHaveBeenCalledWith('green');
  });
});
