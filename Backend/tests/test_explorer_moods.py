"""Moods and genres for Search: shaped for the window, cached, and gentle
with what YouTube Music sends back."""

from __future__ import annotations

from dannify import explorer


class _Fake:
    calls = 0

    def get_mood_categories(self):
        type(self).calls += 1
        return {
            'Moods & moments': [{'title': 'Chill', 'params': 'p1'}, {'title': '', 'params': 'x'}],
            'Genres': [{'title': 'African', 'params': 'p2'}, 'not a card'],
            'Empty': [],
        }

    def get_mood_playlists(self, params):
        type(self).calls += 1
        return [
            {'title': 'Hits Café', 'playlistId': 'RDCLAK1', 'thumbnails': [{'url': 'https://x/1.jpg'}],
             'description': 'Easy songs'},
            {'title': 'No id'},
        ]


def test_moods_and_their_playlists(monkeypatch):
    fake = _Fake()
    monkeypatch.setattr(explorer, '_ytm', lambda: fake)
    explorer.clear_cache()
    sections = explorer.moods()
    assert [s['title'] for s in sections] == ['Moods & moments', 'Genres']
    assert sections[0]['items'] == [{'title': 'Chill', 'params': 'p1'}]
    cards = explorer.mood_playlists('p1')
    assert cards[0]['browse_id'] == 'RDCLAK1' and cards[0]['name'] == 'Hits Café'
    assert len(cards) == 1
    # Asked again: from the cache.
    before = _Fake.calls
    explorer.moods()
    explorer.mood_playlists('p1')
    assert _Fake.calls == before
    explorer.clear_cache()
