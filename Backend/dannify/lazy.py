"""A module imported the first time it is used, not when the app starts.

yt-dlp is the slow way to a stream: it is only needed when YouTube's app
clients refuse a song (streaming.py) and to fetch the bytes of a download
(downloader.py). Imported with the app, it cost every start a tenth of its
time to be ready for something most sessions never do.
"""

from __future__ import annotations

import importlib
import threading
from types import ModuleType
from typing import Any


class LazyModule:
    """Stands in for a module until something is asked of it.

    Reading or setting an attribute imports the module and passes the
    request on, so ``lazy.YoutubeDL`` and a test's
    ``monkeypatch.setattr(lazy, 'YoutubeDL', ...)`` both reach the real one.
    """

    def __init__(self, name: str) -> None:
        object.__setattr__(self, '_lazy_name', name)
        object.__setattr__(self, '_lazy_module', None)
        object.__setattr__(self, '_lazy_lock', threading.Lock())

    def _lazy_load(self) -> ModuleType:
        module = object.__getattribute__(self, '_lazy_module')
        if module is None:
            with object.__getattribute__(self, '_lazy_lock'):
                module = object.__getattribute__(self, '_lazy_module')
                if module is None:
                    module = importlib.import_module(object.__getattribute__(self, '_lazy_name'))
                    object.__setattr__(self, '_lazy_module', module)
        return module

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._lazy_load(), attr)

    def __setattr__(self, attr: str, value: Any) -> None:
        setattr(self._lazy_load(), attr, value)

    def __delattr__(self, attr: str) -> None:
        delattr(self._lazy_load(), attr)

    def __repr__(self) -> str:
        loaded = object.__getattribute__(self, '_lazy_module') is not None
        return f'<lazy module {object.__getattribute__(self, "_lazy_name")!r}{"" if loaded else " (not loaded)"}>'
