"""Release signatures: Ed25519 (RFC 8032), in plain Python.

Every hash an update is checked against comes from the same GitHub release
as the files, so a hash alone only proves the download was not damaged.
Anyone able to put files on the release could ship anything, with matching
hashes. A signature closes that: the release build signs what it publishes
with a private key that never leaves the release machine, and the app only
accepts what verifies against the public key built into it
(``updates.PUBLIC_KEY``).

Pure Python on purpose: nothing new to bundle. Verification is what runs on
users' machines. Signing is not constant-time, which only matters where the
private key is: the release machine, signing its own files.

What is signed is never a file on its own but a short statement naming the
kind of file, its version and its SHA-256 (``statement``), so a signature
for one file cannot be passed off for another, nor an old one for a new one.
"""

from __future__ import annotations

import hashlib

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)

STATEMENT_HEADER = b'dannify-release-v1'


def _sha512_int(*parts: bytes) -> int:
    return int.from_bytes(hashlib.sha512(b''.join(parts)).digest(), 'little')


def _recover_x(y: int, sign: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


# Points in extended coordinates (X, Y, Z, T): x = X/Z, y = Y/Z, xy = T/Z.
def _add(a, b):
    p1 = (a[1] - a[0]) * (b[1] - b[0]) % _P
    p2 = (a[1] + a[0]) * (b[1] + b[0]) % _P
    p3 = 2 * a[3] * b[3] * _D % _P
    p4 = 2 * a[2] * b[2] % _P
    e, f, g, h = p2 - p1, p4 - p3, p4 + p3, p2 + p1
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s: int, point):
    acc = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            acc = _add(acc, point)
        point = _add(point, point)
        s >>= 1
    return acc


def _equal(a, b) -> bool:
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(point) -> bytes:
    zinv = pow(point[2], _P - 2, _P)
    x = point[0] * zinv % _P
    y = point[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, 'little')


def _decompress(data: bytes):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _expand(secret: bytes):
    if len(secret) != 32:
        raise ValueError('an Ed25519 private key is 32 bytes')
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    a, _ = _expand(secret)
    return _compress(_mul(a, _G))


def sign(secret: bytes, message: bytes) -> bytes:
    a, prefix = _expand(secret)
    pub = _compress(_mul(a, _G))
    r = _sha512_int(prefix, message) % _L
    big_r = _compress(_mul(r, _G))
    h = _sha512_int(big_r, pub, message) % _L
    s = (r + h * a) % _L
    return big_r + int.to_bytes(s, 32, 'little')


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """True only for a valid signature; anything malformed is simply False."""

    try:
        if len(public) != 32 or len(signature) != 64:
            return False
        point_a = _decompress(public)
        if point_a is None:
            return False
        big_r_bytes = signature[:32]
        point_r = _decompress(big_r_bytes)
        if point_r is None:
            return False
        s = int.from_bytes(signature[32:], 'little')
        if s >= _L:
            return False
        h = _sha512_int(big_r_bytes, public, message) % _L
        return _equal(_mul(s, _G), _add(point_r, _mul(h, point_a)))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# What a release signs
# ---------------------------------------------------------------------------
def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def statement(kind: str, version: str, sha256_hex: str) -> bytes:
    """The exact bytes signed for one release file.

    ``kind`` is ``package`` (the update list) or ``installer`` (the setup).
    """

    for part in (kind, version, sha256_hex):
        if not part or '\n' in part:
            raise ValueError('incomplete release statement')
    return b'\n'.join(
        (
            STATEMENT_HEADER,
            kind.encode('utf-8'),
            version.encode('utf-8'),
            sha256_hex.lower().encode('ascii'),
        )
    )


def parse_signature(text: str) -> bytes:
    """A ``.sig`` file: the 64-byte signature as hex, whitespace ignored."""

    cleaned = ''.join(str(text or '').split())
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError:
        return b''
    return raw if len(raw) == 64 else b''


def verify_release(public_hex: str, kind: str, version: str, sha256_hex: str, signature_text: str) -> bool:
    try:
        public = bytes.fromhex(public_hex)
        message = statement(kind, version, sha256_hex)
    except (ValueError, UnicodeEncodeError):
        return False
    signature = parse_signature(signature_text)
    if not signature:
        return False
    return verify(public, message, signature)
