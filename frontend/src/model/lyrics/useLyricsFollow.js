// Keeping the line being sung in the middle of the lyrics view, and handing
// the scrolling to the user when they want to read ahead.

import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'

// How long the user's own scrolling wins before the view glides back to the
// line that is playing. The countdown runs whether or not playback is
// paused: "where am I?" should never need a second click.
export const RESUME_MS = 3000

/**
 * @param {object} o
 * @param {import('vue').Ref<HTMLElement|null>} o.container  the scroller
 * @param {import('vue').Ref<number>} o.active  index of the line playing
 * @param {() => unknown} o.lines  the lines, watched for a new song
 */
export function useLyricsFollow({ container, active, lines }) {
  const els = new Map()
  const suspended = ref(false)
  // Restarts the countdown animation on the "current line" pill.
  const suspendTick = ref(0)
  let autoScrolling = false
  let autoTimer = null
  let resumeTimer = null

  function setLineEl(el, idx) {
    if (el) els.set(idx, el)
    else els.delete(idx)
  }

  // Centre the line playing. `instant` on song changes and big jumps, so the
  // view never seems to lag behind the song.
  function scrollToActive(instant = false) {
    const el = els.get(active.value)
    const box = container.value
    if (!el || !box) return
    const top = el.offsetTop - box.clientHeight / 2 + el.clientHeight / 2
    autoScrolling = true
    box.scrollTo({ top, behavior: instant ? 'auto' : 'smooth' })
    clearTimeout(autoTimer)
    autoTimer = setTimeout(() => (autoScrolling = false), instant ? 60 : 450)
  }

  function resume() {
    suspended.value = false
    scrollToActive(false)
  }

  /** The user scrolled or moved through the lines: theirs for a while. */
  function hold() {
    if (autoScrolling) return
    suspended.value = true
    suspendTick.value++
    clearTimeout(resumeTimer)
    resumeTimer = setTimeout(resume, RESUME_MS)
  }

  function jumpToCurrent() {
    clearTimeout(resumeTimer)
    suspended.value = false
    scrollToActive(true)
  }

  watch(active, (idx, prev) => {
    if (suspended.value) return
    const instant = prev == null || Math.abs(idx - prev) > 2
    nextTick(() => scrollToActive(instant))
  })

  // A new song's lines: forget the old ones and land on the right place.
  watch(lines, () => {
    els.clear()
    clearTimeout(resumeTimer)
    suspended.value = false
    nextTick(() => scrollToActive(true))
  })

  // Opened mid-song: on the current line, not the top of the song.
  onMounted(() => nextTick(() => scrollToActive(true)))
  onBeforeUnmount(() => {
    clearTimeout(resumeTimer)
    clearTimeout(autoTimer)
  })

  return { setLineEl, suspended, suspendTick, hold, jumpToCurrent, scrollToActive }
}
