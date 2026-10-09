import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { createLineEditor } from '../model/lyrics/lineEditor'
import { useSyncSession } from '../model/lyrics/useSyncSession'

// Timing against a stand-in player: a playhead that is set by hand, and
// calls recorded instead of sound. The clock the session uses to hold off
// following the song after a user action is set by hand too.

function fakePlayer() {
  const playbackRate = ref(1)
  return {
    currentTime: ref(0),
    duration: ref(200),
    isPlaying: ref(false),
    playbackRate,
    seek: vi.fn(),
    play: vi.fn(),
    toggle: vi.fn(),
    clipLoop: vi.fn(),
    clipUnloop: vi.fn(),
    setPlaybackRate: vi.fn((r) => (playbackRate.value = r)),
  }
}

let clock = 10_000
beforeEach(() => {
  clock = 10_000
  vi.spyOn(performance, 'now').mockImplementation(() => clock)
})
afterEach(() => {
  vi.restoreAllMocks()
})

function setup(lines = [['one'], ['two'], ['three']]) {
  const player = fakePlayer()
  const editor = createLineEditor()
  editor.load(lines.map(([text, time = null]) => ({ text, time })))
  const enabled = ref(true)
  const release = vi.fn()
  const session = useSyncSession({ player, editor, enabled, release })
  return { player, editor, enabled, release, session }
}

function keydown(code, { tag = 'SECTION', role = null, ...mods } = {}) {
  return {
    code,
    key: code,
    ...mods,
    target: { tagName: tag, getAttribute: () => role },
    preventDefault: vi.fn(),
  }
}

describe('tapping', () => {
  it('gives the line the playhead time and moves on', () => {
    const { player, editor, session } = setup()
    player.currentTime.value = 12.34567
    const before = session.reveal.value
    session.stamp()
    expect(editor.lines.value[0].time).toBe(12.346)
    expect(editor.active.value).toBe(1)
    expect(session.reveal.value).toBe(before + 1)
  })

  it('taps any line from its row', () => {
    const { player, editor, session } = setup()
    player.currentTime.value = 4
    session.stamp(2)
    expect(editor.lines.value[2].time).toBe(4)
  })
})

describe('following the song', () => {
  const timed = [['one', 10], ['two', 15], ['three'], ['four']]

  it('puts the cursor on the line about to be sung while it plays', async () => {
    const { player, editor } = setup(timed)
    editor.setActive(0)
    player.isPlaying.value = true
    player.currentTime.value = 15.1
    await nextTick()
    expect(editor.active.value).toBe(2)
  })

  it('stays still while paused', async () => {
    const { player, editor } = setup(timed)
    editor.setActive(0)
    player.currentTime.value = 15.1
    await nextTick()
    expect(editor.active.value).toBe(0)
  })

  it('leaves the cursor where the user just put it, for a moment', async () => {
    const { player, editor, session } = setup(timed)
    player.isPlaying.value = true
    session.moveTo(0)
    clock += 500
    player.currentTime.value = 15.1
    await nextTick()
    expect(editor.active.value).toBe(0)
    clock += 500
    player.currentTime.value = 15.2
    await nextTick()
    expect(editor.active.value).toBe(2)
  })

  it('does not follow while a line is looped, or typed in, or off the step', async () => {
    const { player, editor, session, enabled } = setup(timed)
    player.isPlaying.value = true
    session.toggleLoop(0)
    clock += 5000
    player.currentTime.value = 15.1
    await nextTick()
    expect(editor.active.value).toBe(0)

    session.stopLoop()
    editor.startEdit(1)
    player.currentTime.value = 15.2
    await nextTick()
    expect(editor.active.value).toBe(1)

    editor.stopEdit()
    enabled.value = false
    player.currentTime.value = 15.3
    await nextTick()
    expect(editor.active.value).toBe(1)
  })
})

describe('looping a line', () => {
  it('loops round the line and puts the cursor on it', () => {
    const { player, editor, session } = setup([['one', 10], ['two', 20]])
    session.toggleLoop(1)
    expect(player.clipLoop).toHaveBeenCalledWith(18.5, 22)
    expect(editor.active.value).toBe(1)
    expect(session.loopIndex.value).toBe(1)
    session.toggleLoop(1)
    expect(player.clipUnloop).toHaveBeenCalled()
    expect(session.loopIndex.value).toBe(-1)
  })

  it('follows the line when lines above it come and go', () => {
    const { editor, session } = setup([['one', 10], ['two', 20]])
    session.toggleLoop(1)
    editor.insertAt(0)
    expect(session.loopIndex.value).toBe(2)
  })

  it('ends when the line is deleted, or the step is left', async () => {
    const { player, enabled, session } = setup([['one', 10], ['two', 20]])
    session.toggleLoop(1)
    session.remove(1)
    await nextTick()
    expect(player.clipUnloop).toHaveBeenCalledTimes(1)
    expect(session.loopIndex.value).toBe(-1)

    session.toggleLoop(0)
    enabled.value = false
    await nextTick()
    expect(player.clipUnloop).toHaveBeenCalledTimes(2)
  })

  it('stops when all the timing is cleared', () => {
    const { player, editor, session } = setup([['one', 10]])
    session.toggleLoop(0)
    session.clearAll()
    expect(editor.timed.value).toBe(0)
    expect(player.clipUnloop).toHaveBeenCalled()
  })
})

describe('playing', () => {
  it('plays from a timed line, and only a timed one', () => {
    const { player, session } = setup([['one', 10], ['two']])
    session.playFrom(0)
    expect(player.seek).toHaveBeenCalledWith(10)
    expect(player.play).toHaveBeenCalledTimes(1)
    session.playFrom(1)
    expect(player.seek).toHaveBeenCalledTimes(1)
  })

  it('starts again from the top, on the first line', () => {
    const { player, editor, session } = setup()
    editor.setActive(2)
    session.playFromStart()
    expect(player.seek).toHaveBeenCalledWith(0)
    expect(editor.active.value).toBe(0)
  })

  it('never seeks before the start, and steps the speed', () => {
    const { player, session } = setup()
    player.currentTime.value = 1
    session.seekBy(-10)
    expect(player.seek).toHaveBeenCalledWith(0)
    session.stepRate(-0.25)
    expect(player.playbackRate.value).toBe(0.75)
  })
})

describe('the keyboard', () => {
  it('runs the command for a key and keeps the key from doing anything else', () => {
    const { player, editor, session } = setup()
    player.currentTime.value = 3
    const e = keydown('Space')
    expect(session.handleKey(e)).toBe(true)
    expect(e.preventDefault).toHaveBeenCalled()
    expect(editor.lines.value[0].time).toBe(3)
  })

  it('walks, nudges, edits, inserts, deletes and undoes', () => {
    const { editor, session } = setup([['one', 10], ['two'], ['three']])
    session.handleKey(keydown('KeyK'))
    expect(editor.active.value).toBe(0)
    session.handleKey(keydown('ArrowRight'))
    expect(editor.lines.value[0].time).toBe(10.1)
    session.handleKey(keydown('KeyE'))
    expect(editor.editing.value).toBe(0)
    editor.stopEdit()
    session.handleKey(keydown('Enter'))
    expect(editor.lines.value).toHaveLength(4)
    expect(editor.editing.value).toBe(1)
    editor.stopEdit()
    session.handleKey(keydown('Delete', { shiftKey: true }))
    expect(editor.lines.value).toHaveLength(3)
    session.handleKey(keydown('KeyZ', { ctrlKey: true }))
    expect(editor.lines.value).toHaveLength(4)
    session.handleKey(keydown('End'))
    expect(editor.active.value).toBe(3)
  })

  it('plays, pauses and changes speed', () => {
    const { player, session } = setup()
    session.handleKey(keydown('KeyP'))
    expect(player.toggle).toHaveBeenCalled()
    session.handleKey(keydown('Period'))
    expect(player.playbackRate.value).toBe(1.25)
  })

  it('lets Enter press a focused button, and leaves keys it does not use', () => {
    const { editor, session } = setup()
    const e = keydown('Enter', { tag: 'BUTTON' })
    expect(session.handleKey(e)).toBe(false)
    expect(e.preventDefault).not.toHaveBeenCalled()
    expect(session.handleKey(keydown('KeyQ'))).toBe(false)
    expect(editor.lines.value).toHaveLength(3)
  })

  it('does nothing while the timing step is not showing', () => {
    const { editor, session, enabled } = setup()
    enabled.value = false
    expect(session.handleKey(keydown('Space'))).toBe(false)
    expect(editor.timed.value).toBe(0)
  })
})
