"""Discord: whether the song playing shows on the person's profile, and what
the window says is playing (see presence.py)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body

from .. import presence

router = APIRouter()


@router.get('/api/discord')
def discord_status_endpoint() -> dict[str, Any]:
    return presence.status()


@router.post('/api/discord')
async def discord_set_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Turn it on or off: ``{enabled: bool}``."""

    on = bool(payload.get('enabled')) if isinstance(payload, dict) else False
    return await asyncio.to_thread(presence.set_enabled, on)


@router.post('/api/discord/now-playing')
def discord_now_playing_endpoint(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """What is playing: title, artist, album, cover, video_id, duration,
    position (seconds) and playing; no title for nothing."""

    presence.now_playing(payload)
    return {'ok': True}
