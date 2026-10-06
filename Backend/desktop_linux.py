"""Dannify Linux desktop launcher (Ubuntu / Debian).

Native GTK/WebKit window (pywebview) wrapping the same FastAPI backend +
built Vue frontend as the Windows build. No Windows APIs, no WebView2,
no .NET installer, no .exe redistributables.

Protocol (must match Backend/main.py _Gateway + frontend/src/desktop/bridge.js):
* App URL carries ``?shell=desktop&k=<token>`` (NOT ``?key=``). The server
  trades ``k`` for a ``dnf_session`` HttpOnly cookie; later assets, audio
  range requests and websockets ride the cookie.
* ``window.pywebview.api.win_state`` MUST exist or the frontend's
  ``whenReady()`` never resolves and the app spins on loading forever.
  All other js_api methods degrade to no-ops in the frontend, but Linux
  implements the common window commands for real via the pywebview Window.
* Readiness probe presents the key (``/?k=``) since even ``/`` refuses
  without it (answered 404 as if nothing listens).

Data: $DANNIFY_DATA_DIR or $XDG_DATA_HOME/Dannify or ~/.local/share/Dannify.
Exported as DANNIFY_DATA_DIR BEFORE importing main so DATABASE_DIR and
DOWNLOAD_DIR (= DATA_DIR/Music) stay user-writable, never /opt/dannify/*.
Single instance via POSIX fcntl lock; DANNIFY_INSTANCE suffixes for devs.
Port 42810 preferred, else persisted ephemeral. Loopback unless DANNIFY_LAN=1.
Media: system ffmpeg/ffprobe. JS: deno/bun/node/qjs on PATH (jsruntime.py).
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_TITLE = "Dannify"
PREFERRED_PORT = 42810

LAN_ENABLED = os.environ.get("DANNIFY_LAN", "").strip().lower() in ("1", "true", "yes")
BIND_HOST = "0.0.0.0" if LAN_ENABLED else "127.0.0.1"


def _data_dir() -> Path:
    base = os.getenv("DANNIFY_DATA_DIR")
    if base:
        p = Path(base).expanduser()
    else:
        xdg = os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        p = Path(xdg) / "Dannify"
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_DIR = _data_dir()
PORT_FILE = DATA_DIR / "port.json"
INSTANCE_FILE = DATA_DIR / "instance.json"
LOCK_NAME = f"dannify{os.environ.get('DANNIFY_INSTANCE', '')}.lock"
LOCK_FILE = DATA_DIR / LOCK_NAME
os.environ.setdefault("DANNIFY_LOG_FILE", str(DATA_DIR / "dannify.log"))
# Backend (main.py) defaults DATABASE_DIR to <project>/data (root-owned under
# /opt/dannify). Export user-writable XDG dir BEFORE importing main so both
# database and downloads (DATA_DIR/Music) stay in the home directory.
os.environ["DANNIFY_DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("DATABASE_DIR", str(DATA_DIR))


def _port_is_free(port: int, host: str = BIND_HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _pick_port() -> int:
    if PREFERRED_PORT and _port_is_free(PREFERRED_PORT):
        return PREFERRED_PORT
    try:
        saved = int(json.loads(PORT_FILE.read_text(encoding="utf-8"))["port"])
        if 1024 < saved < 65536 and _port_is_free(saved):
            return saved
    except Exception:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((BIND_HOST, 0))
        port = int(s.getsockname()[1])
    try:
        PORT_FILE.write_text(json.dumps({"port": port}), encoding="utf-8")
    except OSError:
        pass
    return port


_lock_fd = None


def _acquire_single_instance() -> bool:
    """POSIX single instance. True if first copy, False if another runs."""
    global _lock_fd
    try:
        import fcntl  # noqa: PLC0415
    except ImportError:
        return True
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _lock_fd = open(LOCK_FILE, "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _write_instance_file(port: int) -> None:
    try:
        INSTANCE_FILE.write_text(
            json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8"
        )
    except OSError:
        pass


def _start_server(port: int, token: str):
    import main as backend  # noqa: PLC0415
    from uvicorn import Config, Server  # noqa: PLC0415

    try:
        backend._setup_logging(os.environ.get("DANNIFY_LOG_LEVEL", "info"))
    except Exception:
        pass
    try:
        backend.api.state.auth_token = token
    except Exception:
        pass
    try:
        backend._fix_mime_types()
    except Exception:
        pass
    app = backend.build_app()
    config = Config(
        app=app,
        host=BIND_HOST,
        port=port,
        log_level="info",
        log_config=None,
        workers=1,
        server_header=False,
        date_header=False,
    )
    server = Server(config)

    def _run() -> None:
        import asyncio  # noqa: PLC0415

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        except BaseException:
            pass

    t = threading.Thread(target=_run, name="dannify-server", daemon=True)
    t.start()
    return server


def _wait_for_server(port: int, token: str, timeout: float = 30.0) -> bool:
    """Poll with the session key: even / refuses (404) without it."""
    host = BIND_HOST if BIND_HOST != "0.0.0.0" else "127.0.0.1"
    url = f"http://{host}:{port}/?k={token}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                url, headers={"x-dannify-key": token}
            )
            with urllib.request.urlopen(req, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def _splash_html(theme: str = "dark") -> str:
    bg = "#101418" if theme != "light" else "#f6f7f9"
    fg = "#e8eaed" if theme != "light" else "#1a1d21"
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{background:" + bg + ";color:" + fg + ";font-family:system-ui,"
        "sans-serif;display:flex;align-items:center;justify-content:center;"
        "height:100vh;margin:0}h1{font-size:28px;letter-spacing:.5px}"
        ".bar{width:180px;height:3px;background:#ffffff22;margin:14px auto 0;"
        "border-radius:2px;overflow:hidden}.bar i{display:block;height:100%;"
        "width:40%;background:#7aa2ff;border-radius:2px;animation:s 1s infinite "
        "alternate}@keyframes s{from{margin-left:0}to{margin-left:60%}}</style>"
        "</head><body><div><h1>" + APP_TITLE + "</h1><div class='bar'><i></i>"
        "</div></div></body></html>"
    )


def _read_theme() -> str:
    try:
        prefs = json.loads((DATA_DIR / "prefs.json").read_text(encoding="utf-8"))
        if isinstance(prefs, dict) and prefs.get("theme") == "light":
            return "light"
    except Exception:
        pass
    return "dark"


class LinuxApi:
    """js_api for the Linux shell. win_state gates frontend whenReady()."""

    def __init__(self) -> None:
        self._window = None
        self._maximized = False
        self._fullscreen = False
        self._mini = False
        self._on_top = False

    def _attach(self, window) -> None:  # noqa: ANN001
        self._window = window

    def win_state(self) -> dict:
        return {
            "maximized": self._maximized,
            "minimized": False,
            "fullscreen": self._fullscreen,
            "focused": True,
            "mini": self._mini,
            "onTop": self._on_top,
            "nativeFrame": True,
            "nativeFramePref": False,
            "closeToTray": False,
            "globalHotkeys": False,
            "hotkeysTaken": [],
            "autostart": {"available": False, "on": False},
            "ready": True,
        }

    def win_minimize(self):
        try:
            if self._window is not None:
                self._window.minimize()
        except Exception:
            pass

    def win_toggle_maximize(self):
        try:
            if self._window is not None:
                if self._maximized:
                    self._window.restore()
                else:
                    self._window.maximize()
                self._maximized = not self._maximized
        except Exception:
            pass

    def win_close(self):
        try:
            if self._window is not None:
                self._window.destroy()
        except Exception:
            pass

    def win_toggle_fullscreen(self):
        try:
            if self._window is not None:
                self._window.toggle_fullscreen()
                self._fullscreen = not self._fullscreen
        except Exception:
            pass

    def win_set_mini(self, on=False):  # noqa: ANN001
        self._mini = bool(on)

    def win_set_mini_size(self, height=0):  # noqa: ANN001
        return None

    def win_set_on_top(self, on=False):  # noqa: ANN001
        self._on_top = bool(on)

    def win_set_zoom(self, factor=1):  # noqa: ANN001
        return None

    def win_set_native_frame(self, on=False):  # noqa: ANN001
        return None

    def tray_labels(self, labels=None):  # noqa: ANN001
        return None


def main() -> None:
    if "--quit" in sys.argv[1:]:
        sys.exit(0)
    if not _acquire_single_instance():
        try:
            note = json.loads(INSTANCE_FILE.read_text(encoding="utf-8"))
            port = int(note.get("port", 0) or 0)
            if port:
                webbrowser.open(f"http://127.0.0.1:{port}/")
        except Exception:
            pass
        print("Dannify is already running.")
        sys.exit(0)

    port = _pick_port()
    token = secrets.token_urlsafe(24)
    server = _start_server(port, token)
    _write_instance_file(port)

    host = "127.0.0.1" if BIND_HOST == "0.0.0.0" else BIND_HOST
    # shell=desktop lets bridge.js detect the shell; k= trades for dnf_session.
    app_url = f"http://{host}:{port}/?shell=desktop&k={token}"

    try:
        import webview  # noqa: PLC0415
    except Exception as e:
        print(f"pywebview unavailable ({e}); opening system browser at {app_url}")
        if _wait_for_server(port, token, timeout=30.0):
            webbrowser.open(app_url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                server.should_exit = True
            except Exception:
                pass
        return

    api = LinuxApi()
    theme = _read_theme()
    window = webview.create_window(
        APP_TITLE,
        html=_splash_html(theme),
        js_api=api,
        width=1280,
        height=800,
        min_size=(1024, 640),
        text_select=False,
        zoomable=False,
    )

    def _before_show(window):  # noqa: ANN001 (UI thread)
        api._attach(window)

    def _swap_to_app():
        if _wait_for_server(port, token, timeout=30.0):
            try:
                window.load_url(app_url)
            except Exception:
                pass

    threading.Thread(target=_swap_to_app, name="dannify-swap", daemon=True).start()

    def _on_closed():
        try:
            server.should_exit = True
        except Exception:
            pass
        try:
            if INSTANCE_FILE.exists():
                INSTANCE_FILE.unlink()
        except Exception:
            pass

    try:
        window.events.before_show += _before_show
    except Exception:
        pass
    try:
        window.events.closed += _on_closed
    except Exception:
        pass

    try:
        webview.start(debug=False, private_mode=False)
    except Exception as e:
        print(f"WebView failed ({e}); opening system browser at {app_url}")
        if _wait_for_server(port, token, timeout=15.0):
            webbrowser.open(app_url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                server.should_exit = True
            except Exception:
                pass


def entry() -> None:
    main()


if __name__ == "__main__":
    main()
