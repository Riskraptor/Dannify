import { describe, expect, it } from 'vitest'
import { chooseFromLibrary } from '/src/model/player/libraryRadio'

const library = [
  { file: 'a1.mp3', title: 'One', artist: 'Adele', album: '21' },
  { file: 'a2.mp3', title: 'Two', artist: 'Adele', album: '25', video_id: 'vid-two' },
  { file: 'b1.mp3', title: 'Three', artist: 'Bastille', album: '21' },
  { file: 'c1.mp3', title: 'Four', artist: 'Coldplay', album: 'Parachutes' },
  { file: 'c2.mp3', title: 'Five', artist: 'Coldplay', album: 'X&Y', problem: 'damaged' },
  { file: 'd1.mp3', title: 'Six', artist: 'Dua Lipa', artists: ['Dua Lipa', 'Adèle'], album: 'Future' },
]

const fixed = () => 0

describe('chooseFromLibrary', () => {
  it('puts the same artist first, then the album, then the rest', () => {
    const current = { file: 'a1.mp3', artist: 'Adele', album: '21' }
    const files = chooseFromLibrary(current, library, [current], { random: fixed }).map((t) => t.file)
    expect(files.slice(0, 2).sort()).toEqual(['a2.mp3', 'd1.mp3'])
    expect(files[2]).toBe('b1.mp3')
    expect(files.slice(3)).toEqual(['c1.mp3'])
  })

  it('never offers a song already queued, or one that will not play', () => {
    const current = { file: 'c1.mp3', artist: 'Coldplay' }
    const queued = [current, { type: 'remote', video_id: 'vid-two' }]
    const files = chooseFromLibrary(current, library, queued, { random: fixed }).map((t) => t.file)
    expect(files).not.toContain('c1.mp3')
    expect(files).not.toContain('a2.mp3')
    expect(files).not.toContain('c2.mp3')
    expect(files).toHaveLength(3)
  })

  it('keeps to the limit and copes with an empty library', () => {
    const current = { artist: 'Nobody' }
    expect(chooseFromLibrary(current, library, [], { limit: 2 })).toHaveLength(2)
    expect(chooseFromLibrary(current, [], [])).toEqual([])
    expect(chooseFromLibrary(null, null)).toEqual([])
  })
})
