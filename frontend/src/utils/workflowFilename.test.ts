import {
  stripWorkflowExtension,
  normalizeWorkflowStem,
  normalizeWorkflowFilename,
  extractWorkflowPrefixAndStem,
  validateWorkflowName,
  setWorkflowYamlName,
} from './workflowFilename';

describe('workflowFilename utilities', () => {
  describe('stripWorkflowExtension', () => {
    test('strips .yml extension', () => {
      expect(stripWorkflowExtension('build.yml')).toBe('build');
    });

    test('strips .yaml extension', () => {
      expect(stripWorkflowExtension('build.yaml')).toBe('build');
    });

    test('returns name unchanged when no extension present', () => {
      expect(stripWorkflowExtension('build')).toBe('build');
    });

    test('is case-insensitive for extension', () => {
      expect(stripWorkflowExtension('build.YML')).toBe('build');
      expect(stripWorkflowExtension('build.Yaml')).toBe('build');
    });

    test('strips only the trailing extension (not mid-name occurrences)', () => {
      expect(stripWorkflowExtension('my.yml.test')).toBe('my.yml.test');
    });

    test('handles empty string', () => {
      expect(stripWorkflowExtension('')).toBe('');
    });

    test('handles name with hyphens and underscores', () => {
      expect(stripWorkflowExtension('build-and-test.yml')).toBe('build-and-test');
      expect(stripWorkflowExtension('build_test.yaml')).toBe('build_test');
    });
  });

  describe('normalizeWorkflowStem', () => {
    test('trims whitespace and strips .yml extension', () => {
      expect(normalizeWorkflowStem('  build.yml  ')).toBe('build');
    });

    test('trims whitespace and strips .yaml extension', () => {
      expect(normalizeWorkflowStem('  build.yaml  ')).toBe('build');
    });

    test('returns stem unchanged when no extension', () => {
      expect(normalizeWorkflowStem('build')).toBe('build');
    });

    test('returns empty string for whitespace-only input', () => {
      expect(normalizeWorkflowStem('   ')).toBe('');
    });

    test('returns empty string for empty input', () => {
      expect(normalizeWorkflowStem('')).toBe('');
    });
  });

  describe('normalizeWorkflowFilename', () => {
    test('trims whitespace and appends .yml', () => {
      expect(normalizeWorkflowFilename('  build.yaml  ')).toBe('build.yml');
    });

    test('converts .yaml to .yml', () => {
      expect(normalizeWorkflowFilename('build.yaml')).toBe('build.yml');
    });

    test('appends .yml when no extension', () => {
      expect(normalizeWorkflowFilename('build')).toBe('build.yml');
    });

    test('keeps .yml unchanged', () => {
      expect(normalizeWorkflowFilename('build.yml')).toBe('build.yml');
    });

    test('returns empty string for whitespace-only input', () => {
      expect(normalizeWorkflowFilename('   ')).toBe('');
    });

    test('returns empty string for empty input', () => {
      expect(normalizeWorkflowFilename('')).toBe('');
    });
  });

  describe('extractWorkflowPrefixAndStem', () => {
    test('splits AM_CODE_ prefix from stem', () => {
      expect(extractWorkflowPrefixAndStem('AM_RWW1_testrwx')).toEqual({ prefix: 'AM_RWW1_', stem: 'testrwx' });
    });

    test('handles multi-segment stem', () => {
      expect(extractWorkflowPrefixAndStem('AM_PROJ_my-workflow-name')).toEqual({ prefix: 'AM_PROJ_', stem: 'my-workflow-name' });
    });

    test('returns empty prefix when name has no AM_ prefix', () => {
      expect(extractWorkflowPrefixAndStem('testrwx')).toEqual({ prefix: '', stem: 'testrwx' });
    });

    test('returns empty prefix for AM_ with lowercase code (non-matching)', () => {
      // Code part requires [A-Z0-9]+ so lowercase codes do not match
      expect(extractWorkflowPrefixAndStem('AM_rww1_testrwx')).toEqual({ prefix: '', stem: 'AM_rww1_testrwx' });
    });

    test('returns empty prefix when AM_ has empty code segment', () => {
      // [A-Z0-9]+ requires at least one character, so AM__ does not match
      expect(extractWorkflowPrefixAndStem('AM__testrwx')).toEqual({ prefix: '', stem: 'AM__testrwx' });
    });

    test('returns empty prefix and empty stem for empty string', () => {
      expect(extractWorkflowPrefixAndStem('')).toEqual({ prefix: '', stem: '' });
    });

    test('handles digits-only code', () => {
      expect(extractWorkflowPrefixAndStem('AM_123_deploy')).toEqual({ prefix: 'AM_123_', stem: 'deploy' });
    });
  });

  describe('validateWorkflowName', () => {
    test('returns null for a simple valid name', () => {
      expect(validateWorkflowName('build')).toBeNull();
    });

    test('returns null for a valid name with .yml extension', () => {
      expect(validateWorkflowName('build.yml')).toBeNull();
    });

    test('returns null for a valid name with .yaml extension', () => {
      expect(validateWorkflowName('build.yaml')).toBeNull();
    });

    test('returns null for names with hyphens, underscores, dots, and digits', () => {
      expect(validateWorkflowName('my-build_1.test')).toBeNull();
    });

    test('rejects empty string', () => {
      expect(validateWorkflowName('')).toMatch(/empty/i);
    });

    test('rejects whitespace-only input', () => {
      expect(validateWorkflowName('   ')).toMatch(/empty/i);
    });

    test('rejects names containing forward slashes', () => {
      expect(validateWorkflowName('foo/bar')).toMatch(/path separator/i);
    });

    test('rejects names containing backslashes', () => {
      expect(validateWorkflowName('foo\\bar')).toMatch(/path separator/i);
    });

    test('rejects names containing ".." traversal', () => {
      expect(validateWorkflowName('foo..bar')).toMatch(/\.\./);
    });

    test('rejects names that start with a dot', () => {
      expect(validateWorkflowName('.hidden')).toMatch(/dot/i);
    });

    test('rejects names containing spaces', () => {
      expect(validateWorkflowName('my workflow')).toMatch(/letters, numbers/i);
    });

    test('rejects names containing special characters', () => {
      expect(validateWorkflowName('foo@bar')).toMatch(/letters, numbers/i);
    });

    test('rejects names longer than 100 characters', () => {
      expect(validateWorkflowName('a'.repeat(101))).toMatch(/too long/i);
    });

    test('accepts names exactly 100 characters long', () => {
      expect(validateWorkflowName('a'.repeat(100))).toBeNull();
    });

    // Regression tests for path traversal and security edge cases
    test('rejects names starting with ../ traversal', () => {
      expect(validateWorkflowName('../x')).toMatch(/path separator/i);
    });

    test('rejects names ending with a dot', () => {
      expect(validateWorkflowName('workflow.')).toMatch(/dot/i);
    });

    test('rejects names ending with dot after stripping extension', () => {
      // 'workflow..yml' strips to 'workflow.' which ends with dot
      expect(validateWorkflowName('workflow..yml')).toMatch(/dot/i);
    });

    test('rejects duplicate .yml.yml extensions', () => {
      // normalizeWorkflowStem strips the trailing .yml, leaving 'test.yml'
      // which is valid (dots are allowed in the middle)
      expect(validateWorkflowName('test.yml.yml')).toBeNull();
    });

    test('rejects Unicode homoglyph lookalikes', () => {
      // Cyrillic 'a' (U+0430) looks like Latin 'a' but is not allowed
      expect(validateWorkflowName('workflowа')).toMatch(/letters, numbers/i);
    });

    test('rejects Unicode homoglyph slashes', () => {
      // Division slash (U+2215) looks like '/' but is not a path separator
      // Should be rejected by character class check
      expect(validateWorkflowName('work∕flow')).toMatch(/letters, numbers/i);
    });

    test('rejects Unicode zero-width characters', () => {
      // Zero-width space (U+200B) is invisible but present
      expect(validateWorkflowName('work\u200Bflow')).toMatch(/letters, numbers/i);
    });

    test('rejects hidden file pattern without extension', () => {
      expect(validateWorkflowName('.env')).toMatch(/dot/i);
    });

    test('rejects hidden file pattern with extension', () => {
      expect(validateWorkflowName('.gitignore.yml')).toMatch(/dot/i);
    });
  });

  describe('setWorkflowYamlName', () => {
    test('adds a default dispatch workflow when content is empty', () => {
      expect(setWorkflowYamlName('', ' build ')).toBe(
        'name: build\n\non:\n  workflow_dispatch:\n\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v6\n'
      );
    });

    test('replaces an existing top-level name', () => {
      expect(setWorkflowYamlName('name: CI\non: push', 'custom-workflow')).toBe('name: custom-workflow\non: push');
    });

    test('prepends a name when one is missing', () => {
      expect(setWorkflowYamlName('on: push', 'custom-workflow')).toBe('name: custom-workflow\n\non: push');
    });
  });
});
