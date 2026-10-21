"""What has been listened to: History and Stats (see listens.py)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from loguru import logger

from .. import listens as listens_mod
from .. import scrobble

router = APIRouter()


def _take(payload: dict[str, Any]) -> bool:
    found = listens_mod.checked(payload.get('track'), payload.get('seconds'), payload.get('started'))
    if found is None:
        return False
    song, at, seconds = found
    # ``keep: false`` is a listen for ListenBrainz only: the history is
    # paused, and what is paused is the history, not the account.
    if payload.get('keep', True) is False:
        scrobble.submit(song, at, seconds)
        return False
    recorded = listens_mod.keep(found)
    # Only a listen kept now: one already kept was sent when it was.
    if recorded:
        scrobble.submit(song, at, seconds)
    return recorded


@router.post('/api/listens')
async def listen_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """One listen, from the window: ``{track, seconds, started, keep}``.

    ``recorded`` is false for a skip and for one already kept; either way
    the window has nothing left to hand over.
    """

    body = payload if isinstance(payload, dict) else {}
    return {'recorded': await asyncio.to_thread(_take, body)}


@router.get('/api/listens/youtube')
def listens_youtube_status_endpoint() -> dict[str, Any]:
    """When YouTube Music's history was last brought in, and how much."""

    from .. import ytm_history  # noqa: PLC0415

    return ytm_history.status()


@router.post('/api/listens/youtube')
async def listens_youtube_sync_endpoint() -> dict[str, Any]:
    """Bring in what is new in YouTube Music's history (see ytm_history.py).

    401 when not signed in with Google, 503 when YouTube Music cannot be asked.
    """

    from .. import account, ytm_history  # noqa: PLC0415

    try:
        return await asyncio.to_thread(ytm_history.sync)
    except account.NotSignedIn as exc:
        raise HTTPException(status_code=401, detail='signed out') from exc
    except Exception as exc:
        logger.opt(exception=True).info('YouTube Music history could not be read')
        raise HTTPException(status_code=503, detail='unreachable') from exc


@router.get('/api/listenbrainz')
def listenbrainz_status_endpoint() -> dict[str, Any]:
    return scrobble.status()


@router.post('/api/listenbrainz/connect')
async def listenbrainz_connect_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Connect with the person's ListenBrainz user token.

    400 when ListenBrainz does not accept it, 503 when it cannot be asked.
    """

    token = (payload or {}).get('token') if isinstance(payload, dict) else None
    try:
        return await asyncio.to_thread(scrobble.connect, str(token or ''))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='invalid') from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail='unreachable') from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail='not kept') from exc


@router.post('/api/listenbrainz/disconnect')
async def listenbrainz_disconnect_endpoint() -> dict[str, Any]:
    return await asyncio.to_thread(scrobble.disconnect)


@router.get('/api/listens/stats')
async def listens_stats_endpoint(
    days: int = Query(0, ge=0, le=3660), top: int = Query(50, ge=1, le=200)
) -> dict[str, Any]:
    return await asyncio.to_thread(listens_mod.stats, days, top)


@router.get('/api/listens/mixes')
async def listens_mixes_endpoint() -> dict[str, Any]:
    """On repeat, Forgotten favourites and Top this month (see listens.mixes)."""

    return await asyncio.to_thread(listens_mod.mixes)


@router.get('/api/listens/recap')
async def listens_recap_endpoint(year: int = Query(0, ge=0, le=9999)) -> dict[str, Any]:
    """A year of listening; this year when none is named."""

    import datetime  # noqa: PLC0415

    return await asyncio.to_thread(listens_mod.recap, year or datetime.date.today().year)


@router.get('/api/listens/story')
async def listens_story_endpoint(
    period: str = Query('year', pattern='^(day|week|month|year)$'), year: int = Query(0, ge=0, le=9999)
) -> dict[str, Any]:
    """Today, this week, this month or a year, told as a story (see listens.story)."""

    return await asyncio.to_thread(listens_mod.story, period, year or None)


@router.get('/api/listens/glance')
async def listens_glance_endpoint() -> dict[str, Any]:
    """Today, this week, this month and this year at a glance, for Home."""

    return await asyncio.to_thread(listens_mod.glance)


@router.get('/api/listens/history')
async def listens_history_endpoint(
    limit: int = Query(100, ge=1, le=500), before: int = Query(0, ge=0)
) -> dict[str, Any]:
    return await asyncio.to_thread(listens_mod.history, limit, before)


@router.delete('/api/listens/item')
async def listen_forget_endpoint(
    at: int = Query(..., ge=0), key: str = Query(..., min_length=1, max_length=2100)
) -> dict[str, Any]:
    return {'removed': await asyncio.to_thread(listens_mod.forget, at, key)}


@router.delete('/api/listens')
async def listens_clear_endpoint() -> dict[str, Any]:
    await asyncio.to_thread(listens_mod.clear)
    return {'cleared': True}
