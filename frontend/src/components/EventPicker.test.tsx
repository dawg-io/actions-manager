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
