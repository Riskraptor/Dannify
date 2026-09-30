import { ref, watch } from 'vue'
import { usePlayer } from '/src/model/player'
import { useTheme } from '/src/model/theme'

// "Match the artwork": the accent colour follows the song that is playing.
//
// The colour is the most vivid hue in the cover, not its average (the average
// of most covers is a muddy brown), and it is then lightened or darkened until
// it reads on the palette underneath: at least 4.5:1 against the panel, the
// same bar the fixed palettes are held to for anything that carries text. A
// cover with no real colour in it (black and white, a grey photo) leaves the
// palette's own accent alone.

const KEY = 'dn.accentFromArt'

function readPref() {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export const accentFromArt = ref(readPref())

export function setAccentFromArt(on) {
  accentFromArt.value = !!on
  try {
    localStorage.setItem(KEY, on ? '1' : '0')
  } catch {
    // ignore
  }
}

const VARS = ['--c-accent', '--c-accent-hover', '--c-accent-fg']

function clearAccent() {
  const style = document.documentElement.style
  for (const v of VARS) style.removeProperty(v)
}

// ----- colour arithmetic -------------------------------------------------------

function luminance([r, g, b]) {
  const ch = (v) => {
    v /= 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
}

export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

function toHsl([r, g, b]) {
  r /= 255
  g /= 255
  b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h
  if (max === r) h = (g - b) / d + (g < b ? 6 : 0)
  else if (max === g) h = (b - r) / d + 2
  else h = (r - g) / d + 4
  return [h / 6, s, l]
}

function toRgb([h, s, l]) {
  if (s === 0) return [l, l, l].map((v) => Math.round(v * 255))
  const hue = (p, q, t) => {
    if (t < 0) t += 1
    if (t > 1) t -= 1
    if (t < 1 / 6) return p + (q - p) * 6 * t
    if (t < 1 / 2) return q
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
    return p
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  return [hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)].map((v) => Math.round(v * 255))
}

/** The most vivid hue in a set of RGB pixels, or null when there is none. */
export function vividColour(pixels) {
  const buckets = new Array(12).fill(null).map(() => ({ w: 0, r: 0, g: 0, b: 0 }))
  for (const [r, g, b] of pixels) {
    const [h, s, l] = toHsl([r, g, b])
    if (s < 0.28 || l < 0.12 || l > 0.9) continue
    const w = s * (1 - Math.abs(l - 0.5) * 1.4)
    const bucket = buckets[Math.min(11, Math.floor(h * 12))]
    bucket.w += w
    bucket.r += r * w
    bucket.g += g * w
    bucket.b += b * w
  }
  const best = buckets.reduce((a, c) => (c.w > a.w ? c : a))
  // A few stray coloured pixels in a grey cover are not its colour.
  if (best.w < pixels.length * 0.04) return null
  return [best.r / best.w, best.g / best.w, best.b / best.w].map(Math.round)
}

/** Nudge *colour* until it reads on *surface*; returns accent, hover, text-on. */
export function fitAccent(colour, surface, dark) {
  let [h, s, l] = toHsl(colour)
  s = Math.max(s, 0.55)
  let rgb = toRgb([h, s, l])
  for (let i = 0; i < 40 && contrast(rgb, surface) < 4.5; i++) {
    l = dark ? Math.min(0.92, l + 0.02) : Math.max(0.08, l - 0.02)
    rgb = toRgb([h, s, l])
  }
  const hover = toRgb([h, s, dark ? Math.min(0.95, l + 0.07) : Math.max(0.05, l - 0.06)])
  const onDark = [12, 12, 16]
  const onLight = [255, 255, 255]
  const fg = contrast(onDark, rgb) >= contrast(onLight, rgb) ? onDark : onLight
  return { accent: rgb, hover, fg }
}

// ----- reading a cover ---------------------------------------------------------

function samplePixels(url) {
  return new Promise((resolve) => {
    const img = new Image()
    // Covers from YouTube's image hosts are shared with any page; without
    // this the canvas below refuses to be read.
    if (/^https?:/.test(url)) img.crossOrigin = 'anonymous'
    img.decoding = 'async'
    img.onload = () => {
      try {
        const size = 28
        const canvas = document.createElement('canvas')
        canvas.width = size
        canvas.height = size
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        ctx.drawImage(img, 0, 0, size, size)
        const data = ctx.getImageData(0, 0, size, size).data
        const out = []
        for (let i = 0; i < data.length; i += 4) {
          if (data[i + 3] > 200) out.push([data[i], data[i + 1], data[i + 2]])
        }
        resolve(out)
      } catch {
        resolve(null) // a cover that cannot be read: keep the palette's own
      }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}

function panelColour() {
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--c-panel')
  const parts = raw.trim().split(/\s+/).map(Number)
  return parts.length === 3 && parts.every(Number.isFinite) ? parts : [18, 18, 21]
}

let started = false
let seq = 0

export function startArtAccent() {
  if (started || typeof window === 'undefined') return
  started = true
  const player = usePlayer()
  const theme = useTheme()

  async function update() {
    const mine = ++seq
    const track = player.currentTrack.value
    const url = accentFromArt.value && track ? track.cover : ''
    if (!url) {
      clearAccent()
      return
    }
    const pixels = await samplePixels(url)
    if (mine !== seq) return // the song moved on while this one was read
    const colour = pixels && pixels.length ? vividColour(pixels) : null
    if (!colour) {
      clearAccent()
      return
    }
    // The palette's own panel, measured with any artwork accent taken off.
    clearAccent()
    const fit = fitAccent(colour, panelColour(), theme.currentMode.value === 'dark')
    const style = document.documentElement.style
    style.setProperty('--c-accent', fit.accent.join(' '))
    style.setProperty('--c-accent-hover', fit.hover.join(' '))
    style.setProperty('--c-accent-fg', fit.fg.join(' '))
  }

  watch(
    [
      accentFromArt,
      () => player.currentTrack.value && player.currentTrack.value.cover,
      () => theme.currentTheme.value,
    ],
    update,
    { immediate: true }
  )
}
