import { afterEach, describe, expect, it, vi } from 'vitest'
import { createClient } from '../model/http'

// The window's way of talking to its server, on fetch: answers, errors the
// rest of the app reads the way it always has, time limits and calling off.

function answer(status, body, type = 'application/json') {
  return Promise.resolve(
    new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, headers: { 'Content-Type': type } })
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('requests', () => {
  it('asks with the parameters given, leaving out the empty ones', async () => {
    const fetch = vi.fn(() => answer(200, { ok: true }))
    vi.stubGlobal('fetch', fetch)
    const api = createClient({ baseURL: 'http://127.0.0.1:5000' })
    const res = await api.get('/api/listens/story', { params: { period: 'week', year: undefined, ago: 0, force: true } })
    expect(res.data).toEqual({ ok: true })
    expect(res.status).toBe(200)
    expect(fetch.mock.calls[0][0]).toBe('http://127.0.0.1:5000/api/listens/story?period=week&ago=0&force=true')
    expect(fetch.mock.calls[0][1].method).toBe('GET')
  })

  it('sends a body as JSON, and nothing when there is none', async () => {
    const fetch = vi.fn(() => answer(200, ''))
    vi.stubGlobal('fetch', fetch)
    const api = createClient()
    await api.post('/api/playlists', { name: 'Mine', tracks: [] })
    await api.post('/api/update/acknowledge')
    expect(fetch.mock.calls[0][1].body).toBe('{"name":"Mine","tracks":[]}')
    expect(fetch.mock.calls[0][1].headers['Content-Type']).toBe('application/json')
    expect(fetch.mock.calls[1][1].body).toBeUndefined()
  })

  it('reads text that is not JSON as text', async () => {
    vi.stubGlobal('fetch', vi.fn(() => answer(200, 'Song - Artist.mp3', 'text/plain')))
    expect((await createClient().post('/api/download', {})).data).toBe('Song - Artist.mp3')
  })
})

describe('when it goes wrong', () => {
  it('an error the server answered carries its status and what it said', async () => {
    vi.stubGlobal('fetch', vi.fn(() => answer(422, { detail: 'not music' })))
    const err = await createClient().get('/api/links/spotify').catch((e) => e)
    expect(err.response.status).toBe(422)
    expect(err.response.data.detail).toBe('not music')
    expect(err.isAxiosError).toBe(true)
  })

  it('no answer at all has no response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    const err = await createClient().get('/api/net').catch((e) => e)
    expect(err.response).toBeUndefined()
    expect(err.code).toBe('ERR_NETWORK')
  })

  it('gives up after its time limit', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn((_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted')))))
    )
    const asking = createClient().get('/api/explore/suggest', { timeout: 4000 }).catch((e) => e)
    vi.advanceTimersByTime(4000)
    const err = await asking
    expect(err.code).toBe('ECONNABORTED')
    vi.useRealTimers()
  })

  it('can be called off', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted')))))
    )
    const off = new AbortController()
    const asking = createClient().get('/api/explore/suggest', { signal: off.signal }).catch((e) => e)
    off.abort()
    const err = await asking
    expect(err.name).toBe('CanceledError')
  })
})
