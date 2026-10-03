"""How many songs download at once, and changing that while they wait."""

import asyncio

from dannify.api import DownloadSlots


def test_a_new_limit_reaches_songs_already_waiting():
    async def run():
        slots = DownloadSlots(1)
        running = []
        gate = asyncio.Event()

        async def song(i):
            async with slots:
                running.append(i)
                await gate.wait()

        tasks = [asyncio.create_task(song(i)) for i in range(4)]
        await asyncio.sleep(0.01)
        assert running == [0]  # one at a time
        slots.resize(3)  # the setting changed mid-batch
        await asyncio.sleep(0.01)
        assert sorted(running) == [0, 1, 2]
        gate.set()
        await asyncio.gather(*tasks)
        assert sorted(running) == [0, 1, 2, 3] and slots.busy == 0

    asyncio.run(run())


def test_lowering_the_limit_lets_the_running_ones_finish():
    async def run():
        slots = DownloadSlots(3)
        gate = asyncio.Event()
        started = []

        async def song(i):
            async with slots:
                started.append(i)
                await gate.wait()

        tasks = [asyncio.create_task(song(i)) for i in range(5)]
        await asyncio.sleep(0.01)
        assert len(started) == 3
        slots.resize(1)
        gate.set()
        await asyncio.gather(*tasks)
        assert len(started) == 5 and slots.busy == 0

    asyncio.run(run())


def test_a_song_removed_while_it_waits_gives_its_place_up():
    async def run():
        slots = DownloadSlots(1)
        gate = asyncio.Event()

        async def hold():
            async with slots:
                await gate.wait()

        first = asyncio.create_task(hold())
        await asyncio.sleep(0.01)
        waiting = asyncio.create_task(hold())
        await asyncio.sleep(0.01)
        waiting.cancel()
        await asyncio.sleep(0.01)
        assert not slots._waiters
        gate.set()
        await first

    asyncio.run(run())
