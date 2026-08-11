import { resourceCompletions } from './YAMLEditor';
import { toResources, WorkflowResource } from '../utils/workflowResources';

// Covers the data behind the editor's inline `${{ ... }}` autocomplete. The
// EditorView itself is never instantiated in jsdom, so the mapping is asserted
// directly.
describe('resourceCompletions', () => {
  const resources: WorkflowResource[] = [
    { kind: 'secret', name: 'AM_REG1_DOCKER_PASSWORD', repo: 'acme/web' },
    { kind: 'variable', name: 'AM_REG1_DOCKER_REGISTRY', repo: 'acme/web' },
    { kind: 'environment', name: 'production', repo: 'acme/web' },
  ];

  test('offers secrets under the secrets context', () => {
    const secret = resourceCompletions(resources).find(option =>
      option.label.startsWith('secrets.')
    );
    expect(secret?.label).toBe('secrets.AM_REG1_DOCKER_PASSWORD');
  });

  test('offers variables under vars, not secrets', () => {
    const labels = resourceCompletions(resources).map(option => option.label);
    expect(labels).toContain('vars.AM_REG1_DOCKER_REGISTRY');
    expect(labels).not.toContain('secrets.AM_REG1_DOCKER_REGISTRY');
  });

  test('excludes deployment environments, which are a job key not an expression', () => {
    const labels = resourceCompletions(resources).map(option => option.label);
    expect(labels).toHaveLength(2);
    expect(labels.some(label => label.includes('production'))).toBe(false);
  });

  test('names the owning repository in the completion info', () => {
    const secret = resourceCompletions(resources)[0];
    expect(secret.info).toBe('Project secret in acme/web');
  });

  test('never carries a stored value into a completion', () => {
    const mapped = toResources({
      secrets: [{ secret_key: 'TOKEN', repo: 'acme/web', secret_value: 'hunter2' } as any],
      envVars: [{ env_key: 'REGISTRY', repo: 'acme/web', value: 'ghcr.io/acme' } as any],
    });

    const serialized = JSON.stringify(resourceCompletions(mapped));
    expect(serialized).not.toContain('hunter2');
    expect(serialized).not.toContain('ghcr.io/acme');
  });

  test('returns nothing when the project has no resources', () => {
    expect(resourceCompletions([])).toEqual([]);
  });
});
