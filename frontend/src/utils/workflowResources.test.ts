import { EditorState } from '@codemirror/state';
import {
  buildResourceExpression,
  insertIntoText,
  toResources,
  groupResourceScopes,
  WorkflowResource,
} from './workflowResources';

describe('buildResourceExpression', () => {
  test('builds a secrets expression', () => {
    expect(buildResourceExpression({ kind: 'secret', name: 'DOCKER_PASSWORD', repo: 'acme/web' }))
      .toBe('${{ secrets.DOCKER_PASSWORD }}');
  });

  test('builds a vars expression for variables, not secrets', () => {
    expect(buildResourceExpression({ kind: 'variable', name: 'DOCKER_REGISTRY', repo: 'acme/web' }))
      .toBe('${{ vars.DOCKER_REGISTRY }}');
  });

  test('builds the environment job key rather than an expression', () => {
    expect(buildResourceExpression({ kind: 'environment', name: 'production', repo: 'acme/web' }))
      .toBe('environment: production');
  });

  test('passes prefix-mode names through verbatim', () => {
    expect(buildResourceExpression({ kind: 'secret', name: 'AM_REG1_DOCKER_PASSWORD', repo: 'acme/web' }))
      .toBe('${{ secrets.AM_REG1_DOCKER_PASSWORD }}');
    expect(buildResourceExpression({ kind: 'variable', name: 'AM_REG1_DOCKER_REGISTRY', repo: 'acme/web' }))
      .toBe('${{ vars.AM_REG1_DOCKER_REGISTRY }}');
  });
});

describe('insertIntoText', () => {
  const yaml = 'jobs:\n  build:\n    steps:\n      - run: echo \n';

  test('inserts at the caret and leaves the rest of the YAML byte-identical', () => {
    const caret = yaml.indexOf('echo ') + 'echo '.length;
    const result = insertIntoText(yaml, caret, caret, '${{ secrets.TOKEN }}');

    expect(result.text).toBe('jobs:\n  build:\n    steps:\n      - run: echo ${{ secrets.TOKEN }}\n');
    expect(result.text.slice(0, caret)).toBe(yaml.slice(0, caret));
    expect(result.text.slice(result.cursor)).toBe(yaml.slice(caret));
  });

  test('returns the caret immediately after the inserted text', () => {
    const result = insertIntoText('abcdef', 3, 3, 'XY');
    expect(result.text).toBe('abcXYdef');
    expect(result.cursor).toBe(5);
  });

  test('replaces a selection rather than duplicating it', () => {
    const result = insertIntoText('echo OLD_VALUE end', 5, 14, '${{ vars.NEW }}');
    expect(result.text).toBe('echo ${{ vars.NEW }} end');
    expect(result.cursor).toBe(20);
  });

  test('inserts at the start and end of the document', () => {
    expect(insertIntoText('tail', 0, 0, 'head-')).toEqual({ text: 'head-tail', cursor: 5 });
    expect(insertIntoText('head', 4, 4, '-tail')).toEqual({ text: 'head-tail', cursor: 9 });
  });

  test('clamps out-of-range offsets instead of producing undefined slices', () => {
    expect(insertIntoText('abc', 99, 99, 'X')).toEqual({ text: 'abcX', cursor: 4 });
    expect(insertIntoText('abc', -5, -5, 'X')).toEqual({ text: 'Xabc', cursor: 1 });
  });
});

// The YAML editor inserts via CodeMirror's own cursor-aware primitive. Exercising
// it through EditorState needs no DOM, and proves the same two guarantees the
// plain-input path above asserts.
describe('CodeMirror insertion semantics', () => {
  const doc = 'name: ci\non: push\njobs:\n  build:\n    steps:\n      - run: echo \n';

  test('replaceSelection inserts at the cursor and preserves surrounding YAML', () => {
    const caret = doc.indexOf('echo ') + 'echo '.length;
    const state = EditorState.create({ doc, selection: { anchor: caret } });

    const next = state.update(state.replaceSelection('${{ secrets.AM_REG1_TOKEN }}')).state;

    expect(next.doc.toString()).toBe(
      'name: ci\non: push\njobs:\n  build:\n    steps:\n      - run: echo ${{ secrets.AM_REG1_TOKEN }}\n'
    );
    expect(next.doc.toString().slice(0, caret)).toBe(doc.slice(0, caret));
    expect(next.doc.lines).toBe(state.doc.lines);
  });

  test('replaceSelection leaves the caret after the inserted text', () => {
    const caret = doc.indexOf('on: push');
    const state = EditorState.create({ doc, selection: { anchor: caret } });

    const next = state.update(state.replaceSelection('# note\n')).state;

    expect(next.selection.main.head).toBe(caret + '# note\n'.length);
  });
});

describe('toResources', () => {
  test('identifies secrets and variables by kind', () => {
    const resources = toResources({
      secrets: [{ secret_key: 'DOCKER_PASSWORD', repo: 'acme/web' }],
      envVars: [{ env_key: 'DOCKER_REGISTRY', repo: 'acme/web' }],
      environments: [{ name: 'production', repo: 'acme/web' }],
    });

    expect(resources).toEqual([
      { kind: 'secret', name: 'DOCKER_PASSWORD', repo: 'acme/web' },
      { kind: 'variable', name: 'DOCKER_REGISTRY', repo: 'acme/web' },
      { kind: 'environment', name: 'production', repo: 'acme/web' },
    ]);
  });

  test('drops values so no secret or variable value can reach the UI', () => {
    const resources = toResources({
      secrets: [{ secret_key: 'TOKEN', repo: 'acme/web', secret_value: 'hunter2' } as any],
      envVars: [{ env_key: 'REGISTRY', repo: 'acme/web', value: 'ghcr.io' } as any],
    });

    expect(JSON.stringify(resources)).not.toContain('hunter2');
    expect(JSON.stringify(resources)).not.toContain('ghcr.io');
    for (const resource of resources) {
      expect(Object.keys(resource).sort((a, b) => a.localeCompare(b))).toEqual(['kind', 'name', 'repo']);
    }
  });

  test('accepts the alternative `name` key used by some secret payloads', () => {
    expect(toResources({ secrets: [{ name: 'LEGACY_KEY', repo: 'acme/web' }] }))
      .toEqual([{ kind: 'secret', name: 'LEGACY_KEY', repo: 'acme/web' }]);
  });

  test('skips rows with no usable name and tolerates missing repos', () => {
    const resources = toResources({
      secrets: [{ repo: 'acme/web' }, { secret_key: 'OK' }],
      envVars: [{ repo: 'acme/web' }],
    });

    expect(resources).toEqual([{ kind: 'secret', name: 'OK', repo: '' }]);
  });

  test('returns an empty list when nothing is configured', () => {
    expect(toResources({})).toEqual([]);
  });
});

describe('groupResourceScopes', () => {
  test('collapses the same resource across repos into one entry listing both', () => {
    const resources: WorkflowResource[] = [
      { kind: 'secret', name: 'TOKEN', repo: 'acme/web' },
      { kind: 'secret', name: 'TOKEN', repo: 'acme/api' },
      { kind: 'variable', name: 'TOKEN', repo: 'acme/web' },
    ];

    const grouped = groupResourceScopes(resources);

    expect(grouped).toHaveLength(2);
    expect(grouped[0]).toMatchObject({ kind: 'secret', name: 'TOKEN', repos: ['acme/web', 'acme/api'] });
    expect(grouped[1]).toMatchObject({ kind: 'variable', name: 'TOKEN', repos: ['acme/web'] });
  });

  test('does not repeat a repo listed twice', () => {
    const grouped = groupResourceScopes([
      { kind: 'secret', name: 'TOKEN', repo: 'acme/web' },
      { kind: 'secret', name: 'TOKEN', repo: 'acme/web' },
    ]);

    expect(grouped[0].repos).toEqual(['acme/web']);
  });
});
