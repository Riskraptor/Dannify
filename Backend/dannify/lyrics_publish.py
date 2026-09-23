"""Publish lyrics back to lrclib.net.

lrclib's POST /api/publish requires a proof-of-work *publish token* to
deter spam. The flow is:

  1. ``POST /api/request-challenge`` returns a fresh ``prefix`` (random
     32 chars) and a ``target`` (32 bytes, hex-encoded: typically
     ``000000FF000…0``, i.e. the first ~3.5 bytes are zero).
  2. The client must find a *nonce* (non-negative integer) such that

         SHA-256(f"{prefix}:{nonce}".encode())  <  target

     where the comparison is **byte-by-byte** (big-endian, lex order
     on the 32-byte digest vs the 32-byte target). This is a classic
     hashcash variant.
  3. The publish token is then ``f"{prefix}:{nonce}"``, sent in the
     ``X-Publish-Token`` header of the publish request.

Each challenge is single-use and expires after 5 minutes.

A reference Python implementation lives in tranxuanthang/lrcget issue
#109 (https://github.com/tranxuanthang/lrcget/issues/109); we mirror
the comparison semantics from there.

**Why subprocesses?** Python's GIL serialises ``hashlib`` calls when
the input is small (<2 KB), which is exactly our regime. Threads do
NOTHING for us. Subprocesses give real parallelism: each one runs an
independent Python that searches a disjoint nonce stride. The first
one to find a valid nonce wins. On an 8-core machine with the typical
lrclib target (~16 M hashes expected), this completes in 10 - 20 s.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from typing import Any, Optional

import requests
from loguru import logger
from requests.adapters import HTTPAdapter

LRCLIB_BASE = 'https://lrclib.net/api'
_CLIENT_ID = 'Dannify/3.0 (https://github.com/henriquesebastiao/dannify)'
# Generous read timeout: lrclib occasionally takes >10s to commit a
# publish (DB write + revision history). Connect timeout stays short so
# the user fails fast if the service is unreachable.
_TIMEOUT = (8.0, 60.0)

# Shared session: connection pooled, identifies us politely.
_session = requests.Session()
_session.headers.update({
    'User-Agent': _CLIENT_ID,
    'Lrclib-Client': _CLIENT_ID,
})
_session.mount('https://', HTTPAdapter(pool_connections=5, pool_maxsize=10))

# How long a single proof-of-work search may run before we give up. The
# expected work is ~16 M hashes (target ``000000FF…``), which on 8 cores
# takes ~15 s; 120 s gives plenty of headroom for slower devices and
# the higher per-process startup overhead of the frozen build.
_SOLVER_TIMEOUT = 120.0
# More workers on the frozen build to offset their higher startup cost
# (each one launches a copy of Dannify.exe in worker mode).
_DEFAULT_WORKERS = max(2, min(8, os.cpu_count() or 4))
_FROZEN_WORKERS = max(4, min(12, (os.cpu_count() or 4)))

# Inline worker source: copied verbatim into each subprocess so we
# don't need to install a worker script alongside the frozen exe.
#
# NOTE: lrclib hashes ``prefix + nonce`` with NO separator between them
# (matches the Rust reference at lrcget/src-tauri/.../challenge_solver.rs).
# The TOKEN we send in the X-Publish-Token header still uses a colon
# (``prefix:nonce``). That's only the header format. Easy to confuse.
_POW_WORKER_SRC = r"""
import hashlib, sys
prefix = sys.argv[1]
target = bytes.fromhex(sys.argv[2])
start = int(sys.argv[3])
stride = int(sys.argv[4])
pre = prefix.encode()
sha = hashlib.sha256
n = start
while True:
    if sha(pre + str(n).encode()).digest() < target:
        sys.stdout.write(str(n))
        sys.stdout.flush()
        break
    n += stride
"""

# Windows: suppress console-window flash from spawned solver subprocesses
# in the frozen desktop build. Mirrors what we already do in streaming.py
# for the ffmpeg pipes.
if os.name == 'nt':
    _POPEN_FLAGS = subprocess.CREATE_NO_WINDOW
    _POPEN_SI = subprocess.STARTUPINFO()
    _POPEN_SI.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _POPEN_SI.wShowWindow = subprocess.SW_HIDE
else:
    _POPEN_FLAGS = 0
    _POPEN_SI = None


class PublishError(RuntimeError):
    """Raised when the publish flow fails at any stage."""


# ---------------------------------------------------------------------------
# Challenge / proof-of-work
# ---------------------------------------------------------------------------
def request_challenge() -> dict[str, str]:
    """Ask lrclib for a fresh ``{prefix, target}`` proof-of-work challenge."""
    try:
        resp = _session.post(
            f'{LRCLIB_BASE}/request-challenge', timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f'Could not reach lrclib: {exc}') from exc
    if resp.status_code != 200:
        raise PublishError(
            f'lrclib challenge request failed: '
            f'HTTP {resp.status_code} {resp.text[:200]}'
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise PublishError('lrclib challenge response was not JSON') from exc
    prefix = data.get('prefix')
    target = data.get('target')
    if not isinstance(prefix, str) or not isinstance(target, str):
        raise PublishError('lrclib challenge response missing prefix/target')
    return {'prefix': prefix, 'target': target}


def _python_executable() -> tuple[str, dict[str, str]]:
    """Pick the command + env to spawn for solver workers.

    Returns ``(executable, extra_env)``: the parent merges *extra_env*
    into the child's environment.

    * **Dev mode**: ``sys.executable`` is the venv Python; we spawn it
      with ``-c`` and a tiny inline script.
    * **Frozen (PyInstaller windowed)**: ``sys.executable`` IS the
      Dannify.exe windowed app. To avoid re-launching the GUI in every
      worker we set ``DANNIFY_POW_WORKER`` so desktop.py's
      ``if __name__ == '__main__'`` block branches into solver mode
      before reaching ``main()`` (no FastAPI, no window).
    """
    return sys.executable, {}


def _hash_lt_target(digest: bytes, target: bytes) -> bool:
    """True iff *digest* sorts strictly before *target* (lex, byte order)."""
    return digest < target


def _solve_inprocess(prefix: str, target_hex: str, deadline: float) -> int:
    """Single-threaded in-process fallback. Used when subprocess spawning
    is unavailable (testing, restricted environments). Slow but always
    correct.

    Hash input is ``prefix + str(nonce)`` with NO separator: matches
    the lrclib server's algorithm (Rust reference). The colon-separated
    form is only used for the X-Publish-Token HTTP header.
    """
    target = bytes.fromhex(target_hex)
    pre = prefix.encode()
    sha = hashlib.sha256
    nonce = 0
    while True:
        if sha(pre + str(nonce).encode()).digest() < target:
            return nonce
        nonce += 1
        if (nonce & 0xFFFF) == 0 and time.monotonic() >= deadline:
            raise PublishError(
                f'Could not solve lrclib proof-of-work within '
                f'{_SOLVER_TIMEOUT}s'
            )


def _solve_subproc(
    prefix: str, target_hex: str, deadline: float, workers: int,
) -> int:
    """Multi-process search: spawns *workers* Python subprocs, each
    searching a disjoint nonce stride. The first one to find a valid
    nonce wins.
    """
    py, _extra_env = _python_executable()
    frozen = bool(getattr(sys, 'frozen', False))
    procs: list[tuple[subprocess.Popen, Optional[str]]] = []
    # Use a temp dir for the output files (frozen workers can't write to
    # stdout because the windowed exe has no stdout handle).
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix='dannify-pow-')
    try:
        for i in range(workers):
            out_path: Optional[str] = None
            if frozen:
                out_path = os.path.join(tmpdir, f'pow-{i}.txt')
                env = dict(os.environ)
                env['DANNIFY_POW_WORKER'] = (
                    f'{prefix}|{target_hex}|{i}|{workers}'
                )
                env['DANNIFY_POW_OUT'] = out_path
                p = subprocess.Popen(
                    [py],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=_POPEN_FLAGS,
                    startupinfo=_POPEN_SI,
                )
            else:
                p = subprocess.Popen(
                    [py, '-c', _POW_WORKER_SRC, prefix, target_hex,
                     str(i), str(workers)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=_POPEN_FLAGS,
                    startupinfo=_POPEN_SI,
                )
            procs.append((p, out_path))
        # Poll until one prints its nonce / writes its file.
        while time.monotonic() < deadline:
            for p, out_path in procs:
                if out_path:
                    if os.path.exists(out_path):
                        try:
                            with open(out_path, encoding='utf-8') as f:
                                txt = f.read().strip()
                        except OSError:
                            continue
                        if txt.isdigit():
                            return int(txt)
                elif p.poll() is not None:
                    out = (p.stdout.read() if p.stdout else b'').decode(
                        'utf-8', 'ignore',
                    ).strip()
                    if out.isdigit():
                        return int(out)
            time.sleep(0.05)
        raise PublishError(
            f'Could not solve lrclib proof-of-work within '
            f'{_SOLVER_TIMEOUT}s'
        )
    finally:
        for p, _ in procs:
            try:
                p.terminate()
            except Exception:
                pass
        # Clean up the temp files (best-effort).
        try:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def solve_challenge(
    prefix: str,
    target_hex: str,
    *,
    workers: Optional[int] = None,
    deadline: Optional[float] = None,
) -> int:
    """Return a nonce that satisfies the lrclib proof-of-work."""

    if workers is None:
        workers = (
            _FROZEN_WORKERS if getattr(sys, 'frozen', False)
            else _DEFAULT_WORKERS
        )
    if deadline is None:
        deadline = time.monotonic() + _SOLVER_TIMEOUT

    try:
        target = bytes.fromhex(target_hex.strip())
    except ValueError as exc:
        raise PublishError(f'Invalid target hex: {target_hex!r}') from exc
    if len(target) != 32:
        raise PublishError(f'Target must be 32 bytes, got {len(target)}')

    t0 = time.monotonic()
    nonce = _solve_subproc(prefix, target_hex, deadline, workers)

    # Self-verify before returning: catches the "off by one" or wrong
    # comparator-direction class of bugs before lrclib rejects us.
    # Hash input is ``prefix + nonce`` (NO colon): lrclib reference
    # algorithm. The token's colon is ONLY in the HTTP header.
    digest = hashlib.sha256(f'{prefix}{nonce}'.encode()).digest()
    if not _hash_lt_target(digest, target):
        raise PublishError(
            f'Internal: solved nonce {nonce} does not satisfy target'
        )

    logger.info(
        'lrclib publish: solved PoW with nonce {} in {:.2f}s',
        nonce, time.monotonic() - t0,
    )
    return nonce


def make_publish_token(challenge: dict[str, str]) -> str:
    """Combine a challenge with a solved nonce into ``prefix:nonce``."""
    prefix = challenge['prefix']
    nonce = solve_challenge(prefix, challenge['target'])
    return f'{prefix}:{nonce}'


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------
def publish(
    *,
    track_name: str,
    artist_name: str,
    album_name: str,
    duration: float,
    plain_lyrics: str = '',
    synced_lyrics: str = '',
) -> dict[str, Any]:
    """Submit lyrics to lrclib. Returns ``{'published': True}`` on success.

    Raises :class:`PublishError` on any failure (challenge, PoW, network,
    or non-201 response from lrclib).
    """

    track_name = (track_name or '').strip()
    artist_name = (artist_name or '').strip()
    album_name = (album_name or '').strip()
    plain_lyrics = (plain_lyrics or '').strip()
    synced_lyrics = (synced_lyrics or '').strip()
    if not track_name or not artist_name:
        raise PublishError('track_name and artist_name are required')
    try:
        duration_f = float(duration or 0)
    except (TypeError, ValueError):
        raise PublishError('duration must be a number')
    if duration_f <= 0:
        raise PublishError('duration must be > 0')

    challenge = request_challenge()
    token = make_publish_token(challenge)

    body = {
        'trackName': track_name,
        'artistName': artist_name,
        'albumName': album_name,
        'duration': duration_f,
        'plainLyrics': plain_lyrics,
        'syncedLyrics': synced_lyrics,
    }
    headers = {'X-Publish-Token': token, 'Content-Type': 'application/json'}
    try:
        resp = _session.post(
            f'{LRCLIB_BASE}/publish',
            json=body, headers=headers, timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f'lrclib publish request failed: {exc}') from exc

    if resp.status_code == 201:
        logger.info(
            'lrclib publish OK: {} by {} ({}s, {} chars synced)',
            track_name, artist_name, int(duration_f), len(synced_lyrics),
        )
        return {'published': True}

    msg = resp.text[:300]
    try:
        data = resp.json()
        if isinstance(data, dict):
            msg = data.get('message') or data.get('name') or msg
    except ValueError:
        pass
    raise PublishError(
        f'lrclib rejected publish (HTTP {resp.status_code}): {msg}'
    )
