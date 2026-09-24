"""One file for everything the app ships and reads but does not execute.

The install folder used to carry the built interface as a folder of files:
``frontend/dist/index.html`` next to ``assets/index-IN4dTkni.js`` and a
stylesheet. Anybody who opened it could read the whole front end, and what it
looked like was a web page someone had dropped into Program Files rather than
a program. The same went for ``dannify/clients.json`` sitting on its own.

They live in a single ``dannify.res`` now. The format is a marker, a
compressed index, and the members end to end::

    DNR1 | index_len(4, little) | deflate(json index) | member bytes...

The index maps a name to ``[offset, stored, raw]``. ``stored == raw`` means the
member is held as it was: deflate loses on a PNG or a woff2 and there is no
sense paying to find that out twice.

This is compression, not encryption. A key shipped in the same folder as the
thing it locks is not a secret, and pretending otherwise would be worse than
not trying: it would suggest the contents are protected when anyone willing to
spend an afternoon can read them. What it does do is keep the folder from
reading as a web page, and take about 700 KB off the install on the way.
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from typing import Optional

MAGIC = b'DNR1'

# Bytes we already know not to bother deflating. Every one of these is a
# compressed container: running it through zlib spends time to grow the file.
_OPAQUE = {'.png', '.jpg', '.jpeg', '.webp', '.woff2', '.woff', '.ico', '.gz',
           '.zip', '.mp3', '.m4a'}


def pack(members: dict[str, bytes]) -> bytes:
    """Build a resource file from ``{name: bytes}``.

    Names are the paths callers will ask for later, always with forward
    slashes. Order is sorted so a rebuild of unchanged input gives a byte
    identical file, which is what lets a delta update skip it.
    """

    index: dict[str, list[int]] = {}
    body = bytearray()
    for name in sorted(members):
        raw = members[name]
        suffix = ('.' + name.rsplit('.', 1)[-1].lower()) if '.' in name else ''
        if suffix in _OPAQUE:
            stored = raw
        else:
            squeezed = zlib.compress(raw, 9)
            stored = squeezed if len(squeezed) < len(raw) else raw
        index[name] = [len(body), len(stored), len(raw)]
        body += stored

    head = zlib.compress(json.dumps(index, separators=(',', ':')).encode(), 9)
    return MAGIC + struct.pack('<I', len(head)) + head + bytes(body)


class Pack:
    """Read side of a resource file.

    Members are inflated when first asked for and kept after that. The whole
    thing is about a megabyte, so holding the compressed bytes in memory costs
    less than the file handle bookkeeping of doing otherwise, and a member
    served twice is not decompressed twice.
    """

    def __init__(self, blob: bytes) -> None:
        if blob[:4] != MAGIC:
            raise ValueError('not a resource file')
        head_len = struct.unpack('<I', blob[4:8])[0]
        self._index: dict[str, list[int]] = json.loads(
            zlib.decompress(blob[8:8 + head_len]),
        )
        self._body = blob[8 + head_len:]
        self._cache: dict[str, bytes] = {}
        # One fingerprint for the whole pack, for ETags. Per-member hashes
        # would mean reading every member to answer a conditional request,
        # and the pack cannot change without the app being replaced anyway.
        self.stamp = format(zlib.crc32(blob) & 0xFFFFFFFF, '08x')

    @classmethod
    def load(cls, path: Path) -> 'Pack':
        return cls(Path(path).read_bytes())

    def __contains__(self, name: str) -> bool:
        return name in self._index

    def names(self) -> list[str]:
        return list(self._index)

    def size(self, name: str) -> int:
        """Length of a member after decompression, without decompressing it."""

        return self._index[name][2]

    def read(self, name: str) -> bytes:
        hit = self._cache.get(name)
        if hit is not None:
            return hit
        offset, stored, raw = self._index[name]
        chunk = self._body[offset:offset + stored]
        if stored != raw:
            chunk = zlib.decompress(chunk)
        self._cache[name] = chunk
        return chunk


_bundle: Optional[Pack] = None
_looked = False


def bundle(bundle_dir: Optional[Path] = None) -> Optional[Pack]:
    """The shipped resource file, or ``None`` in a source checkout.

    A checkout has no packed file and does not want one: the interface is
    served straight out of ``frontend/dist`` so a rebuild of the front end
    shows up on a refresh.
    """

    global _bundle, _looked
    if _looked:
        return _bundle
    _looked = True
    if bundle_dir is not None:
        path = Path(bundle_dir) / 'dannify.res'
        if path.is_file():
            try:
                _bundle = Pack.load(path)
            except Exception:
                _bundle = None
    return _bundle


def resource(name: str, bundle_dir: Optional[Path] = None) -> Optional[bytes]:
    """One member by name, or ``None`` if there is no pack or no such member."""

    got = bundle(bundle_dir)
    if got is None or name not in got:
        return None
    try:
        return got.read(name)
    except Exception:
        return None
