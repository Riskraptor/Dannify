"""The app's settings, and the music folder they point at."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Query, Request
from loguru import logger

from .. import library as library_mod
from .. import lyrics_index
from .. import vault
from .common import (
    DEFAULT_SETTINGS,
    DownloadSlots,
    _coerce_download_dir,
    _effective_lyrics_providers,
    _save_settings,
    state,
)

router = APIRouter()

# Settings the interface has no business seeing. Where lyrics come from is an
# implementation detail: there is no picker for it, nothing renders it, and a
# name travelling to the UI is a name that ends up in the shipped bundle.
_PRIVATE_SETTINGS = (
    'lyrics_providers', 'audio_providers',
    # Fixed now (see INTERNAL_FORMAT). An old settings file may still hold a
    # choice from when they were offered; it is kept, and not used.
    'format', 'bitrate', 'generate_m3u',
)


@router.get('/api/settings')
def get_settings_endpoint(client_id: str = Query('')) -> dict[str, Any]:
    return {k: v for k, v in state.settings.items() if k not in _PRIVATE_SETTINGS}


@router.post('/api/settings/update')
async def update_settings_endpoint(
    request: Request, client_id: str = Query('')
) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if isinstance(payload, dict):
        # download_dir is special: validate THEN apply live (no restart).
        # Off the event loop: joining a folder walks all of it, and on a big
        # library or a network drive that held every stream, every search and
        # the websocket until it finished.
        if 'download_dir' in payload:
            await asyncio.to_thread(_apply_download_dir, payload['download_dir'])

        if 'lyrics_storage' in payload:
            mode = str(payload['lyrics_storage']).strip().lower()
            if mode in ('sidecar', 'central'):
                state.settings['lyrics_storage'] = mode
                # Downloads use it from now, not from the next start.
                if state.downloader is not None:
                    state.downloader.lyrics_storage = mode

        for key, value in payload.items():
            if key in ('download_dir', 'lyrics_storage') or key in _PRIVATE_SETTINGS:
                continue  # handled above, or not the window's to set
            if key in DEFAULT_SETTINGS:
                state.settings[key] = value
        _apply_to_downloader(payload)
    if state.settings_path is not None:
        await asyncio.to_thread(_save_settings, state.settings_path, state.settings)
    # The same view GET gives: the private ones stay private here too.
    return get_settings_endpoint()


def _apply_download_dir(value: Any) -> None:
    """Move the library to *value*, live. Runs on a worker thread."""

    new_dir = _coerce_download_dir(value)
    if new_dir is None:
        return
    state.download_dir = new_dir
    if state.downloader is not None:
        state.downloader.download_dir = new_dir
        new_dir.mkdir(parents=True, exist_ok=True)
    # Re-point the central lyrics index at the new folder
    # (no-op if storage mode is 'sidecar', it just exists).
    lyrics_index.init(new_dir)
    # And join it, so songs already in it open and new ones are
    # sealed the way that folder's songs are.
    try:
        vault.attach(new_dir)
    except Exception:
        logger.opt(exception=True).warning('could not join {}', new_dir)
    # Drop the library cache so the new location is scanned.
    library_mod.invalidate_cache()
    state.settings['download_dir'] = str(new_dir)
    # Broadcast so the frontend re-loads its library index.
    if state.loop is not None:
        asyncio.run_coroutine_threadsafe(
            state.connections.broadcast({'type': 'library_changed'}),
            state.loop,
        )


def _apply_to_downloader(payload: dict[str, Any]) -> None:
    """Hand the settings that shape a download to the downloader, live."""

    if state.downloader is not None:
        output = payload.get('output')
        if isinstance(output, str) and output:
            state.downloader.output_template = output.replace(
                '.{output-ext}', ''
            )
        if 'lyrics_providers' in payload or 'download_lyrics' in payload:
            state.downloader.lyrics_providers = (
                _effective_lyrics_providers(state.settings)
            )
        if 'organize_by_artist' in payload:
            state.downloader.organize_by_artist = bool(
                payload['organize_by_artist']
            )
    if 'max_parallel_downloads' in payload:
        try:
            count = max(1, int(payload['max_parallel_downloads']))
            if isinstance(state.download_semaphore, DownloadSlots):
                state.download_semaphore.resize(count)
            else:
                state.download_semaphore = DownloadSlots(count)
        except (TypeError, ValueError):
            pass


@router.post('/api/settings/pick-folder')
async def pick_folder_endpoint() -> dict[str, Any]:
    """Open the OS-native folder picker; return ``{path}`` or ``{cancelled:True}``.

    Uses pywebview's dialog when the app is running inside the desktop
    window. Falls back to Tk in browser-mode dev runs so the endpoint is
    safe to call from anywhere.
    """

    def _pick() -> Optional[str]:
        # 1) Desktop build: pywebview window present.
        try:
            import webview  # type: ignore
            if webview.windows:
                win = webview.windows[0]
                result = win.create_file_dialog(
                    webview.FOLDER_DIALOG,  # type: ignore[attr-defined]
                    allow_multiple=False,
                    directory=str(state.download_dir or Path.home()),
                )
                if result:
                    return result[0] if isinstance(result, (list, tuple)) else str(result)
                return None
        except Exception:
            logger.opt(exception=True).debug('pywebview folder picker unavailable')

        # 2) Dev / browser fallback.
        try:
            import tkinter as _tk
            from tkinter import filedialog as _fd

            root = _tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            chosen = _fd.askdirectory(
                title='Choose Dannify downloads folder',
                initialdir=str(state.download_dir or Path.home()),
            )
            root.destroy()
            return chosen or None
        except Exception:
            logger.opt(exception=True).debug('tk folder picker unavailable')
            return None

    chosen = await asyncio.to_thread(_pick)
    if not chosen:
        return {'cancelled': True}
    return {'path': str(Path(chosen).resolve())}
