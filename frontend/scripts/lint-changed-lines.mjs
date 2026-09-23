#!/usr/bin/env node
/**
 * Run the raw-palette guard against CHANGED LINES only.
 *
 * Pre-existing violations are exempt; any line a branch adds or edits is not —
 * including inside the 182 files that already violate the rule. That is the
 * whole point: a file-wide exemption would also wave through NEW violations in
 * those files, which is the regression the guard exists to prevent.
 *
 * Locating a finding is not as simple as trusting message.line. ESLint reports
 * a multi-line TemplateElement at the line the element STARTS on, which is not
 * the line the offending class sits on:
 *
 *     const classes = `          <- 2
 *       rounded-lg px-3           <- 4
 *       ${active ? 'x' : ''}      <- 5   ESLint reports HERE
 *       bg-blue-600               <- 6   the violation is HERE
 *     `
 *
 * Filtering on message.line alone would miss a class added on line 6. Widening
 * to the node's whole span would instead flag a pre-existing violation whenever
 * an unrelated line of the same template is edited. So we re-scan the reported
 * node's own source text and resolve each match to its true line.
 *
 * Base ref resolution, in order: argv[2], $PALETTE_BASE, origin/main.
 * Exits 1 if any finding lands on a changed line, 0 otherwise.
 */
import { execFileSync } from 'node:child_process'
import { ESLint } from 'eslint'
import fs from 'node:fs'
import path from 'node:path'
import { RAW_PALETTE } from '../eslint.palette.config.js'

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

// absolute offset of the start of each 1-based line
function lineOffsets(src) {
  const offs = [0, 0]
  for (let i = 0; i < src.length; i++) if (src.charCodeAt(i) === 10) offs.push(i + 1)
  return offs
}

// The true line(s) of the offending class text inside a reported node.
function offendingLines(src, offs, m) {
  const start = offs[m.line] + (m.column - 1)
  const endLine = m.endLine ?? m.line
  const endCol = m.endColumn ?? m.column + 1
  const end = offs[endLine] + (endCol - 1)
  const text = src.slice(start, end)
  const re = new RegExp(RAW_PALETTE, 'g')
  const hits = []
  let match
  while ((match = re.exec(text)) !== null) {
    const abs = start + match.index
    let line = m.line
    while (line + 1 < offs.length && offs[line + 1] <= abs) line++
    hits.push(line)
    if (match.index === re.lastIndex) re.lastIndex++
  }
  return hits.length ? [...new Set(hits)] : [m.line]
}

let found = 0
for (const res of results) {
  const rel = path.relative(process.cwd(), res.filePath).split(path.sep).join('/')
  const lines = changed.get(rel)
  if (!lines) continue
  const src = fs.readFileSync(res.filePath, 'utf8')
  const offs = lineOffsets(src)
  for (const m of res.messages) {
    for (const line of offendingLines(src, offs, m)) {
      if (!lines.has(line)) continue // pre-existing: exempt
      found++
      console.error(`${rel}:${line}  ${m.message}`)
    }
  }
}

if (found > 0) {
  console.error(`\npalette-guard: ${found} raw palette utilit${found === 1 ? 'y' : 'ies'} on changed lines.`)
  process.exit(1)
}
console.log(`palette-guard: clean across ${files.length} changed file(s).`)
