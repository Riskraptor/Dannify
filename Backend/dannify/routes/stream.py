"""Playing from YouTube: resolving a video and streaming its audio."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from .. import streaming

router = APIRouter()

_YT_ID_RE = re.compile(r'[A-Za-z0-9_-]{11}')


_SPOTIFY_ID_RE = re.compile(r'[A-Za-z0-9]{22}')


async def _resolve_video_id(video_id: str, url: str) -> str:
    """Return a valid 11-char YouTube videoId, resolving non-YT ids/URLs.

    Hardens the stream endpoints against any client (or stale build) that
    sends a Spotify track id / URL instead of a YouTube videoId.
    """

    vid = (video_id or '').strip()
    if not vid and url:
        song = await asyncio.to_thread(streaming.resolve_stream, url)
        vid = str(song.get('video_id') or '')

    if vid and not _YT_ID_RE.fullmatch(vid):
        resolve_src = url
        if not resolve_src and _SPOTIFY_ID_RE.fullmatch(vid):
            resolve_src = f'https://open.spotify.com/track/{vid}'
        if resolve_src:
            song = await asyncio.to_thread(
                streaming.resolve_stream, resolve_src
            )
            vid = str(song.get('video_id') or '')
    return vid


@router.get('/api/stream/info')
async def stream_info_endpoint(
    video_id: str = Query(''),
    url: str = Query(''),
    prefetch: int = Query(0),
) -> dict[str, Any]:
    """Return ``{duration, mime}`` for a streamable source (no audio yet).

    Pass ``prefetch=1`` to also warm the on-disk cache in the background so a
    subsequent play (e.g. the next queued track) starts instantly.
    """

    try:
        vid = await _resolve_video_id(video_id, url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not vid:
        raise HTTPException(status_code=400, detail='Missing video_id or url')
    try:
        info = await asyncio.to_thread(streaming.probe, vid)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if prefetch:
        try:
            streaming.prefetch(vid)
        except Exception:
            pass
    return info


@router.get('/api/stream/prefetch')
async def stream_prefetch_endpoint(video_id: str = Query(...)) -> dict[str, Any]:
    vid = video_id.strip()
    if not vid:
        raise HTTPException(status_code=400, detail='Missing video_id')
    streaming.prefetch(vid)
    return {'prefetching': vid}


@router.get('/api/stream')
async def stream_endpoint(
    request: Request,
    video_id: str = Query('', alias='video_id'),
    url: str = Query(''),
    t: float = Query(0.0),
    force_mp3: int = Query(0),
):
    """Stream audio for a videoId.

    **Default path**: pure HTTP byte-range proxy to the upstream
    googlevideo URL. Forwards the browser's ``Range:`` header and
    response with ``Accept-Ranges: bytes`` + ``Content-Length`` so
    the browser does NATIVE seeking on the progress bar (instant
    same as scrubbing an MP3 served from any web server). No ffmpeg,
    no re-encode, no rebuffer.

    **Fallback path** (``?force_mp3=1`` or legacy ``?t=`` seek hint)
    transcode the audio to MP3 with ffmpeg on the fly. Slower; only
    kept for the (rare) browsers/codecs the proxy can't handle.
    """

    try:
        vid = await _resolve_video_id(video_id, url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Stream resolve failed for {} / {}', video_id, url)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not vid:
        raise HTTPException(status_code=400, detail='Missing video_id or url')

    # Honour the explicit fallback flag (or the legacy ``?t=`` seek path,
    # which only works on the ffmpeg side: but with the new proxy the
    # browser handles seeking natively, so ``?t=`` is essentially dead
    # code on the happy path).
    if force_mp3 or t > 0:
        try:
            mime, gen = await asyncio.to_thread(
                streaming.open_stream, vid, max(0.0, t)
            )
        except Exception as exc:
            logger.exception('Streaming (ffmpeg) failed for {}', vid)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return StreamingResponse(
            gen,
            media_type=mime,
            headers={
                'Content-Type': mime,
                'Cache-Control': 'no-store',
                'Accept-Ranges': 'none',
            },
        )

    # --- Default: native byte-range proxy (instant seek) ---
    range_header = request.headers.get('range') or request.headers.get('Range')
    try:
        status, headers, gen = await asyncio.to_thread(
            streaming.open_proxy, vid, range_header
        )
    except Exception as exc:
        logger.exception('Stream proxy failed for {}', vid)
        # Fallback to ffmpeg path on hard proxy failure so the user still
        # gets audio. Better degraded than broken.
        try:
            mime, fb_gen = await asyncio.to_thread(streaming.open_stream, vid)
        except Exception as exc2:
            raise HTTPException(status_code=502, detail=str(exc2)) from exc2
        return StreamingResponse(
            fb_gen,
            media_type=mime,
            headers={
                'Content-Type': mime,
                'Cache-Control': 'no-store',
                'Accept-Ranges': 'none',
            },
        )
    return StreamingResponse(
        gen,
        status_code=status,
        media_type=headers.get('Content-Type', 'audio/mp4'),
        headers=headers,
    )
