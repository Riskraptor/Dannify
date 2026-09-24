"""Saved music that only plays inside Dannify.

A downloaded track used to land in the music folder as an ordinary .m4a that
any player could open. It is written as a ``.dnf`` container instead: a short
header and the original file, both encrypted with a key belonging to this
installation. Dannify decrypts it as it streams; nothing else can read it.

Be clear about what this is. It is a good lock on the front door, not DRM.
The audio has to reach the player as sound, and anything that can be played
can be recorded. What it does stop is the obvious thing: copying files out of
the music folder and handing them around, or pointing another player at them.

    header  DNF1 | nonce(16) | header length(4) | encrypted json
    payload the original tagged file, byte for byte, encrypted

The cipher is keyed BLAKE2b run as a counter mode, which is in the standard
library. Adding a real crypto package would drag an OpenSSL wheel of about ten
megabytes through every update, and this does not need one: each 64 byte block
of keystream is a hash of the nonce and the block number, so decrypting the
byte at any offset costs one hash. That is what keeps seeking instant and lets
a range request read the middle of a file without touching the rest.

The key is per installation and never leaves the machine. Losing it makes
every .dnf unreadable, so a plain index of what each file was lives beside
them: losing the key then costs a re-download rather than a folder full of
noise nobody can identify.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, BinaryIO, Optional

from loguru import logger

MAGIC = b'DNF1'
NONCE_LEN = 16
BLOCK = 64  # blake2b digest size, and so the keystream block size
SUFFIX = '.dnf'

_master: Optional[bytes] = None
_key_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# The key
# ---------------------------------------------------------------------------
def _protect(raw: bytes) -> bytes:
    """Wrap the key so a copy of the file is useless on another machine.

    Windows ties this to the user account. Everywhere else it is stored as it
    is, which is honest: there is nothing on those platforms that would make
    the difference without a password the user has to type.
    """

    if os.name != 'nt':
        return b'RAW0' + raw
    try:
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
        blob_in = BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        blob_out = BLOB()
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            raise OSError('CryptProtectData refused')
        out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return b'DPAP' + out
    except Exception:
        logger.opt(exception=True).debug('could not protect the vault key')
        return b'RAW0' + raw


def _unprotect(stored: bytes) -> bytes:
    tag, body = stored[:4], stored[4:]
    if tag == b'RAW0':
        return body
    if tag != b'DPAP':
        raise ValueError('unknown key format')
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    blob_in = BLOB(len(body), ctypes.cast(ctypes.create_string_buffer(body), ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError('CryptUnprotectData refused')
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return out


def init(data_dir: Path) -> None:
    """Load this installation's key, making one the first time."""

    global _master, _key_path
    _key_path = Path(data_dir) / 'vault.key'
    try:
        if _key_path.is_file():
            _master = _unprotect(_key_path.read_bytes())
            return
    except Exception:
        # A key we cannot read is worse than none: say so loudly rather than
        # quietly making a second one and orphaning everything already saved.
        logger.error('The saved-music key could not be read. Existing downloads stay locked.')
        _master = None
        return

    _master = secrets.token_bytes(32)
    try:
        _key_path.parent.mkdir(parents=True, exist_ok=True)
        _key_path.write_bytes(_protect(_master))
    except OSError:
        logger.opt(exception=True).error('Could not write the saved-music key')
        _master = None


def ready() -> bool:
    return _master is not None


# ---------------------------------------------------------------------------
# The cipher
# ---------------------------------------------------------------------------
def _file_key(nonce: bytes) -> bytes:
    if _master is None:
        raise RuntimeError('no key')
    return hashlib.blake2b(nonce, key=_master, person=b'dannify-file', digest_size=32).digest()


def _keystream(key: bytes, nonce: bytes, index: int) -> bytes:
    return hashlib.blake2b(
        nonce + index.to_bytes(8, 'little'), key=key, digest_size=BLOCK
    ).digest()


def _xor(key: bytes, nonce: bytes, data: bytes, offset: int) -> bytes:
    """XOR *data*, which starts at *offset* bytes into the payload."""

    out = bytearray(data)
    index, skip = divmod(offset, BLOCK)
    pos = 0
    while pos < len(out):
        block = _keystream(key, nonce, index)
        take = min(BLOCK - skip, len(out) - pos)
        for i in range(take):
            out[pos + i] ^= block[skip + i]
        pos += take
        index += 1
        skip = 0
    return bytes(out)


# ---------------------------------------------------------------------------
# Writing and reading
# ---------------------------------------------------------------------------
def _cover_of(path: Path) -> Optional[tuple[bytes, str]]:
    """The embedded artwork of a still-plain file, if it has any."""

    try:
        from mutagen import File as MutagenFile
        from mutagen.flac import FLAC
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4

        suffix = path.suffix.lower()
        if suffix in ('.mp3', '.wav', '.aac'):
            for frame in ID3(path).getall('APIC'):
                return frame.data, frame.mime or 'image/jpeg'
        elif suffix == '.m4a':
            art = MP4(path).tags.get('covr') if MP4(path).tags else None
            if art:
                first = art[0]
                fmt = getattr(first, 'imageformat', None)
                mime = 'image/png' if fmt == 14 else 'image/jpeg'  # MP4Cover.FORMAT_PNG
                return bytes(first), mime
        elif suffix == '.flac':
            pics = FLAC(path).pictures
            if pics:
                return pics[0].data, pics[0].mime or 'image/jpeg'
        else:
            audio = MutagenFile(path)
            pics = getattr(audio, 'pictures', None) if audio else None
            if pics:
                return pics[0].data, pics[0].mime or 'image/jpeg'
    except Exception:
        return None
    return None


def cover(path: Path) -> Optional[tuple[bytes, str]]:
    """The artwork of a sealed file, read from its header alone."""

    head = read_header(path) or {}
    raw = head.get('cover')
    if not raw:
        return None
    try:
        import base64

        return base64.b64decode(raw), str(head.get('cover_mime') or 'image/jpeg')
    except Exception:
        return None


def seal(source: Path, target: Path, meta: dict[str, Any]) -> Path:
    """Write *source* into *target* as a container, then remove the original."""

    if not ready():
        raise RuntimeError('no key; refusing to seal')
    source, target = Path(source), Path(target)
    nonce = secrets.token_bytes(NONCE_LEN)
    key = _file_key(nonce)

    head = dict(meta)
    head['ext'] = source.suffix.lower()
    head['size'] = source.stat().st_size
    # The artwork goes in the header, because the header is the only part
    # anything reads cheaply. Leaving it in the payload would mean decrypting
    # a whole track every time a list wanted a thumbnail.
    if 'cover' not in head:
        art = _cover_of(source)
        if art:
            import base64

            head['cover'] = base64.b64encode(art[0]).decode('ascii')
            head['cover_mime'] = art[1]
    blob = _xor(key, nonce, json.dumps(head).encode('utf-8'), 0)

    part = target.with_suffix(target.suffix + '.part')
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(source, 'rb') as src, open(part, 'wb') as out:
        out.write(MAGIC)
        out.write(nonce)
        out.write(len(blob).to_bytes(4, 'little'))
        out.write(blob)
        # The payload keystream starts fresh, so offset 0 of the audio is
        # block 0 and a seek lands on a block boundary.
        at = 0
        while True:
            chunk = src.read(1 << 20)
            if not chunk:
                break
            out.write(_xor(key, nonce, chunk, at))
            at += len(chunk)
        out.flush()
        os.fsync(out.fileno())
    part.replace(target)
    # Only once the container is safely on disk.
    try:
        source.unlink()
    except OSError:
        logger.debug('could not remove {} after sealing', source)
    return target


def read_header(path: Path) -> Optional[dict[str, Any]]:
    """The metadata, without touching the audio."""

    try:
        with open(path, 'rb') as f:
            if f.read(4) != MAGIC:
                return None
            nonce = f.read(NONCE_LEN)
            length = int.from_bytes(f.read(4), 'little')
            if length <= 0 or length > 1 << 20:
                return None
            blob = f.read(length)
        return json.loads(_xor(_file_key(nonce), nonce, blob, 0).decode('utf-8'))
    except Exception:
        return None


def payload_offset(path: Path) -> int:
    with open(path, 'rb') as f:
        f.seek(4 + NONCE_LEN)
        length = int.from_bytes(f.read(4), 'little')
    return 4 + NONCE_LEN + 4 + length


def audio_size(path: Path) -> int:
    return max(0, Path(path).stat().st_size - payload_offset(path))


def open_range(path: Path, start: int = 0, length: Optional[int] = None):
    """Yield decrypted audio from *start*, for streaming and seeking.

    A range request decrypts only the blocks it covers, which is what makes
    dragging the seek bar feel the same as it did on a plain file.
    """

    path = Path(path)
    with open(path, 'rb') as f:
        f.seek(4)
        nonce = f.read(NONCE_LEN)
        head_len = int.from_bytes(f.read(4), 'little')
        base = 4 + NONCE_LEN + 4 + head_len
        key = _file_key(nonce)

        total = max(0, path.stat().st_size - base)
        start = max(0, min(start, total))
        remaining = total - start if length is None else min(length, total - start)

        # Begin on a block boundary so the keystream lines up, then drop the
        # few bytes before the real start.
        aligned = (start // BLOCK) * BLOCK
        lead = start - aligned
        f.seek(base + aligned)
        at = aligned
        while remaining > 0:
            want = lead + remaining
            chunk = f.read(min(1 << 18, want + (BLOCK - want % BLOCK) % BLOCK))
            if not chunk:
                break
            clear = _xor(key, nonce, chunk, at)
            at += len(chunk)
            if lead:
                clear = clear[lead:]
                lead = 0
            if len(clear) > remaining:
                clear = clear[:remaining]
            remaining -= len(clear)
            yield clear


PLAIN_EXTS = {'.mp3', '.m4a', '.flac', '.ogg', '.wav', '.aac', '.opus'}


def _note(root: Path, sealed: Path, title: str, artist: str) -> None:
    """Record in plain text what a sealed file is.

    The header is encrypted like everything else, so without this a lost key
    would leave a folder nobody could even take an inventory of.
    """

    index = Path(root) / 'dannify-library.json'
    try:
        existing = json.loads(index.read_text(encoding='utf-8')) if index.is_file() else {}
        if not isinstance(existing, dict):
            existing = {}
    except Exception:
        existing = {}
    existing[sealed.relative_to(root).as_posix()] = {'title': title, 'artist': artist}
    try:
        index.write_text(json.dumps(existing, indent=1), encoding='utf-8')
    except OSError:
        pass


def migrate(root: Path, on_progress=None) -> dict[str, int]:
    """Seal music that was downloaded before there were containers.

    Converted, never deleted. A file that cannot be sealed for any reason is
    left exactly as it was: somebody's music is not the place to be brave.
    Runs on a background thread at startup, so a large library does not hold
    the app closed.
    """

    root = Path(root)
    done = {'sealed': 0, 'skipped': 0, 'failed': 0}
    if not ready() or not root.is_dir():
        return done

    plain = [
        p for p in root.rglob('*')
        if p.is_file() and p.suffix.lower() in PLAIN_EXTS
    ]
    if not plain:
        return done

    logger.info('Sealing {} file(s) already in the music folder', len(plain))
    for index, path in enumerate(plain, 1):
        target = path.with_suffix(SUFFIX)
        if target.exists():
            done['skipped'] += 1
            continue
        try:
            stem = path.stem
            artist, _, title = stem.partition(' - ')
            seal(path, target, {
                'title': title or stem,
                'artist': artist if title else '',
                'album': '',
                'video_id': '',
            })
            done['sealed'] += 1
            _note(root, target, title or stem, artist if title else '')
        except Exception:
            logger.opt(exception=True).warning('Could not seal {}; left alone', path)
            done['failed'] += 1
            # A half-written container helps nobody.
            for junk in (target, target.with_suffix(target.suffix + '.part')):
                try:
                    if junk.exists() and not path.exists():
                        continue  # the original is gone: keep what we have
                    junk.unlink(missing_ok=True)
                except OSError:
                    pass
        if on_progress:
            on_progress(index, len(plain))

    logger.info(
        'Sealed {}, skipped {}, failed {}', done['sealed'], done['skipped'], done['failed']
    )
    return done


def is_sealed(path: Path) -> bool:
    try:
        with open(path, 'rb') as f:
            return f.read(4) == MAGIC
    except OSError:
        return False
