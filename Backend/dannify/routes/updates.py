"""Checking for, preparing and applying updates."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from loguru import logger

from .. import osenv
from .. import layout, updates
from .common import state

router = APIRouter()

@router.get('/api/check_update')
def check_update() -> Optional[dict[str, Any]]:
    return None


@router.get('/api/update/check')
async def update_check_endpoint(force: int = Query(0)) -> dict[str, Any]:
    return await asyncio.to_thread(
        updates.check, state.version or '0.0.0', bool(force)
    )


@router.post('/api/update/download')
async def update_download_endpoint(
    payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    """Get the new version ready, streaming progress over the websocket.

    An installed copy builds the new version beside itself and the launcher
    swaps it in at the next start ('staged'). Anything else downloads the
    installer ('installer').
    """

    info = await asyncio.to_thread(updates.check, state.version or '0.0.0', False)
    loop = state.loop or asyncio.get_running_loop()

    def _progress(percent: float, stage: str = '', done: int = 0, total: int = 0) -> None:
        # A stage name and byte counts, not a sentence: the interface says it
        # in the user's language.
        asyncio.run_coroutine_threadsafe(
            state.connections.broadcast(
                {
                    'type': 'update_progress',
                    'progress': round(percent, 1),
                    'stage': stage,
                    'done': int(done or 0),
                    'total': int(total or 0),
                }
            ),
            loop,
        )

    if layout.managed() and info.get('package_url'):
        try:
            staged = await asyncio.to_thread(updates.stage, info, _progress)
        except Exception as exc:
            logger.opt(exception=True).info('update could not be prepared')
            raise HTTPException(status_code=502, detail='update_failed') from exc
        return {'path': str(staged), 'version': info.get('version', ''), 'kind': 'staged'}

    if not osenv.IS_WINDOWS and not info.get('self_update'):
        # A Linux or macOS copy that cannot install over itself (run from
        # source, or an app moved somewhere it cannot be replaced) is pointed
        # at the download page instead.
        raise HTTPException(status_code=409, detail='manual_update')
    # Only ever the address the release itself names. The interface used to
    # be able to send one of its own, and whatever came back was offered to
    # run as the installer.
    url = str(info.get('download_url') or '')
    if not url:
        raise HTTPException(status_code=404, detail='no_download')
    dest = Path(state.data_dir or Path.home()) / 'updates'
    try:
        path = await asyncio.to_thread(
            updates.download,
            url,
            dest,
            _progress,
            str(info.get('version') or ''),
            str(info.get('installer_signature_url') or ''),
            str(info.get('installer_kind') or 'installer'),
        )
    except Exception as exc:
        logger.opt(exception=True).info('update download failed')
        raise HTTPException(status_code=502, detail='update_failed') from exc
    return {
        'path': str(path),
        'version': info.get('version', ''),
        'kind': 'installer',
    }


@router.get('/api/update/status')
def update_status_endpoint() -> dict[str, Any]:
    """What the launcher and the last update left for the interface to say."""

    waiting = layout.pending()
    fresh = layout.just_updated()
    # A version the launcher had to take back out because it would not
    # start. It used to happen in silence: the update simply never arrived
    # and nobody knew why. Only while it is newer than what runs, so a later
    # release that did install puts an end to the message.
    bad = layout.skipped_version()
    rolled_back = (
        {'version': bad, 'running': state.version or ''}
        if bad and state.version and updates.is_newer(bad, state.version)
        else None
    )
    return {
        'managed': layout.managed(),
        'pending': {'version': str(waiting.get('version') or '')} if waiting else None,
        'just_updated': (
            {'version': state.version, 'notes': str(fresh.get('notes') or '')[:4000]}
            if fresh
            else None
        ),
        'rolled_back': rolled_back,
    }


@router.post('/api/update/acknowledge')
def update_acknowledge_endpoint() -> dict[str, Any]:
    """The "what is new" note was seen: do not show it again."""

    layout.acknowledge_update()
    return {'ok': True}


@router.post('/api/update/discard')
def update_discard_endpoint() -> dict[str, Any]:
    """Skipping a version also drops it if it was already waiting."""

    updates.discard_staged()
    return {'ok': True}
