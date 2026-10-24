// The interface's weight, checked after every build so it can only go one
// way without somebody deciding it should. Run after `vite build`:
//
//   node scripts/size-budget.mjs
//
// The main script is what every start reads before anything is drawn;
// everything that can wait is split off into files fetched when needed
// (pages, dialogs, other languages). Raise a limit on purpose, never by
// accident.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { gzipSync } from 'node:zlib'

const BUDGET = {
  // KB, minified.
  mainScript: 620,
  // KB, compressed as it travels.
  mainScriptGzip: 210,
  // KB: every script and style together, compressed. Every language is
  // counted though one is ever read; raised from 520 for the guided tour and
  // the special days' pages, which say everything in all six.
  totalGzip: 560,
}

const assets = join(import.meta.dirname, '..', 'dist', 'assets')
const files = readdirSync(assets).filter((f) => /\.(js|css)$/.test(f))
const main = files.filter((f) => /^index-.*\.js$/.test(f))
if (main.length !== 1) {
  console.error(`expected one main script in dist/assets, found ${main.length}: run vite build first`)
  process.exit(1)
}

const kb = (n) => Math.round((n / 1024) * 10) / 10
const mainBytes = readFileSync(join(assets, main[0]))
const measured = {
  mainScript: kb(statSync(join(assets, main[0])).size),
  mainScriptGzip: kb(gzipSync(mainBytes, { level: 9 }).length),
  totalGzip: kb(files.reduce((sum, f) => sum + gzipSync(readFileSync(join(assets, f)), { level: 9 }).length, 0)),
}

let over = false
for (const [name, limit] of Object.entries(BUDGET)) {
  const value = measured[name]
  const ok = value <= limit
  over ||= !ok
  console.log(`${ok ? 'ok  ' : 'OVER'} ${name.padEnd(15)} ${String(value).padStart(7)} KB  (budget ${limit} KB)`)
}
if (over) {
  console.error('\nThe interface is heavier than its budget. Split off what can wait, or raise the budget on purpose.')
  process.exit(1)
}
