import { ref, watch } from 'vue'
import API from '/src/model/api'
import { t } from '/src/i18n'
import { currentTime, currentTrack, duration, isPlaying, playbackRate } from '/src/model/player/state'

// Discord: the song playing, on the person's profile. The backend does the
// talking to Discord (Backend/dannify/presence.py); this says what is
// playing, when that changes. Off until it is turned on in Settings, and
// while it is off nothing is sent at all.

export const discordOn = ref(false)
// Whether the Discord app on this computer is there to show it.
export const discordConnected = ref(false)

let started = false
let timer = 0
// What was last sent, to tell a seek from the song simply playing on.
let last = null

function keyOf(track) {
  return track ? `${track.file || ''}|${track.video_id || ''}|${track.url || ''}` : ''
}

function snapshot() {
  const track = currentTrack.value
  if (!track || !track.title) return { playing: false }
  // Only artwork Discord can fetch itself. A saved song's is on this
  // computer; the backend finds it online instead.
  const cover = typeof track.cover === 'string' && track.cover.startsWith('https://') ? track.cover : ''
  return {
    title: track.title,
    artist: track.artist || '',
    album: track.album || '',
    cover,
    video_id: track.video_id || '',
    duration: duration.value || track.duration || 0,
    position: currentTime.value || 0,
    playing: isPlaying.value,
    button: t('discord.button'),
  }
}

function send() {
  timer = 0
  if (!discordOn.value) return
  const song = snapshot()
  last = { playing: song.playing, position: song.position || 0, at: Date.now(), rate: playbackRate.value || 1 }
  API.discordNowPlaying(song).catch(() => {
    // The backend is busy restarting: the next change says it again.
  })
}

function soon(wait = 400) {
  if (!discordOn.value) return
  clearTimeout(timer)
  timer = setTimeout(send, wait)
}

function show(data) {
  if (!data || typeof data !== 'object') return
  const was = discordOn.value
  discordOn.value = !!data.enabled
  discordConnected.value = !!data.connected
  if (discordOn.value && !was) soon(0)
}

export async function refreshDiscord() {
  try {
    show((await API.discordStatus()).data)
  } catch {
    // Settings shows what it last knew.
  }
}

/** Turn it on or off. Throws when the backend could not be told. */
export async function setDiscord(on) {
  show((await API.setDiscord(!!on)).data)
  // Finding Discord takes the backend a moment.
  if (on) setTimeout(refreshDiscord, 1500)
}

export function startPresence() {
  if (started || typeof window === 'undefined') return
  started = true
  watch(() => keyOf(currentTrack.value), () => soon())
  watch(isPlaying, () => soon())
  watch(playbackRate, () => soon())
  // The length is known once the song has loaded: the progress bar needs it.
  watch(duration, (now, before) => {
    if (now && !before) soon()
  })
  // A seek: the playhead is somewhere the clock says it should not be.
  watch(currentTime, (at) => {
    if (!last || !last.playing || !isPlaying.value || timer) return
    const expected = last.position + ((Date.now() - last.at) / 1000) * last.rate
    if (Math.abs(at - expected) > 2.5) soon(250)
  })
  // Nothing about Discord is needed to start: asked once the window is up.
  setTimeout(refreshDiscord, 4000)
}
