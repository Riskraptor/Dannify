// One key per song, whatever version of it a list is showing.
//
// YouTube lists a song as the album track, its music video, its lyric video
// and its visualizer, each with a title of its own: "Commando",
// "Commando (Official Music Video)", "Mavokali - Commando (Lyrics)". Those are
// one song. A remix, a live take, an acoustic or a slowed version is a song of
// its own, so a bracket that says so is kept.

const BRACKET = /\s*[([]([^)\]]*)[)\]]/g
const OTHER_VERSION =
  /\b(?:remix|mix|live|acoustic|version|edit|slowed|sped|reverb|instrumental|cover|reprise|extended|unplugged|acapella|a cappella|demo|karaoke)\b/i
const PACKAGING =
  /\b(?:official|video|audio|lyrics?|visuali[sz]er|hd|hq|4k|mv|clip|oficial|officiel|feat\.?|ft\.?|featuring|with)\b/i
const TRAIL_GUEST = /\s+(?:feat\.?|ft\.?|featuring)\s.*$/i
const SAYS_VIDEO = /\b(?:official|lyrics?|video|audio|visuali[sz]er)\b/i

export function songKey(title, artist = '') {
  let s = String(title || '')
  // "Artist - Title (Official Video)", as videos are often named.
  const dash = s.indexOf(' - ')
  if (dash > 0) {
    const head = fold(s.slice(0, dash))
    if ((artist && head.includes(fold(artist))) || (!artist && SAYS_VIDEO.test(s))) {
      s = s.slice(dash + 3)
    }
  }
  s = s.replace(BRACKET, (whole, inner) =>
    OTHER_VERSION.test(inner) || !PACKAGING.test(inner) ? whole : ''
  )
  s = s.replace(TRAIL_GUEST, '')
  return fold(s)
}

function fold(text) {
  return String(text || '')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
}
