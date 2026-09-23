import { onMounted, onBeforeUnmount, onActivated, onDeactivated } from 'vue'

// Listen to a window event only while the calling view is on screen (views
// are kept alive in the background and must not react there).
export function useActiveWindowEvent(name, fn) {
  let active = false
  const handler = (e) => {
    if (active) fn(e)
  }
  onMounted(() => {
    active = true
    window.addEventListener(name, handler)
  })
  onActivated(() => {
    active = true
  })
  onDeactivated(() => {
    active = false
  })
  onBeforeUnmount(() => {
    active = false
    window.removeEventListener(name, handler)
  })
}

// F5 / Ctrl+R refreshes the visible view's data: never the whole app.
export function onRefresh(fn) {
  useActiveWindowEvent('dannify:refresh', fn)
}

// The on-disk library changed (download finished, file deleted, …).
export function onLibraryChanged(fn) {
  useActiveWindowEvent('dannify:library-changed', fn)
}
