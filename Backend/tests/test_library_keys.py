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
    from mutagen.id3 import ID3, TPE1, TIT2

    for i, who in enumerate(['Bensoul', 'BENSOUL']):
        f = tmp_path / f'{who} - s{i}.mp3'
        f.write_bytes((bytes.fromhex('fffb9064') + bytes(413)) * 20)
        tags = ID3()
        tags.add(TPE1(encoding=3, text=who))
        tags.add(TIT2(encoding=3, text=f's{i}'))
        tags.save(f)
    library.invalidate_cache()
    data = library.library(tmp_path)
    assert {t['group'] for t in data['tracks']} == {'BENSOUL'} or {t['group'] for t in data['tracks']} == {'Bensoul'}
    assert len(data['artists']) == 1 and data['artists'][0]['count'] == 2
    library.invalidate_cache()
