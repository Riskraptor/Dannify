import { describe, expect, it } from 'vitest'
import { counts, createListenMeter } from '../model/listenMeter.js'

// The meter is driven the way the player drives it: a report a few times a
// second saying what is loaded, whether it is playing and where the playhead
// is. The clock here is moved by hand.

function setup(options = {}) {
  let now = 1_000_000
  const meter = createListenMeter({ clock: () => now, ...options })
  // Play `track` for `seconds`, the playhead moving with the clock.
  function play(track, seconds, { from = 0, duration = track.duration } = {}) {
    const finished = []
    const steps = Math.round(seconds * 4)
    for (let i = 0; i <= steps; i++) {
      const done = meter.tick({ track, playing: true, position: from + i / 4, duration })
      if (done) finished.push(done)
      if (i < steps) now += 250
    }
    return finished
  }
  return {
    meter,
    play,
    wait: (seconds) => {
      now += seconds * 1000
    },
    now: () => now,
  }
}

const song = (id, duration = 200) => ({ id, duration })

describe('counts()', () => {
  it('half a minute is a listen, less is a skip', () => {
    expect(counts(30, 200)).toBe(true)
    expect(counts(29, 200)).toBe(false)
  })
  it('half of a song too short for that is a listen', () => {
    expect(counts(20, 40)).toBe(true)
    expect(counts(19, 40)).toBe(false)
    expect(counts(4, 6)).toBe(false)
    expect(counts(20, 0)).toBe(false)
  })
})

describe('the listen meter', () => {
  it('hands back a listen when another song takes over', () => {
    const { meter, play, now } = setup()
    const a = song('a')
    const started = now()
    expect(play(a, 60)).toEqual([])
    const done = meter.tick({ track: song('b'), playing: false, position: 0, duration: 180 })
    expect(done).toMatchObject({ track: a, seconds: 60, started, duration: 200 })
  })

  it('a song skipped past is not a listen', () => {
    const { meter, play } = setup()
    play(song('a'), 12)
    expect(meter.tick({ track: song('b'), playing: true, position: 0, duration: 180 })).toBeNull()
    expect(meter.peek()).toBeNull()
  })

  it('counts only the time it was playing', () => {
    const { meter, play, wait } = setup()
    const a = song('a')
    play(a, 20)
    // Paused for ten minutes, then on for another twenty seconds.
    meter.tick({ track: a, playing: false, position: 20, duration: 200 })
    wait(600)
    meter.tick({ track: a, playing: false, position: 20, duration: 200 })
    play(a, 20, { from: 20 })
    const done = meter.tick({ track: null, playing: false })
    expect(done.seconds).toBe(40)
  })

  it('a gap between reports is not listening', () => {
    const { meter, wait } = setup()
    const a = song('a')
    meter.tick({ track: a, playing: true, position: 0, duration: 200 })
    // The PC slept for an hour with the song "playing".
    wait(3600)
    meter.tick({ track: a, playing: true, position: 1, duration: 200 })
    expect(meter.peek()).toBeNull()
  })

  it('is counted from when it was first heard, not from when it was loaded', () => {
    const { meter, play, wait, now } = setup()
    const a = song('a')
    // Restored at launch, paused, and left for an hour.
    meter.tick({ track: a, playing: false, position: 42, duration: 200 })
    wait(3600)
    const pressed = now()
    play(a, 31, { from: 42 })
    expect(meter.peek()).toMatchObject({ started: pressed, seconds: 31 })
  })

  it('going back over a line is still the same listen', () => {
    const { meter, play } = setup()
    const a = song('a')
    play(a, 100)
    // Back to one minute in, and on to the end of the song.
    expect(play(a, 140, { from: 60 })).toEqual([])
    expect(meter.tick({ track: null, playing: false }).seconds).toBe(240)
  })

  it('a song on repeat is a listen each time round', () => {
    const { meter, play } = setup()
    const a = song('a', 60)
    expect(play(a, 59.75)).toEqual([])
    // It ended, and the player put it back at the start.
    const again = play(a, 59.75)
    expect(again).toHaveLength(1)
    expect(again[0]).toMatchObject({ track: a, seconds: 60 })
    const third = play(a, 30)
    expect(third).toHaveLength(1)
    expect(meter.peek().seconds).toBe(30)
  })

  it('the same song started over by the queue is a new listen', () => {
    const { meter, play } = setup()
    const a = song('a')
    play(a, 45)
    expect(meter.restart()).toMatchObject({ track: a, seconds: 45 })
    // Nothing heard of the new one yet.
    expect(meter.restart()).toBeNull()
    expect(meter.peek()).toBeNull()
  })

  it('the same song as a different object carries on', () => {
    const same = (x, y) => x.id === y.id
    const { meter, play } = setup({ same })
    play({ id: 'a', duration: 200 }, 20)
    // Its saved file gave way to its online copy: another object, one song.
    const online = { id: 'a', duration: 200, online: true }
    expect(play(online, 20, { from: 20 })).toEqual([])
    const done = meter.tick({ track: null, playing: false })
    expect(done.seconds).toBe(40)
    expect(done.track).toBe(online)
  })

  it('what has been heard so far can be read while it plays', () => {
    const { meter, play } = setup()
    const a = song('a')
    play(a, 10)
    expect(meter.peek()).toBeNull() // not a listen yet
    play(a, 25, { from: 10 })
    expect(meter.peek()).toMatchObject({ track: a, seconds: 35 })
  })
})
