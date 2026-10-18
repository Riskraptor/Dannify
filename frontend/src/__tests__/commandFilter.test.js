import { describe, expect, it } from 'vitest'
import { fold, rankCommands } from '../model/commandFilter.js'

const commands = [
  { id: 'home', group: 'Go to', title: 'Home' },
  { id: 'history', group: 'Go to', title: 'History' },
  { id: 'stats', group: 'Go to', title: 'Your stats', keywords: 'Your listening' },
  { id: 'shuffle', group: 'Playback', title: 'Turn shuffle on', keywords: 'Shuffle' },
  { id: 'dark', group: 'Appearance', title: 'Theme: dark', keywords: 'Theme' },
  { id: 'light', group: 'Appearance', title: 'Theme: light', keywords: 'Theme' },
  { id: 'repeat', group: 'Lecture', title: 'Changer la répétition' },
]
const ids = (query) => rankCommands(commands, query).map((c) => c.id)

describe('rankCommands()', () => {
  it('gives everything back, in order, when nothing is typed', () => {
    expect(ids('')).toEqual(commands.map((c) => c.id))
    expect(ids('   ')).toEqual(commands.map((c) => c.id))
  })

  it('finds a command by the start of its name', () => {
    expect(ids('hi')).toEqual(['history'])
    expect(ids('ho')[0]).toBe('home')
  })

  it('needs every word, in any order', () => {
    expect(ids('dark th')).toEqual(['dark'])
    expect(ids('th dark')).toEqual(['dark'])
    expect(ids('theme')).toEqual(['dark', 'light'])
    expect(ids('theme purple')).toEqual([])
  })

  it('puts the start of the name before the start of a word, before the middle', () => {
    const list = [
      { id: 'middle', title: 'Unshuffled' },
      { id: 'word', title: 'Turn shuffle on' },
      { id: 'start', title: 'Shuffle' },
    ]
    expect(rankCommands(list, 'shuf').map((c) => c.id)).toEqual(['start', 'word', 'middle'])
  })

  it('finds a command by what it is also known as, after those named for it', () => {
    expect(ids('listening')).toEqual(['stats'])
    // "Go to" is the group of three of them; none is named that.
    expect(ids('go')).toEqual(['home', 'history', 'stats'])
  })

  it('pays no attention to accents or capitals', () => {
    expect(fold('Répétition')).toBe('repetition')
    expect(ids('REPETITION')).toEqual(['repeat'])
  })

  it('leaves the list it was given alone', () => {
    const before = commands.map((c) => c.id)
    rankCommands(commands, 'theme')
    expect(commands.map((c) => c.id)).toEqual(before)
  })
})
