"""Albums in the library: the songs that share an album and an artist, in
album order, and found again however their link was written."""

from __future__ import annotations

import pytest

from dannify import library


def song(title, album, artist='Sauti Sol', number=0, **extra):
    return {
        'title': title,
        'album': album,
        'artist': artist,
        'artists': [artist],
        'track_number': number,
        'duration': 200,
        'file': f'{artist}/{artist} - {title}.dnf',
        'added': 100.0,
        'problem': '',
        'album_id': '',
        **extra,
    }


@pytest.fixture
def shelf(monkeypatch):
    """A library made of the songs given, grouped the way a real scan does."""

    def use(tracks):
        canon = library._canonicalize_artists([t['artist'] for t in tracks])
        for t in tracks:
            t['group'] = canon.get(t['artist'], t['artist'])
        data = {'tracks': tracks, 'albums': library._album_list(tracks)}
        monkeypatch.setattr(library, '_get', lambda base: data)
        return data

    return use


def test_songs_of_one_album_are_one_album_in_track_order(shelf):
    shelf([
        song('Suzanna', 'Midnight Train', number=3),
        song('Midnight Train', 'Midnight Train', number=1),
        song('Brighter Days', 'Midnight Train', number=2, added=300.0),
    ])
    [album] = library.albums(None)
    assert (album['name'], album['artist'], album['count'], album['duration']) == (
        'Midnight Train', 'Sauti Sol', 3, 600,
    )
    # The newest song saved says when the album was added to.
    assert album['added'] == 300.0
    assert 'tracks' not in album  # the list is light; the page has the songs
    detail = library.album_detail(None, 'Sauti Sol', 'Midnight Train')
    assert [t['title'] for t in detail['tracks']] == ['Midnight Train', 'Brighter Days', 'Suzanna']


def test_a_single_named_after_its_album_is_not_an_album(shelf):
    shelf([
        song('Suzanna', 'Suzanna'),
        song('Lucy', ''),  # no album at all
        song('Melanin', 'Afrikan Sauce'),  # one song of a real album is
    ])
    assert [a['name'] for a in library.albums(None)] == ['Afrikan Sauce']


def test_an_ep_named_after_one_of_its_songs_is_kept_once_it_has_two(shelf):
    shelf([song('Suzanna', 'Suzanna', number=1), song('Suzanna (Remix)', 'Suzanna', number=2)])
    assert [(a['name'], a['count']) for a in library.albums(None)] == [('Suzanna', 2)]


def test_two_artists_with_an_album_of_one_name_have_two_albums(shelf):
    shelf([
        song('A', 'Greatest Hits', artist='Bien'),
        song('B', 'Greatest Hits', artist='Nviiri The Storyteller'),
    ])
    assert sorted(a['artist'] for a in library.albums(None)) == ['Bien', 'Nviiri The Storyteller']


def test_one_artist_spelt_two_ways_is_one_album(shelf):
    shelf([
        song('Lucy', 'The Lion of Sudah', artist='Bensoul', number=1),
        song('Navutishwa', 'THE LION OF SUDAH', artist='BENSOUL', number=2),
    ])
    [album] = library.albums(None)
    assert album['count'] == 2


def test_the_album_id_comes_from_whichever_song_knows_it(shelf):
    shelf([
        song('Old', 'Afrikan Sauce', number=1),
        song('New', 'Afrikan Sauce', number=2, album_id='MPREb_123'),
    ])
    assert library.albums(None)[0]['album_id'] == 'MPREb_123'


def test_an_album_is_found_however_its_link_was_written(shelf):
    shelf([song('Lucy', 'The Lion of Sudah', artist='Bensoul'), song('X', 'The Lion of Sudah', artist='Bensoul')])
    assert library.album_detail(None, 'BENSOUL', 'the lion of sudah')['count'] == 2
    assert library.album_detail(None, 'Bensoul', 'The Lion  of Sudah!')['count'] == 2
    assert library.album_detail(None, 'Bien', 'The Lion of Sudah') is None
    assert library.album_detail(None, 'Bensoul', 'Another') is None
    assert library.album_detail(None, 'Bensoul', '') is None


def test_the_picture_is_from_a_song_that_plays(shelf):
    shelf([
        song('Broken', 'Afrikan Sauce', number=1, problem='damaged'),
        song('Fine', 'Afrikan Sauce', number=2, added=200.0),
    ])
    album = library.albums(None)[0]
    assert album['cover'].endswith('Fine.dnf') and album['cover_v'] == 200


def test_a_sealed_song_reads_its_album_id(monkeypatch, tmp_path):
    from dannify import vault

    path = tmp_path / 'Sauti Sol - Suzanna.dnf'
    path.write_bytes(b'x')
    head = {'title': 'Suzanna', 'artist': 'Sauti Sol', 'album': 'Midnight Train', 'album_id': 'MPREb_9'}
    monkeypatch.setattr(vault, 'inspect', lambda p: (head, ''))
    assert library._read_tags(path)['album_id'] == 'MPREb_9'
    head.pop('album_id')
    assert library._read_tags(path)['album_id'] == ''
