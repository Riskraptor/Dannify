import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'

// What the window tells the backend for Discord (model/presence.js): nothing
// while it is off, and while it is on each change of song, pause and seek,
// once things settle.

const api = vi.hoisted(() => ({
  discordStatus: null,
  setDiscord: null,
  discordNowPlaying: null,
}))
vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/i18n', () => ({ t: (k) => k }))

let P
let S

beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules()
  globalThis.window = globalThis.window || {}
  // The backend remembers the switch.
  let on = false
  api.discordStatus = vi.fn(() => Promise.resolve({ data: { enabled: on, connected: on } }))
  api.setDiscord = vi.fn((value) => {
    on = value
    return Promise.resolve({ data: { enabled: on, connected: on } })
  })
  api.discordNowPlaying = vi.fn(() => Promise.resolve({ data: { ok: true } }))
  S = await import('/src/model/player/state')
  P = await import('/src/model/presence')
  P.startPresence()
})

afterEach(() => {
  vi.useRealTimers()
})

const song = {
  type: 'stream',
  title: 'Suzanna',
  artist: 'Sauti Sol',
  album: 'Midnight Train',
  cover: 'https://lh3.googleusercontent.com/x=w120-h120',
  video_id: 'KNEd-OkExKY',
  url: '/api/stream?id=KNEd-OkExKY',
  duration: 230,
}

// The player's current song is the one at the queue's position.
function playing(track) {
  S.playlist.value = track ? [track] : []
  S.currentIndex.value = track ? 0 : -1
}

async function settle(ms = 500) {
  await nextTick()
  await vi.advanceTimersByTimeAsync(ms)
}

describe('Discord presence from the window', () => {
  it('sends nothing while it is off', async () => {
    playing(song)
    S.isPlaying.value = true
    await settle(5000)
    expect(api.discordStatus).toHaveBeenCalled()
    expect(api.discordNowPlaying).not.toHaveBeenCalled()
  })

  it('turned on, it says what is playing at once, and each change after', async () => {
    playing(song)
    S.isPlaying.value = true
    S.currentTime.value = 30
    await P.setDiscord(true)
    await settle()
    expect(api.setDiscord).toHaveBeenCalledWith(true)
    expect(api.discordNowPlaying).toHaveBeenCalledTimes(1)
    expect(api.discordNowPlaying.mock.calls[0][0]).toEqual({
      title: 'Suzanna',
      artist: 'Sauti Sol',
      album: 'Midnight Train',
      cover: song.cover,
      video_id: 'KNEd-OkExKY',
      duration: 230,
      position: 30,
      playing: true,
      button: 'discord.button',
    })

    S.isPlaying.value = false
    await settle()
    expect(api.discordNowPlaying).toHaveBeenCalledTimes(2)
    expect(api.discordNowPlaying.mock.calls[1][0].playing).toBe(false)
  })

  it('gathers quick skips into one message, with the last song', async () => {
    await P.setDiscord(true)
    S.isPlaying.value = true
    await settle()
    api.discordNowPlaying.mockClear()
    for (const title of ['One', 'Two', 'Three']) {
      playing({ ...song, title, url: `/x/${title}` })
      await nextTick()
      await vi.advanceTimersByTimeAsync(100)
    }
    await settle()
    expect(api.discordNowPlaying).toHaveBeenCalledTimes(1)
    expect(api.discordNowPlaying.mock.calls[0][0].title).toBe('Three')
  })

  it('a seek is sent; the song simply playing on is not', async () => {
    playing(song)
    S.isPlaying.value = true
    S.currentTime.value = 10
    await P.setDiscord(true)
    await settle()
    api.discordNowPlaying.mockClear()
    // Two seconds on, two seconds further: nothing to say.
    await vi.advanceTimersByTimeAsync(2000)
    S.currentTime.value = 12.4
    await settle()
    expect(api.discordNowPlaying).not.toHaveBeenCalled()
    // A jump to a minute and a half.
    S.currentTime.value = 90
    await settle()
    expect(api.discordNowPlaying).toHaveBeenCalledTimes(1)
    expect(api.discordNowPlaying.mock.calls[0][0].position).toBe(90)
  })

  it('a saved song sends no address Discord could not reach', async () => {
    playing({ ...song, type: 'local', cover: '/cover?file=Suzanna.dnf', file: 'Suzanna.dnf' })
    S.isPlaying.value = true
    await P.setDiscord(true)
    await settle()
    expect(api.discordNowPlaying.mock.calls[0][0].cover).toBe('')
    expect(api.discordNowPlaying.mock.calls[0][0].video_id).toBe('KNEd-OkExKY')
  })

  it('nothing playing is said as such', async () => {
    playing(null)
    await P.setDiscord(true)
    await settle()
    expect(api.discordNowPlaying.mock.calls[0][0]).toEqual({ playing: false })
  })
})
