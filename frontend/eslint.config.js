import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import prettier from 'eslint-config-prettier';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'coverage/**',
      'node_modules/**',
      'src/api/schema.d.ts',
      'dev-dist/**',
      '*.config.js',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
    },
    settings: {
      react: { version: 'detect' },
    },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,

      // React 19 / new JSX transform — these are noise.
      'react/prop-types': 'off',
      'react/react-in-jsx-scope': 'off',

      // TypeScript escapes. The cleanup these were staged for is done —
      // the tree has zero `any` and zero unused vars — so they are errors
      // now, and `npm run lint` runs with --max-warnings 0 to keep it that
      // way. Reintroducing one should fail the build, not print a warning
      // nobody reads.
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],

      // Things we genuinely want to keep red.
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      // a11y. The tree is clean on all three, so they block too; the only
      // autofocus uses are the first field of single-purpose auth pages,
      // each carrying a justified inline disable.
      'jsx-a11y/click-events-have-key-events': 'error',
      'jsx-a11y/no-static-element-interactions': 'error',
      'jsx-a11y/no-autofocus': 'error',

      // `allowTransparency` is a valid iframe attribute that React's type
      // checker doesn't know about; the alternative is to spread it via
      // dangerouslySetInnerHTML which is worse.
      'react/no-unknown-property': ['error', { ignore: ['allowTransparency'] }],
    },
  },
  {
    files: ['src/test/**/*.{ts,tsx}', 'src/**/*.test.{ts,tsx}'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      // Tests routinely poke at internals and use any-typed fixtures.
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      'no-console': 'off',
      // Tests intentionally construct elements (e.g. orphan <label>) to
      // exercise hook behaviour; a11y on test fixtures is not the goal.
      'jsx-a11y/label-has-associated-control': 'off',
      'jsx-a11y/click-events-have-key-events': 'off',
      'jsx-a11y/no-static-element-interactions': 'off',
    },
  },
  prettier,
);
