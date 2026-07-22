import React from 'react';
import { createEvent, fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ValidationPanel from './ValidationPanel';
import type { WorkflowDiagnostic } from './YAMLEditor';

const warningDiagnostic: WorkflowDiagnostic = {
  severity: 'warning',
  message: 'Workflow is missing "jobs" section',
  line: 1,
  source: 'workflow-structure',
};

describe('ValidationPanel', () => {
  test('renders warning header and singular issue count', () => {
    render(<ValidationPanel diagnostics={[warningDiagnostic]} />);

    expect(screen.getByTestId('validation-panel')).toBeInTheDocument();
    expect(screen.getByText('Workflow validation warnings')).toBeInTheDocument();
    expect(screen.getByText('1 issue')).toBeInTheDocument();
    expect(screen.getByText('Workflow is missing "jobs" section')).toBeInTheDocument();
  });

  test('renders error header and pluralized issue count', () => {
    render(
      <ValidationPanel
        diagnostics={[
          {
            severity: 'error',
            message: 'YAML syntax error: unexpected end of stream',
            line: 3,
            source: 'yaml-parser',
          },
          warningDiagnostic,
        ]}
      />
    );

    expect(screen.getByText('Workflow validation failed')).toBeInTheDocument();
    expect(screen.getByText('2 issues')).toBeInTheDocument();
  });

  test('renders non-interactive items when no click handler is provided', () => {
    render(<ValidationPanel diagnostics={[warningDiagnostic]} />);

    const item = screen.getByText('Workflow is missing "jobs" section').closest('li');
    expect(item).toHaveClass('validation-panel-item');
    expect(item).not.toHaveClass('clickable');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  test('activates interactive items from keyboard and prevents space scrolling', () => {
    const handleDiagnosticClick = jest.fn();

    render(
      <ValidationPanel
        diagnostics={[warningDiagnostic]}
        onDiagnosticClick={handleDiagnosticClick}
      />
    );

    const item = screen.getByRole('button', { name: /workflow is missing "jobs" section/i });
    expect(item).toHaveClass('clickable');

    const spaceEvent = createEvent.keyDown(item, { key: ' ' });
    fireEvent(item, spaceEvent);

    expect(spaceEvent.defaultPrevented).toBe(true);
    expect(handleDiagnosticClick).toHaveBeenCalledWith(warningDiagnostic);

    fireEvent.keyDown(item, { key: 'Enter' });
    expect(handleDiagnosticClick).toHaveBeenCalledTimes(2);
  });
});
