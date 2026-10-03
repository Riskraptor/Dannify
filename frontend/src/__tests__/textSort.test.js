import { describe, it, expect } from 'vitest'
import { sortedBy, insertSorted, textKey } from '../model/textSort'

describe('textKey', () => {
  it('ignores case and accents', () => {
    expect(textKey('Émile')).toBe(textKey('emile'))
    expect(textKey('BEYONCÉ')).toBe('beyonce')
    expect(textKey(null)).toBe('')
  })
})

describe('sortedBy', () => {
  const names = (list) => list.map((a) => a.name)

  it('sorts names the way people read them, not by character code', () => {
    const list = ['Zed', 'éa', 'adele', 'Eb', 'Émile', 'beyoncé'].map((name) => ({ name }))
    expect(names(sortedBy(list, (a) => a.name))).toEqual(['adele', 'beyoncé', 'éa', 'Eb', 'Émile', 'Zed'])
  })

  it('leaves the list it was given alone', () => {
    const list = [{ name: 'b' }, { name: 'a' }]
    sortedBy(list, (a) => a.name)
    expect(names(list)).toEqual(['b', 'a'])
  })

  it('compares numbers as numbers, with later rules breaking ties', () => {
    const list = [
      { name: 'b', count: 2 },
      { name: 'c', count: 10 },
      { name: 'a', count: 2 },
    ]
    expect(names(sortedBy(list, { by: (a) => a.count, desc: true }, (a) => a.name))).toEqual(['c', 'a', 'b'])
  })

  it('keeps the order of items that tie on everything', () => {
    const list = [
      { name: 'x', n: 1 },
      { name: 'x', n: 2 },
      { name: 'x', n: 3 },
    ]
    expect(sortedBy(list, (a) => a.name).map((a) => a.n)).toEqual([1, 2, 3])
  })

  it('copes with a big library quickly', () => {
    const list = Array.from({ length: 50000 }, (_, i) => ({ name: `Artist ${(i * 7919) % 50000} é` }))
    const t = performance.now()
    const out = sortedBy(list, (a) => a.name)
    expect(performance.now() - t).toBeLessThan(2000)
    expect(out).toHaveLength(50000)
    expect(textKey(out[0].name) <= textKey(out[1].name)).toBe(true)
  })
})

describe('insertSorted', () => {
  const names = (list) => list.map((a) => a.name)

  it('puts each new item where a full sort would', () => {
    const sorted = sortedBy(['b', 'd', 'f', 'h'].map((name) => ({ name })), (a) => a.name)
    const extra = ['g', 'A', 'é', 'z'].map((name) => ({ name }))
    const merged = insertSorted(sorted, extra, (a) => a.name)
    expect(names(merged)).toEqual(names(sortedBy([...sorted, ...extra], (a) => a.name)))
  })

  it('follows several rules, numbers first', () => {
    const by = [{ by: (a) => a.count || 0, desc: true }, (a) => a.name]
    const sorted = sortedBy(
      [
        { name: 'b', count: 9 },
        { name: 'a', count: 3 },
        { name: 'c', count: 3 },
      ],
      ...by
    )
    const merged = insertSorted(sorted, [{ name: 'followed' }, { name: 'bb', count: 3 }], ...by)
    expect(names(merged)).toEqual(['b', 'a', 'bb', 'c', 'followed'])
  })

  it('gives back the list itself when there is nothing to add', () => {
    const sorted = [{ name: 'a' }]
    expect(insertSorted(sorted, [], (a) => a.name)).toBe(sorted)
  })
})
