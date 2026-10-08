// Raw-palette guard — deliberately a SEPARATE config from eslint.config.js.
//
// `frontend/src` currently carries ~5,433 raw Tailwind palette utilities across
// 182 files. Putting this rule in the main config at `error` would fail
// `npm run lint:ci` on the first commit; putting it there at `warn` would blow
// through the `--max-warnings 242` ceiling just as fast. So it lives here and
// runs only via `npm run lint:palette`, which reports findings on CHANGED LINES
// only (scripts/lint-changed-lines.mjs).
//
// Pre-existing violations are therefore exempt, while every line a PR adds or
// edits is covered — including inside the 182 files. A file-wide `ignores` list
// was considered and rejected: it would also exempt NEW violations added to
// those files, which is exactly the regression this exists to prevent.
//
// Phase 2 is done when `npx eslint . --config eslint.palette.config.js` is
// clean repo-wide; at that point this moves into the main config and the
// changed-line scoping goes away.
import { defineConfig, globalIgnores } from 'eslint/config'

const PALETTE = [
  'slate', 'gray', 'zinc', 'neutral', 'stone',
  'red', 'orange', 'amber', 'yellow', 'lime', 'green', 'emerald', 'teal',
  'cyan', 'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose',
].join('|')

const PROPERTY = [
  'bg', 'text', 'border', 'ring', 'from', 'via', 'to',
  'divide', 'outline', 'decoration', 'accent', 'caret', 'placeholder', 'shadow', 'fill', 'stroke',
].join('|')

// e.g. bg-blue-600, text-gray-400, border-slate-700/50, hover:bg-red-500
// Exported so scripts/lint-changed-lines.mjs can locate the exact match inside
// a reported node: ESLint reports a multi-line TemplateElement at its START
// line, not at the line the offending class actually sits on.
export const RAW_PALETTE = String.raw`\b(${PROPERTY})-(${PALETTE})-(50|100|200|300|400|500|600|700|800|900|950)\b`

const MESSAGE =
  'Raw Tailwind palette utility. Use a Workbench token utility instead — ' +
  'bg-paper / bg-paper-sunk for surfaces, text-ink / text-ink-2 / text-ink-3 for text, ' +
  'border-hair for rules, bg-accent + text-accent-ink for the primary action, and ' +
  'text-status-amber / green / red (with their -tint backgrounds) for status. ' +
  'These are defined in src/index.css and follow the theme; raw palette colours do not.'

export default defineConfig([
  globalIgnores([
    'dist',
    'storybook-static',
    // Tests legitimately assert on literal class strings.
    '**/*.{test,spec}.{js,jsx}',
    'src/test/**',
  ]),
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      'no-restricted-syntax': ['error',
        // plain strings: className="bg-blue-600", and class maps like
        // VARIANT_CLASSES = { primary: "bg-blue-600 ..." }
        { selector: `Literal[value=/${RAW_PALETTE}/]`, message: MESSAGE },
        // template literals: className={`bg-blue-600 ${x}`}
        { selector: `TemplateElement[value.raw=/${RAW_PALETTE}/]`, message: MESSAGE },
      ],
    },
  },
])
