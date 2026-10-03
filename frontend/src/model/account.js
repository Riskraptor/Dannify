import { ref, computed, shallowRef } from 'vue'
import router from '/src/router'
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
const following = shallowRef([]) // artists the account follows
const followingIds = ref(new Set())
const history = shallowRef([]) // what it played lately on YouTube Music
// Whether songs played here go into the account's YouTube Music history,
// which is what its recommendations (Home, radio) are made from. On unless
// turned off, as it is in YouTube Music's own player.
const HISTORY_KEY = 'dn.ytHistory'
const sendHistory = ref((() => {
  try {
    return localStorage.getItem(HISTORY_KEY) !== '0'
  } catch {
    return true
  }
})())

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
    loadFollowing()
  } else {
    liked.value = []
    likedIds.value = new Set()
    likedLoaded.value = false
    playlists.value = []
    following.value = []
    followingIds.value = new Set()
    history.value = []
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

async function loadFollowing() {
  if (!signedIn.value) return
  try {
    const res = await API.getFollowing()
    following.value = (res.data && res.data.artists) || []
    followingIds.value = new Set(following.value.map((a) => a.browse_id))
  } catch {
    // following is an extra
  }
}

// An artist can have two ids: their page's (browse_id, which is what the
// list of followed artists holds) and their channel's (channel_id, which is
// what following is done with). They are often different, and checking
// only the channel had an artist the side bar listed as followed showing
// "Follow" on their own page. Either one in the list means followed.
function isFollowing(...ids) {
  return ids.some((id) => !!id && followingIds.value.has(id))
}

/** Follow or stop following an artist on YouTube Music (optimistic). */
async function toggleFollow(artist) {
  const id = artist && (artist.channel_id || artist.browse_id)
  if (!id) return false
  const ids = [artist.channel_id, artist.browse_id].filter(Boolean)
  const page = artist.browse_id || id
  if (!signedIn.value) {
    toast(t('account.signInToFollow'), {
      icon: 'ph:user-plus',
      action: { label: t('account.signIn'), run: () => signIn() },
    })
    return false
  }
  const next = !isFollowing(...ids)
  const before = followingIds.value
  const now = new Set(before)
  for (const each of ids) {
    if (next) now.add(each)
    else now.delete(each)
  }
  followingIds.value = now
  try {
    await API.setFollowing(id, next)
    const others = following.value.filter((a) => !ids.includes(a.browse_id))
    following.value = next
      ? [{ type: 'artist', browse_id: page, name: artist.name || '', cover_url: artist.cover_url || '' }, ...others]
      : others
    return true
  } catch {
    followingIds.value = before
    toast(t('account.followFailed'), { tone: 'error' })
    return false
  }
}

async function loadHistory() {
  if (!signedIn.value) return
  try {
    const res = await API.getHistory()
    history.value = (res.data && res.data.songs) || []
  } catch {
    // shown when there is one
  }
}

function setSendHistory(on) {
  sendHistory.value = !!on
  try {
    localStorage.setItem(HISTORY_KEY, on ? '1' : '0')
  } catch {
    // for this session only
  }
}

// Each song once in a while, not on every replay of it.
const reported = new Map()
/** A song was listened to (see player.js): into the account's history. */
function notePlayedOnAccount(track) {
  if (!signedIn.value || !sendHistory.value || !track) return
  const id = [track.video_id, track.song_id].find((v) => typeof v === 'string' && /^[A-Za-z0-9_-]{11}$/.test(v))
  if (!id) return
  const now = Date.now()
  if (now - (reported.get(id) || 0) < 10 * 60 * 1000) return
  reported.set(id, now)
  API.addHistory(id).catch(() => {})
}

if (typeof window !== 'undefined') {
  window.addEventListener('dannify:played', (e) => notePlayedOnAccount(e.detail))
}

/** Add songs to one of the account's YouTube Music playlists. */
async function addToYouTubePlaylist(playlist, videoIds) {
  const res = await API.addToYouTubePlaylist(playlist.browse_id, videoIds)
  return res.data
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
    // Whatever WebView2 said about it is for the log, not for a toast.
    if (result && result.error) toast(t('account.signInFailed'), { tone: 'error' })
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
    // The heart that was pressed already says so. Only on Liked Songs itself,
    // where the song leaves the list, is there something to take back.
    if (!next && router.currentRoute.value.name === 'Liked') {
      toast(t('account.removedFromLiked'), {
        icon: 'ph:heart-break',
        key: 'liked',
        action: { label: t('actions.undo'), run: () => toggleLike(song) },
      })
    }
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
    following,
    followingIds,
    history,
    sendHistory,
    displayName: computed(() => profile.value.name || ''),
    refresh,
    loadLiked,
    loadPlaylists,
    loadFollowing,
    isFollowing,
    toggleFollow,
    loadHistory,
    setSendHistory,
    notePlayedOnAccount,
    addToYouTubePlaylist,
    signIn,
    signOut,
    isLiked,
    toggleLike,
  }
}
