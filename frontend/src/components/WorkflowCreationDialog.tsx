import React, { useEffect, useMemo, useState } from 'react';
import { DetectedBuildResult, BuildType } from '../types/workflow';
import { normalizeWorkflowStem, validateWorkflowName } from '../utils/workflowFilename';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';

interface WorkflowCreationDialogProps {
  showWorkflowCreationDialog: boolean;
  workflowCreationType: 'regular' | 'reusable' | null;
  showDetectionResultsInModal: boolean;
  isDetecting: boolean;
  detectedBuildTypesState: DetectedBuildResult[];
  isGeneratingTemplates: boolean;
  isAILoading: boolean;
  reusableWorkflowsEnabled: boolean;
  showLinkReusableWorkflow?: boolean;
  existingWorkflowNames?: string[];
  setShowWorkflowCreationDialog: (show: boolean) => void;
  selectWorkflowType: (type: 'regular' | 'reusable') => void;
  onLinkReusableWorkflow?: () => void;
  createBlankWorkflow: (type: 'regular' | 'reusable', workflowName: string) => void;
  handleDetectBuildTypes: () => void;
  handleCreateFromTemplates: (type: 'regular' | 'reusable', workflowName: string) => void;
  handleCreateWithAI: (type: 'regular' | 'reusable', workflowName: string) => void;
  addWorkflowFromDetection: (repo: string, buildType: BuildType, workflowName: string) => Promise<void>;
  setWorkflowCreationType: (type: 'regular' | 'reusable' | null) => void;
  setShowDetectionResultsInModal: (show: boolean) => void;
  setDetectedBuildTypes: (types: DetectedBuildResult[]) => void;
}

const WorkflowCreationDialog: React.FC<WorkflowCreationDialogProps> = ({
  showWorkflowCreationDialog,
  workflowCreationType,
  showDetectionResultsInModal,
  isDetecting,
  detectedBuildTypesState,
  isGeneratingTemplates,
  isAILoading,
  reusableWorkflowsEnabled,
  showLinkReusableWorkflow = false,
  existingWorkflowNames = [],
  setShowWorkflowCreationDialog,
  selectWorkflowType,
  onLinkReusableWorkflow,
  createBlankWorkflow,
  handleDetectBuildTypes,
  handleCreateFromTemplates,
  handleCreateWithAI,
  addWorkflowFromDetection,
  setWorkflowCreationType,
  setShowDetectionResultsInModal,
  setDetectedBuildTypes
}) => {
  const canLinkReusableWorkflow = showLinkReusableWorkflow && !!onLinkReusableWorkflow;
  const [workflowName, setWorkflowName] = useState('');

  useEffect(() => {
    if (!showWorkflowCreationDialog) {
      setWorkflowName('');
    }
  }, [showWorkflowCreationDialog]);

  const workflowNameError = useMemo(() => {
    const validationError = validateWorkflowName(workflowName);
    if (validationError) return validationError;

    const stem = normalizeWorkflowStem(workflowName).toLowerCase();
    const hasDuplicate = existingWorkflowNames.some(
      name => normalizeWorkflowStem(name).toLowerCase() === stem
    );
    return hasDuplicate ? 'A workflow with this name already exists in this project.' : null;
  }, [existingWorkflowNames, workflowName]);

  const normalizedWorkflowName = normalizeWorkflowStem(workflowName);
  const isWorkflowNameValid = !!normalizedWorkflowName && !workflowNameError;

  const handleLinkReusableWorkflow = () => {
    if (!onLinkReusableWorkflow) return;
    setShowWorkflowCreationDialog(false);
    onLinkReusableWorkflow();
  };

  const renderWorkflowNameField = () => (
    <div className="space-y-2">
      <label htmlFor="workflow-name" className="block text-sm font-medium text-slate-900 dark:text-slate-100">
        Workflow Name <span className="text-red-500">*</span>
      </label>
      <input
        id="workflow-name"
        type="text"
        value={workflowName}
        onChange={(event) => setWorkflowName(event.target.value)}
        className={`w-full rounded-md border px-3 py-2 text-sm text-slate-900 shadow-sm focus:outline-none focus:ring-2 dark:bg-slate-900 dark:text-slate-100 ${
          workflowNameError
            ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
            : 'border-slate-300 focus:border-blue-500 focus:ring-blue-500/20 dark:border-slate-700'
        }`}
        placeholder="build-and-test"
        aria-invalid={!!workflowNameError}
        aria-describedby="workflow-name-help workflow-name-error"
      />
      <p id="workflow-name-help" className="text-sm text-slate-600 dark:text-slate-400">
        This name will be used for the managed workflow and the generated workflow file.
      </p>
      {workflowNameError && (
        <p id="workflow-name-error" className="text-sm text-red-600 dark:text-red-400">
          {workflowNameError}
        </p>
      )}
    </div>
  );

  return (
    <Dialog open={showWorkflowCreationDialog} onOpenChange={setShowWorkflowCreationDialog}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create New Workflow</DialogTitle>
          <DialogDescription className="sr-only">
            Create a new workflow by selecting type and creation method including blank, templates, detection, or AI generation
          </DialogDescription>
        </DialogHeader>
        
        {!workflowCreationType ? (
          <div className="space-y-4">
            <p className="text-slate-600 dark:text-slate-400">
              What type of workflow would you like to create?
            </p>
            
            <div className="grid gap-4">
              <button
                className="border-2 border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-all text-left dark:border-slate-700 dark:hover:border-blue-400"
                onClick={() => selectWorkflowType('regular')}
              >
                <div className="flex items-start gap-4">
                  <div className="text-3xl">📝</div>
                  <div className="flex-1">
                    <h4 className="font-semibold text-lg text-slate-900 mb-1 dark:text-slate-100">
                      Regular Workflow
                    </h4>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      Standard CI/CD workflows that run directly in repositories
                    </p>
                  </div>
                </div>
              </button>
              
              <button
                className={`border-2 rounded-lg p-4 transition-all text-left ${
                  !reusableWorkflowsEnabled 
                    ? 'opacity-60 cursor-not-allowed border-slate-200 dark:border-slate-700' 
                    : 'border-slate-200 hover:border-blue-500 dark:border-slate-700 dark:hover:border-blue-400'
                }`}
                onClick={() => reusableWorkflowsEnabled && selectWorkflowType('reusable')}
                disabled={!reusableWorkflowsEnabled}
                title={reusableWorkflowsEnabled 
                  ? "Create reusable workflows that can be called by other workflows across repositories"
                  : "Reusable workflows are disabled. Enable them first in the sidebar."
                }
              >
                <div className="flex items-start gap-4">
                  <div className="text-3xl">🔄</div>
                  <div className="flex-1">
                    <h4 className="font-semibold text-lg text-slate-900 mb-1 dark:text-slate-100">
                      Reusable Workflow
                    </h4>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      Modular workflows that can be called by other workflows across repositories
                    </p>
                  </div>
                </div>
              </button>

              {canLinkReusableWorkflow && (
                <button
                  className="border-2 border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-all text-left dark:border-slate-700 dark:hover:border-blue-400"
                  onClick={handleLinkReusableWorkflow}
                  title="Link an existing reusable workflow from an RWX project into this caller workflow project"
                >
                  <div className="flex items-start gap-4">
                    <div className="text-3xl">🔗</div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-lg text-slate-900 mb-1 dark:text-slate-100">
                        Link Reusable Workflow
                      </h4>
                      <p className="text-sm text-slate-600 dark:text-slate-400">
                        Connect an existing reusable workflow from an RWX project to this caller project
                      </p>
                    </div>
                  </div>
                </button>
              )}
            </div>
          </div>
        ) : showDetectionResultsInModal ? (
          <div className="space-y-4">
            <h4 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              🔍 Detected Build Types
            </h4>
            <p className="text-slate-600 dark:text-slate-400">
              Select a detected build type to create a workflow:
            </p>
            {renderWorkflowNameField()}
            
            {isDetecting ? (
              <div className="text-center py-8">
                <p className="text-slate-600 dark:text-slate-400">
                  🔄 Analyzing repositories...
                </p>
              </div>
            ) : detectedBuildTypesState.length > 0 ? (
              <div className="space-y-4">
                {detectedBuildTypesState.map((repoResult, idx) => (
                  <div key={idx} className="border border-slate-200 rounded-lg p-4 dark:border-slate-700">
                    <h5 className="font-semibold text-slate-900 mb-3 dark:text-slate-100">
                      {repoResult.repo}
                    </h5>
                    {repoResult.error ? (
                      <p className="text-red-600 text-sm dark:text-red-400">
                        ❌ {repoResult.error}
                      </p>
                    ) : repoResult.detected_build_types && repoResult.detected_build_types.length > 0 ? (
                      <div className="space-y-2">
                        {repoResult.detected_build_types.map((buildType, buildIdx) => (
                          <button
                            key={buildIdx}
                            className="w-full border border-slate-200 rounded-lg p-3 hover:border-blue-500 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed dark:border-slate-700 dark:hover:border-blue-400"
                            onClick={() => addWorkflowFromDetection(repoResult.repo, buildType, normalizedWorkflowName)}
                            disabled={!isWorkflowNameValid}
                            title={!isWorkflowNameValid ? "Enter a valid workflow name before creating a workflow" : undefined}
                          >
                            <div className="flex items-start gap-3">
                              <div className="text-xl">🔧</div>
                              <div className="flex-1">
                                <h6 className="font-semibold text-slate-900 dark:text-slate-100">
                                  {buildType.technology} ({buildType.name})
                                </h6>
                                <p className="text-sm text-slate-600 dark:text-slate-400">
                                  {Math.round(buildType.confidence * 100)}% confidence
                                </p>
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="text-slate-500 text-sm dark:text-slate-400">
                        No build types detected for this repository
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-slate-600 dark:text-slate-400">
                  No repositories selected or no build types detected.
                </p>
              </div>
            )}
            
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setShowDetectionResultsInModal(false);
                  setDetectedBuildTypes([]);
                }}
              >
                ← Back to Options
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            <h4 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              {workflowCreationType === 'regular' ? '📝 Regular Workflow Options' : '🔄 Reusable Workflow Options'}
            </h4>
            {renderWorkflowNameField()}
            
            <div className="grid gap-3">
              <button
                className="border border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed dark:border-slate-700 dark:hover:border-blue-400"
                onClick={() => createBlankWorkflow(workflowCreationType, normalizedWorkflowName)}
                disabled={!isWorkflowNameValid}
              >
                <div className="flex items-start gap-3">
                  <div className="text-2xl">📄</div>
                  <div className="flex-1">
                    <h5 className="font-semibold text-slate-900 mb-1 dark:text-slate-100">
                      Open Blank Workflow
                    </h5>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      Start with an empty workflow template
                    </p>
                  </div>
                </div>
              </button>
              
              {workflowCreationType === 'regular' && (
                <button
                  className="border border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed dark:border-slate-700 dark:hover:border-blue-400"
                  onClick={() => handleDetectBuildTypes()}
                  disabled={isDetecting || !isWorkflowNameValid}
                >
                  <div className="flex items-start gap-3">
                    <div className="text-2xl">🔍</div>
                    <div className="flex-1">
                      <h5 className="font-semibold text-slate-900 mb-1 dark:text-slate-100">
                        Detect Build Types
                      </h5>
                      <p className="text-sm text-slate-600 dark:text-slate-400">
                        Analyze repositories to suggest appropriate workflows
                      </p>
                    </div>
                  </div>
                </button>
              )}
              
              <button
                className="border border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed dark:border-slate-700 dark:hover:border-blue-400"
                onClick={() => handleCreateFromTemplates(workflowCreationType, normalizedWorkflowName)}
                disabled={isGeneratingTemplates || !isWorkflowNameValid}
              >
                <div className="flex items-start gap-3">
                  <div className="text-2xl">📋</div>
                  <div className="flex-1">
                    <h5 className="font-semibold text-slate-900 mb-1 dark:text-slate-100">
                      Generate Templates
                    </h5>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      Create workflows from pre-built templates
                    </p>
                  </div>
                </div>
              </button>
              
              <button
                className="border border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed dark:border-slate-700 dark:hover:border-blue-400"
                onClick={() => handleCreateWithAI(workflowCreationType, normalizedWorkflowName)}
                disabled={isAILoading || !isWorkflowNameValid}
              >
                <div className="flex items-start gap-3">
                  <div className="text-2xl">🤖</div>
                  <div className="flex-1">
                    <h5 className="font-semibold text-slate-900 mb-1 dark:text-slate-100">
                      Generate with AI
                    </h5>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      Let AI create a customized workflow for your needs
                    </p>
                  </div>
                </div>
              </button>
            </div>
            
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setWorkflowCreationType(null)}
              >
                ← Back
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default WorkflowCreationDialog;
