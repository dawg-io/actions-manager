/**
 * Workflow filename utilities.
 *
 * Centralises all logic for stripping, normalising, and constructing
 * workflow filenames so the UI consistently shows only the base name
 * while ensuring `.yml` is always used when saving or comparing.
 */

/**
 * Strips a `.yml` or `.yaml` extension from a workflow name.
 *
 * @example
 * stripWorkflowExtension("build.yml")  // → "build"
 * stripWorkflowExtension("build.yaml") // → "build"
 * stripWorkflowExtension("build")      // → "build"
 */
export function stripWorkflowExtension(name: string): string {
  return name.replace(/\.(yml|yaml)$/i, '');
}

/**
 * Returns the canonical stem for DB storage: trim whitespace then strip any
 * `.yml`/`.yaml` extension.  Returns an empty string if the result is empty.
 *
 * The backend stores `workflow_name` as a stem and appends `.yml` itself via
 * `format_workflow_name()`, so all DB writes must use this form.
 *
 * @example
 * normalizeWorkflowStem("  build.yaml  ") // → "build"
 * normalizeWorkflowStem("build.yml")       // → "build"
 * normalizeWorkflowStem("build")           // → "build"
 */
export function normalizeWorkflowStem(name: string): string {
  return stripWorkflowExtension(name.trim());
}

/**
 * Trims whitespace, strips any existing `.yml`/`.yaml` extension, then
 * appends `.yml`.  Returns an empty string if the trimmed base is empty.
 *
 * Use this only when constructing a display label or a literal GitHub path —
 * **not** when writing to the DB (use {@link normalizeWorkflowStem} instead).
 *
 * @example
 * normalizeWorkflowFilename("  build.yaml  ") // → "build.yml"
 * normalizeWorkflowFilename("build")           // → "build.yml"
 * normalizeWorkflowFilename("build.yml")       // → "build.yml"
 */
export function normalizeWorkflowFilename(name: string): string {
  const base = normalizeWorkflowStem(name);
  if (!base) return '';
  return `${base}.yml`;
}

/**
 * Splits a workflow name (with any `.yml`/`.yaml` extension already stripped)
 * into a prefix segment and a stem.
 *
 * The prefix follows the Actions Manager naming convention `AM_{CODE}_` where
 * CODE contains only uppercase letters and digits.  When the name does not
 * start with that pattern the prefix is returned as an empty string so the
 * caller can decide not to render a prefix segment.
 *
 * @example
 * extractWorkflowPrefixAndStem("AM_RWW1_testrwx") // → { prefix: "AM_RWW1_", stem: "testrwx" }
 * extractWorkflowPrefixAndStem("testrwx")          // → { prefix: "",         stem: "testrwx" }
 * extractWorkflowPrefixAndStem("AM_PROJ_my-wf")   // → { prefix: "AM_PROJ_", stem: "my-wf" }
 */
export function extractWorkflowPrefixAndStem(name: string): { prefix: string; stem: string } {
  const match = name.match(/^(AM_[A-Z0-9]+_)(.+)$/);
  if (match) {
    return { prefix: match[1], stem: match[2] };
  }
  return { prefix: '', stem: name };
}

/**
 * Validates a user-supplied workflow base name.
 *
 * Returns an error message string when the name is invalid, or `null` when the
 * name is acceptable for use as a GitHub Actions workflow filename.
 *
 * Rules:
 * - May be supplied with or without a `.yml`/`.yaml` extension; the extension
 *   is stripped before validating the stem.
 * - The stem must be non-empty after trimming.
 * - The stem may only contain letters, numbers, dots, underscores, and hyphens
 *   (the same character class GitHub permits in workflow filenames).
 * - The stem must not contain path separators or `..` traversal sequences.
 * - The stem may not start or end with a dot.
 * - The stem length must be ≤ 100 characters (matches typical OS filename limits).
 */
export function validateWorkflowName(name: string): string | null {
  const stem = normalizeWorkflowStem(name ?? '');
  if (!stem) {
    return 'Workflow name cannot be empty.';
  }
  if (stem.includes('/') || stem.includes('\\')) {
    return 'Workflow name cannot contain path separators.';
  }
  if (stem.includes('..')) {
    return 'Workflow name cannot contain ".." sequences.';
  }
  if (stem.startsWith('.') || stem.endsWith('.')) {
    return 'Workflow name cannot start or end with a dot.';
  }
  if (!/^[A-Za-z0-9._-]+$/.test(stem)) {
    return 'Workflow name may only contain letters, numbers, dots, underscores, and hyphens.';
  }
  if (stem.length > 100) {
    return 'Workflow name is too long (max 100 characters).';
  }
  return null;
}

/**
 * Ensures generated workflow YAML uses the user-provided workflow name in the
 * top-level GitHub Actions `name` field.
 */
export function setWorkflowYamlName(content: string | undefined, name: string): string {
  const stem = normalizeWorkflowStem(name);
  const yamlName = `name: ${stem}`;
  const existingContent = content ?? '';

  if (!existingContent.trim()) {
    return `${yamlName}\n\non:\n  workflow_dispatch:\n\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v6\n`;
  }

  if (/^name\s*:/m.test(existingContent)) {
    return existingContent.replace(/^name\s*:[^\r\n]*/m, yamlName);
  }

  return `${yamlName}\n\n${existingContent.trimStart()}`;
}
