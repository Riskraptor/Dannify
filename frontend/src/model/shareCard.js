// Your Soundtrack as a picture to share: 1080 by 1350, the shape Instagram
// and WhatsApp show whole. Drawn on a canvas in the story's own colours, with
// the minutes, the top artist's photo and the top songs and artists, so it
// can be copied and pasted anywhere or saved in Pictures.
//
// Covers come from Google's image servers, which allow a page to draw them
// (they send Access-Control-Allow-Origin), and from the app itself; one that
// will not load is drawn as a letter instead, never left out with a gap.

import logo from '/src/assets/dannify.svg'

export const WIDTH = 1080
export const HEIGHT = 1350

// A picture that has not come in a few seconds is drawn as a letter: a
// request left hanging must never hold the card back.
function loadImage(src, ms = 6000) {
  return new Promise((resolve) => {
    if (!src) return resolve(null)
    const img = new Image()
    const timer = setTimeout(() => resolve(null), ms)
    img.crossOrigin = 'anonymous'
    img.decoding = 'async'
    img.onload = () => {
      clearTimeout(timer)
      resolve(img)
    }
    img.onerror = () => {
      clearTimeout(timer)
      resolve(null)
    }
    img.src = src
  })
}

function fit(ctx, text, width) {
  let s = String(text || '')
  if (ctx.measureText(s).width <= width) return s
  while (s.length > 1 && ctx.measureText(s + '…').width > width) s = s.slice(0, -1)
  return s.trimEnd() + '…'
}

function font(weight, size, family) {
  return `${weight} ${size}px ${family}`
}

/**
 * @param {object} card
 * @param {string} card.title       e.g. "Your 2026 Soundtrack"
 * @param {string} card.eyebrow     e.g. "Your Soundtrack"
 * @param {number} card.hue         the story's colour turn, in degrees
 * @param {string} card.minutes     the minutes, written in the app's language
 * @param {string} card.minutesUnit "minutes of music"
 * @param {{name: string, picture: string}|null} card.artist
 * @param {string[]} card.songs     top songs' titles
 * @param {string[]} card.artists   top artists' names
 * @param {{topArtist: string, topSongs: string, topArtists: string, footer: string}} card.words
 * @returns {Promise<Blob>} a PNG
 */
export async function drawCard(card) {
  const canvas = document.createElement('canvas')
  canvas.width = WIDTH
  canvas.height = HEIGHT
  const ctx = canvas.getContext('2d')
  const family = getComputedStyle(document.body).fontFamily || 'system-ui, sans-serif'
  try {
    await Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 1500))])
  } catch {
    // drawn in whatever font there is
  }
  const [picture, mark] = await Promise.all([loadImage(card.artist && card.artist.picture), loadImage(logo)])

  // The story's colours, turned to this story's own.
  const bg = ctx.createLinearGradient(0, 0, WIDTH, HEIGHT)
  bg.addColorStop(0, '#2b0d4a')
  bg.addColorStop(0.4, '#6b1d6e')
  bg.addColorStop(0.75, '#c2185b')
  bg.addColorStop(1, '#ff6f3c')
  ctx.save()
  ctx.filter = `hue-rotate(${Number(card.hue) || 0}deg)`
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, WIDTH, HEIGHT)
  ctx.restore()
  for (const [x, y, r, a] of [
    [180, 220, 620, 0.2],
    [960, 1180, 560, 0.16],
  ]) {
    const glow = ctx.createRadialGradient(x, y, 0, x, y, r)
    glow.addColorStop(0, `rgba(255,255,255,${a})`)
    glow.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = glow
    ctx.fillRect(0, 0, WIDTH, HEIGHT)
  }

  const M = 72
  ctx.fillStyle = '#fff'
  ctx.textBaseline = 'alphabetic'

  // The name and the title, along the top.
  if (mark) ctx.drawImage(mark, M, 62, 60, 60)
  ctx.font = font(800, 44, family)
  ctx.fillText('Dannify', M + (mark ? 76 : 0), 108)
  ctx.textAlign = 'right'
  ctx.font = font(700, 30, family)
  ctx.globalAlpha = 0.85
  ctx.fillText(fit(ctx, card.title, 560), WIDTH - M, 104)
  ctx.globalAlpha = 1

  // The minutes, large.
  ctx.textAlign = 'center'
  ctx.font = font(800, 28, family)
  ctx.globalAlpha = 0.8
  ctx.fillText(String(card.eyebrow || '').toUpperCase(), WIDTH / 2, 206)
  ctx.globalAlpha = 1
  ctx.font = font(900, 168, family)
  ctx.fillText(fit(ctx, card.minutes, WIDTH - 2 * M), WIDTH / 2, 370)
  ctx.font = font(700, 40, family)
  ctx.fillText(fit(ctx, card.minutesUnit, WIDTH - 2 * M), WIDTH / 2, 430)

  // The top artist, round, ringed in white.
  if (card.artist) {
    const r = 140
    const cx = WIDTH / 2
    const cy = 620
    ctx.save()
    ctx.shadowColor = 'rgba(0,0,0,0.35)'
    ctx.shadowBlur = 40
    ctx.shadowOffsetY = 16
    ctx.beginPath()
    ctx.arc(cx, cy, r + 8, 0, Math.PI * 2)
    ctx.fillStyle = '#fff'
    ctx.fill()
    ctx.restore()
    ctx.save()
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.clip()
    if (picture) {
      const s = Math.min(picture.naturalWidth, picture.naturalHeight)
      ctx.drawImage(picture, (picture.naturalWidth - s) / 2, (picture.naturalHeight - s) / 2, s, s, cx - r, cy - r, 2 * r, 2 * r)
    } else {
      ctx.fillStyle = 'rgba(255,255,255,0.22)'
      ctx.fillRect(cx - r, cy - r, 2 * r, 2 * r)
      ctx.fillStyle = '#fff'
      ctx.font = font(900, 120, family)
      ctx.textBaseline = 'middle'
      ctx.fillText(Array.from(card.artist.name || '?')[0].toUpperCase(), cx, cy + 6)
      ctx.textBaseline = 'alphabetic'
    }
    ctx.restore()
    ctx.fillStyle = '#fff'
    ctx.font = font(800, 26, family)
    ctx.globalAlpha = 0.78
    ctx.fillText(String(card.words.topArtist || '').toUpperCase(), cx, 830)
    ctx.globalAlpha = 1
    ctx.font = font(900, 64, family)
    ctx.fillText(fit(ctx, card.artist.name, WIDTH - 2 * M), cx, 900)
  }

  // Top songs and top artists, side by side.
  ctx.textAlign = 'left'
  const columns = [
    [M, card.words.topSongs, card.songs],
    [WIDTH / 2 + 20, card.words.topArtists, card.artists],
  ]
  const colWidth = WIDTH / 2 - M - 20
  for (const [x, label, items] of columns) {
    ctx.font = font(800, 24, family)
    ctx.globalAlpha = 0.75
    ctx.fillText(String(label || '').toUpperCase(), x, 990)
    ctx.globalAlpha = 1
    ;(items || []).slice(0, 5).forEach((item, i) => {
      const y = 1044 + i * 46
      ctx.font = font(900, 30, family)
      ctx.globalAlpha = 0.7
      ctx.fillText(String(i + 1), x, y)
      ctx.globalAlpha = 1
      ctx.font = font(700, 30, family)
      ctx.fillText(fit(ctx, item, colWidth - 44), x + 40, y)
    })
  }

  // A line to finish.
  ctx.textAlign = 'center'
  ctx.font = font(700, 26, family)
  ctx.globalAlpha = 0.8
  ctx.fillText(fit(ctx, card.words.footer, WIDTH - 2 * M), WIDTH / 2, HEIGHT - 52)
  ctx.globalAlpha = 1

  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('no picture'))), 'image/png')
  )
}

/** The picture on the clipboard, to paste into a chat or a post. */
export async function copyCard(blob) {
  await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
}

/** The picture as base64, for saving through the app (POST /api/share/image). */
export function toBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}
