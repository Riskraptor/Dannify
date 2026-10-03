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
import { vOverlayScroll } from './model/overlayScroll'

import './index.css'

// Every icon ships inside the bundle: nothing is fetched at runtime.
addCollection(icons)

const app = createApp(App)
installErrorReporting(app)
app.directive('overlay-scroll', vOverlayScroll)
app.use(router)
installShortcuts()
installDesktopIntegration()
app.mount('#app')
startArtAccent()
