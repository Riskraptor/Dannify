"""Browsing YouTube Music: search, artist, album and playlist pages, previews."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from .. import explorer
from .. import spotify, streaming

router = APIRouter()

# ---------------------------------------------------------------------------
# Preview (resolve a Spotify/YouTube link before downloading)
# ---------------------------------------------------------------------------


@router.get('/api/preview')
def preview_endpoint(url: str = Query(...)) -> dict[str, Any]:
    """Resolve a Spotify/YouTube link into a rich, UI-ready preview payload.

    For tracks returns ``{type:'track', tracks:[...]}``; for albums/playlists
    returns the full track list so the UI can let the user pick a subset
    *before* any download or stream happens.
    """

    parsed = spotify.parse_spotify_url(url)
    if parsed is None:
        # Try a bare YouTube video.
        if 'youtu' in url:
            try:
                song = streaming.resolve_stream(url)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return {
                'type': 'track',
                'name': song.get('name'),
                'tracks': [song],
                'total': 1,
            }
        raise HTTPException(status_code=400, detail='Invalid URL')

    kind, sid = parsed
    try:
        if kind == 'track':
            song = spotify.track_from_id(sid)
            return {
                'type': 'track',
                'name': song.get('name'),
                'cover': song.get('cover_url'),
                'tracks': [song],
                'total': 1,
            }
        if kind == 'album':
            tracks = spotify.album_tracks_from_id(sid)
            cover = tracks[0].get('cover_url') if tracks else ''
            return {
                'type': 'album',
                'name': (tracks[0].get('album_name') if tracks else '') or '',
                'cover': cover,
                'tracks': tracks,
                'total': len(tracks),
            }
        if kind == 'playlist':
            name, tracks = spotify.playlist_info_and_tracks(sid)
            cover = tracks[0].get('cover_url') if tracks else ''
            return {
                'type': 'playlist',
                'name': name,
                'cover': cover,
                'playlist_url': url,
                'tracks': tracks,
                'total': len(tracks),
            }
    except Exception as exc:
        logger.exception('Preview failed for {}', url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=f'Unsupported type: {kind}')


# ---------------------------------------------------------------------------
# Online explorer - Spotify-style discovery (songs/artists/albums/playlists)
# ---------------------------------------------------------------------------


@router.get('/api/explore/search')
async def explore_search_endpoint(
    q: str = Query(''), limit: int = Query(20)
) -> dict[str, Any]:
    if not q.strip():
        return {'songs': [], 'artists': [], 'albums': [], 'playlists': []}
    try:
        return await asyncio.to_thread(explorer.search, q, limit)
    except explorer.SearchUnavailable as exc:
        # The window tells "no connection" from "nothing found" by this.
        raise HTTPException(status_code=503, detail='unreachable') from exc
    except Exception as exc:
        logger.exception('explore search failed for {}', q)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/explore/artist')
async def explore_artist_endpoint(id: str = Query(...)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(explorer.artist, id)
    except LookupError as exc:
        # No such artist or channel (removed, or a wrong link): say so, so
        # the page can tell it from YouTube failing to answer.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('explore artist failed for {}', id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/explore/album')
async def explore_album_endpoint(id: str = Query(...)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(explorer.album, id)
    except Exception as exc:
        logger.exception('explore album failed for {}', id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/explore/moods')
async def explore_moods_endpoint() -> dict[str, Any]:
    try:
        return {'sections': await asyncio.to_thread(explorer.moods)}
    except Exception as exc:
        logger.opt(exception=True).info('moods and genres failed')
        raise HTTPException(status_code=502, detail='unavailable') from exc


@router.get('/api/explore/moods/playlists')
async def explore_mood_playlists_endpoint(params: str = Query(..., max_length=400)) -> dict[str, Any]:
    try:
        return {'playlists': await asyncio.to_thread(explorer.mood_playlists, params)}
    except Exception as exc:
        logger.opt(exception=True).info('mood playlists failed')
        raise HTTPException(status_code=502, detail='unavailable') from exc


@router.get('/api/explore/playlist')
async def explore_playlist_endpoint(
    id: str = Query(...), limit: int = Query(200)
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(explorer.playlist, id, limit)
    except Exception as exc:
        logger.exception('explore playlist failed for {}', id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Streaming (play without downloading)
# ---------------------------------------------------------------------------


@router.get('/api/resolve')
async def resolve_endpoint(url: str = Query(...)) -> dict[str, Any]:
    try:
        song = await asyncio.to_thread(streaming.resolve_stream, url)
        # Warm the direct-URL cache + attach duration so the player can show
        # the end time immediately (transcoded streams carry no length header).
        vid = str(song.get('video_id') or '')
        if vid:
            try:
                info = await asyncio.to_thread(streaming.probe, vid)
                if info.get('duration'):
                    song = {**song, 'duration': info['duration']}
                song = {**song, 'stream_mime': info.get('mime')}
            except Exception:
                logger.opt(exception=True).debug('probe failed for {}', vid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Resolve failed for {}', url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return song
