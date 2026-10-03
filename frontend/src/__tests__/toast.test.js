import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The toast model keeps its stack in module state, so every test loads a
// fresh copy of it.
let model
beforeEach(async () => {
  vi.useFakeTimers()
  vi.resetModules()
  model = await import('../model/toast.js')
})
afterEach(() => {
  vi.useRealTimers()
})

const shown = () => model.useToasts().toasts.value

describe('toast()', () => {
  it('keeps the old call shape: message, options, an id back', () => {
    const id = model.toast('Added to queue', { icon: 'ph:list-plus' })
    expect(typeof id).toBe('number')
    expect(shown()).toHaveLength(1)
    expect(shown()[0]).toMatchObject({ id, message: 'Added to queue', icon: 'ph:list-plus', tone: 'default' })
  })

  it('refreshes a message already showing instead of stacking a copy', () => {
    const first = model.toast('Could not save settings', { tone: 'error' })
    vi.advanceTimersByTime(4000)
    const second = model.toast('Could not save settings', { tone: 'error' })
    const third = model.toast('Could not save settings', { tone: 'error' })

    expect(second).toBe(first)
    expect(third).toBe(first)
    expect(shown()).toHaveLength(1)
    expect(shown()[0].count).toBe(3)
    // The countdown started again with the repeat: 4 s in, it is still up
    // well past where the first one would have gone.
    vi.advanceTimersByTime(5000)
    expect(shown()).toHaveLength(1)
    vi.advanceTimersByTime(2000)
    expect(shown()).toHaveLength(0)
  })

  it('takes the newest button when a repeat brings one', () => {
    const older = vi.fn()
    const newer = vi.fn()
    model.toast('Sign in to like songs', { action: { label: 'Sign in', run: older } })
    model.toast('Sign in to like songs', { action: { label: 'Sign in', run: newer } })
    expect(shown()).toHaveLength(1)
    shown()[0].action.run()
    expect(newer).toHaveBeenCalled()
    expect(older).not.toHaveBeenCalled()
  })

  it('does not merge the same words said in a different tone', () => {
    model.toast('Done')
    model.toast('Done', { tone: 'error' })
    expect(shown()).toHaveLength(2)
  })

  it('shows at most three', () => {
    for (const n of [1, 2, 3, 4, 5]) model.toast(`Message ${n}`)
    expect(shown().map((t) => t.message)).toEqual(['Message 3', 'Message 4', 'Message 5'])
  })

  it('pushes out a plain confirmation before an error or a toast with a button', () => {
    model.toast('Downloads finished. 2 failed', {
      tone: 'error',
      action: { label: 'View', run: () => {} },
    })
    model.toast('Added A to queue')
    model.toast('Added B to queue')
    model.toast('Added C to queue')
    expect(shown().map((t) => t.message)).toEqual([
      'Downloads finished. 2 failed',
      'Added B to queue',
      'Added C to queue',
    ])
  })

  it('never drops the newest, even when everything older matters', () => {
    for (const n of [1, 2, 3]) model.toast(`Error ${n}`, { tone: 'error' })
    model.toast('Added to queue')
    expect(shown().map((t) => t.message)).toEqual(['Error 2', 'Error 3', 'Added to queue'])
  })
})

describe('how long a toast stays', () => {
  it('uses the short default for a short confirmation', () => {
    model.toast('Link copied')
    vi.advanceTimersByTime(3100)
    expect(shown()).toHaveLength(1)
    vi.advanceTimersByTime(200)
    expect(shown()).toHaveLength(0)
  })

  it('keeps errors up longer than confirmations', () => {
    expect(model.defaultTimeout('x', 'error')).toBeGreaterThan(model.defaultTimeout('x'))
    expect(model.defaultTimeout('x', 'error', true)).toBeGreaterThan(model.defaultTimeout('x', 'error'))
    expect(model.defaultTimeout('x', 'default', true)).toBeGreaterThan(model.defaultTimeout('x'))
  })

  it('gives a long message time to be read, within reason', () => {
    const long = 'word '.repeat(30)
    expect(model.defaultTimeout(long)).toBeGreaterThan(model.defaultTimeout('short'))
    expect(model.defaultTimeout('word '.repeat(400))).toBe(10000)
  })

  it('respects a timeout the caller chose', () => {
    model.toast('No internet connection', { tone: 'error', timeout: 1000 })
    vi.advanceTimersByTime(1001)
    expect(shown()).toHaveLength(0)
  })

  it('keeps a timeout of 0 until it is closed', () => {
    const id = model.toast('Stays', { timeout: 0 })
    vi.advanceTimersByTime(60000)
    expect(shown()).toHaveLength(1)
    model.dismissToast(id)
    expect(shown()).toHaveLength(0)
  })
})

describe('holding while the pointer is on a toast', () => {
  it('stops every countdown and resumes from where it was', () => {
    const id = model.toast('Update ready', { action: { label: 'Restart', run: () => {} } }) // 5 s
    vi.advanceTimersByTime(3000)
    model.holdToasts(id)
    vi.advanceTimersByTime(60000)
    expect(shown()).toHaveLength(1)
    model.releaseToasts(id)
    vi.advanceTimersByTime(1900)
    expect(shown()).toHaveLength(1)
    vi.advanceTimersByTime(200)
    expect(shown()).toHaveLength(0)
  })

  it('does not start a new toast running while held', () => {
    const first = model.toast('First', { timeout: 0 })
    model.holdToasts(first)
    model.toast('Second')
    vi.advanceTimersByTime(20000)
    expect(shown().map((t) => t.message)).toEqual(['First', 'Second'])
    model.releaseToasts(first)
    vi.advanceTimersByTime(3300)
    expect(shown().map((t) => t.message)).toEqual(['First'])
  })

  it('lets go when the held toast is closed from under the pointer', () => {
    // A toast removed while hovered never gets its mouseleave. Were the hold
    // a bare counter, every toast after it would stay up for good.
    const held = model.toast('Hovered', { timeout: 0 })
    model.toast('Other')
    model.holdToasts(held)
    model.dismissToast(held)
    vi.advanceTimersByTime(4000)
    expect(shown()).toHaveLength(0)
  })

  it('lets go when the held toast is pushed out of the stack', () => {
    const held = model.toast('Hovered')
    model.holdToasts(held)
    for (const n of [1, 2, 3]) model.toast(`New ${n}`)
    expect(shown().some((t) => t.id === held)).toBe(false)
    vi.advanceTimersByTime(4000)
    expect(shown()).toHaveLength(0)
  })

  it('needs every hold on a toast released (pointer and keyboard focus)', () => {
    const id = model.toast('Both')
    model.holdToasts(id) // pointer
    model.holdToasts(id) // focus
    model.releaseToasts(id) // pointer leaves, focus stays
    vi.advanceTimersByTime(10000)
    expect(shown()).toHaveLength(1)
    model.releaseToasts(id)
    vi.advanceTimersByTime(3300)
    expect(shown()).toHaveLength(0)
  })
})

describe('a toast with a key changes in place', () => {
  it('replaces the one with the same key instead of stacking', async () => {
    const { toast, useToasts } = await import('/src/model/toast.js')
    const { toasts } = useToasts()
    toasts.value = []
    const a = toast('Added "One" to the queue', { key: 'queue:add' })
    const b = toast('Added 2 songs to the queue', { key: 'queue:add' })
    const c = toast('Added 3 songs to the queue', { key: 'queue:add' })
    expect(a).toBe(b)
    expect(b).toBe(c)
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].message).toBe('Added 3 songs to the queue')
    toast('Something else')
    expect(toasts.value).toHaveLength(2)
  })
})
