"""Matching a song to a saved file, and grouping artists."""

from __future__ import annotations

import pytest

from dannify import library


@pytest.mark.parametrize('a, b', [
    ('Beyoncé', 'Beyonce'),
    ('BENSOUL', 'Bensoul'),
    ('Sauti  Sol!', 'sauti sol'),
])
def test_fold_treats_spelling_noise_as_the_same(a, b):
    assert library.fold(a) == library.fold(b)


def test_fold_keeps_letters_in_any_script():
    assert library.fold('米津玄師') == '米津玄師'
    assert library.fold('Король и Шут') == 'король и шут'
    assert library.fold('아이유') != ''
    assert library.fold('夜に駆ける') != library.fold('アイドル')


def _index(tracks):
    data = {'by_video_id': {}, 'tracks': tracks,
            'by_key': {library._locate_key(t['artist'], t['title']): t['file'] for t in tracks}}
    return data


def test_a_non_latin_song_is_not_mistaken_for_another(monkeypatch):
    tracks = [{'artist': '米津玄師', 'title': '馬と鹿', 'file': '米津玄師 - 馬と鹿.dnf'}]
    monkeypatch.setattr(library, '_get', lambda base: _index(tracks))
    assert library.locate(None, artist='アイユ', title='夜に駆ける') is None
    assert library.locate(None, artist='YOASOBI', title='アイドル') is None
    assert library.locate(None, artist='米津玄師', title='馬と鹿')['file'] == '米津玄師 - 馬と鹿.dnf'


def test_no_title_matches_nothing(monkeypatch):
    tracks = [{'artist': 'A', 'title': '🎵', 'file': 'A - x.dnf'}]
    monkeypatch.setattr(library, '_get', lambda base: _index(tracks))
    assert library.locate(None, artist='A', title='🔥') is None


@pytest.mark.parametrize('short, long, same', [
    ('Drake', 'Drake Bell', False),
    ('Future', 'Future Islands', False),
    ('Travis', 'Travis Scott', False),
    ('Stephen Kasolo', 'Stephen Kasolo Kitole', True),
    ('Bensoul', 'BENSOUL', True),
])
def test_artist_grouping(short, long, same):
    assert library._same_artist(short, long) is same


def test_lyrics_matching_reads_non_latin_titles():
    from dannify import lyrics, lyrics_index

    assert lyrics._norm('馬と鹿') == '馬と鹿'
    assert lyrics_index._key('YOASOBI', 'アイドル') != lyrics_index._key('YOASOBI', '群青')


def test_canonical_groups():
    canon = library._canonicalize_artists([
        'Stephen Kasolo', 'Stephen Kasolo Kitole', 'Stephen Kasolo Kitelo',
        'Drake', 'Drake Bell', 'Future', 'Future Islands',
    ])
    assert canon['Stephen Kasolo Kitole'] == canon['Stephen Kasolo Kitelo'] == 'Stephen Kasolo'
    assert canon['Drake Bell'] == 'Drake Bell'
    assert canon['Future Islands'] == 'Future Islands'


def _built(monkeypatch, tracks):
    for tr in tracks:
        tr.setdefault('album', '')
        tr.setdefault('track_number', 0)
        tr.setdefault('problem', '')
        tr.setdefault('added', 0)
        tr.setdefault('artists', [tr['artist']])
    monkeypatch.setattr(library, '_read_tags', lambda path: None)

    def fake_build(base):
        canon = library._canonicalize_artists([t['artist'] for t in tracks])
        groups = {}
        for t in tracks:
            t['group'] = canon.get(t['artist'], t['artist'])
            groups.setdefault(t['group'], []).append(t)
        return {'tracks': tracks, 'artists': [library._artist_entry(n, m) for n, m in groups.items()]}

    monkeypatch.setattr(library, '_get', fake_build)


def test_every_name_on_a_song_leads_somewhere(monkeypatch):
    _built(monkeypatch, [
        {'artist': 'Sauti Sol', 'artists': ['Sauti Sol', 'Bensoul'], 'title': 'Extravaganza', 'file': 'a.dnf'},
        {'artist': 'Stephen Kasolo', 'title': 'One', 'file': 'b.dnf'},
        {'artist': 'Stephen Kasolo Kitole', 'title': 'Two', 'file': 'c.dnf'},
    ])
    # A page of their own.
    assert library.artist_detail(None, 'sauti sol')['count'] == 1
    # A spelling folded into another page.
    page = library.artist_detail(None, 'Stephen Kasolo Kitole')
    assert page['name'] == 'Stephen Kasolo' and page['count'] == 2
    # Only ever featured.
    page = library.artist_detail(None, 'Bensoul')
    assert page['name'] == 'Bensoul'
    assert [t['file'] for a in page['albums'] for t in a['tracks']] == ['a.dnf']
    assert library.artist_detail(None, 'Nobody') is None


def test_tracks_know_their_page(tmp_path):
    from tests import _id3

    for i, who in enumerate(['Bensoul', 'BENSOUL']):
        f = tmp_path / f'{who} - s{i}.mp3'
        f.write_bytes(_id3.mp3(_id3.text('TPE1', who), _id3.text('TIT2', f's{i}')))
    library.invalidate_cache()
    data = library.library(tmp_path)
    assert {t['group'] for t in data['tracks']} == {'BENSOUL'} or {t['group'] for t in data['tracks']} == {'Bensoul'}
    assert len(data['artists']) == 1 and data['artists'][0]['count'] == 2
    library.invalidate_cache()


# --- a guest inside a name, and who an artist is ----------------------------

def _sealed(monkeypatch, head):
    from dannify import vault

    monkeypatch.setattr(vault, 'inspect', lambda path: (head, ''))


def test_a_guest_credited_inside_one_name_is_two_artists(monkeypatch, tmp_path):
    # Saved as one name; the sidebar had "Mbosso Ft Diamond Platnumz" beside Mbosso.
    _sealed(monkeypatch, {'title': 'Baikoko', 'artist': 'Mbosso Ft Diamond Platnumz',
                          'artists': ['Mbosso Ft Diamond Platnumz']})
    tags = library._read_tags(tmp_path / 'Mbosso Ft Diamond Platnumz - Baikoko.dnf')
    assert tags['artist'] == 'Mbosso'
    assert tags['artists'] == ['Mbosso', 'Diamond Platnumz']


def test_an_ampersand_in_a_credit_list_stays_one_act(monkeypatch, tmp_path):
    _sealed(monkeypatch, {'title': 'Jamming', 'artist': 'Bob Marley & The Wailers',
                          'artists': ['Bob Marley & The Wailers']})
    tags = library._read_tags(tmp_path / 'x.dnf')
    assert tags['artist'] == 'Bob Marley & The Wailers'
    assert tags['artists'] == ['Bob Marley & The Wailers']


@pytest.mark.parametrize('raw, names', [
    ('A featuring B', ['A', 'B']),
    ('A feat. B', ['A', 'B']),
    ('A Ft. B', ['A', 'B']),
    ('Lil Nas X ft. Billy Ray Cyrus', ['Lil Nas X', 'Billy Ray Cyrus']),
    ('Fifth Harmony', ['Fifth Harmony']),  # "ft" inside a word is not a guest
])
def test_guest_words_split_a_name(raw, names):
    assert library._split_feat([raw]) == names


def test_the_ids_a_song_was_saved_with_are_read(monkeypatch, tmp_path):
    _sealed(monkeypatch, {'title': 'Commando', 'artist': 'Mavokali', 'artists': ['Mavokali'],
                          'artist_ids': [{'name': 'Mavokali', 'id': 'UCsongs'}, {'bad': 1}]})
    assert library._read_tags(tmp_path / 'x.dnf')['artist_ids'] == [{'name': 'Mavokali', 'id': 'UCsongs'}]


def test_an_artist_knows_who_they_are_from_their_songs():
    members = [
        {'artist': 'Mavokali', 'artists': ['Mavokali', 'Rayvanny'], 'video_id': 'v1', 'problem': '',
         'artist_ids': [{'name': 'Mavokali', 'id': 'UCsongs'}, {'name': 'Rayvanny', 'id': 'UCray'}]},
        {'artist': 'Mavokali', 'artists': ['Mavokali'], 'video_id': 'v2', 'problem': '',
         'artist_ids': [{'name': 'MAVOKALI', 'id': 'UCsongs'}]},
        {'artist': 'Mavokali', 'artists': ['Mavokali'], 'video_id': 'v3', 'problem': '',
         'artist_ids': [{'name': 'Mavokali', 'id': 'UCvideos'}]},
        {'artist': 'Mavokali', 'artists': ['Mavokali'], 'video_id': 'broken', 'problem': 'damaged',
         'artist_ids': []},
        # Only featured on it: not one of theirs to ask about.
        {'artist': 'Jay Melody', 'artists': ['Jay Melody', 'Mavokali'], 'video_id': 'v4', 'problem': '',
         'artist_ids': []},
    ]
    ids, videos = library._identity('Mavokali', members)
    assert ids == ['UCsongs', 'UCvideos']  # the most credited first; Rayvanny is not them
    assert videos == ['v1', 'v2', 'v3']


def test_one_artist_spelled_two_ways_is_named_the_same_every_time():
    names = ['ALEX KASAU KATOMBI'] * 5 + ['Alex Kasau Katombi'] + ['MEJJA'] * 2
    for _ in range(20):
        canon = library._canonicalize_artists(list(reversed(names)) if _ % 2 else names)
        assert canon['ALEX KASAU KATOMBI'] == 'Alex Kasau Katombi'
        assert canon['MEJJA'] == 'MEJJA'  # capitals when that is all there is
