"""A saved artist is linked to the right artist online, or to nobody."""

from __future__ import annotations

from dannify import artist_links


def card(name, bid='UC' + 'x' * 22, photo='https://lh3.googleusercontent.com/p=w600'):
    return {'name': name, 'browse_id': bid, 'cover_url': photo}


def test_the_exact_name_wins_wherever_it_is():
    found = [card('Sauti Sol Band', 'A'), card('Sauti Sol', 'B')]
    assert artist_links._pick('sauti sol', found)['browse_id'] == 'B'


def test_accents_and_case_do_not_matter():
    assert artist_links._pick('Beyonce', [card('Beyoncé', 'B')])['browse_id'] == 'B'


def test_a_different_artist_is_not_taken():
    # "Drake" searched, the top hit is Drake Bell: no link rather than the wrong one.
    assert artist_links._pick('Drake', [card('Drake Bell', 'A')]) is None
    assert artist_links._pick('Nobody', []) is None


def test_a_spelling_apart_only_when_it_is_the_top_hit():
    assert artist_links._pick('Stephen Kasolo', [card('Stephen Kasolo Kitole', 'A')])['browse_id'] == 'A'


def test_known_and_link_use_the_cache(tmp_path, monkeypatch):
    artist_links._links.clear()
    artist_links.init(tmp_path)
    calls = []

    def fake_look_up(name, hint=None):
        calls.append(name)
        return {'id': 'UC1', 'photo': 'p', 'name': name, 't': 1e12}

    monkeypatch.setattr(artist_links, '_look_up', fake_look_up)
    assert artist_links.link('Bensoul')['id'] == 'UC1'
    assert artist_links.link('BENSOUL')['id'] == 'UC1'  # same artist, cached
    assert calls == ['Bensoul']
    got, pending = artist_links.known(['Bensoul'])
    assert got == {'Bensoul': {'id': 'UC1', 'photo': 'p'}} and pending == 0
    # Saved to disk, and read back by the next start.
    artist_links._links.clear()
    artist_links.init(tmp_path)
    assert artist_links.known(['bensoul'])[0]['bensoul']['id'] == 'UC1'
    artist_links._links.clear()


def test_an_unreachable_search_is_not_a_miss(monkeypatch, tmp_path):
    # Offline, or refused: tried again later, not written off for a week.
    from dannify import explorer

    artist_links._links.clear()
    artist_links.init(tmp_path)

    def offline(name, limit=6):
        raise ConnectionError('no network')

    monkeypatch.setattr(explorer, 'search_artists', offline)
    assert artist_links.link('Bensoul') is None
    assert artist_links._links == {}

    monkeypatch.setattr(explorer, 'search_artists', lambda name, limit=6: [card('Bensoul', 'UC9')])
    assert artist_links.link('Bensoul')['id'] == 'UC9'
    artist_links._links.clear()


def test_the_no_artist_bucket_is_never_looked_up(monkeypatch):
    calls = []
    monkeypatch.setattr(artist_links, '_look_up', lambda name, hint=None: calls.append(name) or {})
    assert artist_links.link('Unknown Artist') is None
    assert artist_links.known(['Unknown Artist']) == ({}, 0)
    assert calls == []


def test_looking_again_keeps_the_picture_until_the_new_one_arrives(monkeypatch, tmp_path):
    import threading

    artist_links._links.clear()
    artist_links.init(tmp_path)
    monkeypatch.setattr(artist_links, '_look_up', lambda name, hint=None: {'id': 'UC1', 'photo': 'old', 'name': name, 't': 1e12, 'v': 2})
    assert artist_links.link('Bensoul')['photo'] == 'old'

    gate = threading.Event()

    def slow(name, hint=None):
        gate.wait(5)
        return {'id': 'UC1', 'photo': 'new', 'name': name, 't': 1e12, 'v': 2}

    monkeypatch.setattr(artist_links, '_look_up', slow)
    assert artist_links.relook(['Bensoul']) == 1
    links, pending = artist_links.known(['Bensoul'])
    assert links['Bensoul']['photo'] == 'old' and pending == 1  # still there, still coming
    gate.set()
    for _ in range(50):
        links, pending = artist_links.known(['Bensoul'])
        if not pending:
            break
        threading.Event().wait(0.05)
    assert pending == 0 and links['Bensoul']['photo'] == 'new'
    artist_links._links.clear()


# --- who an artist is: their songs first, their name last ------------------

MAVOKALI_VIDEOS = 'UCKQXLM0qgmnIRJXUW3cRRqg'  # a channel of videos, first in a search
MAVOKALI_SONGS = 'UCkHOC2q8HVjFjPReLcdqUMg'  # the one the songs credit


def _no_search(name, limit=6):
    raise AssertionError('searched by name although the songs said who it is')


def test_an_id_the_songs_recorded_wins_over_a_search(monkeypatch, tmp_path):
    from dannify import explorer

    artist_links._links.clear()
    artist_links.init(tmp_path)
    monkeypatch.setattr(explorer, 'search_artists', _no_search)
    monkeypatch.setattr(explorer, 'artist_brief', lambda bid: {'name': 'Mavokali', 'cover_url': 'photo-' + bid})
    got = artist_links.link('Mavokali', {'ids': [MAVOKALI_SONGS], 'videos': []})
    assert got['id'] == MAVOKALI_SONGS and got['photo'] == 'photo-' + MAVOKALI_SONGS
    artist_links._links.clear()


def test_an_older_song_is_asked_who_it_credits(monkeypatch, tmp_path):
    from dannify import explorer

    artist_links._links.clear()
    artist_links.init(tmp_path)
    asked = []

    def credits(video_id):
        asked.append(video_id)
        if video_id == 'unreadable':
            return []
        return [{'name': 'Mavokali', 'id': MAVOKALI_SONGS}, {'name': 'Rayvanny', 'id': 'UCray'}]

    monkeypatch.setattr(explorer, 'search_artists', _no_search)
    monkeypatch.setattr(explorer, 'artists_of_video', credits)
    monkeypatch.setattr(explorer, 'artist_brief', lambda bid: {'name': 'Mavokali', 'cover_url': 'p'})
    got = artist_links.link('Mavokali', {'ids': [], 'videos': ['unreadable', 'ESDRDrvCQ_Y']})
    assert got['id'] == MAVOKALI_SONGS and asked == ['unreadable', 'ESDRDrvCQ_Y']
    artist_links._links.clear()


def test_a_name_search_is_the_last_resort(monkeypatch, tmp_path):
    from dannify import explorer

    artist_links._links.clear()
    artist_links.init(tmp_path)
    monkeypatch.setattr(explorer, 'artists_of_video', lambda vid: [])
    monkeypatch.setattr(explorer, 'search_artists', lambda name, limit=6: [card('Mavokali', MAVOKALI_VIDEOS)])
    assert artist_links.link('Mavokali', {'ids': [], 'videos': ['x']})['id'] == MAVOKALI_VIDEOS
    artist_links._links.clear()


def test_a_wrong_link_from_before_is_put_right_without_a_gap(monkeypatch, tmp_path):
    """The library of a user who saved Mavokali before: linked by name to the
    channel of videos. The songs say otherwise; the old link stands until the
    right one is in, then the right one is kept for good."""

    import threading

    artist_links._links.clear()
    artist_links.init(tmp_path)
    artist_links._links['mavokali'] = {'id': MAVOKALI_VIDEOS, 'photo': 'old', 'name': 'Mavokali', 't': 1e12}
    gate = threading.Event()
    calls = []

    def look_up(name, hint=None):
        calls.append(hint)
        gate.wait(5)
        return {'id': MAVOKALI_SONGS, 'photo': 'right', 'name': name, 't': 1e12, 'v': 2, 'src': 'songs'}

    monkeypatch.setattr(artist_links, '_look_up', look_up)
    hints = {'Mavokali': {'ids': [], 'videos': ['ESDRDrvCQ_Y']}}
    links, pending = artist_links.known(['Mavokali'], hints)
    assert links['Mavokali']['id'] == MAVOKALI_VIDEOS and pending == 1  # no gap meanwhile
    gate.set()
    for _ in range(50):
        links, pending = artist_links.known(['Mavokali'], hints)
        if not pending:
            break
        threading.Event().wait(0.05)
    assert pending == 0 and links['Mavokali'] == {'id': MAVOKALI_SONGS, 'photo': 'right'}
    # Asked once: an answer the songs agree with is not looked up again.
    artist_links.known(['Mavokali'], hints)
    assert len(calls) == 1
    artist_links._links.clear()


def test_a_link_the_songs_contradict_is_looked_up_again():
    entry = {'id': MAVOKALI_VIDEOS, 'v': 2}
    assert artist_links._outdated(entry, {'ids': [MAVOKALI_SONGS], 'videos': []})
    assert not artist_links._outdated(entry, {'ids': [MAVOKALI_VIDEOS], 'videos': []})
    assert not artist_links._outdated(entry, {'ids': [], 'videos': ['v']})  # already asked
    assert artist_links._outdated({'id': MAVOKALI_VIDEOS}, {'ids': [], 'videos': ['v']})  # from before
    assert not artist_links._outdated({'id': MAVOKALI_VIDEOS}, None)  # nothing to go on
