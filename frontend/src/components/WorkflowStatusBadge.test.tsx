import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import WorkflowStatusBadge, {
  WORKFLOW_STATUS_CONFIG,
  WORKFLOW_STATUS_FALLBACK,
} from './WorkflowStatusBadge';

describe('WorkflowStatusBadge', () => {
  describe('known status keys render the correct label and data-testid', () => {
    test('new → "New Local"', () => {
      render(<WorkflowStatusBadge status="new" />);
      expect(screen.getByText('New Local')).toBeInTheDocument();
      expect(screen.getByTestId('workflow-status-badge')).toBeInTheDocument();
    });

    test('committed_locally → "Committed Locally"', () => {
      render(<WorkflowStatusBadge status="committed_locally" />);
      expect(screen.getByText('Committed Locally')).toBeInTheDocument();
    });

    test('under_review → "Under Review"', () => {
      render(<WorkflowStatusBadge status="under_review" />);
      expect(screen.getByText('Under Review')).toBeInTheDocument();
    });

    test('synced_with_github → "Synced"', () => {
      render(<WorkflowStatusBadge status="synced_with_github" />);
      expect(screen.getByText('Synced')).toBeInTheDocument();
    });

    test('linked → "Linked"', () => {
      render(<WorkflowStatusBadge status="linked" />);
      expect(screen.getByText('Linked')).toBeInTheDocument();
    });

    test('draft → "Draft"', () => {
      render(<WorkflowStatusBadge status="draft" />);
      expect(screen.getByText('Draft')).toBeInTheDocument();
    });

    test('unsaved → "Unsaved"', () => {
      render(<WorkflowStatusBadge status="unsaved" />);
      expect(screen.getByText('Unsaved')).toBeInTheDocument();
    });
  });

  describe('label override', () => {
    test('label prop overrides the default status label', () => {
      render(<WorkflowStatusBadge status="committed_locally" label="Draft" />);
      expect(screen.getByText('Draft')).toBeInTheDocument();
      expect(screen.queryByText('Committed Locally')).not.toBeInTheDocument();
    });

    test('label prop works for synced_with_github', () => {
      render(<WorkflowStatusBadge status="synced_with_github" label="Synced" />);
      expect(screen.getByText('Synced')).toBeInTheDocument();
    });
  });

  describe('case-insensitive status lookup', () => {
    test('SYNCED_WITH_GITHUB (uppercase) renders "Synced"', () => {
      render(<WorkflowStatusBadge status="SYNCED_WITH_GITHUB" />);
      expect(screen.getByText('Synced')).toBeInTheDocument();
    });

    test('NEW (uppercase) renders "New Local"', () => {
      render(<WorkflowStatusBadge status="NEW" />);
      expect(screen.getByText('New Local')).toBeInTheDocument();
    });

    test('Under_Review (mixed case) renders "Under Review"', () => {
      render(<WorkflowStatusBadge status="Under_Review" />);
      expect(screen.getByText('Under Review')).toBeInTheDocument();
    });
  });

  describe('unknown status fallback', () => {
    test('renders nothing for unknown status without a label override', () => {
      const { container } = render(<WorkflowStatusBadge status="__unknown_xyz__" />);
      // WORKFLOW_STATUS_FALLBACK has an empty label so the badge should not render
      expect(container.firstChild).toBeNull();
    });

    test('renders with fallback styles when unknown status has a label override', () => {
      render(<WorkflowStatusBadge status="__unknown_xyz__" label="Custom" />);
      expect(screen.getByText('Custom')).toBeInTheDocument();
    });
  });

  describe('custom data-testid', () => {
    test('uses provided data-testid', () => {
      render(<WorkflowStatusBadge status="synced_with_github" data-testid="my-badge" />);
      expect(screen.getByTestId('my-badge')).toBeInTheDocument();
    });

    test('defaults to workflow-status-badge when no data-testid provided', () => {
      render(<WorkflowStatusBadge status="new" />);
      expect(screen.getByTestId('workflow-status-badge')).toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    test('badge has aria-label derived from the display label', () => {
      render(<WorkflowStatusBadge status="synced_with_github" />);
      expect(screen.getByLabelText('Status: Synced')).toBeInTheDocument();
    });

    test('badge title matches the display label', () => {
      render(<WorkflowStatusBadge status="new" />);
      const badge = screen.getByTestId('workflow-status-badge');
      expect(badge).toHaveAttribute('title', 'New Local');
    });
  });

  describe('WORKFLOW_STATUS_CONFIG exports', () => {
    test('exports a config entry for each expected status key', () => {
      const expectedKeys = [
        'new',
        'committed_locally',
        'under_review',
        'synced_with_github',
        'linked',
        'draft',
        'unsaved',
      ];
      expectedKeys.forEach((key) => {
        expect(WORKFLOW_STATUS_CONFIG[key]).toBeDefined();
        expect(WORKFLOW_STATUS_CONFIG[key].label).toBeTruthy();
      });
    });

    test('WORKFLOW_STATUS_FALLBACK has an empty label', () => {
      expect(WORKFLOW_STATUS_FALLBACK.label).toBe('');
    });
  });
});
