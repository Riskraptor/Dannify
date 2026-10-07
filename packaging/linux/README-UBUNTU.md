# Dannify on Ubuntu (native port)

This is the native Ubuntu port of Dannify (Windows music player).
It reuses the same FastAPI backend (`Backend/dannify/*`) and Vue
frontend (`frontend/`) behind a Linux launcher instead of WebView2.

## What changed vs Windows

* New: `Backend/desktop_linux.py` — XDG dirs (`~/.local/share/Dannify`),
  POSIX file-lock single instance, free-port picking (42810 → ephemeral),
  uvicorn loopback server, pywebview GTK/WebKit window with splash →
  app swap, system-browser fallback. No `ctypes.wintypes`, no named mutex,
  no `edgechromium`, no `.exe`.
* Unchanged: `Backend/main.py`, `Backend/dannify/*`, `frontend/*`.
  Media uses system `ffmpeg`/`ffprobe`; JS engine prefers
  `deno`/`bun`/`node`/`qjs` on PATH (see `dannify/jsruntime.py`).
* Packaging: `packaging/linux/` (`dannify` launcher, `dannify.desktop`,
  `requirements-linux.txt`, `build-deb.sh`) → `/opt/dannify`,
  `/usr/bin/dannify`, desktop entry, icon. `Architecture: all`,
  compatible with Ubuntu 22.04/24.04/25.04+ (python3 >= 3.10).

## Install (.deb)

```bash
sudo apt update
sudo apt install ./dannify_4.6.2_all.deb
# apt auto-installs: python3-venv, python3-gi, ffmpeg, webkit2gtk, nodejs.
# First launch creates /opt/dannify/venv (network once), then:
dannify
```

Files: `/opt/dannify/`, `/usr/bin/dannify`, `~/.local/share/Dannify/`.
Env: `DANNIFY_DATA_DIR`, `DANNIFY_INSTANCE`, `DANNIFY_LAN=1` (share LAN),
`DANNIFY_LOG_LEVEL=debug`, `DANNIFY_DEVTOOLS_PORT` (source only).

## Build from source

```bash
cd frontend && npm ci && npm run build && cd ..
bash packaging/linux/build-deb.sh
sudo dpkg -i dannify_*_all.deb
```

Requires: `python3-venv python3-gi ffmpeg libwebkit2gtk-4.1-0 nodejs npm`.
Python 3.10+ works; 3.12/3.14 recommended. Original README asked for
3.14, but Ubuntu archives ship 3.10 (22.04) / 3.12 (24.04) — the port
is tested against the system Python to stay compatible in all.
