"""Tests for client hint merge on per-URL downloads."""

from __future__ import annotations

from dannify.api import _merge_client_track_hints


def test_merge_applies_track_index_and_dates():
    base: dict = {
        'song_id': 'spotify:id',
        'url': 'https://open.spotify.com/track/x',
    }
    _merge_client_track_hints(
        base,
        {
            'track_number': 4,
            'album_track_total': 14,
            'release_date': '2022-03-01',
            'year': '2022',
            'noise': 'ignored',
        },
    )
    assert base['track_number'] == 4
    assert base['album_track_total'] == 14
    assert base['release_date'] == '2022-03-01'
    assert base['year'] == '2022'
    assert 'noise' not in base


def test_merge_ignores_invalid_track_number():
    base: dict = {'song_id': 'a'}
    _merge_client_track_hints(
        base, {'track_number': 'x', 'album_track_total': 0}
    )
    assert 'track_number' not in base
    assert 'album_track_total' not in base


def test_a_song_saved_from_its_album_keeps_the_album():
    # Looked up again by its video, it came back with no album: the page it
    # was saved from knew, and that is what it is filed under.
    base: dict = {'song_id': 'vid', 'album_name': ''}
    _merge_client_track_hints(base, {'album_name': ' Midnight Train ', 'album_id': 'MPREb_1', 'track_number': 2})
    assert (base['album_name'], base['album_id'], base['track_number']) == ('Midnight Train', 'MPREb_1', 2)


def test_the_lookups_own_album_stands():
    base: dict = {'song_id': 'vid', 'album_name': 'Afrikan Sauce', 'album_id': 'MPREb_A'}
    _merge_client_track_hints(base, {'album_name': 'Best of 2019', 'album_id': 'MPREb_B'})
    assert (base['album_name'], base['album_id']) == ('Afrikan Sauce', 'MPREb_A')


def test_the_album_id_is_taken_only_for_the_same_album():
    same: dict = {'song_id': 'vid', 'album_name': 'Afrikan Sauce'}
    _merge_client_track_hints(same, {'album_name': 'afrikan sauce', 'album_id': 'MPREb_A'})
    assert same['album_id'] == 'MPREb_A'
    other: dict = {'song_id': 'vid', 'album_name': 'Afrikan Sauce'}
    _merge_client_track_hints(other, {'album_name': 'Best of 2019', 'album_id': 'MPREb_B'})
    assert 'album_id' not in other
    # Nothing that looks like an album: nothing changes.
    plain: dict = {'song_id': 'vid'}
    _merge_client_track_hints(plain, {'album_name': '   ', 'album_id': 7})
    assert 'album_name' not in plain and 'album_id' not in plain
