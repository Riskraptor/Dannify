"""On-demand audio streaming: instant, storage-free, high-concurrency.

Design goals (per product requirements):
* **No transcode**: copy YouTube's already-compressed audio (AAC/Opus) with
  ``ffmpeg -c:a copy``. ~10x less CPU than re-encoding, so one box can serve
  many simultaneous streams.
* **No server storage**: the remuxed bytes flow straight from googlevideo
  through ffmpeg to the HTTP client. Nothing is written to disk for streaming
  (the on-disk cache is only used by *downloads*, a separate path).
* **Universal playback**: AAC sources are wrapped in fragmented MP4
  (``audio/mp4``) and Opus/Vorbis in WebM/Ogg, both of which phones, TVs,
  laptops and every modern browser play natively.
* **Bounded concurrency**: a semaphore caps how many ffmpeg pipes run at once
  so a burst of hundreds of requests degrades gracefully instead of thrashing.

The expensive part (resolving the googlevideo URL via yt-dlp) is cached per
videoId and de-duplicated, so repeat/parallel requests for the same track pay
that cost at most once.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterator, Optional

import yt_dlp
from loguru import logger

from . import providers, spotify

# --- resolved-song metadata cache (url -> song dict) ---
_MAX_CACHE = 1024
_meta_cache: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_cache_lock = threading.Lock()

# --- direct googlevideo URL cache (videoId -> {url,duration,acodec,ext,ts}) ---
_DIRECT_TTL = 60 * 60 * 3  # googlevideo URLs live ~6h; refresh well before
# Margin kept between an entry's own stated expiry and when we stop trusting
# it, so a long track cannot run past the end of its URL mid-playback.
_EXPIRY_MARGIN = 60 * 20
class _BoundedCache(OrderedDict):
    """A dict that forgets its oldest entries past a size.

    Every song streamed, saved or merely hovered adds one, and nothing ever
    took them out again: a long session carried thousands, and wrote them all
    to disk on every new one.
    """

    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = limit

    def __setitem__(self, key, value) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._limit:
            self.popitem(last=False)


_direct_cache: 'OrderedDict[str, dict[str, Any]]' = _BoundedCache(2000)
_direct_lock = threading.Lock()
_direct_path: Optional['Path'] = None  # noqa: F821. Set by init_persistent_cache
_direct_dirty = False

# Per-key locks so simultaneous callers de-duplicate slow work (extraction).
_key_locks: dict[str, threading.Lock] = {}
_key_locks_guard = threading.Lock()


def _entry_fresh(entry: Optional[dict[str, Any]], now: float) -> bool:
    """Whether a cached direct-URL entry is still worth serving.

    The fast resolver reports YouTube's own ``expiresInSeconds``. Where we
    have it, believe it (less a margin) rather than the blanket TTL, which
    is a guess made for entries that carry no expiry at all.
    """

    if not entry or not entry.get('url'):
        return False
    age = now - float(entry.get('ts') or 0)
    expires = entry.get('expires')
    if expires:
        try:
            return age < max(60.0, float(expires) - _EXPIRY_MARGIN)
        except (TypeError, ValueError):
            pass
    return age < _DIRECT_TTL


# Cap simultaneous ffmpeg remux pipes. Tunable via env for bigger boxes.
_MAX_CONCURRENT_STREAMS = int(os.getenv('DANNIFY_MAX_STREAMS', '64'))
_stream_sema = threading.BoundedSemaphore(_MAX_CONCURRENT_STREAMS)

# --- Windows: never flash console windows for child processes. ---# In the windowed desktop build (PyInstaller --noconsole) every bare
# subprocess would otherwise spawn a visible conhost window AND steal
# focus: slow and ugly. CREATE_NO_WINDOW + hidden STARTUPINFO kills both.
if os.name == 'nt':
    _POPEN_FLAGS = subprocess.CREATE_NO_WINDOW
    _POPEN_SI = subprocess.STARTUPINFO()
    _POPEN_SI.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _POPEN_SI.wShowWindow = subprocess.SW_HIDE
else:
    _POPEN_FLAGS = 0
    _POPEN_SI = None


class _QuietYdlLogger:
    """Funnel yt-dlp's chatter into loguru at DEBUG.

    Losing-the-race client chains emit scary-looking ERROR lines
    ("Requested format is not available") that are entirely expected
    we race several player clients and only need ONE winner. Keeping
    them at DEBUG keeps logs clean and avoids writes to a stderr that
    does not exist in the windowed desktop build.
    """

    @staticmethod
    def debug(msg: str) -> None:
        logger.bind(component='ytdlp').debug('{}', msg)

    @staticmethod
    def info(msg: str) -> None:
        logger.bind(component='ytdlp').debug('{}', msg)

    @staticmethod
    def warning(msg: str) -> None:
        logger.bind(component='ytdlp').debug('{}', msg)

    @staticmethod
    def error(msg: str) -> None:
        logger.bind(component='ytdlp').debug('{}', msg)


_YDL_LOGGER = _QuietYdlLogger()


def init_persistent_cache(data_dir: Path) -> None:
    """Load the persistent direct-URL cache from disk.

    Lets the *second* launch be instantly warm for anything the user
    played recently: the slow yt-dlp resolve is paid once per song
    every ~3 hours (the TTL on googlevideo URLs) rather than once per
    Dannify launch.
    """
    global _direct_path, _direct_cache
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    path = data_dir / 'direct_cache.json'
    _direct_path = path
    if not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        logger.opt(exception=True).debug('direct cache load failed')
        return
    if not isinstance(raw, dict):
        return
    now = time.time()
    loaded = 0
    with _direct_lock:
        for vid, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            ts = float(entry.get('ts') or 0)
            if not entry.get('url') or now - ts > _DIRECT_TTL:
                continue
            _direct_cache[vid] = entry
            loaded += 1
    if loaded:
        logger.info('Stream cache loaded ({} fresh entries)', loaded)


def clear_direct_cache() -> None:
    """Forget every resolved stream address (Settings, Clear caches)."""

    with _direct_lock:
        _direct_cache.clear()
        _persist_direct_cache_locked()


def _persist_direct_cache_locked() -> None:
    """Write the in-memory direct cache to disk atomically."""
    if _direct_path is None:
        return
    # Snapshot under the existing lock then write outside it. Entries past
    # their life are dropped here rather than carried from launch to launch.
    now = time.time()
    snapshot = {
        vid: entry for vid, entry in _direct_cache.items()
        if now - float(entry.get('ts') or 0) <= _DIRECT_TTL
    }
    try:
        tmp = _direct_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(snapshot), encoding='utf-8')
        tmp.replace(_direct_path)
    except OSError:
        logger.opt(exception=True).debug('direct cache persist failed')


_save_timer: Optional[threading.Timer] = None
_save_timer_lock = threading.Lock()


def _save_direct_cache_async() -> None:
    """Persist the cache without blocking the request: best-effort.

    Coalesced: a burst of new entries (a page of hovered rows) is one write
    a few seconds later, not a thread and a full rewrite for each.
    """

    global _save_timer

    def _run() -> None:
        global _save_timer
        with _save_timer_lock:
            _save_timer = None
        with _direct_lock:
            _persist_direct_cache_locked()

    with _save_timer_lock:
        if _save_timer is not None:
            return
        _save_timer = threading.Timer(4.0, _run)
        _save_timer.daemon = True
        _save_timer.start()


def _key_lock(key: str) -> threading.Lock:
    with _key_locks_guard:
        if len(_key_locks) > 4096:
            # Forget the ones nobody holds; they are recreated when needed.
            for stale in [k for k, lk in _key_locks.items() if not lk.locked()]:
                _key_locks.pop(stale, None)
        lk = _key_locks.get(key)
        if lk is None:
            lk = threading.Lock()
            _key_locks[key] = lk
        return lk


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    with _cache_lock:
        if key in _meta_cache:
            _meta_cache.move_to_end(key)
            return _meta_cache[key]
    return None


def _cache_put(key: str, value: dict[str, Any]) -> None:
    with _cache_lock:
        _meta_cache[key] = value
        _meta_cache.move_to_end(key)
        while len(_meta_cache) > _MAX_CACHE:
            _meta_cache.popitem(last=False)


def _video_id_from_url(url: str) -> Optional[str]:
    m = re.search(r'(?:v=|youtu\.be/|/watch\?v=)([A-Za-z0-9_-]{6,})', url)
    return m.group(1) if m else None


def resolve_stream(url: str) -> dict[str, Any]:
    """Resolve *url* (Spotify track or YouTube) to a streamable song dict."""

    cached = _cache_get(url)
    if cached is not None:
        return cached

    song: dict[str, Any]
    video_id: Optional[str] = None

    parsed = spotify.parse_spotify_url(url)
    if parsed is not None:
        kind, sid = parsed
        if kind != 'track':
            raise ValueError('Only Spotify track URLs can be streamed')
        song = spotify.track_from_id(sid)
        video_id, match = providers.find_match(song)
        if match is not None:
            song = providers.enrich_from_match(song, match)
    else:
        vid = _video_id_from_url(url)
        if not vid:
            raise ValueError('Unsupported stream URL')
        song = providers.song_from_video_id(vid)
        video_id = vid

    if not video_id:
        raise ValueError('No playable source found')

    song['video_id'] = video_id
    song['stream_url'] = f'/api/stream?video_id={video_id}'
    _cache_put(url, song)
    return song


def _ydl_opts(clients: list[str]) -> dict[str, Any]:
    extractor_args: dict[str, Any] = {'player_client': clients}
    # App clients don't need the HTML webpage or TV configs: skipping
    # them removes a full round trip from every cold extraction. Web
    # clients DO need the webpage (visitor data / sig js), so only the
    # app chains get the fast path.
    # `android_vr` belongs here too: it is the first chain we try, and
    # leaving it out meant every fallback extraction still downloaded the
    # webpage and the player script it has no use for. That was worth
    # 17 s per track on its own.
    if all(c in ('android', 'android_vr', 'ios') for c in clients):
        extractor_args['player_skip'] = ['webpage', 'configs']
    opts: dict[str, Any] = {
        # Prefer a compact m4a (AAC): universally playable when remuxed to
        # fragmented MP4; fall back to any audio.
        'format': (
            'bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/'
            'bestaudio[ext=webm]/bestaudio/best'
        ),
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        # Route ALL yt-dlp output through loguru. Critical for the windowed
        # desktop build where sys.stderr is None: bare writes would fail.
        'logger': _YDL_LOGGER,
        'skip_download': True,
        'extractor_args': {'youtube': extractor_args},
        'socket_timeout': 10,
    }
    if os.getenv('DANNIFY_STREAM_IPV6') not in ('1', 'true', 'yes'):
        opts['source_address'] = '0.0.0.0'
    # Signed in? Hand yt-dlp the session. Cookies are what keep YouTube from
    # answering "Sign in to confirm you're not a bot", and a fresh stream is
    # required per YoutubeDL because it writes the jar back on close.
    jar = _cookiefile()
    if jar is not None:
        opts['cookiefile'] = jar
    # YouTube ciphers every audio URL behind a JS challenge now; without a
    # runtime to solve it yt-dlp only ever sees storyboards.
    from .jsruntime import apply as _apply_js

    return _apply_js(opts)


def _media_tool_path() -> str:
    """Our bundled encoder, falling back to anything named ffmpeg on PATH."""
    from .jsruntime import media_tool

    tool = media_tool()
    return str(tool) if tool is not None else 'ffmpeg'


def _cookiefile():
    try:
        from . import account

        return account.ydl_cookiefile()
    except Exception:
        return None


# Ordered by measured cold-extract time. Every one of these works now that a
# JS runtime solves the signature challenge, so the list is a fallback chain
# rather than a lottery: the first almost always wins. Keeping it short
# matters because each attempt spawns its own JS solve.
# `android_vr` used to lead this list. It no longer belongs: anonymously it
# answers LOGIN_REQUIRED in about 2.5 s and then the race waits out the
# stagger anyway, and the identity that *does* work is exactly what
# `innertube` already tried before we got here. What is left is the set of
# clients the fast path cannot speak.
_CLIENT_CHAINS_ANON = [
    ['tv_downgraded'],
    ['web_safari'],
    ['mweb'],
]
# Signed in, prefer clients that actually honour cookies: android/ios throw
# the session away, which is what brings back the bot check.
_CLIENT_CHAINS_AUTH = [
    ['tv_downgraded'],
    ['web_safari'],
    ['mweb'],
]


def _client_chains() -> list[list[str]]:
    return _CLIENT_CHAINS_AUTH if _cookiefile() is not None else _CLIENT_CHAINS_ANON


def _extract_with(video_id: str, clients: list[str]) -> Optional[dict[str, Any]]:
    url = f'https://music.youtube.com/watch?v={video_id}'
    with yt_dlp.YoutubeDL(_ydl_opts(clients)) as ydl:
        info = ydl.extract_info(url, download=False)

    direct = info.get('url')
    acodec = info.get('acodec') or ''
    ext = info.get('ext') or ''
    if not direct:
        formats = info.get('formats') or []
        audio = [
            f
            for f in formats
            if f.get('acodec') not in (None, 'none') and f.get('url')
        ]
        # Prefer m4a/AAC (best device compatibility once remuxed to MP4).
        audio.sort(
            key=lambda f: (
                0 if (f.get('ext') == 'm4a' or 'mp4a' in str(f.get('acodec')))
                else 1,
                -(f.get('abr') or 0),
            )
        )
        if audio:
            best = audio[0]
            direct = best.get('url')
            acodec = best.get('acodec') or acodec
            ext = best.get('ext') or ext
    if not direct:
        return None
    return {
        'url': direct,
        'duration': int(info.get('duration') or 0),
        'acodec': acodec,
        'ext': ext,
        'ts': time.time(),
    }


def _extract_direct(video_id: str, *, skip_fast: bool = False) -> dict[str, Any]:
    """Return cached ``{url, duration, acodec, ext}`` for *video_id*.

    De-duplicated per-videoId so a burst of concurrent requests for the same
    track runs yt-dlp once; the rest wait briefly and reuse the result.

    *skip_fast* forces the full extractor. The proxy sets it when a URL the
    fast path handed out was refused by the CDN, so the retry cannot loop on
    the same answer.
    """

    now = time.time()
    with _direct_lock:
        hit = _direct_cache.get(video_id)
        if _entry_fresh(hit, now):
            return hit

    with _key_lock('extract::' + video_id):
        now = time.time()
        with _direct_lock:
            hit = _direct_cache.get(video_id)
            if _entry_fresh(hit, now):
                return hit

        # --- Fast path: ask YouTube directly. ---
        # The app clients in `innertube` get an unciphered URL out of a
        # single JSON POST, so this answers in a few hundred milliseconds
        # where yt-dlp needs seconds to solve the web signature challenge.
        # It returns None for anything it cannot serve (age gates, private
        # uploads, blocked regions), which drops straight through to the
        # full extractor below.
        entry = None
        if not skip_fast:
            try:
                from . import innertube

                entry = innertube.resolve(video_id)
            except Exception:  # noqa: BLE001
                logger.opt(exception=True).debug(
                    'fast resolve failed for {}', video_id,
                )
        if entry is not None:
            with _direct_lock:
                _direct_cache[video_id] = entry
            _save_direct_cache_async()
            return entry

        last_err: Optional[Exception] = None
        # --- Happy-eyeballs extraction race ---
        # Try client chains CONCURRENTLY with a short stagger instead of
        # one-by-one: android launches immediately; if it hasn't answered
        # within the stagger window the next chain joins the race, etc.
        # First success wins → worst-case latency collapses from
        # sum(timeouts) (~10s+) to roughly the fastest client's time,
        # while the common case (android answers) costs a single request.
        import concurrent.futures as _cf
        import queue as _q

        chains = _client_chains()
        results: '_q.Queue[tuple[Optional[dict], Optional[Exception]]]' = (
            _q.Queue()
        )
        pool = _cf.ThreadPoolExecutor(
            max_workers=len(chains),
            thread_name_prefix=f'extract-{video_id[:6]}',
        )
        done = threading.Event()

        def _try(chain: list[str]) -> None:
            if done.is_set():
                results.put((None, None))
                return
            try:
                results.put((_extract_with(video_id, chain), None))
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    'stream extract {} via {} failed: {}',
                    video_id, chain, exc,
                )
                results.put((None, exc))

        # Long enough that a healthy first client finishes alone. Solving the
        # YouTube player costs real CPU, so firing every chain at once would
        # start four JS engines just to throw three of them away.
        _STAGGER = 4.0
        entry: Optional[dict[str, Any]] = None
        launched = 0
        answered = 0
        try:
            while answered < len(chains):
                if launched < len(chains):
                    try:
                        pool.submit(_try, chains[launched])
                    except RuntimeError:
                        # Interpreter is shutting down; nothing left to race.
                        break
                    launched += 1
                # Wait for an answer; while chains remain unlaunched, wake
                # up every _STAGGER seconds to add another to the race.
                timeout = _STAGGER if launched < len(chains) else None
                try:
                    res, err = results.get(timeout=timeout)
                except _q.Empty:
                    continue  # stagger expired → launch the next chain
                answered += 1
                if err is not None:
                    last_err = err
                if res is not None:
                    entry = res
                    done.set()
                    break
        finally:
            done.set()
            pool.shutdown(wait=False, cancel_futures=True)

        if entry is not None:
            with _direct_lock:
                _direct_cache[video_id] = entry
            _save_direct_cache_async()
            return entry

        if last_err is not None:
            raise RuntimeError(
                f'Could not extract audio stream URL: {last_err}'
            )
        raise RuntimeError('Could not extract audio stream URL')


def resolve_for_download(video_id: str) -> Optional[str]:
    """A ready-to-fetch audio URL for *video_id*, or None to use yt-dlp.

    Deliberately narrow: only the fast resolver answers here. Falling back
    to the full extractor inside this helper would double the work, because
    the download path is about to run that extractor itself anyway.
    """

    now = time.time()
    with _direct_lock:
        hit = _direct_cache.get(video_id)
        if _entry_fresh(hit, now):
            return str(hit['url'])
    try:
        from . import innertube

        entry = innertube.resolve(video_id)
    except Exception:  # noqa: BLE001
        logger.opt(exception=True).debug(
            'fast download resolve failed for {}', video_id,
        )
        return None
    if not entry:
        return None
    with _direct_lock:
        _direct_cache[video_id] = entry
    _save_direct_cache_async()
    return str(entry['url'])


def get_duration(video_id: str) -> int:
    try:
        return int(_extract_direct(video_id).get('duration') or 0)
    except Exception:
        logger.opt(exception=True).debug('duration lookup failed {}', video_id)
        return 0


def _container_for(acodec: str, ext: str) -> tuple[str, list[str]]:
    """Always output progressive **MP3**: the single most reliable thing to
    feed an HTML5 ``<audio>`` element over a length-less chunked response.

    Fragmented MP4/WebM looked faster on paper but browsers refuse to play a
    length-less, non-seekable fragmented stream in ``<audio>``, which is what
    broke playback. MP3 plays on phones, TVs, laptops and every browser.

    ``-q:a 2`` (about 190 kbps): this is the fallback for a song that could
    not be streamed as it is, and it used to be ``-q:a 5``, about 130 kbps,
    a quality drop anyone with good headphones could hear. One listener's
    encode is nothing for a desktop to keep up with.
    """

    return (
        'audio/mpeg',
        [
            '-c:a',
            'libmp3lame',
            '-q:a',
            '2',  # VBR ~190 kbps
            '-write_xing',
            '0',  # progressive: emit frames immediately, no seek header
            '-f',
            'mp3',
        ],
    )


def stream_info(video_id: str) -> dict[str, Any]:
    """Return ``{duration, mime}`` for a video without streaming audio."""

    info = _extract_direct(video_id)
    # Report the proxy mime: the default ``/api/stream`` path is the
    # byte-range proxy, not the legacy ffmpeg→MP3 fallback. Browsers
    # need to know it's m4a/webm so they pick the right decoder.
    mime = _proxy_mime_for(info.get('acodec', ''), info.get('ext', ''))
    return {
        'duration': info['duration'],
        'mime': mime,
        # None when the resolver could not tell us; the player then leaves
        # the volume exactly where the user put it.
        'loudness_db': info.get('loudness_db'),
    }


# Back-compat name used elsewhere.
def probe(video_id: str) -> dict[str, Any]:
    return stream_info(video_id)


# ---------------------------------------------------------------------------
# Native byte-range proxy (fast seek path)
#
# Instead of re-spawning ffmpeg every time the user drags the progress bar
# (which means re-encoding the audio from a new timestamp: slow!), we
# expose the upstream googlevideo URL as a regular byte-range-capable HTTP
# resource. The browser then seeks NATIVELY exactly like it would on any
# MP3 file served from a webserver: it sends ``Range: bytes=N-`` and we
# forward that to googlevideo and pipe the bytes back. Result: clicking
# on the progress bar is instant.
#
# Format choice: m4a/AAC plays in every modern <audio> element; opus/webm
# does too. So no transcode is needed: we just relay bytes.
# ---------------------------------------------------------------------------

_PROXY_SEMA = threading.BoundedSemaphore(
    int(os.getenv('DANNIFY_MAX_PROXY', '256'))
)


def _proxy_mime_for(acodec: str, ext: str) -> str:
    """Return a Content-Type that an HTML5 ``<audio>`` element will play."""
    e = (ext or '').lower()
    a = (acodec or '').lower()
    if e in ('m4a', 'mp4') or a.startswith('mp4a') or a.startswith('aac'):
        return 'audio/mp4'
    if e in ('webm', 'opus') or a.startswith('opus'):
        return 'audio/webm'
    if e in ('weba',):
        return 'audio/webm'
    # Conservative fallback: m4a covers ~all YT music audio formats.
    return 'audio/mp4'


def _http_get_range(
    url: str,
    range_header: Optional[str],
    timeout: float = 12.0,
    *,
    max_redirects: int = 5,
):
    """Open a streaming HTTP GET against *url*, forwarding *range_header*.

    Manually follows redirects so we can fix up the **relative**
    ``Location:`` headers that googlevideo's CDN occasionally returns
    (``/videoplayback?...`` instead of a full ``https://host/...``). The
    requests library rejects those with ``MissingSchema``; we resolve
    them against the previous request's URL using ``urljoin`` before
    issuing the next hop.

    Returns a streaming :class:`requests.Response`. Caller must
    iterate ``response.iter_content`` and call ``response.close()`` to
    release the connection back to the pool.
    """

    from urllib.parse import urljoin

    sess = _proxy_session()
    headers: dict[str, str] = {}
    if range_header:
        headers['Range'] = range_header
    # A realistic UA helps a few CDNs not 403 us.
    headers['User-Agent'] = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    )

    current_url = url
    for _ in range(max_redirects + 1):
        resp = sess.get(
            current_url,
            headers=headers,
            stream=True,
            allow_redirects=False,
            timeout=(4.0, timeout),
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get('Location')
            try:
                resp.close()
            except Exception:
                pass
            if not loc:
                break  # malformed redirect: give up and let caller see it
            # Resolve relative paths against the previous URL.
            current_url = urljoin(current_url, loc)
            # 303 forces GET, others preserve method (already GET here).
            continue
        # Stamp the final URL onto the response so the caller can cache it.
        try:
            resp.url = current_url
        except Exception:
            pass
        return resp
    # Ran out of redirects.
    return resp


_proxy_session_singleton: Optional['Any'] = None
_proxy_pool_lock = threading.Lock()


def _proxy_session():
    """Return a process-wide requests.Session.

    Pools TLS connections to the googlevideo CDN so consecutive range
    requests during the same playback session reuse the connection
    instead of paying the handshake cost on every seek.
    """
    global _proxy_session_singleton
    if _proxy_session_singleton is not None:
        return _proxy_session_singleton
    with _proxy_pool_lock:
        if _proxy_session_singleton is None:
            import requests
            from requests.adapters import HTTPAdapter

            sess = requests.Session()
            # Generous pool: every active stream may have one connection
            # to the CDN; we cap at 64 streams elsewhere.
            adapter = HTTPAdapter(
                pool_connections=20, pool_maxsize=64, max_retries=0,
            )
            sess.mount('http://', adapter)
            sess.mount('https://', adapter)
            _proxy_session_singleton = sess
    return _proxy_session_singleton


def open_proxy(
    video_id: str,
    range_header: Optional[str] = None,
) -> tuple[int, dict[str, str], Iterator[bytes]]:
    """Open a byte-range proxy to *video_id*'s upstream audio URL.

    Returns ``(status, response_headers, byte_iterator)`` suitable for a
    FastAPI :class:`StreamingResponse`. Forwards the browser's
    ``Range:`` header so seeking is native and instant.

    Optimisations to cut every-seek latency:

    * **Redirect-target caching.** The first hit follows googlevideo's
      302 to a specific CDN edge URL; we save that resolved URL on the
      cache entry so every later seek goes straight to the CDN (saves
      ~1s per seek, ~half the round-trip).
    * **403/410 → re-extract once.** googlevideo signs URLs with a ~6h
      TTL; when they expire we transparently re-resolve and retry.
    """

    info = _extract_direct(video_id)
    mime = _proxy_mime_for(info.get('acodec', ''), info.get('ext', ''))

    # Use the resolved CDN target if we've already learnt it. Sanity-check
    # that it's an absolute URL: older cache entries from a buggy redirect
    # handler may contain a relative path like ``/videoplayback?...`` which
    # ``requests`` will reject.
    resolved = info.get('resolved_url') or ''
    if resolved.startswith(('http://', 'https://')):
        target_url = resolved
    else:
        if resolved:
            # Drop the bad cache entry so we relearn next time.
            with _direct_lock:
                cached = _direct_cache.get(video_id)
                if cached is not None:
                    cached.pop('resolved_url', None)
        target_url = info['url']

    resp = _http_get_range(target_url, range_header)
    # googlevideo signs these URLs with a ~6h TTL, so a cached one can be
    # refused. Re-resolve fast first: an expired URL is the common case and
    # a fresh one from the same client fixes it in about a third of a
    # second. Only if THAT is refused too is the client itself the problem,
    # which is when the full extractor is worth its ten-plus seconds.
    for attempt in ('fresh', 'full'):
        if resp.status_code not in (403, 410):
            break
        logger.info(
            'Stream URL refused for {}; re-resolving ({})', video_id, attempt,
        )
        try:
            resp.close()
        except Exception:
            pass
        with _direct_lock:
            _direct_cache.pop(video_id, None)
        info = _extract_direct(video_id, skip_fast=(attempt == 'full'))
        target_url = info['url']
        resp = _http_get_range(target_url, range_header)

    # Cache the resolved CDN URL so the next seek skips the 302 hop.
    # ``response.url`` is the FINAL URL after all redirects, set by our
    # manual redirect loop above. Only persist absolute URLs.
    try:
        final_url = resp.url
        if (
            final_url
            and final_url.startswith(('http://', 'https://'))
            and final_url != target_url
            and final_url != info.get('resolved_url')
        ):
            with _direct_lock:
                cached = _direct_cache.get(video_id)
                if cached is not None:
                    cached['resolved_url'] = final_url
            _save_direct_cache_async()
    except Exception:
        logger.opt(exception=True).debug('Could not learn resolved CDN URL')

    headers: dict[str, str] = {
        'Content-Type': mime,
        # CRITICAL: this is what makes the browser do native seeking.
        'Accept-Ranges': 'bytes',
        # Not written to the window's cache: a song streamed once would sit
        # there as a plain audio file anyone could copy. What has been played
        # stays in the player's own memory for scrubbing back.
        'Cache-Control': 'no-store',
    }
    # Pass through Content-Length / Content-Range: these tell the
    # browser the exact duration and the byte range it just got back.
    for name in ('Content-Length', 'Content-Range'):
        v = resp.headers.get(name)
        if v:
            headers[name] = v

    return resp.status_code, headers, _relay(video_id, resp, resp.url or target_url)


def _span(resp) -> Optional[tuple[int, int]]:
    """The first and last byte a response carries, when it says."""

    try:
        if resp.status_code == 206:
            match = re.match(r'bytes (\d+)-(\d+)/', resp.headers.get('Content-Range', ''))
            if match:
                return int(match.group(1)), int(match.group(2))
        elif resp.status_code == 200:
            length = int(resp.headers.get('Content-Length') or 0)
            if length > 0:
                return 0, length - 1
    except Exception:
        pass
    return None


# How many times a stream is picked up again after the CDN drops it.
RESUMES = 3


def _relay(video_id: str, resp, source: str) -> Iterator[bytes]:
    """Pass the CDN's bytes on to the player, picking up where it stopped.

    The CDN sometimes closes a connection part way through a song. The bytes
    promised to the player were then simply not all sent: the server logged
    "Too little data for declared Content-Length", and the player got a cut
    that it had to notice and recover from, which on a slow connection meant
    a gap in the music. Now the missing part is asked for again from exactly
    the byte where it stopped, and the player never knows.

    A listener closing the stream (a seek, the next track) stops this
    generator from the outside; that does not come through the except below.
    """

    if not _PROXY_SEMA.acquire(timeout=15):
        try:
            resp.close()
        except Exception:
            pass
        logger.warning('proxy sema timeout for {}', video_id)
        return
    span = _span(resp)
    current = resp
    sent = 0
    tries = 0
    try:
        while True:
            try:
                for chunk in current.iter_content(64 * 1024):
                    if chunk:
                        sent += len(chunk)
                        yield chunk
            except Exception:
                pass  # the CDN let go part way: see whether anything is missing
            if span is None or span[0] + sent > span[1]:
                return  # everything was sent, or there is no knowing what was not
            if tries >= RESUMES:
                logger.info(
                    'stream for {} ended {} bytes short', video_id,
                    span[1] - span[0] + 1 - sent,
                )
                return
            tries += 1
            try:
                current.close()
            except Exception:
                pass
            try:
                current = _http_get_range(source, f'bytes={span[0] + sent}-{span[1]}')
            except Exception:
                return
            picked_up = _span(current)
            if current.status_code != 206 or not picked_up or picked_up[0] != span[0] + sent:
                return  # the CDN would not carry on from there
    finally:
        try:
            current.close()
        except Exception:
            pass
        _PROXY_SEMA.release()


def open_stream(video_id: str, start_seconds: float = 0.0) -> tuple[str, Iterator[bytes]]:
    """Return ``(mime, byte_iterator)`` that remuxes *video_id* on the fly.

    Pure pass-through: googlevideo → ffmpeg (copy) → client. No disk writes.
    ``start_seconds`` lets the client "seek" on a length-less stream by asking
    the server to begin output at an offset. A bounded semaphore limits how
    many concurrent pipes run so hundreds of requests degrade gracefully.
    """

    info = _extract_direct(video_id)
    mime, copy_args = _container_for(info['acodec'], info['ext'])

    cmd = [
        _media_tool_path(),
        '-hide_banner',
        '-loglevel',
        'error',
        # Low-latency start: don't deep-probe the input (it's a known,
        # clean googlevideo audio stream) and flush output packets as soon
        # as they're encoded so the client hears audio ASAP.
        '-analyzeduration', '0',
        '-probesize', '128k',
        '-fflags', '+nobuffer',
        '-flush_packets', '1',
        # Resilient googlevideo fetch.
        '-reconnect',
        '1',
        '-reconnect_streamed',
        '1',
        '-reconnect_delay_max',
        '5',
    ]
    if start_seconds and start_seconds > 0:
        # Seek before -i for a fast input seek (keyframe-accurate, low CPU).
        cmd += ['-ss', str(start_seconds)]
    cmd += [
        '-i',
        info['url'],
        '-vn',
        *copy_args,
        'pipe:1',
    ]

    def _gen() -> Iterator[bytes]:
        acquired = _stream_sema.acquire(timeout=20)
        if not acquired:
            # Server is saturated; surface as an empty body (client retries).
            logger.warning('stream sema timeout for {}', video_id)
            return
        proc = None
        try:
            # Inside the try: a media tool that will not start (missing, or
            # quarantined by a virus scanner) must still hand its slot back,
            # or every such failure left one fewer stream for good.
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                bufsize=0,
                creationflags=_POPEN_FLAGS,
                startupinfo=_POPEN_SI,
            )
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            if proc is not None:
                try:
                    proc.kill()
                except Exception:
                    pass
            _stream_sema.release()

    return mime, _gen()


def stream_mime(_fmt: str = 'mp3') -> str:
    return 'audio/mpeg'


def prefetch(video_id: str) -> None:
    """Warm the URL cache for *video_id* in the background, so pressing play
    on a row the user has hovered costs nothing.

    This used to call the extractor directly to keep each warm-up down to a
    single yt-dlp invocation rather than the full client race. That is no
    longer the cheap option: the direct resolver answers the same question in
    about a third of a second over one HTTP call, where yt-dlp spends ten
    seconds and a JS engine on it. So warming now takes the same fast path a
    real play does, and only falls back to a single yt-dlp client for the
    tracks that path cannot serve.
    """

    with _direct_lock:
        hit = _direct_cache.get(video_id)
    if _entry_fresh(hit, time.time()):
        return

    # In-flight dedupe: if another prefetch for the same id is already
    # running, don't start a second one.
    with _prefetch_inflight_lock:
        if video_id in _prefetch_inflight:
            return
        _prefetch_inflight.add(video_id)

    def _run() -> None:
        try:
            acquired = _prefetch_sema.acquire(timeout=0)
            if not acquired:
                # Already at the cap (2 in flight). Skip: the user can
                # still play this song; the slow path just kicks in.
                return
            try:
                entry = None
                try:
                    from . import innertube

                    entry = innertube.resolve(video_id)
                except Exception:  # noqa: BLE001
                    logger.opt(exception=True).debug(
                        'fast warm failed {}', video_id,
                    )
                if entry is None:
                    # Single client, not the full race: a warm-up is a
                    # courtesy and must not cost more than the play it saves.
                    entry = _extract_with(video_id, _client_chains()[0])
                if entry is not None:
                    with _direct_lock:
                        _direct_cache[video_id] = entry
                    _save_direct_cache_async()
            finally:
                _prefetch_sema.release()
        except Exception:
            logger.opt(exception=True).debug('prefetch failed {}', video_id)
        finally:
            with _prefetch_inflight_lock:
                _prefetch_inflight.discard(video_id)

    threading.Thread(target=_run, daemon=True).start()


# Bounded background prefetch. The cap was 2 when a warm-up meant a yt-dlp
# run with a JS engine behind it; now it is one HTTP request, so a handful in
# flight costs nothing and the whole visible row of results can be warm by
# the time the user picks one. The cap still exists for the fallback case,
# where a track the fast path refuses does fall through to yt-dlp.
# Real plays go through `_extract_direct` and aren't subject to this cap.
_prefetch_sema = threading.BoundedSemaphore(6)
_prefetch_inflight: set[str] = set()
_prefetch_inflight_lock = threading.Lock()
