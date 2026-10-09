// What can be done to the lyrics on screen: fetch them again, show another
// version, keep a timing correction, or open the editor.
//
// The busy flags live at module level. The toolbar and the empty state's
// "Try again" are separate components, and two of them refreshing at once
// used to send two lookups for the same song.

import { ref, computed, watch, effectScope } from 'vue'
import { usePlayer } from '/src/model/player'
import { useConnectivity } from '/src/model/connectivity'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'
import { openLyricsEditor } from './publish'

const refreshing = ref(false)
const switching = ref(false)
const saving = ref(false)
const saved = ref(false)
let savedTimer = null
let watchingNetwork = false

export function useLyricsTools() {
  const player = usePlayer()
  const { online, isOffline, checking } = useConnectivity()

  const hasTrack = computed(() => !!player.currentTrack.value)
  const hasLines = computed(() => player.lyricsLines.value.length > 0)
  const plain = computed(() => player.lyricsPlain.value || '')
  const offset = computed(() => player.lyricsOffset.value || 0)
  // A negative count means "there are more, not yet counted".
  const hasVersions = computed(
    () => hasLines.value && (player.lyricVersionCount.value > 1 || player.lyricVersionCount.value < 0)
  )
  // Unknown until asked for: the lookup that found these lyrics skipped
  // counting the others, to be quick. "Version 1/1" said there were none.
  const versionsCounted = computed(() => player.lyricVersionCount.value > 0)
  const versionIndex = computed(() => (player.lyricVersionIndex.value || 0) + 1)
  const versionTotal = computed(() => Math.max(versionIndex.value, player.lyricVersionCount.value || 1))
  const loading = computed(
    () => (player.lyricsLoading.value || refreshing.value) && !hasLines.value && !plain.value
  )

  async function refresh() {
    if (refreshing.value) return
    refreshing.value = true
    try {
      await player.refreshLyrics()
    } finally {
      refreshing.value = false
    }
  }

  async function switchVersion() {
    if (switching.value) return
    switching.value = true
    try {
      await player.switchLyricVersion(1)
    } finally {
      switching.value = false
    }
  }

  async function saveOffset() {
    if (saving.value) return
    saving.value = true
    try {
      await player.saveLyricsOffset()
      saved.value = true
      clearTimeout(savedTimer)
      savedTimer = setTimeout(() => (saved.value = false), 2000)
    } catch {
      saved.value = false
      toast(t('lyrics.syncSaveFailed'), { tone: 'error', icon: 'ph:warning-circle' })
    } finally {
      saving.value = false
    }
  }

  // Lyrics that could not be fetched offline are fetched again the moment
  // the connection is back, instead of the view saying "none" for good.
  // Once for the app, in a scope of its own: made inside the first component
  // to ask, it would stop when that component went away.
  if (!watchingNetwork) {
    watchingNetwork = true
    effectScope(true).run(() =>
      watch(online, (on) => {
        if (!on || !player.currentTrack.value) return
        if (player.lyricsLines.value.length || player.lyricsPlain.value || player.lyricsLoading.value) return
        refresh()
      })
    )
  }

  return {
    hasTrack,
    hasLines,
    plain,
    offset,
    hasVersions,
    versionsCounted,
    versionIndex,
    versionTotal,
    loading,
    refreshing,
    switching,
    saving,
    saved,
    isOffline,
    checking,
    refresh,
    switchVersion,
    saveOffset,
    contribute: openLyricsEditor,
  }
}
