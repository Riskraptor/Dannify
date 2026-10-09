"""What every desktop shell shares: folders, preferences, the local server,
the splash page, and how songs are named in trays and menus."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .. import osenv

APP_TITLE = 'Dannify'
DEFAULT_W, DEFAULT_H = 1320, 860
MIN_W, MIN_H = 760, 540
MINI_W, MINI_H = 420, 124
MINI_MAX_H = 560
THEME_BG = {'dark': '#08080a', 'light': '#e7e9ed'}

# Google's own sign-in page, handing back to YouTube Music.
LOGIN_URL = (
    'https://accounts.google.com/ServiceLogin'
    '?service=youtube&continue=https%3A%2F%2Fmusic.youtube.com%2F'
)
SIGNED_IN_HOSTS = ('music.youtube.com', 'www.youtube.com')
ORIGIN = 'https://music.youtube.com'

LAN_ENABLED = os.environ.get('DANNIFY_LAN', '').strip().lower() in ('1', 'true', 'yes')
BIND_HOST = '0.0.0.0' if LAN_ENABLED else '127.0.0.1'

# The global shortcuts, by command: Ctrl+Alt with these keys everywhere.
HOTKEYS = (('toggle', 'P', 'Ctrl+Alt+P'), ('next', 'Right', 'Ctrl+Alt+Right'),
           ('prev', 'Left', 'Ctrl+Alt+Left'))

TRAY_TIP_MAX = 127
MENU_TEXT_MAX = 60


def data_dir() -> Path:
    """This copy's data folder: DANNIFY_DATA_DIR, or the platform's own."""

    raw = os.getenv('DANNIFY_DATA_DIR')
    path = Path(raw).expanduser() if raw else osenv.default_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('DANNIFY_LOG_FILE', str(path / 'dannify.log'))
    return path


DATA_DIR = data_dir()
PREFS_FILE = DATA_DIR / 'window.json'
PORT_FILE = DATA_DIR / 'port.json'
INSTANCE_FILE = DATA_DIR / 'instance.json'
LOGIN_STORAGE = DATA_DIR / 'SignIn'
UPDATES_DIR = DATA_DIR / 'updates'


# ---------------------------------------------------------------------------
# Window preferences (geometry, theme, tray, shortcuts)
# ---------------------------------------------------------------------------
def read_prefs() -> dict:
    try:
        data = json.loads(PREFS_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_prefs(patch: dict) -> None:
    try:
        data = read_prefs()
        data.update(patch)
        tmp = PREFS_FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data), encoding='utf-8')
        tmp.replace(PREFS_FILE)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The local server
# ---------------------------------------------------------------------------
def port_is_free(port: int, host: str = BIND_HOST) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
        return True
    except OSError:
        return False


def pick_port() -> int:
    """The port this installation used last time, if it is still free.

    The page is served from it, so a new port every launch meant a new origin
    and an empty localStorage: volume, language, zoom, the playing position,
    all forgotten. Chosen once per installation and kept.
    """

    try:
        saved = int(json.loads(PORT_FILE.read_text(encoding='utf-8'))['port'])
        if 1024 < saved < 65536 and port_is_free(saved):
            return saved
    except Exception:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((BIND_HOST, 0))
        port = int(s.getsockname()[1])
    try:
        PORT_FILE.write_text(json.dumps({'port': port}), encoding='utf-8')
    except OSError:
        pass
    return port


def start_server(port: int, token: str):
    """Boot the backend on a daemon thread; returns the uvicorn Server."""

    import asyncio

    import main as backend
    from uvicorn import Config, Server

    backend._setup_logging(os.environ.get('DANNIFY_LOG_LEVEL', 'info'))
    backend.api.state.auth_token = token
    backend._fix_mime_types()
    server = Server(Config(
        app=backend.build_app(), host=BIND_HOST, port=port, log_level='info',
        log_config=None, workers=1, server_header=False, date_header=False,
    ))

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        benign = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)

        def quiet(loop, context):  # noqa: ANN001
            # A closed window drops its connections mid-request; that is not
            # an error anybody needs to read about.
            if isinstance(context.get('exception'), benign):
                return
            loop.default_exception_handler(context)

        loop.set_exception_handler(quiet)
        try:
            loop.run_until_complete(server.serve())
        except BaseException:
            logger.opt(exception=True).error('The server stopped or could not start')
        finally:
            server.dannify_stopped = True

    server.dannify_stopped = False
    threading.Thread(target=run, name='dannify-server', daemon=True).start()
    return server


def wait_until_up(port: int, token: str, server=None, timeout: float = 30.0) -> bool:
    """Poll until the API answers, carrying the session key like any request."""

    url = f'http://127.0.0.1:{port}/api/version'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server is not None and getattr(server, 'dannify_stopped', False):
            return False
        try:
            request = urllib.request.Request(url, headers={'X-Dannify-Key': token})
            with urllib.request.urlopen(request, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.05)
    return False


def app_url(port: int, token: str) -> str:
    return f'http://127.0.0.1:{port}/?shell=desktop&k={token}'


def write_instance_file(port: int) -> None:
    try:
        INSTANCE_FILE.write_text(json.dumps({'port': port, 'pid': os.getpid()}), encoding='utf-8')
    except OSError:
        pass


def open_when_connected(path: str) -> None:
    """Play a file handed to us at launch, once the window is listening."""

    import main as backend

    for _ in range(60):
        time.sleep(0.5)
        if getattr(backend.api.state.connections, 'connected', False):
            break
    try:
        backend.open_external(path)
    except Exception:
        logger.opt(exception=True).info('could not open {}', path)


def file_argument(argv: Optional[list[str]] = None) -> str:
    """The file the desktop handed us (a double-clicked song), if any."""

    for arg in (sys.argv[1:] if argv is None else argv):
        if arg.startswith('-'):
            continue
        if arg.startswith('file://'):
            from urllib.parse import urlsplit
            from urllib.request import url2pathname

            arg = url2pathname(urlsplit(arg).path)
        try:
            if Path(arg).is_file():
                return str(Path(arg).resolve())
        except OSError:
            continue
    return ''


# ---------------------------------------------------------------------------
# Paths the interface may ask about
# ---------------------------------------------------------------------------
def library_path(rel_path: str) -> Optional[Path]:
    """*rel_path* inside the live library folder, never outside it."""

    try:
        from dannify import api as _api

        base = Path(_api.state.download_dir).resolve()
    except Exception:
        return None
    if not rel_path:
        return base
    try:
        target = (base / rel_path).resolve()
        target.relative_to(base)
        return target
    except (ValueError, RuntimeError, OSError):
        return None


def vetted_update(path: str, suffix: str) -> Optional[Path]:
    """The update file, but only one we downloaded ourselves.

    Nothing outside our own updates folder is ever installed, whatever the
    interface asks for: this is a path arriving from JavaScript.
    """

    try:
        found = Path(str(path or '')).resolve()
        found.relative_to(UPDATES_DIR.resolve())
        if found.suffix.lower() != suffix or not found.is_file():
            return None
        return found
    except Exception:
        return None


def relaunch_command() -> list[str]:
    """How to start this same copy again."""

    if getattr(sys, 'frozen', False):
        return [sys.executable, *[a for a in sys.argv[1:] if a != '--minimized']]
    entry = Path(__file__).resolve().parents[2] / 'desktop.py'
    return [sys.executable, str(entry)]


# ---------------------------------------------------------------------------
# How a song is named in trays, menus and media panels
# ---------------------------------------------------------------------------
def fit_text(text: str, limit: int) -> str:
    """One line, at most *limit* characters, the cut marked with an ellipsis."""

    flat = ' '.join(str(text or '').split())
    if len(flat) <= limit:
        return flat
    return flat[: max(0, limit - 1)].rstrip() + '\N{HORIZONTAL ELLIPSIS}'


def track_label(title: str, artist: str) -> str:
    """"Title · Artist", the way the interface joins details."""

    title = ' '.join(str(title or '').split())
    artist = ' '.join(str(artist or '').split())
    if title and artist:
        return f'{title} \N{MIDDLE DOT} {artist}'
    return title


DEFAULT_LABELS = {
    'nowPlaying': 'Nothing playing',
    'play': 'Play',
    'pause': 'Pause',
    'next': 'Next',
    'prev': 'Previous',
    'show': 'Open Dannify',
    'quit': 'Quit Dannify',
    'hidden': 'Dannify is still running here.',
}


def tray_menu(labels: dict, track: str, playing: bool, has_track: bool) -> list:
    """The tray menu as (command, text, enabled) rows; None is a separator.

    Built from the current state each time, so Play and Pause can never be
    the wrong way round.
    """

    return [
        ('track', fit_text(track or labels['nowPlaying'], MENU_TEXT_MAX), False),
        None,
        ('toggle', labels['pause' if playing else 'play'], has_track),
        ('prev', labels['prev'], has_track),
        ('next', labels['next'], has_track),
        None,
        ('show', labels['show'], True),
        ('quit', labels['quit'], True),
    ]


def merge_labels(current: dict, incoming: Any) -> dict:
    """Localised menu labels from the interface, only the ones we know."""

    if not isinstance(incoming, dict):
        return current
    out = dict(current)
    for key, value in incoming.items():
        if key in DEFAULT_LABELS and isinstance(value, str) and value.strip():
            out[key] = fit_text(value, MENU_TEXT_MAX)
    return out


def splash_html(theme: str, body: str = '') -> str:
    """What the window shows while the server starts: painted instantly."""

    dark = theme != 'light'
    bg = THEME_BG['dark' if dark else 'light']
    fg = '#e7e7ef' if dark else '#16181c'
    muted = '#8a8a98' if dark else '#6b6f78'
    track = '#23232e' if dark else '#d5d8de'
    content = body or (
        "<div class='logo'>Dan<span>nify</span></div>"
        "<div class='bar'></div>"
        "<div class='hint'>Starting your music…</div>"
    )
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
  html,body{{margin:0;height:100%;background:{bg};color:{fg};overflow:hidden;
    font-family:system-ui,-apple-system,'Segoe UI',Ubuntu,Cantarell,sans-serif;
    user-select:none;cursor:default}}
  .wrap{{height:100%;display:flex;flex-direction:column;align-items:center;
    justify-content:center;text-align:center;animation:fade .45s ease}}
  .logo{{font-size:44px;font-weight:800;letter-spacing:-1px}}
  .logo span{{color:#1db954}}
  .bar{{margin:26px auto 0;width:180px;height:3px;border-radius:99px;
    background:{track};overflow:hidden;position:relative}}
  .bar::after{{content:'';position:absolute;left:-40%;top:0;height:100%;
    width:40%;border-radius:99px;background:#1db954;
    animation:slide 1s cubic-bezier(.4,0,.2,1) infinite}}
  .hint{{margin-top:14px;font-size:12px;color:{muted}}}
  @keyframes slide{{to{{left:100%}}}}
  @keyframes fade{{from{{opacity:0;transform:scale(.97)}}to{{opacity:1}}}}
</style></head><body><div class='wrap'>{content}</div></body></html>"""


def failed_html(theme: str) -> str:
    return splash_html(
        theme,
        '<h2>Dannify could not start</h2>'
        '<p>If a copy is still running, quit it from its icon, then open Dannify again.</p>',
    )
