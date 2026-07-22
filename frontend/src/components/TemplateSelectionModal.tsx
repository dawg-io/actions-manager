import React from 'react';
import { TemplatesByType, WorkflowTemplate } from '../types/workflow';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';

interface TemplateSelectionModalProps {
  showTemplateModal: boolean;
  templatesByType: TemplatesByType;
  setShowTemplateModal: (show: boolean) => void;
  selectTemplate: (template: WorkflowTemplate, isReusable?: boolean) => void;
}

const TemplateSelectionModal: React.FC<TemplateSelectionModalProps> = ({
  showTemplateModal,
  templatesByType,
  setShowTemplateModal,
  selectTemplate
}) => {
  return (
    <Dialog open={showTemplateModal} onOpenChange={setShowTemplateModal}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle id="template-selection-title">Select Workflow Template</DialogTitle>
          <DialogDescription className="sr-only">
            Choose from available workflow templates for standard, reusable, or build-specific workflows
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          {Object.keys(templatesByType).length === 0 ? (
            <div className="text-center py-8">
              <p className="text-slate-600 dark:text-slate-400">Generating templates...</p>
            </div>
          ) : (
            <div className="space-y-4">
              {templatesByType.standard && (
                <div className="space-y-3">
                  <h4 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                    📝 Standard Workflow
                  </h4>
                  <div className="border border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-colors dark:border-slate-700 dark:hover:border-blue-400">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1">
                        <h5 className="font-semibold text-slate-900 mb-1 dark:text-slate-100">
                          {templatesByType.standard.name}
                        </h5>
                        <p className="text-sm text-slate-600 dark:text-slate-400">
                          Standard CI/CD pipeline
                        </p>
                      </div>
                      <Button
                        onClick={() => selectTemplate(templatesByType.standard!, false)}
                      >
                        Use Template
                      </Button>
                    </div>
                  </div>
                </div>
              )}
              
              {templatesByType.reusable && (
                <div className="space-y-3">
                  <h4 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                    🔄 Reusable Workflow
                  </h4>
                  <div className="border border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-colors dark:border-slate-700 dark:hover:border-blue-400">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1">
                        <h5 className="font-semibold text-slate-900 mb-1 dark:text-slate-100">
                          {templatesByType.reusable.name}
                        </h5>
                        <p className="text-sm text-slate-600 dark:text-slate-400">
                          Reusable workflow template
                        </p>
                      </div>
                      <Button
                        onClick={() => selectTemplate(templatesByType.reusable!, true)}
                      >
                        Use Template
                      </Button>
                    </div>
                  </div>
                </div>
              )}
              
              {templatesByType.build && (
                <div className="space-y-3">
                  <h4 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                    🔨 Build-Specific Workflow
                  </h4>
                  <div className="border border-slate-200 rounded-lg p-4 hover:border-blue-500 transition-colors dark:border-slate-700 dark:hover:border-blue-400">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1">
                        <h5 className="font-semibold text-slate-900 mb-1 dark:text-slate-100">
                          {templatesByType.build.name}
                        </h5>
                        <p className="text-sm text-slate-600 dark:text-slate-400">
                          Build-specific workflow
                        </p>
                      </div>
                      <Button
                        onClick={() => selectTemplate(templatesByType.build!, false)}
                      >
                        Use Template
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default TemplateSelectionModal;