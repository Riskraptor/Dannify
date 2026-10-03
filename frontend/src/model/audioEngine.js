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
  // Left and right, and both in one: for one earbud, or one ear.
  const balance = typeof ctx.createStereoPanner === 'function' ? ctx.createStereoPanner() : null
  const mono = ctx.createGain()
  try {
    mono.channelCountMode = 'explicit'
    mono.channelInterpretation = 'speakers'
    mono.channelCount = 2
  } catch {
    // a context that cannot: stereo it stays
  }
  const volume = ctx.createGain()
  const limiter = ctx.createDynamicsCompressor()
  limiter.threshold.value = -1
  limiter.knee.value = 0
  limiter.ratio.value = 20
  limiter.attack.value = 0.003
  limiter.release.value = 0.25

  // The bands are only in the path while the equalizer is on. Ten filters
  // at 0 dB sound exactly like none, and still worked on every sample.
  for (let i = 0; i < bands.length - 1; i++) bands[i].connect(bands[i + 1])
  bands[bands.length - 1].connect(preamp)
  input.connect(preamp)
  if (balance) {
    preamp.connect(balance)
    balance.connect(mono)
  } else {
    preamp.connect(mono)
  }
  mono.connect(volume)
  volume.connect(limiter)
  limiter.connect(ctx.destination)
  let throughEq = false
  let unroute = null

  function route(on) {
    clearTimeout(unroute)
    unroute = null
    if (on === throughEq) return
    throughEq = on
    try {
      input.disconnect()
    } catch {
      // not connected
    }
    input.connect(on ? bands[0] : preamp)
  }

  // Paused for a while: the audio thread stops altogether until the next
  // play, rather than running silence through the graph all evening.
  let idleTimer = null

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
      // Into the path first and then off flat, so the sound glides from one
      // to the other; out of it only once it has glided back to flat.
      if (on) route(true)
      bands.forEach((f, i) => setParam(f.gain, Math.max(EQ_MIN, Math.min(EQ_MAX, Number(g[i]) || 0)), 0.03))
      const top = Math.max(0, ...g.map((x) => Number(x) || 0))
      // Half the biggest boost taken back up front; the limiter catches the rest.
      setParam(preamp.gain, on ? dbToGain(-top / 2) : 1, 0.03)
      if (!on && throughEq && !unroute) unroute = setTimeout(() => route(false), 250)
    },
    /** -1 (left only) to 1 (right only); 0 is the middle. */
    setBalance(v) {
      if (!balance) return
      setParam(balance.pan, Math.max(-1, Math.min(1, Number(v) || 0)), 0.03)
    },
    /** Both channels mixed into one, heard in both ears. */
    setMono(on) {
      try {
        mono.channelCount = on ? 1 : 2
      } catch {
        // not supported here
      }
    },
    /**
     * The equalizer's effect at each of `freqs` (Hz), in dB: the bands and
     * the preamp together, as the filters themselves compute it.
     */
    eqResponse(freqs) {
      const out = new Float32Array(freqs.length)
      if (!throughEq) return out
      const f = Float32Array.from(freqs)
      const mag = new Float32Array(freqs.length)
      const phase = new Float32Array(freqs.length)
      for (const band of bands) {
        if (typeof band.getFrequencyResponse !== 'function') return out
        band.getFrequencyResponse(f, mag, phase)
        for (let i = 0; i < out.length; i++) out[i] += 20 * Math.log10(Math.max(1e-6, mag[i]))
      }
      const pre = 20 * Math.log10(Math.max(1e-6, preamp.gain.value))
      for (let i = 0; i < out.length; i++) out[i] += pre
      return out
    },
    /** Whether the equalizer's bands are in the path (for tests). */
    get eqInPath() {
      return throughEq
    },
    /** Paused: let the audio thread rest after a while. */
    idleSoon(ms = 15000) {
      clearTimeout(idleTimer)
      idleTimer = setTimeout(() => {
        idleTimer = null
        if (ctx.state === 'running' && typeof ctx.suspend === 'function') ctx.suspend().catch(() => {})
      }, ms)
    },
    resume() {
      clearTimeout(idleTimer)
      idleTimer = null
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
