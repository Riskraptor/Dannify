import { createWebHistory, createRouter } from 'vue-router'
import Home from '/src/views/Home.vue'
import Library from '/src/views/Library.vue'
import config from '/src/config'
import { ensureFullWindow } from '/src/desktop/fullWindow'

// Home and Songs are where the app opens, so they come with it. Every other
// page is its own file, read the first time it is needed: the window has less
// to read before it can show anything. They are all fetched quietly once the
// app has settled (below), so going to one later is still instant.
const Search = () => import('/src/views/Search.vue')
const Artists = () => import('/src/views/Artists.vue')
const Artist = () => import('/src/views/Artist.vue')
const Downloads = () => import('/src/views/Downloads.vue')
const Liked = () => import('/src/views/Liked.vue')
const Playlist = () => import('/src/views/Playlist.vue')
const NowPlaying = () => import('/src/views/NowPlaying.vue')
const ExploreArtist = () => import('/src/views/ExploreArtist.vue')
const ExploreCollection = () => import('/src/views/ExploreCollection.vue')
const Settings = () => import('/src/views/Settings.vue')
const Mood = () => import('/src/views/Mood.vue')

const routes = [
  { path: '/', name: 'Home', component: Home },
  { path: '/search/:query?', name: 'Search', component: Search },
  { path: '/library', name: 'Library', component: Library },
  { path: '/artists', name: 'Artists', component: Artists },
  { path: '/artists/:name', name: 'Artist', component: Artist },
  { path: '/liked', name: 'Liked', component: Liked },
  { path: '/playlists/:id', name: 'Playlist', component: Playlist },
  { path: '/downloads', name: 'Downloads', component: Downloads, alias: '/download' },
  { path: '/now-playing', name: 'NowPlaying', component: NowPlaying, alias: '/player' },
  { path: '/explore/artist/:id', name: 'ExploreArtist', component: ExploreArtist },
  {
    path: '/explore/album/:id',
    name: 'ExploreAlbum',
    component: ExploreCollection,
    props: { mode: 'album' },
  },
  {
    path: '/explore/playlist/:id',
    name: 'ExplorePlaylist',
    component: ExploreCollection,
    props: { mode: 'playlist' },
  },
  { path: '/settings', name: 'Settings', component: Settings },
  { path: '/browse/:params', name: 'Mood', component: Mood },
  { path: '/:pathMatch(.*)*', redirect: { name: 'Home' } },
]

const router = createRouter({
  history: createWebHistory(config.BASEURL),
  routes,
})

// A page's file that cannot be read is almost always one the app no longer
// has: it was updated while this window stayed open, and the file names
// changed with it. Opening the page afresh reads the new ones. Once: if that
// fails too, the error is real and reloading again would only loop.
const RELOADED = 'dn.chunkReload'
router.onError((err, to) => {
  const text = String((err && err.message) || err || '')
  if (!/dynamically imported module|module script failed|Loading chunk|Importing a module/i.test(text)) return
  let last = 0
  try {
    last = Number(sessionStorage.getItem(RELOADED) || 0)
    sessionStorage.setItem(RELOADED, String(Date.now()))
  } catch {
    // storage blocked: the reload still happens, just not the guard
  }
  if (Date.now() - last < 15000) return
  window.location.assign(to ? router.resolve(to).href : window.location.href)
})

// Going to a page from the mini player ("Go to artist", "Open" on a notice):
// the page is the point, so the full window comes back to show it.
router.afterEach((to, from) => {
  if (from.matched.length && to.fullPath !== from.fullPath) ensureFullWindow()
})

// Fetch the other pages once things are quiet, so none waits on its file.
function warmPages() {
  for (const load of [Search, Artists, Artist, Downloads, Liked, Playlist, NowPlaying, ExploreArtist, ExploreCollection, Settings, Mood]) {
    load().catch(() => {})
  }
}
if (typeof window !== 'undefined') {
  const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 1500))
  setTimeout(() => idle(warmPages, { timeout: 4000 }), 2500)
}

export default router
