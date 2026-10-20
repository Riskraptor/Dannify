"""Spotify: signing in, and the person's own Spotify, read for the window
(see spotify_account.py). Every answer that fails says why in `detail`, as
one of the reasons spotify_account names, so the window can say what to do."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import APIRouter, Body, HTTPException, Query

from .. import spotify_account as sp

router = APIRouter()

_STATUS = {
    sp.NOT_CONFIGURED: 409,
    sp.EXPIRED: 401,
    sp.NOT_ALLOWED: 403,
    'forbidden': 403,
    'not_found': 404,
}


async def _ask(fn: Callable[..., Any], *args: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args)
    except sp.SpotifyError as exc:
        raise HTTPException(status_code=_STATUS.get(exc.reason, 502), detail=exc.reason) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='invalid') from exc
    except Exception as exc:
        # Spotify unreachable, or answering in a way it never has.
        raise HTTPException(status_code=503, detail='unreachable') from exc


@router.get('/api/spotify')
def spotify_status_endpoint() -> dict[str, Any]:
    return sp.status()


@router.post('/api/spotify/connect')
async def spotify_connect_endpoint() -> dict[str, Any]:
    """The address of Spotify's sign-in page, for the window to open."""

    return {'url': await _ask(sp.begin)}


@router.post('/api/spotify/disconnect')
async def spotify_disconnect_endpoint() -> dict[str, Any]:
    return await _ask(sp.disconnect)


@router.post('/api/spotify/app')
async def spotify_app_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Use one's own Spotify app: ``{client_id}`` ('' for Dannify's)."""

    value = payload.get('client_id') if isinstance(payload, dict) else ''
    return await _ask(sp.set_client_id, str(value or ''))


@router.post('/api/spotify/refresh')
def spotify_refresh_endpoint() -> dict[str, Any]:
    """Forget what was read, so the next answers come from Spotify."""

    sp.forget()
    return {'ok': True}


@router.get('/api/spotify/playlists')
async def spotify_playlists_endpoint() -> dict[str, Any]:
    return {'playlists': await _ask(sp.playlists)}


@router.get('/api/spotify/playlist/{pid}')
async def spotify_playlist_endpoint(pid: str) -> dict[str, Any]:
    return await _ask(sp.playlist, pid[:64])


@router.get('/api/spotify/liked')
async def spotify_liked_endpoint() -> dict[str, Any]:
    return {'songs': await _ask(sp.liked)}


@router.get('/api/spotify/albums')
async def spotify_albums_endpoint() -> dict[str, Any]:
    return {'albums': await _ask(sp.albums)}


@router.get('/api/spotify/album/{aid}')
async def spotify_album_endpoint(aid: str) -> dict[str, Any]:
    return await _ask(sp.album, aid[:64])


@router.get('/api/spotify/artists')
async def spotify_artists_endpoint() -> dict[str, Any]:
    return {'artists': await _ask(sp.artists)}


@router.get('/api/spotify/top')
async def spotify_top_endpoint(
    kind: str = Query('tracks'), span: str = Query('medium_term')
) -> dict[str, Any]:
    return {'items': await _ask(sp.top, kind, span)}


@router.get('/api/spotify/recent')
async def spotify_recent_endpoint() -> dict[str, Any]:
    return {'songs': await _ask(sp.recent)}


@router.post('/api/spotify/import')
async def spotify_import_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Copy a Spotify list into a new Dannify playlist: ``{kind, id, name}``."""

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='invalid')
    job = await _ask(
        sp.start_import,
        str(payload.get('kind') or ''),
        str(payload.get('id') or '')[:64],
        str(payload.get('name') or '')[:120],
    )
    return {'job': job}


@router.get('/api/spotify/import/{job}')
def spotify_import_status_endpoint(job: str) -> dict[str, Any]:
    found = sp.import_status(job[:32])
    if not found:
        raise HTTPException(status_code=404, detail='not_found')
    return found
