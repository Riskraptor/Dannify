import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

// The "Downloads finished. N failed" summary in src/desktop/integration.js,
// driven with a fake download queue. Everything else the module touches is
// replaced with the smallest stand-in that works.

const env = vi.hoisted(() => ({
  queue: null,
  route: null,
  toasts: [],
}))

vi.mock('/src/router', () => ({
  default: {
    get currentRoute() {
      return env.route
    },
    push: () => {},
  },
}))
vi.mock('/src/desktop/bridge', () => ({ desktop: { isDesktop: false } }))
vi.mock('/src/model/player', () => ({ usePlayer: () => ({}) }))
vi.mock('/src/model/downloadStats', () => ({ useDownloadStats: () => ref({ active: 0 }) }))
vi.mock('/src/model/download', () => ({ useProgressTracker: () => ({ downloadQueue: env.queue }) }))
vi.mock('/src/model/toast', () => ({
  toast: (message, opts) => env.toasts.push({ message, opts }),
}))
vi.mock('/src/i18n', async () => {
  const { ref: vueRef } = await import('vue')
  return {
    t: (key, params) => (params ? `${key} ${JSON.stringify(params)}` : key),
    currentLocale: vueRef('en'),
  }
})

class Item {
  constructor(id, status = 'queued') {
    this.song = { song_id: id }
    this.web_status = status
  }
  isPending() {
    return this.web_status === 'queued' || this.web_status === 'downloading'
  }
  isErrored() {
    return this.web_status === 'error'
  }
}

async function setup(initial = []) {
  vi.resetModules()
  // The module hangs its taskbar-command hook on window.
  vi.stubGlobal('window', {})
  env.queue = ref(initial)
  env.route = ref({ name: 'Home' })
  env.toasts = []
  const { installDesktopIntegration } = await import('../desktop/integration.js')
  installDesktopIntegration()
  await nextTick()
}

async function set(id, status) {
  env.queue.value.find((i) => i.song.song_id === id).web_status = status
  await nextTick()
}

async function add(...items) {
  env.queue.value.push(...items)
  await nextTick()
}

describe('download failure summary', () => {
  beforeEach(() => {
    env.toasts = []
  })

  it('says once, at the end of the batch, how many failed', async () => {
    await setup()
    await add(new Item('a'), new Item('b'), new Item('c'))
    await set('a', 'error')
    expect(env.toasts).toHaveLength(0) // the rest are still going
    await set('b', 'done')
    await set('c', 'done')
    expect(env.toasts).toHaveLength(1)
    expect(env.toasts[0].message).toBe('downloads.finishedWithErrors {"failed":1}')
    expect(env.toasts[0].opts.tone).toBe('error')
  })

  it('says nothing when a batch goes perfectly', async () => {
    await setup()
    await add(new Item('a'), new Item('b'))
    await set('a', 'done')
    await set('b', 'done')
    expect(env.toasts).toHaveLength(0)
  })

  it('does not blame a clean batch for an old failure still in the list', async () => {
    // The bug: failed rows stay listed, and every later batch that went
    // perfectly ended with "1 failed" about the same old song.
    await setup([new Item('old', 'error')])
    await add(new Item('a'))
    await set('a', 'done')
    await add(new Item('b'))
    await set('b', 'done')
    expect(env.toasts).toHaveLength(0)
  })

  it('does not repeat itself for the next batch', async () => {
    await setup()
    await add(new Item('a'))
    await set('a', 'error')
    expect(env.toasts).toHaveLength(1)
    await add(new Item('b'))
    await set('b', 'done')
    expect(env.toasts).toHaveLength(1)
  })

  it('counts a retried song that fails again', async () => {
    await setup([new Item('old', 'error')])
    await set('old', 'queued') // retry
    await set('old', 'error')
    expect(env.toasts).toHaveLength(1)
    expect(env.toasts[0].message).toBe('downloads.finishedWithErrors {"failed":1}')
  })

  it('stays quiet on the Downloads page, where the failures are on screen', async () => {
    await setup()
    env.route.value = { name: 'Downloads' }
    await add(new Item('a'))
    await set('a', 'error')
    expect(env.toasts).toHaveLength(0)
    // ...and does not save that failure up for the next batch either.
    env.route.value = { name: 'Home' }
    await add(new Item('b'))
    await set('b', 'done')
    expect(env.toasts).toHaveLength(0)
  })
})
