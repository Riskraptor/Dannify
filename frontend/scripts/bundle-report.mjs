// What the main script is made of, heaviest first.
//
//   node scripts/bundle-report.mjs [count]
//
// Builds as usual into a throwaway folder and lists the modules in the entry
// chunk by the size they take in it, so a size budget that is broken can be
// mended where it matters (scripts/size-budget.mjs).

import { build } from 'vite'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const count = Number(process.argv[2] || 30)
const sizes = []
await build({
  logLevel: 'silent',
  build: { outDir: join(tmpdir(), 'dannify-bundle-report'), emptyOutDir: true },
  plugins: [
    {
      name: 'bundle-report',
      generateBundle(_options, bundle) {
        for (const chunk of Object.values(bundle)) {
          if (chunk.type !== 'chunk' || !chunk.isEntry) continue
          for (const [id, mod] of Object.entries(chunk.modules)) {
            sizes.push([mod.renderedLength, id.replace(/\\/g, '/').replace(/^.*\/(node_modules|src)\//, '$1/')])
          }
        }
      },
    },
  ],
})
sizes.sort((a, b) => b[0] - a[0])
const total = sizes.reduce((n, [s]) => n + s, 0)
console.log(`entry chunk: ${(total / 1024).toFixed(1)} KB before compression, ${sizes.length} modules`)
for (const [size, id] of sizes.slice(0, count)) console.log(`${(size / 1024).toFixed(1).padStart(7)} KB  ${id}`)
