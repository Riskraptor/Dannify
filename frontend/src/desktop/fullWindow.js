import { desktop } from '/src/desktop/bridge'

// The mini player is a 420 pixel strip. Anything that needs the whole app
// (the lyrics editor, a page to go to, a question to answer) used to open
// inside it: a dialog wider than the window, a page nobody could see. Now
// it brings the full window back first, as it was before, and opens there.

let pending = null

export function inMini() {
  return !!(desktop.isDesktop && desktop.state.mini)
}

/** Leave the mini player if it is up. Resolves once the full app is back. */
export function ensureFullWindow() {
  if (!inMini()) return Promise.resolve(false)
  if (!pending) {
    pending = Promise.resolve(desktop.setMini(false))
      .catch(() => {})
      .then(
        () =>
          new Promise((resolve) => {
            // The shell is drawn again on the next frames.
            requestAnimationFrame(() => requestAnimationFrame(() => resolve(true)))
          })
      )
      .finally(() => {
        pending = null
      })
  }
  return pending
}
