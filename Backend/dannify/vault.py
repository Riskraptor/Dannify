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
# Header revision, written as 'v'. 1 is implied by its absence: those were
# sealed by the first version, which threw the tags away and kept a second
# copy of the artwork. repair() brings them up to date.
FORMAT = 2

_master: Optional[bytes] = None
_key_path: Optional[Path] = None
# Why saved music is or is not available: see state().
_state: str = 'unknown'
# True while migrate() or repair() is rewriting the folder. A track being
# replaced is unreadable for the instant it takes, and the health check must
# not mistake a conversion in progress for a library nobody can open.
_busy: bool = False


# ---------------------------------------------------------------------------
# The key
# ---------------------------------------------------------------------------
def _machine_entropy() -> Optional[bytes]:
    """Something only this machine knows, mixed into the key's wrapping.

    DPAPI on its own ties the key to the Windows account. That is already
    enough that carrying vault.key to another PC achieves nothing, but the
    same account can exist on two machines, and a roaming or restored profile
    carries the account's DPAPI material with it. So the machine's own
    installation id and the serial of the volume the key sits on go in as
    additional entropy: unwrapping needs the account AND this machine.

    Be honest about the ceiling here. The app has to decrypt to play, on this
    machine, without asking anybody for anything. So whatever the app can do,
    somebody signed in as this user on this machine can also do. There is no
    arrangement of local storage that changes that. What this does is make the
    key non-portable, which is the part that was actually worth fixing.
    """

    parts = _entropy_parts()
    bits = [v for v in parts if v]
    if not bits:
        return None
    return hashlib.blake2b(
        b'|'.join(bits), person=b'dannify-host', digest_size=32,
    ).digest()


def _entropy_parts() -> tuple[Optional[bytes], Optional[bytes]]:
    """The machine's installation id and the volume serial, each or neither."""

    if os.name != 'nt':
        return (None, None)
    guid = serial = None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\Microsoft\Cryptography',
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            guid = str(winreg.QueryValueEx(key, 'MachineGuid')[0]).encode()
    except Exception:
        pass
    try:
        import ctypes

        root = os.environ.get('SystemDrive', 'C:') + '\\'
        number = ctypes.c_ulong(0)
        if ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), None, 0,
            ctypes.byref(number), None, None, None, 0,
        ):
            serial = str(number.value).encode()
    except Exception:
        pass
    return (guid, serial)


def _entropy_candidates() -> list[Optional[bytes]]:
    """Every entropy this machine might have wrapped a key with, best first.

    Both sources are read through a bare except, so the value depended on
    which ones happened to answer: one transient registry failure produced a
    different entropy, and unwrapping had no fallback, so a single bad read on
    one launch locked the whole library away permanently with nothing to be
    done about it. The combinations are cheap and there are four of them, so
    unwrapping tries them all before concluding a key is not ours.
    """

    guid, serial = _entropy_parts()
    seen: list[Optional[bytes]] = []
    for bits in ([guid, serial], [guid], [serial], []):
        kept = [v for v in bits if v]
        value = (
            hashlib.blake2b(
                b'|'.join(kept), person=b'dannify-host', digest_size=32,
            ).digest()
            if kept
            else None
        )
        if value not in seen:
            seen.append(value)
    return seen


def _dpapi(raw: bytes, entropy: Optional[bytes], unwrap: bool) -> bytes:
    """One call into CryptProtectData / CryptUnprotectData."""

    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [
            ('cbData', wintypes.DWORD),
            ('pbData', ctypes.POINTER(ctypes.c_char)),
        ]

    def blob(data: bytes) -> BLOB:
        return BLOB(
            len(data),
            ctypes.cast(
                ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char),
            ),
        )

    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    salt = ctypes.byref(blob(entropy)) if entropy else None
    out = BLOB()
    call = crypt32.CryptUnprotectData if unwrap else crypt32.CryptProtectData
    if not call(
        ctypes.byref(blob(raw)), None, salt, None, None, 0, ctypes.byref(out),
    ):
        raise OSError('DPAPI refused')
    result = ctypes.string_at(out.pbData, out.cbData)
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return result


def _protect(raw: bytes) -> bytes:
    """Wrap the key so a copy of the file is useless anywhere else.

    Everywhere but Windows it is stored as it is, which is honest: there is
    nothing on those platforms that would make the difference without a
    password the user has to type.
    """

    if os.name != 'nt':
        return b'RAW0' + raw
    try:
        salt = _machine_entropy()
        if salt is not None:
            return b'DPA2' + _dpapi(raw, salt, unwrap=False)
        return b'DPAP' + _dpapi(raw, None, unwrap=False)
    except Exception:
        logger.opt(exception=True).debug('could not protect the vault key')
        return b'RAW0' + raw


def _unprotect(stored: bytes) -> bytes:
    """Unwrap a key written by this or any earlier version."""

    tag, body = stored[:4], stored[4:]
    if tag == b'RAW0':
        return body
    if tag == b'DPAP':
        return _dpapi(body, None, unwrap=True)
    if tag == b'DPA2':
        last: Exception = ValueError('no entropy to try')
        for salt in _entropy_candidates():
            try:
                return _dpapi(body, salt, unwrap=True)
            except Exception as exc:
                last = exc
        raise last
    raise ValueError('unknown key format')


def _write_key(data: bytes) -> None:
    """Put the key on disk in a way that cannot half happen.

    write_bytes opens 'wb', which truncates first. Losing power or being killed
    in the moment between the truncate and the write left a zero length
    vault.key, and a zero length vault.key is every saved track gone for good.
    Written to one side and renamed over instead: a rename is atomic, so the
    file on disk is either the old key or the new one and never neither.
    """

    tmp = _key_path.with_name(_key_path.name + '.tmp')
    with open(tmp, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(_key_path)


def init(data_dir: Path) -> None:
    """Load this installation's key, making one the first time."""

    global _master, _key_path, _state
    _key_path = Path(data_dir) / 'vault.key'
    spare = _key_path.with_name('vault.key.bak')
    try:
        if _key_path.is_file():
            stored = _key_path.read_bytes()
            try:
                _master = _unprotect(stored)
            except Exception:
                # The copy kept from before the last re-wrap. This is the whole
                # reason it is kept: a key that stops unwrapping takes the
                # library with it, and there is nothing else to fall back on.
                if not spare.is_file():
                    raise
                logger.warning('the saved-music key would not open; using the spare')
                _master = _unprotect(spare.read_bytes())
                stored = b''  # force it to be written back below
            _state = 'ready'
            # An older wrapping still opens, and is tightened on the way past
            # so a key written before this stops being portable now. Only if
            # the new wrapping reads back: a key that cannot be unwrapped is
            # every saved track gone.
            want = _protect(_master)
            if stored[:4] != want[:4]:
                try:
                    if _unprotect(want) == _master:
                        if stored:
                            spare.write_bytes(stored)  # keep what did work
                        _write_key(want)
                        logger.debug('vault key re-wrapped for this machine')
                except Exception:
                    logger.opt(exception=True).debug('left the key wrapping alone')
            return
    except Exception:
        # A key we cannot read is worse than none: say so loudly rather than
        # quietly making a second one and orphaning everything already saved.
        logger.opt(exception=True).error(
            'The saved-music key at {} could not be read. Saved music stays '
            'locked until this is sorted out.', _key_path,
        )
        _master = None
        _state = 'unreadable'
        return

    _master = secrets.token_bytes(32)
    try:
        _key_path.parent.mkdir(parents=True, exist_ok=True)
        _write_key(_protect(_master))
        _state = 'ready'
    except OSError:
        logger.opt(exception=True).error('Could not write the saved-music key')
        _master = None
        _state = 'unwritable'


def ready() -> bool:
    return _master is not None


def busy() -> bool:
    """Whether a conversion is rewriting the music folder right now."""

    return _busy


def state() -> str:
    """Why saved music is or is not available, in one word.

    The app used to have only ready() and nothing else, so a key it could not
    read looked exactly like a library with no artwork and no album names, and
    a track that would not play looked like a track someone had deleted. That
    is three debugging sessions' worth of confusion for the sake of one string,
    which the window can now show to the person it is actually happening to.

    'unknown'    init() has not run
    'ready'      the key is loaded
    'unreadable' there is a key and it is not ours, or it is damaged
    'unwritable' there is no key and one could not be made
    """

    return _state


def key_path() -> Optional[Path]:
    return _key_path


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


def _find_in_file(path: Path, needle: bytes) -> int:
    """Where *needle* starts inside *path*, or -1.

    Used to point the header at the artwork already sitting in the payload
    instead of keeping a second copy of it.
    """

    if not needle:
        return -1
    span = len(needle)
    window = max(1 << 20, span * 2)
    at = 0
    tail = b''
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(window)
            if not chunk:
                return -1
            blob = tail + chunk
            found = blob.find(needle)
            if found >= 0:
                return at - len(tail) + found
            at += len(chunk)
            # Keep enough of the end that a match straddling the seam is seen.
            keep = span - 1
            tail = blob[-keep:] if keep > 0 else b''


def cover(path: Path) -> Optional[tuple[bytes, str]]:
    """The artwork of a sealed file.

    Normally this is a range of the payload: the artwork is part of the file
    we sealed, so the header says where it is rather than carrying a second
    copy. Decrypting it costs the few blocks it spans. Older containers, and
    the rare file whose artwork mutagen reports in a form that does not appear
    verbatim on disk, keep the copy, so both are read here.
    """

    head = read_header(path) or {}
    mime = str(head.get('cover_mime') or 'image/jpeg')

    at = head.get('cover_at')
    if at is not None:
        span = int(head.get('cover_len') or 0)
        if span > 0:
            try:
                data = b''.join(open_range(path, int(at), span))
                if len(data) == span:
                    return data, mime
            except Exception:
                return None

    raw = head.get('cover')
    if not raw:
        return None
    try:
        import base64

        return base64.b64decode(raw), mime
    except Exception:
        return None


def seal(source: Path, target: Path, meta: dict[str, Any]) -> Path:
    """Write *source* into *target* as a container, then remove the original."""

    if not ready():
        raise RuntimeError('no key; refusing to seal')
    source, target = Path(source), Path(target)
    # The last thing seal() does is delete the source. Handed the same path
    # twice it would write the container and then delete it, and the track
    # would simply be gone. The download path can produce that: it falls back
    # to globbing for whatever the encoder actually wrote, and a .dnf sitting
    # there from a previous attempt matches.
    if source == target or (
        source.exists() and target.exists() and source.samefile(target)
    ):
        raise ValueError(f'refusing to seal {source.name} onto itself')
    nonce = secrets.token_bytes(NONCE_LEN)
    key = _file_key(nonce)

    head = dict(meta)
    head['v'] = FORMAT
    head['ext'] = source.suffix.lower()
    head['size'] = source.stat().st_size
    # The header says WHERE the artwork is, not what it is. It is already in
    # the file we are about to seal, and an early version copied it into the
    # header as base64 as well: a quarter of a megabyte of duplicate on some
    # tracks, and a third again on top of that for the encoding. A range costs
    # two numbers, and reading it still only decrypts the blocks it spans.
    if 'cover' not in head and 'cover_at' not in head:
        art = _cover_of(source)
        if art:
            at = _find_in_file(source, art[0])
            if at >= 0:
                head['cover_at'] = at
                head['cover_len'] = len(art[0])
                head['cover_mime'] = art[1]
            else:
                # mutagen handed back bytes that are not on disk verbatim
                # (a re-encoded or reconstructed picture). Rare, and a copy is
                # better than no artwork.
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
    # Only once the container is safely on disk. Retried, because the library
    # scanner may have the file open to read its tags at this exact moment and
    # Windows will not delete it while anybody does. Leaving the original
    # behind is the one outcome that defeats the point: a plain copy of the
    # track, in the music folder, that any player can open. _drop_plain_twin
    # is the backstop for the case where it is still held after this.
    for attempt in range(5):
        try:
            source.unlink()
            break
        except OSError:
            if attempt == 4:
                logger.debug('could not remove {} after sealing', source)
            else:
                import time

                time.sleep(0.2 * (attempt + 1))
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


def _tags_of(path: Path) -> dict[str, Any]:
    """Everything the library would read off a plain file.

    The first version of this guessed title and artist from the filename and
    wrote nothing else, so an album, a duration and a video id that were
    sitting in the file's own tags went in the bin along with the file. It
    reads them properly now, using the same reader the library uses so a
    sealed track carries exactly what an unsealed one did.
    """

    stem = path.stem
    artist, _, title = stem.partition(' - ')
    guess = {
        'title': title or stem,
        'artist': artist if title else '',
        'album': '',
        'album_artist': '',
        'genre': '',
        'duration': 0,
        'track_number': 0,
        'video_id': '',
    }
    try:
        from . import library  # noqa: PLC0415  (circular at module level)

        read = library._read_tags(path)
    except Exception:
        logger.opt(exception=True).debug('could not read tags off {}', path)
        return guess

    for field in list(guess):
        value = read.get(field)
        if value:
            guess[field] = value
    artists = read.get('artists')
    if artists:
        guess['artists'] = artists
    return guess


_last_told = 0.0


def _tell(on_change, forced: bool = False) -> None:
    """Let the app know the music folder changed under it.

    Throttled, because every one of these costs the window a full rescan of
    the folder. Often enough that a list on screen is never wrong for long,
    rarely enough that a big library is not one rescan per track.
    """

    global _last_told
    if on_change is None:
        return
    import time

    now = time.monotonic()
    if not forced and now - _last_told < 1.5:
        return
    _last_told = now
    try:
        on_change(forced)
    except Exception:
        logger.opt(exception=True).debug('library refresh callback failed')


def _drop_plain_twin(plain: Path, sealed: Path) -> bool:
    """Remove a plain file whose sealed twin holds the same audio.

    Both existing is the state this whole thing exists to prevent: an ordinary
    file any player can open, sitting next to the container. It happens when
    the original could not be deleted at the time, usually because something
    had it open. The plain one goes only once the sealed one has been read
    back and proved to hold exactly the same bytes. Anything less than proof
    and both stay: nobody's music is worth a guess.
    """

    try:
        size = plain.stat().st_size
        head = read_header(sealed)
        if head is None or int(head.get('size') or -1) != size:
            return False
        if audio_size(sealed) != size:
            return False
        plain.unlink()
        logger.debug('removed the plain copy of {}', sealed.name)
        return True
    except OSError:
        return False


def _refresh_playlists(root: Path) -> int:
    """Point generated .m3u files at the tracks they name.

    A playlist written before the conversion lists the filenames the tracks
    had then, so every line in it names a file that is no longer there. The
    mapping is the same one for all of them, so rather than carry it around,
    each line that points at nothing is checked against the container of the
    same name: if that is there, the line is that.
    """

    fixed = 0
    for sheet in root.rglob('*.m3u'):
        try:
            lines = sheet.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        changed = False
        out = []
        for line in lines:
            entry = line.strip()
            if not entry or entry.startswith('#'):
                out.append(line)
                continue
            here = (sheet.parent / entry).resolve()
            if here.is_file():
                out.append(line)
                continue
            sealed = here.with_suffix(SUFFIX)
            if sealed.is_file():
                out.append(line[: len(line) - len(entry)] + entry.rsplit('.', 1)[0] + SUFFIX)
                changed = True
            else:
                out.append(line)
        if changed:
            try:
                sheet.write_text('\n'.join(out) + '\n', encoding='utf-8')
                fixed += 1
            except OSError:
                pass
    if fixed:
        logger.debug('updated {} playlist file(s)', fixed)
    return fixed


def _claim(root: Path):
    """Take the music folder for the duration of a conversion pass.

    Two copies converting the same folder at once is two processes renaming
    the same files: one seals a track while the other is halfway through
    reading it, and what survives is whatever the filesystem happened to do
    last. A lock file with the owning process id in it settles which copy is
    doing the work, and a stale one from a run that was killed is taken over
    rather than honoured for ever.
    """

    import errno

    lock = Path(root) / '.dannify-converting'
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            owner = int(lock.read_text(encoding='utf-8').strip() or 0)
        except Exception:
            owner = 0
        if owner and owner != os.getpid() and _process_alive(owner):
            return None
        try:  # stale: the copy that wrote it is gone
            lock.unlink()
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return None
    except OSError as exc:
        if exc.errno == errno.EACCES:
            return None
        raise
    try:
        os.write(fd, str(os.getpid()).encode())
    finally:
        os.close(fd)
    return lock


def _release(lock) -> None:
    try:
        if lock is not None:
            Path(lock).unlink(missing_ok=True)
    except OSError:
        pass


def _process_alive(pid: int) -> bool:
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def migrate(root: Path, on_progress=None, on_change=None) -> dict[str, int]:
    """Seal music that was downloaded before there were containers.

    Converted, never deleted. A file that cannot be sealed for any reason is
    left exactly as it was: somebody's music is not the place to be brave.
    Runs on a background thread at startup, so a large library does not hold
    the app closed.

    Which is exactly what made the first version of this so unpleasant. The
    window had already listed the library by then, with every track pointing
    at the .mp3 it was loaded from. Renaming those files out from under it
    left every cover a grey placeholder and every play a toast saying the file
    had been moved or deleted, and nothing said otherwise until the app was
    restarted. The whole point was that nobody should notice. So the library
    is told, as the work goes rather than only at the end.
    """

    global _busy
    root = Path(root)
    done = {'sealed': 0, 'skipped': 0, 'failed': 0}
    if not ready() or not root.is_dir():
        return done

    # A folder full of containers this key cannot open belongs to another
    # installation, and converting anything in it would seal somebody else's
    # music with a key they do not have. That is not a hypothetical: a second
    # copy pointed at the wrong folder did exactly this, and the tracks it
    # wrote could never be opened again by anyone.
    #
    # The test is whether ANY of them open, not whether all of them do. A
    # library of our own can easily hold an orphan or two, left by an install
    # that went wrong once, and refusing to convert forty tracks because of
    # one that cannot be read would be a worse bug than the one this prevents.
    mine = theirs = 0
    for found in root.rglob('*' + SUFFIX):
        if read_header(found) is None:
            theirs += 1
        else:
            mine += 1
            if mine > 2:
                break  # plainly ours; no need to read the rest
    if theirs and not mine:
        logger.error(
            'Every saved track in the music folder was sealed by a different '
            'installation of Dannify, so nothing in it will be converted.',
        )
        return done

    plain = [
        p for p in root.rglob('*')
        if p.is_file() and p.suffix.lower() in PLAIN_EXTS
    ]
    if not plain:
        return done

    held = _claim(root)
    if held is None:
        logger.info('another copy is already converting this folder; leaving it to it')
        return done

    logger.info('Sealing {} file(s) already in the music folder', len(plain))
    _busy = True
    try:
        changed = _seal_pass(root, plain, done, on_progress, on_change)
    finally:
        _release(held)
        # Cleared whatever happens. Left set by an exception it would blind
        # the health check for the rest of the run, which is the one thing
        # that check exists to notice.
        _busy = False

    if changed:
        _refresh_playlists(root)
        _tell(on_change, forced=True)
    logger.info(
        'Sealed {}, skipped {}, failed {}',
        done['sealed'], done['skipped'], done['failed'],
    )
    return done


def _seal_pass(root, plain, done, on_progress, on_change) -> int:
    """The body of migrate(), so _busy is always cleared."""

    changed = 0
    for index, path in enumerate(plain, 1):
        target = path.with_suffix(SUFFIX)
        if target.exists():
            done['skipped'] += 1
            if _drop_plain_twin(path, target):
                changed += 1
            continue
        try:
            meta = _tags_of(path)
            seal(path, target, meta)
            done['sealed'] += 1
            changed += 1
            _note(root, target, meta['title'], meta['artist'])
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
            try:
                on_progress(index, len(plain))
            except Exception:
                logger.opt(exception=True).debug('progress callback failed')
        if changed:
            _tell(on_change)

    # Anything whose original was still held when it was sealed. By now the
    # scanner has long since let go, so this is the pass that catches it.
    for path in plain:
        if path.is_file():
            target = path.with_suffix(SUFFIX)
            if target.is_file() and _drop_plain_twin(path, target):
                done['skipped'] += 1
                changed += 1

    return changed


def repair(root: Path, on_progress=None, on_change=None) -> dict[str, int]:
    """Bring containers written by the first version up to date.

    Those were sealed with a title and an artist guessed off the filename and
    nothing else, so albums, durations, track numbers and video ids were lost,
    and the artwork was copied into the header while still sitting in the
    payload. None of it is actually gone: the payload is the original file,
    byte for byte, tags and all. So each one is opened, read properly, and
    written back with a full header and the artwork left where it already was.

    Every file gets smaller. It is a read and a write per track on a
    background thread, once, and then never again.
    """

    global _busy
    root = Path(root)
    done = {'repaired': 0, 'skipped': 0, 'failed': 0, 'saved': 0}
    if not ready() or not root.is_dir():
        return done

    stale = []
    for path in sorted(root.rglob('*' + SUFFIX)):
        if not path.is_file():
            continue
        head = read_header(path)
        if head is None:
            done['skipped'] += 1  # not ours to read; leave it completely alone
            continue
        if int(head.get('v') or 1) >= FORMAT:
            continue
        stale.append((path, head))

    if not stale:
        return done

    held = _claim(root)
    if held is None:
        logger.info('another copy is already converting this folder; leaving it to it')
        return done

    logger.info('Bringing {} saved track(s) up to date', len(stale))
    # The decrypted copy this makes on its way is an ordinary playable file.
    # It used to be written into the music folder as "Artist - Title.restore.mp3",
    # which is precisely the thing a container exists to stop being there, and
    # if it could not be deleted afterwards it simply stayed. It goes to a
    # scratch folder of its own now, outside the library, and is removed in a
    # finally so no failure can leave one behind.
    import tempfile

    bench = Path(tempfile.mkdtemp(prefix='dnf-update-'))
    _busy = True
    changed = 0
    try:
        _repair_pass(root, stale, bench, done, on_progress, on_change)
    finally:
        _busy = False
        shutil_rmtree(bench)
        _release(held)

    if done['repaired']:
        _tell(on_change, forced=True)
    logger.info(
        'Updated {}, failed {}, {:.1f} MB given back',
        done['repaired'], done['failed'], done['saved'] / (1 << 20),
    )
    return done


def shutil_rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


def _repair_pass(root, stale, bench, done, on_progress, on_change) -> None:
    """The body of repair(), so the scratch folder is always cleaned up."""

    changed = 0
    for index, (path, head) in enumerate(stale, 1):
        ext = str(head.get('ext') or '.mp3')
        scratch = bench / (path.stem + ext)
        try:
            before = path.stat().st_size
            # Put the original back exactly as it was, read it, re-seal it.
            with open(scratch, 'wb') as out:
                for chunk in open_range(path):
                    out.write(chunk)

            meta = _tags_of(scratch)
            # The filename is the better source for these: the restored file's
            # own tags may be blank, and the old header already guessed.
            for field in ('title', 'artist'):
                if not meta.get(field) and head.get(field):
                    meta[field] = head[field]
            if head.get('video_id') and not meta.get('video_id'):
                meta['video_id'] = head['video_id']

            fresh = path.with_suffix(path.suffix + '.rebuilt')
            seal(scratch, fresh, meta)  # seal() removes the scratch file
            fresh.replace(path)
            done['repaired'] += 1
            done['saved'] += max(0, before - path.stat().st_size)
            changed += 1
            _note(root, path, meta['title'], meta['artist'])
        except Exception:
            logger.opt(exception=True).warning('Could not update {}; left as it was', path)
            done['failed'] += 1
            for junk in (path.with_suffix(path.suffix + '.rebuilt'),
                         path.with_suffix(path.suffix + '.rebuilt.part')):
                try:
                    junk.unlink(missing_ok=True)
                except OSError:
                    pass
        finally:
            try:
                scratch.unlink(missing_ok=True)
            except OSError:
                pass
        if on_progress:
            try:
                on_progress(index, len(stale))
            except Exception:
                logger.opt(exception=True).debug('progress callback failed')
        if changed and changed % 5 == 0:
            _tell(on_change)


def is_sealed(path: Path) -> bool:
    try:
        with open(path, 'rb') as f:
            return f.read(4) == MAGIC
    except OSError:
        return False
