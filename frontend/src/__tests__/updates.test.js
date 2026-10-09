import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The updates model talks to the backend and the desktop shell; both are
// stood in for here, so what is tested is the state the interface binds to.
const api = {
  checkForUpdate: vi.fn(),
  downloadUpdate: vi.fn(),
  updateStatus: vi.fn(),
  acknowledgeUpdate: vi.fn(() => Promise.resolve({})),
  discardUpdate: vi.fn(() => Promise.resolve({})),
}
const desktop = {
  restart: vi.fn(() => true),
  installUpdate: vi.fn(() => Promise.resolve(true)),
  stageUpdate: vi.fn(),
  clearStagedUpdate: vi.fn(),
  openExternal: vi.fn(),
  platform: { value: 'windows' },
}
const toasts = []

vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/desktop/bridge', () => ({ desktop }))
vi.mock('/src/model/toast', () => ({ toast: (msg, opts) => toasts.push({ msg, opts }) }))
vi.mock('/src/model/dialog', () => ({ alertDialog: vi.fn(), confirmDialog: vi.fn(() => true) }))
vi.mock('/src/i18n', async () => {
  const { ref } = await import('vue')
  return {
    t: (key, args) => (args ? `${key} ${JSON.stringify(args)}` : key),
    currentLocale: ref('en'),
  }
})
vi.mock('/src/model/player', () => ({ usePlayer: () => ({ isPlaying: { value: false } }) }))

// The tests run in Node: no window, no localStorage. The model only starts
// its timers when there is a window, which is what the restart tests need.
function memoryStorage() {
  const items = new Map()
  return {
    getItem: (k) => (items.has(k) ? items.get(k) : null),
    setItem: (k, v) => items.set(k, String(v)),
    removeItem: (k) => items.delete(k),
    clear: () => items.clear(),
  }
}

let updates
beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules()
  vi.stubGlobal('localStorage', memoryStorage())
  vi.stubGlobal('window', { addEventListener: () => {} })
  toasts.length = 0
  for (const fn of Object.values(api)) fn.mockClear()
  for (const fn of Object.values(desktop)) if (typeof fn.mockClear === 'function') fn.mockClear()
  desktop.platform.value = 'windows'
  api.updateStatus.mockResolvedValue({ data: {} })
  api.checkForUpdate.mockResolvedValue({ data: {} })
  updates = (await import('../model/updates.js')).useUpdates()
})
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

const release = {
  available: true,
  version: '4.7.0',
  current: '4.6.2',
  package_url: 'https://github.com/x/package-4.7.0.zip',
  download_url: 'https://github.com/x/Dannify-Setup-4.7.0.exe',
}

describe('check()', () => {
  it('reports an available update', async () => {
    api.checkForUpdate.mockResolvedValue({ data: release })
    await updates.check(true)
    expect(updates.available.value).toBe(true)
    expect(updates.checkedOk.value).toBe(true)
  })

  it('a failed check is not "up to date"', async () => {
    api.checkForUpdate.mockResolvedValue({ data: { error: 'rate_limited' } })
    await updates.check(true)
    expect(updates.available.value).toBe(false)
    expect(updates.checkedOk.value).toBe(false)
    expect(updates.lastError.value).toBe('rate_limited')
  })

  it('keeps a prepared update visible when the same version is found again', async () => {
    api.checkForUpdate.mockResolvedValue({ data: release })
    await updates.check(true)
    api.downloadUpdate.mockResolvedValue({ data: { path: 'staged', kind: 'staged' } })
    expect(await updates.download({ quiet: true })).toBe(true)
    api.checkForUpdate.mockResolvedValue({ data: { ...release, available: false } })
    await updates.check(true)
    expect(updates.available.value).toBe(true)
    expect(updates.ready.value).toBe(true)
  })
})

describe('download() and install()', () => {
  it('a staged update restarts into it', async () => {
    api.checkForUpdate.mockResolvedValue({ data: release })
    await updates.check(true)
    api.downloadUpdate.mockResolvedValue({ data: { path: 'staged', kind: 'staged' } })
    await updates.download()
    await updates.install()
    expect(desktop.restart).toHaveBeenCalledTimes(1)
    expect(desktop.stageUpdate).not.toHaveBeenCalled()
  })

  it('a downloaded installer is handed to the shell for the next exit', async () => {
    api.checkForUpdate.mockResolvedValue({ data: release })
    await updates.check(true)
    api.downloadUpdate.mockResolvedValue({ data: { path: 'C:/d/Dannify-Setup-4.7.0.exe', kind: 'installer' } })
    await updates.download()
    expect(desktop.stageUpdate).toHaveBeenCalledWith('C:/d/Dannify-Setup-4.7.0.exe')
  })

  it('a refused download (a bad signature, say) leaves nothing ready', async () => {
    api.checkForUpdate.mockResolvedValue({ data: release })
    await updates.check(true)
    api.downloadUpdate.mockRejectedValue(new Error('502'))
    expect(await updates.download({ quiet: true })).toBe(false)
    expect(updates.ready.value).toBe(false)
    expect(toasts).toHaveLength(0) // quiet: retried later, not shouted about
  })

  it('skipping a version hides it and drops one already waiting', async () => {
    api.checkForUpdate.mockResolvedValue({ data: release })
    await updates.check(true)
    api.downloadUpdate.mockResolvedValue({ data: { path: 'staged', kind: 'staged' } })
    await updates.download()
    updates.skipVersion()
    expect(updates.available.value).toBe(false)
    expect(api.discardUpdate).toHaveBeenCalled()
  })
})

describe('after a restart', () => {
  it('says once when an update had to be rolled back', async () => {
    api.updateStatus.mockResolvedValue({
      data: { rolled_back: { version: '4.7.0', running: '4.6.2' } },
    })
    await vi.advanceTimersByTimeAsync(2600)
    const shown = toasts.filter((x) => x.msg.startsWith('update.rolledBack'))
    expect(shown).toHaveLength(1)
    expect(shown[0].msg).toContain('4.7.0')
    expect(shown[0].msg).toContain('4.6.2')
    expect(shown[0].opts.tone).toBe('error')
  })

  it('announces the new version once and acknowledges it', async () => {
    api.updateStatus.mockResolvedValue({
      data: { just_updated: { version: '4.7.0', notes: '- Faster' } },
    })
    await vi.advanceTimersByTimeAsync(2600)
    expect(toasts.some((x) => x.msg.startsWith('update.updatedToast'))).toBe(true)
    expect(api.acknowledgeUpdate).toHaveBeenCalledTimes(1)
  })

  it('says nothing when there is nothing to say', async () => {
    await vi.advanceTimersByTimeAsync(2600)
    expect(toasts).toHaveLength(0)
  })
})

describe('a copy that cannot update itself', () => {
  const manual = { ...release, self_update: false, url: 'https://example.com/releases/4.7.0' }

  it('offers the download page instead of downloading', async () => {
    api.checkForUpdate.mockResolvedValue({ data: manual })
    await updates.check(true)
    expect(updates.manual.value).toBe(true)
    expect(await updates.downloadAndInstall()).toBe(false)
    expect(desktop.openExternal).toHaveBeenCalledWith('https://example.com/releases/4.7.0')
    expect(api.downloadUpdate).not.toHaveBeenCalled()
  })

  it('falls back to the product page when the release names no page', async () => {
    api.checkForUpdate.mockResolvedValue({ data: { ...manual, url: '', site_url: 'https://dannify.example' } })
    await updates.check(true)
    await updates.download()
    expect(desktop.openExternal).toHaveBeenCalledWith('https://dannify.example')
  })

  it('never fetches one in the background', async () => {
    api.checkForUpdate.mockResolvedValue({ data: manual })
    await updates.check(true)
    await vi.advanceTimersByTimeAsync(5 * 60_000)
    expect(api.downloadUpdate).not.toHaveBeenCalled()
    expect(desktop.openExternal).not.toHaveBeenCalled()
  })

  it('believes the backend when it turns a download down as manual', async () => {
    api.checkForUpdate.mockResolvedValue({ data: release })
    await updates.check(true)
    api.downloadUpdate.mockRejectedValue({ response: { status: 409, data: { detail: 'manual_update' } } })
    expect(await updates.downloadAndInstall()).toBe(false)
    expect(desktop.openExternal).toHaveBeenCalledTimes(1)
    expect(toasts).toHaveLength(0) // not a failure: there is somewhere to go
    expect(updates.manual.value).toBe(true)
    await updates.downloadAndInstall()
    expect(api.downloadUpdate).toHaveBeenCalledTimes(1)
    expect(desktop.openExternal).toHaveBeenCalledTimes(2)
  })

  it('a background attempt turned down that way stops trying, quietly', async () => {
    api.checkForUpdate.mockResolvedValue({ data: release })
    api.downloadUpdate.mockRejectedValue({ response: { status: 409, data: { detail: 'manual_update' } } })
    await updates.check(true)
    await vi.advanceTimersByTimeAsync(30_000 + 10 * 60_000)
    expect(api.downloadUpdate).toHaveBeenCalledTimes(1)
    expect(desktop.openExternal).not.toHaveBeenCalled()
    expect(updates.manual.value).toBe(true)
  })
})

describe('installing on each system', () => {
  async function prepared(data) {
    api.checkForUpdate.mockResolvedValue({ data: { ...release, ...data } })
    await updates.check(true)
    api.downloadUpdate.mockResolvedValue({ data: { path: '/tmp/update', kind: 'installer' } })
    expect(await updates.download({ quiet: true })).toBe(true)
    // The stand-in outlives each test's fresh copy of the model.
    const confirm = (await import('/src/model/dialog')).confirmDialog
    confirm.mockClear()
    return confirm
  }

  it('Windows restarts into it without asking, as before', async () => {
    const confirm = await prepared({})
    await updates.downloadAndInstall()
    expect(confirm).not.toHaveBeenCalled()
    expect(desktop.installUpdate).toHaveBeenCalledWith('/tmp/update')
  })

  it('Linux says first that it will ask for the password', async () => {
    desktop.platform.value = 'linux'
    const confirm = await prepared({ installer_kind: 'installer-linux-deb-amd64', self_update: true })
    await updates.downloadAndInstall()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(confirm.mock.calls[0][0].message).toBe('update.installMessageLinux')
    expect(desktop.installUpdate).toHaveBeenCalledWith('/tmp/update')
  })

  it('macOS says it will reopen as the new version', async () => {
    desktop.platform.value = 'macos'
    const confirm = await prepared({ installer_kind: 'app-macos-zip-arm64', self_update: true })
    await updates.downloadAndInstall()
    expect(confirm.mock.calls[0][0].message).toBe('update.installMessageMac')
  })

  it('the release kind wins over a guess about the system', async () => {
    const confirm = await prepared({ installer_kind: 'installer-linux-deb-arm64', self_update: true })
    await updates.downloadAndInstall()
    expect(confirm.mock.calls[0][0].message).toBe('update.installMessageLinux')
  })

  it('nothing is installed when the question is turned down', async () => {
    desktop.platform.value = 'linux'
    const confirm = await prepared({ installer_kind: 'installer-linux-deb-amd64', self_update: true })
    confirm.mockResolvedValueOnce(false)
    expect(await updates.downloadAndInstall()).toBe(false)
    expect(desktop.installUpdate).not.toHaveBeenCalled()
  })
})
