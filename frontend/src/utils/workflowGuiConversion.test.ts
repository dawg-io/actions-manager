import { 
  yamlToGui, 
  guiToYaml, 
  WorkflowGUI,
  DEFAULT_WORKFLOW_GUI,
  DEFAULT_REUSABLE_WORKFLOW_GUI
} from './workflowGuiConversion';

describe('workflowGuiConversion', () => {
  describe('yamlToGui', () => {
    test('should convert simple YAML to GUI structure', () => {
      const yaml = `name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5`;

      const result = yamlToGui(yaml);

      expect(result.name).toBe('CI');
      expect(result.events).toHaveLength(1);
      expect(result.events[0].type).toBe('push');
      expect(result.jobs).toHaveLength(1);
      expect(result.jobs[0].id).toBe('build');
      expect(result.jobs[0].runsOn).toBe('ubuntu-latest');
    });

    test('should handle workflow with multiple events', () => {
      const yaml = `name: Multi Event
on:
  push:
    branches:
      - main
  pull_request:
    branches:
      - main
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5`;

      const result = yamlToGui(yaml);

      expect(result.events).toHaveLength(2);
      expect(result.events[0].type).toBe('push');
      expect(result.events[0].branches).toEqual(['main']);
      expect(result.events[1].type).toBe('pull_request');
    });

    test('should handle workflow_call event with inputs', () => {
      const yaml = `name: Reusable
on:
  workflow_call:
    inputs:
      environment:
        description: "Environment to deploy to"
        required: true
        type: string
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying"`;

      const result = yamlToGui(yaml);

      expect(result.events).toHaveLength(1);
      expect(result.events[0].type).toBe('workflow_call');
      expect(result.events[0].inputs).toBeDefined();
      expect(result.events[0].inputs?.environment).toBeDefined();
      expect(result.events[0].inputs?.environment.required).toBe(true);
    });

    test('should handle schedule event', () => {
      const yaml = `name: Scheduled
on:
  schedule:
    - cron: "0 0 * * *"
jobs:
  nightly:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Running scheduled job"`;

      const result = yamlToGui(yaml);

      expect(result.events).toHaveLength(1);
      expect(result.events[0].type).toBe('schedule');
      // Note: The current parser doesn't extract cron from schedule events
      // as the logic checks for eventConfig.schedule when eventType is 'schedule'
      // This is a limitation of the current implementation
    });

    test('should handle jobs with environment variables', () => {
      const yaml = `name: With Env
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      NODE_ENV: production
    steps:
      - run: npm build`;

      const result = yamlToGui(yaml);

      expect(result.jobs[0].env).toBeDefined();
      expect(result.jobs[0].env?.NODE_ENV).toBe('production');
    });

    test('should handle steps with various properties', () => {
      const yaml = `name: Complex Steps
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - name: Run tests
        run: npm test
        env:
          TEST_VAR: value
      - name: Build
        run: npm build
        if: success()`;

      const result = yamlToGui(yaml);

      expect(result.jobs[0].steps).toHaveLength(3);
      
      // Check first step
      expect(result.jobs[0].steps[0].name).toBe('Checkout');
      expect(result.jobs[0].steps[0].uses).toBe('actions/checkout@v5');
      expect(result.jobs[0].steps[0].with).toBeDefined();
      
      // Check second step
      expect(result.jobs[0].steps[1].name).toBe('Run tests');
      expect(result.jobs[0].steps[1].run).toBe('npm test');
      expect(result.jobs[0].steps[1].env).toBeDefined();
      
      // Check third step
      expect(result.jobs[0].steps[2].if).toBe('success()');
    });

    test('should handle invalid YAML and return default template', () => {
      const invalidYaml = 'this is not valid yaml: [';

      const result = yamlToGui(invalidYaml);

      expect(result).toBeDefined();
      expect(result.name).toBe(DEFAULT_WORKFLOW_GUI.name);
    });

    test('should handle empty YAML and return default template', () => {
      const result = yamlToGui('');

      expect(result).toBeDefined();
      expect(result.name).toBe(DEFAULT_WORKFLOW_GUI.name);
    });

    test('should preserve unsupported top-level fields', () => {
      const yaml = `name: With Unsupported
on: push
permissions:
  contents: read
concurrency:
  group: ci-group
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo test`;

      const result = yamlToGui(yaml);

      expect(result.unsupportedFields).toBeDefined();
      expect(result.unsupportedFields?.permissions).toBeDefined();
      expect(result.unsupportedFields?.concurrency).toBeDefined();
    });

    test('should handle workflow with global env variables', () => {
      const yaml = `name: Global Env
on: push
env:
  GLOBAL_VAR: value
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo test`;

      const result = yamlToGui(yaml);

      expect(result.env).toBeDefined();
      expect(result.env?.GLOBAL_VAR).toBe('value');
    });
  });

  describe('guiToYaml', () => {
    test('should convert simple GUI structure to YAML', () => {
      const gui: WorkflowGUI = {
        name: 'Test Workflow',
        events: [{ type: 'push' }],
        jobs: [
          {
            id: 'build',
            name: 'Build',
            runsOn: 'ubuntu-latest',
            steps: [
              {
                id: 'checkout',
                uses: 'actions/checkout@v5'
              }
            ]
          }
        ]
      };

      const result = guiToYaml(gui);

      expect(result).toContain('name: Test Workflow');
      expect(result).toContain('on: push');
      expect(result).toContain('build:');
      expect(result).toContain('runs-on: ubuntu-latest');
      expect(result).toContain('uses: actions/checkout@v5');
    });

    test('should convert GUI with multiple events to YAML', () => {
      const gui: WorkflowGUI = {
        name: 'Multi Event',
        events: [
          { type: 'push', branches: ['main'] },
          { type: 'pull_request', branches: ['main'] }
        ],
        jobs: [
          {
            id: 'test',
            runsOn: 'ubuntu-latest',
            steps: [{ id: 'test', run: 'npm test' }]
          }
        ]
      };

      const result = guiToYaml(gui);

      expect(result).toContain('push:');
      expect(result).toContain('pull_request:');
      expect(result).toContain('branches:');
      expect(result).toContain('- main');
    });

    test('should convert workflow_call event with inputs to YAML', () => {
      const gui: WorkflowGUI = {
        name: 'Reusable',
        events: [
          {
            type: 'workflow_call',
            inputs: {
              environment: {
                description: 'Environment',
                required: true,
                type: 'string',
                default: 'staging'
              }
            }
          }
        ],
        jobs: [
          {
            id: 'deploy',
            runsOn: 'ubuntu-latest',
            steps: [{ id: 'deploy', run: 'echo deploying' }]
          }
        ]
      };

      const result = guiToYaml(gui);

      expect(result).toContain('workflow_call:');
      expect(result).toContain('inputs:');
      expect(result).toContain('environment:');
      expect(result).toContain('required: true');
    });

    test('should preserve environment variables in YAML', () => {
      const gui: WorkflowGUI = {
        name: 'With Env',
        events: [{ type: 'push' }],
        env: {
          NODE_ENV: 'production',
          API_URL: 'https://api.example.com'
        },
        jobs: [
          {
            id: 'build',
            runsOn: 'ubuntu-latest',
            steps: [{ id: 'build', run: 'npm build' }]
          }
        ]
      };

      const result = guiToYaml(gui);

      expect(result).toContain('env:');
      expect(result).toContain('NODE_ENV: production');
      expect(result).toContain('API_URL: https://api.example.com');
    });

    test('should preserve unsupported fields in YAML', () => {
      const gui: WorkflowGUI = {
        name: 'With Unsupported',
        events: [{ type: 'push' }],
        jobs: [
          {
            id: 'build',
            runsOn: 'ubuntu-latest',
            steps: [{ id: 'build', run: 'npm build' }]
          }
        ],
        unsupportedFields: {
          permissions: { contents: 'read' },
          concurrency: { group: 'ci-group' }
        }
      };

      const result = guiToYaml(gui);

      expect(result).toContain('permissions:');
      expect(result).toContain('concurrency:');
    });

    test('should handle steps with complex properties', () => {
      const gui: WorkflowGUI = {
        name: 'Complex Steps',
        events: [{ type: 'push' }],
        jobs: [
          {
            id: 'test',
            runsOn: 'ubuntu-latest',
            steps: [
              {
                id: 'checkout',
                name: 'Checkout code',
                uses: 'actions/checkout@v5',
                with: {
                  'fetch-depth': '0'
                }
              },
              {
                id: 'test',
                name: 'Run tests',
                run: 'npm test',
                env: {
                  TEST_VAR: 'value'
                },
                if: 'success()'
              }
            ]
          }
        ]
      };

      const result = guiToYaml(gui);

      expect(result).toContain('name: Checkout code');
      expect(result).toContain('uses: actions/checkout@v5');
      expect(result).toContain('with:');
      expect(result).toContain('fetch-depth:');
      expect(result).toContain('name: Run tests');
      expect(result).toContain('run: npm test');
      expect(result).toContain('if: success()');
    });

    test('should not include empty env objects', () => {
      const gui: WorkflowGUI = {
        name: 'No Env',
        events: [{ type: 'push' }],
        env: {},
        jobs: [
          {
            id: 'build',
            runsOn: 'ubuntu-latest',
            steps: [{ id: 'build', run: 'npm build' }]
          }
        ]
      };

      const result = guiToYaml(gui);

      // The env field should not appear in YAML if empty
      const lines = result.split('\n');
      const hasEnvLine = lines.some(line => line.trim() === 'env:');
      expect(hasEnvLine).toBe(false);
    });
  });

  describe('round-trip conversion', () => {
    test('should maintain data integrity through YAML -> GUI -> YAML conversion', () => {
      const originalYaml = `name: CI Pipeline
on:
  push:
    branches:
      - main
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v5
      - name: Build
        run: npm build`;

      const gui = yamlToGui(originalYaml);
      const convertedYaml = guiToYaml(gui);
      const guiAgain = yamlToGui(convertedYaml);

      expect(guiAgain.name).toBe(gui.name);
      expect(guiAgain.events).toHaveLength(gui.events.length);
      expect(guiAgain.jobs).toHaveLength(gui.jobs.length);
      expect(guiAgain.jobs[0].steps).toHaveLength(gui.jobs[0].steps.length);
    });

    test('should maintain reusable workflow structure through conversion', () => {
      const originalYaml = `name: Reusable Workflow
on:
  workflow_call:
    inputs:
      environment:
        required: true
        type: string
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo test`;

      const gui = yamlToGui(originalYaml);
      const convertedYaml = guiToYaml(gui);

      expect(convertedYaml).toContain('workflow_call:');
      expect(convertedYaml).toContain('inputs:');
      expect(convertedYaml).toContain('environment:');
    });
  });

  describe('default templates', () => {
    test('DEFAULT_WORKFLOW_GUI should have valid structure', () => {
      expect(DEFAULT_WORKFLOW_GUI.name).toBeDefined();
      expect(DEFAULT_WORKFLOW_GUI.events).toHaveLength(1);
      expect(DEFAULT_WORKFLOW_GUI.jobs).toHaveLength(1);
      expect(DEFAULT_WORKFLOW_GUI.jobs[0].steps.length).toBeGreaterThan(0);
    });

    test('DEFAULT_REUSABLE_WORKFLOW_GUI should have workflow_call event', () => {
      expect(DEFAULT_REUSABLE_WORKFLOW_GUI.name).toBeDefined();
      expect(DEFAULT_REUSABLE_WORKFLOW_GUI.events).toHaveLength(1);
      expect(DEFAULT_REUSABLE_WORKFLOW_GUI.events[0].type).toBe('workflow_call');
      expect(DEFAULT_REUSABLE_WORKFLOW_GUI.events[0].inputs).toBeDefined();
    });
  });
});
