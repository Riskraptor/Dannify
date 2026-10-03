import { describe, expect, it, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

// Playlists made in the app (src/model/playlists.js): how a song is kept and
// brought back as a row, adding without doubles, and the name prompt. The
// server, the router and the player are stand-ins; tracks.js and the dialog
// and menu models are the real ones.

const api = vi.hoisted(() => ({
  coverFileURL: (f) => `/cover/${f}`,
  downloadFileURL: (f) => `/downloads/${f}`,
  getPlaylists: null,
  getPlaylist: null,
  createPlaylist: null,
  addToPlaylist: null,
  updatePlaylist: null,
  deletePlaylist: null,
}))
const toasts = vi.hoisted(() => [])
const pushed = vi.hoisted(() => [])
const libTracks = vi.hoisted(() => ({ value: [] }))
const savedAs = vi.hoisted(() => new Map())
const played = vi.hoisted(() => [])

vi.mock('/src/model/api', () => ({ default: api }))
vi.mock('/src/router', () => ({
  default: {
    push: (to) => pushed.push(to),
    replace: (to) => pushed.push(to),
    currentRoute: { value: { name: 'Library', params: {} } },
  },
}))
vi.mock('/src/model/toast', () => ({ toast: (m, o) => toasts.push({ m, o }) }))
vi.mock('/src/model/library', () => ({ useLibrary: () => ({ tracks: libTracks }) }))
vi.mock('/src/model/libraryIndex', () => ({
  useLibraryIndex: () => ({
    localFileFor: (song) => savedAs.get(song.video_id) || '',
    isDownloaded: () => false,
  }),
}))
vi.mock('/src/model/player', () => ({
  usePlayer: () => ({
    setPlaylist: (list, opts) => played.push({ list, opts }),
    currentTrack: ref(null),
    toggle: () => {},
  }),
  songToTrack: (s) => ({ type: 'stream', title: s.name, video_id: s.video_id }),
}))
vi.mock('/src/model/account', () => ({ useAccount: () => ({ isLiked: () => false }) }))
vi.mock('/src/model/download', () => ({
  useDownloadManager: () => ({}),
  useProgressTracker: () => ({ getBySong: () => null }),
}))
vi.mock('/src/desktop/bridge', () => ({ desktop: { isDesktop: false } }))
vi.mock('/src/model/clipboard', () => ({ copyText: () => true }))
vi.mock('/src/model/repair', () => ({ repairFiles: () => {}, repairStateOf: () => null }))
vi.mock('/src/model/details', () => ({ refreshDetailsFor: () => {} }))
vi.mock('/src/model/focusTrap', () => ({ rememberFocus: () => () => {} }))
vi.mock('/src/i18n', () => ({
  t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k),
}))

const { entryOf, entryRow, usePlaylists, coverURL } = await import('/src/model/playlists.js')
const { localRow, songRow, playRows } = await import('/src/model/tracks.js')
const { promptDialog, useDialogs } = await import('/src/model/dialog.js')
const { openContextMenu, openMenuAt, lastMenuPoint, useContextMenu } = await import(
  '/src/model/contextMenu.js'
)

const flush = () => new Promise((r) => setTimeout(r, 0))

// The dialogs hand focus back once closed; there is no page here.
globalThis.document = globalThis.document || { activeElement: null, body: {} }

const saved = (file, extra = {}) => ({
  file,
  title: file.replace(/.*\/|\.dnf$/g, ''),
  artist: 'Bien',
  artists: ['Bien'],
  album: 'Inauma',
  duration: 210,
  video_id: '',
  ...extra,
})
const online = (id, extra = {}) =>
  songRow({
    video_id: id,
    name: `Song ${id}`,
    artist_ids: [{ name: 'Bensoul', id: 'UC123' }],
    album_name: 'Album',
    album_id: 'MPRE1',
    cover_url: `https://lh3.googleusercontent.com/${id}=w544-h544`,
    duration: 200,
    ...extra,
  })

beforeEach(() => {
  toasts.length = 0
  pushed.length = 0
  played.length = 0
  savedAs.clear()
  libTracks.value = []
  usePlaylists().list.value = []
  const { queue } = useDialogs()
  queue.value = []
})

describe('a song as a playlist keeps it', () => {
  it('a saved song keeps its file and YouTube id, but not its picture', () => {
    const row = localRow(saved('Bien/Bien - Inauma.dnf', { video_id: 'QtrUp3-HLkw', title: 'Inauma' }))
    const e = entryOf(row)
    expect(e).toMatchObject({
      file: 'Bien/Bien - Inauma.dnf',
      video_id: 'QtrUp3-HLkw',
      title: 'Inauma',
      artists: ['Bien'],
      cover_url: '',
      duration: 210,
    })
  })

  it('a song from YouTube keeps its id, artists with their pages, album and picture', () => {
    const e = entryOf(online('aaaaaaaaaaa'))
    expect(e).toMatchObject({
      video_id: 'aaaaaaaaaaa',
      file: '',
      artists: ['Bensoul'],
      artist_ids: [{ name: 'Bensoul', id: 'UC123' }],
      album_id: 'MPRE1',
    })
    expect(e.cover_url).toContain('aaaaaaaaaaa')
  })
})

describe('a playlist entry shown as a row', () => {
  const entry = {
    video_id: 'QtrUp3-HLkw',
    file: 'Bien/Bien - Inauma.dnf',
    title: 'Inauma',
    artists: ['Bien'],
    duration: 210,
  }

  it('plays the saved file while it is there', () => {
    libTracks.value = [saved('Bien/Bien - Inauma.dnf', { video_id: 'QtrUp3-HLkw' })]
    const row = entryRow(entry, 4)
    expect(row.kind).toBe('local')
    expect(row.file).toBe('Bien/Bien - Inauma.dnf')
    expect(row.playlistIndex).toBe(4)
    expect(row.key.startsWith('pl:4:')).toBe(true)
  })

  it('plays the same song saved again under another name', () => {
    libTracks.value = [saved('Bien/Inauma (2).dnf', { video_id: 'QtrUp3-HLkw' })]
    savedAs.set('QtrUp3-HLkw', 'Bien/Inauma (2).dnf')
    const row = entryRow(entry, 0)
    expect(row.kind).toBe('local')
    expect(row.file).toBe('Bien/Inauma (2).dnf')
  })

  it('plays from YouTube once the file is deleted', () => {
    const row = entryRow(entry, 0)
    expect(row.kind).toBe('song')
    expect(row.raw.video_id).toBe('QtrUp3-HLkw')
    expect(row.title).toBe('Inauma')
    expect(row.gone).toBeFalsy()
  })

  it('is kept but marked gone when there is nothing left to play it by', () => {
    const row = entryRow({ file: 'Old/Gone.dnf', title: 'Gone', duration: 100 }, 2)
    expect(row.gone).toBe(true)
    expect(row.title).toBe('Gone')
  })

  it('a gone song is left out of what plays', () => {
    libTracks.value = [saved('A/one.dnf')]
    const rows = [
      entryRow({ file: 'A/one.dnf', title: 'one' }, 0),
      entryRow({ file: 'Old/Gone.dnf', title: 'Gone' }, 1),
      entryRow({ video_id: 'bbbbbbbbbbb', title: 'two' }, 2),
    ]
    playRows(rows, 0)
    expect(played).toHaveLength(1)
    expect(played[0].list.map((t) => t.title)).toEqual(['one', 'two'])
  })

  it('pictures of saved songs come from their files', () => {
    expect(coverURL('file:Bien/x.dnf')).toBe('/cover/Bien/x.dnf')
    expect(coverURL('https://x/y.jpg')).toBe('https://x/y.jpg')
    expect(coverURL('')).toBe('')
  })
})

describe('adding songs', () => {
  beforeEach(() => {
    api.getPlaylist = vi.fn(() =>
      Promise.resolve({
        data: { id: 'p1', name: 'Mix', tracks: [{ video_id: 'aaaaaaaaaaa', title: 'A' }] },
      })
    )
    api.addToPlaylist = vi.fn((id, tracks) =>
      Promise.resolve({ data: { id, name: 'Mix', count: 1 + tracks.length, covers: [], updated: 2 } })
    )
  })

  it('leaves out songs already in it, and doubles in what was chosen', async () => {
    await usePlaylists().addRows('p1', [
      online('aaaaaaaaaaa'),
      online('bbbbbbbbbbb'),
      online('bbbbbbbbbbb'),
      online('ccccccccccc'),
    ])
    expect(api.addToPlaylist).toHaveBeenCalledTimes(1)
    const sent = api.addToPlaylist.mock.calls[0][1].map((e) => e.video_id)
    expect(sent).toEqual(['bbbbbbbbbbb', 'ccccccccccc'])
    expect(toasts[0].m).toContain('playlists.someAlreadyIn')
    expect(usePlaylists().list.value.map((p) => p.count)).toEqual([3])
  })

  it('says so, and sends nothing, when they are all in it', async () => {
    await usePlaylists().addRows('p1', [online('aaaaaaaaaaa')])
    expect(api.addToPlaylist).not.toHaveBeenCalled()
    expect(toasts[0].m).toContain('playlists.alreadyIn')
  })

  it('forgets a playlist that was deleted meanwhile', async () => {
    usePlaylists().list.value = [{ id: 'p1', name: 'Mix', count: 1, covers: [] }]
    api.getPlaylist = vi.fn(() => Promise.reject({ response: { status: 404 } }))
    await usePlaylists().addRows('p1', [online('bbbbbbbbbbb')])
    expect(usePlaylists().list.value).toEqual([])
    expect(toasts[0].o.tone).toBe('error')
  })
})

describe('the name prompt', () => {
  it('gives back what was typed, trimmed', async () => {
    const answer = promptDialog({ title: 'Name', value: 'x' })
    const { queue, settleDialog } = useDialogs()
    expect(queue.value[0]).toMatchObject({ kind: 'prompt', value: 'x' })
    settleDialog('  Road trip  ')
    expect(await answer).toBe('Road trip')
  })

  it('cancelled, or left empty, is no answer', async () => {
    const { settleDialog } = useDialogs()
    const a = promptDialog({ title: 'Name' })
    settleDialog(false)
    expect(await a).toBe(null)
    const b = promptDialog({ title: 'Name' })
    settleDialog('   ')
    expect(await b).toBe(null)
  })

  it('a new playlist is made with the chosen name and the songs, or not at all', async () => {
    api.createPlaylist = vi.fn((name, tracks) =>
      Promise.resolve({ data: { id: 'n1', name, count: tracks.length, covers: [], updated: 1 } })
    )
    const { settleDialog } = useDialogs()
    const made = usePlaylists().createPlaylist([online('aaaaaaaaaaa')])
    await flush()
    settleDialog('Late night')
    expect((await made).name).toBe('Late night')
    expect(api.createPlaylist.mock.calls[0][1].map((e) => e.video_id)).toEqual(['aaaaaaaaaaa'])
    // With songs in it, it says so and stays put; with none, it opens.
    expect(pushed).toEqual([])
    expect(toasts[0].o.action).toBeTruthy()

    const none = usePlaylists().createPlaylist([])
    await flush()
    settleDialog(false)
    expect(await none).toBe(null)
    expect(api.createPlaylist).toHaveBeenCalledTimes(1)
  })
})

describe('a menu that leads to another', () => {
  it('opens the second where the first was', () => {
    const { menu } = useContextMenu()
    openContextMenu({ clientX: 300, clientY: 220, preventDefault() {}, stopPropagation() {} }, [
      { label: 'Add to playlist', action() {} },
    ])
    expect(lastMenuPoint()).toMatchObject({ x: 300, y: 220 })
    menu.value = null
    openMenuAt(lastMenuPoint(), [{ label: 'Mix', action() {} }])
    expect(menu.value).toMatchObject({ x: 300, y: 220 })
    expect(menu.value.items[0].label).toBe('Mix')
  })
})
