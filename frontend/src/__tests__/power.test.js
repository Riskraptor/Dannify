import { describe, expect, it } from 'vitest'

// While Dannify is not the window in front, what only decorates holds still
// (model/power.js): the page is marked, and unmarked when it is back.

function fakes() {
  const listeners = {}
  const on = (name, fn) => (listeners[name] = [...(listeners[name] || []), fn])
  const doc = {
    hidden: false,
    focused: true,
    hasFocus() {
      return this.focused
    },
    documentElement: { dataset: {} },
    addEventListener: on,
  }
  const win = { addEventListener: on }
  const fire = (name) => (listeners[name] || []).forEach((fn) => fn())
  return { doc, win, fire }
}

describe('attention', () => {
  it('marks the page away while another window is in front, and back again', async () => {
    const { watchAttention, away } = await import('../model/power.js')
    const { doc, win, fire } = fakes()
    watchAttention(doc, win)
    expect(away(doc)).toBe(false)
    doc.focused = false
    fire('blur')
    expect(away(doc)).toBe(true)
    doc.focused = true
    fire('focus')
    expect(away(doc)).toBe(false)
    doc.hidden = true
    fire('visibilitychange')
    expect(away(doc)).toBe(true)
  })

  it('knows a modest computer from its threads and memory', async () => {
    const { modest } = await import('../model/power.js')
    expect(typeof modest).toBe('boolean')
  })
})
