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

    def fake_look_up(name):
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
    monkeypatch.setattr(artist_links, '_look_up', lambda name: calls.append(name) or {})
    assert artist_links.link('Unknown Artist') is None
    assert artist_links.known(['Unknown Artist']) == ({}, 0)
    assert calls == []
