// Small copies of saved songs' artwork, made once and kept.
//
// A saved song's cover is the picture it came with, often 544 or 1200 pixels
// across, and a list draws it at 40. Every row fetched the whole picture,
// which the app decrypts out of the song, and the window decoded all of it
// to show a postage stamp. The first time a cover is drawn small, a copy of
// the size it is drawn at is made here and kept in the window's own cache;
// from then on that is what every list shows, without asking the app at all.
//
// Only for saved songs' covers (/cover?...), only where the window keeps a
// cache (a page opened from another device over plain http has none), and
// never in the way: anything that goes wrong falls back to the picture.

const CACHE_NAME = 'dn-thumbs-1'
// The sizes made, in device pixels. A cover drawn larger than the biggest is
// drawn from the original.
const SIZES = [96, 192, 320]
const PARALLEL = 3
// Object URLs kept in memory, oldest first.
const MEMORY = 600
// Past this many kept copies, the oldest are let go.
const KEEP = 6000

const supported =
  typeof window !== 'undefined' &&
  typeof caches !== 'undefined' &&
  typeof createImageBitmap === 'function' &&
  window.isSecureContext !== false

const memory = new Map()
const pending = new Map()
const waiting = []
let running = 0

/** The size of copy to make for a cover drawn *px* CSS pixels wide, or 0. */
export function thumbSize(px) {
  const ratio = (typeof window !== 'undefined' && window.devicePixelRatio) || 1
  const want = Math.ceil(px * ratio)
  return SIZES.find((s) => s >= want) || 0
}

/** Whether a small copy can stand in for *src* drawn at *px*. */
export function canThumb(src, px) {
  return supported && px > 0 && typeof src === 'string' && src.startsWith('/cover?') && thumbSize(px) > 0
}

function keyOf(src, size) {
  return `${size}:${src}`
}

/** The copy already in memory, so a redraw does not flash. */
export function thumbNow(src, px) {
  const url = memory.get(keyOf(src, thumbSize(px)))
  return url || ''
}

function remember(key, url) {
  memory.delete(key)
  memory.set(key, url)
  while (memory.size > MEMORY) {
    const [oldKey, oldUrl] = memory.entries().next().value
    memory.delete(oldKey)
    URL.revokeObjectURL(oldUrl)
  }
}

function turn() {
  if (running < PARALLEL) {
    running++
    return Promise.resolve()
  }
  return new Promise((resolve) => waiting.push(resolve))
}

function done() {
  const next = waiting.shift()
  if (next) next()
  else running--
}

async function shrink(blob, size) {
  const bitmap = await createImageBitmap(blob)
  try {
    const side = Math.min(bitmap.width, bitmap.height)
    // Already about the size it is drawn at: nothing to gain.
    if (!side || side <= size * 1.15) return blob
    // The middle square: what a cover drawn with object-fit: cover shows.
    const sx = (bitmap.width - side) / 2
    const sy = (bitmap.height - side) / 2
    const canvas =
      typeof OffscreenCanvas === 'function'
        ? new OffscreenCanvas(size, size)
        : Object.assign(document.createElement('canvas'), { width: size, height: size })
    const ctx = canvas.getContext('2d')
    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(bitmap, sx, sy, side, side, 0, 0, size, size)
    if (canvas.convertToBlob) return await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.86 })
    return await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.86))
  } finally {
    bitmap.close?.()
  }
}

async function make(src, size, key) {
  const cache = await caches.open(CACHE_NAME)
  // A name in the cache, never fetched: the copy is made here.
  const id = new Request(`${location.origin}/__thumbs/${size}/${encodeURIComponent(src)}`)
  let blob = null
  const hit = await cache.match(id)
  if (hit) {
    blob = await hit.blob()
  } else {
    await turn()
    try {
      const res = await fetch(src)
      // Not there, or not a picture: the original is tried as before, and
      // whatever stands in for a missing one takes over from there.
      if (!res.ok || !String(res.headers.get('Content-Type') || '').startsWith('image/')) return ''
      blob = await shrink(await res.blob(), size)
      if (blob) cache.put(id, new Response(blob, { headers: { 'Content-Type': blob.type || 'image/jpeg' } })).catch(() => {})
    } finally {
      done()
    }
  }
  if (!blob) return ''
  const url = URL.createObjectURL(blob)
  remember(key, url)
  return url
}

/**
 * An object URL for a small copy of *src* drawn at *px*, made if need be.
 * Resolves to '' when there is none to be had: draw *src* itself then.
 */
export function thumbnail(src, px) {
  if (!canThumb(src, px)) return Promise.resolve('')
  const size = thumbSize(px)
  const key = keyOf(src, size)
  const known = memory.get(key)
  if (known) {
    remember(key, known)
    return Promise.resolve(known)
  }
  if (!pending.has(key)) {
    pending.set(
      key,
      make(src, size, key)
        .catch(() => '')
        .finally(() => pending.delete(key))
    )
  }
  return pending.get(key)
}

// --- Only for what is on screen ----------------------------------------------

let observer = null
const watched = new Map()

function nearScreen(el) {
  const box = el.getBoundingClientRect()
  return box.bottom > -400 && box.top < window.innerHeight + 400 && box.width > 0
}

// The observer only reports when the window draws a frame. A page in a
// window nobody can see draws none, and one that has just been shown can
// take a moment; a cover on screen is not left blank on that account.
let fallbackTimer = null
function checkByHand() {
  fallbackTimer = null
  if (document.visibilityState !== 'visible') return
  for (const [el, run] of [...watched]) {
    if (!el.isConnected) {
      watched.delete(el)
      continue
    }
    if (nearScreen(el)) {
      watched.delete(el)
      observer?.unobserve(el)
      run()
    }
  }
}
function scheduleCheck() {
  if (!fallbackTimer) fallbackTimer = setTimeout(checkByHand, 1500)
}

/** Call *fn* once, when *el* comes near the screen. Returns a way to stop. */
export function whenVisible(el, fn) {
  if (!el || typeof IntersectionObserver !== 'function') {
    fn()
    return () => {}
  }
  scheduleCheck()
  if (!observer) {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          const run = watched.get(entry.target)
          watched.delete(entry.target)
          observer.unobserve(entry.target)
          run?.()
        }
      },
      { rootMargin: '400px' }
    )
  }
  watched.set(el, fn)
  observer.observe(el)
  return () => {
    watched.delete(el)
    observer.unobserve(el)
  }
}

// --- Housekeeping --------------------------------------------------------------

/** Forget every copy (Settings, clear caches). */
export async function clearThumbs() {
  for (const url of memory.values()) URL.revokeObjectURL(url)
  memory.clear()
  if (supported) await caches.delete(CACHE_NAME).catch(() => false)
}

/** Let the oldest copies go once there are many. */
export async function pruneThumbs() {
  if (!supported) return
  try {
    const cache = await caches.open(CACHE_NAME)
    const keys = await cache.keys()
    if (keys.length <= KEEP) return
    await Promise.all(keys.slice(0, keys.length - Math.floor(KEEP * 0.8)).map((k) => cache.delete(k)))
  } catch {
    // Housekeeping only.
  }
}

if (supported) {
  // Some time after start, when nothing else is going on.
  setTimeout(() => {
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 0))
    idle(() => pruneThumbs())
  }, 60_000)
}
