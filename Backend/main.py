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
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI
from load_dotenv import load_dotenv
from loguru import logger
from uvicorn import Config, Server

from dannify import __version__, account, api, gateway, osenv, served
from dannify.logsetup import _setup_logging
from dannify.webui import PackedUI, SPAStaticFiles, _fix_mime_types
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


# Resolve project-relative defaults so the app works out of the box on
# Windows (and any OS) without requiring Docker volume mounts.
#
# Frozen (PyInstaller desktop) builds relocate everything:
#   * bundled read-only resources (frontend dist, ffmpeg) live in
#     ``sys._MEIPASS`` (the unpacked bundle dir),
#   * user data (settings, caches, DBs) lives in the platform's per-user
#     folder (see osenv.default_data_dir),
#   * downloads default to ``~/Music/Dannify``.
# The Linux package runs from source but is installed all the same, so it
# takes the installed defaults too (osenv.packaged).
_FROZEN = bool(getattr(sys, 'frozen', False))
_BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

if osenv.packaged():
    _DEFAULT_DOWNLOADS = osenv.default_music_dir()
    _DEFAULT_DATA = osenv.default_data_dir()
    _DEFAULT_WEB_GUI = (
        _BUNDLE_DIR / 'frontend' / 'dist' if _FROZEN
        else (_PROJECT_ROOT / 'frontend' / 'dist').resolve()
    )
else:
    _DEFAULT_DOWNLOADS = _PROJECT_ROOT / 'downloads'
    _DEFAULT_DATA = _PROJECT_ROOT / 'data'
    _DEFAULT_WEB_GUI = (_PROJECT_ROOT / 'frontend' / 'dist').resolve()

# DANNIFY_DATA_DIR is what the desktop shell uses to put a second copy
# somewhere of its own. It has to move the backend's data too, or a "separate"
# copy quietly reads the real settings, finds the real music folder, and acts
# on it. That is not a hypothetical: it is how a test run ended up converting
# a real library instead of its own throwaway one.
_MOVED = os.getenv('DATABASE_DIR') or os.getenv('DANNIFY_DATA_DIR')
DATABASE_DIR = Path(_MOVED or str(_DEFAULT_DATA))

# And it has to move the music too. Redirecting only the data folder was half
# a fix: a second copy started that way found no settings.json in its fresh
# folder, fell back to the default music folder, which is the real one, made
# itself a brand new key and began converting somebody else's library with it.
# That is exactly what happened, twice, and the tracks sealed with the key
# that was thrown away afterwards could not be opened by anything ever again.
# A copy told to keep its data somewhere else keeps its music there too,
# unless it is told otherwise outright.
DOWNLOAD_DIR = Path(
    os.getenv('DOWNLOAD_DIR')
    or (str(Path(_MOVED) / 'Music') if _MOVED else str(_DEFAULT_DOWNLOADS))
)
WEB_GUI_LOCATION = os.getenv('WEB_GUI_LOCATION', str(_DEFAULT_WEB_GUI))

# Frozen builds ship their own ffmpeg: make it win the PATH race so
# streaming and yt-dlp post-processing work on machines without one.
# Source checkouts use the copy in packaging/ffmpeg (which also has ffprobe;
# the shipped bundle leaves it out: nothing we do needs it, and it is 97 MB).
_ffdir = _BUNDLE_DIR / 'media' if _FROZEN else _PROJECT_ROOT / 'packaging' / 'media'
# The checkout's packaging/media holds the Windows build only: anywhere else
# the system's own ffmpeg is the one to use.
if _ffdir.is_dir() and (_FROZEN or osenv.IS_WINDOWS):
    os.environ['PATH'] = str(_ffdir) + os.pathsep + os.environ.get('PATH', '')
# This machine only, unless asked. It used to be every network the PC was
# on, with no key, so anyone on the same Wi-Fi could read the library and
# change the settings.
DEFAULT_HOST = os.getenv('HOST', '127.0.0.1')


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


def build_app() -> FastAPI:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    # The default music folder may not be the one in use (a folder chosen in
    # Settings is picked up below), and a Music folder redirected somewhere
    # that is not reachable yet used to stop the whole app from starting.
    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.warning('The default music folder cannot be made right now: {}', DOWNLOAD_DIR)

    # A shipped build serves no interactive API docs: /docs and
    # /openapi.json would hand anyone a complete map of the backend.
    app = FastAPI(
        title='Dannify',
        version=__version__,
        docs_url=None if _FROZEN else '/docs',
        redoc_url=None,
        openapi_url=None if _FROZEN else '/openapi.json',
    )
    # No CORS. The interface is served from this same origin, and the
    # development server proxies to it, so nothing legitimate ever makes a
    # cross-origin call. It used to answer every origin, with credentials.
    gateway.install(app)

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
    from dannify import artist_links as _artist_links

    _artist_links.init(DATABASE_DIR)
    from dannify import playlists as _playlists

    _playlists.init(DATABASE_DIR)
    from dannify import bench as _bench

    # Songs are put together in here before they are sealed (see bench.py).
    _bench.set_root(DATABASE_DIR / 'work')
    # Donations and the GitHub updater are config-only: see
    # dannify/support.py and dannify/updates.py.
    from dannify import support as _support
    from dannify import updates as _updates

    _support.init(DATABASE_DIR)
    # What saved music is sealed with. Made once, kept for good; the
    # uninstaller leaves it alone (see installer/Core/Engine.cs). Then
    # joined to the music folder, which keeps its own copy, so the two can
    # never again drift apart and leave the songs unopenable (see vault.attach).
    from dannify import vault as _vault
    _vault.init(DATABASE_DIR)
    try:
        _vault.attach(download_dir)
    except Exception:
        logger.opt(exception=True).warning('could not join the music folder')
    _updates.init(DATABASE_DIR)
    # This version is running, so whatever was downloaded to get here, or to
    # get to an older one, has done its job. A newer one still waiting stays.
    try:
        _updates.prune_downloads(DATABASE_DIR / 'updates', __version__)
    except Exception:
        logger.opt(exception=True).debug('could not tidy old update downloads')
    api.state.downloader = Downloader(
        download_dir,
        audio_format=api.INTERNAL_FORMAT,
        audio_bitrate=api.INTERNAL_BITRATE,
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

        api.state.download_semaphore = api.DownloadSlots(
            int(api.state.settings.get('max_parallel_downloads', 3))
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

        # Downloads are put together outside the music folder. One that was
        # cut off by a crash or a power cut left its half-made copy there.
        async def _tidy_benches() -> None:
            await asyncio.sleep(5.0)
            try:
                from dannify.downloader import sweep_benches

                gone = await asyncio.to_thread(sweep_benches)
                if gone:
                    logger.info('Removed {} unfinished download(s) left by an earlier run', gone)
            except Exception:
                logger.opt(exception=True).debug('could not tidy unfinished downloads')

        asyncio.create_task(_tidy_benches())

        async def _flush_reports() -> None:
            await asyncio.sleep(20.0)
            await api.flush_reports()

        asyncio.create_task(_flush_reports())

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

    served.mount(app, download_dir)

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

    def tell(track: dict[str, Any]) -> None:
        if api.state.loop is None:
            return

        def send() -> None:
            try:
                asyncio.run_coroutine_threadsafe(
                    api.state.connections.broadcast({'type': 'play_file', 'track': track}),
                    api.state.loop,
                )
            except Exception:
                logger.opt(exception=True).debug('could not hand the file to the window')

        if api.state.connections.settled():
            send()
            return

        # A window still coming up (or not there yet) would not hear it: wait
        # for one that is listening, then say it. A double-click in Explorer
        # while Dannify was starting used to be told to nobody.
        def later() -> None:
            import time as _time

            deadline = _time.monotonic() + 45
            while _time.monotonic() < deadline and not api.state.connections.settled():
                _time.sleep(0.2)
            send()

        import threading as _threading

        _threading.Thread(target=later, name='dannify-open-later', daemon=True).start()

    url = None
    rel = None
    try:
        # The live folder, not the boot-time one: Settings can move it.
        base = Path(api.state.download_dir or DOWNLOAD_DIR).resolve()
        rel = target.relative_to(base).as_posix()
        url = '/downloads/' + quote(rel)
    except (ValueError, RuntimeError, OSError):
        rel = None

    sealed = vault.is_sealed(target)
    head: dict[str, Any] = {}
    # A .dnf that does not even start like one is damaged too, and used to
    # fall through to "not a file we play" and do nothing at all.
    if sealed or target.suffix.lower() == vault.SUFFIX:
        found, problem = vault.inspect(target)
        if problem:
            # Locked with another key, or damaged. Saying so is the only useful
            # thing: the alternative is a player sitting at 0:00 for ever. This
            # used to be returned and not sent, so the window never heard and
            # a double-click did nothing whatsoever. A track in the library
            # also says where it is, so the window can offer to repair it.
            logger.warning('cannot open {}: {}', target, problem)
            failed = {'error': 'unplayable', 'name': target.name, 'file': rel}
            tell(failed)
            return failed
        head = found or {}
    elif target.suffix.lower() not in {
        '.mp3', '.m4a', '.flac', '.ogg', '.wav', '.aac', '.opus',
    }:
        return None

    stem = target.stem
    guess_artist, _, guess_title = stem.partition(' - ')

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
    tell(track)
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
    if args.host not in ('127.0.0.1', 'localhost', '::1'):
        # Open to other devices, so not open to anyone: a key, handed out in
        # the address below. Without one the gate would answer only this
        # machine (see _loopback_host), and the network address it printed
        # led to a blank 404. DANNIFY_KEY keeps the same key across restarts
        # so a bookmarked address keeps working.
        import secrets as _secrets

        key = os.getenv('DANNIFY_KEY', '').strip() or _secrets.token_urlsafe(24)
        api.state.auth_token = key
        lan = _local_ip()
        logger.log(
            'SUCCESS',
            'Open on this device:  http://localhost:{}/?k={}',
            args.port, key,
        )
        logger.log(
            'SUCCESS',
            'Open on your network: http://{}:{}/?k={}  (phone, TV, other PCs)',
            lan, args.port, key,
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
