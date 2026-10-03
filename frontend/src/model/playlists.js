import { ref, computed } from 'vue'
import API from '/src/model/api'
import router from '/src/router'
import { toast } from '/src/model/toast'
import { promptDialog, confirmDialog } from '/src/model/dialog'
import { openContextMenu, openMenuAt, lastMenuPoint } from '/src/model/contextMenu'
import { useLibrary } from '/src/model/library'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { localRow, songRow, songVideoId } from '/src/model/tracks'
import { t } from '/src/i18n'

// Playlists the listener makes. They live on this PC (Backend/dannify/
// playlists.py), not in a Google account, so they work signed out and
// offline. A song in one is kept by what identifies it: its file when it is
// saved, its YouTube id when it is not. A saved song plays from disk; one
// that is not, or no longer is, plays from YouTube.

const list = ref([])
const loaded = ref(false)
let inflight = null

function load() {
  if (inflight) return inflight
  inflight = API.getPlaylists()
    .then((res) => {
      const got = res.data && Array.isArray(res.data.playlists) ? res.data.playlists : []
      list.value = got
      loaded.value = true
    })
    .catch(() => {})
    .finally(() => {
      inflight = null
    })
  return inflight
}

function ensureLoaded() {
  if (!loaded.value) return load()
  return Promise.resolve()
}

// Newest first: the one somebody is filling is the one they want at hand.
const recent = computed(() => [...list.value].sort((a, b) => (b.updated || 0) - (a.updated || 0)))

/** Keep a playlist's summary in step after the server answered with it. */
function remember(p) {
  if (!p || !p.id) return
  const summary = {
    id: p.id,
    name: p.name,
    count: p.count,
    duration: p.duration,
    covers: p.covers || [],
    updated: p.updated,
  }
  const at = list.value.findIndex((x) => x.id === p.id)
  if (at < 0) list.value = [...list.value, summary]
  else list.value = list.value.map((x, i) => (i === at ? summary : x))
}

function forget(pid) {
  list.value = list.value.filter((x) => x.id !== pid)
}

/** The picture for one of a playlist's covers (a saved file's, or a web one). */
export function coverURL(cover) {
  if (!cover) return ''
  if (cover.startsWith('file:')) return API.coverFileURL(cover.slice(5))
  return cover
}

// ---------------------------------------------------------------------------
// Rows in, rows out
// ---------------------------------------------------------------------------

/** A table row as a playlist keeps it. */
export function entryOf(row) {
  if (!row) return null
  const raw = row.raw || {}
  const ids = (row.artists || []).filter((a) => a && a.name && a.id)
  return {
    video_id: songVideoId(row) || (typeof raw.video_id === 'string' ? raw.video_id : ''),
    file: row.file || '',
    title: row.title || '',
    album: row.album || '',
    album_id: row.albumId || '',
    // A saved song's picture comes from its file, which can change; only a
    // web picture is worth keeping.
    cover_url: row.kind === 'local' ? '' : row.cover || '',
    artists: (row.artists || []).map((a) => a && a.name).filter(Boolean),
    artist_ids: ids.map((a) => ({ name: a.name, id: a.id })),
    duration: Math.round(row.duration || 0),
  }
}

/** Whether two playlist entries are the same song. */
function sameSong(a, b) {
  if (a.video_id && b.video_id) return a.video_id === b.video_id
  return !!a.file && a.file === b.file
}

/**
 * A playlist entry as a table row: the saved file when it is still there
 * (or the same song saved again under another name), the song online when
 * it is not. `playlistIndex` is its place in the playlist, for reordering and
 * removing whatever the table shows.
 */
export function entryRow(entry, index) {
  const lib = useLibrary()
  const index_ = useLibraryIndex()
  let file = entry.file && lib.tracks.value.some((tr) => tr.file === entry.file) ? entry.file : ''
  if (!file && entry.video_id) file = index_.localFileFor({ video_id: entry.video_id }) || ''
  const saved = file ? lib.tracks.value.find((tr) => tr.file === file) : null
  let row
  if (saved) {
    row = localRow(saved)
  } else {
    row = songRow({
      video_id: entry.video_id,
      song_id: entry.video_id,
      name: entry.title,
      artists: entry.artists || [],
      artist_ids: entry.artist_ids || [],
      album_name: entry.album || '',
      album_id: entry.album_id || '',
      cover_url: entry.cover_url || (entry.file ? API.coverFileURL(entry.file) : ''),
      duration: entry.duration || 0,
    })
    // Nothing to play it by: a saved song, since deleted, that never had a
    // YouTube id. Shown, so the list is what was made, but greyed out.
    if (!entry.video_id) row = { ...row, gone: true }
  }
  return { ...row, key: `pl:${index}:${row.key}`, playlistIndex: index, entry }
}

// ---------------------------------------------------------------------------
// Making and changing
// ---------------------------------------------------------------------------

function nextName() {
  const taken = new Set(list.value.map((p) => p.name))
  for (let n = list.value.length + 1; ; n++) {
    const name = t('playlists.defaultName', { n })
    if (!taken.has(name)) return name
  }
}

function failed() {
  toast(t('playlists.couldNotSave'), { tone: 'error', icon: 'ph:warning' })
}

/**
 * Ask for a name and make a playlist, with `rows` in it if given. Resolves to
 * the new playlist, or null when cancelled. With no songs, opens it.
 */
async function createPlaylist(rows = [], { open = !rows.length, name = '' } = {}) {
  const chosen = await promptDialog({
    title: t('playlists.newTitle'),
    label: t('playlists.nameLabel'),
    value: name || nextName(),
    confirmText: t('playlists.create'),
    icon: 'ph:playlist',
  })
  if (chosen == null) return null
  try {
    const entries = rows.map(entryOf).filter(Boolean)
    const res = await API.createPlaylist(chosen, entries)
    remember(res.data)
    if (open) {
      router.push({ name: 'Playlist', params: { id: res.data.id } })
    } else {
      toast(
        entries.length === 1
          ? t('playlists.added', { name: res.data.name })
          : t('playlists.addedMany', { count: entries.length, name: res.data.name }),
        {
          icon: 'ph:playlist',
          action: {
            label: t('playlists.open'),
            run: () => router.push({ name: 'Playlist', params: { id: res.data.id } }),
          },
        }
      )
    }
    return res.data
  } catch {
    failed()
    return null
  }
}

/** Add `rows` to a playlist, leaving out songs already in it. */
async function addRows(pid, rows) {
  const entries = rows.map(entryOf).filter(Boolean)
  if (!entries.length) return
  try {
    const have = (await API.getPlaylist(pid)).data
    const fresh = entries.filter(
      (e, i) =>
        !have.tracks.some((x) => sameSong(x, e)) &&
        !entries.slice(0, i).some((x) => sameSong(x, e))
    )
    if (!fresh.length) {
      toast(t('playlists.alreadyIn', { name: have.name }), { icon: 'ph:playlist' })
      return
    }
    const res = await API.addToPlaylist(pid, fresh)
    remember(res.data)
    const name = res.data.name
    let text
    if (fresh.length < entries.length) text = t('playlists.someAlreadyIn', { count: fresh.length, name })
    else if (fresh.length === 1) text = t('playlists.added', { name })
    else text = t('playlists.addedMany', { count: fresh.length, name })
    toast(text, {
      icon: 'ph:playlist',
      key: `playlist:${pid}`,
      action: {
        label: t('playlists.open'),
        run: () => router.push({ name: 'Playlist', params: { id: pid } }),
      },
    })
  } catch (err) {
    if (err && err.response && err.response.status === 404) {
      forget(pid)
      toast(t('playlists.notFound'), { tone: 'error', icon: 'ph:warning' })
    } else failed()
  }
}

/** The menu of playlists to add `rows` to. */
function pickerItems(rows) {
  return [
    { label: t('playlists.new'), icon: 'ph:plus', action: () => createPlaylist(rows) },
    recent.value.length && { divider: true },
    ...recent.value.map((p) => ({
      label: p.name,
      icon: 'ph:playlist',
      action: () => addRows(p.id, rows),
    })),
  ]
}

/**
 * Show the playlists to add to. From a menu item, where that menu was; from a
 * button, under it.
 */
async function pickPlaylist(rows, event = null) {
  await ensureLoaded()
  if (event) openContextMenu(event, pickerItems(rows), { anchor: true })
  else openMenuAt(lastMenuPoint(), pickerItems(rows))
}

async function renamePlaylist(pid) {
  const p = list.value.find((x) => x.id === pid)
  const chosen = await promptDialog({
    title: t('playlists.renameTitle'),
    label: t('playlists.nameLabel'),
    value: p ? p.name : '',
    confirmText: t('playlists.save'),
    icon: 'ph:pencil-simple',
  })
  if (chosen == null) return null
  try {
    const res = await API.updatePlaylist(pid, { name: chosen })
    remember(res.data)
    return res.data
  } catch {
    failed()
    return null
  }
}

async function deletePlaylist(pid) {
  const p = list.value.find((x) => x.id === pid)
  const ok = await confirmDialog({
    title: t('playlists.deleteTitle', { name: p ? p.name : '' }),
    message: t('playlists.deleteText'),
    confirmText: t('playlists.delete'),
    danger: true,
    icon: 'ph:trash',
  })
  if (!ok) return false
  try {
    await API.deletePlaylist(pid)
  } catch (err) {
    if (!(err && err.response && err.response.status === 404)) {
      failed()
      return false
    }
  }
  forget(pid)
  const route = router.currentRoute.value
  if (route.name === 'Playlist' && route.params.id === pid) router.replace({ name: 'Library' })
  toast(t('playlists.deleted'), { icon: 'ph:trash' })
  return true
}

/** Save a playlist's songs in a new order, or with some taken out. */
async function setEntries(pid, entries) {
  try {
    const res = await API.updatePlaylist(pid, { tracks: entries })
    remember(res.data)
    return res.data
  } catch {
    failed()
    return null
  }
}

// ---------------------------------------------------------------------------
// Dragging songs onto a playlist
// ---------------------------------------------------------------------------

// The rows being dragged out of a song table, while they are. A drop target
// (a playlist in the sidebar) reads them; nothing outside the app can.
const dragging = ref(null)

export function usePlaylists() {
  return {
    list,
    recent,
    loaded,
    load,
    ensureLoaded,
    remember,
    createPlaylist,
    addRows,
    pickPlaylist,
    renamePlaylist,
    deletePlaylist,
    setEntries,
    dragging,
  }
}
