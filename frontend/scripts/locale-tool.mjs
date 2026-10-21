// Translations, made and checked.
//
//   node scripts/locale-tool.mjs flat en > en.json
//       Every text in a language, flat: { "settings.title": "Settings", ... }.
//   node scripts/locale-tool.mjs build sw sw.json
//       src/i18n/locales/sw.js from a flat file, in the order and shape of
//       en.js, so the two can be read side by side.
//   node scripts/locale-tool.mjs check sw
//       Every text of en.js is there, none is empty, and each keeps the
//       same {placeholders} and the same number of " | " plural forms.

import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const LOCALES = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'i18n', 'locales')

async function load(code) {
  const mod = await import(pathToFileURL(join(LOCALES, `${code}.js`)).href)
  if (code !== 'en') return mod.default
  // English is in two files (see en-more.js): read whole.
  const more = await import(pathToFileURL(join(LOCALES, 'en-more.js')).href)
  return { ...mod.default, ...more.default }
}

function flatten(obj, prefix = '', out = {}) {
  for (const [key, value] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') out[path] = value
    else flatten(value, path, out)
  }
  return out
}

const quote = (s) => `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n')}'`
const ident = (k) => (/^[A-Za-z_$][\w$]*$/.test(k) ? k : quote(k))

/** The shape of *model* (en.js), with *flat*'s texts in it. */
function render(model, flat, prefix = '', depth = 1) {
  const pad = '  '.repeat(depth)
  const lines = []
  for (const [key, value] of Object.entries(model)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') {
      const text = flat[path]
      if (typeof text !== 'string') throw new Error(`missing: ${path}`)
      lines.push(`${pad}${ident(key)}: ${quote(text)},`)
    } else {
      lines.push(`${pad}${ident(key)}: {`)
      lines.push(...render(value, flat, path, depth + 1))
      lines.push(`${pad}},`)
    }
  }
  return lines
}

const holes = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
const forms = (s) => s.split(' | ').length

async function check(code) {
  const en = flatten(await load('en'))
  const other = flatten(await load(code))
  const problems = []
  for (const [key, text] of Object.entries(en)) {
    const theirs = other[key]
    if (typeof theirs !== 'string') problems.push(`missing ${key}`)
    else if (!theirs.trim()) problems.push(`empty ${key}`)
    else {
      if (holes(theirs) !== holes(text)) problems.push(`placeholders ${key}: ${holes(text)} / ${holes(theirs)}`)
      if (forms(theirs) !== forms(text)) problems.push(`plural forms ${key}: ${forms(text)} / ${forms(theirs)}`)
    }
  }
  for (const key of Object.keys(other)) if (!(key in en)) problems.push(`extra ${key}`)
  return problems
}

const [command, code, file] = process.argv.slice(2)
if (command === 'flat') {
  process.stdout.write(JSON.stringify(flatten(await load(code || 'en')), null, 1) + '\n')
} else if (command === 'build') {
  const flat = JSON.parse(readFileSync(file, 'utf8'))
  const model = await load('en')
  const body = render(model, flat).join('\n')
  writeFileSync(join(LOCALES, `${code}.js`), `export default {\n${body}\n}\n`, 'utf8')
  const problems = await check(code)
  console.log(problems.length ? problems.join('\n') : `${code}: built, every text in place`)
  process.exitCode = problems.length ? 1 : 0
} else if (command === 'check') {
  const problems = await check(code)
  console.log(problems.length ? problems.join('\n') : `${code}: every text in place`)
  process.exitCode = problems.length ? 1 : 0
} else {
  console.log('usage: locale-tool.mjs flat <code> | build <code> <flat.json> | check <code>')
  process.exitCode = 2
}
