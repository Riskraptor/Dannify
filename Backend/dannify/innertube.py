"""Direct InnerTube ``/player`` resolution: the fast path to a playable URL.

Why this exists
---------------
yt-dlp is a general-purpose extractor. For a YouTube *web* client it must
download the ~2 MB player script and run YouTube's obfuscated signature and
``n`` challenges through a JS engine, which costs seconds of wall clock on
every cold track. Measured on this machine: 3.4 s to 20.5 s per track.

But YouTube only ciphers the *web* clients. A handful of app clients
(Apple Vision Pro, the Oculus build of YouTube VR) get plain ``url`` fields
in their ``/player`` response: no signature, no ``n`` transform, no PO token.
One JSON POST and the URL is ready. Measured on the same tracks through the
same connection: 344 ms to 890 ms, every URL serving ``206`` to an
open-ended ``Range``.

So this module speaks InnerTube directly for the common case and leaves
yt-dlp as the fallback for whatever these clients refuse (age gates, private
uploads, regional blocks). The client identity strings are the load-bearing
part: they are what makes YouTube answer with an unciphered URL, and they go
stale when Google rotates versions, so they live in ``clients.json`` next to
this file and can be replaced at runtime without a rebuild.

Credit where it is due: the client table and the fallback ordering follow
what LiMusic (github.com/oglimmer/limusic) worked out, which in turn follows
Metrolist. The measurements and the Python are ours.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

import requests
from loguru import logger

# --- endpoints ---
_BASE = 'https://music.youtube.com/youtubei/v1/player'
_ORIGIN = 'https://music.youtube.com'
_VISITOR_SOURCE = 'https://www.youtube.com/sw.js_data'

# How long a bootstrapped visitorData is reused. It is a soft session marker,
# not a credential, so a long life is fine and saves a round trip per launch.
_VISITOR_TTL = 12 * 60 * 60

# Budget for one /player POST. These answer in under a second when healthy;
# anything slower is a stall we would rather spend on the next client.
_PLAYER_TIMEOUT = 6.0
# Budget for the HEAD that proves the URL will actually serve bytes.
_VALIDATE_TIMEOUT = 5.0

_state_lock = threading.Lock()
_visitor: Optional[str] = None
_visitor_ts = 0.0
_visitor_path: Optional[Path] = None
_session: Optional[requests.Session] = None

# Clients whose /player answers with plain URLs, in the order we try them.
# VISIONOS first because it wins essentially every time and carries the full
# format ladder. The two Android VR builds differ by version on purpose: one
# of them is usually healthy when the other has been throttled.
_STREAM_ORDER = ('VISIONOS', 'ANDROID_VR_1_43_32', 'ANDROID_VR_1_65_10')

# Fallback identities, used when clients.json is missing or unreadable.
_BUILTIN_CLIENTS: dict[str, dict[str, str]] = {
    'VISIONOS': {
        'clientName': 'VISIONOS',
        'clientVersion': '0.1',
        'clientId': '101',
        'userAgent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 '
            'Safari/605.1.15'
        ),
        'osName': 'visionOS',
        'osVersion': '1.3.21O771',
        'deviceMake': 'Apple',
        'deviceModel': 'RealityDevice14,1',
    },
    'ANDROID_VR_1_43_32': {
        'clientName': 'ANDROID_VR',
        'clientVersion': '1.43.32',
        'clientId': '28',
        'userAgent': (
            'com.google.android.apps.youtube.vr.oculus/1.43.32 '
            '(Linux; U; Android 12; en_US; Quest 3; '
            'Build/SQ3A.220605.009.A1; Cronet/107.0.5284.2)'
        ),
        'osName': 'Android',
        'osVersion': '12',
        'deviceMake': 'Oculus',
        'deviceModel': 'Quest 3',
        'androidSdkVersion': '32',
    },
    'ANDROID_VR_1_65_10': {
        'clientName': 'ANDROID_VR',
        'clientVersion': '1.65.10',
        'clientId': '28',
        'userAgent': (
            'com.google.android.apps.youtube.vr.oculus/1.65.10 '
            '(Linux; U; Android 12L; eureka-user '
            'Build/SQ3A.220605.009.A1) gzip'
        ),
        'osName': 'Android',
        'osVersion': '12L',
        'deviceMake': 'Oculus',
        'deviceModel': 'Quest 3',
        'androidSdkVersion': '32',
    },
}

_clients: dict[str, dict[str, str]] = dict(_BUILTIN_CLIENTS)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _load_clients(data_dir: Optional[Path]) -> None:
    """Load client identities, preferring an override in the data dir.

    Google rotates client versions every few months and a stale version stops
    getting unciphered URLs. Keeping the table in a data file means a fix can
    ship as a config push rather than a new build.
    """

    global _clients
    candidates: list[Path] = []
    if data_dir is not None:
        candidates.append(Path(data_dir) / 'clients.json')
    candidates.append(Path(__file__).with_name('clients.json'))
    for path in candidates:
        try:
            if not path.is_file():
                continue
            loaded = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict) and loaded:
                merged = dict(_BUILTIN_CLIENTS)
                merged.update(loaded)
                _clients = merged
                logger.debug('innertube clients loaded from {}', path)
                return
        except Exception:
            logger.opt(exception=True).debug('bad clients.json at {}', path)

    # A shipped build keeps the table in the packed resource file rather than
    # loose on disk, so the install folder has one less readable config in it.
    # An override in the data dir still comes first: that is the config push.
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        from dannify import respack

        blob = respack.resource('dannify/clients.json', Path(meipass))
        if blob:
            try:
                loaded = json.loads(blob.decode('utf-8'))
                if isinstance(loaded, dict) and loaded:
                    merged = dict(_BUILTIN_CLIENTS)
                    merged.update(loaded)
                    _clients = merged
                    logger.debug('innertube clients loaded from the bundle')
                    return
            except Exception:
                logger.opt(exception=True).debug('bad clients.json in bundle')

    _clients = dict(_BUILTIN_CLIENTS)


def _build_session() -> requests.Session:
    """One keep-alive session for the process.

    The TLS handshake to googlevideo costs about 500 ms on a cold connection
    and nothing at all on a warm one, which is most of the spread between the
    890 ms and 344 ms ends of the measurements above. Holding the pool open is
    the single cheapest win here.
    """

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=8,
        pool_maxsize=32,
        max_retries=0,  # our own client chain is the retry
    )
    session.mount('https://', adapter)
    return session


def _http() -> requests.Session:
    global _session
    with _state_lock:
        if _session is None:
            _session = _build_session()
        return _session


def init(data_dir: Optional[Path] = None) -> None:
    """Point the module at the app data dir for overrides and caching."""

    global _visitor_path
    _load_clients(data_dir)
    if data_dir is None:
        return
    try:
        path = Path(data_dir) / 'session.json'
        _visitor_path = path
        if path.is_file():
            blob = json.loads(path.read_text(encoding='utf-8'))
            value = blob.get('visitorData')
            stamp = float(blob.get('ts') or 0)
            if value and time.time() - stamp < _VISITOR_TTL:
                global _visitor, _visitor_ts
                with _state_lock:
                    _visitor = value
                    _visitor_ts = stamp
    except Exception:
        logger.opt(exception=True).debug('could not read cached visitor data')


def warm() -> None:
    """Pay the visitorData bootstrap and the TLS handshake before the user
    presses play, so the first track is as fast as the tenth."""

    try:
        _visitor_data()
        _http().head(_ORIGIN, timeout=_VALIDATE_TIMEOUT)
    except Exception:
        logger.opt(exception=True).debug('innertube warm failed')


# ---------------------------------------------------------------------------
# visitorData
# ---------------------------------------------------------------------------

def _parse_visitor(text: str) -> Optional[str]:
    """Dig visitorData out of the sw.js_data blob.

    The path into that nested array is not documented and has moved before,
    so fall back to scanning for the token shape rather than trusting indices.
    """

    try:
        raw = json.loads(text.lstrip(")]}'\n"))
        return raw[0][2][0][0][13]
    except Exception:
        pass
    # Shape-based rescue: visitorData is a longish base64-ish token that
    # starts with "Cg" in every sample we have seen.
    def walk(node: Any) -> Optional[str]:
        if isinstance(node, str):
            if len(node) > 20 and node.startswith('Cg'):
                return node
            return None
        if isinstance(node, (list, tuple)):
            for item in node:
                found = walk(item)
                if found:
                    return found
        return None

    try:
        return walk(json.loads(text.lstrip(")]}'\n")))
    except Exception:
        return None


def _visitor_data() -> Optional[str]:
    global _visitor, _visitor_ts
    now = time.time()
    with _state_lock:
        if _visitor and now - _visitor_ts < _VISITOR_TTL:
            return _visitor
    try:
        text = _http().get(_VISITOR_SOURCE, timeout=_PLAYER_TIMEOUT).text
        value = _parse_visitor(text)
    except Exception:
        logger.opt(exception=True).debug('visitorData bootstrap failed')
        value = None
    if not value:
        return None
    with _state_lock:
        _visitor = value
        _visitor_ts = now
    if _visitor_path is not None:
        try:
            _visitor_path.parent.mkdir(parents=True, exist_ok=True)
            _visitor_path.write_text(
                json.dumps({'visitorData': value, 'ts': now}),
                encoding='utf-8',
            )
        except Exception:
            logger.opt(exception=True).debug('could not cache visitor data')
    return value


# ---------------------------------------------------------------------------
# One /player call
# ---------------------------------------------------------------------------

_CONTEXT_KEYS = (
    'osName',
    'osVersion',
    'deviceMake',
    'deviceModel',
    'androidSdkVersion',
)


def _body(client: dict[str, str], video_id: str, visitor: Optional[str]) -> dict:
    inner: dict[str, Any] = {
        'clientName': client['clientName'],
        'clientVersion': client['clientVersion'],
        'gl': 'US',
        'hl': 'en',
    }
    for key in _CONTEXT_KEYS:
        if client.get(key):
            inner[key] = client[key]
    if visitor:
        inner['visitorData'] = visitor
    return {
        'context': {
            'client': inner,
            'request': {'internalExperimentFlags': [], 'useSsl': True},
            'user': {'lockedSafetyMode': False},
        },
        'videoId': video_id,
        'contentCheckOk': True,
        'racyCheckOk': True,
    }


def _headers(client: dict[str, str], visitor: Optional[str]) -> dict[str, str]:
    head = {
        'content-type': 'application/json',
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'x-goog-api-format-version': '1',
        # This carries the numeric client id, not the name. Required.
        'x-youtube-client-name': client['clientId'],
        'x-youtube-client-version': client['clientVersion'],
        'x-origin': _ORIGIN,
        'referer': _ORIGIN,
        'user-agent': client['userAgent'],
    }
    if visitor:
        head['x-goog-visitor-id'] = visitor
    return head


def _as_int(value: Any, default: int = 0) -> int:
    """These clients send numbers as JSON strings about half the time."""

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _is_audio(fmt: dict) -> bool:
    """Audio-only formats carry no width."""

    return fmt.get('width') is None and str(
        fmt.get('mimeType', '')
    ).startswith('audio/')


def _is_dubbed(fmt: dict) -> bool:
    """YouTube now ships machine-translated audio tracks alongside the real
    one. Picking one means the user hears the wrong language over the right
    song, so they are excluded unless nothing else is on offer."""

    track = fmt.get('audioTrack') or {}
    return bool(track.get('isAutoDubbed'))


def _quality_rank(fmt: dict) -> int:
    return {
        'AUDIO_QUALITY_HIGH': 3,
        'AUDIO_QUALITY_MEDIUM': 2,
        'AUDIO_QUALITY_LOW': 1,
    }.get(str(fmt.get('audioQuality') or ''), 0)


def _pick_format(formats: Iterable[dict]) -> Optional[dict]:
    """Best audio format for our player.

    AAC in MP4 first: it is what the byte-range proxy declares as
    ``audio/mp4`` and what every target decoder handles without argument.
    Opus is ranked behind it rather than dropped, so a track that only
    publishes Opus still plays.
    """

    audio = [f for f in formats if _is_audio(f) and f.get('url')]
    if not audio:
        return None
    original = [f for f in audio if not _is_dubbed(f)]
    pool = original or audio

    def score(fmt: dict) -> tuple:
        mime = str(fmt.get('mimeType', ''))
        aac = 1 if ('mp4a' in mime or 'audio/mp4' in mime) else 0
        return (aac, _quality_rank(fmt), _as_int(fmt.get('bitrate')))

    return max(pool, key=score)


def _ext_and_codec(fmt: dict) -> tuple[str, str]:
    mime = str(fmt.get('mimeType', ''))
    codec = ''
    if 'codecs=' in mime:
        codec = mime.split('codecs=', 1)[1].strip('"; ')
    if 'audio/mp4' in mime:
        return 'm4a', codec or 'mp4a.40.2'
    if 'audio/webm' in mime:
        return 'webm', codec or 'opus'
    return 'm4a', codec or 'mp4a.40.2'


def _player(key: str, video_id: str, visitor: Optional[str]) -> Optional[dict]:
    client = _clients.get(key)
    if client is None:
        return None
    response = _http().post(
        _BASE,
        json=_body(client, video_id, visitor),
        headers=_headers(client, visitor),
        timeout=_PLAYER_TIMEOUT,
    )
    if response.status_code != 200:
        logger.debug('innertube {} -> HTTP {}', key, response.status_code)
        return None
    return response.json()


def _validate(url: str, user_agent: str) -> bool:
    """Prove the URL serves bytes before we hand it to the player.

    Not every client that answers ``OK`` hands out a URL googlevideo will
    honour. The Android VR 1.65 build, for one, answered 200 with a URL that
    then returned 403 to every request shape we tried. One HEAD costs about
    30 to 100 ms and turns that into a silent fallback instead of a track
    that fails in the user's face.
    """

    try:
        head = _http().head(
            url,
            headers={'User-Agent': user_agent},
            timeout=_VALIDATE_TIMEOUT,
            allow_redirects=True,
        )
        return 200 <= head.status_code < 300
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def resolve(video_id: str) -> Optional[dict[str, Any]]:
    """Return ``{url, duration, acodec, ext, ts}`` for *video_id*, or None.

    None is not an error: it means this fast path did not apply and the
    caller should fall back to the full extractor. Every failure mode lands
    here, so the caller never has to tell them apart.
    """

    started = time.perf_counter()
    visitor = _visitor_data()
    blocked_reason = ''
    for key in _STREAM_ORDER:
        try:
            data = _player(key, video_id, visitor)
        except Exception as exc:  # noqa: BLE001
            logger.debug('innertube {} failed for {}: {}', key, video_id, exc)
            continue
        if not data:
            continue
        status = str((data.get('playabilityStatus') or {}).get('status') or '')
        if status != 'OK':
            blocked_reason = status or blocked_reason
            logger.debug('innertube {} {} -> {}', key, video_id, status)
            continue
        streaming = data.get('streamingData') or {}
        fmt = _pick_format(streaming.get('adaptiveFormats') or [])
        if not fmt:
            continue
        url = fmt['url']
        agent = _clients[key]['userAgent']
        if not _validate(url, agent):
            logger.debug('innertube {} url rejected for {}', key, video_id)
            continue
        ext, acodec = _ext_and_codec(fmt)
        # How far below full scale YouTube mastered this track. Every client
        # that plays a YouTube mix uses it to stop a loud single following a
        # quiet album track at twice the apparent volume.
        audio_config = (data.get('playerConfig') or {}).get('audioConfig') or {}
        loudness = fmt.get('loudnessDb')
        if loudness is None:
            loudness = audio_config.get('loudnessDb')
        try:
            loudness = float(loudness) if loudness is not None else None
        except (TypeError, ValueError):
            loudness = None
        details = data.get('videoDetails') or {}
        duration = _as_int(details.get('lengthSeconds'))
        if not duration:
            duration = _as_int(fmt.get('approxDurationMs')) // 1000
        elapsed = (time.perf_counter() - started) * 1000
        logger.info(
            'innertube resolved {} via {} itag {} in {:.0f} ms',
            video_id, key, fmt.get('itag'), elapsed,
        )
        return {
            'url': url,
            'duration': duration,
            'acodec': acodec,
            'ext': ext,
            'ts': time.time(),
            # Kept for callers that want to age the entry against YouTube's
            # own expiry rather than our fixed TTL.
            'expires': _as_int(streaming.get('expiresInSeconds'), 0),
            'client': key,
            'loudness_db': loudness,
        }
    if blocked_reason:
        logger.debug(
            'innertube gave up on {} ({}), falling back', video_id, blocked_reason,
        )
    return None
