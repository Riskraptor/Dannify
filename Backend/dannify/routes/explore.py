"""Browsing YouTube Music: search, artist, album and playlist pages, previews."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from loguru import logger

from .. import explorer
from .. import links, spotify, streaming

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
# A pasted Spotify link: its page, then its songs made playable
# ---------------------------------------------------------------------------


@router.get('/api/links/spotify')
async def spotify_link_endpoint(url: str = Query(..., max_length=500)) -> dict[str, Any]:
    """A Spotify track, album, playlist or artist link as a page of songs
    (spotify.link_page). 400 for what is not a Spotify link, 422 for one that
    is not music, 502 when Spotify could not be read."""

    if spotify.parse_spotify_url(url) is None:
        raise HTTPException(status_code=400, detail='Not a Spotify link')
    try:
        return await asyncio.to_thread(spotify.link_page, url)
    except spotify.Unsupported as exc:
        raise HTTPException(status_code=422, detail=f'Spotify {exc} links are not music') from exc
    except Exception as exc:
        logger.opt(exception=True).info('Spotify link could not be read: {}', url)
        raise HTTPException(status_code=502, detail='Spotify could not be read') from exc


@router.post('/api/links/match')
async def link_match_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """The same songs on YouTube Music, in order: ``{matches: [song|null]}``,
    at most links.MATCH_BATCH at a time."""

    tracks = payload.get('tracks')
    if not isinstance(tracks, list):
        raise HTTPException(status_code=400, detail='tracks must be a list')
    return {'matches': await asyncio.to_thread(links.match, tracks)}


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


@router.get('/api/explore/suggest')
async def explore_suggest_endpoint(
    q: str = Query('', max_length=200), limit: int = Query(8, ge=1, le=20)
) -> dict[str, Any]:
    """Ways to finish what is being typed in the search box.

    Never an error: with no connection, or YouTube saying no, the box simply
    offers nothing, and the search itself is what says why.
    """

    if not q.strip():
        return {'suggestions': []}
    try:
        return {'suggestions': await asyncio.to_thread(explorer.suggest, q, limit)}
    except Exception:
        logger.opt(exception=True).debug('search suggestions failed for {}', q)
        return {'suggestions': []}


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
