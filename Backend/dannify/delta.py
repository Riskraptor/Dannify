"""Updates that download only what changed.

A release is about 145 MB on disk and roughly 50 MB packed, but between two
versions almost none of it moves: Python itself, the WebView2 loader, the
media encoder and every third-party package stay byte for byte identical.
What actually changes is our own code, the built interface and the
executable, which together come to a couple of megabytes.

So rather than shipping the whole installer every time, each release also
carries two small things: a manifest listing every file with its hash, and
a zip of the complete app. The client reads the manifest, works out which
files it does not already have, and then pulls just those entries out of
the zip using HTTP range requests. GitHub serves ranges on release assets,
so this needs no special hosting and no per-version-pair patch files: a copy
five versions old fetches exactly the same way a copy one version old does.

The full installer is still published and still used when this path cannot
be trusted, which keeps a bad delta from ever being the only way forward.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import struct
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

_USER_AGENT = 'Dannify-Updater'
# Past this there is nothing to gain over just fetching the installer, and a
# long series of range requests is more to go wrong.
MAX_DELTA_BYTES = 40 * 1024 * 1024
# Zip end-of-central-directory lives in the last 64 KB at worst (it can carry
# a comment), and the central directory itself is a few hundred KB here.
_EOCD_SEARCH = 66 * 1024

# An installed copy holds more than our build produces. Setup writes its own
# uninstaller next to the app and copies the ship-time settings into config/.
# Neither is in the manifest, which is built from the app folder alone, so a
# plain "anything the manifest does not list is stale" rule would take the
# uninstaller away and reset settings the installer owns, on the first
# partial update. Those files are not ours to remove, whatever is missing
# from the manifest.
_INSTALLER_OWNED_DIRS = ('config/',)
_INSTALLER_OWNED_NAMES = re.compile(r'^unins\d*\.(exe|dat|msg)$', re.IGNORECASE)


def is_ours(rel: str) -> bool:
    """True when *rel* is a file this build produces, and may remove."""

    rel = rel.replace('\\', '/').lstrip('/').lower()
    if any(rel.startswith(d) for d in _INSTALLER_OWNED_DIRS):
        return False
    return not _INSTALLER_OWNED_NAMES.match(rel)


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
# Reading single entries out of a remote zip
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
        self._entries: dict[str, tuple[int, int, int, int]] = {}
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
            self._entries[name] = (method, comp_size, uncomp_size, local_offset)
            pos += 46 + name_len + extra_len + comment_len

    def names(self) -> list[str]:
        return list(self._entries)

    def compressed_size(self, name: str) -> int:
        return self._entries[name][1]

    def read(self, name: str, on_bytes: Optional[Callable[[int], None]] = None) -> bytes:
        """Fetch and decompress one entry.

        *on_bytes* is called with each chunk's size as it arrives. The app
        executable is thirteen megabytes on its own, so without this the
        progress bar would sit still for most of the download and then jump.
        """

        method, comp_size, uncomp_size, local_offset = self._entries[name]
        # The local header repeats the name and may carry a different extra
        # field, so read it to learn where the data actually starts.
        header = _get(self.url, local_offset, local_offset + 29)
        if header[:4] != b'PK\x03\x04':
            raise RuntimeError(f'bad local header for {name}')
        name_len, extra_len = struct.unpack('<HH', header[26:30])
        start = local_offset + 30 + name_len + extra_len
        raw = (
            _get(self.url, start, start + comp_size - 1, on_bytes=on_bytes)
            if comp_size
            else b''
        )
        if method == 0:
            data = raw
        elif method == 8:
            data = zlib.decompress(raw, -15)
        else:
            raise RuntimeError(f'unsupported compression ({method}) for {name}')
        if uncomp_size and len(data) != uncomp_size:
            raise RuntimeError(f'short read for {name}')
        return data


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


# ---------------------------------------------------------------------------
# Planning and fetching
# ---------------------------------------------------------------------------


def plan(
    app_dir: Path,
    manifest: dict[str, Any],
    progress: Optional[Callable[..., None]] = None,
) -> dict[str, Any]:
    """Work out what this installation is missing.

    Returns ``{changed, removed, bytes}``. Hashing the whole folder costs a
    second or two of disk, which is nothing against downloading 50 MB — but
    it is a second or two with nothing on screen, so it reports as it goes.
    """

    app_dir = Path(app_dir).resolve()
    wanted = manifest.get('files') or {}
    changed: list[str] = []
    total = 0
    seen = 0
    count = len(wanted) or 1
    for rel, meta in wanted.items():
        seen += 1
        if progress and seen % 16 == 0:
            progress(seen * 100.0 / count, 'Checking what changed')
        local = app_dir / rel
        try:
            if not local.is_file() or local.stat().st_size != meta['size']:
                changed.append(rel)
                total += int(meta['size'])
                continue
            if sha256_of(local) != meta['sha256']:
                changed.append(rel)
                total += int(meta['size'])
        except OSError:
            changed.append(rel)
            total += int(meta.get('size') or 0)

    have = {
        p.relative_to(app_dir).as_posix()
        for p in app_dir.rglob('*')
        if p.is_file()
    }
    removed = sorted(rel for rel in have - set(wanted) if is_ours(rel))
    return {'changed': changed, 'removed': removed, 'bytes': total}


def fetch(
    zip_url: str,
    names: list[str],
    into: Path,
    progress: Optional[Callable[..., None]] = None,
) -> None:
    """Pull *names* out of the remote zip and write them under *into*."""

    into = Path(into)
    into.mkdir(parents=True, exist_ok=True)
    archive = RemoteZip(zip_url)
    missing = [n for n in names if n not in archive.names()]
    if missing:
        raise RuntimeError(f'{len(missing)} file(s) not in the archive')

    done = 0
    total = sum(archive.compressed_size(n) for n in names) or 1

    for index, name in enumerate(names, 1):
        label = f'Downloading {index} of {len(names)}'
        got = [0]

        def on_bytes(count: int, _got=got) -> None:
            _got[0] += count
            if progress:
                progress(min(99.0, (done + _got[0]) * 100.0 / total), label)

        if progress:
            progress(min(99.0, done * 100.0 / total), label)
        data = archive.read(name, on_bytes=on_bytes)
        target = into / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        done += archive.compressed_size(name)
    if progress:
        progress(100.0, 'Downloaded')


def write_plan(staging: Path, manifest: dict[str, Any], removed: list[str]) -> Path:
    """Leave instructions the applier can follow after we have exited."""

    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / 'apply.json'
    path.write_text(
        json.dumps(
            {
                'version': manifest.get('version', ''),
                'removed': removed,
                'files': manifest.get('files', {}),
            },
            indent=2,
        ),
        encoding='utf-8',
    )
    return path


def verify_staged(staging: Path, changed: list[str], manifest: dict[str, Any]) -> bool:
    """Every downloaded file must match the manifest before anything moves."""

    files = manifest.get('files') or {}
    for rel in changed:
        meta = files.get(rel)
        local = Path(staging) / rel
        if meta is None or not local.is_file():
            logger.debug('staged file missing: {}', rel)
            return False
        if local.stat().st_size != meta['size'] or sha256_of(local) != meta['sha256']:
            logger.debug('staged file does not match the manifest: {}', rel)
            return False
    return True
