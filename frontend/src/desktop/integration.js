import { watch } from 'vue'
import router from '/src/router'
import { desktop } from '/src/desktop/bridge'
import { usePlayer } from '/src/model/player'
import { useDownloadStats } from '/src/model/downloadStats'
import { useProgressTracker } from '/src/model/download'
import { toast } from '/src/model/toast'
import { openLink } from '/src/model/links'
import { t, currentLocale } from '/src/i18n'
import en from '/src/i18n/locales/en.js'

// Every special day with a greeting of its own.
const OCCASION_IDS = Object.keys(en.occasion).filter((id) => id !== 'national' && en.occasion[id]?.title)

// Wires app state into the desktop: taskbar (or dock) progress while
// downloading, the play/pause/next buttons under the Windows taskbar
// thumbnail, the tray, the Linux media panel (MPRIS), and commands coming
// back from all of them. On Android, the same "now playing" drives the
// phone's media notification, lock screen and headsets.

let installed = false

export function installDesktopIntegration() {
  if (installed) return
  installed = true
  const player = usePlayer()
  const stats = useDownloadStats()

  // Commands from the taskbar buttons, the tray, media keys (Python → JS).
  // "seek:<seconds>" comes from a media panel's timeline.
  window.__dannifyMedia = (cmd) => {
    const text = String(cmd || '')
    if (text.startsWith('seek:')) {
      const at = Number(text.slice(5))
      if (Number.isFinite(at) && at >= 0) player.seek(at)
      return
    }
    player.mediaCommand(text)
  }

  // Downloads finishing cleanly is the expected outcome and the indicator
  // already shows it, so only a failure is worth interrupting for: that is
  // something the user has to decide about. One summary per batch, when the
  // last of it is done.
  //
  // It used to count every failed row in the list. Failed rows stay there
  // until someone clears or retries them (they even come back after a
  // restart), so once one download had failed, every later batch that
  // went perfectly still ended with "Downloads finished. 1 failed" about
  // the same old song, again and again. Now only a song this session saw
  // queued or downloading and then fail is counted, and counted once.
  const { downloadQueue } = useProgressTracker()
  const inFlight = new Set()
  let failedThisBatch = 0
  watch(
    // Status changes only: progress ticks do not need to wake this up.
    () => downloadQueue.value.map((item) => `${item.song.song_id}:${item.web_status}`).join('|'),
    () => {
      const present = new Set()
      let active = 0
      for (const item of downloadQueue.value) {
        const id = item.song.song_id
        present.add(id)
        if (item.isPending()) {
          active += 1
          inFlight.add(id)
        } else if (inFlight.delete(id) && item.isErrored()) {
          failedThisBatch += 1
        }
      }
      // Rows removed from the list are not coming back to finish.
      for (const id of inFlight) if (!present.has(id)) inFlight.delete(id)
      if (active > 0 || failedThisBatch === 0) return
      const failed = failedThisBatch
      failedThisBatch = 0
      // Already looking at them, retry buttons and all.
      if (router.currentRoute.value.name === 'Downloads') return
      toast(t('downloads.finishedWithErrors', { failed }), {
        tone: 'error',
        action: {
          label: t('actions.view'),
          run: () => router.push({ name: 'Downloads' }),
        },
      })
    }
  )

  if (desktop.isAndroid) installAndroid()
  if (!desktop.isDesktop && !desktop.isAndroid) return

  // What is playing: the taskbar's buttons and media panels on a desktop,
  // the media notification and lock screen on a phone.
  let lastPlayback = ''
  watch(
    () => ({
      playing: player.isPlaying.value,
      hasTrack: !!player.currentTrack.value,
      title: player.currentTrack.value ? player.currentTrack.value.title : '',
      artist: player.currentTrack.value ? player.currentTrack.value.artist : '',
      // For media panels (MPRIS): the rest of what they show.
      ...mediaDetails(player),
      // Tooltips for the taskbar thumbnail buttons, in the UI language.
      labels: {
        prev: t('player.previous'),
        play: t('player.play'),
        pause: t('player.pause'),
        next: t('player.next'),
      },
    }),
    (s) => {
      const key = JSON.stringify(s)
      if (key === lastPlayback) return
      lastPlayback = key
      // Where the song is now: read here, not watched, or every frame of
      // playback would send the whole state again.
      desktop.setPlaybackState({ ...s, position: Number(player.currentTime.value) || 0 })
    },
    { immediate: true }
  )

  // A seek inside the app moves the media panel's timeline too.
  watch(
    () => Math.round(player.currentTime.value / 15),
    () => {
      if (!player.currentTrack.value) return
      const s = JSON.parse(lastPlayback || '{}')
      desktop.setPlaybackState({ ...s, position: Number(player.currentTime.value) || 0 })
    }
  )

  // Songs being saved: the taskbar (or dock) button's bar on a desktop. On a
  // phone, a notification that also keeps them going with the app put away,
  // in the interface's own words.
  let lastProgress = ''
  watch(
    () => [stats.value.active, Math.round(stats.value.percent)],
    ([active, percent]) => {
      if (desktop.isAndroid) {
        const key = active ? `n:${active}:${percent}` : 'none'
        if (key === lastProgress) return
        lastProgress = key
        desktop.setDownloads(
          active ? { active, percent, text: t('downloads.tooltipActive', { active, percent }) } : null
        )
        return
      }
      const key = active ? `n:${percent}` : 'none'
      if (key === lastProgress) return
      lastProgress = key
      desktop.setTaskbarProgress(active ? Math.max(2, percent) / 100 : 0, active ? 'normal' : 'none')
    }
  )

  if (!desktop.isDesktop) return

  // Tray menu strings, in the UI language. Re-sent when the language
  // changes so the notification area never falls back to English. The
  // splash, shown at the next start before this page is, gets its words too.
  watch(
    () => currentLocale.value,
    (lang) => {
      desktop.setTrayLabels({
        nowPlaying: t('tray.nowPlaying'),
        play: t('player.play'),
        pause: t('player.pause'),
        prev: t('player.previous'),
        next: t('player.next'),
        show: t('tray.show'),
        quit: t('tray.quit'),
        hidden: t('tray.hidden'),
      })
      desktop.setSplashWords({
        lang,
        starting: t('common.starting'),
        national: t('occasion.national.title'),
        titles: Object.fromEntries(OCCASION_IDS.map((id) => [id, t(`occasion.${id}.title`)])),
      })
    },
    { immediate: true }
  )
}

function mediaDetails(player) {
  const track = player.currentTrack.value
  if (!track) return { album: '', cover: '', duration: 0, key: '', next: null }
  const song = track._song || {}
  // The song after this one: the phone's notification offers "next" with it.
  const coming = player.upcoming.value && player.upcoming.value[0]
  return {
    album: track.album || song.album_name || '',
    cover: track.cover || song.cover_url || '',
    duration: Math.floor(Number(player.duration.value) || Number(track.duration) || 0),
    key: String(track.id || track.src || song.song_id || ''),
    next: coming ? { title: coming.title || '', artist: coming.artist || '' } : null,
  }
}

// The Android app: links shared to it, and its back button.
function installAndroid() {
  // A Spotify or YouTube link shared to Dannify, or opened with it. The app
  // keeps it until it is taken, so a link shared while the page was still
  // loading is opened once it is up, and only once.
  const openShared = () =>
    desktop.takeSharedLink().then((link) => {
      if (link) openLink(link)
    })
  window.__dannifyOpen = openShared
  openShared()
  // Back: whatever is open closes first (anything Escape closes), then the
  // page goes back. Nothing left to close or go back to: the app steps
  // aside and the music plays on.
  window.__dannifyBack = () => {
    const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    ;(document.activeElement || document.body).dispatchEvent(escape)
    if (escape.defaultPrevented) return true
    if (window.history.state && window.history.state.back) {
      router.back()
      return true
    }
    return false
  }
}
