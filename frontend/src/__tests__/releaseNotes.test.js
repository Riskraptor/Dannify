import { describe, expect, it } from 'vitest'
import { hasNotes, plainText, readNotes, splitItem } from '../model/releaseNotes'

// The notes 4.9.1 went out with, as the app showed them: markup and all.
const NOTES_491 = `Everything in 4.9.0, now on Windows, Linux and macOS, and Dannify's new home: [github.com/Riskraptor/Dannify](https://github.com/Riskraptor/Dannify).

## Downloads

- Windows 10 and 11: \`Dannify-Setup-4.9.1.exe\`. Run it; it installs over the Dannify you have.
- Ubuntu, Debian, Linux Mint and the like (64-bit): \`linux-dannify_4.9.1_amd64.deb\`, then \`sudo apt install ./linux-dannify_4.9.1_amd64.deb\`.

Copies on 4.9.0, 4.8.1, and 4.6.2 or older update by themselves. On 4.7.0 or 4.8.0, install this version by hand once.

Each file has a \`.dsig\` beside it: the release signature every installed copy checks before it installs anything.

## What's new

- **Linux and macOS get everything in 4.9.0:** Albums in your library, listening history and Your stats, ListenBrainz, the command palette. See [4.9.0](https://github.com/Riskraptor/Dannify/releases/tag/v4.9.0) for the full list.
- **Dannify has moved to github.com/Riskraptor/Dannify.** Updates, the download page and every link in the app point there now.

The full list of changes is in [CHANGELOG.md](https://github.com/Riskraptor/Dannify/blob/main/CHANGELOG.md).
`

const PLAIN = `Albums, your listening stats and ListenBrainz.

## What's new
- Albums in your library: every album you have saved songs from, in album order.
- Your stats: time listened, streaks and your top songs.

## Fixed
- Saving a single song kept its album.
- Liked Songs says when it could not load.

## Under the hood
- starlette 1.3.1, urllib3 2.8.0.

## Downloads
- Windows: Dannify-Setup-4.9.2.exe
`

function everything(read) {
  return [read.summary, ...read.highlights.flatMap((h) => [h.title, h.text]), ...read.fixes.map((f) => f.text)].join('\n')
}

describe('plainText', () => {
  it('takes the markup out and keeps what it says', () => {
    expect(plainText('See [4.9.0](https://x.y/z) for **all** of it, `now`.')).toBe('See 4.9.0 for all of it, now.')
    expect(plainText('Moved to [CHANGELOG.md](https://a.b/c(d)).')).toBe('Moved to CHANGELOG.md.')
    expect(plainText('<b>Bold</b> and _quiet_ words')).toBe('Bold and quiet words')
    expect(plainText('Read more at https://example.com/page now')).toBe('Read more at now')
  })
})

describe('splitItem', () => {
  it('takes a bold lead-in as the title', () => {
    expect(splitItem('**Albums.** Every album you saved.')).toEqual({ title: 'Albums', text: 'Every album you saved.' })
    expect(splitItem('**Linux and macOS:** everything in 4.9.0')).toEqual({
      title: 'Linux and macOS',
      text: 'everything in 4.9.0',
    })
  })

  it('takes a short phrase before a colon as the title', () => {
    expect(splitItem('Your stats: time listened and streaks.')).toEqual({
      title: 'Your stats',
      text: 'Time listened and streaks.',
    })
  })

  it('leaves a sentence with no lead-in whole', () => {
    expect(splitItem('Saving a single song kept its album. It does now: always.')).toEqual({
      title: '',
      text: 'Saving a single song kept its album. It does now: always.',
    })
  })

  it('cuts a long one at a word', () => {
    const { text } = splitItem('word '.repeat(80))
    expect(text.length).toBeLessThanOrEqual(221)
    expect(text.endsWith('…')).toBe(true)
  })
})

describe('readNotes', () => {
  it('shows what is new and nothing about the files', () => {
    const read = readNotes(NOTES_491)
    expect(read.summary).toBe("Everything in 4.9.0, now on Windows, Linux and macOS, and Dannify's new home: github.com/Riskraptor/Dannify.")
    expect(read.highlights.map((h) => h.title)).toEqual([
      'Linux and macOS get everything in 4.9.0',
      'Dannify has moved to github.com/Riskraptor/Dannify',
    ])
    const shown = everything(read)
    for (const bad of ['`', '**', '](', 'http', '.exe', '.deb', '.dsig', 'sudo', 'by hand', 'signature']) {
      expect(shown).not.toContain(bad)
    }
    expect(hasNotes(read)).toBe(true)
  })

  it('splits highlights from fixes and leaves the rest out', () => {
    const read = readNotes(PLAIN)
    expect(read.summary).toBe('Albums, your listening stats and ListenBrainz.')
    expect(read.highlights).toEqual([
      { title: 'Albums in your library', text: 'Every album you have saved songs from, in album order.' },
      { title: 'Your stats', text: 'Time listened, streaks and your top songs.' },
    ])
    expect(read.fixes.map((f) => f.text)).toEqual([
      'Saving a single song kept its album.',
      'Liked Songs says when it could not load.',
    ])
    expect(everything(read)).not.toMatch(/starlette|Dannify-Setup/)
    expect(read.more).toBe(false)
  })

  it('joins a bullet wrapped onto the next line', () => {
    const read = readNotes('## New\n- **Albums.** Every album\n  you have saved.\n')
    expect(read.highlights).toEqual([{ title: 'Albums', text: 'Every album you have saved.' }])
  })

  it('keeps it short and says so', () => {
    const many = '## New\n' + Array.from({ length: 12 }, (_, i) => `- Thing ${i}: does ${i}.`).join('\n')
    const read = readNotes(many)
    expect(read.highlights).toHaveLength(8)
    expect(read.more).toBe(true)
  })

  it('makes do with notes that are only a line or two', () => {
    expect(readNotes('Fixes and improvements.')).toEqual({
      summary: 'Fixes and improvements.',
      highlights: [],
      fixes: [],
      more: false,
    })
    expect(hasNotes(readNotes(''))).toBe(false)
    expect(hasNotes(readNotes('## Downloads\n- Dannify-Setup-1.0.0.exe'))).toBe(false)
  })
})
