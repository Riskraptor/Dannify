# Dannify

A music player for Windows. Search for anything, play it straight away, and
keep the tracks you want as real files with artwork, tags and synced lyrics.

I built it because every other option was either a browser tab pretending to
be an app, or a downloader with no player attached. This is one program: a
native window, a tray icon, media keys, and a backend on loopback that nothing
outside the app can reach.

## What it does

Search the YouTube Music catalogue and play anything in about a third of a
second. Results come in as you type.

Download whatever you want to keep. MP3, FLAC, OGG, Opus or M4A, tagged
properly, with cover art embedded and an `.lrc` beside it.

Lyrics scroll in a side panel and follow the song. If a track has none, there
is an editor for writing them and tapping the timing in, and what you write
goes out to everyone else playing that song.

Sign in with Google and you get your own home feed, liked songs and playlists.

It picks up where you left off. Close it and the queue and the track you were
on come back next launch, paused at the second you stopped.

Closing the window keeps the music going. It drops to the tray instead of
quitting.

## Install

Installers are on the [downloads
page](https://github.com/DANIELMWENDWA9451/dannify-releases/releases).

## Building it

You need Python 3.14, Node 20 or newer, and the .NET SDK (8 or newer) for
the installer.

```powershell
cd Backend
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
cd ..\frontend
npm install
cd ..
pwsh packaging\build.ps1
```

That leaves you `Backend\dist\Dannify\`, the installer
`packaging\out\Dannify-Setup-<version>.exe`, and the update package
(`package-<version>.json` and `.zip`) beside it.

Two binaries are not in the repo because they are redistributables, not
source: the media encoder at `packaging\media\dnfmedia.exe` and the JS engine
at `packaging\jsruntime\dnfjs.exe`. Notes in `packaging\config\README.md`.

## Working on it

```powershell
cd Backend
.\venv\Scripts\python.exe desktop.py
```

Environment variables worth knowing:

| Variable | What it does |
| --- | --- |
| `DANNIFY_INSTANCE` | Suffixes the single-instance lock so a second copy can run |
| `DANNIFY_DATA_DIR` | Settings, caches and the WebView profile |
| `DANNIFY_DEVTOOLS_PORT` | Remote debugging port. Source builds only |
| `DANNIFY_LOG_LEVEL` | `debug` when something is wrong |
| `DANNIFY_UPDATE_REPO` | Check a different `owner/name` for updates |
| `DANNIFY_UPDATE_API` | A stand-in release server, for testing updates. `127.0.0.1` only |
| `DANNIFY_KEY` | The key for `main.py` run on the network (`--host 0.0.0.0`). One is made up and printed if unset |

A second copy needs its own `DANNIFY_DATA_DIR`. WebView2 will not open the
same profile folder twice with different options, and you get a dead window
instead of a useful error.

## A note on how it plays

Streams resolve by talking to YouTube's app clients directly rather than going
through a general-purpose extractor. Those clients hand back a plain URL, so
there is no player script to download and no JavaScript challenge to solve.
Roughly 350 ms instead of fifteen seconds. yt-dlp is still there as a fallback
for the tracks those clients refuse.

The client identity strings are what make this work, and Google rotates them
every few months. They live in `Backend/dannify/clients.json` so a rotation is
a config fix, not a rebuild.

## Installing and updating

`installer/` is one small .NET Framework program that is the installer, the
launcher and the uninstaller. The setup is that program with the app packed
on the end. An install looks like this:

```
%LOCALAPPDATA%\Programs\Dannify\
  Dannify.exe     the launcher; shortcuts and the Apps entry point here
  app\            the app itself
```

The running app gets an update ready in `app-next\` in the background,
fetching only the files that changed out of `package-<version>.zip`. The
launcher swaps the folders the next time Dannify starts, or straight away on
Restart to update, and keeps the previous version. If the new one cannot
start, it goes back to the old one and skips that version.

`python packaging\lifecycle.py` runs install, launch, update, restart,
rollback and uninstall end to end in a sandbox that touches no real install,
registry entry or library. `upgrade`, `restart_previous`,
`setup_over_previous` and `rollback_previous` do the same starting from the
release before this one, the way people who already have Dannify will get the
new version, and `migrate` does it from a 3.x folder.

## Releases

The version lives in `Backend/dannify/__init__.py`; the build stamps it
everywhere else. Bump it, build, then publish:

```powershell
pwsh packaging\publish.ps1 -Notes "what changed"
```

That uploads the installer and the update package and leaves only the new
release on the downloads repo.

## Licence

Proprietary. All rights reserved: see [LICENSE](LICENSE). Components made by
others keep their own licences, listed in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

---

Daniel Mwendwa
