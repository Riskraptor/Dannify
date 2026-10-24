// Links pasted into Dannify: Spotify and YouTube (Music) ones, opened as what
// they are. Pasted into the search box, or anywhere in the window, a link
// used to be searched for as words, and found nothing.

import router from '/src/router'
import API from '/src/model/api'
import { t } from '/src/i18n'
import { toast } from '/src/model/toast'
import { parseLink } from '/src/model/linkParse'

export { parseLink }

/** Open what *text* links to. True when it was a link Dannify opens. */
export async function openLink(text) {
  const link = parseLink(text)
  if (!link) return false
  if (link.source === 'spotify') {
    if (link.kind === 'episode' || link.kind === 'show') {
      toast(t('links.notMusic'), { icon: 'ph:microphone', key: 'link' })
      return true
    }
    router.push({ name: 'Link', query: { url: link.url } })
    return true
  }
  if (link.kind === 'playlist') router.push({ name: 'ExplorePlaylist', params: { id: link.id } })
  else if (link.kind === 'album') router.push({ name: 'ExploreAlbum', params: { id: link.id } })
  else if (link.kind === 'artist') router.push({ name: 'ExploreArtist', params: { id: link.id } })
  else await playVideo(link)
  return true
}

// A song by its YouTube link: played at once, with its title and artist.
async function playVideo(link) {
  const { usePlayer, songToTrack } = await import('/src/model/player')
  toast(t('links.opening'), { icon: 'ph:link', key: 'link', timeout: 3000 })
  try {
    const res = await API.resolveStream(`https://music.youtube.com/watch?v=${link.id}`)
    const song = res.data || {}
    usePlayer().setPlaylist([songToTrack(song)], { startIndex: 0 })
    toast(t('links.playing', { title: song.name || '' }), { icon: 'ph:play-fill', key: 'link' })
  } catch {
    toast(t('links.failed'), { tone: 'error', icon: 'ph:link-break', key: 'link' })
  }
}

/** The label a link is offered with in the search box. */
export function linkLabel(link) {
  if (!link) return ''
  const kind = link.kind === 'song' ? 'track' : link.kind
  return t(`links.open.${link.source}.${kind}`)
}

// Pasted anywhere in the window but a text box: opened. A link copied from
// Spotify or YouTube is the whole of what the person wants to do with it.
export function installLinkPaste() {
  if (typeof window === 'undefined') return
  window.addEventListener('paste', (e) => {
    const el = e.target
    if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
    if (el && el.closest && el.closest('[aria-modal="true"]')) return
    const text = e.clipboardData ? e.clipboardData.getData('text/plain') : ''
    if (!parseLink(text)) return
    e.preventDefault()
    openLink(text)
  })
}
