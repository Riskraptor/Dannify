# Dannify on Linux

Dannify runs on Ubuntu 22.04 and newer, Debian 12 and newer, and the
distributions built on them (Linux Mint, Pop!_OS, elementary, Zorin).

## Install

Download `linux-dannify_<version>_amd64.deb` from the
[releases page](https://github.com/DANIELMWENDWA9451/Dannify/releases) and:

```bash
sudo apt install ./linux-dannify_<version>_amd64.deb
```

apt brings in what it needs (GTK, WebKit, GStreamer, ffmpeg). Then open
Dannify from the app grid, or run `dannify`.

## Updates

Dannify checks for updates itself. A new version is downloaded, its
signature checked against the release key built into the app, and installed
with your password (the system's own prompt). It restarts as the new version.

## What it does on Linux

- A tray icon with play/pause, next and previous. On GNOME it needs the
  AppIndicator extension (Ubuntu has it on). Closing the window then keeps
  the music playing.
- The keyboard's media keys and the desktop's media panel (MPRIS).
- Download progress on the dock icon.
- "Start with your computer", "Show in folder", the system's sound settings.
- Ctrl+Alt+P / Ctrl+Alt+Left / Ctrl+Alt+Right everywhere, on X11 sessions
  (Wayland lets no app take keys for itself; the media keys still work).
- Your YouTube Music session and the key your songs are saved with are kept
  in the system keyring (GNOME Keyring or KWallet).

Settings and the keyring entry live in `~/.local/share/Dannify`; songs in
`~/Music/Dannify`. Removing the package leaves both.

## Remove

```bash
sudo apt remove dannify
```
