import { ref } from 'vue'
import router from '/src/router'
import { travel } from '/src/model/smoothChange'

// Now Playing, the big player: opened from the player bar's cover, its title,
// its expand button, Ctrl+E or the command palette, and always the same way,
// the cover growing from the bar into the page and shrinking back.

const SEEN_KEY = 'dn.npSeen'

function readSeen() {
  try {
    return localStorage.getItem(SEEN_KEY) === '1'
  } catch {
    return false
  }
}

/** Whether Now Playing has ever been opened here: until then, the bar says how. */
export const nowPlayingSeen = ref(readSeen())

function markSeen() {
  if (nowPlayingSeen.value) return
  nowPlayingSeen.value = true
  try {
    localStorage.setItem(SEEN_KEY, '1')
  } catch {
    // remembered for this run only
  }
}

const onIt = () => router.currentRoute.value.name === 'NowPlaying'
// Its cover on screen, or gone from it: what the move waits for.
const coverShown = () => !!document.querySelector('.np-cover-wrap')

export function openNowPlaying() {
  markSeen()
  if (onIt()) return Promise.resolve()
  return travel(() => router.push({ name: 'NowPlaying' }), coverShown)
}

// Going back is not a promise: the page has changed once the router says so.
function afterNavigation() {
  return new Promise((resolve) => {
    let stop = () => {}
    const timer = setTimeout(() => {
      stop()
      resolve()
    }, 800)
    stop = router.afterEach(() => {
      clearTimeout(timer)
      stop()
      resolve()
    })
  })
}

export function closeNowPlaying() {
  if (!onIt()) return Promise.resolve()
  return travel(
    () => {
      if (!(window.history.state && window.history.state.back)) return router.push({ name: 'Home' })
      const done = afterNavigation()
      router.back()
      return done
    },
    () => !coverShown()
  )
}

export function toggleNowPlaying() {
  return onIt() ? closeNowPlaying() : openNowPlaying()
}
