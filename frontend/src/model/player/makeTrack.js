import API from '/src/model/api'
import { useLibraryIndex } from '/src/model/libraryIndex'

// What the rest of the app hands the player (a saved file's path, a song
// from search, Explore or a pasted link, a table row) as the track the queue
// holds.

const _libraryIndex = useLibraryIndex()
// Prime the index on app boot: the data is small (one /api/library call)
// and being already loaded means the first time the user clicks a search
// result trackFromSong() returns a local file synchronously.
_libraryIndex.load()

// One implementation of the path encoding, in api.js. There were three, and
// this one encoded the whole path with encodeURIComponent, so the separators
// came out as %2F and a track in a subfolder asked for a file that was not
// there.
const fileUrl = (file) => API.downloadFileURL(file)
const coverUrl = (file) => API.coverFileURL(file)

export function trackFromFile(file) {
  const noExt = file.replace(/\.[^.]+$/, '')
  let artist = ''
  let title = noExt
  const dash = noExt.indexOf(' - ')
  if (dash > 0) {
    artist = noExt.slice(0, dash).trim()
    title = noExt.slice(dash + 3).trim()
  }
  return {
    type: 'local',
    file,
    url: fileUrl(file),
    cover: coverUrl(file),
    title,
    artist,
  }
}

// Build a streaming track from a resolved/preview song dict.
//
// Two kinds of song dicts arrive here:
//  * YouTube-sourced (search / explorer): ``song_id`` is a real 11-char
//    YouTube videoId: we can stream it directly.
//  * Spotify-sourced (preview of a pasted link): ``song_id`` is a 22-char
//    Spotify track id with no YouTube match yet: we must stream by URL so
//    the backend resolves the matching YouTube video first.
export function trackFromSong(song) {
  const artists = song.artists || []
  const spotifyUrl =
    song.url && song.url.includes('spotify') ? song.url : ''

  // A YouTube videoId is exactly 11 url-safe chars. Anything else (e.g. a
  // Spotify 22-char id) is NOT a playable video id.
  const isYtId = (v) =>
    typeof v === 'string' && /^[A-Za-z0-9_-]{11}$/.test(v)

  let videoId = ''
  if (isYtId(song.video_id)) videoId = song.video_id
  else if (song.source === 'youtube' && isYtId(song.song_id))
    videoId = song.song_id
  else if (!spotifyUrl && isYtId(song.song_id)) videoId = song.song_id

  // ---------------------------------------------------------------------
  // Local-first: if this song is already downloaded, ALWAYS play the
  // on-disk file. Zero ffmpeg, zero network, instant start, lyrics from
  // the local .lrc. The library index is pre-loaded on app boot and
  // refreshed whenever a download finishes (WS library_changed event).
  // ---------------------------------------------------------------------
  try {
    const localFile = _libraryIndex && _libraryIndex.localFileFor(song)
    if (localFile) {
      const stem = localFile.replace(/\.[^.]+$/, '')
      const slash = stem.lastIndexOf('/')
      const tail = slash >= 0 ? stem.slice(slash + 1) : stem
      const dash = tail.indexOf(' - ')
      const guessedArtist = dash > 0 ? tail.slice(0, dash) : ''
      const guessedTitle = dash > 0 ? tail.slice(dash + 3) : tail
      return {
        type: 'local',
        file: localFile,
        url: API.downloadFileURL(localFile),
        cover: API.coverFileURL(localFile),
        title: song.name || guessedTitle,
        artist:
          (Array.isArray(artists) ? artists.join(', ') : String(artists || '')) ||
          guessedArtist,
        album: song.album_name || '',
        duration: song.duration || 0,
        video_id: videoId,
        song_id: song.song_id || videoId,
        _song: song,
      }
    }
  } catch {
    // libraryIndex not yet imported: fall through to stream track.
  }

  // Stream URL: prefer a real videoId; otherwise hand the Spotify URL to the
  // backend (/api/stream?url=) which resolves + matches it to YouTube.
  let url
  if (videoId) url = API.streamURL(videoId)
  else if (spotifyUrl) url = API.streamURLFromLink(spotifyUrl)
  else url = API.streamURL(song.song_id || '') // last-ditch

  return {
    type: 'stream',
    file: null,
    song_id: song.song_id || videoId,
    video_id: videoId, // '' until resolved (Spotify case)
    spotify_url: spotifyUrl,
    url,
    cover: song.cover_url || '',
    title: song.name || '',
    artist: Array.isArray(artists) ? artists.join(', ') : String(artists || ''),
    album: song.album_name || '',
    duration: song.duration || 0,
    _song: song,
  }
}

export function toTrack(item) {
  if (typeof item === 'string') return trackFromFile(item)
  if (item && item.url && (item.type === 'local' || item.type === 'stream')) {
    return item
  }
  return trackFromSong(item)
}
