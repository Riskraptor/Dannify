// Release notes as people read them inside the app: what is new, in a few
// lines each, and nothing about how the release is put together.
//
// The notes are written once, for the releases page, where the downloads,
// the commands to install them and the signature files belong. In the app
// they are noise: whoever is reading them is already being offered the
// update. So the notes are read here, not shown: sections about downloading
// and installing are left out, as is any line naming a release file or a
// command, and the markup is taken out rather than shown as asterisks,
// backticks and bracketed addresses.
//
// Nothing here produces markup. The notes arrive over the network, and every
// piece of them ends up as plain text in the page.

// Sections nobody inside the app needs.
const HIDDEN_SECTION = /download|install|signature|checksum|verif|under the hood|technical|developer|build/i
// Lines that are about the release files rather than the app.
const NOISE = /\.(exe|deb|dmg|zip|dsig|json|msi|appimage)\b|\bsudo\b|apt install|\.dsig|signature|install(ed)? (this version )?by hand/i
const FIXES = /\bfix/i
// "The full list is in CHANGELOG.md": the view has its own link for that.
const POINTER = /^(the )?full (list|notes|changelog)|changelog\.md|releases? page/i

const MAX_HIGHLIGHTS = 8
const MAX_FIXES = 6
const MAX_TEXT = 220

/** Markdown taken out of one line, leaving what it says. */
export function plainText(text) {
  return String(text || '')
    .replace(/<[^>]*>/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\((?:[^()]|\([^)]*\))*\)/g, '$1')
    .replace(/`+([^`]*)`+/g, '$1')
    .replace(/(\*\*|__)(.+?)\1/g, '$2')
    .replace(/(^|[\s(])[*_]([^\s*_][^*_]*?)[*_](?=[\s).,:;!?]|$)/g, '$1$2')
    .replace(/\*\*|__/g, '')
    .replace(/https?:\/\/[^\s)]+/g, '')
    .replace(/\\([\\`*_{}[\]()#+\-.!])/g, '$1')
    .replace(/\(\s*\)/g, '')
    .replace(/\s+/g, ' ')
    .replace(/\s+([.,:;!?])/g, '$1')
    .trim()
}

function shorten(text) {
  if (text.length <= MAX_TEXT) return text
  const cut = text.slice(0, MAX_TEXT)
  return cut.slice(0, Math.max(cut.lastIndexOf(' '), MAX_TEXT - 30)).replace(/[,;:\s]+$/, '') + '…'
}

/**
 * One item as a title and what it says: "**Albums.** Every album…" or
 * "Albums: every album…" both give the title "Albums". A line with no short
 * lead-in is all text.
 */
export function splitItem(raw) {
  const line = String(raw || '').trim()
  const bold = line.match(/^(\*\*|__)(.+?)\1\s*(.*)$/)
  if (bold) {
    const title = plainText(bold[2]).replace(/[.:!]+$/, '').trim()
    const text = plainText(bold[3]).replace(/^[-–—:]\s*/, '')
    if (title) return { title, text: shorten(text) }
  }
  const plain = plainText(line)
  const colon = plain.indexOf(': ')
  if (colon > 2 && colon <= 60 && !/[.!?]/.test(plain.slice(0, colon))) {
    const text = plain.slice(colon + 2)
    return { title: plain.slice(0, colon), text: shorten(text.charAt(0).toUpperCase() + text.slice(1)) }
  }
  return { title: '', text: shorten(plain) }
}

/**
 * `{ summary, highlights, fixes, more }` from a release's notes.
 *
 * *summary* is the first paragraph before any heading. *highlights* are the
 * items of every section that is not about fixes or about getting the files;
 * *fixes* those of the fix sections. *more* says some were left out to keep it
 * short (the releases page has the rest).
 */
export function readNotes(notes) {
  const lines = String(notes || '').replace(/\r\n?/g, '\n').split('\n')
  const intro = []
  const highlights = []
  const fixes = []
  let section = null // { hidden, fixes }
  let last = null // the item a wrapped line continues
  let introDone = false

  const take = (raw) => {
    if (NOISE.test(raw) || POINTER.test(plainText(raw))) return null
    const item = splitItem(raw)
    if (!item.text && !item.title) return null
    const list = section && section.fixes ? fixes : highlights
    list.push(item)
    return item
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    const heading = line.match(/^#{1,6}\s+(.+?)\s*#*$/)
    if (heading) {
      const title = plainText(heading[1])
      section = { hidden: HIDDEN_SECTION.test(title), fixes: FIXES.test(title) }
      last = null
      introDone = true
      continue
    }
    if (!line) {
      last = null
      if (intro.length) introDone = true
      continue
    }
    if (!section) {
      // Before any heading: the first paragraph says what the release is.
      if (!introDone && !NOISE.test(line)) intro.push(line)
      continue
    }
    if (section.hidden) continue
    const bullet = line.match(/^(?:[-*+]|\d+[.)])\s+(.+)$/)
    if (bullet) {
      last = take(bullet[1])
    } else if (last && !NOISE.test(line)) {
      // A bullet wrapped onto the next line.
      const more = plainText(line)
      last.text = shorten(`${last.text} ${more}`.trim())
    } else {
      last = take(line)
    }
  }

  const summary = shorten(plainText(intro.join(' ')))
  return {
    summary,
    highlights: highlights.slice(0, MAX_HIGHLIGHTS),
    fixes: fixes.slice(0, MAX_FIXES),
    more: highlights.length > MAX_HIGHLIGHTS || fixes.length > MAX_FIXES,
  }
}

/** Whether there is anything to show at all. */
export function hasNotes(read) {
  return !!(read && (read.summary || read.highlights.length || read.fixes.length))
}
