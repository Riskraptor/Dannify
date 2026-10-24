"""Made from what is listened to: the mixes, and the year in music."""

from __future__ import annotations

import time

import pytest

from dannify import listens


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    listens.init(tmp_path)
    yield tmp_path
    listens.init(tmp_path)
    listens._path = None


def song(i, artist='Sauti Sol', album='Midnight Train', **extra):
    return {
        'video_id': f'vid{i:08d}',
        'title': f'Song {i}',
        'artists': [artist],
        'album': album,
        'duration': 200,
        **extra,
    }


def when(year, month, day, hour=12):
    return int(time.mktime((year, month, day, hour, 0, 0, 0, 0, -1)))


NOW = when(2026, 10, 20, 22)


def play(i, moment, seconds=180, **extra):
    assert listens.record(song(i, **extra), seconds, moment, now=NOW)


def ids(mix):
    return [s['title'] for s in mix['songs']]


def test_nothing_played_makes_no_mixes():
    assert listens.mixes(now=NOW) == {'mixes': []}


def test_on_repeat_is_what_was_played_more_than_once_lately():
    for i in range(5):
        play(i, when(2026, 10, 18, 10 + i))
        play(i, when(2026, 10, 19, 10 + i))
    play(0, when(2026, 10, 19, 20))  # the most played
    play(9, when(2026, 10, 19, 21))  # once only: not on repeat
    play(8, when(2026, 9, 1, 12))
    play(8, when(2026, 9, 2, 12))  # twice, but long ago
    found = {m['id']: m for m in listens.mixes(now=NOW)['mixes']}
    assert ids(found['on_repeat'])[0] == 'Song 0'
    assert set(ids(found['on_repeat'])) == {'Song 0', 'Song 1', 'Song 2', 'Song 3', 'Song 4'}
    assert found['on_repeat']['songs'][0]['plays'] == 3


def test_forgotten_favourites_were_played_a_lot_and_then_not_for_a_month():
    for i in range(4):
        for d in range(1, 5):
            play(10 + i, when(2026, 7, d, 9 + i))
    for d in range(1, 5):
        play(20, when(2026, 7, d, 15))
    play(20, when(2026, 10, 19, 15))  # came back: not forgotten
    found = {m['id']: m for m in listens.mixes(now=NOW)['mixes']}
    assert set(ids(found['forgotten'])) == {'Song 10', 'Song 11', 'Song 12', 'Song 13'}


def test_top_this_month_counts_this_month_only_by_time_listened():
    for i in range(5):
        play(30 + i, when(2026, 10, 2 + i), seconds=100 + i * 20)
    play(39, when(2026, 9, 30), seconds=190)  # last month
    found = {m['id']: m for m in listens.mixes(now=NOW)['mixes']}
    assert ids(found['top_month']) == ['Song 34', 'Song 33', 'Song 32', 'Song 31', 'Song 30']


def test_a_mix_with_too_few_songs_is_left_out():
    for i in range(3):
        play(i, when(2026, 10, 18))
        play(i, when(2026, 10, 19))
    assert 'on_repeat' not in {m['id'] for m in listens.mixes(now=NOW)['mixes']}


def test_the_year_in_music():
    # 2025: one artist, heard before 2026.
    play(1, when(2025, 6, 1), artist='Bien', album='Alusa')
    # 2026: three days in a row and one more; Sauti Sol most of all.
    for d in (3, 4, 5):
        play(2, when(2026, 3, d, 8))
        play(3, when(2026, 3, d, 21))
    play(4, when(2026, 3, 5, 21), artist='Tems', album='For Broken Ears', seconds=200)
    play(1, when(2026, 8, 9, 21), artist='Bien', album='Alusa')

    year = listens.recap(2026, now=NOW)
    assert year['year'] == 2026
    assert year['years'] == [2026, 2025]
    assert year['plays'] == 8
    assert year['seconds'] == 7 * 180 + 200
    assert year['days'] == 4
    assert year['longest_streak'] == 3
    assert year['busiest_day']['date'] == '2026-03-05'
    assert year['peak_hour'] == 21
    assert year['months'][2] == 6 * 180 + 200 and year['months'][7] == 180
    # Sauti Sol and Tems are new this year; Bien was heard in 2025.
    assert year['new_artists'] == 2
    assert year['top_artists'][0]['name'] == 'Sauti Sol'
    assert [s['title'] for s in year['top_songs'][:2]] == ['Song 2', 'Song 3']
    assert year['top_albums'][0]['name'] == 'Midnight Train'
    assert year['first']['title'] == 'Song 2'


def test_the_year_in_music_tells_more():
    play(1, when(2025, 6, 1), artist='Bien', album='Alusa')
    for d in (3, 4, 5):
        play(2, when(2026, 3, d, 8))
        play(3, when(2026, 3, d, 21))
    play(2, when(2026, 3, 5, 9))
    play(2, when(2026, 3, 5, 10))  # Song 2 three times on 5 March
    play(4, when(2026, 8, 9, 21), artist='Tems', album='For Broken Ears')

    year = listens.recap(2026, now=NOW)
    # When it was listened to: by hour, and by weekday (Monday first).
    assert len(year['hours']) == 24 and year['hours'][21] == 4 * 180
    assert len(year['weekdays']) == 7 and sum(year['weekdays']) == year['seconds']
    # Each month's own favourite.
    assert year['month_artists'][2]['name'] == 'Sauti Sol'
    assert year['month_artists'][7]['name'] == 'Tems'
    assert year['month_artists'][0] is None
    # The song played most in one day, and the top song's own story.
    assert year['repeat']['title'] == 'Song 2' and year['repeat']['plays'] == 3
    assert year['repeat']['date'] == '2026-03-05'
    assert year['top_songs'][0]['title'] == 'Song 2'
    assert year['top_song_more'] == {'first': '2026-03-03', 'most_in_a_day': 3}
    # The year before, to compare.
    assert year['last_year'] == {'seconds': 180, 'plays': 1}


def test_twenty_five_songs_for_the_playlist_five_of_the_rest():
    for i in range(30):
        play(i, when(2026, 2, 1 + i % 27, 12), artist=f'Artist {i}')
    year = listens.recap(2026, now=NOW)
    assert len(year['top_songs']) == 25
    assert len(year['top_artists']) == 5 and len(year['top_albums']) <= 5


def test_a_year_with_nothing_in_it():
    play(1, when(2025, 6, 1))
    year = listens.recap(2026, now=NOW)
    assert year['plays'] == 0 and year['seconds'] == 0
    assert year['busiest_day'] is None and year['peak_hour'] is None and year['first'] is None
    assert year['top_songs'] == []
    assert year['years'] == [2025]


def test_right_about_now_is_this_hour_on_this_kind_of_day():
    assert time.localtime(NOW).tm_wday == 1  # a Tuesday, ten at night
    for day in (13, 14, 15, 16):  # weekday evenings
        for i in (1, 2, 3, 4):
            play(i, when(2026, 10, day, 22) + i * 240)
        play(5, when(2026, 10, day, 8))  # mornings: another time of day
    play(6, when(2026, 10, 17, 22))  # a Saturday night: another kind of day
    play(7, when(2026, 10, 19, 22))  # Monday night counts...
    play(7, NOW - 3600)  # ...but it was played an hour ago: left for later
    found = {m['id']: m for m in listens.mixes(now=NOW)['mixes']}
    assert set(ids(found['right_now'])) == {'Song 1', 'Song 2', 'Song 3', 'Song 4'}
    # Nothing at this hour on this kind of day: no mix.
    assert 'right_now' not in {m['id'] for m in listens.mixes(now=when(2026, 10, 24, 15))['mixes']}
