// Workflow type definitions extracted from UnifiedWorkflows.tsx
import { RwxWorkflow } from '../api/projects';

export interface Workflow {
  name: string;
  content?: string;
  isReusable?: boolean;
  isModified?: boolean;
  gitHash?: string;
  workflowStatus?: string;
  /** Persisted name as stored in the database. Used to detect renames and pass `original_name` to the backend. */
  savedName?: string;
  /** GitHub username of the last user who saved this workflow. */
  lastModifiedBy?: string;
}

export interface RXWorkflow {
  name: string;
  content: string;
  isReusable: boolean;
  isModified?: boolean;
  gitHash?: string;
  workflowStatus?: string;
  /** Persisted name as stored in the database. Used to detect renames and pass `original_name` to the backend. */
  savedName?: string;
  /** GitHub username of the last user who saved this workflow. */
  lastModifiedBy?: string;
}

export interface BuildType {
  name: string;
  technology: string;
  confidence: number;
}

export interface DetectedBuildResult {
  repo: string;
  detected_build_types?: BuildType[];
  error?: string;
}

export interface WorkflowStatusData {
  status?: string;
  html_url?: string;
  message?: string;
}

export interface WorkflowTemplate {
  name: string;
  content: string;
}

export interface TemplatesByType {
  standard?: WorkflowTemplate;
  reusable?: WorkflowTemplate;
  build?: WorkflowTemplate;
}

export interface WorkflowNames {
  reusable: string;
  caller: string;
  technology: string | null;
}

export interface UnifiedWorkflowItem {
  id: string;
  name: string;
  content?: string;
  isReusable: boolean;
  isModified?: boolean;
  gitHash?: string;
  workflowStatus?: string;
  originalIndex: number;
  type: 'regular' | 'reusable' | 'linked';
  /** For linked workflows: the source RWX project id */
  rwxProjectId?: number;
  /** For linked workflows: the source RWX project name */
  rwxProjectName?: string;
  /** For linked workflows: first repo of the source RWX project ("owner/repo"). Used for "Open in GitHub". */
  rwxRepo?: string;
  /** GitHub username of the last user who saved this workflow. */
  lastModifiedBy?: string;
}

export type ProjectPRState = 'new' | 'draft' | 'open' | 'synced';

export interface UnifiedWorkflowsProps {
  // Common props
  user: string;
  projectName: string;
  projectCode: string | null;
  selectedRepos: string[];
  regexPattern: string;
  accountType?: string;
  projectPRState?: ProjectPRState; // Project PR state shared across UI: "new" | "draft" | "open" | "synced"
  usePrefix?: boolean; // Whether to use AM_{PROJECT_CODE}_ prefix
  isReadOnly?: boolean; // Whether the current user has read-only access
  branchOption?: string; // Branch option used for PR creation ("default" or "pattern")

  // Regular workflows props
  workflows: Workflow[];
  setWorkflows: (workflows: Workflow[] | ((prev: Workflow[]) => Workflow[])) => void;
  onRefreshStatus?: (refreshFn: () => Promise<void>, isLoading: boolean) => void;
  onAddWorkflow?: (addWorkflowFn: () => void) => void;
  onClearModifiedStates?: (clearFn: () => void) => void;

  // Reusable workflows props
  rxworkflows: RXWorkflow[];
  setRXWorkflows: (workflows: RXWorkflow[] | ((prev: RXWorkflow[]) => RXWorkflow[])) => void;
  addWorkflowToMain: (workflow: { name: string; content: string; isReusable: boolean }) => void;
  onGenerateTemplates: (generateFn: () => Promise<void>, isGenerating: boolean) => void;
  onAddRXWorkflow: (addFn: () => void) => void;
  detectedBuildTypes: DetectedBuildResult[];
  
  // Reusable workflows enabled state
  reusableWorkflowsEnabled: boolean;
  repoExists: boolean;

  // Linked reusable workflows (standard projects only)
  linkedWorkflows?: RwxWorkflow[];
  setLinkedWorkflows?: (updater: (prev: RwxWorkflow[]) => RwxWorkflow[]) => void;
  canLinkReusableWorkflows?: boolean;
  onLinkReusableWorkflow?: () => void;
  
  // Callback to refresh project list
  refreshProjectsList?: () => Promise<void>;
  // Callback to notify parent when project PR state changes
  onProjectStateChange?: (state: string) => void;
  // Set of workflow names currently drifted on GitHub (rendered as a badge in the list)
  driftedWorkflowNames?: Set<string>;

  // Project Files: custom files
  customFiles?: import('../api/customFiles').CustomFile[];
  setCustomFiles?: (files: import('../api/customFiles').CustomFile[]) => void;
  projectId?: number;
  onCustomFilesChange?: (files: import('../api/customFiles').CustomFile[]) => void;
  /** Bump to force CodeownersManager to reload (e.g. after a campaign completes). */
  codeownersRefreshCounter?: number;
  /** Aggregate status across all repos' CODEOWNERS records, for the nav badge. */
  codeownersAggregateStatus?: string;
  /** Called after a CODEOWNERS draft is saved locally so the parent can refresh status. */
  onCodeownersSaved?: () => void;
}
