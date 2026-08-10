import { describe, it, expect } from 'vitest';
import { getActionInputSchema, actionsProjectToSchema, partitionActionInputs } from './actionInputSchemas';
import type { ActionInput, ActionsProject } from '../api/actionsProjects';

function makeInput(overrides: Partial<ActionInput> = {}): ActionInput {
  return {
    name: 'ref',
    description: 'The branch, tag or SHA to checkout',
    required: false,
    default: null,
    type: 'string',
    options: null,
    ...overrides,
  };
}

function makeProject(overrides: Partial<ActionsProject> = {}): ActionsProject {
  return {
    actions_project_id: 1,
    name: 'Checkout Repository',
    description: 'Check out repository content',
    source_url: 'https://github.com/actions/checkout/blob/v7.0.1/action.yml',
    owner: 'actions',
    repo: 'checkout',
    ref: 'v7.0.1',
    yaml_path: 'action.yml',
    inputs: [
      makeInput(),
      makeInput({ name: 'fetch-depth', description: 'Number of commits to fetch', required: true, default: '1' }),
    ],
    branding_icon: null,
    branding_color: null,
    ...overrides,
  };
}

describe('actionsProjectToSchema', () => {
  it('converts inputs to WorkflowCallInput shape, passing the stored type through', () => {
    const schema = actionsProjectToSchema(makeProject());
    expect(schema).toEqual({
      ref: {
        type: 'string', description: 'The branch, tag or SHA to checkout',
        required: false, default: undefined, options: undefined,
      },
      'fetch-depth': {
        type: 'string', description: 'Number of commits to fetch',
        required: true, default: '1', options: undefined,
      },
    });
  });

  it('maps null description/default/options to undefined', () => {
    const project = makeProject({ inputs: [makeInput({ name: 'path', description: null, default: null })] });
    expect(actionsProjectToSchema(project).path).toEqual({
      type: 'string', description: undefined, required: false, default: undefined, options: undefined,
    });
  });

  it('passes through an upgraded choice type with its options', () => {
    const project = makeProject({
      inputs: [makeInput({
        name: 'log-level', type: 'choice', options: ['debug', 'info', 'warn'], default: 'info',
      })],
    });
    expect(actionsProjectToSchema(project)['log-level']).toEqual({
      type: 'choice', description: 'The branch, tag or SHA to checkout',
      required: false, default: 'info', options: ['debug', 'info', 'warn'],
    });
  });

  it('passes through boolean and number types', () => {
    const project = makeProject({
      inputs: [
        makeInput({ name: 'verbose', type: 'boolean', default: 'true' }),
        makeInput({ name: 'retries', type: 'number', default: '3' }),
      ],
    });
    const schema = actionsProjectToSchema(project);
    expect(schema.verbose.type).toBe('boolean');
    expect(schema.retries.type).toBe('number');
  });
});

describe('getActionInputSchema', () => {
  it('matches an imported action by slug, ignoring the pinned version', () => {
    const projects = [makeProject()];
    expect(getActionInputSchema('actions/checkout@v7.0.1', projects)).toEqual(actionsProjectToSchema(projects[0]));
    expect(getActionInputSchema('actions/checkout@v4', projects)).toEqual(actionsProjectToSchema(projects[0]));
  });

  it('matches even without an @version suffix', () => {
    const projects = [makeProject()];
    expect(getActionInputSchema('actions/checkout', projects)).toEqual(actionsProjectToSchema(projects[0]));
  });

  it('returns undefined for actions outside the imported list', () => {
    expect(getActionInputSchema('some-org/unlisted-action@v1', [makeProject()])).toBeUndefined();
  });

  it('returns undefined when importedActions is empty', () => {
    expect(getActionInputSchema('actions/checkout@v7.0.1', [])).toBeUndefined();
  });
});

describe('partitionActionInputs', () => {
  const schema = actionsProjectToSchema(makeProject({
    inputs: [
      makeInput({ name: 'repository', required: true }),
      makeInput({ name: 'ref' }),
      makeInput({ name: 'token' }),
      makeInput({ name: 'fetch-depth' }),
    ],
  }));
  const names = (entries: [string, unknown][]) => entries.map(([name]) => name);
  const noSticky = new Set<string>();

  it('puts required inputs in visible and unset optional inputs in hidden', () => {
    const { visible, hidden } = partitionActionInputs(schema, undefined, noSticky);
    expect(names(visible)).toEqual(['repository']);
    expect(names(hidden)).toEqual(['ref', 'token', 'fetch-depth']);
  });

  it('promotes an optional input to visible once it is present in with', () => {
    const { visible, hidden } = partitionActionInputs(schema, { ref: 'main' }, noSticky);
    expect(names(visible)).toEqual(['repository', 'ref']);
    expect(names(hidden)).toEqual(['token', 'fetch-depth']);
  });

  it('treats an optional input set to an empty string as set', () => {
    const { visible } = partitionActionInputs(schema, { token: '' }, noSticky);
    expect(names(visible)).toEqual(['repository', 'token']);
  });

  it('keeps a sticky key visible after its value is cleared', () => {
    const { visible, hidden } = partitionActionInputs(schema, {}, new Set(['token']));
    expect(names(visible)).toEqual(['repository', 'token']);
    expect(names(hidden)).toEqual(['ref', 'fetch-depth']);
  });

  it('returns everything hidden when nothing is required and none are set', () => {
    const optionalOnly = actionsProjectToSchema(makeProject({
      inputs: [makeInput({ name: 'ref' }), makeInput({ name: 'token' })],
    }));
    const { visible, hidden } = partitionActionInputs(optionalOnly, undefined, noSticky);
    expect(visible).toEqual([]);
    expect(names(hidden)).toEqual(['ref', 'token']);
  });

  it('returns everything visible when every input is required', () => {
    const allRequired = actionsProjectToSchema(makeProject({
      inputs: [makeInput({ name: 'ref', required: true }), makeInput({ name: 'token', required: true })],
    }));
    const { visible, hidden } = partitionActionInputs(allRequired, undefined, noSticky);
    expect(names(visible)).toEqual(['ref', 'token']);
    expect(hidden).toEqual([]);
  });

  it('returns empty partitions for an undefined schema', () => {
    expect(partitionActionInputs(undefined, { ref: 'main' }, noSticky)).toEqual({ visible: [], hidden: [] });
  });
});
