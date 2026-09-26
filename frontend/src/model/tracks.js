import API from '/src/model/api'
import router from '/src/router'
import { usePlayer, songToTrack } from '/src/model/player'
import { useAccount } from '/src/model/account'
import { useDownloadManager } from '/src/model/download'
import { useLibraryIndex } from '/src/model/libraryIndex'
import { toast } from '/src/model/toast'
import { confirmDialog } from '/src/model/dialog'
import { desktop } from '/src/desktop/bridge'
import { copyText } from '/src/model/clipboard'
import { repairFiles, repairStateOf } from '/src/model/repair'
import { t } from '/src/i18n'

// ---------------------------------------------------------------------------
// Rows: one normalized shape for every track list in the app (library,
// search, albums, playlists, previews, queue). TrackTable renders rows and
// the actions below operate on them.
// ---------------------------------------------------------------------------

const YT_ID = /^[A-Za-z0-9_-]{11}$/

/** A downloaded file from /api/library. */
export function localRow(tr) {
  const names =
    Array.isArray(tr.artists) && tr.artists.length
      ? tr.artists
      : [tr.artist_display || tr.artist || t('common.unknownArtist')]
  return {
    key: `f:${tr.file}`,
    kind: 'local',
    title: tr.title || tr.file,
    artists: names.map((name) => ({ name, local: true })),
    artistText: tr.artist_display || tr.artist || names.join(', '),
    primaryArtist: tr.artist || names[0] || '',
    album: tr.album || '',
    albumId: '',
    duration: tr.duration || 0,
    // The file's date rides along so the address changes when the file
    // does. A repaired track is a new file at the same path, and without
    // this its row kept the blank artwork it had while it was broken.
    cover: `${API.coverFileURL(tr.file)}&v=${Math.floor(tr.added || 0)}`,
    added: tr.added || 0,
    file: tr.file,
    explicit: false,
    // 'locked' or 'damaged' when the backend found the file will not play.
    problem: tr.problem || '',
    raw: tr,
  }
}

/** A YouTube-Music / Spotify song dict (search, explorer, preview). */
export function songRow(s) {
  const artists =
    Array.isArray(s.artist_ids) && s.artist_ids.length
      ? s.artist_ids.map((a) => ({ name: a.name, id: a.id || '' }))
      : (Array.isArray(s.artists) ? s.artists : [s.artists || s.artist || ''])
          .filter(Boolean)
          .map((name) => ({ name, id: '' }))
  return {
    key: `s:${s.song_id || s.video_id || s.url || s.name}`,
    kind: 'song',
    title: s.name || s.title || '',
    artists,
    artistText: artists.map((a) => a.name).join(', '),
    primaryArtist: artists[0] ? artists[0].name : '',
    album: s.album_name || '',
    albumId: s.album_id || '',
    duration: s.duration || 0,
    cover: s.cover_url || '',
    added: 0,
    file: null,
    explicit: !!s.explicit,
    raw: s,
  }
}

/** An entry of the player queue (already a player track). */
export function queueRow(track, index) {
  const song = track._song || null
  const artists =
    song && Array.isArray(song.artist_ids) && song.artist_ids.length
      ? song.artist_ids.map((a) => ({ name: a.name, id: a.id || '' }))
      : String(track.artist || '')
          .split(',')
          .map((n) => n.trim())
          .filter(Boolean)
          .map((name) => ({ name, local: track.type === 'local' }))
  return {
    key: `q:${index}:${track.file || track.song_id || track.url}`,
    kind: track.type === 'local' ? 'local' : 'song',
    queueIndex: index,
    title: track.title || t('common.unknownTrack'),
    artists,
    artistText: track.artist || '',
    primaryArtist: artists[0] ? artists[0].name : '',
    album: track.album || '',
    albumId: (song && song.album_id) || '',
    duration: track.duration || 0,
    cover: track.cover || '',
    added: 0,
    file: track.file || null,
    explicit: !!(song && song.explicit),
    raw: song || track,
    track,
  }
}

// ---------------------------------------------------------------------------
// Player helpers
// ---------------------------------------------------------------------------

export function rowToTrack(row) {
  if (row.track) return row.track
  if (row.kind === 'local') {
    return {
      type: 'local',
      file: row.file,
      url: API.downloadFileURL(row.file),
      cover: API.coverFileURL(row.file),
      title: row.title,
      artist: row.artistText,
      album: row.album,
      duration: row.duration,
      // Downloads carry the YouTube id they came from, so a track playing
      // off disk can still be liked on YouTube Music.
      video_id: (row.raw && row.raw.video_id) || '',
    }
  }
  // Song dicts go through the player's local-first resolver, so a song that's
  // already downloaded plays from disk instead of re-streaming.
  return songToTrack(row.raw)
}

export function isRowCurrent(row) {
  const cur = usePlayer().currentTrack.value
  if (!cur || !row) return false
  if (row.file && cur.file) return row.file === cur.file
  const id = row.raw && (row.raw.song_id || row.raw.video_id)
  return !!id && (cur.song_id === id || cur.video_id === id)
}

// ---------------------------------------------------------------------------
// Saved tracks that will not play
// ---------------------------------------------------------------------------

/** A saved track the backend found will not play. */
export function needsRepair(row) {
  return !!(row && row.kind === 'local' && row.problem)
}

export function repairRows(rows) {
  repairFiles((rows || []).filter((r) => r.kind === 'local' && r.file).map((r) => r.file))
}

/** What pressing play on a broken track does instead of failing. */
export function offerRepair(row) {
  const title = row.title || ''
  const state = repairStateOf(row.file)
  if (state === 'queued' || state === 'working') {
    toast(t('repair.stillWorking', { title }), { icon: 'ph:wrench' })
    return
  }
  toast(t('repair.needsToast', { title }), {
    tone: 'error',
    timeout: 8000,
    action: { label: t('repair.action'), run: () => repairRows([row]) },
  })
}

// A queue never gets a broken track in it. Each one would stop playback with
// an error and skip on, and a few in a row stopped it altogether.
function playable(rows) {
  return rows.filter((r) => !needsRepair(r))
}

/** Replace the queue with `rows` and start at `index`. */
export function playRows(rows, index = 0) {
  if (!rows || !rows.length) return
  const player = usePlayer()
  const target = rows[index]
  if (target && isRowCurrent(target)) {
    player.toggle()
    return
  }
  const list = playable(rows)
  if (!list.length) {
    if (needsRepair(target)) offerRepair(target)
    return
  }
  // Starting on a broken one (Play on a list whose first row is broken)
  // starts on the next that works instead.
  let start = list.indexOf(target)
  if (start < 0) {
    const after = rows.slice(index + 1).find((r) => !needsRepair(r))
    start = after ? list.indexOf(after) : 0
  }
  player.setPlaylist(list.map(rowToTrack), { startIndex: start })
}

export function shuffleRows(rows) {
  const list = playable(rows || [])
  if (!list.length) return
  const player = usePlayer()
  player.setShuffle(true)
  player.setPlaylist(list.map(rowToTrack), {
    startIndex: Math.floor(Math.random() * list.length),
  })
}

export function playNext(rows) {
  const list = playable(rows)
  if (!list.length) {
    if (rows.length) offerRepair(rows[0])
    return
  }
  usePlayer().enqueue(list.map(rowToTrack), { next: true })
  toast(
    list.length === 1
      ? t('actions.willPlayNext', { title: list[0].title })
      : t('actions.willPlayNextMany', { count: list.length }),
    { icon: 'ph:queue' }
  )
}

export function addToQueue(rows) {
  const list = playable(rows)
  if (!list.length) {
    if (rows.length) offerRepair(rows[0])
    return
  }
  usePlayer().enqueue(list.map(rowToTrack))
  toast(
    list.length === 1
      ? t('actions.addedToQueue', { title: list[0].title })
      : t('actions.addedToQueueMany', { count: list.length }),
    { icon: 'ph:list-plus' }
  )
}

// ---------------------------------------------------------------------------
// Library / download actions
// ---------------------------------------------------------------------------

export function isRowDownloaded(row) {
  if (!row) return false
  if (row.kind === 'local') return true
  return useLibraryIndex().isDownloaded(row.raw)
}

export function downloadRows(rows) {
  const songs = rows
    .filter((r) => r.kind === 'song' && !isRowDownloaded(r))
    .map((r) => r.raw)
  if (!songs.length) {
    toast(t('actions.alreadyInLibrary'), { icon: 'ph:check-circle' })
    return
  }
  // No optimistic "in library" marking: rows show progress from the
  // download queue and turn green only once the file really exists.
  useDownloadManager().downloadSongs(songs)
  // No toast here. The download button in the title bar lights up and starts
  // filling its ring the moment this is called, and the row itself shows
  // progress: a popup over the player saying the same thing is one more
  // thing to dismiss.
}

export async function deleteRows(rows) {
  const files = rows.filter((r) => r.kind === 'local' && r.file)
  if (!files.length) return false
  const ok = await confirmDialog({
    title:
      files.length === 1
        ? t('actions.deleteTitle')
        : t('actions.deleteTitleMany', { count: files.length }),
    message:
      files.length === 1
        ? t('actions.deleteMessage', { title: files[0].title })
        : t('actions.deleteMessageMany', { count: files.length }),
    confirmText: t('common.delete'),
    danger: true,
    icon: 'ph:trash',
  })
  if (!ok) return false
  const removed = []
  for (const r of files) {
    try {
      await API.deleteDownload(r.file)
      removed.push(r.file)
    } catch {
      toast(t('library.failedDelete', { file: r.title }), { tone: 'error' })
    }
  }
  if (removed.length) {
    useLibraryIndex().invalidate()
    window.dispatchEvent(
      new CustomEvent('dannify:library-changed', { detail: { removed } })
    )
    toast(
      removed.length === 1
        ? t('actions.deleted', { title: files[0].title })
        : t('actions.deletedMany', { count: removed.length }),
      { icon: 'ph:trash' }
    )
  }
  return removed.length > 0
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

export function openArtist(artist) {
  if (!artist) return
  if (artist.id) router.push({ name: 'ExploreArtist', params: { id: artist.id } })
  else if (artist.name) router.push({ name: 'Artist', params: { name: artist.name } })
}

export function goToArtist(row) {
  const a = row.artists && row.artists.find((x) => x.id) // prefer a deep link
  if (a) return openArtist(a)
  if (row.kind === 'local' && row.primaryArtist) {
    return router.push({ name: 'Artist', params: { name: row.primaryArtist } })
  }
  if (row.primaryArtist) {
    router.push({ name: 'Search', params: { query: row.primaryArtist } })
  }
}

export function goToAlbum(row) {
  if (row.albumId) {
    router.push({ name: 'ExploreAlbum', params: { id: row.albumId } })
  } else if (row.album) {
    const who = row.primaryArtist ? `${row.primaryArtist} ` : ''
    router.push({ name: 'Search', params: { query: `${who}${row.album}` } })
  }
}

/** The YouTube videoId behind a row, if it has one (likes / radio need it). */
export function songVideoId(row) {
  const raw = (row && row.raw) || {}
  const track = (row && row.track) || {}
  const id = [raw.video_id, raw.song_id, track.video_id, track.song_id].find(
    (v) => typeof v === 'string' && YT_ID.test(v)
  )
  return id || ''
}

export function youtubeLink(row) {
  const raw = row.raw || {}
  const id = [raw.video_id, raw.song_id, row.track && row.track.video_id].find(
    (v) => typeof v === 'string' && YT_ID.test(v)
  )
  if (id) return `https://music.youtube.com/watch?v=${id}`
  if (raw.url && /^https?:\/\//.test(raw.url)) return raw.url
  return ''
}

// ---------------------------------------------------------------------------
// Context menu
// ---------------------------------------------------------------------------

/**
 * Build the right-click menu for one or more rows.
 * ctx: { source: rows the selection came from (for "Play" semantics),
 *        queue: true when invoked from the queue panel }
 */
export function trackMenu(rows, ctx = {}) {
  if (!rows || !rows.length) return []
  const player = usePlayer()
  const single = rows.length === 1 ? rows[0] : null
  const locals = rows.filter((r) => r.kind === 'local')
  const pendingDownloads = rows.filter(
    (r) => r.kind === 'song' && !isRowDownloaded(r)
  )
  const link = single ? youtubeLink(single) : ''
  const videoId = single ? songVideoId(single) : ''
  const broken = ctx.queue ? [] : locals.filter(needsRepair)

  const items = []
  // First, when it applies: a broken track cannot be played, so the thing
  // somebody opened this menu for is almost certainly this.
  if (broken.length) {
    items.push(
      {
        label:
          broken.length === 1
            ? t('repair.track')
            : t('repair.tracks', { count: broken.length }),
        icon: 'ph:wrench',
        action: () => repairRows(broken),
      },
      { divider: true }
    )
  }
  if (ctx.queue && single) {
    items.push({
      label: t('actions.play'),
      icon: 'ph:play',
      action: () => player.playAt(single.queueIndex),
    })
  } else {
    items.push({
      label: single
        ? t('actions.play')
        : t('actions.playSelection', { count: rows.length }),
      icon: 'ph:play',
      action: () => playRows(rows, 0),
    })
  }
  items.push(
    {
      label: t('actions.playNext'),
      icon: 'ph:queue',
      action: () => playNext(rows),
    },
    !ctx.queue && {
      label: t('actions.addToQueue'),
      icon: 'ph:list-plus',
      action: () => addToQueue(rows),
    },
    ctx.queue &&
      single && {
        label: t('actions.removeFromQueue'),
        icon: 'ph:x',
        action: () => player.removeFromQueue(single.queueIndex),
      },
    single &&
      videoId && {
        label: t('actions.startRadio'),
        icon: 'ph:broadcast',
        action: () => player.startRadio(single.raw),
      },
    { divider: true },
    videoId && {
      label: useAccount().isLiked(videoId)
        ? t('account.removeFromLiked')
        : t('account.addToLiked'),
      icon: useAccount().isLiked(videoId) ? 'ph:heart-break' : 'ph:heart',
      action: () => useAccount().toggleLike(single.raw),
    },
    pendingDownloads.length > 0 && {
      label:
        pendingDownloads.length === 1
          ? t('actions.download')
          : t('actions.downloadCount', { count: pendingDownloads.length }),
      icon: 'ph:download-simple',
      action: () => downloadRows(pendingDownloads),
    },
    single &&
      single.artists.length > 0 && {
        label: t('actions.goToArtist'),
        icon: 'ph:user',
        action: () => goToArtist(single),
      },
    single &&
      (single.albumId || single.album) && {
        label: t('actions.goToAlbum'),
        icon: 'ph:vinyl-record',
        action: () => goToAlbum(single),
      },
    desktop.isDesktop &&
      single &&
      single.file && {
        label: t('actions.showInFolder'),
        icon: 'ph:folder-open',
        action: () => desktop.revealInFolder(single.file),
      },
    link && {
      label: t('actions.copyLink'),
      icon: 'ph:link',
      action: async () => {
        if (await copyText(link)) toast(t('actions.linkCopied'), { icon: 'ph:link' })
      },
    },
    locals.length > 0 &&
      !ctx.queue && { divider: true },
    locals.length > 0 &&
      !ctx.queue && {
        label:
          locals.length === 1
            ? t('actions.deleteFromLibrary')
            : t('actions.deleteCount', { count: locals.length }),
        icon: 'ph:trash',
        danger: true,
        shortcut: 'Del',
        action: () => deleteRows(locals),
      }
  )
  return items
}
