"""Your Soundtrack for today, this week and this month, and the moments worth
saying about each (listens.story, listens.glance)."""

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


def when(year, month, day, hour=12, minute=0):
    return int(time.mktime((year, month, day, hour, minute, 0, 0, 0, -1)))


# A Tuesday evening: the week began on Monday the 19th.
NOW = when(2026, 10, 20, 22)


def play(i, moment, seconds=180, **extra):
    assert listens.record(song(i, **extra), seconds, moment, now=NOW)


def kinds(d):
    return [f['kind'] for f in d['insights']]


def find(d, kind):
    return next(f for f in d['insights'] if f['kind'] == kind)


def test_this_week_starts_on_monday_and_is_compared_with_the_week_before():
    play(1, when(2026, 10, 18, 12))  # Sunday: last week
    play(2, when(2026, 10, 19, 9))  # Monday
    play(3, when(2026, 10, 20, 21))  # Tuesday
    week = listens.story('week', now=NOW)
    assert week['period'] == 'week'
    assert (week['start'], week['end']) == ('2026-10-19', '2026-10-26')
    assert week['plays'] == 2
    assert week['before'] == {'seconds': 180, 'plays': 1}
    assert week['chart'] == [180, 180, 0, 0, 0, 0, 0]
    assert [p and p['name'] for p in week['parts']][:2] == ['Sauti Sol', 'Sauti Sol']
    assert week['parts'][2] is None


def test_today_is_told_by_the_hour_and_the_part_of_the_day():
    play(1, when(2026, 10, 19, 20))  # yesterday
    play(2, when(2026, 10, 20, 7), artist='Bensoul')  # morning
    play(3, when(2026, 10, 20, 21), artist='Nviiri')  # evening
    day = listens.story('day', now=NOW)
    assert (day['start'], day['end']) == ('2026-10-20', '2026-10-21')
    assert len(day['chart']) == 24
    assert day['chart'][7] == 180 and day['chart'][21] == 180
    assert [p and p['name'] for p in day['parts']] == [None, 'Bensoul', None, 'Nviiri']
    assert day['before']['plays'] == 1


def test_this_month_has_a_bar_for_every_day_of_it():
    play(1, when(2026, 9, 30, 12))
    play(2, when(2026, 10, 1, 12))
    play(3, when(2026, 10, 20, 12))
    month = listens.story('month', now=NOW)
    assert (month['start'], month['end']) == ('2026-10-01', '2026-11-01')
    assert len(month['chart']) == 31
    assert month['chart'][0] == 180 and month['chart'][19] == 180
    assert month['plays'] == 2
    # Weeks of the month: the 1st falls in the first, the 20th in the third.
    assert month['parts'][0]['name'] == 'Sauti Sol' and month['parts'][2]['name'] == 'Sauti Sol'


def test_a_year_story_keeps_the_names_it_always_had():
    play(1, when(2026, 3, 1))
    d = listens.recap(2026, now=NOW)
    assert d['period'] == 'year'
    assert d['months'] == d['chart'] and d['month_artists'] == d['parts']
    assert d['last_year'] == d['before']


def test_an_unknown_stretch_is_a_year():
    assert listens.story('fortnight', now=NOW)['period'] == 'year'


def test_a_quiet_stretch_has_nothing_to_say():
    play(1, when(2026, 9, 1))
    assert listens.story('week', now=NOW)['insights'] == []


def test_there_is_always_something_to_say_about_a_stretch_with_music():
    play(1, when(2026, 10, 20, 12))
    d = listens.story('day', now=NOW)
    assert kinds(d) == ['minutes']
    assert d['insights'][0]['minutes'] == 3


def test_more_than_the_week_before_and_a_run_of_days():
    for day in (16, 17, 18):
        play(day, when(2026, 10, day, 12), seconds=240)
    for day in (19, 20):
        for i in range(4):
            play(100 + day * 10 + i, when(2026, 10, day, 10 + i))
    d = listens.story('week', now=NOW)
    assert find(d, 'more')['percent'] == 100  # 24 minutes, after 12
    assert find(d, 'streak')['days'] == 5
    scores = [f['score'] for f in d['insights']]
    assert scores == sorted(scores, reverse=True)


def test_less_than_before_is_never_said():
    for i in range(10):
        play(i, when(2026, 10, 13, 8 + i))
    play(50, when(2026, 10, 20, 12))
    assert 'more' not in kinds(listens.story('week', now=NOW))


def test_a_record_day_beats_every_day_before_it():
    for day in range(1, 11):
        play(day, when(2026, 9, day, 12))  # ten days of history, 3 minutes each
    for i in range(5):
        play(200 + i, when(2026, 10, 20, 8 + i))
    d = listens.story('day', now=NOW)
    record = find(d, 'record_day')
    assert record['date'] == '2026-10-20' and record['minutes'] == 15
    assert d['insights'][0]['kind'] == 'record_day'


def test_no_record_without_some_history():
    play(1, when(2026, 10, 1))
    for i in range(5):
        play(200 + i, when(2026, 10, 20, 8 + i))
    assert 'record_day' not in kinds(listens.story('day', now=NOW))


def test_a_song_back_after_a_long_time_away():
    play(7, when(2026, 6, 1))
    play(7, when(2026, 6, 2))
    play(7, when(2026, 10, 20, 9))
    comeback = find(listens.story('week', now=NOW), 'comeback')
    assert comeback['song']['title'] == 'Song 7'
    assert comeback['days'] >= 130


def test_an_artist_climbs_into_the_top_five():
    names = ['A', 'B', 'C', 'D', 'E', 'F']
    # Last week F was sixth; this week first.
    for rank, name in enumerate(names):
        for i in range(6 - rank):
            play(rank * 10 + i, when(2026, 10, 13 + (i % 5), 8 + rank), artist=name)
    for i in range(6):
        play(80 + i, when(2026, 10, 19, 8 + i), artist='F')
    play(90, when(2026, 10, 20, 8), artist='A')
    climber = find(listens.story('week', now=NOW), 'climber')
    assert (climber['artist'], climber['rank'], climber['from']) == ('F', 1, 6)


def test_new_artists_and_one_new_straight_into_the_top():
    for i, name in enumerate(['A', 'B', 'C']):
        play(i, when(2026, 10, 13, 9 + i), artist=name)
    for i in range(3):
        play(20 + i, when(2026, 10, 19, 9 + i), artist='Zuchu')
    d = listens.story('week', now=NOW)
    assert find(d, 'new_artists')['artist'] == 'Zuchu'
    assert find(d, 'new_in_top')['artist'] == 'Zuchu'


def test_lifetime_milestones_are_said_once_the_line_is_crossed():
    for i in range(99):
        play(i % 30, when(2026, 9, 1 + i % 28, 6 + i % 12, i % 60), seconds=30)
    play(5, when(2026, 10, 20, 9), seconds=30)
    d = listens.story('day', now=NOW)
    assert find(d, 'milestone_plays')['plays'] == 100


def test_every_day_of_the_week_so_far_and_on_repeat():
    days = [(2026, 10, d) for d in range(5, 13)]
    for i, (y, m, d) in enumerate(days):
        play(i, when(y, m, d, 12))
    for hour in (9, 10, 11):
        play(42, when(2026, 10, 12, hour))
    month_story = listens.story('month', now=when(2026, 10, 12, 22))
    assert 'repeat' in kinds(month_story)
    assert find(month_story, 'repeat')['plays'] == 3
    week_story = listens.story('week', now=when(2026, 10, 11, 22))  # a whole Monday-to-Sunday
    assert find(week_story, 'every_day')['days'] == 7


def test_night_owls_and_faithful_listeners():
    for i in range(4):
        play(i, when(2026, 10, 20, 0, i * 5), artist='Sauti Sol')
    play(9, when(2026, 10, 20, 13), artist='Bensoul')
    d = listens.story('day', now=NOW)
    assert find(d, 'night')['percent'] == 80
    assert find(d, 'loyal')['artist'] == 'Sauti Sol'


def test_no_more_than_eight_moments():
    for day in range(1, 21):
        for i in range(3):
            play(day * 10 + i, when(2026, 10, day, 1 + i), artist=f'Artist {day}')
    assert len(listens.story('month', now=NOW)['insights']) <= 8


def test_glance_is_all_four_stretches():
    play(1, when(2026, 10, 20, 9))
    play(2, when(2026, 10, 19, 9))
    play(3, when(2026, 10, 2, 9))
    play(4, when(2026, 3, 2, 9))
    g = listens.glance(now=NOW)
    assert list(g) == ['day', 'week', 'month', 'year']
    assert [g[p]['plays'] for p in g] == [1, 2, 3, 4]
    assert len(g['day']['chart']) == 24 and len(g['week']['chart']) == 7
    assert g['year']['top_song']['title'] in {'Song 1', 'Song 2', 'Song 3', 'Song 4'}
    assert all(len(g[p]['insights']) <= 3 for p in g)


def test_glance_says_a_run_of_days_once():
    for day in range(14, 21):
        play(day, when(2026, 10, day, 9))
    g = listens.glance(now=NOW)
    told = [p for p in g if any(f['kind'] == 'streak' for f in g[p]['insights'])]
    assert told == ['day']


def test_milestones_are_news_today_and_this_week_only():
    for i in range(99):
        play(i % 30, when(2026, 1, 1 + i % 28, 6 + i % 12, i % 60), seconds=30)
    play(5, when(2026, 10, 20, 9), seconds=30)
    assert 'milestone_plays' in kinds(listens.story('week', now=NOW))
    assert 'milestone_plays' not in kinds(listens.story('month', now=NOW))
    assert 'milestone_plays' not in kinds(listens.story('year', now=NOW))


def test_glance_tells_a_record_once():
    for day in range(1, 11):
        play(day, when(2026, 9, day, 12))
    for i in range(6):
        play(200 + i, when(2026, 10, 20, 8 + i))
    g = listens.glance(now=NOW)
    told = [p for p in g if any(f['kind'] == 'record_day' for f in g[p]['insights'])]
    assert told == ['day']
