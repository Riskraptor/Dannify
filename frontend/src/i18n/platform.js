import { t } from '/src/i18n'
import { platform } from '/src/desktop/bridge'

// Sentences that name a part of the system (its settings, the bin, the tray,
// the file manager) have a version for each system they differ on, beside
// the Windows one: `autostart`, `autostartMac`, `autostartLinux`. A key with
// no version for this system reads the same everywhere.

const SUFFIX = { windows: '', macos: 'Mac', linux: 'Linux' }

/** The key to read for *key* on *system*, when the locale has one. */
export function platformKey(key, system, has = (k) => t(k) !== k) {
  const suffix = SUFFIX[system] || ''
  return suffix && has(key + suffix) ? key + suffix : key
}

/** t(), in the words of the system this runs on. */
export function tp(key, params) {
  return t(platformKey(key, platform.value), params)
}
