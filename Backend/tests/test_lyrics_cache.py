"""What the lyrics cache remembers, and how it is written down."""

from __future__ import annotations

import json
import threading

import requests

from dannify import lyrics


class _Reply:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def _song():
    return {'name': 'Lemon', 'artists': ['Kenshi Yonezu']}


def test_an_unreachable_source_is_not_remembered_as_no_lyrics(tmp_path, monkeypatch):
    lyrics.init_cache(tmp_path)
    lyrics.clear_cache()
    calls = []

    def offline(url, params=None, timeout=None):
        calls.append(url)
        raise requests.ConnectionError('offline')

    monkeypatch.setattr(lyrics._session, 'get', offline)
    assert lyrics.fetch(_song(), ['lrclib']) is None
    first = len(calls)
    assert first > 0

    # Back online: it asks again rather than trusting the failed attempt.
    def online(url, params=None, timeout=None):
        calls.append(url)
        return _Reply(200, {'syncedLyrics': '[00:01.00]yume', 'plainLyrics': 'yume'})

    monkeypatch.setattr(lyrics._session, 'get', online)
    got = lyrics.fetch(_song(), ['lrclib'])
    assert got is not None and got.has_any()
    assert len(calls) > first


def test_a_real_miss_is_remembered(tmp_path, monkeypatch):
    lyrics.init_cache(tmp_path)
    lyrics.clear_cache()
    calls = []

    def none_found(url, params=None, timeout=None):
        calls.append(url)
        return _Reply(404) if 'get' in url else _Reply(200, [])

    monkeypatch.setattr(lyrics._session, 'get', none_found)
    assert lyrics.fetch(_song(), ['lrclib']) is None
    before = len(calls)
    assert lyrics.fetch(_song(), ['lrclib']) is None
    assert len(calls) == before  # served from the cache


def test_overlapping_saves_leave_a_readable_file(tmp_path):
    lyrics.init_cache(tmp_path)
    lyrics.clear_cache()
    with lyrics._lyrics_cache_lock:
        for i in range(3000):
            lyrics._lyrics_cache[f'a{i}|t{i}'] = lyrics.Lyrics(plain='x' * (i % 50))
    threads = []
    for _ in range(8):
        lyrics._persist_cache()
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(timeout=10)
    json.loads((tmp_path / 'lyrics_cache.json').read_text(encoding='utf-8'))
    lyrics.clear_cache()
