import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { normalizeWorkflowFilename } from '../utils/workflowFilename';

// TypeScript interfaces
interface Workflow {
  name: string;
  content?: string;
  isReusable?: boolean;
  isModified?: boolean;
  gitHash?: string;
}

interface WorkflowStatusData {
  status?: string;
  html_url?: string;
  message?: string;
}

interface RepoStatus {
  repo: string;
  status: WorkflowStatusData;
}

interface WorkflowsListProps {
  workflows: Workflow[];
  selectedWorkflowIndex: number | null;
  onSelectWorkflow: (index: number) => void;
  projectCode?: string;
  workflowStatuses?: Record<string, WorkflowStatusData>;
  loadingStatuses?: boolean;
  getWorkflowStatusDisplay: (workflowName: string) => RepoStatus[] | null;
  getStatusIcon: (status: string) => string;
  getStatusColor: (status: string) => string;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

const WorkflowsList: React.FC<WorkflowsListProps> = ({ 
  workflows, 
  selectedWorkflowIndex, 
  onSelectWorkflow, 
  projectCode, 
  workflowStatuses, 
  loadingStatuses, 
  getWorkflowStatusDisplay,
  getStatusIcon,
  getStatusColor,
  isCollapsed,
  onToggleCollapse
}) => {
  return (
    <Card className={`transition-all duration-300 ${isCollapsed ? 'w-16' : 'w-[350px]'} flex flex-col h-full`}>
      <CardHeader className="bg-gradient-to-br from-primary-light to-slate-100 dark:from-primary-light/20 dark:to-slate-800 border-b border-border dark:border-border-dark p-4 flex flex-row items-center justify-between">
        <CardTitle className={`${isCollapsed ? 'text-center text-xl' : 'text-lg'} m-0`}>
          {!isCollapsed ? '📝 Workflows' : '📝'}
        </CardTitle>
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleCollapse}
          title={isCollapsed ? 'Expand workflows list' : 'Collapse workflows list'}
          disabled={!onToggleCollapse}
          className="h-7 w-7 p-0"
        >
          <span className="text-sm font-bold">
            {isCollapsed ? '►' : '◄'}
          </span>
        </Button>
      </CardHeader>
      {!isCollapsed && (
        <CardContent className="p-0 flex-1 overflow-y-auto">
          {workflows.length === 0 ? (
            <div className="p-8 text-center text-text-secondary dark:text-text-secondary-dark">
              <p className="font-medium">No workflows created yet</p>
              <p className="text-sm mt-2">
                Click "Add Workflow" to create your first workflow
              </p>
            </div>
          ) : (
            <ul className="list-none p-0 m-0">
              {workflows.map((workflow, index) => (
                <li key={index} className="list-none p-0 m-0">
                  <button 
                    className={`w-full flex items-center justify-between p-4 border-b border-border dark:border-border-dark cursor-pointer transition-all hover:bg-hover-bg dark:hover:bg-hover-dark-bg ${
                      selectedWorkflowIndex === index 
                        ? 'bg-primary-light dark:bg-primary-light/20 border-l-4 border-l-primary dark:border-l-primary-dark pl-[calc(1rem-4px)]' 
                        : 'border-l-4 border-l-transparent'
                    }`}
                    onClick={() => onSelectWorkflow(index)}
                    type="button"
                  >
                    <div className="flex-1 flex flex-col gap-1">
                      <div className="font-medium text-text-primary dark:text-text-primary-dark">
                        {workflow.name ? normalizeWorkflowFilename(workflow.name) : `Untitled Workflow ${index + 1}`}
                        {workflow.name && (
                          <span className="block text-xs text-text-secondary dark:text-text-secondary-dark font-normal mt-0.5">
                            AM_{(projectCode || '').toUpperCase()}_
                          </span>
                        )}
                      </div>
                      

                    </div>
                    
                    {/* Modified indicator */}
                    {workflow.isModified && (
                      <div className="text-warning text-xl font-bold w-5 text-center" title="Unsaved changes">
                        •
                      </div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      )}
    </Card>
  );
};

export default WorkflowsList;