import { fileURLToPath } from 'node:url';

import { includeIgnoreFile } from '@eslint/compat';
import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import importPlugin from 'eslint-plugin-import';
import svelte from 'eslint-plugin-svelte';
import globals from 'globals';
import ts from 'typescript-eslint';

import svelteConfig from './svelte.config.js';

const gitignorePath = fileURLToPath(new URL('./.gitignore', import.meta.url));

export default ts.config(
	includeIgnoreFile(gitignorePath),
	js.configs.recommended,
	...ts.configs.recommended,
	...svelte.configs.recommended,
	prettier,
	...svelte.configs.prettier,
	{
		languageOptions: {
			globals: { ...globals.browser, ...globals.node }
		},
		plugins: {
			import: importPlugin
		},
		settings: {
			// Use the built-in node resolver (no extra dependency). Path aliases
			// like $lib/$app are categorized via pathGroups below, and unresolved
			// imports are left to TypeScript (import/no-unresolved is off).
			'import/resolver': {
				node: {
					extensions: ['.js', '.ts', '.svelte']
				}
			}
		},
		rules: {
			// Disable conflicting rules
			'no-undef': 'off',

			// Console and debugging
			'no-console': ['warn', { allow: ['warn', 'error'] }],
			'no-debugger': 'warn',

			// Variable declarations
			'prefer-const': 'error',
			'no-var': 'error',

			// Equality and comparisons
			'eqeqeq': ['error', 'always', { null: 'ignore' }],

			// Code style
			'curly': ['error', 'all'],
			'arrow-body-style': ['error', 'as-needed'],
			'object-shorthand': ['error', 'always'],
			'prefer-template': 'error',
			'prefer-arrow-callback': 'error',

			// Spacing and whitespace
			'no-multiple-empty-lines': ['error', { max: 1, maxEOF: 0, maxBOF: 0 }],
			'padding-line-between-statements': [
				'error',
				{ blankLine: 'always', prev: '*', next: 'return' },
				{ blankLine: 'always', prev: ['const', 'let', 'var'], next: '*' },
				{
					blankLine: 'any',
					prev: ['const', 'let', 'var'],
					next: ['const', 'let', 'var']
				},
				{ blankLine: 'always', prev: 'directive', next: '*' },
				{ blankLine: 'any', prev: 'directive', next: 'directive' },
				{ blankLine: 'always', prev: 'import', next: '*' },
				{ blankLine: 'any', prev: 'import', next: 'import' }
			],

			// Comments - must have space after //
			'spaced-comment': [
				'error',
				'always',
				{
					line: {
						markers: ['/'],
						exceptions: ['-', '+', '*']
					},
					block: {
						markers: ['!'],
						exceptions: ['*'],
						balanced: true
					}
				}
			],

			// TypeScript specific
			'@typescript-eslint/explicit-function-return-type': 'off',
			'@typescript-eslint/explicit-module-boundary-types': 'off',
			'@typescript-eslint/no-explicit-any': 'warn',
			'@typescript-eslint/no-unused-vars': [
				'error',
				{
					argsIgnorePattern: '^_',
					varsIgnorePattern: '^_',
					caughtErrorsIgnorePattern: '^_'
				}
			],
			'@typescript-eslint/consistent-type-imports': [
				'error',
				{
					prefer: 'type-imports',
					fixStyle: 'separate-type-imports'
				}
			],

			// Naming conventions
			'@typescript-eslint/naming-convention': [
				'error',
				// Variables: camelCase, UPPER_CASE for constants, PascalCase for components
				{
					selector: 'variable',
					format: ['camelCase', 'UPPER_CASE', 'PascalCase'],
					leadingUnderscore: 'allow'
				},
				// Functions: camelCase or PascalCase (for components)
				{
					selector: 'function',
					format: ['camelCase', 'PascalCase']
				},
				// Types, Interfaces, Classes: PascalCase
				{
					selector: 'typeLike',
					format: ['PascalCase']
				},
				// Interfaces should NOT have "I" prefix
				{
					selector: 'interface',
					format: ['PascalCase'],
					custom: {
						regex: '^I[A-Z]',
						match: false
					}
				},
				// Enums should be PascalCase
				{
					selector: 'enum',
					format: ['PascalCase']
				},
				// Enum members should be UPPER_CASE
				{
					selector: 'enumMember',
					format: ['UPPER_CASE']
				}
			],

			// Import sorting and organization
			'import/order': [
				'error',
				{
					groups: [
						'builtin', // Node.js built-in modules
						'external', // npm packages
						'internal', // Internal/aliased imports
						['parent', 'sibling'], // Relative imports
						'index', // Index imports
						'object',
						'type' // Type imports
					],
					pathGroups: [
						{
							pattern: '$lib/**',
							group: 'internal'
						},
						{
							pattern: '$app/**',
							group: 'internal'
						},
						{
							pattern: '$env/**',
							group: 'internal'
						}
					],
					pathGroupsExcludedImportTypes: ['builtin'],
					'newlines-between': 'always',
					alphabetize: {
						order: 'asc',
						caseInsensitive: true
					},
					warnOnUnassignedImports: true
				}
			],
			'import/no-duplicates': ['error', { 'prefer-inline': false }],
			'import/newline-after-import': ['error', { count: 1 }],
			'import/first': 'error',
			'import/no-unresolved': 'off', // TypeScript handles this

			// Additional best practices
			'no-lonely-if': 'error',
			'no-useless-return': 'error',
			'prefer-destructuring': [
				'error',
				{
					array: false,
					object: true
				}
			]
		}
	},
	{
		files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
		languageOptions: {
			parserOptions: {
				projectService: true,
				extraFileExtensions: ['.svelte'],
				parser: ts.parser,
				svelteConfig
			}
		},
		rules: {
			// Svelte 5 runes ($props/$state/$derived) require `let`, so the base
			// prefer-const wrongly flags them. Use the rune-aware Svelte version.
			'prefer-const': 'off',
			'svelte/prefer-const': 'error'
		}
	},
	{
		// Generated shadcn-svelte primitives: they accept arbitrary `href` props,
		// so the SvelteKit navigation-resolution rule is a false positive here.
		files: ['**/lib/components/ui/**'],
		rules: {
			'svelte/no-navigation-without-resolve': 'off'
		}
	},
	{
		// Server-side logger is the one place console output is intentional.
		files: ['**/lib/server/**'],
		rules: {
			'no-console': 'off'
		}
	}
);
