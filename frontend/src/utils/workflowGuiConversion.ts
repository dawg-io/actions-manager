import * as yaml from 'js-yaml';

// TypeScript interfaces for GUI workflow structure
export interface WorkflowGUI {
  name: string;
  events: WorkflowEvent[];
  jobs: WorkflowJob[];
  env?: { [key: string]: string };
  unsupportedFields?: { [key: string]: any };
}

export interface WorkflowCallInput {
  description?: string;
  required?: boolean;
  type?: 'string' | 'number' | 'boolean' | 'choice';
  default?: string | number | boolean;
  options?: string[];
}

export interface WorkflowEvent {
  type: 'push' | 'pull_request' | 'workflow_dispatch' | 'schedule' | 'release' | 'workflow_call';
  branches?: string[];
  paths?: string[];
  /** Tag patterns for `push.tags` - GitHub Actions has no separate "tag push"
   * event; tag-triggered pushes are the `push` event filtered by tags. */
  tags?: string[];
  cron?: string;
  types?: string[];
  inputs?: { [key: string]: WorkflowCallInput };
}

export interface WorkflowJob {
  id: string;
  name?: string;
  runsOn: string;
  steps: WorkflowStep[];
  env?: { [key: string]: string };
  if?: string;
  needs?: string[];
  timeoutMinutes?: number;
  unsupportedFields?: { [key: string]: any };
}

export interface WorkflowStep {
  id: string;
  name?: string;
  uses?: string;
  run?: string;
  with?: { [key: string]: string };
  env?: { [key: string]: string };
  if?: string;
  shell?: string;
  workingDirectory?: string;
  continueOnError?: boolean;
  timeoutMinutes?: number;
  unsupportedFields?: { [key: string]: any };
}

// Default workflow template
export const DEFAULT_WORKFLOW_GUI: WorkflowGUI = {
  name: 'CI',
  events: [{ type: 'push' }],
  jobs: [
    {
      id: 'build',
      name: 'Build',
      runsOn: 'ubuntu-latest',
      steps: [
        {
          id: 'checkout',
          name: 'Checkout code',
          uses: 'actions/checkout@v5'
        },
        {
          id: 'setup-node',
          name: 'Setup Node.js',
          uses: 'actions/setup-node@v4',
          with: {
            'node-version': '20'
          }
        },
        {
          id: 'install',
          name: 'Install dependencies',
          run: 'npm install'
        }
      ]
    }
  ]
};

// Default reusable workflow template with workflow_call
export const DEFAULT_REUSABLE_WORKFLOW_GUI: WorkflowGUI = {
  name: 'Reusable Workflow',
  events: [{ 
    type: 'workflow_call',
    inputs: {
      environment: {
        description: 'Target environment for deployment',
        required: false,
        type: 'string',
        default: 'staging'
      }
    }
  }],
  jobs: [
    {
      id: 'build',
      name: 'Build',
      runsOn: 'ubuntu-latest',
      steps: [
        {
          id: 'checkout',
          name: 'Checkout code',
          uses: 'actions/checkout@v5'
        },
        {
          id: 'setup-node',
          name: 'Setup Node.js',
          uses: 'actions/setup-node@v4',
          with: {
            'node-version': '20'
          }
        },
        {
          id: 'install',
          name: 'Install dependencies',
          run: 'npm install'
        },
        {
          id: 'build',
          name: 'Build application',
          run: 'npm run build'
        }
      ]
    }
  ]
};

// Convert YAML string to GUI structure
export function yamlToGui(yamlContent: string): WorkflowGUI {
  try {
    const parsed = yaml.load(yamlContent) as any;
    if (!parsed || typeof parsed !== 'object') {
      return DEFAULT_WORKFLOW_GUI;
    }

    const result: WorkflowGUI = {
      name: parsed.name || 'Workflow',
      events: parseEvents(parsed.on),
      jobs: parseJobs(parsed.jobs),
      env: parsed.env,
      unsupportedFields: {}
    };

    // Store unsupported top-level fields
    const supportedTopLevel = ['name', 'on', 'jobs', 'env'];
    Object.keys(parsed).forEach(key => {
      if (!supportedTopLevel.includes(key)) {
        result.unsupportedFields![key] = parsed[key];
      }
    });

    return result;
  } catch (error) {
    console.warn('Failed to parse YAML, using default template:', error);
    return DEFAULT_WORKFLOW_GUI;
  }
}

// Convert GUI structure to YAML string
export function guiToYaml(gui: WorkflowGUI): string {
  const workflow: any = {
    name: gui.name,
    trigger: serializeEvents(gui.events), // Use 'trigger' temporarily to avoid YAML quoting 'on'
    jobs: serializeJobs(gui.jobs)
  };

  // Add env if present
  if (gui.env && Object.keys(gui.env).length > 0) {
    workflow.env = gui.env;
  }

  // Add unsupported fields back
  if (gui.unsupportedFields) {
    Object.assign(workflow, gui.unsupportedFields);
  }

  const yamlStr = yaml.dump(workflow, {
    indent: 2,
    lineWidth: -1,
    noRefs: true,
    sortKeys: false
  });

  // Replace 'trigger:' with 'on:' to avoid YAML quoting the reserved word 'on'
  return yamlStr.replace(/^trigger:/gm, 'on:');
}

// Parse events from YAML 'on' field
function parseEvents(onField: any): WorkflowEvent[] {
  if (!onField) {
    return [{ type: 'push' }];
  }

  if (typeof onField === 'string') {
    return [{ type: onField as any }];
  }

  if (Array.isArray(onField)) {
    return onField.map(event => ({ type: event }));
  }

  const events: WorkflowEvent[] = [];
  Object.keys(onField).forEach(eventType => {
    const eventConfig = onField[eventType];
    const event: WorkflowEvent = { type: eventType as any };

    if (eventConfig && typeof eventConfig === 'object') {
      if (eventConfig.branches) {
        event.branches = Array.isArray(eventConfig.branches) 
          ? eventConfig.branches 
          : [eventConfig.branches];
      }
      if (eventConfig.paths) {
        event.paths = Array.isArray(eventConfig.paths)
          ? eventConfig.paths
          : [eventConfig.paths];
      }
      if (eventConfig.tags) {
        event.tags = Array.isArray(eventConfig.tags)
          ? eventConfig.tags
          : [eventConfig.tags];
      }
      if (eventConfig.schedule && Array.isArray(eventConfig.schedule)) {
        event.cron = eventConfig.schedule[0]?.cron;
      }
      if (eventConfig.types) {
        event.types = Array.isArray(eventConfig.types) 
          ? eventConfig.types 
          : [eventConfig.types];
      }
      // Handle workflow_call / workflow_dispatch inputs (same YAML shape for
      // both - a manual-trigger workflow's `workflow_dispatch.inputs` was
      // previously silently dropped here since only workflow_call was
      // handled, losing data on every YAML -> GUI -> YAML round trip).
      if ((eventType === 'workflow_call' || eventType === 'workflow_dispatch') && eventConfig.inputs) {
        event.inputs = {};
        Object.keys(eventConfig.inputs).forEach(inputName => {
          const inputConfig = eventConfig.inputs[inputName];
          if (inputConfig && typeof inputConfig === 'object') {
            event.inputs![inputName] = {
              description: inputConfig.description,
              required: inputConfig.required,
              type: inputConfig.type || 'string',
              default: inputConfig.default
            };
            if (inputConfig.type === 'choice' && inputConfig.options) {
              event.inputs![inputName].options = inputConfig.options;
            }
          }
        });
      }
    }

    events.push(event);
  });

  return events.length > 0 ? events : [{ type: 'push' }];
}

// Serialize events to YAML 'on' field
function serializeEvents(events: WorkflowEvent[]): any {
  if (events.length === 0) {
    return ['push'];
  }

  if (events.length === 1) {
    const event = events[0];
    if (!event.branches && !event.paths && !event.tags && !event.cron && !event.types && !event.inputs) {
      return event.type;
    }
  }

  const result: any = {};
  events.forEach(event => {
    if (!event.branches && !event.paths && !event.tags && !event.cron && !event.types && !event.inputs) {
      result[event.type] = null;
    } else {
      const config: any = {};
      if (event.branches && event.branches.length > 0) {
        config.branches = event.branches;
      }
      if (event.paths && event.paths.length > 0) {
        config.paths = event.paths;
      }
      if (event.tags && event.tags.length > 0) {
        config.tags = event.tags;
      }
      if (event.types && event.types.length > 0) {
        config.types = event.types;
      }
      if (event.cron) {
        config.schedule = [{ cron: event.cron }];
      }
      // Handle workflow_call / workflow_dispatch inputs (see matching note
      // in parseEvents above).
      if ((event.type === 'workflow_call' || event.type === 'workflow_dispatch') && event.inputs) {
        config.inputs = {};
        Object.keys(event.inputs).forEach(inputName => {
          const input = event.inputs![inputName];
          config.inputs[inputName] = {
            description: input.description,
            required: input.required || false,
            type: input.type || 'string'
          };
          if (input.default !== undefined) {
            config.inputs[inputName].default = input.default;
          }
          if (input.type === 'choice' && input.options) {
            config.inputs[inputName].options = input.options;
          }
        });
      }
      result[event.type] = config;
    }
  });

  return result;
}

// Parse jobs from YAML jobs field
function parseJobs(jobsField: any): WorkflowJob[] {
  if (!jobsField || typeof jobsField !== 'object') {
    return [];
  }

  return Object.keys(jobsField).map(jobId => {
    const job = jobsField[jobId];
    const result: WorkflowJob = {
      id: jobId,
      name: job.name,
      runsOn: job['runs-on'] || 'ubuntu-latest',
      steps: parseSteps(job.steps || []),
      env: job.env,
      if: job.if,
      needs: job.needs,
      timeoutMinutes: job['timeout-minutes'],
      unsupportedFields: {}
    };

    // Store unsupported job fields
    const supportedJobFields = ['name', 'runs-on', 'steps', 'env', 'if', 'needs', 'timeout-minutes'];
    Object.keys(job).forEach(key => {
      if (!supportedJobFields.includes(key)) {
        result.unsupportedFields![key] = job[key];
      }
    });

    return result;
  });
}

// Serialize jobs to YAML jobs field
function serializeJobs(jobs: WorkflowJob[]): any {
  const result: any = {};
  
  jobs.forEach(job => {
    const jobConfig: any = {
      'runs-on': job.runsOn,
      steps: serializeSteps(job.steps)
    };

    if (job.name) jobConfig.name = job.name;
    if (job.env && Object.keys(job.env).length > 0) jobConfig.env = job.env;
    if (job.if) jobConfig.if = job.if;
    if (job.needs && job.needs.length > 0) jobConfig.needs = job.needs;
    if (job.timeoutMinutes) jobConfig['timeout-minutes'] = job.timeoutMinutes;

    // Add unsupported fields back
    if (job.unsupportedFields) {
      Object.assign(jobConfig, job.unsupportedFields);
    }

    result[job.id] = jobConfig;
  });

  return result;
}

// Parse steps from YAML steps array
function parseSteps(stepsField: any[]): WorkflowStep[] {
  if (!Array.isArray(stepsField)) {
    return [];
  }

  return stepsField.map((step, index) => {
    const result: WorkflowStep = {
      id: step.id || `step-${index + 1}`,
      name: step.name,
      uses: step.uses,
      run: step.run,
      with: step.with,
      env: step.env,
      if: step.if,
      shell: step.shell,
      workingDirectory: step['working-directory'],
      continueOnError: step['continue-on-error'],
      timeoutMinutes: step['timeout-minutes'],
      unsupportedFields: {}
    };

    // Store unsupported step fields
    const supportedStepFields = [
      'id', 'name', 'uses', 'run', 'with', 'env', 'if', 'shell', 
      'working-directory', 'continue-on-error', 'timeout-minutes'
    ];
    Object.keys(step).forEach(key => {
      if (!supportedStepFields.includes(key)) {
        result.unsupportedFields![key] = step[key];
      }
    });

    return result;
  });
}

// Serialize steps to YAML steps array
function serializeSteps(steps: WorkflowStep[]): any[] {
  return steps.map(step => {
    const stepConfig: any = {};

    if (step.name) stepConfig.name = step.name;
    if (step.uses) stepConfig.uses = step.uses;
    if (step.run) stepConfig.run = step.run;
    if (step.with && Object.keys(step.with).length > 0) stepConfig.with = step.with;
    if (step.env && Object.keys(step.env).length > 0) stepConfig.env = step.env;
    if (step.if) stepConfig.if = step.if;
    if (step.shell) stepConfig.shell = step.shell;
    if (step.workingDirectory) stepConfig['working-directory'] = step.workingDirectory;
    if (step.continueOnError !== undefined) stepConfig['continue-on-error'] = step.continueOnError;
    if (step.timeoutMinutes) stepConfig['timeout-minutes'] = step.timeoutMinutes;

    // Add unsupported fields back
    if (step.unsupportedFields) {
      Object.assign(stepConfig, step.unsupportedFields);
    }

    return stepConfig;
  });
}

// Validation functions
export interface ValidationError {
  field: string;
  message: string;
  severity: 'error' | 'warning';
}

export function validateWorkflow(gui: WorkflowGUI): ValidationError[] {
  const errors: ValidationError[] = [];

  // Validate workflow name
  if (!gui.name || gui.name.trim() === '') {
    errors.push({
      field: 'name',
      message: 'Workflow name is required',
      severity: 'error'
    });
  }

  // Validate events
  if (!gui.events || gui.events.length === 0) {
    errors.push({
      field: 'events',
      message: 'At least one trigger event is required',
      severity: 'error'
    });
  }

  // Validate jobs
  if (!gui.jobs || gui.jobs.length === 0) {
    errors.push({
      field: 'jobs',
      message: 'At least one job is required',
      severity: 'error'
    });
  } else {
    gui.jobs.forEach((job, jobIndex) => {
      // Validate job ID
      if (!job.id || job.id.trim() === '') {
        errors.push({
          field: `jobs[${jobIndex}].id`,
          message: 'Job ID is required',
          severity: 'error'
        });
      }

      // Validate runner
      if (!job.runsOn || job.runsOn.trim() === '') {
        errors.push({
          field: `jobs[${jobIndex}].runsOn`,
          message: 'Runner is required',
          severity: 'error'
        });
      }

      // Validate steps
      if (!job.steps || job.steps.length === 0) {
        errors.push({
          field: `jobs[${jobIndex}].steps`,
          message: 'At least one step is required',
          severity: 'warning'
        });
      } else {
        job.steps.forEach((step, stepIndex) => {
          // Validate step has either uses or run
          if (!step.uses && !step.run) {
            errors.push({
              field: `jobs[${jobIndex}].steps[${stepIndex}]`,
              message: 'Step must have either "uses" (action) or "run" (script)',
              severity: 'error'
            });
          }

          // Validate action version if uses is present
          if (step.uses && !step.uses.includes('@')) {
            errors.push({
              field: `jobs[${jobIndex}].steps[${stepIndex}].uses`,
              message: 'Action must include a version (e.g., @v4)',
              severity: 'warning'
            });
          }
        });
      }
    });
  }

  return errors;
}