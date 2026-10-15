// How long a song was really listened to, and when that makes a listen.
//
// The player says a song has started the moment it is picked, which is right
// for "Jump back in" and wrong for counting: skipping through an album would
// make every song on it a favourite. This keeps count of the time a song
// actually spent playing, and only calls it a listen once that is enough.
//
// It knows nothing of the player or the network. It is told, a few times a
// second, what is in the player and whether it is playing, and it hands back
// each listen as it ends. That is what lets it be tested with a clock that
// is moved by hand.

// The same rule the app's own history uses to say what it keeps
// (Backend/dannify/listens.py): half a minute, or half of a song too short
// for that.
export const MIN_SECONDS = 30

export function counts(seconds, duration = 0) {
  if (seconds >= MIN_SECONDS) return true
  return duration > 0 && seconds >= 5 && seconds >= duration / 2
}

// The most that one step between two reports can add. They come about four
// times a second while a song plays, so anything much longer was not
// listening: the PC slept, or the stream stalled.
const MAX_STEP = 1.5
// How near the end, and then the start, the playhead has to be for a jump
// back to be the song starting over (repeat one), not a line heard again.
const EDGE = 3

/**
 * `clock()` is the time in milliseconds. `same(a, b)` says whether two
 * tracks are the same song: a song whose saved file gives way to its online
 * copy mid-play is still the one listen.
 */
export function createListenMeter({ clock = () => Date.now(), same = (a, b) => a === b } = {}) {
  // { track, started, seconds, duration } while a song is in the player.
  let open = null
  let last = 0 // when the last report came, while playing
  let lastPosition = 0

  function begin(track) {
    open = track ? { track, started: 0, seconds: 0, duration: 0 } : null
    last = 0
    lastPosition = 0
  }

  /** End the open listen. It is handed back if it was one. */
  function end() {
    const done = open
    open = null
    last = 0
    if (!done || !counts(done.seconds, done.duration)) return null
    return {
      track: done.track,
      started: done.started,
      seconds: Math.round(done.seconds),
      duration: done.duration,
    }
  }

  return {
    /**
     * What the player is doing now. Returns the listen that just ended, when
     * one did: another song took over, or this one started again from the top.
     */
    tick({ track, playing, position = 0, duration = 0 }) {
      const now = clock()
      let finished = null
      if (!track || !open || (track !== open.track && !same(open.track, track))) {
        finished = end()
        begin(track)
      } else {
        // The same song, perhaps as a newer object with more known about it.
        open.track = track
      }
      if (!open) return finished
      if (duration > 0) open.duration = duration

      // Back at the top having been at the very end: the song is on repeat,
      // and each time round is a listen of its own.
      const wrapped =
        open.duration > 0 &&
        lastPosition >= open.duration - EDGE &&
        position <= EDGE &&
        position < lastPosition
      if (wrapped && !finished) {
        const again = open.track
        const length = open.duration
        finished = end()
        begin(again)
        open.duration = length
      }
      lastPosition = position

      if (!playing) {
        last = 0
        return finished
      }
      if (last) open.seconds += Math.max(0, Math.min(MAX_STEP, (now - last) / 1000))
      // Counted from the first moment it was heard, not from when it was
      // loaded: a song restored paused at launch may wait hours for Play.
      if (!open.started) open.started = now
      last = now
      return finished
    },

    /**
     * The same song is starting over because the queue said so (the only
     * song in it, on repeat all). Nothing in what the player reports tells
     * that apart from carrying on.
     */
    restart() {
      if (!open) return null
      const again = open.track
      const length = open.duration
      const finished = end()
      begin(again)
      open.duration = length
      return finished
    },

    /** The listen so far, for keeping somewhere in case the app goes. */
    peek() {
      if (!open || !open.started || !counts(open.seconds, open.duration)) return null
      return {
        track: open.track,
        started: open.started,
        seconds: Math.round(open.seconds),
        duration: open.duration,
      }
    },
  }
}
