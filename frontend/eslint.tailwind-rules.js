/**
 * ─────────────────────────────────────────────────────────────────────────
 * TAILWIND-ONLY STYLING ENFORCEMENT
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Tailwind CSS is the ONLY permitted styling system in this project.
 * These rules prevent regressions by blocking all non-Tailwind styling
 * patterns. To fix a violation, replace the offending code with Tailwind
 * utility classes.
 *
 * ALLOWED EXCEPTIONS:
 *   • `src/index.css`  – Tailwind base/components/utilities directives only.
 *     Any other CSS or SCSS file is NOT permitted.
 *
 * FILES WITH LEGACY VIOLATIONS:
 *   Files that existed before this policy was introduced carry an
 *   eslint-disable comment at the top of the file.
 *   • Inline styles:   eslint-disable no-restricted-syntax
 *   • CSS/SCSS imports: eslint-disable no-restricted-imports
 *   Remove the comment once all violations have been migrated to Tailwind.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Shared between eslint.config.js (general lint, includes WithStatement ban)
 * and eslint.tailwind.config.js (standalone Tailwind-policy-only run) so the
 * two configs can't drift apart.
 */
module.exports = {
  noRestrictedImports: [
    'error',
    {
      paths: [
        { name: 'styled-components', message: 'styled-components is not allowed. Use Tailwind CSS utility classes instead.' },
        { name: '@emotion/react', message: '@emotion/react is not allowed. Use Tailwind CSS utility classes instead.' },
        { name: '@emotion/styled', message: '@emotion/styled is not allowed. Use Tailwind CSS utility classes instead.' },
        { name: '@emotion/css', message: '@emotion/css is not allowed. Use Tailwind CSS utility classes instead.' },
      ],
      patterns: [
        {
          group: ['**/*.css', '!./index.css'],
          message: 'CSS file imports are not allowed. Use Tailwind CSS utility classes instead. Exception: ./index.css for Tailwind base directives.',
          caseSensitive: true,
        },
        {
          group: ['**/*.scss'],
          message: 'SCSS file imports are not allowed. Use Tailwind CSS utility classes instead.',
        },
      ],
    },
  ],
  inlineStyleSelector: {
    selector: "JSXAttribute[name.name='style']",
    message:
      'Inline styles are not allowed. Use Tailwind CSS utility classes instead. See: https://tailwindcss.com/docs',
  },
}
