import { onMounted, onBeforeUnmount, onActivated, onDeactivated } from 'vue'

// Listen to a window event only while the calling view is on screen (views
// are kept alive in the background and must not react there).
//
// With `catchUp`, an event that arrived while the view was away is acted on
// once when it comes back. Without it, a kept-alive view slept through every
// change: open an artist while their first song was still downloading, go
// somewhere else, come back, and the page still showed the half-finished
// song, no album and no picture, until the app was restarted.
export function useActiveWindowEvent(name, fn, { catchUp = false } = {}) {
  let active = false
  let missed = null
  const handler = (e) => {
    if (active) fn(e)
    else if (catchUp) missed = e
  }
  onMounted(() => {
    active = true
    window.addEventListener(name, handler)
  })
  onActivated(() => {
    active = true
    if (missed) {
      const e = missed
      missed = null
      fn(e)
    }
  })
  onDeactivated(() => {
    active = false
  })
  onBeforeUnmount(() => {
    active = false
    missed = null
    window.removeEventListener(name, handler)
  })
}

// F5 / Ctrl+R refreshes the visible view's data: never the whole app.
export function onRefresh(fn) {
  useActiveWindowEvent('dannify:refresh', fn)
}

// The on-disk library changed (download finished, file deleted, …). A view
// that was in the background when it happened catches up when it returns.
export function onLibraryChanged(fn) {
  useActiveWindowEvent('dannify:library-changed', fn, { catchUp: true })
}
