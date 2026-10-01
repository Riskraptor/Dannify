"""The window's live channel survives its own reconnects."""

from __future__ import annotations

import asyncio

from dannify.api import ConnectionManager


class _Socket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def accept(self):
        pass

    async def send_text(self, text):
        if self.closed:
            raise RuntimeError('closed')
        self.sent.append(text)


def test_an_old_socket_closing_does_not_drop_the_new_one():
    async def run():
        manager = ConnectionManager()
        old, new = _Socket(), _Socket()
        await manager.connect('window', old)
        # The window noticed the drop first and is already back.
        await manager.connect('window', new)
        # Now the server notices the old one going away.
        old.closed = True
        manager.disconnect('window', old)
        await manager.broadcast({'type': 'library_changed'})
        return manager.connected, new.sent

    connected, delivered = asyncio.run(run())
    assert connected
    assert delivered == ['{"type": "library_changed"}']


def test_a_dead_socket_found_by_a_broadcast_is_dropped():
    async def run():
        manager = ConnectionManager()
        dead = _Socket()
        await manager.connect('window', dead)
        dead.closed = True
        await manager.broadcast({'x': 1})
        return manager.connected

    assert asyncio.run(run()) is False


def test_a_window_that_has_only_just_connected_is_not_settled(monkeypatch):
    import asyncio

    from dannify import api

    clock = [100.0]
    monkeypatch.setattr(api.time, 'monotonic', lambda: clock[0])

    class WS:
        async def accept(self):
            pass

    cm = api.ConnectionManager()
    assert not cm.settled()  # nobody listening
    asyncio.run(cm.connect('a', WS()))
    assert cm.connected and not cm.settled()  # the page is still coming up
    clock[0] += 2
    assert cm.settled()
    asyncio.run(cm.connect('b', WS()))
    assert cm.settled()  # a second window does not restart the wait
