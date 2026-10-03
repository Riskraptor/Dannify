"""Playlists the listener makes: kept safely, in order, through anything."""

from __future__ import annotations

import json

import pytest

from dannify import playlists


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    playlists._data = {'version': 1, 'playlists': []}
    playlists.init(tmp_path)
    yield tmp_path
    playlists._data = {'version': 1, 'playlists': []}
    playlists._path = None


def song(i, **extra):
    return {'video_id': f'vid{i:08d}', 'title': f'Song {i}', 'artists': ['A'], 'duration': 200, **extra}


def test_a_playlist_is_made_named_and_kept_on_disk(fresh):
    made = playlists.create('Road trip', [song(1), song(2)])
    assert made['name'] == 'Road trip' and made['count'] == 2 and made['duration'] == 400
    saved = json.loads((fresh / 'playlists.json').read_text(encoding='utf-8'))
    assert saved['playlists'][0]['tracks'][1]['title'] == 'Song 2'
    # Read back by the next start.
    playlists._data = {'version': 1, 'playlists': []}
    playlists.init(fresh)
    assert playlists.get(made['id'])['tracks'][0]['video_id'] == 'vid00000001'


def test_songs_are_added_where_asked_and_reordered_and_removed():
    pid = playlists.create('Mix')['id']
    playlists.add_tracks(pid, [song(1), song(2), song(3)])
    playlists.add_tracks(pid, [song(9)], position=1)
    assert [t['title'] for t in playlists.get(pid)['tracks']] == ['Song 1', 'Song 9', 'Song 2', 'Song 3']
    order = playlists.get(pid)['tracks']
    playlists.set_tracks(pid, [order[3], order[0], order[1], order[2]])
    assert [t['title'] for t in playlists.get(pid)['tracks']] == ['Song 3', 'Song 1', 'Song 9', 'Song 2']
    playlists.remove_tracks(pid, [1, 3])
    assert [t['title'] for t in playlists.get(pid)['tracks']] == ['Song 3', 'Song 9']


def test_a_saved_song_keeps_its_file_and_one_with_nothing_to_play_by_is_left_out():
    pid = playlists.create('Mine', [
        {'file': 'Bien/Bien - Inauma.dnf', 'title': 'Inauma', 'video_id': 'QtrUp3-HLkw'},
        {'title': 'nothing to play it by'},
        'not even a song',
    ])['id']
    tracks = playlists.get(pid)['tracks']
    assert len(tracks) == 1 and tracks[0]['file'] == 'Bien/Bien - Inauma.dnf'


def test_names_are_tidied_and_renaming_works():
    pid = playlists.create('   ')['id']
    assert playlists.get(pid)['name'] == 'Playlist'
    playlists.rename(pid, '  Late night  ')
    assert playlists.get(pid)['name'] == 'Late night'
    playlists.rename(pid, '')  # an empty name keeps the one it had
    assert playlists.get(pid)['name'] == 'Late night'


def test_deleting_and_unknown_playlists():
    pid = playlists.create('Gone')['id']
    playlists.delete(pid)
    assert playlists.all_playlists() == []
    with pytest.raises(playlists.NotFound):
        playlists.get(pid)
    with pytest.raises(playlists.NotFound):
        playlists.delete(pid)


def test_a_damaged_file_is_kept_aside_not_lost(tmp_path):
    (tmp_path / 'playlists.json').write_text('{ not json', encoding='utf-8')
    playlists._data = {'version': 1, 'playlists': []}
    playlists.init(tmp_path)
    assert playlists.all_playlists() == []
    assert list(tmp_path.glob('playlists.broken-*.json'))


def test_summaries_carry_up_to_four_pictures():
    pid = playlists.create('Covers', [song(i, cover_url=f'https://x/{i}.jpg') for i in range(6)])['id']
    summary = next(p for p in playlists.all_playlists() if p['id'] == pid)
    assert summary['covers'] == [f'https://x/{i}.jpg' for i in range(4)]
