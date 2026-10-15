"""What has been listened to: History and Stats (see listens.py)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Query

from .. import listens as listens_mod

router = APIRouter()


@router.post('/api/listens')
async def listen_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """One listen, from the window: ``{track, seconds, started}``.

    ``recorded`` is false for a skip and for one already kept; either way
    the window has nothing left to hand over.
    """

    recorded = await asyncio.to_thread(
        listens_mod.record,
        payload.get('track'),
        payload.get('seconds'),
        payload.get('started'),
    )
    return {'recorded': recorded}


@router.get('/api/listens/stats')
async def listens_stats_endpoint(
    days: int = Query(0, ge=0, le=3660), top: int = Query(50, ge=1, le=200)
) -> dict[str, Any]:
    return await asyncio.to_thread(listens_mod.stats, days, top)


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
