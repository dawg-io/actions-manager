import React from 'react';
import type { WorkflowDiagnostic } from './YAMLEditor';
// eslint-disable-next-line no-restricted-imports -- Legacy: TODO migrate CSS file to Tailwind CSS classes
import '../styles/ValidationPanel.css';

interface ValidationPanelProps {
  diagnostics: WorkflowDiagnostic[];
  onDiagnosticClick?: (diagnostic: WorkflowDiagnostic) => void;
}

function getDiagnosticIdentity(diagnostic: WorkflowDiagnostic): string {
  return [
    diagnostic.source ?? 'unknown',
    diagnostic.severity,
    diagnostic.line ?? 0,
    diagnostic.column ?? 0,
    diagnostic.message,
  ].join(':');
}

const severityIcon: Record<string, string> = {
  error: '❌',
  warning: '⚠️',
  info: 'ℹ️'
};

const severityLabel: Record<string, string> = {
  error: 'Error',
  warning: 'Warning',
  info: 'Info'
};

const ValidationPanel: React.FC<ValidationPanelProps> = ({ diagnostics, onDiagnosticClick }) => {
  if (diagnostics.length === 0) return null;

  const hasErrors = diagnostics.some(d => d.severity === 'error');
  const hasWarnings = diagnostics.some(d => d.severity === 'warning');
  const isClickable = Boolean(onDiagnosticClick);
  const keyOccurrences = new Map<string, number>();

  const headerText = hasErrors
    ? 'Workflow validation failed'
    : hasWarnings
    ? 'Workflow validation warnings'
    : 'Workflow validation notes';

  return (
    <div className="validation-panel" data-testid="validation-panel">
      <div className={`validation-panel-header ${hasErrors ? 'has-errors' : hasWarnings ? 'has-warnings' : 'has-info'}`}>
        <span className="validation-panel-icon">{hasErrors ? '❌' : hasWarnings ? '⚠️' : 'ℹ️'}</span>
        <span className="validation-panel-title">{headerText}</span>
        <span className="validation-panel-count">{diagnostics.length} issue{diagnostics.length !== 1 ? 's' : ''}</span>
      </div>
      <ul className="validation-panel-list">
        {diagnostics.map((diag) => {
          const identity = getDiagnosticIdentity(diag);
          const occurrence = (keyOccurrences.get(identity) ?? 0) + 1;
          keyOccurrences.set(identity, occurrence);

          return (
            <li
              key={occurrence === 1 ? identity : `${identity}:${occurrence}`}
              className={`validation-panel-item severity-${diag.severity}${isClickable ? ' clickable' : ''}`}
              onClick={isClickable ? () => onDiagnosticClick?.(diag) : undefined}
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
              onKeyDown={isClickable ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onDiagnosticClick?.(diag);
                }
              } : undefined}
            >
              <span className="validation-item-icon">{severityIcon[diag.severity]}</span>
              <span className="validation-item-content">
                {diag.line && <span className="validation-item-line">Line {diag.line}</span>}
                <span className="validation-item-message">{diag.message}</span>
                {diag.source && <span className="validation-item-source">{diag.source}</span>}
              </span>
              <span className="validation-item-severity">{severityLabel[diag.severity]}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default ValidationPanel;
