"""YouTube Music's history, brought into Dannify's (see ytm_history.py): all of
it the first time, then only what is new, never a play twice."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

import pytest

from dannify import account, listens, ytm_history

TODAY = date(2026, 10, 21)  # a Wednesday


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    listens.init(tmp_path)
    ytm_history.init(tmp_path)
    yield


def item(video: str, heading: str, title: str = '', seconds: int = 200) -> dict:
    return {
        'videoId': video,
        'title': title or f'Song {video}',
        'artists': [{'name': 'Sauti Sol', 'id': 'UC1'}],
        'album': {'name': 'Midnight Train', 'id': 'MPRE1'},
        'thumbnails': [{'url': 'https://lh3.googleusercontent.com/x=w120-h120'}],
        'duration_seconds': seconds,
        'played': heading,
    }


def plays() -> list[tuple[date, str]]:
    found = listens.history(500)['items']
    return [(datetime.fromtimestamp(i['at']).date(), i['video_id']) for i in found]


@pytest.mark.parametrize(('heading', 'first', 'last', 'on'), [
    ('Today', '2026-10-21', '2026-10-21', '2026-10-21'),
    ('Yesterday', '2026-10-20', '2026-10-20', '2026-10-20'),
    ('Monday', '2026-10-19', '2026-10-19', '2026-10-19'),
    ('This week', '2026-10-15', '2026-10-19', '2026-10-18'),
    ('Last week', '2026-10-08', '2026-10-14', '2026-10-12'),
    ('September', '2026-09-01', '2026-09-30', '2026-09-15'),
    ('November 2025', '2025-11-01', '2025-11-30', '2025-11-15'),
    # A month later in the year than now is last year's.
    ('December', '2025-12-01', '2025-12-31', '2025-12-15'),
    ('Last month', '2026-09-01', '2026-09-30', '2026-09-15'),
    ('Older', '2025-10-21', '2026-09-21', '2026-09-06'),
])
def test_each_heading_is_a_span_of_days_and_a_day_in_it(heading, first, last, on):
    got = ytm_history.span_of(heading, TODAY)
    assert tuple(d.isoformat() for d in got) == (first, last, on)


def test_a_copy_installed_today_starts_with_everything_played_before():
    got = ytm_history.bring_in([
        item('aaaaaaaaaaa', 'Today'), item('bbbbbbbbbbb', 'Yesterday'),
        item('ccccccccccc', 'Last week'), item('ddddddddddd', 'September'),
    ], today=TODAY)
    assert got == {'brought': 4, 'checked': 4, 'total': 4}
    days = dict((v, d) for d, v in plays())
    assert days['bbbbbbbbbbb'] == date(2026, 10, 20)
    assert days['ccccccccccc'] == date(2026, 10, 12)
    assert days['ddddddddddd'] == date(2026, 9, 15)
    # As a song listened to all the way through, by its YouTube id.
    song = listens.history(10)['items'][0]
    assert song['title'] and song['artists'] == ['Sauti Sol'] and song['seconds'] >= 30


def test_the_same_play_is_not_counted_again_as_it_grows_older():
    ytm_history.bring_in([item('aaaaaaaaaaa', 'Today')], today=TODAY)
    # The next day it is under "Yesterday", then under "This week".
    assert ytm_history.bring_in([item('aaaaaaaaaaa', 'Yesterday')], today=TODAY + timedelta(days=1))['brought'] == 0
    assert ytm_history.bring_in([item('aaaaaaaaaaa', 'This week')], today=TODAY + timedelta(days=4))['brought'] == 0
    assert len(plays()) == 1


def test_played_again_later_it_is_a_new_listen():
    ytm_history.bring_in([item('aaaaaaaaaaa', 'Last week')], today=TODAY)
    assert ytm_history.bring_in([item('aaaaaaaaaaa', 'Today')], today=TODAY)['brought'] == 1
    assert len(plays()) == 2


def test_what_dannify_played_itself_is_not_brought_in_twice():
    # Dannify tells YouTube Music what it plays: it comes back in the history.
    at = int(datetime(2026, 10, 20, 18, 30).timestamp())
    assert listens.record({'video_id': 'aaaaaaaaaaa', 'title': 'Suzanna', 'duration': 230}, 230, at)
    got = ytm_history.bring_in([item('aaaaaaaaaaa', 'Yesterday'), item('bbbbbbbbbbb', 'Yesterday')], today=TODAY)
    assert got['brought'] == 1
    assert sorted(v for _, v in plays()) == ['aaaaaaaaaaa', 'bbbbbbbbbbb']


def test_a_history_cleared_is_not_filled_again_with_the_old():
    ytm_history.bring_in([item('aaaaaaaaaaa', 'Yesterday')], today=TODAY)
    listens.clear()
    assert ytm_history.bring_in([item('aaaaaaaaaaa', 'Yesterday')], today=TODAY)['brought'] == 0
    assert plays() == []


def test_todays_plays_are_never_put_later_than_now(monkeypatch):
    morning = datetime(2026, 10, 21, 8, 0).timestamp()
    monkeypatch.setattr(ytm_history.time, 'time', lambda: morning)
    ytm_history.bring_in([item('aaaaaaaaaaa', 'Today'), item('bbbbbbbbbbb', 'Today')], today=TODAY)
    times = sorted(i['at'] for i in listens.history(10)['items'])
    assert all(t < morning for t in times) and times[0] < times[1]


def test_signed_out_it_says_so(monkeypatch):
    from fastapi import HTTPException

    from dannify.routes import listens as routes

    def no_session(require_auth=False):
        raise account.NotSignedIn('Sign in with Google to use this feature')

    monkeypatch.setattr(account, 'client', no_session)
    with pytest.raises(HTTPException) as err:
        asyncio.run(routes.listens_youtube_sync_endpoint())
    assert err.value.status_code == 401
    assert routes.listens_youtube_status_endpoint() == {'last': 0, 'total': 0}


def test_the_whole_way_from_the_account(monkeypatch):
    class Client:
        def get_history(self):
            return [item('aaaaaaaaaaa', 'Today'), item('bbbbbbbbbbb', 'Last week')]

    monkeypatch.setattr(account, 'client', lambda require_auth=False: Client())
    got = ytm_history.sync()
    assert got['brought'] == 2 and got['last'] > 0
    assert ytm_history.status()['total'] == 2
