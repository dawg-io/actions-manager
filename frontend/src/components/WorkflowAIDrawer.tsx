import React, { useState, useEffect } from 'react';

interface WorkflowAIDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  workflowName: string;
  workflowType: 'Regular Workflow' | 'Reusable Workflow' | 'Linked Workflow';
  selectedRepos: string[];
  /** When provided, Preview Changes calls this with the prompt. Not wired up yet — coming post-beta. */
  onPreviewChanges?: (prompt: string) => void;
}

const WorkflowAIDrawer: React.FC<WorkflowAIDrawerProps> = ({
  isOpen,
  onClose,
  workflowName,
  workflowType,
  selectedRepos,
  onPreviewChanges
}) => {
  const [prompt, setPrompt] = useState('');
  const [contextItems, setContextItems] = useState({
    currentWorkflow: true,
    workflowType: true,
    selectedRepositories: true,
    projectSettings: true
  });

  // Reset prompt when drawer opens/closes
  useEffect(() => {
    if (!isOpen) {
      setPrompt('');
    }
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Preview Changes is only enabled when an onPreviewChanges handler is wired up.
  const isPreviewEnabled = typeof onPreviewChanges === 'function';

  const handlePreviewChanges = () => {
    if (isPreviewEnabled && prompt.trim()) {
      onPreviewChanges!(prompt);
    }
  };

  const maxCharacters = 2000;
  const characterCount = prompt.length;

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 bottom-0 w-full md:w-[480px] bg-gray-900 border-l border-gray-700 z-50 overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 border-b border-gray-700 p-6 z-10">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xl font-semibold text-white">
              Edit Workflow with AI
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors p-2 rounded hover:bg-gray-800"
              aria-label="Close drawer"
            >
              <span className="text-2xl">×</span>
            </button>
          </div>
          <p className="text-sm text-gray-400">
            Describe the change you want to make.
          </p>
          {/* Workflow context summary */}
          <p className="text-xs text-gray-500 mt-1">
            {workflowName} &middot; {workflowType}
            {selectedRepos.length > 0 && ` · ${selectedRepos.join(', ')}`}
          </p>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Not-configured notice */}
          {!isPreviewEnabled && (
            <div className="bg-yellow-900 bg-opacity-30 border border-yellow-700 rounded-lg p-3">
              <p className="text-sm text-yellow-300">
                AI workflow editing is coming soon. This feature is not available in the current beta.
              </p>
            </div>
          )}

          {/* Prompt Input */}
          <div>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value.slice(0, maxCharacters))}
              placeholder="Add CodeQL scanning and make the workflow reusable."
              className="w-full h-32 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              maxLength={maxCharacters}
            />
            <div className="flex justify-between items-center mt-2">
              <span className="text-xs text-gray-500">
                {characterCount} / {maxCharacters} characters
              </span>
            </div>
          </div>

          {/* Context Section */}
          <div>
            <h3 className="text-sm font-semibold text-white mb-3">Context</h3>
            <div className="space-y-2">
              <label className="flex items-center space-x-3 text-sm text-gray-300 cursor-pointer hover:bg-gray-800 p-2 rounded transition-colors">
                <input
                  type="checkbox"
                  checked={contextItems.currentWorkflow}
                  onChange={(e) => setContextItems({ ...contextItems, currentWorkflow: e.target.checked })}
                  className="w-4 h-4 text-blue-600 bg-gray-700 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
                />
                <span>Current workflow YAML</span>
              </label>
              <label className="flex items-center space-x-3 text-sm text-gray-300 cursor-pointer hover:bg-gray-800 p-2 rounded transition-colors">
                <input
                  type="checkbox"
                  checked={contextItems.workflowType}
                  onChange={(e) => setContextItems({ ...contextItems, workflowType: e.target.checked })}
                  className="w-4 h-4 text-blue-600 bg-gray-700 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
                />
                <span>Workflow type</span>
              </label>
              <label className="flex items-center space-x-3 text-sm text-gray-300 cursor-pointer hover:bg-gray-800 p-2 rounded transition-colors">
                <input
                  type="checkbox"
                  checked={contextItems.selectedRepositories}
                  onChange={(e) => setContextItems({ ...contextItems, selectedRepositories: e.target.checked })}
                  className="w-4 h-4 text-blue-600 bg-gray-700 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
                />
                <span>Selected repositories</span>
              </label>
              <label className="flex items-center space-x-3 text-sm text-gray-300 cursor-pointer hover:bg-gray-800 p-2 rounded transition-colors">
                <input
                  type="checkbox"
                  checked={contextItems.projectSettings}
                  onChange={(e) => setContextItems({ ...contextItems, projectSettings: e.target.checked })}
                  className="w-4 h-4 text-blue-600 bg-gray-700 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
                />
                <span>Project settings</span>
              </label>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-3 pt-4">
            <button
              onClick={handlePreviewChanges}
              disabled={!isPreviewEnabled || !prompt.trim()}
              title={!isPreviewEnabled ? 'AI workflow editing is not configured yet' : undefined}
              className="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Preview Changes
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2.5 bg-gray-800 text-gray-300 rounded-lg font-medium hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 focus:ring-offset-gray-900 transition-colors"
            >
              Cancel
            </button>
          </div>

          {/* Informational Note */}
          <div className="bg-blue-900 bg-opacity-20 border border-blue-700 rounded-lg p-4">
            <p className="text-sm text-blue-200 leading-relaxed">
              <span className="font-medium">Note:</span> AI suggestions update the editor first. They do not commit directly to GitHub.
            </p>
          </div>
        </div>
      </div>
    </>
  );
};

export default WorkflowAIDrawer;
