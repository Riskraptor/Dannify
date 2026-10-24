"""What has been listened to: kept a line at a time, counted honestly, and
summed up the way History and Stats show it."""

from __future__ import annotations

import json
import time

import pytest

from dannify import listens


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    listens.init(tmp_path)
    yield tmp_path
    listens.init(tmp_path)
    listens._path = None


def song(i, **extra):
    return {
        'video_id': f'vid{i:08d}',
        'title': f'Song {i}',
        'artists': ['Sauti Sol'],
        'album': 'Midnight Train',
        'duration': 200,
        **extra,
    }


def at(day, hour=12, minute=0):
    """A time on a day of October 2026, here: days are the listener's own."""

    return int(time.mktime((2026, 10, day, hour, minute, 0, 0, 0, -1)))


NOW = at(14, 23, 0)


def test_half_a_minute_is_a_listen_and_less_is_a_skip():
    assert listens.counts(30, 200) and listens.counts(180, 200)
    assert not listens.counts(29, 200)
    # A song too short for half a minute: half of it.
    assert listens.counts(20, 40) and not listens.counts(19, 40)
    # A few seconds of a jingle is still nothing, and so is an unknown length.
    assert not listens.counts(4, 6) and not listens.counts(20, 0)


def test_a_listen_is_one_line_on_the_end_and_is_read_back(fresh):
    assert listens.record(song(1), 180, at(14, 9), now=NOW)
    assert listens.record(song(1), 200, at(14, 10), now=NOW)
    assert not listens.record(song(2), 12, at(14, 11), now=NOW)  # a skip
    lines = (fresh / 'listens.jsonl').read_text(encoding='utf-8').splitlines()
    # The song once, then a short line for each listen.
    assert len(lines) == 3
    assert json.loads(lines[0])['k'] == 'v:vid00000001'
    assert json.loads(lines[2]) == [at(14, 10), 200, 'v:vid00000001']
    # Read back by the next start.
    listens.init(fresh)
    got = listens.history()
    assert got['total'] == 2 and not got['more']
    assert [item['at'] for item in got['items']] == [at(14, 10), at(14, 9)]
    assert got['items'][0]['title'] == 'Song 1' and got['items'][0]['seconds'] == 200


def test_the_same_listen_handed_over_twice_is_kept_once(fresh):
    assert listens.record(song(1), 180, at(14, 9), now=NOW)
    assert not listens.record(song(1), 180, at(14, 9), now=NOW)
    listens.init(fresh)
    assert listens.history()['total'] == 1


def test_a_song_streamed_and_played_from_its_file_is_one_song(fresh):
    listens.record(song(1, cover_url='https://x/1.jpg'), 180, at(13, 9), now=NOW)
    listens.record(
        {'video_id': 'vid00000001', 'file': 'Sauti Sol/Song 1.dnf', 'title': 'Song 1', 'duration': 200},
        200, at(14, 9), now=NOW,
    )
    top = listens.stats(now=NOW)['top_songs']
    assert len(top) == 1 and top[0]['plays'] == 2
    # Each filled in what the other lacked; neither wiped it out.
    assert top[0]['file'] == 'Sauti Sol/Song 1.dnf'
    assert top[0]['cover_url'] == 'https://x/1.jpg' and top[0]['artists'] == ['Sauti Sol']
    # A saved file that never had an id goes by its path.
    listens.record({'file': 'Bien/Inauma.dnf', 'title': 'Inauma', 'duration': 210}, 100, at(14, 10), now=NOW)
    assert listens.history(1)['items'][0]['key'] == 'f:Bien/Inauma.dnf'


def test_a_line_cut_short_costs_that_line_only(fresh):
    listens.record(song(1), 180, at(13, 9), now=NOW)
    path = fresh / 'listens.jsonl'
    with path.open('a', encoding='utf-8', newline='\n') as f:
        f.write('[17917')  # the power went as this was written
    listens.init(fresh)
    assert listens.history()['total'] == 1
    # And the next listen starts on a line of its own.
    assert listens.record(song(2), 180, at(14, 9), now=NOW)
    listens.init(fresh)
    assert [i['title'] for i in listens.history()['items']] == ['Song 2', 'Song 1']


def test_a_wrong_clock_is_put_right_and_a_runaway_count_is_capped():
    listens.record(song(1), 180, NOW + 86400 * 30, now=NOW)  # a month from now
    listens.record(song(2), 180, 12345, now=NOW)  # 1970
    listens.record(song(3), 10 ** 7, at(14, 1), now=NOW)
    items = {i['title']: i for i in listens.history()['items']}
    assert items['Song 1']['at'] == NOW - 180 and items['Song 2']['at'] == NOW - 180
    assert items['Song 3']['seconds'] == listens.MAX_SECONDS
    # Nothing to play it by, or nothing like a number: not a listen.
    assert not listens.record({'title': 'nameless'}, 180, now=NOW)
    assert not listens.record(song(4), 'a while', now=NOW)
    assert not listens.record('not a song', 180, now=NOW)


def test_history_carries_on_from_where_it_stopped():
    for i in range(1, 8):
        listens.record(song(i), 100, at(14, i), now=NOW)
    first = listens.history(limit=3)
    assert [i['title'] for i in first['items']] == ['Song 7', 'Song 6', 'Song 5'] and first['more']
    rest = listens.history(limit=10, before=first['items'][-1]['at'])
    assert [i['title'] for i in rest['items']] == ['Song 4', 'Song 3', 'Song 2', 'Song 1']
    assert not rest['more'] and rest['total'] == 7


def test_one_listen_can_be_forgotten_and_so_can_all_of_them(fresh):
    listens.record(song(1), 100, at(13, 9), now=NOW)
    listens.record(song(2), 100, at(14, 9), now=NOW)
    assert listens.forget(at(14, 9), 'v:vid00000002')
    assert not listens.forget(at(14, 9), 'v:vid00000002')  # already gone
    assert not listens.forget('yesterday', 'v:vid00000001')
    listens.init(fresh)
    assert [i['title'] for i in listens.history()['items']] == ['Song 1']
    # The song nobody has listened to any more went with its last listen.
    assert 'vid00000002' not in (fresh / 'listens.jsonl').read_text(encoding='utf-8')
    listens.clear()
    assert listens.history() == {'items': [], 'more': False, 'total': 0}
    assert not (fresh / 'listens.jsonl').exists()


def test_stats_for_a_stretch_of_days_and_the_stretch_before():
    # This week: Song 1 three times, Song 2 once. Last week: Song 3 twice.
    for day in (12, 13, 14):
        listens.record(song(1), 200, at(day, 9), now=NOW)
    listens.record(song(2, artists=['Bien', 'Sauti Sol'], album='Alusa'), 100, at(14, 21), now=NOW)
    for day in (3, 4):
        listens.record(song(3), 150, at(day, 9), now=NOW)
    got = listens.stats(days=7, now=NOW)
    assert (got['plays'], got['seconds'], got['songs']) == (4, 700, 2)
    assert got['previous'] == {'seconds': 300, 'plays': 2, 'songs': 1}
    assert [(s['title'], s['plays']) for s in got['top_songs']] == [('Song 1', 3), ('Song 2', 1)]
    assert got['top_songs'][0]['last'] == at(14, 9)
    # Everyone on a song is credited with it.
    assert [(a['name'], a['plays'], a['songs']) for a in got['top_artists']] == [
        ('Sauti Sol', 4, 2), ('Bien', 1, 1),
    ]
    assert [(a['name'], a['artist'], a['plays']) for a in got['top_albums']] == [
        ('Midnight Train', 'Sauti Sol', 3), ('Alusa', 'Bien', 1),
    ]
    # A bar for every day of the week, the quiet ones too.
    assert got['bucket'] == 'day'
    assert [b['label'] for b in got['buckets']] == [f'2026-10-{d:02d}' for d in range(8, 15)]
    assert [b['seconds'] for b in got['buckets']] == [0, 0, 0, 0, 200, 200, 300]
    assert got['by_hour'][9] == 600 and got['by_hour'][21] == 100 and sum(got['by_hour']) == 700
    # Ever: all six, and by the month.
    ever = listens.stats(now=NOW)
    assert ever['plays'] == 6 and ever['previous'] is None and ever['first'] == at(3, 9)
    assert ever['bucket'] == 'month'
    assert ever['buckets'] == [{'label': '2026-10', 'seconds': 1000, 'plays': 6}]


def test_a_long_stretch_is_drawn_by_the_month_with_the_empty_ones():
    listens.record(song(1), 200, at(14, 9), now=NOW)
    got = listens.stats(days=365, now=NOW)
    assert got['bucket'] == 'month'
    assert got['buckets'][0]['label'] == '2025-10' and got['buckets'][-1]['label'] == '2026-10'
    assert len(got['buckets']) == 13 and got['buckets'][-1]['plays'] == 1
    # Nothing at all yet: nothing to draw, and nothing that breaks.
    listens.clear()
    empty = listens.stats(now=NOW)
    assert empty['plays'] == 0 and empty['buckets'] == [] and empty['top_songs'] == []
    assert (empty['streak'], empty['longest_streak'], empty['first']) == (0, 0, 0)


def test_days_in_a_row_are_not_over_until_a_whole_day_is_missed():
    for day in (5, 6, 7, 8, 12, 13):
        listens.record(song(1), 200, at(day, 9), now=NOW)
    got = listens.stats(now=NOW)
    # Nothing yet today, the 14th: yesterday's run of two still stands.
    assert (got['streak'], got['longest_streak']) == (2, 4)
    listens.record(song(1), 200, at(14, 9), now=NOW)
    assert listens.stats(now=NOW)['streak'] == 3
    # Two days on with nothing played, it is over.
    assert listens.stats(now=NOW + 2 * 86400)['streak'] == 0


def test_rediscover_is_what_was_played_a_lot_and_then_not_for_a_while():
    for hour in (9, 10, 11, 12):
        listens.record(song(1), 200, at(1, hour), now=NOW)  # loved, six weeks back
    for hour in (9, 10, 11):
        listens.record(song(2), 200, at(14, hour), now=NOW)  # loved, and still is
    listens.record(song(3), 200, at(1, 15), now=NOW)  # heard once, long ago
    later = NOW + 40 * 86400
    assert [s['title'] for s in listens.stats(now=later)['rediscover']] == ['Song 1', 'Song 2']
    # Ten days on, nothing has been away for long enough.
    assert listens.stats(now=NOW + 10 * 86400)['rediscover'] == []


def test_the_week_and_the_moments_of_a_stretch():
    # Wednesday the 14th: three songs back to back, then Song 1 twice more
    # after a long break. Tuesday the 13th: one.
    listens.record(song(1), 200, at(14, 9, 0), now=NOW)
    listens.record(song(2), 200, at(14, 9, 4), now=NOW)  # starts as Song 1 ends
    listens.record(song(3), 200, at(14, 9, 15), now=NOW)  # 4 min after Song 2 ended
    listens.record(song(1), 200, at(14, 15, 0), now=NOW)
    listens.record(song(1), 200, at(14, 18, 0), now=NOW)
    listens.record(song(4), 100, at(13, 20, 0), now=NOW)
    got = listens.stats(days=7, now=NOW)
    week = got['by_weekday']
    assert week[2] == 1000 and week[1] == 100 and sum(week) == 1100  # Wednesday, Tuesday
    h = got['highlights']
    assert h['best_day'] == {'date': '2026-10-14', 'seconds': 1000}
    assert h['session'] == {'start': at(14, 9, 0), 'seconds': 600, 'plays': 3}
    assert h['repeat']['plays'] == 3 and h['repeat']['song']['title'] == 'Song 1'
    assert h['repeat']['date'] == '2026-10-14'
    assert h['active_days'] == 2 and h['per_day'] == 550


def test_what_was_new_in_a_stretch_and_nothing_is_new_in_ever():
    listens.record(song(1), 200, at(3, 9), now=NOW)  # heard before the week
    listens.record(song(1), 200, at(14, 9), now=NOW)
    listens.record(song(2, artists=['Bien']), 200, at(13, 9), now=NOW)
    listens.record(song(2, artists=['Bien']), 200, at(14, 10), now=NOW)
    listens.record(song(3), 100, at(14, 11), now=NOW)
    got = listens.stats(days=7, now=NOW)
    assert got['highlights']['new_songs'] == 2
    assert got['highlights']['new_artists'] == 1, 'Bien is new; Sauti Sol is not'
    assert [(d['title'], d['plays']) for d in got['discoveries']] == [('Song 2', 2), ('Song 3', 1)]
    ever = listens.stats(now=NOW)
    assert ever['discoveries'] == [] and ever['highlights']['new_songs'] == 0


def test_no_moments_from_nothing():
    got = listens.stats(days=7, now=NOW)
    assert got['by_weekday'] == [0] * 7
    assert got['highlights']['best_day'] is None and got['highlights']['session'] is None
    assert got['highlights']['repeat'] is None and got['highlights']['per_day'] == 0
