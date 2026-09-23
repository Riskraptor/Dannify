# Dannify

A desktop music player for Windows. Search anything, play it instantly, and
keep what you want as a properly tagged file with album art and synced lyrics.

Not a browser in a window: a native frame, a real system tray, media keys, and
a local backend that nothing outside the app can reach.

## What it does

- **Search and play** the whole YouTube Music catalogue, with results as you
  type and the next track warmed before you click it
- **Download** any track with embedded artwork, tags and lyrics, in MP3, FLAC,
  OGG, Opus or M4A
- **Synced lyrics** in a side panel that follows the song, with an editor for
  writing and timing lyrics that do not exist yet
- **Sign in with Google** for your own YouTube Music home feed, liked songs
  and playlists
- **Your library** on disk, organised how you choose, searchable and playable
  offline
- **Picks up where you left off**: the queue and the track you were on come
  back on the next launch
- **Stays out of the way**: closes to the tray and keeps playing, remembers
  its window, and updates itself from GitHub releases

## Install

Download the latest `Dannify-Setup-x.y.z.exe` from
[Releases](https://github.com/DANIELMWENDWA9451/dannify-releases/releases)
and run it. Windows 10 or 11.

The app checks for new releases on its own and offers to restart into them.

## Building from source

Requires Python 3.14, Node 20+, and Inno Setup 6 for the installer.

```powershell
cd Backend
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
cd ..\frontend
npm install
cd ..
pwsh packaging\build.ps1
```

The result is `Backend\dist\Dannify\` (the app folder) and
`packaging\out\Dannify-Setup-<version>.exe`.

Two redistributables are not in this repository because they are binaries, not
source: a media encoder at `packaging\media\dnfmedia.exe` and a JavaScript
engine at `packaging\jsruntime\dnfjs.exe`. See `packaging\config\README.md`.

## Running it in development

```powershell
cd Backend
.\venv\Scripts\python.exe desktop.py
```

Useful environment variables:

| Variable | Effect |
| --- | --- |
| `DANNIFY_INSTANCE` | Suffixes the single-instance lock, so a second copy can run |
| `DANNIFY_DATA_DIR` | Where settings, caches and the WebView profile live |
| `DANNIFY_DEVTOOLS_PORT` | Opens a remote debugging port (source builds only) |
| `DANNIFY_LOG_LEVEL` | `debug` for the full picture |
| `DANNIFY_UPDATE_REPO` | Point the updater at a different `owner/name` |

## Configuration

`packaging/config/` holds the settings baked into a release: which repository
to check for updates (a public, releases-only repository, so the app can
check without credentials), and the donation details. Both ship with empty or
placeholder values; fill them in before building a release of your own.

## License

See [LICENSE](Backend/LICENSE).
