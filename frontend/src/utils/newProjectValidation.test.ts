import {
  validateProjectInputs,
  describeProjectLimitError,
  mismatchedRepos,
  repoMatchesVisibilityScope,
  type ProjectInputs,
} from './newProjectValidation';

const repo = (full_name: string, isPrivate = false) => ({
  name: full_name.split('/').pop() as string,
  full_name,
  private: isPrivate,
});

const inputs = (over: Partial<ProjectInputs> = {}): ProjectInputs => ({
  projectName: 'My Project',
  selectedRepos: ['acme-corp/api'],
  repos: [repo('acme-corp/api')],
  visibilityScope: 'public',
  privateAllowedByTier: true,
  useCustomKey: false,
  projectKey: '',
  ...over,
});

describe('repoMatchesVisibilityScope', () => {
  test('matches public repos to the public scope', () => {
    expect(repoMatchesVisibilityScope(repo('acme-corp/api'), 'public')).toBe(true);
    expect(repoMatchesVisibilityScope(repo('acme-corp/api'), 'private')).toBe(false);
  });

  test('matches private repos to the private scope', () => {
    expect(repoMatchesVisibilityScope(repo('acme-corp/api', true), 'private')).toBe(true);
    expect(repoMatchesVisibilityScope(repo('acme-corp/api', true), 'public')).toBe(false);
  });
});

describe('mismatchedRepos', () => {
  test('reports a selected repo whose visibility does not match', () => {
    const result = mismatchedRepos(
      inputs({
        selectedRepos: ['acme-corp/api', 'acme-corp/secret'],
        repos: [repo('acme-corp/api'), repo('acme-corp/secret', true)],
      }),
    );
    expect(result).toEqual(['acme-corp/secret']);
  });

  test('leaves unknown repos to the backend rather than blocking', () => {
    expect(mismatchedRepos(inputs({ selectedRepos: ['acme-corp/not-loaded'], repos: [] }))).toEqual([]);
  });
});

describe('validateProjectInputs', () => {
  test('accepts a well-formed project', () => {
    expect(validateProjectInputs(inputs())).toBeNull();
  });

  test('requires a name', () => {
    expect(validateProjectInputs(inputs({ projectName: '   ' }))).toMatch(/cannot be empty/i);
  });

  test('requires at least one repository', () => {
    expect(validateProjectInputs(inputs({ selectedRepos: [] }))).toMatch(/at least one repository/i);
  });

  test('names the repositories that do not match the visibility scope', () => {
    const error = validateProjectInputs(
      inputs({
        selectedRepos: ['acme-corp/secret'],
        repos: [repo('acme-corp/secret', true)],
      }),
    );
    expect(error).toMatch(/acme-corp\/secret/);
    expect(error).toMatch(/Public visibility/);
  });

  test('blocks private projects the tier does not allow', () => {
    const error = validateProjectInputs(
      inputs({
        visibilityScope: 'private',
        privateAllowedByTier: false,
        repos: [repo('acme-corp/api', true)],
      }),
    );
    expect(error).toMatch(/Free plan accounts cannot create private/i);
  });

  test.each([['A'], ['ABCDEFGHIJK'], ['!!']])('rejects the custom key %s', (key) => {
    expect(validateProjectInputs(inputs({ useCustomKey: true, projectKey: key }))).toMatch(
      /2–10 characters/,
    );
  });

  test('accepts a custom key once punctuation is stripped', () => {
    expect(validateProjectInputs(inputs({ useCustomKey: true, projectKey: 'ap-i' }))).toBeNull();
  });

  test('ignores the key field when custom keys are off', () => {
    expect(validateProjectInputs(inputs({ useCustomKey: false, projectKey: 'x' }))).toBeNull();
  });
});

describe('describeProjectLimitError', () => {
  test('passes beta wording through untouched', () => {
    const message = 'Self-hosted beta allows 4 Caller Workflow Projects.';
    expect(describeProjectLimitError(message)).toBe(message);
  });

  test('rewrites the free-tier limit into an actionable message', () => {
    expect(describeProjectLimitError('You can only create up to 3 projects')).toMatch(
      /upgrade to Professional/i,
    );
  });

  test('rewrites the professional-tier limit', () => {
    expect(describeProjectLimitError('Professional accounts can create up to 10 projects')).toMatch(
      /upgrade to Enterprise/i,
    );
  });

  test('falls back to the backend message it does not recognise', () => {
    expect(describeProjectLimitError('Something else went wrong')).toBe('Something else went wrong');
  });
});
