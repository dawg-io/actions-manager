const tsParser = require('@typescript-eslint/parser')
const { noRestrictedImports, inlineStyleSelector } = require('./eslint.tailwind-rules')

/**
 * Standalone config for the CI "Enforce Tailwind-Only Styling Policy" step.
 * Runs only the Tailwind styling rules, without the WithStatement ban from
 * eslint.config.js, matching the previous .eslintrc.tailwind.json scope.
 */
module.exports = [
  {
    files: ['src/**/*.{js,jsx,ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 2020,
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      'no-restricted-syntax': ['error', inlineStyleSelector],
      'no-restricted-imports': noRestrictedImports,
    },
  },
]
