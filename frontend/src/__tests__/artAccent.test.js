import { describe, expect, it, vi } from 'vitest'

// The colour maths only; the module's player and theme imports are stubbed.
vi.mock('/src/model/player', () => ({ usePlayer: () => ({}) }))
vi.mock('/src/model/theme', () => ({ useTheme: () => ({}) }))
globalThis.localStorage = { getItem: () => null, setItem: () => {} }

const { vividColour, fitAccent, contrast } = await import('/src/model/artAccent.js')

const px = (rgb, n) => Array.from({ length: n }, () => rgb)

describe('matching the artwork', () => {
  it('picks the vivid colour, not the average of the cover', () => {
    // Mostly near-black with a red subject: the average would be a dark brown.
    const pixels = [...px([10, 10, 12], 600), ...px([220, 30, 40], 180)]
    const [r, g, b] = vividColour(pixels)
    expect(r).toBeGreaterThan(180)
    expect(g).toBeLessThan(80)
    expect(b).toBeLessThan(80)
  })

  it('leaves a cover with no real colour alone', () => {
    expect(vividColour(px([128, 128, 128], 784))).toBe(null)
    expect(vividColour([...px([20, 20, 20], 780), ...px([200, 40, 40], 4)])).toBe(null)
  })

  it('keeps the accent readable on dark and light palettes', () => {
    const darkPanel = [18, 18, 21]
    const lightPanel = [255, 255, 255]
    for (const colour of [[20, 20, 140], [120, 10, 10], [240, 240, 60], [30, 160, 90]]) {
      const onDark = fitAccent(colour, darkPanel, true)
      expect(contrast(onDark.accent, darkPanel)).toBeGreaterThanOrEqual(4.5)
      expect(contrast(onDark.fg, onDark.accent)).toBeGreaterThanOrEqual(4.5)
      const onLight = fitAccent(colour, lightPanel, false)
      expect(contrast(onLight.accent, lightPanel)).toBeGreaterThanOrEqual(4.5)
      expect(contrast(onLight.fg, onLight.accent)).toBeGreaterThanOrEqual(4.5)
    }
  })
})
