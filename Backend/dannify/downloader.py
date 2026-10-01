"""Download a track from YouTube and tag it with the chosen metadata."""

from __future__ import annotations

import os
import re
import re as _re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests
import yt_dlp
from loguru import logger
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TRCK,
    TXXX,
    USLT,
)
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from . import lyrics as lyrics_mod
from .itunes import fetch_genre as _fetch_itunes_genre
from .m3u import sanitize_playlist_name
from .providers import enrich_from_match, find_match, find_match_for_video

_INVALID_FS_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

ProgressCallback = Callable[[float, str], None]


def _env(name: str, default: str = '') -> str:
    """Read a ``DANNIFY_*`` env var, falling back to the legacy ``DOWNTIFY_*``.

    Keeps existing deployments working unchanged after the rebrand.
    """

    val = os.getenv(name)
    if val is None and name.startswith('DANNIFY_'):
        val = os.getenv('DOWNTIFY_' + name[len('DANNIFY_') :])
    return val if val is not None else default



# Names Windows keeps for devices. A folder or file called any of these (with
# any extension) cannot be created at all, so an artist named "Aux" failed
# every download.
_RESERVED_NAMES = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL']
    + [f'COM{i}' for i in range(1, 10)]
    + [f'LPT{i}' for i in range(1, 10)]
)


# A whole path has to fit in the 260 characters Windows still holds most
# programs to, music folder and artist folder included. A classical track with
# eight credited artists and a long movement title came to 353 characters for
# the name alone, and could not be saved at all.
_NAME_LIMIT = 120
_FOLDER_LIMIT = 80


def _sanitize(text: str, limit: int = _NAME_LIMIT) -> str:
    safe = _INVALID_FS_CHARS.sub('', text or '').strip().strip('.').strip()
    if len(safe) > limit:
        cut = safe[:limit]
        # On a word boundary when there is one reasonably close.
        space = cut.rfind(' ')
        if space >= limit * 0.6:
            cut = cut[:space]
        safe = cut.rstrip(' ,;&-').rstrip('.').strip()
    # The device name is whatever comes before the first dot, so that is where
    # the mark goes: "Con.Air" used to become "Con.Air_", still a device.
    head, dot, rest = safe.partition('.')
    if head.strip().upper() in _RESERVED_NAMES:
        safe = f'{head.rstrip()}_{dot}{rest}'
    return safe or 'unknown'


class DownloadStopped(Exception):
    """The download was taken off the queue while it ran."""


# Where a song is put together before it is sealed. A download used to happen
# in the music folder itself: the raw stream, then a plain untagged .mp3, then
# the tags and the lyrics, then the seal. The folder watcher saw every one of
# those, so the library was read while the song was half made. A new artist
# turned up in the sidebar with no picture (it pointed at a file with no art
# yet, which was gone a moment later), the song showed twice with no album,
# and the picture never came back until the app was restarted. Now nothing
# reaches the music folder until it is a finished, sealed track.
_BENCH_PREFIXES = ('dnf-dl-', 'dnf-repair-')
# The encoder's name for a format where it differs from the file's. "ogg" is
# a container: the encoder only knows the codec inside it, and every download
# with OGG chosen in Settings failed on the unknown name.
_ENCODER_NAMES = {'ogg': 'vorbis'}
# What the encoder can hand back for the formats on offer.
_AUDIO_SUFFIXES = frozenset({'.mp3', '.m4a', '.flac', '.ogg', '.opus', '.aac', '.wav'})


def _bench() -> Path:
    return Path(tempfile.mkdtemp(prefix=_BENCH_PREFIXES[0]))


def sweep_benches(max_age: float = 6 * 3600) -> int:
    """Remove benches a crash or a power cut left behind.

    Only old ones: a second copy of the app may be using a fresh one right now.
    """

    removed = 0
    root = Path(tempfile.gettempdir())
    cutoff = time.time() - max_age
    try:
        entries = list(root.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if not entry.name.startswith(_BENCH_PREFIXES):
            continue
        try:
            if not entry.is_dir() or entry.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(entry, ignore_errors=True)
        removed += 1
    return removed


def _move_beside(source: Path, target: Path) -> None:
    """Move *source* onto *target*, across drives if it has to."""

    try:
        os.replace(source, target)
    except OSError:
        shutil.copyfile(source, target)
        source.unlink(missing_ok=True)


_target_locks: dict[str, threading.Lock] = {}
_target_locks_guard = threading.Lock()


def _lock_for(target: Path) -> threading.Lock:
    """The lock for one output name (a folder and a file name without its extension)."""

    key = str(target).lower()
    with _target_locks_guard:
        lock = _target_locks.get(key)
        if lock is None:
            lock = _target_locks[key] = threading.Lock()
        return lock


def _placement(target_dir: Path, basename: str, video_id: str) -> tuple[str, Optional[Path]]:
    """The name this recording is saved under, and its copy if it is already there.

    Two different recordings can share an artist and a title: an "Intro" on
    each of an artist's albums, a live take and the studio one. They used to
    share a file name too, so saving the second sealed it straight over the
    first, lyrics and all, and the first was simply gone. A name that holds a
    different recording that plays is left alone; this one gets " (2)", and
    so on. A copy that will not play is replaced: that is what downloading it
    again is for.
    """

    from . import vault  # noqa: PLC0415

    name = basename
    for number in range(2, 100):
        sealed = target_dir / f'{name}{vault.SUFFIX}'
        if not sealed.is_file():
            return name, None
        try:
            head, problem = vault.inspect(sealed)
        except Exception:
            head, problem = None, 'unreadable'
        if problem or not head:
            return name, None
        if video_id and head.get('video_id') == video_id:
            return name, sealed
        name = f'{basename} ({number})'
    return name, None


# Order matters: yt-dlp tries clients top-to-bottom and uses the first one
# that yields usable formats. `ios` and `android` lead because they still
# provide audio formats in containers without a JS runtime, even though
# YouTube now requires a GVS PO Token for their HTTPS/HLS formats (those
# are skipped with a warning, but lower-quality streams remain available).
# `web_embedded` and `web` need a JS runtime for signature/n-challenge
# solving; without one, they yield no audio at all: so they're kept as
# last-resort fallbacks only. `mweb` and `tv` are included as hail-mary
# clients: `mweb` needs a PO Token too, and `tv` is affected by a DRM
# experiment (yt-dlp #12563), but including them costs nothing.
_DEFAULT_YT_PLAYER_CLIENTS = (
    'android',
    'ios',
    'web_safari',
    'web_embedded',
    'mweb',
    'tv',
    'web',
)

# Warning substrings emitted by yt-dlp that are known-harmless: they mean
# some optional format sources are skipped, but other clients in the list
# still serve usable audio. Suppressed to keep logs readable.
_SUPPRESSED_YT_WARNING_FRAGMENTS = (
    'GVS PO Token which was not provided',
    'Some tv client https formats have been skipped as they are DRM',
    'Signature solving failed: Some formats may be missing',
    'n challenge solving failed: Some formats may be missing',
    'SABR-only streaming experiment',
    'formats have been skipped as they are missing a URL',
)


class _YtdlpLogger:
    @staticmethod
    def debug(msg: str) -> None:
        pass

    @staticmethod
    def info(msg: str) -> None:
        pass

    @staticmethod
    def warning(msg: str) -> None:
        if not any(frag in msg for frag in _SUPPRESSED_YT_WARNING_FRAGMENTS):
            logger.warning('yt-dlp: {}', msg)

    @staticmethod
    def error(msg: str) -> None:
        logger.error('yt-dlp: {}', msg)


# When the user is signed in we lead with clients that actually honour
# cookies: android/ios ignore them, which would throw the session away.
_AUTHED_YT_PLAYER_CLIENTS = ('tv_downgraded', 'web_safari', 'tv', 'mweb', 'android')


def _yt_player_clients() -> list[str]:
    raw = _env('DANNIFY_YT_PLAYER_CLIENTS', '').strip()
    if raw:
        clients = [c.strip() for c in raw.split(',') if c.strip()]
        if clients:
            return clients
    if _account_cookiefile() is not None:
        return list(_AUTHED_YT_PLAYER_CLIENTS)
    return list(_DEFAULT_YT_PLAYER_CLIENTS)


def _account_cookiefile():
    """The signed-in YouTube session as an in-memory cookie jar (or None).

    Sending it is what keeps YouTube from answering "Sign in to confirm
    you're not a bot" mid-download.
    """

    try:
        from . import account

        return account.ydl_cookiefile()
    except Exception:
        return None


def _yt_po_tokens() -> list[str]:
    """Comma-separated PO Tokens, each in the form ``<client>.<context>+<token>``.

    Example: ``mweb.gvs+ABC123,web.gvs+XYZ987``
    """
    raw = _env('DANNIFY_YT_PO_TOKEN', '').strip()
    if not raw:
        return []
    return [t.strip() for t in raw.split(',') if t.strip()]


class Downloader:
    """Wraps ``yt-dlp`` plus ``mutagen`` tagging."""

    def __init__(
        self,
        download_dir: Path | str,
        audio_format: str = 'mp3',
        audio_bitrate: str = '320',
        output_template: str = '{artists} - {title}',
        lyrics_providers: Optional[list[str]] = None,
        organize_by_artist: bool = False,
        lyrics_storage: str = 'sidecar',
    ):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.audio_format = audio_format
        self.audio_bitrate = audio_bitrate
        self.output_template = output_template
        self.lyrics_providers = list(lyrics_providers or [])
        self.organize_by_artist = organize_by_artist
        self.lyrics_storage = lyrics_storage

    @staticmethod
    def _artist_subdir(song: dict[str, Any]) -> str:
        # The first artist, a guest credited inside the name taken off: a
        # song credited as "Mbosso Ft Diamond Platnumz" made a folder of that
        # name beside Mbosso's own.
        from .library import _split_feat  # noqa: PLC0415

        artists = _split_feat([str(a) for a in song.get('artists') or [] if a])
        return _sanitize(artists[0] if artists else 'unknown', _FOLDER_LIMIT)

    def _target(self, song: dict[str, Any], subdir: Optional[str]) -> tuple[Path, str]:
        """The folder a song goes in, and its prefix relative to the library.

        An artist's folder is named after the artist, letters and all. It used
        to go through the playlist-name filter as well, which keeps only
        A to Z: "Beyonce" lost its accent, "P!nk" became "Pnk", and every
        artist written in another script, Japanese, Korean, Cyrillic, landed
        in one shared folder called "playlist".
        """

        if self.organize_by_artist:
            folder = self._artist_subdir(song)
            return self.download_dir / folder, f'{folder}/'
        return self._resolve_target_dir(subdir)

    def _format_basename(self, song: dict[str, Any]) -> str:
        artists = ', '.join(song.get('artists') or []) or 'Unknown Artist'
        template = self.output_template.replace('.{output-ext}', '')
        try:
            rendered = template.format(
                title=song.get('name', 'Unknown'),
                artists=artists,
                artist=artists,
                album=song.get('album_name', ''),
            )
        except (KeyError, IndexError):
            rendered = f'{artists} - {song.get("name", "Unknown")}'
        return _sanitize(rendered)

    def existing_filename_for(
        self,
        song: dict[str, Any],
        subdir: Optional[str] = None,
    ) -> Optional[str]:
        """Return the on-disk filename for ``song`` if any matching file exists.

        Mirrors :meth:`download`'s post-conversion path resolution: prefers
        ``{basename}.{audio_format}`` and falls back to any
        ``{basename}.*`` since yt-dlp occasionally keeps the upstream
        extension (opus, m4a). Returns ``None`` when no file matches.

        When ``subdir`` is given the lookup is scoped to that
        sub-directory and the returned name is relative to
        ``download_dir`` (``<subdir>/<file>.<ext>``).
        """

        import glob as _glob

        from . import vault  # noqa: PLC0415

        basename = self._format_basename(song)
        target_dir, prefix = self._target(song, subdir)
        # Saved songs are containers: that is the copy to find first.
        for primary in (
            target_dir / f'{basename}{vault.SUFFIX}',
            target_dir / f'{basename}.{self.audio_format}',
        ):
            if primary.exists():
                return f'{prefix}{primary.name}'
        # Escaped: "Song [Live]" is a pattern to glob, and matched nothing.
        # Audio only: the lyrics file beside a song shares its name.
        for candidate in sorted(target_dir.glob(f'{_glob.escape(basename)}.*')):
            if candidate.is_file() and candidate.suffix.lower() in _AUDIO_SUFFIXES:
                return f'{prefix}{candidate.name}'
        return None

    def _resolve_target_dir(self, subdir: Optional[str]) -> tuple[Path, str]:
        """Return ``(target_dir, relative_prefix)`` for an optional subdir.

        ``relative_prefix`` is empty when ``subdir`` is not used and
        otherwise terminates with ``'/'`` so callers can build the
        download-dir-relative path with simple concatenation.
        """

        if not subdir:
            return self.download_dir, ''
        safe = sanitize_playlist_name(subdir)
        return self.download_dir / safe, f'{safe}/'

    def download(  # noqa: PLR0914
        self,
        song: dict[str, Any],
        progress_cb: Optional[ProgressCallback] = None,
        subdir: Optional[str] = None,
        cancel: Optional[threading.Event] = None,
    ) -> str:
        """Download ``song`` and return the resulting file name.

        When ``subdir`` is provided the file is written under
        ``download_dir/<sanitized_subdir>/`` and the returned name is
        relative to ``download_dir`` (``<subdir>/<file>.<ext>``). This
        is how playlist downloads are grouped into per-playlist folders.
        """

        # Real stages, reported as they happen. Finding a source and
        # resolving the stream take ten seconds or so before a single byte
        # arrives; without these the bar just sat at zero and looked stuck.
        def stage(percent: float, message: str) -> None:
            if progress_cb is not None:
                try:
                    progress_cb(percent, message)
                except Exception:
                    logger.opt(exception=True).debug('progress hook error')

        stage(0.0, 'Finding source')

        video_id = song.get('youtube_id')
        if not video_id and (song.get('source') == 'youtube'):
            video_id = song.get('song_id')

        match: Optional[dict[str, Any]] = None
        if not video_id:
            video_id, match = find_match(song)
        elif not song.get('album_name') or not song.get('cover_url'):
            # We already have a target video, but the metadata is incomplete.
            # Look up the YT Music entry for THIS specific videoId so we
            # don't risk switching to a karaoke / cover that happens to
            # rank higher.
            try:
                match = find_match_for_video(song, video_id)
            except Exception:
                logger.opt(exception=True).debug('enrichment match failed')
                match = None

        if not video_id:
            raise RuntimeError(
                f'Could not find a YouTube match for {song.get("name")!r}'
            )

        song = enrich_from_match(song, match)
        stage(2.0, 'Preparing')

        basename = self._format_basename(song)
        target_dir, rel_prefix = self._target(song, subdir)
        target_dir.mkdir(parents=True, exist_ok=True)

        # One download at a time per file name. Two downloads of the same song
        # (a double click, a playlist that lists it twice, a monitored
        # playlist catching up while the user saves it by hand) used to write
        # the same files at the same time, and the one that lost the race
        # cleaned up after itself by deleting the song the other had just
        # saved. The second now waits, and then finds the song already there.
        with _lock_for(target_dir / basename):
            basename, already = _placement(target_dir, basename, video_id)
            if already is not None:
                stage(100.0, 'Done')
                return f'{rel_prefix}{already.name}'
            if cancel is not None and cancel.is_set():
                raise DownloadStopped()
            bench = _bench()
            try:
                return self._fetch_and_seal(
                    song, video_id, target_dir, rel_prefix, basename, stage, progress_cb,
                    cancel, bench,
                )
            except BaseException:
                if cancel is not None and cancel.is_set():
                    raise DownloadStopped() from None
                raise
            finally:
                # Whatever the download left, finished or not. The music folder
                # never saw any of it.
                shutil.rmtree(bench, ignore_errors=True)

    def _fetch_and_seal(  # noqa: PLR0913, PLR0914, PLR0915
        self,
        song: dict[str, Any],
        video_id: str,
        target_dir: Path,
        rel_prefix: str,
        basename: str,
        stage: Callable[[float, str], None],
        progress_cb: Optional[ProgressCallback],
        cancel: Optional[threading.Event] = None,
        bench: Optional[Path] = None,
    ) -> str:
        """Download, tag and seal one song. Called with its file name locked.

        Everything up to the seal happens on *bench*, a folder of this
        download's own outside the music folder. The only thing that ever
        arrives in *target_dir* is the finished container, and its lyrics.
        """

        work = Path(bench) if bench is not None else target_dir
        out_template = str(work / f'{basename}.%(ext)s')

        def hook(data: dict[str, Any]) -> None:
            # Raised outside the try below on purpose: yt-dlp stops the
            # transfer when a progress hook raises this.
            if cancel is not None and cancel.is_set():
                raise yt_dlp.utils.DownloadCancelled('stopped from the queue')
            if progress_cb is None:
                return
            try:
                status = data.get('status')
                if status == 'downloading':
                    total = (
                        data.get('total_bytes')
                        or data.get('total_bytes_estimate')
                        or 0
                    )
                    downloaded = data.get('downloaded_bytes') or 0
                    if total:
                        # 4..92 so the bar has visible room before and after
                        # the transfer itself.
                        progress_cb(
                            4.0 + min(88.0, downloaded / total * 88.0),
                            'Downloading',
                        )
                    else:
                        progress_cb(4.0, 'Downloading')
                elif status == 'finished':
                    progress_cb(93.0, 'Converting')
            except Exception:
                logger.opt(exception=True).debug('progress hook error')

        ydl_opts = {
            # AAC in MP4 when there is one, so it is kept as it comes rather
            # than converted (see INTERNAL_FORMAT in api.py).
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': out_template,
            'quiet': True,
            'noprogress': True,
            'logger': _YtdlpLogger(),
            'noplaylist': True,
            # Certificates are checked. They were not, on this one connection
            # of all of them: the one that carries the signed-in YouTube
            # session and fetches the player code that then gets run. Anyone
            # on the same Wi-Fi could have read the first and replaced the
            # second.
            'overwrites': True,
            # A partial file from an earlier attempt is not resumed: a retry
            # can match a different video, and the two would be spliced.
            'continuedl': False,
            'progress_hooks': [hook],
            # Resilience against flaky DNS/network in containers.
            # googlevideo.com CDN hosts are short-lived shards and a single
            # transient EAI_AGAIN/timeout used to abort the whole download.
            'retries': 10,
            'fragment_retries': 10,
            'extractor_retries': 3,
            'socket_timeout': 30,
            # The default `web` player_client is the one most aggressively
            # gated by YouTube's "Sign in to confirm you're not a bot"
            # check on datacenter IPs. `tv` and `mweb` almost always
            # bypass it. Order matters: yt-dlp tries them in sequence.
            'extractor_args': {
                'youtube': {'player_client': _yt_player_clients()}
            },
            # Light pacing so we don't trigger 429 rate limits when the
            # user fires off multiple downloads back-to-back.
            'sleep_interval_requests': 1,
            **(
                {'cookiefile': _account_cookiefile()}
                if _account_cookiefile() is not None
                else {}
            ),
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': _ENCODER_NAMES.get(self.audio_format, self.audio_format),
                    'preferredquality': self.audio_bitrate,
                }
            ],
        }
        # Same JS challenge solver the player uses: without it YouTube
        # hands back storyboards and every download fails.
        from .jsruntime import apply as _apply_js

        _apply_js(ydl_opts)

        # Many container setups have IPv6 advertised but unroutable for
        # googlevideo.com, which surfaces as EAI_AGAIN on the AAAA lookup.
        # Setting DANNIFY_FORCE_IPV4=1 binds yt-dlp to IPv4 only.
        if _env('DANNIFY_FORCE_IPV4', '').strip() in {
            '1',
            'true',
            'yes',
        }:
            ydl_opts['source_address'] = '0.0.0.0'

        # Optional cookie support for the rare case where even alternate
        # player_clients get challenged. DANNIFY_COOKIES_FILE points at a
        # Netscape-format cookies.txt; DANNIFY_COOKIES_FROM_BROWSER takes
        # "<browser>" or "<browser>:<profile>" (e.g. "firefox" or
        # "chrome:Default").
        cookies_file = _env('DANNIFY_COOKIES_FILE', '').strip()
        if cookies_file:
            ydl_opts['cookiefile'] = cookies_file
        cookies_browser = _env('DANNIFY_COOKIES_FROM_BROWSER', '').strip()
        if cookies_browser:
            parts = cookies_browser.split(':', 1)
            ydl_opts['cookiesfrombrowser'] = (
                (parts[0],) if len(parts) == 1 else (parts[0], parts[1])
            )

        # --- Fast path: skip the extraction yt-dlp would redo. ---
        # The player has usually already resolved this track, and even cold
        # the direct resolver answers in well under a second where a full
        # extraction takes fifteen to twenty. Handing yt-dlp the finished
        # URL turns that dead time into bytes on disk.
        #
        # `http_chunk_size` is not optional here. googlevideo throttles a
        # plain sequential GET on these URLs to about 30 KiB/s while
        # serving ranged requests at full speed; measured on one track,
        # 141 s without it against 6.7 s with it. It also means the total
        # size is known from the first callback, so the bar shows real
        # progress instead of sitting on zero.
        url = f'https://music.youtube.com/watch?v={video_id}'
        try:
            from . import streaming as _streaming

            resolved = _streaming.resolve_for_download(video_id)
        except Exception:
            logger.opt(exception=True).debug('fast download resolve failed')
            resolved = None
        if resolved:
            url = resolved
            ydl_opts['http_chunk_size'] = 1024 * 1024
            # A bare CDN URL has no player response to extract, so the
            # client list and its JS solving are dead weight.
            ydl_opts.pop('extractor_args', None)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            stage(3.0, 'Connecting')
            ydl.download([url])
        if cancel is not None and cancel.is_set():
            raise DownloadStopped()

        final_path = work / f'{basename}.{self.audio_format}'
        if not final_path.exists():
            # yt-dlp sometimes keeps the upstream extension for opus/m4a.
            # Compared by name rather than globbed: a title with brackets in
            # it ("Song [Live]") is a pattern to glob, and matched nothing.
            for candidate in sorted(work.iterdir()) if work.is_dir() else ():
                if (
                    candidate.is_file()
                    and candidate.stem == basename
                    and candidate.suffix.lower() in _AUDIO_SUFFIXES
                ):
                    final_path = candidate
                    break
        if not final_path.is_file():
            raise RuntimeError('The download finished but left no audio file.')

        # ── Genre enrichment via iTunes Search API ──────────────
        if not song.get('genre'):
            try:
                genre = _fetch_itunes_genre(song)
                if genre:
                    song = {**song, 'genre': genre}
            except Exception:
                logger.opt(exception=True).debug(
                    'iTunes genre lookup failed for {}', final_path
                )

        try:
            stage(95.0, 'Tagging')
            embed_metadata(final_path, song)
        except Exception:
            logger.exception('Failed to embed metadata into {}', final_path)

        # Store the YouTube videoId in a custom tag so the library index
        # can find this exact file later in O(1) regardless of rename/move.
        try:
            embed_video_id(final_path, video_id)
        except Exception:
            logger.opt(exception=True).debug(
                'Could not embed video_id tag into {}', final_path
            )

        if self.lyrics_providers:
            try:
                fetched = lyrics_mod.fetch(song, self.lyrics_providers)
            except Exception:
                logger.exception('Lyrics fetch crashed for {}', final_path)
                fetched = None
            if fetched is not None:
                try:
                    embed_lyrics(
                        final_path,
                        fetched,
                        write_sidecar=self.lyrics_storage != 'central',
                    )
                except Exception:
                    logger.exception(
                        'Failed to embed lyrics into {}', final_path
                    )
                # Central storage: write the .lrc into the indexed folder.
                if self.lyrics_storage == 'central' and fetched.has_any():
                    try:
                        # Local import avoids a backend-package import cycle.
                        from . import lyrics_index as _li

                        text = fetched.synced or fetched.plain or ''
                        if text:
                            artists = song.get('artists') or []
                            _li.store(
                                artists[0] if artists else '',
                                song.get('name', '') or '',
                                text,
                            )
                    except Exception:
                        logger.opt(exception=True).debug(
                            'Central lyrics store failed for {}', final_path
                        )

        # Seal it. Everything above works on an ordinary tagged file, which is
        # why this is last: the tags, the video id and the lyrics all go in
        # first, then the whole thing becomes a container that only this
        # installation can open. If there is no key, the file is left as it
        # was rather than lost.
        from . import vault  # noqa: PLC0415

        if cancel is not None and cancel.is_set():
            raise DownloadStopped()

        # Not optional, and not best effort. Leaving the plain file behind was
        # the one outcome this whole thing exists to prevent: an ordinary audio
        # file in the music folder that any player can open, delivered by a
        # download that reported itself finished. A track that cannot be sealed
        # does not get saved at all, and the reason is said out loud.
        if not vault.ready():
            final_path.unlink(missing_ok=True)
            raise vault.StorageUnavailable(
                'This song could not be saved. See the message at the top of '
                'the window.'
            )
        try:
            artists = song.get('artists') or []
            # Read what is actually in the file. A hand-made four field header
            # was throwing away the duration, the track number, the genre and
            # the artist list that embed_metadata had just written, so every
            # freshly downloaded track came back with no length and no album
            # in the library, and repair() had no way to tell it was missing
            # because the header claimed to be current.
            meta = vault._tags_of(final_path)
            for field, value in (
                ('title', song.get('name') or ''),
                ('artist', artists[0] if artists else ''),
                ('album', song.get('album_name') or ''),
                ('video_id', video_id),
            ):
                if value and not meta.get(field):
                    meta[field] = value
            # The list the song came with is the right one. Reading it back
            # from the file's own tags goes through a split on separators
            # that can cut a name in two ("X Ambassadors"), so it only fills
            # in when the song had none.
            if artists:
                from .library import _split_feat  # noqa: PLC0415

                meta['artists'] = _split_feat([str(a) for a in artists if a])
            # Which artists these are, by their YouTube Music ids: two with
            # one name are told apart by it, and the right one found online.
            ids = [
                {'name': str(a['name']), 'id': str(a['id'])}
                for a in (song.get('artist_ids') or [])
                if isinstance(a, dict) and a.get('name') and a.get('id')
            ]
            if ids:
                meta['artist_ids'] = ids
            target = target_dir / f'{basename}{vault.SUFFIX}'
            sealed = vault.seal(final_path, target, meta)
        except Exception as exc:
            logger.opt(exception=True).error('Could not seal {}', final_path)
            # Only what this attempt wrote. seal() puts a finished container
            # in place with one rename at the very end, so a .dnf already
            # there is an earlier, good copy of this song and it stays.
            final_path.unlink(missing_ok=True)
            (target_dir / f'{basename}{vault.SUFFIX}.part').unlink(missing_ok=True)
            raise RuntimeError(
                'This song downloaded but could not be saved, so it was not kept.'
            ) from exc

        # The lyrics file was written beside the plain copy on the bench. It
        # belongs beside the song.
        lyric = work / f'{basename}.lrc'
        if work != target_dir and lyric.is_file():
            try:
                _move_beside(lyric, target_dir / lyric.name)
            except OSError:
                logger.opt(exception=True).warning('Could not keep the lyrics for {}', sealed)
        try:
            _remember(self.download_dir, sealed, song, video_id)
        except Exception:
            # The song is saved; the note of what it is can be rebuilt.
            logger.opt(exception=True).warning('Could not note {} in the index', sealed)
        final_path = sealed

        if progress_cb:
            progress_cb(100.0, 'Done')
        return f'{rel_prefix}{final_path.name}'


def _remember(root: Path, sealed: Path, song: dict, video_id: str) -> None:
    """Keep a note of what each sealed file is, in the library's own index.

    The header inside a container is encrypted too, so a song that can no
    longer be opened would otherwise be a file nobody could even identify.
    This costs a few hundred bytes and turns that into "download it again",
    as exactly the same recording.
    """

    from . import vault  # noqa: PLC0415

    try:
        rel = Path(sealed).relative_to(Path(root)).as_posix()
    except ValueError:
        return
    artists = song.get('artists') or []
    vault.note_track(root, rel, {
        'title': song.get('name', '') or '',
        'artist': artists[0] if artists else '',
        'video_id': video_id,
    })


def _download_cover(url: str) -> Optional[bytes]:
    if not url:
        return None
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except Exception:
        logger.opt(exception=True).warning('Failed to fetch cover art {}', url)
        return None
    return response.content


def _album_track_index_for_tags(
    song: dict[str, Any],
) -> tuple[Optional[int], Optional[int]]:
    """Normalize ``track_number`` / ``album_track_total`` for tagging frames."""
    raw_n = song.get('track_number')
    raw_tot = song.get('album_track_total')
    try:
        n = int(raw_n)
    except (TypeError, ValueError):
        return None, None
    if n <= 0:
        return None, None
    tot: Optional[int] = None
    if raw_tot is not None and raw_tot != '':
        try:
            t = int(raw_tot)
        except (TypeError, ValueError):
            pass
        else:
            if t > 0:
                tot = t
    return n, tot


def _recording_date_for_tags(song: dict[str, Any]) -> str:
    """Prefer full ``YYYY-MM-DD`` from Spotify; fall back to year-only."""

    rd = str(song.get('release_date') or '').strip()
    if rd:
        return rd
    return str(song.get('year') or '').strip()


def embed_metadata(path: Path, song: dict[str, Any]) -> None:
    if not path.exists():
        return

    title = song.get('name', '')
    artists = song.get('artists') or []
    album = song.get('album_name', '') or ''
    recording_date = _recording_date_for_tags(song)
    genre = (song.get('genre') or '').strip()
    cover_bytes = _download_cover(song.get('cover_url', ''))
    track_number, album_track_total = _album_track_index_for_tags(song)
    if track_number is None:
        logger.info(
            'Tag embed: no track_number/disc position for file={} '
            'song_id={} title={!r} raw_track_number={!r} raw_total={!r}',
            path.name,
            song.get('song_id'),
            title,
            song.get('track_number'),
            song.get('album_track_total'),
        )
    if not recording_date:
        logger.info(
            'Tag embed: no recording date (year/release_date) for file={} '
            'song_id={} title={!r} raw_year={!r} raw_release_date={!r}',
            path.name,
            song.get('song_id'),
            title,
            song.get('year'),
            song.get('release_date'),
        )
    logger.debug(
        'Tag embed summary: {} track={}/{} date={!r}',
        path.name,
        track_number,
        album_track_total,
        recording_date,
    )

    suffix = path.suffix.lower().lstrip('.')

    if suffix == 'mp3':
        _tag_mp3(
            path,
            title,
            artists,
            album,
            recording_date,
            genre,
            cover_bytes,
            track_number,
            album_track_total,
        )
    elif suffix in {'m4a', 'mp4', 'aac'}:
        _tag_mp4(
            path,
            title,
            artists,
            album,
            recording_date,
            genre,
            cover_bytes,
            track_number,
            album_track_total,
        )
    elif suffix == 'flac':
        _tag_flac(
            path,
            title,
            artists,
            album,
            recording_date,
            genre,
            cover_bytes,
            track_number,
            album_track_total,
        )
    elif suffix in {'ogg', 'oga'}:
        _tag_ogg_vorbis(
            path,
            title,
            artists,
            album,
            recording_date,
            genre,
            track_number,
            album_track_total,
        )
    elif suffix == 'opus':
        _tag_opus(
            path,
            title,
            artists,
            album,
            recording_date,
            genre,
            track_number,
            album_track_total,
        )


def _tag_mp3(
    path: Path,
    title: str,
    artists: list[str],
    album: str,
    year: str,
    genre: str,
    cover_bytes: Optional[bytes],
    track_number: Optional[int],
    album_track_total: Optional[int],
) -> None:
    audio = MP3(str(path), ID3=ID3)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.delall('APIC')
    audio.tags.add(TIT2(encoding=3, text=title))
    if artists:
        audio.tags.add(TPE1(encoding=3, text='/'.join(artists)))
        audio.tags.add(TPE2(encoding=3, text=artists[0]))
    if album:
        audio.tags.add(TALB(encoding=3, text=album))
    if track_number is not None:
        trck = (
            f'{track_number}/{album_track_total}'
            if album_track_total is not None
            else str(track_number)
        )
        audio.tags.add(TRCK(encoding=3, text=trck))
    if year:
        audio.tags.add(TDRC(encoding=3, text=year))
    if genre:
        audio.tags.add(TCON(encoding=3, text=genre))
    if cover_bytes:
        audio.tags.add(
            APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=cover_bytes,
            )
        )
    audio.save(v2_version=3)


def _tag_mp4(
    path: Path,
    title: str,
    artists: list[str],
    album: str,
    year: str,
    genre: str,
    cover_bytes: Optional[bytes],
    track_number: Optional[int],
    album_track_total: Optional[int],
) -> None:
    audio = MP4(str(path))
    audio['\xa9nam'] = title
    if artists:
        audio['\xa9ART'] = artists
        audio['aART'] = [artists[0]]
    if album:
        audio['\xa9alb'] = album
    if track_number is not None:
        total = album_track_total if album_track_total is not None else 0
        audio['trkn'] = [(track_number, total)]
    if year:
        audio['\xa9day'] = year
    if genre:
        audio['\xa9gen'] = genre
    if cover_bytes:
        audio['covr'] = [
            MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)
        ]
    audio.save()


def _tag_flac(
    path: Path,
    title: str,
    artists: list[str],
    album: str,
    year: str,
    genre: str,
    cover_bytes: Optional[bytes],
    track_number: Optional[int],
    album_track_total: Optional[int],
) -> None:
    audio = FLAC(str(path))
    audio['title'] = title
    if artists:
        audio['artist'] = artists
        audio['albumartist'] = artists[0]
    if album:
        audio['album'] = album
    if track_number is not None:
        audio['tracknumber'] = str(track_number)
        if album_track_total is not None:
            audio['tracktotal'] = str(album_track_total)
    if year:
        audio['date'] = year
    if genre:
        audio['genre'] = genre
    if cover_bytes:
        picture = Picture()
        picture.data = cover_bytes
        picture.type = 3
        picture.mime = 'image/jpeg'
        audio.clear_pictures()
        audio.add_picture(picture)
    audio.save()


def _tag_ogg_vorbis(
    path: Path,
    title: str,
    artists: list[str],
    album: str,
    year: str,
    genre: str,
    track_number: Optional[int],
    album_track_total: Optional[int],
) -> None:
    audio = OggVorbis(str(path))
    _apply_vorbis_comments(
        audio,
        title,
        artists,
        album,
        year,
        genre,
        track_number,
        album_track_total,
    )
    audio.save()


def _tag_opus(
    path: Path,
    title: str,
    artists: list[str],
    album: str,
    year: str,
    genre: str,
    track_number: Optional[int],
    album_track_total: Optional[int],
) -> None:
    audio = OggOpus(str(path))
    _apply_vorbis_comments(
        audio,
        title,
        artists,
        album,
        year,
        genre,
        track_number,
        album_track_total,
    )
    audio.save()


def _apply_vorbis_comments(
    audio,
    title,
    artists,
    album,
    year,
    genre,
    track_number: Optional[int],
    album_track_total: Optional[int],
):
    audio['title'] = title
    if artists:
        audio['artist'] = artists
        audio['albumartist'] = artists[0]
    if album:
        audio['album'] = album
    if track_number is not None:
        audio['TRACKNUMBER'] = str(track_number)
        if album_track_total is not None:
            audio['TRACKTOTAL'] = str(album_track_total)
    if year:
        audio['date'] = year
    if genre:
        audio['genre'] = genre


def embed_video_id(path: Path, video_id: str) -> None:
    """Persist the YouTube videoId into *path*'s metadata.

    Uses a format-appropriate frame keyed under ``DANNIFY_VIDEO_ID``:
      * MP3 → ID3 ``TXXX:DANNIFY_VIDEO_ID``
      * MP4/M4A/AAC → custom freeform atom ``----:com.dannify:VIDEO_ID``
      * FLAC/OGG/Opus → Vorbis comment ``DANNIFY_VIDEO_ID``

    Cheap to write (mutagen's in-place save) and lets :mod:`library`
    surface ``video_id`` so the player can locate the local copy of any
    streamed song instantly.
    """

    if not path.exists() or not video_id or not isinstance(video_id, str):
        return
    suffix = path.suffix.lower().lstrip('.')
    try:
        if suffix == 'mp3':
            audio = MP3(str(path), ID3=ID3)
            if audio.tags is None:
                audio.add_tags()
            # Replace any existing instance of the same description.
            existing = [
                f for f in audio.tags.getall('TXXX')
                if getattr(f, 'desc', '') == 'DANNIFY_VIDEO_ID'
            ]
            for f in existing:
                audio.tags.delall(f.HashKey if hasattr(f, 'HashKey') else 'TXXX:DANNIFY_VIDEO_ID')
            audio.tags.add(
                TXXX(encoding=3, desc='DANNIFY_VIDEO_ID', text=video_id)
            )
            audio.save(v2_version=3)
        elif suffix in {'m4a', 'mp4', 'aac'}:
            audio = MP4(str(path))
            audio['----:com.dannify:VIDEO_ID'] = [video_id.encode('utf-8')]
            audio.save()
        elif suffix == 'flac':
            audio = FLAC(str(path))
            audio['DANNIFY_VIDEO_ID'] = video_id
            audio.save()
        elif suffix in {'ogg'}:
            audio = OggVorbis(str(path))
            audio['DANNIFY_VIDEO_ID'] = video_id
            audio.save()
        elif suffix == 'opus':
            audio = OggOpus(str(path))
            audio['DANNIFY_VIDEO_ID'] = video_id
            audio.save()
    except Exception:
        logger.opt(exception=True).debug(
            'embed_video_id failed for {}', path
        )


def embed_lyrics(
    path: Path,
    lyrics: 'lyrics_mod.Lyrics',
    write_sidecar: bool = True,
) -> None:
    """Embed plain lyrics into the audio tag and (optionally) write a .lrc
    sidecar next to it when synced lyrics are available.

    ``write_sidecar=False`` is used when the user configured central
    lyrics storage: the caller writes the .lrc into the indexed folder
    instead so we don't double-store."""

    if not path.exists() or not lyrics.has_any():
        return

    if lyrics.synced and write_sidecar:
        sidecar = path.with_suffix('.lrc')
        try:
            sidecar.write_text(lyrics.synced, encoding='utf-8')
        except OSError:
            logger.opt(exception=True).warning(
                'Could not write LRC sidecar {}', sidecar
            )

    text = lyrics.plain or _strip_lrc_timestamps(lyrics.synced or '')
    if not text:
        return

    suffix = path.suffix.lower().lstrip('.')
    if suffix == 'mp3':
        audio = MP3(str(path), ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.delall('USLT')
        audio.tags.add(USLT(encoding=3, lang='eng', desc='', text=text))
        audio.save(v2_version=3)
    elif suffix in {'m4a', 'mp4', 'aac'}:
        audio = MP4(str(path))
        audio['\xa9lyr'] = text
        audio.save()
    elif suffix == 'flac':
        audio = FLAC(str(path))
        audio['lyrics'] = text
        audio.save()
    elif suffix in {'ogg', 'oga'}:
        audio = OggVorbis(str(path))
        audio['lyrics'] = text
        audio.save()
    elif suffix == 'opus':
        audio = OggOpus(str(path))
        audio['lyrics'] = text
        audio.save()


def _strip_lrc_timestamps(synced: str) -> str:
    cleaned = _re.sub(r'\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]', '', synced)
    return '\n'.join(
        line.strip() for line in cleaned.splitlines() if line.strip()
    )
