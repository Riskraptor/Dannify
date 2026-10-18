import router from '/src/router'
import { usePlayer } from '/src/model/player'
import { useUi } from '/src/model/ui'
import { useAccount } from '/src/model/account'
import { useTheme } from '/src/model/theme'
import { useLibrary, albumRoute } from '/src/model/library'
import { usePlaylists } from '/src/model/playlists'
import {
  currentRow,
  isRowDownloaded,
  likeCurrent,
  saveCurrent,
  songVideoId,
} from '/src/model/tracks'
import { desktop } from '/src/desktop/bridge'
import { t } from '/src/i18n'

// What the command palette offers (Ctrl+Shift+P): everywhere the app can go
// and everything it can be told to do, findable by typing a few letters of
// it. Made afresh each time the palette opens, so a command reads the way
// things are now ("Pause" while a song plays) and one that would do nothing
// is not there at all.
//
// A command is { id, group, title, icon, keys?, hint?, keywords?, run }.
// `keys` is the shortcut that does the same thing, shown beside it: the
// palette is also where the shortcuts get learned.

const PLAYLISTS = 60
const ARTISTS = 40
const ALBUMS = 40

export function buildCommands() {
  const player = usePlayer()
  const ui = useUi()
  const account = useAccount()
  const theme = useTheme()
  const lib = useLibrary()
  const playlists = usePlaylists()

  const row = currentRow()
  const hasQueue = player.playlist.value.length > 0
  const videoId = row ? songVideoId(row) : ''
  const go = (to) => () => router.push(to)

  const goTo = t('palette.groupGo')
  const playback = t('palette.groupPlayback')
  const view = t('palette.groupView')
  const appearance = t('palette.groupAppearance')
  const library = t('palette.groupLibrary')

  const repeatNow = {
    off: t('player.repeatOff'),
    all: t('player.repeatAll'),
    one: t('player.repeatOne'),
  }[player.repeatMode.value]

  return [
    // ----- places -----
    { id: 'go.home', group: goTo, title: t('nav.home'), icon: 'ph:house', run: go({ name: 'Home' }) },
    {
      id: 'go.search',
      group: goTo,
      title: t('nav.search'),
      icon: 'ph:magnifying-glass',
      keys: ['Ctrl', 'K'],
      run: () => {
        router.push({ name: 'Search' })
        ui.focusSearch()
      },
    },
    { id: 'go.songs', group: goTo, title: t('nav.yourSongs'), icon: 'ph:music-notes', run: go({ name: 'Library' }) },
    { id: 'go.artists', group: goTo, title: t('nav.artists'), icon: 'ph:users-three', run: go({ name: 'Artists' }) },
    { id: 'go.albums', group: goTo, title: t('albums.title'), icon: 'ph:vinyl-record', run: go({ name: 'Albums' }) },
    account.signedIn.value && {
      id: 'go.liked',
      group: goTo,
      title: t('account.likedSongs'),
      icon: 'ph:heart',
      run: go({ name: 'Liked' }),
    },
    { id: 'go.stats', group: goTo, title: t('stats.nav'), icon: 'ph:chart-bar', keywords: t('stats.title'), run: go({ name: 'Stats' }) },
    { id: 'go.history', group: goTo, title: t('history.title'), icon: 'ph:clock-counter-clockwise', run: go({ name: 'History' }) },
    { id: 'go.downloads', group: goTo, title: t('nav.downloads'), icon: 'ph:download-simple', run: go({ name: 'Downloads' }) },
    row && {
      id: 'go.nowPlaying',
      group: goTo,
      title: t('player.openNowPlaying'),
      icon: 'ph:arrows-out-simple',
      keys: ['Ctrl', 'E'],
      run: go({ name: 'NowPlaying' }),
    },
    { id: 'go.settings', group: goTo, title: t('nav.settings'), icon: 'ph:gear-six', keys: ['Ctrl', ','], run: go({ name: 'Settings' }) },

    // ----- the music -----
    hasQueue && {
      id: 'play.toggle',
      group: playback,
      title: player.isPlaying.value ? t('player.pause') : t('player.play'),
      icon: player.isPlaying.value ? 'ph:pause' : 'ph:play',
      keys: ['Space'],
      run: () => player.toggle(),
    },
    row && { id: 'play.next', group: playback, title: t('player.next'), icon: 'ph:skip-forward', keys: ['N'], run: () => player.next() },
    row && { id: 'play.prev', group: playback, title: t('player.previous'), icon: 'ph:skip-back', keys: ['P'], run: () => player.prev() },
    {
      id: 'play.shuffle',
      group: playback,
      title: player.shuffle.value ? t('palette.shuffleOff') : t('palette.shuffleOn'),
      icon: 'ph:shuffle',
      keys: ['S'],
      keywords: t('player.shuffle'),
      run: () => player.toggleShuffle(),
    },
    {
      id: 'play.repeat',
      group: playback,
      title: t('palette.repeat'),
      hint: repeatNow,
      icon: 'ph:repeat',
      keys: ['R'],
      run: () => player.cycleRepeat(),
    },
    {
      id: 'play.mute',
      group: playback,
      title: player.isMuted.value ? t('player.unmute') : t('player.mute'),
      icon: player.isMuted.value ? 'ph:speaker-high' : 'ph:speaker-x',
      keys: ['M'],
      run: () => player.toggleMute(),
    },
    videoId && {
      id: 'play.like',
      group: playback,
      title: account.isLiked(videoId) ? t('account.removeFromLiked') : t('account.addToLiked'),
      icon: account.isLiked(videoId) ? 'ph:heart-break' : 'ph:heart',
      keys: ['L'],
      run: () => likeCurrent(),
    },
    row &&
      !isRowDownloaded(row) && {
        id: 'play.save',
        group: playback,
        title: t('player.saveToLibrary'),
        icon: 'ph:arrow-circle-down',
        keys: ['Ctrl', 'D'],
        keywords: t('actions.download'),
        run: () => saveCurrent(),
      },
    videoId && {
      id: 'play.radio',
      group: playback,
      title: t('actions.startRadio'),
      icon: 'ph:broadcast',
      run: () => player.startRadio(row.raw),
    },
    ...[15, 30, 60].map(
      (minutes) =>
        hasQueue && {
          id: `sleep.${minutes}`,
          group: playback,
          title: t('palette.sleepIn', { count: minutes }),
          icon: 'ph:moon',
          run: () => player.setSleepTimer(minutes),
        }
    ),
    row && {
      id: 'sleep.track',
      group: playback,
      title: t('palette.sleepEnd'),
      icon: 'ph:moon',
      run: () => player.setSleepAfterTrack(),
    },
    player.sleepMode.value !== 'off' && {
      id: 'sleep.off',
      group: playback,
      title: t('palette.sleepOff'),
      icon: 'ph:moon-stars',
      run: () => player.cancelSleep(),
    },

    // ----- what is on screen -----
    row && { id: 'view.lyrics', group: view, title: t('shortcuts.lyrics'), icon: 'ph:microphone-stage', keys: ['Ctrl', 'L'], run: () => ui.setPanel('lyrics') },
    hasQueue && { id: 'view.queue', group: view, title: t('shortcuts.queue'), icon: 'ph:queue', keys: ['Ctrl', 'Q'], run: () => ui.setPanel('queue') },
    row && { id: 'view.about', group: view, title: t('panel.aboutButton'), icon: 'ph:vinyl-record', run: () => ui.setPanel('about') },
    !ui.forceRail.value &&
      !ui.isCompact.value && {
        id: 'view.sidebar',
        group: view,
        title: ui.sidebarCollapsedPref.value ? t('nav.expandSidebar') : t('nav.collapseSidebar'),
        icon: 'ph:sidebar-simple',
        keys: ['Ctrl', 'B'],
        run: () => ui.toggleSidebar(),
      },
    desktop.isDesktop && {
      id: 'view.mini',
      group: view,
      title: t('player.miniPlayer'),
      icon: 'ph:picture-in-picture',
      keys: ['Ctrl', 'Shift', 'M'],
      run: () => desktop.setMini(true),
    },
    desktop.isDesktop && {
      id: 'view.fullscreen',
      group: view,
      title: desktop.state.fullscreen ? t('window.exitFullscreen') : t('window.fullscreen'),
      icon: 'ph:corners-out',
      keys: ['F11'],
      run: () => desktop.toggleFullscreen(),
    },
    {
      id: 'view.shortcuts',
      group: view,
      title: t('shortcuts.title'),
      icon: 'ph:keyboard',
      keys: ['Ctrl', '/'],
      run: () => {
        ui.shortcutsOpen.value = true
      },
    },

    // ----- how it looks -----
    ...[
      ['system', 'palette.themeSystem', 'ph:circle-half'],
      ['light', 'palette.themeLight', 'ph:sun'],
      ['dark', 'palette.themeDark', 'ph:moon'],
    ].map(
      ([mode, label, icon]) =>
        theme.preference.value !== mode && {
          id: `theme.${mode}`,
          group: appearance,
          title: t(label),
          icon,
          keywords: t('settings.theme'),
          run: () => theme.setPreference(mode),
        }
    ),
    ...theme.themes.map(
      (palette) =>
        theme.currentTheme.value !== palette.id && {
          id: `palette.${palette.id}`,
          group: appearance,
          title: t('palette.usePalette', { name: t(palette.name) }),
          icon: 'ph:palette',
          swatch: palette.accent,
          keywords: `${t('settings.theme')} ${t(palette.mode === 'dark' ? 'settings.themeDark' : 'settings.themeLight')}`,
          run: () => theme.setTheme(palette.id),
        }
    ),

    // ----- what is yours -----
    { id: 'lib.newPlaylist', group: library, title: t('playlists.new'), icon: 'ph:plus', run: () => playlists.createPlaylist() },
    ...playlists.recent.value.slice(0, PLAYLISTS).map((p) => ({
      id: `playlist.${p.id}`,
      group: library,
      title: t('palette.openPlaylist', { name: p.name }),
      icon: 'ph:playlist',
      run: go({ name: 'Playlist', params: { id: p.id } }),
    })),
    ...[...lib.artists.value]
      .filter((a) => a && a.name)
      .sort((a, b) => (b.count || 0) - (a.count || 0))
      .slice(0, ARTISTS)
      .map((a) => ({
        id: `artist.${a.name}`,
        group: library,
        title: t('palette.openArtist', { name: a.name }),
        icon: 'ph:user',
        run: go({ name: 'Artist', params: { name: a.name } }),
      })),
    ...[...lib.albums.value]
      .sort((a, b) => (b.added || 0) - (a.added || 0))
      .slice(0, ALBUMS)
      .map((a) => ({
        id: `album.${a.artist}|${a.name}`,
        group: library,
        title: t('palette.openAlbum', { name: a.name }),
        hint: a.artist,
        icon: 'ph:vinyl-record',
        keywords: a.artist,
        run: go(albumRoute(a)),
      })),
  ].filter(Boolean)
}
