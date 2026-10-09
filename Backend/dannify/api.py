"""FastAPI router exposed by Dannify.

The endpoints intentionally mirror the surface that the previous
``spotdl``-powered backend exposed so the existing Vue frontend keeps
working without changes:

* ``GET  /api/version``
* ``GET  /api/songs/search``
* ``POST /api/download/url`` (optional JSON body: resolved Spotify row so
  ``track_number`` / ``album_track_total`` survive re-fetch by URL)
* ``GET  /api/settings``
* ``POST /api/settings/update``
* ``WS   /api/ws``
* ``GET  /api/check_update``

Each area lives in its own module under dannify/routes; this joins them into
one router and keeps the names main.py and the tests use here.
"""

from __future__ import annotations

import time  # noqa: F401  (tests set api.time.monotonic)

from fastapi import APIRouter

from .routes import system, downloads, settings, explore, stream, lyrics, library, playlists, account, updates
from .routes.common import (  # noqa: F401  (used through api.<name>)
    ConnectionManager,
    DEFAULT_SETTINGS,
    DownloadSlots,
    INTERNAL_BITRATE,
    INTERNAL_FORMAT,
    _effective_lyrics_providers,
    _load_settings,
    _save_settings,
    state,
)
from .routes.system import (  # noqa: F401  (used through api.<name>)
    WINDOW_ERRORS_PER_MINUTE,
    _reachable,
    _window_error_times,
    _window_errors,
    clear_caches_endpoint,
    client_error_endpoint,
    flush_reports,
    storage_endpoint,
    support_report_send_endpoint,
    support_report_status_endpoint,
)
from .routes.lyrics import (  # noqa: F401  (used through api.<name>)
    _persist_lyrics,
)
from .routes.downloads import (  # noqa: F401  (used through api.<name>)
    _merge_client_track_hints,
)
from .routes.library import (  # noqa: F401  (used through api.<name>)
    _library_file,
)
from .routes.updates import (  # noqa: F401  (used through api.<name>)
    update_status_endpoint,
)

# One router for the whole API, in the order the parts were written: a
# request matches the first route that fits.
router = APIRouter()
for _part in (system, downloads, settings, explore, stream, lyrics, library, playlists, account, updates):
    router.include_router(_part.router)
