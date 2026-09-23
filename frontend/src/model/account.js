import { ref, computed, shallowRef } from 'vue'
import API from '/src/model/api'
import { desktop } from '/src/desktop/bridge'
import { toast } from '/src/model/toast'
import { t } from '/src/i18n'

// Signed-in YouTube Music account: profile, liked songs and the like/unlike
// action. Signing in happens in a real Google window opened by the desktop
// shell (see Backend/desktop.py); the browser build can only read the state.

const profile = ref({})
const signedIn = ref(false)
const busy = ref(false)
const liked = shallowRef([]) // big list: no deep reactivity needed
const likedIds = ref(new Set())
const likedLoaded = ref(false)
const playlists = shallowRef([]) // the account's own YouTube Music playlists

async function refresh() {
  try {
    const res = await API.getAccount()
    signedIn.value = !!res.data.signed_in
    profile.value = res.data.profile || {}
  } catch {
    signedIn.value = false
    profile.value = {}
  }
  if (signedIn.value) {
    loadLiked()
    loadPlaylists()
  } else {
    liked.value = []
    likedIds.value = new Set()
    likedLoaded.value = false
    playlists.value = []
  }
  return signedIn.value
}

async function loadLiked(force = false) {
  if (!signedIn.value || (likedLoaded.value && !force)) return
  try {
    const res = await API.getLikedSongs()
    liked.value = res.data.songs || []
    likedIds.value = new Set(liked.value.map((s) => s.song_id || s.video_id))
    likedLoaded.value = true
  } catch {
    // stay silent: likes are an extra, not a requirement
  }
}

async function loadPlaylists() {
  if (!signedIn.value) return
  try {
    const res = await API.getLibraryPlaylists()
    playlists.value = (res.data && res.data.playlists) || []
  } catch {
    playlists.value = []
  }
}

/** Open the Google sign-in window (desktop only). */
async function signIn() {
  if (!desktop.isDesktop) {
    toast(t('account.desktopOnly'), { tone: 'error' })
    return false
  }
  busy.value = true
  try {
    const result = await desktop.accountSignIn()
    await refresh()
    if (signedIn.value) {
      toast(t('account.signedInAs', { name: profile.value.name || '' }), {
        tone: 'success',
        icon: 'ph:user-circle',
      })
      window.dispatchEvent(new CustomEvent('dannify:account-changed'))
      return true
    }
    if (result && result.error) toast(result.error, { tone: 'error' })
    return false
  } finally {
    busy.value = false
  }
}


async function signOut() {
  busy.value = true
  try {
    await API.signOutAccount()
    await desktop.accountClearSession()
    await refresh()
    window.dispatchEvent(new CustomEvent('dannify:account-changed'))
    toast(t('account.signedOut'), { icon: 'ph:user-circle' })
  } catch {
    toast(t('account.signOutFailed'), { tone: 'error' })
  } finally {
    busy.value = false
  }
}

function isLiked(videoId) {
  return !!videoId && likedIds.value.has(videoId)
}

/** Like / unlike on YouTube Music (optimistic, reverted on failure). */
async function toggleLike(song) {
  const id = song && (song.video_id || song.song_id)
  if (!id) return false
  if (!signedIn.value) {
    toast(t('account.signInToLike'), {
      icon: 'ph:heart',
      action: { label: t('account.signIn'), run: () => signIn() },
    })
    return false
  }
  const next = !isLiked(id)
  const ids = new Set(likedIds.value)
  if (next) ids.add(id)
  else ids.delete(id)
  likedIds.value = ids
  try {
    await API.rateSong(id, next)
    if (next) {
      liked.value = [{ ...song, song_id: id, video_id: id }, ...liked.value.filter((s) => (s.song_id || s.video_id) !== id)]
    } else {
      liked.value = liked.value.filter((s) => (s.song_id || s.video_id) !== id)
    }
    toast(next ? t('account.addedToLiked') : t('account.removedFromLiked'), {
      icon: next ? 'ph:heart-fill' : 'ph:heart-break',
    })
    return true
  } catch {
    const revert = new Set(likedIds.value)
    if (next) revert.delete(id)
    else revert.add(id)
    likedIds.value = revert
    toast(t('account.likeFailed'), { tone: 'error' })
    return false
  }
}

refresh()

export function useAccount() {
  return {
    signedIn,
    profile,
    busy,
    liked,
    likedIds,
    likedLoaded,
    playlists,
    displayName: computed(() => profile.value.name || ''),
    refresh,
    loadLiked,
    loadPlaylists,
    signIn,
    signOut,
    isLiked,
    toggleLike,
  }
}
