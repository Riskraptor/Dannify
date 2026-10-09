import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, nextTick } from 'vue'

// The editor's whole flow, from opening on a song to publishing, driven with
// a stand-in for the player and for the network. Storage is an in-memory
// copy, fresh for every test, and the clock is a fake one, so a draft save
// left pending by one test can never land in the next one's storage.

const net = vi.hoisted(() => ({ calls: [], result: { ok: true }, announced: [] }))
vi.mock('../model/lyrics/publish', () => ({
  sendLyrics: async (payload) => {
    net.calls.push(payload)
    return net.result
  },
  announcePublished: (track, artist) => net.announced.push({ track, artist }),
  openLyricsEditor: () => {},
}))

import { useLyricsSubmit, WORDS, SYNC, REVIEW } from '../model/lyrics/useLyricsSubmit'
import { draftKey } from '../model/lyrics/draft'

const SONG = { title: 'Suzanna', artist: 'Sauti Sol', album: 'Midnight Train', duration: 230, cover: '/c.jpg' }
const SYNCED = [
  { text: 'Kukosana na wewe', time: 10.5 },
  { text: 'Kuwa mbali na wewe', time: 15.5 },
  { text: '', time: 18 },
  { text: 'Kutengana na wewe', time: 20.4 },
]

function fakePlayer({ track = SONG, synced = [], plain = null, duration = 0 } = {}) {
  return {
    currentTrack: ref(track),
    lyricsLines: ref(synced),
    lyricsPlain: ref(plain),
    duration: ref(duration),
  }
}

let storage
beforeEach(() => {
  storage = new Map()
  globalThis.localStorage = {
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k),
  }
  net.calls = []
  net.result = { ok: true }
  net.announced = []
  vi.useFakeTimers()
})
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  delete globalThis.localStorage
})

function openOn(player) {
  const s = useLyricsSubmit({ player })
  s.open()
  return s
}

describe('opening', () => {
  it('starts from the words of timed lyrics, their timing kept aside', () => {
    const s = openOn(fakePlayer({ synced: SYNCED }))
    expect(s.form.value).toMatchObject({ track: 'Suzanna', artist: 'Sauti Sol', album: 'Midnight Train', duration: 230 })
    expect(s.form.value.raw).toBe('Kukosana na wewe\nKuwa mbali na wewe\n♪\nKutengana na wewe')
    expect(s.seedTimes.value).toHaveLength(4)
    expect(s.phase.value).toBe(WORDS)
    expect(s.cover.value).toBe('/c.jpg')
    expect(s.restored.value).toBe(false)
  })

  it('starts from plain words, or from nothing', () => {
    expect(openOn(fakePlayer({ plain: 'one\ntwo' })).form.value.raw).toBe('one\ntwo')
    expect(openOn(fakePlayer()).form.value.raw).toBe('')
  })

  it('does nothing without a song', () => {
    const s = useLyricsSubmit({ player: fakePlayer({ track: null }) })
    expect(s.open()).toBe(false)
  })
})

describe('the words step', () => {
  it('will not go on without title, artist, length and words', () => {
    const s = openOn(fakePlayer({ track: { title: '', artist: 'x', duration: 0 } }))
    expect(s.missing.value).toEqual({ details: true, duration: true, words: true })
    expect(s.showDetails.value).toBe(true)
    s.nextFromWords()
    expect(s.phase.value).toBe(WORDS)
  })

  it('fills in the length once the player knows it, for the same song only', async () => {
    const player = fakePlayer({ track: { ...SONG, duration: 0 } })
    const s = openOn(player)
    expect(s.missing.value.duration).toBe(true)
    player.duration.value = 187
    await nextTick()
    expect(s.form.value.duration).toBe(187)

    const other = fakePlayer({ track: { ...SONG, duration: 0 } })
    const s2 = openOn(other)
    other.currentTrack.value = { title: 'Another' }
    other.duration.value = 99
    await nextTick()
    expect(s2.form.value.duration).toBe(0)
  })

  it('goes straight to the review when a typo fix leaves every line timed', () => {
    const s = openOn(fakePlayer({ synced: SYNCED }))
    s.form.value.raw = s.form.value.raw.replace('Kuwa mbali na wewe', 'Kuwa mbali nawe')
    expect(s.untimedAfterWords.value).toBe(0)
    s.nextFromWords()
    expect(s.phase.value).toBe(REVIEW)
    expect(s.editor.lines.value.map((l) => l.time)).toEqual([10.5, 15.5, 18, 20.4])
    expect(s.syncedOutput.value).toContain('[00:15.50]Kuwa mbali nawe')
  })

  it('sends a new line to the timing step, the cursor on it', () => {
    const s = openOn(fakePlayer({ synced: SYNCED }))
    s.form.value.raw += '\nA brand new line'
    expect(s.untimedAfterWords.value).toBe(1)
    s.nextFromWords()
    expect(s.phase.value).toBe(SYNC)
    expect(s.editor.active.value).toBe(4)
  })

  it('takes pasted LRC as it is, straight to the review', () => {
    const s = openOn(fakePlayer())
    s.form.value.raw = '[00:01.00]one\n[00:02.00]two'
    expect(s.detectedSynced.value).toBe(true)
    expect(s.syncedCount.value).toBe(2)
    s.nextFromWords()
    expect(s.phase.value).toBe(REVIEW)
    expect(s.syncedOutput.value).toBe('[00:01.00]one\n[00:02.00]two')
  })

  it('rebuilds the lines when the words change after going back', () => {
    const s = openOn(fakePlayer())
    s.form.value.raw = 'one\ntwo'
    s.nextFromWords()
    s.editor.stamp(0, 1)
    s.goPhase(WORDS)
    s.form.value.raw = 'one\ntwo\nthree'
    s.goPhase(SYNC)
    expect(s.editor.lines.value.map((l) => [l.text, l.time])).toEqual([
      ['one', 1],
      ['two', null],
      ['three', null],
    ])
  })
})

describe('the timing and review steps', () => {
  function timedSong() {
    const s = openOn(fakePlayer())
    s.form.value.raw = 'one\ntwo\nthree\nfour'
    s.nextFromWords()
    return s
  }

  it('asks for half the lines before the review', () => {
    const s = timedSong()
    expect(s.phase.value).toBe(SYNC)
    expect(s.needTimed.value).toBe(2)
    s.editor.stamp(0, 1)
    expect(s.canReview.value).toBe(false)
    expect(s.syncedOutput.value).toBe('')
    s.editor.stamp(1, 2)
    expect(s.canReview.value).toBe(true)
    expect(s.syncedOutput.value).toBe('[00:01.00]one\n[00:02.00]two')
    expect(s.plainOutput.value).toBe('one\ntwo\nthree\nfour')
  })

  it('previews only the timed lines, in time order', () => {
    const s = timedSong()
    s.editor.stamp(1, 1)
    s.editor.stamp(0, 3)
    s.editor.stamp(2, 5)
    expect(s.previewLines.value.map((l) => l.text)).toEqual(['two', 'one', 'three'])
  })

  it('will not publish lines out of order, and leads back to the first one', async () => {
    const s = timedSong()
    s.editor.stamp(0, 5)
    s.editor.stamp(1, 6)
    s.editor.stamp(2, 2)
    s.goPhase(REVIEW)
    expect(s.blockedByOrder.value).toBe(true)
    expect(s.canSubmit.value).toBe(false)
    expect(await s.submit()).toBe(false)
    expect(net.calls).toHaveLength(0)
    s.fixOrder()
    expect(s.phase.value).toBe(SYNC)
    expect(s.editor.active.value).toBe(2)
  })

  it('goes back to the words from a review of words alone', () => {
    const s = timedSong()
    s.goPhase(REVIEW)
    s.back()
    expect(s.phase.value).toBe(WORDS)
  })
})

describe('publishing', () => {
  function ready() {
    const s = openOn(fakePlayer({ synced: SYNCED }))
    s.form.value.raw += '\nOne more'
    s.nextFromWords()
    s.editor.stamp(4, 25)
    s.goPhase(REVIEW)
    return s
  }

  it('sends the words and the timing, forgets the draft and tells the player', async () => {
    const s = ready()
    s.flushDraft()
    expect(storage.size).toBe(1)
    expect(await s.submit()).toBe(true)
    expect(net.calls[0]).toEqual({
      track: 'Suzanna',
      artist: 'Sauti Sol',
      album: 'Midnight Train',
      duration: 230,
      plain: 'Kukosana na wewe\nKuwa mbali na wewe\n\nKutengana na wewe\nOne more',
      synced:
        '[00:10.50]Kukosana na wewe\n[00:15.50]Kuwa mbali na wewe\n[00:18.00]\n[00:20.40]Kutengana na wewe\n[00:25.00]One more',
    })
    expect(s.status.value).toBe('done')
    expect(s.canSubmit.value).toBe(false)
    expect(storage.size).toBe(0)
    expect(net.announced).toEqual([{ track: 'Suzanna', artist: 'Sauti Sol' }])
  })

  it('says why it failed, and can be tried again', async () => {
    const s = ready()
    net.result = { ok: false, reason: 'rejected', error: 'Track duration is required.' }
    expect(await s.submit()).toBe(false)
    expect(s.status.value).toBe('failed')
    expect(s.failure.value).toEqual(net.result)
    expect(s.canSubmit.value).toBe(true)
    net.result = { ok: true }
    expect(await s.submit()).toBe(true)
  })
})

describe('drafts', () => {
  it('leaves none behind when nothing was changed', () => {
    const s = openOn(fakePlayer({ synced: SYNCED }))
    s.close()
    expect(storage.size).toBe(0)
  })

  it('keeps the work and picks it up next time', () => {
    const player = fakePlayer({ synced: SYNCED })
    const s = openOn(player)
    s.form.value.raw += '\nOne more'
    s.nextFromWords()
    s.editor.stamp(4, 25)
    s.close()
    expect([...storage.keys()]).toEqual([draftKey('Suzanna', 'Sauti Sol')])

    const again = openOn(player)
    expect(again.restored.value).toBe(true)
    expect(again.phase.value).toBe(SYNC)
    expect(again.editor.lines.value[4]).toMatchObject({ text: 'One more', time: 25 })
  })

  it('files the draft under the song, not under a corrected title', () => {
    const player = fakePlayer()
    const s = openOn(player)
    s.form.value.track = 'Suzanna (Live)'
    s.form.value.raw = 'words'
    s.close()
    expect(storage.has(draftKey('Suzanna', 'Sauti Sol'))).toBe(true)
    expect(openOn(player).form.value.track).toBe('Suzanna (Live)')
  })

  it('saves on its own a moment after a change', async () => {
    const s = openOn(fakePlayer())
    s.form.value.raw = 'typed'
    await nextTick()
    expect(storage.size).toBe(0)
    vi.advanceTimersByTime(600)
    expect(storage.size).toBe(1)
  })

  it('throws the draft away on Start over', () => {
    const player = fakePlayer({ plain: 'original' })
    const s = openOn(player)
    s.form.value.raw = 'changed'
    s.close()
    const again = openOn(player)
    again.startOver()
    expect(again.form.value.raw).toBe('original')
    expect(again.restored.value).toBe(false)
    expect(storage.size).toBe(0)
  })

  it('reads a draft saved before drafts said what the lines came from', () => {
    storage.set(
      draftKey('Suzanna', 'Sauti Sol'),
      JSON.stringify({
        form: { track: 'Suzanna', artist: 'Sauti Sol', album: '', duration: 230, raw: 'a\nb' },
        lines: [
          { text: 'a', time: 1 },
          { text: 'b', time: null },
        ],
        phase: 1,
      })
    )
    const s = openOn(fakePlayer())
    expect(s.phase.value).toBe(SYNC)
    expect(s.editor.active.value).toBe(1)
    s.goPhase(SYNC)
    expect(s.editor.lines.value.map((l) => l.time)).toEqual([1, null])
  })

  it('shows the words step for a draft whose lines were lost', () => {
    storage.set(
      draftKey('Suzanna', 'Sauti Sol'),
      JSON.stringify({ form: { track: 'Suzanna', artist: 'Sauti Sol', raw: 'a' }, lines: [], phase: 2 })
    )
    const s = openOn(fakePlayer())
    expect(s.phase.value).toBe(WORDS)
    expect(s.form.value.duration).toBe(230)
  })
})
