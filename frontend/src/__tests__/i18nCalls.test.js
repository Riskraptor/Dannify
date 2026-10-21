import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import enCore from '../i18n/locales/en.js'
import enMore from '../i18n/locales/en-more.js'

// English is in two files (i18n/locales/en-more.js): whole here.
const en = { ...enCore, ...enMore }

// Every t('key', { ... }) in the app gives each {placeholder} its English text
// has. One given under another name ({ n } for "{count} s") showed "{count} s"
// on screen in the sound panel.

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')
// Texts handed on raw, their placeholders filled in elsewhere.
const RAW = new Set(['occasion.national.title'])

function text(key) {
  return key.split('.').reduce((o, k) => (o && typeof o === 'object' ? o[k] : undefined), en)
}

function files(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name !== '__tests__' && name !== 'locales') files(p, out)
    } else if (/\.(vue|js)$/.test(name)) out.push(p)
  }
  return out
}

const CALL = /\btp?\(\s*['`]([\w.]+)['`]\s*(?:,\s*\{([^{}]*)\})?\s*\)/g

describe('translations as the app asks for them', () => {
  const problems = []
  for (const file of files(SRC)) {
    const where = relative(SRC, file)
    for (const m of readFileSync(file, 'utf8').matchAll(CALL)) {
      const key = m[1]
      const value = text(key)
      if (typeof value !== 'string') {
        problems.push(`${where}: no text for ${key}`)
        continue
      }
      const need = [...new Set([...value.matchAll(/\{(\w+)\}/g)].map((x) => x[1]))]
      if (!need.length || RAW.has(key)) continue
      const given = new Set([...(m[2] || '').matchAll(/(?:^|,)\s*(\w+)\s*(?=[:,]|$)/g)].map((x) => x[1]))
      const lacking = need.filter((n) => !given.has(n))
      if (lacking.length) problems.push(`${where}: ${key} lacks {${lacking.join('}, {')}}`)
    }
  }

  it('every text asked for exists, with every placeholder given', () => {
    expect(problems).toEqual([])
  })
})
