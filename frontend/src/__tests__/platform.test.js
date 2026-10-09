import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import en from '../i18n/locales/en.js'
import fr from '../i18n/locales/fr.js'

// Which system Dannify is on, and the words it uses for that system's parts.

let bridge
beforeEach(async () => {
  vi.resetModules()
  vi.stubGlobal('window', { location: { search: '', pathname: '/', hash: '' }, addEventListener: () => {} })
  vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: () => {} })
  vi.stubGlobal('navigator', { platform: 'Win32', userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' })
  bridge = await import('../desktop/bridge.js')
})
afterEach(() => vi.unstubAllGlobals())

describe('detectPlatform()', () => {
  it('reads the newest report the browser gives', () => {
    expect(bridge.detectPlatform({ userAgentData: { platform: 'macOS' }, platform: 'Win32' })).toBe('macos')
    expect(bridge.detectPlatform({ userAgentData: { platform: 'Linux' } })).toBe('linux')
    expect(bridge.detectPlatform({ userAgentData: { platform: 'Windows' } })).toBe('windows')
  })

  it('falls back to the older reports', () => {
    expect(bridge.detectPlatform({ platform: 'MacIntel' })).toBe('macos')
    expect(bridge.detectPlatform({ platform: 'Linux x86_64' })).toBe('linux')
    expect(bridge.detectPlatform({ platform: '', userAgent: 'Mozilla/5.0 (X11; Linux x86_64)' })).toBe('linux')
    expect(bridge.detectPlatform({ platform: '', userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)' })).toBe('macos')
  })

  it('assumes Windows when nothing says otherwise', () => {
    expect(bridge.detectPlatform({})).toBe('windows')
    expect(bridge.detectPlatform(null)).toBe('windows')
  })
})

describe('the platform the shell reports', () => {
  it('starts from the browser and takes the shell’s word over it', () => {
    expect(bridge.platform.value).toBe('windows')
    window.__dannifyWindowState({ platform: 'linux', maximized: true })
    expect(bridge.platform.value).toBe('linux')
    expect(bridge.desktop.platform.value).toBe('linux')
    expect(bridge.desktop.state.maximized).toBe(true)
  })

  it('ignores a platform it does not know', () => {
    window.__dannifyWindowState({ platform: 'beos' })
    expect(bridge.platform.value).toBe('windows')
  })
})

describe('words for each system', () => {
  it('reads the version for this system, and the plain one where there is none', async () => {
    const { platformKey } = await import('../i18n/platform.js')
    const has = (k) => ['settings.autostartMac', 'settings.autostartLinux'].includes(k)
    expect(platformKey('settings.autostart', 'windows', has)).toBe('settings.autostart')
    expect(platformKey('settings.autostart', 'macos', has)).toBe('settings.autostartMac')
    expect(platformKey('settings.autostart', 'linux', has)).toBe('settings.autostartLinux')
    expect(platformKey('settings.theme', 'macos', has)).toBe('settings.theme')
  })

  it('every system version sits beside the one it replaces, in both languages', () => {
    for (const [name, locale] of [['en', en], ['fr', fr]]) {
      const walk = (obj, path) =>
        Object.entries(obj).forEach(([k, v]) => {
          if (v && typeof v === 'object') return walk(v, [...path, k])
          const m = k.match(/^(.+)(Mac|Linux)$/)
          if (m) expect(obj, `${name}: ${[...path, k].join('.')}`).toHaveProperty(m[1])
        })
      walk(locale, [])
    }
  })
})
