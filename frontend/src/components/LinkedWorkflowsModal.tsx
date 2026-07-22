import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { getAvailableRwxWorkflows, RwxWorkflow } from '../api/projects';

interface LinkedWorkflowsModalProps {
  isOpen: boolean;
  user: string;
  projectName: string;
  alreadyLinkedIds: number[];
  onLink: (workflows: RwxWorkflow[]) => Promise<void>;
  onClose: () => void;
  /** When provided, only workflows from this RWX project are shown */
  filterProjectId?: number;
}

const LinkedWorkflowsModal: React.FC<LinkedWorkflowsModalProps> = ({
  isOpen,
  user,
  projectName,
  alreadyLinkedIds,
  onLink,
  onClose,
  filterProjectId,
}) => {
  const [workflows, setWorkflows] = useState<RwxWorkflow[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [adding, setAdding] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!isOpen || !user) return;
    setLoading(true);
    setError(null);
    setSelectedIds(new Set());
    getAvailableRwxWorkflows(user, projectName)
      .then((data) => setWorkflows(data))
      .catch(() => setError('Failed to load reusable workflows.'))
      .finally(() => setLoading(false));
  }, [isOpen, user, projectName]);

  // Reset selection when the project filter changes so stale IDs don't persist
  useEffect(() => {
    setSelectedIds(new Set());
  }, [filterProjectId]);

  const toggleSelect = (workflowId: number) => {
    const workflow = displayedWorkflows.find((wf) => wf.workflow_id === workflowId);
    if (workflow?.link_validation && !workflow.link_validation.allowed) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(workflowId)) {
        next.delete(workflowId);
      } else {
        next.add(workflowId);
      }
      return next;
    });
  };

  const handleAddSelected = async () => {
    const toLink = displayedWorkflows.filter(
      (wf) =>
        selectedIds.has(wf.workflow_id) &&
        !alreadyLinkedIds.includes(wf.workflow_id) &&
        wf.link_validation?.allowed !== false
    );
    if (toLink.length === 0) return;
    setAdding(true);
    try {
      await onLink(toLink);
      setSelectedIds(new Set());
    } finally {
      setAdding(false);
    }
  };

  // Filter by project when filterProjectId is provided
  const displayedWorkflows = filterProjectId
    ? workflows.filter((wf) => wf.rwx_project_id === filterProjectId)
    : workflows;

  // Group by RWX project for cleaner display
  const grouped: Record<string, RwxWorkflow[]> = {};
  for (const wf of displayedWorkflows) {
    const key = `${wf.rwx_project_id}::${wf.rwx_project_name}`;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(wf);
  }

  const newlySelectedCount = displayedWorkflows.filter(
    (wf) =>
      selectedIds.has(wf.workflow_id) &&
      !alreadyLinkedIds.includes(wf.workflow_id) &&
      wf.link_validation?.allowed !== false
  ).length;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>🔗 Link Reusable Workflow</DialogTitle>
          <DialogDescription>
            Select workflows from your Reusable Workflow projects to link into{' '}
            <strong>{projectName}</strong>.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="py-8 text-center text-slate-500 dark:text-slate-400">
            🔄 Loading available workflows…
          </div>
        )}

        {error && (
          <div className="py-4 text-center text-red-600 dark:text-red-400">{error}</div>
        )}

        {!loading && !error && displayedWorkflows.length === 0 && (
          <div className="py-8 text-center text-slate-500 dark:text-slate-400">
            <p>No reusable workflows found.</p>
            <p className="text-sm mt-2">
              Create a <strong>Reusable Workflow Project</strong> (RWX) and add workflows to it first.
            </p>
          </div>
        )}

        {!loading && !error && Object.entries(grouped).map(([groupKey, groupWorkflows]) => {
          const [, projectLabel] = groupKey.split('::');
          return (
            <div key={groupKey} className="mb-4">
              <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2 flex items-center gap-2">
                🔧 {projectLabel}
              </h4>
              <div className="space-y-2">
                {groupWorkflows.map((wf) => {
                  const isLinked = alreadyLinkedIds.includes(wf.workflow_id);
                  const validation = wf.link_validation;
                  const isUnavailable = validation?.allowed === false;
                  const unavailableReason = validation?.reason || 'Unable to determine workflow availability. Please refresh and try again.';
                  const isChecked = isLinked || (!isUnavailable && selectedIds.has(wf.workflow_id));
                  const visibilityLabel = wf.rwx_repo_visibility
                    ? wf.rwx_repo_visibility.charAt(0).toUpperCase() + wf.rwx_repo_visibility.slice(1)
                    : null;
                  return (
                    <label
                      key={wf.workflow_id}
                      className={`flex items-center gap-3 border border-slate-200 dark:border-slate-700 rounded-lg p-3 ${
                        isLinked || isUnavailable
                          ? 'opacity-60 cursor-not-allowed bg-slate-50 dark:bg-slate-900'
                          : 'cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        disabled={isLinked || isUnavailable}
                        onChange={() => !isLinked && !isUnavailable && toggleSelect(wf.workflow_id)}
                        className="h-4 w-4 rounded border-slate-300 accent-blue-600"
                      />
                      <div className="flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-slate-900 dark:text-slate-100">
                            {wf.workflow_name}
                          </span>
                          {visibilityLabel && (
                            <span className="rounded-full border border-slate-300 px-2 py-0.5 text-xs text-slate-600 dark:border-slate-600 dark:text-slate-300">
                              {visibilityLabel}
                            </span>
                          )}
                        </div>
                        {isLinked && (
                          <span className="ml-2 text-xs text-green-600 dark:text-green-400">
                            ✅ Already linked
                          </span>
                        )}
                        {isUnavailable && (
                          <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                            Not available: {unavailableReason}
                          </p>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={adding}>
            Close
          </Button>
          <Button
            onClick={handleAddSelected}
            disabled={newlySelectedCount === 0 || adding}
          >
            {adding ? '⏳ Adding…' : `Add${newlySelectedCount > 0 ? ` (${newlySelectedCount})` : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default LinkedWorkflowsModal;
