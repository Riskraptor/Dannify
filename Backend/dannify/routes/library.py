"""The saved library: songs, artists, details, repair."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from loguru import logger

from .. import account
from .. import library as library_mod
from .. import explorer
from .. import artist_links
from .. import details as details_mod
from .. import repair, vault
from .common import state

router = APIRouter()

@router.get('/api/library/locate')
async def library_locate_endpoint(
    video_id: str = Query(''),
    title: str = Query(''),
    artist: str = Query(''),
) -> dict[str, Any]:
    """Return the local file path for a song if it's downloaded.

    Frontend calls this on every "click play" so a downloaded song is
    served from disk (instant, no ffmpeg, no network) instead of being
    re-streamed from YouTube. Uses the same canonical-artist matching as
    the library index, plus an exact ``video_id`` shortcut.
    """

    base = state.download_dir
    if base is None:
        return {'found': False}
    try:
        hit = await asyncio.to_thread(
            library_mod.locate, base, video_id, artist, title
        )
    except Exception:
        logger.opt(exception=True).debug('library locate failed')
        return {'found': False}
    if hit is None:
        return {'found': False}
    return {'found': True, **hit}


# ---------------------------------------------------------------------------
# Offline library: artists, albums, search
# ---------------------------------------------------------------------------


def _require_download_dir() -> Path:
    if state.download_dir is None:
        raise HTTPException(status_code=500, detail='Library not ready')
    return state.download_dir


def _library_file(file: str) -> Optional[Path]:
    """*file* inside the music folder, or None if it names anywhere else.

    Checked by its shape before anything touches the disk: resolving a
    network path (a UNC name, host and share) is already a connection to that
    host, and the lyrics endpoints used to join whatever they were given onto
    the music folder and read its tags, which answers for any file on the
    machine.
    """

    base = state.download_dir
    if base is None or not file:
        return None
    rel = Path(str(file).replace(chr(92), '/'))
    if rel.is_absolute() or rel.drive or rel.anchor or '..' in rel.parts or ':' in str(file):
        return None
    root = Path(base).resolve()
    try:
        full = (root / rel).resolve()
        full.relative_to(root)
    except (ValueError, RuntimeError, OSError):
        return None
    return full


@router.get('/api/library')
async def library_endpoint() -> dict[str, Any]:
    base = _require_download_dir()
    return await asyncio.to_thread(library_mod.library, base)


@router.get('/api/library/search')
async def library_search_endpoint(
    q: str = Query(''), limit: int = Query(50)
) -> dict[str, Any]:
    base = _require_download_dir()
    return await asyncio.to_thread(library_mod.search, base, q, limit)


@router.get('/api/artists')
async def artists_endpoint() -> list[dict[str, Any]]:
    base = _require_download_dir()
    return await asyncio.to_thread(library_mod.artists, base)


# ---------------------------------------------------------------------------
# Refreshing saved songs' details, and artists'
# ---------------------------------------------------------------------------

_details_lock: Optional[asyncio.Lock] = None


@router.post('/api/library/details')
async def refresh_details_endpoint(
    payload: Optional[dict[str, Any]] = Body(None),
) -> dict[str, Any]:
    """Fetch the details of saved songs again, around the same audio.

    ``{"files": [...]}``. Runs in the background, one song at a time; the
    window hears how it goes over the websocket (``type: details``).
    """

    global _details_lock
    body = payload if isinstance(payload, dict) else {}
    if not vault.ready():
        raise HTTPException(status_code=409, detail='storage_unavailable')
    wanted = [f for f in (body.get('files') or []) if isinstance(f, str)][:2000]
    paths = [(f, p) for f, p in ((f, _library_file(f)) for f in wanted) if p is not None and p.is_file()]
    if not paths:
        raise HTTPException(status_code=400, detail='no_files')
    if _details_lock is None:
        _details_lock = asyncio.Lock()
    root = Path(state.download_dir).resolve()
    providers_ = list(getattr(state.downloader, 'lyrics_providers', None) or [])

    async def run() -> None:
        async with _details_lock:
            updated = failed = 0
            reasons: dict[str, int] = {}
            for index, (rel, path) in enumerate(paths, 1):
                outcome, why = await asyncio.to_thread(details_mod.refresh, root, path, providers_)
                if outcome == details_mod.UPDATED:
                    updated += 1
                else:
                    failed += 1
                    reasons[why] = reasons.get(why, 0) + 1
                await state.connections.broadcast({
                    'type': 'details', 'file': rel, 'state': outcome,
                    'done': index, 'total': len(paths),
                })
                # The library shows each one as it lands, in batches.
                if outcome == details_mod.UPDATED and index % 10 == 0:
                    library_mod.invalidate_cache()
                    await state.connections.broadcast({'type': 'library_changed'})
            library_mod.invalidate_cache()
            await state.connections.broadcast({
                'type': 'details', 'finished': True,
                'updated': updated, 'failed': failed, 'reasons': reasons,
            })
            await state.connections.broadcast({'type': 'library_changed'})

    task = asyncio.create_task(run())
    task.add_done_callback(
        lambda t: t.cancelled() or not t.exception()
        or logger.opt(exception=t.exception()).error('details refresh crashed')
    )
    return {'queued': len(paths)}


@router.post('/api/artists-online/refresh')
async def refresh_artists_endpoint(
    payload: Optional[dict[str, Any]] = Body(None),
) -> dict[str, Any]:
    """Look artists up again: their picture and their online page.

    ``{"names": [...]}``, or every artist in the library when there are none.
    """

    body = payload if isinstance(payload, dict) else {}
    names = [n for n in (body.get('names') or []) if isinstance(n, str) and n.strip()]
    if not names:
        base = _require_download_dir()
        names = [a['name'] for a in await asyncio.to_thread(library_mod.artists, base)]
    for name in names:
        known = artist_links._links.get(library_mod.fold(name)) or {}
        if known.get('id'):
            explorer.forget_artist(known['id'])
    hints = await _artist_hints(names)
    await asyncio.to_thread(artist_links.relook, names, hints)
    links, pending = await asyncio.to_thread(artist_links.known, names, hints)
    return {'links': links, 'pending': pending}


async def _artist_hints(names: list[str]) -> dict[str, dict[str, list[str]]]:
    """What the songs in the library say about who each artist is."""

    base = state.download_dir
    if base is None:
        return {}
    try:
        return await asyncio.to_thread(library_mod.artist_hints, Path(base), names)
    except Exception:
        logger.opt(exception=True).debug('artist hints unavailable')
        return {}


@router.get('/api/artists-online/links')
async def artist_links_endpoint() -> dict[str, Any]:
    """The online identity (page id and picture) of every artist in the library.

    What is not known yet is looked up in the background; ``pending`` says how
    many, and asking again shortly picks them up.
    """

    base = _require_download_dir()
    names = [a['name'] for a in await asyncio.to_thread(library_mod.artists, base)]
    hints = await _artist_hints(names)
    links, pending = await asyncio.to_thread(artist_links.known, names, hints)
    return {'links': links, 'pending': pending}


@router.get('/api/artists-online/page')
async def artist_online_page_endpoint(name: str = Query(...)) -> dict[str, Any]:
    """Everything a saved artist has released, for the rest of their page."""

    hint = (await _artist_hints([name])).get(name)
    found = await asyncio.to_thread(artist_links.link, name, hint)
    if not found:
        raise HTTPException(status_code=404, detail='Artist not found online')
    try:
        page = await asyncio.to_thread(explorer.artist, found['id'])
    except Exception as exc:
        logger.opt(exception=True).info('online page for {} failed', name)
        raise HTTPException(status_code=502, detail='unavailable') from exc
    return page


# `:path`, because a name can hold a slash: "AC/DC" arrives as AC%2FDC and is
# decoded before routing, which a plain parameter does not match.
@router.get('/api/artists/{name:path}')
async def artist_detail_endpoint(name: str) -> dict[str, Any]:
    base = _require_download_dir()
    detail = await asyncio.to_thread(library_mod.artist_detail, base, name)
    if detail is None:
        raise HTTPException(status_code=404, detail='Artist not found')
    return detail


# ---------------------------------------------------------------------------
# Repairing saved tracks that will not play (see repair.py)
# ---------------------------------------------------------------------------


def _repair_context():
    base = state.download_dir
    if base is None:
        return None
    return Path(base), state.downloader, state.data_dir


def _repair_notify(message: dict[str, Any]) -> None:
    # Called from the repair threads; the sockets belong to the event loop.
    loop = state.loop
    if loop is None or loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(state.connections.broadcast(message), loop)


def _repair_changed() -> None:
    library_mod.invalidate_cache()
    _repair_notify({'type': 'library_changed'})


repair.jobs.configure(_repair_context, _repair_notify, _repair_changed)


@router.get('/api/library/repair')
def repair_status_endpoint() -> dict[str, Any]:
    return repair.jobs.status()


@router.post('/api/library/repair')
async def repair_endpoint(
    payload: Optional[dict[str, Any]] = Body(None),
) -> dict[str, Any]:
    """Download saved tracks again, in place.

    ``{"all": true}`` repairs every track the library finds a problem with.
    ``{"files": [...]}`` repairs those, and with ``"force": true`` does so even
    when nothing looks wrong: the player asks for that after a file failed to
    play for a reason the checks here cannot see.
    """

    body = payload if isinstance(payload, dict) else {}
    if not vault.ready():
        raise HTTPException(status_code=409, detail='unavailable')
    base = _require_download_dir()
    if body.get('all'):
        data = await asyncio.to_thread(library_mod.library, base)
        files = [tr['file'] for tr in data.get('tracks', []) if tr.get('problem')]
        force = False
    else:
        raw = body.get('files')
        files = (
            [f for f in raw if isinstance(f, str) and f.strip()]
            if isinstance(raw, list)
            else []
        )
        force = bool(body.get('force'))
    return await asyncio.to_thread(repair.jobs.add, files, force)


@router.post('/api/library/repair/stop')
def repair_stop_endpoint() -> dict[str, Any]:
    return repair.jobs.stop()


@router.get('/api/library/playlists')
async def library_playlists_endpoint(limit: int = Query(50)) -> dict[str, Any]:
    if not account.is_signed_in():
        return {'playlists': []}
    try:
        playlists = await asyncio.to_thread(account.library_playlists, limit)
    except Exception:
        logger.opt(exception=True).debug('library playlists failed')
        playlists = []
    return {'playlists': playlists}
