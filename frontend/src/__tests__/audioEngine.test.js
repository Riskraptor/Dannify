import { describe, expect, it, vi } from 'vitest'
import { createEngine, fadeCurve, EQ_BANDS, EQ_PRESETS } from '../model/audioEngine'

// A Web Audio stand-in that records how nodes are wired and what they are set to.
class Param {
  constructor(v = 1) {
    this.value = v
  }
  cancelScheduledValues() {}
  setTargetAtTime(v) {
    this.value = v
  }
  setValueAtTime(v) {
    this.value = v
  }
  linearRampToValueAtTime(v) {
    this.value = v
  }
  setValueCurveAtTime(curve) {
    this.value = curve[curve.length - 1]
  }
}
class Node {
  constructor(kind) {
    this.kind = kind
    this.out = []
    this.type = ''
    this.gain = new Param(kind === 'filter' ? 0 : 1)
    this.frequency = new Param(0)
    this.Q = new Param(1)
    this.threshold = new Param(0)
    this.knee = new Param(0)
    this.ratio = new Param(1)
    this.attack = new Param(0)
    this.release = new Param(0)
  }
  connect(n) {
    this.out.push(n)
    return n
  }
  disconnect(n) {
    this.out = n ? this.out.filter((x) => x !== n) : []
  }
}
class FakeContext {
  constructor() {
    this.currentTime = 0
    this.state = 'running'
    this.destination = new Node('destination')
    this.sources = []
  }
  createGain() {
    return new Node('gain')
  }
  createBiquadFilter() {
    return new Node('filter')
  }
  createDynamicsCompressor() {
    return new Node('limiter')
  }
  createStereoPanner() {
    const n = new Node('panner')
    n.pan = new Param(0)
    return n
  }
  createMediaElementSource(el) {
    const n = new Node('source')
    n.el = el
    this.sources.push(n)
    return n
  }
  resume() {
    this.state = 'running'
    return Promise.resolve()
  }
  suspend() {
    this.state = 'suspended'
    return Promise.resolve()
  }
}

// Every node from a source to the speakers, following the first connection.
function chain(from) {
  const out = []
  for (let n = from; n; n = n.out[0]) out.push(n)
  return out
}

// With the equalizer on unless asked otherwise: its bands are only in the
// path then.
function made({ eq = true } = {}) {
  const ctx = new FakeContext()
  const engine = createEngine(function () {
    return ctx
  })
  const el = { volume: 0.3 }
  const deck = engine.attach(el)
  if (eq) engine.setEq(true, EQ_PRESETS.flat)
  const nodes = chain(ctx.sources[0])
  return { ctx, engine, el, deck, nodes }
}

describe('the sound path', () => {
  it('is there when Web Audio is, and says so when it is not', () => {
    expect(made().engine.available).toBe(true)
    expect(createEngine(null).available).toBe(false)
    const refuses = function () {
      throw new Error('no audio here')
    }
    expect(createEngine(refuses).available).toBe(false)
  })

  it('goes deck level, fade, equalizer, preamp, volume, limiter, speakers', () => {
    const { nodes, el } = made()
    const kinds = nodes.map((n) => n.kind)
    // source, norm, fade, the meeting point, the bands, preamp, balance,
    // mono, volume, limiter, out
    expect(kinds).toEqual([
      'source', 'gain', 'gain', 'gain',
      ...EQ_BANDS.map(() => 'filter'),
      'gain', 'panner', 'gain', 'gain', 'limiter', 'destination',
    ])
    expect(nodes.slice(4, 14).map((f) => f.frequency.value)).toEqual(EQ_BANDS)
    expect(nodes[4].type).toBe('lowshelf')
    expect(nodes[13].type).toBe('highshelf')
    // The element plays at full level: every level is set in the graph.
    expect(el.volume).toBe(1)
  })

  it('leaves the equalizer out of the path while it is off, and puts it back', () => {
    vi.useFakeTimers()
    try {
      const { engine, ctx } = made({ eq: false })
      const kinds = () => chain(ctx.sources[0]).map((n) => n.kind)
      expect(engine.eqInPath).toBe(false)
      expect(kinds()).toEqual(['source', 'gain', 'gain', 'gain', 'gain', 'panner', 'gain', 'gain', 'limiter', 'destination'])
      engine.setEq(true, EQ_PRESETS.vocal)
      expect(kinds()).toContain('filter')
      // Off: flat at once, out of the path once it has settled there.
      engine.setEq(false, EQ_PRESETS.vocal)
      expect(engine.eqInPath).toBe(true)
      vi.advanceTimersByTime(300)
      expect(engine.eqInPath).toBe(false)
      expect(kinds()).not.toContain('filter')
      // Back on before it left: it stays.
      engine.setEq(true, EQ_PRESETS.vocal)
      engine.setEq(false, EQ_PRESETS.vocal)
      engine.setEq(true, EQ_PRESETS.vocal)
      vi.advanceTimersByTime(300)
      expect(engine.eqInPath).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('rests the audio thread after a long pause and wakes it to play', async () => {
    vi.useFakeTimers()
    try {
      const { engine, ctx } = made()
      engine.idleSoon(15000)
      vi.advanceTimersByTime(14000)
      expect(ctx.state).toBe('running')
      vi.advanceTimersByTime(2000)
      expect(ctx.state).toBe('suspended')
      await engine.resume()
      expect(ctx.state).toBe('running')
      // Played again before the time was up: never suspended.
      engine.idleSoon(15000)
      vi.advanceTimersByTime(5000)
      await engine.resume()
      vi.advanceTimersByTime(20000)
      expect(ctx.state).toBe('running')
    } finally {
      vi.useRealTimers()
    }
  })

  it('balances left and right, and mixes to one channel for mono', () => {
    const { engine, nodes } = made()
    const panner = nodes.find((n) => n.kind === 'panner')
    const mono = nodes[nodes.indexOf(panner) + 1]
    engine.setBalance(-0.4)
    expect(panner.pan.value).toBeCloseTo(-0.4)
    engine.setBalance(5)
    expect(panner.pan.value).toBe(1)
    expect(mono.channelCount).toBe(2)
    engine.setMono(true)
    expect(mono.channelCount).toBe(1)
    expect(mono.channelInterpretation).toBe('speakers')
    engine.setMono(false)
    expect(mono.channelCount).toBe(2)
  })

  it('draws the equalizer from the filters themselves, flat when it is off', () => {
    const { engine, ctx } = made({ eq: false })
    expect([...engine.eqResponse([100, 1000])]).toEqual([0, 0])
    engine.setEq(true, EQ_PRESETS.bass)
    // The fake filters answer +2 dB each at every frequency.
    for (const n of chain(ctx.sources[0]).filter((x) => x.kind === 'filter')) {
      n.getFrequencyResponse = (f, mag) => mag.fill(Math.pow(10, 2 / 20))
    }
    // The bands' shape, through the handles...
    expect(engine.eqResponse([100, 1000])[0]).toBeCloseTo(EQ_BANDS.length * 2, 1)
    // ...and what is heard, with the pre-amp: half the +6 dB boost taken back.
    expect(engine.eqResponse([100, 1000], true)[0]).toBeCloseTo(EQ_BANDS.length * 2 - 3, 1)
  })

  it('two decks meet at the same point before the equalizer', () => {
    const { ctx, engine, nodes } = made()
    engine.attach({ volume: 1 })
    const second = chain(ctx.sources[1])
    expect(second[3]).toBe(nodes[3])
  })

  it('makes room for an equalizer boost, and gives it back when off', () => {
    const { engine, nodes } = made()
    const bands = nodes.slice(4, 14)
    const preamp = nodes[14]
    engine.setEq(true, EQ_PRESETS.bass)
    expect(bands.map((b) => b.gain.value)).toEqual(EQ_PRESETS.bass)
    expect(preamp.gain.value).toBeCloseTo(Math.pow(10, -3 / 20), 3) // half of +6 dB taken back
    engine.setEq(false, EQ_PRESETS.bass)
    expect(bands.every((b) => b.gain.value === 0)).toBe(true)
    expect(preamp.gain.value).toBe(1)
  })

  it('keeps band gains inside the range the sliders allow', () => {
    const { engine, nodes } = made()
    engine.setEq(true, [40, -40, 0, 0, 0, 0, 0, 0, 0, 0])
    expect(nodes[4].gain.value).toBe(12)
    expect(nodes[5].gain.value).toBe(-12)
  })

  it('sets the listener volume after the equalizer, and a deck level and fade on the deck', async () => {
    const { engine, deck, nodes } = made()
    // The gain just before the limiter.
    const volume = nodes[nodes.findIndex((n) => n.kind === 'limiter') - 1]
    engine.setVolume(0.4)
    expect(volume.gain.value).toBe(0.4)
    engine.setVolume(3)
    expect(volume.gain.value).toBe(1)
    deck.setNorm(0.5)
    expect(nodes[1].gain.value).toBe(0.5)
    deck.setFade(0)
    await deck.fadeTo(1, 0)
    expect(nodes[2].gain.value).toBe(1)
  })

  it('a limiter that catches peaks: high ratio, fast attack, just under full scale', () => {
    const limiter = made().nodes.find((n) => n.kind === 'limiter')
    expect(limiter.ratio.value).toBeGreaterThanOrEqual(12)
    expect(limiter.threshold.value).toBeLessThan(0)
    expect(limiter.attack.value).toBeLessThan(0.01)
  })
})

describe('a fade that does not dip', () => {
  it('meets in the middle at about -3 dB each, so the sum stays level', () => {
    const out = fadeCurve(1, 0, 101)
    const into = fadeCurve(0, 1, 101)
    expect(out[0]).toBeCloseTo(1)
    expect(out[100]).toBeCloseTo(0)
    expect(into[0]).toBeCloseTo(0)
    expect(into[100]).toBeCloseTo(1)
    expect(out[50]).toBeCloseTo(Math.SQRT1_2, 2)
    expect(into[50]).toBeCloseTo(Math.SQRT1_2, 2)
    // Power, not amplitude, adds up to one all the way through.
    for (let i = 0; i <= 100; i += 10) expect(out[i] ** 2 + into[i] ** 2).toBeCloseTo(1, 2)
  })
})

describe('equalizer presets', () => {
  it('have a gain for every band, within what the sliders allow', () => {
    for (const [name, gains] of Object.entries(EQ_PRESETS)) {
      expect(gains, name).toHaveLength(EQ_BANDS.length)
      for (const g of gains) expect(Math.abs(g)).toBeLessThanOrEqual(12)
    }
    expect(EQ_PRESETS.flat.every((g) => g === 0)).toBe(true)
  })
})
