"""A song's details inside its audio file: read for any format, written for MP4.

Reading goes through tinytag (MIT licensed). Writing is done here, for MP4
only: every song Dannify saves is AAC in an MP4 file before it is sealed,
and a sealed song keeps its details in its own header, so nothing else ever
needs writing. This replaced mutagen, whose GPL licence does not allow it in
a program that is not itself GPL.

What is written matches what mutagen wrote, item for item, so songs saved
before and after the change read back the same:

* ``©nam`` ``©ART`` (one value per artist) ``aART`` ``©alb`` ``©day``
  ``©gen`` ``trkn`` ``covr`` ``©lyr``
* ``----:com.dannify:VIDEO_ID``, the YouTube id the song came from
"""

from __future__ import annotations

import os
import re
import struct
from pathlib import Path
from typing import Any, Optional, Union

from loguru import logger

# Imported where it is used: library scans import this module, and tinytag is
# only needed for plain audio files, which most libraries no longer have.

MP4_SUFFIXES = frozenset({'.m4a', '.mp4'})
_VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
# Where the YouTube id lives, by format, as tinytag names it.
_VIDEO_ID_KEYS = ('dannify_video_id', 'video_id')
_LYRICS_KEYS = ('lyrics', 'unsyncedlyrics', 'unsynced_lyrics')


class Unsupported(Exception):
    """This file's layout is not one the MP4 writer will touch."""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _get(path: Union[str, Path], image: bool = False):
    from tinytag import TinyTag

    try:
        return TinyTag.get(str(path), image=image)
    except Exception:
        logger.opt(exception=True).debug('could not read the tags of {}', path)
        return None


def _first(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ''
    return str(value or '').strip()


def details(path: Union[str, Path]) -> dict[str, Any]:
    """Title, artist, album and the rest, or {} when the file has none."""

    tag = _get(path)
    if tag is None:
        return {}
    other = tag.other or {}
    return {
        'title': _first(tag.title),
        'artist': _first(tag.artist),
        'albumartist': _first(tag.albumartist),
        'album': _first(tag.album),
        'genre': _first(tag.genre),
        'track': int(tag.track or 0),
        'year': _first(tag.year),
        'duration': float(tag.duration or 0),
        'video_id': _video_id_in(other),
        'lyrics': _lyrics_in(other),
    }


def _video_id_in(other: dict[str, Any]) -> str:
    for key in _VIDEO_ID_KEYS:
        candidate = _first(other.get(key))
        if _VIDEO_ID.match(candidate):
            return candidate
    return ''


def _lyrics_in(other: dict[str, Any]) -> str:
    for key in _LYRICS_KEYS:
        text = _first(other.get(key))
        if text:
            return text
    return ''


def video_id(path: Union[str, Path]) -> str:
    """The YouTube id the file was saved from, or ''."""

    tag = _get(path)
    return _video_id_in(tag.other or {}) if tag is not None else ''


def lyrics(path: Union[str, Path]) -> str:
    """Plain lyrics kept in the file itself, or ''."""

    tag = _get(path)
    return _lyrics_in(tag.other or {}) if tag is not None else ''


def cover(path: Union[str, Path]) -> Optional[tuple[bytes, str]]:
    """The file's own artwork as ``(bytes, mime)``, or None."""

    tag = _get(path, image=True)
    if tag is None:
        return None
    try:
        image = tag.images.front_cover or tag.images.any
    except Exception:
        return None
    if image is None or not image.data:
        return None
    return bytes(image.data), image.mime_type or 'image/jpeg'


# ---------------------------------------------------------------------------
# Writing (MP4)
# ---------------------------------------------------------------------------
def writable(path: Union[str, Path]) -> bool:
    return Path(path).suffix.lower() in MP4_SUFFIXES


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack('>I4s', 8 + len(payload), kind) + payload


def _children(data: bytes, start: int, end: int) -> list[tuple[bytes, int, int, int]]:
    """``(kind, offset, header_length, size)`` of each box from *start* to *end*."""

    out = []
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack_from('>I4s', data, pos)
        header = 8
        if size == 1:
            if pos + 16 > end:
                raise Unsupported('a box is cut short')
            size = struct.unpack_from('>Q', data, pos + 8)[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            raise Unsupported(f'a {kind!r} box runs past its parent')
        out.append((kind, pos, header, size))
        pos += size
    return out


def _data(type_code: int, payload: bytes) -> bytes:
    # version 0, the type in the flags, then a locale of 0
    return _box(b'data', struct.pack('>II', type_code, 0) + payload)


def _text(name: bytes, values: list[str]) -> bytes:
    return _box(name, b''.join(_data(1, v.encode('utf-8')) for v in values))


def _freeform(mean: str, name: str, value: str) -> bytes:
    return _box(
        b'----',
        _box(b'mean', b'\0\0\0\0' + mean.encode('utf-8'))
        + _box(b'name', b'\0\0\0\0' + name.encode('utf-8'))
        + _data(1, value.encode('utf-8')),
    )


def _freeform_id(item: bytes) -> tuple[str, str]:
    """``(mean, name)`` of a ``----`` item."""

    mean = name = ''
    for kind, pos, header, size in _children(item, 8, len(item)):
        body = item[pos + header + 4 : pos + size]  # skip version/flags
        if kind == b'mean':
            mean = body.decode('utf-8', 'replace')
        elif kind == b'name':
            name = body.decode('utf-8', 'replace')
    return mean, name


_DANNIFY_ID = ('com.dannify', 'VIDEO_ID')
_HDLR = _box(b'hdlr', b'\0' * 8 + b'mdirappl' + b'\0' * 9)


def _items(fields: dict[str, Any]) -> tuple[dict[bytes, Optional[bytes]], Optional[str]]:
    """The ilst items *fields* ask for (None: take it out), and the video id."""

    items: dict[bytes, Optional[bytes]] = {}

    def text(name: bytes, value: Any) -> None:
        if value is None:
            return
        values = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
        values = [v for v in values if v]
        items[name] = _text(name, values) if values else None

    text(b'\xa9nam', fields.get('title'))
    artists = fields.get('artists')
    if artists is not None:
        text(b'\xa9ART', list(artists))
        text(b'aART', [artists[0]] if artists else [])
    text(b'\xa9alb', fields.get('album'))
    text(b'\xa9day', fields.get('date'))
    text(b'\xa9gen', fields.get('genre'))
    text(b'\xa9lyr', fields.get('lyrics'))
    if 'track' in fields:
        track = fields['track']
        if track:
            number, total = track
            items[b'trkn'] = _box(b'trkn', _data(0, struct.pack('>HHHH', 0, int(number), int(total or 0), 0)))
        else:
            items[b'trkn'] = None
    if 'cover' in fields:
        art = fields['cover']
        if art:
            blob, mime = art
            items[b'covr'] = _box(b'covr', _data(14 if mime == 'image/png' else 13, bytes(blob)))
        else:
            items[b'covr'] = None
    return items, fields.get('video_id')


def _shift_offsets(moov: bytes, delta: int, past: int) -> bytes:
    """*moov* with every chunk offset at or after *past* moved by *delta*.

    Chunk offsets count from the start of the file, so a moov that grows in
    front of the audio pushes the audio along by the same amount.
    """

    out = bytearray(moov)

    def walk(start: int, end: int) -> None:
        for kind, pos, header, size in _children(moov, start, end):
            body = pos + header
            if kind in (b'trak', b'mdia', b'minf', b'stbl'):
                walk(body, pos + size)
            elif kind in (b'stco', b'co64'):
                count = struct.unpack_from('>I', moov, body + 4)[0]
                wide = kind == b'co64'
                step = 8 if wide else 4
                if body + 8 + count * step > pos + size:
                    raise Unsupported('a chunk offset table is cut short')
                for i in range(count):
                    at = body + 8 + i * step
                    value = struct.unpack_from('>Q' if wide else '>I', moov, at)[0]
                    if value < past:
                        continue
                    value += delta
                    if value < 0 or (not wide and value > 0xFFFFFFFF):
                        raise Unsupported('a chunk offset would not fit')
                    struct.pack_into('>Q' if wide else '>I', out, at, value)

    walk(8, len(moov))
    return bytes(out)


def _shift_fragments(data: bytes, top: list, moov_at: int, delta: int) -> bytes:
    """Everything after the moov, with the fragments' absolute offsets moved.

    What YouTube serves is a fragmented MP4: the moov, an index (sidx), then
    pairs of moof and mdat. The index counts from its own end and each moof
    normally counts from itself (default-base-is-moof), so a moov that grows
    in front of them moves nothing they refer to. A fragment that gives an
    absolute base offset is moved like a chunk offset. An index ahead of the
    moov, or a random-access table (mfra) of absolute positions, is refused:
    a refused write leaves the file as it was.
    """

    moov_end = next(pos + size for kind, pos, _h, size in top if pos == moov_at)
    out = bytearray(data[moov_end:])
    for kind, pos, header, size in top:
        if kind == b'mfra':
            raise Unsupported('a random-access table of absolute positions')
        if kind == b'sidx' and pos < moov_at:
            raise Unsupported('an index ahead of the moov')
        if kind != b'moof' or pos < moov_end:
            continue
        for k2, p2, h2, s2 in _children(data, pos + header, pos + size):
            if k2 != b'traf':
                continue
            for k3, p3, h3, s3 in _children(data, p2 + h2, p2 + s2):
                if k3 != b'tfhd':
                    continue
                flags = int.from_bytes(data[p3 + h3 + 1 : p3 + h3 + 4], 'big')
                if not flags & 0x000001:  # no base-data-offset: relative
                    continue
                at = p3 + h3 + 8  # version/flags, track_ID
                base = struct.unpack_from('>Q', data, at)[0]
                if base >= moov_end:
                    struct.pack_into('>Q', out, at - moov_end, base + delta)
    return bytes(out)


def write_mp4(path: Union[str, Path], **fields: Any) -> None:
    """Set the given details in the MP4 file at *path*, leaving the rest.

    Fields: ``title``, ``artists`` (a list), ``album``, ``date``, ``genre``,
    ``track`` (``(number, total)``), ``cover`` (``(bytes, mime)``),
    ``lyrics``, ``video_id``. An empty value takes that detail out.
    The file is replaced in one step: a failure leaves it as it was.
    """

    path = Path(path)
    if not writable(path):
        raise Unsupported(f'not an MP4 file: {path.name}')
    data = path.read_bytes()
    top = _children(data, 0, len(data))
    moovs = [b for b in top if b[0] == b'moov']
    if len(moovs) != 1:
        raise Unsupported('no single moov box')
    _, moov_at, moov_header, moov_size = moovs[0]
    if moov_header != 8:
        raise Unsupported('a 64-bit moov box')
    moov = data[moov_at : moov_at + moov_size]

    wanted, vid = _items(fields)

    # moov > udta > meta > ilst, made where missing, everything else kept.
    udta_box = meta_box = ilst_box = None
    moov_rest: list[bytes] = []
    for kind, pos, header, size in _children(moov, 8, len(moov)):
        if kind == b'udta' and udta_box is None:
            udta_box = moov[pos : pos + size]
        else:
            moov_rest.append(moov[pos : pos + size])
    udta_rest: list[bytes] = []
    if udta_box is not None:
        for kind, pos, header, size in _children(udta_box, 8, len(udta_box)):
            if kind == b'meta' and meta_box is None:
                meta_box = udta_box[pos : pos + size]
            else:
                udta_rest.append(udta_box[pos : pos + size])
    meta_rest: list[bytes] = []
    if meta_box is not None:
        # meta is a full box: four bytes of version and flags first.
        for kind, pos, header, size in _children(meta_box, 12, len(meta_box)):
            if kind == b'ilst' and ilst_box is None:
                ilst_box = meta_box[pos : pos + size]
            elif kind != b'free':
                meta_rest.append(meta_box[pos : pos + size])
    if not any(b[4:8] == b'hdlr' for b in meta_rest):
        meta_rest.insert(0, _HDLR)

    kept: list[bytes] = []
    if ilst_box is not None:
        for kind, pos, header, size in _children(ilst_box, 8, len(ilst_box)):
            item = ilst_box[pos : pos + size]
            if kind in wanted:
                continue
            if kind == b'----' and vid is not None and _freeform_id(item) == _DANNIFY_ID:
                continue
            kept.append(item)
    added = [item for item in wanted.values() if item]
    if vid:
        added.append(_freeform(_DANNIFY_ID[0], _DANNIFY_ID[1], str(vid)))
    ilst = _box(b'ilst', b''.join(kept + added))
    meta = _box(b'meta', b'\0\0\0\0' + b''.join(meta_rest) + ilst)
    udta = _box(b'udta', b''.join(udta_rest) + meta)
    new_moov = _box(b'moov', b''.join(moov_rest) + udta)

    delta = len(new_moov) - moov_size
    moov_end = moov_at + moov_size
    rest = data[moov_end:]
    if delta and any(b[1] > moov_at for b in top):
        new_moov = _shift_offsets(new_moov, delta, moov_end)
        rest = _shift_fragments(data, top, moov_at, delta)

    scratch = path.with_name(path.name + '.tagging')
    try:
        with open(scratch, 'wb') as out:
            out.write(data[:moov_at])
            out.write(new_moov)
            out.write(rest)
        os.replace(scratch, path)
    finally:
        scratch.unlink(missing_ok=True)
