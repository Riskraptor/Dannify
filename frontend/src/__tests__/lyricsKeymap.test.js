import { describe, expect, it } from 'vitest'
import { syncCommand } from '../model/lyrics/keymap'

const key = (code, mods = {}) => ({ code, key: code, ...mods })
const on = (tag, role) => ({ tag, role })

describe('syncCommand', () => {
  it('taps with Space, and stays on the line with Shift', () => {
    expect(syncCommand(key('Space'))).toBe('stamp')
    expect(syncCommand(key('Space', { shiftKey: true }))).toBe('stamp-stay')
  })

  it('still taps with Space when a toolbar button has the focus', () => {
    expect(syncCommand(key('Space'), on('BUTTON'))).toBe('stamp')
  })

  it('moves the cursor with the arrows, J and K, Home and End', () => {
    expect(syncCommand(key('ArrowDown'))).toBe('next')
    expect(syncCommand(key('KeyJ'))).toBe('next')
    expect(syncCommand(key('ArrowUp'))).toBe('prev')
    expect(syncCommand(key('KeyK'))).toBe('prev')
    expect(syncCommand(key('Home'))).toBe('first')
    expect(syncCommand(key('End'))).toBe('last')
  })

  it('nudges with left and right', () => {
    expect(syncCommand(key('ArrowLeft'))).toBe('nudge-back')
    expect(syncCommand(key('ArrowRight'))).toBe('nudge-forward')
  })

  it('has a letter for each line action', () => {
    expect(syncCommand(key('KeyL'))).toBe('loop')
    expect(syncCommand(key('KeyP'))).toBe('play')
    expect(syncCommand(key('KeyE'))).toBe('edit')
    expect(syncCommand(key('F2'))).toBe('edit')
    expect(syncCommand(key('KeyZ'))).toBe('clear-last')
    expect(syncCommand(key('Comma'))).toBe('slower')
    expect(syncCommand(key('Period'))).toBe('faster')
  })

  it('adds a line with Enter, but lets Enter press a focused button', () => {
    expect(syncCommand(key('Enter'))).toBe('insert')
    expect(syncCommand(key('NumpadEnter'), on('LI'))).toBe('insert')
    expect(syncCommand(key('Enter'), on('BUTTON'))).toBeNull()
    expect(syncCommand(key('Enter'), on('a'))).toBeNull()
  })

  it('deletes a line only with Shift', () => {
    expect(syncCommand(key('Backspace', { shiftKey: true }))).toBe('delete')
    expect(syncCommand(key('Delete', { shiftKey: true }))).toBe('delete')
    expect(syncCommand(key('Backspace'))).toBeNull()
  })

  it('keeps its own undo history on Ctrl+Z and Ctrl+Y', () => {
    expect(syncCommand(key('KeyZ', { ctrlKey: true }))).toBe('undo')
    expect(syncCommand(key('KeyZ', { ctrlKey: true, shiftKey: true }))).toBe('redo')
    expect(syncCommand(key('KeyY', { metaKey: true }))).toBe('redo')
  })

  it('lets every other modifier shortcut through', () => {
    expect(syncCommand(key('KeyC', { ctrlKey: true }))).toBeNull()
    expect(syncCommand(key('KeyL', { ctrlKey: true }))).toBeNull()
    expect(syncCommand(key('Space', { altKey: true }))).toBeNull()
  })

  it('never takes keys from a text field', () => {
    expect(syncCommand(key('Space'), on('TEXTAREA'))).toBeNull()
    expect(syncCommand(key('KeyZ', { ctrlKey: true }), on('input'))).toBeNull()
  })

  it('leaves a focused slider its own arrow keys', () => {
    expect(syncCommand(key('ArrowLeft'), on('DIV', 'slider'))).toBeNull()
    expect(syncCommand(key('Home'), on('DIV', 'slider'))).toBeNull()
    expect(syncCommand(key('Space'), on('DIV', 'slider'))).toBe('stamp')
  })

  it('ignores keys it has no use for', () => {
    expect(syncCommand(key('KeyQ'))).toBeNull()
    expect(syncCommand(key('Tab'))).toBeNull()
  })
})
