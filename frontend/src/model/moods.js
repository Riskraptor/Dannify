import { ref } from 'vue'
import API from '/src/model/api'

// Moods and genres from YouTube Music, for Search before anything is typed
// (and each one's page of playlists). Read once a session; the server keeps
// them for half a day.

const sections = ref([])
const loaded = ref(false)
const failed = ref(false)
let loading = null

export function loadMoods() {
  if (loaded.value && sections.value.length) return Promise.resolve()
  if (!loading) {
    loading = API.getMoods()
      .then((res) => {
        sections.value = (res.data && res.data.sections) || []
        failed.value = false
      })
      .catch(() => {
        failed.value = true
      })
      .finally(() => {
        loaded.value = true
        loading = null
      })
  }
  return loading
}

// Bold, distinct colours, each mood keeping the same one every time.
const COLOURS = [
  '#e13300', '#1e3264', '#8d67ab', '#148a08', '#e8115b', '#477d95', '#ba5d07',
  '#509bf5', '#af2896', '#e91429', '#0d73ec', '#8400e7', '#7358ff', '#27856a',
  '#d84000', '#503750', '#056952', '#b06239', '#f037a5', '#283ea8',
]

export function moodColour(title) {
  let h = 0
  for (const ch of String(title || '')) h = (h * 31 + ch.codePointAt(0)) >>> 0
  return COLOURS[h % COLOURS.length]
}

// A picture for the tile, by what the mood is called.
const GLYPHS = [
  [/chill|relax|calm/i, 'ph:coffee'],
  [/commute|drive|road/i, 'ph:car-profile'],
  [/energ|power|pump/i, 'ph:lightning'],
  [/feel good|happy|good vibes/i, 'ph:smiley'],
  [/focus|study|concentr/i, 'ph:target'],
  [/gaming|game/i, 'ph:game-controller'],
  [/party|club|dance/i, 'ph:confetti'],
  [/romance|love/i, 'ph:heart'],
  [/sad|heartbreak|melanchol/i, 'ph:cloud-rain'],
  [/sleep|night/i, 'ph:moon-stars'],
  [/workout|fitness|gym/i, 'ph:barbell'],
  [/classical|piano|orchestr/i, 'ph:piano-keys'],
  [/gospel|christian|worship/i, 'ph:church'],
  [/hip.?hop|rap/i, 'ph:microphone'],
  [/rock|metal|indie|alternative/i, 'ph:guitar'],
  [/pop/i, 'ph:star'],
  [/african|afro|amapiano/i, 'ph:globe-hemisphere-east'],
  [/jazz|blues|soul/i, 'ph:vinyl-record'],
  [/electronic|edm|house|techno/i, 'ph:wave-sine'],
  [/reggae|caribbean|latin/i, 'ph:sun'],
  [/country|folk/i, 'ph:leaf'],
  [/r&b|r and b/i, 'ph:headphones'],
  [/decade|throwback|[0-9]0s/i, 'ph:radio'],
]

export function moodGlyph(title) {
  const found = GLYPHS.find(([re]) => re.test(String(title || '')))
  return found ? found[1] : 'ph:music-notes'
}

export function useMoods() {
  return { sections, loaded, failed, load: loadMoods }
}
