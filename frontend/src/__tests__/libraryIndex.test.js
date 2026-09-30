import { describe, expect, it, vi, beforeEach } from 'vitest'

// The real module, with the one call it makes to the server stubbed.
const tracks = []
let calls = 0
let hold = null
vi.mock('/src/model/api', () => ({
  default: {
    getLibrary: () => {
      calls++
      const snapshot = tracks.slice()
      const reply = { data: { tracks: snapshot } }
      return hold ? hold.then(() => reply) : Promise.resolve(reply)
    },
  },
}))

const { useLibraryIndex } = await import('/src/model/libraryIndex.js')
const index = useLibraryIndex()

beforeEach(async () => {
  tracks.length = 0
  calls = 0
  hold = null
})

async function loadWith(list) {
  tracks.length = 0
  tracks.push(...list)
  await index.load(true)
}

describe('library index', () => {
  it('does not mistake one non-Latin song for another', async () => {
    await loadWith([{ artist: 'YOASOBI', title: '群青', file: 'YOASOBI - 群青.dnf' }])
    expect(index.isDownloaded({ artists: ['YOASOBI'], title: 'アイドル' })).toBe(false)
    expect(index.localFileFor({ artists: ['YOASOBI'], title: 'アイドル' })).toBe('')
    expect(index.localFileFor({ artists: ['YOASOBI'], title: '群青' })).toBe('YOASOBI - 群青.dnf')
  })

  it('reads different scripts and accents sensibly', async () => {
    await loadWith([
      { artist: 'Кино', title: 'Группа крови', file: 'a.dnf' },
      { artist: 'Beyoncé', title: 'Halo', file: 'b.dnf' },
    ])
    expect(index.isDownloaded({ artists: ['Сплин'], title: 'Выхода нет' })).toBe(false)
    expect(index.localFileFor({ artists: ['Кино'], title: 'Группа крови' })).toBe('a.dnf')
    expect(index.localFileFor({ artists: ['Beyonce'], title: 'HALO' })).toBe('b.dnf')
  })

  it('never matches on an empty title', async () => {
    await loadWith([{ artist: 'A', title: '🎵', file: 'a.dnf' }])
    expect(index.isDownloaded({ artists: ['A'], title: '🔥' })).toBe(false)
  })

  it('reads again when asked during a read', async () => {
    let release
    hold = new Promise((r) => (release = r))
    tracks.push({ artist: 'A', title: 'One', file: 'one.dnf' })
    const first = index.load(true)
    // A second download finishes while the first read is still out.
    tracks.push({ artist: 'A', title: 'Two', file: 'two.dnf' })
    const second = index.load(true)
    release()
    await first
    await second
    expect(calls).toBe(2)
    expect(index.localFileFor({ artists: ['A'], title: 'Two' })).toBe('two.dnf')
  })
})
