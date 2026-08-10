import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import EventPicker from './EventPicker';
import { WorkflowEvent } from '../utils/workflowGuiConversion';

describe('EventPicker advanced options', () => {
  const mockOnChange = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  const openAdvanced = () => {
    fireEvent.click(screen.getByTitle('Advanced options'));
  };

  test('toggling a pull_request sub-type checkbox updates types', () => {
    const events: WorkflowEvent[] = [{ type: 'pull_request', types: ['opened'] }];
    render(<EventPicker events={events} onChange={mockOnChange} />);
    openAdvanced();

    fireEvent.click(screen.getByLabelText('synchronize'));

    expect(mockOnChange).toHaveBeenCalledWith([
      { type: 'pull_request', types: ['opened', 'synchronize'] },
    ]);
  });

  test('unchecking the last sub-type clears types', () => {
    const events: WorkflowEvent[] = [{ type: 'pull_request', types: ['opened'] }];
    render(<EventPicker events={events} onChange={mockOnChange} />);
    openAdvanced();

    fireEvent.click(screen.getByLabelText('opened'));

    expect(mockOnChange).toHaveBeenCalledWith([
      { type: 'pull_request', types: undefined },
    ]);
  });

  test('adding, editing, and removing a branch', () => {
    const events: WorkflowEvent[] = [{ type: 'push' }];
    const { rerender } = render(<EventPicker events={events} onChange={mockOnChange} />);
    openAdvanced();

    fireEvent.click(screen.getByText('➕ Add Branch'));
    expect(mockOnChange).toHaveBeenLastCalledWith([{ type: 'push', branches: [''] }]);

    const withBranch: WorkflowEvent[] = [{ type: 'push', branches: ['main'] }];
    rerender(<EventPicker events={withBranch} onChange={mockOnChange} />);
    fireEvent.change(screen.getByPlaceholderText('branch name or pattern'), {
      target: { value: 'develop' },
    });
    expect(mockOnChange).toHaveBeenLastCalledWith([{ type: 'push', branches: ['develop'] }]);

    const branchInput = screen.getByPlaceholderText('branch name or pattern');
    fireEvent.click(branchInput.closest('.array-item')!.querySelector('.array-remove') as HTMLElement);
    expect(mockOnChange).toHaveBeenLastCalledWith([{ type: 'push', branches: undefined }]);
  });

  test('adding, editing, and removing a path', () => {
    const events: WorkflowEvent[] = [{ type: 'push' }];
    const { rerender } = render(<EventPicker events={events} onChange={mockOnChange} />);
    openAdvanced();

    fireEvent.click(screen.getByText('➕ Add Path'));
    expect(mockOnChange).toHaveBeenLastCalledWith([{ type: 'push', paths: [''] }]);

    const withPath: WorkflowEvent[] = [{ type: 'push', paths: ['src/**'] }];
    rerender(<EventPicker events={withPath} onChange={mockOnChange} />);
    fireEvent.change(screen.getByPlaceholderText('path pattern (e.g., src/**)'), {
      target: { value: 'docs/**' },
    });
    expect(mockOnChange).toHaveBeenLastCalledWith([{ type: 'push', paths: ['docs/**'] }]);
  });
});

describe('EventPicker trigger toggle', () => {
  const mockOnChange = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  const triggerButton = (name: string) => screen.getByRole('button', { name });

  test('adds a trigger with its seeded defaults when not present', () => {
    render(<EventPicker events={[]} onChange={mockOnChange} />);

    fireEvent.click(triggerButton('Schedule'));

    expect(mockOnChange).toHaveBeenCalledWith([{ type: 'schedule', cron: '0 0 * * *' }]);
  });

  test('removes an already-added trigger on second click', () => {
    const events: WorkflowEvent[] = [{ type: 'push' }];
    render(<EventPicker events={events} onChange={mockOnChange} />);

    fireEvent.click(triggerButton('Push'));

    expect(mockOnChange).toHaveBeenCalledWith([]);
  });

  test('clicking Pull Request twice removes it instead of appending a duplicate', () => {
    const { rerender } = render(<EventPicker events={[]} onChange={mockOnChange} />);

    fireEvent.click(triggerButton('Pull Request'));
    const added = mockOnChange.mock.calls[0][0] as WorkflowEvent[];
    expect(added).toEqual([{ type: 'pull_request', types: ['opened', 'synchronize'] }]);

    rerender(<EventPicker events={added} onChange={mockOnChange} />);
    fireEvent.click(triggerButton('Pull Request'));

    expect(mockOnChange).toHaveBeenLastCalledWith([]);
  });

  test('clicking Release twice removes it instead of appending a duplicate', () => {
    const { rerender } = render(<EventPicker events={[]} onChange={mockOnChange} />);

    fireEvent.click(triggerButton('Release'));
    const added = mockOnChange.mock.calls[0][0] as WorkflowEvent[];
    expect(added).toEqual([{ type: 'release', types: ['published'] }]);

    rerender(<EventPicker events={added} onChange={mockOnChange} />);
    fireEvent.click(triggerButton('Release'));

    expect(mockOnChange).toHaveBeenLastCalledWith([]);
  });

  test('removing one trigger leaves the others untouched', () => {
    const events: WorkflowEvent[] = [{ type: 'push' }, { type: 'schedule', cron: '0 0 * * *' }];
    render(<EventPicker events={events} onChange={mockOnChange} />);

    fireEvent.click(triggerButton('Push'));

    expect(mockOnChange).toHaveBeenCalledWith([{ type: 'schedule', cron: '0 0 * * *' }]);
  });

  test('marks added triggers with aria-pressed and leaves every button enabled', () => {
    render(<EventPicker events={[{ type: 'push' }]} onChange={mockOnChange} />);

    expect(triggerButton('Push')).toHaveAttribute('aria-pressed', 'true');
    expect(triggerButton('Schedule')).toHaveAttribute('aria-pressed', 'false');
    for (const label of ['Push', 'Pull Request', 'Manual Trigger', 'Schedule', 'Release']) {
      expect(triggerButton(label)).toBeEnabled();
    }
  });

  test('keeps advanced options attached to their own event after another is removed', () => {
    const events: WorkflowEvent[] = [{ type: 'push' }, { type: 'schedule', cron: '0 0 * * *' }];
    const { rerender } = render(<EventPicker events={events} onChange={mockOnChange} />);

    // Open Advanced on the schedule event (the second card).
    fireEvent.click(screen.getAllByTitle('Advanced options')[1]);
    expect(screen.getByPlaceholderText('0 0 * * * (daily at midnight)')).toBeInTheDocument();

    // Dropping the push event must not slide the open panel onto a different card.
    rerender(<EventPicker events={[{ type: 'schedule', cron: '0 0 * * *' }]} onChange={mockOnChange} />);

    expect(screen.getByPlaceholderText('0 0 * * * (daily at midnight)')).toBeInTheDocument();
    expect(screen.queryByText('➕ Add Branch')).not.toBeInTheDocument();
  });
});
