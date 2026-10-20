import { afterEach, describe, expect, it, vi } from 'vitest'
import en from '../i18n/locales/en.js'
import fr from '../i18n/locales/fr.js'
import es from '../i18n/locales/es.js'
import pt from '../i18n/locales/pt.js'
import de from '../i18n/locales/de.js'
import sw from '../i18n/locales/sw.js'

/**
 * Recursively collect every dotted key path in an i18n object.
 * e.g. { settings: { title: '…' } }  →  ['settings.title']
 */
function allKeys(obj, prefix = '') {
  return Object.entries(obj).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof value === 'object' && value !== null
      ? allKeys(value, path)
      : [path]
  })
}

const textOf = (locale, key) => key.split('.').reduce((obj, k) => obj[k], locale)
const holes = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
const forms = (s) => s.split(' | ').length

const enKeys = allKeys(en).sort()
const OTHERS = { fr, es, pt, de, sw }
const ALL = { en, ...OTHERS }

describe('i18n locale key consistency', () => {
  for (const [name, locale] of Object.entries(OTHERS)) {
    it(`${name} has exactly the same keys as en`, () => {
      expect(allKeys(locale).sort()).toEqual(enKeys)
    })

    it(`${name} keeps every {placeholder} and plural form of en`, () => {
      for (const key of enKeys) {
        const ours = textOf(en, key)
        const theirs = textOf(locale, key)
        expect(holes(theirs), `${name}: "${key}" placeholders`).toBe(holes(ours))
        expect(forms(theirs), `${name}: "${key}" plural forms`).toBe(forms(ours))
      }
    })
  }

  it('all locales declare a language name', () => {
    for (const locale of Object.values(ALL)) {
      expect(typeof locale.language.name).toBe('string')
      expect(locale.language.name.length).toBeGreaterThan(0)
    }
  })

  it('no locale has an empty translation string', () => {
    for (const [name, locale] of Object.entries(ALL)) {
      for (const key of allKeys(locale)) {
        expect(textOf(locale, key).trim(), `${name}: "${key}" is empty`).not.toBe('')
      }
    }
  })
})

describe('the language Dannify speaks', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  async function startWith(languages) {
    vi.stubGlobal('navigator', { languages, language: languages[0] })
    vi.resetModules()
    return import('../i18n/index.js')
  }

  it('is the computer’s own language at the first start', async () => {
    const i18n = await startWith(['sw-KE', 'en-GB'])
    expect(i18n.languageChoice.value).toBe('auto')
    expect(i18n.currentLocale.value).toBe('sw')
  })

  it('takes a regional variant as its language', async () => {
    expect((await startWith(['pt-BR'])).currentLocale.value).toBe('pt')
    expect((await startWith(['es-419'])).currentLocale.value).toBe('es')
    expect((await startWith(['de_AT'])).currentLocale.value).toBe('de')
  })

  it('goes down the computer’s list to one it speaks, then English', async () => {
    expect((await startWith(['ja-JP', 'fr-CA'])).currentLocale.value).toBe('fr')
    expect((await startWith(['ja-JP', 'ko-KR'])).currentLocale.value).toBe('en')
  })

  it('switches, with every text in the new language', async () => {
    const i18n = await startWith(['en-US'])
    await i18n.localeReady
    expect(i18n.t('settings.language')).toBe('Language')
    await i18n.setLocale('de')
    expect(i18n.currentLocale.value).toBe('de')
    expect(i18n.languageChoice.value).toBe('de')
    expect(i18n.t('settings.language')).toBe('Sprache')
    await i18n.setLocale('auto')
    expect(i18n.languageChoice.value).toBe('auto')
    expect(i18n.currentLocale.value).toBe('en')
  })

  it('ignores a language it does not have', async () => {
    const i18n = await startWith(['en-US'])
    await i18n.setLocale('xx')
    expect(i18n.currentLocale.value).toBe('en')
    expect(i18n.languageChoice.value).toBe('auto')
  })

  it('counts by each language’s own rule', async () => {
    const i18n = await startWith(['en-US'])
    await i18n.setLocale('en')
    expect(i18n.t('nav.artistSongs', { count: 0 })).toBe('0 songs')
    expect(i18n.t('nav.artistSongs', { count: 1 })).toBe('1 song')
    await i18n.setLocale('fr')
    expect(i18n.t('nav.artistSongs', { count: 0 })).toBe(i18n.t('nav.artistSongs', { count: 1 }).replace('1', '0'))
    await i18n.setLocale('pt')
    expect(i18n.t('nav.artistSongs', { count: 0 })).toBe('0 música')
    expect(i18n.t('nav.artistSongs', { count: 2 })).toBe('2 músicas')
    await i18n.setLocale('de')
    expect(i18n.t('nav.artistSongs', { count: 0 })).toBe('0 Songs')
    expect(i18n.t('nav.artistSongs', { count: 1 })).toBe('1 Song')
  })
})
