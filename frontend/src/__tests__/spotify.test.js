import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'

// Spotify in the window (model/spotify.js): opening Spotify's page, noticing
// the person come back signed in, saying why something failed, and following
// a copy into Dannify to its end.

const api = vi.hoisted(() => ({
  spotifyStatus: null,
  spotifyConnect: null,
  spotifyDisconnect: null,
  spotifySetApp: null,
  spotifyPlaylists: null,
  spotifyImport: null,
  spotifyImportStatus: null,
}))
const opened = vi.hoisted(() => [])
const toasts = vi.hoisted(() => [])
const loads = vi.hoisted(() => ({ count: 0 }))

vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/i18n', () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k) }))
vi.mock('/src/desktop/bridge', () => ({
  desktop: { isDesktop: true, openExternal: (url) => opened.push(url) && Promise.resolve() },
}))
vi.mock('/src/model/toast', () => ({ toast: (text, opts) => toasts.push({ text, opts }) }))
vi.mock('/src/model/tracks', () => ({ playRows: () => {} }))
vi.mock('/src/model/playlists', () => ({
  usePlaylists: () => ({ load: () => (loads.count++, Promise.resolve()) }),
}))

let S
let status

beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules()
  opened.length = 0
  toasts.length = 0
  loads.count = 0
  globalThis.window = globalThis.window || {}
  window.addEventListener = window.addEventListener || (() => {})
  window.removeEventListener = window.removeEventListener || (() => {})
  window.dispatchEvent = window.dispatchEvent || (() => {})
  status = { configured: true, own_app: false, connected: false, signing_in: false, user: {}, error: '' }
  api.spotifyStatus = vi.fn(() => Promise.resolve({ data: { ...status } }))
  api.spotifyConnect = vi.fn(() => {
    status.signing_in = true
    return Promise.resolve({ data: { url: 'https://accounts.spotify.com/authorize?x=1' } })
  })
  api.spotifyDisconnect = vi.fn(() => Promise.resolve({ data: { ...status, connected: false } }))
  api.spotifySetApp = vi.fn((id) => Promise.resolve({ data: { ...status, own_app: !!id } }))
  api.spotifyPlaylists = vi.fn(() => Promise.resolve({ data: { playlists: [{ id: 'p1', name: 'Mine' }] } }))
  S = await import('/src/model/spotify')
  // The model's own first look, a moment after the window is up.
  await vi.advanceTimersByTimeAsync(3000)
  api.spotifyStatus.mockClear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Spotify in the window', () => {
  it('says what each reason means', () => {
    expect(S.errorKey('not_allowed')).toBe('spotify.errorNotAllowed')
    expect(S.errorKey('expired')).toBe('spotify.errorExpired')
    expect(S.errorKey('busy')).toBe('spotify.errorBusy')
    expect(S.errorKey('something new')).toBe('spotify.errorFailed')
    expect(S.reasonOf({ response: { data: { detail: 'not_configured' } } })).toBe('not_configured')
    expect(S.reasonOf({ response: { data: {} } })).toBe('failed')
    expect(S.reasonOf(new Error('network'))).toBe('unreachable')
  })

  it('opens Spotify’s page, and notices the person come back signed in', async () => {
    const sp = S.useSpotify()
    expect(await S.connectSpotify()).toBe(true)
    expect(opened).toEqual(['https://accounts.spotify.com/authorize?x=1'])
    expect(sp.status.value.signing_in).toBe(true)
    status.connected = true
    status.signing_in = false
    status.user = { name: 'Dani M' }
    await vi.advanceTimersByTimeAsync(1600)
    expect(sp.connected.value).toBe(true)
    expect(toasts.some((x) => x.text.startsWith('spotify.connectedToast'))).toBe(true)
    // Done watching: no more questions asked.
    const asked = api.spotifyStatus.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.spotifyStatus.mock.calls.length).toBe(asked)
  })

  it('a sign-in that ended badly says so, and saying no is not an error', async () => {
    await S.connectSpotify()
    status.signing_in = false
    status.error = 'not_allowed'
    await vi.advanceTimersByTimeAsync(1600)
    expect(toasts.at(-1).text).toBe('spotify.errorNotAllowed')
    toasts.length = 0
    status.error = 'denied'
    await S.connectSpotify()
    status.signing_in = false
    await vi.advanceTimersByTimeAsync(1600)
    expect(toasts).toEqual([])
  })

  it('without a Spotify app, connecting explains instead of opening anything', async () => {
    api.spotifyConnect = vi.fn(() => Promise.reject({ response: { data: { detail: 'not_configured' } } }))
    expect(await S.connectSpotify()).toBe(false)
    expect(opened).toEqual([])
    expect(toasts.at(-1).text).toBe('spotify.errorNotConfigured')
  })

  it('a copy is followed to its end and its playlist shown', async () => {
    api.spotifyImport = vi.fn(() => Promise.resolve({ data: { job: 'j1' } }))
    const answers = [
      { total: 3, done: 1, matched: 1, finished: false },
      { total: 3, done: 3, matched: 2, finished: true, playlist: 'pl9', name: 'Road trip', error: '' },
    ]
    api.spotifyImportStatus = vi.fn(() => Promise.resolve({ data: answers.shift() }))
    const seen = []
    const done = S.importSpotify('playlist', 'p1', 'Road trip', (now) => seen.push(now.done))
    await vi.advanceTimersByTimeAsync(2000)
    expect(await done).toBe('pl9')
    expect(seen).toEqual([1, 3])
    expect(loads.count).toBe(1)
    expect(toasts.at(-1).text).toContain('spotify.importedSome')
  })

  it('a copy with nothing found makes nothing and says so', async () => {
    api.spotifyImport = vi.fn(() => Promise.resolve({ data: { job: 'j2' } }))
    api.spotifyImportStatus = vi.fn(() =>
      Promise.resolve({ data: { total: 2, done: 2, matched: 0, finished: true, playlist: '', error: 'nothing_matched' } })
    )
    const done = S.importSpotify('liked')
    await vi.advanceTimersByTimeAsync(1000)
    expect(await done).toBe('')
    expect(toasts.at(-1).text).toBe('spotify.importNothing')
  })

  it('the playlists are asked for only once signed in', async () => {
    expect(await S.loadSpotifyPlaylists()).toEqual([])
    expect(api.spotifyPlaylists).not.toHaveBeenCalled()
    status.connected = true
    await S.refreshSpotify()
    await S.loadSpotifyPlaylists()
    expect(S.spotifyPlaylists.value).toEqual([{ id: 'p1', name: 'Mine' }])
  })
})
