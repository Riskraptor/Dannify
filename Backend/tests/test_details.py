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
    from tests import _id3

    # A song saved as MP3, tagged the way those versions tagged them.
    plain.write_bytes(_id3.tag(_id3.txxx('DANNIFY_VIDEO_ID', 'KNEd-OkExKY')) + FRAMES)
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
    monkeypatch.setattr(providers, 'watch_track', lambda vid: None)
    monkeypatch.setattr(details, '_online', lambda: True)
    raw = sealed.read_bytes()
    assert details.refresh(root, sealed, []) == (details.FAILED, details.NOT_FOUND)
    assert sealed.read_bytes() == raw


def test_a_song_saved_from_a_music_video_is_found_by_its_recording(sealed_song, monkeypatch):
    # Not among the song results a search looks through: it used to be
    # "no details found" every time. Its credits come back as two artists,
    # each with their id.
    root, sealed, _ = sealed_song
    from dannify import providers

    monkeypatch.setattr(providers, 'find_match_for_video', lambda song, vid: None)
    monkeypatch.setattr(providers, 'watch_track', lambda vid: {
        'videoId': vid, 'title': 'Baikoko', 'thumbnails': [],
        'artists': [{'name': 'Mbosso', 'id': 'UCm'}, {'name': 'Diamond Platnumz', 'id': 'UCd'}],
    })
    assert details.refresh(root, sealed, []) == (details.UPDATED, '')
    head, _ = vault.inspect(sealed)
    assert head['artists'] == ['Mbosso', 'Diamond Platnumz']
    assert head['artist_ids'] == [{'name': 'Mbosso', 'id': 'UCm'}, {'name': 'Diamond Platnumz', 'id': 'UCd'}]


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


# ---------------------------------------------------------------------------
# Songs saved without their album (one at a time, before 4.9) get it back
# ---------------------------------------------------------------------------
@pytest.fixture
def no_album_lookup(sealed_song, monkeypatch):
    from dannify import providers

    def enrich(song, match):
        return {**song, 'name': 'Suzanna', 'artists': ['Sauti Sol'], 'album_name': ''}

    monkeypatch.setattr(providers, 'enrich_from_match', enrich)
    monkeypatch.setattr(providers, 'watch_track', lambda vid: {'videoId': vid, 'album': None})
    songs: list[dict] = []

    class Client:
        def search(self, query, filter=None, limit=10):
            assert filter == 'songs'
            return list(songs)

    monkeypatch.setattr(providers, '_ytm', lambda: Client())
    return (*sealed_song, songs)


def test_the_album_comes_from_the_recording_when_the_search_has_none(no_album_lookup, monkeypatch):
    root, sealed, _, _ = no_album_lookup
    from dannify import providers

    monkeypatch.setattr(providers, 'watch_track', lambda vid: {
        'videoId': vid, 'album': {'name': 'Midnight Train', 'id': 'MPREb_mt'},
    })
    assert details.refresh(root, sealed, []) == (details.UPDATED, '')
    head, _ = vault.inspect(sealed)
    assert head['album'] == 'Midnight Train'
    assert head['album_id'] == 'MPREb_mt'


def test_a_music_video_takes_the_album_of_the_same_song(no_album_lookup):
    root, sealed, _, songs = no_album_lookup
    songs.extend([
        # A single of the same name comes first, with no album of its own...
        {'videoId': 'SINGLE00001', 'title': 'Suzanna (Remix)', 'artists': [{'name': 'Sauti Sol'}],
         'album': {'name': 'Suzanna (Remix)', 'id': 'MPREb_single'}},
        {'videoId': 'NOALBUM0001', 'title': 'Suzanna', 'artists': [{'name': 'Sauti Sol'}], 'album': None},
        # ...and the album track with exactly this title is the one taken.
        {'videoId': 'ALBUMTRACK1', 'title': 'Suzanna', 'artists': [{'name': 'Sauti Sol'}],
         'album': {'name': 'Midnight Train', 'id': 'MPREb_mt'}},
    ])
    assert details.refresh(root, sealed, []) == (details.UPDATED, '')
    head, _ = vault.inspect(sealed)
    assert head['album'] == 'Midnight Train'
    assert head['video_id'] == 'KNEd-OkExKY'  # only the album was taken, not the recording


def test_some_other_songs_album_is_never_taken(no_album_lookup):
    root, sealed, _, songs = no_album_lookup
    songs.extend([
        {'videoId': 'OTHERSONG11', 'title': 'Sura Yako', 'artists': [{'name': 'Sauti Sol'}],
         'album': {'name': 'Live and Die in Afrika', 'id': 'MPREb_x'}},
        {'videoId': 'SOMEONEELSE', 'title': 'Suzanna', 'artists': [{'name': 'A Cover Band'}],
         'album': {'name': 'Covers', 'id': 'MPREb_c'}},
    ])
    assert details.refresh(root, sealed, []) == (details.UPDATED, '')
    head, _ = vault.inspect(sealed)
    assert not head.get('album')
    assert not head.get('album_id')


def test_a_match_names_its_album_by_id_only_when_it_is_the_same_album():
    from dannify import providers

    match = {'album': {'name': 'Midnight Train', 'id': 'MPREb_mt'}, 'thumbnails': []}
    assert providers.enrich_from_match({'name': 'S'}, match)['album_id'] == 'MPREb_mt'
    same = providers.enrich_from_match({'name': 'S', 'album_name': 'midnight train'}, match)
    assert same['album_id'] == 'MPREb_mt'
    other = providers.enrich_from_match({'name': 'S', 'album_name': 'A Deluxe Edition'}, match)
    assert 'album_id' not in other
