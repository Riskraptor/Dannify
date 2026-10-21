import { beforeEach, describe, expect, it, vi } from 'vitest'

// The summary of what was listened to, asked for by several parts of a page
// at once (Home's year card and its mixes): one request between them.

const api = vi.hoisted(() => ({ getListenStats: vi.fn() }))
vi.mock('/src/model/api', () => ({ default: api }))
// The player, which needs a window, is not what this is about.
vi.mock('/src/model/player/state', async () => {
  const { ref } = await import('vue')
  return { currentTime: ref(0), currentTrack: ref(null), duration: ref(0), isPlaying: ref(false) }
})
vi.mock('/src/model/playlists', () => ({ entryOf: () => null }))
vi.mock('/src/model/tracks', () => ({ queueRow: () => null }))
vi.mock('/src/model/support', () => ({ notePlayed: () => {} }))

let listens
beforeEach(async () => {
  vi.resetModules()
  api.getListenStats.mockReset()
  listens = await import('../model/listens.js')
})

describe('fetchStats', () => {
  it('shares one request between callers asking at the same time', async () => {
    let answer
    api.getListenStats.mockReturnValue(new Promise((r) => (answer = r)))
    const a = listens.fetchStats(294, 4)
    const b = listens.fetchStats(294, 4)
    answer({ data: { plays: 7 } })
    expect(await a).toEqual({ plays: 7 })
    expect(await b).toEqual({ plays: 7 })
    expect(api.getListenStats).toHaveBeenCalledTimes(1)
  })

  it('asks again for a different stretch', async () => {
    api.getListenStats.mockResolvedValue({ data: {} })
    await listens.fetchStats(7, 4)
    await listens.fetchStats(30, 4)
    expect(api.getListenStats).toHaveBeenCalledTimes(2)
  })

  it('does not keep a failure, so the next ask tries again', async () => {
    api.getListenStats.mockRejectedValueOnce(new Error('offline'))
    await expect(listens.fetchStats(7, 4)).rejects.toThrow('offline')
    api.getListenStats.mockResolvedValueOnce({ data: { plays: 1 } })
    expect(await listens.fetchStats(7, 4)).toEqual({ plays: 1 })
    expect(api.getListenStats).toHaveBeenCalledTimes(2)
  })

  it('asks again once the history has changed', async () => {
    api.getListenStats.mockResolvedValue({ data: {} })
    await listens.fetchStats(7, 4)
    listens.listensEpoch.value++
    await listens.fetchStats(7, 4)
    expect(api.getListenStats).toHaveBeenCalledTimes(2)
  })
})
