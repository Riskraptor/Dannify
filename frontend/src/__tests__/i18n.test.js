import { describe, expect, it } from 'vitest'
import en from '../i18n/locales/en.js'
import fr from '../i18n/locales/fr.js'

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

const enKeys = allKeys(en).sort()

describe('i18n locale key consistency', () => {
  it('fr has exactly the same keys as en', () => {
    expect(allKeys(fr).sort()).toEqual(enKeys)
  })

  it('all locales have the organize-by-artist setting keys', () => {
    for (const locale of [en, fr]) {
      expect(locale.settings).toHaveProperty('organizationSection')
      expect(locale.settings).toHaveProperty('organizeByArtist')
      expect(locale.settings).toHaveProperty('organizeByArtistHint')
    }
  })

  it('all locales declare a language name', () => {
    for (const locale of [en, fr]) {
      expect(typeof locale.language.name).toBe('string')
      expect(locale.language.name.length).toBeGreaterThan(0)
    }
  })

  it('no locale has an empty translation string', () => {
    for (const [name, locale] of [
      ['en', en],
      ['fr', fr],
    ]) {
      for (const key of allKeys(locale)) {
        const value = key.split('.').reduce((obj, k) => obj[k], locale)
        expect(value, `${name}: "${key}" is empty`).not.toBe('')
      }
    }
  })

  it('all locales have the same number of keys', () => {
    expect(allKeys(fr).length).toBe(enKeys.length)
  })
})
