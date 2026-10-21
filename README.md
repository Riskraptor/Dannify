# Dannify

[![Latest release](https://img.shields.io/github/v/release/Riskraptor/Dannify?label=release)](https://github.com/Riskraptor/Dannify/releases/latest)
[![CI](https://github.com/Riskraptor/Dannify/actions/workflows/ci.yml/badge.svg)](https://github.com/Riskraptor/Dannify/actions/workflows/ci.yml)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20macOS-informational)](#install)
[![Licence: all rights reserved](https://img.shields.io/badge/licence-all%20rights%20reserved-blue)](LICENSE)

A music player for Windows, Linux and macOS. Search for anything, play it
straight away, and save the songs you want to keep in your library, with
artwork, tags and synced lyrics, to play offline.

I built it because every other option was either a browser tab pretending to
be an app, or a downloader with no player attached. This is one program: a
native window, a tray icon, media keys, and a backend on loopback that nothing
outside the app can reach.

![Dannify: Home, with the song playing and its lyrics beside it](docs/screenshots/home.png)

| | |
| --- | --- |
| ![Your music lately and Made for you: today, this week, this month and this year at a glance, and mixes that keep up with your listening](docs/screenshots/made-for-you.png) | ![Your Soundtrack: your year in music, told as a story you can play](docs/screenshots/year-in-music.png) |
| ![Now Playing, with synced lyrics](docs/screenshots/now-playing.png) | ![Your stats: time listened, streaks and a chart of every day](docs/screenshots/stats.png) |
| ![Settings: each pane in its own colour, with your account and version down the side](docs/screenshots/settings.png) | ![The welcome after a big update](docs/screenshots/welcome.png) |
| ![A special day: Diwali, with its lamps and its music](docs/screenshots/special-day.png) | ![Lyrics timing: click the line you hear and the words line up](docs/screenshots/lyrics-timing.png) |
| ![Albums in your library](docs/screenshots/albums.png) | ![An album, its songs in album order](docs/screenshots/album.png) |
| ![An artist page](docs/screenshots/artist.png) | ![Search](docs/screenshots/search.png) |
| ![The command palette](docs/screenshots/palette.png) | ![The Sound panel on the play bar](docs/screenshots/sound.png) |
| ![Your songs](docs/screenshots/library.png) | ![Home in the light theme](docs/screenshots/home-light.png) |

## What it does

Search the YouTube Music catalogue and play anything in about a third of a
second. Suggestions and results come in as you type.

Save whatever you want to keep. Saved songs live in your library, tagged
properly, with their artwork and lyrics, and play without a connection. They
are kept in Dannify's own sealed format, so they play in Dannify and not
elsewhere.

Your library is organised by song, artist, album and playlist. Each album
lists its songs in album order with their real track numbers, and one click
opens the whole album to save the rest of it.

It keeps a listening history, if you want it to. History shows what you
played day by day, and Your stats shows time listened, streaks, the hours you
listen at and your top songs, artists and albums. It stays on your computer;
connect ListenBrainz in Settings, Accounts and your listens go to your profile
there too. Signed in with Google, what you play on YouTube Music elsewhere
(your phone, the web, a speaker) counts here as well, so a copy installed
today starts with all your listening. It comes in by itself whenever you
open Your stats, History or Your Soundtrack, with nothing to press.

From that history Home makes you mixes that keep themselves up to date: On
Repeat, Top This Month, Forgotten Favourites and Recently Added. Your
Soundtrack tells the story of your year in music in up to fourteen pages:
your minutes against last year, your top artist and song and albums, your
year month by month, the hours and weekdays you listen most, your longest
streak, the song you could not stop repeating, what you discovered and the
kind of listener you are. Everything in it plays at a click, the music can
follow the story page by page, and it ends on a card you can play or save
as a playlist, or share as a picture. Today, this week and this month (and
the ones just gone) get stories of their own,
and Home's Your music lately shows all four at a glance: the minutes, the
shape of your listening, and the moments worth telling, like your biggest
music day ever, days in a row, an artist climbing to number one or a song
back after months away. Signed in to YouTube, it all says hello by name.

Lyrics scroll in a side panel and follow the song, lighting up word by word
as each line is sung. If they run early or late, click the line you are
hearing and they line up; if there are several versions, pick the one that
fits best, for a saved song too, and it is kept beside the song. If a track
has none, there is an editor for writing them (a chorus
typed once and repeated) and tapping the timing in, and what you write goes
out to everyone else playing that song.

When the queue runs out, the music keeps going with songs like the last one,
and from your own library when there is no connection.

Ctrl+Shift+P opens a command palette: any page, playback control, setting,
playlist, artist or album, by typing a few letters.

Sign in with Google and you get your own home feed, liked songs and playlists.

Your Library, down the side, holds your playlists, artists and albums in one
list, with chips to show just one kind, a sort, and a compact view. Pin the
ones you play most and they stay at the top.

It celebrates the special days of your year, wherever you are: the New Year,
Lunar New Year, Ramadan and Eid, Holi, Easter, Vesak, Diwali, Hanukkah,
Christmas and many more on your country's own dates, and your country's own
days in its flag's colours. Each has its own look (snow drifting in depth,
fireworks that climb and burst, glowing lanterns and lamps, shooting stars,
petals, confetti) in the app, on the startup screen and in the installer, a
greeting, and music for the day on Home. It works it all out offline, from
this computer's time zone and region. Setting Dannify up asks where you
are, and Settings, Special days lets you change it, with the next special
day shown in its own colours and the rest of the year after it.
Nothing moves when the system asks for reduced motion. There is a welcome
after each big update too.

It speaks English, Français, Español, Português, Deutsch and Kiswahili. It
starts in your computer's language and follows it, or pick one in Settings,
General.

It picks up where you left off. Close it and the queue and the track you were
on come back next launch, paused at the second you stopped. Restart it into
an update and the song plays on from the same second.

Closing the window keeps the music going. It drops to the tray instead of
quitting.

When something goes wrong it says so, with the fix beside it: a song that
will not play can be repaired (downloaded again in the same place), a music
folder that has gone can be chosen again, and saved songs from another PC or
account can be started afresh without deleting anything.

What changed in each version is in [CHANGELOG.md](CHANGELOG.md).

## Install

Everything is on the [downloads
page](https://github.com/Riskraptor/Dannify/releases):

- **Windows 10 and 11:** `Dannify-Setup-<version>.exe`.
- **Ubuntu, Debian, Mint and the like:** `linux-dannify_<version>_amd64.deb`,
  installed with `sudo apt install ./linux-dannify_<version>_amd64.deb`
  (see [packaging/linux](packaging/linux/README-UBUNTU.md)).
- **macOS:** `macos-Dannify-<version>-arm64.dmg` for Apple silicon, `-x64` for
  Intel Macs. The app is not notarized by Apple, so the first time, right-click
  it and choose Open (see [packaging/macos](packaging/macos/README.md)).

Every copy updates itself from signed releases.

## A note on how it plays

Streams resolve by talking to YouTube's app clients directly rather than going
through a general-purpose extractor. Those clients hand back a plain URL, so
there is no player script to download and no JavaScript challenge to solve.
Roughly 350 ms instead of fifteen seconds. yt-dlp is still there as a fallback
for the tracks those clients refuse.

The client identity strings are what make this work, and Google rotates them
every few months. They live in `Backend/dannify/clients.json` so a rotation is
a config fix, not a rebuild.

## Help Dannify grow

Dannify is made by one person and gets better with the help of the people who
use it:

- **Something went wrong, or an idea?** Tell the developer straight from
  the app: Settings, About, Report a problem, or Settings, Support Dannify,
  Share an idea. You can also
  [open an issue](https://github.com/Riskraptor/Dannify/issues/new/choose) or talk
  about it in [Discussions](https://github.com/Riskraptor/Dannify/discussions).
- **Your language?** Dannify speaks six; help it speak yours, or put a word
  right.
- **Lyrics missing or out of time?** Add or improve them right in the lyrics
  panel; everyone who plays the song gets them.
- **Enjoying it?** Star the repository, tell a friend, or
  [sponsor Dannify on GitHub](https://github.com/sponsors/Riskraptor),
  monthly or one time. It's also in the app: Settings, Support Dannify.

How to do each is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Dannify is free to download and use, and its code is here to read, but it is
not open source: all rights are reserved. Please do not copy it, change it
outside this repository, or publish it under another name; if you want to
build on it, open an issue and ask. The details are in [LICENSE](LICENSE).
Versions before 4.13.0 were released under the MIT licence.

Components made by others keep their own licences, listed in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

---

Daniel Mwendwa
