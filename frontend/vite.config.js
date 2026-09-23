import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const SRC_DIR = fileURLToPath(new URL('./src', import.meta.url))

// Bundle ONLY the Phosphor icons the app references, straight into the JS.
// The desktop app must render every icon offline — the stock @iconify/vue
// build would otherwise fetch each icon from api.iconify.design at runtime.
// Icons are discovered by scanning src/ for 'ph:<name>' string literals, so
// always write icon names in full (never build them by concatenation).
function offlineIcons() {
  const VIRTUAL_ID = 'virtual:dannify-icons'
  const RESOLVED_ID = '\0' + VIRTUAL_ID

  function collectNames(dir, found) {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry)
      if (statSync(full).isDirectory()) {
        collectNames(full, found)
      } else if (['.vue', '.js'].includes(extname(entry))) {
        const text = readFileSync(full, 'utf8')
        for (const m of text.matchAll(/['"`]ph:([a-z0-9-]+)['"`]/g)) {
          found.add(m[1])
        }
      }
    }
    return found
  }

  return {
    name: 'dannify-offline-icons',
    resolveId(id) {
      if (id === VIRTUAL_ID) return RESOLVED_ID
    },
    load(id) {
      if (id !== RESOLVED_ID) return
      const all = JSON.parse(
        readFileSync(require.resolve('@iconify-json/ph/icons.json'), 'utf8')
      )
      const icons = {}
      const aliases = {}
      for (const name of collectNames(SRC_DIR, new Set())) {
        if (all.icons[name]) {
          icons[name] = all.icons[name]
        } else if (all.aliases && all.aliases[name]) {
          aliases[name] = all.aliases[name]
          const parent = all.aliases[name].parent
          if (all.icons[parent]) icons[parent] = all.icons[parent]
        } else {
          this.warn(`Unknown Phosphor icon "ph:${name}"`)
        }
      }
      const collection = {
        prefix: 'ph',
        width: all.width,
        height: all.height,
        icons,
        aliases,
      }
      return `export default ${JSON.stringify(collection)}`
    },
    handleHotUpdate({ server }) {
      // Re-scan on any source edit so newly used icons appear in dev.
      const mod = server.moduleGraph.getModuleById(RESOLVED_ID)
      if (mod) server.moduleGraph.invalidateModule(mod)
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue(), offlineIcons()],
  resolve: {
    alias: [
      // Force the offline Iconify build everywhere: no network requests.
      { find: /^@iconify\/vue$/, replacement: '@iconify/vue/offline' },
    ],
  },
  define: {
    'process.env': {},
  },
  build: {
    // Shipping builds carry nothing that helps someone read the app back:
    // no source maps, no comments, no leftover console plumbing, and names
    // mangled by esbuild. This raises the bar; it cannot make a client-side
    // app unreadable, since the code has to run on the user's machine.
    sourcemap: false,
    minify: 'esbuild',
    reportCompressedSize: false,
    cssCodeSplit: false,
    chunkSizeWarningLimit: 1200,
  },
  esbuild: {
    drop: ['console', 'debugger'],
    legalComments: 'none',
  },
  server: {
    // `npm run dev` talks to a locally running backend (python main.py).
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', ws: true },
      '/downloads': 'http://127.0.0.1:8000',
      '/cover': 'http://127.0.0.1:8000',
      '/list': 'http://127.0.0.1:8000',
      '/delete': 'http://127.0.0.1:8000',
    },
  },
})
