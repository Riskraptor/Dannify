"""The YouTube Music account: sign-out, home, likes, following, history, radio."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from loguru import logger

from .. import account
from .. import explorer

router = APIRouter()

# ---------------------------------------------------------------------------
# Account (YouTube Music sign-in), personalized feeds and likes
# ---------------------------------------------------------------------------
@router.get('/api/account')
def account_status_endpoint() -> dict[str, Any]:
    return account.status()


@router.post('/api/account/signout')
async def account_signout_endpoint() -> dict[str, Any]:
    result = account.sign_out()
    explorer.clear_cache()
    return result


@router.get('/api/home')
async def home_endpoint(limit: int = Query(6)) -> dict[str, Any]:
    """The YouTube Music home feed: personalized once signed in."""

    try:
        sections = await asyncio.to_thread(explorer.home, limit)
    except Exception as exc:
        logger.opt(exception=True).info('home feed failed')
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {'sections': sections, 'signed_in': account.is_signed_in()}


@router.get('/api/liked')
async def liked_endpoint(limit: int = Query(250)) -> dict[str, Any]:
    if not account.is_signed_in():
        raise HTTPException(status_code=401, detail='Not signed in')
    try:
        songs = await asyncio.to_thread(account.liked_songs, limit)
    except Exception as exc:
        logger.opt(exception=True).info('liked songs failed')
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {'songs': songs}


@router.get('/api/account/following')
async def account_following_endpoint() -> dict[str, Any]:
    if not account.is_signed_in():
        return {'artists': []}
    try:
        return {'artists': await asyncio.to_thread(account.subscriptions, 200)}
    except Exception:
        logger.opt(exception=True).debug('subscriptions failed')
        return {'artists': []}


@router.post('/api/account/follow')
async def account_follow_endpoint(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not account.is_signed_in():
        raise HTTPException(status_code=401, detail='Not signed in')
    try:
        return await asyncio.to_thread(
            account.follow, str(payload.get('channel_id') or ''), bool(payload.get('follow', True))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.opt(exception=True).info('follow failed')
        raise HTTPException(status_code=502, detail='YouTube Music did not answer') from exc


@router.get('/api/account/history')
async def account_history_endpoint() -> dict[str, Any]:
    if not account.is_signed_in():
        return {'songs': []}
    try:
        return {'songs': await asyncio.to_thread(account.history)}
    except Exception:
        logger.opt(exception=True).debug('history failed')
        return {'songs': []}


@router.post('/api/account/history/add')
async def account_history_add_endpoint(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not account.is_signed_in():
        return {'added': False}
    try:
        added = await asyncio.to_thread(account.add_history, str(payload.get('video_id') or ''))
    except Exception:
        logger.opt(exception=True).debug('history item failed')
        added = False
    return {'added': added}


@router.post('/api/account/playlist/add')
async def account_playlist_add_endpoint(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if not account.is_signed_in():
        raise HTTPException(status_code=401, detail='Not signed in')
    ids = payload.get('video_ids') if isinstance(payload.get('video_ids'), list) else []
    try:
        return await asyncio.to_thread(account.add_to_playlist, str(payload.get('playlist_id') or ''), ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.opt(exception=True).info('adding to a YouTube Music playlist failed')
        raise HTTPException(status_code=502, detail='YouTube Music did not take it') from exc


@router.post('/api/rate')
async def rate_endpoint(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Like / unlike a song on the signed-in YouTube Music account."""

    if not account.is_signed_in():
        raise HTTPException(status_code=401, detail='Not signed in')
    video_id = str(payload.get('video_id') or '').strip()
    liked = bool(payload.get('liked'))
    if not video_id:
        raise HTTPException(status_code=400, detail='video_id required')
    try:
        return await asyncio.to_thread(account.rate, video_id, liked)
    except Exception as exc:
        logger.opt(exception=True).info('rate failed')
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get('/api/radio')
async def radio_endpoint(
    video_id: str = Query(''), limit: int = Query(30)
) -> dict[str, Any]:
    """Endless mix for a track: powers autoplay when the queue runs out."""

    if not video_id:
        raise HTTPException(status_code=400, detail='video_id required')
    try:
        songs = await asyncio.to_thread(account.radio, video_id, limit)
    except Exception:
        logger.opt(exception=True).debug('radio failed for {}', video_id)
        songs = []
    return {'songs': songs}
