// Sorting by name, fast enough for a library of any size. A comparison with
// locale options (`a.localeCompare(b, undefined, { sensitivity })`) sets its
// rules up again on every call: 200,000 names took over 20 seconds. Each
// name is folded once instead (case and accents), and the folded names
// compared with the engine's own fast path.

const MARKS = /[̀-ͯ]/g

/** `name` as it sorts: no case, no accents ("Émile" next to "emile"). */
export function textKey(name) {
  return String(name ?? '')
    .normalize('NFD')
    .replace(MARKS, '')
    .toLowerCase()
}

/**
 * A sorted copy of `list`. Each `by` is a function of an item, or
 * `{ by, desc: true }`, compared in turn: text by its folded form, numbers
 * as numbers. Items that tie on all of them keep their order.
 */
export function sortedBy(list, ...specs) {
  const rules = rulesOf(specs)
  const keyed = list.map((item, i) => ({
    item,
    i,
    keys: rules.map((r) => {
      const v = r.by(item)
      return typeof v === 'number' ? v : textKey(v)
    }),
  }))
  keyed.sort((a, b) => {
    for (let k = 0; k < rules.length; k++) {
      const x = a.keys[k]
      const y = b.keys[k]
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
      if (c) return c * rules[k].sign
    }
    return a.i - b.i
  })
  return keyed.map((e) => e.item)
}

function rulesOf(specs) {
  return specs.map((s) => (typeof s === 'function' ? { by: s, sign: 1 } : { by: s.by, sign: s.desc ? -1 : 1 }))
}

function compare(rules, a, b) {
  for (const r of rules) {
    const x = r.by(a)
    const y = r.by(b)
    const c =
      typeof x === 'number' && typeof y === 'number' ? x - y : textKey(x).localeCompare(textKey(y))
    if (c) return c * r.sign
  }
  return 0
}

/**
 * `sorted` (already in this order) with a few more `items` put in their
 * places: a binary search each, rather than sorting a big list again for a
 * handful of additions.
 */
export function insertSorted(sorted, items, ...specs) {
  if (!items.length) return sorted
  const rules = rulesOf(specs)
  const out = []
  let from = 0
  for (const item of sortedBy(items, ...specs)) {
    let lo = from
    let hi = sorted.length
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (compare(rules, sorted[mid], item) <= 0) lo = mid + 1
      else hi = mid
    }
    for (let i = from; i < lo; i++) out.push(sorted[i])
    out.push(item)
    from = lo
  }
  for (let i = from; i < sorted.length; i++) out.push(sorted[i])
  return out
}
