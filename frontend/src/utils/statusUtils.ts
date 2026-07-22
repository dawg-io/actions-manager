import { WorkflowStatusData } from '../types/workflow';

// Status management functions
export const getStatusIcon = (status: string): string => {
  switch (status.toLowerCase()) {
    case 'success': return '✅';
    case 'failure': return '❌';
    case 'in_progress': case 'queued': case 'pending': return '🟡';
    case 'cancelled': return '⚫';
    default: return '❓';
  }
};

export const getStatusColor = (status: string): string => {
  switch (status.toLowerCase()) {
    case 'success': return 'var(--color-success)';
    case 'failure': return 'var(--color-error)';
    case 'in_progress': case 'queued': case 'pending': return 'var(--color-warning)';
    case 'cancelled': return 'var(--color-muted)';
    default: return 'var(--text-secondary)';
  }
};

export const getWorkflowStatusDisplay = (
  workflowName: string,
  workflowStatuses: Record<string, WorkflowStatusData>,
  selectedRepos: string[]
) => {
  if (!workflowName || !workflowStatuses) return null;
  
  return selectedRepos.map(repo => ({
    repo,
    status: workflowStatuses[`${workflowName}-${repo}`] || { status: 'unknown' }
  })).filter(item => item.status);
};