import { ref, watch, onUnmounted } from 'vue'

// Loading states that are honest about how long they last.
//
// Now that a track resolves in about a third of a second instead of fifteen,
// most loads finish before a skeleton has finished fading in. Showing one
// anyway reads as a glitch: a grey flash, then content. Hiding it entirely is
// worse for the slow cases.
//
// So: wait a beat before admitting we are loading at all, and once we have
// admitted it, stay admitted long enough to look deliberate.

const SHOW_AFTER_MS = 180 // below this, the user perceives it as instant
const KEEP_FOR_MS = 340 // once shown, never flash away faster than this

export function useDeferred(source, options = {}) {
  const showAfter = options.showAfter ?? SHOW_AFTER_MS
  const keepFor = options.keepFor ?? KEEP_FOR_MS

  const visible = ref(false)
  let showTimer = null
  let shownAt = 0
  let hideTimer = null

  function clearTimers() {
    if (showTimer) {
      clearTimeout(showTimer)
      showTimer = null
    }
    if (hideTimer) {
      clearTimeout(hideTimer)
      hideTimer = null
    }
  }

  watch(
    source,
    (busy) => {
      clearTimers()
      if (busy) {
        if (visible.value) return // already up, leave it alone
        showTimer = setTimeout(() => {
          visible.value = true
          shownAt = Date.now()
          showTimer = null
        }, showAfter)
        return
      }
      if (!visible.value) return // finished before we ever showed it
      const owed = keepFor - (Date.now() - shownAt)
      if (owed <= 0) {
        visible.value = false
        return
      }
      hideTimer = setTimeout(() => {
        visible.value = false
        hideTimer = null
      }, owed)
    },
    { immediate: true },
  )

  onUnmounted(clearTimers)

  return visible
}
