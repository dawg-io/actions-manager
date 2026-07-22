import { getStatusIcon, getStatusColor, getWorkflowStatusDisplay } from './statusUtils';
import { WorkflowStatusData } from '../types/workflow';

describe('statusUtils', () => {
  describe('getStatusIcon', () => {
    test('should return success icon for success status', () => {
      expect(getStatusIcon('success')).toBe('✅');
      expect(getStatusIcon('SUCCESS')).toBe('✅');
    });

    test('should return failure icon for failure status', () => {
      expect(getStatusIcon('failure')).toBe('❌');
      expect(getStatusIcon('FAILURE')).toBe('❌');
    });

    test('should return warning icon for in_progress status', () => {
      expect(getStatusIcon('in_progress')).toBe('🟡');
      expect(getStatusIcon('IN_PROGRESS')).toBe('🟡');
    });

    test('should return warning icon for queued status', () => {
      expect(getStatusIcon('queued')).toBe('🟡');
      expect(getStatusIcon('QUEUED')).toBe('🟡');
    });

    test('should return warning icon for pending status', () => {
      expect(getStatusIcon('pending')).toBe('🟡');
      expect(getStatusIcon('PENDING')).toBe('🟡');
    });

    test('should return cancelled icon for cancelled status', () => {
      expect(getStatusIcon('cancelled')).toBe('⚫');
      expect(getStatusIcon('CANCELLED')).toBe('⚫');
    });

    test('should return unknown icon for unknown status', () => {
      expect(getStatusIcon('unknown')).toBe('❓');
      expect(getStatusIcon('invalid')).toBe('❓');
      expect(getStatusIcon('')).toBe('❓');
    });
  });

  describe('getStatusColor', () => {
    test('should return success color for success status', () => {
      expect(getStatusColor('success')).toBe('var(--color-success)');
      expect(getStatusColor('SUCCESS')).toBe('var(--color-success)');
    });

    test('should return error color for failure status', () => {
      expect(getStatusColor('failure')).toBe('var(--color-error)');
      expect(getStatusColor('FAILURE')).toBe('var(--color-error)');
    });

    test('should return warning color for in_progress status', () => {
      expect(getStatusColor('in_progress')).toBe('var(--color-warning)');
      expect(getStatusColor('IN_PROGRESS')).toBe('var(--color-warning)');
    });

    test('should return warning color for queued status', () => {
      expect(getStatusColor('queued')).toBe('var(--color-warning)');
      expect(getStatusColor('QUEUED')).toBe('var(--color-warning)');
    });

    test('should return warning color for pending status', () => {
      expect(getStatusColor('pending')).toBe('var(--color-warning)');
      expect(getStatusColor('PENDING')).toBe('var(--color-warning)');
    });

    test('should return muted color for cancelled status', () => {
      expect(getStatusColor('cancelled')).toBe('var(--color-muted)');
      expect(getStatusColor('CANCELLED')).toBe('var(--color-muted)');
    });

    test('should return default color for unknown status', () => {
      expect(getStatusColor('unknown')).toBe('var(--text-secondary)');
      expect(getStatusColor('invalid')).toBe('var(--text-secondary)');
      expect(getStatusColor('')).toBe('var(--text-secondary)');
    });
  });

  describe('getWorkflowStatusDisplay', () => {
    test('should return status display for each repository', () => {
      const workflowStatuses: Record<string, WorkflowStatusData> = {
        'build-owner/repo1': { status: 'success' },
        'build-owner/repo2': { status: 'failure' }
      };
      const selectedRepos = ['owner/repo1', 'owner/repo2'];

      const result = getWorkflowStatusDisplay('build', workflowStatuses, selectedRepos);

      expect(result).toEqual([
        { repo: 'owner/repo1', status: { status: 'success' } },
        { repo: 'owner/repo2', status: { status: 'failure' } }
      ]);
    });

    test('should return unknown status for repositories without status', () => {
      const workflowStatuses: Record<string, WorkflowStatusData> = {
        'build-owner/repo1': { status: 'success' }
      };
      const selectedRepos = ['owner/repo1', 'owner/repo2'];

      const result = getWorkflowStatusDisplay('build', workflowStatuses, selectedRepos);

      expect(result).toEqual([
        { repo: 'owner/repo1', status: { status: 'success' } },
        { repo: 'owner/repo2', status: { status: 'unknown' } }
      ]);
    });

    test('should return null for empty workflow name', () => {
      const workflowStatuses: Record<string, WorkflowStatusData> = {};
      const selectedRepos = ['owner/repo1'];

      const result = getWorkflowStatusDisplay('', workflowStatuses, selectedRepos);

      expect(result).toBeNull();
    });

    test('should return null for null workflow statuses', () => {
      const selectedRepos = ['owner/repo1'];

      const result = getWorkflowStatusDisplay('build', null as any, selectedRepos);

      expect(result).toBeNull();
    });

    test('should handle empty selectedRepos array', () => {
      const workflowStatuses: Record<string, WorkflowStatusData> = {};
      const selectedRepos: string[] = [];

      const result = getWorkflowStatusDisplay('build', workflowStatuses, selectedRepos);

      expect(result).toEqual([]);
    });

    test('should filter out items without status', () => {
      const workflowStatuses: Record<string, WorkflowStatusData> = {
        'build-owner/repo1': { status: 'success' }
      };
      const selectedRepos = ['owner/repo1'];

      const result = getWorkflowStatusDisplay('build', workflowStatuses, selectedRepos);

      expect(result).toBeTruthy();
      expect(result?.length).toBe(1);
    });
  });
});
