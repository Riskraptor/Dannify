"""The folder watcher tells the window when the folder moves away from what
the window last read."""

from __future__ import annotations

from pathlib import Path

from dannify import diskwatch


def _drive(monkeypatch, looks, served):
    """Run the loop over a script of (folder fingerprint, last read) pairs."""

    seq = iter(zip(looks, served))
    state = {}
    told = []

    def next_look(base):
        state['look'], state['served'] = next(seq)
        return state['look']

    monkeypatch.setattr(diskwatch.library_mod, 'signature', next_look)
    monkeypatch.setattr(diskwatch.library_mod, 'served_signature', lambda base: state['served'])
    monkeypatch.setattr(diskwatch.library_mod, 'invalidate_cache', lambda: None)

    ticks = {'n': 0}

    def wait(seconds):
        ticks['n'] += 1
        if ticks['n'] >= len(looks):
            diskwatch._stop.set()
        return diskwatch._stop.is_set()

    monkeypatch.setattr(diskwatch._stop, 'wait', wait)
    diskwatch._stop.clear()
    diskwatch._run(lambda: Path('.'), lambda: told.append(state['look']))
    diskwatch._stop.clear()
    return told


def test_a_change_between_looks_is_reported(monkeypatch):
    A, B = ('A',), ('A', 'B')
    assert _drive(monkeypatch, [A, B, B], [None, A, A]) == [B]


def test_a_song_added_and_removed_between_looks_is_still_reported(monkeypatch):
    # The window read the library with the new song in it (the download said
    # so itself); the file was deleted before the loop looked again.
    A, AS = ('A',), ('A', 'Suzanna')
    told = _drive(monkeypatch, [A, A, A, A], [None, AS, AS, AS])
    assert told == [A]  # once, not on every look


def test_nothing_changed_nothing_said(monkeypatch):
    A = ('A',)
    assert _drive(monkeypatch, [A, A, A], [None, A, A]) == []
