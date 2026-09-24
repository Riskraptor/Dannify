"""Dannify entry point.

Boots the FastAPI app that powers the web UI. The previous incarnation
relied on the Spotify Web API (via ``spotdl`` + ``spotipy``); since that
path now requires a Spotify Premium account, this version resolves
metadata directly from the public ``open.spotify.com/embed`` endpoints
and pulls the audio from YouTube via ``yt-dlp``.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from load_dotenv import load_dotenv
from loguru import logger
from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from uvicorn import Config, Server

from dannify import __version__, account, api
from dannify.downloader import Downloader


def providers_warm() -> None:
    """Build the YouTube Music client and fill the home feed, off the
    startup path.

    Home is the first screen the user sees and its feed is a ~4 s round trip
    to YouTube. Fetching it here means the UI's own request usually lands on
    the warm cache instead of waiting.
    """

    from dannify import explorer, innertube, providers

    # Cheapest first: one round trip for the session marker plus the TLS
    # handshake to YouTube. Doing it here is the difference between the
    # first play costing ~900 ms and costing ~350 ms.
    innertube.warm()
    providers._ytm()
    try:
        explorer.home(6)
    except Exception:
        logger.opt(exception=True).debug('home pre-fetch skipped')

load_dotenv()


import contextlib


def _make_lifespan(startup_fn):
    """Build an ASGI lifespan context that runs *startup_fn* on boot.

    Replaces the deprecated ``@app.on_event('startup')`` decorator (and its
    noisy DeprecationWarning) with the modern lifespan protocol.
    """

    @contextlib.asynccontextmanager
    async def _lifespan(_app):
        await startup_fn()
        yield

    return _lifespan


class _InterceptHandler(logging.Handler):
    """Redirect all stdlib logging records into loguru."""

    @staticmethod
    def emit(record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _setup_logging(level: str) -> None:
    logger.remove()

    def _patch(record: dict) -> None:
        """Attach a compact, friendly component name to every record."""

        name = record['name'] or ''
        if name.startswith('dannify.'):
            short = name.split('.', 1)[1]
        elif name.startswith('uvicorn'):
            short = 'http'
        elif name.startswith('websockets'):
            short = 'ws'
        elif name == '__main__':
            short = 'dannify'
        else:
            short = name.split('.')[-1]
        # Respect an explicit component already bound via logger.bind(...).
        if not record['extra'].get('component'):
            record['extra']['component'] = short[:12]

    logger.configure(patcher=_patch, extra={'component': ''})

    # Friendly level icons for at-a-glance scanning (set before adding sink).
    for lvl, icon in (
        ('TRACE', '·'),
        ('DEBUG', '•'),
        ('INFO', 'ℹ'),
        ('SUCCESS', '✓'),
        ('WARNING', '⚠'),
        ('ERROR', '✗'),
        ('CRITICAL', '‼'),
    ):
        try:
            logger.level(lvl, icon=icon)
        except Exception:
            pass

    # Console sink: only when a real console exists. Windowed desktop
    # builds (PyInstaller --noconsole) have ``sys.stderr = None``.
    if sys.stderr is not None:
        try:
            _colorize = bool(sys.stderr.isatty())
        except Exception:
            _colorize = False
        logger.add(
            sys.stderr,
            format=(
                '<dim>{time:HH:mm:ss}</dim> '
                '<level>{level.icon} {level: <7}</level> '
                '<magenta>{extra[component]: <12}</magenta> '
                '<level>{message}</level>'
            ),
            level=level.upper(),
            colorize=_colorize or None,
            backtrace=False,
            diagnose=False,
        )

    # File sink: used by the desktop build so users (and we) can debug
    # without a console. Rotates so it never grows unbounded. UTF-8 is
    # explicit because the icons in the log format (✓ ✗ ‼ ♪) crash a
    # cp1252 default sink on Windows.
    _log_file = os.getenv('DANNIFY_LOG_FILE')
    if _log_file:
        try:
            Path(_log_file).parent.mkdir(parents=True, exist_ok=True)
            logger.add(
                _log_file,
                format=(
                    '{time:YYYY-MM-DD HH:mm:ss} '
                    '{level.icon} {level: <7} '
                    '{extra[component]: <12} {message}'
                ),
                level=level.upper(),
                colorize=False,
                backtrace=False,
                diagnose=False,
                rotation='5 MB',
                retention=3,
                enqueue=True,
                encoding='utf-8',
            )
        except Exception:
            pass

    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    # Route uvicorn/fastapi logs through loguru; silence uvicorn's noisy
    # per-request access lines (we emit our own concise request logs).
    for _name in ('uvicorn', 'uvicorn.error', 'fastapi'):
        _log = logging.getLogger(_name)
        _log.handlers = [_InterceptHandler()]
        _log.propagate = False
    # Access logs: handled by our own concise middleware; silence the raw
    # uvicorn access logger to avoid duplicate, noisy per-asset lines.
    _access = logging.getLogger('uvicorn.access')
    _access.handlers = []
    _access.propagate = False
    _access.disabled = True


# Resolve project-relative defaults so the app works out of the box on
# Windows (and any OS) without requiring Docker volume mounts.
#
# Frozen (PyInstaller desktop) builds relocate everything:
#   * bundled read-only resources (frontend dist, ffmpeg) live in
#     ``sys._MEIPASS`` (the unpacked bundle dir),
#   * user data (settings, caches, DBs) lives in ``%LOCALAPPDATA%/Dannify``,
#   * downloads default to ``~/Music/Dannify``.
_FROZEN = bool(getattr(sys, 'frozen', False))
_BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

if _FROZEN:
    _DEFAULT_DOWNLOADS = Path.home() / 'Music' / 'Dannify'
    _DEFAULT_DATA = (
        Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
        / 'Dannify'
    )
    _DEFAULT_WEB_GUI = _BUNDLE_DIR / 'frontend' / 'dist'
else:
    _DEFAULT_DOWNLOADS = _PROJECT_ROOT / 'downloads'
    _DEFAULT_DATA = _PROJECT_ROOT / 'data'
    _DEFAULT_WEB_GUI = (_PROJECT_ROOT / 'frontend' / 'dist').resolve()

DOWNLOAD_DIR = Path(os.getenv('DOWNLOAD_DIR', str(_DEFAULT_DOWNLOADS)))
# DANNIFY_DATA_DIR is what the desktop shell uses to put a second copy
# somewhere of its own. It has to move the backend's data too, or a "separate"
# copy quietly reads the real settings, finds the real music folder, and acts
# on it. That is not a hypothetical: it is how a test run ended up converting
# a real library instead of its own throwaway one.
DATABASE_DIR = Path(
    os.getenv('DATABASE_DIR') or os.getenv('DANNIFY_DATA_DIR') or str(_DEFAULT_DATA)
)
WEB_GUI_LOCATION = os.getenv('WEB_GUI_LOCATION', str(_DEFAULT_WEB_GUI))

# Frozen builds ship their own ffmpeg: make it win the PATH race so
# streaming and yt-dlp post-processing work on machines without one.
# Source checkouts use the copy in packaging/ffmpeg (which also has ffprobe;
# the shipped bundle leaves it out: nothing we do needs it, and it is 97 MB).
_ffdir = _BUNDLE_DIR / 'media' if _FROZEN else _PROJECT_ROOT / 'packaging' / 'media'
if _ffdir.is_dir():
    os.environ['PATH'] = str(_ffdir) + os.pathsep + os.environ.get('PATH', '')
DEFAULT_HOST = os.getenv('HOST', '0.0.0.0')


def _local_ip() -> str:
    """Best-effort detection of this machine's LAN IP for friendly logging."""

    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't actually send packets; just picks the outbound interface.
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'
    finally:
        s.close()


# Prefer DANNIFY_PORT, fall back to the legacy DOWNTIFY_PORT, then PORT.
DEFAULT_PORT = int(
    os.getenv('DANNIFY_PORT')
    or os.getenv('DOWNTIFY_PORT')
    or os.getenv('PORT', '8000')
)


class SPAStaticFiles(StaticFiles):
    """Serve ``index.html`` for unknown paths so SPA routing works."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except Exception:
            return await super().get_response('index.html', scope)


class PackedUI:
    """Serve the interface out of the shipped resource file.

    A folder of readable HTML, JavaScript and CSS in the install directory made
    the app look like a web page someone had copied into Program Files, so the
    built interface ships as one packed file instead (see dannify/respack.py).
    This is the same thing StaticFiles did, reading from that file: a path, a
    content type, an ETag, and index.html for anything the router owns.
    """

    def __init__(self, pack) -> None:
        self._pack = pack
        self._etag = f'"{pack.stamp}"'

    def _member(self, path: str) -> str:
        rel = path.lstrip('/')
        if not rel or rel.endswith('/'):
            rel += 'index.html'
        name = f'ui/{rel}'
        # Anything else is a route the front end handles itself.
        return name if name in self._pack else 'ui/index.html'

    async def __call__(self, scope, receive, send) -> None:
        from starlette.responses import PlainTextResponse, Response

        if scope['type'] != 'http':
            return
        if scope['method'] not in ('GET', 'HEAD'):
            await PlainTextResponse('Method Not Allowed', status_code=405)(
                scope, receive, send,
            )
            return

        name = self._member(scope['path'])
        body = self._pack.read(name)
        media = mimetypes.guess_type(name)[0] or 'application/octet-stream'

        # Vite puts a content hash in every asset filename, so those can be
        # cached for good. index.html is the one file whose name stays the
        # same across builds, and it names the others.
        if name == 'ui/index.html':
            cache = 'no-cache'
        else:
            cache = 'public, max-age=31536000, immutable'

        headers = {'Cache-Control': cache, 'ETag': self._etag}
        asked = b''
        for key, value in scope.get('headers', ()):
            if key.lower() == b'if-none-match':
                asked = value
                break
        if self._etag.encode() in (t.strip() for t in asked.split(b',')):
            await Response(status_code=304, headers=headers)(scope, receive, send)
            return

        await Response(
            content=b'' if scope['method'] == 'HEAD' else body,
            media_type=media,
            headers={**headers, 'Content-Length': str(len(body))},
        )(scope, receive, send)


def _fix_mime_types() -> None:
    mimetypes.add_type('application/javascript', '.js')
    mimetypes.add_type('application/javascript', '.mjs')
    mimetypes.add_type('text/css', '.css')


def _extract_cover(path: Path) -> tuple[bytes | None, str | None]:
    """Return ``(image_bytes, mime)`` for the embedded cover, or ``(None, None)``.

    Reads tags lazily: mutagen format detection handles MP3/FLAC/M4A/OGG/Opus
    without us needing to dispatch on extension.
    """

    # A sealed container carries its artwork in its own header; mutagen would
    # only see noise.
    if path.suffix.lower() == '.dnf':
        from dannify import vault

        found = vault.cover(path)
        return found if found else (None, None)

    try:
        # ID3 (mp3, sometimes wav/aac)
        try:
            tag = ID3(str(path))
            for frame in tag.getall('APIC'):
                if frame.data:
                    return frame.data, frame.mime or 'image/jpeg'
        except Exception:
            pass

        # FLAC
        if path.suffix.lower() == '.flac':
            try:
                f = FLAC(str(path))
                if f.pictures:
                    pic = f.pictures[0]
                    return pic.data, pic.mime or 'image/jpeg'
            except Exception:
                pass

        # MP4 / M4A
        if path.suffix.lower() in {'.m4a', '.mp4', '.aac'}:
            try:
                m = MP4(str(path))
                covr = m.tags.get('covr') if m.tags else None
                if covr:
                    pic = covr[0]
                    fmt = getattr(pic, 'imageformat', None)
                    mime = (
                        'image/png'
                        if fmt == 14  # MP4Cover.FORMAT_PNG
                        else 'image/jpeg'
                    )
                    return bytes(pic), mime
            except Exception:
                pass

        # Ogg Vorbis / Opus - METADATA_BLOCK_PICTURE base64
        if path.suffix.lower() in {'.ogg', '.opus'}:
            try:
                ogg = (
                    OggOpus(str(path))
                    if path.suffix.lower() == '.opus'
                    else OggVorbis(str(path))
                )
                blocks = ogg.get('metadata_block_picture') or []
                for raw in blocks:
                    try:
                        pic = Picture(base64.b64decode(raw))
                        if pic.data:
                            return pic.data, pic.mime or 'image/jpeg'
                    except Exception:
                        continue
            except Exception:
                pass

        # Generic fallback: let mutagen pick the right parser
        try:
            f = MutagenFile(str(path))
            if f is not None and getattr(f, 'pictures', None):
                pic = f.pictures[0]
                return pic.data, pic.mime or 'image/jpeg'
        except Exception:
            pass
    except Exception:
        return None, None
    return None, None


def build_app() -> FastAPI:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    # A shipped build serves no interactive API docs: /docs and
    # /openapi.json would hand anyone a complete map of the backend.
    app = FastAPI(
        title='Dannify',
        version=__version__,
        docs_url=None if _FROZEN else '/docs',
        redoc_url=None,
        openapi_url=None if _FROZEN else '/openapi.json',
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    # Search and home payloads run to tens of KB of JSON. Compressing them
    # costs a millisecond and pays for itself on every phone on the LAN.
    #
    # Audio must be left alone, and the size floor does not do that. The floor
    # only applies to a response that arrives in one piece; a streamed one goes
    # down the other branch and is compressed whatever its size, which drops
    # Content-Length and switches to chunked. A track then has no length for
    # the player to read, so the bar sits at 0:00 forever, and a range reply is
    # worse than that: Content-Range still describes the bytes that were asked
    # for while the body is a gzip stream of them. A thousand-byte range came
    # back as 504 bytes with a header promising 1024.
    from fastapi.middleware.gzip import GZipMiddleware

    _NEVER_GZIP = ('/downloads/', '/opened/', '/cover', '/api/stream')

    class _GzipTextOnly:
        """Compression for the JSON and the interface, never for media."""

        def __init__(self, inner):
            self.inner = inner
            self.gzip = GZipMiddleware(inner, minimum_size=2048, compresslevel=5)

        async def __call__(self, scope, receive, send):
            if scope['type'] == 'http' and not scope['path'].startswith(_NEVER_GZIP):
                await self.gzip(scope, receive, send)
                return
            await self.inner(scope, receive, send)

    app.add_middleware(_GzipTextOnly)

    # --- Private by default -------------------------------------------------
    # Dannify is a desktop app that happens to talk to itself over HTTP. The
    # window arrives carrying a one-shot key and trades it for a cookie;
    # everything else (another browser, another program, a curious phone)
    # gets a flat 404. Without this the whole library and API answer anyone
    # who opens localhost.
    # --- One ASGI pass: private by default, plus request logging ----------
    #
    # This used to be two @app.middleware('http') functions. Starlette wraps
    # those in a task group and a memory stream, which streaming cannot
    # survive: an <audio> element aborts and re-issues range requests
    # constantly, and each abort surfaced as "RuntimeError: No response
    # returned" and killed playback. Pure ASGI has no wrapper, so aborts are
    # just aborts, and every request gets a little faster too.
    #
    # The gate itself: the app window arrives carrying a one-shot key and
    # trades it for a cookie. Anything else, another browser, another
    # program, a curious phone, is answered as if nothing is listening.
    import time as _time

    _COOKIE = 'dnf_session'
    # Nothing is reachable without the session key, including the readiness
    # probe: an open endpoint is an open door, and it told anyone who knocked
    # what was behind it. The shell sends the key like any other caller.
    _OPEN_PATHS: set[str] = set()
    _QUIET_PREFIXES = ('/assets/', '/cover', '/favicon', '/downloads/')
    _QUIET_EXACT = {'/list', '/api/queue', '/api/version', '/api/settings'}

    class _Gateway:
        def __init__(self, inner):
            self.inner = inner

        @staticmethod
        def _presented(scope) -> tuple[str, bool]:
            """The key this request carries, and whether it came in the URL."""
            from urllib.parse import parse_qs

            query = parse_qs(scope.get('query_string', b'').decode('latin-1'))
            in_url = (query.get('k') or [''])[0]
            if in_url:
                return in_url, True
            for name, value in scope.get('headers') or ():
                if name == b'x-dannify-key':
                    return value.decode('latin-1'), False
                if name == b'cookie':
                    for part in value.decode('latin-1').split(';'):
                        key, _, val = part.strip().partition('=')
                        if key == _COOKIE:
                            return val, False
            return '', False

        async def __call__(self, scope, receive, send):
            if scope['type'] not in ('http', 'websocket'):
                await self.inner(scope, receive, send)
                return

            token = api.state.auth_token
            path = scope.get('path', '')
            if token:
                given, from_url = self._presented(scope)
                if given != token and path not in _OPEN_PATHS:
                    await _refuse(scope, send)
                    return
            else:
                from_url = False  # dev server: no shell, no key, no gate

            if scope['type'] == 'websocket':
                await self.inner(scope, receive, send)
                return

            started = _time.perf_counter()
            quiet = path.startswith(_QUIET_PREFIXES) or path in _QUIET_EXACT

            async def send_wrapper(message):
                if message['type'] == 'http.response.start':
                    if from_url:
                        # Hand the window a cookie so every later asset,
                        # audio range request and websocket carries the key.
                        message.setdefault('headers', [])
                        message['headers'].append((
                            b'set-cookie',
                            f'{_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax'.encode(),
                        ))
                    if not quiet:
                        _log_response(scope, message['status'], started)
                await send(message)

            await self.inner(scope, receive, send_wrapper)

    async def _refuse(scope, send) -> None:
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        await send({
            'type': 'http.response.start',
            'status': 404,
            'headers': [(b'content-length', b'0')],
        })
        await send({'type': 'http.response.body', 'body': b''})

    def _log_response(scope, status: int, started: float) -> None:
        # Time to first byte, which for a stream is the number that matters.
        ms = (_time.perf_counter() - started) * 1000
        raw = scope.get('query_string', b'').decode('latin-1')
        # Never echo the session key into the log file.
        q = ''
        if raw:
            q = '?' + '&'.join(p for p in raw.split('&') if not p.startswith('k='))
        tag = '✗' if status >= 500 else ('⚠' if status >= 400 else '→')
        lvl = 'ERROR' if status >= 500 else ('WARNING' if status >= 400 else 'INFO')
        logger.bind(component='http').log(
            lvl,
            '{} {} {}{}  {}  {:.0f}ms',
            tag,
            scope.get('method', '?'),
            scope.get('path', ''),
            q[:80],
            status,
            ms,
        )

    app.add_middleware(_Gateway)

    settings_path = DATABASE_DIR / 'settings.json'
    api.state.settings_path = settings_path
    api.state.settings = api._load_settings(settings_path)

    # --- Apply user-saved download_dir (overrides env default) ---
    # The very first run leaves this blank; subsequent runs may store an
    # absolute path the user picked in Settings. If the saved path is
    # missing or unwritable, gracefully fall back to the default.
    download_dir = DOWNLOAD_DIR
    saved_dir = str(api.state.settings.get('download_dir') or '').strip()
    if saved_dir:
        try:
            candidate = Path(saved_dir).expanduser()
            candidate.mkdir(parents=True, exist_ok=True)
            # Probe writability so we don't hand a broken folder to the UI.
            probe = candidate / '.dannify-write-probe'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink(missing_ok=True)
            download_dir = candidate.resolve()
            api.state.settings['download_dir'] = str(download_dir)
        except Exception:
            logger.warning(
                'Saved download_dir {!r} is not usable; reverting to {}',
                saved_dir, download_dir,
            )
            api.state.settings['download_dir'] = str(download_dir)
    else:
        # First-run: record the default so the UI shows something useful.
        api.state.settings['download_dir'] = str(download_dir)

    api.state.version = __version__
    api.state.download_dir = download_dir
    # Crowd-sourced lyric timing offsets, persisted under the data dir.
    from dannify import lyrics_offsets
    lyrics_offsets.init(DATABASE_DIR)
    # Persistent lyrics cache so lrclib's latency is paid once ever.
    from dannify import lyrics as _lyrics_mod
    _lyrics_mod.init_cache(DATABASE_DIR)
    # Central lyrics folder + on-disk (artist|title) index.
    from dannify import lyrics_index as _lyrics_index
    _lyrics_index.init(download_dir)
    # Persistent stream-URL cache so the second launch is instantly warm
    # for everything the user played recently.
    from dannify import streaming as _streaming_mod
    _streaming_mod.init_persistent_cache(DATABASE_DIR)
    # Restore the YouTube Music sign-in (personalized home, likes, and a
    # session yt-dlp can use so YouTube stops asking for a bot check).
    account.init(DATABASE_DIR)
    # Where yt-dlp caches the solved YouTube player (see dannify/jsruntime).
    from dannify import jsruntime as _jsruntime

    _jsruntime.init(DATABASE_DIR)
    # The direct-to-YouTube resolver: client identities and the cached
    # session marker live beside the rest of the app data.
    from dannify import innertube as _innertube

    _innertube.init(DATABASE_DIR)
    api.state.data_dir = DATABASE_DIR
    # Donations and the GitHub updater are config-only: see
    # dannify/support.py and dannify/updates.py.
    from dannify import support as _support
    from dannify import updates as _updates

    _support.init(DATABASE_DIR)
    # The key saved music is encrypted with. Made once, kept for good; the
    # uninstaller is told to leave it alone (see packaging/dannify.iss).
    from dannify import vault as _vault
    _vault.init(DATABASE_DIR)
    _updates.init(DATABASE_DIR)
    api.state.downloader = Downloader(
        download_dir,
        audio_format=api.state.settings['format'],
        audio_bitrate=api.state.settings.get('bitrate', '320'),
        output_template=api.state.settings['output'].replace(
            '.{output-ext}', ''
        ),
        lyrics_providers=api._effective_lyrics_providers(api.state.settings),
        organize_by_artist=bool(
            api.state.settings.get('organize_by_artist', False)
        ),
        lyrics_storage=str(
            api.state.settings.get('lyrics_storage', 'sidecar')
        ),
    )
    app.include_router(api.router)

    async def _run_startup() -> None:
        loop = asyncio.get_running_loop()
        api.state.loop = loop

        # --- Concurrency: a generous thread pool so blocking I/O (yt-dlp,
        # ytmusicapi, lyrics HTTP, ffmpeg, tag reads) never serializes. This
        # lets search + playback + downloads all run truly in parallel. ---
        import concurrent.futures as _cf

        cpu = os.cpu_count() or 4
        # The blocking work here is I/O (network, subprocess, disk), which
        # releases the GIL, so a handful of threads per core genuinely run in
        # parallel. ThreadPoolExecutor creates threads lazily, but each one
        # that is created reserves ~1 MB of stack, and a desktop app serving
        # one person never needs hundreds. This ceiling still covers a phone
        # or two on the LAN plus a batch download.
        max_workers = min(48, max(16, cpu * 4))
        executor = _cf.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix='dannify'
        )
        loop.set_default_executor(executor)
        api.state.executor = executor

        # anyio's own cap (FastAPI sync routes and ``asyncio.to_thread``)
        # has to match the executor, or it either queues work the pool could
        # run or admits work the pool cannot.
        try:
            import anyio

            limiter = anyio.to_thread.current_default_thread_limiter()
            limiter.total_tokens = max_workers
        except Exception:
            logger.opt(exception=True).debug('Could not size the anyio limiter')

        logger.info('Worker pool ready ({} threads)', max_workers)

        api.state.download_semaphore = asyncio.Semaphore(
            max(1, int(api.state.settings.get('max_parallel_downloads', 3)))
        )
        logger.log('SUCCESS', 'Dannify is ready: happy listening ♪')

        # Warm the YouTube Music session in the background, ~2s after the
        # window is already interactive. The first search/play then skips
        # the client bootstrap instead of paying for it on the click.
        async def _warm_up() -> None:
            await asyncio.sleep(2.0)
            try:
                await asyncio.to_thread(providers_warm)
            except Exception:
                logger.opt(exception=True).debug('warm-up skipped')

        asyncio.create_task(_warm_up())

        # Watch the music folder for changes made outside the app. Deleting an
        # album in Explorer used to leave it listed here until the next
        # restart, with play buttons that led nowhere.
        from dannify import diskwatch

        def _library_base():
            downloader = api.state.downloader
            return downloader.download_dir if downloader is not None else None

        def _announce() -> None:
            # The watcher runs on its own thread; the broadcast has to go back
            # to the loop that owns the websockets.
            asyncio.run_coroutine_threadsafe(
                api.state.connections.broadcast({'type': 'library_changed'}),
                loop,
            )

        diskwatch.start(_library_base, _announce)

        # Music saved before containers existed gets sealed, and anything
        # sealed by the first version gets its tags back (see vault.repair).
        # On a thread: a large library is minutes of work and nobody should
        # wait at a splash screen for it.
        #
        # Both hand back an on_change, and both must. They rename every file
        # in the music folder while the window is already showing a list built
        # from the old names. Without this the covers go grey and every play
        # says the file was moved or deleted, until the app is restarted. The
        # folder watcher would find it eventually, but it polls on a backoff
        # and this is a change we are making ourselves and know about.
        from dannify import library as _library

        def _library_moved(forced: bool = False) -> None:
            _library.invalidate_cache()
            _announce()

        def _convert() -> None:
            base = _library_base() or download_dir
            try:
                _vault.migrate(base, on_change=_library_moved)
            except Exception:
                logger.opt(exception=True).warning('sealing pass failed')
            try:
                _vault.repair(base, on_change=_library_moved)
            except Exception:
                logger.opt(exception=True).warning('update pass failed')

        if _vault.ready():
            import threading as _th

            _th.Thread(target=_convert, name='seal-existing', daemon=True).start()

    app.router.lifespan_context = _make_lifespan(_run_startup)

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
        try:
            full.unlink()
        except Exception as exc:
            return {'deleted': False, 'error': str(exc)}
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
        head = vault.read_header(target)
        if head is None:
            logger.error(
                'cannot read {}: the wrong key for it, or it is damaged',
                target.name,
            )
            await _Resp(status_code=409)(scope, receive, send)
            return

        media = MIME.get(str(head.get('ext', '')).lower(), 'audio/mpeg')
        total = vault.audio_size(target)
        stat = target.stat()

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
        # Both parts are known without decrypting anything, and both change
        # whenever the file does. Without them every backward seek was a fresh
        # read and a fresh decrypt of everything before the point seeked to.
        headers = {
            'Accept-Ranges': 'bytes',
            'Content-Length': str(length),
            'Cache-Control': 'private, no-cache',
            'ETag': f'"{int(stat.st_mtime)}-{total}"',
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
            data, mime = _extract_cover(target)
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

    # A shipped build serves the interface from the packed resource file; a
    # source checkout has no pack and serves frontend/dist, so rebuilding the
    # front end shows up on a refresh. WEB_GUI_LOCATION set by hand wins over
    # both: that is what it is for.
    from dannify import respack  # noqa: PLC0415

    packed = None
    if not os.getenv('WEB_GUI_LOCATION'):
        packed = respack.bundle(_BUNDLE_DIR if _FROZEN else None)
    if packed is not None and 'ui/index.html' in packed:
        app.mount('/', PackedUI(packed), name='static')
    else:
        if _FROZEN and not os.getenv('WEB_GUI_LOCATION'):
            # The pack is part of the install. Missing or unreadable means the
            # install is damaged, and saying so beats a window that comes up
            # blank with nothing in the log to explain it.
            raise RuntimeError(
                f'the interface file is missing or damaged: '
                f'{_BUNDLE_DIR / "dannify.res"}',
            )
        app.mount(
            '/',
            SPAStaticFiles(directory=WEB_GUI_LOCATION, html=True),
            name='static',
        )
    return app


def open_external(path: str | Path) -> dict[str, Any] | None:
    """Work out how to play a file the shell handed us, and tell the window.

    This is what a double-clicked .dnf in Explorer ends up calling. A track
    already in the music folder plays by its normal URL, so it behaves exactly
    like clicking it in the library. Anything else gets a one-off ticket, and
    the file is read but never moved or imported: opening a file is not the
    same as asking for it to be added.
    """

    import secrets

    from dannify import vault

    try:
        target = Path(path).expanduser().resolve()
    except Exception:
        return None
    if not target.is_file():
        logger.info('asked to open a file that is not there: {}', path)
        return None

    sealed = vault.is_sealed(target)
    if sealed and not vault.read_header(target):
        # Sealed, but not by this installation. Saying so is the only useful
        # thing here: the alternative is a player that sits at 0:00 forever.
        logger.warning('cannot open {}: sealed with a different key', target)
        return {'error': 'other_key', 'name': target.name}
    if not sealed and target.suffix.lower() not in {
        '.mp3', '.m4a', '.flac', '.ogg', '.wav', '.aac', '.opus',
    }:
        return None

    head = (vault.read_header(target) or {}) if sealed else {}
    stem = target.stem
    guess_artist, _, guess_title = stem.partition(' - ')

    url = None
    rel = None
    try:
        # The live folder, not the boot-time one: Settings can move it.
        base = Path(api.state.download_dir or DOWNLOAD_DIR).resolve()
        rel = target.relative_to(base).as_posix()
        url = '/downloads/' + quote(rel)
    except (ValueError, RuntimeError, OSError):
        rel = None
    if url is None:
        tickets = getattr(api.state, 'opened', None)
        if tickets is None:
            tickets = api.state.opened = {}
        ticket = secrets.token_urlsafe(16)
        tickets[ticket] = target
        # A window's worth of tickets is plenty; this is not a library.
        for old in list(tickets)[:-32]:
            tickets.pop(old, None)
        url = '/opened/' + ticket

    track = {
        'type': 'local',
        'url': url,
        'file': rel,
        'title': str(head.get('title') or (guess_title or stem)),
        'artist': str(head.get('artist') or (guess_artist if guess_title else '')),
        'album': str(head.get('album') or ''),
        'duration': int(head.get('duration') or 0),
        'cover': ('/cover?file=' + quote(rel)) if rel else (url + '?cover=1'),
    }
    if api.state.loop is not None:
        try:
            asyncio.run_coroutine_threadsafe(
                api.state.connections.broadcast({'type': 'play_file', 'track': track}),
                api.state.loop,
            )
        except Exception:
            logger.opt(exception=True).debug('could not hand the file to the window')
    return track


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='dannify')
    # The legacy entrypoint passed ``web`` as the subcommand plus a few
    # spotdl-only flags. We accept and ignore the unsupported ones so
    # existing Docker images keep starting cleanly.
    parser.add_argument('mode', nargs='?', default='web')
    parser.add_argument('--host', default=DEFAULT_HOST)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--log-level', default='info')
    parser.add_argument('--keep-alive', action='store_true')
    parser.add_argument('--keep-sessions', action='store_true')
    parser.add_argument('--web-use-output-dir', action='store_true')
    args, _ = parser.parse_known_args()
    return args


def main() -> None:
    args = _parse_args()
    _setup_logging(args.log_level)

    _fix_mime_types()
    app = build_app()

    # On Python >= 3.10 new_event_loop() already returns a ProactorEventLoop
    # on Windows; the explicit ProactorEventLoop() call was deprecated in
    # 3.12 and removed in 3.14.
    loop = asyncio.new_event_loop()

    # Silence the benign Windows ProactorEventLoop noise that fires when a
    # client closes a streaming/range connection early (seek, skip, tab close).
    # These ConnectionReset/"shutdown" errors are harmless and don't affect
    # any response: we only drop them from the loop's default handler.
    _BENIGN_MSGS = (
        '_call_connection_lost',
        'Error on transport creation',
        'ssl.SSLError',
    )
    _BENIGN_EXC = (
        ConnectionResetError,
        ConnectionAbortedError,
        BrokenPipeError,
    )

    def _quiet_exception_handler(loop, context):  # noqa: ANN001
        exc = context.get('exception')
        msg = context.get('message', '')
        if isinstance(exc, _BENIGN_EXC) or any(
            frag in msg for frag in _BENIGN_MSGS
        ):
            return  # swallow harmless client-disconnect noise
        # Anything else: log it concisely.
        logger.opt(exception=exc).warning(
            'asyncio: {}', msg or (exc.__class__.__name__ if exc else 'error')
        )

    loop.set_exception_handler(_quiet_exception_handler)

    config = Config(
        app=app,
        host=args.host,
        port=args.port,
        loop=loop,  # type: ignore[arg-type]
        log_level=args.log_level.lower(),
        log_config=None,
        workers=1,
    )
    server = Server(config)

    logger.info('Starting Dannify {}', __version__)
    if args.host in ('0.0.0.0', '::'):
        lan = _local_ip()
        logger.log(
            'SUCCESS',
            'Open on this device:  http://localhost:{}',
            args.port,
        )
        logger.log(
            'SUCCESS',
            'Open on your network: http://{}:{}  (phone, TV, other PCs)',
            lan,
            args.port,
        )
    else:
        logger.info(
            'Listening on http://{}:{}', args.host, args.port
        )
    logger.info('Application log level (Loguru): {}', args.log_level.upper())

    try:
        loop.run_until_complete(server.serve())
    except (KeyboardInterrupt, asyncio.CancelledError):
        # uvicorn re-raises the captured SIGINT after a clean shutdown; we
        # already logged "Application shutdown complete", so just exit quietly.
        pass
    finally:
        try:
            # Cancel any stragglers and close the loop so there's no noisy
            # "Task was destroyed but it is pending" output on exit.
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        finally:
            loop.close()
    logger.info('Dannify stopped. Goodbye ♪')


if __name__ == '__main__':
    main()
