"""The user's own playlists."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from .. import playlists as playlists_mod

router = APIRouter()

# ---------------------------------------------------------------------------
# Playlists the listener makes (see playlists.py)
# ---------------------------------------------------------------------------


def _playlist_or_404(fn, *args):
    try:
        return fn(*args)
    except playlists_mod.NotFound as exc:
        raise HTTPException(status_code=404, detail='Playlist not found') from exc


@router.get('/api/playlists')
async def playlists_endpoint() -> dict[str, Any]:
    return {'playlists': playlists_mod.all_playlists()}


@router.post('/api/playlists')
async def playlist_create_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    tracks = payload.get('tracks') if isinstance(payload.get('tracks'), list) else []
    try:
        return playlists_mod.create(str(payload.get('name') or ''), tracks)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/api/playlists/{pid}')
async def playlist_endpoint(pid: str) -> dict[str, Any]:
    return _playlist_or_404(playlists_mod.get, pid)


@router.patch('/api/playlists/{pid}')
async def playlist_update_endpoint(pid: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    if isinstance(payload.get('name'), str):
        _playlist_or_404(playlists_mod.rename, pid, payload['name'])
    if isinstance(payload.get('tracks'), list):
        return _playlist_or_404(playlists_mod.set_tracks, pid, payload['tracks'])
    return _playlist_or_404(playlists_mod.get, pid)


@router.post('/api/playlists/{pid}/tracks')
async def playlist_add_endpoint(pid: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    tracks = payload.get('tracks') if isinstance(payload.get('tracks'), list) else []
    position = payload.get('position')
    return _playlist_or_404(
        playlists_mod.add_tracks, pid, tracks, int(position) if isinstance(position, int) else None
    )


@router.delete('/api/playlists/{pid}')
async def playlist_delete_endpoint(pid: str) -> dict[str, Any]:
    _playlist_or_404(playlists_mod.delete, pid)
    return {'deleted': True}
