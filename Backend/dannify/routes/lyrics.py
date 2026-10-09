"""Lyrics: finding, storing, versions, timing offsets and publishing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from loguru import logger

from .. import library as library_mod
from .. import lyrics as lyrics_mod
from .. import lyrics_index
from .. import lyrics_offsets
from .. import lyrics_publish
from .. import spotify, streaming
from .common import _effective_lyrics_providers, state
from .library import _library_file

router = APIRouter()

# ---------------------------------------------------------------------------
# Lyrics (synced + plain) for streamed or downloaded tracks
# ---------------------------------------------------------------------------


def _lyrics_storage_mode() -> str:
    return str(state.settings.get('lyrics_storage') or 'sidecar').lower()


def _persist_lyrics(full: Path, artist: str, title: str, text: str) -> None:
    """Write *text* as the .lrc for this track in the user-chosen location."""
    if not text:
        return
    # The song itself has to be there. Lyrics for one deleted a moment ago
    # (still on screen, still paused) used to be written beside its old name,
    # leaving a lyrics file behind with nothing to belong to.
    if not full.is_file():
        return
    mode = _lyrics_storage_mode()
    try:
        if mode == 'central':
            lyrics_index.store(artist, title, text)
        else:
            full.with_suffix('.lrc').write_text(text, encoding='utf-8')
    except OSError:
        logger.opt(exception=True).debug('Could not write .lrc for {}', full)


def _read_existing_lyrics(full: Path, artist: str, title: str) -> str:
    """Return any already-stored .lrc text for this track, '' if none.

    Looks in BOTH places (sidecar + central) regardless of the current
    setting, so toggling the storage mode doesn't orphan previously
    saved lyrics.
    """
    sidecar = full.with_suffix('.lrc')
    if sidecar.is_file():
        try:
            return sidecar.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            pass
    central = lyrics_index.lookup_text(artist, title)
    return central or ''


def _lyrics_from_file(
    file: str,
    refresh: bool = False,
    hints: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Read synced/plain lyrics from a downloaded file's .lrc or tags.

    When *refresh* is True the local ``.lrc``/embedded copies are skipped and
    fresh lyrics are fetched online (and re-saved), so the reload button always
    re-queries the source.
    """

    if state.download_dir is None:
        raise HTTPException(status_code=500, detail='Library not ready')
    full = _library_file(file)
    if full is None:
        raise HTTPException(status_code=400, detail='Invalid path')

    # Prefer a stored .lrc (sidecar OR central index) unless reloading.
    meta_for_keys = library_mod._read_tags(full)
    keys_artist = meta_for_keys.get('artist', '') or ''
    keys_title = meta_for_keys.get('title', '') or ''
    if not refresh:
        stored = _read_existing_lyrics(full, keys_artist, keys_title)
        if stored:
            lines = lyrics_mod.parse_lrc(stored)
            if lines:
                plain = '\n'.join(
                    ln['text'] for ln in lines if ln['text']
                ) or None
                return {'synced': lines, 'plain': plain, 'has': True}
            txt = stored.strip()
            if txt:
                return {'synced': [], 'plain': txt, 'has': True}

    # Fall back to plain lyrics kept in the file itself.
    plain = None
    try:
        from . import tags as _tags  # noqa: PLC0415

        plain = _tags.lyrics(full) or None
    except Exception:
        logger.opt(exception=True).debug('Embedded lyrics read failed')

    # ------------------------------------------------------------------
    # Online fallback: if the file has no synced lyrics locally, query the
    # online source (lrclib) using the file's own tags, then PERSIST the
    # result as a .lrc sidecar so future loads are instant (offline): unless
    # the user explicitly reloads.
    # ------------------------------------------------------------------
    try:
        meta = library_mod._read_tags(full)
        song = {
            'name': meta.get('title') or '',
            'artists': meta.get('artists') or (
                [meta['artist']] if meta.get('artist') else []
            ),
            'album_name': meta.get('album') or '',
            'duration': meta.get('duration') or 0,
        }
        # A downloaded file's tags are whatever the download managed to
        # write, and they are regularly thinner than what the app itself
        # knows: a missing artist used to skip the online lookup entirely,
        # which is why lyrics published for a downloaded song never came
        # back. Fall back to what the player is showing.
        hint = hints or {}
        if not song['name']:
            song['name'] = str(hint.get('title') or '')
        if not song['artists']:
            song['artists'] = [
                a.strip()
                for a in str(hint.get('artist') or '').split(',')
                if a.strip()
            ]
        if not song['album_name']:
            song['album_name'] = str(hint.get('album') or '')
        if not song['duration']:
            song['duration'] = int(hint.get('duration') or 0)

        if song['name'] and song['artists']:
            raw = lyrics_mod.fetch(
                song, _effective_lyrics_providers(state.settings) or ['lrclib']
            )
            # Tags and the player can disagree about how a track is named.
            # If the file's own version found nothing, try the player's.
            if (raw is None or not raw.has_any()) and hint.get('title'):
                alt = {
                    'name': str(hint.get('title') or ''),
                    'artists': [
                        a.strip()
                        for a in str(hint.get('artist') or '').split(',')
                        if a.strip()
                    ],
                    'album_name': str(hint.get('album') or ''),
                    'duration': int(hint.get('duration') or 0),
                }
                if alt['name'] and alt['artists'] and alt != song:
                    raw = lyrics_mod.fetch(
                        alt,
                        _effective_lyrics_providers(state.settings) or ['lrclib'],
                    )
            if raw is not None and raw.has_any():
                # Persist using the user-chosen storage location.
                text_to_save = raw.synced or (raw.plain or '')
                if text_to_save:
                    _persist_lyrics(
                        full,
                        meta.get('artist', '') or keys_artist,
                        meta.get('title', '') or keys_title,
                        text_to_save,
                    )

                synced_lines = lyrics_mod.parse_lrc(raw.synced)
                out_plain = raw.plain or plain
                if not out_plain and synced_lines:
                    out_plain = '\n'.join(
                        ln['text'] for ln in synced_lines if ln['text']
                    ) or None
                return {
                    'synced': synced_lines,
                    'plain': out_plain,
                    'has': bool(synced_lines or out_plain),
                }
    except Exception:
        logger.opt(exception=True).debug('Online lyrics fallback failed')

    return {
        'synced': [],
        'plain': plain,
        'has': bool(plain),
    }


@router.get('/api/lyrics')
async def lyrics_endpoint(
    file: str = Query(''),
    url: str = Query(''),
    title: str = Query(''),
    artist: str = Query(''),
    album: str = Query(''),
    duration: int = Query(0),
    refresh: int = Query(0),
) -> dict[str, Any]:
    """Return ``{synced:[{time,text}], plain, has}`` for a track.

    Accepts either a downloaded ``file`` (reads .lrc/embedded), a Spotify/
    YouTube ``url`` (live lrclib lookup), or raw ``title``/``artist`` hints.
    Pass ``refresh=1`` to bypass the lyrics cache and re-query the source.
    """
    if refresh:
        lyrics_mod.clear_cache()

    if file:
        result = await asyncio.to_thread(
            _lyrics_from_file,
            file,
            bool(refresh),
            {
                'title': title,
                'artist': artist,
                'album': album,
                'duration': duration,
            },
        )
        # Attach the crowd-sourced prefs using the file's own tags.
        try:
            where = _library_file(file)
            if where is None:
                raise ValueError('not in the library')
            meta = library_mod._read_tags(where)
            prefs = lyrics_offsets.get_prefs(
                meta.get('title', ''), meta.get('artist', '')
            )
            result['offset'] = prefs['offset']
            result['version'] = prefs['version']
            result['title'] = meta.get('title', '')
            result['artist'] = meta.get('artist', '')
        except Exception:
            result.setdefault('offset', 0.0)
            result.setdefault('version', 0)
        return result

    song: dict[str, Any]
    if url:
        parsed = spotify.parse_spotify_url(url)
        if parsed is not None and parsed[0] == 'track':
            song = await asyncio.to_thread(spotify.track_from_id, parsed[1])
        else:
            song = await asyncio.to_thread(streaming.resolve_stream, url)
    else:
        artists = [a.strip() for a in artist.split(',') if a.strip()]
        song = {
            'name': title,
            'artists': artists,
            'album_name': album,
            'duration': duration,
        }
    if not song.get('name'):
        return {
            'synced': [], 'plain': None, 'has': False,
            'offset': 0.0, 'version': 0, 'version_count': 0,
        }

    song_artists = song.get('artists') or []
    primary = song_artists[0] if song_artists else ''
    prefs = lyrics_offsets.get_prefs(song.get('name', ''), primary)

    if prefs['version'] > 0:
        # User picked a specific version → resolve the full list.
        versions = await asyncio.to_thread(
            lyrics_mod.fetch_versions_structured, song
        )
        if versions:
            idx = prefs['version'] if prefs['version'] < len(versions) else 0
            chosen = versions[idx]
            result = {
                'synced': chosen['synced'],
                'plain': chosen['plain'],
                'has': True,
                'version_count': len(versions),
            }
        else:
            result = await asyncio.to_thread(
                lyrics_mod.fetch_structured,
                song,
                _effective_lyrics_providers(state.settings) or ['lrclib'],
            )
            result['version_count'] = 0
    else:
        # FAST PATH: single best-match fetch (one parallel /get+/search round).
        # The version count is discovered lazily by the frontend only when the
        # user opens the switcher: keeping the common load quick.
        result = await asyncio.to_thread(
            lyrics_mod.fetch_structured,
            song,
            _effective_lyrics_providers(state.settings) or ['lrclib'],
        )
        # -1 means "unknown; ask /api/lyrics/versions on demand".
        result['version_count'] = -1 if result.get('synced') else 0

    result['offset'] = prefs['offset']
    result['version'] = prefs['version']
    result['title'] = song.get('name', '')
    result['artist'] = primary
    return result


@router.get('/api/lyrics/versions')
async def lyrics_versions_endpoint(
    title: str = Query(''),
    artist: str = Query(''),
    album: str = Query(''),
    duration: int = Query(0),
    url: str = Query(''),
    file: str = Query(''),
) -> dict[str, Any]:
    """Return ALL synced lyric versions for a song so the UI can switch.

    Each entry: ``{synced:[{time,text}], plain}``. The currently-saved version
    index + offset are included.
    """

    song: dict[str, Any]
    where = _library_file(file) if file else None
    if where is not None:
        try:
            meta = library_mod._read_tags(where)
            song = {
                'name': meta.get('title') or '',
                'artists': meta.get('artists')
                or ([meta['artist']] if meta.get('artist') else []),
                'album_name': meta.get('album') or '',
                'duration': meta.get('duration') or 0,
            }
        except Exception:
            song = {'name': title, 'artists': [artist] if artist else []}
    elif url:
        parsed = spotify.parse_spotify_url(url)
        if parsed is not None and parsed[0] == 'track':
            song = await asyncio.to_thread(spotify.track_from_id, parsed[1])
        else:
            song = await asyncio.to_thread(streaming.resolve_stream, url)
    else:
        artists = [a.strip() for a in artist.split(',') if a.strip()]
        song = {
            'name': title,
            'artists': artists,
            'album_name': album,
            'duration': duration,
        }
    if not song.get('name'):
        return {'versions': [], 'version': 0, 'offset': 0.0}
    versions = await asyncio.to_thread(
        lyrics_mod.fetch_versions_structured, song
    )
    song_artists = song.get('artists') or []
    primary = song_artists[0] if song_artists else ''
    prefs = lyrics_offsets.get_prefs(song.get('name', ''), primary)
    return {
        'versions': versions,
        'version': prefs['version'] if prefs['version'] < len(versions) else 0,
        'offset': prefs['offset'],
        'title': song.get('name', ''),
        'artist': primary,
    }


@router.post('/api/lyrics/offset')
async def lyrics_offset_endpoint(request: Request) -> dict[str, Any]:
    """Save per-song lyric prefs (timing offset + chosen version). Shared.

    Body: ``{title, artist, offset?, version?}``. Positive offset = lyrics
    appear later; version = index of the synced version that syncs best.
    """

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid JSON')
    title = str(payload.get('title') or '').strip()
    artist = str(payload.get('artist') or '').strip()
    if not title or not artist:
        raise HTTPException(status_code=400, detail='title and artist required')
    offset = payload.get('offset')
    version = payload.get('version')
    try:
        offset = None if offset is None else float(offset)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='offset must be a number')
    try:
        version = None if version is None else int(version)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail='version must be an int')
    rec = await asyncio.to_thread(
        lyrics_offsets.set, title, artist, offset, version
    )
    return {
        'title': title,
        'artist': artist,
        'offset': rec['offset'],
        'version': rec['version'],
    }


@router.post('/api/lyrics/publish')
async def lyrics_publish_endpoint(request: Request) -> dict[str, Any]:
    """Submit lyrics to lrclib.

    Body: ``{track, artist, album, duration, plain?, synced?}``.

    The flow is entirely synchronous from the client's POV: this endpoint
    requests a fresh proof-of-work challenge from lrclib, solves it
    (multi-process search, ~10-20 s on a typical box), then posts the
    final lyrics. We invalidate the in-memory lyrics cache for this song
    on success so the next ``/api/lyrics`` lookup picks up the new
    contribution from lrclib.

    Returns ``{published: true}`` on success or ``{published: false,
    error: '…'}`` on failure (HTTP 200 either way. The UI shows the
    error inline; this avoids needing two error-handling paths).
    """

    try:
        payload = await request.json()
    except Exception:
        return {'published': False, 'error': 'Invalid JSON body'}

    track = str(payload.get('track') or '').strip()
    artist = str(payload.get('artist') or '').strip()
    album = str(payload.get('album') or '').strip()
    plain = str(payload.get('plain') or '')
    synced = str(payload.get('synced') or '')
    try:
        duration = float(payload.get('duration') or 0)
    except (TypeError, ValueError):
        return {'published': False, 'error': 'duration must be a number'}

    if not track or not artist:
        return {
            'published': False,
            'error': 'Track title and artist are required.',
        }
    if duration <= 0:
        return {
            'published': False,
            'error': 'Track duration is required (must be > 0).',
        }
    if not plain.strip() and not synced.strip():
        # lrclib's docs allow empty-both (marks track as instrumental),
        # but our UI shouldn't be sending that: guard explicitly.
        return {
            'published': False,
            'error': 'No lyrics provided. Add plain or synced lyrics.',
        }

    try:
        await asyncio.to_thread(
            lyrics_publish.publish,
            track_name=track,
            artist_name=artist,
            album_name=album,
            duration=duration,
            plain_lyrics=plain,
            synced_lyrics=synced,
        )
    except lyrics_publish.PublishError as exc:
        logger.warning('lyrics publish refused: {}', exc)
        return {'published': False, 'error': str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception('lyrics publish crashed')
        return {'published': False, 'error': f'Unexpected error: {exc}'}

    # Drop our caches for this song so the next lookup refreshes from
    # lrclib (which now serves the user's own contribution).
    try:
        song_key = {
            'name': track,
            'artists': [artist],
        }
        lyrics_mod.clear_cache(song_key)
    except Exception:
        logger.opt(exception=True).debug(
            'Could not clear lyrics cache after publish'
        )

    return {'published': True}
