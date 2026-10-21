// Must run first: detects the desktop shell and strips its URL marker
// before the router reads the address.
import './desktop/bridge'

import { createApp } from 'vue'
import { addCollection } from '@iconify/vue'
import icons from 'virtual:dannify-icons'
import App from './App.vue'
import router from './router/index'
import './model/theme'
import { installShortcuts } from './desktop/shortcuts'
import { installDesktopIntegration } from './desktop/integration'
import { startArtAccent } from './model/artAccent'
import { installErrorReporting } from './model/problems'
import { startListening } from './model/listens'
import { watchAttention } from './model/power'
import { localeReady } from './i18n'
import { vOverlayScroll } from './model/overlayScroll'

import './index.css'

// Every icon ships inside the bundle: nothing is fetched at runtime.
addCollection(icons)

// A part of the app fetched when first needed (the mini player, a page) that
// could not be read, because its files were replaced while this window was
// open: the page is read again, once, instead of that part staying blank.
const RELOADED = 'dannify-reloaded'
window.addEventListener('vite:preloadError', (event) => {
  try {
    if (sessionStorage.getItem(RELOADED)) return
    sessionStorage.setItem(RELOADED, '1')
  } catch {
    return
  }
  event.preventDefault()
  location.reload()
})
setTimeout(() => {
  try {
    sessionStorage.removeItem(RELOADED)
  } catch {
    // nothing kept, nothing to clear
  }
}, 15000)

const app = createApp(App)
installErrorReporting(app)
app.directive('overlay-scroll', vOverlayScroll)
app.use(router)
installShortcuts()
installDesktopIntegration()
// Drawn once the language it starts in has arrived: a moment for anything
// but English, and no flash of English before it.
localeReady.finally(() => app.mount('#app'))
startArtAccent()
startListening()
watchAttention()
