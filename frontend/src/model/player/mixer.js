import { ref } from 'vue'
import { EQ_PRESETS, EQ_BANDS } from '/src/model/audioEngine'
import { audio, cancelTransition, engine } from '/src/model/player/decks'
import { readStored, storeSetting } from '/src/model/player/state'
import { setPlaybackRate } from '/src/model/player/transport'

// --- Crossfade, gapless, equalizer: the sound engine's settings ---
const CROSSFADE_KEY = 'dannify-crossfade'
const GAPLESS_KEY = 'dannify-gapless'
const EQ_KEY = 'dannify-eq'
export const crossfade = ref(Math.max(0, Math.min(12, Number(readStored(CROSSFADE_KEY)) || 0)))
export const gapless = ref(readStored(GAPLESS_KEY) !== '0')
export const eq = ref(readEq())

function readEq() {
  try {
    const v = JSON.parse(readStored(EQ_KEY) || 'null')
    if (v && Array.isArray(v.gains) && v.gains.length === EQ_BANDS.length) {
      const preamp = typeof v.preamp === 'number' && Number.isFinite(v.preamp) ? v.preamp : 'auto'
      return { on: !!v.on, preset: String(v.preset || 'custom'), gains: v.gains.map((g) => Number(g) || 0), preamp }
    }
  } catch {
    // a damaged setting: start flat
  }
  return { on: false, preset: 'flat', gains: [...EQ_PRESETS.flat], preamp: 'auto' }
}
export function applyEq() {
  if (engine) engine.setEq(eq.value.on, eq.value.gains, eq.value.preamp === 'auto' ? null : eq.value.preamp)
}
function setEq(next) {
  eq.value = next
  storeSetting(EQ_KEY, JSON.stringify(next))
  applyEq()
}
export function setEqEnabled(on) {
  setEq({ ...eq.value, on: !!on })
}
export function setEqPreset(name) {
  const own = String(name).startsWith('user:') ? eqUserPresets.value.find((p) => 'user:' + p.name === name) : null
  const gains = own ? own.gains : EQ_PRESETS[name]
  if (!gains) return
  setEq({ ...eq.value, on: true, preset: name, gains: [...gains] })
}
export function setEqBand(index, db) {
  if (index < 0 || index >= EQ_BANDS.length) return
  const gains = [...eq.value.gains]
  gains[index] = Math.max(-12, Math.min(12, Math.round(Number(db) * 2) / 2 || 0))
  setEq({ ...eq.value, on: true, preset: 'custom', gains })
}
/** 'auto' (half the biggest boost taken back) or dB, -12 to +12. */
export function setEqPreamp(v) {
  const preamp = v === 'auto' ? 'auto' : Math.max(-12, Math.min(12, Math.round(Number(v) * 2) / 2 || 0))
  setEq({ ...eq.value, preamp })
}

// Equalizer settings of the listener's own, by name.
const EQ_USER_KEY = 'dannify-eq-user'
const EQ_USER_MAX = 12
export const eqUserPresets = ref((() => {
  try {
    const v = JSON.parse(readStored(EQ_USER_KEY) || '[]')
    return Array.isArray(v)
      ? v.filter((p) => p && p.name && Array.isArray(p.gains) && p.gains.length === EQ_BANDS.length).slice(0, EQ_USER_MAX)
      : []
  } catch {
    return []
  }
})())
export function saveEqPreset(name) {
  const clean = String(name || '').trim().slice(0, 40)
  if (!clean) return false
  const list = eqUserPresets.value.filter((p) => p.name !== clean)
  list.unshift({ name: clean, gains: [...eq.value.gains] })
  eqUserPresets.value = list.slice(0, EQ_USER_MAX)
  storeSetting(EQ_USER_KEY, JSON.stringify(eqUserPresets.value))
  setEq({ ...eq.value, preset: 'user:' + clean })
  return true
}
export function deleteEqPreset(name) {
  eqUserPresets.value = eqUserPresets.value.filter((p) => p.name !== name)
  storeSetting(EQ_USER_KEY, JSON.stringify(eqUserPresets.value))
  if (eq.value.preset === 'user:' + name) setEq({ ...eq.value, preset: 'custom' })
}

// Listening speed, kept between runs, and whether the pitch stays put.
const SPEED_KEY = 'dannify-speed'
const PITCH_KEY = 'dannify-keep-pitch'
export const speed = ref(Math.max(0.5, Math.min(2, Number(readStored(SPEED_KEY)) || 1)))
export const keepPitch = ref(readStored(PITCH_KEY) !== '0')
export function setSpeed(v) {
  speed.value = Math.max(0.5, Math.min(2, Math.round((Number(v) || 1) * 20) / 20))
  storeSetting(SPEED_KEY, String(speed.value))
  setPlaybackRate(speed.value)
}
export function setKeepPitch(on) {
  keepPitch.value = !!on
  storeSetting(PITCH_KEY, on ? '1' : '0')
  if (audio) {
    try {
      audio.preservesPitch = keepPitch.value
    } catch {
      // not supported here
    }
  }
}
/** Back to the listener's own speed (after the lyrics editor's slow motion). */
export function restoreSpeed() {
  setPlaybackRate(speed.value)
}
/** The output's spectrum into `out` (dB per bin); false without the engine. */
export function spectrum(out) {
  return engine && typeof engine.spectrum === 'function' ? engine.spectrum(out) : false
}
export function spectrumInfo() {
  return engine ? { bins: engine.bins || 0, sampleRate: engine.sampleRate || 48000 } : { bins: 0, sampleRate: 48000 }
}
export function setCrossfade(seconds) {
  crossfade.value = Math.max(0, Math.min(12, Math.round(Number(seconds) || 0)))
  storeSetting(CROSSFADE_KEY, String(crossfade.value))
  cancelTransition()
}
export function setGapless(on) {
  gapless.value = !!on
  storeSetting(GAPLESS_KEY, on ? '1' : '0')
  cancelTransition()
}

// Balance and mono (the sound engine's; see audioEngine.js).
const BALANCE_KEY = 'dannify-balance'
const MONO_KEY = 'dannify-mono'
export const balance = ref(Math.max(-1, Math.min(1, Number(readStored(BALANCE_KEY)) || 0)))
export const mono = ref(readStored(MONO_KEY) === '1')
export function setBalance(v) {
  balance.value = Math.max(-1, Math.min(1, Math.round((Number(v) || 0) * 100) / 100))
  storeSetting(BALANCE_KEY, String(balance.value))
  if (engine) engine.setBalance(balance.value)
}
export function setMono(on) {
  mono.value = !!on
  storeSetting(MONO_KEY, on ? '1' : '0')
  if (engine) engine.setMono(mono.value)
}
/** The equalizer's response at `freqs`, in dB, for drawing it. */
export function eqCurve(freqs) {
  return engine && typeof engine.eqResponse === 'function' ? engine.eqResponse(freqs) : new Float32Array(freqs.length)
}
