// What a pasted link points at, read from the text alone: a Spotify song,
// album, playlist, artist, podcast or episode, or a YouTube (Music) song,
// playlist, album, artist (by channel or @name) or podcast. Kept apart from
// opening them so it can be checked on its own.

const SPOTIFY = /^(?:https?:\/\/)?(?:open\.|play\.)?spotify\.com\/(?:intl-[a-z]{2}(?:-[a-z]{2})?\/)?(?:embed\/)?(track|album|playlist|artist|episode|show)\/([A-Za-z0-9]{8,40})/i
const SPOTIFY_URI = /^spotify:(track|album|playlist|artist|episode|show):([A-Za-z0-9]{8,40})$/i
const YT_HOST = /^(?:https?:\/\/)?(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)\//i
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/

/**
 * What *text* links to, or null when it is not a link Dannify opens.
 * @returns {{source: 'spotify', kind: string, id: string, url: string}
 *         | {source: 'youtube', kind: 'song'|'playlist'|'album'|'artist'|'handle', id: string, url: string}
 *         | null}
 */
export function parseLink(text) {
  const raw = String(text || '').trim()
  if (!raw || raw.length > 500 || /\s/.test(raw)) return null
  const uri = raw.match(SPOTIFY_URI)
  if (uri) {
    const [, kind, id] = uri
    return { source: 'spotify', kind: kind.toLowerCase(), id, url: `https://open.spotify.com/${kind.toLowerCase()}/${id}` }
  }
  const sp = raw.match(SPOTIFY)
  if (sp) {
    const [, kind, id] = sp
    return { source: 'spotify', kind: kind.toLowerCase(), id, url: `https://open.spotify.com/${kind.toLowerCase()}/${id}` }
  }
  if (!YT_HOST.test(raw)) return null
  let url
  try {
    url = new URL(/^https?:/i.test(raw) ? raw : `https://${raw}`)
  } catch {
    return null
  }
  const path = url.pathname.replace(/\/+$/, '')
  const params = url.searchParams
  if (/youtu\.be$/i.test(url.hostname)) {
    const id = path.slice(1)
    return VIDEO_ID.test(id) ? { source: 'youtube', kind: 'song', id, url: url.href } : null
  }
  const v = params.get('v')
  if ((path === '/watch' || path === '') && v && VIDEO_ID.test(v)) {
    return { source: 'youtube', kind: 'song', id: v, url: url.href }
  }
  const short = path.match(/^\/(?:shorts|live|embed)\/([A-Za-z0-9_-]{11})$/)
  if (short) return { source: 'youtube', kind: 'song', id: short[1], url: url.href }
  const list = params.get('list')
  if (path === '/playlist' && list) return { source: 'youtube', kind: 'playlist', id: list, url: url.href }
  const browse = path.match(/^\/browse\/([A-Za-z0-9_-]+)$/)
  if (browse) {
    const id = browse[1]
    if (id.startsWith('MPRE')) return { source: 'youtube', kind: 'album', id, url: url.href }
    // A podcast, and one of its episodes.
    if (id.startsWith('MPSP')) return { source: 'youtube', kind: 'playlist', id, url: url.href }
    if (id.startsWith('MPED') && VIDEO_ID.test(id.slice(4))) return { source: 'youtube', kind: 'song', id: id.slice(4), url: url.href }
    if (id.startsWith('VL')) return { source: 'youtube', kind: 'playlist', id: id.slice(2), url: url.href }
    if (id.startsWith('UC')) return { source: 'youtube', kind: 'artist', id, url: url.href }
  }
  const channel = path.match(/^\/channel\/(UC[A-Za-z0-9_-]{10,})$/)
  if (channel) return { source: 'youtube', kind: 'artist', id: channel[1], url: url.href }
  const podcast = path.match(/^\/podcast\/([A-Za-z0-9_-]{10,})$/)
  if (podcast) return { source: 'youtube', kind: 'playlist', id: podcast[1], url: url.href }
  // youtube.com/@SautiSol: a channel by its name, found as an artist.
  const handle = path.match(/^\/@([\w.-]{2,60})(?:\/(?:featured|videos|music|releases))?$/)
  if (handle) return { source: 'youtube', kind: 'handle', id: decodeURIComponent(handle[1]), url: url.href }
  return null
}
