import { ref } from 'vue'
import { isDesktop } from '/src/desktop/bridge'
import { useLibrary } from '/src/model/library'

// The first time Dannify opens after a fresh install, a short walk through
// the three choices worth making up front: how it looks, where saved music
// goes, and signing in to YouTube Music. Skippable at every step, and
// shown once.
//
// Never after an update. Every copy that has run before has its version in
// storage (api.js writes it on each start), so that is checked here, while
// the app is still loading and before this run has written anything. A
// library that already has songs in it is not a first run either, whatever
// storage says (a reset web profile, say).

const KEY = 'dannify-onboarded'

function read(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Blocked storage: it may be shown once more, which is harmless.
  }
}

const firstRun = isDesktop && !read(KEY) && !read('version')
const show = ref(false)

export function startOnboarding() {
  if (!firstRun) {
    if (!read(KEY)) write(KEY, '1')
    return
  }
  const library = useLibrary()
  Promise.resolve(library.ensureLoaded())
    .catch(() => {})
    .then(() => {
      if (library.tracks.value.length > 0) {
        write(KEY, '1')
        return
      }
      show.value = true
    })
}

export function finishOnboarding() {
  show.value = false
  write(KEY, '1')
}

export function useOnboarding() {
  return { show, finish: finishOnboarding }
}
