"""Fetch a saved song's details again, and keep the song exactly as it is.

Title, artists, album, year, track number, genre and artwork come from
YouTube Music for the recording the song was saved from (its video id), and
are written back around the same audio: nothing is downloaded but the
details and the picture, the file keeps its name and place, and it stays
sealed. A song saved before its details were any good, or whose album has
since been released properly, catches up without being downloaded again.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from . import vault

UPDATED = 'updated'
FAILED = 'failed'
# Why, when it failed. The window says it in the user's language.
NOT_FOUND = 'not_found'
DAMAGED = 'damaged'
OFFLINE = 'offline'


def _song_from(head: dict[str, Any], path: Path) -> dict[str, Any]:
    artists = head.get('artists')
    if not isinstance(artists, list) or not artists:
        artists = [head['artist']] if head.get('artist') else []
    return {
        'name': head.get('title') or path.stem,
        'artists': [str(a) for a in artists if a],
        'album_name': head.get('album') or '',
        'duration': int(head.get('duration') or 0),
    }


def _fresh_details(song: dict[str, Any], video_id: str) -> tuple[Optional[dict[str, Any]], str]:
    """The song as YouTube Music describes it now, and its video id."""

    from . import providers  # noqa: PLC0415  (imports ytmusicapi)

    try:
        if video_id:
            match = providers.find_match_for_video(song, video_id)
        else:
            video_id, match = providers.find_match(song)
    except Exception:
        logger.opt(exception=True).debug('details lookup failed for {}', song.get('name'))
        return None, ''
    if not match or not video_id:
        return None, video_id or ''
    fresh = providers.enrich_from_match({**song, 'youtube_id': video_id}, match)
    return fresh, video_id


def refresh(root: Path, path: Path, lyrics_providers: Optional[list[str]] = None) -> tuple[str, str]:
    """Bring one saved song's details up to date. Returns ``(state, why)``."""

    from . import downloader as dl  # noqa: PLC0415
    from . import lyrics as lyrics_mod  # noqa: PLC0415

    head, problem = vault.inspect(path)
    if head is None or problem:
        # A song that will not open is for a repair, which downloads it again.
        return FAILED, DAMAGED
    song = _song_from(head, path)
    video_id = str(head.get('video_id') or '')
    fresh, video_id = _fresh_details(song, video_id)
    if fresh is None:
        return FAILED, NOT_FOUND if _online() else OFFLINE

    ext = str(head.get('ext') or '.m4a')
    # The same bench a download uses, so a crash leaves nothing behind that
    # the startup sweep does not clear.
    bench = Path(tempfile.mkdtemp(prefix='dnf-dl-'))
    try:
        plain = bench / f'song{ext}'
        with open(plain, 'wb') as out:
            for chunk in vault.open_range(path):
                out.write(chunk)

        if not fresh.get('genre'):
            try:
                genre = dl._fetch_itunes_genre(fresh)
                if genre:
                    fresh = {**fresh, 'genre': genre}
            except Exception:
                logger.opt(exception=True).debug('genre lookup failed')
        dl.embed_metadata(plain, fresh)
        dl.embed_video_id(plain, video_id)

        # Lyrics too, when the song has none beside it yet.
        lyric = path.with_suffix('.lrc')
        if lyrics_providers and not lyric.exists():
            try:
                found = lyrics_mod.fetch(fresh, lyrics_providers)
                if found is not None and found.has_any():
                    dl.embed_lyrics(plain, found, write_sidecar=True)
                    made = plain.with_suffix('.lrc')
                    if made.is_file():
                        shutil.move(str(made), str(lyric))
            except Exception:
                logger.opt(exception=True).debug('lyrics for {} not found', path.name)

        meta = vault._tags_of(plain)
        artists = fresh.get('artists') or []
        for field, value in (
            ('title', fresh.get('name') or ''),
            ('artist', artists[0] if artists else ''),
            ('album', fresh.get('album_name') or ''),
            ('video_id', video_id),
        ):
            if value and not meta.get(field):
                meta[field] = value
        if artists:
            meta['artists'] = list(artists)

        rebuilt = path.with_suffix(path.suffix + '.rebuilt')
        vault.seal(plain, rebuilt, meta)  # seal() removes the plain copy
        _swap(rebuilt, path)
        try:
            vault._note(root, path, meta)
        except Exception:
            logger.opt(exception=True).debug('could not note {}', path.name)
        return UPDATED, ''
    except Exception:
        logger.opt(exception=True).warning('could not refresh the details of {}', path.name)
        path.with_suffix(path.suffix + '.rebuilt').unlink(missing_ok=True)
        path.with_suffix(path.suffix + '.rebuilt.part').unlink(missing_ok=True)
        return FAILED, DAMAGED
    finally:
        shutil.rmtree(bench, ignore_errors=True)


def _swap(fresh: Path, path: Path) -> None:
    """Put the rebuilt song in place of the old one; retried while the old
    one is being read for a moment (a cover being drawn, a scan)."""

    for attempt in range(6):
        try:
            fresh.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.25 * (attempt + 1))


def _online() -> bool:
    import socket  # noqa: PLC0415

    try:
        with socket.create_connection(('music.youtube.com', 443), timeout=3):
            return True
    except OSError:
        return False
