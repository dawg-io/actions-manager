const tsParser = require('@typescript-eslint/parser')
const { noRestrictedImports, inlineStyleSelector } = require('./eslint.tailwind-rules')

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
      'no-restricted-syntax': ['error', 'WithStatement', inlineStyleSelector],
      'no-restricted-imports': noRestrictedImports,
    },
  },
]
