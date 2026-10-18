"""Sending what is listened to on to ListenBrainz, for whoever asks for it.

Nothing goes anywhere until somebody connects an account in Settings with
their ListenBrainz user token. From then on every listen the app counts (see
listens.counts) is sent as it happens, so their profile, charts and
recommendations there follow what they play here.

The token is kept encrypted the way the Google sign-in is (account.py): it
lets anyone holding it write to that person's profile. Listens wait in a
small file of their own until ListenBrainz has them, so a song played on a
train arrives when the connection does, at the time it was played, and a
restart in between loses none of them.

Last.fm would need a key registered to the app itself, which no build of
Dannify has. ListenBrainz needs nothing but the person's own token.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from . import __version__

API = 'https://api.listenbrainz.org'
_FILE = 'listenbrainz.dat'
_QUEUE = 'listenbrainz-queue.json'
# A year of heavy listening offline. Past this the oldest go: the queue is a
# way to get through a dead spot, not an archive (that is listens.jsonl).
MAX_WAITING = 20000
# What ListenBrainz takes in one request of the kind that sends a backlog.
BATCH = 100
_TIMEOUT = 15
# How long to wait after a failure before trying again, doubling each time.
_RETRY_FIRST = 30.0
_RETRY_MOST = 15 * 60.0

# Why sending stopped, for Settings to say: '' when it has not.
TOKEN = 'token'  # ListenBrainz no longer takes the token (revoked, changed)

_lock = threading.RLock()
_wake = threading.Event()
_state: dict[str, Any] = {
    'dir': None,
    'token': '',
    'user': '',
    'error': '',
    'worker': None,
    'sent': 0,
}
_waiting: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Kept between runs
# ---------------------------------------------------------------------------
def init(data_dir: Path) -> None:
    """Load the connection and whatever was still waiting to be sent."""

    from . import vault  # noqa: PLC0415

    folder = Path(data_dir)
    with _lock:
        _state['dir'] = folder
        _state['token'] = _state['user'] = _state['error'] = ''
        _waiting.clear()
        try:
            stored = (folder / _FILE).read_bytes()
            data = json.loads(vault._unprotect(stored).decode('utf-8'))
            if isinstance(data, dict) and data.get('token'):
                _state['token'] = str(data['token'])
                _state['user'] = str(data.get('user') or '')
        except FileNotFoundError:
            pass
        except Exception:
            logger.opt(exception=True).warning('could not read the ListenBrainz connection')
        try:
            queued = json.loads((folder / _QUEUE).read_text(encoding='utf-8'))
            if isinstance(queued, list):
                _waiting.extend(q for q in queued if _valid(q))
        except FileNotFoundError:
            pass
        except Exception:
            logger.opt(exception=True).warning('ListenBrainz queue unreadable; starting it afresh')
    if _state['token'] and _waiting:
        _kick()


def _save_connection() -> bool:
    from . import vault  # noqa: PLC0415

    folder = _state['dir']
    if folder is None:
        return False
    path = folder / _FILE
    try:
        if _state['token']:
            raw = json.dumps({'token': _state['token'], 'user': _state['user']}).encode('utf-8')
            blob = vault._protect(raw)
            if vault._unprotect(blob) != raw:
                return False
            folder.mkdir(parents=True, exist_ok=True)
            vault._atomic_write(path, blob)
        else:
            path.unlink(missing_ok=True)
        return True
    except Exception:
        logger.opt(exception=True).warning('could not keep the ListenBrainz connection')
        return False


def _save_queue() -> None:
    folder = _state['dir']
    if folder is None:
        return
    path = folder / _QUEUE
    try:
        if not _waiting:
            path.unlink(missing_ok=True)
            return
        tmp = path.with_name(path.name + '.part')
        tmp.write_text(json.dumps(_waiting, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)
    except OSError:
        logger.opt(exception=True).debug('could not keep the ListenBrainz queue')


# ---------------------------------------------------------------------------
# Connecting
# ---------------------------------------------------------------------------
def status() -> dict[str, Any]:
    with _lock:
        return {
            'connected': bool(_state['token']),
            'user': _state['user'],
            'waiting': len(_waiting),
            'error': _state['error'],
        }


def _request(method: str, path: str, token: str, body: Any = None):
    import requests  # noqa: PLC0415

    return requests.request(
        method,
        API + path,
        headers={'Authorization': f'Token {token}', 'User-Agent': f'Dannify/{__version__}'},
        json=body,
        timeout=_TIMEOUT,
    )


def connect(token: str) -> dict[str, Any]:
    """Check *token* with ListenBrainz and keep it.

    Raises ValueError when ListenBrainz says it is not a token, and
    ConnectionError when ListenBrainz could not be asked.
    """

    import requests  # noqa: PLC0415

    token = str(token or '').strip()
    if not token or len(token) > 200 or any(ch.isspace() for ch in token):
        raise ValueError('not a token')
    try:
        res = _request('GET', '/1/validate-token', token)
    except requests.RequestException as exc:
        raise ConnectionError('ListenBrainz could not be reached') from exc
    try:
        data = res.json()
    except ValueError:
        data = {}
    if res.status_code >= 500:
        raise ConnectionError(f'ListenBrainz answered {res.status_code}')
    if not (isinstance(data, dict) and data.get('valid')):
        raise ValueError('not accepted')
    with _lock:
        _state['token'] = token
        _state['user'] = str(data.get('user_name') or '')
        _state['error'] = ''
        if not _save_connection():
            _state['token'] = _state['user'] = ''
            raise OSError('the connection could not be kept')
    logger.info('ListenBrainz connected ({})', _state['user'] or 'unnamed')
    _kick()
    return status()


def disconnect() -> dict[str, Any]:
    """Forget the token, and every listen not yet sent with it."""

    with _lock:
        _state['token'] = _state['user'] = _state['error'] = ''
        _waiting.clear()
        _save_connection()
        _save_queue()
    logger.info('ListenBrainz disconnected')
    return status()


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def _valid(item: Any) -> bool:
    if not isinstance(item, dict) or not isinstance(item.get('listened_at'), int):
        return False
    meta = item.get('track_metadata')
    return isinstance(meta, dict) and bool(meta.get('artist_name')) and bool(meta.get('track_name'))


def listen_of(song: dict[str, Any], at: int, seconds: int) -> Optional[dict[str, Any]]:
    """One listen as ListenBrainz takes it, or None without a title and artist."""

    title = str(song.get('title') or '').strip()
    artists = [str(a).strip() for a in (song.get('artists') or []) if str(a or '').strip()]
    if not title or not artists:
        return None
    info: dict[str, Any] = {
        'media_player': 'Dannify',
        'submission_client': 'Dannify',
        'submission_client_version': __version__,
        'artist_names': artists,
    }
    duration = int(song.get('duration') or 0)
    if duration > 0:
        info['duration_ms'] = duration * 1000
    video = str(song.get('video_id') or '')
    if video:
        info['origin_url'] = f'https://music.youtube.com/watch?v={video}'
        info['music_service'] = 'music.youtube.com'
    meta: dict[str, Any] = {
        'artist_name': ', '.join(artists),
        'track_name': title,
        'additional_info': info,
    }
    album = str(song.get('album') or '').strip()
    if album:
        meta['release_name'] = album
    return {'listened_at': int(at), 'track_metadata': meta}


def submit(song: dict[str, Any], at: int, seconds: int) -> bool:
    """Send one listen when connected. Returns whether it was taken on."""

    listen = listen_of(song, at, seconds)
    if listen is None:
        return False
    with _lock:
        if not _state['token']:
            return False
        _waiting.append(listen)
        if len(_waiting) > MAX_WAITING:
            del _waiting[: len(_waiting) - MAX_WAITING]
        _save_queue()
    _kick()
    return True


def _kick() -> None:
    """Start the sender, or wake it from a wait."""

    with _lock:
        worker = _state['worker']
        if worker is None or not worker.is_alive():
            worker = threading.Thread(target=_send_all, name='listenbrainz', daemon=True)
            _state['worker'] = worker
            worker.start()
            return
    _wake.set()


def _send_all() -> None:
    delay = _RETRY_FIRST
    while True:
        with _lock:
            token = _state['token']
            batch = list(_waiting[:BATCH])
            if not token or not batch or _state['error'] == TOKEN:
                _state['worker'] = None
                return
        outcome = _send(token, batch)
        if outcome == 'sent' or outcome == 'refused':
            with _lock:
                # Only what was sent goes: more may have joined meanwhile, and
                # a disconnect may have emptied the list altogether.
                if _waiting[: len(batch)] == batch:
                    del _waiting[: len(batch)]
                    _save_queue()
                if outcome == 'sent':
                    _state['sent'] += len(batch)
            delay = _RETRY_FIRST
            continue
        if outcome == 'token':
            with _lock:
                _state['error'] = TOKEN
            logger.warning('ListenBrainz no longer accepts the token; sending stopped')
            continue
        # Offline, or ListenBrainz busy: wait, then try again. A new listen,
        # or connecting again, cuts the wait short.
        if _wake.wait(delay):
            _wake.clear()
        delay = min(delay * 2, _RETRY_MOST)


def _send(token: str, batch: list[dict[str, Any]]) -> str:
    """'sent', 'token' (not accepted), 'refused' (bad data: dropped) or 'later'."""

    import requests  # noqa: PLC0415

    body = {'listen_type': 'single' if len(batch) == 1 else 'import', 'payload': batch}
    try:
        res = _request('POST', '/1/submit-listens', token, body)
    except requests.RequestException:
        logger.debug('ListenBrainz unreachable; {} listen(s) wait', len(batch))
        return 'later'
    if res.status_code == 200:
        logger.debug('sent {} listen(s) to ListenBrainz', len(batch))
        return 'sent'
    if res.status_code == 401:
        return 'token'
    if res.status_code == 400:
        # Something in these it will never take. Kept, they would block
        # every listen behind them for good.
        logger.warning('ListenBrainz refused {} listen(s): {}', len(batch), res.text[:300])
        return 'refused'
    logger.debug('ListenBrainz answered {}; trying again later', res.status_code)
    return 'later'


def flush(timeout: float = 5.0) -> None:
    """Wait a little for the sender to finish (tests, and quitting)."""

    began = time.monotonic()
    while time.monotonic() - began < timeout:
        with _lock:
            worker = _state['worker']
        if worker is None or not worker.is_alive():
            return
        time.sleep(0.02)
