#!/usr/bin/env node
/**
 * Run the raw-palette guard against CHANGED LINES only.
 *
 * Pre-existing violations are exempt; any line a branch adds or edits is not —
 * including inside the 182 files that already violate the rule. That is the
 * whole point: a file-wide exemption would also wave through NEW violations in
 * those files, which is the regression the guard exists to prevent.
 *
 * Base ref resolution, in order: argv[2], $PALETTE_BASE, origin/main.
 * Exits 1 if any finding lands on a changed line, 0 otherwise.
 */
import { execFileSync } from 'node:child_process'
import { ESLint } from 'eslint'
import path from 'node:path'

const base = process.argv[2] || process.env.PALETTE_BASE || 'origin/main'
const git = (...args) => execFileSync('git', args, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })

try {
  git('rev-parse', '--verify', `${base}^{commit}`)
} catch {
  console.error(`palette-guard: cannot resolve base ref "${base}".`)
  console.error('In CI make sure the base commit is fetched (actions/checkout fetch-depth: 0).')
  process.exit(2)
}

// Added/changed line numbers per file, from a zero-context diff.
const diff = git('diff', '--unified=0', '--diff-filter=ACMR', `${base}...HEAD`, '--', '*.js', '*.jsx')
const changed = new Map()
let current = null
for (const line of diff.split('\n')) {
  const file = /^\+\+\+ b\/(.+)$/.exec(line)
  if (file) {
    current = file[1].startsWith('frontend/') ? file[1].slice('frontend/'.length) : null
    continue
  }
  if (!current) continue
  const hunk = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/.exec(line)
  if (!hunk) continue
  const start = Number(hunk[1])
  const count = hunk[2] === undefined ? 1 : Number(hunk[2])
  if (count === 0) continue // pure deletion
  if (!changed.has(current)) changed.set(current, new Set())
  const set = changed.get(current)
  for (let n = start; n < start + count; n++) set.add(n)
}

const files = [...changed.keys()].filter(f => f.startsWith('src/'))
if (files.length === 0) {
  console.log('palette-guard: no changed frontend source lines; nothing to check.')
  process.exit(0)
}

const eslint = new ESLint({ overrideConfigFile: 'eslint.palette.config.js' })
const results = await eslint.lintFiles(files)

let found = 0
for (const res of results) {
  const rel = path.relative(process.cwd(), res.filePath).split(path.sep).join('/')
  const lines = changed.get(rel)
  if (!lines) continue
  for (const m of res.messages) {
    if (!lines.has(m.line)) continue // pre-existing: exempt
    found++
    console.error(`${rel}:${m.line}:${m.column}  ${m.message}`)
  }
}

if (found > 0) {
  console.error(`\npalette-guard: ${found} raw palette utilit${found === 1 ? 'y' : 'ies'} on changed lines.`)
  process.exit(1)
}
console.log(`palette-guard: clean across ${files.length} changed file(s).`)
