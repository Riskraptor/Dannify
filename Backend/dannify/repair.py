"""Getting saved tracks that will not play working again.

A saved track stops working in one of two ways (see vault.inspect). It can be
locked: sealed with a key this installation does not have. Or it can be
damaged: cut short while it was being written. Either way the audio in it is
out of reach. What the track WAS is not: the header names the video it came
from when it opens, and the plain index kept beside the music names it when
it does not.

So a repair downloads the track again and puts it back at exactly the same
path. The same path is the point. Playlists, the queue, recently played and
the saved session all know a track by where it is, and a repaired track in a
new place would be a new track to all of them and a missing one to the rest.

The file being replaced is kept for a fortnight in the data folder rather than
deleted. It cannot be played here, which is why it is being replaced, but if
the key it was sealed with ever turns up, it is the original.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from . import vault

# Where replaced files are kept, inside the data folder, and for how long.
KEPT = 'replaced'
KEEP_DAYS = 14

# Why a repair did not work. The window turns each into a sentence.
NOT_FOUND = 'not_found'  # nothing online matches it any more
OFFLINE = 'offline'
IN_USE = 'in_use'  # something had the file open the whole time
UNAVAILABLE = 'unavailable'  # nothing can be saved right now
MISSING = 'missing'  # not there, or not a saved track
FAILED = 'failed'

_VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')


# ---------------------------------------------------------------------------
# One track
# ---------------------------------------------------------------------------
def identify(base: Path, path: Path, head: Optional[dict[str, Any]]) -> dict[str, Any]:
    """What a saved track is, as a song the downloader can fetch again.

    The header knows best when it can be read. When it cannot, the library's
    index usually knows the video it came from, which gets back exactly the
    recording that was saved rather than whatever a search ranks first. The
    filename is the last resort: it is always "Artists - Title".
    """

    from .library import _split_artists  # noqa: PLC0415  (circular at import)

    head = head or {}
    notes = vault.lookup(base, path)

    named_artist, _, named_title = path.stem.partition(' - ')
    if not named_title:
        named_artist, named_title = '', path.stem

    title = str(head.get('title') or notes.get('title') or named_title).strip()

    # The fullest list of artists wins: the header's own list, then the one in
    # the filename, which has every credit where the indexes kept only the
    # first. The search for a match is better for all of them.
    stored = head.get('artists')
    if isinstance(stored, list) and any(stored):
        artists = [str(a) for a in stored if a]
    else:
        artists = _split_artists(named_artist)
        if not artists:
            single = str(head.get('artist') or notes.get('artist') or '').strip()
            artists = [single] if single else []

    video_id = str(head.get('video_id') or notes.get('video_id') or '').strip()
    song: dict[str, Any] = {
        'name': title,
        'artists': artists,
        'album_name': str(head.get('album') or ''),
        'duration': _int(head.get('duration')),
        'song_id': video_id or f'repair:{path.name}',
    }
    if _int(head.get('track_number')):
        song['track_number'] = _int(head.get('track_number'))
    if head.get('genre'):
        song['genre'] = str(head['genre'])
    if _VIDEO_ID.match(video_id):
        song['youtube_id'] = video_id
    return song


def fix(
    root: Path,
    rel: str,
    downloader: Any,
    data_dir: Optional[Path] = None,
    force: bool = False,
    progress: Optional[Callable[[float, str], None]] = None,
) -> tuple[str, str]:
    """Repair one saved track, in place.

    Returns ``(state, reason)``: 'fixed', 'fine' (nothing was wrong with it,
    so nothing was done) or 'failed' with one of the reasons above. The old
    file is only touched once a new one has been downloaded, sealed and read
    back whole, so a repair that fails for any reason leaves things exactly as
    they were.

    *force* repairs a track that looks fine: the window asks for that when a
    file failed to play for a reason nothing here can see.
    """

    try:
        base = Path(root).resolve()
        path = (base / rel).resolve()
        path.relative_to(base)
    except (ValueError, RuntimeError, OSError):
        return 'failed', MISSING
    if path.suffix.lower() != vault.SUFFIX or not path.is_file():
        return 'failed', MISSING

    head, problem = vault.inspect(path)
    if not problem and not force:
        return 'fine', ''
    if not vault.ready():
        return 'failed', UNAVAILABLE
    if downloader is None:
        return 'failed', FAILED

    _wait_for_conversion()
    song = identify(base, path, head)

    # No video to go back to: search, but only accept the track itself. The
    # downloader's own search settles for the closest thing it finds, which
    # is right for a new download somebody is watching and wrong here, where
    # it would put some other song in place of theirs without a word.
    if not song.get('youtube_id'):
        from . import providers  # noqa: PLC0415

        try:
            video_id, match = providers.find_match(song)
        except Exception as exc:
            logger.opt(exception=True).warning('search for {} failed', rel)
            return 'failed', _reason(exc)
        if not video_id or not _confident(song, match):
            logger.info(
                'nothing online is clearly {!r} by {!r}; not repairing {}',
                song['name'], ', '.join(song['artists']), rel,
            )
            return 'failed', NOT_FOUND if _online() else OFFLINE
        song['youtube_id'] = video_id
        try:
            song = providers.enrich_from_match(song, match)
        except Exception:
            logger.opt(exception=True).debug('could not fill in details for {}', rel)

    logger.info(
        'repairing {} ({}), as {!r} by {!r}{}',
        rel, problem or 'asked to', song['name'], ', '.join(song['artists']),
        f' [{song["youtube_id"]}]' if song.get('youtube_id') else '',
    )

    # Downloaded somewhere of its own, outside the music folder: a plain copy
    # sits there for the few seconds before it is sealed, and it must never be
    # somewhere the library, or anybody browsing the folder, can see it.
    from . import bench as _bench_mod  # noqa: PLC0415

    bench = _bench_mod.make('dnf-repair-')
    try:
        from .downloader import Downloader  # noqa: PLC0415

        worker = Downloader(
            bench,
            audio_format=getattr(downloader, 'audio_format', 'mp3'),
            audio_bitrate=getattr(downloader, 'audio_bitrate', '320'),
            output_template=getattr(downloader, 'output_template', '{artists} - {title}'),
            lyrics_providers=list(getattr(downloader, 'lyrics_providers', None) or []),
            organize_by_artist=False,
            lyrics_storage=getattr(downloader, 'lyrics_storage', 'sidecar'),
        )
        try:
            name = worker.download(song, progress)
        except Exception as exc:
            logger.opt(exception=True).warning('could not download {} again', rel)
            return 'failed', _reason(exc)

        fresh = bench / name
        fresh_head, wrong = (
            vault.inspect(fresh) if fresh.is_file() else (None, vault.DAMAGED)
        )
        if fresh_head is None or wrong:
            logger.error('the new copy of {} did not check out: {}', rel, wrong or 'unreadable')
            return 'failed', FAILED

        # Deleted while it was downloading: somebody meant that. The swap below
        # would happily create the path, bringing back a track they had just
        # removed, so it is checked again at the last moment.
        if not path.is_file():
            logger.info('{} was removed during its repair; not putting it back', rel)
            return 'failed', MISSING

        kept = _keep(path, base, data_dir)
        try:
            _place(fresh, path)
        except OSError:
            logger.opt(exception=True).warning('could not put {} back in place', rel)
            if kept is not None:
                _unlink(kept)
            return 'failed', IN_USE

        # Lyrics come down with the track when there are any, as a file beside
        # it. Named after the track they belong to, not the download.
        lyric = fresh.with_suffix('.lrc')
        if lyric.is_file():
            try:
                _place(lyric, path.with_suffix('.lrc'))
            except OSError:
                logger.opt(exception=True).debug('lyrics for {} not moved', rel)

        _renote(base, path, fresh_head)
        logger.info('repaired {}', rel)
        return 'fixed', ''
    finally:
        shutil.rmtree(bench, ignore_errors=True)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _key(raw: Any) -> str:
    """A track's path inside the music folder, spelled one way."""

    return str(raw or '').replace('\\', '/').strip().lstrip('/')


def _norm(text: Any) -> str:
    """Lower case, letters and digits only, in any script."""

    return ' '.join(
        ''.join(ch if ch.isalnum() else ' ' for ch in str(text or '').casefold()).split()
    )


def _confident(song: dict[str, Any], match: Optional[dict[str, Any]]) -> bool:
    """Whether a search result is this track, and not just something like it.

    The title has to be the same, allowing for what uploads add to it ("Live",
    "Official Audio"), and one of the artists has to be there, credited or in
    the title the way a channel names its uploads.
    """

    if not match or not match.get('videoId'):
        return False
    want = _norm(song.get('name'))
    got = _norm(match.get('title'))
    if not want or not got:
        return False
    title_ok = want in got or got in want
    if not title_ok:
        words = set(want.split())
        title_ok = len(words & set(got.split())) >= 0.6 * len(words)

    wanted = [_norm(a) for a in (song.get('artists') or []) if _norm(a)]
    if not wanted:
        return title_ok
    credited = [
        _norm(a.get('name')) for a in (match.get('artists') or []) if isinstance(a, dict)
    ]
    artist_ok = any(
        w and c and (w in c or c in w) for w in wanted for c in credited
    ) or any(w in got for w in wanted)
    return title_ok and artist_ok


def _wait_for_conversion(limit: float = 900.0) -> None:
    """Hold off while the startup pass is rewriting the music folder.

    It renames files as it goes, and a repair swapping one in at the same time
    is two things writing the same path at once.
    """

    began = time.monotonic()
    while vault.busy() and time.monotonic() - began < limit:
        time.sleep(0.5)


def _keep(path: Path, base: Path, data_dir: Optional[Path]) -> Optional[Path]:
    """Copy the file about to be replaced into the data folder."""

    if not data_dir:
        return None
    shelf = Path(data_dir) / KEPT / path.relative_to(base)
    try:
        shelf.parent.mkdir(parents=True, exist_ok=True)
        # copyfile, not copy2: the copy's date is when it was kept, which is
        # what prune() goes by. copy2 would carry the track's own date across,
        # and a track saved a month ago would be thrown away on the next run.
        shutil.copyfile(path, shelf)
        return shelf
    except OSError:
        logger.opt(exception=True).warning('could not keep a copy of {}', path.name)
        return None


def _copy_synced(src: Path, dest: Path) -> None:
    with open(src, 'rb') as a, open(dest, 'wb') as b:
        shutil.copyfileobj(a, b, 1 << 20)
        b.flush()
        os.fsync(b.fileno())


def _place(src: Path, dest: Path) -> None:
    """Put *src* at *dest* in one step, replacing what is there.

    It arrives beside the destination first, under a name nothing scans for,
    and is then renamed over it. A rename is atomic: the path holds the old
    file or the new one and is never empty or half written. Moving it there is
    a rename too when both are on the same drive, and a copy when not.

    The swap is retried for a few seconds. Windows will not replace a file
    somebody has open, and the player or the library scanner can have it open
    for a moment at any time.
    """

    incoming = dest.with_name(dest.name + '.incoming')
    try:
        os.replace(src, incoming)
    except OSError:
        _copy_synced(src, incoming)
    last: Optional[OSError] = None
    for attempt in range(8):
        try:
            os.replace(incoming, dest)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.25 * (attempt + 1))
    _unlink(incoming)
    raise last if last is not None else OSError('could not replace the file')


def _unlink(path: Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _renote(base: Path, path: Path, head: dict[str, Any]) -> None:
    """Point the library's index at what is in the file now."""

    vault.note_track(base, path.relative_to(base).as_posix(), {
        'title': str(head.get('title') or ''),
        'artist': str(head.get('artist') or ''),
        'video_id': str(head.get('video_id') or ''),
    })


def _online() -> bool:
    import socket  # noqa: PLC0415

    try:
        socket.create_connection(('music.youtube.com', 443), timeout=4).close()
        return True
    except OSError:
        return False


def _reason(exc: BaseException) -> str:
    """Which of the reasons a failed download comes down to.

    Checked in this order because being offline makes everything else fail
    too: a search that cannot reach anybody finds no match, and telling
    somebody their song is gone when their Wi-Fi is off sends them the wrong
    way entirely.
    """

    text = f'{type(exc).__name__}: {exc}'.lower()
    if isinstance(exc, vault.StorageUnavailable) or isinstance(
        exc.__cause__, vault.StorageUnavailable
    ):
        return UNAVAILABLE
    if not _online():
        return OFFLINE
    if 'could not find a youtube match' in text or any(
        word in text
        for word in (
            'unavailable', 'private video', 'been removed', 'terminated',
            'not available', 'http error 404', 'http error 410',
        )
    ):
        return NOT_FOUND
    return FAILED


def prune(data_dir: Optional[Path], root: Optional[Path] = None) -> None:
    """Clear out old kept copies, and anything a repair that was cut off left.

    Only ever called with no repair running, so nothing half placed is
    anybody's work in progress.
    """

    if data_dir:
        shelf = Path(data_dir) / KEPT
        cutoff = time.time() - KEEP_DAYS * 86400
        if shelf.is_dir():
            for item in sorted(shelf.rglob('*'), reverse=True):
                try:
                    if item.is_file() and item.stat().st_mtime < cutoff:
                        item.unlink()
                    elif item.is_dir() and not any(item.iterdir()):
                        item.rmdir()
                except OSError:
                    pass
    if root and Path(root).is_dir():
        try:
            for stray in Path(root).rglob('*.incoming'):
                if stray.name.endswith(('.dnf.incoming', '.lrc.incoming')):
                    _unlink(stray)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------
class _Jobs:
    """Repairs asked for, done a couple at a time in the background.

    Everything about the current round is kept here and sent to the window as
    it changes, so a banner that has just been opened, or a window that was
    reloaded halfway through, shows the same thing as one that watched from
    the start.
    """

    WORKERS = 2

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: list[tuple[str, bool]] = []
        self._items: dict[str, dict[str, Any]] = {}
        self._threads = 0
        self._context: Optional[Callable[[], Any]] = None
        self._notify: Optional[Callable[[dict[str, Any]], None]] = None
        self._changed: Optional[Callable[[], None]] = None
        self._sent = 0.0
        self._told = 0.0
        # Every snapshot is numbered. Two threads report, and the one that took
        # its snapshot first can be the one whose message goes out last; the
        # window keeps whichever is newest instead of whichever arrived last,
        # which could otherwise be a "still repairing" that is never followed
        # by anything. The epoch tells a restarted app's numbers from old ones.
        self._seq = 0
        self._epoch = secrets.token_hex(4)
        # Tracks deleted while their repair was already under way. They finish
        # quietly and are dropped from the round: see forget().
        self._forgotten: set[str] = set()

    def configure(self, context, notify, changed) -> None:
        """*context* returns (music folder, downloader, data folder) or None,
        read fresh for every track so a folder changed in Settings is used."""

        self._context = context
        self._notify = notify
        self._changed = changed

    # -- asking -------------------------------------------------------------
    def add(self, files: list[str], force: bool = False) -> dict[str, Any]:
        spawn = 0
        with self._lock:
            fresh_round = not self._queue and not self._threads
            if fresh_round:
                self._items = {}
            for raw in files:
                file = _key(raw)
                if not file:
                    continue
                current = self._items.get(file)
                if current and current['state'] in ('queued', 'working'):
                    continue
                self._items[file] = {'state': 'queued', 'reason': '', 'progress': 0}
                self._queue.append((file, bool(force)))
            spawn = max(0, min(self.WORKERS, len(self._queue)) - self._threads)
            self._threads += spawn
        if fresh_round and spawn:
            try:
                ctx = self._context() if self._context else None
                if ctx:
                    prune(ctx[2], ctx[0])
            except Exception:
                logger.opt(exception=True).debug('could not tidy up before repairing')
        for _ in range(spawn):
            threading.Thread(target=self._work, name='repair', daemon=True).start()
        return self._send(forced=True)

    def forget(self, file: str) -> None:
        """A track was deleted: do not repair it, and do not put it back.

        Still waiting, it is simply dropped. Already downloading, it runs to
        the end, finds nothing to replace (fix() looks again before it swaps)
        and leaves the round without a word: whoever deleted it meant to, and
        a message that it "could not be repaired" would be news about nothing.
        """

        key = _key(file)
        with self._lock:
            waiting = [entry for entry in self._queue if entry[0] == key]
            if waiting:
                self._queue = [entry for entry in self._queue if entry[0] != key]
                self._items.pop(key, None)
            elif (self._items.get(key) or {}).get('state') == 'working':
                self._forgotten.add(key)
            else:
                return
        self._send(forced=True)

    def stop(self) -> dict[str, Any]:
        """Drop whatever has not started. What is downloading finishes."""

        with self._lock:
            for file, _ in self._queue:
                self._items.pop(file, None)
            self._queue.clear()
        return self._send(forced=True)

    def status(self) -> dict[str, Any]:
        with self._lock:
            items = {f: dict(v) for f, v in self._items.items()}
            self._seq += 1
            seq = self._seq
        count = {'queued': 0, 'working': 0, 'fixed': 0, 'failed': 0, 'fine': 0}
        for item in items.values():
            count[item['state']] = count.get(item['state'], 0) + 1
        return {
            'type': 'repair',
            'seq': seq,
            'epoch': self._epoch,
            'running': bool(count['queued'] or count['working']),
            'total': len(items),
            'done': count['fixed'] + count['failed'] + count['fine'],
            'fixed': count['fixed'],
            'failed': count['failed'],
            'fine': count['fine'],
            'items': items,
        }

    # -- doing ----------------------------------------------------------------
    def _work(self) -> None:
        last = False
        current = ''
        try:
            while True:
                with self._lock:
                    # Seeing the queue empty and leaving happen under one hold
                    # of the lock. Done in two steps, a repair asked for in the
                    # gap between them counted this worker as still there,
                    # started nobody, and sat queued for ever.
                    if not self._queue:
                        self._threads -= 1
                        last = self._threads == 0
                        break
                    current, force = self._queue.pop(0)
                    self._items[current] = {'state': 'working', 'reason': '', 'progress': 0}
                self._one(current, force)
                current = ''
        except BaseException:
            logger.opt(exception=True).error('a repair worker stopped')
            with self._lock:
                self._threads -= 1
                last = self._threads == 0
                if current:
                    self._items[current] = {'state': 'failed', 'reason': FAILED, 'progress': 0}
                if last:
                    # Nobody is left to do these. Saying they failed is true;
                    # leaving them queued would be a spinner that never stops.
                    for file, _ in self._queue:
                        self._items[file] = {'state': 'failed', 'reason': FAILED, 'progress': 0}
                    self._queue.clear()
        if last:
            self._library_changed(forced=True)
            self._send(forced=True)

    def _one(self, file: str, force: bool) -> None:
        self._send(forced=True)

        def progress(percent: float, _message: str = '') -> None:
            with self._lock:
                item = self._items.get(file)
                if item is not None and item['state'] == 'working':
                    item['progress'] = int(max(0.0, min(100.0, percent)))
            self._send()

        try:
            ctx = self._context() if self._context else None
            if not ctx:
                result = ('failed', FAILED)
            else:
                root, downloader, data_dir = ctx
                result = fix(root, file, downloader, data_dir, force, progress)
        except Exception:
            logger.opt(exception=True).error('repairing {} went wrong', file)
            result = ('failed', FAILED)

        state, reason = result
        with self._lock:
            if file in self._forgotten:
                self._forgotten.discard(file)
                self._items.pop(file, None)
            else:
                self._items[file] = {
                    'state': state,
                    'reason': reason,
                    'progress': 100 if state == 'fixed' else 0,
                }
        if state == 'fixed':
            self._library_changed()
        self._send(forced=True)

    # -- telling --------------------------------------------------------------
    def _send(self, forced: bool = False) -> Optional[dict[str, Any]]:
        """Tell the window where things are. Progress is sent a few times a
        second at most; anything that changes a track's state always goes."""

        now = time.monotonic()
        if not forced and now - self._sent < 0.3:
            return None
        self._sent = now
        snapshot = self.status()
        if self._notify is not None:
            try:
                self._notify(snapshot)
            except Exception:
                logger.opt(exception=True).debug('could not send repair progress')
        return snapshot

    def _library_changed(self, forced: bool = False) -> None:
        # Each of these costs the window a fresh read of the library, so a
        # long round is not one per track. The last always goes.
        now = time.monotonic()
        if not forced and now - self._told < 1.5:
            return
        self._told = now
        if self._changed is None:
            return
        try:
            self._changed()
        except Exception:
            logger.opt(exception=True).debug('library refresh after repair failed')


jobs = _Jobs()
