// How much motion this computer can comfortably afford, and whether anyone is
// looking at the window.
//
// A modest laptop (four threads or fewer, or 4 GB of memory or less) gets
// lighter decoration: fewer pieces in a special day's weather, no parallax.
// And while Dannify is not the window in front, whatever only decorates holds
// still (html[data-away], see index.css): a drifting background behind a
// spreadsheet costs the battery and shows nobody anything. The music, the
// lyrics and the progress bar go on as they were.

function measure() {
  try {
    const threads = navigator.hardwareConcurrency || 8
    const memory = navigator.deviceMemory || 8
    return threads <= 4 || memory <= 4
  } catch {
    return false
  }
}

export const modest = measure()

let watching = false

/** Mark the page: data-power="low" on a modest computer, data-away while unseen. */
export function watchAttention(doc = document, win = window) {
  if (watching) return
  watching = true
  const root = doc.documentElement
  if (modest) root.dataset.power = 'low'
  const update = () => {
    const seen = !doc.hidden && (typeof doc.hasFocus !== 'function' || doc.hasFocus())
    if (seen) delete root.dataset.away
    else root.dataset.away = '1'
  }
  win.addEventListener('focus', update)
  win.addEventListener('blur', update)
  doc.addEventListener('visibilitychange', update)
  update()
}

/** Whether the window is out of sight or behind another just now. */
export function away(doc = document) {
  return 'away' in doc.documentElement.dataset
}
