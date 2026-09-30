import { watch } from 'vue'
import router from '/src/router'
import { desktop } from '/src/desktop/bridge'
import { usePlayer } from '/src/model/player'
import { useDownloadStats } from '/src/model/downloadStats'
import { useProgressTracker } from '/src/model/download'
import { toast } from '/src/model/toast'
import { t, currentLocale } from '/src/i18n'

// Wires app state into Windows: taskbar progress while downloading, the
// play/pause/next buttons under the taskbar thumbnail, and commands coming
// back from those buttons.

let installed = false

export function installDesktopIntegration() {
  if (installed) return
  installed = true
  const player = usePlayer()
  const stats = useDownloadStats()

  // Commands from the taskbar thumbnail toolbar (Python → JS).
  window.__dannifyMedia = (cmd) => player.mediaCommand(String(cmd || ''))

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

  if (!desktop.isDesktop) return

  // Taskbar button progress bar mirrors the download queue.
  let lastProgress = ''
  watch(
    () => [stats.value.active, Math.round(stats.value.percent)],
    ([active, percent]) => {
      const key = active ? `n:${percent}` : 'none'
      if (key === lastProgress) return
      lastProgress = key
      desktop.setTaskbarProgress(active ? Math.max(2, percent) / 100 : 0, active ? 'normal' : 'none')
    }
  )

  // Thumbnail toolbar: keep the play/pause glyph and enabled states in sync.
  let lastPlayback = ''
  watch(
    () => ({
      playing: player.isPlaying.value,
      hasTrack: !!player.currentTrack.value,
      title: player.currentTrack.value ? player.currentTrack.value.title : '',
      artist: player.currentTrack.value ? player.currentTrack.value.artist : '',
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
      desktop.setPlaybackState(s)
    },
    { immediate: true }
  )

  // Tray menu strings, in the UI language. Re-sent when the language
  // changes so the notification area never falls back to English.
  watch(
    () => currentLocale.value,
    () =>
      desktop.setTrayLabels({
        nowPlaying: t('tray.nowPlaying'),
        play: t('player.play'),
        pause: t('player.pause'),
        prev: t('player.previous'),
        next: t('player.next'),
        show: t('tray.show'),
        quit: t('tray.quit'),
        hidden: t('tray.hidden'),
      }),
    { immediate: true }
  )
}
