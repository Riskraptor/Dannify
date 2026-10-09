"""The library's files over HTTP: the song list, deleting, covers, and the
saved songs themselves (opened from their sealed form as they stream), plus
files opened from outside the library."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import Response
from loguru import logger

from . import api, osenv


def _extract_cover(path: Path) -> tuple[bytes | None, str | None]:
    """Return ``(image_bytes, mime)`` for the embedded cover, or ``(None, None)``."""

    # A sealed container carries its artwork in its own header; a tag reader
    # would only see noise.
    if path.suffix.lower() == '.dnf':
        from dannify import vault

        found = vault.cover(path)
        return found if found else (None, None)

    from dannify import tags

    try:
        found = tags.cover(path)
    except Exception:
        found = None
    return found if found else (None, None)


def mount(app, download_dir: Path) -> None:  # noqa: ANN001
    def _live_download_dir() -> Path:
        """Always use the CURRENT download_dir.

        ``DOWNLOAD_DIR`` is the boot-time default but ``state.download_dir``
        reflects whatever the user picked in Settings (the
        ``POST /api/settings/update`` endpoint mutates it live). Without
        this indirection, ``/list``, ``/cover``, ``/downloads/`` and
        ``/delete`` would keep serving from the original folder and the
        UI would 404 every file after a folder change.
        """
        d = api.state.download_dir or download_dir
        return Path(d)

    @app.get('/list')
    def list_downloads() -> list[str]:
        audio_exts = {'.mp3', '.m4a', '.flac', '.ogg', '.wav', '.aac', '.opus', '.dnf'}
        base = _live_download_dir().resolve()
        if not base.exists():
            return []
        files: list[str] = []
        # Walk recursively so per-playlist sub-folders show up alongside
        # loose downloads in the library view.
        for path in base.rglob('*'):
            if not path.is_file():
                continue
            if path.suffix.lower() not in audio_exts:
                continue
            files.append(path.relative_to(base).as_posix())
        files.sort()
        return files

    @app.delete('/delete')
    def delete_download(file: str) -> dict:
        # Resolve and confine to the LIVE download_dir to prevent traversal.
        base = _live_download_dir().resolve()
        try:
            full = (base / file).resolve()
            full.relative_to(base)
        except (ValueError, RuntimeError):
            return {'deleted': False, 'error': 'Invalid path'}
        if not full.is_file():
            return {'deleted': False, 'error': 'File not found'}
        # To the Recycle Bin, with the song's lyrics file. Deleting used to be
        # final, and the lyrics file was left behind on its own: a song
        # removed by mistake was gone for good, while a stray .lrc beside
        # nothing stayed in the folder for ever.
        doomed = [full]
        lyrics = full.with_suffix('.lrc')
        if lyrics.is_file():
            doomed.append(lyrics)
        if not osenv.trash(doomed):
            try:
                for path in doomed:
                    path.unlink(missing_ok=True)
            except Exception as exc:
                return {'deleted': False, 'error': str(exc)}
        # A repair of this track still to come, or under way, must not put it
        # back: it was deleted on purpose.
        try:
            from dannify import repair as _repair

            _repair.jobs.forget(full.relative_to(base).as_posix())
        except Exception:
            logger.opt(exception=True).debug('could not drop a repair for {}', file)
        return {'deleted': True}

    @app.get('/cover')
    def get_cover(file: str):
        # Resolve and confine to the LIVE download_dir.
        base = _live_download_dir().resolve()
        try:
            full = (base / file).resolve()
            full.relative_to(base)
        except (ValueError, RuntimeError):
            raise HTTPException(status_code=400, detail='Invalid path')
        if not full.is_file():
            raise HTTPException(status_code=404, detail='File not found')

        data, mime = _extract_cover(full)
        if data is None:
            raise HTTPException(status_code=404, detail='No embedded cover')
        return Response(
            content=data,
            media_type=mime or 'image/jpeg',
            headers={
                # Cache by mtime: clients fetch once per file revision.
                'Cache-Control': 'public, max-age=86400',
                'ETag': f'"{int(full.stat().st_mtime)}"',
            },
        )

    # The /downloads static mount needs to follow the live download_dir
    # too. StaticFiles caches the directory at construction time, so we
    # wrap it with a small Starlette app that re-resolves on every
    # request: same trick, applied to the static-file path.
    from starlette.responses import FileResponse as _FileResponse
    from starlette.types import Receive, Scope, Send

    try:
        from starlette._utils import get_route_path as _route_path
    except ImportError:  # older Starlette rewrote scope['path'] itself
        def _route_path(scope):
            return scope['path']

    async def _send_sealed(target, request, scope, receive, send) -> None:
        """Stream a sealed file back as ordinary audio.

        The browser thinks it is talking to a plain file: it gets a length, it
        gets Accept-Ranges, and a Range it asks for comes back as a 206 with
        the bytes it wanted. What it never gets is the file as it sits on disk.
        """

        from starlette.responses import Response as _Resp
        from starlette.responses import StreamingResponse
        from dannify import vault  # noqa: PLC0415

        MIME = {
            '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.flac': 'audio/flac',
            '.ogg': 'audio/ogg', '.opus': 'audio/ogg', '.wav': 'audio/wav',
            '.aac': 'audio/aac',
        }

        # A header we cannot read means the wrong key, and the old code took
        # `or {}` and carried on: it then streamed the payload through a
        # keystream that does not fit and answered with a flawless 206 full of
        # noise. The player got a response that looked perfect and sounded
        # like nothing, which is not a state anybody can debug.
        #
        # Read off the event loop: every seek is a new range request that
        # lands here, and doing the file work inline held up every other
        # request (another device's audio, the websocket) while it ran.
        def _look() -> tuple:
            found = vault.read_header(target)
            if found is None:
                return None, 0, None
            return found, vault.audio_size(target), target.stat()

        head, total, stat = await asyncio.to_thread(_look)
        if head is None:
            logger.error('cannot open {}', target.name)
            await _Resp(status_code=409)(scope, receive, send)
            return

        media = MIME.get(str(head.get('ext', '')).lower(), 'audio/mpeg')

        start, end = 0, total - 1
        status = 200
        raw = request.headers.get('range', '')

        async def unsatisfiable() -> None:
            await _Resp(
                status_code=416, headers={'Content-Range': f'bytes */{total}'},
            )(scope, receive, send)

        if raw.startswith('bytes='):
            spec = raw[6:].strip()
            if ',' in spec:
                # More than one range. Answering the first and describing it as
                # if it were the whole request is a lie the player cannot
                # detect, so decline and let it ask again.
                await unsatisfiable()
                return
            first, sep, last = spec.partition('-')
            if not sep:
                await unsatisfiable()
                return
            try:
                if first:
                    start = int(first)
                    end = int(last) if last else total - 1
                elif last:  # a suffix range: the final N bytes
                    start = max(0, total - int(last))
                else:
                    raise ValueError('empty range')
            except ValueError:
                await unsatisfiable()
                return
            end = min(end, total - 1)
            if start < 0 or start >= total or end < start:
                await unsatisfiable()
                return
            status = 206

        length = max(0, end - start + 1)
        # Never kept by the window. "no-cache" still let the browser store
        # the decrypted audio in its cache folder on disk, where it could be
        # copied out as a plain file: the one thing a sealed song must never
        # be. Seeking does not need it either: any range is decrypted on its
        # own (vault.open_range), as fast as reading it.
        headers = {
            'Accept-Ranges': 'bytes',
            'Content-Length': str(length),
            'Cache-Control': 'no-store',
            'Content-Type': media,
        }
        if status == 206:
            headers['Content-Range'] = f'bytes {start}-{end}/{total}'

        # A HEAD asks what is there, not for it. Streaming the answer meant
        # decrypting a whole track to throw it away.
        if request.method.upper() == 'HEAD':
            await _Resp(status_code=status, headers=headers)(scope, receive, send)
            return

        def body():
            yield from vault.open_range(target, start, length)

        await StreamingResponse(
            body(), status_code=status, media_type=media, headers=headers,
        )(scope, receive, send)

    async def _downloads_app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            return
        from starlette.requests import Request as _Req

        request = _Req(scope, receive)
        # The path is already decoded once, by the server. Decoding it a
        # second time turned a per cent sign in a filename into the start of
        # an escape and resolved to something else entirely, which for a track
        # called "100% Love" was a 404 nobody could explain. A mount no longer
        # rewrites scope['path'] either, it sets root_path, so the part after
        # the mount has to be taken rather than assumed.
        rel = _route_path(scope).lstrip('/')
        try:
            base = _live_download_dir().resolve()
            target = (base / rel).resolve()
            target.relative_to(base)
        except (ValueError, RuntimeError):
            from starlette.responses import PlainTextResponse

            await PlainTextResponse('Forbidden', status_code=403)(
                scope, receive, send,
            )
            return
        if not target.is_file():
            from starlette.responses import PlainTextResponse

            await PlainTextResponse('Not Found', status_code=404)(
                scope, receive, send,
            )
            return

        # Saved music is written as a sealed container, so it cannot be played
        # by anything but this app. Decrypt it on the way out, honouring Range
        # so dragging the seek bar still only reads the part it lands on.
        from dannify import vault  # noqa: PLC0415

        if vault.is_sealed(target):
            await _send_sealed(target, request, scope, receive, send)
            return
        await _FileResponse(str(target))(scope, receive, send)

    async def _opened_app(scope: Scope, receive: Receive, send: Send) -> None:
        """Serve a file the user opened from Explorer.

        Double-clicking a .dnf hands us a path that can be anywhere, and
        /downloads only serves what is inside the music folder, which is the
        guard that stops a crafted URL reading the rest of the disk. So a file
        opened deliberately gets a one-off ticket instead: open_external()
        checks it and puts it in a list, and nothing without a ticket is here.
        """

        if scope['type'] != 'http':
            return
        from starlette.requests import Request as _Req
        from starlette.responses import PlainTextResponse

        ticket = scope['path'].rsplit('/', 1)[-1]
        target = (getattr(api.state, 'opened', None) or {}).get(ticket)
        if target is None or not Path(target).is_file():
            await PlainTextResponse('Not Found', status_code=404)(scope, receive, send)
            return

        from dannify import vault  # noqa: PLC0415

        target = Path(target)
        if b'cover=1' in scope.get('query_string', b''):
            data, mime = await asyncio.to_thread(_extract_cover, target)
            if not data:
                await PlainTextResponse('Not Found', status_code=404)(
                    scope, receive, send,
                )
                return
            await Response(
                content=data,
                media_type=mime or 'image/jpeg',
                headers={'Cache-Control': 'no-store'},
            )(scope, receive, send)
            return

        request = _Req(scope, receive)
        if vault.is_sealed(target):
            await _send_sealed(target, request, scope, receive, send)
            return
        await _FileResponse(str(target))(scope, receive, send)

    app.mount('/opened', _opened_app, name='opened')
    app.mount('/downloads', _downloads_app, name='downloads')
