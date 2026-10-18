# Changelog

What changed in each release of Dannify. The newest is at the top. Every
release, with its downloads, is on the [releases
page](https://github.com/DANIELMWENDWA9451/Dannify/releases).

## 4.9.0

### New

- **Albums in your library.** Your Library has an Albums page: every album you
  have saved songs from, sorted by when you added it, by name or by artist.
  Each album opens to its songs in album order, numbered by their real track
  numbers, with Play, Shuffle, the song menus, and **Full album**, which opens
  the whole album on YouTube Music to save the rest of it. "Go to album" on a
  saved song opens the album in your library.
- **Listening history and stats.** Dannify keeps count of what you listen to
  (a listen is 30 seconds, or half of a short song). **History** lists it day
  by day, and **Your stats** shows time listened, streaks, the hours you
  listen at, and your top songs, artists and albums for the last week, month,
  year or all time. Home gains *On repeat* and *Rediscover*. The history stays
  on your computer; it can be paused or cleared in Settings, and one listen can
  be taken out of it.
- **ListenBrainz.** Connect your ListenBrainz account in Settings with your user
  token, and what you listen to goes to your profile as you play it. Listens
  played offline are sent when you are back online. Nothing is sent unless you
  connect an account.
- **Command palette.** Ctrl+Shift+P (Cmd+Shift+P on a Mac) finds any page,
  playback control, setting, playlist, artist or album by typing a few letters.
- **Search suggestions** as you type in the search box.
- **Shortcuts:** L likes the song that is playing, Ctrl+D saves it, and 0 to 9
  jump through it.

### Repair and recovery

- When saved songs cannot be opened on this account (a new PC, a new Windows
  account, a profile restored from a backup), Dannify used to stop saving
  anything and suggest a restart that changed nothing. The message now has two
  ways out: **Try again**, for a keyring that was still locked when Dannify
  started, and **Start fresh**, which lets new songs save again without
  deleting anything, after which the old songs can be repaired.
- A music folder that has gone (an unplugged drive) can be chosen again, or
  checked again, from the message itself.
- **Repair all** says so when nothing needs repairing, instead of doing nothing.
- A repaired song keeps its album, and every original a repair replaces is
  kept for two weeks, not only the latest one.
- What a crash or a power cut left behind in the middle of a repair is tidied
  up the next time Dannify starts.

### Fixed

- Saving a single song lost its album, so songs saved one at a time sat loose
  under "Singles" on artist pages. They keep their album now, and **Look up
  missing albums** on the Albums page finds the album for songs saved before.
- A download whose stream YouTube refused part-way (HTTP 403) failed; it now
  retries the slower, sure way, as playback already did.
- Liked Songs said you had liked nothing when it could not load. It says it
  could not load, and loads by itself once you are back online.
- The support note counted every song that started, skips included; it counts
  real listens now.

### Under the hood

- Libraries with published security advisories were updated: starlette 1.3.1,
  urllib3 2.8.0 and anyio 4.14.2. Also ytmusicapi 1.12.3, certifi 2026.7.22,
  Vue 3.5.44 and axios 1.20.0.

## 4.8.1

If you have 4.7.0 or 4.8.0, install this version by hand, once: those two
accept only updates signed with a key that was lost with the computer it was
on. After this one, updates install themselves again.

- **Linux:** the window shows its own icon and name on the dock, can be pinned
  there, and has Play, Next and Previous on the icon's menu; download progress
  shows on the dock icon.
- **Linux:** a song opened from the file manager starts playing.
- **Linux:** if the page inside the window stops, it loads again by itself.
- **Linux:** the package brings in the media plugins the player needs, and
  shows one Dannify in the desktop's media panel instead of two.
- Every platform's files are built on GitHub's machines and signed on the
  release machine with a new release key.

## 4.8.0

- Dannify runs on **Linux and macOS** as well as Windows, each a native app
  that updates itself from signed releases.
- Plain YouTube channels open and stay followed; a resumed queue comes back as
  it was.
- The lyrics view and editor are redesigned, and the interface reads better and
  works from the keyboard.

## 4.7.0

- Every update is signed (Ed25519), and installed copies refuse anything that
  does not verify against the release key.
- Update checks reuse ETags and back off when GitHub limits them; prerelease
  versions are ordered correctly; a rolled-back update is announced.
- The installer reads its payload past an Authenticode signature.
- CI runs the backend, interface and installer checks.
- Dannify is licensed MIT.

## 4.6.2

- Updates, links and the installer point at this public repository.
- README screenshots; cover art is fetched with retries.

## 4.6.1

- Song details are read without mutagen.

## 4.6.0

- The Sound panel on the play bar; Your Library built for big collections.
- Deleted saved songs play from YouTube Music.
- Follow on YouTube, your YouTube playlists and history; smaller updates.

## 4.5.0

- Half the size: a slim media tool. Your Library in the side bar, Browse,
  About, the Sound panel, the mini player, and problem reports from the app.

## 4.4.0

- Slim overlay scrollbars, cross-fading appearance changes, quieter
  notifications.
- Save any album or playlist as your own playlist; your account's playlists in
  the side bar.
- Audio is never kept in the window's cache, settings that would open the app
  up are refused, and songs are worked on in the app's own data folder.
- An interrupted setup download resumes.

## 4.3.0

- Crossfade, gapless playback, a 10-band equalizer with presets, loudness
  levelling and a sleep timer.
- Global shortcuts, start with Windows.
- Your own playlists: create, rename, reorder, drag songs onto them, save the
  queue as one.
- Report a problem from the app.

## 4.2.0

- The right artists, an app that knows when it is offline, and lyrics anyone
  can correct.

## 4.1.1

- Tick many songs at once to play, queue, refresh or delete them.
- Refresh details fetches a saved song's title, artists, album, year, artwork
  and missing lyrics again without downloading it again.

## 4.1.0

- Downloads are put together away from the music folder, so the library only
  ever sees a finished song.
- Artist pages show saved songs first, then the rest of their music online.
- Search shows matching saved songs and artists first, offline too.
- Settings search, storage and caches, named interface sizes, new palettes.
- Certificates are checked on every download; updates come only from the
  release.

## 4.0.0

- A new installer: one small program that installs, launches and uninstalls
  Dannify, in English and French.
- Updates are prepared in the background, fetching only the files that
  changed, and applied the next time Dannify starts. If a new version cannot
  start, the one before comes back.
- A first-run welcome.

Earlier versions are in the [commit
history](https://github.com/DANIELMWENDWA9451/Dannify/commits/main).
