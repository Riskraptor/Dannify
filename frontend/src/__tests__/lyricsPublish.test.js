import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Sending lyrics and keeping drafts: the backend and the connection check
// are stand-ins, storage is an in-memory copy.

const api = vi.hoisted(() => ({ publishLyrics: null }))
const net = vi.hoisted(() => ({ offline: false }))
vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/model/connectivity', () => ({ failedForNetwork: async () => net.offline }))

import { sendLyrics, announcePublished } from '../model/lyrics/publish'
import { draftKey, loadDraft, saveDraft, clearDraft } from '../model/lyrics/draft'

const PAYLOAD = { track: 'Suzanna', artist: 'Sauti Sol', album: '', duration: 230, plain: 'a', synced: '' }

describe('sendLyrics', () => {
  beforeEach(() => {
    net.offline = false
  })

  it('is done when the catalogue says published', async () => {
    api.publishLyrics = vi.fn(async () => ({ data: { published: true } }))
    expect(await sendLyrics(PAYLOAD)).toEqual({ ok: true })
    expect(api.publishLyrics).toHaveBeenCalledWith(PAYLOAD)
  })

  it('passes on the reason the catalogue gave', async () => {
    api.publishLyrics = async () => ({ data: { published: false, error: ' Track duration is required. ' } })
    expect(await sendLyrics(PAYLOAD)).toEqual({ ok: false, reason: 'rejected', error: 'Track duration is required.' })
  })

  it('fails plainly when no reason was given', async () => {
    api.publishLyrics = async () => ({ data: {} })
    expect(await sendLyrics(PAYLOAD)).toEqual({ ok: false, reason: 'failed' })
  })

  it('tells a timeout apart', async () => {
    api.publishLyrics = async () => {
      throw Object.assign(new Error('timeout of 120000ms exceeded'), { code: 'ECONNABORTED' })
    }
    expect(await sendLyrics(PAYLOAD)).toEqual({ ok: false, reason: 'timeout' })
  })

  it('tells a lost connection apart from a server that failed', async () => {
    api.publishLyrics = async () => {
      throw new Error('Network Error')
    }
    net.offline = true
    expect(await sendLyrics(PAYLOAD)).toEqual({ ok: false, reason: 'offline' })
    net.offline = false
    expect(await sendLyrics(PAYLOAD)).toEqual({ ok: false, reason: 'failed' })
  })
})

describe('announcePublished', () => {
  afterEach(() => {
    delete globalThis.window
  })

  it('tells the rest of the app which song has new lyrics', () => {
    const seen = []
    globalThis.window = { dispatchEvent: (e) => seen.push(e) }
    announcePublished('Suzanna', 'Sauti Sol')
    expect(seen[0].type).toBe('dannify:lyrics-published')
    expect(seen[0].detail).toEqual({ track: 'Suzanna', artist: 'Sauti Sol' })
  })
})

describe('drafts', () => {
  let storage
  beforeEach(() => {
    storage = new Map()
    globalThis.localStorage = {
      getItem: (k) => (storage.has(k) ? storage.get(k) : null),
      setItem: (k, v) => storage.set(k, String(v)),
      removeItem: (k) => storage.delete(k),
    }
  })
  afterEach(() => {
    delete globalThis.localStorage
  })

  it('keys a draft the way drafts were always keyed', () => {
    expect(draftKey('Suzanna', 'Sauti Sol')).toBe('dannify-lyric-draft|suzanna|sauti sol')
  })

  it('reads back what it saved', () => {
    const draft = {
      form: { track: 'T', artist: 'A', album: '', duration: 200, raw: 'x' },
      lines: [{ text: 'x', time: 1.5 }],
      phase: 1,
      seed: [],
      from: 'x',
    }
    expect(saveDraft('k', draft)).toBe(true)
    expect(loadDraft('k')).toEqual(draft)
    clearDraft('k')
    expect(loadDraft('k')).toBeNull()
  })

  it('repairs what it can and refuses what it cannot', () => {
    storage.set('bad', '{not json')
    storage.set('none', JSON.stringify({ lines: [] }))
    storage.set(
      'odd',
      JSON.stringify({ form: { raw: 'x', duration: 'abc' }, lines: [{ text: 'x', time: 'soon' }, null], phase: 9 })
    )
    expect(loadDraft('bad')).toBeNull()
    expect(loadDraft('none')).toBeNull()
    expect(loadDraft('missing')).toBeNull()
    expect(loadDraft('odd')).toEqual({
      form: { track: '', artist: '', album: '', duration: 0, raw: 'x' },
      lines: [
        { text: 'x', time: null },
        { text: '', time: null },
      ],
      phase: 2,
      seed: [],
      from: 'x',
    })
  })

  it('carries on when storage is full or blocked', () => {
    globalThis.localStorage.setItem = () => {
      throw new Error('QuotaExceededError')
    }
    expect(saveDraft('k', { form: { raw: '' } })).toBe(false)
  })
})
