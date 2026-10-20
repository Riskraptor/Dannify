import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { ref } from 'vue'

// YouTube Music's history into Your stats (model/ytmSync.js): only for
// someone signed in who keeps a history and has not turned it off; the
// pages showing the history read it again only when something came in.

const api = vi.hoisted(() => ({ syncYouTubeHistory: null, youTubeHistoryStatus: null }))
const state = vi.hoisted(() => ({ signedIn: null, keeping: null, epoch: null }))

vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/model/account', () => ({ useAccount: () => ({ signedIn: state.signedIn }) }))
vi.mock('/src/model/listens', () => ({
  get keeping() {
    return state.keeping
  },
  get listensEpoch() {
    return state.epoch
  },
}))

const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
}

let S
beforeEach(async () => {
  store.clear()
  vi.resetModules()
  state.signedIn = ref(true)
  state.keeping = ref(true)
  state.epoch = ref(0)
  api.syncYouTubeHistory = vi.fn(() => Promise.resolve({ data: { brought: 3, checked: 5, total: 3, last: 1792000000 } }))
  api.youTubeHistoryStatus = vi.fn(() => Promise.resolve({ data: { last: 0, total: 0 } }))
  S = await import('/src/model/ytmSync')
})

afterEach(() => vi.useRealTimers())

describe('bringing in YouTube Music’s history', () => {
  it('brings it in, and has the history read again', async () => {
    const got = await S.syncFromYouTube()
    expect(got.brought).toBe(3)
    expect(state.epoch.value).toBe(1)
    expect(S.ytmStatus.value).toEqual({ last: 1792000000, total: 3 })
  })

  it('nothing new: the history is left as it is', async () => {
    api.syncYouTubeHistory.mockResolvedValue({ data: { brought: 0, checked: 5, total: 3, last: 1792000100 } })
    await S.syncFromYouTube()
    expect(state.epoch.value).toBe(0)
  })

  it('not for someone signed out, keeping no history, or who turned it off', async () => {
    state.signedIn.value = false
    expect(await S.syncFromYouTube()).toBe(null)
    state.signedIn.value = true
    state.keeping.value = false
    expect(await S.syncFromYouTube()).toBe(null)
    state.keeping.value = true
    S.setYtmSync(false)
    expect(store.get('dn.ytmSync')).toBe('0')
    expect(await S.syncFromYouTube()).toBe(null)
    expect(api.syncYouTubeHistory).not.toHaveBeenCalled()
  })

  it('turned back on, it brings it in straight away', async () => {
    S.setYtmSync(false)
    S.setYtmSync(true)
    await vi.waitFor(() => expect(api.syncYouTubeHistory).toHaveBeenCalledTimes(1))
  })

  it('offline: nothing breaks, and it tries again next time', async () => {
    api.syncYouTubeHistory.mockRejectedValue(new Error('offline'))
    expect(await S.syncFromYouTube()).toBe(null)
    expect(S.ytmSyncing.value).toBe(false)
  })

  it('says when, in words', () => {
    const now = 1792000000 * 1000
    expect(S.syncedAgo(0, now)).toBe('')
    expect(S.syncedAgo(1792000000, now)).toBe('now')
    expect(S.syncedAgo(1792000000 - 5 * 60, now)).toBe('5 minutes ago')
    expect(S.syncedAgo(1792000000 - 3 * 3600, now)).toBe('3 hours ago')
    expect(S.syncedAgo(1792000000 - 2 * 86400, now)).toBe('2 days ago')
  })
})
