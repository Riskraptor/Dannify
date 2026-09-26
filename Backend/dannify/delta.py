"""Fetching just the files that changed out of a release's package archive.

A release is about 145 MB on disk and roughly 50 MB packed, but between two
versions almost none of it moves: Python itself, the WebView2 loader, the
media encoder and every third-party package stay byte for byte identical.
What actually changes is our own code, the built interface and the
executable.

So each release carries a list of every file with its hash
(package-<version>.json) and a zip of the whole app (package-<version>.zip).
The updater compares the list against the running copy and pulls only the
entries it lacks out of the zip with HTTP range requests. GitHub serves
ranges on release assets, so this needs no special hosting and no
per-version-pair patch files: a copy five versions old fetches exactly the
same way a copy one version old does.
"""

from __future__ import annotations

import hashlib
import struct
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Callable, Optional

_USER_AGENT = 'Dannify-Updater'
# Zip end-of-central-directory lives in the last 64 KB at worst (it can carry
# a comment), and the central directory itself is a few hundred KB here.
_EOCD_SEARCH = 66 * 1024
# Two wanted files closer together than this are fetched in one request, gap
# and all: a round trip costs more than half a megabyte of bytes.
_JOIN_GAP = 512 * 1024

_EOCD_SIG = b'PK\x05\x06'
_EOCD64_LOCATOR_SIG = b'PK\x06\x07'
_EOCD64_SIG = b'PK\x06\x06'


def _get(
    url: str,
    start: Optional[int] = None,
    end: Optional[int] = None,
    on_bytes: Optional[Callable[[int], None]] = None,
) -> bytes:
    headers = {'User-Agent': _USER_AGENT, 'Accept': '*/*'}
    if start is not None:
        headers['Range'] = f'bytes={start}-' + ('' if end is None else str(end))
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        if start is not None and response.status != 206:
            raise RuntimeError(f'range request refused ({response.status})')
        if on_bytes is None:
            return response.read()
        out = bytearray()
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            out += chunk
            on_bytes(len(chunk))
        return bytes(out)


def _content_length(url: str) -> int:
    request = urllib.request.Request(url, headers={'User-Agent': _USER_AGENT})
    request.get_method = lambda: 'HEAD'
    with urllib.request.urlopen(request, timeout=20) as response:
        return int(response.headers.get('Content-Length') or 0)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, version: str) -> dict[str, Any]:
    """Describe every file in an app folder: relative path, size and hash."""

    root = Path(root).resolve()
    files: dict[str, Any] = {}
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = {'size': path.stat().st_size, 'sha256': sha256_of(path)}
    return {'version': version, 'files': files}


# ---------------------------------------------------------------------------
# Reading entries out of a remote zip
# ---------------------------------------------------------------------------


class RemoteZip:
    """Just enough zip to pull named entries out of one over HTTP.

    Deliberately not zipfile: that wants a seekable file object and will
    happily read far more than asked for. Here every read is a range request
    whose size is known in advance, which is the whole point.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self.size = _content_length(url)
        if self.size <= 0:
            raise RuntimeError('could not size the archive')
        # name -> (method, compressed size, size, local header offset)
        self.entries: dict[str, tuple[int, int, int, int]] = {}
        self.dir_offset = 0
        self._read_directory()

    def _read_directory(self) -> None:
        tail_len = min(_EOCD_SEARCH, self.size)
        tail = _get(self.url, self.size - tail_len, self.size - 1)
        at = tail.rfind(_EOCD_SIG)
        if at < 0:
            raise RuntimeError('no end-of-central-directory record')

        count, dir_size, dir_offset = struct.unpack('<HII', tail[at + 10 : at + 20])
        # Zip64: the 32-bit fields saturate and the real ones live elsewhere.
        if dir_offset == 0xFFFFFFFF or count == 0xFFFF:
            loc = tail.rfind(_EOCD64_LOCATOR_SIG)
            if loc < 0:
                raise RuntimeError('zip64 locator missing')
            eocd64_at = struct.unpack('<Q', tail[loc + 8 : loc + 16])[0]
            head = _get(self.url, eocd64_at, eocd64_at + 55)
            if head[:4] != _EOCD64_SIG:
                raise RuntimeError('bad zip64 end record')
            count = struct.unpack('<Q', head[32:40])[0]
            dir_size, dir_offset = struct.unpack('<QQ', head[40:56])
        self.dir_offset = dir_offset

        blob = _get(self.url, dir_offset, dir_offset + dir_size - 1)
        pos = 0
        for _ in range(count):
            if blob[pos : pos + 4] != b'PK\x01\x02':
                break
            # Central directory file header, by field offset. Spelled out
            # rather than packed into one format string: the layout has
            # gaps, and getting it subtly wrong reads plausible nonsense.
            head = blob[pos : pos + 46]
            method = struct.unpack('<H', head[10:12])[0]
            comp_size = struct.unpack('<I', head[20:24])[0]
            uncomp_size = struct.unpack('<I', head[24:28])[0]
            name_len = struct.unpack('<H', head[28:30])[0]
            extra_len = struct.unpack('<H', head[30:32])[0]
            comment_len = struct.unpack('<H', head[32:34])[0]
            local_offset = struct.unpack('<I', head[42:46])[0]
            name = blob[pos + 46 : pos + 46 + name_len].decode('utf-8', 'replace')
            extra = blob[pos + 46 + name_len : pos + 46 + name_len + extra_len]
            if 0xFFFFFFFF in (comp_size, uncomp_size, local_offset):
                comp_size, uncomp_size, local_offset = _zip64_extra(
                    extra, comp_size, uncomp_size, local_offset
                )
            self.entries[name] = (method, comp_size, uncomp_size, local_offset)
            pos += 46 + name_len + extra_len + comment_len


def _zip64_extra(
    extra: bytes, comp: int, uncomp: int, offset: int
) -> tuple[int, int, int]:
    """Pull the real sizes out of a zip64 extra field."""

    pos = 0
    while pos + 4 <= len(extra):
        tag, size = struct.unpack('<HH', extra[pos : pos + 4])
        body = extra[pos + 4 : pos + 4 + size]
        if tag == 0x0001:
            at = 0
            if uncomp == 0xFFFFFFFF and at + 8 <= len(body):
                uncomp = struct.unpack('<Q', body[at : at + 8])[0]
                at += 8
            if comp == 0xFFFFFFFF and at + 8 <= len(body):
                comp = struct.unpack('<Q', body[at : at + 8])[0]
                at += 8
            if offset == 0xFFFFFFFF and at + 8 <= len(body):
                offset = struct.unpack('<Q', body[at : at + 8])[0]
            break
        pos += 4 + size
    return comp, uncomp, offset


def inside(root: Path, rel: str) -> bool:
    """Whether *rel* names something within *root*, and nothing else.

    Every name here came off the network and is about to be used as a path to
    write to. Path('C:/app') / 'C:/Windows/x.dll' is 'C:/Windows/x.dll' on
    Windows: an absolute right-hand side wins outright, and '..' walks out
    just as easily.
    """

    text = str(rel or '')
    if not text or text != text.strip():
        return False
    if text.startswith(('/', '\\')) or ':' in text:
        return False
    if any(part in ('..', '.', '') for part in text.replace('\\', '/').split('/')):
        return False
    try:
        (Path(root) / text).resolve().relative_to(Path(root).resolve())
    except (ValueError, OSError):
        return False
    return True


def fetch(
    zip_url: str,
    names: list[str],
    into: Path,
    progress: Optional[Callable[..., None]] = None,
) -> None:
    """Pull *names* out of the remote zip and write them under *into*.

    Entries sit back to back in the archive, so wanted ones that are close
    together are fetched in one request: a whole update is usually a handful
    of requests rather than two for every file.
    """

    into = Path(into)
    into.mkdir(parents=True, exist_ok=True)
    archive = RemoteZip(zip_url)
    missing = [n for n in names if n not in archive.entries]
    if missing:
        raise RuntimeError(f'{len(missing)} file(s) not in the archive')
    for name in names:
        if not inside(into, name):
            raise ValueError(f'archive entry outside the staging folder: {name!r}')

    # Each entry runs from its local header to the next entry's.
    order = sorted((meta[3], name) for name, meta in archive.entries.items())
    ends: dict[str, int] = {}
    for index, (offset, name) in enumerate(order):
        ends[name] = order[index + 1][0] if index + 1 < len(order) else archive.dir_offset

    groups: list[list[Any]] = []
    for name in sorted(names, key=lambda n: archive.entries[n][3]):
        start, end = archive.entries[name][3], ends[name]
        if groups and start - groups[-1][1] <= _JOIN_GAP:
            groups[-1][1] = max(groups[-1][1], end)
            groups[-1][2].append(name)
        else:
            groups.append([start, end, [name]])

    total = sum(end - start for start, end, _ in groups) or 1
    moved = [0]

    def on_bytes(count: int) -> None:
        moved[0] += count
        if progress:
            progress(min(1.0, moved[0] / total), moved[0], total)

    for start, end, members in groups:
        blob = _get(zip_url, start, end - 1, on_bytes=on_bytes)
        if len(blob) != end - start:
            raise RuntimeError('short read from the archive')
        for name in members:
            method, comp_size, uncomp_size, offset = archive.entries[name]
            at = offset - start
            header = blob[at : at + 30]
            if header[:4] != b'PK\x03\x04':
                raise RuntimeError(f'bad local header for {name}')
            name_len, extra_len = struct.unpack('<HH', header[26:30])
            data_at = at + 30 + name_len + extra_len
            raw = blob[data_at : data_at + comp_size]
            if len(raw) != comp_size:
                raise RuntimeError(f'short entry {name}')
            if method == 0:
                data = raw
            elif method == 8:
                data = zlib.decompress(raw, -15)
            else:
                raise RuntimeError(f'unsupported compression ({method}) for {name}')
            if len(data) != uncomp_size:
                raise RuntimeError(f'wrong size for {name}')
            target = into / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if progress:
        progress(1.0, total, total)
