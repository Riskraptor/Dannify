// Finding a command by typing some of it.
//
// What is typed is matched a word at a time, and every word has to be found:
// "dark th" finds "Theme: dark". Accents and case are ignored, so "repetition"
// finds "Répétition". Where a word is found decides how good the match is:
// at the start of the name, at the start of a word in it, anywhere in it, or
// only among the words a command is also known by.

export function fold(text) {
  return String(text || '')
    .normalize('NFKD')
    .replace(/\p{M}+/gu, '')
    .toLowerCase()
}

function wordScore(title, extra, word) {
  const at = title.indexOf(word)
  if (at === 0) return 100
  if (at > 0) return /[\s:·\-/(]/.test(title[at - 1]) ? 70 : 40
  return extra.includes(word) ? 20 : 0
}

/**
 * The commands that match `query`, best first. With nothing typed, all of
 * them, in the order they were given.
 */
export function rankCommands(commands, query) {
  const words = fold(query).split(/\s+/).filter(Boolean)
  if (!words.length) return commands.slice()
  const scored = []
  commands.forEach((command, order) => {
    const title = fold(command.title)
    const extra = fold(`${command.keywords || ''} ${command.group || ''}`)
    let total = 0
    for (const word of words) {
      const score = wordScore(title, extra, word)
      if (!score) return
      total += score
    }
    // A short name that matches is a better answer than a long one that does.
    scored.push({ command, order, score: total - title.length / 100 })
  })
  scored.sort((a, b) => b.score - a.score || a.order - b.order)
  return scored.map((s) => s.command)
}
