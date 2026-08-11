/* eslint-disable no-restricted-syntax, no-restricted-imports -- Legacy: TODO migrate inline styles and CSS imports to Tailwind CSS classes */
import React, { useEffect, useRef, useCallback, useImperativeHandle, useMemo } from 'react';
import { EditorView, basicSetup } from 'codemirror';
import { EditorState } from '@codemirror/state';
import { yaml } from '@codemirror/lang-yaml';
import { oneDark } from '@codemirror/theme-one-dark';
import { autocompletion, completionKeymap, Completion } from '@codemirror/autocomplete';
import { searchKeymap } from '@codemirror/search';
import { linter, lintKeymap, Diagnostic } from '@codemirror/lint';
import { indentWithTab } from '@codemirror/commands';
import { keymap } from '@codemirror/view';
import { foldKeymap } from '@codemirror/language';
import * as yamlParser from 'js-yaml';
import { WorkflowResource } from '../utils/workflowResources';
import '../styles/YAMLEditor.css';

// Structured validation diagnostic exposed to parent components
export interface WorkflowDiagnostic {
  severity: 'error' | 'warning' | 'info';
  message: string;
  line?: number;
  column?: number;
  source?: string;
}

// TypeScript interfaces
interface GitHubActionsCompletion {
  label: string;
  type: 'keyword' | 'constant';
  info: string;
}

interface YAMLEditorProps {
  value?: string;
  onChange?: (value: string) => void;
  onStructuralDiagnostics?: (diagnostics: WorkflowDiagnostic[]) => void;
  height?: string;
  placeholder?: string;
  readOnly?: boolean;
  theme?: 'dark' | 'light';
  /** Project secrets/variables offered as completions inside `${{ }}` expressions. */
  resources?: WorkflowResource[];
}

/** Imperative handle used to insert text without disturbing the caret. */
export interface YamlEditorHandle {
  insertAtCursor: (text: string) => void;
}

// GitHub Actions workflow autocomplete suggestions
const githubActionsCompletions: GitHubActionsCompletion[] = [
  // Workflow structure
  { label: 'name', type: 'keyword', info: 'The name of your workflow' },
  { label: 'on', type: 'keyword', info: 'Specifies the trigger for this workflow' },
  { label: 'env', type: 'keyword', info: 'Environment variables that are available to all jobs and steps' },
  { label: 'defaults', type: 'keyword', info: 'Default settings that will apply to all jobs in the workflow' },
  { label: 'concurrency', type: 'keyword', info: 'Concurrency ensures that only a single job or workflow is running' },
  { label: 'jobs', type: 'keyword', info: 'A workflow run is made up of one or more jobs' },
  
  // Trigger events
  { label: 'push', type: 'keyword', info: 'Runs when commits are pushed' },
  { label: 'pull_request', type: 'keyword', info: 'Runs when pull requests are opened, closed, or updated' },
  { label: 'pull_request_target', type: 'keyword', info: 'Runs when pull requests target the base repository' },
  { label: 'workflow_dispatch', type: 'keyword', info: 'Allows manual triggering of the workflow' },
  { label: 'schedule', type: 'keyword', info: 'Runs the workflow on a schedule' },
  { label: 'release', type: 'keyword', info: 'Runs when releases are published' },
  { label: 'workflow_call', type: 'keyword', info: 'Makes this workflow reusable' },
  
  // Job properties
  { label: 'runs-on', type: 'keyword', info: 'The type of machine to run the job on' },
  { label: 'steps', type: 'keyword', info: 'A sequence of tasks that will be executed' },
  { label: 'needs', type: 'keyword', info: 'Identifies any jobs that must complete successfully' },
  { label: 'if', type: 'keyword', info: 'Conditional execution of the job' },
  { label: 'strategy', type: 'keyword', info: 'Strategy for running the job' },
  { label: 'matrix', type: 'keyword', info: 'Matrix strategy for running multiple variants' },
  { label: 'outputs', type: 'keyword', info: 'Job outputs that can be used by other jobs' },
  { label: 'permissions', type: 'keyword', info: 'Permissions granted to the job' },
  { label: 'timeout-minutes', type: 'keyword', info: 'Maximum minutes to let a job run' },
  
  // Step properties
  { label: 'uses', type: 'keyword', info: 'Selects an action to run as part of a step' },
  { label: 'run', type: 'keyword', info: 'Runs command-line programs using the shell' },
  { label: 'with', type: 'keyword', info: 'Input parameters defined by the action' },
  { label: 'continue-on-error', type: 'keyword', info: 'Prevents a job from failing when a step fails' },
  { label: 'working-directory', type: 'keyword', info: 'Working directory for run steps' },
  { label: 'shell', type: 'keyword', info: 'Override the default shell settings' },
  
  // Common runners
  { label: 'ubuntu-latest', type: 'constant', info: 'Latest Ubuntu runner' },
  { label: 'ubuntu-20.04', type: 'constant', info: 'Ubuntu 20.04 runner' },
  { label: 'ubuntu-22.04', type: 'constant', info: 'Ubuntu 22.04 runner' },
  { label: 'windows-latest', type: 'constant', info: 'Latest Windows runner' },
  { label: 'macos-latest', type: 'constant', info: 'Latest macOS runner' },
  
  // Common actions (keep in sync with backend/action_versions.py)
  { label: 'actions/checkout@v7.0.1', type: 'constant', info: 'Check out repository content' },
  { label: 'actions/setup-node@v7.0.0', type: 'constant', info: 'Set up Node.js environment' },
  { label: 'actions/setup-python@v7.0.0', type: 'constant', info: 'Set up Python environment' },
  { label: 'actions/upload-artifact@v7.0.1', type: 'constant', info: 'Upload build artifacts' },
  { label: 'actions/download-artifact@v8.0.1', type: 'constant', info: 'Download build artifacts' },
  { label: 'actions/cache@v6.1.0', type: 'constant', info: 'Cache dependencies and build outputs' },
  
  // Common branches
  { label: 'main', type: 'constant', info: 'Main branch' },
  { label: 'master', type: 'constant', info: 'Master branch' },
  { label: 'develop', type: 'constant', info: 'Development branch' },
  
  // Common events
  { label: 'opened', type: 'constant', info: 'Pull request opened' },
  { label: 'closed', type: 'constant', info: 'Pull request closed' },
  { label: 'synchronize', type: 'constant', info: 'Pull request synchronized' },
  { label: 'published', type: 'constant', info: 'Release published' },
  
  // Common shells
  { label: 'bash', type: 'constant', info: 'Bash shell' },
  { label: 'pwsh', type: 'constant', info: 'PowerShell shell' },
  { label: 'cmd', type: 'constant', info: 'Command prompt shell' },
];

// Simple YAML linter for GitHub Actions - only emits inline squiggles for precise token issues.
// Structural workflow validation (missing jobs, on, etc.) is reported via the onStructuralDiagnostics callback.
function createYamlLinter(onStructuralDiagnostics: (diags: WorkflowDiagnostic[]) => void) {
  return linter((view): Diagnostic[] => {
    const diagnostics: Diagnostic[] = [];
    const structural: WorkflowDiagnostic[] = [];
    const doc = view.state.doc;
    const text = doc.toString();
    
    try {
      const lines = text.split('\n');
      let hasName = false;
      let hasOn = false;
      let hasJobs = false;
      
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmedLine = line.trim();
        
        if (trimmedLine.startsWith('name:')) hasName = true;
        if (trimmedLine.startsWith('on:')) hasOn = true;
        if (trimmedLine.startsWith('jobs:')) hasJobs = true;
        
        // Precise inline diagnostics: mixed tabs and spaces on a specific line
        if (trimmedLine.length > 0 && !trimmedLine.startsWith('#')) {
          if (line.includes('\t') && line.includes(' ')) {
            const from = doc.line(i + 1).from;
            const to = doc.line(i + 1).to;
            diagnostics.push({
              from,
              to,
              severity: 'warning',
              message: 'Mixed tabs and spaces detected. Use consistent indentation.'
            });
          }
          
          // Check for invalid characters in key names - precise inline marker
          if (trimmedLine.includes(':') && !trimmedLine.startsWith('http') && !trimmedLine.startsWith('https') && !trimmedLine.startsWith('-')) {
            const beforeColon = trimmedLine.split(':')[0].trim();
            const isValidKey = /^[\w\-_.]+$/.test(beforeColon) || 
                              beforeColon.includes("'") || 
                              beforeColon.includes('"') ||
                              beforeColon === 'paths-ignore' ||
                              beforeColon === 'runs-on' ||
                              beforeColon === 'pull_request' ||
                              beforeColon === 'workflow_dispatch';
            
            if (!isValidKey && beforeColon.length > 0) {
              // Only squiggle the key portion, not the whole line
              const lineStart = doc.line(i + 1).from;
              const keyStart = lineStart + line.indexOf(beforeColon);
              const keyEnd = keyStart + beforeColon.length;
              diagnostics.push({
                from: keyStart,
                to: keyEnd,
                severity: 'info',
                message: 'Key names should generally contain only letters, numbers, hyphens, and underscores'
              });
            }
          }
        }
      }

      yamlParser.load(text);
      
      // Structural errors go to the validation panel, not inline squiggles
      const meaningfulLines = lines.filter(line => line.trim() && !line.trim().startsWith('#')).length;
      
      if (meaningfulLines > 2) {
        if (!hasName) {
          structural.push({
            severity: 'info',
            message: 'Consider adding a "name" field to describe your workflow',
            line: 1,
            source: 'workflow-structure'
          });
        }
        
        if (!hasOn) {
          structural.push({
            severity: 'warning',
            message: 'Workflow is missing "on" trigger specification',
            line: 1,
            source: 'workflow-structure'
          });
        }
        
        if (!hasJobs) {
          structural.push({
            severity: 'warning',
            message: 'Workflow is missing "jobs" section',
            line: 1,
            source: 'workflow-structure'
          });
        }
      }
      
    } catch (error) {
      const yamlError = error as Error & {
        mark?: {
          line?: number;
          column?: number;
        };
      };
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      structural.push({
        severity: 'error',
        message: 'YAML syntax error: ' + errorMessage,
        line: (yamlError.mark?.line ?? 0) + 1,
        column: (yamlError.mark?.column ?? 0) + 1,
        source: 'yaml-parser'
      });
    }
    
    onStructuralDiagnostics(structural);
    return diagnostics;
  });
}

// Completions for project secrets and variables, offered only while the caret
// sits inside an unclosed `${{ ... }}` expression. Deployment environments are
// deliberately excluded: `environment:` is a job key, not an expression.
export function resourceCompletions(resources: WorkflowResource[]): Completion[] {
  return resources
    .filter(resource => resource.kind !== 'environment')
    .map(resource => {
      const label = `${resource.kind === 'secret' ? 'secrets' : 'vars'}.${resource.name}`;
      return {
        label,
        type: 'variable',
        info: resource.repo
          ? `Project ${resource.kind} in ${resource.repo}`
          : `Project ${resource.kind}`,
        apply: label
      };
    });
}

// Custom autocomplete source for GitHub Actions. `resourcesRef` is read at
// completion time rather than captured, so refreshed project resources never
// force the EditorView to be torn down and recreated.
function createGithubActionsAutocompletion(resourcesRef: React.RefObject<WorkflowResource[]>) {
  return autocompletion({
    override: [
      (context) => {
        const insideExpression = context.matchBefore(/\$\{\{[^}]*$/);

        // Inside an expression the token spans the `secrets.`/`vars.` prefix, so
        // the dot has to be part of it. Everywhere else the original word
        // pattern is kept, leaving the existing keyword completions untouched.
        const word = context.matchBefore(insideExpression ? /[\w.]*/ : /\w*/);
        if (!word) return null;

        const candidates: Completion[] = insideExpression
          ? resourceCompletions(resourcesRef.current ?? [])
          : githubActionsCompletions.map(completion => ({
              label: completion.label,
              type: completion.type,
              info: completion.info,
              apply: completion.label
            }));

        const options = candidates.filter(option =>
          option.label.toLowerCase().includes(word.text.toLowerCase())
        );

        return {
          from: word.from,
          options: options.slice(0, 20) // Limit to 20 suggestions
        };
      }
    ]
  });
}

const YAMLEditor = React.forwardRef<YamlEditorHandle, YAMLEditorProps>(({
  value = '',
  onChange,
  onStructuralDiagnostics,
  height = '400px',
  placeholder = 'Enter your GitHub Actions workflow YAML here...',
  readOnly = false,
  theme = 'dark',
  resources
}, ref) => {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const valueRef = useRef<string>(value);
  const isInternalChangeRef = useRef<boolean>(false);
  const isProgrammaticUpdateRef = useRef<boolean>(false);
  const onStructuralDiagnosticsRef = useRef(onStructuralDiagnostics);
  const resourcesRef = useRef<WorkflowResource[]>(resources ?? []);

  // Built once so the extension identity - and therefore the EditorView - stays
  // stable while the resource list behind it changes.
  const githubActionsAutocompletion = useMemo(
    () => createGithubActionsAutocompletion(resourcesRef),
    []
  );

  // Keep callback ref in sync
  useEffect(() => {
    onStructuralDiagnosticsRef.current = onStructuralDiagnostics;
  }, [onStructuralDiagnostics]);

  useEffect(() => {
    resourcesRef.current = resources ?? [];
  }, [resources]);

  // Inserts at the caret by dispatching on the view directly. Routing this
  // through the `value` prop instead would hit the external-sync effect below,
  // which resets the selection to the start of the document.
  useImperativeHandle(ref, () => ({
    insertAtCursor: (text: string) => {
      const view = viewRef.current;
      if (!view || readOnly) return;
      view.dispatch(view.state.replaceSelection(text));
      view.focus();
    }
  }), [readOnly]);

  // Update value ref when prop changes
  useEffect(() => {
    valueRef.current = value;
  }, [value]);

  const handleChange = useCallback((newValue: string) => {
    // Don't call onChange if this is a programmatic update
    if (isProgrammaticUpdateRef.current) {
      return;
    }
    
    if (onChange && newValue !== valueRef.current) {
      valueRef.current = newValue;
      isInternalChangeRef.current = true; // Mark as internal change
      onChange(newValue);
    }
  }, [onChange]);

  useEffect(() => {
    if (!editorRef.current) return;

    // Reset the internal change flag when editor is recreated
    isInternalChangeRef.current = false;

    const extensions = [
      basicSetup,
      yaml(),
      EditorView.theme({
        '&': {
          fontSize: '14px',
          fontFamily: 'Consolas, "Courier New", monospace',
          height: '100%'
        },
        '.cm-content': {
          padding: '16px',
          minHeight: height
        },
        '.cm-focused': {
          outline: 'none'
        },
        '.cm-editor': {
          borderRadius: '8px',
          height: '100%'
        },
        '.cm-scroller': {
          lineHeight: '1.5',
          height: '100%',
          overflow: 'auto'
        }
      }),
      EditorView.updateListener.of(update => {
        if (update.docChanged) {
          const newValue = update.state.doc.toString();
          handleChange(newValue);
        }
      }),
      EditorState.readOnly.of(readOnly),
      keymap.of([
        indentWithTab,
        ...completionKeymap,
        ...searchKeymap,
        ...lintKeymap,
        ...foldKeymap
      ]),
      githubActionsAutocompletion,
      createYamlLinter((diags) => {
        if (onStructuralDiagnosticsRef.current) {
          onStructuralDiagnosticsRef.current(diags);
        }
      }),
      EditorView.lineWrapping,
      EditorState.tabSize.of(2)
    ];

    // Add theme if dark mode
    if (theme === 'dark') {
      extensions.push(oneDark);
    }

    const state = EditorState.create({
      doc: value,
      extensions
    });

    const view = new EditorView({
      state,
      parent: editorRef.current
    });

    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height, readOnly, theme]); // Intentionally excluding value and handleChange to prevent recreation

  // Update editor content when value prop changes externally
  useEffect(() => {
    if (viewRef.current && value !== viewRef.current.state.doc.toString()) {
      // If this is an internal change (user typing), don't update the editor
      if (isInternalChangeRef.current) {
        isInternalChangeRef.current = false;
        return;
      }
      
      // Set flag to prevent onChange from being called during programmatic update
      isProgrammaticUpdateRef.current = true;
      
      // Update editor content
      const transaction = viewRef.current.state.update({
        changes: {
          from: 0,
          to: viewRef.current.state.doc.length,
          insert: value
        },
        // Reset cursor to beginning when loading new workflow
        selection: { anchor: 0, head: 0 }
      });
      
      viewRef.current.dispatch(transaction);
      
      // Reset flag after dispatch completes
      isProgrammaticUpdateRef.current = false;
      
      // Reset scroll position
      requestAnimationFrame(() => {
        if (viewRef.current) {
          viewRef.current.scrollDOM.scrollTop = 0;
          viewRef.current.scrollDOM.scrollLeft = 0;
        }
      });
    }
  }, [value]);

  return (
    <div 
      className="yaml-editor-container" 
      style={{ height }}
      data-testid="yaml-editor"
    >
      <div 
        ref={editorRef} 
        className="yaml-editor"
        style={{ height: '100%' }}
      />
    </div>
  );
});

YAMLEditor.displayName = 'YAMLEditor';

export default YAMLEditor;