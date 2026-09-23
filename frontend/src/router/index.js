import { createWebHistory, createRouter } from 'vue-router'
import Home from '/src/views/Home.vue'
import Search from '/src/views/Search.vue'
import Library from '/src/views/Library.vue'
import Artists from '/src/views/Artists.vue'
import Artist from '/src/views/Artist.vue'
import Downloads from '/src/views/Downloads.vue'
import Liked from '/src/views/Liked.vue'
import NowPlaying from '/src/views/NowPlaying.vue'
import ExploreArtist from '/src/views/ExploreArtist.vue'
import ExploreCollection from '/src/views/ExploreCollection.vue'
import Settings from '/src/views/Settings.vue'
import config from '/src/config'

const routes = [
  { path: '/', name: 'Home', component: Home },
  { path: '/search/:query?', name: 'Search', component: Search },
  { path: '/library', name: 'Library', component: Library },
  { path: '/artists', name: 'Artists', component: Artists },
  { path: '/artists/:name', name: 'Artist', component: Artist },
  { path: '/liked', name: 'Liked', component: Liked },
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
  { path: '/:pathMatch(.*)*', redirect: { name: 'Home' } },
]

const router = createRouter({
  history: createWebHistory(config.BASEURL),
  routes,
})

export default router
