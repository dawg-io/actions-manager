import React, { useState, useEffect } from 'react';

interface OpenInGitHubModalProps {
  isOpen: boolean;
  onClose: () => void;
  workflowName: string;
  repositories: string[];
  buildWorkflowUrl: (repo: string) => string | null;
  buildRepoUrl: (repo: string) => string | null;
}

const OpenInGitHubModal: React.FC<OpenInGitHubModalProps> = ({
  isOpen,
  onClose,
  workflowName,
  repositories,
  buildWorkflowUrl,
  buildRepoUrl
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  // Reset search when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setSearchQuery('');
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

  const filteredRepositories = repositories.filter(repo =>
    repo.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleOpenWorkflow = (repo: string) => {
    const url = buildWorkflowUrl(repo);
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  const handleOpenRepository = (repo: string) => {
    const url = buildRepoUrl(repo);
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-gray-900 rounded-lg border border-gray-700 shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
          {/* Header */}
          <div className="border-b border-gray-700 p-6">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl font-semibold text-white">
                Open in GitHub
              </h2>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded hover:bg-gray-800"
                aria-label="Close modal"
              >
                <span className="text-2xl">×</span>
              </button>
            </div>
            <p className="text-sm text-gray-400">
              Workflow: <span className="text-white font-mono">{workflowName}</span>
            </p>
          </div>

          {/* Search (only show if more than 3 repos) */}
          {repositories.length > 3 && (
            <div className="p-4 border-b border-gray-700">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search repositories..."
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          )}

          {/* Repository List */}
          <div className="flex-1 overflow-y-auto p-4">
            {filteredRepositories.length === 0 ? (
              <div className="text-center text-gray-400 py-8">
                No repositories found
              </div>
            ) : (
              <div className="space-y-3">
                {filteredRepositories.map((repo) => {
                  const workflowUrl = buildWorkflowUrl(repo);
                  const repoUrl = buildRepoUrl(repo);

                  return (
                    <div
                      key={repo}
                      className="bg-gray-800 rounded-lg border border-gray-700 p-4 hover:border-gray-600 transition-colors"
                    >
                      <div className="flex items-center justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <h3 className="text-white font-medium truncate">
                            {repo}
                          </h3>
                        </div>
                        <div className="flex gap-2 flex-shrink-0">
                          {workflowUrl ? (
                            <button
                              onClick={() => handleOpenWorkflow(repo)}
                              className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900 transition-colors"
                            >
                              Open Workflow
                            </button>
                          ) : (
                            <button
                              disabled
                              title="Workflow URL cannot be built for this repository"
                              className="px-3 py-1.5 bg-gray-700 text-gray-500 text-sm rounded-lg cursor-not-allowed"
                            >
                              Open Workflow
                            </button>
                          )}
                          {repoUrl ? (
                            <button
                              onClick={() => handleOpenRepository(repo)}
                              className="px-3 py-1.5 bg-gray-700 text-white text-sm rounded-lg hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 focus:ring-offset-gray-900 transition-colors"
                            >
                              Open Repository
                            </button>
                          ) : (
                            <button
                              disabled
                              title="Repository URL cannot be built"
                              className="px-3 py-1.5 bg-gray-700 text-gray-500 text-sm rounded-lg cursor-not-allowed"
                            >
                              Open Repository
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-gray-700 p-4">
            <button
              onClick={onClose}
              className="w-full px-4 py-2 bg-gray-800 text-gray-300 rounded-lg hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 focus:ring-offset-gray-900 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

export default OpenInGitHubModal;
