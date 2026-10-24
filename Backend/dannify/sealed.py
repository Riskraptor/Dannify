"""Sealed logs: what the app writes about itself, readable by the developer only.

A shipped copy writes each line of its log sealed: X25519 (RFC 7748) with a
key made for this run, against the developer's public key (``LOG_PUBLIC``),
then the line enciphered and signed with keys drawn from what the two share.
Anyone opening the file sees lines of letters; the developer's own copy of
the private key, made from the release key (``log_private``), opens them
(packaging/read_logs.py).

Every line carries all it needs to be opened on its own, so a log turned over
in the middle, two copies writing to one file during an update, or the last
lines of it pasted into a report email can all still be read.

Plain Python, like the signatures (signing.py): nothing new to bundle. A run
from source writes plain lines unless asked (``DANNIFY_SEAL_LOGS=1``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys
import threading
from typing import Optional

# The developer's public key for logs, made from the release key by
# ``log_private`` (packaging/release_key.py log-public prints it).
LOG_PUBLIC = '5135d7fcfb7e7e7bd1295bd7238e3b07242c95107fa1e5a26b39d98cafd73f47'

MARK = '~'
_P = 2**255 - 19
_A24 = 121665
_BASE = (9).to_bytes(32, 'little')
_NONCE = 12
_TAG = 16


def x25519(scalar: bytes, point: bytes) -> bytes:
    """RFC 7748's X25519: *scalar* times *point*, both 32 bytes."""

    k = bytearray(scalar[:32])
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    n = int.from_bytes(k, 'little')
    u = bytearray(point[:32])
    u[31] &= 127
    x1 = int.from_bytes(u, 'little') % _P
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        bit = (n >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a = (x2 + z2) % _P
        aa = a * a % _P
        b = (x2 - z2) % _P
        bb = b * b % _P
        e = (aa - bb) % _P
        c = (x3 + z3) % _P
        d = (x3 - z3) % _P
        da = d * a % _P
        cb = c * b % _P
        x3 = (da + cb) * (da + cb) % _P
        z3 = x1 * (da - cb) * (da - cb) % _P
        x2 = aa * bb % _P
        z2 = e * (aa + _A24 * e) % _P
    if swap:
        x2, z2 = x3, z3
    return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, 'little')


def public_of(private: bytes) -> bytes:
    return x25519(private, _BASE)


def log_private(release_secret: bytes) -> bytes:
    """The developer's private key for logs, from the release key."""

    return hashlib.blake2b(release_secret, digest_size=32, person=b'dannify-logs-v1').digest()


def _keys(shared: bytes, sender: bytes, receiver: bytes) -> tuple[bytes, bytes]:
    both = hashlib.blake2b(shared + sender + receiver, digest_size=64, person=b'dannify-seal-v1').digest()
    return both[:32], both[32:]


def _stream(key: bytes, nonce: bytes, data: bytes) -> bytes:
    pad = hashlib.shake_256(key + nonce).digest(len(data))
    return (int.from_bytes(data, 'big') ^ int.from_bytes(pad, 'big')).to_bytes(len(data), 'big')


class Sealer:
    """Seals lines for one public key, with a key of its own made once."""

    def __init__(self, public: bytes, private: Optional[bytes] = None) -> None:
        own = private or os.urandom(32)
        self.sender = public_of(own)
        self.enc, self.mac = _keys(x25519(own, public), self.sender, public)

    def seal(self, text: str) -> str:
        nonce = os.urandom(_NONCE)
        body = _stream(self.enc, nonce, text.encode('utf-8'))
        tag = hmac.new(self.mac, self.sender + nonce + body, hashlib.blake2b).digest()[:_TAG]
        raw = self.sender + nonce + body + tag
        return MARK + base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


class Opener:
    """Opens sealed lines with the private key they were sealed for."""

    def __init__(self, private: bytes) -> None:
        self.private = private
        self.public = public_of(private)
        self._keys: dict[bytes, tuple[bytes, bytes]] = {}

    def open(self, line: str) -> Optional[str]:
        """The line as it was written, or None when it is not one sealed for us."""

        if not is_sealed(line):
            return None
        data = line.strip()[1:]
        try:
            raw = base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))
        except ValueError:
            return None
        if len(raw) < 32 + _NONCE + _TAG:
            return None
        sender, nonce, body, tag = raw[:32], raw[32:32 + _NONCE], raw[32 + _NONCE:-_TAG], raw[-_TAG:]
        if sender not in self._keys:
            self._keys[sender] = _keys(x25519(self.private, sender), sender, self.public)
        enc, mac = self._keys[sender]
        if not hmac.compare_digest(hmac.new(mac, sender + nonce + body, hashlib.blake2b).digest()[:_TAG], tag):
            return None
        return _stream(enc, nonce, body).decode('utf-8', errors='replace')

    def read(self, text: str) -> str:
        """A whole text with every sealed line in it opened."""

        out = []
        for line in text.splitlines():
            if is_sealed(line):
                opened = self.open(line)
                out.append(opened if opened is not None else '[a line that could not be opened]')
            else:
                out.append(line)
        return '\n'.join(out)


def is_sealed(line: str) -> bool:
    line = line.strip()
    return len(line) > 60 and line.startswith(MARK) and ' ' not in line


def sealing() -> bool:
    """Whether this run's log is sealed: a shipped copy's always is."""

    asked = os.getenv('DANNIFY_SEAL_LOGS', '').strip()
    if asked in ('0', '1'):
        return asked == '1' or bool(getattr(sys, 'frozen', False))
    return bool(getattr(sys, 'frozen', False))


_lock = threading.Lock()
_sealer: Optional[Sealer] = None


def line(text: str) -> str:
    """*text* as this run writes it to its log: sealed, or as it is."""

    global _sealer
    if not sealing():
        return text
    with _lock:
        if _sealer is None:
            _sealer = Sealer(bytes.fromhex(LOG_PUBLIC))
    return _sealer.seal(text)
