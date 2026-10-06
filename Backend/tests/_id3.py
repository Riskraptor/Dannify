"""ID3v2.3 tags for test files, written by hand.

Songs saved before they were sealed are MP3s with Dannify's tags in them.
The app no longer writes MP3 tags, so tests that need such a file build the
tag here instead.
"""

from __future__ import annotations

import struct

# MPEG-1 layer III, 128 kbps, 44.1 kHz: real frames, 417 bytes each.
FRAMES = (bytes.fromhex('fffb9064') + bytes(413)) * 20


def _size(n: int) -> bytes:
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def _frame(fid: str, payload: bytes) -> bytes:
    return fid.encode('ascii') + struct.pack('>I', len(payload)) + b'\0\0' + payload


def text(fid: str, value: str) -> bytes:
    """A text frame (TIT2, TPE1, ...), UTF-16 like the app's own were."""

    return _frame(fid, b'\x01' + value.encode('utf-16'))


def txxx(desc: str, value: str) -> bytes:
    return _frame('TXXX', b'\x01' + desc.encode('utf-16') + b'\0\0' + value.encode('utf-16'))


def tag(*frames: bytes) -> bytes:
    body = b''.join(frames)
    return b'ID3\x03\x00\x00' + _size(len(body)) + body


def mp3(*frames: bytes) -> bytes:
    """A small playable MP3 carrying *frames*."""

    return tag(*frames) + FRAMES
