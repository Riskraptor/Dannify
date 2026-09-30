"""Refreshing a saved song's details keeps the song itself exactly as it was."""

from __future__ import annotations

import secrets

import pytest

from dannify import details, downloader, library, vault
from dannify import lyrics as lyrics_mod

FRAMES = (bytes.fromhex('fffb9064') + bytes(413)) * 700  # real MPEG frames, over one read
JPEG = bytes.fromhex('ffd8ffe000104a46494600010100000100010000ffd9')


@pytest.fixture
def sealed_song(tmp_path, monkeypatch):
    saved = (vault._master, vault._keys, vault._state)
    vault._master, vault._keys, vault._state = secrets.token_bytes(32), [], 'ready'
    music = tmp_path / 'Music' / 'Sauti Sol'
    music.mkdir(parents=True)
    plain = music / 'Sauti Sol - Suzanna.mp3'
    plain.write_bytes(FRAMES)
    downloader.embed_video_id(plain, 'KNEd-OkExKY')
    sealed = vault.seal(plain, music / 'Sauti Sol - Suzanna.dnf', {
        'title': 'Suzanna', 'artist': 'Sauti Sol', 'artists': ['Sauti Sol'],
        'album': '', 'video_id': 'KNEd-OkExKY',
    })
    library.invalidate_cache()

    from dannify import providers

    asked = {}

    def by_video(song, vid):
        asked['video'] = vid
        return {'videoId': vid}

    def enrich(song, match):
        return {**song, 'name': 'Suzanna', 'artists': ['Sauti Sol'], 'album_name': 'Midnight Train',
                'cover_url': 'https://example.invalid/c.jpg', 'track_number': 7, 'genre': 'Afro-Pop'}

    monkeypatch.setattr(providers, 'find_match_for_video', by_video)
    monkeypatch.setattr(providers, 'enrich_from_match', enrich)
    monkeypatch.setattr(downloader, '_download_cover', lambda url: JPEG)
    monkeypatch.setattr(lyrics_mod, 'fetch', lambda song, p: lyrics_mod.Lyrics(synced='[00:01.00]Suzanna'))
    yield tmp_path / 'Music', sealed, asked
    vault._master, vault._keys, vault._state = saved
    library.invalidate_cache()


def _audio_frames(path):
    data = b''.join(vault.open_range(path))
    return data[data.index(bytes.fromhex('fffb9064')):]


def test_details_come_back_and_the_audio_stays(sealed_song):
    root, sealed, asked = sealed_song
    before = _audio_frames(sealed)

    state, why = details.refresh(root, sealed, ['lrclib'])

    assert (state, why) == (details.UPDATED, '')
    assert asked['video'] == 'KNEd-OkExKY'  # the same recording, not a search
    head, problem = vault.inspect(sealed)
    assert not problem
    assert head['album'] == 'Midnight Train'
    assert head['video_id'] == 'KNEd-OkExKY'
    assert _audio_frames(sealed) == before  # not one audio byte changed
    assert vault.cover(sealed)[0] == JPEG  # the artwork is in
    assert sealed.with_suffix('.lrc').read_text(encoding='utf-8') == '[00:01.00]Suzanna'
    assert sorted(p.name for p in sealed.parent.iterdir()) == [
        'Sauti Sol - Suzanna.dnf', 'Sauti Sol - Suzanna.lrc',
    ]


def test_a_song_it_cannot_find_is_left_alone(sealed_song, monkeypatch):
    root, sealed, _ = sealed_song
    from dannify import providers

    monkeypatch.setattr(providers, 'find_match_for_video', lambda song, vid: None)
    monkeypatch.setattr(details, '_online', lambda: True)
    raw = sealed.read_bytes()
    assert details.refresh(root, sealed, []) == (details.FAILED, details.NOT_FOUND)
    assert sealed.read_bytes() == raw


def test_a_song_replaced_while_it_streams_stops_cleanly(sealed_song):
    root, sealed, _ = sealed_song
    stream = vault.open_range(sealed, 0)
    first = next(stream)
    assert first
    details.refresh(root, sealed, [])  # the file is swapped underneath
    rest = b''.join(stream)
    # Nothing more from the old stream: no bytes of the new file read through
    # the old one's key.
    assert rest == b''
