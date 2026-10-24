import { nextTick, ref } from 'vue'

// Appearance changes, made gently. The new look cross-fades over the old one
// instead of snapping, and the control that was clicked stays where it was
// under the pointer. A bigger typeface or interface size used to reflow the
// page and carry the button away while the pointer was still on it, and the
// whole screen seemed to jump.

const scroller = () => document.querySelector('.shell-main')
const reduced = () => {
  try {
    return matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}
const frame = () => new Promise((r) => requestAnimationFrame(() => r()))
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

/**
 * Remember where `anchor` is on screen; the function returned scrolls the page
 * so it is there again. `scale` is old size / new size, for a change of
 * interface size, where the same spot on screen is a different CSS pixel.
 */
function pin(anchor, scale = 1) {
  const el = scroller()
  if (!anchor || !anchor.isConnected || !el || !el.contains(anchor)) return () => {}
  const want = anchor.getBoundingClientRect().top * scale
  return () => {
    if (!anchor.isConnected) return
    const drift = anchor.getBoundingClientRect().top - want
    if (Math.abs(drift) > 0.5) el.scrollTop += drift
  }
}

// A typeface not used yet is fetched when it is first needed: the page is
// drawn in the fallback and then again in the face, a second jump.
async function fontsSettled(ms = 450) {
  if (!document.fonts || !document.fonts.ready) return
  await Promise.race([document.fonts.ready, wait(ms)])
}

/** A palette, light or dark, a typeface, an accent: cross-faded, kept in place. */
export function restyle(change, anchor = null) {
  if (typeof document === 'undefined') return Promise.resolve(change())
  const restore = pin(anchor)
  const run = async () => {
    change()
    await nextTick()
    await fontsSettled()
    restore()
  }
  if (typeof document.startViewTransition !== 'function' || reduced()) return run()
  try {
    return document.startViewTransition(run).finished.catch(() => {})
  } catch {
    return run()
  }
}

/**
 * From one page to another with what they share moving between them: an
 * element named the same on both (`view-transition-name`) travels from where
 * it was to where it is, and the rest cross-fades. `go` changes the page and
 * resolves once it has.
 */
/**
 * True while a page change is being carried by the browser (travel): the
 * pages' own fade steps aside, swapping at once. It is timed with frames, and
 * the browser holds frames back while it captures, so the swap stalled.
 */
export const traveling = ref(false)

export function travel(go, arrived = () => true) {
  if (
    typeof document === 'undefined' ||
    typeof document.startViewTransition !== 'function' ||
    reduced() ||
    document.visibilityState !== 'visible'
  ) {
    return Promise.resolve(go())
  }
  traveling.value = true
  try {
    return document
      // The new page is waited for, so what is captured is the page arrived
      // at. Timers, not frames: the browser holds frames back meanwhile.
      .startViewTransition(async () => {
        await go()
        await nextTick()
        for (let waited = 0; !arrived() && waited < 900; waited += 25) await wait(25)
      })
      .finished.catch(() => {})
      .finally(() => {
        traveling.value = false
      })
  } catch {
    traveling.value = false
    return Promise.resolve(go())
  }
}

/**
 * The interface size. The window's zoom changes every measurement on the page
 * at once, which a cross-fade cannot span, so the page dips out for a moment
 * and comes back at the new size with the control where it was.
 */
export async function resize(change, from, to, anchor = null) {
  const restore = pin(anchor, from && to ? from / to : 1)
  const root = document.documentElement
  const animate = !reduced()
  if (animate) {
    root.classList.add('is-resizing')
    await wait(120)
  }
  const resized = new Promise((resolve) => {
    let done = false
    const finish = () => {
      if (done) return
      done = true
      window.removeEventListener('resize', finish)
      resolve()
    }
    window.addEventListener('resize', finish)
    setTimeout(finish, 450)
  })
  change()
  await resized
  await frame()
  restore()
  if (animate) {
    await frame()
    root.classList.remove('is-resizing')
  }
}
