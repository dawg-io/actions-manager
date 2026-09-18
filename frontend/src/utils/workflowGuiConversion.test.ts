import {
  yamlToGui,
  yamlToGuiResult,
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

    test('should handle workflow_dispatch event with inputs', () => {
      const yaml = `name: Manual Deploy
on:
  workflow_dispatch:
    inputs:
      environment:
        description: "Environment to deploy to"
        required: true
        type: choice
        options:
          - staging
          - production
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying"`;

      const result = yamlToGui(yaml);

      expect(result.events).toHaveLength(1);
      expect(result.events[0].type).toBe('workflow_dispatch');
      expect(result.events[0].inputs).toBeDefined();
      expect(result.events[0].inputs?.environment).toBeDefined();
      expect(result.events[0].inputs?.environment.required).toBe(true);
      expect(result.events[0].inputs?.environment.type).toBe('choice');
      expect(result.events[0].inputs?.environment.options).toEqual(['staging', 'production']);
    });

    test('should handle push event with tags', () => {
      const yaml = `name: Release
on:
  push:
    tags:
      - "v*"
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5`;

      const result = yamlToGui(yaml);

      expect(result.events).toHaveLength(1);
      expect(result.events[0].type).toBe('push');
      expect(result.events[0].tags).toEqual(['v*']);
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

    test('should convert workflow_dispatch event with inputs to YAML', () => {
      const gui: WorkflowGUI = {
        name: 'Manual Deploy',
        events: [
          {
            type: 'workflow_dispatch',
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

      expect(result).toContain('workflow_dispatch:');
      expect(result).toContain('inputs:');
      expect(result).toContain('environment:');
      expect(result).toContain('required: true');
    });

    test('should convert push event with tags to YAML', () => {
      const gui: WorkflowGUI = {
        name: 'Release',
        events: [{ type: 'push', tags: ['v*'] }],
        jobs: [
          {
            id: 'release',
            runsOn: 'ubuntu-latest',
            steps: [{ id: 'checkout', uses: 'actions/checkout@v5' }]
          }
        ]
      };

      const result = guiToYaml(gui);

      expect(result).toContain('push:');
      expect(result).toContain('tags:');
      expect(result).toContain('v*');
      expect(result).not.toContain('tag_push');
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

    test('should not drop workflow_dispatch inputs through YAML -> GUI -> YAML conversion', () => {
      // Regression test: workflow_dispatch.inputs was previously silently
      // dropped by parseEvents/serializeEvents, which only handled
      // workflow_call.inputs - a manually-triggered workflow's inputs would
      // vanish the moment a user switched from YAML mode to GUI mode and back.
      const originalYaml = `name: Manual Deploy
on:
  workflow_dispatch:
    inputs:
      environment:
        description: "Target environment"
        required: true
        type: choice
        options:
          - staging
          - production
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo deploying`;

      const gui = yamlToGui(originalYaml);
      const convertedYaml = guiToYaml(gui);
      const guiAgain = yamlToGui(convertedYaml);

      expect(convertedYaml).toContain('workflow_dispatch:');
      expect(convertedYaml).toContain('inputs:');
      expect(convertedYaml).toContain('environment:');
      expect(guiAgain.events[0].inputs?.environment).toBeDefined();
      expect(guiAgain.events[0].inputs?.environment.required).toBe(true);
      expect(guiAgain.events[0].inputs?.environment.options).toEqual(['staging', 'production']);
    });

    test('should not corrupt tag-triggered push workflows through conversion', () => {
      // Regression test: the editor previously exposed a "Tag Push" trigger
      // that serialized to an invalid `tag_push:` YAML key (not a real
      // GitHub Actions event - GitHub silently ignores it, so the workflow
      // never actually triggers). Tag-triggered pushes are really the `push`
      // event filtered by `tags:`.
      const originalYaml = `name: Release
on:
  push:
    tags:
      - "v*"
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5`;

      const gui = yamlToGui(originalYaml);
      const convertedYaml = guiToYaml(gui);
      const guiAgain = yamlToGui(convertedYaml);

      expect(convertedYaml).not.toContain('tag_push');
      expect(convertedYaml).toContain('push:');
      expect(convertedYaml).toContain('tags:');
      expect(guiAgain.events[0].type).toBe('push');
      expect(guiAgain.events[0].tags).toEqual(['v*']);
    });

    // Regression tests: parseEvents modelled only a fixed set of keys under
    // `on:` and, unlike parseJobs/parseSteps, kept nothing else. A reusable
    // workflow's `workflow_call.secrets` and `.outputs` - its public interface
    // - were silently dropped the moment it was opened in GUI mode and saved,
    // breaking every caller and drifting every repo already holding the file.
    const REUSABLE_WITH_SECRETS = `name: Reusable Deploy
on:
  workflow_call:
    secrets:
      NPM_TOKEN:
        required: true
      SLACK_WEBHOOK:
        required: false
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: npm publish
`;

    const REUSABLE_WITH_OUTPUTS = `name: Reusable Build
on:
  workflow_call:
    outputs:
      image-tag:
        description: Published image tag
        value: \${{ jobs.build.outputs.tag }}
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: npm run build
`;

    const REUSABLE_WITH_BOTH = `name: Reusable Release
on:
  workflow_call:
    inputs:
      environment:
        description: Target environment
        required: true
        type: string
    outputs:
      image-tag:
        description: Published image tag
        value: \${{ jobs.release.outputs.tag }}
    secrets:
      NPM_TOKEN:
        required: true
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - run: npm publish
`;

    test('should round-trip workflow_call secrets byte-identically', () => {
      expect(guiToYaml(yamlToGui(REUSABLE_WITH_SECRETS))).toBe(REUSABLE_WITH_SECRETS);
    });

    test('should round-trip workflow_call outputs byte-identically', () => {
      expect(guiToYaml(yamlToGui(REUSABLE_WITH_OUTPUTS))).toBe(REUSABLE_WITH_OUTPUTS);
    });

    test('should round-trip workflow_call secrets and outputs together byte-identically', () => {
      expect(guiToYaml(yamlToGui(REUSABLE_WITH_BOTH))).toBe(REUSABLE_WITH_BOTH);
    });

    test('should keep workflow_call secrets and outputs when a step is edited', () => {
      const gui = yamlToGui(REUSABLE_WITH_BOTH);
      gui.jobs[0].steps[0].run = 'npm publish --provenance';

      const editedYaml = guiToYaml(gui);

      expect(editedYaml).toBe(REUSABLE_WITH_BOTH.replace('npm publish', 'npm publish --provenance'));
      expect(yamlToGui(editedYaml).events[0].unsupportedFields).toEqual({
        outputs: {
          'image-tag': {
            description: 'Published image tag',
            value: '${{ jobs.release.outputs.tag }}'
          }
        },
        secrets: { NPM_TOKEN: { required: true } }
      });
    });

    test('should leave a workflow without workflow_call unaffected', () => {
      const originalYaml = `name: CI
on:
  push:
    branches:
      - main
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: npm ci
`;

      const gui = yamlToGui(originalYaml);

      expect(gui.events[0].unsupportedFields).toBeUndefined();
      expect(guiToYaml(gui)).toBe(originalYaml);
    });

    test('should keep unmodelled push filters such as paths-ignore', () => {
      const originalYaml = `name: Docs
on:
  push:
    branches:
      - main
    paths-ignore:
      - docs/**
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: npm ci
`;

      expect(guiToYaml(yamlToGui(originalYaml))).toBe(originalYaml);
    });

    test('should drop a preserved -ignore filter when the GUI sets its counterpart', () => {
      // GitHub rejects an event carrying both `branches` and `branches-ignore`,
      // so preserving the ignore variant must not turn a lossy save into an
      // invalid workflow: the filter the user just set in the GUI wins.
      const originalYaml = `name: CI
on:
  push:
    branches-ignore:
      - gh-pages
    paths-ignore:
      - docs/**
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: npm ci
`;

      const gui = yamlToGui(originalYaml);
      const edited = {
        ...gui,
        events: [{ ...gui.events[0], branches: ['main'], paths: ['src/**'] }]
      };

      const editedYaml = guiToYaml(edited);

      expect(editedYaml).toContain('branches:');
      expect(editedYaml).toContain('paths:');
      expect(editedYaml).not.toContain('branches-ignore');
      expect(editedYaml).not.toContain('paths-ignore');
    });

    test('should keep unmodelled keys that appear before the modelled ones', () => {
      // Preserved keys are re-emitted after the modelled ones, so a workflow
      // that lists them first comes back reordered - lossless, but not
      // byte-identical. Pinning that so the difference is a decision, not a
      // surprise.
      const originalYaml = `name: Reusable
on:
  workflow_call:
    secrets:
      NPM_TOKEN:
        required: true
    inputs:
      environment:
        description: Target environment
        required: true
        type: string
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: npm publish
`;

      const convertedYaml = guiToYaml(yamlToGui(originalYaml));

      expect(convertedYaml).toContain('NPM_TOKEN');
      expect(convertedYaml).toContain('environment');
      expect(convertedYaml.indexOf('inputs:')).toBeLessThan(convertedYaml.indexOf('secrets:'));
    });
  });

  describe('yamlToGuiResult', () => {
    test('reports no error and a populated model for valid YAML', () => {
      const { gui, error } = yamlToGuiResult('name: CI\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: npm ci\n');

      expect(error).toBeNull();
      expect(gui.name).toBe('CI');
      expect(gui.jobs).toHaveLength(1);
      expect(gui.jobs[0].steps[0].run).toBe('npm ci');
    });

    test('reports an error for YAML that does not parse', () => {
      const { error } = yamlToGuiResult('name: [unclosed\non: push');

      expect(error).toBeTruthy();
      expect(typeof error).toBe('string');
    });

    test('reports an error when the document is not a mapping', () => {
      expect(yamlToGuiResult('just a bare string').error).toBeTruthy();
    });

    test('treats empty content as a new workflow, not a failure', () => {
      expect(yamlToGuiResult('').error).toBeNull();
      expect(yamlToGuiResult('   \n  ').error).toBeNull();
      expect(yamlToGuiResult('').gui).toEqual(DEFAULT_WORKFLOW_GUI);
    });

    test('yamlToGui keeps swallowing failures for existing callers', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

      expect(yamlToGui('name: [unclosed')).toEqual(DEFAULT_WORKFLOW_GUI);
      expect(() => yamlToGui('name: [unclosed')).not.toThrow();

      warn.mockRestore();
    });

    test('yamlToGui still converts valid YAML identically', () => {
      const content = 'name: CI\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: npm ci\n';
      expect(yamlToGui(content)).toEqual(yamlToGuiResult(content).gui);
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
