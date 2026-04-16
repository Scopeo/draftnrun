module.exports = {
  env: {
    browser: true,
    es2021: true,
  },
  extends: [
    '@antfu/eslint-config-vue',
    'plugin:vue/vue3-recommended',
    'plugin:import/recommended',
    'plugin:import/typescript',
    'plugin:promise/recommended',
    'plugin:sonarjs/recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:case-police/recommended',
    'plugin:regexp/recommended',
    'plugin:prettier/recommended',
  ],
  parser: 'vue-eslint-parser',
  parserOptions: {
    ecmaVersion: 13,
    parser: '@typescript-eslint/parser',
    sourceType: 'module',
  },
  plugins: ['vue', '@typescript-eslint', 'regex', 'regexp'],
  ignorePatterns: [
    'src/plugins/iconify/*.js',
    'node_modules',
    'dist',
    '*.d.ts',
    'vendor',
    '*.json',
    'supabase/**',
    '*.yml',
    '*.yaml',
  ],
  rules: {
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',

    // Formatting handled by Prettier
    'n/prefer-global/process': ['off'],
    'sonarjs/cognitive-complexity': ['off'],

    'vue/first-attribute-linebreak': 'off',

    'antfu/top-level-function': 'off',
    'antfu/if-newline': 'off',
    '@typescript-eslint/no-explicit-any': 'warn',

    // Camelcase disabled - conflicts with database field names
    camelcase: 'off',

    // Disable max-len (handled by Prettier printWidth)
    'max-len': 'off',

    // Warn for unused variables (too many to fix immediately)
    '@typescript-eslint/no-unused-vars': ['warn', { varsIgnorePattern: '^_+$', argsIgnorePattern: '^_+$' }],
    // Disable duplicate rule from @antfu config
    'unused-imports/no-unused-vars': 'off',
    // Disable - functions are hoisted, common pattern in Vue composables
    '@typescript-eslint/no-use-before-define': 'off',
    // Warn instead of error for confirm() dialogs
    'no-alert': 'warn',

    'vue/multi-word-component-names': 'off',

    'padding-line-between-statements': [
      'error',
      { blankLine: 'always', prev: 'expression', next: 'const' },
      { blankLine: 'always', prev: 'const', next: 'expression' },
      { blankLine: 'always', prev: 'multiline-const', next: '*' },
      { blankLine: 'always', prev: '*', next: 'multiline-const' },
    ],

    // Plugin: eslint-plugin-import
    'import/prefer-default-export': 'off',
    'import/newline-after-import': ['error', { count: 1 }],
    'no-restricted-imports': [
      'error',
      'vuetify/components',
      {
        name: 'vue3-apexcharts',
        message: 'apexcharts are auto imported',
      },
    ],

    // For omitting extension for ts files
    'import/extensions': [
      'error',
      'ignorePackages',
      {
        js: 'never',
        jsx: 'never',
        ts: 'never',
        tsx: 'never',
      },
    ],

    // ignore virtual files
    'import/no-unresolved': [
      2,
      {
        ignore: [
          '~pages$',
          'virtual:generated-layouts',
          '#auth$',
          '#components$',

          // Ignore vite's ?raw imports
          '.*\?raw',
        ],
      },
    ],

    // Thanks: https://stackoverflow.com/a/63961972/10796681
    'no-shadow': 'off',
    '@typescript-eslint/no-shadow': 'warn',

    '@typescript-eslint/consistent-type-imports': 'error',

    // Plugin: eslint-plugin-promise
    'promise/always-return': 'off',
    'promise/catch-or-return': 'off',

    // ESLint plugin vue
    'vue/block-tag-newline': 'error',
    'vue/component-api-style': 'error',
    'vue/component-name-in-template-casing': [
      'error',
      'PascalCase',
      { registeredComponentsOnly: false, ignores: ['/^swiper-/'] },
    ],
    'vue/custom-event-name-casing': [
      'warn',
      'camelCase',
      {
        ignores: ['/^(click):[a-z]+((\d)|([A-Z0-9][a-z0-9]+))*([A-Z])?/'],
      },
    ],
    'vue/define-macros-order': 'error',
    'vue/html-comment-content-newline': 'error',
    'vue/html-comment-content-spacing': 'error',
    'vue/html-comment-indent': 'error',
    'vue/match-component-file-name': 'error',
    'vue/no-child-content': 'error',
    'vue/require-default-prop': 'off',

    'vue/no-duplicate-attr-inheritance': 'error',
    'vue/no-empty-component-block': 'error',
    'vue/no-multiple-objects-in-class': 'error',
    'vue/no-reserved-component-names': 'error',
    'vue/no-template-target-blank': 'error',
    'vue/no-useless-mustaches': 'error',
    'vue/no-useless-v-bind': 'error',
    'vue/no-mutating-props': 'warn',
    'vue/padding-line-between-blocks': 'error',
    'vue/prefer-separate-static-class': 'error',
    'vue/prefer-true-attribute-shorthand': 'off',
    'vue/v-on-function-call': 'error',
    'vue/no-restricted-class': ['error', '/^(p|m)(l|r)-/'],
    'vue/valid-v-slot': [
      'error',
      {
        allowModifiers: true,
      },
    ],

    // -- Extension Rules
    'vue/no-irregular-whitespace': 'error',
    'vue/template-curly-spacing': 'error',

    // -- Sonarlint
    'sonarjs/no-duplicate-string': 'off',
    'sonarjs/no-nested-template-literals': 'off',
    'sonarjs/no-collapsible-if': 'warn',
    'sonarjs/prefer-single-boolean-return': 'off',
    'sonarjs/no-gratuitous-expressions': 'warn',
    'sonarjs/no-duplicated-branches': 'warn',
    'sonarjs/no-identical-functions': 'warn',
    'sonarjs/no-all-duplicated-branches': 'warn',
    'sonarjs/no-useless-catch': 'warn',

    // -- Regexp (complex regex patterns)
    'regexp/no-super-linear-backtracking': 'off',
    'regexp/optimal-quantifier-concatenation': 'off',
    'regexp/no-unused-capturing-group': 'warn',

    // -- Other relaxed rules
    'import/order': 'warn',
    'no-case-declarations': 'warn',
    'no-new': 'off',
    'no-useless-catch': 'warn',
    'prefer-rest-params': 'warn',
    '@typescript-eslint/ban-ts-comment': 'warn',

    // -- Unicorn
    'unicorn/prefer-number-properties': 'off',
    // 'unicorn/filename-case': 'off',
    // 'unicorn/prevent-abbreviations': ['error', {
    //   replacements: {
    //     props: false,
    //   },
    // }],

    // https://github.com/gmullerb/eslint-plugin-regex
    'regex/invalid': [
      'error',
      [
        {
          regex: '@/assets/images',
          replacement: '@images',
          message: "Use '@images' path alias for image imports",
        },
        {
          regex: '@/assets/styles',
          replacement: '@styles',
          message: "Use '@styles' path alias for importing styles from 'src/assets/styles'",
        },
      ],

      // Ignore files
      '\.eslintrc\.cjs',
    ],
  },
  settings: {
    'import/resolver': {
      node: true,
      typescript: {},
    },
  },
}
