// The sound path: what happens to the audio between the file and the speakers.
//
//   deck A  ─ norm ─ fade ─┐
//                          ├─ EQ (10 bands) ─ preamp ─ volume ─ limiter ─ out
//   deck B  ─ norm ─ fade ─┘
//
// Two decks, so one song can fade into the next (crossfade) or start the
// instant the last one stops (gapless). Each deck has its own level for
// evening out loudness ("norm") and its own fade. After they meet: the
// equalizer, the listener's volume, and a limiter, so a quiet song turned up
// or a boosted bass never clips.
//
// Without Web Audio (a test, or a browser that refuses it) the engine says
// so and the player falls back to setting the element's own volume, exactly
// as it always did.

export const EQ_BANDS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

// Gains in dB, one per band. Named for what they are for, not for a genre's
// idea of itself: "Bass" is more bass, "Vocal" brings voices forward.
export const EQ_PRESETS = {
  flat: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  bass: [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
  treble: [0, 0, 0, 0, 0, 0, 2, 4, 5, 6],
  vocal: [-2, -1, 0, 2, 4, 4, 3, 1, 0, -1],
  afrobeats: [5, 4, 2, 1, -1, -1, 1, 1, 2, 2],
  pop: [-1, 1, 3, 4, 3, 0, -1, -1, 0, 1],
  rock: [4, 3, 1, -1, -2, -1, 1, 3, 4, 4],
  electronic: [4, 4, 1, 0, -2, 1, 0, 1, 4, 5],
  acoustic: [3, 2, 1, 1, 2, 2, 3, 3, 2, 1],
  smallSpeakers: [5, 4, 3, 1, 0, 0, 1, 2, 3, 3],
  night: [-3, -2, -1, 0, 1, 1, 0, -1, -2, -3],
}

export const EQ_MIN = -12
export const EQ_MAX = 12

const dbToGain = (db) => Math.pow(10, db / 20)

/** An equal-power curve from *from* to *to*, for a fade that does not dip. */
export function fadeCurve(from, to, steps = 64) {
  const out = new Float32Array(steps)
  for (let i = 0; i < steps; i++) {
    const x = i / (steps - 1)
    // cos/sin quarter waves: at the crossover both decks are at -3 dB, so the
    // sum stays level instead of dropping in the middle.
    const w = to > from ? Math.sin((x * Math.PI) / 2) : Math.cos((x * Math.PI) / 2)
    out[i] = to > from ? from + (to - from) * w : to + (from - to) * w
  }
  return out
}

export function createEngine(Ctx = typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)) {
  if (!Ctx) return { available: false }
  let ctx
  try {
    ctx = new Ctx({ latencyHint: 'playback' })
  } catch {
    return { available: false }
  }

  const input = ctx.createGain() // where the decks meet
  const bands = EQ_BANDS.map((freq, i) => {
    const f = ctx.createBiquadFilter()
    f.type = i === 0 ? 'lowshelf' : i === EQ_BANDS.length - 1 ? 'highshelf' : 'peaking'
    f.frequency.value = freq
    f.Q.value = 1.1
    f.gain.value = 0
    return f
  })
  const preamp = ctx.createGain()
  const volume = ctx.createGain()
  const limiter = ctx.createDynamicsCompressor()
  limiter.threshold.value = -1
  limiter.knee.value = 0
  limiter.ratio.value = 20
  limiter.attack.value = 0.003
  limiter.release.value = 0.25

  let node = input
  for (const f of bands) {
    node.connect(f)
    node = f
  }
  node.connect(preamp)
  preamp.connect(volume)
  volume.connect(limiter)
  limiter.connect(ctx.destination)

  const now = () => ctx.currentTime

  function setParam(param, value, smooth = 0.02) {
    try {
      param.cancelScheduledValues(now())
      param.setTargetAtTime(value, now(), smooth)
    } catch {
      param.value = value
    }
  }

  function attach(el) {
    const source = ctx.createMediaElementSource(el)
    const norm = ctx.createGain()
    const fade = ctx.createGain()
    source.connect(norm)
    norm.connect(fade)
    fade.connect(input)
    // The element plays at full level; every level is set in the graph.
    el.volume = 1
    return {
      el,
      setNorm(gain, smooth = 0.25) {
        setParam(norm.gain, gain, smooth)
      },
      setFade(value) {
        try {
          fade.gain.cancelScheduledValues(now())
        } catch {
          // nothing scheduled
        }
        fade.gain.value = value
      },
      /** Fade to *to* over *seconds*; resolves when done. */
      fadeTo(to, seconds) {
        const from = fade.gain.value
        try {
          fade.gain.cancelScheduledValues(now())
          if (seconds > 0.01) fade.gain.setValueCurveAtTime(fadeCurve(from, to), now(), seconds)
          else fade.gain.setValueAtTime(to, now())
        } catch {
          fade.gain.value = to
        }
        return new Promise((resolve) => setTimeout(resolve, Math.max(0, seconds * 1000)))
      },
    }
  }

  return {
    available: true,
    ctx,
    attach,
    /** The listener's volume, 0 to 1 (0 when muted). */
    setVolume(v, smooth = 0.015) {
      setParam(volume.gain, Math.max(0, Math.min(1, v)), smooth)
    },
    /** Fade the whole output to *v* over *seconds* (the sleep timer). */
    rampVolume(v, seconds) {
      try {
        volume.gain.cancelScheduledValues(now())
        volume.gain.setValueAtTime(volume.gain.value, now())
        volume.gain.linearRampToValueAtTime(Math.max(0, v), now() + seconds)
      } catch {
        volume.gain.value = v
      }
    },
    /** Band gains in dB; *on* false is flat. A preamp makes room for boosts. */
    setEq(on, gains) {
      const g = on ? gains : EQ_PRESETS.flat
      bands.forEach((f, i) => setParam(f.gain, Math.max(EQ_MIN, Math.min(EQ_MAX, Number(g[i]) || 0)), 0.03))
      const top = Math.max(0, ...g.map((x) => Number(x) || 0))
      // Half the biggest boost taken back up front; the limiter catches the rest.
      setParam(preamp.gain, on ? dbToGain(-top / 2) : 1, 0.03)
    },
    resume() {
      if (ctx.state !== 'running') return ctx.resume().catch(() => {})
      return Promise.resolve()
    },
    async setSink(id) {
      if (typeof ctx.setSinkId !== 'function') return false
      try {
        await ctx.setSinkId(id || '')
        return true
      } catch {
        return false
      }
    },
  }
}
