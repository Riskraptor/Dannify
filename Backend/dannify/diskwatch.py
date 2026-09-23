"""Notice when the music folder changes behind the app's back.

The library used to refresh only when Dannify itself added or removed a file.
Delete an album in Explorer and the app went on listing it, offering to play
tracks that were not there any more. Nothing was wrong with the scan: nothing
ever asked it to run again.

This polls the folder fingerprint (file count plus newest mtime, the same one
the library cache keys on) and broadcasts when it moves. Polling rather than a
filesystem watcher on purpose: a watcher means another dependency and a native
handle per directory, and it has to be debounced anyway because a single copy
fires a dozen events. A cheap check a few seconds apart is indistinguishable
to the user and cannot get stuck holding a directory open.

The interval backs off while nothing is happening, so an idle app is not
walking the disk every few seconds forever.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from . import library as library_mod

# How often to look, at the fastest, and how far the interval is allowed to
# stretch once the folder has been quiet for a while.
_MIN_INTERVAL = 4.0
_MAX_INTERVAL = 30.0
# Quiet checks before the interval grows a step.
_BACKOFF_AFTER = 3

_thread: Optional[threading.Thread] = None
_stop = threading.Event()


def _run(base_of: Callable[[], Optional[Path]], notify: Callable[[], None]) -> None:
    last: Optional[tuple[int, float]] = None
    interval = _MIN_INTERVAL
    quiet = 0
    while not _stop.is_set():
        base = None
        try:
            base = base_of()
        except Exception:
            logger.opt(exception=True).debug('watch: could not resolve the folder')
        if base is not None:
            try:
                current = library_mod.signature(base)
            except Exception:
                logger.opt(exception=True).debug('watch: could not read the folder')
                current = None
            if current is not None:
                if last is None:
                    last = current
                elif current != last:
                    logger.info(
                        'Music folder changed on disk ({} -> {} files)',
                        last[0], current[0],
                    )
                    last = current
                    quiet = 0
                    interval = _MIN_INTERVAL
                    library_mod.invalidate_cache()
                    try:
                        notify()
                    except Exception:
                        logger.opt(exception=True).debug('watch: notify failed')
                else:
                    quiet += 1
                    if quiet >= _BACKOFF_AFTER:
                        quiet = 0
                        interval = min(_MAX_INTERVAL, interval * 1.6)
        _stop.wait(interval)


def start(base_of: Callable[[], Optional[Path]], notify: Callable[[], None]) -> None:
    """Begin watching. *base_of* is re-read every tick so the watcher follows
    the user moving their library folder."""

    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_run,
        args=(base_of, notify),
        name='dannify-diskwatch',
        daemon=True,
    )
    _thread.start()


def stop() -> None:
    _stop.set()
